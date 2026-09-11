/**
 * Dark retro-futuristic hero with an ASCII neural-core vessel.
 *
 * Two things here are load-bearing and easy to get wrong:
 *
 * 1. FONT. This project's Tailwind `font-mono` is Space Grotesk -- a
 *    PROPORTIONAL sans. ASCII art set in it has a different width on every
 *    line and the drawing collapses. The art uses its own true-monospace
 *    stack (MONO below) and must keep using it.
 *
 * 2. GLYPH COVERAGE. The character set is restricted to ASCII, box drawing,
 *    and the U+2580 block range, all of which the standard monospace faces
 *    carry. Rarer glyphs (arrows, geometric shapes, the U+2571 diagonals)
 *    render as tofu boxes in some faces -- which destroys the alignment the
 *    art exists for. `\` and `/` are used for diagonals instead.
 *
 * No third-party animation runtime: the graphic is text, so it costs nothing
 * to load, scales by font-size alone, and carries no vendor watermark.
 */

import { useEffect, useState } from 'react'
import { Activity, ArrowRight, Radar, Terminal, Waves } from 'lucide-react'

/** True monospace. Deliberately NOT Tailwind's `font-mono` -- see the note above. */
const MONO =
  'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace'

/**
 * AURORA-class survey vessel: a lens hull carrying a neural lattice core,
 * sensor mast above, thrust rake below.
 */
const CORE = [
  '                                      ·                                       ',
  '                                      |                                       ',
  '                                     /|\\                                      ',
  '                                    / | \\                                     ',
  '                    ▒▒▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▒▒                   ',
  '                ░▒▓█   ·                               ·   █▓▒░               ',
  '             ░▒▓█   ·   ░                             ░   ·   █▓▒░            ',
  '           ░▒▓█   ·   ░                                 ░   ·   █▓▒░          ',
  '         ░▒▓█   ·   ░                                     ░   ·   █▓▒░        ',
  '        ░▒▓█   ·   ░                                       ░   ·   █▓▒░       ',
  '       ░▒▓█   ·   ░                                         ░   ·   █▓▒░      ',
  '      ░▒▓█   ·   ░        ┌─────────────────────────┐        ░   ·   █▓▒░     ',
  '     ░▒▓█   ·   ░         │  o───o───o───o───o───o  │         ░   ·   █▓▒░    ',
  '   ══░▒▓█   ·   ░         │  │\\ /│\\ /│\\ /│\\ /│\\ /│  │         ░   ·   █▓▒░══  ',
  '  ═══░▒▓█   ·   ░         │  o───█───█───█───█───o  │         ░   ·   █▓▒░═══ ',
  '   ══░▒▓█   ·   ░         │  │/ \\│/ \\│/ \\│/ \\│/ \\│  │         ░   ·   █▓▒░══  ',
  '     ░▒▓█   ·   ░         │  o───o───o───o───o───o  │         ░   ·   █▓▒░    ',
  '      ░▒▓█   ·   ░        └─────────────────────────┘        ░   ·   █▓▒░     ',
  '       ░▒▓█   ·   ░                                         ░   ·   █▓▒░      ',
  '        ░▒▓█   ·   ░                                       ░   ·   █▓▒░       ',
  '         ░▒▓█   ·   ░                                     ░   ·   █▓▒░        ',
  '           ░▒▓█   ·   ░                                 ░   ·   █▓▒░          ',
  '             ░▒▓█   ·   ░                             ░   ·   █▓▒░            ',
  '                ░▒▓█   ·                               ·   █▓▒░               ',
  '                    ▒▒▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▒▒                   ',
  '                                    \\ | /                                     ',
  '                                     \\|/                                      ',
  '                                      |                                       ',
  '                                      ·                                       ',
]

/** Small-screen variant: the full hull needs ~78 columns to stay legible. */
const CORE_COMPACT = [
  '                      ·                       ',
  '                      |                       ',
  '                     /|\\                      ',
  '                    / | \\                     ',
  '            ▒▒▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▒▒           ',
  '        ░▒▓█                       █▓▒░       ',
  '      ░▒▓█                           █▓▒░     ',
  '     ░▒▓█      ┌───────────────┐      █▓▒░    ',
  '    ░▒▓█       │   o───o───o   │       █▓▒░   ',
  ' ══░▒▓█  ·     │   │\\ /│\\ /│   │     ·  █▓▒░══',
  '═══░▒▓█  ·     │   o───█───o   │     ·  █▓▒░══',
  ' ══░▒▓█  ·     │   │/ \\│/ \\│   │     ·  █▓▒░══',
  '    ░▒▓█       │   o───o───o   │       █▓▒░   ',
  '     ░▒▓█      └───────────────┘      █▓▒░    ',
  '      ░▒▓█                           █▓▒░     ',
  '        ░▒▓█                       █▓▒░       ',
  '            ▒▒▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▒▒           ',
  '                    \\ | /                     ',
  '                     \\|/                      ',
  '                      |                       ',
  '                      ·                       ',
]

/** Pad at render time so an edit to the arrays above cannot leave them ragged. */
function block(lines) {
  const width = Math.max(...lines.map((l) => l.length))
  return lines.map((l) => l.padEnd(width)).join('\n')
}

const NAV = [
  { label: 'PIPELINE', href: '#pipeline' },
  { label: 'DETECTOR', href: '#detector' },
  { label: 'CHART', href: '#chart' },
  { label: 'REPORT', href: '#report' },
]

const SPECS = [
  { icon: Radar, label: 'DETECTOR', value: 'YOLOv8 / ONNX' },
  { icon: Waves, label: 'INGEST', value: 'XTF · JSF' },
  { icon: Activity, label: 'mAP@0.5', value: '0.839' },
]

export default function HeroAsciiCore({
  brand = 'WRECKOGNISE',
  version = 'v1.0.0',
  vessel = 'AURORA-CLASS SURVEY CORE',
  headline = 'Find every wreck on the seabed.',
  headlineAccent = 'Fix it to a coordinate.',
  body =
    'Raw side-scan sonar in, georeferenced contacts out. OpenCV strips the acoustic ' +
    'speckle, a YOLOv8 detector sweeps the swath, and every bounding box resolves to a ' +
    'WGS-84 position with a stated error budget.',
  primaryCta = 'run --demo-scan',
  secondaryCta = 'upload sonar',
  onPrimary,
  onSecondary,
}) {
  // The caret is the only motion on the page; ASCII plus a blink reads as a
  // live terminal without anything having to animate.
  const [caret, setCaret] = useState(true)
  useEffect(() => {
    const id = setInterval(() => setCaret((c) => !c), 560)
    return () => clearInterval(id)
  }, [])

  return (
    <main className="relative min-h-screen overflow-hidden bg-[#05070A] text-neutral-200">
      {/* Scanline + vignette wash */}
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.18]"
        style={{
          backgroundImage:
            'repeating-linear-gradient(0deg, rgba(0,180,216,0.10) 0px, rgba(0,180,216,0.10) 1px, transparent 1px, transparent 3px)',
        }}
      />
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            'radial-gradient(ellipse 70% 55% at 50% 42%, rgba(0,180,216,0.13), transparent 70%)',
        }}
      />

      {/* Corner brackets */}
      <div className="pointer-events-none absolute left-4 top-4 h-8 w-8 border-l border-t border-cyan-400/30 lg:h-12 lg:w-12" />
      <div className="pointer-events-none absolute right-4 top-4 h-8 w-8 border-r border-t border-cyan-400/30 lg:h-12 lg:w-12" />
      <div className="pointer-events-none absolute bottom-4 left-4 h-8 w-8 border-b border-l border-cyan-400/30 lg:h-12 lg:w-12" />
      <div className="pointer-events-none absolute bottom-4 right-4 h-8 w-8 border-b border-r border-cyan-400/30 lg:h-12 lg:w-12" />

      {/* Nav */}
      <header className="relative z-10 border-b border-white/8">
        <nav className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4 lg:px-10">
          <div className="flex items-center gap-3">
            <Terminal className="h-4 w-4 text-cyan-400" strokeWidth={1.5} />
            <span
              className="text-sm font-semibold tracking-[0.28em] text-white"
              style={{ fontFamily: MONO }}
            >
              {brand}
            </span>
            <span className="hidden h-3 w-px bg-white/20 sm:block" />
            <span
              className="hidden text-[10px] tracking-[0.2em] text-neutral-500 sm:block"
              style={{ fontFamily: MONO }}
            >
              {version}
            </span>
          </div>

          <div className="hidden items-center gap-8 lg:flex">
            {NAV.map((item) => (
              <a
                key={item.label}
                href={item.href}
                className="text-[11px] tracking-[0.2em] text-neutral-500 transition-colors hover:text-cyan-400"
                style={{ fontFamily: MONO }}
              >
                {item.label}
              </a>
            ))}
          </div>

          <div className="flex items-center gap-2">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-cyan-400" />
            <span
              className="text-[10px] tracking-[0.2em] text-neutral-500"
              style={{ fontFamily: MONO }}
            >
              ONLINE
            </span>
          </div>
        </nav>
      </header>

      <div className="relative z-10 mx-auto max-w-7xl px-5 pb-24 pt-10 lg:px-10 lg:pt-14">
        {/* --- ASCII hero graphic --- */}
        <div className="flex flex-col items-center">
          <p
            className="mb-6 text-[10px] tracking-[0.34em] text-neutral-600"
            style={{ fontFamily: MONO }}
          >
            {vessel}
          </p>

          <div className="relative w-full overflow-hidden">
            <div
              className="pointer-events-none absolute inset-0 blur-2xl"
              style={{
                background:
                  'radial-gradient(ellipse 45% 60% at 50% 50%, rgba(0,180,216,0.22), transparent 70%)',
              }}
            />

            {/* Scales by font-size alone: no transform, so it stays crisp. */}
            <pre
              aria-hidden="true"
              className="relative hidden select-none whitespace-pre text-center text-cyan-300/85 sm:block"
              style={{
                fontFamily: MONO,
                fontSize: 'clamp(4.5px, 1.08vw, 12px)',
                lineHeight: 1.18,
                textShadow: '0 0 12px rgba(0,180,216,0.45)',
              }}
            >
              {block(CORE)}
            </pre>

            <pre
              aria-hidden="true"
              className="relative select-none whitespace-pre text-center text-cyan-300/85 sm:hidden"
              style={{
                fontFamily: MONO,
                fontSize: 'clamp(5px, 2.3vw, 10px)',
                lineHeight: 1.2,
                textShadow: '0 0 10px rgba(0,180,216,0.45)',
              }}
            >
              {block(CORE_COMPACT)}
            </pre>
          </div>

          {/* Spec rail */}
          <div className="mt-8 grid w-full max-w-3xl grid-cols-3 divide-x divide-white/8 border-y border-white/8">
            {SPECS.map(({ icon: Icon, label, value }) => (
              <div key={label} className="flex flex-col items-center gap-1.5 px-2 py-3">
                <Icon className="h-3.5 w-3.5 text-cyan-400/70" strokeWidth={1.5} />
                <span
                  className="text-[9px] tracking-[0.22em] text-neutral-600"
                  style={{ fontFamily: MONO }}
                >
                  {label}
                </span>
                <span
                  className="text-[11px] text-neutral-200"
                  style={{ fontFamily: MONO }}
                >
                  {value}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* --- Value proposition --- */}
        <div className="mx-auto mt-14 max-w-3xl text-center">
          <h1 className="text-3xl font-semibold leading-[1.12] tracking-tight text-white sm:text-4xl lg:text-5xl">
            {headline}
            <span className="mt-1 block text-cyan-400">{headlineAccent}</span>
          </h1>

          <p className="mx-auto mt-6 max-w-2xl text-sm leading-relaxed text-neutral-400 lg:text-base">
            {body}
          </p>

          {/* CTAs styled as terminal commands */}
          <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <button
              type="button"
              onClick={onPrimary}
              className="group flex w-full items-center justify-center gap-2 border border-cyan-400/60 bg-cyan-400/10 px-5 py-3 text-xs text-cyan-300 transition-colors hover:bg-cyan-400 hover:text-[#05070A] sm:w-auto"
              style={{ fontFamily: MONO }}
            >
              <span className="text-cyan-400/70 group-hover:text-[#05070A]">$</span>
              {primaryCta}
              <span className={caret ? 'opacity-100' : 'opacity-0'}>_</span>
              <ArrowRight className="h-3.5 w-3.5" strokeWidth={1.5} />
            </button>

            <button
              type="button"
              onClick={onSecondary}
              className="flex w-full items-center justify-center gap-2 border border-white/15 px-5 py-3 text-xs text-neutral-400 transition-colors hover:border-white/40 hover:text-white sm:w-auto"
              style={{ fontFamily: MONO }}
            >
              <span className="text-neutral-600">$</span>
              {secondaryCta}
            </button>
          </div>
        </div>
      </div>

      {/* Footer telemetry */}
      <footer className="absolute bottom-0 left-0 right-0 z-10 border-t border-white/8 bg-black/40 backdrop-blur-sm">
        <div
          className="mx-auto flex max-w-7xl items-center justify-between px-5 py-2.5 text-[9px] tracking-[0.2em] text-neutral-600 lg:px-10"
          style={{ fontFamily: MONO }}
        >
          <span>WGS-84 / EPSG:4326</span>
          <span className="hidden sm:inline">LAT 8.6000&deg;N · LON 78.4000&deg;E</span>
          <span>SIH 2026</span>
        </div>
      </footer>
    </main>
  )
}
