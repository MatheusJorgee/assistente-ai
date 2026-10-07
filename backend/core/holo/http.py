"""
Cliente HTTP dos hologramas: educado com as APIs abertas e seguro contra surpresas.

  - HOSTS EM ALLOWLIST: só fala com as fontes conhecidas (nem um redirect leva para outro host).
  - User-Agent IDENTIFICÁVEL (o Nominatim exige; sem isso o IP é banido). Contato em HOLO_CONTACT.
  - INTERVALO MÍNIMO por host (Nominatim: 1,1 s entre pedidos) e no máximo 4 pedidos simultâneos.
  - TETO DE 2 MB por resposta, timeouts curtos, 429 com uma espera e desistência.
  - CACHE em disco (backend/data/holo_cache/): resposta boa vale dias; falha vale minutos (não
    martela um servidor fora do ar). Escrita atômica; a pasta é podada quando passa de 50 MB.

Usa `requests` em thread (asyncio.to_thread): o aiohttp trava com alguns hosts no Windows.
`_requisitar` é o único ponto que toca a rede (é o que os testes substituem).
"""

import asyncio
import hashlib
import json
import os
import threading
import time
import weakref
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple
from urllib.parse import urlencode, urljoin, urlparse

import requests

try:
    from ..config import get_config
    from ..logger import get_logger
except ImportError:  # execução fora do pacote
    from core.config import get_config
    from core.logger import get_logger

logger = get_logger(__name__)

HOSTS_PERMITIDOS = frozenset({
    "nominatim.openstreetmap.org",
    "overpass-api.de", "overpass.kumi.systems",
    "pt.wikivoyage.org", "en.wikivoyage.org",
    "pt.wikipedia.org", "en.wikipedia.org",
    "api.open-meteo.com", "archive-api.open-meteo.com",
})

_INTERVALO_MINIMO = {"nominatim.openstreetmap.org": 1.1}
_MAX_BYTES = 2 * 1024 * 1024
_TIMEOUT = (4, 12)  # (conectar, ler) em segundos
_MAX_REDIRECTS = 2
_TTL_FALHA = 300.0
_DIR_CACHE = Path(__file__).resolve().parents[2] / "data" / "holo_cache"
_CACHE_MAX_BYTES = 50 * 1024 * 1024
_CONTATO_PADRAO = "https://github.com/MatheusJorgee/quinta-feira-ui"

_locks: Dict[str, threading.Lock] = {}
_ultimo: Dict[str, float] = {}
_locks_guarda = threading.Lock()
_escritas = 0
_semaforos: "weakref.WeakKeyDictionary[Any, asyncio.Semaphore]" = weakref.WeakKeyDictionary()


def _user_agent() -> str:
    contato = (getattr(get_config(), "HOLO_CONTACT", "") or "").strip() or _CONTATO_PADRAO
    return f"QuintaFeira/1.0 (assistente pessoal local; contato: {contato})"


def _host_ok(url: str) -> bool:
    try:
        p = urlparse(url)
    except Exception:
        return False
    return p.scheme == "https" and (p.hostname or "").lower() in HOSTS_PERMITIDOS


def _esperar_vez(host: str) -> None:
    """Respeita o intervalo mínimo entre pedidos ao mesmo host (bloqueia a thread)."""
    intervalo = _INTERVALO_MINIMO.get(host, 0.0)
    if intervalo <= 0:
        return
    with _locks_guarda:
        lock = _locks.setdefault(host, threading.Lock())
    with lock:
        falta = _ultimo.get(host, 0.0) + intervalo - time.monotonic()
        if falta > 0:
            time.sleep(falta)
        _ultimo[host] = time.monotonic()


def _requisitar(
    metodo: str, url: str, params: Optional[Mapping[str, Any]], dados: Optional[Mapping[str, Any]],
) -> Optional[Tuple[int, bytes]]:
    """ÚNICO ponto que toca a rede. Devolve (status, corpo) ou None. Redirects só dentro da allowlist."""
    atual, redirects = url, 0
    headers = {"User-Agent": _user_agent(), "Accept": "application/json"}
    while True:
        host = (urlparse(atual).hostname or "").lower()
        _esperar_vez(host)
        try:
            with requests.request(
                metodo, atual, params=params if redirects == 0 else None,
                data=dados if redirects == 0 else None, headers=headers,
                timeout=_TIMEOUT, allow_redirects=False, stream=True,
            ) as r:
                if r.status_code in (301, 302, 303, 307, 308) and redirects < _MAX_REDIRECTS:
                    destino = urljoin(atual, r.headers.get("Location", ""))
                    if not _host_ok(destino):
                        logger.debug(f"[HOLO] redirect para host fora da allowlist bloqueado: {destino[:80]}")
                        return None
                    atual, redirects = destino, redirects + 1
                    continue
                corpo = bytearray()
                for pedaco in r.iter_content(chunk_size=65536):
                    corpo += pedaco
                    if len(corpo) > _MAX_BYTES:
                        logger.debug("[HOLO] resposta acima do teto de 2 MB; descartada")
                        return None
                return r.status_code, bytes(corpo)
        except requests.RequestException as exc:
            logger.debug(f"[HOLO] falha de rede em {host}: {type(exc).__name__}")
            return None


# ----------------------------------------------------------------------------- cache

def _chave(metodo: str, url: str, params: Optional[Mapping[str, Any]], dados: Optional[Mapping[str, Any]]) -> str:
    base = json.dumps([metodo, url, sorted((params or {}).items()), sorted((dados or {}).items())],
                      ensure_ascii=False, default=str)
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:40]


def _ler_cache(chave: str) -> Tuple[bool, Any]:
    """(achou, dado). `dado` None com achou=True = falha recente em cache."""
    arq = _DIR_CACHE / f"{chave}.json"
    try:
        reg = json.loads(arq.read_text(encoding="utf-8"))
        if time.time() - float(reg["ts"]) <= float(reg["ttl"]):
            return True, (reg["data"] if reg.get("ok") else None)
    except Exception:
        pass
    return False, None


def _gravar_cache(chave: str, dado: Any, ok: bool, ttl: float) -> None:
    global _escritas
    try:
        _DIR_CACHE.mkdir(parents=True, exist_ok=True)
        tmp = _DIR_CACHE / f"{chave}.tmp{os.getpid()}"
        tmp.write_text(json.dumps({"ts": time.time(), "ttl": ttl, "ok": ok, "data": dado}, ensure_ascii=False),
                       encoding="utf-8")
        os.replace(tmp, _DIR_CACHE / f"{chave}.json")
        _escritas += 1
        if _escritas % 25 == 0:
            _podar_cache()
    except Exception as exc:
        logger.debug(f"[HOLO] cache não gravado: {exc}")


def _podar_cache() -> None:
    """Passou de 50 MB: apaga os arquivos mais antigos até voltar a ~70% do teto."""
    try:
        arquivos = sorted(_DIR_CACHE.glob("*.json"), key=lambda p: p.stat().st_mtime)
        total = sum(p.stat().st_size for p in arquivos)
        for p in arquivos:
            if total <= _CACHE_MAX_BYTES * 0.7:
                break
            total -= p.stat().st_size
            p.unlink(missing_ok=True)
    except Exception:
        pass


# ----------------------------------------------------------------------------- API

def get_json(
    url: str, *, params: Optional[Mapping[str, Any]] = None, dados: Optional[Mapping[str, Any]] = None,
    metodo: str = "GET", ttl: float = 86400.0,
) -> Optional[Any]:
    """JSON da resposta, ou None (host fora da allowlist, erro, 4xx/5xx, grande demais, não-JSON)."""
    if not _host_ok(url):
        logger.debug(f"[HOLO] host fora da allowlist: {url[:80]}")
        return None
    chave = _chave(metodo, url, params, dados)
    achou, dado = _ler_cache(chave)
    if achou:
        return dado

    resp = _requisitar(metodo, url, params, dados)
    if resp is not None and resp[0] == 429:  # pediram calma: uma espera e desiste
        time.sleep(2.0)
        resp = _requisitar(metodo, url, params, dados)
    if resp is None or resp[0] != 200:
        _gravar_cache(chave, None, False, _TTL_FALHA)
        return None
    try:
        dado = json.loads(resp[1].decode("utf-8", errors="replace"))
    except ValueError:
        _gravar_cache(chave, None, False, _TTL_FALHA)
        return None
    _gravar_cache(chave, dado, True, ttl)
    return dado


def _semaforo() -> asyncio.Semaphore:
    """No máximo 4 pedidos simultâneos por loop de eventos."""
    loop = asyncio.get_running_loop()
    sem = _semaforos.get(loop)
    if sem is None:
        sem = asyncio.Semaphore(4)
        _semaforos[loop] = sem
    return sem


async def aget_json(url: str, **kw: Any) -> Optional[Any]:
    """Versão assíncrona (roda o `requests` numa thread, com teto de 4 pedidos simultâneos)."""
    async with _semaforo():
        return await asyncio.to_thread(get_json, url, **kw)


def url_com_params(url: str, params: Mapping[str, Any]) -> str:
    """Só para montar links (nunca para requisições): URL + querystring codificada."""
    return f"{url}?{urlencode(params)}"
