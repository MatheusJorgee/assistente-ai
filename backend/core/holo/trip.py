"""
Cronograma por PROXIMIDADE, determinístico, só com locais REAIS.

Não usa LLM: um modelo escrevendo o roteiro a partir de texto de terceiros (OSM/Wikivoyage) abriria
a porta para injeção e para nomes inventados. Aqui o roteiro só REFERENCIA ids de atrações reais
do painel; a UI resolve os nomes.

Algoritmo (sem aleatoriedade, então o mesmo pedido dá o mesmo roteiro):
  1. Fica com os mais notórios (até 4 por dia).
  2. Escolhe uma "semente" por dia (a 1ª = a mais notória; as outras, as mais distantes das já escolhidas).
  3. Cada local vai para a semente mais próxima que ainda tem vaga.
  4. Os dias são ordenados pela notoriedade do melhor local; dentro do dia, vizinho mais próximo.
  5. Metade da manhã, metade da tarde.
"""

import math
from collections import Counter
from typing import Any, Dict, List, Sequence

from .geo import _haversine_km

POR_DIA = 4


def _dist(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    return _haversine_km(a["lat"], a["lon"], b["lat"], b["lon"])


def _sementes(pois: Sequence[Dict[str, Any]], n: int) -> List[int]:
    """Índices das sementes: a mais notória, depois sempre a mais distante das já escolhidas."""
    escolhidas = [0]
    while len(escolhidas) < n:
        melhor, melhor_d = -1, -1.0
        for i, p in enumerate(pois):
            if i in escolhidas:
                continue
            d = min(_dist(p, pois[j]) for j in escolhidas)
            if d > melhor_d:  # empate: fica o mais notório (menor índice), pois só troca se maior
                melhor, melhor_d = i, d
        escolhidas.append(melhor)
    return escolhidas


def _vizinho_mais_proximo(indices: List[int], pois: Sequence[Dict[str, Any]]) -> List[int]:
    """Ordena o dia partindo do local mais notório, sempre indo ao mais próximo."""
    restantes = sorted(indices)  # menor índice = mais notório
    ordem = [restantes.pop(0)]
    while restantes:
        ultimo = pois[ordem[-1]]
        prox = min(restantes, key=lambda i: (_dist(ultimo, pois[i]), i))
        restantes.remove(prox)
        ordem.append(prox)
    return ordem


def _titulo(n: int, itens: Sequence[Dict[str, Any]]) -> str:
    cats = Counter(i.get("categoria", "") for i in itens if i.get("categoria"))
    if not cats:
        return f"Dia {n}"
    principal = sorted(cats.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    return f"Dia {n} · {principal}"


def agrupar_por_dia(atracoes: Sequence[Dict[str, Any]], dias: int) -> List[Dict[str, Any]]:
    """Atrações (em ordem de notoriedade, com id/lat/lon/categoria) -> `dias` do cronograma.

    Menos locais que dias => menos dias (nunca se enche o roteiro com o que não existe)."""
    pois = [a for a in atracoes if all(k in a for k in ("id", "lat", "lon"))]
    dias = max(1, int(dias))
    if not pois:
        return []
    pois = pois[: dias * POR_DIA]
    n = min(dias, len(pois))
    capacidade = min(POR_DIA, math.ceil(len(pois) / n))

    sementes = _sementes(pois, n)
    grupos: List[List[int]] = [[s] for s in sementes]
    for i in range(len(pois)):
        if i in sementes:
            continue
        ordem_sementes = sorted(range(n), key=lambda g: (_dist(pois[i], pois[sementes[g]]), g))
        destino = next((g for g in ordem_sementes if len(grupos[g]) < capacidade), None)
        if destino is None:  # todos cheios (só se arredondou mal): vai para o menos cheio
            destino = min(range(n), key=lambda g: (len(grupos[g]), g))
        grupos[destino].append(i)

    grupos.sort(key=lambda g: min(g))  # dia 1 = o grupo com o local mais notório

    cronograma = []
    for numero, grupo in enumerate(grupos, start=1):
        ordem = _vizinho_mais_proximo(grupo, pois)
        itens = [pois[i] for i in ordem]
        meio = math.ceil(len(itens) / 2)
        blocos = [{"periodo": "manha", "poi_ids": [i["id"] for i in itens[:meio]]}]
        if itens[meio:]:
            blocos.append({"periodo": "tarde", "poi_ids": [i["id"] for i in itens[meio:]]})
        cronograma.append({"n": numero, "titulo": _titulo(numero, itens), "blocos": blocos})
    return cronograma
