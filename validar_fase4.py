#!/usr/bin/env python3
"""
CHECKLIST - FASE 4 HUB DISTRIBUÍDO
Script rápido para validar se tudo está configurado corretamente.
"""

import os
import sys
import subprocess
from pathlib import Path

def check_file_exists(path: str, description: str) -> bool:
    """Verificar se arquivo existe."""
    exists = Path(path).exists()
    status = "✅" if exists else "❌"
    print(f"{status} {description}: {path}")
    return exists

def check_file_contains(path: str, text: str, description: str) -> bool:
    """Verificar se arquivo contém texto."""
    try:
        with open(path, 'r') as f:
            content = f.read()
            found = text in content
            status = "✅" if found else "❌"
            print(f"{status} {description}")
            return found
    except Exception as e:
        print(f"❌ {description} - Erro: {e}")
        return False

def check_env_var(var_name: str, description: str) -> bool:
    """Verificar se variável de ambiente está definida."""
    value = os.getenv(var_name)
    if value:
        print(f"✅ {description}: {var_name} definida")
        return True
    else:
        print(f"❌ {description}: {var_name} NÃO definida")
        return False

def check_package(package: str, description: str) -> bool:
    """Verificar se pacote está instalado."""
    try:
        __import__(package)
        print(f"✅ {description}: {package} instalado")
        return True
    except ImportError:
        print(f"❌ {description}: {package} NÃO instalado")
        return False

def main():
    print("\n" + "="*70)
    print("🔍 CHECKLIST - FASE 4 HUB DISTRIBUÍDO")
    print("="*70 + "\n")
    
    checks_passed = 0
    checks_total = 0
    
    # ============ BACKEND ============
    print("\n📦 BACKEND")
    print("-" * 70)
    
    checks = [
        # Arquivos
        (lambda: check_file_exists(
            "backend/start_hub.py",
            "script start_hub.py"
        ), "Backend files"),
        
        # Código
        (lambda: check_file_contains(
            "backend/start_hub.py",
            "async def start_uvicorn",
            "async uvicorn em start_hub.py"
        ), "Async code"),
        
        (lambda: check_file_contains(
            "backend/start_hub.py",
            "ngrok.connect",
            "ngrok tunnel em start_hub.py"
        ), "Ngrok integration"),
        
        # Deps
        (lambda: check_package("uvicorn", "Uvicorn"), "Backend deps - uvicorn"),
        
        # Env
        (lambda: check_env_var("GEMINI_API_KEY", "Gemini API Key"), "Env vars"),
    ]
    
    for check_fn, category in checks:
        checks_total += 1
        if check_fn():
            checks_passed += 1
    
    # ============ FRONTEND ============
    print("\n🎨 FRONTEND")
    print("-" * 70)
    
    frontend_checks = [
        # Arquivos
        (lambda: check_file_exists(
            "frontend/app/page.tsx",
            "page.tsx (UI)"
        ), "Frontend files"),
        
        (lambda: check_file_exists(
            "frontend/app/api/chat/route.ts",
            "route.ts (Cloud API)"
        ), "Cloud fallback"),
        
        (lambda: check_file_exists(
            "frontend/.env.local.example",
            ".env.local.example"
        ), "Config template"),
        
        # Código em page.tsx
        (lambda: check_file_contains(
            "frontend/app/page.tsx",
            "NEXT_PUBLIC_WS_HOST",
            "NEXT_PUBLIC_WS_HOST em page.tsx"
        ), "Env support"),
        
        (lambda: check_file_contains(
            "frontend/app/page.tsx",
            "cloudMode",
            "cloudMode state em page.tsx"
        ), "Cloud fallback detection"),
        
        (lambda: check_file_contains(
            "frontend/app/page.tsx",
            "enviarModoNuvem",
            "enviarModoNuvem em page.tsx"
        ), "Cloud fallback function"),
        
        # Código em route.ts
        (lambda: check_file_contains(
            "frontend/app/api/chat/route.ts",
            "NEXT_GEMINI_API_KEY",
            "NEXT_GEMINI_API_KEY em route.ts"
        ), "Gemini config"),
        
        (lambda: check_file_contains(
            "frontend/app/api/chat/route.ts",
            "MODO NUVEM",
            "System prompt nuvem em route.ts"
        ), "Cloud prompt"),
        
        # Deps
        (lambda: check_package("generativeai", "Google Generative AI"), "Frontend deps"),
    ]
    
    for check_fn, category in frontend_checks:
        checks_total += 1
        if check_fn():
            checks_passed += 1
    
    # ============ RESUMO ============
    print("\n" + "="*70)
    print(f"📊 RESULTADO: {checks_passed}/{checks_total} verificações passaram")
    print("="*70)
    
    if checks_passed == checks_total:
        print("\n✅ TUDO PRONTO! A Fase 4 está configurada corretamente.\n")
        return 0
    else:
        print(f"\n⚠️  {checks_total - checks_passed} verificação(ões) falharam.\n")
        return 1

if __name__ == "__main__":
    sys.exit(main())
