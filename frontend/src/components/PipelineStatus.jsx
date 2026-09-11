import { BentoCard, Meter, Stat } from './Primitives'
import { classLabel, severityStyle } from '../utils/format'

const STAGES = [
  { id: 'ingest', label: 'Ingest', detail: 'pyxtf decode' },
  { id: 'filter', label: 'Filter', detail: 'OpenCV denoise' },
  { id: 'detect', label: 'Detect', detail: 'YOLOv8' },
  { id: 'georef', label: 'Georeference', detail: 'WGS-84 solve' },
  { id: 'report', label: 'Report', detail: 'Brief + GIS' },
]

/** Which stages are done, given where the pipeline has reached. */
function reachedIndex(stage, hasReport) {
  if (hasReport) return 5
  if (stage === 'complete') return 4
  if (stage === 'preprocessed') return 2
  return 0
}

/**
 * A wide, low bento tile: the pipeline's state of play plus the headline
 * figures, so the whole run is legible without scrolling the grid.
 */
export default function PipelineStatus({ stage, ingest, inference, report, busy }) {
  const reached = reachedIndex(stage, Boolean(report))
  const summary = inference?.summary
  const classes = Object.entries(summary?.by_class ?? {}).sort((a, b) => b[1] - a[1])

  return (
    <BentoCard tone="light" className="p-6">
      <div className="grid gap-6 lg:grid-cols-[1.35fr_1fr]">
        {/* --- stage rail --- */}
        <div>
          <p className="label text-azure">Pipeline State</p>
          <ol className="mt-4 flex items-start justify-between gap-1">
            {STAGES.map((item, index) => {
              const done = index < reached
              const active =
                (busy === 'ingest' && index <= 1) ||
                (busy === 'detect' && (index === 2 || index === 3)) ||
                (busy === 'report' && index === 4)

              return (
                <li key={item.id} className="relative flex flex-1 flex-col items-center text-center">
                  {index > 0 && (
                    <span
                      className={`absolute right-1/2 top-3.5 h-0.5 w-full -translate-y-1/2 ${
                        done ? 'bg-azure' : 'bg-ink/12'
                      }`}
                      aria-hidden="true"
                    />
                  )}
                  <span
                    className={`relative z-10 grid h-7 w-7 place-items-center rounded-full font-mono text-2xs font-bold transition-colors ${
                      active
                        ? 'bg-aqua text-ink ring-4 ring-aqua/25'
                        : done
                          ? 'bg-azure text-cream'
                          : 'bg-sand text-ink/35 ring-1 ring-ink/10'
                    }`}
                  >
                    {done && !active ? '✓' : index + 1}
                  </span>
                  <span
                    className={`mt-2 font-mono text-2xs font-semibold uppercase tracking-wide ${
                      done || active ? 'text-ink' : 'text-ink/35'
                    }`}
                  >
                    {item.label}
                  </span>
                  <span className="mt-0.5 hidden font-serif text-2xs text-ink/40 sm:block">
                    {item.detail}
                  </span>
                </li>
              )
            })}
          </ol>

          <div className="mt-6 grid grid-cols-2 gap-4 border-t border-ink/8 pt-4 sm:grid-cols-4">
            <Stat
              label="Pings"
              value={ingest ? ingest.metadata.ping_count : '—'}
            />
            <Stat
              label="Coverage"
              value={summary ? summary.area_surveyed_km2.toFixed(4) : '—'}
              unit={summary ? 'km²' : ''}
            />
            <Stat
              label="Contacts"
              value={summary ? summary.total : '—'}
              accent={summary?.total ? 'text-azure' : undefined}
            />
            <Stat
              label="Peak Conf."
              value={summary ? `${(summary.highest_confidence * 100).toFixed(0)}%` : '—'}
            />
          </div>
        </div>

        {/* --- class distribution --- */}
        <div className="lg:border-l lg:border-ink/8 lg:pl-6">
          <p className="label text-azure">Contact Classification</p>
          {classes.length === 0 ? (
            <p className="mt-4 font-serif text-sm text-ink/45">
              No contacts classified yet. Run detection to break the swath down by
              anomaly class and severity.
            </p>
          ) : (
            <ul className="mt-4 space-y-2.5">
              {classes.map(([name, count]) => {
                const share = count / Math.max(summary.total, 1)
                return (
                  <li key={name}>
                    <div className="flex items-baseline justify-between">
                      <span className="font-sans text-xs font-medium text-ink">
                        {classLabel(name)}
                      </span>
                      <span className="font-mono text-2xs tabular-nums text-ink/50">
                        {count} · {(share * 100).toFixed(0)}%
                      </span>
                    </div>
                    <div className="mt-1">
                      <Meter
                        value={share}
                        colour="bg-gradient-to-r from-azure to-aqua"
                        height="h-1"
                      />
                    </div>
                  </li>
                )
              })}
            </ul>
          )}

          {summary && (
            <div className="mt-4 flex flex-wrap gap-1.5 border-t border-ink/8 pt-3">
              {['critical', 'high', 'medium', 'low'].map((severity) => {
                const count = summary.by_severity[severity]
                if (!count) return null
                const style = severityStyle(severity)
                return (
                  <span key={severity} className={`badge ${style.badge}`}>
                    <span className={`h-1.5 w-1.5 rounded-full ${style.dot}`} />
                    {style.label} {count}
                  </span>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </BentoCard>
  )
}
