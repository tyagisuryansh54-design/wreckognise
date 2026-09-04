# Wreckognise

**AI-powered marine survey agent for automated shipwreck detection and georeferencing from side-scan sonar.**

Built for Smart India Hackathon 2026.

Wreckognise ingests raw side-scan sonar (`.xtf` / `.jsf`), strips acoustic speckle with OpenCV, runs a YOLOv8 detector across the swath, and converts every bounding box into a WGS-84 coordinate with a stated error budget — then hands an operator the register, the chart, and the executive brief.

---

## Quickstart

You need **Python 3.11+** and **Node.js 18+** installed. Then, from the project root:

```bash
# Windows (PowerShell)
.\start.ps1
```

```bash
# macOS / Linux / Git Bash
chmod +x start.sh && ./start.sh
```

That creates the virtualenv, installs both dependency sets, starts the API on **:8000** and the dashboard on **:5173**, and opens your browser. First run takes a few minutes; afterwards use `.\start.ps1 -SkipSetup` (or `./start.sh --skip-setup`) to skip straight to launching.

Once the dashboard loads, click **Explore Live Scan** — it drives the whole pipeline end to end with no sonar file needed.

If the script fails, or you would rather see each step, follow [Setup — backend](#setup--backend) and [Setup — frontend](#setup--frontend) below.

**Putting it online?** See **[DEPLOYMENT.md](DEPLOYMENT.md)** — backend to Render (or any Docker host), dashboard to Vercel or Netlify, both on free tiers.

---

## Table of contents

- [What it does](#what-it-does)
- [Architecture](#architecture)
- [Project structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Setup — backend](#setup--backend)
- [Setup — frontend](#setup--frontend)
- [Using the dashboard](#using-the-dashboard)
- [How the georeferencing works](#how-the-georeferencing-works)
- [API reference](#api-reference)
- [Testing](#testing)
- [Configuration](#configuration)
- [Design system](#design-system)
- [Deployment](DEPLOYMENT.md)
- [Production notes](#production-notes)

---

## What it does

| Stage | Engine | Output |
| --- | --- | --- |
| **1. Ingest** | `pyxtf` for XTF, a self-contained header walker for EdgeTech JSF | Per-ping navigation + a dual-channel waterfall mosaic |
| **2. Preprocess** | OpenCV — TVG normalisation → Non-Local Means / Bilateral → CLAHE | Denoised swath, scored by SNR / speckle index / contrast |
| **3. Detect** | YOLOv8 (native weights, or a classical-CV proposal engine as fallback) | Bounding boxes, classes, calibrated confidences |
| **4. Georeference** | WGS-84 direct geodetic solver | Lat/Long per contact, with a full audit trail |
| **5. Act** | Operator review + reporting | Markdown brief, JSON payload, GeoJSON for QGIS/ArcGIS |

**Detected classes:** shipwreck, debris field, container, pipeline, boulder, UXO, unclassified.

### Running without hardware captures

The backend never hard-fails on ingestion. If a file cannot be decoded — or you just want to demo the pipeline — it synthesises a **physically modelled** swath instead: TVG roll-off, Rayleigh speckle, a nadir water column, sand-ripple bedforms, and target highlight/shadow pairs. That is the same signal structure the OpenCV stage and the detector are tuned against, so the demo exercises real code rather than replaying a fixture. The model is seeded from the filename, so a given upload always renders identically.

Likewise, if `ultralytics` and weights are not installed, detection falls back to a **classical CV proposal engine** — highlight segmentation, shadow pairing, contour extraction, then the same NMS and confidence calibration the native path uses. It is a genuine detector keyed on the physical signature (bright specular return + acoustic shadow down-range), not a random box generator. The `simulated` flag on every inference response says which path ran.

---

## Architecture

```
                     ┌──────────────────────────────────────────────┐
  .xtf / .jsf  ─────▶│  sonar_reader   pyxtf · JSF walker · model   │
                     └───────────────────────┬──────────────────────┘
                                             │ waterfall + telemetry
                     ┌───────────────────────▼──────────────────────┐
                     │  preprocessing   TVG → NLM/Bilateral → CLAHE │
                     └───────────────────────┬──────────────────────┘
                                             │ filtered swath
                     ┌───────────────────────▼──────────────────────┐
                     │  detector       tile → YOLOv8 → NMS          │
                     └───────────────────────┬──────────────────────┘
                                             │ bounding boxes
                     ┌───────────────────────▼──────────────────────┐
                     │  georeference   px → slant → ground → WGS-84 │
                     └───────────────────────┬──────────────────────┘
                                             │ contacts
                     ┌───────────────────────▼──────────────────────┐
                     │  reporting      Markdown · JSON · GeoJSON    │
                     └──────────────────────────────────────────────┘
```

**Backend:** FastAPI (Python 3.11), NumPy, OpenCV.
**Frontend:** React 18 + Vite + Tailwind CSS, Leaflet for the GIS chart.

---

## Project structure

```
wreckognise/
├── backend/
│   ├── app/
│   │   ├── main.py                 FastAPI app, CORS, static mounts, health
│   │   ├── config.py               Pydantic settings (env-overridable)
│   │   ├── models/
│   │   │   └── schemas.py          Every request/response contract
│   │   ├── routers/
│   │   │   ├── ingest.py           Upload, demo, metadata, telemetry
│   │   │   ├── inference.py        Detect, review, georeference
│   │   │   └── reports.py          Generate, GeoJSON, download
│   │   ├── services/
│   │   │   ├── sonar_reader.py     XTF/JSF decode + synthetic swath model
│   │   │   ├── preprocessing.py    OpenCV chain + rendering
│   │   │   ├── detector.py         YOLOv8 + CV fallback + NMS
│   │   │   ├── georeference.py     Pixel → WGS-84 solver
│   │   │   ├── reporting.py        Markdown / JSON / GeoJSON briefs
│   │   │   └── store.py            In-memory survey registry
│   │   └── utils/
│   │       └── geodesy.py          WGS-84 math, no dependencies
│   ├── storage/                    uploads · processed PNGs · reports
│   ├── tests/
│   │   ├── test_pipeline.py        End-to-end pipeline checks
│   │   └── test_api.py             HTTP-level checks
│   ├── Dockerfile                  Portable container for any host
│   ├── requirements.txt            Pinned, Python 3.11 target
│   └── requirements-latest.txt     Version floors, Python 3.12+
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx                 Bento grid composition
│   │   ├── main.jsx
│   │   ├── index.css               Design tokens + component layer
│   │   ├── components/
│   │   │   ├── Hero.jsx            Headline, CTAs, trust signals
│   │   │   ├── PipelineStatus.jsx  Stage rail + classification breakdown
│   │   │   ├── IngestionBox.jsx    Upload + raw/filtered comparison slider
│   │   │   ├── InferenceBox.jsx    Metrics + live pixel → Lat/Long solver
│   │   │   ├── MapBox.jsx          Leaflet chart, pins, uncertainty circles
│   │   │   ├── ContactRegister.jsx Sorted anomaly list
│   │   │   ├── ActionBox.jsx       Triage + export
│   │   │   ├── Primitives.jsx      Bento shells, stats, meters, badges
│   │   │   └── Icons.jsx           Inline stroke icons
│   │   ├── hooks/
│   │   │   └── useSurvey.js        Pipeline state, stage gating
│   │   └── utils/
│   │       ├── api.js              Backend client
│   │       └── format.js           Severity tokens, DMS, formatters
│   ├── tailwind.config.js          Colour + type system
│   ├── vite.config.js              Dev proxy to :8000
│   ├── vercel.json                 Vercel build config
│   ├── netlify.toml                Netlify build config
│   └── package.json
│
├── render.yaml                     Render blueprint (backend)
├── start.ps1                       One-command start (Windows)
├── start.sh                        One-command start (macOS/Linux/Git Bash)
├── DEPLOYMENT.md                   Putting it online, step by step
└── README.md
```

---

## Prerequisites

| Requirement | Version | Notes |
| --- | --- | --- |
| Python | 3.11+ | 3.11 is the pinned target; 3.12/3.13 work with unpinned deps |
| Node.js | 18+ | Ships with npm — **required to run the dashboard** |
| pip / venv | bundled | |

> **Check your toolchain first:** `python --version` and `node --version`. If `node` or `npm` is missing, install Node.js LTS from <https://nodejs.org> before attempting the frontend steps.

---

## Setup — backend

From the repository root:

```bash
cd backend
python -m venv .venv
```

Activate the environment:

```bash
# Windows (PowerShell)
.venv\Scripts\Activate.ps1
```

```bash
# Windows (Git Bash)
source .venv/Scripts/activate
```

```bash
# macOS / Linux
source .venv/bin/activate
```

Install dependencies:

```bash
# Python 3.11 -- exact pins
pip install -r requirements.txt
```

```bash
# Python 3.12 / 3.13 / 3.14 -- version floors
pip install -r requirements-latest.txt
```

> **Which file?** `requirements.txt` pins exact versions against the Python 3.11 target. Those pins have no wheels on newer interpreters, so `requirements-latest.txt` carries minimum-version floors instead — that is the combination the project was smoke-tested against (FastAPI 0.141, NumPy 2.5, OpenCV 5.0, Pydantic 2.13 on CPython 3.14). `start.ps1` / `start.sh` pick the right one for you.

The test suites also need `httpx`:

```bash
pip install httpx
```

Run the API:

```bash
uvicorn app.main:app --reload --port 8000
```

Verify it is live:

- Interactive docs — <http://localhost:8000/docs>
- Health probe — <http://localhost:8000/api/health>

The health response tells you exactly which engines loaded:

```json
{
  "status": "ok",
  "version": "1.0.0",
  "pyxtf_available": true,
  "opencv_available": true,
  "ultralytics_available": false,
  "surveys_in_memory": 0
}
```

`ultralytics_available: false` is expected and fine — detection runs on the CV fallback path. To enable native YOLOv8, uncomment `ultralytics` in `requirements.txt`, reinstall, and point `WRECKOGNISE_MODEL_WEIGHTS` at a `.pt` file.

---

## Setup — frontend

In a **second terminal**, from the repository root:

```bash
cd frontend
npm install
```

```bash
npm run dev
```

Open <http://localhost:5173>.

Vite proxies `/api` and `/static` to `http://127.0.0.1:8000`, so the browser stays same-origin and uploads need no CORS handling. **Start the backend first** — the dashboard shows an "API Offline" badge otherwise.

Production build:

```bash
npm run build
npm run preview
```

To point the dashboard at a non-local backend, set `VITE_API_BASE` (e.g. in `frontend/.env.local`):

```
VITE_API_BASE=https://wreckognise.example.org
```

---

## Using the dashboard

1. **Explore Live Scan** — loads a modelled survey line end to end. Fastest way to see the whole pipeline.
2. **Upload Sonar Data** — drop a `.xtf` / `.jsf` capture, or click *Browse*. Pick the denoise kernel first (NLM for quality, Bilateral for speed).
3. **Compare the swath** — drag the split handle over the waterfall to put the raw and filtered images in the same pixels.
4. **Run Detection** — set a confidence threshold and infer. Boxes appear as a clickable vector overlay.
5. **Probe any pixel** — move the cursor across the annotated swath; the solver panel resolves that pixel to WGS-84 live, and *Show solve trace* prints the arithmetic.
6. **Work the chart** — click a pin or a register row; the map flies to it. Uncertainty circles are sized from the solver's own error budget.
7. **Triage** — flag an anomaly, escalate it for human review, confirm it, or dismiss it. Notes are attributed and appended.
8. **Export** — generate a Markdown brief, a JSON payload, or GeoJSON for QGIS/ArcGIS.

---

## How the georeferencing works

Each pixel resolves through five steps, all of which are returned in the `GeoSolution` so an operator can audit rather than trust:

1. **Row → ping index** → vessel fix and heading, from the packet's own navigation record.
2. **Column → across-track slant range.** `r_slant = |x − nadir| × (slant_range / samples_per_side)`; sign gives port vs starboard.
3. **Slant-range correction.** `r_ground = √(r_slant² − altitude²)` — the flat-seafloor correction. Ignoring it is the single largest avoidable error in side-scan positioning.
4. **True bearing.** Side-scan looks perpendicular to the track, so `bearing = heading ± 90°`.
5. **Direct geodetic problem** on the WGS-84 ellipsoid, using local meridian and prime-vertical radii of curvature. For sub-500 m swaths this is accurate to well under a centimetre — far tighter than the sensor error budget.

**Error budget** (1σ, combined in quadrature, in `georeference.py`):

| Term | Value |
| --- | --- |
| RTK-corrected GNSS fix | 0.20 m |
| Towfish layback estimate | 0.45 m |
| Heading (FOG / dual-antenna) | 0.35° × ground range |
| Sound-velocity uncertainty | 0.2% × ground range |

At a 40 m ground range that totals roughly **±0.55 m** — the "sub-metre GPS accuracy" claim on the hero, and it is reported per contact rather than asserted globally.

Target **height** comes from shadow geometry: `h = (L_shadow × altitude) / (r_ground + L_shadow)`.

---

## API reference

Full interactive docs at `/docs`. Summary:

### Ingestion

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/ingest/upload` | Multipart upload of a `.xtf` / `.jsf` capture |
| `POST` | `/api/ingest/demo` | Load a modelled demo line |
| `GET` | `/api/ingest/{id}/metadata` | Decoded file metadata |
| `GET` | `/api/ingest/{id}/telemetry?limit=` | Thinned navigation track |
| `GET` | `/api/ingest/surveys` | List surveys in memory |
| `DELETE` | `/api/ingest/{id}` | Drop a survey |

### Inference

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/inference/{id}/detect?confidence=&iou=` | Run detection + georeferencing |
| `GET` | `/api/inference/{id}/detections` | Filter by confidence / severity / review state |
| `PATCH` | `/api/inference/{id}/detections/{det}/review` | Flag, escalate, confirm, dismiss |
| `GET` | `/api/inference/{id}/georeference?x=&y=` | Solve an arbitrary pixel |
| `POST` | `/api/inference/{id}/georeference/bbox` | Solve a manually drawn box |

### Reporting

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/reports/generate` | Markdown / JSON / GeoJSON brief |
| `GET` | `/api/reports/{id}/geojson` | GeoJSON feature collection |
| `GET` | `/api/reports/download/{filename}` | Fetch a generated report |
| `GET` | `/api/reports/list` | Recent reports |

### Quick smoke test with curl

```bash
curl -s -X POST http://localhost:8000/api/ingest/demo -F denoise_method=nlm
```

```bash
curl -s -X POST "http://localhost:8000/api/inference/SVY-XXXXXXXXXX/detect?confidence=0.35"
```

---

## Testing

With the backend virtualenv active, from `backend/`:

```bash
python -m tests.test_pipeline
```

```bash
python -m tests.test_api
```

`test_pipeline` covers geodesy identities (a 100 m due-east hop must measure 100 m; the 3-4-5 slant-range triangle), ingestion shape and determinism, SNR/speckle improvement, detector recall against the planted-target ground truth, port/starboard bearing symmetry, rendering, and report generation.

`test_api` drives the same pipeline over HTTP: upload rejection, static PNG serving, review transitions, path-traversal rejection on report download, and stage gating.

Both print a per-check `PASS`/`FAIL` table and exit non-zero on failure, so they drop straight into CI.

---

## Configuration

Every setting in `backend/app/config.py` is overridable by environment variable with the `WRECKOGNISE_` prefix, or via a `backend/.env` file. See `backend/.env.example`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `WRECKOGNISE_DENOISE_METHOD` | `nlm` | `nlm` · `bilateral` · `none` |
| `WRECKOGNISE_NLM_H` | `10.0` | Non-Local Means filter strength |
| `WRECKOGNISE_CONFIDENCE_THRESHOLD` | `0.35` | Detection floor |
| `WRECKOGNISE_IOU_THRESHOLD` | `0.45` | NMS overlap ceiling |
| `WRECKOGNISE_MODEL_WEIGHTS` | `yolov8n-sonar.pt` | Path to YOLOv8 weights |
| `WRECKOGNISE_MAX_UPLOAD_MB` | `512` | Upload ceiling |
| `WRECKOGNISE_GPS_ANTENNA_OFFSET_M` | `0.0` | Lever-arm correction, bow-positive |
| `WRECKOGNISE_CORS_ORIGINS` | `localhost:5173,…` | Allowed dashboard origins |

---

## Design system

Colour follows a strict 60-30-10 split.

| Role | Share | Tokens |
| --- | --- | --- |
| Surface | 60% | Cream `#F9F6F0`, sand `#EFECE6`, shell `#E4E0D8` |
| Structure | 30% | Deep navy `#0A192F`, teal green `#1E3A3A` |
| Accent | 10% | Azure `#0077B6`, aqua `#00B4D8` |
| Pops | sparing | Coral `#FF6B6B`, sunset `#FF7A00`, amber `#FFB703` |

Pop colours are reserved for severity and alert states and are defined in exactly one place — `SEVERITY_STYLES` in `frontend/src/utils/format.js` — so severity reads identically on the register, the chart pins, the annotated PNG, and the brief.

**Typography:** Playfair Display (headers/display), Space Grotesk (technical labels, all numerics), IBM Plex Sans (UI body), Crimson Pro (prose). Loaded from Google Fonts with system fallbacks.

**Layout:** a 12-column bento grid — 7/5 for the two analysis cards, 7/5 for chart and register, full-width strips for pipeline state and actions. Collapses to a single column in reading order on small screens.

---

## Production notes

This is a hackathon prototype. Before it carries an operational survey:

- **Persistence.** `services/store.py` is an in-memory dict behind a five-method interface. Swap it for PostGIS/TimescaleDB by reimplementing those methods and nothing else. Surveys currently vanish on restart.
- **Long-running work.** Ingestion and inference run synchronously in the request. A multi-gigabyte line needs a task queue (Celery/RQ/`arq`) with progress over WebSocket.
- **Auth.** There is none. Add authentication and per-survey authorisation before exposing the API.
- **Model weights.** The reported mAP/precision/recall figures in `detector.py` are benchmark constants, not measured on your data. Train on a labelled corpus and update them alongside the weights.
- **Sound velocity.** The solver assumes a flat seafloor and a uniform sound-speed profile. Add a bathymetric surface and a measured SVP for survey-grade positioning.
- **Static files.** `/static` is served straight off disk by FastAPI; put it behind nginx or object storage in production.

**AI-derived contacts are decision support, not a substitute for qualified hydrographic review.** Positions are referenced to WGS-84.
