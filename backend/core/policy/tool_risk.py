"""
Classificacao de risco das ferramentas da Quinta-Feira (Fase 0.3 do plano).

Tres classes, decididas por FERRAMENTA e, quando ela faz coisas muito diferentes, por ACAO:

  LEITURA  so consulta; nenhum efeito no mundo (cotar, listar, ler arquivo, pesquisar).
  ESCRITA  muda estado LOCAL e reversivel (lembrete, memoria, abrir app, tocar musica).
  CRITICA  efeito externo ou irreversivel: enviar mensagem, terminal, apagar/escrever
           arquivo, iniciar/encerrar processo.

So a CRITICA pede aprovacao no modo padrao (core/policy/approvals.py). A classificacao e
uma tabela EXPLICITA: o smoke test falha se uma ferramenta registrada nao estiver nela,
entao ferramenta nova nao entra "sem ninguem ter pensado no risco".

Macros nao aparecem como critica: cada passo roda por ToolRegistry.execute e e classificado
individualmente. `agendar_acao` idem: o comando agendado passa pelo gate quando dispara.
"""

from enum import Enum
from typing import Any, Dict, Mapping, Optional, Tuple


class Risco(str, Enum):
    LEITURA = "leitura"
    ESCRITA = "escrita"
    CRITICA = "critica"


_ORDEM = {Risco.LEITURA: 0, Risco.ESCRITA: 1, Risco.CRITICA: 2}

L, E, C = Risco.LEITURA, Risco.ESCRITA, Risco.CRITICA

# ferramenta -> risco fixo (nao depende da acao)
RISCO_FIXO: Dict[str, Risco] = {
    "abrir_programa": E,
    "abrir_e_olhar": E,
    "agenda": L,
    "agendar_acao": E,
    "anotar_ideia": E,
    "buscar_arquivo": L,
    "calcular": L,
    "capturar_tela": L,
    "clipboard_inject": E,
    "controlar_midia": E,
    "discord": L,
    "discord_amigos": L,
    "executar_terminal": C,
    "foco": E,
    "ler_documento": L,
    "macro": E,
    "memorizar_informacao": E,
    "mostrar_no_visor": L,
    "mostrar_holograma": L,
    "network_scan_local": E,
    "pesquisar_informacao_online": L,
    "rascunhar": L,
    "sistema": L,
    "v2_os_command": C,
    "vlc_control": E,
    "tocar_youtube_invisivel": E,
}

# ferramenta -> (campo que carrega a acao, {acao: risco}, risco de acao DESCONHECIDA)
# Acao desconhecida cai no valor mais cauteloso: um alias/typo do LLM nao pode virar brecha.
RISCO_POR_ACAO: Dict[str, Tuple[str, Dict[str, Risco], Risco]] = {
    "whatsapp": ("acao", {
        "enviar_mensagem": C, "criar_sessao": E,
        "triagem": L, "ler_mensagens": L, "status": L,
    }, C),
    "v2_file_ops": ("action", {
        "write_file": C, "delete": C, "undo": E, "read_file": L, "list_dir": L,
    }, C),
    "v2_process_control": ("action", {
        "start": C, "stop": C, "list": L,
    }, C),
    "skills": ("acao", {"listar": L, "ler": L, "propor": E}, E),
    "propor_ferramenta": ("acao", {"listar": L, "propor": E}, E),
    "pendencias": ("acao", {"listar": L, "preparo": L, "adicionar": E, "resolver": E, "dispensar": E}, E),
    "financas": ("acao", {
        "acompanhar": E, "parar_de_acompanhar": E, "cotar": L, "listar": L,
    }, E),
    "lembrete": ("acao", {"criar": E, "cancelar": E, "listar": L}, E),
    "pessoas": ("acao", {"salvar": E, "consultar": L, "listar": L, "esquecidos": L}, E),
}

# SecurityLevel do proprio metadata da tool -> risco (rede de seguranca p/ tool NAO listada acima)
_POR_SECURITY_LEVEL = {"low": L, "medium": E, "critical": C}


def _mais_estrito(a: Risco, b: Risco) -> Risco:
    return a if _ORDEM[a] >= _ORDEM[b] else b


def classificar(nome: str, argumentos: Optional[Mapping[str, Any]] = None, tool: Any = None) -> Risco:
    """Risco de UMA chamada (ferramenta + argumentos). Nunca levanta excecao."""
    argumentos = argumentos or {}
    try:
        if nome.startswith("mcp__"):
            # Ferramenta de servidor MCP: CRÍTICA (pede aprovação) salvo as que VOCÊ marcou como
            # somente leitura no mcp.json.
            from ..mcp import e_leitura
            return L if e_leitura(nome) else C
        if nome.startswith("agente_"):
            # Ferramenta criada pela Quinta e aprovada por você: CRÍTICA a cada uso, salvo as que você
            # marcou como somente leitura ao aprovar.
            from ..plugins import e_leitura as _plugin_leitura
            return L if _plugin_leitura(nome) else C
        if nome in RISCO_POR_ACAO:
            campo, mapa, desconhecida = RISCO_POR_ACAO[nome]
            acao = str(argumentos.get(campo) or "").strip().lower()
            return mapa.get(acao, desconhecida)

        if nome == "v2_os_command" and bool(argumentos.get("dry_run")):
            return L  # dry_run nao executa nada

        if nome in RISCO_FIXO:
            return RISCO_FIXO[nome]

        # Tool nao classificada: usa o SecurityLevel declarado por ela; sem isso, ESCRITA.
        nivel = getattr(getattr(getattr(tool, "metadata", None), "security_level", None), "value", None)
        return _POR_SECURITY_LEVEL.get(str(nivel), E)
    except Exception:
        return C  # na duvida (erro ao classificar), o mais cauteloso


def esta_classificada(nome: str) -> bool:
    """True se a ferramenta tem classificacao EXPLICITA (usado pelo smoke test)."""
    return nome in RISCO_FIXO or nome in RISCO_POR_ACAO or nome.startswith(("mcp__", "agente_"))


def _cortar(valor: Any, limite: int = 280) -> str:
    texto = str(valor if valor is not None else "").replace("\r", " ").replace("\n", " ").strip()
    return texto if len(texto) <= limite else texto[: limite - 1] + "…"


def resumir(nome: str, argumentos: Optional[Mapping[str, Any]] = None) -> str:
    """Frase curta em portugues do que a chamada FARIA, para o cartao de aprovacao.
    Mostra o comando/texto de verdade: e exatamente o que o dono precisa ver para decidir."""
    a = dict(argumentos or {})
    if nome.startswith("mcp__"):
        servidor, _, ferramenta = nome[5:].partition("__")
        return f"Chamar {servidor}/{ferramenta} (servidor MCP) com {_cortar(a, 240)}"
    if nome == "whatsapp":
        acao = str(a.get("acao") or "").lower()
        if acao == "enviar_mensagem":
            return f"Enviar WhatsApp para {_cortar(a.get('destinatario') or '?', 60)}: “{_cortar(a.get('mensagem'))}”"
        return f"WhatsApp: {_cortar(acao or 'ação desconhecida', 60)}"
    if nome in ("executar_terminal", "v2_os_command"):
        from .shell_guard import sinais_da_chamada
        avisos = sinais_da_chamada(nome, a)
        aviso = f" ⚠ Atenção: {', '.join(avisos)}" if avisos else ""
        if nome == "executar_terminal":
            return f"Executar no terminal: {_cortar(a.get('comando'))}{aviso}"
        return f"Executar script no PowerShell: {_cortar(a.get('script'))}{aviso}"
    if nome == "v2_file_ops":
        acao = str(a.get("action") or "").lower()
        caminho = _cortar(a.get("path"), 200)
        if acao == "delete":
            return f"Apagar {caminho}" + (" (recursivo)" if a.get("recursive") else "")
        if acao == "undo":
            return "Desfazer a última operação de arquivo"
        if acao == "write_file":
            tam = len(str(a.get("content") or ""))
            return f"Escrever em {caminho} ({tam} caracteres)" + (" — sobrescrevendo" if a.get("overwrite") else "")
        return f"Arquivos ({_cortar(acao, 30)}): {caminho}"
    if nome == "v2_process_control":
        acao = str(a.get("action") or "").lower()
        if acao == "stop":
            return f"Encerrar o processo {_cortar(a.get('pid'), 20)}" + (" à força" if a.get("force") else "")
        if acao == "start":
            return f"Iniciar {_cortar(a.get('executable'), 120)} {_cortar(a.get('args') or '', 120)}".strip()
        return f"Processos ({_cortar(acao, 30)})"
    partes = ", ".join(f"{k}={_cortar(v, 60)}" for k, v in list(a.items())[:5])
    return f"{nome}({partes})"
