/**
 * Landing screen: ASCII core, value proposition, terminal-style CTAs.
 *
 * The spec rail carries measured numbers. 0.839 is the deployed model's
 * held-out mAP@0.5 and 0.203 is its cross-dataset score on a corpus it never
 * trained on -- the second number is the honest one and it stays on the page.
 */

import { useNavigate } from 'react-router-dom'
import { ArrowRight, Activity, Crosshair, Radar, Waves } from 'lucide-react'
import AsciiAiShip from '../AsciiAiShip'
import { Button, Panel } from '../primitives'

const SPECS = [
  { icon: Radar, label: 'DETECTOR', value: 'YOLOv8 / ONNX' },
  { icon: Waves, label: 'INGEST', value: 'XTF · JSF' },
  { icon: Activity, label: 'mAP@0.5', value: '0.839' },
  { icon: Crosshair, label: 'CROSS-SET', value: '0.203' },
]

const CAPABILITIES = [
  {
    title: 'SLANT-RANGE CORRECTED',
    body: 'Ground range solves as sqrt(slant^2 - altitude^2). Ignoring it is the largest avoidable error in side-scan positioning.',
  },
  {
    title: 'AUDITABLE ERROR BUDGET',
    body: 'RTK fix, layback, heading and sound-velocity terms combine in quadrature and are reported per contact, not asserted globally.',
  },
  {
    title: 'MEASURED, NOT CLAIMED',
    body: 'Accuracy is read from a metrics file written only by a real held-out evaluation. No file, no numbers.',
  },
]

export default function Home() {
  const navigate = useNavigate()

  return (
    <div className="mx-auto max-w-7xl px-5 pb-20 pt-10 lg:px-10">
      {/* --- hero --- */}
      <section className="flex flex-col items-center">
        <p className="mono mb-6 text-[10px] tracking-[0.34em] text-[var(--ink-dim)]">
          AURORA-CLASS SURVEY CORE
        </p>

        <AsciiAiShip />

        <div className="mt-10 grid w-full max-w-3xl grid-cols-2 divide-x divide-[var(--edge)] border-y border-[var(--edge)] sm:grid-cols-4">
          {SPECS.map(({ icon: Icon, label, value }) => (
            <div key={label} className="flex flex-col items-center gap-1.5 px-2 py-3">
              <Icon className="h-3.5 w-3.5 text-[var(--cyan)]/70" strokeWidth={1.5} />
              <span className="mono text-[9px] tracking-[0.22em] text-[var(--ink-dim)]">
                {label}
              </span>
              <span className="mono text-[11px] text-[var(--ink)]">{value}</span>
            </div>
          ))}
        </div>

        <div className="mx-auto mt-14 max-w-3xl text-center">
          <h1 className="text-3xl font-semibold leading-[1.12] tracking-tight text-white sm:text-4xl lg:text-5xl">
            Find every wreck on the seabed.
            <span className="mt-1 block text-[var(--cyan)]">Fix it to a coordinate.</span>
          </h1>

          <p className="mx-auto mt-6 max-w-2xl text-sm leading-relaxed text-[var(--ink-dim)] lg:text-base">
            Raw side-scan sonar in, georeferenced contacts out. OpenCV strips the acoustic
            speckle, a YOLOv8 detector sweeps the swath, and every bounding box resolves to a
            WGS-84 position with a stated error budget.
          </p>

          <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Button variant="primary" onClick={() => navigate('/dashboard')} className="w-full sm:w-auto">
              <span className="opacity-70">$</span> run --demo-scan
              <span className="con-caret">_</span>
              <ArrowRight className="h-3.5 w-3.5" strokeWidth={1.5} />
            </Button>
            <Button onClick={() => navigate('/sandbox')} className="w-full sm:w-auto">
              <span className="opacity-60">$</span> open sandbox
            </Button>
          </div>
        </div>
      </section>

      {/* --- capabilities --- */}
      <section className="mt-20 grid grid-cols-1 gap-4 md:grid-cols-3">
        {CAPABILITIES.map((c, i) => (
          <Panel key={c.title} title={c.title} meta={`0${i + 1}`}>
            <p className="text-sm leading-relaxed text-[var(--ink-dim)]">{c.body}</p>
          </Panel>
        ))}
      </section>
    </div>
  )
}
