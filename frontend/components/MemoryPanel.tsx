'use client'

/**
 * MemoryPanel — gaveta lateral esquerda: "o que ela aprendeu sobre você".
 *
 * Carrega GET /profile ao abrir: fatos semânticos (agrupados por categoria),
 * diários da reflexão e metadados do último ciclo. Botão "Refletir agora"
 * dispara POST /reflect e recarrega.
 *
 * Mesmo vidro escuro do ChatOverlay, espelhado para a esquerda.
 */

import { useCallback, useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, BrainCircuit, RefreshCw, BookOpen, Compass, Clock, Pencil, Trash2, Check, ShieldCheck, Activity } from 'lucide-react'

interface Fato {
  id?: number
  categoria: string
  chave: string
  valor: string
  fonte: string
  atualizado_em: string
}

interface SkillPendente {
  id: string
  nome: string
  descricao: string
  texto: string
  texto_atual: string
  edita: boolean
}

interface PropostaGuarda {
  id: string
  licao: string
  regra: { acao: string; tipo: string }
  status: string
}

interface Melhoria {
  id: string
  tipo: 'skill' | 'regra' | 'ferramenta' | 'prompt' | 'permissao'
  titulo: string
  porque: string
  acao: string
  status: string
}

interface GrupoLacuna {
  tipo: string
  ferramenta: string
  acao: string
  causa: string
  n: number
}

interface ResumoEvals {
  casos: number
  avaliaveis: number
  sem_checagem: number
  regras_fora_do_prompt: string[]
  custo_estimado_chamadas: number
}

interface ResultadoEval {
  passaram?: number
  total?: number
  regrediu?: string[]
  melhorou?: string[]
  motivo?: string
}

interface PluginPendente {
  id: string
  nome: string
  descricao: string
  codigo: string
  testes: string
  avisos: string[]
  resultado_testes: { ok: boolean; passaram?: number; falhas?: string[] } | null
  testes_ok_sha: string
  sha: string
  relatorio: { criticos: string[]; avisos: string[] }
}

interface Painel {
  alertas: string[]
  custo?: { chamadas: number; usd: number; projecao_mes_usd: number; taxa_cache: number; top: { funcao: string; chamadas: number; usd: number }[]; erro?: string }
  latencia?: { pedidos: number; etapas: Record<string, { n: number; p50_ms: number; p95_ms: number }>; erro?: string }
  lacunas?: { total_7d: number; erro?: string }
  backups?: { total: number; ultimo: string | null; hoje: boolean; erro?: string }
  pendentes?: { skills: number; ferramentas: number; melhorias: number; regras: number; erro?: string }
  seguranca?: { token_modo: string; aprovacao_modo: string; mcp_ativo: boolean; erro?: string }
}

interface PendenciaAberta {
  id: string
  texto: string
  proximo_passo: string
  toques: number
}

interface Diario {
  resumo: string
  data: string
}

interface Descoberta {
  texto: string
  data: string
}

interface Profile {
  fatos: Fato[]
  diarios: Diario[]
  descobertas?: Descoberta[]
  ultima_reflexao_ts?: number
  fatos_na_ultima_reflexao?: number
  ultima_curiosidade_ts?: number
}

// Item unificado da linha do tempo (diário + descoberta), do mais novo ao mais velho
interface TimelineItem {
  tipo: 'diario' | 'descoberta'
  texto: string
  data: string
}

function dataCurta(iso?: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso.slice(0, 10)
  return d.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' }) +
    ' ' + d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
}

interface MemoryPanelProps {
  isOpen: boolean
  httpBase: string
  onClose: () => void
}

const panelVariants = {
  hidden: {
    x: '-100%',
    opacity: 0,
    transition: { duration: 0.32, ease: [0.4, 0, 1, 1] as [number, number, number, number] },
  },
  visible: {
    x: 0,
    opacity: 1,
    transition: { duration: 0.38, ease: [0, 0, 0.2, 1] as [number, number, number, number] },
  },
}

function tempoRelativo(ts?: number): string {
  if (!ts) return 'nunca'
  const diffMin = Math.floor((Date.now() / 1000 - ts) / 60)
  if (diffMin < 1) return 'agora há pouco'
  if (diffMin < 60) return `há ${diffMin} min`
  const h = Math.floor(diffMin / 60)
  if (h < 24) return `há ${h}h`
  return `há ${Math.floor(h / 24)} dia(s)`
}

type ConflitoMemoria = { id: number; memory_id: number; proposto: string; atual: string; category: string; key: string }
type SaudeMemoria = { fatos: number; por_fonte: Record<string, number>; nunca_usados: number; esqueciveis: number; conflitos: number; do_mundo: number }

export function MemoryPanel({ isOpen, httpBase, onClose }: MemoryPanelProps) {
  const [profile, setProfile] = useState<Profile | null>(null)
  const [loading, setLoading] = useState(false)
  const [reflecting, setReflecting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [aba, setAba] = useState<'sabe' | 'timeline' | 'aprovacoes' | 'saude'>('sabe')
  // Edição de fatos (B12): corrigir ou esquecer o que ela aprendeu errado. Sem LLM.
  const [editando, setEditando] = useState<number | null>(null)
  const [rascunho, setRascunho] = useState('')
  const [apagando, setApagando] = useState<number | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const r = await fetch(`${httpBase}/profile`)
      if (!r.ok) throw new Error(`profile ${r.status}`)
      setProfile(await r.json())
    } catch {
      setError('Não consegui falar com o backend.')
    } finally {
      setLoading(false)
    }
  }, [httpBase])

  // Aprovações (B7/B13): skills que ela propôs e regras sugeridas a partir das suas correções.
  // Só VOCÊ decide aqui; o modelo não tem acesso a estas rotas.
  const [skills, setSkills] = useState<{ pendentes: SkillPendente[]; skills: { nome: string; descricao: string }[] }>({ pendentes: [], skills: [] })
  const [propostas, setPropostas] = useState<PropostaGuarda[]>([])
  const [aviso, setAviso] = useState<string | null>(null)
  const [melhorias, setMelhorias] = useState<Melhoria[]>([])
  const [lacunas, setLacunas] = useState<{ total: number; grupos: GrupoLacuna[] }>({ total: 0, grupos: [] })
  const [revisando, setRevisando] = useState(false)
  const [evals, setEvals] = useState<ResumoEvals | null>(null)
  const [resultadoEval, setResultadoEval] = useState<ResultadoEval | null>(null)
  const [rodandoEval, setRodandoEval] = useState(false)
  const [painel, setPainel] = useState<Painel | null>(null)
  const [pendencias, setPendencias] = useState<PendenciaAberta[]>([])
  const [plugins, setPlugins] = useState<PluginPendente[]>([])
  const [conflitos, setConflitos] = useState<ConflitoMemoria[]>([])
  const [saudeMem, setSaudeMem] = useState<SaudeMemoria | null>(null)
  const [testandoPlugin, setTestandoPlugin] = useState<string | null>(null)

  const decidirConflito = async (id: number, acao: 'aceitar' | 'manter') => {
    const r = await fetch(`${httpBase}/memoria/conflitos/${id}/${acao}`, { method: 'POST' })
    if (r.ok) {
      setConflitos((cs) => cs.filter((c) => c.id !== id))
      if (acao === 'aceitar') void load()
    } else setAviso('Não consegui resolver o conflito.')
  }

  const carregarAprovacoes = useCallback(async () => {
    try {
      const [a, b, c, d, e, f, g, h] = await Promise.all([
        fetch(`${httpBase}/skills`), fetch(`${httpBase}/guardas/propostas`),
        fetch(`${httpBase}/melhorias`), fetch(`${httpBase}/lacunas`), fetch(`${httpBase}/evals`), fetch(`${httpBase}/plugins`), fetch(`${httpBase}/pendencias`), fetch(`${httpBase}/memoria/conflitos`),
      ])
      if (a.ok) setSkills(await a.json())
      if (b.ok) setPropostas(((await b.json()).propostas ?? []) as PropostaGuarda[])
      if (c.ok) setMelhorias(((await c.json()).melhorias ?? []) as Melhoria[])
      if (d.ok) setLacunas(await d.json())
      if (e.ok) setEvals(await e.json())
      if (f.ok) setPlugins(((await f.json()).pendentes ?? []) as PluginPendente[])
      if (g.ok) setPendencias(((await g.json()).abertas ?? []) as PendenciaAberta[])
      if (h.ok) setConflitos(((await h.json()).conflitos ?? []) as ConflitoMemoria[])
    } catch {
      setError('Não consegui carregar as aprovações.')
    }
  }, [httpBase])

  const decidirSkill = useCallback(async (id: string, decisao: 'aprovar' | 'rejeitar' | 'quarentena') => {
    const r = await fetch(`${httpBase}/skills/pendentes/${id}/${decisao}`, { method: 'POST' })
    const j = await r.json().catch(() => ({}))
    setAviso(j.mensagem && !j.ok ? String(j.mensagem) : null)
    await carregarAprovacoes()
  }, [httpBase, carregarAprovacoes])

  const decidirMelhoria = useCallback(async (id: string, decisao: 'aceitar' | 'rejeitar') => {
    const r = await fetch(`${httpBase}/melhorias/${id}/${decisao}`, { method: 'POST' })
    const j = await r.json().catch(() => ({}))
    setAviso(j.mensagem ? String(j.mensagem) : null)
    await carregarAprovacoes()
  }, [httpBase, carregarAprovacoes])

  const revisarAgora = useCallback(async () => {
    setRevisando(true)
    try {
      const r = await fetch(`${httpBase}/melhorias/revisar`, { method: 'POST' })
      const j = await r.json().catch(() => ({}))
      setAviso(j.motivo ? String(j.motivo) : j.novas ? `${j.novas} sugestão(ões) nova(s).` : null)
      await carregarAprovacoes()
    } finally {
      setRevisando(false)
    }
  }, [httpBase, carregarAprovacoes])

  const testarPlugin = useCallback(async (id: string) => {
    setTestandoPlugin(id)
    try {
      await fetch(`${httpBase}/plugins/${id}/testar`, { method: 'POST' })
      await carregarAprovacoes()
    } finally {
      setTestandoPlugin(null)
    }
  }, [httpBase, carregarAprovacoes])

  const decidirPlugin = useCallback(async (id: string, decisao: 'aprovar' | 'rejeitar', leitura = false) => {
    const r = await fetch(`${httpBase}/plugins/${id}/${decisao}?leitura=${leitura}`, { method: 'POST' })
    const j = await r.json().catch(() => ({}))
    setAviso(j.mensagem ? String(j.mensagem) : null)
    await carregarAprovacoes()
  }, [httpBase, carregarAprovacoes])

  const decidirPendencia = useCallback(async (id: string, estado: 'resolvida' | 'dispensada') => {
    await fetch(`${httpBase}/pendencias/${id}/${estado}`, { method: 'POST' })
    await carregarAprovacoes()
  }, [httpBase, carregarAprovacoes])

  const rodarEvals = useCallback(async () => {
    const n = evals?.custo_estimado_chamadas ?? 0
    // O custo é dito ANTES: nunca roda sozinho.
    if (!n || !window.confirm(`Isto faz ${n} chamada(s) ao modelo (uma por caso). Rodar agora?`)) return
    setRodandoEval(true)
    try {
      const r = await fetch(`${httpBase}/evals/rodar`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ confirmar: true }),
      })
      setResultadoEval(await r.json())
    } finally {
      setRodandoEval(false)
    }
  }, [httpBase, evals])

  const decidirGuarda = useCallback(async (id: string, decisao: 'aceitar' | 'rejeitar') => {
    await fetch(`${httpBase}/guardas/propostas/${id}/${decisao}`, { method: 'POST' })
    await carregarAprovacoes()
  }, [httpBase, carregarAprovacoes])

  useEffect(() => {
    if (isOpen && aba === 'aprovacoes') void carregarAprovacoes()
  }, [isOpen, aba, carregarAprovacoes])

  useEffect(() => {
    if (!isOpen || aba !== 'saude') return
    fetch(`${httpBase}/memoria/saude`).then((r) => (r.ok ? r.json() : null)).then((j) => j && setSaudeMem(j as SaudeMemoria)).catch(() => undefined)
    fetch(`${httpBase}/painel`).then((r) => (r.ok ? r.json() : null)).then((j) => j && setPainel(j)).catch(() => setError('Não consegui carregar o painel.'))
  }, [isOpen, aba, httpBase])

  const salvarFato = useCallback(async (id: number) => {
    const valor = rascunho.trim()
    if (!valor) return
    try {
      const r = await fetch(`${httpBase}/memoria/fatos/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ valor }),
      })
      if (!r.ok) throw new Error(`editar ${r.status}`)
      setEditando(null)
      await load()
    } catch {
      setError('Não consegui salvar a correção.')
    }
  }, [httpBase, rascunho, load])

  const apagarFato = useCallback(async (id: number) => {
    try {
      const r = await fetch(`${httpBase}/memoria/fatos/${id}`, { method: 'DELETE' })
      if (!r.ok) throw new Error(`apagar ${r.status}`)
      setApagando(null)
      await load()
    } catch {
      setError('Não consegui esquecer esse fato.')
    }
  }, [httpBase, load])

  useEffect(() => {
    if (isOpen) void load()
  }, [isOpen, load])

  const refletirAgora = useCallback(async () => {
    setReflecting(true)
    try {
      await fetch(`${httpBase}/reflect`, { method: 'POST' })
      await load()
    } catch {
      setError('A reflexão falhou — backend offline?')
    } finally {
      setReflecting(false)
    }
  }, [httpBase, load])

  // Agrupa fatos por categoria preservando a ordem de chegada
  const grupos = new Map<string, Fato[]>()
  for (const f of profile?.fatos ?? []) {
    const cat = f.categoria || 'geral'
    if (!grupos.has(cat)) grupos.set(cat, [])
    grupos.get(cat)!.push(f)
  }

  // Fato aprendido sozinha na internet? (curiosidade)
  const ehCuriosidade = (f: Fato) =>
    f.fonte === 'curiosidade' || f.categoria === 'aprendizado'

  // Linha do tempo: diários + descobertas, do mais recente ao mais antigo
  const timeline: TimelineItem[] = [
    ...(profile?.diarios ?? []).map((d) => ({ tipo: 'diario' as const, texto: d.resumo, data: d.data })),
    ...(profile?.descobertas ?? []).map((d) => ({ tipo: 'descoberta' as const, texto: d.texto, data: d.data })),
  ]
    .filter((t) => t.texto)
    .sort((a, b) => (b.data || '').localeCompare(a.data || ''))

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div
            key="memory-backdrop"
            className="fixed inset-0 z-40"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={onClose}
          />

          <motion.aside
            key="memory-panel"
            className="fixed left-0 top-0 bottom-0 z-50 flex flex-col"
            style={{
              width: 'min(420px, 92vw)',
              background: 'linear-gradient(200deg, rgba(10,20,30,0.84), rgba(6,13,22,0.80))',
              backdropFilter: 'blur(20px)',
              WebkitBackdropFilter: 'blur(20px)',
              borderRight: '1px solid rgba(6,182,212,0.12)',
              boxShadow: '24px 0 80px rgba(0,0,0,0.50), inset -1px 0 0 rgba(255,255,255,0.05)',
            }}
            variants={panelVariants}
            initial="hidden"
            animate="visible"
            exit="hidden"
          >
            {/* Cabeçalho */}
            <div
              className="flex items-center justify-between px-5 py-4 shrink-0"
              style={{ borderBottom: '1px solid rgba(6,182,212,0.10)' }}
            >
              <div className="flex items-center gap-2.5">
                <BrainCircuit size={16} style={{ color: 'rgba(6,182,212,0.85)' }} />
                <span
                  className="text-sm font-semibold tracking-widest uppercase"
                  style={{ color: 'rgba(6,182,212,0.85)', letterSpacing: '0.12em' }}
                >
                  Memória
                </span>
              </div>
              <button
                onClick={onClose}
                className="flex items-center justify-center w-8 h-8 rounded-full transition-colors text-slate-400 hover:text-slate-100"
                aria-label="Fechar memória"
              >
                <X size={16} />
              </button>
            </div>

            {/* Meta do último ciclo */}
            <div
              className="px-5 py-3 shrink-0 flex items-center justify-between text-[11px] font-mono text-slate-400"
              style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}
            >
              <span>
                última reflexão: {tempoRelativo(profile?.ultima_reflexao_ts)}
                {profile?.fatos_na_ultima_reflexao
                  ? ` · ${profile.fatos_na_ultima_reflexao} fato(s)`
                  : ''}
              </span>
              <button
                onClick={refletirAgora}
                disabled={reflecting}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg transition-all disabled:opacity-40"
                style={{
                  background: 'rgba(6,182,212,0.10)',
                  border: '1px solid rgba(6,182,212,0.20)',
                  color: 'rgba(6,182,212,0.90)',
                }}
                title="Disparar uma rodada de reflexão agora"
              >
                <RefreshCw size={11} className={reflecting ? 'animate-spin' : ''} />
                refletir
              </button>
            </div>

            {/* Abas: o que ela sabe × linha do tempo */}
            <div className="flex gap-1 px-5 pt-3 shrink-0">
              {([['sabe', 'O que ela sabe'], ['timeline', 'Linha do tempo'], ['aprovacoes', 'Aprovações'], ['saude', 'Saúde']] as const).map(([id, label]) => (
                <button
                  key={id}
                  onClick={() => setAba(id)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-mono transition-all"
                  style={{
                    background: aba === id ? 'rgba(6,182,212,0.14)' : 'transparent',
                    border: `1px solid ${aba === id ? 'rgba(6,182,212,0.28)' : 'rgba(255,255,255,0.06)'}`,
                    color: aba === id ? 'rgba(6,182,212,0.95)' : 'rgba(148,163,184,0.7)',
                  }}
                >
                  {id === 'timeline' ? <Clock size={11} /> : id === 'aprovacoes' ? <ShieldCheck size={11} /> : id === 'saude' ? <Activity size={11} /> : <BrainCircuit size={11} />}
                  {label}
                </button>
              ))}
            </div>

            {/* Conteúdo */}
            <div className="flex-1 overflow-y-auto px-5 py-4 custom-scrollbar">
              {aba === 'saude' ? (
                <div className="flex flex-col gap-4 text-sm">
                  {!painel ? <p className="text-slate-500 font-mono animate-pulse">carregando…</p> : (
                    <>
                      {painel.alertas.length ? (
                        <ul className="rounded-xl border border-amber-400/25 bg-amber-400/5 p-3 text-xs text-amber-200 space-y-1">
                          {painel.alertas.map((a, i) => <li key={i}>• {a}</li>)}
                        </ul>
                      ) : <p className="text-emerald-300/90 text-xs">Tudo em ordem.</p>}
                      {saudeMem ? (
                        <div className="rounded-xl border border-white/10 bg-slate-900/60 p-3 text-xs text-slate-300">
                          <div className="text-[10px] font-mono uppercase tracking-wider text-cyan-300/80 mb-1">Memória</div>
                          <div>{saudeMem.fatos} fatos · {saudeMem.do_mundo} curiosidades da web · {saudeMem.nunca_usados} nunca usados</div>
                          <div className="text-slate-400">
                            Fonte: {Object.entries(saudeMem.por_fonte).map(([k, v]) => `${k} ${v}`).join(' · ')}
                          </div>
                          {saudeMem.esqueciveis || saudeMem.conflitos ? (
                            <div className="text-amber-200 mt-1">{saudeMem.esqueciveis} esquecíveis · {saudeMem.conflitos} conflito(s) esperando você</div>
                          ) : null}
                        </div>
                      ) : null}
                      <div className="grid grid-cols-2 gap-2 text-xs">
                        {painel.custo && !painel.custo.erro ? (
                          <div className="rounded-xl border border-white/10 bg-slate-900/60 p-3">
                            <div className="text-[10px] font-mono uppercase text-cyan-300/80">Gasto (24 h)</div>
                            <div className="text-lg text-slate-100">US$ {painel.custo.usd.toFixed(3)}</div>
                            <div className="text-slate-400">{painel.custo.chamadas} chamadas · projeção US$ {painel.custo.projecao_mes_usd}/mês</div>
                          </div>
                        ) : null}
                        {painel.latencia && !painel.latencia.erro ? (
                          <div className="rounded-xl border border-white/10 bg-slate-900/60 p-3">
                            <div className="text-[10px] font-mono uppercase text-cyan-300/80">Velocidade</div>
                            <div className="text-slate-200">resposta: {painel.latencia.etapas.total ? `${Math.round(painel.latencia.etapas.total.p50_ms / 100) / 10}s (p50)` : '—'}</div>
                            <div className="text-slate-400">1º áudio: {painel.latencia.etapas.primeiro_audio ? `${Math.round(painel.latencia.etapas.primeiro_audio.p50_ms / 100) / 10}s` : '—'}</div>
                          </div>
                        ) : null}
                        {painel.lacunas && !painel.lacunas.erro ? (
                          <div className="rounded-xl border border-white/10 bg-slate-900/60 p-3">
                            <div className="text-[10px] font-mono uppercase text-cyan-300/80">Falhas (7 dias)</div>
                            <div className="text-lg text-slate-100">{painel.lacunas.total_7d}</div>
                          </div>
                        ) : null}
                        {painel.backups && !painel.backups.erro ? (
                          <div className="rounded-xl border border-white/10 bg-slate-900/60 p-3">
                            <div className="text-[10px] font-mono uppercase text-cyan-300/80">Backup</div>
                            <div className={painel.backups.hoje ? 'text-emerald-300' : 'text-amber-300'}>{painel.backups.hoje ? 'de hoje ok' : `último: ${painel.backups.ultimo ?? 'nenhum'}`}</div>
                          </div>
                        ) : null}
                        {painel.pendentes && !painel.pendentes.erro ? (
                          <div className="rounded-xl border border-white/10 bg-slate-900/60 p-3">
                            <div className="text-[10px] font-mono uppercase text-cyan-300/80">Esperando você</div>
                            <div className="text-lg text-slate-100">{painel.pendentes.skills + painel.pendentes.ferramentas + painel.pendentes.melhorias + painel.pendentes.regras}</div>
                          </div>
                        ) : null}
                        {painel.seguranca && !painel.seguranca.erro ? (
                          <div className="rounded-xl border border-white/10 bg-slate-900/60 p-3">
                            <div className="text-[10px] font-mono uppercase text-cyan-300/80">Segurança</div>
                            <div className="text-slate-200">token: {painel.seguranca.token_modo}</div>
                            <div className="text-slate-400">aprovação: {painel.seguranca.aprovacao_modo}</div>
                          </div>
                        ) : null}
                      </div>
                      {painel.custo?.top?.length ? (
                        <div className="text-xs text-slate-400">
                          <div className="mb-1 text-[10px] font-mono uppercase text-cyan-300/80">Onde o gasto vai</div>
                          {painel.custo.top.map((t) => <div key={t.funcao}>{t.chamadas}× {t.funcao} · US$ {t.usd.toFixed(4)}</div>)}
                        </div>
                      ) : null}
                    </>
                  )}
                </div>
              ) : aba === 'aprovacoes' ? (
                <div className="flex flex-col gap-5 text-sm">
                  {aviso ? <p className="text-rose-300/90 text-xs">{aviso}</p> : null}
                  <section aria-label="Conflitos de memória">
                    <h3 className="mb-2 text-[10px] font-mono uppercase tracking-wider text-cyan-300/80">Memória: quero mudar um fato seu</h3>
                    {conflitos.length === 0 ? (
                      <p className="text-slate-500 text-xs">Nenhum conflito. Quando eu deduzir algo diferente do que você definiu, pergunto aqui em vez de sobrescrever.</p>
                    ) : conflitos.map((c) => (
                      <div key={c.id} className="mb-3 rounded-xl border border-white/10 bg-slate-900/60 p-3 text-xs">
                        <div className="text-[10px] font-mono text-slate-500 mb-1">{c.category} · {c.key}</div>
                        <div className="text-slate-300">Hoje: <span className="text-slate-100">{c.atual}</span></div>
                        <div className="text-slate-300">Eu deduzi: <span className="text-amber-200">{c.proposto}</span></div>
                        <div className="mt-2 flex gap-2">
                          <button onClick={() => void decidirConflito(c.id, 'aceitar')} className="px-2.5 py-1 rounded-lg text-xs text-cyan-200 bg-cyan-500/15 hover:bg-cyan-500/25">Aceitar a nova</button>
                          <button onClick={() => void decidirConflito(c.id, 'manter')} className="px-2.5 py-1 rounded-lg text-xs text-slate-300 bg-white/5 hover:bg-white/10">Manter a atual</button>
                        </div>
                      </div>
                    ))}
                  </section>
                  <section aria-label="Skills propostas">
                    <h3 className="mb-2 text-[10px] font-mono uppercase tracking-wider text-cyan-300/80">Skills propostas</h3>
                    {skills.pendentes.length === 0 ? (
                      <p className="text-slate-500 text-xs">Nada esperando aprovação.</p>
                    ) : skills.pendentes.map((p) => (
                      <div key={p.id} className="mb-3 rounded-xl border border-white/10 bg-slate-900/60 p-3">
                        <div className="font-medium text-slate-100">{p.nome}{p.edita ? <span className="ml-2 text-[10px] text-amber-300">edição</span> : null}</div>
                        <div className="text-xs text-slate-400 mb-2">{p.descricao}</div>
                        <pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded-lg bg-black/30 p-2 text-[11px] text-slate-300">{p.texto}</pre>
                        {p.edita ? (
                          <details className="mt-1 text-[11px] text-slate-500"><summary>versão atual</summary>
                            <pre className="max-h-32 overflow-auto whitespace-pre-wrap">{p.texto_atual}</pre>
                          </details>
                        ) : null}
                        <div className="mt-2 flex gap-2">
                          <button onClick={() => void decidirSkill(p.id, 'aprovar')} className="px-2.5 py-1 rounded-lg text-xs text-cyan-200 bg-cyan-500/15 hover:bg-cyan-500/25">Aprovar</button>
                          <button onClick={() => void decidirSkill(p.id, 'rejeitar')} className="px-2.5 py-1 rounded-lg text-xs text-slate-300 bg-white/5 hover:bg-white/10">Rejeitar</button>
                          <button onClick={() => void decidirSkill(p.id, 'quarentena')} className="px-2.5 py-1 rounded-lg text-xs text-rose-300 bg-rose-500/10 hover:bg-rose-500/20">Quarentena</button>
                        </div>
                      </div>
                    ))}
                    {skills.skills.length ? (
                      <p className="mt-2 text-[11px] text-slate-500">Aprovadas: {skills.skills.map((x) => x.nome).join(', ')}</p>
                    ) : null}
                  </section>
                  <section aria-label="Pendências em aberto">
                    <h3 className="mb-2 text-[10px] font-mono uppercase tracking-wider text-cyan-300/80">Pendências que ela acompanha</h3>
                    {pendencias.length === 0 ? (
                      <p className="text-slate-500 text-xs">Nada em aberto. Ela anota o que você diz que ainda vai decidir ou fazer, e retoma no máximo 1 por dia, 3 vezes por item.</p>
                    ) : pendencias.map((pd) => (
                      <div key={pd.id} className="mb-2 rounded-xl border border-white/10 bg-slate-900/60 p-3">
                        <div className="text-slate-100">{pd.texto}</div>
                        {pd.proximo_passo ? <div className="text-xs text-slate-400">Próximo passo: {pd.proximo_passo}</div> : null}
                        <div className="mt-2 flex items-center gap-2">
                          <button onClick={() => void decidirPendencia(pd.id, 'resolvida')} className="px-2.5 py-1 rounded-lg text-xs text-emerald-200 bg-emerald-500/15 hover:bg-emerald-500/25">Já resolvi</button>
                          <button onClick={() => void decidirPendencia(pd.id, 'dispensada')} className="px-2.5 py-1 rounded-lg text-xs text-slate-300 bg-white/5 hover:bg-white/10">Dispensar</button>
                          <span className="ml-auto text-[10px] text-slate-500">{pd.toques}/3 lembretes</span>
                        </div>
                      </div>
                    ))}
                  </section>
                  <section aria-label="Ferramentas propostas">
                    <h3 className="mb-2 text-[10px] font-mono uppercase tracking-wider text-cyan-300/80">Ferramentas que ela propôs (código em quarentena)</h3>
                    {plugins.length === 0 ? (
                      <p className="text-slate-500 text-xs">Nenhuma proposta. Nada roda sem você ler, testar e aprovar.</p>
                    ) : plugins.map((pl) => {
                      const testesPassaram = pl.testes_ok_sha === pl.sha && pl.testes_ok_sha !== ''
                      return (
                        <div key={pl.id} className="mb-3 rounded-xl border border-white/10 bg-slate-900/60 p-3">
                          <div className="font-medium text-slate-100">agente_{pl.nome}</div>
                          <div className="text-xs text-slate-400 mb-2">{pl.descricao}</div>
                          {pl.relatorio.criticos.length ? (
                            <p className="mb-1 text-xs text-rose-300">Bloqueada pelo scanner: {pl.relatorio.criticos.join('; ')}</p>
                          ) : null}
                          {pl.relatorio.avisos.length ? (
                            <p className="mb-1 text-xs text-amber-300">Atenção: {pl.relatorio.avisos.join('; ')}</p>
                          ) : null}
                          <details className="text-[11px] text-slate-400" open>
                            <summary>código</summary>
                            <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-lg bg-black/30 p-2 text-slate-300">{pl.codigo}</pre>
                          </details>
                          <details className="mt-1 text-[11px] text-slate-400">
                            <summary>testes</summary>
                            <pre className="max-h-32 overflow-auto whitespace-pre-wrap rounded-lg bg-black/30 p-2 text-slate-300">{pl.testes}</pre>
                          </details>
                          {pl.resultado_testes ? (
                            <p className={`mt-1 text-xs ${pl.resultado_testes.ok ? 'text-emerald-300' : 'text-rose-300'}`}>
                              {pl.resultado_testes.ok ? `Testes passaram (${pl.resultado_testes.passaram}).` : `Testes falharam: ${(pl.resultado_testes.falhas ?? []).join('; ')}`}
                            </p>
                          ) : null}
                          <div className="mt-2 flex flex-wrap gap-2">
                            <button onClick={() => void testarPlugin(pl.id)} disabled={testandoPlugin === pl.id} className="px-2.5 py-1 rounded-lg text-xs text-cyan-200 bg-cyan-500/10 hover:bg-cyan-500/20 disabled:opacity-40">
                              {testandoPlugin === pl.id ? 'testando…' : 'Rodar testes'}
                            </button>
                            <button onClick={() => void decidirPlugin(pl.id, 'aprovar')} disabled={!testesPassaram || pl.relatorio.criticos.length > 0} className="px-2.5 py-1 rounded-lg text-xs text-cyan-200 bg-cyan-500/15 hover:bg-cyan-500/25 disabled:opacity-30" title={testesPassaram ? '' : 'Rode os testes primeiro'}>Aprovar</button>
                            <button onClick={() => void decidirPlugin(pl.id, 'rejeitar')} className="px-2.5 py-1 rounded-lg text-xs text-slate-300 bg-white/5 hover:bg-white/10">Rejeitar</button>
                          </div>
                          <p className="mt-1 text-[10px] text-slate-500">Aprovada, cada uso ainda pede o seu OK. Só vale depois de reiniciar a Quinta.</p>
                        </div>
                      )
                    })}
                  </section>
                  <section aria-label="Melhorias sugeridas">
                    <div className="mb-2 flex items-center justify-between">
                      <h3 className="text-[10px] font-mono uppercase tracking-wider text-cyan-300/80">Melhorias que ela sugere para si mesma</h3>
                      <button
                        onClick={() => void revisarAgora()}
                        disabled={revisando}
                        className="px-2 py-0.5 rounded-lg text-[10px] font-mono text-cyan-200 bg-cyan-500/10 hover:bg-cyan-500/20 disabled:opacity-40"
                        title="Roda a revisão das falhas agora (no máximo 1 chamada leve ao modelo)"
                      >{revisando ? 'revisando…' : 'revisar agora'}</button>
                    </div>
                    {melhorias.filter((m) => m.status === 'pendente').length === 0 ? (
                      <p className="text-slate-500 text-xs">Sem sugestões pendentes. A revisão roda uma vez por semana, se houver falhas suficientes.</p>
                    ) : melhorias.filter((m) => m.status === 'pendente').map((m) => (
                      <div key={m.id} className="mb-3 rounded-xl border border-white/10 bg-slate-900/60 p-3">
                        <div className="flex items-center gap-2">
                          <span className="rounded bg-cyan-500/15 px-1.5 py-0.5 text-[9px] font-mono uppercase text-cyan-200">{m.tipo}</span>
                          <span className="font-medium text-slate-100">{m.titulo}</span>
                        </div>
                        {m.porque ? <div className="mt-1 text-xs text-slate-400">{m.porque}</div> : null}
                        <div className="mt-1 text-[12.5px] text-slate-300">{m.acao}</div>
                        <div className="mt-2 flex gap-2">
                          <button onClick={() => void decidirMelhoria(m.id, 'aceitar')} className="px-2.5 py-1 rounded-lg text-xs text-cyan-200 bg-cyan-500/15 hover:bg-cyan-500/25">Aceitar</button>
                          <button onClick={() => void decidirMelhoria(m.id, 'rejeitar')} className="px-2.5 py-1 rounded-lg text-xs text-slate-300 bg-white/5 hover:bg-white/10">Rejeitar (não sugerir de novo)</button>
                        </div>
                      </div>
                    ))}
                    {lacunas.total > 0 ? (
                      <details className="mt-1 text-[11px] text-slate-500">
                        <summary>{lacunas.total} falha(s) registrada(s) nos últimos 7 dias</summary>
                        <ul className="mt-1 space-y-0.5">
                          {lacunas.grupos.slice(0, 8).map((g, i) => (
                            <li key={i}>{g.n}× {g.tipo}{g.ferramenta ? ` · ${g.ferramenta}` : ''}{g.acao ? `/${g.acao}` : ''} — {g.causa}</li>
                          ))}
                        </ul>
                      </details>
                    ) : null}
                  </section>
                  <section aria-label="Testes das suas correções">
                    <h3 className="mb-2 text-[10px] font-mono uppercase tracking-wider text-cyan-300/80">Testes feitos das suas correções</h3>
                    {!evals || evals.casos === 0 ? (
                      <p className="text-slate-500 text-xs">Ainda sem casos: cada correção sua vira um teste.</p>
                    ) : (
                      <div className="text-xs text-slate-300">
                        <p>{evals.casos} caso(s); {evals.avaliaveis} com checagem automática{evals.sem_checagem ? ` (${evals.sem_checagem} só de leitura)` : ''}.</p>
                        {evals.regras_fora_do_prompt.length ? (
                          <p className="mt-1 text-amber-300/90">
                            {evals.regras_fora_do_prompt.length} regra(s) que você ensinou não chegam ao prompt (só as mais reforçadas cabem).
                          </p>
                        ) : null}
                        <button
                          onClick={() => void rodarEvals()}
                          disabled={rodandoEval || evals.custo_estimado_chamadas === 0}
                          className="mt-2 px-2.5 py-1 rounded-lg text-xs text-cyan-200 bg-cyan-500/15 hover:bg-cyan-500/25 disabled:opacity-40"
                        >{rodandoEval ? 'rodando…' : `Rodar (${evals.custo_estimado_chamadas} chamada${evals.custo_estimado_chamadas === 1 ? '' : 's'})`}</button>
                        {resultadoEval?.total !== undefined ? (
                          <p className="mt-1">
                            {resultadoEval.passaram}/{resultadoEval.total} passaram
                            {resultadoEval.regrediu?.length ? <span className="text-rose-300"> · {resultadoEval.regrediu.length} regrediram</span> : null}
                            {resultadoEval.melhorou?.length ? <span className="text-emerald-300"> · {resultadoEval.melhorou.length} melhoraram</span> : null}
                          </p>
                        ) : resultadoEval?.motivo ? <p className="mt-1 text-slate-400">{resultadoEval.motivo}</p> : null}
                      </div>
                    )}
                  </section>
                  <section aria-label="Regras sugeridas">
                    <h3 className="mb-2 text-[10px] font-mono uppercase tracking-wider text-cyan-300/80">Regras sugeridas pelas suas correções</h3>
                    {propostas.filter((x) => x.status === 'pendente').length === 0 ? (
                      <p className="text-slate-500 text-xs">Nenhuma ainda: aparecem quando você corrige a mesma coisa 3 vezes.</p>
                    ) : propostas.filter((x) => x.status === 'pendente').map((g) => (
                      <div key={g.id} className="mb-3 rounded-xl border border-white/10 bg-slate-900/60 p-3">
                        <div className="text-slate-200">“{g.licao}”</div>
                        <div className="text-xs text-slate-400 my-1">Virar regra: não entregar avisos do tipo <b>{g.regra.tipo}</b> (os críticos continuam).</div>
                        <div className="flex gap-2">
                          <button onClick={() => void decidirGuarda(g.id, 'aceitar')} className="px-2.5 py-1 rounded-lg text-xs text-cyan-200 bg-cyan-500/15 hover:bg-cyan-500/25">Aceitar</button>
                          <button onClick={() => void decidirGuarda(g.id, 'rejeitar')} className="px-2.5 py-1 rounded-lg text-xs text-slate-300 bg-white/5 hover:bg-white/10">Rejeitar (não propor de novo)</button>
                        </div>
                      </div>
                    ))}
                  </section>
                </div>
              ) : loading && !profile ? (
                <p className="text-sm text-slate-500 font-mono animate-pulse">carregando memória...</p>
              ) : error ? (
                <p className="text-sm text-rose-400/80">{error}</p>
              ) : !profile?.fatos?.length && !profile?.diarios?.length ? (
                <div className="flex flex-col items-center justify-center h-full gap-2 text-center text-slate-500">
                  <BrainCircuit size={28} className="opacity-30" />
                  <p className="text-sm">Ela ainda não aprendeu nada sozinha.</p>
                  <p className="text-xs opacity-70">Converse mais — a reflexão roda a cada 6h.</p>
                </div>
              ) : aba === 'sabe' ? (
                <>
                  {/* Fatos por categoria */}
                  {[...grupos.entries()].map(([cat, fatos]) => (
                    <div key={cat} className="mb-5">
                      <span
                        className="inline-block mb-2 px-2 py-0.5 rounded-md text-[10px] font-mono uppercase tracking-wider"
                        style={{
                          background: 'rgba(6,182,212,0.10)',
                          border: '1px solid rgba(6,182,212,0.18)',
                          color: 'rgba(6,182,212,0.85)',
                        }}
                      >
                        {cat}
                      </span>
                      <ul className="flex flex-col gap-1.5">
                        {fatos.map((f, i) => (
                          <li
                            key={`${f.chave}_${i}`}
                            className="rounded-xl px-3 py-2 text-sm leading-relaxed"
                            style={{
                              background: ehCuriosidade(f) ? 'rgba(16,30,40,0.65)' : 'rgba(15,23,42,0.55)',
                              border: `1px solid ${ehCuriosidade(f) ? 'rgba(45,212,191,0.22)' : 'rgba(255,255,255,0.05)'}`,
                            }}
                          >
                            {ehCuriosidade(f) ? (
                              <span
                                className="inline-flex items-center gap-1 mr-1.5 px-1.5 py-0.5 rounded text-[9px] font-mono uppercase align-middle"
                                style={{ background: 'rgba(45,212,191,0.14)', color: 'rgba(94,234,212,0.9)' }}
                                title="Ela foi atrás disso sozinha na internet"
                              >
                                <Compass size={9} /> curiosidade
                              </span>
                            ) : (
                              <span className="text-slate-400">{f.chave.replaceAll('_', ' ')}: </span>
                            )}
                            {editando !== null && editando === f.id ? (
                              <span className="flex items-start gap-1.5 mt-1">
                                <textarea
                                  value={rascunho}
                                  onChange={(e) => setRascunho(e.target.value)}
                                  maxLength={500}
                                  rows={2}
                                  autoFocus
                                  className="flex-1 rounded-lg bg-slate-900/80 border border-cyan-500/30 px-2 py-1 text-sm text-slate-100 outline-none focus:border-cyan-400"
                                  aria-label="Corrigir este fato"
                                />
                                <button
                                  onClick={() => f.id !== undefined && void salvarFato(f.id)}
                                  className="p-1.5 rounded-lg text-cyan-300 hover:bg-cyan-500/15"
                                  aria-label="Salvar correção"
                                ><Check size={14} /></button>
                                <button
                                  onClick={() => setEditando(null)}
                                  className="p-1.5 rounded-lg text-slate-400 hover:bg-white/5"
                                  aria-label="Cancelar"
                                ><X size={14} /></button>
                              </span>
                            ) : (
                              <>
                                <span className="text-slate-200">{f.valor}</span>
                                {f.id !== undefined ? (
                                  <span className="float-right ml-2 flex items-center gap-0.5">
                                    {apagando === f.id ? (
                                      <>
                                        <button
                                          onClick={() => void apagarFato(f.id!)}
                                          className="px-1.5 py-0.5 rounded text-[10px] font-mono text-rose-300 bg-rose-500/15 hover:bg-rose-500/25"
                                        >esquecer?</button>
                                        <button onClick={() => setApagando(null)} className="p-1 text-slate-500 hover:text-slate-300" aria-label="Cancelar"><X size={12} /></button>
                                      </>
                                    ) : (
                                      <>
                                        <button
                                          onClick={() => { setEditando(f.id!); setRascunho(f.valor); setApagando(null) }}
                                          className="p-1 rounded text-slate-500 hover:text-cyan-300"
                                          aria-label="Corrigir este fato"
                                          title="Corrigir"
                                        ><Pencil size={12} /></button>
                                        <button
                                          onClick={() => setApagando(f.id!)}
                                          className="p-1 rounded text-slate-500 hover:text-rose-300"
                                          aria-label="Esquecer este fato"
                                          title="Esquecer"
                                        ><Trash2 size={12} /></button>
                                      </>
                                    )}
                                  </span>
                                ) : null}
                              </>
                            )}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </>
              ) : (
                // ─── Linha do tempo: diários + descobertas ───
                timeline.length ? (
                  <ul className="flex flex-col">
                    {timeline.map((t, i) => (
                      <li key={i} className="relative pl-6 pb-4">
                        {/* trilho */}
                        {i < timeline.length - 1 ? (
                          <span className="absolute left-[6px] top-4 bottom-0 w-px bg-cyan-500/15" />
                        ) : null}
                        {/* nó */}
                        <span
                          className="absolute left-0 top-1.5 w-3 h-3 rounded-full flex items-center justify-center"
                          style={{
                            background: t.tipo === 'descoberta' ? 'rgba(45,212,191,0.9)' : 'rgba(6,182,212,0.85)',
                            boxShadow: `0 0 8px ${t.tipo === 'descoberta' ? 'rgba(45,212,191,0.5)' : 'rgba(6,182,212,0.5)'}`,
                          }}
                        />
                        <div className="flex items-center gap-1.5 mb-1">
                          {t.tipo === 'descoberta' ? (
                            <Compass size={11} className="text-teal-300/80" />
                          ) : (
                            <BookOpen size={11} className="text-cyan-400/70" />
                          )}
                          <span className="text-[9px] font-mono uppercase tracking-[0.16em] text-slate-500">
                            {t.tipo === 'descoberta' ? 'descobriu' : 'diário'} · {dataCurta(t.data)}
                          </span>
                        </div>
                        <p className="text-[13px] leading-relaxed text-slate-300/90 italic">“{t.texto}”</p>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <div className="flex flex-col items-center justify-center h-full gap-2 text-center text-slate-500">
                    <Clock size={26} className="opacity-30" />
                    <p className="text-sm">A linha do tempo ainda está vazia.</p>
                    <p className="text-xs opacity-70">Diários e descobertas aparecem aqui conforme ela vive o dia.</p>
                  </div>
                )
              )}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  )
}
