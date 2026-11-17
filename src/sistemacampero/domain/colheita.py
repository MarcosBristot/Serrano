"""Colheita: o que a colheitadeira mediu, já no padrão de comercialização (massa seca, sacas).

O monitor mede massa **úmida**; o grão é vendido descontando a água acima da umidade padrão
de cada cultura. ``massa_seca = massa_umida x (100 - umidade) / (100 - padrão)``.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import datetime

KG_POR_SACA = 60.0

# Umidade de comercialização (%): soja e milho 14 (MAPA), trigo e cereais de inverno 13.
UMIDADE_PADRAO = {
    "soja": 14.0,
    "milho": 14.0,
    "feijao": 14.0,
    "sorgo": 14.0,
    "girassol": 11.0,
    "trigo": 13.0,
    "aveia": 13.0,
    "cevada": 13.0,
    "centeio": 13.0,
    "triticale": 13.0,
    "canola": 10.0,
}
INVERNO = {"trigo", "aveia", "cevada", "centeio", "triticale", "canola"}


@dataclass(frozen=True, slots=True)
class Colheita:
    """Resumo de uma operação de colheita (um arquivo do monitor)."""

    cultura: str | None  # "soja", "trigo"... (normalizada)
    variedade: str | None
    massa_umida_kg: float
    umidade_pct: float | None  # média ponderada pela massa
    area_colhida_ha: float  # só com a plataforma abaixada
    ano_safra: int | None = None  # o que o monitor informa (cropYear)


def cultura_normalizada(nome: str | None) -> str | None:
    """'Trigo (Dur Vrm Inv)' -> 'trigo'; 'Soja' -> 'soja'; desconhecida fica como veio."""
    if not nome:
        return None
    base = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode().lower()
    for cultura in UMIDADE_PADRAO:
        if base.startswith(cultura) or f" {cultura}" in base:
            return cultura
    return base.split("(")[0].strip() or None


def massa_seca_kg(c: Colheita) -> float:
    padrao = UMIDADE_PADRAO.get(c.cultura or "")
    if padrao is None or c.umidade_pct is None or c.umidade_pct <= padrao:
        return c.massa_umida_kg  # sem desconto (já está seco ou não sabemos o padrão)
    return c.massa_umida_kg * (100 - c.umidade_pct) / (100 - padrao)


def safra_de(cultura: str | None, colhida_em: datetime) -> str:
    """Rótulo de safra como o produtor fala: 'Inverno 2022' ou '2025/26' (verão)."""
    ano = colhida_em.year
    if cultura in INVERNO:
        return f"Inverno {ano}"
    # Verão: soja e milho colhidos até agosto são da safra que começou no ano anterior.
    inicio = ano - 1 if colhida_em.month <= 8 else ano
    return f"{inicio}/{(inicio + 1) % 100:02d}"
