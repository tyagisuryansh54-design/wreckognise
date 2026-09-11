"""One-shot GPU training + evaluation run for Kaggle.

Everything the notebook does, in a single script with no cell boundaries:
install, fetch both datasets, build the YOLO corpus, train, measure on both
benchmarks, export ONNX. Run it with two lines in one Kaggle code cell:

    !curl -sL https://raw.githubusercontent.com/tyagisuryansh54-design/wreckognise/main/notebooks/kaggle_run.py -o run.py
    !python run.py

Requires: Settings -> Accelerator -> GPU, and Internet -> On (SCTD is cloned
from GitHub). AI4Shipwrecks should be attached as an input; without it the run
still trains on SCTD alone, but transfer will be poor and the cross-dataset
number -- the one this run exists to produce -- cannot be measured.

Every stage is idempotent and training resumes from its last checkpoint, so a
session that dies partway costs minutes rather than the whole run.
"""

from __future__ import annotations

import os
import random
import shutil
import subprocess
import sys
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

WORK = Path("/kaggle/working")
OUT = Path("/kaggle/working/dataset")
RUNS, NAME = str(WORK), "run"
CLASSES = ["aircraft", "human", "ship"]
SHIP_ID = CLASSES.index("ship")
TILE, STRIDE = 512, 384
MIN_BLOB_PX, MIN_BOX_PX, NEG_RATIO = 60, 12, 0.6
EPOCHS = int(os.environ.get("WRECK_EPOCHS", "150"))
IMGSZ = int(os.environ.get("WRECK_IMGSZ", "640"))
# The number to beat. Measured on CPU for the 512 px combined model; printed at
# the end so the deploy/keep decision is made by the script, not by eye.
CPU_CROSS_DATASET = 0.349
rng = random.Random(1337)


def step(n: str) -> None:
    print(f"\n{'=' * 64}\n  {n}\n{'=' * 64}", flush=True)


# ---------------------------------------------------------------- 1. install
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
    """Locate the dataset by SHAPE rather than by name.

    Public mirrors and a hand-uploaded zip lay the files out differently and
    dataset slugs change. What does not change is the structure: a directory
    holding train/images alongside train/labels.
    """
    if not root.exists():
        return None, None
    for cand in root.rglob("train"):
        if (cand / "images").is_dir() and (cand / "labels").is_dir():
            return cand.parent, None
    for cand in root.rglob("*.zip"):
        if "ai4" in cand.name.lower() or "shipwreck" in cand.name.lower():
            return None, cand
    return None, None


def fetch() -> Path | None:
    step("2/6  fetch datasets")
    if not Path("/kaggle/working/sctd").exists():
        print("  cloning SCTD (needs Internet: On)...")
        subprocess.run(
            ["git", "clone", "-q", "--depth", "1",
             "https://github.com/MingqiangNing/SCTD.git", "/kaggle/working/sctd_repo"],
            check=True,
        )
        with zipfile.ZipFile("/kaggle/working/sctd_repo/SCTD.zip") as z:
            z.extractall("/kaggle/working/sctd")
    print("  SCTD images:", len(list(Path("/kaggle/working/sctd").rglob("*.jpg"))),
          "| annotations:", len(list(Path("/kaggle/working/sctd").rglob("*.xml"))))

    pre, zp = find_ai4shipwrecks()
    ai4 = Path("/kaggle/working/ai4sw/AI4Shipwrecks")
    if ai4.exists():
        print("  AI4Shipwrecks already available")
    elif pre is not None:
        # /kaggle/input is read-only but readable in place: symlink rather than
        # burn several minutes copying gigabytes.
        ai4.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(pre, ai4)
        print("  AI4Shipwrecks linked from", pre)
    elif zp is not None:
        print("  extracting AI4Shipwrecks, 1-2 min...")
        with zipfile.ZipFile(zp) as z:
            z.extractall("/kaggle/working/ai4sw")
    else:
        attached = [p.name for p in Path("/kaggle/input").glob("*")] \
            if Path("/kaggle/input").exists() else []
        print("  AI4Shipwrecks NOT attached. inputs:", attached or "NONE")
        print("  -> Add Input -> search ai4shipwrecks -> doanduchieu/ai4shipwrecks")
        print("  continuing on SCTD alone; cross-dataset cannot be measured")
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


def build(ai4: Path | None) -> None:
    step("3/6  build YOLO dataset")
    if (OUT / "data.yaml").is_file():
        print("  already built (delete /kaggle/working/dataset to rebuild)")
    else:
        import cv2
        import numpy as np

        for s in ("train", "val"):
            (OUT / "images" / s).mkdir(parents=True, exist_ok=True)
            (OUT / "labels" / s).mkdir(parents=True, exist_ok=True)

        # --- SCTD: Pascal VOC -> YOLO, stratified 80/20 ---
        imgs = {p.stem: p for p in Path("/kaggle/working/sctd").rglob("*.jpg")}
        xmls = {p.stem: p for p in Path("/kaggle/working/sctd").rglob("*.xml")}
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

        for split, entries in (("train", train), ("val", val)):
            for k, w, h, boxes in entries:
                shutil.copy2(imgs[k], OUT / "images" / split / f"{k}.jpg")
                (OUT / "labels" / split / f"{k}.txt").write_text("\n".join(
                    f"{CLASSES.index(n)} {((x0 + x1) / 2) / w:.6f} {((y0 + y1) / 2) / h:.6f}"
                    f" {(x1 - x0) / w:.6f} {(y1 - y0) / h:.6f}"
                    for n, x0, y0, x1, y1 in boxes))
        print(f"  SCTD -> train {len(train)}, val {len(val)}")

        # --- AI4Shipwrecks: segmentation masks -> tiled boxes ---
        if ai4 is not None:
            def mask_boxes(m):
                n, _, st, _ = cv2.connectedComponentsWithStats((m > 0).astype(np.uint8), 8)
                return [tuple(int(v) for v in st[i][:4]) for i in range(1, n)
                        if st[i][4] >= MIN_BLOB_PX and st[i][2] >= 4 and st[i][3] >= 4]

            for src, dstsplit in (("train", "train"), ("test", "val")):
                pos, neg = [], []
                for ip in sorted((ai4 / src / "images").glob("*.png")):
                    im = cv2.imread(str(ip), cv2.IMREAD_GRAYSCALE)
                    mk = cv2.imread(str(ai4 / src / "labels" / ip.name), cv2.IMREAD_GRAYSCALE)
                    if im is None or mk is None:
                        continue
                    if mk.shape != im.shape:
                        mk = cv2.resize(mk, (im.shape[1], im.shape[0]),
                                        interpolation=cv2.INTER_NEAREST)
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
                            rec = (ip, left, top, right - left, bot - top, local)
                            (pos if local else neg).append(rec)
                rng.shuffle(neg)
                neg = neg[:int(len(pos) * NEG_RATIO)]
                for i, (ip, left, top, tw, th, boxes) in enumerate(pos + neg):
                    im = cv2.imread(str(ip), cv2.IMREAD_GRAYSCALE)
                    stem = f"ai4_{ip.stem}_{left}_{top}_{i}"
                    cv2.imwrite(str(OUT / "images" / dstsplit / f"{stem}.jpg"),
                                im[top:top + th, left:left + tw])
                    (OUT / "labels" / dstsplit / f"{stem}.txt").write_text("\n".join(
                        f"{SHIP_ID} {(bx + bw / 2) / tw:.6f} {(by + bh / 2) / th:.6f}"
                        f" {bw / tw:.6f} {bh / th:.6f}"
                        for bx, by, bw, bh in boxes))
                print(f"  AI4SW {src} -> {dstsplit}: {len(pos)} positive + {len(neg)} empty tiles")

        (OUT / "data.yaml").write_text(
            f"path: {OUT}\ntrain: images/train\nval: images/val\n\nnames:\n"
            + "".join(f"  {i}: {c}\n" for i, c in enumerate(CLASSES)))

    print("  TOTAL train:", len(list((OUT / "images" / "train").glob("*.jpg"))),
          "| val:", len(list((OUT / "images" / "val").glob("*.jpg"))))


# ------------------------------------------------------------------ 4. train
def train() -> str:
    step(f"4/6  train  ({EPOCHS} epochs @ {IMGSZ}px)")
    from ultralytics import YOLO

    last = Path(RUNS) / NAME / "weights" / "last.pt"
    resume = last.is_file()
    print("  resuming from checkpoint" if resume else "  starting fresh")

    model = YOLO(str(last)) if resume else YOLO("yolov8s.pt")
    model.train(
        data=str(OUT / "data.yaml"),
        epochs=EPOCHS, imgsz=IMGSZ, batch=16, device=0,
        project=RUNS, name=NAME, exist_ok=True, resume=resume,
        patience=40, seed=1337, deterministic=True, plots=True, save_period=10,
        # --- sonar-aware augmentation ---
        fliplr=0.5,            # port/starboard swap: physically valid
        flipud=0.0,            # would invert shadow direction: never
        degrees=5.0, translate=0.10, scale=0.5, shear=0.0, perspective=0.0,
        mosaic=1.0, close_mosaic=15, mixup=0.1,
        hsv_h=0.0, hsv_s=0.0,  # sonar is single-channel intensity
        hsv_v=0.4,             # gain variation between surveys is real
    )
    return str(Path(RUNS) / NAME / "weights" / "best.pt")


# ---------------------------------------------------------------- 5. measure
def measure(best: str) -> dict:
    step("5/6  measure")
    from ultralytics import YOLO

    res = {}
    box = YOLO(best).val(data=str(OUT / "data.yaml"), imgsz=IMGSZ,
                         device=0, plots=False).box
    res["combined"] = dict(map50=float(box.map50), map=float(box.map),
                           p=float(box.mp), r=float(box.mr))

    # An AI4Shipwrecks-only split, for the cross-dataset read. Ultralytics wants
    # a train path to exist, so two tiles are copied there; it is never trained.
    sub = Path("/kaggle/working/ai4_only")
    if sub.exists():
        shutil.rmtree(sub)
    for s in ("train", "val"):
        (sub / "images" / s).mkdir(parents=True, exist_ok=True)
        (sub / "labels" / s).mkdir(parents=True, exist_ok=True)

    tiles = sorted((OUT / "images" / "val").glob("ai4_*.jpg"))
    for p in tiles:
        shutil.copy2(p, sub / "images" / "val" / p.name)
        lp = OUT / "labels" / "val" / f"{p.stem}.txt"
        if lp.is_file():
            shutil.copy2(lp, sub / "labels" / "val" / lp.name)
    for p in tiles[:2]:
        shutil.copy2(p, sub / "images" / "train" / p.name)
        shutil.copy2(sub / "labels" / "val" / f"{p.stem}.txt",
                     sub / "labels" / "train" / f"{p.stem}.txt")
    (sub / "data.yaml").write_text(
        f"path: {sub}\ntrain: images/train\nval: images/val\n\n"
        "names:\n  0: aircraft\n  1: human\n  2: ship\n")

    if tiles:
        b2 = YOLO(best).val(data=str(sub / "data.yaml"), imgsz=IMGSZ,
                            device=0, plots=False).box
        res["ai4shipwrecks_only"] = dict(map50=float(b2.map50), map=float(b2.map),
                                         p=float(b2.mp), r=float(b2.mr))
    else:
        print("  no AI4Shipwrecks tiles: cross-dataset NOT measured")
    return res


# ----------------------------------------------------------------- 6. export
def export(best: str, res: dict) -> None:
    step("6/6  export")
    import json

    from ultralytics import YOLO

    onnx = Path(YOLO(best).export(format="onnx", imgsz=IMGSZ, simplify=True, opset=12))
    shutil.copy2(onnx, WORK / "yolov8n-sonar.onnx")

    head = res.get("combined", {})
    p, r = head.get("p", 0.0), head.get("r", 0.0)
    metrics = {
        "model_version": "3.0.0-kaggle-combined",
        "map50": round(head.get("map50", 0.0), 4),
        "map50_95": round(head.get("map", 0.0), 4),
        "precision": round(p, 4),
        "recall": round(r, 4),
        "f1": round(2 * p * r / max(p + r, 1e-9), 4),
        "per_benchmark": {k: {kk: round(vv, 4) for kk, vv in v.items()}
                          for k, v in res.items()},
        "validated_on": "SCTD 1.0 + AI4Shipwrecks held-out split",
        "trained_on": f"SCTD + AI4Shipwrecks tiles, YOLOv8s @ {IMGSZ}px, {EPOCHS} epochs, Kaggle T4",
        "imgsz": IMGSZ,
        "evaluated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (WORK / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print("  wrote /kaggle/working/yolov8n-sonar.onnx and metrics.json")


def main() -> int:
    install()
    ai4 = fetch()
    build(ai4)
    best = train()
    res = measure(best)
    export(best, res)

    print(f"\n{'=' * 64}\n  RESULTS\n{'=' * 64}")
    for k, v in res.items():
        print(f"  {k:22} mAP50={v['map50']:.4f}  mAP50-95={v['map']:.4f}"
              f"  P={v['p']:.3f}  R={v['r']:.3f}")

    cross = res.get("ai4shipwrecks_only", {}).get("map50")
    if cross is None:
        print("\n  cross-dataset NOT measured (AI4Shipwrecks was not attached)")
    else:
        verdict = ("BETTER, worth deploying" if cross > CPU_CROSS_DATASET
                   else "no improvement, keep the deployed model")
        print(f"\n  cross-dataset {cross:.4f} vs CPU run {CPU_CROSS_DATASET} -> {verdict}")
    print("\n  Download from the Output panel: yolov8n-sonar.onnx + metrics.json\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
