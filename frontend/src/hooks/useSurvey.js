import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, onBackendWaking } from '../utils/api'

/**
 * Single owner of the survey pipeline's state.
 *
 * Keeping ingest -> detect -> review -> report in one hook means the bento
 * boxes stay presentational, and the stage gating (you cannot detect before
 * you ingest, or report before you detect) lives in exactly one place.
 */
export function useSurvey() {
  // undefined = not asked yet, null = asked and the backend did not answer.
  // Collapsing the two lets the UI assert "offline" before it knows, which on
  // a free-tier instance that sleeps is wrong for the first several seconds of
  // every cold visit.
  const [health, setHealth] = useState(undefined)
  const [ingest, setIngest] = useState(null)
  const [inference, setInference] = useState(null)
  const [telemetry, setTelemetry] = useState([])
  const [report, setReport] = useState(null)

  const [samples, setSamples] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [busy, setBusy] = useState(null) // 'ingest' | 'detect' | 'report' | null
  const [error, setError] = useState(null)
  const [progress, setProgress] = useState(0)
  const [waking, setWaking] = useState(false)

  useEffect(() => onBackendWaking(setWaking), [])

  useEffect(() => {
    // Only a well-formed health payload counts as "online". Anything else --
    // an HTML rewrite from a static host, a proxy error page -- must read as
    // offline, or the badge cheerfully lies about a backend that isn't there.
    api
      .health()
      .then((body) => setHealth(body && typeof body === 'object' && body.status ? body : null))
      .catch(() => setHealth(null))

    api
      .samples()
      .then((r) => setSamples(Array.isArray(r?.samples) ? r.samples : []))
      .catch(() => setSamples([]))
  }, [])

  const run = useCallback(async (stage, work) => {
    setBusy(stage)
    setError(null)
    setProgress(8)
    // A determinate-looking ramp; the real completion snaps it to 100.
    const ticker = setInterval(() => setProgress((p) => (p < 88 ? p + 6 : p)), 260)
    try {
      return await work()
    } catch (err) {
      setError(err.message ?? String(err))
      return null
    } finally {
      clearInterval(ticker)
      setProgress(100)
      setBusy(null)
      setTimeout(() => setProgress(0), 700)
    }
  }, [])

  /*
   * How the current survey was made, as a replayable thunk.
   *
   * The backend holds surveys in memory and processed frames on an ephemeral
   * disk, so a restart -- a deploy, or the free instance waking from sleep --
   * leaves the page holding a survey the server has no record of. Every panel
   * then fails on its own: the waterfall 404s, the chart has no track, the
   * relief surface cannot be built.
   *
   * Replaying the original call rebuilds all of it. For the demo and the
   * bundled samples there is nothing to keep; for an upload the closure holds
   * the File, which is why this is a thunk rather than a description.
   */
  const sourceRef = useRef(null)
  const inflightRef = useRef(null)

  const resetDownstream = useCallback(() => {
    setInference(null)
    setReport(null)
    setSelectedId(null)
  }, [])

  const loadDemo = useCallback(
    (denoiseMethod = 'nlm') =>
      run('ingest', async () => {
        sourceRef.current = () => api.loadDemo(denoiseMethod)
        const result = await api.loadDemo(denoiseMethod)
        setIngest(result)
        resetDownstream()
        setTelemetry(await api.telemetry(result.survey_id))
        return result
      }),
    [run, resetDownstream],
  )

  /** Run a bundled REAL sonar image -- imagery the detector never trained on. */
  const loadSample = useCallback(
    (filename, denoiseMethod = 'nlm') =>
      run('ingest', async () => {
        sourceRef.current = () => api.loadSample(filename, denoiseMethod)
        const result = await api.loadSample(filename, denoiseMethod)
        setIngest(result)
        resetDownstream()
        setTelemetry(await api.telemetry(result.survey_id))
        return result
      }),
    [run, resetDownstream],
  )

  const uploadFile = useCallback(
    (file, options) =>
      run('ingest', async () => {
        sourceRef.current = () => api.upload(file, options)
        const result = await api.upload(file, options)
        setIngest(result)
        resetDownstream()
        setTelemetry(await api.telemetry(result.survey_id))
        return result
      }),
    [run, resetDownstream],
  )

  const detect = useCallback(
    (options) =>
      run('detect', async () => {
        if (!ingest) throw new Error('Ingest a sonar line before running detection.')
        const result = await api.detect(ingest.survey_id, options)
        setInference(result)
        setReport(null)
        setSelectedId(result.detections[0]?.detection_id ?? null)
        return result
      }),
    [run, ingest],
  )

  const generateReport = useCallback(
    (format = 'markdown') =>
      run('report', async () => {
        if (!ingest) throw new Error('Ingest a sonar line first.')
        if (!inference) throw new Error('Run detection before generating a report.')
        const result = await api.report({
          survey_id: ingest.survey_id,
          format,
          operator: 'Survey Lead',
          vessel: 'RV Sagar Nidhi',
        })
        setReport(result)
        return result
      }),
    [run, ingest, inference],
  )

  /** Optimistically update a contact's review state, rolling back on failure. */
  const reviewContact = useCallback(
    async (detectionId, reviewStatus, notes) => {
      if (!ingest || !inference) return
      const previous = inference.detections

      setInference((current) => ({
        ...current,
        detections: current.detections.map((d) =>
          d.detection_id === detectionId ? { ...d, review_status: reviewStatus } : d,
        ),
      }))

      try {
        const updated = await api.review(ingest.survey_id, detectionId, {
          review_status: reviewStatus,
          notes,
          operator: 'operator@wreckognise',
        })
        setInference((current) => ({
          ...current,
          detections: current.detections.map((d) =>
            d.detection_id === detectionId ? updated : d,
          ),
        }))
        setReport(null) // the brief is stale the moment a disposition changes
      } catch (err) {
        setInference((current) => ({ ...current, detections: previous }))
        setError(err.message ?? String(err))
      }
    },
    [ingest, inference],
  )

  /*
   * Memoised, and the reason is not tidiness. `inference?.detections ?? []`
   * evaluates to a NEW empty array on every render until detection has run.
   * ReliefView keys its effect on this value, and that effect sets state --
   * so each render produced a new array, which re-ran the effect, which set
   * state, which rendered. The image load was torn down and restarted before
   * it could ever finish, and the panel stayed blank. It only settled once
   * detection ran and `inference.detections` became a stable reference, which
   * is why the relief view sometimes "worked" and mostly did not.
   */
  const detections = useMemo(() => inference?.detections ?? [], [inference])

  const selected = useMemo(
    () => detections.find((d) => d.detection_id === selectedId) ?? null,
    [detections, selectedId],
  )

  /**
   * Acknowledge a hazard contact.
   *
   * Not routed through `run()` like the pipeline stages: acknowledging is not
   * a stage, and blocking the whole dashboard behind a progress bar to record
   * "I saw this" would be absurd. It updates the one detection in place.
   */
  const acknowledgeHazard = useCallback(
    async (detectionId, operator = 'operator') => {
      if (!ingest) return null
      try {
        const updated = await api.acknowledge(ingest.survey_id, detectionId, operator)
        setInference((current) =>
          current
            ? {
                ...current,
                detections: current.detections.map((d) =>
                  d.detection_id === updated.detection_id ? updated : d,
                ),
              }
            : current,
        )
        return updated
      } catch (err) {
        setError(err.message ?? String(err))
        return null
      }
    },
    [ingest],
  )

  /**
   * Rebuild a survey the server has forgotten.
   *
   * Guarded against re-entry: several panels can notice the loss at once, and
   * three of them each kicking off an ingest would be worse than the failure.
   * Detection is re-run only if it had already been run, so recovery restores
   * what was on screen rather than silently discarding the operator's
   * contacts along with the survey.
   */
  const recover = useCallback(() => {
    // A second caller while a rebuild is in flight gets THE SAME promise, not
    // a sentinel. Returning null for "already running" made it indistinguishable
    // from "the replay failed", and the Rebuild button reported failure on a
    // rebuild that was about to succeed. One promise, one truth.
    if (inflightRef.current) return inflightRef.current
    const replay = sourceRef.current
    if (!replay) return Promise.resolve(null)
    const hadInference = Boolean(inference)
    const attempt = run('ingest', async () => {
      const result = await replay()
      setIngest(result)
      resetDownstream()
      setTelemetry(await api.telemetry(result.survey_id))
      if (hadInference) {
        const again = await api.detect(result.survey_id)
        setInference(again)
        setSelectedId(again.detections[0]?.detection_id ?? null)
      }
      return result
    }).finally(() => {
      inflightRef.current = null
    })
    inflightRef.current = attempt
    return attempt
  }, [run, resetDownstream, inference])

  const stage = useMemo(() => {
    if (inference) return 'complete'
    if (ingest) return 'preprocessed'
    return 'idle'
  }, [ingest, inference])

  return {
    health,
    ingest,
    inference,
    telemetry,
    report,
    detections,
    selected,
    selectedId,
    setSelectedId,
    stage,
    busy,
    progress,
    waking,
    error,
    clearError: () => setError(null),
    loadDemo,
    loadSample,
    recover,
    samples,
    uploadFile,
    detect,
    generateReport,
    reviewContact,
    acknowledgeHazard,
  }
}
