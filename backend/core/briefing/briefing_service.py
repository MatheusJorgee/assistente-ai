"""
Compositor do briefing matinal.

Reúne clima + notícias de forma determinística e usa o LLM APENAS para
transformar os dados em um texto falado natural (1 chamada, sem tools, sem
injeção de memória — barato e previsível).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

try:
    from .. import get_config, get_logger
    from ..llm_provider import Message
except ImportError:
    from .. import get_config, get_logger
    from ..llm_provider import Message

from .weather import get_weather
from .news import get_top_news

logger = get_logger(__name__)


def _saudacao(hora: int) -> str:
    if 5 <= hora < 12:
        return "Bom dia"
    if 12 <= hora < 18:
        return "Boa tarde"
    return "Boa noite"


async def gerar_briefing(brain: Any) -> str:
    """
    Gera o texto do briefing matinal (clima + notícias + saudação).

    Args:
        brain: instância QuintaFeiraBrain (usamos brain.llm_provider direto).

    Returns:
        Texto pronto para ser falado/exibido.
    """
    config = get_config()
    agora = datetime.now()

    # 1. Coleta determinística (paralela seria possível, mas serial é simples e suficiente)
    clima = await get_weather(config.BRIEFING_CITY, config.OPENWEATHER_API_KEY)
    noticias = await get_top_news(limit=config.BRIEFING_NEWS_COUNT)

    # 2. Monta o contexto factual
    linhas = []
    if clima:
        linhas.append(
            f"Clima em {clima['cidade']}: {clima['temp']} graus "
            f"(sensacao {clima['sensacao']}), {clima['descricao']}, "
            f"minima {clima['min']}, maxima {clima['max']}, umidade {clima['umidade']}%."
        )
    else:
        linhas.append("Clima: indisponivel no momento.")

    if noticias:
        linhas.append("Manchetes do momento:")
        for n in noticias:
            linhas.append(f"- {n}")
    else:
        linhas.append("Noticias: indisponiveis no momento.")

    contexto = "\n".join(linhas)

    # 3. Composição via LLM (sem tools, sem histórico — chamada isolada e barata)
    system = (
        "Voce e a Quinta-Feira, assistente do Matheus, fazendo o briefing matinal. "
        "Fale de forma natural, breve e direta, como uma secretaria executiva eficiente. "
        "IMPORTANTE: o texto sera FALADO em voz alta - nada de markdown, listas com simbolos, "
        "asteriscos ou emojis. Comece com a saudacao do horario. Resuma o clima em uma frase "
        "e as noticias em 2 a 3 frases agrupando os temas por assunto. Maximo 6 frases."
    )
    user = (
        f"Saudacao sugerida: {_saudacao(agora.hour)}. "
        f"Horario: {agora.strftime('%H:%M de %d/%m/%Y')}.\n\n"
        f"Dados coletados:\n{contexto}\n\n"
        "Gere o briefing falado agora."
    )

    try:
        response = await brain.llm_provider.generate(
            messages=[
                Message(role="system", content=system),
                Message(role="user", content=user),
            ],
            tools=None,
            temperature=0.6,
        )
        texto = (response.text or "").strip()
        if texto:
            logger.info(f"[BRIEFING] Gerado ({len(texto)} chars)")
            return texto
    except Exception as exc:
        logger.warning(f"[BRIEFING] Falha ao compor via LLM: {exc}")

    # 4. Fallback sem LLM: entrega os dados crus de forma legível
    fallback = f"{_saudacao(agora.hour)}, Matheus. " + " ".join(
        l for l in linhas if not l.startswith("-")
    )
    return fallback
