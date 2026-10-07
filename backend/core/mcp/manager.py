"""
Gerenciador MCP: lê .runtime/mcp.json, sobe os servidores e registra as ferramentas deles.

Formato de .runtime/mcp.json (só VOCÊ edita; o modelo não tem como adicionar servidor):
{
  "servers": {
    "arquivos": {
      "command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "D:\\\\projetos"],
      "env": {"ALGUMA_CHAVE": "..."},        // opcional: só o que este servidor precisa
      "leitura": ["read_file", "list_directory"],   // ferramentas sem efeito colateral (sem cartão)
      "timeout_s": 30,
      "ativo": true
    }
  }
}

Cada ferramenta vira `mcp__<servidor>__<ferramenta>`:
  - risco: CRÍTICA (pede aprovação) a não ser que esteja em "leitura";
  - a saída é sempre conteúdo EXTERNO (envelope + contaminação do turno);
  - a descrição vinda do servidor é texto de terceiros: cortada e higienizada.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .client import ErroMCP, ServidorMCP

_ARQ = Path(__file__).resolve().parents[2] / ".runtime" / "mcp.json"
NOME_RE = re.compile(r"^[a-z][a-z0-9_-]{1,30}$")
MAX_FERRAMENTAS_POR_SERVIDOR = 40
PREFIXO = "mcp__"

_servidores: Dict[str, ServidorMCP] = {}
_leitura: Dict[str, set] = {}          # servidor -> ferramentas sem efeito colateral
_nomes: Dict[str, tuple] = {}          # nome registrado -> (servidor, ferramenta original)


def ler_config(arquivo: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    """Servidores válidos e ativos. Config inválida vira ignorada, nunca erro de boot."""
    try:
        bruto = json.loads((arquivo or _ARQ).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    saida: Dict[str, Dict[str, Any]] = {}
    for nome, cfg in (bruto.get("servers") or {}).items() if isinstance(bruto, dict) else []:
        if not NOME_RE.match(str(nome)) or not isinstance(cfg, dict) or not isinstance(cfg.get("command"), str) or not cfg["command"].strip():
            continue
        if cfg.get("ativo", True) is False:
            continue
        saida[nome] = {
            "command": cfg["command"].strip(),
            "args": [str(a) for a in (cfg.get("args") or [])][:30],
            "env": {str(k): str(v) for k, v in (cfg.get("env") or {}).items()} if isinstance(cfg.get("env"), dict) else {},
            "leitura": {str(x) for x in (cfg.get("leitura") or [])},
            "timeout_s": float(cfg.get("timeout_s") or 30),
        }
    return saida


def nome_da_ferramenta(servidor: str, ferramenta: str) -> str:
    seguro = re.sub(r"[^a-zA-Z0-9_]", "_", ferramenta)[:40]
    return f"{PREFIXO}{servidor}__{seguro}"


def e_mcp(nome: str) -> bool:
    return str(nome).startswith(PREFIXO)


def e_leitura(nome: str) -> bool:
    """A ferramenta MCP foi marcada por você como sem efeito colateral?"""
    info = _nomes.get(nome)
    return bool(info and info[1] in _leitura.get(info[0], set()))


def _higienizar(texto: Any, n: int) -> str:
    return " ".join(str(texto or "").split())[:n]


async def carregar(registry: Any, arquivo: Optional[Path] = None) -> List[str]:
    """Sobe os servidores configurados e registra as ferramentas. Devolve os nomes registrados.
    Falha de um servidor não derruba os outros nem o boot."""
    from .tools import MCPTool
    registradas: List[str] = []
    for nome, cfg in ler_config(arquivo).items():
        srv = ServidorMCP(nome, cfg["command"], cfg["args"], cfg["env"], cfg["timeout_s"])
        try:
            await srv.iniciar()
            ferramentas = await srv.listar_ferramentas()
        except Exception as exc:
            await srv.parar()
            print(f"[MCP] servidor '{nome}' não subiu: {type(exc).__name__}: {str(exc)[:120]}")
            continue
        _servidores[nome] = srv
        _leitura[nome] = cfg["leitura"]
        for f in ferramentas[:MAX_FERRAMENTAS_POR_SERVIDOR]:
            reg_nome = nome_da_ferramenta(nome, f["name"])
            _nomes[reg_nome] = (nome, f["name"])
            registry.register(MCPTool(reg_nome, srv, f, somente_leitura=f["name"] in cfg["leitura"]))
            registradas.append(reg_nome)
    return registradas


async def parar_todos() -> None:
    for srv in list(_servidores.values()):
        try:
            await srv.parar()
        except Exception:
            pass
    _servidores.clear()
    _leitura.clear()
    _nomes.clear()
