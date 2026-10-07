"""
TelegramBridge — a Quinta-Feira no celular do Matheus.

Long-polling na Bot API do Telegram (sem dependência nova: usa requests em
thread). Funciona nos dois sentidos:

  ENTRADA: Matheus manda mensagem no bot → vai pro brain (mesma persona,
           mesma memória, mesmas ferramentas) → resposta volta no Telegram.
  SAÍDA:   avisos proativos são espelhados pro Telegram quando ele está
           longe do PC (via ProactiveMonitor → send()).

Setup (uma vez): criar bot no @BotFather, colocar TELEGRAM_BOT_TOKEN no .env.
O DONO só existe se VOCÊ o configurar (TELEGRAM_CHAT_ID no .env, ou o arquivo
.runtime/telegram_owner.txt de uma configuração antiga). Antes, o primeiro humano
que escrevesse para o bot virava dono, e o dono tem ações críticas SEM cartão de
aprovação: quem descobrisse o nome do bot ganhava terminal e arquivos. Agora um
chat desconhecido NUNCA chega ao cérebro: no máximo recebe UMA resposta com o seu
chat_id, para você copiar para o .env. Só conversa privada conta (grupo não).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Optional

from ..policy.approvals import ORIGEM_TELEGRAM, origem_atual

try:
    import requests
except Exception:
    requests = None

try:
    from .. import get_logger
except ImportError:
    from .. import get_logger

logger = get_logger(__name__)

_OWNER_FILE = Path(__file__).resolve().parent.parent.parent / ".runtime" / "telegram_owner.txt"


class TelegramBridge:
    def __init__(self, *, brain: Any, config: Any) -> None:
        self._brain = brain
        self._token = getattr(config, "TELEGRAM_BOT_TOKEN", "") or ""
        self._chat_id = str(getattr(config, "TELEGRAM_CHAT_ID", "") or "").strip()
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None
        self._offset = 0
        self._avisados: set = set()   # chats desconhecidos que já receberam a instrução (uma vez só)

        if not self._chat_id and _OWNER_FILE.exists():
            try:
                self._chat_id = _OWNER_FILE.read_text(encoding="utf-8").strip()
            except Exception:
                pass

    @property
    def is_available(self) -> bool:
        """True se dá pra ENVIAR mensagem proativa (token + dono conhecido)."""
        return bool(self._token and self._chat_id and requests)

    @property
    def is_running(self) -> bool:
        return self._running

    # ── ciclo de vida ────────────────────────────────────────────────────────
    async def start(self) -> None:
        if self._running:
            return
        if not self._token:
            logger.info("[TELEGRAM] Sem TELEGRAM_BOT_TOKEN no .env — ponte desligada")
            return
        if not requests:
            logger.warning("[TELEGRAM] biblioteca requests indisponível — ponte desligada")
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop(), name="telegram_bridge")
        logger.info("[TELEGRAM] Ponte ativa (long-polling)")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[TELEGRAM] Ponte encerrada")

    # ── API Telegram (requests em thread; long-poll de 50s) ─────────────────
    def _api(self, method: str, timeout: float = 15.0, **params: Any) -> dict:
        url = f"https://api.telegram.org/bot{self._token}/{method}"
        r = requests.post(url, json=params, timeout=timeout)
        return r.json() if r.ok else {"ok": False, "status": r.status_code}

    async def _poll_loop(self) -> None:
        backoff = 5
        while self._running:
            try:
                data = await asyncio.to_thread(
                    self._api, "getUpdates", 60.0,
                    offset=self._offset, timeout=50, allowed_updates=["message"],
                )
                backoff = 5
                for update in data.get("result", []) or []:
                    self._offset = max(self._offset, int(update.get("update_id", 0)) + 1)
                    await self._handle_update(update)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.debug(f"[TELEGRAM] poll falhou ({exc}); tentando de novo em {backoff}s")
                await asyncio.sleep(backoff)
                backoff = min(120, backoff * 2)

    async def _handle_update(self, update: dict) -> None:
        msg = update.get("message") or {}
        chat_id = str((msg.get("chat") or {}).get("id", "")).strip()
        texto = (msg.get("text") or "").strip()
        if not chat_id or not texto:
            return

        # Só conversa PRIVADA conta: em grupo, qualquer membro escreveria "como o dono".
        if (msg.get("chat") or {}).get("type") != "private":
            logger.warning(f"[TELEGRAM] Mensagem fora de conversa privada ({chat_id}) ignorada")
            return

        # Trava de dono: só o chat que VOCÊ configurou. Desconhecido nunca chega ao cérebro.
        if chat_id != self._chat_id:
            logger.warning(f"[TELEGRAM] Mensagem de chat não autorizado ({chat_id}) ignorada")
            if chat_id not in self._avisados and len(self._avisados) < 20:
                self._avisados.add(chat_id)
                try:
                    await asyncio.to_thread(
                        self._api, "sendMessage", 15.0, chat_id=chat_id,
                        text=(f"Não estou autorizada a conversar com este chat. Se é você, o seu chat_id é {chat_id}: "
                              "coloque TELEGRAM_CHAT_ID=" + chat_id + " no .env da Quinta e reinicie."),
                    )
                except Exception:
                    pass
            return

        logger.info(f"[TELEGRAM] Matheus (celular): {texto[:60]}")
        # Origem = dono autenticado por chat_id: ações críticas dele NÃO pedem aprovação na tela
        # (ele está longe do PC). Fica registrado na auditoria (.runtime/audit/tool_risk.jsonl).
        _origem_token = origem_atual.set(ORIGEM_TELEGRAM)
        try:
            resposta = await asyncio.wait_for(
                self._brain.ask(
                    texto,
                    hidden_context=(
                        "[CANAL: TELEGRAM] O Matheus está falando com você pelo CELULAR, "
                        "longe do computador. Responda curto e direto, como mensagem de "
                        "chat — sem markdown pesado. Ações no PC dele continuam disponíveis "
                        "pelas suas ferramentas (o computador está ligado com você dentro)."
                    ),
                ),
                timeout=60.0,
            )
            texto_resposta = (resposta.text or "").strip() or "Fiquei sem palavras — tenta de novo."
        except Exception as exc:
            logger.warning(f"[TELEGRAM] brain falhou: {exc}")
            texto_resposta = "Tive um engasgo aqui pra processar isso. Manda de novo?"
        finally:
            origem_atual.reset(_origem_token)

        await self.send(texto_resposta)

    async def send(self, texto: str) -> bool:
        """Envia mensagem proativa pro dono (usado também pelo ProactiveMonitor)."""
        if not self.is_available or not texto:
            return False
        try:
            data = await asyncio.to_thread(
                self._api, "sendMessage", 15.0, chat_id=self._chat_id, text=texto[:4000]
            )
            return bool(data.get("ok"))
        except Exception as exc:
            logger.debug(f"[TELEGRAM] send falhou: {exc}")
            return False
