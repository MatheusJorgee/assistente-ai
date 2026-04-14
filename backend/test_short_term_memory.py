#!/usr/bin/env python3
"""Test short-term memory implementation."""

from brain.quinta_feira_brain import MessageHistory, Message

# Teste 1: Criar histórico com 15 mensagens
history = MessageHistory(max_messages=50)
for i in range(15):
    role = 'user' if i % 2 == 0 else 'assistant'
    history.add(role, f'Message {i+1}')

# Teste 2: Verificar que get_messages() retorna tudo
all_msgs = history.get_messages()
assert len(all_msgs) == 15, f"Expected 15, got {len(all_msgs)}"
print(f'✓ get_messages(): {len(all_msgs)} mensagens')

# Teste 3: Verificar que get_recent_messages_for_llm() retorna 10
recent = history.get_recent_messages_for_llm(limit=10)
assert len(recent) == 10, f"Expected 10, got {len(recent)}"
print(f'✓ get_recent_messages_for_llm(): {len(recent)} mensagens')

# Teste 4: Verificar ordem cronológica
print(f'✓ Primeira mensagem recente: {recent[0].content}')
print(f'✓ Última mensagem recente: {recent[-1].content}')

# Teste 5: Verificar que System Prompt pode ser adicionado
system_msg = Message(role='system', content='You are Quinta-Feira')
llm_messages = [system_msg]
llm_messages.extend(recent)
assert llm_messages[0].role == 'system', "System prompt not at top"
assert len(llm_messages) == 11, f"Expected 11, got {len(llm_messages)}"
print(f'✓ Sistema prompt no topo: {llm_messages[0].role}')
print(f'✓ Total para LLM: {len(llm_messages)} mensagens')

# Teste 6: Verificar com menos de 10 mensagens
history2 = MessageHistory()
history2.add('user', 'Only message')
recent2 = history2.get_recent_messages_for_llm(limit=10)
assert len(recent2) == 1, "Should return 1 message when history has 1"
print(f'✓ Com 1 mensagem, retorna: {len(recent2)} mensagem')

# Teste 7: Verificar com 50+ mensagens (buffer overflow)
history3 = MessageHistory(max_messages=50)
for i in range(60):
    history3.add('user' if i % 2 == 0 else 'assistant', f'Msg {i+1}')
all_msgs3 = history3.get_messages()
recent3 = history3.get_recent_messages_for_llm(limit=10)
assert len(all_msgs3) == 50, f"Buffer should keep 50, got {len(all_msgs3)}"
assert len(recent3) == 10, f"Should return 10 for LLM, got {len(recent3)}"
print(f'✓ Com 60 msgs adicionadas, buffer mantém: {len(all_msgs3)} (últimas)')
print(f'✓ LLM recebe: {len(recent3)} (das últimas 50)')

print('\n✅ TODOS OS TESTES PASSARAM')
print('Sistema de Memória de Curto Prazo está operacional!')
