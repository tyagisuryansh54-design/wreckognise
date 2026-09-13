/**
 * Ordnance alert. Sits above the pipeline, not inside the review queue.
 *
 * A UXO contact on a survey line is a diver-safety matter before it is a data
 * point, so it must not be scrollable-past in an ordinary list of contacts.
 * Three properties follow from that:
 *
 *  - it renders at the top of the page, not in the register;
 *  - it is visually unlike every other state on the site -- the only coral
 *    surface, the only pulsing element, the only thing that outranks the
 *    accent colour;
 *  - it cannot be closed. There is no dismiss control. It clears only when
 *    every hazard has been acknowledged, and acknowledgement is a separate
 *    endpoint from review so a hazard cannot leave the queue as a side effect
 *    of routine triage.
 *
 * The acknowledgement records who and when, because "somebody probably saw it"
 * is not a safety record.
 */

import { useState } from 'react'
import { IconAlert } from './Icons'
import { classLabel } from '../utils/format'

export default function HazardAlert({ detections = [], onAcknowledge, onSelect }) {
  const [busyId, setBusyId] = useState(null)

  const hazards = detections.filter((d) => d.priority === 'hazard')
  const pending = hazards.filter((d) => !d.acknowledged_by)
  if (hazards.length === 0) return null

  const cleared = pending.length === 0

  return (
    <section
      role="alert"
      aria-live="assertive"
      className={`con-rise mt-4 border ${
        cleared ? 'border-ink/18 bg-sand' : 'border-coral bg-coral/10'
      }`}
    >
      <header className="flex items-start gap-3 px-5 py-4">
        <span className="relative mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center">
          {!cleared && (
            <span className="absolute inline-flex h-4 w-4 animate-ping rounded-full bg-coral/60" />
          )}
          <IconAlert className={`relative h-4 w-4 ${cleared ? 'text-ink-dim' : 'text-coral'}`} />
        </span>

        <div className="min-w-0 flex-1">
          <p
            className={`font-mono text-2xs font-bold uppercase tracking-label ${
              cleared ? 'text-ink-dim' : 'text-coral'
            }`}
          >
            {cleared
              ? `Ordnance acknowledged · ${hazards.length} contact${hazards.length > 1 ? 's' : ''}`
              : `Possible ordnance · ${pending.length} unacknowledged`}
          </p>
          <p className="mt-1 max-w-2xl text-sm leading-relaxed text-ink/70">
            {cleared
              ? 'Every hazard contact on this line has been acknowledged. Positions are in the register and the exported brief.'
              : 'The detector has classified one or more contacts as unexploded ordnance. ' +
                'Do not task divers or an ROV against this line until each has been reviewed. ' +
                'This notice cannot be dismissed — it clears when every contact is acknowledged.'}
          </p>

          <ul className="mt-3 space-y-2">
            {hazards.map((d) => (
              <li
                key={d.detection_id}
                className="flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-ink/10 pt-2 first:border-0 first:pt-0"
              >
                <button
                  type="button"
                  onClick={() => onSelect?.(d.detection_id)}
                  className="font-mono text-2xs text-ink underline-offset-2 hover:underline"
                >
                  {d.detection_id}
                </button>
                <span className="font-mono text-2xs text-ink-dim">
                  {classLabel(d.label)} · {(d.confidence * 100).toFixed(0)}% ·{' '}
                  {d.length_m}×{d.width_m} m
                </span>

                {d.acknowledged_by ? (
                  <span className="font-mono text-2xs text-ink-faint">
                    seen by {d.acknowledged_by} · {d.acknowledged_at?.slice(0, 16).replace('T', ' ')}
                  </span>
                ) : (
                  <button
                    type="button"
                    disabled={busyId === d.detection_id}
                    onClick={async () => {
                      setBusyId(d.detection_id)
                      await onAcknowledge?.(d.detection_id)
                      setBusyId(null)
                    }}
                    className="btn !border-coral !px-3 !py-1.5 !text-coral hover:!bg-coral hover:!text-cream disabled:opacity-50"
                  >
                    {busyId === d.detection_id ? 'recording…' : 'I have seen this'}
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      </header>
    </section>
  )
}
