/** Inline stroke icons -- no icon-font dependency, all inherit currentColor. */

const base = {
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.6,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
  'aria-hidden': 'true',
}

const Svg = ({ children, className = 'h-4 w-4', viewBox = '0 0 24 24' }) => (
  <svg className={className} viewBox={viewBox} {...base}>
    {children}
  </svg>
)

export const IconSonar = (p) => (
  <Svg {...p}>
    <path d="M12 20a8 8 0 0 0-8-8" />
    <path d="M12 20a12 12 0 0 0-12-12" opacity="0.55" />
    <path d="M12 20a4 4 0 0 0-4-4" />
    <circle cx="12" cy="20" r="1.2" fill="currentColor" stroke="none" />
  </Svg>
)

export const IconUpload = (p) => (
  <Svg {...p}>
    <path d="M12 16V4" />
    <path d="m7.5 8.5 4.5-4.5 4.5 4.5" />
    <path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
  </Svg>
)

export const IconScan = (p) => (
  <Svg {...p}>
    <path d="M4 8V6a2 2 0 0 1 2-2h2" />
    <path d="M16 4h2a2 2 0 0 1 2 2v2" />
    <path d="M20 16v2a2 2 0 0 1-2 2h-2" />
    <path d="M8 20H6a2 2 0 0 1-2-2v-2" />
    <path d="M4 12h16" />
  </Svg>
)

export const IconTarget = (p) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="8" />
    <circle cx="12" cy="12" r="3.4" />
    <path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22" />
  </Svg>
)

export const IconMap = (p) => (
  <Svg {...p}>
    <path d="m9 3 6 3 5.2-2.1a.5.5 0 0 1 .8.4v14.3l-6 2.4-6-3-5.2 2.1a.5.5 0 0 1-.8-.4V5.4Z" />
    <path d="M9 3v15M15 6v15" />
  </Svg>
)

export const IconReport = (p) => (
  <Svg {...p}>
    <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8Z" />
    <path d="M14 3v5h5" />
    <path d="M9 13h6M9 17h4" />
  </Svg>
)

export const IconFlag = (p) => (
  <Svg {...p}>
    <path d="M5 21V4" />
    <path d="M5 4h11l-1.6 3.5L16 11H5" />
  </Svg>
)

export const IconCheck = (p) => (
  <Svg {...p}>
    <path d="m4.5 12.5 5 5 10-11" />
  </Svg>
)

export const IconX = (p) => (
  <Svg {...p}>
    <path d="m6 6 12 12M18 6 6 18" />
  </Svg>
)

export const IconEye = (p) => (
  <Svg {...p}>
    <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z" />
    <circle cx="12" cy="12" r="3" />
  </Svg>
)

export const IconAlert = (p) => (
  <Svg {...p}>
    <path d="M12 4.5 2.8 20h18.4Z" />
    <path d="M12 10v4.2M12 17.2v.4" />
  </Svg>
)

export const IconSatellite = (p) => (
  <Svg {...p}>
    <path d="m7 15-4 4 2 2 4-4" />
    <path d="m9.5 12.5 2 2" />
    <path d="M13.5 3.5 20.5 10.5 15 16 8 9Z" />
    <path d="M16 19a5 5 0 0 0 5-5" />
  </Svg>
)

export const IconWave = (p) => (
  <Svg {...p}>
    <path d="M2 9c2.2 0 2.2 2.5 4.4 2.5S8.6 9 10.8 9 13 11.5 15.2 11.5 17.4 9 19.6 9 21.8 11.5 22 11.5" />
    <path d="M2 15.5c2.2 0 2.2 2.5 4.4 2.5s2.2-2.5 4.4-2.5 2.2 2.5 4.4 2.5 2.2-2.5 4.4-2.5 2.2 2.5 2.4 2.5" opacity="0.5" />
  </Svg>
)

export const IconDownload = (p) => (
  <Svg {...p}>
    <path d="M12 4v11" />
    <path d="m7.5 10.5 4.5 4.5 4.5-4.5" />
    <path d="M4 19h16" />
  </Svg>
)

export const IconLayers = (p) => (
  <Svg {...p}>
    <path d="m12 3 9 5-9 5-9-5Z" />
    <path d="m3 13 9 5 9-5" />
  </Svg>
)

export const IconShield = (p) => (
  <Svg {...p}>
    <path d="M12 3 5 6v6c0 4.2 2.9 7.6 7 9 4.1-1.4 7-4.8 7-9V6Z" />
    <path d="m9 12 2 2 4-4" />
  </Svg>
)

export const IconChip = (p) => (
  <Svg {...p}>
    <rect x="7" y="7" width="10" height="10" rx="1.6" />
    <path d="M10 3v4M14 3v4M10 17v4M14 17v4M3 10h4M3 14h4M17 10h4M17 14h4" />
  </Svg>
)

export const IconMenu = (p) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" {...p}>
    <path d="M4 7h16M4 12h16M4 17h16" strokeLinecap="round" />
  </svg>
)

export const IconArrowRight = (p) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" {...p}>
    <path d="M5 12h14M13 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
)
