/**
 * Shared console surfaces: panels, buttons, meters, telemetry, modal.
 *
 * Telemetry reports measured values, not decorative ones. Latency is a real
 * round trip to /api/health and FPS is a real requestAnimationFrame count --
 * a status bar that invents its numbers is a lie rendered in monospace, and on
 * a page whose whole claim is instrumentation it is the wrong lie to tell.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { X } from 'lucide-react'
import { api } from '../utils/api'

/* ------------------------------------------------------------------ panel */

export function Panel({ title, meta, children, className = '', ...rest }) {
  return (
    <section
      className={`con-edge relative bg-[var(--panel)]/70 backdrop-blur-sm ${className}`}
      {...rest}
    >
      {(title || meta) && (
        <header className="flex items-center justify-between border-b border-[var(--edge)] px-4 py-2.5">
          <h2 className="mono text-[10px] tracking-[0.24em] text-[var(--ink)]">{title}</h2>
          {meta && (
            <span className="mono text-[9px] tracking-[0.2em] text-[var(--ink-dim)]">{meta}</span>
          )}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  )
}

/* ----------------------------------------------------------------- button */

export function Button({ as = 'button', variant = 'ghost', className = '', children, ...rest }) {
  const Tag = as
  const base =
    'con-edge con-btn mono inline-flex items-center justify-center gap-2 px-4 py-2.5 ' +
    'text-[11px] tracking-[0.12em] transition-colors disabled:cursor-not-allowed disabled:opacity-40'
  const tone =
    variant === 'primary'
      ? 'border-[rgba(0,214,255,0.5)] bg-[var(--cyan-soft)] text-[var(--cyan)] hover:bg-[var(--cyan)] hover:text-[var(--obsidian)]'
      : variant === 'danger'
        ? 'border-[rgba(255,107,107,0.45)] text-[var(--coral)] hover:bg-[var(--coral)] hover:text-[var(--obsidian)]'
        : 'text-[var(--ink-dim)] hover:text-[var(--ink)]'
  return (
    <Tag className={`${base} ${tone} ${className}`} {...rest}>
      {children}
    </Tag>
  )
}

/* ------------------------------------------------------------------ meter */

/** ASCII meter. A bar drawn in glyphs reads as instrumentation, not chrome. */
export function AsciiMeter({ value = 0, width = 18, tone = 'var(--cyan)' }) {
  const filled = Math.max(0, Math.min(width, Math.round(value * width)))
  return (
    <span className="mono text-[11px]" style={{ color: tone }}>
      [{'█'.repeat(filled)}
      <span style={{ color: 'rgba(107,127,147,0.4)' }}>{'░'.repeat(width - filled)}</span>]
    </span>
  )
}

export function Stat({ label, value, unit, tone }) {
  return (
    <div>
      <p className="mono text-[9px] tracking-[0.22em] text-[var(--ink-dim)]">{label}</p>
      <p className="mono mt-1 text-lg tabular-nums" style={{ color: tone || 'var(--ink)' }}>
        {value}
        {unit && <span className="ml-1 text-[10px] text-[var(--ink-dim)]">{unit}</span>}
      </p>
    </div>
  )
}

/* -------------------------------------------------------------- telemetry */

/**
 * Live link state. Polls health, timing the round trip.
 *
 * The interval is long: the hosted backend suspends when idle and a cold boot
 * takes ~45s, so a chatty status bar would both mask that and keep the free
 * instance awake as a side effect of being looked at.
 */
export function useTelemetry(pollMs = 30000) {
  const [state, setState] = useState({ status: 'boot', latency: null, engine: null })

  const ping = useCallback(async () => {
    const t0 = performance.now()
    try {
      const body = await api.health()
      const ok = body && typeof body === 'object' && body.status
      setState({
        status: ok ? 'online' : 'degraded',
        latency: Math.round(performance.now() - t0),
        engine: body?.detection_engine ?? null,
      })
    } catch {
      setState({ status: 'offline', latency: null, engine: null })
    }
  }, [])

  useEffect(() => {
    ping()
    const id = setInterval(ping, pollMs)
    return () => clearInterval(id)
  }, [ping, pollMs])

  return { ...state, refresh: ping }
}

/**
 * Measured frame rate, sampled once a second.
 *
 * Returns 'off' rather than null when motion is reduced: there is nothing
 * animating to measure, and a readout stuck on `--` looks like a broken gauge
 * rather than a deliberate one.
 */
export function useFps() {
  const [fps, setFps] = useState(null)
  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setFps('off')
      return
    }
    let frames = 0
    let last = performance.now()
    let raf = 0
    const tick = (t) => {
      frames += 1
      if (t - last >= 1000) {
        setFps(Math.round((frames * 1000) / (t - last)))
        frames = 0
        last = t
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [])
  return fps
}

const TONE = {
  online: 'var(--cyan)',
  boot: 'var(--amber)',
  degraded: 'var(--amber)',
  offline: 'var(--coral)',
}

export function StatusDot({ status }) {
  const colour = TONE[status] ?? 'var(--ink-dim)'
  return (
    <span className="relative inline-flex h-2 w-2 shrink-0">
      <span
        className="absolute inset-0 rounded-full"
        style={{ background: colour, animation: 'con-pulse-ring 2.2s ease-out infinite' }}
      />
      <span className="relative inline-flex h-2 w-2 rounded-full" style={{ background: colour }} />
    </span>
  )
}

export function TelemetryStrip({ telemetry, fps, className = '' }) {
  const { status, latency, engine } = telemetry
  return (
    <div
      className={`mono flex flex-wrap items-center gap-x-5 gap-y-1 text-[9px] tracking-[0.2em] text-[var(--ink-dim)] ${className}`}
    >
      <span className="flex items-center gap-2">
        <StatusDot status={status} />
        <span style={{ color: TONE[status] }}>[SYS_{status.toUpperCase()}]</span>
      </span>
      <span className="tabular-nums">
        LAT {latency == null ? '--' : latency}
        <span className="opacity-60">ms</span>
      </span>
      <span className="tabular-nums">
        FPS {fps == null ? '--' : fps}
      </span>
      {engine && <span className="hidden sm:inline">ENG {engine.toUpperCase()}</span>}
    </div>
  )
}

/* ------------------------------------------------------------------ modal */

export function Modal({ open, onClose, title, children, footer }) {
  const ref = useRef(null)

  // Escape closes, and focus moves into the dialog. A modal you cannot dismiss
  // from the keyboard is a trap for anyone not using a mouse.
  useEffect(() => {
    if (!open) return
    const onKey = (e) => e.key === 'Escape' && onClose?.()
    document.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    ref.current?.focus()
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prev
    }
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-black/80 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className="con-rise relative w-full max-w-lg border border-[var(--edge-hot)] bg-[var(--panel)] shadow-[0_0_60px_-15px_rgba(0,214,255,0.5)] outline-none"
      >
        <header className="flex items-center justify-between border-b border-[var(--edge)] px-4 py-3">
          <h2 className="mono text-[11px] tracking-[0.24em] text-[var(--ink)]">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="text-[var(--ink-dim)] transition-colors hover:text-[var(--cyan)]"
          >
            <X className="h-4 w-4" strokeWidth={1.5} />
          </button>
        </header>
        <div className="px-4 py-4 text-sm text-[var(--ink-dim)]">{children}</div>
        {footer && (
          <footer className="flex justify-end gap-2 border-t border-[var(--edge)] px-4 py-3">
            {footer}
          </footer>
        )}
      </div>
    </div>
  )
}
