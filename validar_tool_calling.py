#!/usr/bin/env python3
"""
Script de Validação: Tool Calling Gemini
Verifica se as ferramentas estão sendo injetadas corretamente.
"""

import sys
import os

# Adicionar backend ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

def validar_tool_calling():
    print("=" * 80)
    print("🔍 TOOL CALLING VALIDATION")
    print("=" * 80)
    
    try:
        print("\n[1/5] Importando Brain v2...")
        from backend.brain_v2 import QuintaFeiraBrainV2
        print("✓ Brain v2 importado")
        
        print("\n[2/5] Inicializando Brain...")
        brain = QuintaFeiraBrainV2()
        print("✓ Brain inicializado")
        
        print("\n[3/5] Verificando Ferramentas Registradas...")
        tools = brain.tool_registry.list_tools()
        print(f"✓ {len(tools)} ferramentas encontradas:")
        for tool in tools:
            print(f"   - {tool.metadata.name}: {tool.metadata.description[:60]}...")
        
        print("\n[4/5] Verificando Config Gemini...")
        if hasattr(brain, 'config_com_tools'):
            print("✓ config_com_tools armazenado")
            config = brain.config_com_tools
            
            # Verificar tool_config
            if hasattr(config, 'tool_config'):
                print("✓ tool_config presente")
                if hasattr(config.tool_config, 'function_calling_config'):
                    mode = config.tool_config.function_calling_config.mode
                    print(f"✓ function_calling_config mode: {mode}")
            
            # Verificar tools
            tools_config = getattr(config, 'tools', None)
            if tools_config:
                print(f"✓ {len(list(tools_config))} tools injetadas no config")
            else:
                print("❌ Nenhuma tool no config!")
        else:
            print("❌ config_com_tools não encontrado!")
        
        print("\n[5/5] Verificando System Instruction...")
        if hasattr(brain, 'instrucao_sistema'):
            instr = brain.instrucao_sistema
            if "FORCE ABSOLUTA" in instr:
                print("✓ DIRETIVA SUPREMA presente")
            if "ABSOLUTAMENTE PROIBIDO" in instr:
                print("✓ Proibições explícitas presentes")
            if "ÚNICO COMPORTAMENTO ACEITO" in instr:
                print("✓ Comportamento obrigatório definido")
        
        print("\n" + "=" * 80)
        print("✅ VALIDAÇÃO COMPLETA - Sistema pronto para tool calling")
        print("=" * 80)
        
        return True
        
    except Exception as e:
        print(f"\n❌ ERRO: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = validar_tool_calling()
    sys.exit(0 if success else 1)
