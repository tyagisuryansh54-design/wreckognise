"""Raise the deployed model's score without changing what the score means.

    !curl -sL https://raw.githubusercontent.com/tyagisuryansh54-design/wreckognise/main/notebooks/kaggle_train_v4.py -o train4.py
    !python train4.py

Requires: Settings -> Accelerator -> GPU, Internet -> On. AI4Shipwrecks
attached as an input is optional; it is used for EVALUATION ONLY here.

What this run changes, and why each is the thing that moves the number
------------------------------------------------------------------------
The deployed model scores 0.839 mAP@0.5 on the SCTD held-out split. That is
the mean of three per-class APs:

    aircraft  0.9875   (57 training images)
    ship      0.9748   (266)
    human     0.5559   (34)   <- this is the whole gap

Three previous runs changed the backbone, the resolution and the corpus and
moved the headline by about a point each way. None touched the class that is
half-broken from 34 examples. So:

1. OVERSAMPLE the scarce class, in the TRAIN split only. Every training image
   that contains a `human` box is duplicated OVERSAMPLE times, so the model
   sees that class as often per epoch as the others. The held-out split is
   never touched; a duplicate that leaked into validation would inflate the
   score while measuring nothing.

2. SONAR-CORRECT augmentation. The previous recipe rotated images by up to 5
   degrees and forbade vertical flips. Both are backwards for side-scan: a
   rotation tilts the nadir line, which cannot happen; a vertical flip merely
   reverses the direction of travel, and shadows still fall across-track, away
   from the sonar. Rotation off, both flips on -- a free, physically valid
   doubling of the data. No hue or saturation (single-channel intensity),
   gain variation kept.

3. LONGER training with early stopping, so the run ends when validation stops
   improving rather than at a round number.

4. SAME split, SAME classes, SAME export contract. The split is the stratified
   80/20 with the same seed and ordering the previous runs used, so the new
   number is comparable to 0.839 rather than a different exam. The ONNX drops
   into backend/models/ unchanged, and metrics.json has the shape the
   dashboard already reads.

AI4Shipwrecks is NOT trained on. That keeps it a genuine zero-shot benchmark,
which is what the 0.203 the project publishes for it is.

5. MORE DATA FOR THE SCARCE CLASS, if it is attached. AquaScan-1K (Zenodo
   10.5281/zenodo.18771165, MIT) is 1,033 side-scan images of human targets in
   YOLO format, single class. Attach it as a Kaggle input and every image goes
   into the TRAIN split as `human` -- thirty times the 34 examples the class
   had. The held-out SCTD split is still the exam, so the number stays
   comparable. Detected by shape (images/ + labels/ + classes.txt), so the
   dataset slug does not matter.

Knobs (environment variables):
    WRECK_MODEL       yolov8n.pt (default, drop-in)  |  yolo11n.pt  |  yolo11s.pt
    WRECK_IMGSZ       640
    WRECK_EPOCHS      200
    WRECK_OVERSAMPLE  5     duplicates per human-containing SCTD training image
    WRECK_AQUASCAN=0        ignore an attached AquaScan-1K
    WRECK_RESET=1     rebuild everything from scratch
"""

from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

WORK = Path("/kaggle/working")

MODEL = os.environ.get("WRECK_MODEL", "yolov8n.pt")
IMGSZ = int(os.environ.get("WRECK_IMGSZ", "640"))
EPOCHS = int(os.environ.get("WRECK_EPOCHS", "200"))
OVERSAMPLE = int(os.environ.get("WRECK_OVERSAMPLE", "5"))
if OVERSAMPLE < 1:
    # 0 would write ZERO copies of every human-containing image and silently
    # remove the class from training while val still contains it.
    raise SystemExit("WRECK_OVERSAMPLE must be >= 1 (1 means no oversampling)")
USE_AQUASCAN = os.environ.get("WRECK_AQUASCAN", "1") != "0"
RESET = os.environ.get("WRECK_RESET") == "1"

# Cache directories carry the knobs they depend on. A dataset built with one
# oversampling factor, or a checkpoint trained with one backbone, must never be
# picked up by a run that asked for another -- ultralytics resumes with the
# checkpoint's own recipe and only the label in metrics.json would change.
_ARCH = Path(MODEL).stem
OUT = WORK / f"dataset4-x{OVERSAMPLE}{'-aq' if USE_AQUASCAN else ''}"
AI4_ONLY = WORK / "ai4_only4"
RUNS, NAME = str(WORK), f"run4-{_ARCH}-x{OVERSAMPLE}-{IMGSZ}{'-aq' if USE_AQUASCAN else ''}"

# Same order as backend/app/services/onnx_detector.py CLASS_NAMES. The export
# is a drop-in only while this holds.
CLASSES = ["aircraft", "human", "ship"]
SHIP_ID = CLASSES.index("ship")
RARE = "human"

TILE, STRIDE = 512, 384
MIN_BLOB_PX, MIN_BOX_PX, NEG_RATIO = 60, 12, 0.6

# The numbers to beat, from backend/models/metrics.json for the deployed model.
# Measured at 512 px; the like-for-like comparison below is made at 512 too.
DEPLOYED = {
    "sctd_map50": 0.8394,
    "per_class": {"aircraft": 0.9875, "human": 0.5559, "ship": 0.9748},
    "ai4_zero_shot_map50": 0.2027,
    "imgsz": 512,
}
LIKE_FOR_LIKE_IMGSZ = DEPLOYED["imgsz"]

# The zero-shot tile subset must be a pure function of the AI4 test data, not
# of what consumed the shared rng before it. Separate generator.
AI4_NEG_SEED = 1337

# Seeded exactly as the previous runs were, and consumed in the same order, so
# the held-out split is the same 20%.
rng = random.Random(1337)


def step(n: str) -> None:
    print(f"\n{'=' * 64}\n  {n}\n{'=' * 64}", flush=True)


# ------------------------------------------------------------------ 1. install
def install() -> None:
    step("1/6  install")
    try:
        import ultralytics  # noqa: F401

        print("  ultralytics already present")
        return
    except ImportError:
        pass
    subprocess.run(
        [sys.executable, "-m", "pip", "-q", "install", "ultralytics", "onnx", "onnxslim"],
        check=True,
    )
    print("  installed")


# ------------------------------------------------------------------ 2. data
def find_ai4shipwrecks(root=Path("/kaggle/input")):
    """Locate the dataset by SHAPE, not by name: a dir holding train/images + train/labels."""
    if not root.exists():
        return None, None
    for cand in root.rglob("train"):
        if (cand / "images").is_dir() and (cand / "labels").is_dir():
            return cand.parent, None
    for cand in root.rglob("*.zip"):
        if "ai4" in cand.name.lower() or "shipwreck" in cand.name.lower():
            return None, cand
    return None, None


def find_aquascan(root=Path("/kaggle/input")):
    """AquaScan-1K by SHAPE: a directory holding images/, labels/ and classes.txt.

    Distinguished from AI4Shipwrecks (which has train/images) by the flat
    layout and the single-class classes.txt.
    """
    if not root.exists():
        return None

    def scan(base: Path):
        for cand in base.rglob("classes.txt"):
            d = cand.parent
            if (d / "images").is_dir() and (d / "labels").is_dir():
                names = [ln.strip().lower() for ln in cand.read_text(errors="ignore").splitlines() if ln.strip()]
                if names and names[0] in ("human", "person", "body"):
                    return d
        return None

    found = scan(root)
    if found is not None:
        return found
    # Kaggle extracts uploaded zips, but a raw archive attached as-is would
    # otherwise be found by nothing. Same fallback the AI4Shipwrecks finder has.
    for zp in root.rglob("*.zip"):
        if "aquascan" in zp.name.lower():
            dest = WORK / "aquascan"
            if not dest.exists():
                print(f"  extracting {zp.name} ...")
                with zipfile.ZipFile(zp) as z:
                    z.extractall(dest)
            return scan(dest)
    return None


def fetch() -> Path | None:
    step("2/6  fetch")
    sctd = WORK / "sctd"
    # A marker written only after extractall returns. Checking for "any jpg"
    # let a session that died mid-extract pass with a partial corpus -- and a
    # partial corpus produces a different, smaller held-out split that looks
    # like a real score.
    done = sctd / ".extracted"
    if RESET or not done.is_file():
        shutil.rmtree(sctd, ignore_errors=True)
        shutil.rmtree(WORK / "sctd_repo", ignore_errors=True)
        print("  cloning SCTD (needs Internet: On)...")
        subprocess.run(
            ["git", "clone", "-q", "--depth", "1",
             "https://github.com/MingqiangNing/SCTD.git", str(WORK / "sctd_repo")],
            check=True,
        )
        with zipfile.ZipFile(WORK / "sctd_repo/SCTD.zip") as z:
            z.extractall(sctd)
        done.write_text("ok")
    print("  SCTD images:", len(list(sctd.rglob("*.jpg"))),
          "| annotations:", len(list(sctd.rglob("*.xml"))))

    pre, zp = find_ai4shipwrecks()
    ai4 = WORK / "ai4sw/AI4Shipwrecks"
    if ai4.exists():
        print("  AI4Shipwrecks available (evaluation only)")
    elif pre is not None:
        ai4.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(pre, ai4)
        print("  AI4Shipwrecks linked from", pre, "(evaluation only)")
    elif zp is not None:
        print("  extracting AI4Shipwrecks...")
        with zipfile.ZipFile(zp) as z:
            z.extractall(WORK / "ai4sw")
    else:
        print("  AI4Shipwrecks not attached: zero-shot transfer will not be measured")
        return None
    return ai4 if ai4.exists() else None


# ------------------------------------------------------------------ 3. build
def parse_voc(path: Path):
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return None, None, []
    size = root.find("size")
    if size is None:
        return None, None, []
    w, h = int(float(size.findtext("width"))), int(float(size.findtext("height")))
    out = []
    for obj in root.findall("object"):
        name = (obj.findtext("name") or "").strip().lower()
        bb = obj.find("bndbox")
        if not name or bb is None or name not in CLASSES:
            continue
        x0, y0 = float(bb.findtext("xmin")), float(bb.findtext("ymin"))
        x1, y1 = float(bb.findtext("xmax")), float(bb.findtext("ymax"))
        x0, x1 = sorted((max(0, x0), min(w, x1)))
        y0, y1 = sorted((max(0, y0), min(h, y1)))
        if x1 - x0 >= 2 and y1 - y0 >= 2:
            out.append((name, x0, y0, x1, y1))
    return w, h, out


def _yolo_lines(w, h, boxes):
    return "\n".join(
        f"{CLASSES.index(n)} {((x0 + x1) / 2) / w:.6f} {((y0 + y1) / 2) / h:.6f}"
        f" {(x1 - x0) / w:.6f} {(y1 - y0) / h:.6f}"
        for n, x0, y0, x1, y1 in boxes
    )


def build(ai4: Path | None, aqua: Path | None = None) -> None:
    step("3/6  build")
    if RESET:
        shutil.rmtree(OUT, ignore_errors=True)
        shutil.rmtree(AI4_ONLY, ignore_errors=True)
    if (OUT / "data.yaml").is_file() and any((OUT / "images/train").glob("*.jpg")):
        print("  already built (WRECK_RESET=1 to rebuild)")
        if aqua is not None and not any((OUT / "images/train").glob("aqua_*")):
            print("  NOTE: AquaScan-1K is attached but this build predates it. WRECK_RESET=1 to include it.")
    else:
        shutil.rmtree(OUT, ignore_errors=True)
        for s in ("train", "val"):
            (OUT / "images" / s).mkdir(parents=True, exist_ok=True)
            (OUT / "labels" / s).mkdir(parents=True, exist_ok=True)

        # --- SCTD: Pascal VOC -> YOLO, stratified 80/20, identical to before ---
        sctd = WORK / "sctd"
        imgs = {p.stem: p for p in sctd.rglob("*.jpg")}
        xmls = {p.stem: p for p in sctd.rglob("*.xml")}
        samples = []
        for k in sorted(imgs.keys() & xmls.keys()):
            w, h, b = parse_voc(xmls[k])
            if w and h and b:
                samples.append((k, w, h, b))

        by_cls = defaultdict(list)
        for entry in samples:
            by_cls[Counter(x[0] for x in entry[3]).most_common(1)[0][0]].append(entry)
        train, val = [], []
        for entries in by_cls.values():
            rng.shuffle(entries)
            cut = max(1, round(len(entries) * 0.2))
            val += entries[:cut]
            train += entries[cut:]

        for k, w, h, boxes in val:
            shutil.copy2(imgs[k], OUT / "images/val" / f"{k}.jpg")
            (OUT / "labels/val" / f"{k}.txt").write_text(_yolo_lines(w, h, boxes))

        # --- oversample the scarce class, TRAIN ONLY ---
        dup_images = 0
        for k, w, h, boxes in train:
            lines = _yolo_lines(w, h, boxes)
            copies = 1 + (OVERSAMPLE - 1 if any(n == RARE for n, *_ in boxes) else 0)
            for i in range(copies):
                stem = k if i == 0 else f"{k}_x{i}"
                shutil.copy2(imgs[k], OUT / "images/train" / f"{stem}.jpg")
                (OUT / "labels/train" / f"{stem}.txt").write_text(lines)
            dup_images += copies - 1

        def class_image_counts(entries):
            c = Counter()
            for _, _, _, boxes in entries:
                for name in {n for n, *_ in boxes}:
                    c[name] += 1
            return c

        # --- AquaScan-1K: every image into TRAIN as `human`, never into val ---
        aqua_added = 0
        if aqua is not None:
            human_id = CLASSES.index("human")
            for ip in sorted((aqua / "images").iterdir()):
                if ip.suffix.lower() not in (".png", ".jpg", ".jpeg"):
                    continue
                lp = aqua / "labels" / f"{ip.stem}.txt"
                if not lp.is_file():
                    continue
                rows = []
                for ln in lp.read_text(errors="ignore").splitlines():
                    parts = ln.split()
                    if len(parts) != 5:
                        continue
                    # Single-class file: whatever id it uses, it means human here.
                    rows.append(f"{human_id} " + " ".join(parts[1:]))
                if not rows:
                    continue
                stem = f"aqua_{ip.stem}"
                shutil.copy2(ip, OUT / "images/train" / f"{stem}{ip.suffix.lower()}")
                (OUT / "labels/train" / f"{stem}.txt").write_text("\n".join(rows))
                aqua_added += 1
            print(f"  AquaScan-1K -> train: {aqua_added} human images added (val untouched)")

        tr, va = class_image_counts(train), class_image_counts(val)
        print(f"  SCTD split -> train {len(train)} | val {len(val)}  (val untouched)")
        print("  images containing each class:")
        for c in CLASSES:
            seen = tr[c] * (OVERSAMPLE if c == RARE else 1) + (aqua_added if c == RARE else 0)
            print(f"    {c:<9} train {tr[c]:>3}  -> after oversampling {seen:>4}   | val {va[c]:>3}")
        print(f"  {dup_images} duplicate training images written for '{RARE}' (x{OVERSAMPLE})")

        (OUT / "data.yaml").write_text(
            f"path: {OUT}\ntrain: images/train\nval: images/val\n\nnames:\n"
            + "".join(f"  {i}: {c}\n" for i, c in enumerate(CLASSES))
        )

    # --- AI4Shipwrecks test tiles, evaluation only, never trained on ---
    if ai4 is not None and not (AI4_ONLY / "data.yaml").is_file():
        import cv2
        import numpy as np

        for s in ("train", "val"):
            (AI4_ONLY / "images" / s).mkdir(parents=True, exist_ok=True)
            (AI4_ONLY / "labels" / s).mkdir(parents=True, exist_ok=True)

        def mask_boxes(m):
            n, _, st, _ = cv2.connectedComponentsWithStats((m > 0).astype(np.uint8), 8)
            return [tuple(int(v) for v in st[i][:4]) for i in range(1, n)
                    if st[i][4] >= MIN_BLOB_PX and st[i][2] >= 4 and st[i][3] >= 4]

        pos, neg = [], []
        for ip in sorted((ai4 / "test" / "images").glob("*.png")):
            im = cv2.imread(str(ip), cv2.IMREAD_GRAYSCALE)
            mk = cv2.imread(str(ai4 / "test" / "labels" / ip.name), cv2.IMREAD_GRAYSCALE)
            if im is None or mk is None:
                continue
            if mk.shape != im.shape:
                mk = cv2.resize(mk, (im.shape[1], im.shape[0]), interpolation=cv2.INTER_NEAREST)
            boxes = mask_boxes(mk)
            H, W = im.shape
            for top in range(0, max(1, H - TILE + 1), STRIDE):
                for left in range(0, max(1, W - TILE + 1), STRIDE):
                    bot, right = min(top + TILE, H), min(left + TILE, W)
                    if bot - top < TILE // 2 or right - left < TILE // 2:
                        continue
                    local = []
                    for bx, by, bw, bh in boxes:
                        ix0, iy0 = max(bx, left), max(by, top)
                        ix1, iy1 = min(bx + bw, right), min(by + bh, bot)
                        if ix1 - ix0 < MIN_BOX_PX or iy1 - iy0 < MIN_BOX_PX:
                            continue
                        if (ix1 - ix0) * (iy1 - iy0) < 0.35 * bw * bh:
                            continue
                        local.append((ix0 - left, iy0 - top, ix1 - ix0, iy1 - iy0))
                    (pos if local else neg).append((ip, left, top, right - left, bot - top, local))
        random.Random(AI4_NEG_SEED).shuffle(neg)
        neg = neg[: int(len(pos) * NEG_RATIO)]
        if not pos:
            print("  AI4Shipwrecks: no labelled test tiles found (expected test/images + "
                  "test/labels/<image>.png); cross-dataset NOT measured")
            shutil.rmtree(AI4_ONLY, ignore_errors=True)
        for i, (ip, left, top, tw, th, boxes) in enumerate(pos + neg):
            im = cv2.imread(str(ip), cv2.IMREAD_GRAYSCALE)
            stem = f"ai4_{ip.stem}_{left}_{top}_{i}"
            cv2.imwrite(str(AI4_ONLY / "images/val" / f"{stem}.jpg"), im[top:top + th, left:left + tw])
            (AI4_ONLY / "labels/val" / f"{stem}.txt").write_text("\n".join(
                f"{SHIP_ID} {(bx + bw / 2) / tw:.6f} {(by + bh / 2) / th:.6f}"
                f" {bw / tw:.6f} {bh / th:.6f}" for bx, by, bw, bh in boxes))
        if pos:
            # Ultralytics insists a train path exists; two tiles, never trained on.
            for p in sorted((AI4_ONLY / "images/val").glob("*.jpg"))[:2]:
                shutil.copy2(p, AI4_ONLY / "images/train" / p.name)
                shutil.copy2(AI4_ONLY / "labels/val" / f"{p.stem}.txt", AI4_ONLY / "labels/train" / f"{p.stem}.txt")
            (AI4_ONLY / "data.yaml").write_text(
                f"path: {AI4_ONLY}\ntrain: images/train\nval: images/val\n\nnames:\n"
                + "".join(f"  {i}: {c}\n" for i, c in enumerate(CLASSES))
            )
            print(f"  AI4Shipwrecks test tiles for zero-shot eval: {len(pos)} positive + {len(neg)} empty")

    n_train = sum(1 for p in (OUT / "images/train").iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    n_val = len(list((OUT / "images/val").glob("*.jpg")))
    print(f"  TOTAL train {n_train} (with duplicates and any AquaScan) | val {n_val}")
    if n_train == 0 or n_val == 0:
        print("  BUILD PRODUCED AN EMPTY SPLIT -- stopping. Re-run with WRECK_RESET=1")
        raise SystemExit(1)

    # Counted from the label files actually on disk, so this runs identically
    # on a fresh build and a cached one. A class missing from val is silently
    # dropped from the mAP mean; a class missing from train scores 0 and the
    # oversampling is a no-op. Either way the number would look real.
    def classes_in(split: str) -> Counter:
        c = Counter()
        for lp in (OUT / "labels" / split).glob("*.txt"):
            for ln in lp.read_text(errors="ignore").splitlines():
                if ln.strip():
                    c[CLASSES[int(ln.split()[0])]] += 1
        return c

    missing = [c for c in CLASSES if classes_in("train")[c] == 0 or classes_in("val")[c] == 0]
    if missing:
        print(f"  CLASS MISSING FROM A SPLIT: {missing} -- the score would be meaningless. "
              "Re-run with WRECK_RESET=1; if it persists the SCTD annotations did not parse.")
        raise SystemExit(1)


# ------------------------------------------------------------------ 4. train
def _checkpoint_finished(last: Path) -> bool:
    """True when ultralytics has already run final_eval on this checkpoint.

    On completion -- epochs reached or early stop -- the trainer strips the
    optimizer from last.pt and sets epoch to -1. Such a file is not resumable:
    older 8.4 asserts "nothing to resume"; current 8.4 demotes resume to a
    FRESH run in the same directory and overwrites best.pt on its first epoch,
    which would ship a two-stage model under a single-stage label.
    """
    import torch

    ck = torch.load(last, map_location="cpu", weights_only=False)
    finished = int(ck.get("epoch", -1)) < 0 or ck.get("optimizer") is None
    del ck
    return finished


def train() -> str:
    step(f"4/6  train  {MODEL} @ {IMGSZ}px, {EPOCHS} epochs, oversample x{OVERSAMPLE}")
    from ultralytics import YOLO

    run_dir = Path(RUNS) / NAME
    if RESET:
        # "Rebuild everything from scratch" includes the optimiser state.
        shutil.rmtree(run_dir, ignore_errors=True)
    last, best = run_dir / "weights" / "last.pt", run_dir / "weights" / "best.pt"

    resume = False
    if last.is_file():
        if _checkpoint_finished(last):
            if best.is_file():
                print("  training already complete; reusing best.pt (WRECK_RESET=1 to retrain)")
                shutil.copy2(best, WORK / "sonar-v4-best.pt")
                return str(best)
            print("  finished checkpoint with no best.pt: starting from scratch")
            shutil.rmtree(run_dir, ignore_errors=True)
        else:
            resume = True
    print("  resuming from checkpoint" if resume else f"  starting from {MODEL}")

    model = YOLO(str(last)) if resume else YOLO(MODEL)
    model.train(
        data=str(OUT / "data.yaml"),
        epochs=EPOCHS, imgsz=IMGSZ, batch=16, device=0,
        project=RUNS, name=NAME, exist_ok=True, resume=resume,
        # patience=0 disables early stopping. Mosaic is closed only for the last
        # close_mosaic epochs and the cosine schedule only reaches its floor at
        # the end; an early stop at epoch 120 of 200 would skip both. best.pt
        # is still the best epoch, so a run that plateaus loses nothing.
        patience=0, seed=1337, deterministic=True, plots=True, save_period=10,
        cos_lr=True,
        # --- sonar-correct augmentation ---
        fliplr=0.5,       # port/starboard swap: shadows still fall away from nadir
        flipud=0.5,       # reversed direction of travel: geometry unchanged
        degrees=0.0,      # a rotation tilts the nadir line, which cannot happen
        shear=0.0, perspective=0.0,
        translate=0.10, scale=0.5,
        mosaic=1.0, close_mosaic=15, mixup=0.1,
        hsv_h=0.0, hsv_s=0.0,   # single-channel intensity: no hue, no saturation
        hsv_v=0.4,              # gain differs between surveys
    )
    if not best.is_file():
        raise SystemExit(f"training ended without {best}")
    # Copied out immediately, so a crash in measure() or export() cannot lose it.
    shutil.copy2(best, WORK / "sonar-v4-best.pt")
    return str(best)


# ---------------------------------------------------------------- 5. measure
def _per_class(box) -> dict:
    out = {}
    try:
        for idx, ap in zip(box.ap_class_index, box.ap50):
            out[CLASSES[int(idx)]] = round(float(ap), 4)
    except Exception as exc:  # noqa: BLE001 -- metrics object shape differs across versions
        print(f"  WARNING: per-class AP unavailable ({type(exc).__name__}: {exc}); "
              "the verdict cannot check the rare class and will say so")
    return out


def _val(best: str, yaml: Path, imgsz: int) -> dict:
    from ultralytics import YOLO

    box = YOLO(best).val(data=str(yaml), imgsz=imgsz, device=0, plots=False).box
    return dict(
        map50=round(float(box.map50), 4), map50_95=round(float(box.map), 4),
        precision=round(float(box.mp), 4), recall=round(float(box.mr), 4),
        per_class_ap50=_per_class(box), imgsz=imgsz,
    )


def measure(best: str) -> dict:
    step("5/6  measure")
    res = {}
    res["sctd_heldout"] = _val(best, OUT / "data.yaml", IMGSZ)
    res["sctd_heldout"]["note"] = (
        f"In-distribution at the export resolution ({IMGSZ} px): the same stratified "
        "20% held-out split, never trained on."
    )
    if IMGSZ != LIKE_FOR_LIKE_IMGSZ:
        # The deployed 0.839 was measured at 512. Same images, same resolution,
        # so the deploy decision is not confounded by the resolution change.
        res["sctd_heldout_like_for_like"] = _val(best, OUT / "data.yaml", LIKE_FOR_LIKE_IMGSZ)
        res["sctd_heldout_like_for_like"]["note"] = (
            f"Same held-out split evaluated at {LIKE_FOR_LIKE_IMGSZ} px, the resolution the "
            "deployed model was measured at. This is the comparable number."
        )

    yaml = AI4_ONLY / "data.yaml"
    if yaml.is_file() and any((AI4_ONLY / "images/val").glob("*.jpg")):
        try:
            r = _val(best, yaml, IMGSZ)
            r.pop("per_class_ap50", None)
            r["note"] = (
                "Zero-shot: different lake, sonar and survey; never seen in training or "
                "validation. The tile subset is seeded independently, so it is stable "
                "run to run but not tile-for-tile identical to the set behind the "
                "deployed 0.203."
            )
            res["ai4shipwrecks_cross_dataset"] = r
        except Exception as exc:  # noqa: BLE001 -- the cross-dataset read must not cost the export
            print(f"  AI4Shipwrecks evaluation failed ({type(exc).__name__}: {exc}); continuing")
    else:
        print("  AI4Shipwrecks not attached: cross-dataset NOT measured")
    return res


# ----------------------------------------------------------------- 6. export
def export(best: str, res: dict) -> None:
    step("6/6  export")
    import hashlib

    from ultralytics import YOLO

    # opset 12 matches the deployed export; YOLO11's attention blocks need 17.
    opset = 17 if "yolo11" in MODEL.lower() or "yolo12" in MODEL.lower() else 12
    onnx = Path(YOLO(best).export(format="onnx", imgsz=IMGSZ, simplify=True, opset=opset))
    # The backend loads this exact filename regardless of architecture.
    shutil.copy2(onnx, WORK / "yolov8n-sonar.onnx")
    shutil.copy2(best, WORK / "sonar-v4-best.pt")

    # The held-out split, as a fingerprint. Anyone can verify two runs sat the
    # same exam by comparing this, which a prose claim cannot offer.
    val_stems = sorted(p.stem for p in (OUT / "images/val").glob("*.jpg"))
    split_sha = hashlib.sha256("\n".join(val_stems).encode()).hexdigest()

    head = res.get("sctd_heldout", {})
    p, r = head.get("precision", 0.0), head.get("recall", 0.0)
    aquascan = any((OUT / "images/train").glob("aqua_*"))
    metrics = {
        "model_version": f"4.0.0-sctd-balanced-{_ARCH}",
        "map50": head.get("map50", 0.0),
        "map50_95": head.get("map50_95", 0.0),
        "precision": p,
        "recall": r,
        "f1": round(2 * p * r / max(p + r, 1e-9), 4),
        "per_class_ap50": head.get("per_class_ap50", {}),
        "validated_on": (
            f"SCTD 1.0 held-out split ({len(val_stems)} images, 20% stratified, same split "
            f"logic as the committed notebook, never trained on), evaluated at {IMGSZ} px"
        ),
        "validation_split_sha256": split_sha,
        "trained_on": (
            f"SCTD 1.0 train split with '{RARE}' oversampled x{OVERSAMPLE}"
            + (" + AquaScan-1K (human, MIT)" if aquascan else "")
            + f", {MODEL} @ {IMGSZ}px, sonar-correct augmentation, {EPOCHS} epochs, Kaggle GPU"
        ),
        "imgsz": IMGSZ,
        "evaluated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "per_benchmark": res,
        "baseline_deployed": DEPLOYED,
    }
    (WORK / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(f"  wrote yolov8n-sonar.onnx (opset {opset}), sonar-v4-best.pt, metrics.json")
    print(f"  held-out split fingerprint: {split_sha[:16]}…  ({len(val_stems)} images)")


def main() -> int:
    install()
    ai4 = fetch()
    aqua = find_aquascan() if USE_AQUASCAN else None
    print("  AquaScan-1K:", f"found at {aqua}" if aqua else "not attached (optional)")
    build(ai4, aqua)
    best = train()
    assert Path(best).is_file(), best
    res = measure(best)
    export(best, res)

    step("RESULTS")
    head = res["sctd_heldout"]
    like = res.get("sctd_heldout_like_for_like", head)
    print(f"  SCTD held-out mAP@0.5 @ {IMGSZ}px       {head['map50']:.4f}")
    print(f"  SCTD held-out mAP@0.5 @ {like['imgsz']}px       {like['map50']:.4f}   "
          f"(deployed {DEPLOYED['sctd_map50']:.4f} @ {DEPLOYED['imgsz']}px)  <- comparable")
    per = like.get("per_class_ap50", {})
    for c in CLASSES:
        new, old = per.get(c), DEPLOYED["per_class"][c]
        if new is None:
            print(f"    {c:<9}      n/a   (deployed {old:.4f})")
        else:
            print(f"    {c:<9} {new:>8.4f}   (deployed {old:.4f})  {'+' if new >= old else '-'}{abs(new - old):.4f}")
    cross = res.get("ai4shipwrecks_cross_dataset", {}).get("map50")
    if cross is not None:
        print(f"  AI4Shipwrecks zero-shot @ {IMGSZ}px    {cross:.4f}   (deployed {DEPLOYED['ai4_zero_shot_map50']:.4f})")

    human = per.get(RARE)
    if human is None:
        print("\n  VERDICT: per-class AP unavailable -- cannot confirm the rare class improved. "
              "Do not deploy on the headline alone; inspect the run.")
    elif like["map50"] > DEPLOYED["sctd_map50"] and human > DEPLOYED["per_class"][RARE]:
        print("\n  VERDICT: better on the same exam at the same resolution -> deploy.")
        print("  Copy yolov8n-sonar.onnx and metrics.json into backend/models/ and push.")
    else:
        print("\n  VERDICT: not better on the same exam -> keep the deployed model.")
        print("  This is still a measured result; record it rather than discarding it.")
    print("\n  Download from the Output panel: yolov8n-sonar.onnx, metrics.json, sonar-v4-best.pt\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
