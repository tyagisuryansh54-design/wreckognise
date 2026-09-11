/**
 * Console navigation: desktop rail, a dropdown, and a mobile drawer.
 *
 * Routes are real (react-router NavLink), so the active state comes from the
 * URL rather than from a local state variable that can drift out of step with
 * where the user actually is.
 */

import { useEffect, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { ChevronDown, Menu, Radar, X } from 'lucide-react'
import { TelemetryStrip } from './primitives'

const ROUTES = [
  { to: '/', label: 'HOME', end: true },
  { to: '/dashboard', label: 'DASHBOARD' },
  { to: '/sandbox', label: 'SANDBOX' },
]

const RESOURCES = [
  { label: 'API DOCS', href: 'https://wreckognise-api.onrender.com/docs' },
  { label: 'REPOSITORY', href: 'https://github.com/tyagisuryansh54-design/wreckognise' },
  { label: 'HEALTH JSON', href: 'https://wreckognise-api.onrender.com/api/health' },
]

const linkClass = ({ isActive }) =>
  `mono text-[10px] tracking-[0.24em] transition-colors ${
    isActive ? 'text-[var(--cyan)] con-glow-soft' : 'text-[var(--ink-dim)] hover:text-[var(--ink)]'
  }`

export default function Navigation({ telemetry, fps }) {
  const [drawer, setDrawer] = useState(false)
  const [menu, setMenu] = useState(false)
  const location = useLocation()

  // Navigating must close the drawer, or the new page renders behind it.
  useEffect(() => {
    setDrawer(false)
    setMenu(false)
  }, [location.pathname])

  useEffect(() => {
    if (!drawer) return
    const onKey = (e) => e.key === 'Escape' && setDrawer(false)
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [drawer])

  return (
    <header className="relative z-40 border-b border-[var(--edge)] bg-[var(--obsidian)]/80 backdrop-blur">
      <nav className="mx-auto flex max-w-7xl items-center justify-between px-5 py-3.5 lg:px-10">
        <NavLink to="/" className="flex items-center gap-3">
          <Radar className="h-4 w-4 text-[var(--cyan)]" strokeWidth={1.5} />
          <span className="mono text-sm font-semibold tracking-[0.3em] text-[var(--ink)]">
            WRECKOGNISE
          </span>
        </NavLink>

        <div className="hidden items-center gap-8 lg:flex">
          {ROUTES.map((r) => (
            <NavLink key={r.to} to={r.to} end={r.end} className={linkClass}>
              {r.label}
            </NavLink>
          ))}

          <div className="relative">
            <button
              type="button"
              onClick={() => setMenu((m) => !m)}
              aria-expanded={menu}
              aria-haspopup="menu"
              className="mono flex items-center gap-1.5 text-[10px] tracking-[0.24em] text-[var(--ink-dim)] transition-colors hover:text-[var(--ink)]"
            >
              RESOURCES
              <ChevronDown
                className={`h-3 w-3 transition-transform ${menu ? 'rotate-180' : ''}`}
                strokeWidth={1.5}
              />
            </button>

            {menu && (
              <>
                {/* Click-away layer: a dropdown that only closes via its own
                    button strands the user if they click elsewhere. */}
                <div className="fixed inset-0 z-10" onClick={() => setMenu(false)} />
                <div
                  role="menu"
                  className="con-rise absolute right-0 z-20 mt-3 w-52 border border-[var(--edge-hot)] bg-[var(--panel)] shadow-[0_0_40px_-12px_rgba(0,214,255,0.5)]"
                >
                  {RESOURCES.map((item) => (
                    <a
                      key={item.label}
                      role="menuitem"
                      href={item.href}
                      target="_blank"
                      rel="noreferrer"
                      className="mono block border-b border-[var(--edge)] px-4 py-2.5 text-[10px] tracking-[0.2em] text-[var(--ink-dim)] transition-colors last:border-0 hover:bg-[var(--cyan-soft)] hover:text-[var(--cyan)]"
                    >
                      {item.label}
                    </a>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>

        <div className="flex items-center gap-4">
          <TelemetryStrip telemetry={telemetry} fps={fps} className="hidden md:flex" />
          <button
            type="button"
            onClick={() => setDrawer(true)}
            aria-label="Open menu"
            className="text-[var(--ink-dim)] transition-colors hover:text-[var(--cyan)] lg:hidden"
          >
            <Menu className="h-5 w-5" strokeWidth={1.5} />
          </button>
        </div>
      </nav>

      {/* --- mobile drawer --- */}
      {drawer && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div
            className="absolute inset-0 bg-black/80 backdrop-blur-sm"
            onClick={() => setDrawer(false)}
            aria-hidden="true"
          />
          <aside
            className="con-rise absolute right-0 top-0 flex h-full w-72 flex-col border-l border-[var(--edge-hot)] bg-[var(--panel)]"
            role="dialog"
            aria-modal="true"
            aria-label="Navigation"
          >
            <div className="flex items-center justify-between border-b border-[var(--edge)] px-5 py-4">
              <span className="mono text-[10px] tracking-[0.24em] text-[var(--ink-dim)]">
                NAVIGATION
              </span>
              <button
                type="button"
                onClick={() => setDrawer(false)}
                aria-label="Close menu"
                className="text-[var(--ink-dim)] transition-colors hover:text-[var(--cyan)]"
              >
                <X className="h-4 w-4" strokeWidth={1.5} />
              </button>
            </div>

            <div className="flex flex-col">
              {ROUTES.map((r) => (
                <NavLink
                  key={r.to}
                  to={r.to}
                  end={r.end}
                  className={({ isActive }) =>
                    `mono border-b border-[var(--edge)] px-5 py-4 text-[11px] tracking-[0.24em] transition-colors ${
                      isActive
                        ? 'bg-[var(--cyan-soft)] text-[var(--cyan)]'
                        : 'text-[var(--ink-dim)] hover:text-[var(--ink)]'
                    }`
                  }
                >
                  {r.label}
                </NavLink>
              ))}
              {RESOURCES.map((item) => (
                <a
                  key={item.label}
                  href={item.href}
                  target="_blank"
                  rel="noreferrer"
                  className="mono border-b border-[var(--edge)] px-5 py-4 text-[11px] tracking-[0.24em] text-[var(--ink-dim)] transition-colors hover:text-[var(--ink)]"
                >
                  {item.label} &nearr;
                </a>
              ))}
            </div>

            <div className="mt-auto border-t border-[var(--edge)] px-5 py-4">
              <TelemetryStrip telemetry={telemetry} fps={fps} />
            </div>
          </aside>
        </div>
      )}
    </header>
  )
}
