"""
Carrega, no boot, as ferramentas que VOCÊ aprovou (plugins_agent/ + manifesto com hash pinado).

Cada arquivo é conferido de novo antes de importar: hash igual ao aprovado e scanner sem críticos.
Arquivo alterado depois da aprovação, arquivo fora do manifesto ou nome fora do padrão NÃO carregam.
As ferramentas carregadas se chamam `agente_<nome>` e são CRÍTICAS (pedem aprovação a cada uso) a
não ser que você tenha marcado "somente leitura" ao aprovar; a saída é sempre conteúdo externo.
"""

import hashlib
import importlib.util
from pathlib import Path
from typing import Any, List, Optional

from .scan import escanear
from .store import NOME_RE, PluginStore, get_plugin_store

PREFIXO = "agente_"
_leitura: set = set()


def e_plugin(nome: str) -> bool:
    return str(nome).startswith(PREFIXO)


def e_leitura(nome: str) -> bool:
    return nome in _leitura


def carregar_plugins(registry: Any, store: Optional[PluginStore] = None) -> List[str]:
    """Registra as ferramentas aprovadas e íntegras. Nunca levanta: plugin ruim é ignorado."""
    store = store or get_plugin_store()
    registradas: List[str] = []
    for nome, info in store.aprovadas().items():
        try:
            if not NOME_RE.match(nome):
                continue
            arq = Path(store.dir) / f"{nome}.py"
            codigo = arq.read_text(encoding="utf-8")
            if hashlib.sha256(codigo.encode("utf-8")).hexdigest() != info.get("sha"):
                print(f"[PLUGINS] '{nome}' NÃO carregado: o arquivo mudou depois da aprovação")
                continue
            if escanear(codigo)["criticos"]:
                print(f"[PLUGINS] '{nome}' NÃO carregado: o scanner bloqueou")
                continue
            spec = importlib.util.spec_from_file_location(f"plugin_agente_{nome}", arq)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            for tool in list(getattr(mod, "TOOLS", []))[:5]:
                if tool.metadata.name != f"{PREFIXO}{nome}":
                    print(f"[PLUGINS] '{nome}': a ferramenta deve se chamar '{PREFIXO}{nome}' (veio '{tool.metadata.name}')")
                    continue
                registry.register(tool)
                registradas.append(tool.metadata.name)
                if info.get("leitura"):
                    _leitura.add(tool.metadata.name)
        except Exception as exc:
            print(f"[PLUGINS] '{nome}' falhou ao carregar: {type(exc).__name__}: {str(exc)[:120]}")
    return registradas
