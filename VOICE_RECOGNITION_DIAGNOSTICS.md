"""
🎤 GUIA DE DIAGNÓSTICO - Reconhecimento de Voz
Debug e troubleshooting para problemas de transcrição
"""

# ============ PROBLEMA: POR QUE A VOZ NÃO ESTÁ SENDO RECONHECIDA BEM? ============

## 1️⃣ DIAGNÓSTICO RÁPIDO

### A. Você está usando Chrome?
- ✅ Google Chrome → Suporte completo
- ✅ Chromium → Suporte completo  
- ⚠️ Brave → Pode ter erro 'network' (solução: modo confiável)
- ❌ Firefox → Suporte limitado
- ❌ Safari → Não funciona em desktop

### B. Seu microfone está ON?
```bash
# Windows: Verificar permissão
1. Settings → Privacy & Security → Microphone → Allow
2. Verificar que aplicativo tem permissão

# Linux:
arecord --list-devices  # Lista mics
</bash>

### C. O navegador tem permissão?
```
Browser asking for microphone permission?
YES ✓ → Continue
NO ✗ → Go to address bar lock icon → Microphone → Allow → Reload
```

---

## 2️⃣ PROBLEMAS COMUNS E SOLUÇÕES

| Problema | Sintoma | Causa | Solução |
|----------|---------|-------|---------|
| **Não reconhece nada** | Microfone ativo mas sem transcrição | Browser não pediu permissão | Clicar no lock → Allow microphone |
| **Reconhece parcialmente** | Só a primeira palavra | Buffer flush timing | Aumentar `flush timeout` (L238: 1400 → 1800ms) |
| **Reconhece errado** | "Quinta-Feira" vira "Quinto Faira" | Qualidade de áudio ruim | Falar mais claro / perto do mic |
| **Áudio muito baixo** | Não capta voz morna | Gain muito baixo | Aumentar volume do mic (windows settings) |
| **Erro "network"** | Em Brave "network error" | Restrição de segurança | Usar Chrome ou modo trusted local |
| **Delay muito grande** | 3+ segundos | Conexão internet lenta | Próximo de router Wi-Fi |
| **Interrupção de áudio** | Áudio da IA cortado | Barge-in funcionando mas output não controlado | Aumentar volume antes de falar |

---

## 3️⃣ TESTE PASSO A PASSO

### Teste 1: Navegador Compatível
```
1. Abrir DevTools (F12)
2. Console → console.log((window as any).SpeechRecognition)
   Resultado:
   - Se vir: [Function SpeechRecognition] → ✅ Browser suporta
   - Se vir: undefined → ❌ Browser não suporta
```

### Teste 2: Permissão de Microfone
```
1. DevTools → Console → 
   navigator.mediaDevices.getUserMedia({audio: true})
   
   Resultado:
   - Se vir: Promise { <pending> } → Iniciará permissão
   - Se permitir → ✅ Mic funciona
   - Se denegar → ❌ Mic não autorizado
```

### Teste 3: Speech Recognition Direto
```javascript
// Cole isso no DevTools Console:
const sr = new (window as any).SpeechRecognition || new (window as any).webkitSpeechRecognition();
sr.lang = 'pt-BR';
sr.continuous = true;
sr.interimResults = true;

sr.onstart = () => console.log('>>> Started listening');
sr.onresult = (e) => {
  for (let i = e.resultIndex; i < e.results.length; i++) {
    console.log('Transcription:', e.results[i][0].transcript, 'Final:', e.results[i].isFinal);
  }
};
sr.onerror = (e) => console.log('Error:', e.error);
sr.onend = () => console.log('>>> Ended listening');

sr.start();
// Fale algo...
// sr.stop(); // Quando terminar
```

---

## 4️⃣ CÓDIGO DE MELHORIA (Para implementar)

### A. Diagnostic Page - `/diagnose`
```tsx
// frontend/app/diagnose/page.tsx
export default function VoiceDiagnostics() {
  return (
    <div className="p-8">
      <h1>🎤 Diagnóstico de Voz</h1>
      
      <DiagnosticCheck 
        name="Chrome/Chromium"
        test={() => navigator.userAgent.includes('Chrome')}
        help="Use Google Chrome para melhor suporte"
      />
      
      <DiagnosticCheck
        name="Speech Recognition API"
        test={() => (window as any).SpeechRecognition !== undefined}
        help="Seu navegador não suporta Speech Recognition"
      />
      
      <DiagnosticCheck
        name="Permissão de Microfone"
        test={async () => {
          try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            stream.getTracks().forEach(t => t.stop());
            return true;
          } catch { return false; }
        }}
        help="Microfone não autorizado - verifique Settings"
      />
      
      <LiveTranscriptionTest />
    </div>
  );
}
```

### B. Melhor Normalização (page.tsx L214)
```typescript
// ✅ MELHORADO: Mais robusto
const normalizarTexto = (texto: string) => {
  // 1. Remove diacríticos
  let normalized = texto.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  
  // 2. Remove símbolos, mantém apenas alphanuméricas
  normalized = normalized.replace(/[^a-zA-Z0-9\s\-áéíóúãõ]/g, " ");
  
  // 3. Converte para minúsculas
  normalized = normalized.toLowerCase();
  
  // 4. Remove espaços múltiplos
  normalized = normalized.replace(/\s+/g, " ").trim();
  
  return normalized;
};

// Teste:
console.log(normalizarTexto("Quintá-Feirá!!!"));  // → "quinta feira"
console.log(normalizarTexto("QUINTA     FEIRA"));  // → "quinta feira"
```

### C. Melhor Detecção de Ativação (page.tsx L218)
```typescript
// ✅ MELHORADO: Mais fino e menos falso-positivo
const contemPalavraAtivacao = (texto: string) => {
  const t = normalizarTexto(texto);
  
  // Variações de "Quinta-Feira" / "Quinta-Fera"
  const patterns = [
    /\bquinta\s*feira\b/,
    /\bquinta\s*fera\b/,
    /\bquintafeira\b/,
    /\bquintafera\b/,
    /\bquinta\b/,  // Só "quinta" tbm funciona como ativação
  ];
  
  return patterns.some(p => p.test(t));
};

// Teste:
console.log(contemPalavraAtivacao("Quinta-Feira"));       // → true
console.log(contemPalavraAtivacao("quinta fera"));        // → true
console.log(contemPalavraAtivacao("Quinto Faira"));       // → false (melhor!)
```

### D. Buffer de Transcrição Melhorado (page.tsx L240)
```typescript
// ✅ MELHORADO: Timestamp + Better flush logic

const flushComandoRapido = () => {
  const transcricaoBruta = comandoRapidoBufferRef.current.trim();
  comandoRapidoBufferRef.current = "";
  
  if (!transcricaoBruta) {
    setDiagnosticoVoz("❌ Não capturado. Tente novamente.");
    return;
  }
  
  // Remover palavra de ativação
  let transcricao = transcricaoBruta
    .replace(/quinta\s*feira/gi, "")
    .replace(/quinta\s*fera/gi, "")
    .replace(/quintafeira/gi, "")
    .trim();
  
  if (!transcricao) {
    setDiagnosticoVoz("❌ Apenas palavra de ativação, fale o comando.");
    return;
  }
  
  const comandoAjustado = ajustarComandoBilingue(transcricao);
  
  // Log detalhado
  setDiagnosticoVoz(
    `✓ Ouvido: "${transcricaoBruta}"\n` +
    `✓ Comando: "${comandoAjustado}"\n` +
    `⏱️ [${new Date().toLocaleTimeString()}]`
  );
  
  enviarMensagemTexto(comandoAjustado);
};
```

### E. Status Visual de Voz (Novo Componente)
```tsx
// frontend/components/VoiceStatus.tsx
export function VoiceStatus({ diagnostico, isListening, wsConnected }) {
  return (
    <div className="p-4 bg-gray-900 border border-cyan-500 rounded">
      <div className="flex items-center gap-3 mb-3">
        {isListening ? (
          <div className="animate-pulse bg-red-500 w-3 h-3 rounded-full" />
        ) : (
          <div className="bg-green-500 w-3 h-3 rounded-full" />
        )}
        <span className="text-sm">
          {isListening ? "🎤 Escutando..." : "🔇 Inativo"}
        </span>
        <span className={wsConnected ? "text-green-400" : "text-red-400"}>
          {wsConnected ? "✓ Conectado" : "✗ Offline"}
        </span>
      </div>
      
      <div className="text-xs text-gray-300 whitespace-pre-wrap font-mono">
        {diagnostico || "Pronto para comandos de voz..."}
      </div>
    </div>
  );
}
```

---

## 5️⃣ TIMING PARAMETERS (Fine-tuning)

Se o reconhecimento está muito lento ou rápido, ajuste:

```typescript
// Tempo de espera após última fala para enviar
const COMANDO_FLUSH_TIMEOUT = 1400;  // ← Aumentar se cut off (1600-1800)
                                       // ← Diminuir se muito lento (1200)

// Contexto: brain_v2 think time
const THINK_TIMEOUT = 2000;  // Esperar 2s antes de enviar "Pensando..."

// Speech Recognition settings (page.tsx L227)
recognition.continuous = true;        // Continua gravando
recognition.interimResults = true;    // Mostra resultados parciais
recognition.maxAlternatives = 1;      // Só 1ª opção (mais rápido)
```

---

## 6️⃣ LOGS PARA DEBUG (DevTools)

Adicione isso em page.tsx para logs detalhados:

```typescript
// No recognition.onresult
recognition.onresult = (event: any) => {
  console.log('[SPEECH]', {
    resultIndex: event.resultIndex,
    resultsLength: event.results.length,
    results: event.results.map((r: any) => ({
      transcript: r[0].transcript,
      confidence: r[0].confidence,
      isFinal: r.isFinal
    }))
  });
  // ... resto do código
};
```

---

## 7️⃣ CHECKLIST FINAL

Antes de assumir que "reconhecimento está ruim", verifique:

- [ ] Chrome/Chromium (não Firefox/Safari)
- [ ] Permissão de mic ativada
- [ ] Microfone funcionando (teste em outro app)
- [ ] Falar claramente perto do mic
- [ ] Mensagem de desconexão? → Reconectar backend
- [ ] Teste o speech recognition direto (Teste 3 acima)
- [ ] Checar logs no DevTools Console
- [ ] Isoladamente: frase curta e clara

---

## ⚙️ Se Nada Disso Funcionar

1. Abrir DevTools (F12)
2. Network tab → Verificar se WebSocket conecta a ws://localhost:8000/ws
3. Se não conecta → Backend não está rodando
   ```bash
   cd backend
   python -m uvicorn main:app --reload
   ```

4. Se WebSocket OK mas recognition não: Usar diagnose page acima

---

**Última atualização**: v2.1
**Problemas conhecidos**: Brave browser pode ter erro 'network' → usar Chrome
