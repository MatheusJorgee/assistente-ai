'use client'

/**
 * HoloGlobe — globo holográfico em Three.js (e mapa plano, como alternativa/fallback).
 *
 * - Textura: canvas equirretangular desenhado por d3-geo (holoTexture.ts).
 * - Renderização SOB DEMANDA: o laço de animação só roda enquanto algo se move (voo até o
 *   lugar, pulso do pin, arraste com inércia) e para sozinho; em repouso não gasta GPU.
 * - Cleanup idempotente (StrictMode monta/desmonta/monta): cancela rAF, libera geometrias,
 *   materiais, textura e o contexto WebGL, remove listeners.
 * - Reduced-motion: sem voo nem pulso, o globo já abre no lugar.
 * - Ganchos de teste: data-holo-state ('loading' | 'ready' | 'flat' | 'error'), data-holo-lat/lon.
 */

import { useCallback, useEffect, useRef } from 'react'
import {
  AdditiveBlending, BackSide, CanvasTexture, Color, DoubleSide, Group, Mesh, MeshBasicMaterial,
  PerspectiveCamera, Quaternion, RingGeometry, Scene, ShaderMaterial, SphereGeometry, Vector3,
  WebGLRenderer, SRGBColorSpace,
} from 'three'
import type { HoloPayload } from '@/types'
import { clampPitch, latLonToVec3 } from '@/lib/holo'
import { desenharMapa } from './holoTexture'

interface HoloGlobeProps {
  geo: HoloPayload['geo']
  plano: boolean
  reduzirMovimento: boolean
  /** WebGL indisponível: o pai troca para o mapa plano. */
  onSemWebGL: () => void
}

const TEX_W = 2048
const TEX_H = 1024
const RAD = Math.PI / 180

/** Guinada (yaw) e inclinação (pitch), em rad, que trazem lat/lon para o centro da tela. */
function alvoDe(lat: number, lon: number): { yaw: number; pitch: number } {
  const [x, y, z] = latLonToVec3(lat, lon)
  const yaw = Math.atan2(-x, z)
  const z1 = Math.hypot(x, z)
  const pitch = Math.atan2(y, z1)
  return { yaw, pitch }
}

const angDiff = (a: number, b: number) => {
  let d = (b - a) % (2 * Math.PI)
  if (d > Math.PI) d -= 2 * Math.PI
  if (d < -Math.PI) d += 2 * Math.PI
  return d
}

export function HoloGlobe({ geo, plano, reduzirMovimento, onSemWebGL }: HoloGlobeProps) {
  const raizRef = useRef<HTMLDivElement>(null)
  // Estado exposto como atributo (gancho de teste e de estilo): direto no DOM, sem re-render.
  const marcar = useCallback((estado: 'loading' | 'ready' | 'flat' | 'error') => {
    if (raizRef.current) raizRef.current.dataset.holoState = estado
  }, [])
  const boxRef = useRef<HTMLDivElement>(null)
  const canvasPlanoRef = useRef<HTMLCanvasElement>(null)

  // ------------------------------------------------------------ mapa plano
  useEffect(() => {
    if (!plano) return
    const c = canvasPlanoRef.current
    if (!c) return
    try {
      desenharMapa(c, geo)
      marcar('flat')
    } catch {
      marcar('error')
    }
  }, [plano, geo, marcar])

  // ------------------------------------------------------------ globo
  useEffect(() => {
    if (plano) return
    const box = boxRef.current
    if (!box) return

    let renderer: WebGLRenderer | null = null
    try {
      renderer = new WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'low-power' })
    } catch {
      marcar('error')
      onSemWebGL()
      return
    }
    let disposed = false
    let raf = 0
    let ativoAte = 0
    let arrastando = false
    let ultimoFrame = 0

    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5))
    renderer.setClearColor(0x000000, 0)
    renderer.outputColorSpace = SRGBColorSpace
    const canvas = renderer.domElement
    canvas.style.display = 'block'
    canvas.style.touchAction = 'none'
    canvas.style.cursor = 'grab'
    box.appendChild(canvas)

    const scene = new Scene()
    const camera = new PerspectiveCamera(35, 1, 0.1, 20)
    camera.position.set(0, 0, 4.2)

    const globo = new Group()
    scene.add(globo)

    // textura do mapa
    const texCanvas = document.createElement('canvas')
    texCanvas.width = TEX_W
    texCanvas.height = TEX_H
    try {
      desenharMapa(texCanvas, geo)
    } catch {
      /* segue com textura vazia: o pin ainda mostra o lugar */
    }
    const textura = new CanvasTexture(texCanvas)
    textura.colorSpace = SRGBColorSpace
    textura.anisotropy = 4

    const geoEsfera = new SphereGeometry(1, 64, 48)
    const miolo = new Mesh(geoEsfera, new MeshBasicMaterial({ color: new Color('#031017'), transparent: true, opacity: 0.82 }))
    miolo.scale.setScalar(0.996)
    const casca = new Mesh(geoEsfera, new MeshBasicMaterial({ map: textura, transparent: true, blending: AdditiveBlending, depthWrite: false }))
    globo.add(miolo, casca)

    // halo (fresnel) atrás do globo
    const halo = new Mesh(
      new SphereGeometry(1.14, 48, 32),
      new ShaderMaterial({
        transparent: true, side: BackSide, blending: AdditiveBlending, depthWrite: false,
        vertexShader: 'varying vec3 vN; void main(){ vN = normalize(normalMatrix * normal); gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }',
        fragmentShader: 'varying vec3 vN; void main(){ float i = pow(0.72 - dot(vN, vec3(0.0,0.0,1.0)), 3.0); gl_FragColor = vec4(0.02,0.71,0.83,1.0) * clamp(i,0.0,1.0); }',
      }),
    )
    scene.add(halo)

    // pin no lugar (filho do globo: gira junto)
    const [px, py, pz] = latLonToVec3(geo.lat, geo.lon, 1.004)
    const pino = new Mesh(new SphereGeometry(0.017, 16, 12), new MeshBasicMaterial({ color: new Color('#a5f3fc') }))
    pino.position.set(px, py, pz)
    const anelGeo = new RingGeometry(0.03, 0.037, 40)
    const anelMat = new MeshBasicMaterial({ color: new Color('#22d3ee'), transparent: true, opacity: 0.9, side: DoubleSide, blending: AdditiveBlending, depthWrite: false })
    const anel = new Mesh(anelGeo, anelMat)
    anel.position.set(px, py, pz)
    anel.lookAt(new Vector3(px * 2, py * 2, pz * 2)) // a face do anel aponta para fora da esfera
    globo.add(pino, anel)

    // ---- orientação (yaw/pitch), voo até o lugar e arraste
    const alvo = alvoDe(geo.lat, geo.lon)
    let yaw = reduzirMovimento ? alvo.yaw : alvo.yaw - 1.6
    let pitch = reduzirMovimento ? alvo.pitch : 0.25
    let voo: { t0: number; y0: number; p0: number } | null = reduzirMovimento ? null : { t0: performance.now(), y0: yaw, p0: pitch }
    let vYaw = 0
    let vPitch = 0
    const DUR_VOO = 1400
    const qYaw = new Quaternion()
    const qPitch = new Quaternion()
    const eixoY = new Vector3(0, 1, 0)
    const eixoX = new Vector3(1, 0, 0)

    const aplicar = () => {
      qYaw.setFromAxisAngle(eixoY, yaw)
      qPitch.setFromAxisAngle(eixoX, pitch)
      globo.quaternion.copy(qPitch).multiply(qYaw)
    }

    const redimensionar = () => {
      if (disposed || !renderer) return
      const w = Math.max(64, Math.floor(box.clientWidth))
      const h = Math.max(64, Math.floor(box.clientHeight))
      renderer.setSize(w, h, false)
      canvas.style.width = '100%'
      canvas.style.height = '100%'
      camera.aspect = w / h
      camera.updateProjectionMatrix()
    }

    const desenhar = (agora: number) => {
      if (disposed || !renderer) return
      if (voo) {
        const t = Math.min(1, (agora - voo.t0) / DUR_VOO)
        const e = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2
        yaw = voo.y0 + angDiff(voo.y0, alvo.yaw) * e
        pitch = voo.p0 + (alvo.pitch - voo.p0) * e
        if (t >= 1) voo = null
      } else if (!arrastando && (Math.abs(vYaw) > 1e-4 || Math.abs(vPitch) > 1e-4)) {
        yaw += vYaw
        pitch = clampPitch((pitch + vPitch) / RAD) * RAD
        vYaw *= 0.92
        vPitch *= 0.92
      }
      // pulso do pin (só enquanto o laço roda; em repouso fica no tamanho normal)
      const pulso = reduzirMovimento ? 1 : 1 + 0.9 * ((agora / 1000) % 1.6) / 1.6
      anel.scale.setScalar(pulso)
      anelMat.opacity = reduzirMovimento ? 0.9 : 0.9 * (1 - ((agora / 1000) % 1.6) / 1.6)
      aplicar()
      renderer.render(scene, camera)
    }

    const ocupado = () => voo !== null || arrastando || Math.abs(vYaw) > 1e-4 || Math.abs(vPitch) > 1e-4

    const tick = (agora: number) => {
      raf = 0
      if (disposed) return
      if (document.hidden) return // aba oculta: para; visibilitychange religa
      const pulsando = agora < ativoAte
      // 30 fps só no pulso; voo e arraste usam a taxa cheia
      if (!ocupado() && pulsando && agora - ultimoFrame < 33) {
        raf = requestAnimationFrame(tick)
        return
      }
      ultimoFrame = agora
      desenhar(agora)
      if (ocupado() || pulsando) raf = requestAnimationFrame(tick)
      else {
        // último quadro: pulso assentado, sem animação
        anel.scale.setScalar(1)
        anelMat.opacity = 0.9
        renderer!.render(scene, camera)
      }
    }

    const invalidar = (ms = 0) => {
      if (disposed) return
      ativoAte = Math.max(ativoAte, performance.now() + ms)
      if (!raf && !document.hidden) raf = requestAnimationFrame(tick)
    }

    // ---- entrada (pointer events, sem OrbitControls)
    let ultX = 0
    let ultY = 0
    const aoPressionar = (e: PointerEvent) => {
      arrastando = true
      voo = null
      vYaw = 0
      vPitch = 0
      ultX = e.clientX
      ultY = e.clientY
      canvas.setPointerCapture?.(e.pointerId)
      canvas.style.cursor = 'grabbing'
      invalidar()
    }
    const aoMover = (e: PointerEvent) => {
      if (!arrastando) return
      const dx = e.clientX - ultX
      const dy = e.clientY - ultY
      ultX = e.clientX
      ultY = e.clientY
      vYaw = dx * 0.005
      vPitch = dy * 0.005
      yaw += vYaw
      pitch = clampPitch((pitch + vPitch) / RAD) * RAD
      invalidar()
    }
    const aoSoltar = (e: PointerEvent) => {
      arrastando = false
      canvas.releasePointerCapture?.(e.pointerId)
      canvas.style.cursor = 'grab'
      if (reduzirMovimento) {
        vYaw = 0
        vPitch = 0
      }
      invalidar()
    }
    const aoVisibilidade = () => { if (!document.hidden) invalidar(1500) }
    const aoPerderContexto = (e: Event) => { e.preventDefault(); marcar('error') }
    const aoRestaurarContexto = () => { marcar('ready'); invalidar(1500) }

    canvas.addEventListener('pointerdown', aoPressionar)
    canvas.addEventListener('pointermove', aoMover)
    canvas.addEventListener('pointerup', aoSoltar)
    canvas.addEventListener('pointercancel', aoSoltar)
    canvas.addEventListener('webglcontextlost', aoPerderContexto)
    canvas.addEventListener('webglcontextrestored', aoRestaurarContexto)
    document.addEventListener('visibilitychange', aoVisibilidade)
    const ro = new ResizeObserver(() => { redimensionar(); invalidar() })
    ro.observe(box)

    redimensionar()
    aplicar()
    marcar('ready')
    invalidar(reduzirMovimento ? 0 : 6000) // voo + ~6 s de pulso, depois para

    return () => {
      if (disposed) return
      disposed = true
      if (raf) cancelAnimationFrame(raf)
      ro.disconnect()
      canvas.removeEventListener('pointerdown', aoPressionar)
      canvas.removeEventListener('pointermove', aoMover)
      canvas.removeEventListener('pointerup', aoSoltar)
      canvas.removeEventListener('pointercancel', aoSoltar)
      canvas.removeEventListener('webglcontextlost', aoPerderContexto)
      canvas.removeEventListener('webglcontextrestored', aoRestaurarContexto)
      document.removeEventListener('visibilitychange', aoVisibilidade)
      geoEsfera.dispose()
      anelGeo.dispose()
      pino.geometry.dispose()
      halo.geometry.dispose()
      ;(miolo.material as MeshBasicMaterial).dispose()
      ;(casca.material as MeshBasicMaterial).dispose()
      ;(pino.material as MeshBasicMaterial).dispose()
      ;(halo.material as ShaderMaterial).dispose()
      anelMat.dispose()
      textura.dispose()
      renderer!.dispose()
      renderer!.forceContextLoss()
      canvas.remove()
    }
  }, [plano, geo, reduzirMovimento, onSemWebGL, marcar])

  const [pinX, pinY] = [((geo.lon + 180) / 360) * 100, ((90 - geo.lat) / 180) * 100]

  return (
    <div
      ref={raizRef}
      className="relative w-full h-full"
      data-holo-state="loading"
      data-holo-lat={geo.lat}
      data-holo-lon={geo.lon}
    >
      {plano ? (
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="relative w-full" style={{ aspectRatio: '2 / 1', maxHeight: '100%' }}>
            <canvas ref={canvasPlanoRef} width={TEX_W} height={TEX_H} className="w-full h-full rounded-lg border border-cyan-500/30 bg-cyan-950/20" />
            <span
              className="absolute w-3 h-3 -ml-1.5 -mt-1.5 rounded-full bg-cyan-200 shadow-[0_0_12px_4px_rgba(34,211,238,0.7)]"
              style={{ left: `${pinX}%`, top: `${pinY}%` }}
              aria-hidden
            />
          </div>
        </div>
      ) : (
        <div ref={boxRef} className="absolute inset-0" />
      )}
    </div>
  )
}

export default HoloGlobe
