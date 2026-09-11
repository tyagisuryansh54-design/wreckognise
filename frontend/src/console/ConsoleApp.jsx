/**
 * Shell for the ASCII console: background, navigation, routes, footer.
 *
 * The starfield lives here rather than inside each page so it is mounted once
 * and keeps running across navigation -- remounting the canvas on every route
 * change would reseed the field and the sky would visibly jump.
 */

import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import AtmosphericBackground from './AtmosphericBackground'
import Navigation from './Navigation'
import Home from './pages/Home'
import Dashboard from './pages/Dashboard'
import Sandbox from './pages/Sandbox'
import { TelemetryStrip, useFps, useTelemetry } from './primitives'
import './theme.css'

function Shell() {
  const telemetry = useTelemetry()
  const fps = useFps()
  const { pathname } = useLocation()

  return (
    <div className="console-root relative min-h-screen">
      <AtmosphericBackground className="fixed" />

      {/* Corner brackets, fixed to the viewport so they frame every route. */}
      <div className="pointer-events-none fixed left-3 top-3 z-30 h-8 w-8 border-l border-t border-[var(--edge-hot)] opacity-50 lg:h-12 lg:w-12" />
      <div className="pointer-events-none fixed right-3 top-3 z-30 h-8 w-8 border-r border-t border-[var(--edge-hot)] opacity-50 lg:h-12 lg:w-12" />
      <div className="pointer-events-none fixed bottom-3 left-3 z-30 h-8 w-8 border-b border-l border-[var(--edge-hot)] opacity-50 lg:h-12 lg:w-12" />
      <div className="pointer-events-none fixed bottom-3 right-3 z-30 h-8 w-8 border-b border-r border-[var(--edge-hot)] opacity-50 lg:h-12 lg:w-12" />

      <div className="relative z-10 flex min-h-screen flex-col">
        <Navigation telemetry={telemetry} fps={fps} />

        {/* Keyed so each route animates in rather than swapping instantly. */}
        <main key={pathname} className="con-rise flex-1">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/sandbox" element={<Sandbox />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>

        <footer className="border-t border-[var(--edge)] bg-[var(--obsidian)]/80 backdrop-blur">
          <div className="mx-auto flex max-w-7xl flex-col gap-2 px-5 py-3 sm:flex-row sm:items-center sm:justify-between lg:px-10">
            <TelemetryStrip telemetry={telemetry} fps={fps} />
            <span className="mono text-[9px] tracking-[0.2em] text-[var(--ink-dim)]">
              WGS-84 / EPSG:4326 &middot; SIH 2026
            </span>
          </div>
        </footer>
      </div>
    </div>
  )
}

export default function ConsoleApp() {
  return (
    <BrowserRouter>
      <Shell />
    </BrowserRouter>
  )
}
