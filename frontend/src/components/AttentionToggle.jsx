/**
 * "Show attention" — an Eigen-CAM heat map over one contact's crop.
 *
 * The point is to let an operator, or a judge, see WHERE the network was
 * looking when it made a call. Section 4.2 of the report records the original
 * CV engine reacting to speckle texture rather than objects; this is the
 * instrument that would have shown that at a glance instead of after an
 * evaluation harness was written.
 *
 * Loaded on demand. The map is a second forward pass plus an SVD per contact,
 * so computing one for every detection during ingestion would slow the
 * pipeline for something most contacts are never asked about. The backend
 * caches by detection id, the browser caches the image, so a second toggle is
 * instant.
 */

import { useState } from 'react'
import { api } from '../utils/api'
import { IconEye } from './Icons'

export default function AttentionToggle({ surveyId, detection, className = '' }) {
  const [shown, setShown] = useState(false)
  const [state, setState] = useState('idle')   // idle | loading | ready | error

  if (!surveyId || !detection) return null
  const url = api.attentionUrl(surveyId, detection.detection_id)

  return (
    <div className={className}>
      <button
        type="button"
        onClick={() => {
          setShown((s) => !s)
          if (!shown && state === 'idle') setState('loading')
        }}
        aria-pressed={shown}
        className={`inline-flex items-center gap-2 border px-2.5 py-1.5 font-mono text-2xs
          tracking-label transition-colors ${
            shown
              ? 'border-azure/60 bg-azure/10 text-azure'
              : 'border-ink/18 text-ink-dim hover:border-azure/50 hover:text-azure'
          }`}
      >
        <IconEye className="h-3 w-3" />
        {shown ? 'hide attention' : 'show attention'}
      </button>

      {shown && (
        <figure className="mt-3">
          <div className="relative overflow-hidden rounded border border-ink/12 bg-cream/60">
            {state === 'loading' && (
              <div className="flex h-28 items-center justify-center">
                <span className="font-mono text-2xs text-ink-dim">computing attention…</span>
              </div>
            )}
            {state === 'error' && (
              <div className="flex h-28 items-center justify-center px-4 text-center">
                <span className="font-mono text-2xs text-ink-dim">
                  attention unavailable for this engine
                </span>
              </div>
            )}
            <img
              src={url}
              alt={`Network attention for ${detection.detection_id}`}
              onLoad={() => setState('ready')}
              onError={() => setState('error')}
              className={`w-full ${state === 'ready' ? 'block' : 'hidden'}`}
              style={{ imageRendering: 'auto' }}
            />
          </div>

          <figcaption className="mt-2 flex items-start gap-2">
            {/* The ramp, so red/blue is not left to guesswork. */}
            <span
              aria-hidden="true"
              className="mt-[3px] h-2 w-12 shrink-0 rounded-sm"
              style={{
                background: 'linear-gradient(90deg,#00308F,#00B4D8,#7CFF4F,#FFB703,#D7263D)',
              }}
            />
            <span className="font-mono text-2xs leading-relaxed text-ink/45">
              red = strongest response, blue = ignored. Eigen-CAM on the last neck layer —
              it shows where the network responded most distinctively, not which class it
              chose, so treat it as “what drew its eye”, not proof of the label.
            </span>
          </figcaption>
        </figure>
      )}
    </div>
  )
}
