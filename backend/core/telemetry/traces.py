"""
Traces por etapa (B11): onde o tempo da resposta é gasto.

Por pedido: recebido -> primeira ferramenta -> primeiro texto -> resposta final (servidor) e
primeiro áudio tocando (tela, via `voice_trace`). Grava JSONL por dia em data/traces/ (14 dias) e
`resumo()` devolve p50/p95 por etapa. Local, sem LLM, custo zero.
"""

import json
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

_DIR = Path(__file__).resolve().parents[2] / "data" / "traces"
RETENCAO_DIAS = 14
_lock = threading.Lock()


class Trace:
    def __init__(self, request_id: str, pasta: Optional[Path] = None) -> None:
        self.request_id = str(request_id)
        self._t0 = time.perf_counter()
        self._marcas: Dict[str, float] = {}
        self._tools: List[str] = []
        self._pasta = pasta

    def marca(self, nome: str) -> None:
        """Marca a PRIMEIRA vez que a etapa acontece (as seguintes são ignoradas)."""
        self._marcas.setdefault(nome, time.perf_counter())

    def ferramenta(self, nome: str) -> None:
        self.marca("primeira_ferramenta")
        if nome and nome not in self._tools:
            self._tools.append(nome)

    def etapas_ms(self) -> Dict[str, int]:
        return {k: int((v - self._t0) * 1000) for k, v in self._marcas.items()}

    def gravar(self, ok: bool = True) -> None:
        _escrever({
            "tipo": "servidor", "ts": datetime.utcnow().isoformat() + "Z", "request_id": self.request_id,
            "ok": ok, "total_ms": int((time.perf_counter() - self._t0) * 1000),
            "etapas_ms": self.etapas_ms(), "tools": self._tools,
        }, self._pasta)


def registrar_cliente(request_id: str, dados: Dict[str, Any], pasta: Optional[Path] = None) -> None:
    """Etapas medidas na tela (ex.: primeiro áudio). Só números, e só os campos conhecidos."""
    permitidos = ("primeiro_audio_ms",)
    limpo = {k: int(dados[k]) for k in permitidos if isinstance(dados.get(k), (int, float)) and 0 <= dados[k] < 600000}
    if limpo:
        _escrever({"tipo": "cliente", "ts": datetime.utcnow().isoformat() + "Z",
                   "request_id": str(request_id)[:64], **limpo}, pasta)


def _escrever(registro: Dict[str, Any], pasta: Optional[Path]) -> None:
    pasta = pasta or _DIR
    try:
        with _lock:
            pasta.mkdir(parents=True, exist_ok=True)
            with (pasta / f"{date.today().isoformat()}.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(registro, ensure_ascii=False) + "\n")
            _expurgar(pasta)
    except OSError:
        pass  # telemetria nunca quebra o fluxo


def _expurgar(pasta: Path) -> None:
    limite = date.today() - timedelta(days=RETENCAO_DIAS)
    for arq in pasta.glob("*.jsonl"):
        try:
            if date.fromisoformat(arq.stem) < limite:
                arq.unlink(missing_ok=True)
        except ValueError:
            continue


def _percentil(valores: List[int], p: float) -> int:
    if not valores:
        return 0
    v = sorted(valores)
    return v[min(len(v) - 1, int(round(p * (len(v) - 1))))]


def resumo(pasta: Optional[Path] = None, ultimos: int = 200) -> Dict[str, Any]:
    """p50/p95 por etapa dos últimos `ultimos` pedidos."""
    pasta = pasta or _DIR
    linhas: List[Dict[str, Any]] = []
    for arq in sorted(pasta.glob("*.jsonl"))[-3:]:
        for bruto in arq.read_text(encoding="utf-8").splitlines():
            try:
                linhas.append(json.loads(bruto))
            except ValueError:
                continue
    servidor = [l for l in linhas if l.get("tipo") == "servidor"][-ultimos:]
    cliente = [l for l in linhas if l.get("tipo") == "cliente"]
    etapas: Dict[str, List[int]] = {"total": [t["total_ms"] for t in servidor]}
    for t in servidor:
        for nome, ms in (t.get("etapas_ms") or {}).items():
            etapas.setdefault(nome, []).append(ms)
    etapas["primeiro_audio"] = [c["primeiro_audio_ms"] for c in cliente if "primeiro_audio_ms" in c][-ultimos:]
    return {
        "pedidos": len(servidor),
        "etapas": {k: {"n": len(v), "p50_ms": _percentil(v, 0.5), "p95_ms": _percentil(v, 0.95)} for k, v in etapas.items() if v},
    }
