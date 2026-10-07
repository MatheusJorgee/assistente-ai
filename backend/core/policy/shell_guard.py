"""
Guarda de shell com estado de aspas (B8), para PowerShell e cmd.

Terminal e PowerShell já são sempre "críticos" (perguntam). Este guarda acrescenta uma segunda
camada: quando o comando contém um padrão típico de ofuscação, download-e-execução ou
alteração do sistema, o gate PERGUNTA SEMPRE, inclusive no modo autônomo e via Telegram de
confiança, e o cartão mostra os padrões achados.

Estado de aspas: no PowerShell, `$(...)` dentro de aspas SIMPLES é texto literal e inofensivo;
dentro de aspas duplas ou fora de aspas, executa. Por isso o scanner separa o texto "vivo" (fora
de aspas simples) do literal. Local, sem LLM.
"""

import re
from typing import Any, List, Mapping

FERRAMENTAS = {"executar_terminal": "comando", "v2_os_command": "script"}

# (rótulo, regex) aplicados ao texto VIVO (fora de aspas simples)
_VIVOS = [
    ("subexpressão $()", re.compile(r"\$\(")),
    ("crase de ofuscação", re.compile(r"`[A-Za-z]")),
    ("comentário de bloco <#", re.compile(r"<#")),
    ("comando codificado (-EncodedCommand)", re.compile(r"(?<![\w-])-e(nc(odedcommand)?)?\s+[A-Za-z0-9+/=]{12,}", re.I)),
    ("Invoke-Expression/iex", re.compile(r"(?<![\w-])(iex|invoke-expression)(?![\w-])", re.I)),
    ("baixa da internet", re.compile(r"(?<![\w-])(iwr|irm|invoke-webrequest|invoke-restmethod|downloadstring|downloadfile|start-bitstransfer|certutil\s+-urlcache|bitsadmin)(?![\w-])", re.I)),
    ("sobe privilégio (RunAs)", re.compile(r"-verb\s+runas", re.I)),
    ("muda a política de execução", re.compile(r"set-executionpolicy", re.I)),
    ("mexe no antivírus", re.compile(r"(add|set)-mppreference|disable-realtimemonitoring|disablerealtime", re.I)),
    ("edita o registro", re.compile(r"(?<![\w-])reg(\.exe)?\s+(add|delete|import)|set-itemproperty\s+.*hk(lm|cu)", re.I)),
    ("cria tarefa/serviço persistente", re.compile(r"schtasks\s+/create|new-service|register-scheduledtask|sc(\.exe)?\s+create", re.I)),
    ("mexe em contas de usuário", re.compile(r"net\s+user|net\s+localgroup|new-localuser", re.I)),
    ("apaga cópias de sombra/boot", re.compile(r"vssadmin\s+delete|bcdedit|wbadmin\s+delete|cipher\s+/w", re.I)),
    ("apaga em massa", re.compile(r"(remove-item|rm|del|rd|rmdir)\b[^|;&\n]*(-recurse|/s\b)[^|;&\n]*([a-z]:\\s*$|[a-z]:\\*|\\*|\s\*)", re.I)),
    ("formata disco", re.compile(r"(?<![\w-])(format(-volume)?|diskpart|clear-disk)(?![\w-])\s*", re.I)),
]

# Aplicados ao texto COMPLETO (o perigo existe mesmo dentro de aspas, ex.: powershell -c "..."
_COMPLETOS = [
    ("encadeia PowerShell codificado", re.compile(r"powershell(\.exe)?\s+.*-e(nc(odedcommand)?)?\s+[A-Za-z0-9+/=]{12,}", re.I)),
    ("baixa e executa (pipe para iex)", re.compile(r"\|\s*(iex|invoke-expression)\b", re.I)),
]


def texto_vivo(texto: str) -> str:
    """Remove o conteúdo de aspas SIMPLES (literal no PowerShell). Aspas duplas continuam vivas."""
    saida: List[str] = []
    em_simples = False
    em_duplas = False
    for ch in texto:
        if ch == '"' and not em_simples:
            em_duplas = not em_duplas
            saida.append(ch)
        elif ch == "'" and not em_duplas:
            em_simples = not em_simples
            saida.append(ch)
        elif em_simples:
            continue
        else:
            saida.append(ch)
    return "".join(saida)


def sinais(texto: str) -> List[str]:
    """Rótulos dos padrões de risco encontrados (sem repetição, na ordem)."""
    if not texto:
        return []
    vivo = texto_vivo(texto)
    achados: List[str] = []
    for rotulo, rx in _VIVOS:
        if rx.search(vivo) and rotulo not in achados:
            achados.append(rotulo)
    for rotulo, rx in _COMPLETOS:
        if rx.search(texto) and rotulo not in achados:
            achados.append(rotulo)
    return achados


def sinais_da_chamada(ferramenta: str, argumentos: Mapping[str, Any]) -> List[str]:
    campo = FERRAMENTAS.get(ferramenta)
    if not campo:
        return []
    return sinais(str((argumentos or {}).get(campo) or ""))
