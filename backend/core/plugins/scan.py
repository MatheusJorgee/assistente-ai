"""
Scanner estático de código proposto pela Quinta (ferramentas novas).

IMPORTANTE, honestidade: isto é uma barreira em CAMADAS, não uma sandbox. Um plugin aprovado roda
dentro do processo da Quinta, com os poderes dela. O que protege de verdade é: (1) você lê o código e
os avisos antes de aprovar; (2) o hash aprovado é conferido a cada boot (código alterado depois não
carrega); (3) a ferramenta é classificada CRÍTICA (pede aprovação a cada uso) e a saída é tratada como
conteúdo externo. O scanner só barra o óbvio e mostra o que merece atenção.

Política: allowlist de imports (lógica pura); proibido tudo que executa comandos, mexe no sistema de
arquivos, na rede crua, em introspecção ou em avaliação dinâmica. `requests`/`httpx` são permitidos
COM AVISO de rede (você decide se aceita).
"""

import ast
from typing import Dict, List

IMPORTS_OK = {
    "json", "re", "math", "datetime", "typing", "dataclasses", "collections", "itertools", "statistics",
    "hashlib", "base64", "textwrap", "string", "decimal", "fractions", "asyncio", "time", "random",
    "enum", "functools", "operator", "unicodedata", "urllib.parse", "html", "uuid", "zoneinfo",
    "core.tools.base", "core.tools",
}
IMPORTS_REDE = {"requests", "httpx", "aiohttp", "urllib.request"}     # permitidos com aviso
IMPORTS_TESTE = {"unittest", "unittest.mock", "pytest"}
PROIBIDAS_CHAMADAS = {"eval", "exec", "compile", "__import__", "open", "input", "getattr", "setattr", "delattr",
                      "globals", "locals", "vars", "breakpoint", "memoryview"}
PROIBIDOS_ATRIBUTOS = {"write_text", "write_bytes", "unlink", "rmdir", "rename", "replace", "mkdir", "touch",
                       "chmod", "system", "popen", "spawn", "startfile", "remove", "rmtree", "makedirs"}


def escanear(codigo: str, *, teste: bool = False) -> Dict[str, List[str]]:
    """{"criticos": [...], "avisos": [...]}: qualquer crítico impede a aprovação."""
    crit: List[str] = []
    avisos: List[str] = []
    try:
        arvore = ast.parse(codigo)
    except SyntaxError as exc:
        return {"criticos": [f"erro de sintaxe na linha {exc.lineno}"], "avisos": []}

    permitidos = IMPORTS_OK | (IMPORTS_TESTE if teste else set())
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            for a in no.names:
                _checar_import(a.name, permitidos, crit, avisos, no.lineno)
        elif isinstance(no, ast.ImportFrom):
            if no.level:
                crit.append(f"linha {no.lineno}: import relativo não é permitido")
            else:
                _checar_import(no.module or "", permitidos, crit, avisos, no.lineno)
        elif isinstance(no, ast.Call):
            f = no.func
            nome = f.id if isinstance(f, ast.Name) else None
            if nome in PROIBIDAS_CHAMADAS:
                crit.append(f"linha {no.lineno}: chamada proibida `{nome}()`")
            if isinstance(f, ast.Attribute) and f.attr in PROIBIDOS_ATRIBUTOS:
                crit.append(f"linha {no.lineno}: operação de sistema `.{f.attr}()`")
        elif isinstance(no, ast.Attribute):
            if no.attr.startswith("__") and no.attr.endswith("__") and no.attr not in ("__init__", "__name__", "__doc__"):
                crit.append(f"linha {no.lineno}: acesso a atributo especial `{no.attr}`")
        elif isinstance(no, (ast.Global, ast.Nonlocal)):
            avisos.append(f"linha {no.lineno}: usa estado global")
    return {"criticos": sorted(set(crit)), "avisos": sorted(set(avisos))}


def _checar_import(modulo: str, permitidos: set, crit: List[str], avisos: List[str], linha: int) -> None:
    if modulo in IMPORTS_REDE or modulo.split(".")[0] in {m.split(".")[0] for m in IMPORTS_REDE if "." not in m}:
        avisos.append(f"linha {linha}: acessa a REDE (`{modulo}`): confira para onde ele envia dados")
        return
    if modulo in permitidos:
        return
    crit.append(f"linha {linha}: import não permitido `{modulo}`")
