"""
Testes: YouTube Loop + WhatsApp Integration
Valida: Loop no YouTube, envio de mensagens WhatsApp
"""

import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from core.youtube_loop import (
    create_youtube_loop_manager,
    YouTubeLoopMode,
)
from core.whatsapp_sender import (
    create_whatsapp_sender,
    MessageStatus
)


# ============================================================================
# TESTES YOUTUBE LOOP
# ============================================================================

async def test_youtube_loop_creation():
    """Testa criacao de sessao de loop no YouTube."""
    print("\n" + "="*60)
    print("TEST 1: YouTube Loop - Session Creation")
    print("="*60)
    
    events = []
    
    async def event_callback(event_type, data):
        events.append((event_type, data))
    
    manager = create_youtube_loop_manager(event_bus_callback=event_callback)
    
    # Create loop session
    session = await manager.create_loop_session(
        video_url_or_id="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        title="Never Gonna Give You Up",
        loop_mode=YouTubeLoopMode.SINGLE
    )
    
    passed = session is not None and session.video.video_id == "dQw4w9WgXcQ"
    
    print(f"Session created: {session.session_id if session else 'FAILED'}")
    print(f"Video ID: {session.video.video_id if session else 'N/A'}")
    print(f"Title: {session.video.title if session else 'N/A'}")
    print(f"Loop mode: {session.loop_mode.value if session else 'N/A'}")
    print(f"URL: {session.video.full_url if session else 'N/A'}")
    print(f"\nEvents emitted: {len(events)}")
    
    print(f"\n-> Resultado: {'PASSOU' if passed else 'FALHOU'}")
    return passed


async def test_youtube_loop_operations():
    """Testa operacoes com loop (start, pause, resume, stop)."""
    print("\n" + "="*60)
    print("TEST 2: YouTube Loop - Operations")
    print("="*60)
    
    events = []
    
    async def event_callback(event_type, data):
        events.append((event_type, data))
    
    manager = create_youtube_loop_manager(event_bus_callback=event_callback)
    
    # Create session
    session = await manager.create_loop_session(
        video_url_or_id="dQw4w9WgXcQ",
        title="Never Gonna Give You Up",
        loop_mode=YouTubeLoopMode.SINGLE
    )
    
    if not session:
        print("FAIL: Could not create session")
        return False
    
    # Test operations
    tests = []
    
    # Start
    result_start = await manager.start_loop(session.session_id)
    tests.append(("START", result_start))
    print(f"  [1] Start loop: {'OK' if result_start else 'FAIL'}")
    
    # Pause
    result_pause = await manager.pause_loop(session.session_id)
    tests.append(("PAUSE", result_pause))
    print(f"  [2] Pause loop: {'OK' if result_pause else 'FAIL'}")
    
    # Resume
    result_resume = await manager.resume_loop(session.session_id)
    tests.append(("RESUME", result_resume))
    print(f"  [3] Resume loop: {'OK' if result_resume else 'FAIL'}")
    
    # Change mode
    result_mode = await manager.set_loop_mode(session.session_id, YouTubeLoopMode.ALL)
    tests.append(("CHANGE_MODE", result_mode))
    print(f"  [4] Change mode: {'OK' if result_mode else 'FAIL'}")
    
    # Get status
    status = await manager.get_session_status(session.session_id)
    tests.append(("GET_STATUS", status is not None))
    print(f"  [5] Get status: {'OK' if status else 'FAIL'}")
    if status:
        print(f"      Loop mode: {status['loop_mode']}")
        print(f"      Is playing: {status['is_playing']}")
    
    # Stop
    result_stop = await manager.stop_loop(session.session_id)
    tests.append(("STOP", result_stop))
    print(f"  [6] Stop loop: {'OK' if result_stop else 'FAIL'}")
    
    passed = all(result for _, result in tests)
    print(f"\n-> Resultado: {'PASSOU' if passed else 'FALHOU'}")
    
    return passed


async def test_youtube_loop_video_extraction():
    """Testa extracao de video ID de diferentes formatos."""
    print("\n" + "="*60)
    print("TEST 3: YouTube Loop - Video ID Extraction")
    print("="*60)
    
    manager = create_youtube_loop_manager()
    
    test_cases = [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ", "Full URL"),
        ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ", "Short URL"),
        ("dQw4w9WgXcQ", "dQw4w9WgXcQ", "Direct ID"),
        ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ", "Embed URL"),
    ]
    
    all_passed = True
    for url_input, expected_id, description in test_cases:
        extracted_id = await manager.extract_video_id(url_input)
        passed = extracted_id == expected_id
        
        status = "[OK]" if passed else "[FAIL]"
        print(f"  {status} {description:20} | Input: {url_input[:30]:30} | Got: {extracted_id}")
        
        if not passed:
            all_passed = False
    
    print(f"\n-> Resultado: {'PASSOU' if all_passed else 'FALHOU'}")
    return all_passed


# ============================================================================
# TESTES WHATSAPP
# ============================================================================

async def test_whatsapp_session_creation():
    """Testa criacao de sessao WhatsApp."""
    print("\n" + "="*60)
    print("TEST 4: WhatsApp - Session Creation")
    print("="*60)
    
    events = []
    
    async def event_callback(event_type, data):
        events.append((event_type, data))
    
    sender = create_whatsapp_sender(event_bus_callback=event_callback)
    
    # Create session
    session_id = await sender.create_session("default")
    
    info = await sender.get_session_info(session_id)
    
    passed = info is not None and info['session_id'] == session_id
    
    print(f"Session ID: {session_id}")
    print(f"Is authenticated: {info['is_authenticated'] if info else 'N/A'}")
    print(f"Total messages: {info['total_messages_sent'] if info else 'N/A'}")
    print(f"Events emitted: {len(events)}")
    
    print(f"\n-> Resultado: {'PASSOU' if passed else 'FALHOU'}")
    return passed


async def test_whatsapp_message_sending():
    """Testa envio de mensagens WhatsApp."""
    print("\n" + "="*60)
    print("TEST 5: WhatsApp - Message Sending")
    print("="*60)
    
    events = []
    
    async def event_callback(event_type, data):
        events.append((event_type, data))
    
    sender = create_whatsapp_sender(event_bus_callback=event_callback)
    
    # Create session
    session_id = await sender.create_session("test")
    
    # Send individual message
    msg_id = await sender.send_message(
        session_id=session_id,
        phone_or_group="5511999999999",
        message="Ola! Esta eh uma mensagem de teste via assistente."
    )
    
    passed = msg_id is not None
    
    print(f"Message ID: {msg_id}")
    print(f"Status: SENT")
    
    # Get session info
    info = await sender.get_session_info(session_id)
    print(f"Session message count: {info['total_messages_sent'] if info else 0}")
    
    # Get message history
    history = await sender.get_message_history(session_id)
    print(f"Message history length: {len(history)}")
    if history:
        last_msg = history[-1]
        print(f"Last message to: {last_msg.phone_number}")
        print(f"Text preview: {last_msg.message_text[:40]}...")
    
    print(f"Events emitted: {len(events)}")
    
    print(f"\n-> Resultado: {'PASSOU' if passed else 'FALHOU'}")
    return passed


async def test_whatsapp_bulk_send():
    """Testa envio em massa no WhatsApp."""
    print("\n" + "="*60)
    print("TEST 6: WhatsApp - Bulk Message Sending")
    print("="*60)
    
    events = []
    
    async def event_callback(event_type, data):
        events.append((event_type, data))
    
    sender = create_whatsapp_sender(event_bus_callback=event_callback)
    
    # Create session
    session_id = await sender.create_session("bulk")
    
    # Recipients list
    recipients = [
        "5511999999999",
        "5521999999999",
        "5585999999999"
    ]
    
    # Send bulk
    message_ids = await sender.send_bulk_messages(
        session_id=session_id,
        recipients=recipients,
        message="Mensagem de notificacao importante!"
    )
    
    passed = len(message_ids) == len(recipients)
    
    print(f"Recipients: {len(recipients)}")
    print(f"Successfully sent: {len(message_ids)}")
    print(f"Message IDs: {len(message_ids)} created")
    
    # Get session info
    info = await sender.get_session_info(session_id)
    print(f"Total messages in session: {info['total_messages_sent'] if info else 0}")
    
    print(f"Events emitted: {len(events)}")
    
    print(f"\n-> Resultado: {'PASSOU' if passed else 'FALHOU'}")
    return passed


async def test_whatsapp_phone_validation():
    """Testa validacao e normalizacao de numeros."""
    print("\n" + "="*60)
    print("TEST 7: WhatsApp - Phone Validation")
    print("="*60)
    
    sender = create_whatsapp_sender()
    
    test_cases = [
        ("5511999999999", True, "Valid: +55 11 9999-9999"),
        ("11999999999", True, "Valid: 11 9999-9999 (sem +55)"),
        ("11 99999999", True, "Valid: 11 9999-9999 (com espacos)"),
        ("(11) 9999-9999", True, "Valid: (11) 9999-9999 (com mascara)"),
        ("1199", False, "Invalid: muito curto"),
        ("+55 11 99999-9999", True, "Valid: formato completo com espacos"),
    ]
    
    all_passed = True
    for phone, should_pass, description in test_cases:
        is_valid = sender._validate_phone_number(phone)
        normalized = sender._normalize_phone_number(phone) if is_valid else "INVALID"
        
        status = "[OK]" if is_valid == should_pass else "[FAIL]"
        print(f"  {status} {description:40} | Normalized: {normalized}")
        
        if is_valid != should_pass:
            all_passed = False
    
    print(f"\n-> Resultado: {'PASSOU' if all_passed else 'FALHOU'}")
    return all_passed


# ============================================================================
# RUNNER PRINCIPAL
# ============================================================================

async def run_all_tests():
    """Executa todos os testes."""
    print("\n" + "#"*60)
    print("# TESTES: YouTube Loop + WhatsApp Integration")
    print("#"*60)
    
    results = {
        'YouTube Loop - Session Creation': await test_youtube_loop_creation(),
        'YouTube Loop - Operations': await test_youtube_loop_operations(),
        'YouTube Loop - Video Extraction': await test_youtube_loop_video_extraction(),
        'WhatsApp - Session Creation': await test_whatsapp_session_creation(),
        'WhatsApp - Message Sending': await test_whatsapp_message_sending(),
        'WhatsApp - Bulk Send': await test_whatsapp_bulk_send(),
        'WhatsApp - Phone Validation': await test_whatsapp_phone_validation(),
    }
    
    # Resumo final
    print("\n" + "#"*60)
    print("# RESUMO DOS TESTES")
    print("#"*60)
    
    total = len(results)
    passed = sum(1 for r in results.values() if r)
    failed = total - passed
    
    print(f"\nTotal: {total} testes")
    print(f"[PASS] Passaram: {passed}")
    print(f"[FAIL] Falharam: {failed}")
    
    print(f"\nResultados:")
    for test_name, result in results.items():
        status = "[PASS]" if result else "[FAIL]"
        print(f"  {status} | {test_name}")
    
    print("\n" + "#"*60)
    
    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
