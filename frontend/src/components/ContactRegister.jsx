import { useMemo, useState } from 'react'
import { Badge, BentoCard, CardHeader, EmptyState, Meter } from './Primitives'
import { IconAlert, IconTarget } from './Icons'
import { REVIEW_LABELS, classLabel, severityStyle } from '../utils/format'

const FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'critical', label: 'Critical' },
  { id: 'flagged', label: 'Flagged' },
  { id: 'pending', label: 'Pending' },
]

/**
 * Bento box 4a -- the anomaly register.
 *
 * This is the operator's working list: sorted by severity then confidence, so
 * the thing most likely to sink a ship is always the first row on screen.
 */
export default function ContactRegister({ detections, selected, onSelect, summary }) {
  const [filter, setFilter] = useState('all')

  const rows = useMemo(() => {
    const order = { critical: 0, high: 1, medium: 2, low: 3 }
    return detections
      .filter((d) => {
        if (filter === 'all') return true
        if (filter === 'critical') return d.severity === 'critical'
        if (filter === 'flagged') return d.review_status === 'flagged'
        if (filter === 'pending') return d.review_status === 'pending'
        return true
      })
      .sort(
        (a, b) => order[a.severity] - order[b.severity] || b.confidence - a.confidence,
      )
  }, [detections, filter])

  const criticalCount = detections.filter((d) => d.severity === 'critical').length

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
          criticalCount > 0 ? (
            <Badge className="shrink-0 bg-coral/15 text-coral ring-1 ring-coral/30" pulse>
              {criticalCount} Critical
            </Badge>
          ) : (
            <span className="hidden shrink-0 rounded-full bg-navy/5 p-2.5 text-azure sm:block">
              <IconTarget className="h-5 w-5" />
            </span>
          )
        }
      />

      <div className="mt-4 flex gap-1.5 rounded-full bg-sand p-1">
        {FILTERS.map((option) => {
          const count =
            option.id === 'all'
              ? detections.length
              : option.id === 'critical'
                ? criticalCount
                : detections.filter((d) => d.review_status === option.id).length
          return (
            <button
              key={option.id}
              type="button"
              onClick={() => setFilter(option.id)}
              aria-pressed={filter === option.id}
              className={`flex-1 rounded-full px-2.5 py-1.5 font-mono text-2xs font-semibold uppercase tracking-wide transition-colors ${
                filter === option.id ? 'bg-navy text-cream' : 'text-navy/50 hover:text-navy'
              }`}
            >
              {option.label}
              <span className={filter === option.id ? 'ml-1.5 text-aqua' : 'ml-1.5 text-navy/35'}>
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
                    ? `border-transparent bg-navy text-cream ring-2 ${style.ring}`
                    : 'border-navy/10 bg-white/70 hover:border-navy/25 hover:bg-white'
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className={`h-2 w-2 shrink-0 rounded-full ${style.dot}`} />
                      <p
                        className={`truncate font-display text-sm font-semibold ${
                          active ? 'text-cream' : 'text-navy'
                        }`}
                      >
                        {classLabel(d.label)}
                      </p>
                    </div>
                    <p
                      className={`mt-0.5 font-mono text-2xs ${
                        active ? 'text-cream/40' : 'text-navy/40'
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
                    <p
                      className={`font-mono text-2xs ${active ? 'text-cream/40' : 'text-navy/40'}`}
                    >
                      {REVIEW_LABELS[d.review_status]}
                    </p>
                  </div>
                </div>

                <div className="mt-2.5">
                  <Meter
                    value={d.confidence}
                    colour={active ? 'bg-aqua' : 'bg-azure'}
                    track={active ? 'bg-cream/12' : 'bg-navy/8'}
                    height="h-1"
                  />
                </div>

                <div
                  className={`mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-2xs ${
                    active ? 'text-cream/55' : 'text-navy/50'
                  }`}
                >
                  <span className="tabular-nums">
                    {d.geo.latitude.toFixed(5)}, {d.geo.longitude.toFixed(5)}
                  </span>
                  <span className={active ? 'text-cream/25' : 'text-navy/25'}>·</span>
                  <span>
                    {d.length_m}×{d.width_m} m
                  </span>
                  <span className={active ? 'text-cream/25' : 'text-navy/25'}>·</span>
                  <span>±{d.geo.horizontal_uncertainty_m.toFixed(2)} m</span>
                </div>
              </button>
            )
          })
        )}
      </div>
    </BentoCard>
  )
}
