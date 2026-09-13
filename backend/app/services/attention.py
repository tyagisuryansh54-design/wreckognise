"""Eigen-CAM attention maps from the deployed ONNX detector.

WHY NOT GRAD-CAM
----------------
Grad-CAM weights each feature map by the gradient of the class score with
respect to it, which needs backpropagation. This service runs ONNX Runtime
precisely because it is forward-only and fits in 512 MB; adding PyTorch to get
gradients would cost several gigabytes of resident memory to explain a
prediction we can already explain another way.

Eigen-CAM needs no gradients. It takes the activations of one convolutional
layer, treats each spatial location as a vector of channel responses, and
projects onto the first principal component -- the single direction that
explains the most variance across the feature map. Where the network's response
is strongest and most distinctive, that projection is large.

HOW THE FEATURE MAP IS OBTAINED
-------------------------------
The exported graph emits only boxes and scores. Rather than re-export from the
.pt (which would need PyTorch again), the ONNX graph is loaded once and the
neck's P3 tensor is appended to its outputs. That is a pure graph edit: the
same weights, the same arithmetic, one more tensor returned. The probe model is
built lazily and held in memory, so the served detector is untouched.

P3 is chosen deliberately -- it is the highest-resolution neck output (64x64
for a 512 input), so the map has enough spatial detail to localise within a
contact rather than merely pointing at its general area.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import cv2
import numpy as np

from . import onnx_detector

logger = logging.getLogger("wreckognise")

# The neck's highest-resolution output, feeding the detect head.
FEATURE_TENSOR = "/model.15/cv2/act/Mul_output_0"

_lock = threading.Lock()
_session = None
_input_name: str | None = None
_unavailable = False


def _build_probe():
    """Load the deployed graph and expose the P3 feature map as an output."""
    global _session, _input_name, _unavailable
    if _session is not None or _unavailable:
        return _session

    with _lock:
        if _session is not None or _unavailable:
            return _session
        try:
            import onnx
            import onnxruntime as ort
            from onnx import TensorProto, helper

            weights = onnx_detector.weights_path()
            model = onnx.load(str(weights))
            existing = {o.name for o in model.graph.output}
            if FEATURE_TENSOR not in existing:
                model.graph.output.append(
                    helper.make_tensor_value_info(FEATURE_TENSOR, TensorProto.FLOAT, None)
                )
            _session = ort.InferenceSession(
                model.SerializeToString(), providers=["CPUExecutionProvider"]
            )
            _input_name = _session.get_inputs()[0].name
            logger.info("attention | eigen-cam probe ready on %s", FEATURE_TENSOR)
        except Exception as exc:  # noqa: BLE001
            # Explanation is a nice-to-have. If the graph shape ever changes,
            # detection must keep working -- so this degrades to unavailable
            # rather than taking the inference path down with it.
            _unavailable = True
            logger.warning("attention | unavailable: %s", exc)
    return _session


def is_available() -> bool:
    return _build_probe() is not None


def _eigen_cam(feature: np.ndarray) -> np.ndarray:
    """First principal component of the channel responses, normalised 0..1."""
    channels, height, width = feature.shape
    flat = feature.reshape(channels, -1).T.astype(np.float32)   # pixels x channels
    flat -= flat.mean(axis=0, keepdims=True)
    # SVD rather than a full covariance eigendecomposition: 4096x64 is small,
    # and this avoids forming a 64x64 covariance matrix that adds nothing.
    _u, _s, vt = np.linalg.svd(flat, full_matrices=False)
    cam = (flat @ vt[0]).reshape(height, width)
    cam = np.abs(cam)
    span = float(np.ptp(cam))
    return (cam - cam.min()) / (span + 1e-9)


def heatmap(image: np.ndarray, bbox: tuple[int, int, int, int] | None = None) -> np.ndarray | None:
    """A BGR heat map the size of `image`, or of `bbox` within it.

    Returns None when the probe could not be built, so callers can fall back to
    showing the detection without an explanation rather than failing.
    """
    session = _build_probe()
    if session is None:
        return None

    # Identical preprocessing to the detector, by calling the detector's own
    # letterbox. A second implementation here would drift, and the heat map
    # would then explain a slightly different image to the one that was scored.
    onnx_detector._load()
    size = onnx_detector._input_size
    padded, ratio, pad_x, pad_y = onnx_detector._letterbox(image, size)
    rgb = cv2.cvtColor(padded, cv2.COLOR_GRAY2RGB).astype(np.float32) / 255.0
    tensor = np.transpose(rgb, (2, 0, 1))[None, ...]

    outputs = session.run(None, {_input_name: tensor})
    feature = outputs[-1][0]                       # C x H x W
    cam = _eigen_cam(feature)

    # Back to letterboxed pixels, then strip the padding and undo the scale, so
    # the map lands on the original image rather than on the padded copy.
    cam = cv2.resize(cam, (size, size), interpolation=cv2.INTER_LINEAR)
    h, w = image.shape[:2]
    x0, y0 = int(round(pad_x)), int(round(pad_y))
    x1, y1 = x0 + int(round(w * ratio)), y0 + int(round(h * ratio))
    cam = cam[y0:y1, x0:x1]
    if cam.size == 0:
        return None
    cam = cv2.resize(cam, (w, h), interpolation=cv2.INTER_LINEAR)

    if bbox is not None:
        bx, by, bw, bh = bbox
        bx, by = max(0, bx), max(0, by)
        crop = cam[by:by + bh, bx:bx + bw]
        if crop.size == 0:
            return None
        # Renormalise within the crop: a contact's own strongest region is the
        # useful signal, not how it compares to the brightest thing in the swath.
        span = float(np.ptp(crop))
        cam = (crop - crop.min()) / (span + 1e-9)

    coloured = cv2.applyColorMap((cam * 255).astype(np.uint8), cv2.COLORMAP_JET)
    return coloured
