/**
 * Full-bleed animated hero, adapted from the shadcn-style `hero-ascii-one` and
 * restyled into the Wreckognise design system.
 *
 * The source was black-and-white brutalist with mono type. What survives is its
 * structure -- corner brackets, telemetry rails, a dithered margin mark -- which
 * happens to read as survey instrumentation and suits a sonar tool. What changed
 * is every colour and typeface: navy ground (the 30% structure band), cream
 * type, azure and aqua for the 10% accent, nothing outside the documented
 * palette. The pops (coral/sunset/amber) stay reserved for alerts, so none
 * appear here.
 *
 * Stack notes, since the source assumed Next.js + TypeScript:
 *
 * - `.jsx`, not `.tsx` -- this project is JavaScript.
 * - `'use client'` dropped: a Next App Router directive, inert under Vite.
 * - `<style jsx>` dropped: styled-jsx is a Next feature. Under Vite it emits an
 *   UNSCOPED <style> plus a React warning about the unknown `jsx` attribute, so
 *   its two patterns would have leaked into the dashboard. Inline styles now.
 * - The branding-removal block is gone. It hid UnicornStudio's attribution
 *   badge on a 50 ms interval that never stopped while the page lived; that
 *   badge is a condition of their free tier.
 */

import { useEffect } from 'react'

const SCRIPT_SRC =
  'https://cdn.jsdelivr.net/gh/hiunicornstudio/unicornstudio.js@v1.4.33/dist/unicornStudio.umd.js'

/** Margin rule: a fine azure cross-hatch, replacing the source's white dither. */
const DITHER = {
  backgroundImage:
    'repeating-linear-gradient(0deg, transparent 0 1px, #00B4D8 1px 2px),' +
    'repeating-linear-gradient(90deg, transparent 0 1px, #00B4D8 1px 2px)',
  backgroundSize: '3px 3px',
}

/**
 * Mobile fallback for the WebGL canvas: scattered aqua returns on navy, which
 * reads as sonar contacts rather than as the source's starfield.
 */
const CONTACTS = {
  backgroundImage: [
    'radial-gradient(1.5px 1.5px at 20% 30%, #00B4D8, transparent)',
    'radial-gradient(1px 1px at 60% 70%, #0077B6, transparent)',
    'radial-gradient(1px 1px at 50% 50%, #00B4D8, transparent)',
    'radial-gradient(1.5px 1.5px at 80% 18%, #0077B6, transparent)',
    'radial-gradient(1px 1px at 90% 60%, #00B4D8, transparent)',
    'radial-gradient(1px 1px at 33% 80%, #0077B6, transparent)',
    'radial-gradient(1.5px 1.5px at 15% 62%, #00B4D8, transparent)',
    'radial-gradient(1px 1px at 72% 42%, #0077B6, transparent)',
  ].join(','),
  backgroundSize:
    '200% 200%, 180% 180%, 250% 250%, 220% 220%, 190% 190%, 240% 240%, 210% 210%, 230% 230%',
  backgroundPosition: '0% 0%, 40% 40%, 60% 60%, 20% 20%, 80% 80%, 30% 30%, 70% 70%, 50% 50%',
  opacity: 0.55,
}

/**
 * Load the UnicornStudio runtime exactly once per page.
 *
 * Deliberately not undone on unmount: removing the <script> element does not
 * unload the library or reset `window.UnicornStudio`, so a cleanup that looked
 * tidy would only guarantee a double-init on the next mount.
 */
function useUnicornStudio(enabled) {
  useEffect(() => {
    if (!enabled || typeof window === 'undefined') return
    if (window.UnicornStudio) return

    window.UnicornStudio = { isInitialized: false }
    const script = document.createElement('script')
    script.src = SCRIPT_SRC
    script.async = true
    script.onload = () => {
      if (!window.UnicornStudio.isInitialized) {
        window.UnicornStudio.init()
        window.UnicornStudio.isInitialized = true
      }
    }
    document.head.appendChild(script)
  }, [enabled])
}

export default function HeroAsciiOne({
  brand = 'WRECKOGNISE',
  established = 'EST. 2026',
  eyebrow = 'Autonomous Seabed Intelligence',
  title = 'Find every wreck',
  titleAccent = 'on the seabed.',
  body =
    'Raw side-scan sonar in, georeferenced contacts out. OpenCV strips the acoustic ' +
    'speckle, a YOLOv8 detector sweeps the swath, and every bounding box resolves to ' +
    'a WGS-84 position with a stated error budget.',
  primaryCta = 'Explore Live Scan',
  secondaryCta = 'Upload Sonar Data',
  onPrimary,
  onSecondary,
  latitude = '8.6000',
  longitude = '78.4000',
  projectId = 'OMzqyUv6M3kSnv0JeAtC',
  version = 'v1.0.0',
  notation = 'WGS-84 / EPSG:4326',
}) {
  useUnicornStudio(Boolean(projectId))

  return (
    <main className="relative min-h-screen overflow-hidden bg-navy">
      {/* Background animation: desktop only -- a full-screen WebGL canvas. */}
      <div className="absolute inset-0 hidden h-full w-full opacity-70 lg:block">
        <div data-us-project={projectId} style={{ width: '100%', height: '100%', minHeight: '100vh' }} />
      </div>

      {/* Mobile fallback */}
      <div className="absolute inset-0 h-full w-full lg:hidden" style={CONTACTS} />

      {/* Keeps type legible over whatever the canvas renders. */}
      <div className="absolute inset-0 bg-gradient-to-r from-navy via-navy/85 to-navy/35" />

      {/* Header */}
      <div className="absolute left-0 right-0 top-0 z-20 border-b border-cream/12">
        <div className="container mx-auto flex items-center justify-between px-4 py-3 lg:px-8 lg:py-4">
          <div className="flex items-center gap-2 lg:gap-4">
            <span className="font-mono text-xl font-bold tracking-label text-cream lg:text-2xl">
              {brand}
            </span>
            <div className="h-3 w-px bg-cream/25 lg:h-4" />
            <span className="label text-cream/40">{established}</span>
          </div>

          <div className="hidden items-center gap-3 lg:flex">
            <span className="label tabular-nums text-cream/40">LAT {latitude}&deg;N</span>
            <span className="h-1 w-1 rounded-full bg-aqua/60" />
            <span className="label tabular-nums text-cream/40">LON {longitude}&deg;E</span>
          </div>
        </div>
      </div>

      {/* Corner frame accents */}
      <div className="absolute left-0 top-0 z-20 h-8 w-8 border-l-2 border-t-2 border-aqua/40 lg:h-12 lg:w-12" />
      <div className="absolute right-0 top-0 z-20 h-8 w-8 border-r-2 border-t-2 border-aqua/40 lg:h-12 lg:w-12" />
      <div className="absolute left-0 z-20 h-8 w-8 border-b-2 border-l-2 border-aqua/40 lg:h-12 lg:w-12" style={{ bottom: '5vh' }} />
      <div className="absolute right-0 z-20 h-8 w-8 border-b-2 border-r-2 border-aqua/40 lg:h-12 lg:w-12" style={{ bottom: '5vh' }} />

      {/* Content. The source pinned this right against its animation; kept, so
          the canvas stays readable on the opposite side. */}
      <div className="relative z-10 flex min-h-screen items-center justify-end pt-16 lg:pt-0" style={{ marginTop: '5vh' }}>
        <div className="w-full px-6 lg:w-3/5 lg:px-16 lg:pr-[8%]">
          <div className="relative max-w-xl lg:ml-auto">
            <div className="mb-4 flex items-center gap-3">
              <div className="h-px w-8 bg-aqua" />
              <span className="label text-aqua">{eyebrow}</span>
              <div className="h-px flex-1 bg-cream/12" />
            </div>

            <div className="relative">
              <div className="absolute -left-5 bottom-1 top-1 hidden w-1 opacity-50 lg:block" style={DITHER} />
              <h1 className="font-display text-4xl font-bold leading-[1.05] tracking-tight text-cream sm:text-5xl lg:text-6xl">
                {title}
                <span className="block text-aqua">{titleAccent}</span>
              </h1>
            </div>

            {/* Range ticks: the source's dot rail, re-read as a scale bar. */}
            <div className="mt-6 hidden items-end gap-1 lg:flex" aria-hidden="true">
              {Array.from({ length: 40 }).map((_, i) => (
                <div
                  key={i}
                  className={i % 10 === 0 ? 'w-px bg-aqua/70' : 'w-px bg-cream/20'}
                  style={{ height: i % 10 === 0 ? '10px' : '5px' }}
                />
              ))}
            </div>

            <p className="mt-5 font-serif text-base leading-relaxed text-cream/65 lg:text-lg">
              {body}
            </p>

            <div className="mt-7 flex flex-col gap-3 sm:flex-row lg:gap-4">
              <button type="button" onClick={onPrimary} className="btn-primary">
                {primaryCta}
              </button>
              <button type="button" onClick={onSecondary} className="btn-ghost-light">
                {secondaryCta}
              </button>
            </div>

            <div className="mt-8 hidden items-center gap-3 lg:flex">
              <span className="h-1 w-1 rounded-full bg-aqua/60" />
              <div className="h-px flex-1 bg-cream/12" />
              <span className="label text-cream/35">{notation}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Footer telemetry strip */}
      <div className="absolute left-0 right-0 z-20 border-t border-cream/12 bg-navy/55 backdrop-blur-sm" style={{ bottom: '5vh' }}>
        <div className="container mx-auto flex items-center justify-between px-4 py-2 lg:px-8 lg:py-3">
          <div className="flex items-center gap-3 lg:gap-6">
            <span className="label text-cream/40">
              <span className="hidden lg:inline">SYSTEM ACTIVE</span>
              <span className="lg:hidden">SYS ACT</span>
            </span>
            {/* Fixed heights, not Math.random(): a random height per render
                changes on every re-render and flickers. */}
            <div className="hidden items-end gap-1 lg:flex" aria-hidden="true">
              {[6, 11, 4, 14, 8, 12, 5, 9].map((h, i) => (
                <div key={i} className="w-1 bg-aqua/35" style={{ height: `${h}px` }} />
              ))}
            </div>
            <span className="label tabular-nums text-cream/40">{version}</span>
          </div>

          <div className="flex items-center gap-2 lg:gap-4">
            <span className="label hidden text-cream/40 lg:inline">RENDERING</span>
            <div className="flex gap-1" aria-hidden="true">
              <div className="h-1 w-1 animate-pulse rounded-full bg-aqua/80" />
              <div className="h-1 w-1 animate-pulse rounded-full bg-aqua/50" style={{ animationDelay: '0.2s' }} />
              <div className="h-1 w-1 animate-pulse rounded-full bg-aqua/25" style={{ animationDelay: '0.4s' }} />
            </div>
            <span className="label hidden text-cream/40 lg:inline">LIVE SWATH</span>
          </div>
        </div>
      </div>
    </main>
  )
}
