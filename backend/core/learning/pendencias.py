"""
Pendências: o que o Matheus deixou em aberto e a Quinta acompanha por conta própria.

Sem isso ela é reativa: você comentou a viagem, o projeto travado, a decisão que ia tomar... e nunca mais
volta ao assunto. Aqui há uma lista viva:

  - NASCE na reflexão diária (que já roda: o modelo devolve `pendencias` no mesmo JSON, sem chamada extra)
    ou quando você pede ("anota como pendência...");
  - é RETOMADA no máximo 1 vez por dia, com uma frase fixa (sem LLM), e no máximo 3 toques por item:
    sem resposta, ela arquiva sozinha ("dispensada por falta de resposta"): não insiste;
  - você resolve ou dispensa quando quiser (tela, voz ou tool).

Local, persistido, com tetos (10 abertas). Só vem de conversa DIRETA com você (a reflexão já descarta
texto de terceiros). Zero chamadas de modelo aqui.
"""

import json
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

ESTADOS = ("aberta", "resolvida", "dispensada")
MAX_ABERTAS = 10
MAX_TOQUES = 3
INTERVALO_TOQUE_S = 2 * 86400.0       # mesma pendência: no mínimo 2 dias entre toques
INTERVALO_DIA_S = 24 * 3600.0         # no máximo 1 retomada por dia (de qualquer pendência)
_DIR = Path(__file__).resolve().parents[2] / ".runtime"
_STOP = {"a", "o", "as", "os", "de", "da", "do", "das", "dos", "e", "em", "no", "na", "um", "uma", "que", "pra", "para", "com", "por", "se", "eu", "ele", "vou", "ver"}


def _limpo(t: Any, n: int) -> str:
    from .gaps import mascarar
    return mascarar(str(t or ""), n)


def _tokens(t: str) -> set:
    return {w for w in re.findall(r"[a-zà-ú0-9]+", t.lower()) if w not in _STOP and len(w) > 2}


class Pendencias:
    def __init__(self, arquivo: Optional[Path] = None) -> None:
        self._arq = Path(arquivo) if arquivo else _DIR / "pendencias.json"
        self._lock = threading.Lock()

    def _ler(self) -> List[Dict[str, Any]]:
        try:
            return list(json.loads(self._arq.read_text(encoding="utf-8")).get("itens", []))
        except Exception:
            return []

    def _gravar(self, itens: List[Dict[str, Any]]) -> None:
        self._arq.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._arq.with_suffix(".tmp")
        tmp.write_text(json.dumps({"itens": itens}, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self._arq)

    # ------------------------------------------------------------------ criar

    def adicionar(self, texto: str, proximo_passo: str = "", origem: str = "reflexao", agora: Optional[float] = None) -> Optional[str]:
        """Cria (ou ignora se já existe algo parecido). Devolve o id ou None."""
        texto, passo = _limpo(texto, 140), _limpo(proximo_passo, 120)
        if len(texto) < 8:
            return None
        agora = time.time() if agora is None else agora
        novo = _tokens(texto)
        with self._lock:
            itens = self._ler()
            for it in itens:
                antigo = _tokens(it["texto"])
                if novo and antigo and len(novo & antigo) / len(novo | antigo) >= 0.5:
                    return None   # já é a mesma pendência (aberta, resolvida ou dispensada: não reabre sozinha)
            if sum(1 for i in itens if i["estado"] == "aberta") >= MAX_ABERTAS:
                return None
            pid = uuid.uuid4().hex[:8]
            itens.append({"id": pid, "texto": texto, "proximo_passo": passo, "origem": origem, "estado": "aberta",
                          "criada": agora, "ultimo_toque": 0.0, "toques": 0})
            self._gravar(itens[-100:])
            return pid

    # ------------------------------------------------------------------ consultar / decidir

    def listar(self, estado: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            return [i for i in self._ler() if estado is None or i["estado"] == estado]

    def decidir(self, pid: str, estado: str) -> bool:
        if estado not in ("resolvida", "dispensada"):
            return False
        with self._lock:
            itens = self._ler()
            for it in itens:
                if it["id"] == pid and it["estado"] == "aberta":
                    it["estado"] = estado
                    self._gravar(itens)
                    return True
        return False

    # ------------------------------------------------------------------ retomar

    def proxima_para_retomar(self, agora: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """A pendência a retomar HOJE (ou None): aberta, não tocada há 2 dias, e nenhuma outra retomada nas
        últimas 24 h. A mais antiga sem toque primeiro."""
        agora = time.time() if agora is None else agora
        with self._lock:
            itens = self._ler()
        if any(agora - float(i.get("ultimo_toque", 0)) < INTERVALO_DIA_S for i in itens):
            return None
        candidatas = [i for i in itens if i["estado"] == "aberta" and agora - max(float(i["criada"]), float(i.get("ultimo_toque", 0))) >= INTERVALO_TOQUE_S]
        return sorted(candidatas, key=lambda i: (int(i.get("toques", 0)), float(i["criada"])))[0] if candidatas else None

    def marcar_preparado(self, pid: str) -> bool:
        """O trabalho de bastidor deixou um resumo pronto para esta pendência."""
        with self._lock:
            itens = self._ler()
            for it in itens:
                if it["id"] == pid:
                    it["preparado"] = True
                    self._gravar(itens)
                    return True
        return False

    def registrar_toque(self, pid: str, agora: Optional[float] = None) -> Optional[str]:
        """Conta o toque. No 3º sem resposta, arquiva. Devolve 'arquivada' quando isso acontece."""
        agora = time.time() if agora is None else agora
        with self._lock:
            itens = self._ler()
            for it in itens:
                if it["id"] == pid:
                    it["toques"] = int(it.get("toques", 0)) + 1
                    it["ultimo_toque"] = agora
                    if it["toques"] >= MAX_TOQUES:
                        it["estado"] = "dispensada"
                        self._gravar(itens)
                        return "arquivada"
                    self._gravar(itens)
                    return None
        return None


def frase_de_retomada(p: Dict[str, Any]) -> str:
    """Frase fixa (sem LLM). Varia um pouco pelo número do toque para não soar igual."""
    passo = p.get("proximo_passo") or ""
    n = int(p.get("toques", 0))
    if n == 0:
        base = f"Faz uns dias que você comentou isto: {p['texto']}."
    elif n == 1:
        base = f"Voltando àquilo que ficou em aberto: {p['texto']}."
    else:
        base = f"Última vez que toco neste assunto, prometo: {p['texto']}."
    pergunta = f" Quer que eu {passo.rstrip('.')}?" if passo else " Quer que eu ajude com isso ou posso dispensar?"
    return base + (" Já deixei um resumo pronto: é só pedir." if p.get("preparado") else "") + pergunta


_instancia: Optional[Pendencias] = None


def get_pendencias() -> Pendencias:
    global _instancia
    if _instancia is None:
        _instancia = Pendencias()
    return _instancia
