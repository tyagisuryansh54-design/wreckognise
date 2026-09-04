import { useRef } from 'react'
import { useSurvey } from './hooks/useSurvey'
import Hero from './components/Hero'
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
    error,
    clearError,
    loadDemo,
    uploadFile,
    detect,
    generateReport,
    reviewContact,
  } = survey

  return (
    <div className="min-h-screen">
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
