"""
Media Tool - Controle REAL de mídia do sistema (qualquer player).

Mecanismo primário: API WinRT de sessões de mídia do Windows (SMTC) — a mesma
que alimenta o overlay de volume do sistema. Com ela a assistente:
  - VÊ o que está tocando (app + título + artista), mesmo que não foi ela
    que iniciou (Spotify, YouTube em qualquer navegador, Brave, VLC...);
  - pausa/retoma/pula DIRETO na sessão (sem simular tecla, sem toggle cego).

Fallback: tecla de mídia global (keybd_event) se o WinRT não estiver disponível.
Volume absoluto via WASAPI (pycaw); medidor de pico informa se há som saindo.
"""

import asyncio
import sys
from typing import Any, Dict, List, Optional

try:
    from ..tools.base import MotorTool, ToolMetadata, ToolParameter, SecurityLevel
    from .. import get_logger
except ImportError:
    from .base import MotorTool, ToolMetadata, ToolParameter, SecurityLevel
    from .. import get_logger

logger = get_logger(__name__)

# Virtual-key codes das teclas de mídia do Windows (fallback)
_VK_MEDIA_PLAY_PAUSE = 0xB3
_VK_MEDIA_NEXT = 0xB0
_VK_MEDIA_PREV = 0xB1
_VK_MEDIA_STOP = 0xB2
_VK_VOLUME_UP = 0xAF
_VK_VOLUME_DOWN = 0xAE
_VK_VOLUME_MUTE = 0xAD

_KEYEVENTF_EXTENDEDKEY = 0x0001
_KEYEVENTF_KEYUP = 0x0002

# GlobalSystemMediaTransportControlsSessionPlaybackStatus
_ST_PLAYING = 4
_ST_PAUSED = 5

_APPS_BONITOS = {
    "spotify": "Spotify", "brave": "Brave", "chrome": "Chrome", "msedge": "Edge",
    "firefox": "Firefox", "opera": "Opera", "vlc": "VLC", "wmplayer": "Media Player",
}


def _nome_app(aumid: str) -> str:
    base = (aumid or "").split("!")[0].split("_")[0].replace(".exe", "").lower()
    for chave, nome in _APPS_BONITOS.items():
        if chave in base:
            return nome
    return base.capitalize() or "player"


def _press_media_key(vk: int) -> None:
    """Fallback: tecla de mídia global (mesmo efeito do teclado físico)."""
    import ctypes

    user32 = ctypes.windll.user32
    user32.keybd_event(vk, 0, _KEYEVENTF_EXTENDEDKEY, 0)
    user32.keybd_event(vk, 0, _KEYEVENTF_EXTENDEDKEY | _KEYEVENTF_KEYUP, 0)


# ── WinRT SMTC: o caminho de verdade ─────────────────────────────────────────
async def _listar_sessoes() -> List[Dict[str, Any]]:
    """Sessões de mídia do sistema: [{app, titulo, artista, tocando, _session}]."""
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as _Manager,
    )

    mgr = await _Manager.request_async()
    out: List[Dict[str, Any]] = []
    for s in mgr.get_sessions():
        try:
            info = await s.try_get_media_properties_async()
            status = s.get_playback_info().playback_status
            out.append(
                {
                    "app": _nome_app(s.source_app_user_model_id),
                    "titulo": (info.title or "").strip(),
                    "artista": (info.artist or "").strip(),
                    "tocando": int(status) == _ST_PLAYING,
                    "pausado": int(status) == _ST_PAUSED,
                    "_session": s,
                }
            )
        except Exception:
            continue
    return out


def _descrever(s: Dict[str, Any]) -> str:
    titulo = s["titulo"] or "a mídia"
    artista = f" — {s['artista']}" if s["artista"] else ""
    return f"'{titulo}{artista}' no {s['app']}"


async def _smtc_acao(acao: str) -> Optional[str]:
    """
    Executa play/pause/next/previous/stop na sessão certa via SMTC.
    Retorna a frase de resultado, ou None se o WinRT não estiver disponível.
    """
    try:
        sessoes = await _listar_sessoes()
    except ImportError:
        return None
    except Exception as exc:
        logger.warning(f"[MEDIA] SMTC indisponível ({exc}); usando tecla global")
        return None

    tocando = [s for s in sessoes if s["tocando"]]
    pausadas = [s for s in sessoes if s["pausado"]]

    if acao in ("pause", "play_pause") and tocando:
        alvo = tocando[0]
        await alvo["_session"].try_pause_async()
        return f"Pausei {_descrever(alvo)}."
    if acao in ("play", "play_pause") and pausadas:
        alvo = pausadas[0]
        await alvo["_session"].try_play_async()
        return f"Voltei a tocar {_descrever(alvo)}."
    if acao == "next" and (tocando or pausadas):
        alvo = (tocando or pausadas)[0]
        await alvo["_session"].try_skip_next_async()
        return f"Pulei para a próxima no {alvo['app']}."
    if acao == "previous" and (tocando or pausadas):
        alvo = (tocando or pausadas)[0]
        await alvo["_session"].try_skip_previous_async()
        return f"Voltei uma faixa no {alvo['app']}."
    if acao == "stop" and (tocando or pausadas):
        alvo = (tocando or pausadas)[0]
        try:
            await alvo["_session"].try_stop_async()
        except Exception:
            await alvo["_session"].try_pause_async()
        return f"Parei {_descrever(alvo)}."

    # Sem sessão compatível — resposta verdadeira sobre o estado
    if acao == "pause":
        if pausadas:
            return f"Já está pausado: {_descrever(pausadas[0])}."
        return "Não achei nada tocando agora — nada pra pausar."
    if acao == "play":
        if tocando:
            return f"Já está tocando: {_descrever(tocando[0])}."
        return "Não achei nenhuma mídia pausada pra retomar."
    if acao == "play_pause":
        return "Não achei nenhuma sessão de mídia ativa agora."
    return f"Não achei mídia ativa para a ação '{acao}'."


def _get_endpoint_volume():
    """Interface WASAPI do volume mestre (pycaw). Levanta exceção se indisponível."""
    from pycaw.pycaw import AudioUtilities

    return AudioUtilities.GetSpeakers().EndpointVolume


def _audio_is_playing() -> Optional[bool]:
    """True se há som saindo agora; None se não foi possível medir."""
    try:
        import comtypes
        from pycaw.pycaw import AudioUtilities, IAudioMeterInformation

        device = AudioUtilities.GetSpeakers()._dev
        interface = device.Activate(
            IAudioMeterInformation._iid_, comtypes.CLSCTX_ALL, None
        )
        meter = interface.QueryInterface(IAudioMeterInformation)
        return meter.GetPeakValue() > 0.004
    except Exception:
        return None


def _com_call(fn, *args):
    """Roda função COM em thread própria com CoInitialize (exigência do WASAPI)."""
    import comtypes

    comtypes.CoInitialize()
    try:
        return fn(*args)
    finally:
        try:
            comtypes.CoUninitialize()
        except Exception:
            pass


def _set_volume_sync(valor: int) -> str:
    vol = _get_endpoint_volume()
    vol.SetMasterVolumeLevelScalar(max(0, min(100, valor)) / 100.0, None)
    return f"Volume do sistema ajustado para {valor}%."


def _step_volume_sync(direcao: str) -> str:
    vol = _get_endpoint_volume()
    atual = vol.GetMasterVolumeLevelScalar()
    novo = atual + 0.08 if direcao == "up" else atual - 0.08
    novo = max(0.0, min(1.0, novo))
    vol.SetMasterVolumeLevelScalar(novo, None)
    return f"Volume {'aumentado' if direcao == 'up' else 'reduzido'} para {round(novo * 100)}%."


def _mute_sync(mute: bool) -> str:
    vol = _get_endpoint_volume()
    vol.SetMute(1 if mute else 0, None)
    return "Som mutado." if mute else "Som restaurado."


class MediaTool(MotorTool):
    """Controla a mídia que estiver tocando no PC, de qualquer origem."""

    def __init__(self):
        super().__init__(
            metadata=ToolMetadata(
                name="controlar_midia",
                description=(
                    "Vê e controla QUALQUER mídia tocando no computador AGORA — Spotify, "
                    "YouTube em qualquer navegador (Brave/Chrome/Edge), VLC, etc. — mesmo "
                    "que a reprodução NÃO tenha sido iniciada por você. Use para pausar, "
                    "despausar/continuar, pular faixa, voltar faixa, parar, mutar ou mexer "
                    "no volume. Use acao=info para descobrir O QUE está tocando agora "
                    "(app, título, artista) antes de comentar ou decidir."
                ),
                category="media",
                parameters=[
                    ToolParameter(
                        name="acao",
                        type="string",
                        description=(
                            "Ação: info (lista o que está tocando), play_pause (pausa se "
                            "tocando, retoma se pausado), pause, play, next, previous, stop, "
                            "mute, unmute, volume_up, volume_down, volume_set"
                        ),
                        required=True,
                        choices=[
                            "info", "play", "pause", "play_pause", "next", "previous", "stop",
                            "mute", "unmute",
                            "volume_up", "volume_down", "volume_set",
                            "abrir_spotify", "abrir_youtube",
                        ],
                    ),
                    ToolParameter(
                        name="valor",
                        type="int",
                        description="Para volume_set: valor de 0-100",
                        required=False,
                        default=None,
                    ),
                ],
                examples=[
                    "acao=info  (o que está tocando agora?)",
                    "acao=pause  (pausa o que estiver tocando, ex: Spotify do usuário)",
                    "acao=next",
                    "acao=volume_set, valor=50",
                ],
                security_level=SecurityLevel.LOW,
                tags=["media", "audio", "spotify", "youtube", "pause", "volume"],
            )
        )

    def validate_input(self, **kwargs) -> bool:
        acao = str(kwargs.get("acao", "")).lower()
        return acao in {
            "info", "play", "pause", "play_pause", "next", "previous", "stop",
            "mute", "unmute", "volume_up", "volume_down", "volume_set",
            "abrir_spotify", "abrir_youtube",
        }

    async def execute(self, **kwargs) -> str:
        acao = str(kwargs.get("acao", "")).lower()
        valor = kwargs.get("valor", None)

        if sys.platform != "win32":
            return "[ERRO] Controle de mídia só está implementado no Windows."

        try:
            if acao == "info":
                return await self._info()
            if acao in ("play", "pause", "play_pause", "next", "previous", "stop"):
                return await self._transporte(acao)
            if acao == "mute":
                return await self._volume_op(_mute_sync, True)
            if acao == "unmute":
                return await self._volume_op(_mute_sync, False)
            if acao == "volume_up":
                return await self._volume_op(_step_volume_sync, "up")
            if acao == "volume_down":
                return await self._volume_op(_step_volume_sync, "down")
            if acao == "volume_set":
                if valor is None or not (0 <= int(valor) <= 100):
                    raise ValueError("Valor de volume deve estar entre 0 e 100")
                return await self._volume_op(_set_volume_sync, int(valor))
            if acao == "abrir_spotify":
                return await self._abrir_app("spotify")
            if acao == "abrir_youtube":
                return await self._abrir_app("youtube")
            raise ValueError(f"Ação desconhecida: {acao}")
        except Exception as e:
            raise RuntimeError(f"Erro ao controlar mídia: {str(e)}")

    async def _info(self) -> str:
        try:
            sessoes = await _listar_sessoes()
        except Exception as exc:
            return f"[ERRO] Não consegui ler as sessões de mídia: {exc}"
        if not sessoes:
            return "Nenhuma mídia aberta no momento."
        linhas = []
        for s in sessoes:
            estado = "TOCANDO" if s["tocando"] else ("pausado" if s["pausado"] else "parado")
            linhas.append(f"- {_descrever(s)} [{estado}]")
        return "Mídia no sistema agora:\n" + "\n".join(linhas)

    async def _transporte(self, acao: str) -> str:
        """Play/pause/next/previous/stop: SMTC primeiro, tecla global de reserva."""
        resultado = await _smtc_acao(acao)
        if resultado is not None:
            logger.info(f"[MEDIA] SMTC {acao}: {resultado}")
            return resultado

        # Fallback: tecla de mídia global + medidor pra resposta honesta
        tocando = await asyncio.to_thread(_com_call, _audio_is_playing)
        if acao == "pause" and tocando is False:
            return "Não tem nada tocando agora — nada pra pausar."
        if acao == "play" and tocando is True:
            return "Já tem som rolando."
        mapa = {
            "pause": _VK_MEDIA_PLAY_PAUSE, "play": _VK_MEDIA_PLAY_PAUSE,
            "play_pause": _VK_MEDIA_PLAY_PAUSE, "next": _VK_MEDIA_NEXT,
            "previous": _VK_MEDIA_PREV, "stop": _VK_MEDIA_STOP,
        }
        await asyncio.to_thread(_press_media_key, mapa[acao])
        logger.info(f"[MEDIA] tecla global enviada ({acao})")
        return {
            "pause": "Pausado.", "play": "Voltou a tocar.",
            "play_pause": "Alternei o play/pause.", "next": "Pulei para a próxima faixa.",
            "previous": "Voltei para a faixa anterior.", "stop": "Reprodução parada.",
        }[acao]

    async def _volume_op(self, fn, arg) -> str:
        try:
            return await asyncio.to_thread(_com_call, fn, arg)
        except Exception as e:
            # Fallback: teclas de volume (passos de ~2%)
            logger.warning(f"[MEDIA] WASAPI indisponível ({e}); usando teclas de volume")
            if fn is _step_volume_sync:
                vk = _VK_VOLUME_UP if arg == "up" else _VK_VOLUME_DOWN
                for _ in range(4):
                    await asyncio.to_thread(_press_media_key, vk)
                return f"Volume {'aumentado' if arg == 'up' else 'reduzido'}."
            if fn is _mute_sync:
                await asyncio.to_thread(_press_media_key, _VK_VOLUME_MUTE)
                return "Mute alternado."
            raise

    async def _abrir_app(self, app: str) -> str:
        try:
            if app == "spotify":
                if sys.platform == "win32":
                    await asyncio.create_subprocess_exec("explorer", "spotify://")
                else:
                    await asyncio.create_subprocess_exec("open", "-a", "Spotify")
                return "[OK] Abrindo Spotify..."
            if app == "youtube":
                import webbrowser
                webbrowser.open("https://www.youtube.com")
                return "[OK] Abrindo YouTube no navegador..."
            raise ValueError(f"Aplicativo desconhecido: {app}")
        except Exception as e:
            raise RuntimeError(f"Erro ao abrir {app}: {str(e)}")
