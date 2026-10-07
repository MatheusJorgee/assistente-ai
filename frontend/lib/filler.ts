// Frases de espera (A3): quando uma ferramenta LENTA dispara e ela ainda não falou nada, uma frase
// curta ("um instante") cobre o silêncio. O áudio é buscado uma vez ao conectar e reutilizado.

export const FRASES_ESPERA = [
  'Um instante.',
  'Deixa eu ver.',
  'Só um segundo.',
  'Já vejo isso.',
  'Vou dar uma olhada.',
  'Pera aí.',
  'Deixa comigo.',
  'Estou vendo.',
]

// Só ferramentas que costumam levar segundos; calcular/lembrete respondem antes do filler acabar.
const FERRAMENTAS_LENTAS = new Set([
  'pesquisar_informacao_online', 'ler_documento', 'buscar_arquivo', 'capturar_tela',
  'mostrar_holograma', 'financas', 'agenda', 'whatsapp', 'discord', 'discord_amigos',
])

export function ferramentaLenta(nome: string): boolean {
  return FERRAMENTAS_LENTAS.has(nome)
}

/** Sorteia uma frase diferente da última (para não soar repetido). */
export function escolherFiller(ultima: string | null, sorteio: () => number = Math.random): string {
  const opcoes = FRASES_ESPERA.filter((f) => f !== ultima)
  return opcoes[Math.min(opcoes.length - 1, Math.floor(sorteio() * opcoes.length))]
}

/** Só fala filler se está tudo quieto: nada tocando, nada na fila, e ainda não usou neste turno. */
export function podeFalarFiller(
  e: { falando: boolean; filaVazia: boolean; jaUsouNoTurno: boolean; narracao: boolean },
): boolean {
  return e.narracao && !e.falando && e.filaVazia && !e.jaUsouNoTurno
}
