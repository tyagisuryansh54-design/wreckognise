import { useMemo, useState } from 'react'
import { BentoCard, CardHeader, EmptyState, Meter } from './Primitives'
import { IconAlert, IconTarget } from './Icons'
import { REVIEW_LABELS, classLabel, severityStyle } from '../utils/format'

/** Disposition colours. Pending is absent on purpose -- it renders nothing. */
const REVIEW_TONES = {
  flagged: 'text-coral',
  under_review: 'text-amber',
  confirmed: 'text-aqua',
  dismissed: 'text-ink/35',
}

const FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'flagged', label: 'Flagged' },
  { id: 'pending', label: 'Pending' },
]

/**
 * Bento box 4a -- the anomaly register.
 *
 * This is the operator's working list: sorted by severity then confidence, so
 * the thing most likely to sink a ship is always the first row on screen.
 */
export default function ContactRegister({ detections, selected, onSelect, summary, simulatedNav = false }) {
  const [filter, setFilter] = useState('all')

  const rows = useMemo(() => {
    const order = { critical: 0, high: 1, medium: 2, low: 3 }
    return detections
      .filter((d) => {
        if (filter === 'all') return true
        return d.review_status === filter
      })
      .sort(
        (a, b) => order[a.severity] - order[b.severity] || b.confidence - a.confidence,
      )
  }, [detections, filter])

  return (
    <BentoCard tone="light" className="flex flex-col p-6">
      <CardHeader
        eyebrow="04 · Anomaly Register"
        title="Contacts awaiting disposition"
        meta={
          summary
            ? `${summary.total} contacts · mean confidence ${(summary.mean_confidence * 100).toFixed(1)}%`
            : 'Run detection to populate the register'
        }
        action={
          <span className="hidden shrink-0 rounded-full bg-ink/5 p-2.5 text-azure sm:block">
            <IconTarget className="h-5 w-5" />
          </span>
        }
      />

      <div className="mt-4 flex gap-1.5 rounded-full bg-sand p-1">
        {FILTERS.map((option) => {
          const count =
            option.id === 'all'
              ? detections.length
              : detections.filter((d) => d.review_status === option.id).length
          return (
            <button
              key={option.id}
              type="button"
              onClick={() => setFilter(option.id)}
              aria-pressed={filter === option.id}
              className={`flex-1 rounded-full px-2.5 py-1.5 font-mono text-2xs font-semibold uppercase tracking-wide transition-colors ${
                filter === option.id ? 'bg-navy text-ink' : 'text-ink/50 hover:text-ink'
              }`}
            >
              {option.label}
              <span className={filter === option.id ? 'ml-1.5 text-aqua' : 'ml-1.5 text-ink/35'}>
                {count}
              </span>
            </button>
          )
        })}
      </div>

      <div className="scroll-slim mt-4 max-h-[26rem] flex-1 space-y-2 overflow-y-auto pr-1">
        {rows.length === 0 ? (
          <div className="h-48">
            <EmptyState
              icon={<IconAlert className="h-5 w-5" />}
              title={
                detections.length
                  ? 'Nothing matches this filter'
                  : summary
                    ? 'No contacts cleared the threshold'
                    : 'Register is empty'
              }
              body={
                detections.length
                  ? 'Switch back to “All” to see every contact on this line.'
                  : summary
                    // The detector ran and returned nothing -- almost always a
                    // confidence threshold set above what this line supports.
                    // Saying "run the detector" here sends the operator to a
                    // button they already pressed.
                    ? 'The detector ran but no anomaly beat the confidence threshold. Lower it in the inference panel and run detection again.'
                    : 'Run the detector to populate the contact register.'
              }
            />
          </div>
        ) : (
          rows.map((d) => {
            const style = severityStyle(d.severity)
            const active = selected?.detection_id === d.detection_id
            return (
              <button
                key={d.detection_id}
                type="button"
                onClick={() => onSelect(d.detection_id)}
                className={`w-full rounded-xl border px-3.5 py-3 text-left transition-all ${
                  active
                    ? `border-transparent bg-navy text-ink ring-2 ${style.ring}`
                    : 'border-ink/10 bg-sand hover:border-ink/25 hover:bg-navy-soft'
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className={`h-2 w-2 shrink-0 rounded-full ${style.dot}`} />
                      <p
                        className={`truncate font-display text-sm font-semibold ${
                          active ? 'text-ink' : 'text-ink'
                        }`}
                      >
                        {classLabel(d.label)}
                      </p>
                    </div>
                    <p
                      className={`mt-0.5 font-mono text-2xs ${
                        active ? 'text-ink/40' : 'text-ink/40'
                      }`}
                    >
                      {d.detection_id}
                    </p>
                  </div>

                  <div className="shrink-0 text-right">
                    <p
                      className={`font-mono text-sm font-semibold tabular-nums ${
                        active ? 'text-aqua' : 'text-azure'
                      }`}
                    >
                      {(d.confidence * 100).toFixed(1)}%
                    </p>
                    {/* Every contact starts pending, so printing "Pending" on
                        every row is noise that buries the rows an operator has
                        actually dealt with. Show a disposition only once there
                        is one, and colour it by what it means. */}
                    {d.review_status !== 'pending' && (
                      <p
                        className={`font-mono text-2xs font-semibold ${
                          REVIEW_TONES[d.review_status] ??
                          (active ? 'text-ink/40' : 'text-ink/40')
                        }`}
                      >
                        {REVIEW_LABELS[d.review_status]}
                      </p>
                    )}
                  </div>
                </div>

                <div className="mt-2.5">
                  <Meter
                    value={d.confidence}
                    colour={active ? 'bg-aqua' : 'bg-azure'}
                    track={active ? 'bg-cream/12' : 'bg-ink/8'}
                    height="h-1"
                  />
                </div>

                <div
                  className={`mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-2xs ${
                    active ? 'text-ink/55' : 'text-ink/50'
                  }`}
                >
                  {d.geometry_agrees === false && (
                    <>
                      <span className="font-mono text-2xs text-amber" title={`Measured shape fits ${d.geometry_suggests} better`}>
                        ⚠ class uncertain
                      </span>
                      <span className="text-ink/25">·</span>
                    </>
                  )}
                  {simulatedNav ? (
                    <span className="text-ink/35">no navigation in source</span>
                  ) : (
                    <span className="tabular-nums">
                      {d.geo.latitude.toFixed(5)}, {d.geo.longitude.toFixed(5)}
                    </span>
                  )}
                  <span className="text-ink/25">·</span>
                  <span>
                    {d.length_m}×{d.width_m} m
                  </span>
                  {!simulatedNav && (
                    <>
                      <span className="text-ink/25">·</span>
                      <span>±{d.geo.horizontal_uncertainty_m.toFixed(2)} m</span>
                    </>
                  )}
                </div>
              </button>
            )
          })
        )}
      </div>
    </BentoCard>
  )
}
