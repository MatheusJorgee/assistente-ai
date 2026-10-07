"""
Cache de disco para frases curtas de TTS (custo).

Frases que se repetem ("Um instante.", "Preciso da sua aprovação na tela.", as frases de espera
que a tela pré-busca a cada carregamento) não precisam ser sintetizadas de novo. Com ElevenLabs
cada síntese é um crédito pago; com edge-tts é tempo. Só entra no cache texto CURTO (frase que se
repete); frase longa é única e não vale o disco.

A chave inclui a identidade do provider primário: trocar de voz não devolve áudio da voz antiga.
Limite de arquivos e de bytes, com descarte dos menos usados.
"""

import hashlib
import os
import time
from pathlib import Path
from typing import Optional

TEXTO_MAX = 120
ARQUIVOS_MAX = 300
BYTES_MAX = 60 * 1024 * 1024
_DIR = Path(__file__).resolve().parents[2] / "data" / "tts_cache"


def chave(texto: str, voz: str) -> str:
    return hashlib.sha256(f"{voz}\x00{texto.strip()}".encode("utf-8")).hexdigest()[:40]


def cacheavel(texto: str) -> bool:
    return 0 < len((texto or "").strip()) <= TEXTO_MAX


def ler(texto: str, voz: str, pasta: Optional[Path] = None) -> Optional[bytes]:
    if not cacheavel(texto):
        return None
    arq = (pasta or _DIR) / f"{chave(texto, voz)}.bin"
    try:
        dados = arq.read_bytes()
        os.utime(arq)  # "usado agora": entra por último na fila de descarte
        return dados or None
    except OSError:
        return None


def gravar(texto: str, voz: str, audio: bytes, pasta: Optional[Path] = None) -> None:
    if not cacheavel(texto) or not audio:
        return
    pasta = pasta or _DIR
    try:
        pasta.mkdir(parents=True, exist_ok=True)
        arq = pasta / f"{chave(texto, voz)}.bin"
        tmp = arq.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_bytes(audio)
        os.replace(tmp, arq)
        _podar(pasta)
    except OSError:
        pass


def _podar(pasta: Path) -> None:
    arqs = sorted(pasta.glob("*.bin"), key=lambda p: p.stat().st_mtime)
    total = sum(p.stat().st_size for p in arqs)
    while arqs and (len(arqs) > ARQUIVOS_MAX or total > BYTES_MAX):
        velho = arqs.pop(0)
        total -= velho.stat().st_size
        velho.unlink(missing_ok=True)


async def sintetizar_com_cache(voice_manager, texto: str, pasta: Optional[Path] = None) -> bytes:
    """Fluxo do /tts: cache -> provider -> grava. `voice_manager` só precisa de
    `get_active_provider()` e `async synthesize(texto)`."""
    voz = voice_manager.get_active_provider()
    audio = ler(texto, voz, pasta)
    if audio is None:
        audio = await voice_manager.synthesize(texto)
        gravar(texto, voz, audio, pasta)
    return audio
