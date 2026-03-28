# YouTube Loop + WhatsApp Integration - Documentação

## 🎵 YouTube Loop Manager

### Funcionalidades

- ✅ Criar sessões de loop no YouTube
- ✅ Suportar múltiplos modos de repetição:
  - `SINGLE`: Repetir uma faixa
  - `ALL`: Repetir playlist inteira
  - `SHUFFLE`: Modo aleatória com repetição
  - `OFF`: Sem repetição

- ✅ Controles: Start, Pause, Resume, Stop
- ✅ Extração de video ID de múltiplos formatos de URL
- ✅ Gerenciamento de múltiplas sessões simultâneas
- ✅ Sistema de eventos para rastreabilidade

### Uso Básico

```python
from backend.core import create_youtube_loop_manager, YouTubeLoopMode
import asyncio

async def main():
    manager = create_youtube_loop_manager()
    
    # Criar sessão de loop
    session = await manager.create_loop_session(
        video_url_or_id="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        title="Never Gonna Give You Up",
        loop_mode=YouTubeLoopMode.SINGLE
    )
    
    # Iniciar loop
    await manager.start_loop(session.session_id)
    
    # Alterar modo
    await manager.set_loop_mode(session.session_id, YouTubeLoopMode.ALL)
    
    # Obter status
    status = await manager.get_session_status(session.session_id)
    print(f"Status: {status}")
    
    # Parar
    await manager.stop_loop(session.session_id)

asyncio.run(main())
```

### Formatos de URL Suportados

```python
# URL completa
https://www.youtube.com/watch?v=dQw4w9WgXcQ

# URL curta
https://youtu.be/dQw4w9WgXcQ

# ID direto
dQw4w9WgXcQ

# URL de embed
https://www.youtube.com/embed/dQw4w9WgXcQ
```

---

## 💬 WhatsApp Message Sender

### Funcionalidades

- ✅ Criar sessões autenticadas de WhatsApp
- ✅ Enviar mensagens individuais
- ✅ Envio em massa (bulk)
- ✅ Suporte a grupos e contatos
- ✅ Validação e normalização de números
- ✅ Histórico de mensagens
- ✅ Rastreamento de status
- ✅ Sistema de eventos

### Uso Básico

```python
from backend.core import create_whatsapp_sender
import asyncio

async def main():
    sender = create_whatsapp_sender()
    
    # Criar sessão
    session_id = await sender.create_session("minha_sessao")
    
    # Enviar mensagem simples
    msg_id = await sender.send_message(
        session_id=session_id,
        phone_or_group="5511999999999",
        message="Olá! Esta é uma mensagem de teste."
    )
    
    print(f"Mensagem enviada: {msg_id}")
    
    # Enviar para múltiplos contatos
    recipients = [
        "5511999999999",
        "5521999999999",
        "5585999999999"
    ]
    
    message_ids = await sender.send_bulk_messages(
        session_id=session_id,
        recipients=recipients,
        message="Notificação importante para você!"
    )
    
    print(f"Enviadas {len(message_ids)} mensagens")
    
    # Obter histórico
    history = await sender.get_message_history(session_id)
    print(f"Total de mensagens: {len(history)}")

asyncio.run(main())
```

### Formatos de Telefone Suportados

```python
# Formato completo
"+5511999999999"

# Sem +55
"11999999999"

# Com formatação
"11 99999-9999"
"(11) 9999-9999"

# Todos são normalizados para: +5511999999999
```

---

## 🔗 Integração com Sistema

### No main.py

```python
from backend.core import (
    create_youtube_loop_manager,
    create_whatsapp_sender,
    YouTubeLoopMode
)

# Inicializar managers
youtube_manager = create_youtube_loop_manager(event_bus_callback=handle_event)
whatsapp_sender = create_whatsapp_sender(event_bus_callback=handle_event)

# Em handlers WebSocket
async def handle_command(command):
    if command.startswith("loop_youtube"):
        # Extract URL and mode
        parts = command.split("|")
        url = parts[1]
        mode = YouTubeLoopMode.SINGLE
        
        session = await youtube_manager.create_loop_session(url, "Música", mode)
        await youtube_manager.start_loop(session.session_id)
        
    elif command.startswith("send_whatsapp"):
        # Parse recipient and message
        parts = command.split("|")
        recipient = parts[1]
        message = parts[2]
        
        session_id = await whatsapp_sender.create_session()
        await whatsapp_sender.send_message(session_id, recipient, message)
```

---

## 📊 Estrutura de Dados

### YouTubeVideo
```python
@dataclass
class YouTubeVideo:
    video_id: str           # ID único do vídeo
    title: str              # Título
    duration_seconds: int   # Duração em segundos
    is_music: bool          # É música?
    url: Optional[str]      # URL completa
```

### LoopSession (YouTube)
```python
@dataclass
class LoopSession:
    session_id: str         # ID único da sessão
    video: YouTubeVideo     # Vídeo
    loop_mode: YouTubeLoopMode  # Modo de repetição
    browser_type: str       # Tipo: chrome, firefox, edge
    started_at: str         # Timestamp de início
    loop_count: int         # Contador de loops
    current_time_seconds: int  # Tempo atual
    is_playing: bool        # Tocando?
```

### WhatsAppMessage
```python
@dataclass
class WhatsAppMessage:
    message_id: str         # ID único
    phone_number: str       # Número de telefone
    contact_name: Optional[str]  # Nome do contato
    message_text: str       # Texto da mensagem
    timestamp: str          # Quando foi enviada
    status: MessageStatus   # Status (pending, sent, delivered, read, failed)
    media_path: Optional[str]  # Caminho para arquivo/imagem
    is_group: bool          # É grupo?
    group_name: Optional[str]  # Nome do grupo
```

---

## 🧪 Testes

Execute os testes com:

```bash
cd backend
python teste_novas_features.py
```

Resultado esperado: **7/7 testes passando**

- ✅ YouTube Loop - Session Creation
- ✅ YouTube Loop - Operations
- ✅ YouTube Loop - Video Extraction
- ✅ WhatsApp - Session Creation
- ✅ WhatsApp - Message Sending
- ✅ WhatsApp - Bulk Send
- ✅ WhatsApp - Phone Validation

---

## 📱 Notas Importantes

### YouTube Loop
- A lógica funciona com extração automática de IDs
- Para controle real de browser, integre com Selenium/Puppeteer
- Suporta rastreamento de múltiplas sessões simultâneas
- Events emitidos: `youtube_loop_created`, `youtube_loop_started`, `youtube_loop_paused`, etc.

### WhatsApp
- Sistema de validação de telefone com suporte a múltiplos formatos
- Normaliza automaticamente para formato internacional
- Suporta envio para grupos e contatos individuais
- Histórico mantido em memória (para persistência, integre com BD)
- Events emitidos: `whatsapp_message_sent`, `whatsapp_bulk_messages_sent`, etc.

---

## 🔄 Event Bus Integration

Ambos os módulos emitem eventos que podem ser capturados para logging, UI updates, etc:

```python
async def event_handler(event_type, data):
    print(f"Event: {event_type}")
    print(f"Data: {data}")

manager = create_youtube_loop_manager(event_bus_callback=event_handler)
sender = create_whatsapp_sender(event_bus_callback=event_handler)
```

Exemplos de eventos:
- `youtube_loop_session_created`
- `youtube_loop_started`
- `youtube_loop_paused`
- `youtube_loop_stopped`
- `whatsapp_message_sent`
- `whatsapp_bulk_messages_sent`
- `whatsapp_session_created`
- `whatsapp_authenticated`

---

## 🚀 Próximas Implementações (v2.2)

- [ ] Integração com Selenium para controle real de browser
- [ ] Persistência de sessões em banco de dados
- [ ] Suporte a múltiplas contas WhatsApp
- [ ] Webhook para receber mensagens
- [ ] Dashboard de controle em tempo real
- [ ] API REST para acesso remoto
