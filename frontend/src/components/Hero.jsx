import { Badge, Spinner } from './Primitives'
import {
  IconChip,
  IconReport,
  IconSatellite,
  IconShield,
  IconSonar,
  IconTarget,
  IconUpload,
} from './Icons'

const TRUST_SIGNALS = [
  { icon: IconShield, label: 'SIH 2026 Finalist', detail: 'Smart India Hackathon' },
  { icon: IconSatellite, label: 'Sub-Meter GPS Accuracy', detail: 'RTK-corrected WGS-84' },
  { icon: IconChip, label: 'High-Precision Telemetry Sync', detail: 'Per-ping nav binding' },
]

/**
 * Mission header: the one screen a judge reads before deciding whether the
 * rest of the dashboard is worth their time.
 */
export default function Hero({ onExplore, onUpload, onReport, stage, busy, health }) {
  const engineLive = Boolean(health)

  return (
    <header className="relative overflow-hidden rounded-bento bg-navy text-cream shadow-bento">
      {/* Sonar chrome: grid, sweep line and range arcs. */}
      <div className="pointer-events-none absolute inset-0 grid-overlay opacity-40" />
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="h-16 w-full animate-sweep bg-gradient-to-b from-transparent via-aqua/12 to-transparent" />
      </div>
      <svg
        className="pointer-events-none absolute -right-20 -top-24 h-[30rem] w-[30rem] text-aqua/12"
        viewBox="0 0 200 200"
        fill="none"
        aria-hidden="true"
      >
        {[36, 58, 80, 102].map((r) => (
          <circle key={r} cx="100" cy="100" r={r} stroke="currentColor" strokeWidth="0.7" />
        ))}
        <path d="M100 100 L100 0 A100 100 0 0 1 186 50 Z" fill="currentColor" opacity="0.25" />
      </svg>
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-40 bg-gradient-to-t from-teal/60 to-transparent" />

      <div className="relative px-6 py-10 sm:px-10 md:px-14 md:py-16">
        {/* --- brand + status bar --- */}
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="grid h-10 w-10 place-items-center rounded-xl bg-aqua/15 text-aqua ring-1 ring-aqua/30">
              <IconSonar className="h-5 w-5" />
            </span>
            <div>
              <p className="font-mono text-sm font-bold uppercase tracking-label text-cream">
                Wreckognise
              </p>
              <p className="label text-cream/40">Marine Survey Agent · v1.0</p>
            </div>
          </div>

          <Badge
            className={
              engineLive
                ? 'bg-aqua/15 text-aqua ring-1 ring-aqua/30'
                : 'bg-coral/15 text-coral ring-1 ring-coral/30'
            }
            pulse
          >
            {engineLive ? 'Engines Online' : 'API Offline'}
          </Badge>
        </div>

        {/* --- headline --- */}
        <div className="mt-10 max-w-3xl">
          <p className="label text-aqua">Autonomous Seabed Intelligence</p>
          <h1 className="mt-4 font-display text-4xl font-bold leading-[1.05] tracking-tight text-cream sm:text-5xl md:text-6xl">
            Find every wreck on the seabed.
            <span className="block text-aqua">Fix it to a coordinate.</span>
          </h1>
          <p className="mt-6 max-w-2xl font-serif text-lg leading-relaxed text-cream/65 md:text-xl">
            Wreckognise ingests raw side-scan sonar, strips acoustic speckle with
            OpenCV, and runs a YOLOv8 detector across the swath — then converts every
            bounding box into a WGS-84 position accurate to under a metre. What took a
            hydrographer a full shift now takes a single pass.
          </p>
        </div>

        {/* --- calls to action --- */}
        <div className="mt-9 flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={onExplore}
            disabled={busy === 'ingest'}
            className="btn-primary"
          >
            {busy === 'ingest' ? <Spinner /> : <IconTarget className="h-4 w-4" />}
            {busy === 'ingest' ? 'Scanning…' : 'Explore Live Scan'}
          </button>

          <button type="button" onClick={onUpload} className="btn-ghost-light">
            <IconUpload className="h-4 w-4" />
            Upload Sonar Data
          </button>

          <button
            type="button"
            onClick={onReport}
            disabled={stage !== 'complete' || busy === 'report'}
            className="btn-ghost-light"
            title={
              stage !== 'complete'
                ? 'Run ingestion and detection before generating a report'
                : 'Generate the executive survey summary'
            }
          >
            {busy === 'report' ? <Spinner /> : <IconReport className="h-4 w-4" />}
            Generate Report
          </button>
        </div>

        {/* --- trust signals --- */}
        <ul className="mt-11 grid gap-3 border-t border-cream/10 pt-7 sm:grid-cols-3">
          {TRUST_SIGNALS.map(({ icon: Icon, label, detail }) => (
            <li key={label} className="flex items-start gap-3">
              <span className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-cream/6 text-aqua ring-1 ring-cream/10">
                <Icon className="h-4 w-4" />
              </span>
              <div className="min-w-0">
                <p className="font-mono text-xs font-semibold uppercase tracking-wide text-cream">
                  {label}
                </p>
                <p className="mt-0.5 font-serif text-sm text-cream/45">{detail}</p>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </header>
  )
}
