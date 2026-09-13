"""ONNX inference backend for the trained YOLOv8 sonar detector.

The deployed API runs on a 512 MB instance. PyTorch plus ultralytics needs
several gigabytes resident, so the trained weights are exported to ONNX and
served through onnxruntime instead -- roughly 50 MB of dependencies and no
autograd machinery.

This module owns only the network: letterboxing in, raw boxes out. Confidence
calibration, georeferencing and severity assignment stay in `detector.py`, so
both the ONNX path and the CV fallback produce the same contract.
"""

from __future__ import annotations

import threading
from pathlib import Path

import cv2
import numpy as np

try:  # pragma: no cover - optional dependency
    import onnxruntime as ort

    ONNX_AVAILABLE = True
except ImportError:  # pragma: no cover
    ort = None
    ONNX_AVAILABLE = False


# Class order must match the `names:` block in the training data.yaml.
CLASS_NAMES = ("aircraft", "human", "ship")

_session: "ort.InferenceSession | None" = None
_session_lock = threading.Lock()
_input_name: str | None = None
_input_size: int = 512


def weights_path() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "models" / "yolov8n-sonar.onnx"


def is_available() -> bool:
    return ONNX_AVAILABLE and weights_path().is_file()


def _load() -> "ort.InferenceSession":
    """Lazily build the session once; onnxruntime sessions are thread-safe."""
    global _session, _input_name, _input_size
    if _session is None:
        with _session_lock:
            if _session is None:
                options = ort.SessionOptions()
                # One thread per core is counterproductive on a shared 0.5 vCPU
                # instance; two keeps latency low without starving the server.
                options.intra_op_num_threads = 2
                options.graph_optimization_level = (
                    ort.GraphOptimizationLevel.ORT_ENABLE_ALL
                )
                session = ort.InferenceSession(
                    str(weights_path()), options, providers=["CPUExecutionProvider"]
                )
                shape = session.get_inputs()[0].shape
                # Static export gives [1, 3, H, W]; fall back to 512 if dynamic.
                if isinstance(shape[-1], int):
                    _input_size = int(shape[-1])
                _input_name = session.get_inputs()[0].name
                _session = session
    return _session


def _letterbox(image: np.ndarray, size: int) -> tuple[np.ndarray, float, int, int]:
    """Resize preserving aspect ratio and pad to a square, as YOLO expects."""
    h, w = image.shape[:2]
    scale = min(size / w, size / h)
    new_w, new_h = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

    canvas = np.full((size, size), 114, dtype=np.uint8)
    pad_x, pad_y = (size - new_w) // 2, (size - new_h) // 2
    canvas[pad_y : pad_y + new_h, pad_x : pad_x + new_w] = resized
    return canvas, scale, pad_x, pad_y


def detect(image: np.ndarray, conf_threshold: float) -> list[dict]:
    """Run the trained network over one grayscale swath.

    Returns proposals in the same dict shape the CV fallback produces, in the
    source image's pixel coordinates.
    """
    session = _load()
    size = _input_size

    padded, scale, pad_x, pad_y = _letterbox(image, size)
    rgb = cv2.cvtColor(padded, cv2.COLOR_GRAY2RGB).astype(np.float32) / 255.0
    tensor = np.transpose(rgb, (2, 0, 1))[None, ...]

    outputs = session.run(None, {_input_name: tensor})[0]

    # YOLOv8 exports as [1, 4 + num_classes, num_anchors].
    predictions = np.squeeze(outputs, axis=0)
    if predictions.shape[0] < predictions.shape[1]:
        predictions = predictions.T  # -> [num_anchors, 4 + num_classes]

    boxes_xywh = predictions[:, :4]
    class_scores = predictions[:, 4:]
    confidences = class_scores.max(axis=1)
    class_ids = class_scores.argmax(axis=1)

    keep = confidences >= conf_threshold
    if not np.any(keep):
        return []

    boxes_xywh = boxes_xywh[keep]
    confidences = confidences[keep]
    class_ids = class_ids[keep]
    # The whole score vector, not just its maximum. The argmax is the answer;
    # the rest of the vector is how close the runners-up came, which is the
    # difference between "a ship" and "a ship, but only just".
    kept_scores = class_scores[keep]

    # Undo letterboxing: centre-xywh in network space -> xywh in image space.
    cx, cy, bw, bh = boxes_xywh.T
    x0 = (cx - bw / 2 - pad_x) / scale
    y0 = (cy - bh / 2 - pad_y) / scale
    w = bw / scale
    h = bh / scale

    height, width = image.shape[:2]
    proposals: list[dict] = []
    for i in range(len(confidences)):
        px = int(max(0, min(width - 1, x0[i])))
        py = int(max(0, min(height - 1, y0[i])))
        pw = int(max(1, min(width - px, w[i])))
        ph = int(max(1, min(height - py, h[i])))
        patch = image[py : py + ph, px : px + pw]
        proposals.append(
            {
                "x": px,
                "y": py,
                "w": pw,
                "h": ph,
                "confidence": float(confidences[i]),
                "raw_class": CLASS_NAMES[int(class_ids[i])]
                if int(class_ids[i]) < len(CLASS_NAMES)
                else "unknown",
                "class_scores": {
                    name: float(kept_scores[i][j])
                    for j, name in enumerate(CLASS_NAMES)
                    if j < kept_scores.shape[1]
                },
                # The network does not measure shadows; detector.py fills this
                # in from the image so height-from-shadow still works.
                "shadow_px": 0,
                "backscatter": float(patch.mean()) if patch.size else 0.0,
            }
        )
    return proposals
