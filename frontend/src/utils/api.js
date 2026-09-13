/**
 * Typed-ish client for the Wreckognise FastAPI backend.
 *
 * Vite proxies /api and /static to http://127.0.0.1:8000 in development, so
 * every path here stays relative and the browser never leaves its origin.
 */

const BASE = import.meta.env.VITE_API_BASE ?? ''

/**
 * The hosted backend runs on a free instance that is suspended after 15
 * minutes without traffic. The first request afterwards has to wait for a cold
 * boot -- measured at 43 seconds -- during which the platform either holds the
 * connection open or answers 502/503. Both used to surface as "is uvicorn
 * running on port 8000?", which is a local-development question shown to a
 * visitor on the public site.
 *
 * So: wait long enough for a boot, retry the failures a boot actually causes,
 * and let the UI say the backend is waking rather than that it is broken.
 */
const REQUEST_TIMEOUT_MS = 90_000
const NETWORK_RETRIES = 3
const RETRY_BACKOFF_MS = [2000, 4000, 7000]
const COLD_START_STATUSES = new Set([502, 503, 504, 522, 524])

class ApiError extends Error {
  constructor(message, status, body) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

const wakeListeners = new Set()
let waking = false

/** Subscribe to "the backend is cold-starting" transitions. Returns an unsubscribe. */
export function onBackendWaking(listener) {
  wakeListeners.add(listener)
  listener(waking)
  return () => wakeListeners.delete(listener)
}

function setWaking(next) {
  if (waking === next) return
  waking = next
  wakeListeners.forEach((l) => l(next))
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

async function fetchWithTimeout(url, options) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)
  try {
    return await fetch(url, { ...options, signal: controller.signal })
  } finally {
    clearTimeout(timer)
  }
}

const unreachable = () =>
  new ApiError(
    BASE
      ? `Cannot reach the Wreckognise API at ${BASE}. The backend sleeps when idle and ` +
        'takes about a minute to wake; it did not answer within that window. Try again in a moment.'
      : 'Cannot reach the Wreckognise API. Is uvicorn running on port 8000?',
    0,
    null,
  )

async function request(path, options = {}) {
  let response = null
  // Only a hosted backend can be asleep. Against a local uvicorn a refused
  // connection is final, and retrying it just delays an honest error by 13 s.
  const retries = BASE ? NETWORK_RETRIES : 0

  for (let attempt = 0; attempt <= retries; attempt += 1) {
    try {
      response = await fetchWithTimeout(`${BASE}${path}`, options)
      if (!COLD_START_STATUSES.has(response.status)) break
    } catch {
      response = null // network error, or the 90 s timeout fired
    }

    if (attempt === retries) {
      setWaking(false)
      throw unreachable()
    }
    setWaking(true)
    await sleep(RETRY_BACKOFF_MS[attempt] ?? 7000)
  }

  setWaking(false)

  if (!response.ok) {
    let detail = `Request failed (${response.status})`
    let body = null
    try {
      body = await response.json()
      if (body?.detail) {
        detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
      }
    } catch {
      /* a non-JSON error body is not worth failing twice over */
    }
    throw new ApiError(detail, response.status, body)
  }

  if (response.status === 204) return null

  const contentType = response.headers.get('content-type') ?? ''
  if (contentType.includes('application/json')) return response.json()

  // A 200 that is not JSON almost always means the request never reached the
  // API. Static hosts rewrite unmatched paths to index.html, so /api/* comes
  // back as the dashboard's own HTML with a success status -- which would sail
  // past the `response.ok` check above and fail later, somewhere confusing.
  if (contentType.includes('text/html')) {
    throw new ApiError(
      BASE
        ? `Expected JSON from ${BASE}${path} but received HTML. That host is not serving the Wreckognise API -- check VITE_API_BASE.`
        : `Request to ${path} returned the dashboard's own HTML, not API data. ` +
          'VITE_API_BASE is unset, so the call went to this site instead of the backend. ' +
          'Set it to your backend URL and redeploy.',
      response.status,
      null,
    )
  }

  return response.text()
}

/**
 * Resolve a backend-relative asset path (rendered waterfalls, annotated
 * frames) into something the browser can actually fetch.
 *
 * The API returns root-relative paths like `/static/processed/x.png`. In
 * development Vite proxies those to the backend, but in production the browser
 * resolves them against the dashboard's own origin -- where a static host's
 * catch-all rewrite answers with index.html, and the <img> renders broken.
 */
export const assetUrl = (path) => {
  if (!path) return path
  return /^https?:\/\//i.test(path) ? path : `${BASE}${path}`
}

export const api = {
  health: () => request('/api/health'),

  // --- ingestion ---------------------------------------------------
  loadDemo: (denoiseMethod = 'nlm', lineName = 'GoM-Line-07.xtf') => {
    const form = new FormData()
    form.append('denoise_method', denoiseMethod)
    form.append('line_name', lineName)
    return request('/api/ingest/demo', { method: 'POST', body: form })
  },

  upload: (file, { denoiseMethod = 'nlm', applyTvg = true, applyClahe = true } = {}) => {
    const form = new FormData()
    form.append('file', file)
    form.append('denoise_method', denoiseMethod)
    form.append('apply_tvg', String(applyTvg))
    form.append('apply_clahe', String(applyClahe))
    return request('/api/ingest/upload', { method: 'POST', body: form })
  },

  samples: () => request('/api/ingest/samples'),

  loadSample: (filename, denoiseMethod = 'nlm') => {
    const form = new FormData()
    form.append('filename', filename)
    form.append('denoise_method', denoiseMethod)
    return request('/api/ingest/sample', { method: 'POST', body: form })
  },

  telemetry: (surveyId, limit = 400) =>
    request(`/api/ingest/${surveyId}/telemetry?limit=${limit}`),

  surveys: () => request('/api/ingest/surveys'),

  // --- inference ---------------------------------------------------
  detect: (surveyId, { confidence, iou } = {}) => {
    const params = new URLSearchParams()
    if (confidence != null) params.set('confidence', confidence)
    if (iou != null) params.set('iou', iou)
    const query = params.toString()
    return request(`/api/inference/${surveyId}/detect${query ? `?${query}` : ''}`, {
      method: 'POST',
    })
  },

  georeference: (surveyId, x, y) =>
    request(`/api/inference/${surveyId}/georeference?x=${x}&y=${y}`),

  /** Eigen-CAM heat map for one contact. A URL, not a fetch: the browser
   *  caches the image and the backend caches the computation. */
  attentionUrl: (surveyId, detectionId) =>
    `${BASE}/api/inference/${surveyId}/detections/${detectionId}/attention`,

  /** Assert that a human has seen a hazard contact. Deliberately not `review`:
   *  review is a judgement, this is only "I looked". */
  acknowledge: (surveyId, detectionId, operator = 'operator') =>
    request(
      `/api/inference/${surveyId}/detections/${detectionId}/acknowledge` +
        `?operator=${encodeURIComponent(operator)}`,
      { method: 'POST' },
    ),

  review: (surveyId, detectionId, payload) =>
    request(`/api/inference/${surveyId}/detections/${detectionId}/review`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  // --- reference data -----------------------------------------------
  catalogue: () => request('/api/catalogue'),

  // --- reporting ---------------------------------------------------
  report: (payload) =>
    request('/api/reports/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  geojsonUrl: (surveyId) => `${BASE}/api/reports/${surveyId}/geojson`,
}

export { ApiError }
