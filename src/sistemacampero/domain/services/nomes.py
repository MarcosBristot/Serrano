"""Nomes de talhão vindos de monitores diferentes: a mesma lavoura escrita de vários jeitos.

O monitor da colheitadeira grava o talhão com a cultura e a safra ("CoxilhaGrand_Trigo22",
"Mae_Aveia22"); o do trator, sem acento ("Mae"); o controlador do pulverizador, com outra
pontuação ("Paulo3-7"). ``chave_talhao`` reduz tudo à mesma chave e ``mesmo_talhao`` aceita o
nome cortado pelo limite de caracteres do monitor.
"""

from __future__ import annotations

import re
import unicodedata

_CULTURAS = (
    "soja|trigo|milho|aveia|feijao|canola|cevada|sorgo|azevem|nabo|centeio|triticale|girassol"
)
# "_Trigo22", " soja 2023", "-aveia" no fim do nome
_SUFIXO_SAFRA = re.compile(rf"[\s_.\-]*(?:{_CULTURAS})[\s_.\-]*(?:\d{{2}}|\d{{4}})?\s*$")
MIN_PREFIXO = 6  # "coxilhagrand" (12) casa com "coxilhagrande"; "paulo" (5) não casa com nada


def _sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()


def chave_talhao(nome: str) -> str:
    """'CoxilhaGrand_Trigo22' -> 'coxilhagrand'; 'Mãe' = 'Mae'; 'Paulo 3,7' = 'Paulo3.7'."""
    base = _sem_acento(nome).lower().strip()
    sem_safra = _SUFIXO_SAFRA.sub("", base) or base
    return "".join(c for c in sem_safra if c.isalnum())


def mesmo_talhao(a: str, b: str) -> bool:
    """Chaves iguais, ou uma é o começo da outra (nome cortado pelo monitor)."""
    if not a or not b:
        return False
    if a == b:
        return True
    curta, longa = sorted((a, b), key=len)
    return len(curta) >= MIN_PREFIXO and longa.startswith(curta)
