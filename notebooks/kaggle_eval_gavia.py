"""Cross-dataset evaluation of the deployed detector on the Gavia mine corpus.

Run it with two lines in one Kaggle code cell:

    !curl -sL https://raw.githubusercontent.com/tyagisuryansh54-design/wreckognise/main/notebooks/kaggle_eval_gavia.py -o eval.py
    !python eval.py

Needs Internet on. A GPU helps but is not required -- the bottleneck is the
OpenCV denoise on CPU, not the network.

WHAT THIS MEASURES, AND WHY NOT mAP
-----------------------------------
The Gavia corpus (Pessanha Santos & Moura, 1,170 images, Teledyne Gavia AUV,
2010-2021, CC BY 4.0) labels MILCO and NOMBO. The deployed model knows
aircraft, human and ship. Those vocabularies do not overlap, so a per-class mAP
would be a number with no meaning attached.

Two things are measurable and both matter:

  1. FALSE POSITIVES on the empty frames. Nothing is there, so every box is
     wrong regardless of what it is called. This is the failure the
     AI4Shipwrecks run exposed -- 33 false positives on 170 empty tiles -- and
     this corpus has 866 empty frames to test it against properly.

  2. CLASS-AGNOSTIC RECALL on the annotated frames. Ignoring the label, does
     the detector look in the right place? That separates "cannot see it" from
     "sees it, names it wrong" -- different problems needing different fixes.

Images go through the same preprocessing the served API applies, by importing
the repository's own modules rather than reimplementing them. A second
implementation that drifts from production would measure something that is not
deployed, which is how the CLAHE train/serve mismatch went unnoticed.
"""

from __future__ import annotations

import os
import subprocess
import sys
import zipfile
from pathlib import Path

WORK = Path("/kaggle/working")
REPO = WORK / "wreckognise"
DATA = WORK / "gavia"
CONF = float(os.environ.get("WRECK_CONF", "0.35"))       # the dashboard default
DENOISE = os.environ.get("WRECK_DENOISE", "nlm")         # what production uses
IOU_HIT = 0.10   # generous: asking "did it look here", not "how tight is the box"

# Figshare file ids for DOI 10.6084/m9.figshare.24574879. Training.zip is
# skipped -- it is the authors' YOLOv4 weights, not data.
FIGSHARE = {
    "2010.zip": 43169008,
    "2015.zip": 43169002,
    "2017.zip": 43169005,
    "2018.zip": 43169011,
    "2021.zip": 43168999,
}


def step(msg: str) -> None:
    print(f"\n{'=' * 64}\n  {msg}\n{'=' * 64}", flush=True)


def sh(*args: str) -> None:
    subprocess.run(list(args), check=True)


def setup() -> None:
    step("1/3  fetch code, model and data")

    try:
        import cv2, onnxruntime  # noqa: F401
    except ImportError:
        sh(sys.executable, "-m", "pip", "-q", "install",
           "opencv-python-headless", "onnxruntime", "pydantic", "pydantic-settings")

    if not REPO.exists():
        sh("git", "clone", "-q", "--depth", "1",
           "https://github.com/tyagisuryansh54-design/wreckognise.git", str(REPO))
    print("  repo + deployed weights:", (REPO / "backend/models/yolov8n-sonar.onnx").stat().st_size // 1024, "KB")

    DATA.mkdir(parents=True, exist_ok=True)
    for name, file_id in FIGSHARE.items():
        target = DATA / name
        if target.exists():
            continue
        print(f"  downloading {name}...", flush=True)
        sh("curl", "-sL", f"https://ndownloader.figshare.com/files/{file_id}", "-o", str(target))
        with zipfile.ZipFile(target) as z:
            z.extractall(DATA)
    print("  images:", len(list(DATA.rglob("*.jpg"))))


def load_labels(path: Path):
    """YOLO normalised cx,cy,w,h. Class deliberately ignored."""
    if not path.is_file():
        return []
    out = []
    for line in path.read_text().strip().splitlines():
        parts = line.split()
        if len(parts) >= 5:
            out.append(tuple(float(v) for v in parts[1:5]))
    return out


def iou(a, b) -> float:
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / max(union, 1e-9)


def evaluate() -> None:
    step(f"2/3  evaluate  (conf {CONF}, denoise {DENOISE})")
    sys.path.insert(0, str(REPO / "backend"))
    import cv2
    from app.services import onnx_detector
    from app.services.preprocessing import preprocess

    if not onnx_detector.is_available():
        raise SystemExit("  trained weights did not load")

    images = sorted(DATA.rglob("*.jpg"))
    empty_n = empty_fp = empty_hit = 0
    pos_n = pos_found = gt_total = gt_hit = 0
    by_year: dict[str, list[int]] = {}

    for i, path in enumerate(images, 1):
        if i % 200 == 0:
            print(f"    {i}/{len(images)}", flush=True)
        raw = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if raw is None:
            continue
        _display, detect_input, _stats = preprocess(raw, method=DENOISE)
        dets = onnx_detector.detect(detect_input, conf_threshold=CONF)
        pred = [(d["x"], d["y"], d["x"] + d["w"], d["y"] + d["h"]) for d in dets]

        h, w = raw.shape[:2]
        truth = [((cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w, (cy + bh / 2) * h)
                 for cx, cy, bw, bh in load_labels(path.with_suffix(".txt"))]

        slot = by_year.setdefault(path.parent.name, [0, 0, 0])
        slot[0] += 1
        if not truth:
            empty_n += 1
            empty_fp += len(pred)
            empty_hit += 1 if pred else 0
        else:
            pos_n += 1
            found = False
            for t in truth:
                gt_total += 1
                slot[1] += 1
                if any(iou(t, p) >= IOU_HIT for p in pred):
                    gt_hit += 1
                    slot[2] += 1
                    found = True
            pos_found += 1 if found else 0

    step("3/3  results")
    print("  EMPTY FRAMES -- nothing is there, so every box is a false positive")
    print(f"    frames                {empty_n}")
    print(f"    frames with a box     {empty_hit}  ({100 * empty_hit / max(empty_n, 1):.1f}%)")
    print(f"    false positives       {empty_fp}   ({empty_fp / max(empty_n, 1):.3f} per frame)")

    print("\n  ANNOTATED FRAMES -- class-agnostic: did it look in the right place")
    print(f"    frames                {pos_n}")
    print(f"    frames with >=1 hit   {pos_found}  ({100 * pos_found / max(pos_n, 1):.1f}%)")
    print(f"    ground-truth objects  {gt_total}")
    print(f"    objects localised     {gt_hit}  (recall {100 * gt_hit / max(gt_total, 1):.1f}%)")

    print("\n  BY COLLECTION YEAR")
    for year in sorted(by_year):
        frames, gt, hits = by_year[year]
        rec = f"{100 * hits / gt:.0f}%" if gt else "   -"
        print(f"    {year}   frames {frames:4}   objects {gt:4}   recall {rec:>4}")

    print("\n  For context, the same model on its own held-out SCTD split scores")
    print("  0.839 mAP@0.5, and 0.203 on AI4Shipwrecks. This is a third corpus.")


if __name__ == "__main__":
    setup()
    evaluate()
