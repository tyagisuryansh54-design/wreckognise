/**
 * The AURORA-class neural core: ASCII hull with data pulses running through it.
 *
 * Scaling is by font-size alone -- `clamp()` in vw units, no transform -- so
 * the glyphs stay crisp at every size instead of being resampled. Below `sm` a
 * 46-column variant swaps in, because the full hull needs ~78 columns before
 * the lattice stops being legible.
 *
 * The pulse is a gradient bar swept across the art by CSS, masked to the text.
 * Re-rendering the array with a moving highlight would mean a React commit per
 * frame for a purely decorative effect.
 */

import { useEffect, useState } from 'react'
import { CORE, CORE_COMPACT, block } from './shipArt'

const FULL = block(CORE)
const COMPACT = block(CORE_COMPACT)

/** Node labels that light in sequence, so the lattice reads as computing. */
const NODES = ['INGEST', 'DENOISE', 'DETECT', 'GEOREF', 'REPORT']

export default function AsciiAiShip({ className = '' }) {
  const [active, setActive] = useState(0)

  useEffect(() => {
    const id = setInterval(() => setActive((n) => (n + 1) % NODES.length), 1400)
    return () => clearInterval(id)
  }, [])

  return (
    <div className={`relative w-full ${className}`}>
      {/* Bloom behind the hull */}
      <div
        className="pointer-events-none absolute inset-0 blur-3xl"
        style={{
          background:
            'radial-gradient(ellipse 42% 58% at 50% 50%, rgba(0,214,255,0.28), transparent 70%)',
        }}
      />

      <div className="relative overflow-hidden">
        {/* Data pulse: a bright band travelling across the hull. */}
        {/* The band is masked top and bottom as well as left and right --
            without the vertical fade its square ends cut a visible rectangle
            out of the page background either side of the hull. */}
        <div
          aria-hidden="true"
          className="con-sweep pointer-events-none absolute inset-y-0 left-0 w-1/3 mix-blend-screen"
          style={{
            background:
              'linear-gradient(90deg, transparent, rgba(0,214,255,0.16), transparent)',
            maskImage: 'linear-gradient(180deg, transparent, #000 22%, #000 78%, transparent)',
            WebkitMaskImage:
              'linear-gradient(180deg, transparent, #000 22%, #000 78%, transparent)',
          }}
        />

        <pre
          aria-hidden="true"
          className="mono con-flicker relative hidden select-none whitespace-pre text-center sm:block"
          style={{
            color: 'rgba(0,214,255,0.88)',
            fontSize: 'clamp(4.5px, 1.06vw, 12px)',
            lineHeight: 1.18,
            textShadow: '0 0 12px rgba(0,214,255,0.45)',
          }}
        >
          {FULL}
        </pre>

        <pre
          aria-hidden="true"
          className="mono relative select-none whitespace-pre text-center sm:hidden"
          style={{
            color: 'rgba(0,214,255,0.88)',
            fontSize: 'clamp(5px, 2.25vw, 10px)',
            lineHeight: 1.2,
            textShadow: '0 0 10px rgba(0,214,255,0.45)',
          }}
        >
          {COMPACT}
        </pre>
      </div>

      {/* Stage readout under the hull -- the lattice nodes, named. */}
      <div className="mono mt-5 flex flex-wrap items-center justify-center gap-x-3 gap-y-2 text-[9px] tracking-[0.22em]">
        {NODES.map((node, i) => (
          <span key={node} className="flex items-center gap-2">
            <span
              className="inline-block h-1.5 w-1.5 rounded-full transition-colors duration-300"
              style={{
                background: i === active ? 'var(--cyan)' : 'rgba(107,127,147,0.45)',
                boxShadow: i === active ? '0 0 8px var(--cyan)' : 'none',
              }}
            />
            <span
              className="transition-colors duration-300"
              style={{ color: i === active ? 'var(--ink)' : 'var(--ink-dim)' }}
            >
              {node}
            </span>
            {i < NODES.length - 1 && (
              <span style={{ color: 'rgba(107,127,147,0.4)' }}>&rarr;</span>
            )}
          </span>
        ))}
      </div>
    </div>
  )
}
