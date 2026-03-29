#!/usr/bin/env python3
"""
Wrapper para iniciar o Hub do Quinta-Feira
Localizado na raiz do projeto para comodidade
"""

import sys
import os
import subprocess

# Adicionar backend ao path
backend_path = os.path.join(os.path.dirname(__file__), 'backend')
sys.path.insert(0, backend_path)

# Importar e executar o hub
from backend.start_hub import main

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Encerramento solicitado pelo usuário")
        sys.exit(0)
    except Exception as e:
        print(f"[ERRO] {e}")
        sys.exit(1)
