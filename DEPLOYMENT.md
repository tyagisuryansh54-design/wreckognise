# Deploying Wreckognise

Two pieces deploy separately: the **FastAPI backend** (a Python web service) and the **React dashboard** (static files). The dashboard needs to know the backend's URL, so deploy the backend first.

Everything below has a free tier. Budget about 20 minutes end to end.

---

## Read this before you start

Wreckognise was built as a hackathon prototype, and two design choices matter once it leaves your laptop:

**Surveys live in process memory.** `backend/app/services/store.py` is a Python dict. A restart, a redeploy, or a free-tier idle timeout wipes every ingested survey. The dashboard recovers in seconds — click **Explore Live Scan** — but a link you sent someone yesterday will not still show yesterday's contacts.

**Rendered PNGs are written to local disk.** Same story: free tiers give you a fresh filesystem on each deploy.

Both are fine for a demo, where each visitor runs their own scan anyway. Neither is fine for real survey work. The [Making it durable](#making-it-durable) section says what to change.

**Keep the backend at one instance.** Because the store is per-process, a second instance would answer "run detection on survey X" for a survey it never ingested, and return a confusing 404. The blueprint pins `numInstances: 1`.

---

## Step 1 — Push to GitHub

Every host below deploys from a Git repository.

```bash
cd wreckognise
git init
git add .
git commit -m "Wreckognise: AI marine survey agent"
```

Create an empty repo on GitHub, then:

```bash
git remote add origin https://github.com/<you>/wreckognise.git
git branch -M main
git push -u origin main
```

The included `.gitignore` already keeps `node_modules`, `.venv`, `.env` and storage artefacts out.

---

## Step 2 — Deploy the backend (Render)

1. Go to <https://dashboard.render.com> and sign in with GitHub.
2. **New → Blueprint**, pick your repo. Render reads `render.yaml` and configures the service.
3. It will ask for the two `sync: false` variables. **Leave both blank for now** — you do not know the dashboard's URL yet.
4. Click **Apply**. First build takes 3–5 minutes (OpenCV and NumPy are large wheels).
5. Copy your service URL, e.g. `https://wreckognise-api.onrender.com`.

Verify it is alive:

```
https://wreckognise-api.onrender.com/api/health
```

You want `"status": "ok"`. Interactive docs are at `/docs`.

> **No blueprint?** Create a Web Service manually with **Root Directory** `backend`, build `pip install -r requirements.txt`, start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, health check path `/api/health`, and `PYTHON_VERSION=3.11.9`.

### Alternatives

Both read `backend/Dockerfile`, so the container is identical everywhere:

- **Railway** — New Project → Deploy from GitHub → set root directory to `backend`. Detects the Dockerfile.
- **Fly.io** — `cd backend && fly launch --dockerfile Dockerfile`
- **Google Cloud Run** — `gcloud run deploy --source backend`

Each injects `$PORT`, which the Dockerfile's `CMD` already honours.

---

## Step 3 — Deploy the dashboard (Vercel)

1. Go to <https://vercel.com/new> and import the same repo.
2. Set **Root Directory** to `frontend`. Vercel reads `frontend/vercel.json` for the rest.
3. Add one environment variable:

   | Name | Value |
   | --- | --- |
   | `VITE_API_BASE` | `https://wreckognise-api.onrender.com` |

   Your backend URL from step 2, **no trailing slash**.
4. **Deploy.** Copy the resulting URL, e.g. `https://wreckognise.vercel.app`.

> `VITE_API_BASE` is baked in at build time, not read at runtime. Change it later and you must redeploy for it to take effect.

**Netlify instead?** `netlify.toml` is already configured — import the repo, set the same environment variable, deploy.

---

## Step 4 — Open CORS to the dashboard

The backend rejects browser requests from unknown origins, so it does not yet trust your dashboard. In Render → your service → **Environment**, set:

| Key | Value |
| --- | --- |
| `WRECKOGNISE_CORS_ORIGINS` | `https://wreckognise.vercel.app` |

Your dashboard URL, no trailing slash. Comma-separate several if you have more than one.

To let Vercel's per-commit preview URLs through as well, also set:

| Key | Value |
| --- | --- |
| `WRECKOGNISE_CORS_ORIGIN_REGEX` | `https://.*\.vercel\.app` |

Save. Render restarts automatically (~30 seconds).

---

## Step 5 — Verify

Open your dashboard URL and check, in order:

1. The badge top-right reads **ENGINES ONLINE**, not "API Offline".
2. Click **Explore Live Scan** — the pipeline rail should tick through Ingest and Filter.
3. Click **Run Detection** — contacts appear, pins drop on the chart.
4. Click **Generate Report** — the brief renders.

If the badge says **API Offline**, it is almost always one of these:

| Symptom | Cause | Fix |
| --- | --- | --- |
| Console shows a CORS error | Step 4 not done, or URL mismatch | Check for a trailing slash or `http` vs `https` |
| Requests go to the dashboard's own domain | `VITE_API_BASE` missing at build time | Set it, then **redeploy** — it is compile-time |
| First request hangs ~50 s, then works | Free instance was asleep | Normal. Upgrade, or warm it before a demo |
| 404 on `/api/health` | Root directory not set to `backend` | Fix the service's root directory |

---

## Free-tier behaviour worth knowing before a demo

Render's free web services **sleep after 15 minutes of inactivity**, and the next request takes roughly 50 seconds to wake them. In a live demo that reads as a broken app.

Open the backend's `/api/health` in a tab five minutes before you present. That wakes it, and the dashboard will feel instant. For anything you cannot risk, Render's cheapest paid instance removes the sleep entirely.

---

## Making it durable

Change these before Wreckognise carries a real survey:

**Persistence.** `services/store.py` is an in-memory dict behind a five-method interface (`put`, `get`, `list_ids`, `all`, `delete`). Reimplement those against PostgreSQL with PostGIS — contacts are points with attributes, which is exactly what PostGIS is for — and nothing else in the codebase changes.

**File storage.** Rendered waterfalls go to local disk via `settings.processed_dir`. Point them at S3 or Cloudflare R2, or attach a Render persistent disk.

**Long-running work.** Ingestion and inference run inside the request. A multi-gigabyte sonar line will exceed the platform's request timeout. Move both to a task queue (Celery, RQ, or `arq`) and stream progress over WebSocket.

**Auth.** There is none — anyone with the URL can upload files and consume CPU. Add authentication before it is public, and cap `WRECKOGNISE_MAX_UPLOAD_MB`.

**Model weights.** The mAP/precision/recall figures in `detector.py` are benchmark constants, not measured on your data. If you train real weights, update those numbers alongside them.

---

## Full environment variable reference

### Backend

| Variable | Default | Notes |
| --- | --- | --- |
| `WRECKOGNISE_CORS_ORIGINS` | localhost origins | **Required in production.** Comma-separated, no trailing slashes |
| `WRECKOGNISE_CORS_ORIGIN_REGEX` | unset | Optional, for preview deploys |
| `WRECKOGNISE_DEBUG` | `true` | Set `false` in production |
| `WRECKOGNISE_MAX_UPLOAD_MB` | `512` | Lower it on a public deployment |
| `WRECKOGNISE_CONFIDENCE_THRESHOLD` | `0.35` | Detection floor |
| `WRECKOGNISE_MODEL_WEIGHTS` | `yolov8n-sonar.pt` | Path to YOLOv8 weights |
| `PORT` | `8000` | Injected by the host; the Dockerfile honours it |

### Frontend

| Variable | Notes |
| --- | --- |
| `VITE_API_BASE` | **Required in production.** Full backend origin, no trailing slash. Build-time only |
