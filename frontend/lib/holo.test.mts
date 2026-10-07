/* eslint-disable @typescript-eslint/no-explicit-any */
// Testes da lógica pura dos hologramas. Rodar: node --test lib/holo.test.mts
import test from 'node:test'
import assert from 'node:assert/strict'
import { clampPitch, clampPolygon, latLonToVec3, parseHoloPayload, safeUrl, unwrapRing } from './holo.ts'

const near = (a: number, b: number, eps = 1e-9) => assert.ok(Math.abs(a - b) < eps, `${a} != ${b}`)

test('safeUrl: só https/http de hosts esperados, sem credenciais', () => {
  assert.equal(safeUrl('javascript:alert(1)'), null)
  assert.equal(safeUrl('data:text/html,<b>x</b>'), null)
  assert.equal(safeUrl('https://evil.com/x'), null)
  assert.equal(safeUrl('https://booking.com.evil.com/'), null)
  assert.equal(safeUrl('https://user:pw@booking.com/x'), null)
  assert.equal(safeUrl('ftp://booking.com/'), null)
  assert.ok(safeUrl('https://www.booking.com/searchresults.html?ss=Lisboa'))
  assert.ok(safeUrl('https://pt.wikipedia.org/wiki/Lisboa'))
  assert.equal(safeUrl(42), null)
})

test('latLonToVec3: convenção do SphereGeometry (lon 0 -> +x, leste -> -z, norte -> +y)', () => {
  const [x, y, z] = latLonToVec3(0, 0)
  near(x, 1); near(y, 0); near(z, 0)
  const l = latLonToVec3(0, 90)
  near(l[0], 0); near(l[2], -1)
  const n = latLonToVec3(90, 123)
  near(n[0], 0); near(n[1], 1); near(n[2], 0)
  const a = latLonToVec3(0, 180)
  near(a[0], -1)
  const [px, py, pz] = latLonToVec3(-12.3, -41.9, 2)
  near(Math.hypot(px, py, pz), 2)
})

test('clampPitch', () => {
  assert.equal(clampPitch(120), 80)
  assert.equal(clampPitch(-95), -80)
  assert.equal(clampPitch(NaN), 0)
  assert.equal(clampPitch(33), 33)
})

test('unwrapRing: atravessar o antimeridiano não pula 360°', () => {
  const fiji = [[179, -17], [-179, -17], [-179, -18], [179, -18], [179, -17]]
  const u = unwrapRing(fiji)
  for (let i = 1; i < u.length; i++) assert.ok(Math.abs(u[i][0] - u[i - 1][0]) < 180)
  assert.deepEqual(u[1], [181, -17])
  // anel comum não muda
  const comum = [[10, 10], [11, 10], [11, 11], [10, 10]]
  assert.deepEqual(unwrapRing(comum), comum)
})

test('clampPolygon: respeita o teto de pontos', () => {
  const anel = (n: number) => Array.from({ length: n }, (_, i) => [i / 100, 0])
  const mp = [[anel(500)], [anel(500)], [anel(100)]]
  const c = clampPolygon(mp, 800)
  assert.equal(c.length, 1)
})

const poi = (id: string) => ({ id, nome: 'Torre ' + id, lat: 38.7, lon: -9.1, link_mapa: 'https://www.openstreetmap.org/?mlat=1&mlon=2' })

test('parseHoloPayload: payload válido passa; ids do cronograma são preservados', () => {
  const p = parseHoloPayload({
    v: 1, id: 'x', tipo: 'viagem', titulo: 'Viagem', geo: { lat: 38.7, lon: -9.1, kind: 'ponto' },
    paineis: [
      { tipo: 'atracoes', itens: [poi('a0')] },
      { tipo: 'cronograma', dias: [{ n: 1, titulo: 'Dia 1', blocos: [{ periodo: 'manha', poi_ids: ['a0'] }] }] },
      { tipo: 'hospedagem', itens: [], links: [{ rotulo: 'Booking', url: 'https://www.booking.com/x' }] },
    ],
    fontes: [{ nome: 'OSM', url: 'https://www.openstreetmap.org/copyright' }],
  })
  assert.ok(p)
  assert.deepEqual(p!.paineis.map(x => x.tipo), ['atracoes', 'cronograma', 'hospedagem'])
  const h = p!.paineis[2] as any
  assert.ok(h.aviso.length > 0, 'aviso de "sem preço ao vivo" sempre presente')
})

test('parseHoloPayload: rejeita o inválido sem lançar', () => {
  assert.equal(parseHoloPayload(null), null)
  assert.equal(parseHoloPayload('x'), null)
  assert.equal(parseHoloPayload({ v: 2, geo: { lat: 0, lon: 0 } }), null)
  assert.equal(parseHoloPayload({ v: 1, geo: { lat: 999, lon: 0 } }), null)
  assert.equal(parseHoloPayload({ v: 1, geo: { lat: NaN, lon: 0 } }), null)
})

test('parseHoloPayload: descarta painel desconhecido, URL perigosa e duplicado', () => {
  const p = parseHoloPayload({
    v: 1, id: 'x', tipo: 'mapa', titulo: 'T', geo: { lat: 1, lon: 2, kind: 'ponto' },
    paineis: [
      { tipo: 'malicioso', html: '<script>' },
      { tipo: 'resumo', texto: 'um' },
      { tipo: 'resumo', texto: 'dois' },
      { tipo: 'hospedagem', itens: [{ nome: 'H', link_mapa: 'javascript:alert(1)' }], links: [{ rotulo: 'x', url: 'javascript:1' }] },
    ],
    fontes: [{ nome: 'ruim', url: 'javascript:1' }],
  })
  assert.ok(p)
  assert.deepEqual(p!.paineis.map(x => x.tipo), ['resumo'])
  assert.equal((p!.paineis[0] as any).texto, 'um')
  assert.equal(p!.fontes.length, 0)
})

test('parseHoloPayload: excesso é cortado (12 itens, 800 pontos)', () => {
  const itens = Array.from({ length: 30 }, (_, i) => poi('a' + i))
  const anel = Array.from({ length: 2000 }, (_, i) => [i / 1000, (i % 10) / 1000])
  const p = parseHoloPayload({
    v: 1, id: 'x', tipo: 'mapa', titulo: 'T',
    geo: { lat: 1, lon: 2, kind: 'area', polygon: [[anel]] },
    paineis: [{ tipo: 'atracoes', itens }],
  })
  assert.ok(p)
  assert.equal((p!.paineis[0] as any).itens.length, 12)
  assert.equal(p!.geo.polygon, undefined, 'anel de 2000 pontos estoura o teto e é descartado inteiro')
})
