'use client'

/**
 * HologramLayer — camada dos hologramas (globo + painéis), acima do fundo e abaixo do Visor,
 * do cartão de aprovação e do ControlDeck. A camada NÃO captura cliques: só o globo e os
 * cartões (pointer-events-auto). Esc fecha (o handler vive em useQuintaFeiraUI).
 *
 * Em telas largas os painéis ficam em duas colunas ao lado do globo; em telas estreitas viram abas.
 */

import dynamic from 'next/dynamic'
import { useCallback, useMemo, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { Globe2, Map as MapIcon, X } from 'lucide-react'
import type { HoloPainel, HoloPayload } from '@/types'
import { Fontes, PainelView, ROTULO_PAINEL } from './HoloCards'

// three fica fora do bundle inicial: só baixa quando o primeiro holograma abre.
const HoloGlobe = dynamic(() => import('./HoloGlobe'), {
  ssr: false,
  loading: () => <div className="h-full w-full animate-pulse rounded-full bg-cyan-500/5" aria-hidden />,
})

interface HologramLayerProps {
  holo: HoloPayload | null
  onClose: () => void
}

const COLUNA_ESQ: HoloPainel['tipo'][] = ['resumo', 'clima', 'dicas']
const COLUNA_DIR: HoloPainel['tipo'][] = ['hospedagem', 'atracoes', 'cronograma']

export function HologramLayer({ holo, onClose }: HologramLayerProps) {
  // key = id: um holograma novo remonta o conteúdo (volta ao globo e à primeira aba).
  return <AnimatePresence>{holo ? <Conteudo key={holo.id} holo={holo} onClose={onClose} /> : null}</AnimatePresence>
}

function Conteudo({ holo, onClose }: { holo: HoloPayload; onClose: () => void }) {
  const reduzir = useReducedMotion() ?? false
  const [plano, setPlano] = useState(false)
  const [aba, setAba] = useState<HoloPainel['tipo'] | null>(null)

  const semWebGL = useCallback(() => setPlano(true), [])

  const nomes = useMemo(() => {
    const m = new Map<string, string>()
    const atr = holo.paineis.find(p => p.tipo === 'atracoes')
    if (atr && atr.tipo === 'atracoes') atr.itens.forEach(i => m.set(i.id, i.nome))
    return m
  }, [holo])

  const porTipo = (tipos: HoloPainel['tipo'][]) => (holo.paineis ?? []).filter(p => tipos.includes(p.tipo))
  const esquerda = porTipo(COLUNA_ESQ)
  const direita = porTipo(COLUNA_DIR)
  const abaAtual = holo.paineis.find(p => p.tipo === aba) ?? holo.paineis[0]

  return (
        <motion.div
          key="holo-layer"
          className="pointer-events-none fixed inset-0 z-[35]"
          role="region"
          aria-label={`Holograma: ${holo.titulo}`}
          initial={reduzir ? false : { opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={reduzir ? { opacity: 0, transition: { duration: 0 } } : { opacity: 0 }}
          transition={{ duration: 0.35 }}
        >
          {/* fundo levemente escurecido para dar leitura ao holograma */}
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(2,10,16,0.55),rgba(2,10,16,0.15)_70%)]" aria-hidden />

          {/* cabeçalho */}
          <div className="pointer-events-auto absolute left-1/2 top-20 flex -translate-x-1/2 items-center gap-2 rounded-full border border-cyan-500/30 bg-zinc-950/80 py-1.5 pl-4 pr-1.5 backdrop-blur-xl">
            <span className="max-w-[46vw] truncate text-sm font-medium text-cyan-100 holo-glow">{holo.titulo}</span>
            <button
              type="button"
              onClick={() => setPlano(p => !p)}
              className="flex h-7 items-center gap-1 rounded-full px-2.5 text-xs text-cyan-200 hover:bg-cyan-500/15 focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-400"
              aria-pressed={plano}
              title={plano ? 'Ver o globo' : 'Ver o mapa plano'}
            >
              {plano ? <Globe2 size={14} aria-hidden /> : <MapIcon size={14} aria-hidden />}
              {plano ? 'Globo' : 'Mapa plano'}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="flex h-7 w-7 items-center justify-center rounded-full text-zinc-300 hover:bg-cyan-500/15 hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-400"
              aria-label="Fechar holograma (Esc)"
              title="Fechar (Esc)"
            >
              <X size={15} aria-hidden />
            </button>
          </div>

          {/* globo / mapa */}
          <div
            className={`pointer-events-auto absolute left-1/2 top-[34%] -translate-x-1/2 -translate-y-1/2 lg:top-1/2 ${
              plano
                ? 'h-[min(30vh,300px)] w-[min(92vw,600px)] lg:h-[min(38vh,340px)] lg:w-[min(92vw,680px)]'
                : 'h-[min(38vh,400px)] w-[min(38vh,400px,92vw)] lg:h-[min(60vh,560px)] lg:w-[min(60vh,560px,92vw)]'
            }`}
          >
            <HoloGlobe geo={holo.geo} plano={plano} reduzirMovimento={reduzir} onSemWebGL={semWebGL} />
          </div>

          {/* colunas de painéis (telas largas) */}
          <div className="holo-scroll pointer-events-none absolute bottom-40 left-6 top-[20rem] hidden w-[300px] flex-col gap-3 overflow-y-auto pr-1 lg:flex">
            {esquerda.map(p => (
              <div key={p.tipo} className="pointer-events-auto"><PainelView painel={p} atracoes={nomes} /></div>
            ))}
          </div>
          <div className="holo-scroll pointer-events-none absolute bottom-40 right-6 top-44 hidden w-[320px] flex-col gap-3 overflow-y-auto pr-1 lg:flex">
            {direita.map(p => (
              <div key={p.tipo} className="pointer-events-auto"><PainelView painel={p} atracoes={nomes} /></div>
            ))}
          </div>

          {/* fontes/licenças (telas largas; nas estreitas vão dentro das abas) */}
          <div className="pointer-events-auto absolute bottom-36 left-1/2 hidden max-w-[60vw] -translate-x-1/2 rounded-lg bg-zinc-950/60 px-3 py-1.5 backdrop-blur lg:block">
            <Fontes fontes={holo.fontes} />
          </div>

          {/* abas (telas estreitas) */}
          <div className="pointer-events-auto absolute inset-x-3 bottom-44 flex max-h-[30vh] flex-col gap-2 lg:hidden">
            <div className="flex gap-1 overflow-x-auto scrollbar-hide" role="tablist">
              {holo.paineis.map(p => (
                <button
                  key={p.tipo}
                  type="button"
                  role="tab"
                  aria-selected={abaAtual?.tipo === p.tipo}
                  onClick={() => setAba(p.tipo)}
                  className={`shrink-0 rounded-full border px-3 py-1 text-xs ${
                    abaAtual?.tipo === p.tipo
                      ? 'border-cyan-400/60 bg-cyan-500/20 text-cyan-100'
                      : 'border-cyan-500/20 bg-zinc-950/70 text-zinc-300'
                  }`}
                >
                  {ROTULO_PAINEL[p.tipo]}
                </button>
              ))}
            </div>
            <div className="overflow-y-auto scrollbar-hide">
              {abaAtual ? <PainelView painel={abaAtual} atracoes={nomes} /> : null}
              <div className="mt-2"><Fontes fontes={holo.fontes} /></div>
            </div>
          </div>
        </motion.div>
  )
}

export default HologramLayer
