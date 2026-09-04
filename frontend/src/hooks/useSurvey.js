import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../utils/api'

/**
 * Single owner of the survey pipeline's state.
 *
 * Keeping ingest -> detect -> review -> report in one hook means the bento
 * boxes stay presentational, and the stage gating (you cannot detect before
 * you ingest, or report before you detect) lives in exactly one place.
 */
export function useSurvey() {
  const [health, setHealth] = useState(null)
  const [ingest, setIngest] = useState(null)
  const [inference, setInference] = useState(null)
  const [telemetry, setTelemetry] = useState([])
  const [report, setReport] = useState(null)

  const [selectedId, setSelectedId] = useState(null)
  const [busy, setBusy] = useState(null) // 'ingest' | 'detect' | 'report' | null
  const [error, setError] = useState(null)
  const [progress, setProgress] = useState(0)

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null))
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

  const resetDownstream = useCallback(() => {
    setInference(null)
    setReport(null)
    setSelectedId(null)
  }, [])

  const loadDemo = useCallback(
    (denoiseMethod = 'nlm') =>
      run('ingest', async () => {
        const result = await api.loadDemo(denoiseMethod)
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

  const detections = inference?.detections ?? []

  const selected = useMemo(
    () => detections.find((d) => d.detection_id === selectedId) ?? null,
    [detections, selectedId],
  )

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
    error,
    clearError: () => setError(null),
    loadDemo,
    uploadFile,
    detect,
    generateReport,
    reviewContact,
  }
}
