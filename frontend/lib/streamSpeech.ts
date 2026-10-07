/**
 * streamSpeech — lógica PURA (sem React, sem áudio) da fala em streaming.
 *
 * A resposta chega em pedaços (`text_delta`). Aqui se decide, a cada pedaço, quais FRASES já
 * estão completas e podem ir para a voz, e — quando chega o texto final — o que ainda falta
 * falar sem repetir nada. Fica separado do hook para ser testado com `node --test`.
 */

/** Máximo de caracteres falados por resposta (o mesmo teto de antes: evita monólogo). */
export const ORCAMENTO_FALA = 300

export interface EstadoStream {
  /** Texto recebido desde o último reset. */
  buf: string
  /** Até onde de `buf` já foram extraídas frases completas. */
  pos: number
  /** Quantos caracteres ainda podem ser falados nesta resposta. */
  orcamento: number
}

export function novoEstadoStream(): EstadoStream {
  return { buf: '', pos: 0, orcamento: ORCAMENTO_FALA }
}

/** Tira markdown e símbolos que o TTS leria em voz alta ("asterisco asterisco…"). */
export function limparParaFala(texto: string): string {
  return texto
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/[*_`#>~]+/g, '')
    .replace(/^\s*[-•]\s+/gm, '')
    .replace(/\s+/g, ' ')
    .trim()
}

/**
 * Frases COMPLETAS de `buf` a partir de `desde`. Uma frase só fecha com pontuação seguida de
 * espaço/quebra de linha (assim "R$ 5,40" ou "3.14" chegando aos pedaços não é cortado); com
 * `final`, o resto do texto também sai. `ate` é onde parou.
 */
export function extrairFrases(
  buf: string,
  desde: number,
  final: boolean,
): { frases: string[]; ate: number } {
  const frases: string[] = []
  let pos = desde
  const re = /[.!?…]+["')\]]*\s+|\n+/g
  re.lastIndex = desde
  let m: RegExpExecArray | null
  while ((m = re.exec(buf))) {
    const fim = m.index + m[0].length
    frases.push(buf.slice(pos, fim))
    pos = fim
  }
  if (final && pos < buf.length) {
    frases.push(buf.slice(pos))
    pos = buf.length
  }
  return { frases: frases.map((f) => f.trim()).filter(Boolean), ate: pos }
}

const semEspacos = (s: string): string => s.replace(/\s+/g, '')

/** Corta de `texto` os primeiros `n` caracteres NÃO-brancos (ignora diferença de espaços). */
export function cortarPrefixoSemEspacos(texto: string, n: number): string {
  if (n <= 0) return texto
  let vistos = 0
  for (let i = 0; i < texto.length; i++) {
    if (!/\s/.test(texto[i])) {
      vistos += 1
      if (vistos === n) return texto.slice(i + 1)
    }
  }
  return ''
}

/** Consome o orçamento: devolve só as frases que ainda cabem (a última pode passar do teto). */
export function aplicarOrcamento(e: EstadoStream, frases: string[]): string[] {
  const falar: string[] = []
  for (const f of frases) {
    if (e.orcamento <= 0) break
    falar.push(f)
    e.orcamento -= f.length
  }
  return falar
}

/** Chegou um pedaço de texto: devolve as frases que já podem ser faladas. */
export function aoDelta(e: EstadoStream, delta: string): string[] {
  e.buf += delta
  const { frases, ate } = extrairFrases(e.buf, e.pos, false)
  if (e.pos === 0 && frases.length === 0) {
    // Primeira frase curta (A1): a voz só começa depois do 1º pedaço, e o TTS leva ~1,8 s por
    // pedaço. Sem ponto final ainda, corta no 1º ponto natural de pausa em vez de esperar.
    const corte = primeiroCorte(e.buf)
    if (corte > 0) {
      e.pos = corte
      return aplicarOrcamento(e, [e.buf.slice(0, corte).trim()])
    }
  }
  e.pos = ate
  return aplicarOrcamento(e, frases)
}

/** Onde cortar a 1ª frase antes do ponto final: vírgula/;/:/travessão seguido de espaço depois de
 *  ~20 caracteres, ou um espaço depois de ~48 (palavra completa). -1 se ainda não dá. Vírgula
 *  colada em dígito ("3,14") nunca corta, pois exige espaço depois. */
export const PRIMEIRO_CORTE_PAUSA_MIN = 20
export const PRIMEIRO_CORTE_ESPACO_MIN = 48
export function primeiroCorte(buf: string): number {
  const pausa = /[,;:]\s|\s[—–-]\s/g
  let m: RegExpExecArray | null
  while ((m = pausa.exec(buf))) {
    const fim = m.index + m[0].length
    if (m.index >= PRIMEIRO_CORTE_PAUSA_MIN) return fim
  }
  if (buf.length > PRIMEIRO_CORTE_ESPACO_MIN) {
    const i = buf.indexOf(' ', PRIMEIRO_CORTE_ESPACO_MIN)
    if (i > 0 && i < buf.length - 0) return i + 1
  }
  return -1
}

/** `text_reset`: o que foi mostrado era só um preâmbulo (ou o streaming recomeçou). A fala já
 *  enfileirada continua (uma pessoa diz "deixa eu ver…" e depois trabalha). */
export function aoReset(e: EstadoStream): void {
  e.buf = ''
  e.pos = 0
}

/**
 * Chegou o texto FINAL (autoritativo). Se ele continua o que já foi extraído, só falta o resto;
 * se diferiu (ex.: texto de erro, ou resposta sem streaming), recomeça: `pararAntes` manda cortar
 * a fala em andamento e o orçamento volta ao máximo.
 */
export function aoFinal(e: EstadoStream, texto: string): { pararAntes: boolean; frases: string[] } {
  const jaExtraido = e.buf.slice(0, e.pos)
  const alvo = semEspacos(jaExtraido)
  if (semEspacos(texto).startsWith(alvo)) {
    const resto = cortarPrefixoSemEspacos(texto, alvo.length)
    return { pararAntes: false, frases: aplicarOrcamento(e, extrairFrases(resto, 0, true).frases) }
  }
  e.orcamento = ORCAMENTO_FALA
  return { pararAntes: true, frases: aplicarOrcamento(e, extrairFrases(texto, 0, true).frases) }
}
