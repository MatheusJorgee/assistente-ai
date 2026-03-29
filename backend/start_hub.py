#!/usr/bin/env python3
"""
START_HUB.PY - Túnel Reverso Seguro para Quinta-Feira

Objetivo:
- Iniciar o Uvicorn backend normalmente
- Iniciar um túnel pyngrok simultânea
- Expor URL pública para acesso remoto
- Exibir credenciais de acesso

Uso:
  python start_hub.py [--nohup] [--port 8001] [--host 127.0.0.1]

Argumentos opcionais:
  --nohup     : Executar em background (Linux/Mac)
  --port NUM  : Porta Uvicorn (default: 8001)
  --host ADDR : Host binding (default: 127.0.0.1 local, 0.0.0.0 remoto)
  --public    : Expor publicamente (use com CUIDADO!)
"""

import os
import sys
import subprocess
import threading
import time
import argparse
from pathlib import Path
from dotenv import load_dotenv

# Carregar .env
project_root = Path(__file__).parent
load_dotenv(project_root / ".env")

# Importar pyngrok (com fallback)
try:
    from pyngrok import ngrok
    PYNGROK_AVAILABLE = True
except ImportError:
    print("[WARNING] pyngrok não instalado. Execute: pip install pyngrok")
    PYNGROK_AVAILABLE = False

def banner():
    """Exibir banner"""
    print("""
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║         🚀 QUINTA-FEIRA HUB - Túnel Reverso              ║
║                                                           ║
║         Backend FastAPI + Ngrok Tunnel                    ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
    """)

def start_uvicorn(port: int, host: str):
    """
    Inicia o servidor Uvicorn em foreground.
    
    Args:
        port: Porta para o servidor
        host: Host para binding (127.0.0.1 = local, 0.0.0.0 = remoto)
    """
    print(f"\n[UVICORN] Iniciando servidor em {host}:{port}...")
    print("[UVICORN] → Este processo vai rodar em foreground")
    print("[UVICORN] → Pressione Ctrl+C para parar\n")
    
    import sys
    
    # Import uvicorn e rodar diretamente (mais robusto que subprocess)
    try:
        import uvicorn
        uvicorn.run(
            "main:app",  # <--- CORREÇÃO APLICADA AQUI: de "backend.main:app" para "main:app"
            host=host,
            port=port,
            reload=True,
            log_level="info",
            access_log=True,
            server_header=False,
            date_header=False
        )
    except KeyboardInterrupt:
        print("\n[UVICORN] ✋ Servidor interrompido pelo utilizador")
        sys.exit(0)
    except Exception as e:
        print(f"[UVICORN] ❌ Erro ao iniciar: {e}")
        sys.exit(1)

def start_ngrok_tunnel(port: int, auth_token: str = None, public: bool = False):
    """
    Inicia túnel Ngrok para expor URL pública
    
    Args:
        port: Porta local para tunelar
        auth_token: Token de autenticação Ngrok (opcional)
        public: Se True, expõe publicamente
    """
    if not PYNGROK_AVAILABLE:
        print("[NGROK] ⚠️  Pyngrok não disponível. Execute: pip install pyngrok")
        return None
    
    try:
        print(f"\n[NGROK] Configurando túnel reverso para localhost:{port}...")
        
        # Autenticar se token fornecido
        if auth_token:
            ngrok.set_auth_token(auth_token)
            print("[NGROK] ✓ Autenticado com token")
        
        # Abrir túnel
        if public:
            # Túnel público (requer conta ngrok)
            public_url = ngrok.connect(port, "http")
        else:
            # Túnel local (padrão - não requer autenticação)
            public_url = ngrok.connect(port, "http")
        
        tunnel_url = public_url.public_url
        print(f"\n[NGROK] ✓ Túnel estabelecido!")
        print(f"[NGROK] 🌐 URL Pública: {tunnel_url}")
        
        return tunnel_url
    
    except Exception as e:
        print(f"[NGROK] ❌ Erro ao estabelecer túnel: {e}")
        return None

def display_access_info(local_url: str, public_url: str = None):
    """
    Exibir informações de acesso
    
    Args:
        local_url: URL local (localhost)
        public_url: URL pública (ngrok)
    """
    print("\n" + "="*60)
    print("📡 INFORMAÇÕES DE ACESSO")
    print("="*60)
    
    print(f"\n✓ Backend Local:  {local_url}")
    print(f"  └─ WebSocket:  {local_url.replace('http', 'ws')}/ws")
    print(f"  └─ REST:       {local_url}/api/chat")
    
    if public_url:
        print(f"\n✓ Backend Público (Ngrok): {public_url}")
        print(f"  └─ WebSocket:  {public_url.replace('http', 'ws')}/ws")
        print(f"  └─ REST:       {public_url}/api/chat")
        print(f"\n  ⚠️  AVISO: URL pública expira em ~2 horas")
        print(f"     Renova automaticamente ao reconectar")
    
    print("\n" + "="*60)
    print("📝 CONFIGURAR FRONTEND (.env.local):")
    print("="*60)
    
    if public_url:
        host = public_url.replace("http://", "").replace("https://", "")
        print(f"\nNEXT_PUBLIC_WS_HOST={host}")
        print(f"NEXT_PUBLIC_WS_PORT=443")
        print(f"NEXT_PUBLIC_WS_PATH=/ws")
    else:
        print(f"\nNEXT_PUBLIC_WS_HOST=127.0.0.1")
        print(f"NEXT_PUBLIC_WS_PORT={args.port if hasattr(args, 'port') else 8000}")
        print(f"NEXT_PUBLIC_WS_PATH=/ws")
    
    print("\n" + "="*60)

def main():
    parser = argparse.ArgumentParser(description="Inicia Quinta-Feira Hub com túnel reverso")
    parser.add_argument("--port", type=int, default=8001, help="Porta do servidor (default: 8001)")
    parser.add_argument("--host", default="127.0.0.1", help="Host binding (default: 127.0.0.1)")
    parser.add_argument("--public", action="store_true", help="Expor publicamente via Ngrok")
    parser.add_argument("--ngrok-token", help="Token de autenticação Ngrok (opcional)")
    
    args = parser.parse_args()
    
    banner()
    
    # URLs
    local_url = f"http://{args.host}:{args.port}"
    public_url = None
    
    # Se modo público, iniciar Ngrok em thread separada
    if args.public and PYNGROK_AVAILABLE:
        print("\n[SISTEMA] Aguardando inicialização do Uvicorn (3s)...")
        time.sleep(3)
        
        ngrok_thread = threading.Thread(
            target=lambda: None,  # Placeholder
            daemon=True
        )
        
        # Na verdade, vamos configurar o ngrok antes de iniciar uvicorn
        try:
            print("[NGROK] Configurando túnel reverso...")
            
            # Autenticar se token fornecido
            if args.ngrok_token or os.getenv("NGROK_AUTH_TOKEN"):
                ngrok.set_auth_token(args.ngrok_token or os.getenv("NGROK_AUTH_TOKEN"))
                print("[NGROK] ✓ Autenticado com token")
            
            # Abrir túnel
            print(f"[NGROK] Tuneando porta {args.port}...")
            public_url = ngrok.connect(args.port, "http").public_url
            print(f"[NGROK] ✓ Túnel estabelecido: {public_url}")
        
        except Exception as e:
            print(f"[NGROK] ❌ Erro ao estabelecer túnel: {e}")
            print("[NGROK] ⚠️  Continuando sem túnel público...")
    
    # Exibir informações de acesso
    display_access_info(local_url, public_url)
    
    # Mensagem final
    print("\n[✓] Quinta-Feira Hub pronto! Iniciando Uvicorn...\n")
    print("[!] Pressione Ctrl+C para parar completamente.\n")
    
    try:
        # Iniciar Uvicorn em foreground (vai bloquear até Ctrl+C)
        start_uvicorn(args.port, args.host)
    
    except KeyboardInterrupt:
        print("\n\n[SHUTDOWN] A encerrar Hub...")
        
        # Cleanup
        try:
            if PYNGROK_AVAILABLE:
                ngrok.kill()
                print("[NGROK] ✓ Túnel Ngrok encerrado")
        except:
            pass
        
        print("[✓] Hub encerrado com sucesso.")
        sys.exit(0)
    
    except Exception as e:
        print(f"\n[ERRO] Erro inesperado: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()