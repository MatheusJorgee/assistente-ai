// Lógica PURA dos hologramas (sem React, sem three): validação do payload que chega pelo
// WebSocket, links seguros e geometria do globo. Testada em lib/holo.test.mts.
import type { HoloPainel, HoloPayload, HoloMultiPoligono, HoloPoi } from '../types'

export const MAX_ITENS = 12
export const MAX_PAINEIS = 7
export const MAX_PONTOS_POLIGONO = 800
export const PITCH_MAX = 80

// Mesmos hosts que o backend usa em core/holo/schema.py (HOSTS_LINK)
const HOSTS_LINK = [
  'booking.com', 'google.com', 'airbnb.com.br', 'airbnb.com', 'openstreetmap.org',
  'wikipedia.org', 'wikivoyage.org', 'open-meteo.com',
]

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const isObj = (v: unknown): v is Record<string, any> => typeof v === 'object' && v !== null && !Array.isArray(v)
const txt = (v: unknown, max: number): string =>
  typeof v === 'string' ? v.replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, '').replace(/\s+/g, ' ').trim().slice(0, max) : ''
const num = (v: unknown, lo: number, hi: number): number | null =>
  typeof v === 'number' && Number.isFinite(v) && v >= lo && v <= hi ? v : null

/** Só https/http, sem credenciais, e só de hosts esperados. Qualquer outra coisa vira null. */
export function safeUrl(url: unknown, hosts: string[] = HOSTS_LINK): string | null {
  if (typeof url !== 'string' || url.length > 2000) return null
  let u: URL
  try {
    u = new URL(url)
  } catch {
    return null
  }
  if (u.protocol !== 'https:' && u.protocol !== 'http:') return null
  if (u.username || u.password) return null
  const host = u.hostname.toLowerCase()
  if (!hosts.some(h => host === h || host.endsWith('.' + h))) return null
  return u.toString()
}

// ------------------------------------------------------------------ geometria do globo

/** Vetor 3D (y para cima) de lat/lon em graus, na MESMA convenção do UV de SphereGeometry:
 *  lon 0 -> +x, lon 90 (leste) -> -z, polo norte -> +y. */
export function latLonToVec3(lat: number, lon: number, r = 1): [number, number, number] {
  const la = (lat * Math.PI) / 180
  const lo = (lon * Math.PI) / 180
  return [r * Math.cos(la) * Math.cos(lo), r * Math.sin(la), -r * Math.cos(la) * Math.sin(lo)]
}

export function clampPitch(deg: number): number {
  if (!Number.isFinite(deg)) return 0
  return Math.max(-PITCH_MAX, Math.min(PITCH_MAX, deg))
}

/** Longitudes contínuas: se dois pontos seguidos "pulam" mais de 180°, atravessaram o antimeridiano
 *  (Fiji, Chukotka) e o anel é desenhado sem cortar o mapa. */
export function unwrapRing(ring: number[][]): number[][] {
  const out: number[][] = []
  let deslocamento = 0
  for (let i = 0; i < ring.length; i++) {
    const [lon, lat] = ring[i]
    if (i > 0) {
      const anterior = ring[i - 1][0]
      if (lon - anterior > 180) deslocamento -= 360
      else if (lon - anterior < -180) deslocamento += 360
    }
    out.push([lon + deslocamento, lat])
  }
  return out
}

/** Limita o total de pontos (defesa contra payload gigante); mantém os polígonos maiores primeiro. */
export function clampPolygon(mp: HoloMultiPoligono, max = MAX_PONTOS_POLIGONO): HoloMultiPoligono {
  const saida: HoloMultiPoligono = []
  let total = 0
  for (const poly of mp) {
    const aneis: number[][][] = []
    for (const anel of poly) {
      if (total + anel.length > max) return saida
      total += anel.length
      aneis.push(anel)
    }
    if (aneis.length) saida.push(aneis)
  }
  return saida
}

// ------------------------------------------------------------------ validação do payload

function parsePoligono(v: unknown): HoloMultiPoligono | undefined {
  if (!Array.isArray(v)) return undefined
  const mp: HoloMultiPoligono = []
  for (const poly of v) {
    if (!Array.isArray(poly)) continue
    const aneis: number[][][] = []
    for (const anel of poly) {
      if (!Array.isArray(anel)) continue
      const pts: number[][] = []
      for (const pt of anel) {
        if (!Array.isArray(pt)) continue
        const lo = num(pt[0], -180, 180)
        const la = num(pt[1], -90, 90)
        if (lo !== null && la !== null) pts.push([lo, la])
      }
      if (pts.length >= 4) aneis.push(pts)
    }
    if (aneis.length) mp.push(aneis)
  }
  const limitado = clampPolygon(mp)
  return limitado.length ? limitado : undefined
}

function parsePoi(v: unknown): HoloPoi | null {
  if (!isObj(v)) return null
  const nome = txt(v.nome, 80)
  const link = safeUrl(v.link_mapa)
  if (!nome || !link) return null
  const poi: HoloPoi = { nome, link_mapa: link }
  const id = txt(v.id, 12)
  if (id) poi.id = id
  const cat = txt(v.categoria, 40)
  if (cat) poi.categoria = cat
  const desc = txt(v.descricao, 160)
  if (desc) poi.descricao = desc
  const lat = num(v.lat, -90, 90)
  const lon = num(v.lon, -180, 180)
  if (lat !== null && lon !== null) {
    poi.lat = lat
    poi.lon = lon
  }
  const wiki = safeUrl(v.wikipedia)
  if (wiki) poi.wikipedia = wiki
  return poi
}

const status = (v: unknown): 'ok' | 'parcial' | 'indisponivel' =>
  v === 'parcial' || v === 'indisponivel' ? v : 'ok'

function parsePainel(p: unknown): HoloPainel | null {
  if (!isObj(p)) return null
  switch (p.tipo) {
    case 'resumo': {
      const texto = txt(p.texto, 600)
      return texto ? { tipo: 'resumo', texto, status: status(p.status) } : null
    }
    case 'atracoes': {
      const itens = (Array.isArray(p.itens) ? p.itens : []).slice(0, MAX_ITENS).map(parsePoi)
        .filter((i): i is HoloPoi & { id: string; lat: number; lon: number } =>
          !!i && !!i.id && i.lat !== undefined && i.lon !== undefined)
      return itens.length ? { tipo: 'atracoes', itens, status: status(p.status) } : null
    }
    case 'hospedagem': {
      const itens = (Array.isArray(p.itens) ? p.itens : []).slice(0, MAX_ITENS).map(parsePoi).filter((i): i is HoloPoi => !!i)
      const links = (Array.isArray(p.links) ? p.links : []).slice(0, 5).flatMap(l => {
        const url = isObj(l) ? safeUrl(l.url) : null
        const rotulo = isObj(l) ? txt(l.rotulo, 60) : ''
        return url && rotulo ? [{ rotulo, url }] : []
      })
      if (!itens.length && !links.length) return null
      // O aviso de "sem preço ao vivo" é da TELA também: não depende do que veio no payload.
      const aviso = txt(p.aviso, 300) || 'Sem preço nem disponibilidade ao vivo.'
      return { tipo: 'hospedagem', itens, links, aviso, status: status(p.status) }
    }
    case 'cronograma': {
      const dias = (Array.isArray(p.dias) ? p.dias : []).slice(0, 14).flatMap(d => {
        if (!isObj(d)) return []
        const blocos = (Array.isArray(d.blocos) ? d.blocos : []).slice(0, 3).flatMap(b => {
          if (!isObj(b) || !['manha', 'tarde', 'noite'].includes(b.periodo)) return []
          const ids = (Array.isArray(b.poi_ids) ? b.poi_ids : []).filter((i: unknown): i is string => typeof i === 'string').slice(0, 4)
          return ids.length ? [{ periodo: b.periodo as 'manha' | 'tarde' | 'noite', poi_ids: ids }] : []
        })
        const n = num(d.n, 1, 99)
        return blocos.length && n !== null ? [{ n, titulo: txt(d.titulo, 60), blocos }] : []
      })
      return dias.length
        ? { tipo: 'cronograma', dias, metodo: p.metodo === 'llm' ? 'llm' : 'proximidade',
            aviso: txt(p.aviso, 300), status: status(p.status) }
        : null
    }
    case 'clima': {
      const dias = (Array.isArray(p.dias) ? p.dias : []).slice(0, 16).flatMap(d => {
        if (!isObj(d)) return []
        const tmin = num(d.tmin, -90, 70)
        const tmax = num(d.tmax, -90, 70)
        const data = txt(d.data, 10)
        return data && tmin !== null && tmax !== null ? [{ data, tmin, tmax, chuva_mm: num(d.chuva_mm, 0, 2000) ?? 0 }] : []
      })
      return dias.length
        ? { tipo: 'clima', rotulo: txt(p.rotulo, 100), origem: p.origem === 'ano_anterior' ? 'ano_anterior' : 'previsao',
            dias, status: status(p.status) }
        : null
    }
    case 'dicas': {
      const secoes = (Array.isArray(p.secoes) ? p.secoes : []).slice(0, 5).flatMap(s => {
        if (!isObj(s)) return []
        const titulo = txt(s.titulo, 40)
        const itens = (Array.isArray(s.itens) ? s.itens : []).slice(0, 6).map(i => txt(i, 200)).filter(Boolean)
        return titulo && itens.length ? [{ titulo, itens }] : []
      })
      return secoes.length ? { tipo: 'dicas', secoes, status: status(p.status) } : null
    }
    default:
      return null
  }
}

/** Payload do WebSocket -> HoloPayload seguro, ou null. Nunca lança: o inválido é descartado. */
export function parseHoloPayload(raw: unknown): HoloPayload | null {
  try {
    if (!isObj(raw) || raw.v !== 1 || !isObj(raw.geo)) return null
    const lat = num(raw.geo.lat, -90, 90)
    const lon = num(raw.geo.lon, -180, 180)
    if (lat === null || lon === null) return null

    const geo: HoloPayload['geo'] = { lat, lon, kind: raw.geo.kind === 'area' ? 'area' : 'ponto' }
    const b = raw.geo.bbox
    if (Array.isArray(b) && b.length === 4) {
      const [s, n, w, e] = [num(b[0], -90, 90), num(b[1], -90, 90), num(b[2], -180, 180), num(b[3], -180, 180)]
      if (s !== null && n !== null && w !== null && e !== null) geo.bbox = [s, n, w, e]
    }
    if (geo.kind === 'area') {
      const poly = parsePoligono(raw.geo.polygon)
      if (poly) geo.polygon = poly
    }

    const vistos = new Set<string>()
    const paineis: HoloPainel[] = []
    for (const bruto of Array.isArray(raw.paineis) ? raw.paineis : []) {
      const p = parsePainel(bruto)
      if (p && !vistos.has(p.tipo)) {
        vistos.add(p.tipo)
        paineis.push(p)
      }
      if (paineis.length >= MAX_PAINEIS) break
    }

    const fontes = (Array.isArray(raw.fontes) ? raw.fontes : []).slice(0, 6).flatMap(f => {
      const url = isObj(f) ? safeUrl(f.url) : null
      const nome = isObj(f) ? txt(f.nome, 60) : ''
      return url && nome ? [{ nome, url }] : []
    })

    return {
      v: 1,
      id: txt(raw.id, 40) || 'holo',
      tipo: raw.tipo === 'viagem' ? 'viagem' : 'mapa',
      titulo: txt(raw.titulo, 80) || 'Holograma',
      geo,
      paineis,
      fontes,
    }
  } catch {
    return null
  }
}
