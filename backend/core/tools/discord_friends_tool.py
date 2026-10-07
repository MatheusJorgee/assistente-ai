"""
DiscordFriendsTool — quem está online pra chamar pra jogar.

LIMITE REAL do Discord: a API NÃO expõe a presença dos seus AMIGOS a bots. O
único caminho é colocar um bot num SERVIDOR que você compartilha com a galera
(ex: "BAR DO PRADU"), com a "Presence Intent" ligada — aí o bot vê quais MEMBROS
daquele servidor estão online. Requer setup do usuário:
  1. Criar um bot em discord.com/developers, ligar Presence + Server Members Intent
  2. Adicionar o bot ao servidor da galera
  3. DISCORD_BOT_TOKEN e DISCORD_GUILD_ID no .env

Sem isso, a tool explica o que falta (não finge que funciona).
"""

from __future__ import annotations

import asyncio
from typing import Any, List

try:
    from .base import MotorTool, SecurityLevel, ToolMetadata, ToolParameter
    from .. import get_logger, get_config
except ImportError:
    from .base import MotorTool, SecurityLevel, ToolMetadata, ToolParameter
    from .. import get_logger, get_config

logger = get_logger(__name__)


def _online_members_sync(token: str, guild_id: int) -> List[str]:
    """Conexão curta ao gateway pra fotografar membros online do servidor."""
    import discord  # lazy: só importa se a lib existir

    intents = discord.Intents.none()
    intents.guilds = True
    intents.members = True
    intents.presences = True

    online: List[str] = []
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        try:
            guild = client.get_guild(guild_id) or await client.fetch_guild(guild_id)
            membros = guild.members if guild else []
            for m in membros:
                if m.bot:
                    continue
                status = str(getattr(m, "status", "offline"))
                if status in ("online", "idle", "dnd"):
                    rotulo = {"online": "online", "idle": "ausente", "dnd": "não perturbe"}.get(status, status)
                    online.append(f"{m.display_name} ({rotulo})")
        except Exception as exc:
            logger.debug(f"[DISCORD] coleta de presença falhou: {exc}")
        finally:
            await client.close()

    try:
        client.run(token, log_handler=None)
    except Exception as exc:
        logger.debug(f"[DISCORD] gateway falhou: {exc}")
    return online


class DiscordFriendsTool(MotorTool):
    def __init__(self) -> None:
        super().__init__(
            metadata=ToolMetadata(
                name="discord_amigos",
                description=(
                    "Mostra quem da galera está ONLINE no Discord pra chamar pra jogar. "
                    "Funciona via um bot num servidor compartilhado (precisa de setup do "
                    "Matheus). Use quando ele perguntar quem está online / com quem dá pra jogar."
                ),
                category="communication",
                parameters=[
                    ToolParameter(name="acao", type="string", description="Apenas 'online'.",
                                  required=False, default="online", choices=["online"]),
                ],
                examples=["acao=online"],
                security_level=SecurityLevel.LOW,
                tags=["discord", "amigos", "online", "jogar"],
            )
        )

    def validate_input(self, **kwargs: Any) -> bool:
        return True

    async def execute(self, **kwargs: Any) -> str:
        import json
        cfg = get_config()
        token = getattr(cfg, "DISCORD_BOT_TOKEN", "")
        guild = getattr(cfg, "DISCORD_GUILD_ID", "")
        if not token or not guild:
            return json.dumps({
                "ok": False, "configurar": True,
                "msg": ("Pra eu ver quem tá online preciso de um bot num servidor que você "
                        "compartilha com a galera. Setup: crie um bot em discord.com/developers "
                        "(ligue 'Presence' e 'Server Members' Intent), adicione ao servidor, e "
                        "ponha DISCORD_BOT_TOKEN e DISCORD_GUILD_ID no .env. O Discord não deixa "
                        "ver a lista de amigos direto — só membros de um servidor."),
            }, ensure_ascii=False)
        try:
            import importlib.util
            if not importlib.util.find_spec("discord"):
                return json.dumps({"ok": False, "msg": "Falta a lib: pip install discord.py"}, ensure_ascii=False)
            online = await asyncio.to_thread(_online_members_sync, token, int(guild))
            if not online:
                return json.dumps({"ok": True, "online": [], "msg": "Ninguém da galera online agora no servidor."}, ensure_ascii=False)
            return json.dumps({"ok": True, "online": online,
                               "msg": f"Online agora: {', '.join(online[:15])}."}, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"ok": False, "msg": f"Falha ao checar Discord: {str(exc)[:80]}"}, ensure_ascii=False)
