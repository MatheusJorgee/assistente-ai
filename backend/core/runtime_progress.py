"""
Progresso em tempo real (Fase 0.6): a tela ve O QUE a Quinta esta fazendo, enquanto faz.

O brain nao conhece o WebSocket. Quem hospeda a conversa (o router) instala um callback no
CONTEXTO da tarefa (`com_progresso`), e o brain so chama `emitir(...)`. Sem callback (Telegram,
loop autonomo, testes) `emitir` nao faz nada — nunca quebra o fluxo principal.

Eventos:
  tool_call_start   {tool, label, iteration}
  tool_call_result  {tool, ok, duration_ms}
  text_delta        {text}   pedaco da resposta, conforme o modelo gera (streaming)
  text_reset        {}       descarte o que foi mostrado: a volta terminou numa ferramenta
                             (o texto era so um preambulo) ou o streaming falhou e recomecou

So vai o NOME da ferramenta e um rotulo humano ("lendo suas mensagens do WhatsApp"), nunca os
argumentos: eles podem ter conteudo privado, e o cartao de aprovacao ja mostra o que importa.
"""

import contextlib
import contextvars
from typing import Any, Awaitable, Callable, Dict, Mapping, Optional

Callback = Callable[[str, Dict[str, Any]], Awaitable[None]]

_callback: "contextvars.ContextVar[Optional[Callback]]" = contextvars.ContextVar("qf_progresso", default=None)


@contextlib.contextmanager
def com_progresso(callback: Callback):
    """`with com_progresso(cb): await brain.ask(...)` — quem escuta o progresso desta tarefa."""
    token = _callback.set(callback)
    try:
        yield
    finally:
        _callback.reset(token)


def tem_ouvinte() -> bool:
    """Alguem esta escutando o progresso desta tarefa? (so entao vale gastar streaming)"""
    return _callback.get() is not None


async def emitir(tipo: str, /, **dados: Any) -> None:
    """Avisa quem estiver escutando. Silencioso se ninguem escuta ou se o callback falhar."""
    callback = _callback.get()
    if callback is None:
        return
    try:
        await callback(tipo, dict(dados))
    except Exception:
        pass


_ROTULOS: Dict[str, str] = {
    "pesquisar_informacao_online": "pesquisando na web",
    "ler_documento": "lendo o documento",
    "buscar_arquivo": "procurando arquivos",
    "agenda": "consultando a agenda",
    "calcular": "fazendo as contas",
    "financas": "consultando o mercado",
    "lembrete": "mexendo nos lembretes",
    "pessoas": "consultando o que sei das pessoas",
    "memorizar_informacao": "guardando na memória",
    "controlar_midia": "controlando a mídia",
    "abrir_programa": "abrindo o programa",
    "capturar_tela": "olhando a tela",
    "executar_terminal": "rodando um comando",
    "v2_os_command": "rodando um script",
    "v2_file_ops": "mexendo em arquivos",
    "v2_process_control": "mexendo em processos",
    "mostrar_no_visor": "preparando o visor",
    "mostrar_holograma": "montando o holograma",
    "skills": "consultando as skills",
    "propor_ferramenta": "propondo uma ferramenta nova",
    "abrir_e_olhar": "abrindo e olhando a tela",
    "pendencias": "mexendo nas pendências",
    "rascunhar": "escrevendo um rascunho",
    "macro": "rodando uma rotina",
    "agendar_acao": "agendando uma ação",
    "anotar_ideia": "anotando a ideia",
    "foco": "cuidando do seu foco",
    "discord": "olhando o Discord",
    "discord_amigos": "olhando o Discord",
    "sistema": "olhando o sistema",
    "clipboard_inject": "copiando para a área de transferência",
    "vlc_control": "controlando o VLC",
    "network_scan_local": "escaneando a rede",
    "tocar_youtube_invisivel": "colocando a música",
}


def rotulo_ferramenta(nome: str, argumentos: Optional[Mapping[str, Any]] = None) -> str:
    """Frase curta, em portugues, do que a ferramenta esta fazendo agora."""
    if nome == "whatsapp":
        acao = str((argumentos or {}).get("acao") or "").lower()
        if acao == "enviar_mensagem":
            return "enviando mensagem no WhatsApp"
        if acao in ("ler_mensagens", "triagem"):
            return "lendo suas mensagens do WhatsApp"
        return "mexendo no WhatsApp"
    return _ROTULOS.get(nome, f"usando {nome}")


def resultado_ok(texto: Any) -> bool:
    """A saida de uma tool indica sucesso? (erros voltam como texto com prefixo conhecido)"""
    inicio = str(texto or "").lstrip()[:24].upper()
    return not inicio.startswith(("[ERRO", "[APROVAÇÃO_NEGADA", "[POLICY_BLOCKED", "[TOOL_"))
