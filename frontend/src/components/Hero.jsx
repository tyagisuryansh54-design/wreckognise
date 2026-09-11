/**
 * Hero, composed like the reference template rather than like a dashboard card.
 *
 * The previous hero was a filled panel carrying a brand block, a status pill,
 * three CTAs and a trust rail -- a lot of furniture. The reference earns its
 * weight from restraint: a code-comment eyebrow, one very large two-tone
 * headline, a short paragraph, one solid accent button. Everything else that
 * used to live here moved out to the status line under the fold, where it can
 * be read rather than decoded.
 */

import { useEffect, useState } from 'react'
import { IconArrowRight, IconUpload } from './Icons'

const TITLE = 'Find every wreck on the seabed.'

export default function Hero({ onExplore, onUpload, busy, health }) {
  const engineLive = Boolean(health)

  // Typing cursor on the headline, as the reference has. The text itself is
  // not typed out: re-rendering a 30-character string one letter at a time is
  // a layout pass per frame, and a headline that assembles itself delays the
  // one thing a visitor came to read.
  const [caret, setCaret] = useState(true)
  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const id = setInterval(() => setCaret((c) => !c), 560)
    return () => clearInterval(id)
  }, [])

  return (
    <section className="relative flex min-h-[82vh] flex-col justify-center py-20">
      <p className="comment animate-fade-up">Autonomous Seabed Intelligence</p>

      <h1
        className="mt-6 max-w-4xl text-4xl font-bold leading-[1.08] tracking-tight text-ink animate-fade-up sm:text-5xl lg:text-6xl"
        style={{ animationDelay: '60ms' }}
      >
        {TITLE}
        <span className="mt-1 block text-ink-dim">
          Fix it to a coordinate.
          <span
            className={`ml-1 inline-block w-[0.5ch] text-azure ${caret ? 'opacity-100' : 'opacity-0'}`}
            aria-hidden="true"
          >
            _
          </span>
        </span>
      </h1>

      <p
        className="mt-8 max-w-2xl text-base leading-relaxed text-ink-dim animate-fade-up"
        style={{ animationDelay: '120ms' }}
      >
        Wreckognise ingests raw side-scan sonar, strips acoustic speckle with OpenCV, and
        runs a YOLOv8 detector across the swath — then converts every bounding box into a
        WGS-84 position accurate to under a metre. What took a hydrographer a full shift
        now takes a single pass.
      </p>

      <div
        className="mt-10 flex flex-wrap items-center gap-3 animate-fade-up"
        style={{ animationDelay: '180ms' }}
      >
        <button
          type="button"
          onClick={onExplore}
          disabled={busy === 'ingest'}
          className="btn-primary group"
        >
          {busy === 'ingest' ? 'Scanning…' : 'Explore Live Scan'}
          <IconArrowRight className="h-3.5 w-3.5 transition-transform duration-200 group-hover:translate-x-0.5" />
        </button>

        <button type="button" onClick={onUpload} className="btn-ghost">
          <IconUpload className="h-3.5 w-3.5" />
          Upload Sonar Data
        </button>
      </div>

      {/* Status line: the old status pill and trust badges, reduced to one row
          of machine-readable facts. */}
      <div
        className="mt-14 flex flex-wrap items-center gap-x-8 gap-y-2 border-t border-shell pt-6 font-mono text-2xs text-ink-faint animate-fade-up"
        style={{ animationDelay: '240ms' }}
      >
        <span className="flex items-center gap-2">
          <span
            className={`h-1.5 w-1.5 rounded-full ${engineLive ? 'animate-pulse bg-azure' : 'bg-coral'}`}
          />
          <span className={engineLive ? 'text-azure' : 'text-coral'}>
            {engineLive ? 'engines online' : 'engines offline'}
          </span>
        </span>
        <span>sub-metre gps · rtk-corrected wgs-84</span>
        <span>per-ping telemetry binding</span>
        <span>mAP@0.5 0.839</span>
      </div>
    </section>
  )
}
