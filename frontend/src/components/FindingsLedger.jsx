import { useEffect, useMemo, useState } from 'react'
import { BentoCard, CardHeader, EmptyState, Meter } from './Primitives'
import { IconLayers, IconAlert } from './Icons'
import { api } from '../utils/api'
import { severityStyle } from '../utils/format'

const POLL_MS = 5000

/**
 * Bento box 06 -- the live findings ledger.
 *
 * Every survey the server analyses appends its catalogued anomalies here, so
 * this shows findings across every scan rather than only the survey currently
 * open. It polls rather than pushes: at five seconds the freshness is
 * indistinguishable from a socket, and it survives the backend restarting
 * without a reconnect dance.
 */
export default function FindingsLedger({ refreshKey }) {
  const [data, setData] = useState(null)
  const [category, setCategory] = useState('all')
  const [error, setError] = useState(false)

  useEffect(() => {
    let alive = true
    const load = () =>
      api
        .findings()
        .then((r) => {
          if (!alive) return
          setData(r)
          setError(false)
        })
        .catch(() => alive && setError(true))

    load()
    const timer = setInterval(load, POLL_MS)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [refreshKey])

  const categories = useMemo(
    () => ['all', ...Object.keys(data?.by_category ?? {}).sort()],
    [data],
  )

  const rows = useMemo(() => {
    const all = data?.findings ?? []
    return category === 'all' ? all : all.filter((f) => f.category === category)
  }, [data, category])

  return (
    <BentoCard tone="light" className="flex flex-col p-6">
      <CardHeader
        eyebrow="06 · Ocean Findings Ledger"
        title="Everything catalogued so far"
        meta={
          data
            ? `${data.total} finding${data.total === 1 ? '' : 's'} across all analysed surveys · live`
            : 'Waiting for the first analysed survey'
        }
        action={
          <span className="hidden shrink-0 rounded-full bg-navy/5 p-2.5 text-azure sm:block">
            <IconLayers className="h-5 w-5" />
          </span>
        }
      />

      {categories.length > 1 && (
        <div className="mt-4 flex flex-wrap gap-1.5">
          {categories.map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => setCategory(c)}
              aria-pressed={category === c}
              className={`rounded-full px-3 py-1.5 font-mono text-2xs font-semibold uppercase tracking-wide transition-colors ${
                category === c
                  ? 'bg-navy text-cream'
                  : 'bg-sand text-navy/55 hover:text-navy'
              }`}
            >
              {c === 'all' ? 'All' : c}
              <span className={category === c ? 'ml-1.5 text-aqua' : 'ml-1.5 text-navy/35'}>
                {c === 'all' ? data?.total ?? 0 : data?.by_category?.[c] ?? 0}
              </span>
            </button>
          ))}
        </div>
      )}

      <div className="scroll-slim mt-4 max-h-[22rem] flex-1 space-y-2 overflow-y-auto pr-1">
        {rows.length === 0 ? (
          <div className="h-40">
            <EmptyState
              icon={error ? <IconAlert className="h-5 w-5" /> : <IconLayers className="h-5 w-5" />}
              title={error ? 'Ledger unavailable' : 'No findings recorded yet'}
              body={
                error
                  ? 'The API is not reachable, so the live ledger cannot update.'
                  : 'Analyse a survey and every catalogued anomaly is appended here automatically.'
              }
            />
          </div>
        ) : (
          rows.map((f) => {
            const style = severityStyle(f.severity)
            return (
              <article
                key={f.finding_id}
                className="rounded-xl border border-navy/10 bg-white/70 px-3.5 py-3"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className={`h-2 w-2 shrink-0 rounded-full ${style.dot}`} />
                      <p className="truncate font-display text-sm font-semibold text-navy">
                        {f.display_name}
                      </p>
                    </div>
                    <p className="mt-0.5 truncate font-mono text-2xs text-navy/40">
                      {f.finding_id} · {f.category} · {f.source_file}
                    </p>
                  </div>
                  <p className="shrink-0 font-mono text-sm font-semibold tabular-nums text-azure">
                    {(f.confidence * 100).toFixed(1)}%
                  </p>
                </div>

                <div className="mt-2.5 grid grid-cols-2 gap-3">
                  <div>
                    <p className="label text-navy/35">Model confidence</p>
                    <div className="mt-1">
                      <Meter value={f.confidence} colour="bg-azure" height="h-1" />
                    </div>
                  </div>
                  <div>
                    {/* Kept separate from confidence on purpose: a model can be
                        sure of a class and still have found something the wrong
                        size to be one. */}
                    <p className="label text-navy/35">Size plausibility</p>
                    <div className="mt-1">
                      <Meter
                        value={f.size_plausibility}
                        colour={f.size_plausibility >= 0.6 ? 'bg-aqua' : 'bg-amber'}
                        height="h-1"
                      />
                    </div>
                  </div>
                </div>

                <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-2xs text-navy/50">
                  <span className="tabular-nums">
                    {f.latitude.toFixed(5)}, {f.longitude.toFixed(5)}
                  </span>
                  <span className="text-navy/25">·</span>
                  <span>
                    {f.length_m}×{f.width_m} m
                  </span>
                  <span className="text-navy/25">·</span>
                  <span>±{f.horizontal_uncertainty_m.toFixed(2)} m</span>
                </div>

                {f.severity === 'critical' && (
                  <p className="mt-2 rounded-lg bg-coral/8 px-2.5 py-1.5 font-serif text-2xs leading-relaxed text-coral">
                    {f.operational_note}
                  </p>
                )}
              </article>
            )
          })
        )}
      </div>
    </BentoCard>
  )
}
