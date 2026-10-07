// Testes da lógica pura de fala em streaming. Rodar: node --test lib/streamSpeech.test.mts
import test from 'node:test'
import assert from 'node:assert/strict'
import {
  ORCAMENTO_FALA,
  aoDelta,
  aoFinal,
  aoReset,
  aplicarOrcamento,
  cortarPrefixoSemEspacos,
  extrairFrases,
  limparParaFala,
  novoEstadoStream,
  primeiroCorte,
} from './streamSpeech.ts'

const falarTudo = (pedacos: string[]) => {
  const e = novoEstadoStream()
  const faladas: string[] = []
  for (const p of pedacos) faladas.push(...aoDelta(e, p))
  return { e, faladas }
}

test('frase só fecha com pontuação + espaço: "R$ 5,40" e "3.14" não são cortados', () => {
  const { faladas } = falarTudo(['O dólar está em R$ 5', ',40 hoje. ', 'Pi é 3', '.14 e pronto. '])
  assert.deepEqual(faladas, ['O dólar está em R$ 5,40 hoje.', 'Pi é 3.14 e pronto.'])
})

test('pontuação no fim do buffer ESPERA (pode vir mais texto colado)', () => {
  const { faladas, e } = falarTudo(['Olá.'])
  assert.deepEqual(faladas, [])
  assert.equal(e.pos, 0)
})

test('as frases saem assim que fecham, uma por vez, na ordem', () => {
  const e = novoEstadoStream()
  assert.deepEqual(aoDelta(e, 'Primeira frase. Seg'), ['Primeira frase.'])
  assert.deepEqual(aoDelta(e, 'unda frase! Terceira'), ['Segunda frase!'])
  assert.deepEqual(aoDelta(e, ' aqui.\n'), ['Terceira aqui.'])
})

test('quebra de linha também fecha (itens de lista)', () => {
  const { faladas } = falarTudo(['- um item\n- outro item\n'])
  assert.deepEqual(faladas, ['- um item', '- outro item'])
})

test('final coerente: fala só o que falta, SEM repetir', () => {
  const { e, faladas } = falarTudo(['Olá, tudo bem? ', 'Hoje faz sol e '])
  assert.deepEqual(faladas, ['Olá, tudo bem?'])
  const r = aoFinal(e, 'Olá, tudo bem? Hoje faz sol e está quente.')
  assert.equal(r.pararAntes, false)
  assert.deepEqual(r.frases, ['Hoje faz sol e está quente.'])
})

test('final coerente ignora diferença de espaços/quebras (o backend faz strip)', () => {
  const { e } = falarTudo(['\nOlá  mundo. ', 'Resto'])
  const r = aoFinal(e, 'Olá mundo. Resto aqui.')
  assert.equal(r.pararAntes, false)
  assert.deepEqual(r.frases, ['Resto aqui.'])
})

test('final DIFERENTE do que foi falado: recomeça (pararAntes) com orçamento cheio', () => {
  const { e } = falarTudo(['Vou tentar isso. '])
  const r = aoFinal(e, 'Não consegui fazer isso.')
  assert.equal(r.pararAntes, true)
  assert.deepEqual(r.frases, ['Não consegui fazer isso.'])
})

test('resposta SEM streaming (rota determinística): fala tudo, sem parar nada', () => {
  const e = novoEstadoStream()
  const r = aoFinal(e, 'Tocando Numb. Curte aí.')
  assert.equal(r.pararAntes, false)
  assert.deepEqual(r.frases, ['Tocando Numb.', 'Curte aí.'])
})

test('reset (preâmbulo antes de uma ferramenta) zera o texto mostrado, mas não o orçamento', () => {
  const e = novoEstadoStream()
  aoDelta(e, 'Deixa eu ver. ')
  const gasto = e.orcamento
  aoReset(e)
  assert.equal(e.buf, '')
  assert.equal(e.pos, 0)
  assert.equal(e.orcamento, gasto)
  const r = aoFinal(e, 'O dólar está em R$ 5,40.')
  assert.equal(r.pararAntes, false)
  assert.deepEqual(r.frases, ['O dólar está em R$ 5,40.'])
})

test('orçamento: para de falar depois do teto, em fronteira de frase', () => {
  const e = novoEstadoStream()
  const longa = 'a'.repeat(200) + '. '
  const r1 = aoDelta(e, longa + longa + longa)
  assert.equal(r1.length, 2) // 202 + 202 já passou de 300; a 3ª não entra
  assert.ok(e.orcamento <= 0)
  assert.deepEqual(aoDelta(e, 'Mais uma. '), [])
})

test('aplicarOrcamento não fala nada com orçamento zerado', () => {
  const e = novoEstadoStream()
  e.orcamento = 0
  assert.deepEqual(aplicarOrcamento(e, ['x']), [])
  assert.equal(ORCAMENTO_FALA, 300)
})

test('limparParaFala tira markdown que o TTS leria em voz alta', () => {
  assert.equal(limparParaFala('**Atenção**: veja [o site](http://x.com) agora'), 'Atenção: veja o site agora')
  assert.equal(limparParaFala('- item um\n- item dois'), 'item um item dois')
  assert.equal(limparParaFala('```js\ncodigo()\n``` fim'), 'fim')
  assert.equal(limparParaFala('# Título'), 'Título')
})

test('extrairFrases com final devolve o resto sem pontuação', () => {
  assert.deepEqual(extrairFrases('Uma. Duas sem ponto', 0, true).frases, ['Uma.', 'Duas sem ponto'])
  assert.deepEqual(extrairFrases('Uma. Duas sem ponto', 0, false).frases, ['Uma.'])
})

test('cortarPrefixoSemEspacos', () => {
  assert.equal(cortarPrefixoSemEspacos('ab cd ef', 3), 'd ef')
  assert.equal(cortarPrefixoSemEspacos('abc', 3), '')
  assert.equal(cortarPrefixoSemEspacos('abc', 0), 'abc')
})

test('primeira frase curta: corta na vírgula em vez de esperar o ponto final', () => {
  const e = novoEstadoStream()
  assert.deepEqual(aoDelta(e, 'Olha só o que eu encontrei'), [])
  const saida = aoDelta(e, ' sobre isso, e é bem interessante')
  assert.deepEqual(saida, ['Olha só o que eu encontrei sobre isso,'])
})

test('primeira frase curta: vírgula decimal e frase curta não cortam', () => {
  assert.equal(primeiroCorte('O valor é 3,14 reais e'), -1)
  assert.equal(primeiroCorte('Sim, claro'), -1)
})

test('primeira frase curta: sem pausa, corta em palavra inteira depois de ~48 caracteres', () => {
  const buf = 'uma frase longa sem nenhuma pausa natural que continua andando e andando'
  const c = primeiroCorte(buf)
  assert.ok(c > 48 && buf[c - 1] === ' ')
  assert.equal(primeiroCorte('uma frase longa sem pausa natural que continua'), -1)
})

test('primeira frase curta: o final coerente não repete o que já foi falado', () => {
  const e = novoEstadoStream()
  const falado = aoDelta(e, 'Olha só o que eu encontrei sobre isso, e é bem interessante')
  assert.equal(falado.length, 1)
  const fim = aoFinal(e, 'Olha só o que eu encontrei sobre isso, e é bem interessante. Quer os detalhes?')
  assert.equal(fim.pararAntes, false)
  assert.deepEqual(fim.frases, ['e é bem interessante.', 'Quer os detalhes?'])
})

test('primeira frase curta: só vale para o começo da resposta', () => {
  const e = novoEstadoStream()
  aoDelta(e, 'Primeira frase completa aqui. ')
  assert.deepEqual(aoDelta(e, 'Segunda, que continua e continua sem parar por um tempo longo'), [])
})
