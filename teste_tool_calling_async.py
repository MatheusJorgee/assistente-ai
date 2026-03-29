#!/usr/bin/env python3
"""
Teste completo do Tool Calling + Async YouTube
Validar que:
1. Tool calling funciona (Gemini → função → resultado)
2. Event loop não bloqueia (async YouTube)
3. System prompt agressivo (sem negações)
"""

import asyncio
import os
import sys
import json
import time
import psutil
from dotenv import load_dotenv

# Setup path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def main():
    print("\n" + "="*70)
    print("🧪 TESTE DE TOOL CALLING + ASYNC")
    print("="*70 + "\n")
    
    # Load environment
    load_dotenv()
    
    # Test 1: Verificar se brain_v2 initializa corretamente
    print("[TEST 1] Inicializar Brain v2...")
    try:
        from backend.brain_v2 import QuintaFeiraBrainV2
        brain = QuintaFeiraBrainV2()
        print("✅ Brain v2 inicializado com sucesso")
        print(f"   - Ferramentas carregadas: {len(brain.tool_registry.list_tools())}")
        ferramentas = brain.tool_registry.list_tools()
        for tool in ferramentas:
            print(f"     • {tool.metadata.name}")
    except Exception as e:
        print(f"❌ Erro ao inicializar brain: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Test 2: Verificar se youtube_controller tem async_tocar_youtube_invisivel
    print("\n[TEST 2] Verificar método async do YouTube...")
    try:
        controller = brain.automacao
        if hasattr(controller, 'async_tocar_youtube_invisivel'):
            print("✅ Método async_tocar_youtube_invisivel encontrado")
        else:
            print("❌ Método async_tocar_youtube_invisivel NÃO encontrado")
    except Exception as e:
        print(f"❌ Erro: {e}")
    
    # Test 3: System prompt agressivo
    print("\n[TEST 3] Verificar system prompt agressivo...")
    try:
        if "DOUTRINA INQUEBRÁVEL" in brain.instrucao_sistema:
            print("✅ System prompt contém DOUTRINA INQUEBRÁVEL")
        if "EXECUTE-A IMEDIATAMENTE" in brain.instrucao_sistema:
            print("✅ System prompt contém instruções agressivas")
        if "NÃO EXPLIQUE O QUE PODES FAZER" in brain.instrucao_sistema:
            print("✅ System prompt força execução sem explicação")
    except Exception as e:
        print(f"❌ Erro: {e}")
    
    # Test 4: Processos Chromium vigentes (antes do teste)
    print("\n[TEST 4] Monitor de processos (antes)...")
    try:
        chrome_processes_before = 0
        for proc in psutil.process_iter(['pid', 'name']):
            if 'edge' in proc.name().lower() or 'chromium' in proc.name().lower():
                chrome_processes_before += 1
        print(f"   Processos Chrome/Edge antes: {chrome_processes_before}")
    except Exception as e:
        print(f"⚠️  Erro ao contar processos: {e}")
    
    # Test 5: Tool calling com Gemini (teste real!)
    print("\n[TEST 5] Tool Calling com Gemini...")
    print("   Enviando: 'Tira um print da tela'...")
    try:
        mem_before = psutil.virtual_memory().percent
        cpu_before = psutil.cpu_percent(interval=0.1)
        
        start_time = time.time()
        response = await brain.ask("Tira um print da tela")
        elapsed = time.time() - start_time
        
        mem_after = psutil.virtual_memory().percent
        cpu_after = psutil.cpu_percent(interval=0.1)
        
        # Parse response
        try:
            response_json = json.loads(response)
            text = response_json.get('text', '')
            mode = response_json.get('mode', '')
        except:
            text = response
            mode = "ERROR"
        
        print(f"✅ Resposta recebida em {elapsed:.2f}s [{mode}]")
        print(f"   Conteúdo: {text[:100]}...")
        print(f"   Memória: {mem_before:.1f}% → {mem_after:.1f}%")
        print(f"   CPU: {cpu_before:.1f}% → {cpu_after:.1f}%")
        
        # Verificações de sucesso
        if "não consigo" in text.lower() or "assistente de texto" in text.lower():
            print("❌ FALHA: Gemini ainda nega capacidades!")
        elif "▶" in text or "capturado" in text.lower() or "tela" in text.lower():
            print("✅ SUCESSO: Gemini usou ferramenta!")
        else:
            print("⚠️  Resposta neutra (verificar manualmente)")
    
    except Exception as e:
        print(f"❌ Erro ao fazer chamada Gemini: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 6: Teste de YouTube específico
    print("\n[TEST 6] Teste de Tool Calling YouTube...")
    print("   Enviando: 'Toca The Weeknd'...")
    try:
        mem_before = psutil.virtual_memory().percent
        
        start_time = time.time()
        response = await brain.ask("Toca The Weeknd por favor")
        elapsed = time.time() - start_time
        
        mem_after = psutil.virtual_memory().percent
        
        try:
            response_json = json.loads(response)
            text = response_json.get('text', '')
            mode = response_json.get('mode', '')
        except:
            text = response
            mode = "ERROR"
        
        print(f"✅ Resposta recebida em {elapsed:.2f}s [{mode}]")
        print(f"   Conteúdo: {text[:100]}...")
        print(f"   Memória: {mem_before:.1f}% → {mem_after:.1f}%")
        
        if "weeknd" in text.lower() or "tocando" in text.lower() or "▶" in text:
            print("✅ SUCESSO: YouTube foi tocado!")
        elif "não consigo" in text.lower():
            print("❌ FALHA: Gemini nega capacidade de tocar música")
        else:
            print("⚠️  Resposta neutra")
    
    except Exception as e:
        print(f"❌ Erro: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 7: Monitor de processos (depois)
    print("\n[TEST 7] Monitor de processos (depois)...")
    try:
        chrome_processes_after = 0
        for proc in psutil.process_iter(['pid', 'name']):
            if 'edge' in proc.name().lower() or 'chromium' in proc.name().lower():
                chrome_processes_after += 1
        print(f"   Processos Chrome/Edge depois: {chrome_processes_after}")
        if chrome_processes_after > chrome_processes_before:
            print(f"⚠️  {chrome_processes_after - chrome_processes_before} processos adicionados")
        else:
            print("✅ Processos foram limpos corretamente")
    except Exception as e:
        print(f"⚠️  Erro ao contar processos: {e}")
    
    # Test 8: Limpar resources
    print("\n[TEST 8] Cleanup...")
    try:
        if hasattr(brain, '__del__'):
            brain.__del__()
        print("✅ Brain cleanup realizado")
    except Exception as e:
        print(f"⚠️  Erro durante cleanup: {e}")
    
    print("\n" + "="*70)
    print("✅ TESTES COMPLETOS")
    print("="*70 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
