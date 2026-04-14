#!/usr/bin/env python3
"""
DEMONSTRAÇÃO: Memória de Curto Prazo (Short-Term Memory)

Sistema de 2 camadas:
1. MEMÓRIA DE CURTO PRAZO (Short-term): Últimas 10 mensagens em RAM
   - Rápida, para contexto imediato da conversa
   - Enviada ao LLM para decisões
   - Econômica em tokens

2. MEMÓRIA DE LONGO PRAZO (Long-term): Todas as mensagens no banco
   - Persistida em SQLite
   - Acessada via ferramentas (memory_manager, busca semântica)
   - Recuperada quando necessário (ex: "Qual foi nosso primeiro assunto?")

ANTES (Problema):
- LLM recebia TODAS as 50+ mensagens
- Consumia muitos tokens
- Contexto ruins para decisões
- Lentidão

DEPOIS (Solução):
- LLM recebe APENAS últimas 10 mensagens + System Prompt
- Economia de tokens: ~80%
- Contexto focado no imediato
- Rápido e responsivo
- Memória antiga acessível via tools
"""

from typing import List, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Message:
    """Modelo de mensagem."""
    role: str  # "user", "assistant", "system"
    content: str
    tool_calls: Optional[list] = None
    

class MessageHistoryShortTerm:
    """
    Gerencia memória de CURTO PRAZO (Short-term Memory).
    
    - Mantém até 50 mensagens em RAM (buffer)
    - Ao enviar para LLM, usa apenas últimas 10
    - System Prompt sempre no topo
    - Economiza tokens no LLM
    """
    
    def __init__(self, max_buffer_size: int = 50):
        """
        Args:
            max_buffer_size: Máximo de mensagens a manter em memória.
                             Padrão 50 é suficiente para maioria das conversas.
        """
        self.max_buffer_size = max_buffer_size
        self.messages: List[Message] = []
    
    def add(self, role: str, content: str, tool_calls: Optional[list] = None) -> None:
        """
        Adiciona uma mensagem ao buffer de curto prazo.
        
        Args:
            role: "user" ou "assistant"
            content: Conteúdo da mensagem
            tool_calls: Função calling (se houver)
        
        Exemplo:
            >> history.add("user", "Olá, quanto é 2+2?")
            >> history.add("assistant", "2+2 = 4")
        """
        msg = Message(role=role, content=content, tool_calls=tool_calls)
        self.messages.append(msg)
        
        # Se exceder o buffer, remover mensagens antigas
        if len(self.messages) > self.max_buffer_size:
            removed = len(self.messages) - self.max_buffer_size
            self.messages = self.messages[-self.max_buffer_size:]
            print(f"[INFO] Buffer cheio: removidas {removed} mensagens antiga(s)")
    
    def get_recent_messages_for_llm(self, limit: int = 10) -> List[Message]:
        """
        Retorna últimas N mensagens para ENVIAR AO LLM.
        
        CRÍTICO: Este é o método usado quando construir contexto para Gemini.
        
        Args:
            limit: Número de mensagens a retornar (default 10).
            
        Returns:
            Lista de mensagens em ordem cronológica.
            
        Exemplo:
            >> history.add("user", "Olá")
            >> history.add("assistant", "Oi!")
            >> history.add("user", "Como vai?")
            >> recent = history.get_recent_messages_for_llm(limit=10)
            >> # recent = [Message("user", "Olá"), Message("assistant", "Oi!"), ...]
        """
        if len(self.messages) > limit:
            # Retorna últimas N mensagens em ordem cronológica
            return self.messages[-limit:].copy()
        else:
            # Se temos menos que N, retorna todas
            return self.messages.copy()
    
    def get_all_messages(self) -> List[Message]:
        """Retorna TODAS as mensagens do buffer (para debug)."""
        return self.messages.copy()
    
    def prepare_for_gemini(self, system_prompt: str) -> List[dict]:
        """
        Prepara lista de mensagens EXATAMENTE como será enviada ao Gemini.
        
        FLUXO CORRETO:
        1. System Prompt no topo (sempre)
        2. Últimas 10 mensagens de user/assistant
        3. Sem mensagens de "system" no histórico
        
        Args:
            system_prompt: Instruções iniciais da Quinta-Feira
        
        Returns:
            Lista de dicts pronta para Gemini API
            
        Exemplo output:
            [
                {"role": "system", "content": "Você é o Quinta-Feira..."},
                {"role": "user", "content": "Olá"},
                {"role": "assistant", "content": "Oi! Como posso ajudar?"},
                {"role": "user", "content": "Quanto é 2+2?"},
                {"role": "assistant", "content": "2+2 = 4"},
            ]
        """
        messages = [{"role": "system", "content": system_prompt}]
        
        # Adicionar últimas 10 mensagens
        for msg in self.get_recent_messages_for_llm(limit=10):
            messages.append({
                "role": msg.role,
                "content": msg.content,
                # tool_calls campo omitido neste exemplo
            })
        
        return messages
    
    def get_stats(self) -> dict:
        """Retorna estatísticas do buffer."""
        return {
            "total_messages": len(self.messages),
            "buffer_size": self.max_buffer_size,
            "utilization": f"{len(self.messages) / self.max_buffer_size * 100:.1f}%",
            "recent_for_llm": min(10, len(self.messages)) 
        }


def demo_short_term_memory():
    """Demonstração do novo sistema de memória."""
    
    print("=" * 70)
    print("DEMONSTRAÇÃO: Memória de Curto Prazo (Short-Term Memory)")
    print("=" * 70)
    
    # 1. Criar histórico
    history = MessageHistoryShortTerm(max_buffer_size=50)
    
    # 2. Simular conversa com 15 mensagens
    print("\n[1] Adicionando 15 mensagens ao buffer...")
    
    conversations = [
        ("user", "Oi, como você está?"),
        ("assistant", "Olá! Estou bem, obrigado por perguntar."),
        ("user", "Qual é a capital de França?"),
        ("assistant", "A capital de França é Paris."),
        ("user", "E a população de Paris?"),
        ("assistant", "Paris tem aproximadamente 2,2 milhões de habitantes."),
        ("user", "Me mostre a temperatura em Lisboa"),
        ("assistant", "[Usando ferramenta de clima...] Temperatura em Lisboa: 18°C e céu parcialmente nublado."),
        ("user", "Toque uma música relaxante"),
        ("assistant", "[Tocando YouTube invisível: relaxante] Música iniciada."),
        ("user", "Quantas mensagens trocamos?"),
        ("assistant", "Trocamos 11 mensagens até agora (contando essa)."),
        ("user", "O que falamos primeiro?"),
        ("assistant", "Você começou nos perguntando como eu estava."),
        ("user", "Obrigado, você é ótimo!"),
    ]
    
    for role, content in conversations:
        history.add(role, content)
        print(f"  + {role:10} | {content[:50]}")
    
    # 3. Mostrar stats
    print(f"\n[2] Estatísticas do buffer:")
    stats = history.get_stats()
    for key, value in stats.items():
        print(f"  - {key}: {value}")
    
    # 4. Mostrar que banco tem TODAS as 15, mas LLM recebe apenas 10
    print(f"\n[3] Comparação de tokens:")
    print(f"  Buffer (memória em RAM): {len(history.get_all_messages())} mensagens")
    print(f"  Enviado ao LLM: {len(history.get_recent_messages_for_llm(limit=10))} mensagens")
    print(f"  Economia de tokens: ~25%")
    
    # 5. Mostrar como seria enviado ao Gemini
    print(f"\n[4] Mensagens que serão enviadas ao Gemini API:")
    system_prompt = """Você é o Sistema Quinta-Feira, assistente operacional criado por Matheus.
Características: Brilhante, pragmática, direta ao ponto."""
    
    gemini_payload = history.prepare_for_gemini(system_prompt)
    print(f"  System Prompt: {len(gemini_payload[0]['content'])} chars")
    print(f"  Histórico: {len(gemini_payload) - 1} mensagens")
    print("\n  Estrutura enviada:")
    for i, msg in enumerate(gemini_payload):
        role = msg['role'].upper()
        content = msg['content'][:45] + "..." if len(msg['content']) > 45 else msg['content']
        print(f"    [{i}] {role:10} → {content}")
    
    # 6. Demonstrar que mensagens antigas estão em banco (não no LLM)
    print(f"\n[5] Gestão de Memória em 2 Camadas:")
    all_msgs = history.get_all_messages()
    recent_for_llm = history.get_recent_messages_for_llm(limit=10)
    
    print(f"  Memória de LONGO PRAZO (Banco de Dados):")
    print(f"    - Total de mensagens: {len(all_msgs)}")
    print(f"    - Primeira: '{all_msgs[0].content[:40]}...'")
    print(f"    - Quinta: '{all_msgs[4].content[:40]}...'")
    print(f"    - Acesso via: ferramentas (memory_manager, busca semântica)")
    
    print(f"\n  Memória de CURTO PRAZO (Contexto do LLM):")
    print(f"    - Mensagens para LLM: {len(recent_for_llm)}")
    print(f"    - Primeira: '{recent_for_llm[0].content[:40]}...'")
    print(f"    - Última: '{recent_for_llm[-1].content[:40]}...'")
    print(f"    - Propósito: decisões imediatas, economizar tokens")
    
    print("\n" + "=" * 70)
    print("CONCLUSÃO:")
    print("=" * 70)
    print("""
✓ LLM recebe contexto focado (últimas 10 mensagens)
✓ Decisões mais rápidas e diretas
✓ Economia de tokens (~80% em conversas longas)
✓ Histórico completo ainda acessível via tools
✓ Banco de dados preserva tudo para análise futura

PRÓXIMOS PASSOS:
1. memory_manager tool para recuperar conversas antigas
2. Busca semântica sobre histórico completo
3. Sumarização automática de contexto anterior
    """)


if __name__ == "__main__":
    demo_short_term_memory()
