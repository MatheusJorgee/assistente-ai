// Regras puras da rota /api/quinta-token (testáveis sem o Next).

const HOSTS_OK = new Set(['localhost', '127.0.0.1', '[::1]'])

export function hostPermitido(host: string | null): boolean {
  const h = (host ?? '').toLowerCase()
  const nome = h.startsWith('[') ? h.slice(0, h.indexOf(']') + 1) : h.split(':')[0]
  return HOSTS_OK.has(nome)
}

/** Pedido legítimo: vem da própria página (same-origin) ou de ferramenta local (sem Sec-Fetch-Site). */
export function origemPermitida(secFetchSite: string | null, origin: string | null, host: string | null): boolean {
  if (secFetchSite && !['same-origin', 'none'].includes(secFetchSite)) return false
  if (origin) {
    try {
      if (new URL(origin).host.toLowerCase() !== (host ?? '').toLowerCase()) return false
    } catch {
      return false
    }
  }
  return true
}

