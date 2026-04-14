#!/usr/bin/env python3
"""
EXEMPLO PRÁTICO: Como o Sistema de Memória de Curto Prazo Funciona

Este script mostra EXATAMENTE como o Quinta-Feira usa a nova memória.
"""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Message:
    """Modelo simplificado de mensagem."""
    role: str  # "system", "user", "assistant"
    content: str


def example_1_basic_usage():
    """Exemplo 1: Uso básico da memória."""
    print("\n" + "="*70)
    print("EXEMPLO 1: Uso Básico")
    print("="*70)
    
    # Simular conversa com 15 mensagens
    messages = []
    
    # Adicionar mensagens (como faria o cérebro)
    conversation = [
        ("user", "Olá"),
        ("assistant", "Olá! Como posso ajudar?"),
        ("user", "Toque música"),
        ("assistant", "[Tocando YouTube...] Música iniciada"),
        ("user", "Qual é a temperatura?"),
        ("assistant", "Temperatura: 22°C"),
        ("user", "Abra o terminal"),
        ("assistant", "[Abrindo terminal...] Terminal aberto"),
        ("user", "Quantas mensagens temos?"),
        ("assistant", "Temos 9 mensagens até agora"),
        ("user", "Fale sobre machine learning"),
        ("assistant", "ML é um ramo da IA que..."),
        ("user", "Me mande um email"),
        ("assistant", "[Enviando email...] Email enviado"),
        ("user", "Qual foi a primeira coisa que falamos?"),
    ]
    
    for role, content in conversation:
        messages.append(Message(role=role, content=content))
    
    print(f"\nConversa inteira: {len(messages)} mensagens")
    for i, msg in enumerate(messages):
        print(f"  {i+1:2}. {msg.role:10} | {msg.content[:50]}")
    
    # Mostrar o que seria enviado ao LLM
    print(f"\nO que vai PARA O GEMINI (últimas 10):")
    system_prompt = "Você é o Quinta-Feira..."
    print(f"  [SYS] {system_prompt}")
    
    llm_messages = [Message("system", system_prompt)]
    if len(messages) > 10:
        llm_messages.extend(messages[-10:])
    else:
        llm_messages.extend(messages)
    
    for i, msg in enumerate(llm_messages):
        if msg.role != "system":
            print(f"  [{i}] {msg.role:10} | {msg.content[:50]}")
    
    total_msgs = len(llm_messages) - 1  # Exclude system
    print(f"\nTotal para LLM: {total_msgs} mensagens + System Prompt")


def example_2_memory_overflow():
    """Exemplo 2: O que acontece quando histórico excede limite."""
    print("\n" + "="*70)
    print("EXEMPLO 2: Buffer Cheio - O que Fica/Sai")
    print("="*70)
    
    # Simular buffer com limite de 50 (padrão)
    print("\nScenario: Conversa muito longa com 60 mensagens")
    print("- Buffer em RAM: máximo 50 mensagens")
    print("- LLM recebe: máximo 10 mensagens")
    print("- Banco de dados: TODAS as 60 mensagens")
    
    # Criar 60 mensagens
    all_messages = []
    for i in range(60):
        role = "user" if i % 2 == 0 else "assistant"
        all_messages.append(Message(role=role, content=f"Message {i+1}"))
    
    print(f"\nTotal de mensagens geradas: {len(all_messages)}")
    
    # O que fica no buffer (últimas 50)
    buffer = all_messages[-50:]
    print(f"Buffer em RAM: {len(buffer)} mensagens")
    print(f"  Primeira: {buffer[0].content}")
    print(f"  Última: {buffer[-1].content}")
    print(f"  (Mensagens 1-10 foram removidas do buffer)")
    
    # O que vai para LLM (últimas 10 do buffer)
    llm_context = buffer[-10:]
    print(f"\nLLM recebe: {len(llm_context)} mensagens")
    print(f"  Primeira: {llm_context[0].content}")
    print(f"  Última: {llm_context[-1].content}")
    print(f"  (Mensagens 41-50 do buffer NÃO vão para LLM)")
    
    # O que está no banco (TODAS as 60)
    print(f"\nBanco de dados: {len(all_messages)} mensagens")
    print(f"  Primeira: {all_messages[0].content}")
    print(f"  Última: {all_messages[-1].content}")
    print(f"  Acessível via: ferramentas, memory_manager, busca")


def example_3_token_economy():
    """Exemplo 3: Economia de tokens."""
    print("\n" + "="*70)
    print("EXEMPLO 3: Economia de Tokens")
    print("="*70)
    
    # Estimativa: ~30-50 tokens por mensagem média
    tokens_per_message = 40
    
    print(f"\nEstimates (considerando {tokens_per_message} tokens/msg média)")
    
    scenarios = [
        ("Curta (5 msgs)", 5),
        ("Média (20 msgs)", 20),
        ("Longa (50 msgs)", 50),
        ("Muito longa (100 msgs)", 100),
    ]
    
    print(f"\n{'Scenario':<20} | {'Antes':<15} | {'Depois':<15} | {'Economia':<10}")
    print("-" * 70)
    
    for name, total_msgs in scenarios:
        before_tokens = total_msgs * tokens_per_message
        # LLM acessa apenas últimas 10
        after_msgs = min(10, total_msgs)
        after_tokens = after_msgs * tokens_per_message
        saved = ((before_tokens - after_tokens) / before_tokens * 100) if before_tokens > 0 else 0
        
        print(f"{name:<20} | {before_tokens:<15} | {after_tokens:<15} | {saved:.0f}%")


def example_4_system_prompt_position():
    """Exemplo 4: System Prompt sempre no topo."""
    print("\n" + "="*70)
    print("EXEMPLO 4: Posição do System Prompt")
    print("="*70)
    
    system_prompt = """Você é o Quinta-Feira.
Características: Pragmático, diz 'não sei' quando não sabe."""
    
    conversation = [
        ("user", "Olá"),
        ("assistant", "Oi!"),
        ("user", "Qual é o PI?"),
        ("assistant", "π ≈ 3.14159"),
    ]
    
    print(f"\nMensagens preparadas para Gemini:")
    print(f"\n[0] SYSTEM (SEMPRE AQUI)")
    print(f"    {system_prompt.split(chr(10))[0]}")  # Primeira linha
    print(f"    ...")
    
    for i, (role, content) in enumerate(conversation, start=1):
        print(f"\n[{i}] {role.upper()}")
        print(f"    {content}")
    
    print(f"\n✓ Sistema Prompt SEMPRE index [0]")
    print(f"✓ Mensagens começam index [1]")
    print(f"✓ Garante que instruções sempre influenciam decisão do LLM")


def example_5_accessing_old_messages():
    """Exemplo 5: Como acessar mensagens antigas."""
    print("\n" + "="*70)
    print("EXEMPLO 5: Acessando Mensagens Antigas")
    print("="*70)
    
    print("""
CENÁRIO:
Conversa com 50 mensagens. LLM recebe apenas últimas 10.
Como acessar a primeira mensagem?

SOLUÇÃO 1: Usar método get_messages() sem limite
    history = MessageHistory()
    # ... adicionar 50 msgs ...
    all_messages = history.get_messages()  # Retorna todas as 50
    first_msg = all_messages[0]
    print(f"Primeira mensagem: {first_msg.content}")

SOLUÇÃO 2: Usar memory_manager tool (recomendado)
    await brain.execute_tool_call({
        "name": "memory_manager",
        "arguments": {
            "action": "retrieve_memory",
            "query": "qual foi o primeiro assunto?"
        }
    })
    # Busca no banco e retorna contexto relevante

SOLUÇÃO 3: Busca semântica (futuro)
    results = await database.semantic_search(
        query="conversas sobre météo",
        session_id="session123"
    )
    # Retorna mensagens semanticamente similares
    """)


def example_6_complete_flow():
    """Exemplo 6: Fluxo completo."""
    print("\n" + "="*70)
    print("EXEMPLO 6: Fluxo Completo (Simulado)")
    print("="*70)
    
    print("""
USER diz: "Qual é o resultado de 2+2?"

FLUXO INTERNO:
┌────────────────────────────────────────────────────────────┐
│ 1. Adicionar mensagem ao buffer de curto prazo             │
│    history.add("user", "Qual é o resultado de 2+2?")      │
└────────────────────────────────────────────────────────────┘
                           ↓
┌────────────────────────────────────────────────────────────┐
│ 2. Preparar contexto para Gemini                           │
│    llm_messages = [system_prompt]                          │
│    llm_messages.extend(                                    │
│        history.get_recent_messages_for_llm(limit=10)      │
│    )                                                        │
│    # llm_messages agora tem: 1 system + até 10 msgs        │
└────────────────────────────────────────────────────────────┘
                           ↓
┌────────────────────────────────────────────────────────────┐
│ 3. Chamar Gemini API                                       │
│    response = gemini.generate(llm_messages)                │
│    # Usa apenas as últimas 10 msgs para economizar tokens  │
└────────────────────────────────────────────────────────────┘
                           ↓
┌────────────────────────────────────────────────────────────┐
│ 4. Adicionar resposta ao buffer                            │
│    history.add("assistant", "2+2 = 4")                    │
└────────────────────────────────────────────────────────────┘
                           ↓
┌────────────────────────────────────────────────────────────┐
│ 5. Persistir no banco de dados                             │
│    database.add_message(user="assistant", content="...")   │
│    # Banco agora tem TODAS as mensagens                    │
└────────────────────────────────────────────────────────────┘
                           ↓
┌────────────────────────────────────────────────────────────┐
│ 6. Retornar resposta para o usuário                        │
│    return BrainResponse(text="2+2 = 4", ...)               │
└────────────────────────────────────────────────────────────┘

RESULTADO:
✓ Sistema Prompt influi na decisão
✓ Últimas 10 msgs dão contexto imediato
✓ Tokens economizados (~80%)
✓ Histórico completo preservado no banco
✓ Usuário não vê nenhuma mudança
    """)


if __name__ == "__main__":
    print("\n" + "█" * 70)
    print("█" + " " * 68 + "█")
    print("█" + "  EXEMPLOS PRÁTICOS: MEMÓRIA DE CURTO PRAZO".center(68) + "█")
    print("█" + " " * 68 + "█")
    print("█" * 70)
    
    example_1_basic_usage()
    example_2_memory_overflow()
    example_3_token_economy()
    example_4_system_prompt_position()
    example_5_accessing_old_messages()
    example_6_complete_flow()
    
    print("\n" + "█" * 70)
    print("█" + "  FIM DOS EXEMPLOS".center(68) + "█")
    print("█" * 70 + "\n")
