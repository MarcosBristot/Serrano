"""Manutenção pelo horímetro: quando cada item vence e quantos dias de trabalho faltam.

Os modelos são sugestões de partida (intervalos comuns de mercado), não o manual do
fabricante: o produtor ajusta para a máquina dele.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

MODELOS: dict[str, list[tuple[str, float]]] = {
    "trator": [
        ("Óleo e filtro do motor", 250),
        ("Filtro de combustível", 500),
        ("Filtro de ar", 500),
        ("Óleo da transmissão e hidráulico", 1000),
    ],
    "colheitadeira": [
        ("Óleo e filtro do motor", 250),
        ("Filtros de combustível", 500),
        ("Correias, rolamentos e lubrificação", 250),
        ("Óleo hidráulico e da transmissão", 1000),
    ],
    "pulverizador": [
        ("Óleo e filtro do motor", 250),
        ("Filtros de combustível", 500),
        ("Bicos e filtros de linha", 100),
        ("Óleo hidráulico", 1000),
    ],
}


class Situacao(StrEnum):
    EM_DIA = "em_dia"
    PROXIMA = "proxima"  # dentro da margem: agendar
    VENCIDA = "vencida"
    SEM_REFERENCIA = "sem_referencia"  # falta saber o horímetro da última vez


@dataclass(frozen=True, slots=True)
class Previsao:
    proxima_h: float | None
    faltam_h: float | None
    situacao: Situacao
    dias_trabalho: float | None  # no ritmo de uso recente


DIAS_PARA_AGENDAR = 5  # tempo prático para comprar a peça e chamar o mecânico


def margem_h(intervalo_h: float) -> float:
    """Aviso com 10 % do intervalo de antecedência (pelo menos 25 h)."""
    return max(25.0, 0.10 * intervalo_h)


def prever(
    intervalo_h: float, ultima_h: float | None, horimetro_h: float | None, uso_h_dia: float | None
) -> Previsao:
    if ultima_h is None or horimetro_h is None:
        return Previsao(None, None, Situacao.SEM_REFERENCIA, None)
    proxima = ultima_h + intervalo_h
    faltam = proxima - horimetro_h
    dias = max(faltam, 0) / uso_h_dia if uso_h_dia and uso_h_dia > 0 else None
    if faltam <= 0:
        situacao = Situacao.VENCIDA
    elif faltam <= margem_h(intervalo_h) or (dias is not None and dias <= DIAS_PARA_AGENDAR):
        situacao = Situacao.PROXIMA
    else:
        situacao = Situacao.EM_DIA
    return Previsao(proxima, faltam, situacao, dias)
