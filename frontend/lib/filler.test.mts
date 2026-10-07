// node --test lib/filler.test.mts
import test from 'node:test'
import assert from 'node:assert/strict'
import { escolherFiller, ferramentaLenta, FRASES_ESPERA, podeFalarFiller } from './filler.ts'

test('filler: nunca repete a última frase', () => {
  for (const f of FRASES_ESPERA) {
    for (const s of [0, 0.5, 0.999]) assert.notEqual(escolherFiller(f, () => s), f)
  }
})

test('filler: só ferramentas lentas', () => {
  assert.ok(ferramentaLenta('pesquisar_informacao_online'))
  assert.ok(!ferramentaLenta('calcular'))
})

test('filler: só com tudo quieto e uma vez por turno', () => {
  const base = { falando: false, filaVazia: true, jaUsouNoTurno: false, narracao: true }
  assert.ok(podeFalarFiller(base))
  assert.ok(!podeFalarFiller({ ...base, falando: true }))
  assert.ok(!podeFalarFiller({ ...base, filaVazia: false }))
  assert.ok(!podeFalarFiller({ ...base, jaUsouNoTurno: true }))
  assert.ok(!podeFalarFiller({ ...base, narracao: false }))
})
