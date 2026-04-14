#!/usr/bin/env python3
"""
Teste rigoroso de integração da Memória de Curto Prazo.
Verifica se o sistema realmente limita mensagens para o LLM.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from brain.quinta_feira_brain import QuintaFeiraBrain, MessageHistory, Message
import asyncio

async def test_integration():
    """Teste de integração completo"""
    
    print("\n" + "="*70)
    print("TESTE DE INTEGRAÇÃO - MEMÓRIA DE CURTO PRAZO")
    print("="*70)
    
    # 1. Criar instância do cérebro
    brain = QuintaFeiraBrain()
    
    # 2. Adicionar 30 mensagens de teste
    print("\n[1] Adicionando 30 mensagens de teste...")
    for i in range(1, 31):
        brain.message_history.add(
            role="user" if i % 2 == 1 else "assistant",
            content=f"Mensagem {i}: {'Pergunta' if i % 2 == 1 else 'Resposta'}"
        )
    
    total_in_history = len(brain.message_history.get_messages())
    print(f"    ✓ Total no histórico: {total_in_history}")
    
    # 3. Verificar get_recent_messages_for_llm
    print("\n[2] Testando get_recent_messages_for_llm(limit=10)...")
    recent_10 = brain.message_history.get_recent_messages_for_llm(limit=10)
    print(f"    ✓ Mensagens retornadas: {len(recent_10)}")
    if len(recent_10) > 0:
        print(f"    ✓ Primeira (índice 0): {recent_10[0].content[:50]}")
        print(f"    ✓ Última (índice -1): {recent_10[-1].content[:50]}")
    
    # 4. Verificar que são realmente as ÚLTIMAS 10
    print("\n[3] Verificando se são as ÚLTIMAS 10 mensagens...")
    all_messages = brain.message_history.get_messages()
    expected_first = all_messages[-10] if len(all_messages) >= 10 else all_messages[0]
    expected_last = all_messages[-1]
    
    if recent_10[0].content == expected_first.content and recent_10[-1].content == expected_last.content:
        print(f"    ✓ CORRETO: São as últimas 10 mensagens do histórico")
    else:
        print(f"    ✗ ERRO: Não são as últimas 10 mensagens!")
        return False
    
    # 5. Simular construção do contexto para LLM (como em ask())
    print("\n[4] Simulando construção de contexto para LLM...")
    system_prompt = "Você é um assistente útil."
    llm_messages = [Message(role="system", content=system_prompt)]
    llm_messages.extend(brain.message_history.get_recent_messages_for_llm(limit=10))
    
    print(f"    ✓ Mensagens para LLM: {len(llm_messages)}")
    print(f"      - 1ª é system prompt: {llm_messages[0].role == 'system'}")
    print(f"      - Restantes: {len(llm_messages) - 1} mensagens de contexto")
    
    if len(llm_messages) != 11:  # 1 system + 10 histórico
        print(f"    ✗ ERRO: Esperava 11 mensagens (1 system + 10 histórico), mas tem {len(llm_messages)}")
        return False
    
    # 6. Teste com pouquíssimas mensagens
    print("\n[5] Testando com poucas mensagens (3 total)...")
    small_history = MessageHistory()
    for i in range(3):
        small_history.add(role="user", content=f"Msg {i+1}")
    
    small_recent = small_history.get_recent_messages_for_llm(limit=10)
    print(f"    ✓ Com 3 mensagens, retorna: {len(small_recent)} (esperado: 3)")
    if len(small_recent) != 3:
        print(f"    ✗ ERRO: Esperava 3, retornou {len(small_recent)}")
        return False
    
    # 7. Teste com 0 mensagens
    print("\n[6] Testando com 0 mensagens...")
    empty_history = MessageHistory()
    empty_recent = empty_history.get_recent_messages_for_llm(limit=10)
    print(f"    ✓ Com 0 mensagens, retorna: {len(empty_recent)} (esperado: 0)")
    if len(empty_recent) != 0:
        print(f"    ✗ ERRO: Esperava 0, retornou {len(empty_recent)}")
        return False
    
    print("\n" + "="*70)
    print("✅ TODOS OS TESTES DE INTEGRAÇÃO PASSARAM")
    print("="*70)
    return True

if __name__ == "__main__":
    try:
        result = asyncio.run(test_integration())
        sys.exit(0 if result else 1)
    except Exception as e:
        print(f"\n❌ ERRO CRÍTICO: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
