import { useEffect, useMemo, useState } from 'react'
import {
  Circle,
  MapContainer,
  Marker,
  Polyline,
  Popup,
  TileLayer,
  useMap,
} from 'react-leaflet'
import L from 'leaflet'
import { BentoCard, CardHeader, EmptyState } from './Primitives'
import { IconMap } from './Icons'
import { classLabel, severityStyle, toDMS } from '../utils/format'

/** Warning pin, built as a divIcon so it inherits the severity pop colour. */
function contactIcon(severity, active) {
  const { hex } = severityStyle(severity)
  const size = active ? 38 : 30
  return L.divIcon({
    className: 'contact-pin',
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    html: `
      <div style="position:relative;width:${size}px;height:${size}px">
        ${
          active
            ? `<span style="position:absolute;inset:0;border-radius:50%;background:${hex};opacity:.28;animation:pulseRing 2.2s cubic-bezier(.24,.6,.36,1) infinite"></span>`
            : ''
        }
        <span style="position:absolute;inset:0;display:grid;place-items:center;
                     border-radius:50%;background:#0A192F;
                     border:2px solid ${hex};
                     box-shadow:0 0 0 ${active ? 4 : 2}px ${hex}33, 0 6px 14px rgba(0,0,0,.5)">
          <svg width="${size * 0.44}" height="${size * 0.44}" viewBox="0 0 24 24"
               fill="none" stroke="${hex}" stroke-width="2.4"
               stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 5 3 20h18Z"/><path d="M12 10v4M12 17v.4"/>
          </svg>
        </span>
      </div>`,
  })
}

/** Keeps the viewport tracking the active survey and the selected contact. */
function ViewportController({ track, selected, detections }) {
  const map = useMap()

  useEffect(() => {
    if (selected) {
      map.flyTo([selected.geo.latitude, selected.geo.longitude], 17, { duration: 0.8 })
      return
    }
    const points = [
      ...track.map((t) => [t.latitude, t.longitude]),
      ...detections.map((d) => [d.geo.latitude, d.geo.longitude]),
    ]
    if (points.length > 1) {
      map.fitBounds(L.latLngBounds(points).pad(0.25), { animate: true })
    }
  }, [map, selected, track, detections])

  return null
}

/**
 * Basemaps, all keyless.
 *
 * `maxNativeZoom` is the deepest level each service actually has tiles for --
 * Esri's Ocean basemap stops at 16, and asking it for 17 returns a canned
 * "data not available" placeholder rather than a 404. Declaring the real limit
 * makes Leaflet upscale the last good tile instead, so a contact stays legible
 * at survey zoom on every layer.
 */
const BASEMAPS = {
  dark: {
    label: 'Dark',
    url: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
    attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
    maxNativeZoom: 20,
  },
  ocean: {
    label: 'Bathymetry',
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}',
    attribution: 'Esri — GEBCO, NOAA, National Geographic',
    maxNativeZoom: 16,
  },
  satellite: {
    label: 'Satellite',
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attribution: 'Esri — Earthstar Geographics',
    maxNativeZoom: 19,
  },
}

/** Deepest zoom the UI will ever request, across all layers. */
const MAX_ZOOM = 20

/**
 * Bento box 3 -- interactive GIS chart.
 *
 * Every contact carries an uncertainty circle sized from the solver's own
 * error budget, so the map shows where a wreck *is* and how confidently,
 * rather than implying a pin is a point measurement.
 */
export default function MapBox({ telemetry, detections, selected, onSelect }) {
  const [basemap, setBasemap] = useState('dark')
  const [showUncertainty, setShowUncertainty] = useState(true)

  const trackLine = useMemo(
    () => telemetry.map((t) => [t.latitude, t.longitude]),
    [telemetry],
  )

  const centre = useMemo(() => {
    if (trackLine.length) return trackLine[Math.floor(trackLine.length / 2)]
    return [8.926, 78.156]
  }, [trackLine])

  const tiles = BASEMAPS[basemap]

  return (
    <BentoCard tone="light" className="flex flex-col overflow-hidden p-0">
      <div className="p-6 pb-4">
        <CardHeader
          eyebrow="03 · Interactive GIS Chart"
          title="Every contact, fixed to the chart"
          meta="WGS-84 · uncertainty circles from the live error budget"
          action={
            <span className="hidden shrink-0 rounded-full bg-ink/5 p-2.5 text-azure sm:block">
              <IconMap className="h-5 w-5" />
            </span>
          }
        />

        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex gap-1.5 rounded-full bg-sand p-1">
            {Object.entries(BASEMAPS).map(([id, config]) => (
              <button
                key={id}
                type="button"
                onClick={() => setBasemap(id)}
                aria-pressed={basemap === id}
                className={`rounded-full px-3 py-1.5 font-mono text-2xs font-semibold uppercase tracking-wide transition-colors ${
                  basemap === id ? 'bg-navy text-ink' : 'text-ink/50 hover:text-ink'
                }`}
              >
                {config.label}
              </button>
            ))}
          </div>

          <label className="flex cursor-pointer items-center gap-2 font-mono text-2xs uppercase tracking-wide text-ink/50">
            <input
              type="checkbox"
              checked={showUncertainty}
              onChange={(e) => setShowUncertainty(e.target.checked)}
              className="h-3.5 w-3.5 accent-[#0077B6]"
            />
            Error circles
          </label>
        </div>
      </div>

      <div className="relative min-h-[24rem] flex-1">
        {trackLine.length === 0 ? (
          <div className="absolute inset-0 bg-ink/[0.03]">
            <EmptyState
              icon={<IconMap className="h-5 w-5" />}
              title="No survey line plotted"
              body="Ingest a sonar capture to draw the vessel track, then run detection to drop contact pins."
            />
          </div>
        ) : (
          <MapContainer
            center={centre}
            zoom={15}
            maxZoom={MAX_ZOOM}
            scrollWheelZoom
            className="absolute inset-0 h-full w-full"
            attributionControl
          >
            <TileLayer
              key={basemap}
              url={tiles.url}
              attribution={tiles.attribution}
              maxZoom={MAX_ZOOM}
              maxNativeZoom={tiles.maxNativeZoom}
            />

            {/* Vessel track: a wide azure casing under a bright aqua core. */}
            <Polyline positions={trackLine} pathOptions={{ color: '#0077B6', weight: 7, opacity: 0.35 }} />
            <Polyline
              positions={trackLine}
              pathOptions={{ color: '#00B4D8', weight: 2, opacity: 0.95, dashArray: '1 7', lineCap: 'round' }}
            />

            {showUncertainty &&
              detections.map((d) => (
                <Circle
                  key={`u-${d.detection_id}`}
                  center={[d.geo.latitude, d.geo.longitude]}
                  radius={Math.max(d.geo.horizontal_uncertainty_m, 1.5)}
                  pathOptions={{
                    color: severityStyle(d.severity).hex,
                    weight: 1,
                    opacity: 0.55,
                    fillOpacity: 0.1,
                  }}
                />
              ))}

            {detections.map((d) => (
              <Marker
                key={d.detection_id}
                position={[d.geo.latitude, d.geo.longitude]}
                icon={contactIcon(d.severity, selected?.detection_id === d.detection_id)}
                eventHandlers={{ click: () => onSelect(d.detection_id) }}
              >
                <Popup>
                  <p className="font-mono text-[10px] uppercase tracking-label text-[#00B4D8]">
                    {d.detection_id}
                  </p>
                  <p className="mt-1 text-sm font-semibold">{classLabel(d.label)}</p>
                  <p className="mt-1 text-[11px] opacity-70">
                    {toDMS(d.geo.latitude, 'lat')}
                    <br />
                    {toDMS(d.geo.longitude, 'lon')}
                  </p>
                  <p className="mt-2 text-[11px]">
                    <span style={{ color: severityStyle(d.severity).hex }}>
                      {severityStyle(d.severity).label.toUpperCase()}
                    </span>
                    {' · '}
                    {(d.confidence * 100).toFixed(1)}% confidence
                  </p>
                  <p className="mt-1 text-[11px] opacity-70">
                    {d.length_m} × {d.width_m} m · ht {d.height_estimate_m} m · ±
                    {d.geo.horizontal_uncertainty_m.toFixed(2)} m
                  </p>
                </Popup>
              </Marker>
            ))}

            <ViewportController track={telemetry} selected={selected} detections={detections} />
          </MapContainer>
        )}

        {/* Legend floats over the chart rather than stealing card height. */}
        {detections.length > 0 && (
          <div className="pointer-events-none absolute bottom-4 left-4 z-[1000] rounded-xl bg-cream/88 px-3.5 py-2.5 backdrop-blur">
            <p className="label text-ink/40">Severity</p>
            <ul className="mt-1.5 space-y-1">
              {['critical', 'high', 'medium', 'low'].map((severity) => {
                const count = detections.filter((d) => d.severity === severity).length
                if (!count) return null
                const style = severityStyle(severity)
                return (
                  <li key={severity} className="flex items-center gap-2">
                    <span className={`h-2 w-2 rounded-full ${style.dot}`} />
                    <span className="font-mono text-2xs text-ink/70">
                      {style.label}
                      <span className="ml-1.5 text-ink/40">{count}</span>
                    </span>
                  </li>
                )
              })}
            </ul>
          </div>
        )}
      </div>
    </BentoCard>
  )
}
