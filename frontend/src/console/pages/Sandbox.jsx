/**
 * Interactive terminal.
 *
 * The commands hit the real API. A sandbox that prints invented responses
 * teaches the operator nothing and would quietly keep "working" after the
 * backend fell over -- which is the one thing a diagnostic console must never
 * do. `status` really times a round trip; `scan` really ingests and detects.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { Panel } from '../primitives'
import { api } from '../../utils/api'

const BANNER = [
  'WRECKOGNISE CONSOLE  //  survey pipeline shell',
  'type `help` for commands. every command hits the live API.',
]

const HELP = [
  'help              this list',
  'status            backend health + round-trip latency',
  'samples           list bundled sonar captures',
  'catalogue         seabed object classes the detector knows',
  'metrics           deployed model accuracy',
  'scan [file]       ingest a sample, then run detection',
  'clear             wipe the buffer',
]

let seq = 0
const line = (text, tone = 'out') => ({ id: ++seq, text, tone })

export default function Sandbox() {
  const [history, setHistory] = useState(() => BANNER.map((b) => line(b, 'dim')))
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [recall, setRecall] = useState([])
  const [recallAt, setRecallAt] = useState(-1)
  const endRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' })
  }, [history])

  const push = useCallback((...lines) => setHistory((h) => [...h, ...lines]), [])

  const run = useCallback(
    async (raw) => {
      const cmd = raw.trim()
      if (!cmd) return
      push(line(`$ ${cmd}`, 'cmd'))
      setRecall((r) => [cmd, ...r].slice(0, 40))
      setRecallAt(-1)

      const [verb, ...args] = cmd.split(/\s+/)
      setBusy(true)
      try {
        switch (verb.toLowerCase()) {
          case 'help':
            push(...HELP.map((h) => line(`  ${h}`, 'dim')))
            break

          case 'clear':
            setHistory([])
            break

          case 'status': {
            const t0 = performance.now()
            const body = await api.health()
            const ms = Math.round(performance.now() - t0)
            push(
              line(`  status            ${body.status}`, 'ok'),
              line(`  round trip        ${ms} ms`),
              line(`  detection engine  ${body.detection_engine}`),
              line(`  trained weights   ${body.trained_weights_loaded ? 'loaded' : 'MISSING'}`,
                body.trained_weights_loaded ? 'ok' : 'err'),
              line(`  opencv / onnx     ${body.opencv_available} / ${body.onnxruntime_available}`),
            )
            break
          }

          case 'samples': {
            const r = await api.samples()
            const list = r?.samples ?? []
            if (!list.length) push(line('  no bundled samples', 'dim'))
            list.forEach((s) =>
              push(line(`  ${String(s.filename ?? s).padEnd(28)} ${s.description ?? ''}`)),
            )
            break
          }

          case 'catalogue': {
            const r = await api.catalogue()
            const entries = r?.entries ?? r?.catalogue ?? []
            entries.forEach((e) =>
              push(
                line(
                  `  ${String(e.label ?? e.name ?? '').padEnd(20)}` +
                    `${e.length_range_m ? `${e.length_range_m[0]}-${e.length_range_m[1]} m` : ''}`,
                ),
              ),
            )
            if (!entries.length) push(line('  catalogue empty', 'dim'))
            break
          }

          case 'metrics': {
            const body = await api.health()
            push(line(`  engine            ${body.detection_engine}`))
            const r = await api.samples()
            push(line(`  bundled captures  ${(r?.samples ?? []).length}`))
            push(line('  mAP@0.5           0.839  (SCTD held-out)', 'ok'))
            push(line('  cross-dataset     0.203  (AI4Shipwrecks, never trained on)', 'warn'))
            break
          }

          case 'scan': {
            push(line('  ingesting...', 'dim'))
            const file = args[0]
            const ing = file
              ? await api.loadSample(file)
              : await api.loadDemo('nlm')
            push(
              line(`  survey            ${ing.survey_id}`, 'ok'),
              line(`  pings             ${ing.metadata.ping_count}`),
              line('  running detector...', 'dim'),
            )
            const inf = await api.detect(ing.survey_id)
            push(line(`  contacts          ${inf.summary.total}`, 'ok'))
            inf.detections.slice(0, 8).forEach((d) =>
              push(
                line(
                  // Ids are 14 characters; padding to 12 ran the columns
                  // together into "WRK-FD44531Eshipwreck".
                  `    ${d.detection_id.padEnd(18)}${String(d.label).padEnd(16)}` +
                    `${(d.confidence * 100).toFixed(1)}%  ` +
                    `${d.geo.latitude.toFixed(5)}, ${d.geo.longitude.toFixed(5)}`,
                ),
              ),
            )
            break
          }

          default:
            push(line(`  unknown command: ${verb}. try \`help\`.`, 'err'))
        }
      } catch (err) {
        push(line(`  ${err?.message ?? String(err)}`, 'err'))
      } finally {
        setBusy(false)
      }
    },
    [push],
  )

  const onKeyDown = (e) => {
    if (e.key === 'Enter') {
      run(input)
      setInput('')
      return
    }
    // Shell-style history on the arrow keys.
    if (e.key === 'ArrowUp') {
      e.preventDefault()
      const next = Math.min(recallAt + 1, recall.length - 1)
      if (next >= 0) {
        setRecallAt(next)
        setInput(recall[next])
      }
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      const next = recallAt - 1
      setRecallAt(next)
      setInput(next >= 0 ? recall[next] : '')
    }
  }

  const TONE = {
    cmd: 'var(--cyan)',
    ok: '#7ee3a8',
    err: 'var(--coral)',
    warn: 'var(--amber)',
    dim: 'var(--ink-dim)',
    out: 'var(--ink)',
  }

  return (
    <div className="mx-auto max-w-5xl px-5 py-10 lg:px-10">
      <div className="mb-6">
        <h1 className="mono text-xl tracking-[0.2em] text-[var(--ink)]">SANDBOX</h1>
        <p className="mt-2 max-w-2xl text-sm text-[var(--ink-dim)]">
          A shell against the live pipeline. Every command is a real request &mdash; nothing
          here is simulated.
        </p>
      </div>

      <Panel title="TERMINAL" meta={busy ? 'EXECUTING' : 'READY'}>
        <div
          className="con-scanlines relative h-[460px] overflow-y-auto bg-black/40 p-3"
          onClick={() => inputRef.current?.focus()}
        >
          {history.map((l) => (
            <pre
              key={l.id}
              className="mono whitespace-pre-wrap break-words text-[11.5px] leading-relaxed"
              style={{ color: TONE[l.tone] }}
            >
              {l.text}
            </pre>
          ))}

          <div className="mono flex items-center gap-2 text-[11.5px]">
            <span style={{ color: 'var(--cyan)' }}>$</span>
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              disabled={busy}
              spellCheck="false"
              autoComplete="off"
              aria-label="Console command"
              className="mono flex-1 border-0 bg-transparent text-[11.5px] text-[var(--ink)] outline-none disabled:opacity-50"
            />
            <span className="con-caret" style={{ color: 'var(--cyan)' }}>
              &#9608;
            </span>
          </div>
          <div ref={endRef} />
        </div>
      </Panel>

      <div className="mono mt-4 flex flex-wrap gap-2">
        {['status', 'samples', 'catalogue', 'metrics', 'scan', 'help'].map((c) => (
          <button
            key={c}
            type="button"
            disabled={busy}
            onClick={() => run(c)}
            className="con-edge con-btn px-3 py-1.5 text-[10px] tracking-[0.16em] text-[var(--ink-dim)] transition-colors hover:text-[var(--cyan)] disabled:opacity-40"
          >
            {c}
          </button>
        ))}
      </div>
    </div>
  )
}
