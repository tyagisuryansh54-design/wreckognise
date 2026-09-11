import { useEffect, useRef, useState } from 'react'
import { useSurvey } from './hooks/useSurvey'
import Hero from './components/Hero'
import HeroAsciiOne from './components/ui/HeroAsciiOne'
import PipelineStatus from './components/PipelineStatus'
import IngestionBox from './components/IngestionBox'
import InferenceBox from './components/InferenceBox'
import MapBox from './components/MapBox'
import ContactRegister from './components/ContactRegister'
import ActionBox from './components/ActionBox'
import { ProgressBar } from './components/Primitives'
import { IconAlert, IconX } from './components/Icons'

export default function App() {
  const survey = useSurvey()
  const uploadRef = useRef(null)

  // The landing screen sits in front of the dashboard until a CTA is pressed.
  // useSurvey's health check still fires on mount underneath it, so the hosted
  // backend spends its cold start behind the hero rather than behind a spinner
  // the visitor is watching.
  const [entered, setEntered] = useState(false)
  const [pendingUpload, setPendingUpload] = useState(false)

  useEffect(() => {
    // The file input lives inside IngestionBox, which is not mounted while the
    // landing screen is up -- so the click has to wait for the dashboard to
    // render, one commit later.
    if (!entered || !pendingUpload) return
    setPendingUpload(false)
    uploadRef.current?.click()
  }, [entered, pendingUpload])

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

  if (!entered) {
    return (
      <HeroAsciiOne
        onPrimary={() => {
          setEntered(true)
          loadDemo('nlm')
        }}
        onSecondary={() => {
          setEntered(true)
          setPendingUpload(true)
        }}
      />
    )
  }

  return (
    <div className="min-h-screen animate-rise-in">
      <ProgressBar value={progress} />

      <main className="mx-auto max-w-[1500px] px-4 py-6 sm:px-6 lg:px-8 lg:py-10">
        <Hero
          health={health}
          stage={stage}
          busy={busy}
          onExplore={() => loadDemo('nlm')}
          onUpload={() => uploadRef.current?.click()}
          onReport={() => generateReport('markdown')}
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
              <p className="mt-1 font-serif text-sm text-navy/70">
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
              <p className="mt-1 font-serif text-sm text-navy/70">{error}</p>
            </div>
            <button
              type="button"
              onClick={clearError}
              aria-label="Dismiss error"
              className="shrink-0 rounded-full p-1 text-navy/35 transition-colors hover:bg-navy/6 hover:text-navy"
            >
              <IconX className="h-3.5 w-3.5" />
            </button>
          </div>
        )}

        {/*
          Bento grid.

          12 columns on large screens. The two heavy analysis cards take 7/5,
          the chart takes 7 beside the register's 5, and the pipeline strip and
          action card span their own rows. Everything collapses to one column
          on small screens in reading order: ingest, infer, map, register, act.
        */}
        <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-12">
          <div className="lg:col-span-12">
            <PipelineStatus
              stage={stage}
              ingest={ingest}
              inference={inference}
              report={report}
              busy={busy}
            />
          </div>

          <div className="lg:col-span-7">
            <IngestionBox
              ingest={ingest}
              busy={busy}
              uploadRef={uploadRef}
              onUpload={uploadFile}
              onDemo={loadDemo}
              onSample={loadSample}
              samples={samples}
            />
          </div>

          <div className="lg:col-span-5">
            <InferenceBox
              ingest={ingest}
              inference={inference}
              detections={detections}
              selected={selected}
              onSelect={setSelectedId}
              busy={busy}
              onDetect={detect}
            />
          </div>

          <div className="lg:col-span-7">
            <MapBox
              telemetry={telemetry}
              detections={detections}
              selected={selected}
              onSelect={setSelectedId}
            />
          </div>

          <div className="lg:col-span-5">
            <ContactRegister
              detections={detections}
              selected={selected}
              onSelect={setSelectedId}
              summary={inference?.summary}
            />
          </div>

          <div className="lg:col-span-12">
            <ActionBox
              ingest={ingest}
              inference={inference}
              selected={selected}
              report={report}
              busy={busy}
              onReview={reviewContact}
              onGenerate={generateReport}
            />
          </div>
        </div>

        <footer className="mt-10 flex flex-col items-center justify-between gap-3 border-t border-navy/8 pt-6 text-center sm:flex-row sm:text-left">
          <p className="font-serif text-xs text-navy/45">
            <span className="font-mono font-semibold uppercase tracking-label text-navy/60">
              Wreckognise
            </span>{' '}
            — automated marine survey agent. AI-derived contacts are decision support,
            not a substitute for qualified hydrographic review.
          </p>
          <p className="font-mono text-2xs uppercase tracking-label text-navy/35">
            Smart India Hackathon 2026 · WGS-84
          </p>
        </footer>
      </main>
    </div>
  )
}
