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
import { BentoCard, CardHeader, EmptyState } from './Primitives'
import { IconLayers } from './Icons'
import { assetUrl } from '../utils/api'

const STRIDE = 3          // sample every Nth pixel; 1 would be ~1M points
const Z_SCALE = 14        // metres of relief at full backscatter, for legibility

/** Terminal-green ramp, dark seabed through to a lit return. */
function ramp(t) {
  // t 0..1 -> deep teal to bright accent green
  return [0.02 + 0.08 * t, 0.18 + 0.82 * t, 0.12 + 0.25 * t]
}

export default function ReliefView({ ingest, detections = [] }) {
  const mountRef = useRef(null)
  const [status, setStatus] = useState('idle')
  const [points, setPoints] = useState(0)

  const meta = ingest?.metadata
  const src = ingest?.filtered_waterfall_png

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

      const positions = []
      const colours = []
      for (let row = 0; row < h; row += STRIDE) {
        for (let col = 0; col < w; col += STRIDE) {
          const intensity = data[(row * w + col) * 4] / 255
          if (intensity < 0.06) continue          // water column and dead shadow

          // Slant range from the nadir gap outward, then corrected to ground
          // range -- the same solve the georeferencer does per contact.
          const slant = (Math.abs(col - nadir) / nadir) * halfSwath
          const ground = Math.sqrt(Math.max(0, slant * slant - altitude * altitude))
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

    image.onerror = () => setStatus('error')
    image.src = assetUrl(src)

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
  }, [src, meta, detections])

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
          {status === 'error' && (
            <p className="mt-2 font-mono text-2xs text-coral">could not load the waterfall</p>
          )}

          <dl className="mt-3 grid grid-cols-3 gap-3 border-t border-ink/10 pt-3">
            <div>
              <p className="label text-ink/40">X · across track</p>
              <p className="font-mono text-2xs text-ink/70">
                ground range, slant-corrected
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
