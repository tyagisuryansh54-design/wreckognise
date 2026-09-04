/** Shared formatting and design-token lookups for the dashboard. */

/** Severity -> Tailwind classes. The pop colours live here and nowhere else. */
export const SEVERITY_STYLES = {
  critical: {
    label: 'Critical',
    dot: 'bg-coral',
    hex: '#FF6B6B',
    badge: 'bg-coral/15 text-coral border border-coral/30',
    badgeDark: 'bg-coral/20 text-coral border border-coral/35',
    ring: 'ring-coral/45',
  },
  high: {
    label: 'High',
    dot: 'bg-sunset',
    hex: '#FF7A00',
    badge: 'bg-sunset/15 text-sunset border border-sunset/30',
    badgeDark: 'bg-sunset/20 text-sunset border border-sunset/35',
    ring: 'ring-sunset/45',
  },
  medium: {
    label: 'Medium',
    dot: 'bg-amber',
    hex: '#FFB703',
    badge: 'bg-amber/18 text-[#8a6100] border border-amber/40',
    badgeDark: 'bg-amber/20 text-amber border border-amber/35',
    ring: 'ring-amber/45',
  },
  low: {
    label: 'Low',
    dot: 'bg-aqua',
    hex: '#00B4D8',
    badge: 'bg-aqua/15 text-azure border border-aqua/35',
    badgeDark: 'bg-aqua/20 text-aqua border border-aqua/35',
    ring: 'ring-aqua/45',
  },
}

export const severityStyle = (severity) => SEVERITY_STYLES[severity] ?? SEVERITY_STYLES.low

/** Human labels for the detector's class taxonomy. */
export const CLASS_LABELS = {
  shipwreck: 'Shipwreck',
  debris_field: 'Debris Field',
  container: 'Container',
  pipeline: 'Pipeline',
  boulder: 'Boulder',
  uxo: 'Ordnance (UXO)',
  unknown: 'Unclassified',
}

export const classLabel = (value) => CLASS_LABELS[value] ?? 'Unclassified'

export const REVIEW_LABELS = {
  pending: 'Pending',
  flagged: 'Flagged',
  under_review: 'Operator Review',
  confirmed: 'Confirmed',
  dismissed: 'Dismissed',
}

/** Decimal degrees -> DMS, the notation on an actual chart. */
export function toDMS(value, axis) {
  const hemisphere = axis === 'lat' ? (value >= 0 ? 'N' : 'S') : value >= 0 ? 'E' : 'W'
  const absolute = Math.abs(value)
  const degrees = Math.floor(absolute)
  const minutesFloat = (absolute - degrees) * 60
  const minutes = Math.floor(minutesFloat)
  const seconds = ((minutesFloat - minutes) * 60).toFixed(2)
  return `${degrees}° ${String(minutes).padStart(2, '0')}' ${String(seconds).padStart(5, '0')}" ${hemisphere}`
}

export const pct = (value, digits = 1) => `${(value * 100).toFixed(digits)}%`

export const metres = (value, digits = 1) => `${Number(value).toFixed(digits)} m`

export function bytes(value) {
  if (!value) return '—'
  const units = ['B', 'KB', 'MB', 'GB']
  let size = value
  let unit = 0
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024
    unit += 1
  }
  return `${size.toFixed(size >= 100 || unit === 0 ? 0 : 1)} ${units[unit]}`
}

export const clock = (iso) => {
  try {
    return new Date(iso).toISOString().slice(11, 19) + 'Z'
  } catch {
    return '—'
  }
}

/** Compass point for a true bearing, e.g. 247.5 -> WSW. */
export function compass(bearing) {
  const points = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
    'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
  return points[Math.round(((bearing % 360) / 22.5)) % 16]
}

/** Trigger a client-side file download from an in-memory string. */
export function downloadText(filename, text, mime = 'text/plain') {
  const url = URL.createObjectURL(new Blob([text], { type: mime }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}
