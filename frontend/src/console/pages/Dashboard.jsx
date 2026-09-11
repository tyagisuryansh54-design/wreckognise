/**
 * Analytics workspace: run a survey, filter the contacts, inspect one.
 *
 * Contacts come from the real pipeline, so the grid is empty until a scan has
 * run. An "empty" state that quietly shows fabricated rows is worse than a
 * blank table: it looks like the system is working when nothing has happened.
 */

import { useEffect, useMemo, useState } from 'react'
import { Filter, Play, RefreshCw, Upload } from 'lucide-react'
import { AsciiMeter, Button, Modal, Panel, Stat } from '../primitives'
import { api, assetUrl } from '../../utils/api'

const CLASS_LABEL = {
  shipwreck: 'Shipwreck',
  aircraft: 'Aircraft Fuselage',
  sar_contact: 'SAR Contact',
  container: 'Cargo Container',
  ghost_net: 'Ghost Net',
  anchor_debris: 'Anchor & Chain',
  debris_field: 'Debris Field',
  pipeline: 'Subsea Pipeline',
  boulder: 'Boulder',
  uxo: 'Ordnance (UXO)',
  unknown: 'Unclassified',
}

/**
 * Display order only. The set of filters actually offered is derived from the
 * response -- hardcoding it hid every `critical` contact behind a filter the
 * UI never rendered, which is the worst kind of bug on a triage screen: the
 * table looked empty rather than filtered.
 */
const SEVERITY_ORDER = ['critical', 'high', 'medium', 'low']

export default function Dashboard() {
  const [survey, setSurvey] = useState(null)
  const [inference, setInference] = useState(null)
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState(null)
  const [active, setActive] = useState(null)   // null = nothing filtered yet
  const [selected, setSelected] = useState(null)
  const [samples, setSamples] = useState([])

  useEffect(() => {
    api.samples().then((r) => setSamples(r?.samples ?? [])).catch(() => setSamples([]))
  }, [])

  async function runScan(filename) {
    setBusy('scan')
    setError(null)
    try {
      const ing = filename ? await api.loadSample(filename) : await api.loadDemo('nlm')
      setSurvey(ing)
      setInference(null)
      const inf = await api.detect(ing.survey_id)
      setInference(inf)
      // Every severity the run actually produced starts enabled.
      setActive(new Set(inf.detections.map((d) => d.severity)))
    } catch (err) {
      setError(err?.message ?? String(err))
    } finally {
      setBusy(null)
    }
  }

  const toggle = (s) =>
    setActive((prev) => {
      const next = new Set(prev ?? present)
      if (next.has(s)) next.delete(s)
      else next.add(s)
      return next
    })

  const present = useMemo(() => {
    const found = new Set((inference?.detections ?? []).map((d) => d.severity))
    const known = SEVERITY_ORDER.filter((s) => found.has(s))
    // Anything the backend adds later still gets a filter chip rather than
    // vanishing from the table.
    const extra = [...found].filter((s) => !SEVERITY_ORDER.includes(s))
    return [...known, ...extra]
  }, [inference])

  const rows = useMemo(
    () => (inference?.detections ?? []).filter((d) => !active || active.has(d.severity)),
    [inference, active],
  )

  const summary = inference?.summary

  return (
    <div className="mx-auto max-w-7xl px-5 py-10 lg:px-10">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="mono text-xl tracking-[0.2em] text-[var(--ink)]">WORKSPACE</h1>
          <p className="mt-2 max-w-xl text-sm text-[var(--ink-dim)]">
            Ingest a swath, sweep it with the detector, and triage what comes back.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="primary" onClick={() => runScan()} disabled={busy === 'scan'}>
            {busy === 'scan' ? (
              <RefreshCw className="h-3.5 w-3.5 animate-spin" strokeWidth={1.5} />
            ) : (
              <Play className="h-3.5 w-3.5" strokeWidth={1.5} />
            )}
            {busy === 'scan' ? 'RUNNING' : 'RUN DEMO SCAN'}
          </Button>
        </div>
      </div>

      {error && (
        <div className="con-rise mb-5 border border-[rgba(255,107,107,0.4)] bg-[rgba(255,107,107,0.07)] px-4 py-3">
          <p className="mono text-[10px] tracking-[0.2em] text-[var(--coral)]">PIPELINE ERROR</p>
          <p className="mt-1 text-sm text-[var(--ink-dim)]">{error}</p>
        </div>
      )}

      {/* --- stat cards --- */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Panel title="PINGS">
          <Stat label="DECODED" value={survey ? survey.metadata.ping_count.toLocaleString() : '--'} />
        </Panel>
        <Panel title="COVERAGE">
          <Stat
            label="AREA"
            value={summary ? summary.area_surveyed_km2.toFixed(4) : '--'}
            unit={summary ? 'km²' : ''}
          />
        </Panel>
        <Panel title="CONTACTS">
          <Stat
            label="TOTAL"
            value={summary ? summary.total : '--'}
            tone={summary?.total ? 'var(--cyan)' : undefined}
          />
        </Panel>
        <Panel title="PEAK CONF">
          <Stat
            label="HIGHEST"
            value={summary ? `${(summary.highest_confidence * 100).toFixed(0)}%` : '--'}
          />
        </Panel>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* --- contact grid --- */}
        <Panel
          title="CONTACT REGISTER"
          meta={`${rows.length}/${inference?.detections.length ?? 0}`}
          className="lg:col-span-2"
        >
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <Filter className="h-3 w-3 text-[var(--ink-dim)]" strokeWidth={1.5} />
            {present.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => toggle(s)}
                aria-pressed={!active || active.has(s)}
                className={`mono con-btn border px-2.5 py-1 text-[9px] tracking-[0.18em] transition-colors ${
                  !active || active.has(s)
                    ? 'border-[rgba(0,214,255,0.5)] bg-[var(--cyan-soft)] text-[var(--cyan)]'
                    : 'border-[var(--edge)] text-[var(--ink-dim)] hover:text-[var(--ink)]'
                }`}
              >
                {s.toUpperCase()}
              </button>
            ))}
          </div>

          {!inference ? (
            <p className="mono py-10 text-center text-[11px] text-[var(--ink-dim)]">
              no survey loaded &mdash; run a scan to populate the register
            </p>
          ) : rows.length === 0 ? (
            <p className="mono py-10 text-center text-[11px] text-[var(--ink-dim)]">
              every contact filtered out
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="mono w-full min-w-[560px] text-left text-[11px]">
                <thead>
                  <tr className="border-b border-[var(--edge)] text-[9px] tracking-[0.2em] text-[var(--ink-dim)]">
                    <th className="py-2 pr-3 font-normal">ID</th>
                    <th className="py-2 pr-3 font-normal">CLASS</th>
                    <th className="py-2 pr-3 font-normal">CONF</th>
                    <th className="py-2 pr-3 font-normal">LAT</th>
                    <th className="py-2 pr-3 font-normal">LON</th>
                    <th className="py-2 font-normal">±m</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((d) => (
                    <tr
                      key={d.detection_id}
                      onClick={() => setSelected(d)}
                      className="cursor-pointer border-b border-[var(--edge)] transition-colors hover:bg-[var(--cyan-soft)]"
                    >
                      <td className="py-2 pr-3 text-[var(--ink-dim)]">{d.detection_id}</td>
                      <td className="py-2 pr-3 text-[var(--ink)]">
                        {CLASS_LABEL[d.label] ?? d.label}
                      </td>
                      <td className="py-2 pr-3">
                        <span className="flex items-center gap-2">
                          <AsciiMeter value={d.confidence} width={8} />
                          <span className="tabular-nums text-[var(--ink-dim)]">
                            {(d.confidence * 100).toFixed(0)}%
                          </span>
                        </span>
                      </td>
                      <td className="py-2 pr-3 tabular-nums text-[var(--ink-dim)]">
                        {d.geo.latitude.toFixed(5)}
                      </td>
                      <td className="py-2 pr-3 tabular-nums text-[var(--ink-dim)]">
                        {d.geo.longitude.toFixed(5)}
                      </td>
                      <td className="py-2 tabular-nums text-[var(--ink-dim)]">
                        {d.geo.horizontal_uncertainty_m.toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        {/* --- class distribution + sample picker --- */}
        <div className="flex flex-col gap-4">
          <Panel title="CLASS DISTRIBUTION">
            {!summary ? (
              <p className="mono text-[11px] text-[var(--ink-dim)]">awaiting detection</p>
            ) : (
              <ul className="space-y-2.5">
                {Object.entries(summary.by_class)
                  .sort((a, b) => b[1] - a[1])
                  .map(([name, count]) => (
                    <li key={name}>
                      <div className="mono flex items-baseline justify-between text-[10px]">
                        <span className="text-[var(--ink)]">{CLASS_LABEL[name] ?? name}</span>
                        <span className="tabular-nums text-[var(--ink-dim)]">{count}</span>
                      </div>
                      <div className="mt-1">
                        <AsciiMeter value={count / Math.max(summary.total, 1)} width={22} />
                      </div>
                    </li>
                  ))}
              </ul>
            )}
          </Panel>

          <Panel title="CAPTURES" meta={`${samples.length}`}>
            {samples.length === 0 ? (
              <p className="mono text-[11px] text-[var(--ink-dim)]">none bundled</p>
            ) : (
              <ul className="space-y-1.5">
                {samples.map((s) => {
                  const name = s.filename ?? String(s)
                  return (
                    <li key={name}>
                      <button
                        type="button"
                        disabled={busy === 'scan'}
                        onClick={() => runScan(name)}
                        className="mono con-btn flex w-full items-center gap-2 border border-[var(--edge)] px-2.5 py-2 text-left text-[10px] text-[var(--ink-dim)] transition-colors hover:border-[var(--edge-hot)] hover:text-[var(--cyan)] disabled:opacity-40"
                      >
                        <Upload className="h-3 w-3 shrink-0" strokeWidth={1.5} />
                        <span className="truncate">{name}</span>
                      </button>
                    </li>
                  )
                })}
              </ul>
            )}
          </Panel>
        </div>
      </div>

      {/* --- contact inspector --- */}
      <Modal
        open={Boolean(selected)}
        onClose={() => setSelected(null)}
        title={selected ? `CONTACT ${selected.detection_id}` : ''}
        footer={
          <Button variant="ghost" onClick={() => setSelected(null)}>
            CLOSE
          </Button>
        }
      >
        {selected && (
          <div className="mono space-y-2 text-[11px]">
            {[
              ['class', CLASS_LABEL[selected.label] ?? selected.label],
              ['confidence', `${(selected.confidence * 100).toFixed(1)}%`],
              ['severity', selected.severity],
              ['latitude', selected.geo.latitude.toFixed(6)],
              ['longitude', selected.geo.longitude.toFixed(6)],
              ['slant range', `${selected.geo.slant_range_m.toFixed(2)} m`],
              ['ground range', `${selected.geo.ground_range_m.toFixed(2)} m`],
              ['uncertainty', `± ${selected.geo.horizontal_uncertainty_m.toFixed(2)} m`],
            ].map(([k, v]) => (
              <div key={k} className="flex justify-between gap-4 border-b border-[var(--edge)] pb-1.5">
                <span className="text-[var(--ink-dim)]">{k}</span>
                <span className="text-[var(--ink)]">{v}</span>
              </div>
            ))}
            {survey?.annotated_image && (
              <img
                src={assetUrl(survey.annotated_image)}
                alt="Annotated swath"
                className="mt-3 w-full border border-[var(--edge)]"
              />
            )}
          </div>
        )}
      </Modal>
    </div>
  )
}
