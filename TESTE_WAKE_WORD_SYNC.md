# 🧪 TESTE: Sincronização de Wake Word (Botão RADAR)

## ✅ Checklist de Validação

### 1. **Renderização do Botão**
- [ ] Abrir http://localhost:3000
- [ ] Procurar no header por botão "RADAR" (📡 ou 🔌)
- [ ] Botão deve estar à esquerda do status "NÚCLEO ONLINE"

### 2. **Feedback Visual ao Clicar**
- [ ] Botão inativo (padrão): `🔌 RADAR` (cinza/cyan)
- [ ] Clicar no botão
- [ ] Botão ativo deve ficar: `📡 RADAR ATIVO` (verde lima + brilho)
- [ ] Deve aparecer ponto animado (pulsando) quando ativo
- [ ] Cor deve passar de cyan para lime

### 3. **Console Logs (Abrir DevTools - F12)**
Ao clicar no botão, procurar por logs:

```
[PAGE_BUTTON_CLICK] Botão RADAR clicado! Novo estado: 🟢 LIGADO
[PAGE] isWakeWordEnabled mudou para: 🟢 CONTINUO
[VOICE_CONTROL] Modo alterado para: 🟢 CONTINUO
[WAKE_WORD_SYNC] Modo alterado para: 🟢 CONTINUO
[WAKE_WORD_SYNC] Reiniciando microfone para aplicar nova configuração...
[HOOK_INIT] recognition.continuous configurado para: true (isWakeWordEnabled=true)
[WAKE_WORD_SYNC] Microfone reiniciado com continuous=true
```

### 4. **Comportamento do Microfone**
- [ ] **Modo MANUAL (🔌)**: 
  - Clicar em botão de voz (🎤)
  - Conceder permissão de microfone
  - Falar algo ou fazer silêncio
  - Microfone PARA após 1-2 segundos (NÃO reinicia automaticamente)

- [ ] **Modo CONTINUO (📡 ATIVO)**:
  - Clicar em botão de voz (🎤)
  - Conceder permissão de microfone
  - Fazer silêncio ou falar
  - Microfone CONTINUA escutando (reinicia automaticamente) ✅

### 5. **Status no Painel Lateral**
- [ ] Procurar seção "Atalhos" no painel direito (sidebar)
- [ ] Deve mostrar: `Modo: 🟢 CONTINUO` ou `Modo: 🔵 MANUAL`
- [ ] Ponto antes deve estar **pulsando (verde) quando CONTINUO**
- [ ] Ponto deve estar **estático (azul) quando MANUAL**

### 6. **Som de Ativação (Wake Word)**
- [ ] Modo CONTINUO ativo (📡 verde)
- [ ] Clicar microfone
- [ ] Falar "Quinta-Feira"
- [ ] Deve ouvir som musical duplo (440Hz + 880Hz) ✅

### 7. **Teste Full Flow**
```
1. Padrão: RADAR 🔌 (inativo)
2. Clicar botão → 📡 RADAR ATIVO (verde)
3. Clicar 🎤 (microfone)
4. Falar "Quinta-Feira" lentamente
   → Som de "radar ativado" (beep musical)
   → Microfone continua escutando comando
5. Falar comando (ex: "toca rock")
6. Sistema deve executar
7. Microfone volta a escutar "Quinta-Feira" AUTOMATICAMENTE
8. Desativar RADAR (📡 → 🔌)
9. Clicar 🎤 novamente
   → Microfone faz APENAS UM ciclo
   → Para e NÃO reinicia (diferente do anterior)
```

## 🔧 Troubleshooting

### "Botão não aparece"
- [ ] Verificar em DevTools: `document.querySelector('button[title*="Escuta"]')`
- [ ] Se vazio, probável error na renderização
- [ ] Procurar erro "Parsing ecmascript" no build

### "Botão aparece mas não funciona"
- [ ] Abrir F12 → Console
- [ ] Clicar botão
- [ ] Procurar por `[PAGE_BUTTON_CLICK]`
- [ ] Se não aparecer, onClick não está sendo disparado

### "Texto não muda de cor"
- [ ] Verificar se classe Tailwind `text-lime-200` está compilada
- [ ] Procurar em DevTools: elementos > propriedades CSS
- [ ] Deve conter `color: rgb(217, 249, 157)` (lime-200)

### "Microfone não reinicia em modo CONTINUO"
- [ ] F12 → Console
- [ ] Procurar por `[CONTINUOUS_LISTENING]`
- [ ] Se não aparecer, o onend não está reiniciando
- [ ] Verificar se `recognition.continuous = true` foi aplicado

## 📊 Esperado vs Atual

| O que deveria acontecer | Atual | Status |
|------------------------|--------|--------|
| Botão RADAR visível | ? | |
| Cor muda ao clicar | ? | |
| Ponto animate quando ativo | ? | |
| Status mostra no sidebar | ? | |
| Logs aparecem em DevTools | ? | |
| Microfone reinicia em CONTINUO | ? | |
| Som plays ao detectar "Quinta-Feira" | ? | |
| Full flow funciona end-to-end | ? | |

## 🚀 Próximos Passos

Quando todos os testes passarem:
1. ✅ Documentar quais testes passaram
2. ✅ Reportar quais falharam com números de linha
3. ✅ Incluir screenshots dos logs de DevTools
4. ✅ Proceder para testes com backend (command execution)
