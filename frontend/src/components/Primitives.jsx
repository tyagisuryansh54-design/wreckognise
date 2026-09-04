/** Shared building blocks for the bento grid. */

export function BentoCard({
  as: Tag = 'section',
  tone = 'light',
  className = '',
  children,
  ...rest
}) {
  const tones = {
    light: 'bento-light',
    dark: 'bento-dark',
    teal: 'bento-teal',
  }
  return (
    <Tag className={`${tones[tone] ?? tones.light} ${className}`} {...rest}>
      {children}
    </Tag>
  )
}

export function CardHeader({ eyebrow, title, meta, dark = false, action }) {
  return (
    <header className="flex items-start justify-between gap-4">
      <div className="min-w-0">
        {eyebrow && (
          <p className={`label ${dark ? 'text-aqua' : 'text-azure'}`}>{eyebrow}</p>
        )}
        <h2
          className={`mt-1.5 font-display text-xl font-semibold leading-tight md:text-2xl ${
            dark ? 'text-cream' : 'text-navy'
          }`}
        >
          {title}
        </h2>
        {meta && (
          <p
            className={`mt-1 font-serif text-sm ${
              dark ? 'text-cream/55' : 'text-navy/55'
            }`}
          >
            {meta}
          </p>
        )}
      </div>
      {action}
    </header>
  )
}

/** A labelled figure. `dark` flips it for navy/teal grounds. */
export function Stat({ label, value, unit, dark = false, accent, hint }) {
  return (
    <div className="min-w-0">
      <p className={`label ${dark ? 'text-cream/40' : 'text-navy/40'}`}>{label}</p>
      <p
        className={`stat mt-1 truncate ${accent ?? (dark ? 'text-cream' : 'text-navy')}`}
        title={hint ?? `${value}${unit ? ` ${unit}` : ''}`}
      >
        {value}
        {unit && (
          <span
            className={`ml-1 font-mono text-xs font-medium ${
              dark ? 'text-cream/40' : 'text-navy/40'
            }`}
          >
            {unit}
          </span>
        )}
      </p>
    </div>
  )
}

/** Key/value row used in the metadata and telemetry readouts. */
export function Row({ label, value, mono = true, dark = false, accent }) {
  return (
    <div
      className={`flex items-baseline justify-between gap-3 border-b py-1.5 last:border-0 ${
        dark ? 'border-cream/8' : 'border-navy/8'
      }`}
    >
      <span
        className={`shrink-0 font-sans text-xs ${dark ? 'text-cream/45' : 'text-navy/50'}`}
      >
        {label}
      </span>
      <span
        className={`truncate text-right text-xs font-medium ${
          mono ? 'font-mono tabular-nums' : 'font-sans'
        } ${accent ?? (dark ? 'text-cream/90' : 'text-navy')}`}
        title={String(value)}
      >
        {value}
      </span>
    </div>
  )
}

export function Badge({ className = '', children, pulse = false }) {
  return (
    <span className={`badge ${className}`}>
      {pulse && (
        <span className="relative flex h-1.5 w-1.5">
          <span className="absolute inline-flex h-full w-full animate-pulse-ring rounded-full bg-current" />
          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-current" />
        </span>
      )}
      {children}
    </span>
  )
}

/** Horizontal meter used for confidence, coverage and class distribution. */
export function Meter({ value, max = 1, colour = 'bg-aqua', track = 'bg-navy/10', height = 'h-1.5' }) {
  const width = Math.max(0, Math.min(100, (value / max) * 100))
  return (
    <div className={`w-full overflow-hidden rounded-full ${track} ${height}`}>
      <div
        className={`${height} rounded-full ${colour} transition-[width] duration-700 ease-out`}
        style={{ width: `${width}%` }}
      />
    </div>
  )
}

export function EmptyState({ icon, title, body, action, dark = false }) {
  return (
    <div className="flex h-full flex-col items-center justify-center px-6 py-10 text-center">
      <div
        className={`mb-3 grid h-11 w-11 place-items-center rounded-full ${
          dark ? 'bg-cream/8 text-aqua' : 'bg-navy/5 text-azure'
        }`}
      >
        {icon}
      </div>
      <p
        className={`font-display text-base font-semibold ${
          dark ? 'text-cream/85' : 'text-navy/85'
        }`}
      >
        {title}
      </p>
      <p
        className={`mt-1 max-w-xs font-serif text-sm ${
          dark ? 'text-cream/45' : 'text-navy/50'
        }`}
      >
        {body}
      </p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

/** Thin indeterminate-looking bar shown while a pipeline stage runs. */
export function ProgressBar({ value, dark = false }) {
  if (!value) return null
  return (
    <div
      className={`fixed inset-x-0 top-0 z-50 h-0.5 ${dark ? 'bg-cream/10' : 'bg-navy/8'}`}
      role="progressbar"
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div
        className="h-full bg-gradient-to-r from-azure to-aqua transition-[width] duration-300 ease-out"
        style={{ width: `${value}%` }}
      />
    </div>
  )
}

export function Spinner({ className = 'h-3.5 w-3.5' }) {
  return (
    <svg className={`${className} animate-spin`} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
      <path
        d="M21 12a9 9 0 0 0-9-9"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
      />
    </svg>
  )
}
