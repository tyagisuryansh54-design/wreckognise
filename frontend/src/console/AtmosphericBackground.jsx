/**
 * Canvas starfield: dots that twinkle on their own cycle and drift toward the
 * pointer.
 *
 * Canvas rather than N absolutely-positioned divs because this is 200+ nodes
 * animating every frame; as DOM elements that is 200 style recalculations per
 * frame and the page janks the moment anything else needs the main thread.
 *
 * Three things keep it honest:
 *  - the loop stops when the tab is hidden, so a backgrounded page is not
 *    burning a core and a laptop battery;
 *  - it stops entirely under prefers-reduced-motion, painting one static frame;
 *  - the pointer target is eased rather than followed, so the field drifts
 *    instead of snapping.
 */

import { useEffect, useRef } from 'react'

const DENSITY = 1 / 9000     // dots per css pixel
const MAX_DOTS = 260
const PARALLAX = 26          // px of travel at full pointer deflection

export default function AtmosphericBackground({ className = '' }) {
  const canvasRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d', { alpha: true })
    if (!ctx) return

    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches

    let width = 0
    let height = 0
    let dots = []
    let raf = 0
    let running = true

    // Pointer, and the eased value that actually drives the parallax.
    const target = { x: 0, y: 0 }
    const eased = { x: 0, y: 0 }

    const rand = (a, b) => a + Math.random() * (b - a)

    function seed() {
      const count = Math.min(MAX_DOTS, Math.round(width * height * DENSITY))
      dots = Array.from({ length: count }, () => ({
        x: Math.random(),
        y: Math.random(),
        r: rand(0.4, 1.5),
        depth: rand(0.25, 1),           // drives both parallax and brightness
        phase: Math.random() * Math.PI * 2,
        speed: rand(0.5, 1.9),
        warm: Math.random() < 0.12,     // a few amber dots break the monotone
      }))
    }

    function resize() {
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      const rect = canvas.getBoundingClientRect()
      width = rect.width
      height = rect.height
      canvas.width = Math.round(width * dpr)
      canvas.height = Math.round(height * dpr)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      seed()
    }

    function draw(t) {
      ctx.clearRect(0, 0, width, height)

      eased.x += (target.x - eased.x) * 0.045
      eased.y += (target.y - eased.y) * 0.045

      for (const d of dots) {
        // Each dot twinkles on its own period, so the field never pulses in
        // unison -- which reads as a strobe rather than as stars.
        const tw = reduced ? 0.7 : 0.5 + 0.5 * Math.sin(t * 0.001 * d.speed + d.phase)
        const alpha = (0.1 + 0.72 * tw) * d.depth

        const px = d.x * width + eased.x * PARALLAX * d.depth
        const py = d.y * height + eased.y * PARALLAX * d.depth

        ctx.beginPath()
        ctx.arc(px, py, d.r * (0.7 + 0.5 * tw), 0, Math.PI * 2)
        ctx.fillStyle = d.warm
          ? `rgba(255, 183, 3, ${alpha * 0.75})`
          : `rgba(150, 230, 255, ${alpha})`
        ctx.fill()

        // Brightest few get a bloom. Cheap, and it sells the depth.
        if (tw > 0.93 && d.depth > 0.7) {
          ctx.beginPath()
          ctx.arc(px, py, d.r * 4.5, 0, Math.PI * 2)
          ctx.fillStyle = `rgba(0, 214, 255, ${0.05 * alpha})`
          ctx.fill()
        }
      }
    }

    function frame(t) {
      if (!running) return
      draw(t)
      raf = requestAnimationFrame(frame)
    }

    function onPointer(e) {
      target.x = (e.clientX / window.innerWidth) * 2 - 1
      target.y = (e.clientY / window.innerHeight) * 2 - 1
    }

    function onVisibility() {
      if (document.hidden) {
        running = false
        cancelAnimationFrame(raf)
      } else if (!reduced) {
        running = true
        raf = requestAnimationFrame(frame)
      }
    }

    resize()
    const ro = new ResizeObserver(resize)
    ro.observe(canvas)
    window.addEventListener('pointermove', onPointer, { passive: true })
    document.addEventListener('visibilitychange', onVisibility)

    if (reduced) {
      draw(0)                       // one static frame, then stop
    } else {
      raf = requestAnimationFrame(frame)
    }

    return () => {
      running = false
      cancelAnimationFrame(raf)
      ro.disconnect()
      window.removeEventListener('pointermove', onPointer)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [])

  return (
    <div className={`pointer-events-none absolute inset-0 overflow-hidden ${className}`}>
      <canvas ref={canvasRef} className="h-full w-full" aria-hidden="true" />
      <div
        className="absolute inset-0"
        style={{
          background:
            'radial-gradient(ellipse 65% 50% at 50% 38%, rgba(0,214,255,0.10), transparent 72%)',
        }}
      />
    </div>
  )
}
