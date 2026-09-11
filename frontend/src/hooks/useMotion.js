/**
 * Two small motion helpers, both of which fail visible.
 *
 * That is the whole design constraint here: an animation that hides content
 * until JavaScript says otherwise turns a missing observer, a stalled frame or
 * a reduced-motion preference into a blank page. Both hooks below start in the
 * finished state and only opt into motion when they can see it through.
 */

import { useEffect, useRef, useState } from 'react'

const prefersReducedMotion = () =>
  typeof window !== 'undefined' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches

/**
 * True once the element has been scrolled into view.
 *
 * Starts true when motion is reduced or IntersectionObserver is missing, so
 * the content is simply there rather than waiting for an event that will
 * never arrive.
 */
export function useInView({ rootMargin = '0px 0px -12% 0px' } = {}) {
  const ref = useRef(null)
  const [inView, setInView] = useState(
    () => prefersReducedMotion() || typeof IntersectionObserver === 'undefined',
  )

  useEffect(() => {
    if (inView) return
    const node = ref.current
    if (!node) return

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setInView(true)
          observer.disconnect()   // reveal is one-way; nothing re-hides on scroll back
        }
      },
      { rootMargin, threshold: 0.08 },
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [inView, rootMargin])

  return [ref, inView]
}

/**
 * Count a numeric readout up to its new value.
 *
 * Only plain numbers are animated; anything else (a dash, a percentage, a
 * coordinate) is passed straight through, because a readout that animates
 * sometimes and not others looks broken rather than alive. The count is driven
 * by requestAnimationFrame against elapsed time, not by a fixed step, so it
 * lands on the exact target regardless of frame rate.
 */
export function useCountUp(value, duration = 650) {
  const numeric = typeof value === 'number' && Number.isFinite(value)
  const [shown, setShown] = useState(numeric ? value : null)
  const fromRef = useRef(numeric ? value : 0)

  useEffect(() => {
    if (!numeric) return
    if (prefersReducedMotion()) {
      setShown(value)
      fromRef.current = value
      return
    }

    const from = fromRef.current
    const delta = value - from
    if (delta === 0) return

    let raf = 0
    const start = performance.now()
    const tick = (now) => {
      const t = Math.min(1, (now - start) / duration)
      // Cubic ease-out: quick off the mark, settles rather than stops dead.
      const eased = 1 - (1 - t) ** 3
      setShown(from + delta * eased)
      if (t < 1) raf = requestAnimationFrame(tick)
      else fromRef.current = value
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [value, numeric, duration])

  return numeric ? shown : value
}
