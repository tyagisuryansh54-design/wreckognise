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
import { classLabel, downloadText, severityStyle, toDMS } from '../utils/format'

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
      <div className="mt-5 rounded-2xl bg-navy/45 p-4 ring-1 ring-cream/10">
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
                <p className="label text-cream/40">Selected Contact</p>
                <h3 className="mt-1 font-display text-lg font-semibold text-cream">
                  {classLabel(selected.label)}
                </h3>
                <p className="font-mono text-2xs text-cream/40">{selected.detection_id}</p>
              </div>
              <Badge className={`shrink-0 ${style.badgeDark}`}>{style.label}</Badge>
            </div>

            <div className="mt-3 rounded-lg bg-navy/50 px-3 py-2 font-mono text-2xs leading-relaxed text-cream/60">
              {toDMS(selected.geo.latitude, 'lat')}
              <br />
              {toDMS(selected.geo.longitude, 'lon')}
              <br />
              <span className="text-cream/35">
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
              <span className="label text-cream/40">Operator Note</span>
              <textarea
                value={note}
                onChange={(e) => setNote(e.target.value)}
                rows={2}
                placeholder="e.g. Strong shadow, consistent with a steel hull. Verify with ROV."
                className="mt-1.5 w-full resize-none rounded-lg border border-cream/12 bg-navy/50 px-3 py-2
                           font-serif text-xs text-cream placeholder:text-cream/25
                           focus:border-aqua focus:outline-none"
              />
            </label>

            <div className="mt-3 grid grid-cols-2 gap-2">
              <button type="button" onClick={() => act('flagged')} className="btn-alert !px-3 !py-2">
                <IconFlag className="h-3.5 w-3.5" />
                Flag Anomaly
              </button>
              <button
                type="button"
                onClick={() => act('under_review')}
                className="btn !bg-amber !px-3 !py-2 !text-navy hover:!bg-sunset hover:!text-white"
              >
                <IconEye className="h-3.5 w-3.5" />
                Human Review
              </button>
              <button
                type="button"
                onClick={() => act('confirmed')}
                className="btn !bg-aqua !px-3 !py-2 !text-navy hover:!bg-azure hover:!text-white"
              >
                <IconCheck className="h-3.5 w-3.5" />
                Confirm
              </button>
              <button type="button" onClick={() => act('dismissed')} className="btn-ghost-light !px-3 !py-2">
                <IconX className="h-3.5 w-3.5" />
                Dismiss
              </button>
            </div>
          </>
        )}
      </div>

      {/* --- export --- */}
      <div className="mt-5">
        <p className="label text-cream/40">Export Format</p>
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
                  : 'border-cream/12 text-cream/50 hover:border-cream/30'
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
              <p className="mt-0.5 font-mono text-2xs text-cream/40">
                {report.report_id} · {report.format} ·{' '}
                {report.content.length.toLocaleString()} chars
              </p>
            </div>
            <button type="button" onClick={saveReport} className="btn-ghost-light !px-3 !py-2">
              <IconDownload className="h-3.5 w-3.5" />
              Save
            </button>
          </div>

          <pre className="scroll-slim mt-3 max-h-56 overflow-auto whitespace-pre-wrap break-words rounded-xl bg-navy/60 p-4 font-mono text-2xs leading-relaxed text-cream/65">
            {report.content.slice(0, 2600)}
            {report.content.length > 2600 && '\n\n… truncated — use Save for the full brief.'}
          </pre>
        </div>
      )}
    </BentoCard>
  )
}
