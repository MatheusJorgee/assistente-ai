"""
Token por sessão: só quem recebeu o token fala com a Quinta.

O guarda de origem (local_guard.py) barra PÁGINAS de terceiros, mas outro PROGRAMA da mesma máquina
ainda alcançava o backend (que tem terminal, WhatsApp e arquivos). Aqui, a cada subida o backend gera
um token aleatório e o grava em `.runtime/session_token` (só o seu usuário lê). O frontend o busca
pelo servidor do Next (nunca vai para o bundle público) e o manda:
  - HTTP: cabeçalho `X-Quinta-Token`;
  - WebSocket: subprotocolo `qf.token.<token>` (navegador não põe cabeçalho em WebSocket; assim o token
    não vai para a URL nem para os logs).

Modos (`SESSION_TOKEN_MODE`): `off` | `registrar` (deixa passar mas avisa no log: para validar que o
frontend manda o token sem quebrar nada) | `exigir` (401 / fecha o WebSocket).

Isentos: `/health` e `/api/health` (scripts de saúde) e a pré-checagem CORS (OPTIONS).
Não substitui autenticação forte: um programa rodando como VOCÊ ainda lê o arquivo do token. Barra o que
não é você (outro usuário do Windows, processo sem acesso à pasta, página web).
"""

import hmac
import os
import secrets
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

try:
    from ..logger import get_logger
except ImportError:
    from core.logger import get_logger

logger = get_logger(__name__)

PREFIXO_SUBPROTOCOLO = "qf.token."
CABECALHO = b"x-quinta-token"
ISENTOS = {"/health", "/api/health"}
MODOS = ("off", "registrar", "exigir")
_ARQ = Path(__file__).resolve().parents[2] / ".runtime" / "session_token"

_token: Optional[str] = None


def iniciar_token(arquivo: Optional[Path] = None) -> str:
    """Gera um token novo e o grava no arquivo. Chamado uma vez por subida do backend."""
    global _token
    _token = secrets.token_urlsafe(32)
    arq = Path(arquivo) if arquivo else _ARQ
    try:
        arq.parent.mkdir(parents=True, exist_ok=True)
        arq.write_text(_token, encoding="utf-8")
        try:
            os.chmod(arq, 0o600)   # no Windows é quase inócuo; a ACL da pasta do usuário é quem protege
        except OSError:
            pass
    except OSError as exc:
        logger.warning(f"[TOKEN] não consegui gravar o arquivo do token: {exc}")
    return _token


def token_atual() -> Optional[str]:
    return _token


def modo_configurado() -> str:
    m = os.getenv("SESSION_TOKEN_MODE", "registrar").strip().lower()
    return m if m in MODOS else "registrar"


def extrair(headers: Dict[bytes, bytes]) -> Tuple[str, str]:
    """(token, subprotocolo oferecido). Vazios se não veio."""
    direto = headers.get(CABECALHO, b"").decode("latin-1").strip()
    if direto:
        return direto, ""
    for item in headers.get(b"sec-websocket-protocol", b"").decode("latin-1").split(","):
        item = item.strip()
        if item.startswith(PREFIXO_SUBPROTOCOLO):
            return item[len(PREFIXO_SUBPROTOCOLO):], item
    return "", ""


class TokenGuard:
    def __init__(self, app: Any, modo: Optional[str] = None, token_fn: Any = None) -> None:
        self.app = app
        self.modo = modo if modo in MODOS else modo_configurado()
        self._token_fn = token_fn or token_atual
        self._avisos: Dict[Tuple[str, str], float] = {}

    def _valido(self, recebido: str) -> bool:
        esperado = self._token_fn()
        return bool(esperado and recebido and hmac.compare_digest(recebido.encode(), esperado.encode()))

    def _avisar(self, tipo: str, caminho: str) -> None:
        agora = time.time()
        if agora - self._avisos.get((tipo, caminho), 0.0) > 60:   # não enche o log
            self._avisos[(tipo, caminho)] = agora
            logger.warning(f"[TOKEN] {tipo} {caminho} sem token válido ({'exigindo' if self.modo == 'exigir' else 'só registrando'})")

    async def __call__(self, scope: Dict[str, Any], receive: Any, send: Any) -> None:
        tipo = scope.get("type")
        if self.modo == "off" or tipo not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        caminho = scope.get("path", "")
        if caminho in ISENTOS or (tipo == "http" and scope.get("method") == "OPTIONS"):
            await self.app(scope, receive, send)
            return

        recebido, subprotocolo = extrair(dict(scope.get("headers") or []))
        valido = self._valido(recebido)
        if not valido:
            self._avisar(tipo, caminho)
            if self.modo == "exigir":
                if tipo == "websocket":
                    await receive()
                    await send({"type": "websocket.close", "code": 1008})
                    return
                corpo = b'{"detail":"token ausente ou invalido"}'
                await send({"type": "http.response.start", "status": 401, "headers": [
                    (b"content-type", b"application/json"), (b"content-length", str(len(corpo)).encode())]})
                await send({"type": "http.response.body", "body": corpo})
                return

        if tipo == "websocket" and subprotocolo:
            # O cliente ofereceu o subprotocolo: o servidor precisa ecoá-lo no accept, senão o navegador
            # derruba a conexão. Fazemos aqui para não mexer em cada rota que aceita WebSocket.
            async def send_com_subprotocolo(msg: Dict[str, Any]) -> None:
                if msg.get("type") == "websocket.accept" and not msg.get("subprotocol"):
                    msg = dict(msg, subprotocol=subprotocolo)
                await send(msg)
            await self.app(scope, receive, send_com_subprotocolo)
            return
        await self.app(scope, receive, send)
