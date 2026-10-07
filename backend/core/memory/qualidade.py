"""
Qualidade da memória: regras puras (sem banco, sem LLM) para decidir o que vale lembrar, o que proteger
e o que deixar de lado.

Problemas que isto resolve (achados na memória real):
  - metade dos fatos era curiosidade sobre o MUNDO, e o bloco de perfil pegava os "10 mais recentes":
    trivia empurrava para fora o que importa sobre o Matheus;
  - categorias fragmentadas ("habito|pessoa", "traço-humor" x "traço-de-humor");
  - a correção feita na tela era sobrescrita pela próxima reflexão (a fonte continuava "reflexao");
  - nada media o que é USADO (access_count nunca era atualizado), então nada podia envelhecer.
"""

import math
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

# Quem manda mais: o que o Matheus diz/corrige vale mais que o que ela deduziu, que vale mais que a web.
RANK_FONTE = {"usuario": 4, "tool": 3, "reflexao": 2, "curiosidade": 1}
RANK_PADRAO = 2

# Categorias canônicas e o quanto pesam num perfil ESSENCIAL (0 = só entra por relevância, nunca no perfil)
PESO_CATEGORIA = {"perfil": 1.0, "preferencia": 0.95, "pessoa": 0.9, "projeto": 0.9, "habito": 0.7, "humor": 0.4, "user": 0.6}
CATEGORIA_MUNDO = "aprendizado"          # curiosidades da web: nada a ver com quem ele é
_ALIASES = {
    "habitos": "habito", "rotina": "habito", "rotinas": "habito",
    "preferencias": "preferencia", "gosto": "preferencia", "gostos": "preferencia",
    "pessoas": "pessoa", "projetos": "projeto",
    "traco-de-humor": "humor", "traco-humor": "humor", "traco": "humor", "tracos": "humor", "humor": "humor",
    "aprendizados": CATEGORIA_MUNDO, "curiosidade": CATEGORIA_MUNDO,
}
MEIA_VIDA_DIAS = 180.0                   # confiança efetiva cai pela metade a cada 180 dias SEM uso
MAX_POR_CATEGORIA = 3
_ESP = re.compile(r"\s+")


def _sem_acento(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t or "") if unicodedata.category(c) != "Mn")


def canonicalizar_categoria(cat: Any) -> str:
    """'Hábito|pessoa' -> 'habito'; 'traço-humor' -> 'humor'; vazio -> 'user'."""
    bruto = str(cat or "").strip()
    if not bruto:
        return "user"
    primeira = re.split(r"[|,;/]", bruto)[0].strip().lower()
    norm = re.sub(r"[^a-z0-9-]+", "-", _sem_acento(primeira)).strip("-")
    return _ALIASES.get(norm, norm or "user")


def rank_da_fonte(fonte: Any) -> int:
    return RANK_FONTE.get(str(fonte or "").strip().lower(), RANK_PADRAO)


def mesmo_valor(a: Any, b: Any) -> bool:
    def n(t: Any) -> str:
        return _ESP.sub(" ", re.sub(r"[^\w\s]", "", _sem_acento(str(t or "")).lower())).strip()
    return n(a) == n(b)


def _dias(desde: Any, agora: datetime) -> float:
    try:
        d = datetime.fromisoformat(str(desde).replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return max(0.0, (agora - d).total_seconds() / 86400.0)
    except (ValueError, TypeError):
        return 0.0


def confianca_efetiva(fato: Dict[str, Any], agora: Optional[datetime] = None) -> float:
    """Confiança guardada, corrigida pelo tempo SEM USO. O que é seu (fonte 'usuario') não envelhece."""
    agora = agora or datetime.now(timezone.utc)
    base = float(fato.get("confidence") or 0.5)
    if rank_da_fonte(fato.get("source")) >= RANK_FONTE["usuario"]:
        return base
    ultimo_uso = fato.get("last_accessed_at") or fato.get("updated_at") or fato.get("created_at")
    return base * math.pow(0.5, _dias(ultimo_uso, agora) / MEIA_VIDA_DIAS)


def pontuar(fato: Dict[str, Any], agora: Optional[datetime] = None) -> float:
    """Importância para o PERFIL: peso da categoria x confiança efetiva x uso (log) x leve frescor."""
    agora = agora or datetime.now(timezone.utc)
    peso = PESO_CATEGORIA.get(canonicalizar_categoria(fato.get("category")), 0.5)
    uso = 1.0 + 0.1 * math.log1p(int(fato.get("access_count") or 0))
    frescor = 1.0 + 0.15 * math.exp(-_dias(fato.get("updated_at"), agora) / 30.0)
    bonus_dono = 1.25 if rank_da_fonte(fato.get("source")) >= RANK_FONTE["usuario"] else 1.0
    return peso * confianca_efetiva(fato, agora) * uso * frescor * bonus_dono


def escolher_perfil(fatos: Iterable[Dict[str, Any]], limite: int = 8, agora: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """O perfil essencial que entra em TODA resposta: sem curiosidade do mundo, sem lixo de baixa
    confiança, no máximo 3 por categoria (variedade) e os de maior pontuação primeiro."""
    agora = agora or datetime.now(timezone.utc)
    candidatos = []
    for f in fatos:
        cat = canonicalizar_categoria(f.get("category"))
        if cat == CATEGORIA_MUNDO or PESO_CATEGORIA.get(cat, 0.5) <= 0:
            continue
        if confianca_efetiva(f, agora) < 0.25:
            continue
        candidatos.append((pontuar(f, agora), cat, f))
    candidatos.sort(key=lambda x: x[0], reverse=True)
    saida: List[Dict[str, Any]] = []
    por_cat: Dict[str, int] = {}
    for _, cat, f in candidatos:
        if por_cat.get(cat, 0) >= MAX_POR_CATEGORIA:
            continue
        por_cat[cat] = por_cat.get(cat, 0) + 1
        saida.append(f)
        if len(saida) >= limite:
            break
    return saida


def esqueciveis(fatos: Iterable[Dict[str, Any]], limite_conf: float = 0.3, agora: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Candidatos a esquecer (NUNCA apaga sozinha): confiança efetiva baixa e não é seu. Só sugere."""
    agora = agora or datetime.now(timezone.utc)
    out = []
    for f in fatos:
        if rank_da_fonte(f.get("source")) >= RANK_FONTE["tool"]:
            continue
        ce = confianca_efetiva(f, agora)
        if ce < limite_conf:
            out.append(dict(f, confianca_efetiva=round(ce, 2)))
    return sorted(out, key=lambda x: x["confianca_efetiva"])


def rotulo_de_origem(fato: Dict[str, Any], agora: Optional[datetime] = None) -> str:
    """Sufixo honesto para o prompt: o modelo sabe o quanto confiar naquela linha."""
    agora = agora or datetime.now(timezone.utc)
    fonte = str(fato.get("source") or "").lower()
    if fonte == "curiosidade" or canonicalizar_categoria(fato.get("category")) == CATEGORIA_MUNDO:
        return " [pesquisa na web, não confirmado]"
    if rank_da_fonte(fonte) >= RANK_FONTE["usuario"]:
        return ""
    if confianca_efetiva(fato, agora) < 0.5:
        return " [incerto: pergunte antes de afirmar]"
    return ""
