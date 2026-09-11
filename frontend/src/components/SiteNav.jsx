/**
 * Fixed header, as the reference template has it: logo left, links right,
 * backdrop blur over the ruled ground, active link in the accent.
 *
 * Active section is tracked with IntersectionObserver rather than on scroll.
 * A scroll handler firing on every frame to measure element positions is the
 * classic way to make a page feel heavy, and the observer reports the same
 * thing off the main thread.
 */

import { useEffect, useState } from 'react'
import { IconMenu, IconX } from './Icons'

const LINKS = [
  { id: 'ingest', label: 'Ingest' },
  { id: 'detect', label: 'Detect' },
  { id: 'chart', label: 'Chart' },
  { id: 'register', label: 'Register' },
  { id: 'report', label: 'Report' },
]

export default function SiteNav() {
  const [active, setActive] = useState(null)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    const sections = LINKS.map((l) => document.getElementById(l.id)).filter(Boolean)
    if (!sections.length) return

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0]
        if (visible) setActive(visible.target.id)
      },
      // Bias the band toward the upper half so a section counts as "current"
      // once its heading is in view, not once it fills the screen.
      { rootMargin: '-20% 0px -60% 0px', threshold: [0.05, 0.25, 0.5] },
    )
    sections.forEach((s) => observer.observe(s))
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (!open) return
    const onKey = (e) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open])

  const go = (id) => {
    setOpen(false)
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <header className="fixed inset-x-0 top-0 z-50 border-b border-shell/70 bg-cream/80 backdrop-blur-md">
      <nav className="mx-auto flex max-w-[1500px] items-center justify-between px-4 py-4 sm:px-6 lg:px-8">
        <button
          type="button"
          onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
          className="font-mono text-sm font-bold tracking-tight text-azure transition-opacity hover:opacity-75"
        >
          &lt;wreckognise /&gt;
        </button>

        <div className="hidden items-center gap-8 md:flex">
          {LINKS.map((l) => (
            <button
              key={l.id}
              type="button"
              onClick={() => go(l.id)}
              className={`font-mono text-xs transition-colors ${
                active === l.id ? 'text-azure' : 'text-ink-dim hover:text-ink'
              }`}
            >
              {l.label}
            </button>
          ))}
        </div>

        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-label={open ? 'Close menu' : 'Open menu'}
          aria-expanded={open}
          className="text-ink-dim transition-colors hover:text-azure md:hidden"
        >
          {open ? <IconX className="h-4 w-4" /> : <IconMenu className="h-4 w-4" />}
        </button>
      </nav>

      {/* Mobile drawer: slides down out of the header rather than covering the
          page, so the reader keeps their place. */}
      {open && (
        <div className="border-t border-shell/70 bg-cream/95 backdrop-blur-md md:hidden">
          {LINKS.map((l) => (
            <button
              key={l.id}
              type="button"
              onClick={() => go(l.id)}
              className={`block w-full border-b border-shell/60 px-5 py-3.5 text-left font-mono text-xs transition-colors last:border-0 ${
                active === l.id ? 'text-azure' : 'text-ink-dim hover:text-ink'
              }`}
            >
              {l.label}
            </button>
          ))}
        </div>
      )}
    </header>
  )
}
