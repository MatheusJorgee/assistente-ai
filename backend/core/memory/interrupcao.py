"""
Registro do que foi REALMENTE falado quando ela é interrompida (B5).

Sem isto o histórico guarda a resposta inteira, e o Matheus acha que ela disse o que nunca chegou
a sair da caixa de som ("como eu falei…"). A tela informa o que tocou; o histórico passa a
refletir isso, com a marca "[interrompido]". Local, sem LLM.
"""

import re

MARCA = "[interrompido]"
_ESP = re.compile(r"\s+")


def _norm(t: str) -> str:
    return _ESP.sub("", t or "")


def texto_interrompido(completo: str, falado: str) -> str:
    """Devolve o que deve ficar no histórico no lugar de `completo`.

    - falado é um prefixo mais curto do completo -> o prefixo (com o espaçamento original) + marca
    - nada foi falado                              -> "[interrompido antes de falar]"
    - falou tudo, ou não bate com o texto          -> o completo, sem mexer (na dúvida, não inventa)
    """
    completo = completo or ""
    n_falado = _norm(falado)
    if not completo or MARCA in completo or n_falado == _norm(completo) and n_falado:
        return completo
    if not n_falado:
        return "[interrompido antes de falar]"
    if not _norm(completo).startswith(n_falado):
        return completo
    # recorta o prefixo preservando o espaçamento original
    vistos, corte = 0, len(completo)
    for i, ch in enumerate(completo):
        if not ch.isspace():
            vistos += 1
            if vistos == len(n_falado):
                corte = i + 1
                break
    return f"{completo[:corte].rstrip()} {MARCA}"
