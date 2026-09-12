import { useCallback, useEffect, useRef, useState } from 'react'
import { BentoCard, CardHeader, EmptyState, Meter, Row, Spinner, Stat } from './Primitives'
import { IconChip, IconScan, IconTarget } from './Icons'
import { api, assetUrl } from '../utils/api'
import { classLabel, compass, severityStyle, toDMS } from '../utils/format'

/**
 * Bento box 2 -- YOLOv8 inference and live georeferencing.
 *
 * Boxes are drawn as an SVG overlay in the swath's own pixel space rather than
 * baked into the image, so they stay crisp at any card width and stay
 * clickable. Moving the cursor over the swath probes the backend solver, which
 * is what makes the pixel -> Lat/Long chain legible instead of magical.
 */
export default function InferenceBox({
  simulatedNav = false,
  ingest,
  inference,
  detections,
  selected,
  onSelect,
  busy,
  onDetect,
}) {
  const [confidence, setConfidence] = useState(0.35)
  const [probe, setProbe] = useState(null)
  const [cursor, setCursor] = useState(null)
  const frameRef = useRef(null)
  const pendingRef = useRef(null)
  const lastCallRef = useRef(0)

  // Coalesce before multiplying: `undefined * 2` is NaN, and `??` does not
  // catch NaN, so the viewBox would silently become unusable.
  const swathWidth = (ingest?.metadata?.channels?.[0]?.samples_per_ping ?? 512) * 2
  const swathHeight = ingest?.metadata?.ping_count ?? 900

  /** Throttled solver probe -- at most one request every 140 ms. */
  const probeAt = useCallback(
    (px, py) => {
      if (!ingest) return
      const now = Date.now()
      pendingRef.current = [px, py]
      if (now - lastCallRef.current < 140) return
      lastCallRef.current = now
      const [x, y] = pendingRef.current
      api
        .georeference(ingest.survey_id, Math.round(x), Math.round(y))
        .then(setProbe)
        .catch(() => {})
    },
    [ingest],
  )

  useEffect(() => {
    setProbe(null)
    setCursor(null)
  }, [ingest?.survey_id])

  const onMove = useCallback(
    (event) => {
      const frame = frameRef.current
      if (!frame) return
      const rect = frame.getBoundingClientRect()

      /*
       * The swath is letterboxed inside a square frame, so the image does not
       * fill it. Mapping the pointer against the FRAME would report a
       * coordinate the cursor is not actually over -- increasingly wrong
       * toward the edges, and silently so, which on a pixel-to-WGS-84 solver
       * is the worst kind of wrong. Map against the rendered image instead.
       */
      const scale = Math.min(rect.width / swathWidth, rect.height / swathHeight)
      const drawnW = swathWidth * scale
      const drawnH = swathHeight * scale
      const offsetX = (rect.width - drawnW) / 2
      const offsetY = (rect.height - drawnH) / 2

      const localX = event.clientX - rect.left - offsetX
      const localY = event.clientY - rect.top - offsetY
      if (localX < 0 || localY < 0 || localX > drawnW || localY > drawnH) {
        setCursor(null)          // pointer is on the letterbox, not the swath
        return
      }

      setCursor({
        left: ((localX + offsetX) / rect.width) * 100,
        top: ((localY + offsetY) / rect.height) * 100,
      })
      probeAt((localX / drawnW) * swathWidth, (localY / drawnH) * swathHeight)
    },
    [probeAt, swathWidth, swathHeight],
  )

  const metrics = inference?.metrics
  const readout = probe ?? selected?.geo ?? null

  return (
    <BentoCard tone="dark" className="flex flex-col p-6">
      <CardHeader
        dark
        eyebrow="02 · AI Inference & Georeferencing"
        title="YOLOv8 acoustic anomaly detection"
        meta="Tiled inference → NMS → WGS-84 pixel solve"
        action={
          <span className="hidden shrink-0 rounded-full bg-cream/8 p-2.5 text-aqua sm:block">
            <IconChip className="h-5 w-5" />
          </span>
        }
      />

      {/* --- controls --- */}
      <div className="mt-5 flex flex-wrap items-end gap-4 rounded-2xl bg-cream/5 p-4 ring-1 ring-ink/10">
        <label className="min-w-[11rem] flex-1">
          <span className="label text-ink/40">
            Confidence Threshold · <span className="text-aqua">{confidence.toFixed(2)}</span>
          </span>
          <input
            type="range"
            min="0.05"
            max="0.95"
            step="0.05"
            value={confidence}
            onChange={(e) => setConfidence(Number(e.target.value))}
            className="mt-2 w-full accent-[#00B4D8]"
          />
        </label>
        <button
          type="button"
          onClick={() => onDetect({ confidence })}
          disabled={!ingest || busy === 'detect'}
          className="btn-primary"
          title={ingest ? 'Run the detector over the filtered swath' : 'Ingest a sonar line first'}
        >
          {busy === 'detect' ? <Spinner /> : <IconScan className="h-4 w-4" />}
          {busy === 'detect' ? 'Inferring…' : 'Run Detection'}
        </button>
      </div>

      {/* --- annotated swath with interactive overlay --- */}
      <div className="mt-5">
        {!inference ? (
          <div className="h-56 rounded-2xl bg-cream/[0.04] ring-1 ring-ink/10">
            <EmptyState
              dark
              icon={<IconTarget className="h-5 w-5" />}
              title={ingest ? 'Swath ready for inference' : 'Awaiting a sonar line'}
              body={
                ingest
                  ? 'Run detection to place bounding boxes and resolve each contact to a coordinate.'
                  : 'Ingest a capture in the panel to the left, then run the detector.'
              }
            />
          </div>
        ) : (
          <figure
            ref={frameRef}
            onMouseMove={onMove}
            onMouseLeave={() => setCursor(null)}
            className="relative mx-auto aspect-square w-full max-w-[512px] overflow-hidden rounded ring-1 ring-ink/15"
          >
            <img
              src={assetUrl(inference.annotated_png)}
              alt="Sonar waterfall with YOLOv8 detection boxes"
              className="block h-full w-full object-contain"
              draggable="false"
            />

            {/* Vector overlay in swath pixel space -- crisp at any card width.
                `meet` matches object-contain on the image: with `none` the boxes
                stretch to fill the square frame while the swath letterboxes
                inside it, and every box lands off its contact. */}
            <svg
              viewBox={`0 0 ${swathWidth} ${swathHeight}`}
              preserveAspectRatio="xMidYMid meet"
              className="absolute inset-0 h-full w-full"
            >
              {detections.map((d) => {
                const style = severityStyle(d.severity)
                const active = selected?.detection_id === d.detection_id
                return (
                  <g
                    key={d.detection_id}
                    onClick={() => onSelect(d.detection_id)}
                    className="cursor-pointer"
                  >
                    <rect
                      x={d.bbox.x - 6}
                      y={d.bbox.y - 6}
                      width={d.bbox.width + 12}
                      height={d.bbox.height + 12}
                      fill={active ? style.hex : 'transparent'}
                      fillOpacity={active ? 0.16 : 0}
                      stroke={style.hex}
                      strokeWidth={active ? 5 : 2.5}
                      vectorEffect="non-scaling-stroke"
                      rx="3"
                    />
                    {active && (
                      <>
                        <line
                          x1={d.bbox.x + d.bbox.width / 2}
                          y1="0"
                          x2={d.bbox.x + d.bbox.width / 2}
                          y2={swathHeight}
                          stroke={style.hex}
                          strokeWidth="1"
                          strokeDasharray="6 8"
                          strokeOpacity="0.5"
                          vectorEffect="non-scaling-stroke"
                        />
                        <line
                          x1="0"
                          y1={d.bbox.y + d.bbox.height / 2}
                          x2={swathWidth}
                          y2={d.bbox.y + d.bbox.height / 2}
                          stroke={style.hex}
                          strokeWidth="1"
                          strokeDasharray="6 8"
                          strokeOpacity="0.5"
                          vectorEffect="non-scaling-stroke"
                        />
                      </>
                    )}
                  </g>
                )
              })}
              {/* Nadir: the towfish track down the centre of the swath. */}
              <line
                x1={swathWidth / 2}
                y1="0"
                x2={swathWidth / 2}
                y2={swathHeight}
                stroke="#00B4D8"
                strokeWidth="1"
                strokeDasharray="3 6"
                strokeOpacity="0.45"
                vectorEffect="non-scaling-stroke"
              />
            </svg>

            {cursor && (
              <span
                className="pointer-events-none absolute z-10 h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full border border-aqua bg-aqua/25"
                style={{ left: `${cursor.left}%`, top: `${cursor.top}%` }}
              />
            )}

            <figcaption className="pointer-events-none absolute inset-x-0 bottom-0 flex items-center justify-between bg-gradient-to-t from-navy/90 to-transparent px-3 py-2 font-mono text-2xs text-ink/60">
              <span>
                {metrics.simulated
                  ? 'CV fallback · unvalidated'
                  : `${metrics.model_name} · trained weights`}
              </span>
              <span>hover to solve any pixel →</span>
            </figcaption>
          </figure>
        )}
      </div>

      {/* --- live pixel -> lat/long solver --- */}
      <div className="mt-5 rounded-2xl bg-teal/70 p-4 ring-1 ring-ink/10">
        <div className="flex items-center justify-between">
          <p className="label text-aqua">Pixel → Lat/Long Solver</p>
          {probe && <span className="label text-ink/35">live probe</span>}
        </div>

        {!readout ? (
          <p className="mt-3 font-serif text-sm text-ink/45">
            Run detection, then move the cursor across the swath to resolve any pixel
            to a WGS-84 coordinate in real time.
          </p>
        ) : (
          <>
            {/*
              Across-track range and bearing are derived from the SWATH itself
              -- sonar altitude, slant range, nadir position -- so they hold for
              an image. Latitude and longitude additionally need the vessel's
              GPS, which an image does not carry, so they are withheld rather
              than shown as a number that looks like a fix.
            */}
            {simulatedNav ? (
              <div className="mt-3 grid grid-cols-2 gap-4">
                <div>
                  <p className="label text-ink/40">Across track</p>
                  <p className="mt-1 font-mono text-lg font-semibold tabular-nums text-aqua">
                    {readout.across_track_m.toFixed(1)} m
                  </p>
                  <p className="font-mono text-2xs text-ink/40">
                    {readout.across_track_m < 0 ? 'port' : 'starboard'}
                  </p>
                </div>
                <div>
                  <p className="label text-ink/40">Position</p>
                  <p className="mt-1 font-mono text-lg font-semibold text-ink/45">
                    not derivable
                  </p>
                  <p className="font-mono text-2xs text-ink/40">no navigation in source</p>
                </div>
              </div>
            ) : (
              <div className="mt-3 grid grid-cols-2 gap-4">
                <div>
                  <p className="label text-ink/40">Latitude</p>
                  <p className="mt-1 font-mono text-lg font-semibold tabular-nums text-aqua">
                    {readout.latitude.toFixed(6)}°
                  </p>
                  <p className="font-mono text-2xs text-ink/40">{toDMS(readout.latitude, 'lat')}</p>
                </div>
                <div>
                  <p className="label text-ink/40">Longitude</p>
                  <p className="mt-1 font-mono text-lg font-semibold tabular-nums text-aqua">
                    {readout.longitude.toFixed(6)}°
                  </p>
                  <p className="font-mono text-2xs text-ink/40">{toDMS(readout.longitude, 'lon')}</p>
                </div>
              </div>
            )}

            <dl className="mt-3">
              <Row dark label="Ping index" value={readout.ping_index.toLocaleString()} />
              <Row dark label="Slant range" value={`${readout.slant_range_m.toFixed(2)} m`} />
              <Row
                dark
                label="Ground range"
                value={`${readout.ground_range_m.toFixed(2)} m`}
                accent="text-aqua"
              />
              <Row dark label="Towfish altitude" value={`${readout.altitude_m.toFixed(2)} m`} />
              <Row
                dark
                label="Bearing"
                value={`${readout.bearing_deg.toFixed(1)}° ${compass(readout.bearing_deg)}`}
              />
              <Row
                dark
                label="Across-track"
                value={`${readout.across_track_m >= 0 ? '+' : ''}${readout.across_track_m.toFixed(2)} m ${
                  readout.across_track_m >= 0 ? 'stbd' : 'port'
                }`}
              />
              <Row
                dark
                label="Horizontal σ"
                value={`± ${readout.horizontal_uncertainty_m.toFixed(2)} m`}
                accent={readout.horizontal_uncertainty_m < 1 ? 'text-aqua' : 'text-amber'}
              />
            </dl>

            <details className="mt-3 group">
              <summary className="label cursor-pointer list-none text-ink/40 transition-colors hover:text-aqua">
                ▸ Show solve trace
              </summary>
              <pre className="scroll-slim mt-2 max-h-28 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-cream/70 p-3 font-mono text-2xs leading-relaxed text-ink/60">
                {readout.formula}
              </pre>
            </details>
          </>
        )}
      </div>

      {/* --- model telemetry --- */}
      {metrics && (
        <div className="mt-5">
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Stat dark label="Contacts" value={inference.summary.total} accent="text-aqua" />
            <Stat dark label="Latency" value={metrics.total_ms.toFixed(0)} unit="ms" />
            <Stat
              dark
              label="mAP@50"
              value={metrics.map50 != null ? metrics.map50.toFixed(3) : '—'}
              hint={metrics.map50 == null ? 'No validated accuracy for this engine' : metrics.validated_on}
            />
            <Stat dark label="Throughput" value={metrics.fps.toFixed(1)} unit="fps" />
          </div>

          {/* Accuracy is shown only when the engine has a measured validation
              run behind it. An unvalidated engine says so plainly rather than
              displaying a number it cannot support. */}
          {metrics.precision != null ? (
            <>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <div>
                  <div className="flex items-center justify-between">
                    <span className="label text-ink/40">Precision</span>
                    <span className="font-mono text-2xs text-ink/60">
                      {metrics.precision.toFixed(3)}
                    </span>
                  </div>
                  <div className="mt-1.5">
                    <Meter value={metrics.precision} colour="bg-aqua" track="bg-cream/10" />
                  </div>
                </div>
                <div>
                  <div className="flex items-center justify-between">
                    <span className="label text-ink/40">Recall</span>
                    <span className="font-mono text-2xs text-ink/60">
                      {metrics.recall.toFixed(3)}
                    </span>
                  </div>
                  <div className="mt-1.5">
                    <Meter value={metrics.recall} colour="bg-azure" track="bg-cream/10" />
                  </div>
                </div>
              </div>
              {metrics.validated_on && (
                <p className="mt-2 font-serif text-2xs text-ink/40">
                  Measured on {metrics.validated_on}
                </p>
              )}
            </>
          ) : (
            <div className="mt-4 rounded-xl border border-amber/30 bg-amber/10 px-4 py-3">
              <p className="label text-amber">Unvalidated Engine</p>
              <p className="mt-1 font-serif text-xs leading-relaxed text-ink/60">
                No trained weights are loaded, so this run has no measured
                detection accuracy. Contacts are candidates for human review,
                not a validated result.
              </p>
            </div>
          )}

          <dl className="mt-4 rounded-xl bg-cream/5 px-4 py-2">
            <Row dark label="Model" value={`${metrics.model_name} v${metrics.model_version}`} mono={false} />
            <Row dark label="Device" value={metrics.device} />
            <Row dark label="Input" value={`${metrics.input_resolution} · ${metrics.tiles_processed} tiles`} />
            <Row
              dark
              label="Candidates"
              value={`${metrics.raw_candidates} raw → ${metrics.kept_after_nms} kept`}
            />
            <Row dark label="NMS IoU" value={metrics.iou_threshold.toFixed(2)} />
            <Row
              dark
              label="Coverage"
              value={`${inference.summary.area_surveyed_km2.toFixed(4)} km² · ${inference.summary.contacts_per_km2.toFixed(1)}/km²`}
            />
          </dl>

          {selected && (
            <div className="mt-4 rounded-xl bg-cream/5 px-4 py-3 ring-1 ring-ink/10">
              <p className="label text-ink/40">Selected Contact · Acoustic Geometry</p>
              <p className="mt-1 font-display text-base font-semibold text-ink">
                {classLabel(selected.label)}{' '}
                <span className="font-mono text-xs font-normal text-ink/40">
                  {selected.detection_id}
                </span>
              </p>
              <dl className="mt-2">
                <Row dark label="Dimensions (L × W)" value={`${selected.length_m} × ${selected.width_m} m`} />
                <Row dark label="Shadow length" value={`${selected.shadow_length_m} m`} />
                <Row
                  dark
                  label="Height (from shadow)"
                  value={`${selected.height_estimate_m} m`}
                  accent="text-amber"
                />
                <Row dark label="Aspect ratio" value={selected.aspect_ratio.toFixed(2)} />
                <Row dark label="Backscatter" value={`${selected.backscatter_db} dB`} />
              </dl>

              {/*
                Advisory, not a correction. The network judged texture and
                shadow; the swath measured shape. When they disagree the label
                stands and the operator is told, because silently resolving it
                either way throws away one of two independent pieces of
                evidence.
              */}
              {selected.geometry_agrees === false && (
                <div className="mt-3 flex items-start gap-2.5 rounded border border-amber/40 bg-amber/10 px-3 py-2.5">
                  <span className="mt-[3px] h-1.5 w-1.5 shrink-0 rounded-full bg-amber" />
                  <div className="min-w-0">
                    <p className="font-mono text-2xs font-semibold uppercase tracking-label text-amber">
                      Class uncertain · geometry disagrees
                    </p>
                    <p className="mt-1 font-mono text-2xs leading-relaxed text-ink/55">
                      Aspect {selected.aspect_ratio.toFixed(2)} is outside the range for{' '}
                      {classLabel(selected.label).toLowerCase()}. Measured shape fits{' '}
                      <span className="text-ink/80">
                        {classLabel(selected.geometry_suggests).toLowerCase()}
                      </span>{' '}
                      better — worth operator review.
                    </p>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </BentoCard>
  )
}
