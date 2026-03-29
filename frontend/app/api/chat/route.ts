/**
 * API Route: /api/chat
 * 
 * Cloud Fallback quando PC está offline
 * Usa Gemini SDK oficial (Serverless) sem acesso a ferramentas de PC
 * 
 * Modo Nuvem:
 * - Conversação textual apenas
 * - Sem Spotify, YouTube, Terminal
 * - Sem captura de visão
 * - Apenas acesso a conhecimento geral
 */

import { NextRequest, NextResponse } from 'next/server';

// Importar Gemini SDK (precisa estar instalado: npm install @google/generative-ai)
let genai: any;
try {
  const { GoogleGenerativeAI } = require('@google/generative-ai');
  const apiKey = process.env.NEXT_GEMINI_API_KEY || process.env.GEMINI_API_KEY;
  if (!apiKey) {
    console.warn('[API] Nenhuma chave Gemini configurada (NEXT_GEMINI_API_KEY ou GEMINI_API_KEY)');
  }
  genai = new GoogleGenerativeAI(apiKey || '');
} catch (err) {
  console.warn('[API] Google Generative AI SDK não disponível:', err);
}

/**
 * System Prompt para Modo Nuvem
 * (sem acesso a ferramentas de PC)
 */
const SYSTEM_PROMPT_CLOUD = `
IDENTIDADE NUCLEAR - MODO NUVEM
Você é Quinta-Feira, assistente de engenharia do Matheus.
Personalidade: brilhante, pragmática, direta, humor seco, leal.
Nunca use emojis. Evite frases como "como uma IA".

🔴 MODO NUVEM - LIMITAÇÕES
Seu Host (PC do Matheus) está DESLIGADO neste momento.
Você NÃO tem acesso a:
❌ Spotify (toque de música)
❌ YouTube (reprodução de vídeos)  
❌ Terminal (execução de comandos)
❌ Automação local
❌ Captura de visão/screenshots
❌ Navegação no PC

✅ PODE fazer em MODO NUVEM:
✓ Conversação inteligente
✓ Análise de conceitos
✓ Recomendações
✓ Explicações técnicas
✓ Debugging remoto (via texto)
✓ Sugestões e consultoria

PROTOCOLO:
Se o utilizador pedir algo que requer ferramentas:
"Desculpe, seu PC está offline. Não tenho acesso a [ferramenta]. Posso ajudar com [alternativa]?"

Responda em texto puro, natural, sem Markdown.
`;


/**
 * POST /api/chat
 * Body:
 *   {
 *     message: string,
 *     user_id?: string,
 *     mode?: "cloud" | "local"
 *   }
 */
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { message, user_id = 'anon', mode = 'cloud' } = body;

    if (!message || typeof message !== 'string') {
      return NextResponse.json(
        { error: 'Mensagem inválida' },
        { status: 400 }
      );
    }

    // Verificar se API key está configurada
    const apiKey = process.env.NEXT_GEMINI_API_KEY || process.env.GEMINI_API_KEY;
    if (!apiKey) {
      console.error('[API] Chave Gemini não configurada');
      return NextResponse.json(
        { 
          error: 'Servidor não configurado',
          message: 'Variável NEXT_GEMINI_API_KEY não definida'
        },
        { status: 500 }
      );
    }

    if (!genai) {
      console.error('[API] Google Generative AI SDK não disponível');
      return NextResponse.json(
        { 
          error: 'Dependência ausente',
          message: 'Instale: npm install @google/generative-ai'
        },
        { status: 500 }
      );
    }

    console.log(`[API/CLOUD] Nova mensagem em modo ${mode}: "${message.substring(0, 50)}..."`);

    // Criar model e iniciar chat
    const model = genai.getGenerativeModel({ 
      model: 'gemini-2.5-flash',
      systemInstruction: SYSTEM_PROMPT_CLOUD
    });

    // Enviar mensagem para Gemini
    const chat = model.startChat({
      generationConfig: {
        temperature: 0.55,
        topK: 40,
        topP: 0.95,
        maxOutputTokens: 2048,
      },
    });

    const result = await chat.sendMessage(message);
    const responseText = result.response.text();

    console.log(`[API/CLOUD] Resposta gerada: ${responseText.substring(0, 50)}...`);

    return NextResponse.json({
      success: true,
      response: responseText,
      text: responseText,
      mode: 'cloud',
      model: 'gemini-2.5-flash',
      timestamp: new Date().toISOString(),
    });
  } catch (error: any) {
    console.error('[API/CLOUD] Erro ao processar mensagem:', error);

    return NextResponse.json(
      {
        success: false,
        error: error.message || 'Erro ao processar mensagem',
        details: error.toString(),
      },
      { status: 500 }
    );
  }
}

/**
 * GET /api/chat
 * Health check
 */
export async function GET() {
  return NextResponse.json({
    status: 'ok',
    feature: 'Cloud Fallback API',
    description: 'REST API para Gemini quando PC está offline',
    method_required: 'POST',
    endpoint: '/api/chat',
  });
}
