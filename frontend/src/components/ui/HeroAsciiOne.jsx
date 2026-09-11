/**
 * Full-bleed animated hero -- the shadcn-style `hero-ascii-one`, kept to the
 * source's own design: black ground, white mono type, corner brackets and
 * telemetry rails.
 *
 * Ported to this project's stack, which the source did not assume:
 *
 * - `.jsx`, not `.tsx` -- this project is JavaScript, with no tsconfig.
 * - `'use client'` dropped: a Next.js App Router directive, inert under Vite.
 * - `<style jsx>` dropped: styled-jsx is a Next feature. Under Vite it emits an
 *   UNSCOPED <style> plus a React warning about the unknown `jsx` attribute, so
 *   `.dither-pattern` and `.stars-bg` would have leaked into the dashboard's
 *   own styles. They are inline background styles here -- same pixels, no leak.
 * - Footer bar heights are drawn once with useMemo instead of calling
 *   Math.random() inline. Inline, they were re-rolled on every render and the
 *   bars visibly flickered; this keeps the ragged look and holds it still.
 * - The branding-removal block is not included. It hid UnicornStudio's
 *   attribution badge on a 50 ms interval that ran for the life of the page;
 *   that badge is a condition of their free tier.
 */

import { useEffect, useMemo } from 'react'

const SCRIPT_SRC =
  'https://cdn.jsdelivr.net/gh/hiunicornstudio/unicornstudio.js@v1.4.33/dist/unicornStudio.umd.js'

const DITHER = {
  backgroundImage:
    'repeating-linear-gradient(0deg, transparent 0px, transparent 1px, white 1px, white 2px),' +
    'repeating-linear-gradient(90deg, transparent 0px, transparent 1px, white 1px, white 2px)',
  backgroundSize: '3px 3px',
}

const STARS = {
  backgroundImage: [
    'radial-gradient(1px 1px at 20% 30%, white, transparent)',
    'radial-gradient(1px 1px at 60% 70%, white, transparent)',
    'radial-gradient(1px 1px at 50% 50%, white, transparent)',
    'radial-gradient(1px 1px at 80% 10%, white, transparent)',
    'radial-gradient(1px 1px at 90% 60%, white, transparent)',
    'radial-gradient(1px 1px at 33% 80%, white, transparent)',
    'radial-gradient(1px 1px at 15% 60%, white, transparent)',
    'radial-gradient(1px 1px at 70% 40%, white, transparent)',
  ].join(','),
  backgroundSize:
    '200% 200%, 180% 180%, 250% 250%, 220% 220%, 190% 190%, 240% 240%, 210% 210%, 230% 230%',
  backgroundPosition: '0% 0%, 40% 40%, 60% 60%, 20% 20%, 80% 80%, 30% 30%, 70% 70%, 50% 50%',
  opacity: 0.3,
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
  brand = 'UIMIX',
  established = 'EST. 2025',
  title = 'ENDLESS PURSUIT',
  body =
    'Like Sisyphus, we push forward — not despite the struggle, but because of it. ' +
    'Every iteration, every pixel, every line of code is our boulder.',
  primaryCta = 'BEGIN THE CLIMB',
  secondaryCta = 'EMBRACE THE JOURNEY',
  onPrimary,
  onSecondary,
  latitude = '37.7749',
  longitude = '122.4194',
  projectId = 'OMzqyUv6M3kSnv0JeAtC',
  version = 'V1.0.0',
  notation = 'SISYPHUS.PROTOCOL',
}) {
  useUnicornStudio(Boolean(projectId))

  // Drawn once per mount, not per render -- see the header note.
  const bars = useMemo(
    () => Array.from({ length: 8 }, () => Math.random() * 12 + 4),
    [],
  )

  return (
    <main className="relative min-h-screen overflow-hidden bg-black">
      {/* Background animation */}
      <div className="absolute inset-0 hidden h-full w-full lg:block">
        <div
          data-us-project={projectId}
          style={{ width: '100%', height: '100%', minHeight: '100vh' }}
        />
      </div>

      {/* Mobile stars background */}
      <div className="absolute inset-0 h-full w-full lg:hidden" style={STARS} />

      {/* Top header */}
      <div className="absolute left-0 right-0 top-0 z-20 border-b border-white/20">
        <div className="container mx-auto flex items-center justify-between px-4 py-3 lg:px-8 lg:py-4">
          <div className="flex items-center gap-2 lg:gap-4">
            <div className="-skew-x-12 transform font-mono text-xl font-bold italic tracking-widest text-white lg:text-2xl">
              {brand}
            </div>
            <div className="h-3 w-px bg-white/40 lg:h-4" />
            <span className="font-mono text-[8px] text-white/60 lg:text-[10px]">
              {established}
            </span>
          </div>

          <div className="hidden items-center gap-3 font-mono text-[10px] text-white/60 lg:flex">
            <span>LAT: {latitude}&deg;</span>
            <div className="h-1 w-1 rounded-full bg-white/40" />
            <span>LONG: {longitude}&deg;</span>
          </div>
        </div>
      </div>

      {/* Corner frame accents */}
      <div className="absolute left-0 top-0 z-20 h-8 w-8 border-l-2 border-t-2 border-white/30 lg:h-12 lg:w-12" />
      <div className="absolute right-0 top-0 z-20 h-8 w-8 border-r-2 border-t-2 border-white/30 lg:h-12 lg:w-12" />
      <div
        className="absolute left-0 z-20 h-8 w-8 border-b-2 border-l-2 border-white/30 lg:h-12 lg:w-12"
        style={{ bottom: '5vh' }}
      />
      <div
        className="absolute right-0 z-20 h-8 w-8 border-b-2 border-r-2 border-white/30 lg:h-12 lg:w-12"
        style={{ bottom: '5vh' }}
      />

      {/* CTA content */}
      <div
        className="relative z-10 flex min-h-screen items-center justify-end pt-16 lg:pt-0"
        style={{ marginTop: '5vh' }}
      >
        <div className="w-full px-6 lg:w-1/2 lg:px-16 lg:pr-[10%]">
          <div className="relative max-w-lg lg:ml-auto">
            {/* Top decorative line */}
            <div className="mb-3 flex items-center gap-2 opacity-60">
              <div className="h-px w-8 bg-white" />
              <span className="font-mono text-[10px] tracking-wider text-white">&#8734;</span>
              <div className="h-px flex-1 bg-white" />
            </div>

            {/* Title with dithered accent */}
            <div className="relative">
              <div
                className="absolute -right-3 bottom-0 top-0 hidden w-1 opacity-40 lg:block"
                style={DITHER}
              />
              <h1
                className="mb-3 whitespace-nowrap font-mono text-2xl font-bold leading-tight tracking-wider text-white lg:-ml-[5%] lg:mb-4 lg:text-5xl"
                style={{ letterSpacing: '0.1em' }}
              >
                {title}
              </h1>
            </div>

            {/* Decorative dots pattern - desktop only */}
            <div className="mb-3 hidden gap-1 opacity-40 lg:flex">
              {Array.from({ length: 40 }).map((_, i) => (
                <div key={i} className="h-0.5 w-0.5 rounded-full bg-white" />
              ))}
            </div>

            {/* Description */}
            <div className="relative">
              <p className="mb-5 font-mono text-xs leading-relaxed text-gray-300 opacity-80 lg:mb-6 lg:text-base">
                {body}
              </p>

              {/* Technical corner accent - desktop only */}
              <div
                className="absolute -left-4 top-1/2 hidden h-3 w-3 border border-white opacity-30 lg:block"
                style={{ transform: 'translateY(-50%)' }}
              >
                <div
                  className="absolute left-1/2 top-1/2 h-1 w-1 bg-white"
                  style={{ transform: 'translate(-50%, -50%)' }}
                />
              </div>
            </div>

            {/* Buttons with technical accents */}
            <div className="flex flex-col gap-3 lg:flex-row lg:gap-4">
              <button
                type="button"
                onClick={onPrimary}
                className="group relative border border-white bg-transparent px-5 py-2 font-mono text-xs text-white transition-all duration-200 hover:bg-white hover:text-black lg:px-6 lg:py-2.5 lg:text-sm"
              >
                <span className="absolute -left-1 -top-1 hidden h-2 w-2 border-l border-t border-white opacity-0 transition-opacity group-hover:opacity-100 lg:block" />
                <span className="absolute -bottom-1 -right-1 hidden h-2 w-2 border-b border-r border-white opacity-0 transition-opacity group-hover:opacity-100 lg:block" />
                {primaryCta}
              </button>

              <button
                type="button"
                onClick={onSecondary}
                className="relative border border-white bg-transparent px-5 py-2 font-mono text-xs text-white transition-all duration-200 hover:bg-white hover:text-black lg:px-6 lg:py-2.5 lg:text-sm"
                style={{ borderWidth: '1px' }}
              >
                {secondaryCta}
              </button>
            </div>

            {/* Bottom technical notation - desktop only */}
            <div className="mt-6 hidden items-center gap-2 opacity-40 lg:flex">
              <span className="font-mono text-[9px] text-white">&#8734;</span>
              <div className="h-px flex-1 bg-white" />
              <span className="font-mono text-[9px] text-white">{notation}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Bottom footer */}
      <div
        className="absolute left-0 right-0 z-20 border-t border-white/20 bg-black/40 backdrop-blur-sm"
        style={{ bottom: '5vh' }}
      >
        <div className="container mx-auto flex items-center justify-between px-4 py-2 lg:px-8 lg:py-3">
          <div className="flex items-center gap-3 font-mono text-[8px] text-white/50 lg:gap-6 lg:text-[9px]">
            <span className="hidden lg:inline">SYSTEM.ACTIVE</span>
            <span className="lg:hidden">SYS.ACT</span>
            <div className="hidden gap-1 lg:flex">
              {bars.map((h, i) => (
                <div key={i} className="w-1 bg-white/30" style={{ height: `${h}px` }} />
              ))}
            </div>
            <span>{version}</span>
          </div>

          <div className="flex items-center gap-2 font-mono text-[8px] text-white/50 lg:gap-4 lg:text-[9px]">
            <span className="hidden lg:inline">&#9680; RENDERING</span>
            <div className="flex gap-1">
              <div className="h-1 w-1 animate-pulse rounded-full bg-white/60" />
              <div
                className="h-1 w-1 animate-pulse rounded-full bg-white/40"
                style={{ animationDelay: '0.2s' }}
              />
              <div
                className="h-1 w-1 animate-pulse rounded-full bg-white/20"
                style={{ animationDelay: '0.4s' }}
              />
            </div>
            <span className="hidden lg:inline">FRAME: &#8734;</span>
          </div>
        </div>
      </div>
    </main>
  )
}
