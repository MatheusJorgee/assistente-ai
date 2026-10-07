"""
ContextSensor — os "sentidos" da Quinta-Feira.

Monta uma fotografia do momento presente: hora e dia da semana, app em primeiro
plano, jogo rodando, ociosidade real do teclado/mouse, bateria, CPU/RAM, clima
e tempo de sessão. Essa fotografia alimenta o cérebro nos avisos proativos,
nas observações espontâneas e no aprendizado de hábitos — é o que permite que
ela fale do que está acontecendo AGORA, e não de um template.
"""

from __future__ import annotations

import asyncio
import ctypes
import sys
import time
from datetime import datetime
from typing import Any, Dict, Optional

try:
    import psutil
except Exception:
    psutil = None

try:
    from .. import get_logger
except ImportError:
    from .. import get_logger

logger = get_logger(__name__)

_DIAS_SEMANA = [
    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
    "sexta-feira", "sábado", "domingo",
]

# Apps que dizem algo sobre o que o Matheus está fazendo (nome de processo → rótulo)
_APPS_CONHECIDOS = {
    "code": "VS Code", "devenv": "Visual Studio", "pycharm": "PyCharm",
    "idea": "IntelliJ", "windowsterminal": "Terminal", "powershell": "PowerShell",
    "chrome": "Chrome", "msedge": "Edge", "firefox": "Firefox", "opera": "Opera",
    "spotify": "Spotify", "discord": "Discord", "steam": "Steam",
    "obsidian": "Obsidian", "notion": "Notion", "obs64": "OBS",
    "photoshop": "Photoshop", "premiere": "Premiere", "blender": "Blender",
    "excel": "Excel", "winword": "Word", "powerpnt": "PowerPoint",
    "telegram": "Telegram", "whatsapp": "WhatsApp",
    "vlc": "VLC", "deadbydaylight": "Dead by Daylight",
    "valorant": "Valorant", "leagueoflegends": "League of Legends",
    "cs2": "CS2", "minecraft": "Minecraft", "fortnite": "Fortnite",
    "robloxplayerbeta": "Roblox", "gta5": "GTA V", "eldenring": "Elden Ring",
}

_GAME_PROCS = {
    "deadbydaylight", "dbd", "leagueoflegends", "valorant", "minecraft",
    "cs2", "csgo", "robloxplayerbeta", "fortnite", "overwatch", "gta5",
    "gtav", "cyberpunk2077", "eldenring", "darksouls",
}


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def seconds_idle() -> Optional[float]:
    """Segundos desde o último input real de teclado/mouse (Windows)."""
    if sys.platform != "win32":
        return None
    try:
        lii = _LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(_LASTINPUTINFO)
        if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
            millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
            return max(0.0, millis / 1000.0)
    except Exception:
        pass
    return None


class _RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


def foreground_app() -> Dict[str, Any]:
    """App em primeiro plano: processo + título + se está em TELA CHEIA (Windows)."""
    out: Dict[str, Any] = {"processo": "", "titulo": "", "fullscreen": False}
    if sys.platform != "win32":
        return out
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return out
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            out["titulo"] = buf.value
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if psutil and pid.value:
            try:
                out["processo"] = psutil.Process(pid.value).name().lower().replace(".exe", "")
            except Exception:
                pass
        # Tela cheia: janela em foco cobre o monitor inteiro (e não é o desktop/shell)
        try:
            rect = _RECT()
            if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                screen_w = user32.GetSystemMetrics(0)
                screen_h = user32.GetSystemMetrics(1)
                cobre = (rect.right - rect.left) >= screen_w and (rect.bottom - rect.top) >= screen_h
                shell = out["processo"] in ("explorer", "", "shellexperiencehost", "searchhost")
                out["fullscreen"] = bool(cobre and not shell)
        except Exception:
            pass
    except Exception:
        pass
    return out


class ContextSensor:
    """Coleta a fotografia do momento. Clima é cacheado (30 min) pra não custar API."""

    def __init__(self, config: Any) -> None:
        self._config = config
        self._weather_cache: Optional[Dict[str, Any]] = None
        self._weather_ts = 0.0
        self._session_start = time.time()

    # ── coleta síncrona (roda em thread) ─────────────────────────────────────
    def _collect_sync(self) -> Dict[str, Any]:
        agora = datetime.now()
        snap: Dict[str, Any] = {
            "hora": agora.strftime("%H:%M"),
            "dia_semana": _DIAS_SEMANA[agora.weekday()],
            "data": agora.strftime("%d/%m/%Y"),
            "uptime_sessao_min": int((time.time() - self._session_start) / 60),
            "ocioso_seg": seconds_idle(),
        }

        fg = foreground_app()
        snap["app_em_foco"] = _APPS_CONHECIDOS.get(fg["processo"], fg["processo"]) or ""
        snap["janela_em_foco"] = fg["titulo"][:120]
        snap["fullscreen"] = bool(fg.get("fullscreen"))
        # Pista de chamada/reunião em andamento (Discord, Meet, Zoom, Teams)
        titulo_low = (fg.get("titulo") or "").lower()
        snap["em_chamada"] = any(
            t in titulo_low for t in ("meet.google", "zoom", "microsoft teams", "- discord")
        ) and fg.get("processo") in ("discord", "zoom", "teams", "msedge", "chrome", "brave")

        apps_abertos = set()
        jogo = ""
        if psutil:
            try:
                for p in psutil.process_iter(["name"]):
                    n = (p.info.get("name") or "").lower().replace(".exe", "")
                    if n in _APPS_CONHECIDOS:
                        apps_abertos.add(_APPS_CONHECIDOS[n])
                    if any(g in n for g in _GAME_PROCS):
                        jogo = _APPS_CONHECIDOS.get(n, n)
            except Exception:
                pass
            try:
                snap["cpu_pct"] = int(psutil.cpu_percent())
                snap["ram_pct"] = int(psutil.virtual_memory().percent)
            except Exception:
                pass
            try:
                bat = psutil.sensors_battery()
                if bat is not None:
                    snap["bateria_pct"] = int(bat.percent)
                    snap["na_tomada"] = bool(bat.power_plugged)
            except Exception:
                pass

        snap["apps_abertos"] = sorted(apps_abertos)[:10]
        snap["jogo_rodando"] = jogo
        return snap

    async def snapshot(self, include_weather: bool = True) -> Dict[str, Any]:
        snap = await asyncio.to_thread(self._collect_sync)
        if include_weather:
            clima = await self._weather()
            if clima:
                snap["clima"] = {
                    "descricao": clima.get("descricao", ""),
                    "temp": clima.get("temp"),
                    "cidade": clima.get("cidade", ""),
                }
        return snap

    async def _weather(self) -> Optional[Dict[str, Any]]:
        key = getattr(self._config, "OPENWEATHER_API_KEY", "")
        if not key:
            return None
        if self._weather_cache and (time.time() - self._weather_ts) < 1800:
            return self._weather_cache
        try:
            from ..briefing.weather import get_weather
            clima = await get_weather(self._config.BRIEFING_CITY, key)
            if clima:
                self._weather_cache = clima
                self._weather_ts = time.time()
            return clima
        except Exception as exc:
            logger.debug(f"[SENSOR] clima indisponível: {exc}")
            return None

    @staticmethod
    def to_prompt(snap: Dict[str, Any]) -> str:
        """Converte a fotografia em linhas legíveis pro LLM."""
        linhas = [f"Agora: {snap.get('dia_semana')}, {snap.get('data')}, {snap.get('hora')}."]

        ocioso = snap.get("ocioso_seg")
        if ocioso is not None:
            if ocioso < 120:
                linhas.append("O Matheus está ATIVO no computador neste momento.")
            else:
                linhas.append(f"O Matheus está sem mexer no PC há {int(ocioso / 60)} min.")

        if snap.get("jogo_rodando"):
            linhas.append(f"Jogo rodando: {snap['jogo_rodando']}.")
        if snap.get("app_em_foco"):
            foco = snap["app_em_foco"]
            titulo = snap.get("janela_em_foco") or ""
            linhas.append(f"App em primeiro plano: {foco}" + (f" ({titulo})" if titulo else "") + ".")
        if snap.get("apps_abertos"):
            linhas.append("Apps abertos: " + ", ".join(snap["apps_abertos"]) + ".")

        if "bateria_pct" in snap:
            tomada = "na tomada" if snap.get("na_tomada") else "NA BATERIA (sem carregador)"
            linhas.append(f"Bateria: {snap['bateria_pct']}%, {tomada}.")
        if "cpu_pct" in snap:
            linhas.append(f"CPU {snap['cpu_pct']}% | RAM {snap.get('ram_pct', '?')}%.")

        clima = snap.get("clima")
        if clima:
            linhas.append(
                f"Clima em {clima.get('cidade', '')}: {clima.get('descricao', '')}, {clima.get('temp', '?')}°C."
            )

        up = snap.get("uptime_sessao_min", 0)
        if up >= 60:
            linhas.append(f"Sessão ligada há {up // 60}h{up % 60:02d}min.")
        return "\n".join(linhas)
