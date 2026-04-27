"""
WhatsAppTool -- Envio de mensagens via WhatsApp Web (CDP + Edge externo).

Suporta destinatario por NUMERO ou NOME DE CONTATO:
  - Numero  -> deep link direto (/send?phone=...)
  - Nome    -> pesquisa na UI do WhatsApp Web (barra de busca)

Auto-Launch: se o Edge nao estiver rodando, inicia automaticamente
com --remote-debugging-port=9222.

Pre-requisito (manual ou automatico):
  msedge.exe --remote-debugging-port=9222
             --user-data-dir=C:\\wa_bot_profile
             --no-first-run
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import subprocess
import sys
import urllib.parse
from typing import Any

try:
    from .base import MotorTool, SecurityLevel, ToolMetadata, ToolParameter
except ImportError:
    from base import MotorTool, SecurityLevel, ToolMetadata, ToolParameter

logger = logging.getLogger(__name__)

_CDP_URL = "http://localhost:9222"
_WA_BOOT_TIMEOUT_MS = 60_000
_WA_SEND_TIMEOUT_MS = 120_000

_MSG_BOX_SELECTOR = (
    'div[contenteditable="true"][data-tab="10"], '
    'div[contenteditable="true"][data-tab="11"], '
    'footer .lexical-rich-text-input'
)
_SEARCH_BOX_SELECTOR = 'div[contenteditable="true"][data-tab="3"]'


def _is_phone(destinatario: str) -> bool:
    """True se o destinatario e composto apenas por digitos/+/-/espaco."""
    return bool(re.fullmatch(r"[\d\+\-\s]+", destinatario.strip()))


def _normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    if not phone.strip().startswith("+"):
        if not digits.startswith("55"):
            digits = "55" + digits
    return digits


async def _connect(pw) -> tuple:
    """Conecta ao Edge; lanca o processo se necessario. Retorna (browser, ctx, page)."""
    from playwright.async_api import async_playwright  # noqa (ja importado pelo caller)

    try:
        browser = await pw.chromium.connect_over_cdp(_CDP_URL)
        logger.info("[WHATSAPP] Conectado ao Edge via CDP.")
    except Exception:
        logger.warning("[WHATSAPP] Edge nao encontrado -- iniciando processo...")
        subprocess.Popen([
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            "--remote-debugging-port=9222",
            r"--user-data-dir=C:\wa_bot_profile",
            "--no-first-run",
            "--no-default-browser-check",
        ])
        await asyncio.sleep(5)
        logger.info("[WHATSAPP] Reconectando ao Edge...")
        browser = await pw.chromium.connect_over_cdp(_CDP_URL)

    ctx = browser.contexts[0] if browser.contexts else await browser.new_context()

    # Radar de abas: prioriza aba que ja tem WhatsApp aberto
    page = None
    for p in ctx.pages:
        if "web.whatsapp.com" in p.url:
            page = p
            break

    if not page:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

    # Acorda a aba e traz para foreground (evita throttling de aba inativa)
    await page.bring_to_front()
    await asyncio.sleep(1)

    return browser, ctx, page


async def _boot_whatsapp(page) -> None:
    """Boot suave: abre web.whatsapp.com e espera a UI principal."""
    logger.info("[WHATSAPP] Boot: aguardando UI principal...")
    await page.goto("https://web.whatsapp.com", timeout=_WA_SEND_TIMEOUT_MS)
    try:
        await page.wait_for_selector("canvas, #pane-side", timeout=_WA_BOOT_TIMEOUT_MS)
        logger.info("[WHATSAPP] UI principal carregada.")
        await asyncio.sleep(2)
    except Exception:
        logger.warning("[WHATSAPP] Boot timeout -- continuando mesmo assim...")


async def _playwright_send(destinatario: str, message: str) -> str:
    try:
        from playwright.async_api import async_playwright, TimeoutError as PWTimeout
    except ImportError:
        raise RuntimeError(
            "playwright nao instalado. "
            "Execute: pip install playwright && playwright install msedge"
        )

    async with async_playwright() as pw:
        _browser, _ctx, page = await _connect(pw)

        if _is_phone(destinatario):
            # ── Fluxo por NUMERO: deep link ─────────────────────────────
            phone_digits = _normalize_phone(destinatario)
            url_envio = (
                f"https://web.whatsapp.com/send"
                f"?phone={phone_digits}&text={urllib.parse.quote(message)}"
            )
            logger.info("[WHATSAPP] Rota NUMERO -> deep link para %s", phone_digits)

            await _boot_whatsapp(page)

            logger.info("[WHATSAPP] Navegando para deep link de envio...")
            await page.goto(url_envio, timeout=_WA_SEND_TIMEOUT_MS)
            await asyncio.sleep(2)

            try:
                await page.wait_for_selector(_MSG_BOX_SELECTOR, timeout=30000)
            except PWTimeout:
                raise PermissionError(
                    "[TIMEOUT] Caixa de texto nao apareceu. Verifique autenticacao no Edge."
                )

            await asyncio.sleep(1.5)
            # Texto preenchido pelo deep link -- apenas Enter
            await page.keyboard.press("Enter")

        else:
            # ── Fluxo por NOME: pesquisa na UI ───────────────────────────
            logger.info("[WHATSAPP] Rota NOME -> pesquisando contato '%s'", destinatario)

            # 0. Acessa o WhatsApp apenas se nao estiver la (evita refresh)
            if "web.whatsapp.com" not in page.url:
                await page.goto("https://web.whatsapp.com", timeout=_WA_SEND_TIMEOUT_MS)

            # 1. Aguarda barra de pesquisa com seletor inquebravel
            search_box_selector = '#side div[contenteditable="true"]'
            await page.wait_for_selector(search_box_selector, timeout=30000)
            await asyncio.sleep(1)
            await page.click(search_box_selector)
            await page.keyboard.type(destinatario)
            await asyncio.sleep(2)  # aguarda resultados filtrarem

            # 2. Analisa resultados com heuristica Two-Pass (exato > parcial)
            await page.wait_for_selector("#pane-side span[title]", timeout=15000)
            await asyncio.sleep(1.5)

            elementos = await page.locator("#pane-side span[title]").all()
            alvo = None

            # Passo 1: match exato (case-insensitive)
            for el in elementos:
                nome = await el.get_attribute("title")
                if nome and destinatario.lower() == nome.lower():
                    alvo = el
                    break

            # Passo 2: match parcial (fallback)
            if not alvo:
                for el in elementos:
                    nome = await el.get_attribute("title")
                    if nome and destinatario.lower() in nome.lower():
                        alvo = el
                        break

            if alvo:
                await alvo.scroll_into_view_if_needed()
                await alvo.click()
                logger.info("[WHATSAPP] Contato selecionado via heuristica.")
            else:
                raise ValueError(
                    f"Nao encontrei ninguem parecido com '{destinatario}' nos resultados. "
                    "Use o nome exato salvo no celular ou forneça o numero."
                )

            # 3. Aguarda caixa de mensagem da conversa abrir no painel principal
            await page.wait_for_selector('#main div[contenteditable="true"]', timeout=10000)
            await asyncio.sleep(1)

            # 4. Digita a mensagem como humano e envia
            await page.keyboard.type(message)
            await asyncio.sleep(1)
            await page.keyboard.press("Enter")

        logger.info("[WHATSAPP] Enter pressionado. Aguardando envio...")
        await asyncio.sleep(3)

    return json.dumps(
        {"ok": True, "destinatario": destinatario, "preview": message[:80]},
        ensure_ascii=False,
    )


def _send_in_thread(destinatario: str, message: str) -> str:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_playwright_send(destinatario, message))
    finally:
        loop.close()

async def triagem_notificacoes_whatsapp() -> str:
    """
    Le contatos fixados e mensagens nao lidas no WhatsApp Web via texto bruto do DOM.

    DIRETRIZ ESTRITA DE RELATORIO: Ao receber a lista do WhatsApp, voce DEVE filtrar o ruido antes de falar com o usuario.
    Use sua inteligencia para diferenciar Nomes de Pessoas (ex: 'Mae', 'Paulo') de Nomes de Grupos/Lojas (ex: 'Crias e o Miau', 'Achados Originais', frases longas).
    Se voce classificar o nome como um GRUPO ou LOJA, e a flag 'has_mention' for False, E ESTRITAMENTE PROIBIDO menciona-lo no resumo. Ignore-o silenciosamente.
    So relate Grupos se 'has_mention' for True. Relate Pessoas normalmente se tiverem nova mensagem.
    """
    import re as _re

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise RuntimeError("playwright nao instalado. Execute: pip install playwright && playwright install msedge")

    async with async_playwright() as pw:
        _browser, _ctx, page = await _connect(pw)

        if "web.whatsapp.com" not in page.url:
            await _boot_whatsapp(page)

        try:
            await page.wait_for_selector("#pane-side", timeout=10000)
            await page.wait_for_timeout(1000)
        except Exception as e:
            print(f"[WHATSAPP RADAR] Erro: Painel lateral nao carregou a tempo. {e}")

        print("\n--- [WHATSAPP RADAR] INICIANDO VARREDURA DA LISTA LATERAL ---")

        chats = await page.locator('#pane-side div[role="listitem"], #pane-side div[role="row"]').all()
        print(f"[WHATSAPP RADAR] Total de chats encontrados no DOM: {len(chats)}")

        resultados = []

        for i, chat in enumerate(chats[:15]):
            try:
                texto = await chat.inner_text()
                texto_limpo = texto.replace("\n", " | ")
                texto_lower = texto.lower()
                html_interno = (await chat.evaluate("el => el.innerHTML")).lower()

                tem_nao_lida = " lida" in texto_lower
                is_pinned = "pin" in html_interno or "fixado" in texto_lower
                is_grupo = "default-group" in html_interno or "grupo" in html_interno or "group" in html_interno
                is_muted = 'data-icon="muted"' in html_interno or "silenciado" in texto_lower
                has_mention = 'data-icon="mention"' in html_interno or "@" in texto_limpo

                if i < 10:
                    print(f"Chat {i}: {texto_limpo[:120]} | nao_lida={tem_nao_lida} | pinned={is_pinned} | muted={is_muted} | mention={has_mention}")

                # Filtro do silencio: mudo e nao fixado = descarta
                if is_muted and not is_pinned:
                    continue

                if tem_nao_lida or is_pinned:
                    partes = [p.strip() for p in texto_limpo.split("|")]

                    # Nome: se a primeira parte contiver "lida", o nome está na segunda
                    if partes and "lida" in partes[0].lower():
                        nome = partes[1].strip() if len(partes) > 1 else partes[0]
                    else:
                        nome = partes[0].strip()

                    # Contagem de nao lidas: regex no texto bruto
                    m = _re.search(r"(\d+)\s*mensagem", texto_lower)
                    nao_lidas = int(m.group(1)) if m else (1 if tem_nao_lida else 0)

                    print(f"[WHATSAPP RADAR] Detectado: nome={nome!r} | pinned={is_pinned} | nao_lidas={nao_lidas} | grupo={is_grupo} | mention={has_mention}")
                    resultados.append({
                        "nome": nome,
                        "is_pinned": is_pinned,
                        "tem_nova_mensagem": tem_nao_lida,
                        "has_mention": has_mention,
                        "raw_text": texto_limpo[:200],
                    })
            except Exception as e:
                print(f"Chat {i}: [ERRO: {e}]")
                continue

        print("--- [WHATSAPP RADAR] FIM DA VARREDURA ---\n")

    if not resultados:
        return "Triagem concluida. Nenhuma mensagem nova importante ou pin relevante encontrado no momento."
    return f"Resultado da Triagem:\n{json.dumps(resultados, ensure_ascii=False, indent=2)}"


async def ler_mensagens_whatsapp(contato: str, limite: int = 5) -> str:
    """Abre o chat de um contato e retorna as ultimas N mensagens."""
    try:
        from playwright.async_api import async_playwright, TimeoutError as PWTimeout
    except ImportError:
        raise RuntimeError("playwright nao instalado. Execute: pip install playwright && playwright install msedge")

    async with async_playwright() as pw:
        _browser, _ctx, page = await _connect(pw)

        if "web.whatsapp.com" not in page.url:
            await _boot_whatsapp(page)

        # 1. Abrir barra de busca e digitar contato
        try:
            await page.wait_for_selector(_SEARCH_BOX_SELECTOR, timeout=15000)
        except Exception:
            await page.wait_for_selector('#side div[contenteditable="true"]', timeout=15000)

        search_sel = _SEARCH_BOX_SELECTOR
        await page.click(search_sel)
        await asyncio.sleep(0.3)
        # Limpar campo anterior com Ctrl+A + Delete
        await page.keyboard.press("Control+a")
        await page.keyboard.press("Delete")
        await page.keyboard.type(contato)
        await asyncio.sleep(1.5)

        # 2. Clicar no primeiro resultado
        try:
            await page.wait_for_selector("#pane-side span[title]", timeout=10000)
        except PWTimeout:
            return json.dumps({"ok": False, "error": f"Nenhum resultado encontrado para '{contato}'"}, ensure_ascii=False)

        elementos = await page.locator("#pane-side span[title]").all()
        alvo = None
        for el in elementos:
            nome = await el.get_attribute("title")
            if nome and contato.lower() == nome.lower():
                alvo = el
                break
        if not alvo:
            for el in elementos:
                nome = await el.get_attribute("title")
                if nome and contato.lower() in nome.lower():
                    alvo = el
                    break

        if not alvo:
            return json.dumps({"ok": False, "error": f"Contato '{contato}' nao encontrado na busca"}, ensure_ascii=False)

        await alvo.scroll_into_view_if_needed()
        await alvo.click()
        await asyncio.sleep(2)

        # 3. Ler mensagens do painel principal
        try:
            await page.wait_for_selector("#main", timeout=10000)
        except PWTimeout:
            return json.dumps({"ok": False, "error": "Painel principal nao carregou"}, ensure_ascii=False)

        rows = await page.locator('#main div[role="row"]').all()
        mensagens = []
        for row in rows[-(limite):]:
            try:
                texto = await row.inner_text()
                texto = texto.strip().replace("\n", " | ")
                if texto:
                    mensagens.append(texto)
            except Exception:
                continue

        print(f"[WHATSAPP LEITOR] {len(mensagens)} mensagens lidas de '{contato}'")

    if not mensagens:
        return json.dumps({"ok": True, "contato": contato, "mensagens": [], "aviso": "Nenhuma mensagem lida no painel"}, ensure_ascii=False)

    return json.dumps({"ok": True, "contato": contato, "mensagens": mensagens}, ensure_ascii=False)


def _ler_in_thread(contato: str, limite: int) -> str:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(ler_mensagens_whatsapp(contato, limite))
    finally:
        loop.close()


def _triagem_in_thread() -> str:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(triagem_notificacoes_whatsapp())
        return json.dumps(result, ensure_ascii=False)
    finally:
        loop.close()


class WhatsAppTool(MotorTool):
    """
    Ferramenta de mensagens WhatsApp via CDP (Edge externo).

    Aceita NUMERO (+5511...) ou NOME DO CONTATO (ex: 'Mae', 'Joao Silva').
    Auto-Launch: inicia o Edge automaticamente se necessario.
    """

    def __init__(self) -> None:
        super().__init__(
            metadata=ToolMetadata(
                name="whatsapp",
                description=(
                    "Envia mensagens de texto via WhatsApp Web. "
                    "Aceita numero de telefone (ex: +5511999998888) "
                    "OU nome do contato salvo no celular (ex: 'Mae', 'Joao'). "
                    "Use quando o usuario pedir para mandar mensagem via WhatsApp. "
                    "REGRA DE SINERGIA: Se o destinatario solicitado for um apelido "
                    "(ex: 'yngridola', 'amor', 'mae') ou voce nao tiver o nome completo, "
                    "VOCE DEVE PRIMEIRO chamar a ferramenta pesquisar_memoria para descobrir "
                    "o nome real da pessoa. NUNCA envie mensagem para um apelido sem antes checar a memoria."
                ),
                category="communication",
                parameters=[
                    ToolParameter(
                        name="acao",
                        type="string",
                        description="Acao: 'enviar_mensagem', 'criar_sessao', 'triagem' ou 'ler_mensagens'.",
                        required=True,
                        choices=["enviar_mensagem", "criar_sessao", "triagem", "ler_mensagens"],
                    ),
                    ToolParameter(
                        name="destinatario",
                        type="string",
                        description=(
                            "Numero de telefone (ex: +5511999998888) "
                            "OU nome exato do contato salvo no celular (ex: 'Mae', 'Pedro'). "
                            "Se for apelido, use pesquisar_memoria antes para descobrir o nome real."
                        ),
                        required=False,
                    ),
                    ToolParameter(
                        name="mensagem",
                        type="string",
                        description="Texto da mensagem a enviar.",
                        required=False,
                    ),
                    ToolParameter(
                        name="limite",
                        type="int",
                        description="Numero de mensagens a ler (apenas para acao=ler_mensagens). Padrao: 5.",
                        required=False,
                        default=5,
                    ),
                ],
                examples=[
                    "acao=enviar_mensagem, destinatario=+5511999998888, mensagem=Ola!",
                    "acao=enviar_mensagem, destinatario=Mae, mensagem=Oi mae!",
                    "acao=criar_sessao",
                ],
                security_level=SecurityLevel.MEDIUM,
                tags=["whatsapp", "messaging", "communication"],
            )
        )

    def validate_input(self, **kwargs: Any) -> bool:
        acao = str(kwargs.get("acao", "")).strip().lower()
        if acao not in {"enviar_mensagem", "criar_sessao", "triagem", "ler_mensagens"}:
            return False
        if acao == "enviar_mensagem":
            return (
                bool(str(kwargs.get("destinatario", "")).strip())
                and bool(str(kwargs.get("mensagem", "")).strip())
            )
        if acao == "ler_mensagens":
            return bool(str(kwargs.get("destinatario", "")).strip())
        return True

    async def execute(self, **kwargs: Any) -> str:
        acao = str(kwargs.get("acao", "")).strip().lower()

        if acao == "criar_sessao":
            return json.dumps(
                {
                    "ok": True,
                    "backend": "playwright-cdp",
                    "cdp_url": _CDP_URL,
                    "instrucoes": (
                        "Abra o Edge com: msedge.exe --remote-debugging-port=9222 "
                        "--user-data-dir=C:\\wa_bot_profile --no-first-run"
                    ),
                },
                ensure_ascii=False,
            )

        if acao == "enviar_mensagem":
            destinatario = str(kwargs.get("destinatario", "")).strip()
            mensagem = str(kwargs.get("mensagem", "")).strip()

            logger.info("[WHATSAPP] Enviando para '%s' via CDP...", destinatario)
            result = await asyncio.to_thread(_send_in_thread, destinatario, mensagem)
            logger.info("[WHATSAPP] Entregue para '%s'.", destinatario)
            return result

        if acao == "triagem":
            result = await asyncio.to_thread(_triagem_in_thread)
            return result

        if acao == "ler_mensagens":
            destinatario = str(kwargs.get("destinatario", "")).strip()
            limite = int(kwargs.get("limite", 5))
            logger.info("[WHATSAPP] Lendo %d mensagens de '%s'...", limite, destinatario)
            result = await asyncio.to_thread(_ler_in_thread, destinatario, limite)
            return result

        raise ValueError(f"Acao desconhecida: {acao}")
