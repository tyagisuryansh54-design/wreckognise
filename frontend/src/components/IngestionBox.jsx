import { useCallback, useEffect, useRef, useState } from 'react'
import { BentoCard, CardHeader, EmptyState, Meter, Row, Spinner, Stat } from './Primitives'
import { IconLayers, IconUpload, IconWave } from './Icons'
import { bytes } from '../utils/format'
import { assetUrl } from '../utils/api'

const DENOISE_OPTIONS = [
  { id: 'nlm', label: 'Non-Local Means', hint: 'Best speckle suppression' },
  { id: 'bilateral', label: 'Bilateral', hint: '~8× faster, deck-side review' },
  { id: 'none', label: 'Raw', hint: 'No denoising — baseline' },
]

/**
 * Bento box 1 -- data ingestion and OpenCV preprocessing.
 *
 * The comparison slider is the point of this card: it puts the raw swath and
 * the denoised swath in the same pixels so the filter's effect is visible
 * rather than merely asserted in a metrics table.
 */
export default function IngestionBox({ ingest, busy, onUpload, onDemo, onSample, samples = [], uploadRef }) {
  const [method, setMethod] = useState('nlm')
  const [sampleIndex, setSampleIndex] = useState(0)
  const [split, setSplit] = useState(52)
  const [dragging, setDragging] = useState(false)
  const frameRef = useRef(null)

  /*
   * How the swath on screen was loaded, so changing the kernel can re-run it.
   *
   * Without this the selector only set a variable that the NEXT load happened
   * to read: with a swath already on screen, picking a different filter
   * changed nothing visible. A control that looks live and does nothing is
   * worse than no control -- it reads as a broken app rather than a setting.
   */
  const replay = useRef(null)
  const lastMethod = useRef(method)

  const handleFiles = useCallback(
    (files) => {
      const file = files?.[0]
      if (!file) return
      replay.current = (m) => onUpload(file, { denoiseMethod: m })
      onUpload(file, { denoiseMethod: method })
    },
    [onUpload, method],
  )

  // Re-run the current swath when the kernel changes. Skipped on first render
  // and while a stage is already running.
  useEffect(() => {
    if (lastMethod.current === method) return
    lastMethod.current = method
    if (!ingest || busy || !replay.current) return
    replay.current(method)
  }, [method, ingest, busy])

  const onDrop = useCallback(
    (event) => {
      event.preventDefault()
      setDragging(false)
      handleFiles(event.dataTransfer.files)
    },
    [handleFiles],
  )

  /** Drag the split handle with pointer capture so it tracks outside the frame. */
  const startDrag = useCallback((event) => {
    const frame = frameRef.current
    if (!frame) return
    event.preventDefault()

    const move = (e) => {
      const rect = frame.getBoundingClientRect()
      const clientX = e.touches?.[0]?.clientX ?? e.clientX
      setSplit(Math.max(2, Math.min(98, ((clientX - rect.left) / rect.width) * 100)))
    }
    const stop = () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', stop)
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', stop)
  }, [])

  const stats = ingest?.preprocess
  const meta = ingest?.metadata

  return (
    <BentoCard tone="light" className="flex flex-col p-6">
      <CardHeader
        eyebrow="01 · Ingestion & Preprocessing"
        title="Raw sonar in, clean swath out"
        meta="pyxtf decode → TVG normalisation → OpenCV denoise → CLAHE"
        action={
          <span className="hidden shrink-0 rounded-full bg-ink/5 p-2.5 text-azure sm:block">
            <IconWave className="h-5 w-5" />
          </span>
        }
      />

      {/* --- drop zone --- */}
      <div
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`mt-5 rounded-2xl border-2 border-dashed px-5 py-4 transition-colors ${
          dragging ? 'border-aqua bg-aqua/8' : 'border-ink/15 bg-sand/50'
        }`}
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="grid h-9 w-9 place-items-center rounded-lg bg-navy text-aqua">
              {busy === 'ingest' ? <Spinner className="h-4 w-4" /> : <IconUpload className="h-4 w-4" />}
            </span>
            <div>
              <p className="font-sans text-sm font-semibold text-ink">
                {busy === 'ingest' ? 'Decoding sonar packets…' : 'Drop a sonar capture or waterfall image'}
              </p>
              <p className="font-serif text-xs text-ink/50">
                Raw: XTF · JSF · SEG-Y   |   Image: JPG · PNG · TIFF
              </p>
            </div>
          </div>

          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => uploadRef.current?.click()}
              disabled={busy === 'ingest'}
              className="btn-dark !px-4 !py-2"
            >
              Browse
            </button>
            <button
              type="button"
              onClick={() => {
                replay.current = (m) => onDemo(m)
                onDemo(method)
              }}
              disabled={busy === 'ingest'}
              className="btn-ghost !px-4 !py-2"
              title="A modelled swath — synthetic, for exercising the full pipeline"
            >
              Demo Line
            </button>
            {samples.length > 0 && (
              <button
                type="button"
                onClick={() => {
                  const pick = samples[sampleIndex % samples.length].file
                  replay.current = (m) => onSample(pick, m)
                  onSample(pick, method)
                  setSampleIndex((i) => i + 1)
                }}
                disabled={busy === 'ingest'}
                className="btn-primary !px-4 !py-2"
                title={samples[sampleIndex % samples.length].description}
              >
                Real Sonar
              </button>
            )}
          </div>
        </div>

        <input
          ref={uploadRef}
          type="file"
          accept=".xtf,.jsf,.sgy,.segy,.jpg,.jpeg,.png,.tif,.tiff"
          className="hidden"
          onChange={(e) => {
            handleFiles(e.target.files)
            e.target.value = ''
          }}
        />
      </div>

      {/* --- denoise kernel selector --- */}
      <fieldset className="mt-4">
        <legend className="label text-ink/40">Denoise Kernel</legend>
        <div className="segmented mt-2">
          {DENOISE_OPTIONS.map((option) => (
            <button
              key={option.id}
              type="button"
              onClick={() => setMethod(option.id)}
              title={option.hint}
              aria-pressed={method === option.id}
              className={
                method === option.id
                  ? 'bg-azure/12 text-azure'
                  : 'text-ink-dim hover:bg-ink/[0.04] hover:text-ink'
              }
            >
              <span className="block font-mono text-2xs font-semibold uppercase tracking-label">
                {option.label}
              </span>
              <span className="mt-0.5 block truncate text-2xs text-ink-faint">
                {option.hint}
              </span>
            </button>
          ))}
        </div>
      </fieldset>

      {/* --- comparison viewer --- */}
      <div className="mt-5 flex-1">
        {!ingest ? (
          <div className="h-56 rounded-2xl border border-ink/10 bg-ink/[0.03]">
            <EmptyState
              icon={<IconLayers className="h-5 w-5" />}
              title="No swath loaded"
              body="Upload a capture or load the demo line to see the raw and filtered waterfalls side by side."
            />
          </div>
        ) : (
          <>
            {meta?.file_format === 'image' && (
              /* A bare sonar image carries no navigation. Coordinates derived
                 from a simulated track must never read as survey-grade. */
              <div className="mb-3 rounded-xl border border-aqua/40 bg-aqua/10 px-4 py-2.5">
                <p className="label text-azure">Real Sonar · Held-Out Sample</p>
                <p className="mt-1 font-serif text-xs leading-relaxed text-ink/70">
                  Genuine survey imagery the detector never saw during training.
                  The image carries no navigation, so the track and coordinates
                  are simulated for illustration — the detections are real.
                </p>
              </div>
            )}
            <div
              ref={frameRef}
              className="relative h-64 select-none overflow-hidden rounded-2xl bg-navy ring-1 ring-ink/15 md:h-72"
            >
              {/* Filtered (right of the handle) sits underneath. */}
              <img
                src={assetUrl(ingest.filtered_waterfall_png)}
                alt="OpenCV-denoised sonar waterfall"
                className="absolute inset-0 h-full w-full object-cover"
                draggable="false"
              />
              {/* Raw (left of the handle) is clipped over the top. */}
              <div
                className="absolute inset-0 overflow-hidden"
                style={{ clipPath: `inset(0 ${100 - split}% 0 0)` }}
              >
                <img
                  src={assetUrl(ingest.raw_waterfall_png)}
                  alt="Raw sonar waterfall before filtering"
                  className="h-full w-full object-cover"
                  draggable="false"
                />
              </div>

              <span className="pointer-events-none absolute left-3 top-3 rounded-full bg-cream/85 px-2.5 py-1 font-mono text-2xs font-semibold uppercase tracking-label text-coral">
                Raw
              </span>
              <span className="pointer-events-none absolute right-3 top-3 rounded-full bg-cream/85 px-2.5 py-1 font-mono text-2xs font-semibold uppercase tracking-label text-aqua">
                Filtered
              </span>
              <span className="pointer-events-none absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full bg-cream/85 px-2.5 py-1 font-mono text-2xs text-ink/60">
                nadir ▲ centre-frame
              </span>

              {/* Split handle */}
              <div
                className="absolute inset-y-0 z-10 w-0.5 cursor-ew-resize bg-aqua"
                style={{ left: `${split}%` }}
                onPointerDown={startDrag}
                role="slider"
                tabIndex={0}
                aria-label="Compare raw and filtered swath"
                aria-valuenow={Math.round(split)}
                aria-valuemin={2}
                aria-valuemax={98}
                onKeyDown={(e) => {
                  if (e.key === 'ArrowLeft') setSplit((s) => Math.max(2, s - 4))
                  if (e.key === 'ArrowRight') setSplit((s) => Math.min(98, s + 4))
                }}
              >
                <span className="absolute left-1/2 top-1/2 grid h-8 w-8 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full bg-aqua text-ink shadow-lg">
                  <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
                    <path d="m10 8-4 4 4 4M14 8l4 4-4 4" />
                  </svg>
                </span>
              </div>
            </div>

            {/* --- quality metrics --- */}
            <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
              <Stat
                label="SNR Gain"
                value={`${stats.snr_gain_db > 0 ? '+' : ''}${stats.snr_gain_db.toFixed(2)}`}
                unit="dB"
                accent={stats.snr_gain_db > 0 ? 'text-azure' : 'text-coral'}
              />
              <Stat label="Speckle Index" value={stats.speckle_index_after.toFixed(3)} hint={`from ${stats.speckle_index_before}`} />
              <Stat label="Contrast" value={`×${stats.contrast_ratio.toFixed(2)}`} />
              <Stat label="Stage Time" value={stats.elapsed_ms.toFixed(0)} unit="ms" />
            </div>

            <div className="mt-3">
              <div className="flex items-center justify-between">
                <span className="label text-ink/40">Speckle Suppression</span>
                <span className="font-mono text-2xs text-ink/50">
                  {stats.speckle_index_before.toFixed(3)} → {stats.speckle_index_after.toFixed(3)}
                </span>
              </div>
              <div className="mt-1.5">
                <Meter
                  value={Math.max(
                    0,
                    1 - stats.speckle_index_after / Math.max(stats.speckle_index_before, 1e-6),
                  )}
                  colour="bg-gradient-to-r from-azure to-aqua"
                />
              </div>
            </div>

            {/* --- decoded file facts --- */}
            <dl className="mt-4 rounded-xl bg-sand/60 px-4 py-2">
              <Row label="Source" value={meta.filename} mono={false} />
              <Row label="Parser" value={meta.parser} mono={false} />
              <Row label="Pings decoded" value={meta.ping_count.toLocaleString()} />
              <Row label="Channels" value={meta.channels.map((c) => `${c.name} ${c.frequency_khz}kHz`).join(' · ')} />
              <Row label="Swath / line" value={`${meta.swath_width_m} m × ${(meta.line_length_m / 1000).toFixed(3)} km`} />
              <Row label="Mean altitude" value={`${meta.mean_altitude_m} m`} />
              <Row label="File size" value={bytes(meta.file_size_bytes)} />
              <Row label="Kernel" value={stats.kernel} mono={false} />
            </dl>
          </>
        )}
      </div>
    </BentoCard>
  )
}
