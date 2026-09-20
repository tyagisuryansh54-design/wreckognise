import { useCallback, useEffect, useRef, useState } from 'react'
import { IconCheck, IconCopy } from './Icons'

/**
 * Copy an operational value to the clipboard.
 *
 * Two rules, both learned from what this data is used for.
 *
 * `value` is the payload, never the rendered text. On-screen positions are
 * truncated to five or six decimals, or formatted as DMS; a chart plotter,
 * QGIS or an ECDIS wants full-precision decimal degrees. Copying what is
 * displayed would quietly round a fix before it reached the system that
 * plots it.
 *
 * Failure is reported, never silent. navigator.clipboard exists only in a
 * secure context, so an http:// LAN deployment -- a survey vessel's onboard
 * network is exactly that -- falls back to the textarea trick, and if both
 * fail the button says so rather than pretending.
 */

async function write(text) {
  if (navigator.clipboard?.writeText && window.isSecureContext) {
    await navigator.clipboard.writeText(text)
    return true
  }

  // Deprecated but still the only thing that works off a secure origin. The
  // previously focused element is restored afterwards: ta.select() moves
  // focus, and without this a keyboard operator who pressed Enter on Copy
  // would find their next Tab restarting at the top of the document.
  const previous = document.activeElement
  const ta = document.createElement('textarea')
  ta.value = text
  ta.setAttribute('readonly', '')
  ta.style.cssText = 'position:fixed;top:-9999px;opacity:0'
  document.body.appendChild(ta)
  ta.select()
  let ok = false
  try {
    ok = document.execCommand('copy')
  } catch {
    ok = false
  }
  ta.remove()
  if (previous instanceof HTMLElement) previous.focus({ preventScroll: true })
  return ok
}

export default function CopyButton({
  value,
  label = 'Copy',
  srLabel,
  title,
  iconOnly = false,
  className = '',
}) {
  const [state, setState] = useState('idle')
  const timer = useRef(null)

  // Cleared on unmount: MapBox popups and the register rows unmount freely,
  // and a timeout firing into a dead component is a React warning at best.
  useEffect(() => () => clearTimeout(timer.current), [])

  const onCopy = useCallback(
    async (event) => {
      // These buttons sit inside clickable rows and Leaflet popups; without
      // this, copying also selects a contact or pans the chart.
      event.stopPropagation()
      event.preventDefault()
      clearTimeout(timer.current)
      let ok = false
      try {
        ok = await write(String(value))
      } catch {
        ok = false
      }
      setState(ok ? 'copied' : 'error')
      timer.current = setTimeout(() => setState('idle'), 1600)
    },
    [value],
  )

  const copied = state === 'copied'
  const failed = state === 'error'

  return (
    <button
      type="button"
      onClick={onCopy}
      title={title || `Copy ${srLabel || label}`}
      aria-label={srLabel ? `Copy ${srLabel}` : label}
      className={`inline-flex shrink-0 items-center gap-1.5 rounded-bento px-1.5 py-1 font-mono text-2xs transition-colors ${
        copied
          ? 'text-azure'
          : failed
            ? 'text-coral'
            : 'text-ink/35 hover:text-ink/75'
      } ${className}`}
    >
      {copied ? <IconCheck className="h-3 w-3" /> : <IconCopy className="h-3 w-3" />}
      {!iconOnly && <span>{copied ? 'Copied' : failed ? 'Copy failed' : label}</span>}
      {/*
        Icon-only buttons still have to announce the outcome. aria-live on a
        visually hidden span is the only thing a screen-reader user gets --
        the colour change is invisible to them.
      */}
      <span className="sr-only" aria-live="polite">
        {copied ? 'Copied to clipboard' : failed ? 'Copy failed' : ''}
      </span>
    </button>
  )
}
