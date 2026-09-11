import { useState } from 'react'
import { Badge, BentoCard, CardHeader, EmptyState, Spinner } from './Primitives'
import {
  IconCheck,
  IconDownload,
  IconEye,
  IconFlag,
  IconReport,
  IconX,
} from './Icons'
import { api } from '../utils/api'
import { REVIEW_LABELS, classLabel, downloadText, severityStyle, toDMS } from '../utils/format'

const DISPOSITIONS = [
  {
    status: 'flagged',
    label: 'Flag Anomaly',
    icon: IconFlag,
    className: 'btn border border-coral/40 bg-transparent text-coral hover:bg-coral hover:text-cream',
  },
  { status: 'under_review', label: 'Human Review', icon: IconEye, className: 'btn-ghost' },
  { status: 'confirmed', label: 'Confirm', icon: IconCheck, className: 'btn-primary' },
  { status: 'dismissed', label: 'Dismiss', icon: IconX, className: 'btn-ghost' },
]

/** Disposition chip shown beside the severity badge. Labels come from
    REVIEW_LABELS so the chip and the register never drift apart. */
const REVIEW_CHIP = {
  flagged: 'bg-coral/20 text-coral border border-coral/35',
  under_review: 'bg-amber/20 text-amber border border-amber/35',
  confirmed: 'bg-aqua/20 text-aqua border border-aqua/35',
  dismissed: 'bg-cream/10 text-ink/45 border border-ink/20',
}

const FORMATS = [
  { id: 'markdown', label: 'Markdown', ext: 'md', mime: 'text/markdown' },
  { id: 'json', label: 'JSON', ext: 'json', mime: 'application/json' },
  { id: 'geojson', label: 'GeoJSON', ext: 'geojson', mime: 'application/geo+json' },
]

/**
 * Bento box 4b -- operator actions and reporting.
 *
 * Disposition and export live in the same card because they are one workflow:
 * an operator triages a contact, then exports the line once every contact has
 * been dealt with.
 */
export default function ActionBox({
  ingest,
  inference,
  selected,
  report,
  busy,
  onReview,
  onGenerate,
}) {
  const [format, setFormat] = useState('markdown')
  const [note, setNote] = useState('')

  const act = (status) => {
    if (!selected) return
    onReview(selected.detection_id, status, note.trim() || undefined)
    setNote('')
  }

  const style = selected ? severityStyle(selected.severity) : null
  const config = FORMATS.find((f) => f.id === format)

  const saveReport = () => {
    if (!report) return
    downloadText(`${report.report_id}.${config.ext}`, report.content, config.mime)
  }

  return (
    <BentoCard tone="teal" className="flex flex-col p-6">
      <CardHeader
        dark
        eyebrow="05 · Action & Reporting"
        title="Triage, escalate, export"
        meta="Operator disposition → executive brief → GIS handoff"
        action={
          <span className="hidden shrink-0 rounded-full bg-cream/8 p-2.5 text-aqua sm:block">
            <IconReport className="h-5 w-5" />
          </span>
        }
      />

      {/* --- selected contact triage --- */}
      <div className="mt-5 rounded-2xl bg-cream/45 p-4 ring-1 ring-ink/10">
        {!selected ? (
          <div className="py-4">
            <EmptyState
              dark
              icon={<IconFlag className="h-5 w-5" />}
              title="No contact selected"
              body="Pick a contact from the register or a pin on the chart to flag it, escalate it, or clear it."
            />
          </div>
        ) : (
          <>
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="label text-ink/40">Selected Contact</p>
                <h3 className="mt-1 font-display text-lg font-semibold text-ink">
                  {classLabel(selected.label)}
                </h3>
                <p className="font-mono text-2xs text-ink/40">{selected.detection_id}</p>
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1.5">
                <Badge className={style.badgeDark}>{style.label}</Badge>
                {REVIEW_CHIP[selected.review_status] && (
                  <Badge className={REVIEW_CHIP[selected.review_status]}>
                    {REVIEW_LABELS[selected.review_status]}
                  </Badge>
                )}
              </div>
            </div>

            <div className="mt-3 rounded-lg bg-cream/50 px-3 py-2 font-mono text-2xs leading-relaxed text-ink/60">
              {toDMS(selected.geo.latitude, 'lat')}
              <br />
              {toDMS(selected.geo.longitude, 'lon')}
              <br />
              <span className="text-ink/35">
                ± {selected.geo.horizontal_uncertainty_m.toFixed(2)} m ·{' '}
                {(selected.confidence * 100).toFixed(1)}% confidence
              </span>
            </div>

            {selected.notes && (
              <p className="mt-3 rounded-lg bg-amber/10 px-3 py-2 font-serif text-xs italic leading-relaxed text-amber">
                {selected.notes}
              </p>
            )}

            <label className="mt-3 block">
              <span className="label text-ink/40">Operator Note</span>
              <textarea
                value={note}
                onChange={(e) => setNote(e.target.value)}
                rows={2}
                placeholder="e.g. Strong shadow, consistent with a steel hull. Verify with ROV."
                className="mt-1.5 w-full resize-none rounded-lg border border-ink/12 bg-cream/50 px-3 py-2
                           font-serif text-xs text-ink placeholder:text-ink/25
                           focus:border-aqua focus:outline-none"
              />
            </label>

            {/* The disposition buttons write to a contact that is rendered in
                a different bento box, so without an active state here a click
                changes nothing the operator can see and reads as a dead
                button. Each one latches when it is the current disposition. */}
            <div className="mt-3 grid grid-cols-2 gap-2">
              {DISPOSITIONS.map(({ status, label, icon: Icon, className }) => {
                const isCurrent = selected.review_status === status
                return (
                  <button
                    key={status}
                    type="button"
                    onClick={() => act(status)}
                    aria-pressed={isCurrent}
                    className={`${className} !px-3 !py-2 ${
                      isCurrent ? 'ring-2 ring-ink/70 ring-offset-2 ring-offset-navy' : ''
                    }`}
                  >
                    {isCurrent ? <IconCheck className="h-3.5 w-3.5" /> : <Icon className="h-3.5 w-3.5" />}
                    {label}
                  </button>
                )
              })}
            </div>
          </>
        )}
      </div>

      {/* --- export --- */}
      <div className="mt-5">
        <p className="label text-ink/40">Export Format</p>
        <div className="mt-2 grid grid-cols-3 gap-2">
          {FORMATS.map((option) => (
            <button
              key={option.id}
              type="button"
              onClick={() => setFormat(option.id)}
              aria-pressed={format === option.id}
              className={`rounded-xl border px-3 py-2 font-mono text-2xs font-semibold uppercase tracking-wide transition-all ${
                format === option.id
                  ? 'border-aqua bg-aqua/15 text-aqua'
                  : 'border-ink/12 text-ink/50 hover:border-ink/30'
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => onGenerate(format)}
            disabled={!inference || busy === 'report'}
            className="btn-primary flex-1"
            title={inference ? 'Build the executive brief' : 'Run detection first'}
          >
            {busy === 'report' ? <Spinner /> : <IconReport className="h-4 w-4" />}
            {busy === 'report' ? 'Compiling…' : 'Generate Report'}
          </button>

          <a
            href={ingest ? api.geojsonUrl(ingest.survey_id) : undefined}
            className={`btn-ghost-light ${!inference ? 'pointer-events-none opacity-45' : ''}`}
            download
            title="Download contacts as GeoJSON for QGIS or ArcGIS"
          >
            <IconDownload className="h-4 w-4" />
            GIS Export
          </a>
        </div>
      </div>

      {/* --- generated brief --- */}
      {report && (
        <div className="mt-5 animate-rise-in">
          <div className="flex items-center justify-between">
            <div>
              <p className="label text-aqua">Report Ready</p>
              <p className="mt-0.5 font-mono text-2xs text-ink/40">
                {report.report_id} · {report.format} ·{' '}
                {report.content.length.toLocaleString()} chars
              </p>
            </div>
            <button type="button" onClick={saveReport} className="btn-ghost-light !px-3 !py-2">
              <IconDownload className="h-3.5 w-3.5" />
              Save
            </button>
          </div>

          <pre className="scroll-slim mt-3 max-h-56 overflow-auto whitespace-pre-wrap break-words rounded-xl bg-cream/60 p-4 font-mono text-2xs leading-relaxed text-ink/65">
            {report.content.slice(0, 2600)}
            {report.content.length > 2600 && '\n\n… truncated — use Save for the full brief.'}
          </pre>
        </div>
      )}
    </BentoCard>
  )
}
