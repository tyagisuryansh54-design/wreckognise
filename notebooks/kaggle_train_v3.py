"""Train a four-class detector on SCTD + AI4Shipwrecks + Gavia.

One Kaggle code cell, GPU on, Internet on:

    !curl -sL https://raw.githubusercontent.com/tyagisuryansh54-design/wreckognise/main/notebooks/kaggle_train_v3.py -o train3.py
    !python train3.py

WHAT CHANGES FROM THE 3-CLASS MODEL
-----------------------------------
A fourth class, `mine`, from the Gavia corpus (1,170 images, Teledyne Gavia
AUV, 2010-2021, CC BY 4.0). Three decisions in how that corpus is used, each
made on a measurement rather than by taste:

1. IMAGE SIZE 1024, not 512. Gavia targets are a median 33 x 19 px in a
   1024 px frame. Letterboxed to 512 they become ~16 px, and evaluating the
   deployed model on them returned 0.6% recall -- it cannot see objects that
   small because it has never been shown any. Training at 512 would reproduce
   exactly that. This is the single most important setting in the file.

2. NOMBO IS DROPPED. It means "an object, but not a mine" -- true, and useless
   here: it is not a mine, and it is not one of our other three classes
   either. Mapping it anywhere would teach the model something false; calling
   it background would teach it to ignore real objects.

3. NEGATIVES CAPPED. 866 of the 1,170 Gavia frames are empty seabed, which is
   74% of the corpus and the most valuable part of it -- the deployed model
   has almost never been shown what "nothing" looks like. But at 74% the
   cheapest way to reduce loss is to predict nothing, and recall collapses.
   They come in capped against the positive count instead.

Evaluated on all three corpora separately afterwards, because a single blended
number would hide exactly the transfer behaviour this is trying to fix.
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
OUT = WORK / "dataset3"
RUNS, NAME = str(WORK), "run3"

CLASSES = ["aircraft", "human", "ship", "mine"]
AIRCRAFT, HUMAN, SHIP, MINE = 0, 1, 2, 3

EPOCHS = int(os.environ.get("WRECK_EPOCHS", "80"))
IMGSZ = int(os.environ.get("WRECK_IMGSZ", "1024"))
BATCH = int(os.environ.get("WRECK_BATCH", "8"))          # 1024px needs a smaller batch
NEG_RATIO = float(os.environ.get("WRECK_NEG", "0.45"))   # empties per positive frame
TILE, STRIDE = 512, 384
MIN_BLOB_PX, MIN_BOX_PX = 60, 12
rng = random.Random(1337)

GAVIA = {"2010.zip": 43169008, "2015.zip": 43169002, "2017.zip": 43169005,
         "2018.zip": 43169011, "2021.zip": 43168999}


def step(msg: str) -> None:
    print(f"\n{'=' * 66}\n  {msg}\n{'=' * 66}", flush=True)


def sh(*args: str) -> None:
    subprocess.run(list(args), check=True)


# --------------------------------------------------------------- 1. install
def install() -> None:
    step("1/6  install")
    try:
        import ultralytics  # noqa: F401
        print("  ultralytics present")
    except ImportError:
        sh(sys.executable, "-m", "pip", "-q", "install", "ultralytics", "onnx", "onnxslim")


# ----------------------------------------------------------------- 2. fetch
def find_ai4(root=Path("/kaggle/input")):
    if not root.exists():
        return None, None
    for cand in root.rglob("train"):
        if (cand / "images").is_dir() and (cand / "labels").is_dir():
            return cand.parent, None
    for cand in root.rglob("*.zip"):
        if "ai4" in cand.name.lower() or "shipwreck" in cand.name.lower():
            return None, cand
    return None, None


def fetch():
    step("2/6  fetch corpora")
    sctd = WORK / "sctd"
    if not any(sctd.rglob("*.jpg")):
        shutil.rmtree(sctd, ignore_errors=True)
        shutil.rmtree(WORK / "sctd_repo", ignore_errors=True)
        sh("git", "clone", "-q", "--depth", "1",
           "https://github.com/MingqiangNing/SCTD.git", str(WORK / "sctd_repo"))
        with zipfile.ZipFile(WORK / "sctd_repo/SCTD.zip") as z:
            z.extractall(sctd)
    print("  SCTD images :", len(list(sctd.rglob("*.jpg"))))

    ai4 = WORK / "ai4sw/AI4Shipwrecks"
    if not ai4.exists():
        pre, zp = find_ai4()
        if pre is not None:
            ai4.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(pre, ai4)
        elif zp is not None:
            with zipfile.ZipFile(zp) as z:
                z.extractall(WORK / "ai4sw")
    print("  AI4Shipwrecks:", "yes" if ai4.exists() else "NOT ATTACHED")

    gav = WORK / "gavia"
    gav.mkdir(parents=True, exist_ok=True)
    if len(list(gav.rglob("*.jpg"))) < 1000:
        for name, fid in GAVIA.items():
            target = gav / name
            if not target.exists():
                print(f"  downloading {name}...", flush=True)
                sh("curl", "-sL", f"https://ndownloader.figshare.com/files/{fid}", "-o", str(target))
            with zipfile.ZipFile(target) as z:
                z.extractall(gav)
    print("  Gavia images :", len(list(gav.rglob("*.jpg"))))
    return sctd, (ai4 if ai4.exists() else None), gav


# ----------------------------------------------------------------- 3. build
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


def build(sctd: Path, ai4, gav: Path) -> None:
    step("3/6  build the four-class corpus")
    if (OUT / "data.yaml").is_file() and any((OUT / "images/train").glob("*.jpg")):
        print("  already built")
    else:
        import cv2
        import numpy as np

        shutil.rmtree(OUT, ignore_errors=True)
        for s in ("train", "val"):
            (OUT / "images" / s).mkdir(parents=True, exist_ok=True)
            (OUT / "labels" / s).mkdir(parents=True, exist_ok=True)

        # --- SCTD: Pascal VOC, stratified 80/20 ---
        imgs = {p.stem: p for p in sctd.rglob("*.jpg")}
        xmls = {p.stem: p for p in sctd.rglob("*.xml")}
        samples = []
        for k in sorted(imgs.keys() & xmls.keys()):
            w, h, b = parse_voc(xmls[k])
            if w and h and b:
                samples.append((k, w, h, b))
        by_cls = defaultdict(list)
        for e in samples:
            by_cls[Counter(x[0] for x in e[3]).most_common(1)[0][0]].append(e)
        tr, va = [], []
        for entries in by_cls.values():
            rng.shuffle(entries)
            cut = max(1, round(len(entries) * 0.2))
            va += entries[:cut]; tr += entries[cut:]
        for split, entries in (("train", tr), ("val", va)):
            for k, w, h, boxes in entries:
                shutil.copy2(imgs[k], OUT / "images" / split / f"sctd_{k}.jpg")
                (OUT / "labels" / split / f"sctd_{k}.txt").write_text("\n".join(
                    f"{CLASSES.index(n)} {((x0+x1)/2)/w:.6f} {((y0+y1)/2)/h:.6f}"
                    f" {(x1-x0)/w:.6f} {(y1-y0)/h:.6f}" for n, x0, y0, x1, y1 in boxes))
        print(f"  SCTD           train {len(tr)}  val {len(va)}")

        # --- AI4Shipwrecks: masks -> tiled boxes, all class `ship` ---
        if ai4 is not None:
            def mask_boxes(m):
                n, _, st, _ = cv2.connectedComponentsWithStats((m > 0).astype(np.uint8), 8)
                return [tuple(int(v) for v in st[i][:4]) for i in range(1, n)
                        if st[i][4] >= MIN_BLOB_PX and st[i][2] >= 4 and st[i][3] >= 4]
            for src, dst in (("train", "train"), ("test", "val")):
                kept = 0
                for ip in sorted((ai4 / src / "images").glob("*.png")):
                    im = cv2.imread(str(ip), cv2.IMREAD_GRAYSCALE)
                    mk = cv2.imread(str(ai4 / src / "labels" / ip.name), cv2.IMREAD_GRAYSCALE)
                    if im is None or mk is None:
                        continue
                    if mk.shape != im.shape:
                        mk = cv2.resize(mk, (im.shape[1], im.shape[0]), interpolation=cv2.INTER_NEAREST)
                    boxes = mask_boxes(mk); H, W = im.shape
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
                            if not local:
                                continue
                            tw, th = right - left, bot - top
                            stem = f"ai4_{ip.stem}_{left}_{top}"
                            cv2.imwrite(str(OUT / "images" / dst / f"{stem}.jpg"), im[top:bot, left:right])
                            (OUT / "labels" / dst / f"{stem}.txt").write_text("\n".join(
                                f"{SHIP} {(bx+bw/2)/tw:.6f} {(by+bh/2)/th:.6f} {bw/tw:.6f} {bh/th:.6f}"
                                for bx, by, bw, bh in local))
                            kept += 1
                print(f"  AI4SW {src:<6}   -> {dst}: {kept} tiles")

        # --- Gavia: MILCO -> mine, NOMBO dropped, empties capped ---
        positives, empties = [], []
        for txt in sorted(gav.rglob("*.txt")):
            jpg = txt.with_suffix(".jpg")
            if not jpg.exists():
                continue
            rows = [l.split() for l in txt.read_text().strip().splitlines() if l.strip()]
            milco = [r for r in rows if r[0] == "0"]
            nombo = [r for r in rows if r[0] == "1"]
            if milco:
                positives.append((jpg, milco))
            elif not nombo:
                empties.append(jpg)          # truly empty, not "NOMBO only"
        rng.shuffle(empties)
        empties = empties[: int(len(positives) * NEG_RATIO)]
        print(f"  Gavia          {len(positives)} with mines, {len(empties)} empty frames kept")

        def write_gavia(items, split):
            for item in items:
                jpg, rows = (item, []) if isinstance(item, Path) else item
                stem = f"gav_{jpg.parent.name}_{jpg.stem}"
                shutil.copy2(jpg, OUT / "images" / split / f"{stem}.jpg")
                (OUT / "labels" / split / f"{stem}.txt").write_text("\n".join(
                    f"{MINE} {r[1]} {r[2]} {r[3]} {r[4]}" for r in rows))

        rng.shuffle(positives)
        cut = max(1, round(len(positives) * 0.2))
        write_gavia(positives[cut:], "train"); write_gavia(positives[:cut], "val")
        ecut = max(1, round(len(empties) * 0.2))
        write_gavia(empties[ecut:], "train"); write_gavia(empties[:ecut], "val")

        (OUT / "data.yaml").write_text(
            f"path: {OUT}\ntrain: images/train\nval: images/val\n\nnames:\n"
            + "".join(f"  {i}: {c}\n" for i, c in enumerate(CLASSES)))

    print("  TOTAL train:", len(list((OUT / "images/train").glob("*.jpg"))),
          "| val:", len(list((OUT / "images/val").glob("*.jpg"))))


# ----------------------------------------------------------------- 4. train
def train() -> str:
    step(f"4/6  train  ({EPOCHS} epochs @ {IMGSZ}px, batch {BATCH})")
    from ultralytics import YOLO
    last = Path(RUNS) / NAME / "weights/last.pt"
    resume = last.is_file()
    print("  resuming" if resume else "  starting fresh")
    model = YOLO(str(last)) if resume else YOLO("yolov8s.pt")
    model.train(
        data=str(OUT / "data.yaml"),
        epochs=EPOCHS, imgsz=IMGSZ, batch=BATCH, device=0,
        project=RUNS, name=NAME, exist_ok=True, resume=resume,
        patience=25, seed=1337, deterministic=True, plots=True, save_period=10,
        fliplr=0.5, flipud=0.0,
        degrees=5.0, translate=0.10, scale=0.5, shear=0.0, perspective=0.0,
        mosaic=1.0, close_mosaic=12, mixup=0.1,
        hsv_h=0.0, hsv_s=0.0, hsv_v=0.4,
    )
    return str(Path(RUNS) / NAME / "weights/best.pt")


# --------------------------------------------------------------- 5. measure
def subset_yaml(prefix: str, tag: str) -> Path | None:
    """A val split containing only files from one corpus."""
    sub = WORK / f"eval_{tag}"
    shutil.rmtree(sub, ignore_errors=True)
    for s in ("train", "val"):
        (sub / "images" / s).mkdir(parents=True, exist_ok=True)
        (sub / "labels" / s).mkdir(parents=True, exist_ok=True)
    files = sorted((OUT / "images/val").glob(f"{prefix}*.jpg"))
    if not files:
        return None
    for p in files:
        shutil.copy2(p, sub / "images/val" / p.name)
        lp = OUT / "labels/val" / f"{p.stem}.txt"
        if lp.is_file():
            shutil.copy2(lp, sub / "labels/val" / lp.name)
    for p in files[:2]:
        shutil.copy2(p, sub / "images/train" / p.name)
        shutil.copy2(sub / "labels/val" / f"{p.stem}.txt", sub / "labels/train" / f"{p.stem}.txt")
    (sub / "data.yaml").write_text(
        f"path: {sub}\ntrain: images/train\nval: images/val\n\nnames:\n"
        + "".join(f"  {i}: {c}\n" for i, c in enumerate(CLASSES)))
    return sub / "data.yaml"


def measure(best: str) -> dict:
    step("5/6  measure, per corpus")
    from ultralytics import YOLO
    res = {}
    targets = [("combined", OUT / "data.yaml")]
    for prefix, tag in (("sctd_", "sctd"), ("ai4_", "ai4shipwrecks"), ("gav_", "gavia")):
        y = subset_yaml(prefix, tag)
        if y:
            targets.append((tag, y))
    for tag, yaml in targets:
        box = YOLO(best).val(data=str(yaml), imgsz=IMGSZ, device=0, plots=False, verbose=False).box
        res[tag] = dict(map50=round(float(box.map50), 4), map=round(float(box.map), 4),
                        p=round(float(box.mp), 4), r=round(float(box.mr), 4))
        print(f"    {tag:16} mAP50={box.map50:.4f}  P={box.mp:.4f}  R={box.mr:.4f}")
    return res


# ---------------------------------------------------------------- 6. export
def export(best: str, res: dict) -> None:
    step("6/6  export")
    import json
    from ultralytics import YOLO
    onnx = Path(YOLO(best).export(format="onnx", imgsz=IMGSZ, simplify=True, opset=12))
    shutil.copy2(onnx, WORK / "yolov8s-sonar-4class.onnx")
    head = res.get("combined", {})
    p, r = head.get("p", 0.0), head.get("r", 0.0)
    (WORK / "metrics-4class.json").write_text(json.dumps({
        "model_version": "3.0.0-4class-sctd-ai4sw-gavia",
        "classes": CLASSES,
        "map50": head.get("map50"), "map50_95": head.get("map"),
        "precision": p, "recall": r,
        "f1": round(2 * p * r / max(p + r, 1e-9), 4),
        "per_benchmark": res,
        "imgsz": IMGSZ,
        "trained_on": "SCTD 1.0 + AI4Shipwrecks tiles + Gavia (MILCO as mine, NOMBO dropped)",
        "evaluated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }, indent=2))
    print("  wrote yolov8s-sonar-4class.onnx and metrics-4class.json")
    print(f"  ONNX {(WORK / 'yolov8s-sonar-4class.onnx').stat().st_size / 1048576:.1f} MB")


def main() -> int:
    install()
    sctd, ai4, gav = fetch()
    build(sctd, ai4, gav)
    best = train()
    res = measure(best)
    export(best, res)
    step("DONE")
    print("  For comparison, the deployed 3-class model at 512px scored")
    print("    SCTD held-out 0.839 | AI4Shipwrecks 0.203 | Gavia recall 0.6%")
    print("  Download both files from the Output panel.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
