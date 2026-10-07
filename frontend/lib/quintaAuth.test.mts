// node --test lib/quintaAuth.test.mts
import test from 'node:test'
import assert from 'node:assert/strict'
import { CABECALHO, ehUrlDoBackend, PREFIXO_SUBPROTOCOLO, protocolosDoToken, tokenValido } from './quintaAuth.ts'
import { hostPermitido, origemPermitida } from './tokenRota.ts'

test('só URLs do backend (porta 8000 local) recebem o token', () => {
  assert.ok(ehUrlDoBackend('http://127.0.0.1:8000/tts'))
  assert.ok(ehUrlDoBackend('ws://localhost:8000/ws/quinta'))
  assert.ok(ehUrlDoBackend('http://localhost:8000'))
  assert.ok(!ehUrlDoBackend('https://api.exemplo.com/x'))
  assert.ok(!ehUrlDoBackend('http://127.0.0.1:8000.evil.com/x'))
  assert.ok(!ehUrlDoBackend('http://evil.com:8000/x'))
  assert.ok(!ehUrlDoBackend('/api/quinta-token'))
})

test('token com caracteres estranhos é descartado (nada de injeção em cabeçalho/subprotocolo)', () => {
  assert.ok(tokenValido('a'.repeat(43)))
  assert.ok(!tokenValido('curto'))
  assert.ok(!tokenValido('a'.repeat(30) + '\r\nX-Evil: 1'))
  assert.ok(!tokenValido('a b'.repeat(20)))
  assert.ok(!tokenValido(null))
  assert.equal(protocolosDoToken('x'), undefined)
  assert.deepEqual(protocolosDoToken('a'.repeat(43)), [PREFIXO_SUBPROTOCOLO + 'a'.repeat(43)])
  assert.equal(CABECALHO, 'X-Quinta-Token')
})

test('rota do token: só localhost e nunca de outro site', () => {
  assert.ok(hostPermitido('localhost:3000') && hostPermitido('127.0.0.1:3100') && hostPermitido('[::1]:3000'))
  assert.ok(!hostPermitido('evil.com') && !hostPermitido('192.168.18.3:3000') && !hostPermitido(null))
  assert.ok(origemPermitida('same-origin', null, 'localhost:3000'))
  assert.ok(origemPermitida(null, null, 'localhost:3000'))            // ferramenta local (curl)
  assert.ok(origemPermitida('none', null, 'localhost:3000'))
  assert.ok(!origemPermitida('cross-site', 'https://evil.com', 'localhost:3000'))
  assert.ok(!origemPermitida('same-site', null, 'localhost:3000'))
  assert.ok(!origemPermitida(null, 'https://evil.com', 'localhost:3000'))
  assert.ok(origemPermitida('same-origin', 'http://localhost:3000', 'localhost:3000'))
})
