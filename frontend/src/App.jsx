import { useRef } from 'react'
import { useInView } from './hooks/useMotion'
import { useSurvey } from './hooks/useSurvey'
import Hero from './components/Hero'
import SiteNav from './components/SiteNav'
import PipelineStatus from './components/PipelineStatus'
import IngestionBox from './components/IngestionBox'
import InferenceBox from './components/InferenceBox'
import MapBox from './components/MapBox'
import ContactRegister from './components/ContactRegister'
import ActionBox from './components/ActionBox'
import { ProgressBar } from './components/Primitives'
import { IconAlert, IconX } from './components/Icons'

/**
 * One pipeline stage. The code-comment label is the reference template's own
 * device for section headers, and it earns its place here: these really are
 * numbered stages in a pipeline.
 */
function Section({ id, label, title, children }) {
  const [ref, inView] = useInView()
  return (
    <section
      id={id}
      ref={ref}
      className={`scroll-mt-24 transition-[opacity,transform] duration-700 ease-out ${
        inView ? 'translate-y-0 opacity-100' : 'translate-y-3 opacity-0'
      }`}
    >
      <p className="comment">{label}</p>
      <h2 className="mt-3 text-2xl font-bold tracking-tight text-ink sm:text-3xl">{title}</h2>
      <div className="mt-6">{children}</div>
    </section>
  )
}

export default function App() {
  const survey = useSurvey()
  const uploadRef = useRef(null)

  const {
    health,
    ingest,
    inference,
    telemetry,
    report,
    detections,
    selected,
    setSelectedId,
    stage,
    busy,
    progress,
    waking,
    error,
    clearError,
    loadDemo,
    loadSample,
    samples,
    uploadFile,
    detect,
    generateReport,
    reviewContact,
  } = survey

  return (
    <div className="min-h-screen">
      <ProgressBar value={progress} />
      <SiteNav />

      <main className="mx-auto max-w-6xl px-5 pb-24 pt-16 sm:px-8">
        <Hero
          health={health}
          stage={stage}
          busy={busy}
          onExplore={() => loadDemo('nlm')}
          onUpload={() => uploadRef.current?.click()}
        />

        {/*
          A cold start is not a failure, and showing it as one taught visitors
          the site was broken when it was merely asleep. The free instance
          suspends after 15 minutes idle and takes about a minute to boot;
          say so, and let the retry in api.js finish the job.
        */}
        {waking && !error && (
          <div
            role="status"
            className="mt-4 flex items-start gap-3 rounded-2xl border border-amber/35 bg-amber/10 px-5 py-4 animate-rise-in"
          >
            <span className="mt-1 shrink-0">
              <span className="block h-2.5 w-2.5 animate-pulse rounded-full bg-amber" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="font-mono text-2xs font-semibold uppercase tracking-label text-sunset">
                Waking the Inference Backend
              </p>
              <p className="mt-1 font-serif text-sm text-ink/70">
                The API sleeps when idle to stay within the free hosting tier. First
                request after a quiet spell takes up to a minute while it boots — this
                will clear on its own, no action needed.
              </p>
            </div>
          </div>
        )}

        {error && (
          <div
            role="alert"
            className="mt-4 flex items-start gap-3 rounded-2xl border border-coral/30 bg-coral/8 px-5 py-4 animate-rise-in"
          >
            <span className="mt-0.5 shrink-0 text-coral">
              <IconAlert className="h-4 w-4" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="font-mono text-2xs font-semibold uppercase tracking-label text-coral">
                Pipeline Error
              </p>
              <p className="mt-1 font-serif text-sm text-ink/70">{error}</p>
            </div>
            <button
              type="button"
              onClick={clearError}
              aria-label="Dismiss error"
              className="shrink-0 rounded-full p-1 text-ink/35 transition-colors hover:bg-ink/6 hover:text-ink"
            >
              <IconX className="h-3.5 w-3.5" />
            </button>
          </div>
        )}

        {/*
          Stacked sections rather than a bento grid.

          The grid packed seven cards into a viewport, which is how an
          operations console is read but not how a landing page is. One
          section per pipeline stage, each announced by a code-comment label,
          gives the page a spine and lets each stage have room.
        */}
        <div className="mt-8 space-y-24">
          <Section id="ingest" label="01 / ingest" title="Raw sonar in.">
            <IngestionBox
              ingest={ingest}
              busy={busy}
              uploadRef={uploadRef}
              onUpload={uploadFile}
              onDemo={loadDemo}
              onSample={loadSample}
              samples={samples}
            />
          </Section>

          <Section id="pipeline" label="02 / pipeline" title="Five stages, audited.">
            <PipelineStatus
              stage={stage}
              ingest={ingest}
              inference={inference}
              report={report}
              busy={busy}
            />
          </Section>

          <Section id="detect" label="03 / detect" title="YOLOv8 across the swath.">
            <InferenceBox
              ingest={ingest}
              inference={inference}
              detections={detections}
              selected={selected}
              onSelect={setSelectedId}
              busy={busy}
              onDetect={detect}
            />
          </Section>

          <Section id="chart" label="04 / georeference" title="Every box, a coordinate.">
            <MapBox
              telemetry={telemetry}
              detections={detections}
              selected={selected}
              onSelect={setSelectedId}
            />
          </Section>

          <Section id="register" label="05 / triage" title="Contacts, dispositioned.">
            <ContactRegister
              detections={detections}
              selected={selected}
              onSelect={setSelectedId}
              summary={inference?.summary}
            />
          </Section>

          <Section id="report" label="06 / report" title="Brief and GIS export.">
            <ActionBox
              ingest={ingest}
              inference={inference}
              selected={selected}
              report={report}
              busy={busy}
              onReview={reviewContact}
              onGenerate={generateReport}
            />
          </Section>
        </div>

        <footer className="mt-28 border-t border-shell pt-8">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="font-mono text-sm font-bold text-azure">&lt;wreckognise /&gt;</p>
              <p className="mt-2 max-w-lg text-xs leading-relaxed text-ink-faint">
                Automated marine survey agent. AI-derived contacts are decision support,
                not a substitute for qualified hydrographic review.
              </p>
            </div>
            <p className="font-mono text-2xs text-ink-faint">
              smart india hackathon 2026 &middot; wgs-84 / epsg:4326
            </p>
          </div>
        </footer>

      </main>
    </div>
  )
}
