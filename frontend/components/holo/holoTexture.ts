// Desenha o mapa-múndi holográfico num canvas equirretangular (2:1): grade, continentes e o
// contorno destacado do lugar. Serve de textura para o globo (Three.js) E de mapa plano.
import { geoEquirectangular, geoGraticule10, geoPath } from 'd3-geo'
import { feature } from 'topojson-client'
import land110 from 'world-atlas/land-110m.json'
import type { HoloPayload } from '@/types'
import { unwrapRing } from '@/lib/holo'

const CIANO = '6,182,212'
const CIANO_CLARO = '103,232,249'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let terraCache: any = null
function terra() {
  if (!terraCache) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const topo: any = land110
    terraCache = feature(topo, topo.objects.land)
  }
  return terraCache
}

export function desenharMapa(canvas: HTMLCanvasElement, geo: HoloPayload['geo']): void {
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  const W = canvas.width
  const H = canvas.height
  const k = W / 2048 // espessuras proporcionais ao tamanho da textura
  ctx.clearRect(0, 0, W, H)

  const proj = geoEquirectangular().fitSize([W, H], { type: 'Sphere' } as never)
  const path = geoPath(proj, ctx)

  // grade de 10°
  ctx.beginPath()
  path(geoGraticule10())
  ctx.strokeStyle = `rgba(${CIANO},0.22)`
  ctx.lineWidth = 1 * k
  ctx.stroke()

  // continentes
  ctx.beginPath()
  path(terra())
  ctx.fillStyle = `rgba(${CIANO},0.13)`
  ctx.fill()
  ctx.strokeStyle = `rgba(${CIANO},0.6)`
  ctx.lineWidth = 1.2 * k
  ctx.stroke()

  // destaque do lugar: projeção equirretangular direta (sem polígono esférico, então não há
  // anel invertido); atravessar o antimeridiano é tratado com unwrapRing + cópias a ±360°.
  const X = (lon: number) => ((lon + 180) / 360) * W
  const Y = (lat: number) => ((90 - lat) / 180) * H
  ctx.fillStyle = `rgba(${CIANO_CLARO},0.32)`
  ctx.strokeStyle = `rgba(${CIANO_CLARO},0.95)`
  ctx.lineWidth = Math.max(1.6, 2.4 * k)
  ctx.lineJoin = 'round'

  if (geo.kind === 'area' && geo.polygon?.length) {
    for (const deslocar of [-W, 0, W]) {
      ctx.beginPath()
      for (const poly of geo.polygon) {
        for (const anel of poly) {
          const u = unwrapRing(anel)
          u.forEach(([lon, lat], i) => {
            const x = X(lon) + deslocar
            if (i === 0) ctx.moveTo(x, Y(lat))
            else ctx.lineTo(x, Y(lat))
          })
          ctx.closePath()
        }
      }
      ctx.fill('evenodd')
      ctx.stroke()
    }
  } else if (geo.kind === 'area' && geo.bbox) {
    const [s, n, w, e] = geo.bbox
    ctx.strokeRect(X(w), Y(n), Math.max(2, X(e) - X(w)), Math.max(2, Y(s) - Y(n)))
  }
}
