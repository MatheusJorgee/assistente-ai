'use client'

/**
 * Painéis do holograma. TODO texto vem de terceiros (OSM, Wikipedia, Wikivoyage): sempre
 * renderizado como string React (nunca HTML) e os links já passaram por safeUrl.
 */

import { BedDouble, CalendarDays, CloudSun, ExternalLink, Info, Landmark, Lightbulb, MapPin } from 'lucide-react'
import type { ReactNode } from 'react'
import type { HoloPainel, HoloPayload } from '@/types'

export const ROTULO_PAINEL: Record<HoloPainel['tipo'], string> = {
  resumo: 'Resumo',
  hospedagem: 'Hospedagem',
  atracoes: 'Atrações',
  cronograma: 'Cronograma',
  clima: 'Clima',
  dicas: 'Dicas',
}

const PERIODO: Record<string, string> = { manha: 'Manhã', tarde: 'Tarde', noite: 'Noite' }

function Moldura({ icone, titulo, status, children }: { icone: ReactNode; titulo: string; status?: string; children: ReactNode }) {
  return (
    <section className="holo-panel p-3.5 text-zinc-100" aria-label={titulo}>
      <div className="holo-scanlines" aria-hidden />
      <header className="relative flex items-center gap-2 mb-2">
        <span className="text-cyan-300">{icone}</span>
        <h3 className="text-[11px] font-semibold tracking-[0.18em] uppercase text-cyan-200 holo-glow">{titulo}</h3>
        {status && status !== 'ok' ? (
          <span className="ml-auto text-[10px] text-amber-300/90">{status === 'parcial' ? 'parcial' : 'indisponível'}</span>
        ) : null}
      </header>
      <div className="relative text-[13px] leading-relaxed">{children}</div>
    </section>
  )
}

function Link({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 text-cyan-300 hover:text-cyan-100 underline decoration-cyan-500/40 underline-offset-2"
    >
      {children}
      <ExternalLink size={11} aria-hidden />
    </a>
  )
}

export function PainelView({ painel, atracoes }: { painel: HoloPainel; atracoes: Map<string, string> }) {
  switch (painel.tipo) {
    case 'resumo':
      return (
        <Moldura icone={<Info size={14} />} titulo="Resumo" status={painel.status}>
          <p className="text-zinc-200">{painel.texto}</p>
        </Moldura>
      )

    case 'hospedagem':
      return (
        <Moldura icone={<BedDouble size={14} />} titulo="Hospedagem" status={painel.status}>
          <p className="mb-2 rounded-md border border-amber-400/30 bg-amber-400/5 px-2 py-1.5 text-[11.5px] text-amber-200">
            {painel.aviso}
          </p>
          {painel.links.length ? (
            <div className="mb-2 flex flex-wrap gap-x-3 gap-y-1">
              {painel.links.map(l => (
                <Link key={l.url} href={l.url}>{l.rotulo}</Link>
              ))}
            </div>
          ) : null}
          {painel.itens.length ? (
            <ul className="space-y-1">
              {painel.itens.map(h => (
                <li key={h.link_mapa + h.nome} className="flex items-baseline justify-between gap-2">
                  <span className="truncate">{h.nome}</span>
                  <span className="flex shrink-0 items-center gap-2 text-[11px] text-zinc-400">
                    {h.categoria}
                    <Link href={h.link_mapa}>mapa</Link>
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-zinc-400">Nenhum hotel mapeado no OpenStreetMap para esta área.</p>
          )}
        </Moldura>
      )

    case 'atracoes':
      return (
        <Moldura icone={<Landmark size={14} />} titulo="Atrações" status={painel.status}>
          <ul className="space-y-1.5">
            {painel.itens.map(a => (
              <li key={a.id}>
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-medium text-zinc-50">{a.nome}</span>
                  <Link href={a.link_mapa}>mapa</Link>
                </div>
                {a.categoria ? <div className="text-[11px] text-cyan-300/70">{a.categoria}</div> : null}
                {a.descricao ? <div className="text-[12px] text-zinc-400">{a.descricao}</div> : null}
              </li>
            ))}
          </ul>
        </Moldura>
      )

    case 'cronograma':
      return (
        <Moldura icone={<CalendarDays size={14} />} titulo="Cronograma" status={painel.status}>
          {painel.aviso ? <p className="mb-2 text-[11.5px] text-zinc-400">{painel.aviso}</p> : null}
          <ol className="space-y-2">
            {painel.dias.map(d => (
              <li key={d.n}>
                <div className="text-[12px] font-semibold text-cyan-200">{d.titulo || `Dia ${d.n}`}</div>
                {d.blocos.map(b => (
                  <div key={b.periodo} className="ml-2 flex gap-2 text-[12.5px]">
                    <span className="w-12 shrink-0 text-cyan-300/70">{PERIODO[b.periodo]}</span>
                    <span className="text-zinc-200">{b.poi_ids.map(id => atracoes.get(id)).filter(Boolean).join(' · ')}</span>
                  </div>
                ))}
              </li>
            ))}
          </ol>
        </Moldura>
      )

    case 'clima':
      return (
        <Moldura icone={<CloudSun size={14} />} titulo="Clima" status={painel.status}>
          <p className={`mb-2 text-[11.5px] ${painel.origem === 'ano_anterior' ? 'text-amber-200' : 'text-zinc-400'}`}>{painel.rotulo}</p>
          <ul className="space-y-0.5 font-mono text-[12px]">
            {painel.dias.map(d => (
              <li key={d.data} className="flex justify-between gap-2">
                <span className="text-zinc-400">{d.data.slice(5).split('-').reverse().join('/')}</span>
                <span>{Math.round(d.tmin)}° – {Math.round(d.tmax)}°</span>
                <span className="text-cyan-300/80">{d.chuva_mm > 0 ? `${d.chuva_mm.toFixed(1)} mm` : '—'}</span>
              </li>
            ))}
          </ul>
        </Moldura>
      )

    case 'dicas':
      return (
        <Moldura icone={<Lightbulb size={14} />} titulo="Dicas do guia" status={painel.status}>
          <div className="space-y-2">
            {painel.secoes.map(s => (
              <div key={s.titulo}>
                <div className="text-[12px] font-semibold text-cyan-200">{s.titulo}</div>
                <ul className="ml-3 list-disc space-y-0.5 text-[12.5px] text-zinc-300 marker:text-cyan-500/60">
                  {s.itens.map(i => <li key={i}>{i}</li>)}
                </ul>
              </div>
            ))}
          </div>
        </Moldura>
      )
  }
}

export function Fontes({ fontes }: { fontes: HoloPayload['fontes'] }) {
  if (!fontes.length) return null
  return (
    <p className="text-[10.5px] leading-snug text-zinc-500">
      <MapPin size={10} className="mr-1 inline" aria-hidden />
      Fontes:{' '}
      {fontes.map((f, i) => (
        <span key={f.url}>
          {i > 0 ? ' · ' : ''}
          <a href={f.url} target="_blank" rel="noopener noreferrer" className="underline decoration-zinc-600 hover:text-zinc-300">
            {f.nome}
          </a>
        </span>
      ))}
    </p>
  )
}
