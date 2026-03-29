#!/usr/bin/env python3
"""
Script de validação: Quinta-Feira v2.0
Verifica se todas as dependências e imports estão corretos antes de rodar.
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
    END = '\033[0m'

def print_check(msg, success=True):
    symbol = f"{Colors.GREEN}✓{Colors.END}" if success else f"{Colors.RED}✗{Colors.END}"
    print(f"{symbol} {msg}")

def print_section(title):
    print(f"\n{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BLUE}{title.center(60)}{Colors.END}")
    print(f"{Colors.BLUE}{'='*60}{Colors.END}\n")

def check_imports():
    """Verifica se todos os imports críticos funcionam"""
    print_section("CHECANDO IMPORTS")
    
    issues = []
    
    # Import 1: backend.main
    try:
        from backend.brain_v2 import QuintaFeiraBrain
        print_check("brain_v2.QuintaFeiraBrain")
    except Exception as e:
        issues.append(f"brain_v2: {str(e)}")
        print_check(f"brain_v2.QuintaFeiraBrain - {str(e)[:50]}", False)
    
    # Import 2: core modules
    try:
        from backend import get_di_container, EventBus, ToolRegistry
        print_check("core.get_di_container, EventBus, ToolRegistry")
    except Exception as e:
        issues.append(f"core: {str(e)}")
        print_check(f"core modules - {str(e)[:50]}", False)
    
    # Import 3: database
    try:
        from backend.database import BaseDadosMemoria
        print_check("database.BaseDadosMemoria")
    except Exception as e:
        issues.append(f"database: {str(e)}")
        print_check(f"database - {str(e)[:50]}", False)
    
    # Import 4: oracle
    try:
        from backend.oracle import OraculoEngine
        print_check("oracle.OraculoEngine")
    except Exception as e:
        issues.append(f"oracle: {str(e)}")
        print_check(f"oracle - {str(e)[:50]}", False)
    
    # Import 5: automation
    try:
        from backend.automation import OSAutomation
        print_check("automation.OSAutomation")
    except Exception as e:
        issues.append(f"automation: {str(e)}")
        print_check(f"automation - {str(e)[:50]}", False)
    
    # Import 6: tools
    try:
        from backend.tools import inicializar_ferramentas
        print_check("tools.inicializar_ferramentas")
    except Exception as e:
        issues.append(f"tools: {str(e)}")
        print_check(f"tools - {str(e)[:50]}", False)
    
    return len(issues) == 0, issues

def check_environment():
    """Verifica variáveis de ambiente"""
    print_section("CHECANDO VARIÁVEIS DE AMBIENTE")
    
    required_vars = ["GEMINI_API_KEY"]
    optional_vars = ["SPOTIFY_CLIENT_ID", "ELEVENLABS_API_KEY"]
    
    from dotenv import load_dotenv
    
    # Tenta carregar .env de diferentes locais
    env_paths = [
        ".env",
        "backend/.env",
        os.path.expanduser("~/.env")
    ]
    
    loaded = False
    for path in env_paths:
        if os.path.exists(path):
            load_dotenv(path)
            print_check(f"Carregado: {path}")
            loaded = True
            break
    
    if not loaded:
        print_check("Nenhum .env encontrado", False)
        print(f"{Colors.YELLOW}⚠ Use 'cp backend/.env.example backend/.env' para criar.{Colors.END}\n")
    
    # Check required
    missing = []
    for var in required_vars:
        if os.getenv(var):
            print_check(f"{var} = {os.getenv(var)[:20]}...")
        else:
            print_check(f"{var} (OBRIGATÓRIO)", False)
            missing.append(var)
    
    # Check optional
    for var in optional_vars:
        if os.getenv(var):
            print_check(f"{var} = {os.getenv(var)[:20]}...")
        else:
            print_check(f"{var} (opcional - não configurado)")
    
    return len(missing) == 0, missing

def check_directories():
    """Verifica estrutura de pastas"""
    print_section("CHECANDO ESTRUTURA DE PASTAS")
    
    required_dirs = [
        "backend",
        "backend/core",
        "backend/tools",
        "frontend",
    ]
    
    all_exist = True
    for dir_path in required_dirs:
        exists = os.path.isdir(dir_path)
        print_check(f"Pasta: {dir_path}", exists)
        if not exists:
            all_exist = False
    
    return all_exist

def check_files():
    """Verifica arquivos críticos"""
    print_section("CHECANDO ARQUIVOS CRÍTICOS")
    
    required_files = [
        "backend/__init__.py",
        "backend/main.py",
        "backend/brain_v2.py",
        "backend/requirements.txt",
        "backend/core/__init__.py",
        "backend/tools/__init__.py",
        "frontend/app/page.tsx",
    ]
    
    all_exist = True
    for file_path in required_files:
        exists = os.path.isfile(file_path)
        status = "✓" if exists else "✗"
        print_check(f"{status} {file_path}", exists)
        if not exists:
            all_exist = False
    
    return all_exist

def main():
    print(f"\n{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BLUE}Quinta-Feira v2.0 - Validação de Setup{Colors.END}")
    print(f"{Colors.BLUE}{'='*60}{Colors.END}\n")
    
    # Executar checks
    dirs_ok = check_directories()
    files_ok = check_files()
    imports_ok, import_issues = check_imports()
    env_ok, missing_vars = check_environment()
    
    # Summary
    print_section("RESUMO")
    
    all_ok = dirs_ok and files_ok and imports_ok and env_ok
    
    if all_ok:
        print(f"{Colors.GREEN}✓ TUDO PRONTO! Sistema validado com sucesso.{Colors.END}\n")
        print("Próximo passo: rodar o backend")
        print(f"  {Colors.BLUE}cd backend{Colors.END}")
        print(f"  {Colors.BLUE}uvicorn main:app --reload{Colors.END}\n")
    else:
        print(f"{Colors.RED}✗ Existem problemas detectados:{Colors.END}\n")
        
        if not dirs_ok or not files_ok:
            print(f"{Colors.YELLOW}⚠ Problemas na estrutura de pastas/arquivos{Colors.END}")
        
        if import_issues:
            print(f"{Colors.YELLOW}⚠ Problemas nos imports:{Colors.END}")
            for issue in import_issues:
                print(f"   - {issue}")
        
        if missing_vars:
            print(f"{Colors.YELLOW}⚠ Variáveis obrigatórias não configuradas:{Colors.END}")
            for var in missing_vars:
                print(f"   - {var}")
            print(f"\n   Configure em backend/.env")
    
    print()

if __name__ == "__main__":
    main()
