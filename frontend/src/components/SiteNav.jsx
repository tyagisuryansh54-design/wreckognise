/**
 * Fixed header, as the reference template has it: logo left, links right,
 * backdrop blur over the ruled ground, active link in the accent.
 *
 * Active section is tracked with IntersectionObserver rather than on scroll.
 * A scroll handler firing on every frame to measure element positions is the
 * classic way to make a page feel heavy, and the observer reports the same
 * thing off the main thread.
 */

import { useEffect, useRef, useState } from 'react'
import { IconMenu, IconX } from './Icons'

const LINKS = [
  { id: 'ingest', label: 'Ingest' },
  { id: 'detect', label: 'Detect' },
  { id: 'chart', label: 'Chart' },
  { id: 'relief', label: 'Relief' },
  { id: 'register', label: 'Register' },
  { id: 'report', label: 'Report' },
]

export default function SiteNav() {
  const [active, setActive] = useState(null)
  const [open, setOpen] = useState(false)
  const toggleRef = useRef(null)

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
    // Focus returns to the control that opened the drawer. Without it,
    // dismissing with Escape drops focus to <body> and the next Tab restarts
    // at the top of the document.
    const onKey = (e) => {
      if (e.key !== 'Escape') return
      setOpen(false)
      toggleRef.current?.focus({ preventScroll: true })
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open])

  const go = (id) => {
    setOpen(false)
    // preventScroll matters here: a plain focus() would fight the smooth
    // scroll that follows and snap the page back to the header.
    toggleRef.current?.focus({ preventScroll: true })
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <header className="fixed inset-x-0 top-0 z-50 border-b border-shell/70 bg-cream/80 backdrop-blur-md">
      <nav className="mx-auto flex max-w-[1500px] items-center justify-between px-4 py-4 sm:px-6 lg:px-8">
        {/*
          Wordmark in Inter rather than the template's angle-bracketed mono.
          `<name />` is a developer-portfolio signature; on a survey instrument
          it reads as borrowed. Wide-tracked uppercase with a single accent
          mark is the register this product actually occupies.
        */}
        <button
          type="button"
          onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
          className="group flex items-baseline gap-2.5 transition-opacity hover:opacity-80"
        >
          <span className="h-[7px] w-[7px] shrink-0 translate-y-[-1px] bg-azure transition-transform duration-200 group-hover:rotate-45" />
          <span className="text-sm font-semibold uppercase tracking-[0.2em] text-ink">
            Wreckognise
          </span>
        </button>

        <div className="hidden items-center gap-8 md:flex">
          {LINKS.map((l) => (
            <button
              key={l.id}
              type="button"
              onClick={() => go(l.id)}
              aria-current={active === l.id ? 'location' : undefined}
              className={`font-mono text-xs transition-colors ${
                active === l.id ? 'text-azure' : 'text-ink-dim hover:text-ink'
              }`}
            >
              {l.label}
            </button>
          ))}
        </div>

        <button
          ref={toggleRef}
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-label="Menu"
          aria-expanded={open}
          aria-controls="site-nav-mobile"
          /* -m-2 p-2 grows a 16px icon to a 32px target without moving
             anything: the negative margin cancels the padding's effect on
             layout, so header spacing is pixel-identical. */
          className="-m-2 p-2 text-ink-dim transition-colors hover:text-azure md:hidden"
        >
          {open ? <IconX className="h-4 w-4" /> : <IconMenu className="h-4 w-4" />}
        </button>
      </nav>

      {/* Mobile drawer: slides down out of the header rather than covering the
          page, so the reader keeps their place. */}
      {open && (
        <nav
          id="site-nav-mobile"
          aria-label="Sections"
          /* Caps at the viewport and scrolls inside itself. On a short phone
             in landscape the six links otherwise run off the bottom with no
             way to reach the last of them. */
          className="max-h-[calc(100dvh-4rem)] overflow-y-auto scroll-slim border-t border-shell/70 bg-cream/95 backdrop-blur-md md:hidden"
        >
          {LINKS.map((l) => (
            <button
              key={l.id}
              type="button"
              onClick={() => go(l.id)}
              aria-current={active === l.id ? 'location' : undefined}
              className={`block w-full border-b border-shell/60 px-5 py-3.5 text-left font-mono text-xs transition-colors last:border-0 ${
                active === l.id ? 'text-azure' : 'text-ink-dim hover:text-ink'
              }`}
            >
              {l.label}
            </button>
          ))}
        </nav>
      )}
    </header>
  )
}
