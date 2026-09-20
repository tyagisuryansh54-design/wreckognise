import { lazy, Suspense, useRef } from 'react'
import { useAuth } from './hooks/useAuth'
import { useInView } from './hooks/useMotion'
import { useSurvey } from './hooks/useSurvey'
import Hero from './components/Hero'
import LoginPage from './components/LoginPage'
import SiteNav from './components/SiteNav'
import HazardAlert from './components/HazardAlert'
import SonarBackdrop from './components/SonarBackdrop'
import PipelineStatus from './components/PipelineStatus'
import IngestionBox from './components/IngestionBox'
import InferenceBox from './components/InferenceBox'
import MapBox from './components/MapBox'
/*
 * three.js more than doubles the bundle -- 112 KB gzipped to 251 KB -- and the
 * relief view is one panel far down a long page. Loaded on demand instead, so
 * the cost lands on the reader who scrolls to it rather than on everyone who
 * opens the site.
 */
const ReliefView = lazy(() => import('./components/ReliefView'))
import ContactRegister from './components/ContactRegister'
import ActionBox from './components/ActionBox'
import { ProgressBar } from './components/Primitives'
import { IconAlert, IconX } from './components/Icons'

/*
 * Replaced at build time by Vite (see vite.config.js). Declared with a
 * fallback so the module still evaluates under a bare `vite dev` from a
 * config that predates the define.
 */
const BUILD_DATE = typeof __BUILD_DATE__ === 'string' ? __BUILD_DATE__ : '2026-01-01'

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
  const auth = useAuth()
  const survey = useSurvey()
  const uploadRef = useRef(null)

  // Hooks run unconditionally -- returning before useSurvey() would change the
  // hook order between renders, which React rejects outright. So the gate sits
  // after the hooks and only swaps what is rendered.
  //
  // There is no loading branch here on purpose. Holding a blank screen until
  // the auth probe answers meant a sleeping backend rendered the site black
  // for minutes.
  if (auth.gated) {
    return <LoginPage onAuthenticated={auth.signIn} />
  }

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
    acknowledgeHazard,
  } = survey

  /*
   * An uploaded or bundled IMAGE carries no navigation -- a picture has no GPS
   * per ping. The pipeline attaches a plausible track so the geodesy and chart
   * stay exercisable, but the coordinates that fall out are invented, and a
   * coordinate on screen is read as a fix. So they are withheld for image
   * sources rather than shown with a caveat nobody reads.
   */
  const simulatedNav = ingest?.metadata?.file_format === 'image'

  return (
    <div className="min-h-screen">
      <ProgressBar value={progress} />
      <SonarBackdrop />
      <SiteNav />

      <main className="mx-auto max-w-6xl px-5 pb-24 pt-16 sm:px-8">
        <Hero
          health={health}
          stage={stage}
          busy={busy}
          onExplore={() => loadDemo('nlm')}
          onUpload={() => uploadRef.current?.click()}
        />

        {/* Above the pipeline, deliberately: ordnance must not wait its turn
            in the register. */}
        <HazardAlert
          detections={detections}
          onAcknowledge={acknowledgeHazard}
          onSelect={setSelectedId}
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
              simulatedNav={simulatedNav}
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
              simulatedNav={simulatedNav}
              telemetry={telemetry}
              detections={detections}
              selected={selected}
              onSelect={setSelectedId}
            />
          </Section>

          <Section id="relief" label="05 / relief" title="The swath, in three dimensions.">
            <Suspense
              fallback={
                <div className="flex h-80 items-center justify-center rounded border border-ink/10 bg-sand">
                  <p className="font-mono text-2xs text-ink-dim">loading renderer…</p>
                </div>
              }
            >
              <ReliefView ingest={ingest} detections={detections} />
            </Suspense>
          </Section>

          <Section id="register" label="06 / triage" title="Contacts, dispositioned.">
            <ContactRegister
              simulatedNav={simulatedNav}
              detections={detections}
              selected={selected}
              onSelect={setSelectedId}
              summary={inference?.summary}
            />
          </Section>

          <Section id="report" label="07 / report" title="Brief and GIS export.">
            <ActionBox
              surveyId={ingest?.survey_id}
              simulatedNav={simulatedNav}
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

        {/*
          The right-hand column is provenance, not decoration. A hydrographer
          reading a machine-derived contact wants to know which datum it is in
          and which build produced it, and both belong somewhere permanent
          rather than in a release note nobody keeps.

          The detector version comes from /api/health, so it describes what is
          actually serving rather than what this bundle was built against --
          the two drift apart the moment either side deploys alone.
        */}
        <footer className="mt-28 border-t border-shell pt-8">
          <div className="flex flex-col gap-8 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="flex items-baseline gap-2.5">
                <span className="h-[7px] w-[7px] shrink-0 translate-y-[-1px] bg-azure" />
                <span className="text-sm font-semibold uppercase tracking-[0.2em] text-ink">
                  Wreckognise
                </span>
              </p>
              <p className="mt-3 max-w-lg text-xs leading-relaxed text-ink-faint">
                Automated marine survey agent. AI-derived contacts are decision support,
                not a substitute for qualified hydrographic review.
              </p>
            </div>

            <dl className="grid gap-x-6 gap-y-1.5 font-mono text-2xs text-ink-faint sm:text-right">
              <div className="flex gap-2 sm:justify-end">
                <dt className="text-ink-faint/60">datum</dt>
                <dd className="text-ink-dim">WGS-84 &middot; EPSG:4326</dd>
              </div>
              <div className="flex gap-2 sm:justify-end">
                <dt className="text-ink-faint/60">detector</dt>
                <dd className="text-ink-dim">
                  {health === undefined
                    ? '—'
                    : health?.version
                      ? `v${health.version}${health.detection_engine ? ` · ${health.detection_engine}` : ''}`
                      : 'offline'}
                </dd>
              </div>
              <div className="flex gap-2 sm:justify-end">
                <dt className="text-ink-faint/60">updated</dt>
                <dd className="text-ink-dim">
                  <time dateTime={BUILD_DATE}>{BUILD_DATE}</time>
                </dd>
              </div>
            </dl>
          </div>

          <p className="mt-8 border-t border-shell/60 pt-5 font-mono text-2xs text-ink-faint/70">
            &copy; {BUILD_DATE.slice(0, 4)} Wreckognise
          </p>
        </footer>

      </main>
    </div>
  )
}
