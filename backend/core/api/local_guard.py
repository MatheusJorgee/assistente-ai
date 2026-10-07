"""
Guarda de acesso local da Quinta-Feira (ASGI puro: cobre HTTP e WebSocket).

Por que existe: o backend controla terminal, WhatsApp e arquivos. Mesmo escutando so em
127.0.0.1, uma PAGINA WEB qualquer aberta no seu navegador pode tentar falar com
ws://127.0.0.1:8000 (o navegador deixa; CORS nao protege WebSocket) ou fazer POSTs
"simples" cross-site. Duas checagens fecham isso:

  1. Host: so localhost / 127.0.0.1 / [::1] (+ EXTRA_ALLOWED_HOSTS). Barra DNS rebinding,
     em que um dominio malicioso passa a resolver para 127.0.0.1.
  2. Origin: se o cabecalho existe (todo navegador manda em WebSocket e em POST cross-site),
     tem que ser o frontend (ou EXTRA_ALLOWED_ORIGINS). Cliente sem Origin (curl, scripts
     locais, o proprio Next no servidor) passa — nao e navegador de terceiros.

Nao e autenticacao: outro programa da MESMA maquina ainda alcanca o backend. Token por
sessao continua no plano (Fase 0.2).
"""

from typing import Any, Dict, Iterable, Tuple

try:
    from ..logger import get_logger
except ImportError:  # execucao fora do pacote
    from core.logger import get_logger

logger = get_logger(__name__)

HOSTS_LOCAIS = ("localhost", "127.0.0.1", "[::1]")


def origens_permitidas(frontend_url: str, extras: Iterable[str] = ()) -> Tuple[str, ...]:
    """Mesmas origens do CORS do main.py (frontend em 3000, docs em 8000) + extras."""
    base = [
        frontend_url,
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]
    return tuple(dict.fromkeys(o.rstrip("/").lower() for o in [*base, *extras] if o))


class LocalOnlyGuard:
    def __init__(self, app: Any, allowed_origins: Iterable[str], allowed_hosts: Iterable[str] = ()) -> None:
        self.app = app
        self.origens = {o.rstrip("/").lower() for o in allowed_origins if o}
        self.hosts = {h.strip().lower() for h in (*HOSTS_LOCAIS, *allowed_hosts) if h}

    @staticmethod
    def _so_host(valor: str) -> str:
        h = (valor or "").strip().lower()
        if h.startswith("["):  # IPv6 literal: [::1]:8000
            return h.split("]")[0] + "]"
        return h.split(":")[0]

    def avaliar(self, headers: Dict[bytes, bytes]) -> Tuple[bool, str]:
        host = self._so_host(headers.get(b"host", b"").decode("latin-1"))
        if host not in self.hosts:
            return False, f"host não permitido: {host!r}"
        origem = headers.get(b"origin", b"").decode("latin-1").strip().rstrip("/").lower()
        if origem and origem not in self.origens:
            return False, f"origem não permitida: {origem!r}"
        return True, ""

    async def __call__(self, scope: Dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        ok, motivo = self.avaliar(dict(scope.get("headers") or []))
        if ok:
            await self.app(scope, receive, send)
            return

        logger.warning(f"[GUARD] Acesso barrado ({scope.get('type')} {scope.get('path')}): {motivo}")
        if scope["type"] == "websocket":
            # Fechar ANTES do accept rejeita o handshake (o cliente recebe 403).
            await receive()  # websocket.connect
            await send({"type": "websocket.close", "code": 1008})
            return

        corpo = b'{"detail":"acesso negado"}'
        await send({
            "type": "http.response.start",
            "status": 403,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(corpo)).encode())],
        })
        await send({"type": "http.response.body", "body": corpo})
