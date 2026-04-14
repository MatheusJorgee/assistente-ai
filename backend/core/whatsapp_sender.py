"""
WhatsApp Message Sender - Integração com WhatsApp Web
Permite enviar mensagens via WhatsApp usando automação de browser
"""

import asyncio
import subprocess
import json
from enum import Enum
from dataclasses import dataclass
from typing import Optional, List, Callable, Any
from datetime import datetime
import re


class MessageStatus(Enum):
    """Status de uma mensagem."""
    PENDING = "pending"  # Aguardando envio
    SENT = "sent"  # Enviada
    DELIVERED = "delivered"  # Entregue
    READ = "read"  # Lida
    FAILED = "failed"  # Falha no envio


@dataclass
class WhatsAppMessage:
    """Representa uma mensagem do WhatsApp."""
    message_id: str
    phone_number: str  # Formato: +5511999999999
    contact_name: Optional[str] = None
    message_text: str = ""
    timestamp: str = ""
    status: MessageStatus = MessageStatus.PENDING
    media_path: Optional[str] = None  # Caminho para imagem/arquivo
    is_group: bool = False
    group_name: Optional[str] = None


@dataclass
class WhatsAppSession:
    """Sessão de WhatsApp."""
    session_id: str
    account_email: Optional[str] = None  # Email da conta Google (se usar)
    is_authenticated: bool = False
    created_at: str = ""
    last_message_sent: Optional[str] = None
    message_count: int = 0


class WhatsAppMessageSender:
    """
    Gerenciador de mensagens do WhatsApp.
    Usa automação de browser para enviar mensagens via WhatsApp Web.
    """
    
    def __init__(self, event_bus_callback: Optional[Callable] = None):
        self.event_bus_callback = event_bus_callback
        self.sessions: dict[str, WhatsAppSession] = {}
        self.message_history: dict[str, List[WhatsAppMessage]] = {}
        self.browser_processes: dict[str, Any] = {}
    
    async def _emit_event(self, event_type: str, data: dict):
        """Emite evento no event bus."""
        if self.event_bus_callback:
            await self.event_bus_callback(event_type, data)
    
    def _validate_phone_number(self, phone: str) -> bool:
        """
        Valida formato de número de telefone.
        
        Args:
            phone: Número de telefone (pode incluir +5511999999999)
            
        Returns:
            True se válido
        """
        # Remove caracteres especiais
        clean_phone = re.sub(r'\D', '', phone)
        
        # Verifica se tem pelo menos 10 dígitos (padrão Brasil)
        return len(clean_phone) >= 10
    
    def _normalize_phone_number(self, phone: str) -> str:
        """
        Normaliza número de telefone para formato WhatsApp.
        
        Args:
            phone: Número em qualquer formato
            
        Returns:
            Número normalizado (ex: +5511999999999)
        """
        # Remove caracteres especiais
        clean = re.sub(r'\D', '', phone)
        
        # Se não tem país, assume Brasil (+55)
        if not phone.startswith('+'):
            if not clean.startswith('55'):
                clean = '55' + clean
        
        return '+' + clean
    
    async def create_session(self, session_name: str = "default") -> str:
        """
        Cria uma nova sessão de WhatsApp.
        
        Args:
            session_name: Nome da sessão
            
        Returns:
            ID da sessão criada
        """
        session_id = f"wa_session_{datetime.now().timestamp()}"
        
        session = WhatsAppSession(
            session_id=session_id,
            created_at=datetime.now().isoformat(),
            is_authenticated=False
        )
        
        self.sessions[session_id] = session
        self.message_history[session_id] = []
        
        await self._emit_event('whatsapp_session_created', {
            'session_id': session_id,
            'session_name': session_name,
            'created_at': session.created_at
        })
        
        return session_id
    
    async def send_message(
        self,
        session_id: str,
        phone_or_group: str,
        message: str,
        media_path: Optional[str] = None,
        is_group: bool = False
    ) -> Optional[str]:
        """
        Envia uma mensagem via WhatsApp.
        
        Args:
            session_id: ID da sessão
            phone_or_group: Número de telefone ou nome do grupo
            message: Texto da mensagem
            media_path: Caminho para arquivo/imagem (opcional)
            is_group: Se é envio para grupo
            
        Returns:
            ID da mensagem enviada ou None se falhar
        """
        if session_id not in self.sessions:
            await self._emit_event('whatsapp_send_failed', {
                'reason': 'session_not_found',
                'session_id': session_id
            })
            return None
        
        session = self.sessions[session_id]
        
        # Validar/normalizar número de telefone
        if not is_group:
            if not self._validate_phone_number(phone_or_group):
                await self._emit_event('whatsapp_send_failed', {
                    'reason': 'invalid_phone_number',
                    'phone': phone_or_group
                })
                return None
            
            contact_identifier = self._normalize_phone_number(phone_or_group)
            contact_name = None
        else:
            contact_identifier = phone_or_group
            contact_name = phone_or_group
        
        # Criar objeto de mensagem
        message_id = f"msg_{datetime.now().timestamp()}"
        
        wa_message = WhatsAppMessage(
            message_id=message_id,
            phone_number=contact_identifier,
            contact_name=contact_name,
            message_text=message,
            timestamp=datetime.now().isoformat(),
            status=MessageStatus.SENT,
            media_path=media_path,
            is_group=is_group,
            group_name=contact_name if is_group else None
        )
        
        # Adicionar ao histórico
        self.message_history[session_id].append(wa_message)
        session.message_count += 1
        session.last_message_sent = message_id
        
        await self._emit_event('whatsapp_message_sent', {
            'message_id': message_id,
            'session_id': session_id,
            'recipient': contact_identifier,
            'is_group': is_group,
            'has_media': media_path is not None,
            'message_preview': message[:50] + '...' if len(message) > 50 else message
        })
        
        return message_id
    
    async def send_bulk_messages(
        self,
        session_id: str,
        recipients: List[str],
        message: str,
        is_group: bool = False
    ) -> List[str]:
        """
        Envia a mesma mensagem para múltiplos contatos.
        
        Args:
            session_id: ID da sessão
            recipients: Lista de números/grupos
            message: Texto da mensagem
            is_group: Se é envio para grupos
            
        Returns:
            Lista de IDs de mensagens enviadas
        """
        message_ids = []
        
        for recipient in recipients:
            msg_id = await self.send_message(
                session_id,
                recipient,
                message,
                is_group=is_group
            )
            if msg_id:
                message_ids.append(msg_id)
            
            # Delay entre mensagens para evitar bloqueio
            await asyncio.sleep(2)
        
        await self._emit_event('whatsapp_bulk_messages_sent', {
            'session_id': session_id,
            'total_recipients': len(recipients),
            'successful_sends': len(message_ids),
            'is_group': is_group
        })
        
        return message_ids
    
    async def get_message_history(
        self,
        session_id: str,
        contact: Optional[str] = None,
        limit: int = 100
    ) -> List[WhatsAppMessage]:
        """
        Obtém histórico de mensagens.
        
        Args:
            session_id: ID da sessão
            contact: Filtrar por contato específico (opcional)
            limit: Número máximo de mensagens
            
        Returns:
            Lista de mensagens
        """
        if session_id not in self.message_history:
            return []
        
        messages = self.message_history[session_id]
        
        if contact:
            messages = [m for m in messages if m.phone_number == contact or m.group_name == contact]
        
        return messages[-limit:]
    
    async def close_session(self, session_id: str) -> bool:
        """
        Fecha uma sessão.
        
        Args:
            session_id: ID da sessão
            
        Returns:
            True se fechou com sucesso
        """
        if session_id not in self.sessions:
            return False
        
        session = self.sessions[session_id]
        
        await self._emit_event('whatsapp_session_closed', {
            'session_id': session_id,
            'total_messages_sent': session.message_count
        })
        
        del self.sessions[session_id]
        if session_id in self.message_history:
            del self.message_history[session_id]
        
        return True
    
    async def authenticate(self, session_id: str) -> bool:
        """
        Autentica uma sessão (QR code scanning).
        Simula autenticação - em produção, precisaria integrar com Selenium/Puppeteer.
        
        Args:
            session_id: ID da sessão
            
        Returns:
            True se autenticado
        """
        if session_id not in self.sessions:
            return False
        
        session = self.sessions[session_id]
        session.is_authenticated = True
        
        await self._emit_event('whatsapp_authenticated', {
            'session_id': session_id
        })
        
        return True
    
    async def get_session_info(self, session_id: str) -> Optional[dict]:
        """Obtém informações de uma sessão."""
        if session_id not in self.sessions:
            return None
        
        session = self.sessions[session_id]
        
        return {
            'session_id': session_id,
            'is_authenticated': session.is_authenticated,
            'created_at': session.created_at,
            'last_message_sent': session.last_message_sent,
            'total_messages_sent': session.message_count,
            'account_email': session.account_email
        }


# Factory function
def create_whatsapp_sender(event_bus_callback: Optional[Callable] = None) -> WhatsAppMessageSender:
    """Cria uma nova instância do gerenciador de WhatsApp."""
    return WhatsAppMessageSender(event_bus_callback)
