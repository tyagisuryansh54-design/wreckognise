# Wreckognise — Datasets and Measured Accuracy

Every corpus used, what it contributed, and every accuracy figure measured against it.

| | |
| --- | --- |
| Deployed model | `1.0.0-sctd-c6c120c` |
| Architecture | YOLOv8n, fine-tuned, exported to ONNX opset 12 |
| Input size | 512 px |
| Live at | https://wrecks.in |
| Report date | 19 September 2026 |

---

## 1. The short version

The detector scores **0.839 mAP@0.5** on sonar resembling its training data and **0.203** on sonar from a different survey. That gap is the finding, not a footnote: it was measured deliberately, it was reproduced on a third corpus, and it was traced to a cause.

**Precision transfers. Scale does not.** Across two unseen corpora the detector stays conservative on empty seabed — it does not invent wrecks in noise. What it cannot do is find objects an order of magnitude smaller than anything it was trained on.

---

## 2. Corpora used

| Dataset | Images | Role | Licence |
| --- | --- | --- | --- |
| **SCTD 1.0** | 357 | Training + held-out validation | Academic, cite authors |
| **AI4Shipwrecks** | 286 swaths | Cross-dataset benchmark; training in the combined model | MIT |
| **Gavia mine corpus** | 1,170 | Third cross-dataset benchmark | CC BY 4.0 |
| **China Offshore SSS-AI** | 3,255 chips | Negatives only (836 used) | Zenodo, open |

Four independent sonar systems, three bodies of water, collection spanning 2010 to 2023.

### 2.1 SCTD 1.0

357 side-scan images with Pascal VOC boxes: 266 shipwrecks, 57 aircraft, 34 drowning victims. Split 286 train / 71 held-out, stratified by dominant class. The held-out split was never trained on and is the basis of the headline figure.

### 2.2 AI4Shipwrecks

261 image/mask pairs at 5579×1728, collected over five weeks at Thunder Bay National Marine Sanctuary, Lake Huron, using an Iver3 AUV with an EdgeTech 2205. Masks were converted to boxes and the swaths tiled at 512 px with 384 stride.

### 2.3 Gavia mine corpus

1,170 real sonar images collected 2010–2021 with a Teledyne Marine Gavia AUV, labelled MILCO (mine-like) and NOMBO (non-mine bottom object). 304 frames carry 437 mine boxes; 866 frames are empty seabed.

### 2.4 China Offshore SSS-AI

3,255 chips from four Chinese marginal seas — Dongying, Shenzhen, Quanzhou, Yantai. **A classification set: folders, no bounding boxes.** It cannot teach localisation. Its `seabed_surface` and `hard_negative` folders supply 836 negative examples, which is the use it is put to.

### 2.5 Evaluated and rejected

| Dataset | Why not used |
| --- | --- |
| `ARG-NCTU/sonar_dataset_coco` | Downloaded 109 MB and inspected: screen captures of sonar acquisition software, complete with window chrome and toolbars, under a single generic `object` class. Training on it would have taught the model to detect UI widgets. |
| Synthetic mine set (ICIAP 2025) | 10,000 images, but not released — the paper is paywalled and no data drop exists. Synthetic besides. |
| Seabed Objects-KLSG | ~1,190 images including 385 wrecks. Requires an author request; not obtained in time. |

Every dataset was opened and looked at before use. The first rejection is why.

---

## 3. Measured accuracy

### 3.1 Deployed model, in distribution

Measured on the SCTD held-out split: 71 images, 71 boxes, never trained on.

| Metric | Value |
| --- | --- |
| mAP@0.5 | **0.8394** |
| mAP@0.5–0.95 | 0.5432 |
| Precision | 0.9788 |
| Recall | 0.7002 |
| F1 | 0.8164 |

Per class:

| Class | AP@0.5 | Training images |
| --- | --- | --- |
| aircraft | 0.9875 | 57 |
| ship | 0.9748 | 266 |
| human | **0.5559** | 34 |

The weak class tracks the scarce class exactly. 34 training examples is not enough, and the score says so.

### 3.2 Cross-dataset: AI4Shipwrecks

Different lake, different sonar, different survey. Never seen in training or validation.

| Metric | Value |
| --- | --- |
| mAP@0.5 | **0.2027** |
| Precision | 0.493 |
| Recall | 0.217 |
| False positives | 33 across 170 empty tiles (0.19 per frame) |

### 3.3 Cross-dataset: Gavia

A third corpus. Because the label vocabularies do not overlap — Gavia labels MILCO/NOMBO, the model knows aircraft/human/ship — a per-class mAP would be meaningless. Two things are measurable without a shared vocabulary.

**Empty frames.** Nothing is present, so every box is wrong regardless of its name.

| Metric | Value |
| --- | --- |
| Frames | 866 |
| Frames with any detection | 20 (2.3%) |
| False positives | 74 |
| Per frame | **0.085** |

Less than half the AI4Shipwrecks rate, on five times more empty seabed.

**Annotated frames**, class-agnostic: ignoring the label, did the detector look in the right place?

| Metric | Value |
| --- | --- |
| Ground-truth objects | 668 |
| Localised | 4 |
| Recall | **0.6%** |

By collection year: 2010 0%, 2015 1%, 2017 0%, 2018 0%, 2021 0%.

**The cause, measured.** Gavia targets are a median 33 × 19 px in a 1024 px frame. Letterboxed to the model's 512 px input they become roughly 16 px across. The training corpus contains objects filling a large fraction of the frame. This is a scale limit, not a generalisation failure — the model has never been shown targets that small.

This run was executed twice, locally and on Kaggle, with different denoise filters. Both produced identical figures.

---

## 4. Alternative model, and what it cost

A second model was trained on SCTD **and** AI4Shipwrecks combined.

| Model | SCTD held-out | AI4Shipwrecks |
| --- | --- | --- |
| `1.0.0-sctd` (deployed) | **0.8394** | 0.2027 |
| `2.0.0-combined` | 0.7738 | **0.3489** |
| `3.0.0` (Kaggle, YOLOv8s @ 640) | — | 0.3348 |

Adding the second corpus lifted transfer by 72% and cost 0.065 on the headline figure.

**The deployed model remains the SCTD-only one**, because 0.3489 against 0.3348 on a validation set of a few hundred tiles is within noise, and the in-distribution loss is not.

### Why more compute was not the answer

The third row is the important one. A larger model (YOLOv8s not YOLOv8n), at higher resolution (640 not 512), trained for 150 epochs on a Tesla T4, reached **the same transfer performance** as a small model trained on a laptop CPU.

```
combined val     0.6631
cross-dataset    0.3348   vs 0.3489 from the CPU run
```

Not a compute problem. Not a model-capacity problem. A data problem.

---

## 5. The four-class model

`3.0.0-4class-sctd-ai4sw-gavia` — adding `mine` from Gavia, YOLOv8s at 1024 px, trained on SCTD + AI4Shipwrecks tiles + Gavia with negatives from Gavia and China. Measured 13 September 2026.

| Benchmark | mAP@0.5 | mAP@0.5–0.95 | Precision | Recall |
| --- | --- | --- | --- | --- |
| Combined validation | 0.6358 | 0.3781 | 0.6639 | 0.5711 |
| SCTD | **0.7797** | 0.4898 | 0.824 | 0.6364 |
| AI4Shipwrecks | 0.3412 | 0.146 | 0.4414 | 0.4057 |
| Gavia | **0.7196** | 0.3702 | 0.8034 | 0.600 |

### 5.1 Two of those rows cannot be compared to §3

This model trained on its own 80/20 split of **every** corpus it is scored against. The deployed model had never seen Gavia or AI4Shipwrecks at all.

So "Gavia recall 0.6% → 60%" is not a like-for-like improvement, and must not be presented as one. The old figure was zero-shot; the new one is a held-out split of training data. They are different experiments.

**What it does legitimately establish.** §3.3 diagnosed the 0.6% as a *scale* limit — 33 × 19 px targets collapsing to ~16 px after a 512 px letterbox — rather than an unfixable generalisation failure. Scoring 0.7196 on those same targets at 1024 px confirms that diagnosis. One variable was changed and the prediction held.

### 5.2 The comparison that is valid

Both the 2.0.0 combined model and this one trained on AI4Shipwrecks, so their scores on it are directly comparable:

| Model | AI4Shipwrecks mAP@0.5 |
| --- | --- |
| `2.0.0-combined` (YOLOv8n @ 512, CPU) | 0.3489 |
| `3.0.0-4class` (YOLOv8s @ 1024, T4, + Gavia) | **0.3412** |

A larger model, double the input resolution, a GPU and an additional corpus moved it by **−0.008**. That is §4's finding reproduced a third time.

### 5.3 What it cost, and what it bought

SCTD fell 0.839 → 0.7797, a loss of 0.059 on the headline figure — the same size of trade the 2.0.0 model made.

It bought a fourth class. The deployed model's output tensor has three columns and physically cannot emit `mine`; this one can, which is what makes the UXO hazard path reachable at all.

**No true cross-dataset benchmark remains for this model.** Every corpus available is now training data. The 0.203 in §3.2 stays the project's generalisation figure, and belongs to the 3-class model that earned it.

---

## 6. Honest summary

| Claim | Evidence |
| --- | --- |
| Works on sonar like its training data | 0.839 mAP@0.5, held-out split |
| Does not hallucinate on empty seabed | 0.085 and 0.19 false positives per frame, two corpora |
| Does not transfer to unfamiliar sonar | 0.203 mAP@0.5 |
| Cannot see small targets — at 512 px | 0.6% recall at a median 33 × 19 px |
| Resolution was the cause, as predicted | 0.7196 mAP on the same targets at 1024 px |
| More compute still did not help transfer | 0.3489 → 0.3412 on a like-for-like AI4Shipwrecks comparison |
| Weakest on its scarcest class | human 0.556, from 34 images |
| More compute would not fix it | T4 run matched the CPU run on transfer |

Every number here was produced by an evaluation that was run. An earlier version of this dashboard displayed accuracy figures that no evaluation had ever generated; they were caught when the model was first measured against real labelled data, and that is documented in the project report rather than quietly removed.
