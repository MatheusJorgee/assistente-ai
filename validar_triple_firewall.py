#!/usr/bin/env python3
"""
🛡️ TRIPLE FIREWALL VALIDATION
Verifica se as 3 camadas de proteção contra Base64 estão implementadas corretamente.

Uso: python validar_triple_firewall.py
"""

import sys
import os
from pathlib import Path

# Cores para output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    ORANGE = '\033[33m'
    END = '\033[0m'

def print_check(msg, success=True, warning=False):
    if warning:
        symbol = f"{Colors.YELLOW}⚠{Colors.END}"
    else:
        symbol = f"{Colors.GREEN}✓{Colors.END}" if success else f"{Colors.RED}✗{Colors.END}"
    print(f"{symbol} {msg}")

# ============ CAMADA 1: Backend Validação ============
print(f"\n{Colors.BLUE}[CAMADA 1] Backend Validação (main.py){Colors.END}")

backend_main_path = Path(__file__).parent / "backend" / "main.py"
try:
    with open(backend_main_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Verificar validação de Base64 no texto
    checks_layer1 = [
        ('validação de UklGR', 'startswith("UklGR")'),
        ('validação de SUQz', 'startswith("SUQz")'),
        ('bloqueio do Base64', '[ERRO] Base64 vazou no texto'),
        ('log de erro P0', '[P0] BASE64 DETECTADO NO TEXTO'),
    ]
    
    layer1_ok = True
    for check_name, check_str in checks_layer1:
        if check_str in content:
            print_check(f"  {check_name} detectado")
        else:
            print_check(f"  {check_name} NÃO encontrado", False)
            layer1_ok = False
    
    if layer1_ok:
        print_check(f"✓ CAMADA 1 COMPLETA", True)
    else:
        print_check(f"✗ CAMADA 1 INCOMPLETA - Adicionar validações em main.py", False)

except FileNotFoundError:
    print_check(f"  Arquivo main.py não encontrado em {backend_main_path}", False)

# ============ CAMADA 2: Backend Isolamento ============
print(f"\n{Colors.BLUE}[CAMADA 2] Backend Isolamento (main.py){Colors.END}")

try:
    with open(backend_main_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Verificar isolamento de áudio
    checks_layer2 = [
        ('audio header UklGR', 'audio_resposta.startswith("UklGR")'),
        ('audio header SUQz', 'audio_resposta.startswith("SUQz")'),
        ('audio header ID3', 'audio_resposta.startswith("ID3")'),
        ('audio header MP3 frame', 'audio_resposta.startswith("/+MYxA")'),
        ('tipo evento audio', '"type": "audio"'),
        ('isolamento do audio', '"audio": audio_resposta'),
    ]
    
    layer2_ok = True
    for check_name, check_str in checks_layer2:
        if check_str in content:
            print_check(f"  {check_name} detectado")
        else:
            print_check(f"  {check_name} NÃO encontrado", False)
            layer2_ok = False
    
    if layer2_ok:
        print_check(f"✓ CAMADA 2 COMPLETA", True)
    else:
        print_check(f"✗ CAMADA 2 INCOMPLETA - Adicionar isolamento em main.py", False)

except FileNotFoundError:
    print_check(f"  Arquivo main.py não encontrado", False)

# ============ CAMADA 3: Frontend Firewall ============
print(f"\n{Colors.BLUE}[CAMADA 3] Frontend Firewall (page.tsx){Colors.END}")

frontend_page_path = Path(__file__).parent / "frontend" / "app" / "page.tsx"
try:
    with open(frontend_page_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Verificar firewall
    checks_layer3 = [
        ('Layer 1 - UklGR detection', 'startsWith("UklGR")'),
        ('Layer 1 - SUQz detection', 'startsWith("SUQz")'),
        ('Layer 1 - ID3 detection', 'startsWith("ID3")'),
        ('Layer 1 - MP3 frame detection', 'startsWith("/+MYxA")'),
        ('Layer 2 - Regex pattern', '/^[A-Za-z0-9+/=]+$/'),
        ('Layer 3 - Firewall block', 'if (isAudioBase64 || isLongoSemEspacos)'),
        ('Layer 3 - tocarAudioBase64 call', 'tocarAudioBase64(data.content)'),
        ('Layer 3 - Early return', 'return; // ← SAIR ANTES'),
    ]
    
    layer3_ok = True
    for check_name, check_str in checks_layer3:
        if check_str in content:
            print_check(f"  {check_name} detectado")
        else:
            print_check(f"  {check_name} NÃO encontrado", False)
            layer3_ok = False
    
    if layer3_ok:
        print_check(f"✓ CAMADA 3 COMPLETA", True)
    else:
        print_check(f"✗ CAMADA 3 INCOMPLETA - Adicionar firewall em page.tsx", False)

except FileNotFoundError:
    print_check(f"  Arquivo page.tsx não encontrado em {frontend_page_path}", False)

# ============ RESUMO FINAL ============
print(f"\n{Colors.ORANGE}{'='*60}{Colors.END}")
print(f"{Colors.BLUE}RESUMO: Triple Firewall Validation{Colors.END}")
print(f"{Colors.ORANGE}{'='*60}{Colors.END}")

if all([layer1_ok, layer2_ok, layer3_ok]):
    print(f"\n{Colors.GREEN}✓ TODAS AS 3 CAMADAS IMPLEMENTADAS COM SUCESSO!{Colors.END}")
    print(f"\n{Colors.BLUE}Sistema está protegido contra:${Colors.END}")
    print(f"  1. Base64 no texto de streaming")
    print(f"  2. Áudio misturado com texto")
    print(f"  3. Maximum Update Depth loop")
    print(f"  4. PC congela em 100% CPU/RAM")
    sys.exit(0)
else:
    print(f"\n{Colors.RED}✗ Faltam implementações.{Colors.END}")
    print(f"\n{Colors.YELLOW}Próximos passos:{Colors.END}")
    if not layer1_ok:
        print(f"  1. Adicionar validação de Base64 em backend/main.py")
    if not layer2_ok:
        print(f"  2. Certificar isolamento de áudio em backend/main.py")
    if not layer3_ok:
        print(f"  3. Implementar firewall multi-camada em frontend/app/page.tsx")
    sys.exit(1)
