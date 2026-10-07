"""
Guarda de caminhos sensíveis para ferramentas MCP.

O servidor de arquivos enxerga TUDO dentro da pasta que você liberou, inclusive `.env`, `.vault`,
perfis de navegador e chaves. Ferramentas de LEITURA não pedem aprovação, e o que elas devolvem vai
para o modelo (a API do Google). Então, antes de qualquer chamada, os argumentos são conferidos: um
caminho que parece segredo é recusado localmente (o servidor nem é chamado). A saída também tem
segredos mascarados. Local, sem LLM.
"""

import re
from typing import Any, Iterable, Optional

_SENSIVEL = re.compile(
    r"(^|/)(\.env(?!\.(example|sample|template)\b)[\w.-]*"
    r"|\.vault|\.wa_profile|\.yt_profile|\.ssh|\.aws|\.azure|\.kube|\.gnupg|\.git-credentials|\.netrc|\.npmrc|\.pypirc"
    r"|id_rsa[\w.-]*|id_ed25519[\w.-]*|[\w.-]+\.(pem|pfx|p12|key|kdbx)"
    r"|(credentials?|secrets?|tokens?)(\.[\w]+)?|cookies|login data|web data|local state)(/|$)", re.I)
_SEGREDO_NO_TEXTO = re.compile(
    r"(AIza[0-9A-Za-z_\-]{20,}|sk-[A-Za-z0-9_\-]{16,}|xox[bap]-[A-Za-z0-9\-]{10,}|gh[pousr]_[A-Za-z0-9]{20,}"
    r"|\b\d{6,}:[A-Za-z0-9_\-]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"|^\s*[A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|SENHA)[A-Z0-9_]*\s*=\s*\S+)", re.I | re.M)


def _strings(valor: Any) -> Iterable[str]:
    if isinstance(valor, str):
        yield valor
    elif isinstance(valor, dict):
        for v in valor.values():
            yield from _strings(v)
    elif isinstance(valor, (list, tuple)):
        for v in valor:
            yield from _strings(v)


def caminho_sensivel(argumentos: Any) -> Optional[str]:
    """O primeiro argumento que parece um caminho de segredo, ou None."""
    for s in _strings(argumentos):
        norm = s.replace("\\", "/")
        if _SENSIVEL.search(norm):
            return s[:120]
    return None


def mascarar_segredos(texto: str) -> str:
    return _SEGREDO_NO_TEXTO.sub("[segredo omitido]", texto or "")
