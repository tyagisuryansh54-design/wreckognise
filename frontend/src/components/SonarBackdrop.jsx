/**
 * Sonar ripple behind the page: concentric rings expanding out of a fixed
 * origin, drifting against the scroll.
 *
 * Carried over from the original design's range arcs, but as a slow emission
 * rather than a static decoration. Deliberately faint -- at this size a ring
 * bright enough to notice on its own is bright enough to compete with the
 * contact markers on the chart, which are the one thing on the page that
 * should catch the eye.
 *
 * Four rings, transform and opacity only, so the compositor handles them and
 * nothing triggers layout. The parallax reads scrollY inside a rAF callback
 * instead of writing styles from the scroll event, which would force a style
 * recalculation on every wheel tick.
 */

import { useEffect, useRef } from 'react'

const RINGS = [0, 2.6, 5.2, 7.8]   // seconds of delay; period is 10.4s
const PARALLAX = -0.045            // px of drift per px scrolled

export default function SonarBackdrop() {
  const layerRef = useRef(null)

  useEffect(() => {
    const layer = layerRef.current
    if (!layer) return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return

    let raf = 0
    let pending = false

    const apply = () => {
      pending = false
      layer.style.transform = `translate3d(0, ${window.scrollY * PARALLAX}px, 0)`
    }
    const onScroll = () => {
      if (pending) return
      pending = true
      raf = requestAnimationFrame(apply)
    }

    apply()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => {
      window.removeEventListener('scroll', onScroll)
      cancelAnimationFrame(raf)
    }
  }, [])

  return (
    <div
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 -z-10 overflow-hidden"
    >
      <div ref={layerRef} className="absolute inset-0 will-change-transform">
        {/* Origin sits off-centre and high, so the rings sweep across the
            reading column rather than radiating from behind the text. */}
        <div className="absolute left-[68%] top-[22%] -translate-x-1/2 -translate-y-1/2">
          {RINGS.map((delay) => (
            <span
              key={delay}
              className="sonar-ring absolute left-1/2 top-1/2 block h-[44vmin] w-[44vmin] -translate-x-1/2 -translate-y-1/2 rounded-full border border-azure/45"
              style={{ animationDelay: `${delay}s` }}
            />
          ))}
          <span className="absolute left-1/2 top-1/2 block h-1.5 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-azure/40" />
        </div>
      </div>
    </div>
  )
}
