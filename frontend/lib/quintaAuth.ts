// Token de sessão da Quinta (backend/core/api/session_token.py): busca o token pelo servidor do Next e
// o envia em toda chamada ao backend (cabeçalho no HTTP, subprotocolo no WebSocket).

export const PREFIXO_SUBPROTOCOLO = 'qf.token.'
export const CABECALHO = 'X-Quinta-Token'

let tokenEmCache: string | null = null
let buscando: Promise<string | null> | null = null

/** É uma URL do backend (porta 8000 em localhost/127.0.0.1)? Só essas recebem o token. */
export function ehUrlDoBackend(url: string): boolean {
  return /^(https?|wss?):\/\/(127\.0\.0\.1|localhost|\[::1\]):8000(\/|$|\?)/i.test(url)
}

/** Token só com caracteres seguros para subprotocolo/cabeçalho (base64 url-safe); senão, descarta. */
export function tokenValido(token: unknown): token is string {
  return typeof token === 'string' && /^[A-Za-z0-9_-]{20,128}$/.test(token)
}

export function protocolosDoToken(token: string | null = tokenEmCache): string[] | undefined {
  return tokenValido(token) ? [PREFIXO_SUBPROTOCOLO + token] : undefined
}

/** Busca o token (uma vez; `renovar` refaz a busca, ex.: depois de o backend reiniciar). Nunca lança. */
export async function obterToken(renovar = false): Promise<string | null> {
  if (typeof window === 'undefined') return null
  if (!renovar && tokenEmCache) return tokenEmCache
  if (buscando) return buscando
  buscando = (async () => {
    try {
      const r = await originalFetch()('/api/quinta-token', { cache: 'no-store' })
      const j = r.ok ? await r.json() : null
      tokenEmCache = tokenValido(j?.token) ? j.token : null
    } catch {
      tokenEmCache = null
    } finally {
      buscando = null
    }
    return tokenEmCache
  })()
  return buscando
}

export function tokenSincrono(): string | null {
  return tokenEmCache
}

// ---- fetch autenticado (instalado uma vez): as ~20 chamadas espalhadas ao backend passam a levar o token
type FetchFn = typeof fetch
let fetchOriginal: FetchFn | null = null
const originalFetch = (): FetchFn => fetchOriginal ?? window.fetch.bind(window)

export function instalarFetchAutenticado(): void {
  if (typeof window === 'undefined' || fetchOriginal) return
  fetchOriginal = window.fetch.bind(window)
  const base = fetchOriginal
  window.fetch = async (entrada: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof entrada === 'string' ? entrada : entrada instanceof URL ? entrada.href : entrada.url
    if (!ehUrlDoBackend(url)) return base(entrada, init)
    const enviar = async (token: string | null) => {
      const headers = new Headers(init?.headers ?? (typeof entrada === 'object' && 'headers' in entrada ? entrada.headers : undefined))
      if (token) headers.set(CABECALHO, token)
      return base(entrada, { ...init, headers })
    }
    let resp = await enviar(await obterToken())
    if (resp.status === 401) resp = await enviar(await obterToken(true))   // o backend reiniciou: token novo
    return resp
  }
}

if (typeof window !== 'undefined') instalarFetchAutenticado()
