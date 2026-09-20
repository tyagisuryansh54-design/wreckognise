/**
 * Acoustic relief: the swath as a rotatable 3D point cloud.
 *
 * WHAT THE AXES ARE, AND WHAT THEY ARE NOT
 *
 * Every axis here is a measured quantity, and Z is deliberately NOT depth:
 *
 *   X  across-track ground range, slant-corrected -- sqrt(slant^2 - alt^2)
 *   Y  along-track distance, from ping index over the line length
 *   Z  backscatter intensity, from the denoised waterfall
 *
 * A multibeam sonar measures depth directly at every point, which is what
 * produces the bathymetric point clouds this resembles. Side-scan does not: it
 * measures how loudly each patch of seabed returned sound. Plotting that as
 * "depth" would be inventing a survey product we never measured, so the panel
 * says backscatter relief and the axis is labelled in dB, not metres.
 *
 * The one place we do derive height is per contact, from shadow geometry --
 * h = (L_shadow * altitude) / (ground_range + L_shadow) -- and those are drawn
 * as markers at their solved positions rather than as a surface.
 */

import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { BentoCard, CardHeader, EmptyState, Spinner } from './Primitives'
import { IconLayers } from './Icons'
import { api, assetUrl } from '../utils/api'

/*
 * Point budget rather than a fixed stride. A bundled demo frame is under a
 * megapixel; a real USGS line arrives at 2048 x 1695 and a phone photo at
 * 4 MP, and a fixed stride of 3 turns those into 400k-plus points with six
 * floats each. The stride is derived per swath so every source lands near the
 * same budget -- the demo keeps its detail and real data stays interactive.
 */
const POINT_BUDGET = 250_000
const Z_SCALE = 14        // metres of relief at full backscatter, for legibility

/** Terminal-green ramp, dark seabed through to a lit return. */
function ramp(t) {
  // t 0..1 -> deep teal to bright accent green
  return [0.02 + 0.08 * t, 0.18 + 0.82 * t, 0.12 + 0.25 * t]
}

export default function ReliefView({ ingest, detections = [], onRecover }) {
  const mountRef = useRef(null)
  const [status, setStatus] = useState('idle')
  const [points, setPoints] = useState(0)
  // One attempt per survey id. Without the guard a recovery that fails for
  // any other reason would retry forever.
  const recoveredFor = useRef(null)

  const meta = ingest?.metadata
  const src = ingest?.filtered_waterfall_png
  // Content key, so a caller handing over a fresh-but-equal array cannot
  // re-run the effect. Identity is not a fact about the data.
  const detectionKey = detections.map((d) => d.detection_id).join(',')

  useEffect(() => {
    if (!src || !meta || !mountRef.current) return
    const mount = mountRef.current
    let disposed = false
    let frame = 0
    setStatus('loading')

    const scene = new THREE.Scene()
    scene.background = new THREE.Color(0x0a0a0a)

    const camera = new THREE.PerspectiveCamera(
      45, mount.clientWidth / mount.clientHeight, 0.1, 5000,
    )
    const renderer = new THREE.WebGLRenderer({ antialias: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setSize(mount.clientWidth, mount.clientHeight)
    mount.appendChild(renderer.domElement)

    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.dampingFactor = 0.08

    const image = new Image()
    // The waterfall is served from the API origin, which is a different host in
    // production. Without this the canvas is tainted and getImageData throws.
    image.crossOrigin = 'anonymous'

    image.onload = () => {
      if (disposed) return
      const { width: w, height: h } = image
      const canvas = document.createElement('canvas')
      canvas.width = w
      canvas.height = h
      const ctx = canvas.getContext('2d', { willReadFrequently: true })
      ctx.drawImage(image, 0, 0)

      let data
      try {
        data = ctx.getImageData(0, 0, w, h).data
      } catch {
        setStatus('tainted')
        return
      }

      const swath = meta.swath_width_m || 200
      const along = meta.line_length_m || 300
      const altitude = meta.mean_altitude_m || 10
      const halfSwath = swath / 2
      const nadir = w / 2

      const stride = Math.max(1, Math.round(Math.sqrt((w * h) / POINT_BUDGET)))

      /*
       * The nadir gap: where the slant range has not yet reached the seabed.
       *
       * Below this the ping is still travelling through water, so there is no
       * bottom return to place and sqrt(slant^2 - alt^2) is zero. Keeping
       * those samples piles them all onto x=0 as a vertical sheet -- and on a
       * real line it is not a minor artefact. The USGS Grand Bay survey flies
       * at 60 m altitude with a 100 m range, so SIXTY PERCENT of every ping is
       * water column, and that sheet was most of what the view rendered.
       *
       * Real side-scan processing discards this region rather than plotting
       * it, which is what the gap down the middle of a waterfall image is.
       */
      const positions = []
      const colours = []
      for (let row = 0; row < h; row += stride) {
        for (let col = 0; col < w; col += stride) {
          const intensity = data[(row * w + col) * 4] / 255
          if (intensity < 0.06) continue          // dead shadow

          // Slant range from the nadir gap outward, then corrected to ground
          // range -- the same solve the georeferencer does per contact.
          const slant = (Math.abs(col - nadir) / nadir) * halfSwath
          if (slant <= altitude) continue         // still in the water column
          const ground = Math.sqrt(slant * slant - altitude * altitude)
          const x = Math.sign(col - nadir) * ground
          const y = (row / h) * along - along / 2
          const z = intensity * Z_SCALE

          positions.push(x, z, y)               // three.js is Y-up
          const [r, g, b] = ramp(intensity)
          colours.push(r, g, b)
        }
      }

      const geometry = new THREE.BufferGeometry()
      geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
      geometry.setAttribute('color', new THREE.Float32BufferAttribute(colours, 3))
      const cloud = new THREE.Points(
        geometry,
        new THREE.PointsMaterial({ size: 0.55, vertexColors: true, sizeAttenuation: true }),
      )
      scene.add(cloud)
      setPoints(positions.length / 3)

      // Contacts, at their solved across/along position. Height here IS derived
      // -- from shadow geometry -- so the marker sits at its estimated height.
      detections.forEach((d) => {
        const marker = new THREE.Mesh(
          new THREE.SphereGeometry(1.4, 12, 12),
          new THREE.MeshBasicMaterial({ color: 0xff5c5c }),
        )
        const across = d.geo?.across_track_m ?? 0
        const alongPos = ((d.bbox.y + d.bbox.height / 2) / h) * along - along / 2
        marker.position.set(across, (d.height_estimate_m || 1) + 2, alongPos)
        scene.add(marker)
      })

      // Ground plane grid, so the relief has something to sit on.
      const grid = new THREE.GridHelper(Math.max(swath, along), 24, 0x1f3a2a, 0x14251c)
      grid.position.y = -0.5
      scene.add(grid)

      camera.position.set(swath * 0.75, swath * 0.5, along * 0.8)
      controls.target.set(0, 0, 0)
      controls.update()
      setStatus('ready')

      const tick = () => {
        if (disposed) return
        frame = requestAnimationFrame(tick)
        controls.update()
        renderer.render(scene, camera)
      }
      tick()
    }

    /*
     * Work out WHICH failure this is before reporting it. A processed frame
     * lives on an ephemeral disk behind a signed URL, so it goes away when the
     * instance sleeps -- and then the page is holding a survey the server no
     * longer has. That is a different message, and a different action, from a
     * genuinely broken image.
     */
    image.onerror = () => {
      setStatus('error')
      if (!ingest?.survey_id) return
      api.surveyExists(ingest.survey_id).then((exists) => {
        if (disposed || exists) return
        setStatus('expired')
        // Rebuild it rather than asking the operator to. The call that made
        // this survey is replayable, so the honest recovery is to replay it.
        if (!onRecover || recoveredFor.current === ingest.survey_id) return
        recoveredFor.current = ingest.survey_id
        setStatus('recovering')

        /*
         * The result is checked, and that is the whole point.
         *
         * useSurvey.run() catches everything and resolves to null, so a replay
         * that fails -- a cold start past the timeout, a 429 from the ingest
         * throttle, a 503 mid-deploy -- never calls setIngest. Nothing changes,
         * this effect never re-runs, and the "rebuilding…" line stays on screen
         * for good. Fire-and-forget turned a recoverable failure into a
         * permanent one.
         */
        Promise.resolve(onRecover()).then(
          (rebuilt) => {
            if (disposed || rebuilt) return   // success re-runs the effect
            recoveredFor.current = null       // let the operator try again
            setStatus('expired')
          },
          () => {
            if (disposed) return
            recoveredFor.current = null
            setStatus('expired')
          },
        )
      })
    }
    /*
     * A distinct URL from the one the <img> tags use, on purpose.
     *
     * The ingest panel loads this exact file in a plain <img> -- no Origin,
     * so the reply carries no Access-Control-Allow-Origin -- and the browser
     * caches that reply. This request is CORS-mode (crossOrigin above), and
     * given the same URL Chrome serves it from that cache, finds no ACAO on
     * the cached copy, and fails it as a CORS error. The server sends Vary:
     * Origin to prevent exactly that, but a CDN or proxy between here and it
     * may not honour Vary, and the cost of a second fetch is nothing next to
     * a blank panel. The signature covers filename and expiry only, so the
     * extra parameter does not invalidate it.
     */
    const separator = src.includes('?') ? '&' : '?'
    image.src = assetUrl(`${src}${separator}mode=cors`)

    const onResize = () => {
      if (!mount.clientWidth) return
      camera.aspect = mount.clientWidth / mount.clientHeight
      camera.updateProjectionMatrix()
      renderer.setSize(mount.clientWidth, mount.clientHeight)
    }
    const observer = new ResizeObserver(onResize)
    observer.observe(mount)

    return () => {
      disposed = true
      cancelAnimationFrame(frame)
      observer.disconnect()
      controls.dispose()
      renderer.dispose()
      // WebGL contexts are a limited resource; a component that mounts and
      // unmounts without releasing them takes the whole page down after a
      // dozen cycles.
      scene.traverse((o) => {
        o.geometry?.dispose?.()
        o.material?.dispose?.()
      })
      if (renderer.domElement.parentNode === mount) mount.removeChild(renderer.domElement)
    }
  }, [src, meta, detectionKey]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <BentoCard tone="light" className="flex flex-col p-6">
      <CardHeader
        eyebrow="04 · Acoustic Relief"
        title="Backscatter surface, rotatable"
        meta={points ? `${points.toLocaleString()} points` : '3D'}
      />

      {!ingest ? (
        <div className="mt-4 h-80 rounded border border-ink/10 bg-cream/50">
          <EmptyState
            icon={<IconLayers className="h-5 w-5" />}
            title="No swath loaded"
            body="Ingest a survey line to build the acoustic relief surface."
          />
        </div>
      ) : (
        <>
          <div
            ref={mountRef}
            className="mt-4 h-80 w-full cursor-grab overflow-hidden rounded border border-ink/10 active:cursor-grabbing sm:h-96"
          />
          {status === 'tainted' && (
            <p className="mt-2 font-mono text-2xs text-coral">
              waterfall blocked by cross-origin policy — relief unavailable
            </p>
          )}
          {status === 'recovering' && (
            <p className="mt-2 flex items-center gap-2 font-mono text-2xs text-azure">
              <Spinner className="h-3 w-3" />
              the server no longer had this survey — rebuilding it. A sleeping
              instance can take up to a minute to answer.
            </p>
          )}

          {/* Both failure states are recoverable by hand, so both offer the
              control rather than describing what the operator should go and
              do somewhere else. */}
          {(status === 'expired' || status === 'error') && (
            <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5">
              <p
                className={`font-mono text-2xs ${
                  status === 'expired' ? 'text-amber' : 'text-coral'
                }`}
              >
                {status === 'expired'
                  ? 'the server no longer has this survey and the rebuild did not complete'
                  : 'could not load the waterfall — the survey is still on the server, so this is the image request failing'}
              </p>
              {onRecover && (
                <button
                  type="button"
                  onClick={() => {
                    recoveredFor.current = null
                    setStatus('recovering')
                    Promise.resolve(onRecover()).then(
                      (r) => !r && setStatus('expired'),
                      () => setStatus('expired'),
                    )
                  }}
                  className="btn-ghost !px-2.5 !py-1 !text-2xs"
                >
                  Rebuild
                </button>
              )}
            </div>
          )}

          <dl className="mt-3 grid grid-cols-3 gap-3 border-t border-ink/10 pt-3">
            <div>
              <p className="label text-ink/40">X · across track</p>
              <p className="font-mono text-2xs text-ink/70">
                {meta
                  ? `ground range · ${Math.round(
                      Math.min(0.95, (meta.mean_altitude_m || 10) / ((meta.swath_width_m || 200) / 2)) * 100,
                    )}% nadir gap removed`
                  : 'ground range, slant-corrected'}
              </p>
            </div>
            <div>
              <p className="label text-ink/40">Y · along track</p>
              <p className="font-mono text-2xs text-ink/70">
                {meta ? `${meta.line_length_m.toFixed(0)} m line` : '—'}
              </p>
            </div>
            <div>
              <p className="label text-ink/40">Z · relief</p>
              <p className="font-mono text-2xs text-ink/70">backscatter, not depth</p>
            </div>
          </dl>

          <p className="mt-3 font-serif text-xs leading-relaxed text-ink/45">
            Side-scan measures how loudly the seabed returns sound, not its depth — a
            multibeam sonar would be needed for true bathymetry. Height here is
            backscatter intensity; the red markers are contacts at their shadow-derived
            heights. Drag to rotate, scroll to zoom.
          </p>
        </>
      )}
    </BentoCard>
  )
}
