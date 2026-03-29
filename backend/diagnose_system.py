#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SCRIPT DE DIAGNÓSTICO COMPLETO - Quinta-Feira v2.1

Uso:
  python diagnose_system.py

O que verifica:
  1. Versão do Python e pacotes
  2. Imports dos módulos críticos
  3. Conexão com .env
  4. Status do banco de dados
  5. Disponibilidade das ferramentas
  6. Geminai API key
"""

import sys
import os

# Fix Windows encoding
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from pathlib import Path
from datetime import datetime
import json
import traceback

# Colors for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    END = '\033[0m'
    BOLD = '\033[1m'

class DiagnosticReport:
    def __init__(self):
        self.checks = []
        self.errors = []
        self.timestamp = datetime.now().isoformat()

    def add_check(self, name: str, passed: bool, message: str, help_text: str = ""):
        symbol = f"{Colors.GREEN}[OK]{Colors.END}" if passed else f"{Colors.RED}[FAIL]{Colors.END}"
        status = f"PASS" if passed else f"FAIL"
        
        print(f"{symbol} {name:<40} [{status}]")
        print(f"  -> {message}")
        
        if help_text:
            print(f"  INFO: {help_text}")
        
        print()
        
        self.checks.append({
            'name': name,
            'passed': passed,
            'message': message,
            'help': help_text
        })
        
        if not passed:
            self.errors.append(name)

    def summary(self):
        total = len(self.checks)
        passed = sum(1 for c in self.checks if c['passed'])
        failed = total - passed
        
        print(f"\n{Colors.CYAN}{'='*60}{Colors.END}")
        print(f"{Colors.BOLD}RESUMO DO DIAGNOSTICO{Colors.END}")
        print(f"{Colors.CYAN}{'='*60}{Colors.END}\n")
        
        print(f"Total de testes: {total}")
        print(f"{Colors.GREEN}Passou: {passed}{Colors.END}")
        
        if failed > 0:
            print(f"{Colors.RED}Falhou: {failed}{Colors.END}")
        
        if self.errors:
            print(f"\n{Colors.YELLOW}Problemas encontrados:{Colors.END}")
            for error in self.errors:
                print(f"  [FAIL] {error}")
        else:
            print(f"\n{Colors.GREEN}[OK] Nenhum problema encontrado!{Colors.END}")
        
        print(f"\nTimestamp: {self.timestamp}\n")

def main():
    report = DiagnosticReport()
    
    print(f"\n{Colors.CYAN}{Colors.BOLD}[DIAG] DIAGNOSTICO - Quinta-Feira v2.1{Colors.END}\n")
    
    # ========== PYTHON VERSION ==========
    python_ok = sys.version_info >= (3, 10)
    report.add_check(
        "Python Version",
        python_ok,
        f"Python {sys.version.split()[0]}",
        "Recomendado: Python 3.10+"
    )
    
    # ========== WORKING DIRECTORY ==========
    cwd = os.getcwd()
    is_backend = cwd.endswith('backend')
    report.add_check(
        "Diretório Correto",
        is_backend or os.path.basename(cwd) == 'assistente-ai',
        f"CWD: {cwd}",
        "Execute de backend/ ou da raiz assistente-ai/"
    )
    
    # ========== .ENV FILE ==========
    env_path = Path(cwd) / '.env' if is_backend else Path(cwd) / 'backend' / '.env'
    if not is_backend:
        env_path = Path(cwd) / 'backend' / '.env'
    else:
        env_path = Path(cwd) / '.env'
    
    env_exists = env_path.exists()
    report.add_check(
        ".env File",
        env_exists,
        f"Localização: {env_path}",
        "Crie com: cp .env.example .env"
    )
    
    # ========== GEMINI API KEY ==========
    api_key_ok = False
    if env_exists:
        try:
            from dotenv import load_dotenv
            load_dotenv(env_path)
            api_key = os.getenv('GEMINI_API_KEY', '')
            api_key_ok = bool(api_key) and len(api_key) > 10
        except Exception as e:
            api_key_ok = False
    
    report.add_check(
        "Gemini API Key",
        api_key_ok,
        "✓ Configurada" if api_key_ok else "✗ Não encontrada",
        "Adicione GEMINI_API_KEY ao .env"
    )
    
    # ========== IMPORTS CRÍTICOS ==========
    
    # FastAPI
    try:
        import fastapi
        report.add_check("FastAPI", True, f"v{fastapi.__version__}", "")
    except ImportError:
        report.add_check("FastAPI", False, "Não instalado", "pip install fastapi uvicorn")
    
    # Google GenAI
    try:
        from google import genai
        report.add_check("Google GenAI", True, "Instalado ✓", "")
    except ImportError:
        report.add_check("Google GenAI", False, "Não instalado", "pip install google-genai")
    
    # Pydantic
    try:
        import pydantic
        report.add_check("Pydantic", True, f"v{pydantic.__version__}", "")
    except ImportError:
        report.add_check("Pydantic", False, "Não instalado", "pip install pydantic")
    
    # PIL/Pillow
    try:
        from PIL import Image
        report.add_check("Pillow", True, "Instalado ✓", "")
    except ImportError:
        report.add_check("Pillow", False, "Não instalado", "pip install pillow")
    
    # Backend Brain
    try:
        # Try to import Brain
        if not is_backend:
            sys.path.insert(0, 'backend')
        from brain_v2 import QuintaFeiraBrainV2
        report.add_check(
            "QuintaFeiraBrain v2",
            True,
            "Importação OK ✓",
            ""
        )
    except Exception as e:
        report.add_check(
            "QuintaFeiraBrain v2",
            False,
            f"Erro: {str(e)[:50]}...",
            "Verifique imports em brain_v2.py"
        )
    
    # Database
    try:
        from database import BaseDadosMemoria
        report.add_check(
            "Database Module",
            True,
            "BaseDadosMemoria importável ✓",
            ""
        )
    except Exception as e:
        report.add_check(
            "Database Module",
            False,
            f"Erro: {str(e)[:50]}...",
            "Verifique database.py"
        )
    
    # Oracle
    try:
        from oracle import OraculoEngine
        report.add_check(
            "Oracle Module",
            True,
            "OraculoEngine importável ✓",
            ""
        )
    except Exception as e:
        report.add_check(
            "Oracle Module",
            False,
            f"Erro: {str(e)[:50]}...",
            "Verifique oracle.py"
        )
    
    # Core
    try:
        from core.tool_registry import ToolRegistry, EventBus, DIContainer
        report.add_check(
            "Core Modules",
            True,
            "tool_registry, EventBus, DIContainer ✓",
            ""
        )
    except Exception as e:
        report.add_check(
            "Core Modules",
            False,
            f"Erro: {str(e)[:50]}...",
            "Verifique core/tool_registry.py"
        )
    
    # ========== MAIN.PY ==========
    main_py_path = Path(cwd) / 'main.py' if is_backend else Path(cwd) / 'backend' / 'main.py'
    main_exists = main_py_path.exists()
    report.add_check(
        "main.py Existe",
        main_exists,
        f"Localização: {main_py_path}",
        "Arquivo FastAPI principal"
    )
    
    # ========== PRÓXIMOS PASSOS ==========
    print(f"\n{Colors.CYAN}{Colors.BOLD}[NEXT] PROXIMOS PASSOS{Colors.END}\n")
    
    if report.errors:
        print("Resolva os erros acima antes de continuar.\n")
    else:
        print(f"{Colors.GREEN}[OK] Tudo OK! Voce pode rodar o backend:{Colors.END}\n")
        print(f"  cd backend")
        print(f"  python -m uvicorn main:app --reload\n")
        print(f"Frontend:\n")
        print(f"  cd frontend")
        print(f"  npm run dev\n")
        print(f"Depois acesse: http://localhost:3000\n")
    
    report.summary()
    
    # Write report to file
    report_file = Path('diagnostic_report.json') if is_backend else Path('backend/diagnostic_report.json')
    try:
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump({
                'timestamp': report.timestamp,
                'checks': report.checks,
                'errors': report.errors,
                'summary': {
                    'total': len(report.checks),
                    'passed': sum(1 for c in report.checks if c['passed']),
                    'failed': len(report.errors)
                }
            }, f, indent=2)
        print(f"[FILE] Relatorio salvo: {report_file}\n")
    except Exception as e:
        print(f"[WARN] Nao foi possivel salvar relatorio: {e}\n")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n{Colors.RED}[ERROR] ERRO NAO TRATADO:{Colors.END}")
        traceback.print_exc()
        sys.exit(1)
