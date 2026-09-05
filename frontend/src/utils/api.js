/**
 * Typed-ish client for the Wreckognise FastAPI backend.
 *
 * Vite proxies /api and /static to http://127.0.0.1:8000 in development, so
 * every path here stays relative and the browser never leaves its origin.
 */

const BASE = import.meta.env.VITE_API_BASE ?? ''

class ApiError extends Error {
  constructor(message, status, body) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

async function request(path, options = {}) {
  let response
  try {
    response = await fetch(`${BASE}${path}`, options)
  } catch {
    throw new ApiError(
      'Cannot reach the Wreckognise API. Is uvicorn running on port 8000?',
      0,
      null,
    )
  }

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

  review: (surveyId, detectionId, payload) =>
    request(`/api/inference/${surveyId}/detections/${detectionId}/review`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

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
