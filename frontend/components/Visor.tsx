/**
 * Visor — painel visual flutuante e ARRASTÁVEL dentro da página da Quinta-Feira.
 *
 *  - noticia → CARROSSEL de cards (foto à esquerda + texto à direita) que troca
 *              sozinho com transição suave; pausa ao passar o mouse.
 *  - grafico → widget embutível (TradingView)
 *  - imagem  → imagem com legenda
 *
 * Arrastável pelo cabeçalho (framer-motion). Aceita `items` (lista) para o
 * carrossel ou campos planos (card único / gráfico / imagem).
 */

'use client';

import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

export interface VisorNewsItem {
  titulo?: string;
  resumo?: string;
  imagem?: string;
  fonte?: string;
  url?: string;
  fala?: string;  // versão conversacional ("com as palavras dela") para a narração
}

export interface VisorContent {
  tipo: 'noticia' | 'grafico' | 'imagem' | string;
  titulo?: string;
  resumo?: string;
  imagem?: string;
  fonte?: string;
  url?: string;
  ativo?: string;
  embed_url?: string;
  legenda?: string;
  items?: VisorNewsItem[];
  comentario?: string;  // opinião/leitura final dela sobre o conjunto de notícias
}

interface Props {
  content: VisorContent | null;
  onClose: () => void;
  /** Índice controlado externamente (sincronizado com a narração por voz).
   *  Quando é número, o carrossel mostra esse card e NÃO gira sozinho. */
  activeIndex?: number | null;
}

function NewsCard({ item }: { item: VisorNewsItem }) {
  return (
    <div className="flex gap-4 p-4">
      {item.imagem ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={item.imagem}
          alt=""
          className="w-44 h-44 flex-shrink-0 rounded-xl object-cover bg-zinc-800"
          draggable={false}
        />
      ) : (
        <div className="w-44 h-44 flex-shrink-0 rounded-xl bg-zinc-800/70 flex items-center justify-center">
          <span className="text-cyan-500/40 text-3xl">▤</span>
        </div>
      )}
      <div className="flex-1 min-w-0 flex flex-col">
        {item.titulo ? (
          <h3 className="text-base font-semibold text-zinc-100 leading-snug">{item.titulo}</h3>
        ) : null}
        {item.resumo ? (
          <p className="mt-2 text-sm text-zinc-400 leading-relaxed line-clamp-4">{item.resumo}</p>
        ) : null}
        <div className="mt-auto pt-3 flex items-center justify-between">
          {item.fonte ? (
            <span className="text-[10px] font-mono uppercase tracking-wider text-cyan-500/70">
              {item.fonte}
            </span>
          ) : <span />}
          {item.url ? (
            <a
              href={item.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[10px] font-mono text-zinc-400 hover:text-cyan-300 transition-colors"
            >
              abrir no navegador →
            </a>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export function Visor({ content, onClose, activeIndex }: Props) {
  const isNoticia = content?.tipo === 'noticia';

  // Lista de itens do carrossel (usa items[]; senão monta 1 a partir dos campos planos)
  const items: VisorNewsItem[] =
    isNoticia && content
      ? (content.items && content.items.length ? content.items : [content])
      : [];

  const controlado = typeof activeIndex === 'number';
  const [idx, setIdx] = useState(0);
  const [paused, setPaused] = useState(false);

  // Reinicia ao trocar de conteúdo
  useEffect(() => { setIdx(0); }, [content]);

  // Auto-rotação só quando NÃO está sob controle da narração e sem hover
  useEffect(() => {
    if (controlado || !isNoticia || items.length <= 1 || paused) return;
    const t = setInterval(() => setIdx((i) => (i + 1) % items.length), 7000);
    return () => clearInterval(t);
  }, [controlado, isNoticia, items.length, paused]);

  if (!content) return null;

  const posClass = isNoticia
    ? 'bottom-6 left-0 right-0 mx-auto w-[640px] max-w-[94vw]'
    : 'right-5 top-24 w-[380px] max-w-[92vw]';

  const baseIdx = controlado ? (activeIndex as number) : idx;
  const safeIdx = items.length ? ((baseIdx % items.length) + items.length) % items.length : 0;

  return (
    <motion.div
      drag
      dragMomentum={false}
      dragElastic={0.05}
      onHoverStart={() => setPaused(true)}
      onHoverEnd={() => setPaused(false)}
      initial={{ opacity: 0, scale: 0.97 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className={`fixed ${posClass} z-40 rounded-2xl border border-cyan-500/30
                  bg-zinc-950/90 backdrop-blur-xl shadow-2xl shadow-cyan-950/40 overflow-hidden`}
    >
      {/* Header (alça de arrastar) */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-cyan-500/15 cursor-move select-none">
        <span className="text-[10px] font-mono tracking-[0.22em] uppercase text-cyan-400/80">
          {content.tipo === 'grafico' ? 'Gráfico' : content.tipo === 'imagem' ? 'Visor' : 'Notícias'}
          {isNoticia && items.length > 1 ? `  ${safeIdx + 1}/${items.length}` : ''}
        </span>
        <button
          onClick={onClose}
          onPointerDownCapture={(e) => e.stopPropagation()}
          className="text-zinc-500 hover:text-cyan-300 transition-colors text-sm px-1"
          title="Fechar visor"
        >
          ✕
        </button>
      </div>

      {/* NOTÍCIA: carrossel com transição suave */}
      {isNoticia ? (
        <div className="relative">
          <AnimatePresence mode="wait">
            <motion.div
              key={safeIdx}
              initial={{ opacity: 0, x: 24 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -24 }}
              transition={{ duration: 0.4, ease: 'easeInOut' }}
            >
              <NewsCard item={items[safeIdx]} />
            </motion.div>
          </AnimatePresence>

          {/* Indicadores (bolinhas) */}
          {items.length > 1 ? (
            <div className="flex justify-center gap-1.5 pb-3 -mt-1">
              {items.map((_, i) => (
                <button
                  key={i}
                  onClick={() => setIdx(i)}
                  onPointerDownCapture={(e) => e.stopPropagation()}
                  className={`h-1.5 rounded-full transition-all ${
                    i === safeIdx ? 'w-5 bg-cyan-400' : 'w-1.5 bg-zinc-600 hover:bg-zinc-500'
                  }`}
                  aria-label={`Notícia ${i + 1}`}
                />
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      {/* GRÁFICO */}
      {content.tipo === 'grafico' && content.embed_url ? (
        <div className="relative w-full h-[340px] bg-black">
          <iframe
            key={content.embed_url}
            src={content.embed_url}
            title={content.titulo || 'Gráfico'}
            className="absolute inset-0 w-full h-full"
            allow="clipboard-write"
          />
        </div>
      ) : null}

      {/* IMAGEM */}
      {content.tipo === 'imagem' && content.url ? (
        <div className="p-2">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={content.url} alt={content.legenda || ''} className="w-full rounded-lg" draggable={false} />
          {content.legenda ? (
            <p className="mt-2 px-1 text-xs text-zinc-300 font-mono">{content.legenda}</p>
          ) : null}
        </div>
      ) : null}
    </motion.div>
  );
}
