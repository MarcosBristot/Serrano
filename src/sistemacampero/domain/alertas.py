"""Ciclo de vida do alerta e configuração de regras por organização."""

from __future__ import annotations

from dataclasses import asdict, fields
from enum import StrEnum
from typing import Any

from sistemacampero.domain.errors import Conflito, Invalido
from sistemacampero.domain.services.rules import ConfigRegras


class StatusAlerta(StrEnum):
    ABERTO = "aberto"
    RECONHECIDO = "reconhecido"
    RESOLVIDO = "resolvido"
    INVALIDADO = "invalidado"  # a regra deixou de disparar no reprocessamento


class AcaoAlerta(StrEnum):
    RECONHECER = "reconhecer"
    RESOLVER = "resolver"
    REABRIR = "reabrir"


_TRANSICOES: dict[AcaoAlerta, tuple[set[StatusAlerta], StatusAlerta]] = {
    AcaoAlerta.RECONHECER: ({StatusAlerta.ABERTO}, StatusAlerta.RECONHECIDO),
    AcaoAlerta.RESOLVER: ({StatusAlerta.ABERTO, StatusAlerta.RECONHECIDO}, StatusAlerta.RESOLVIDO),
    AcaoAlerta.REABRIR: ({StatusAlerta.RECONHECIDO, StatusAlerta.RESOLVIDO}, StatusAlerta.ABERTO),
}

SEVERIDADES = ("info", "atencao", "alto")


def transicao(atual: str, acao: AcaoAlerta) -> StatusAlerta:
    origens, destino = _TRANSICOES[acao]
    if StatusAlerta(atual) not in origens:
        raise Conflito(
            f"Não é possível '{acao}' um alerta '{atual}'.",
            codigo="TRANSICAO_INVALIDA",
            status_atual=atual,
        )
    return destino


def severidade_atende(severidade: str, minima: str) -> bool:
    return SEVERIDADES.index(severidade) >= SEVERIDADES.index(minima)


# Limites aceitos na configuração por organização (o resto fica no padrão).
LIMITES: dict[str, tuple[float, float]] = {
    "ociosidade_min_minutos": (5, 240),
    "ociosidade_tolerancia_s": (0, 600),
    "vazao_desvio": (0.05, 3.0),
    "vazao_janela_min": (2, 60),
    "vazao_min_amostras": (30, 3600),
    "gps_velocidade_max_kmh": (20, 200),
    "gps_salto_min_m": (10, 5000),
    "l_ha_desvio": (0.05, 3.0),
    "l_ha_min_sessoes": (3, 100),
}


def config_de(dados: dict[str, Any] | None) -> ConfigRegras:
    """Mescla o salvo com o padrão, validando faixas (versão = hash da config final)."""
    padrao = asdict(ConfigRegras())
    if not dados:
        return ConfigRegras()
    validos = {f.name for f in fields(ConfigRegras)}
    desconhecidos = set(dados) - validos
    if desconhecidos:
        raise Invalido(
            f"Parâmetros desconhecidos: {', '.join(sorted(desconhecidos))}.",
            codigo="CONFIG_REGRAS_INVALIDA",
        )
    final = {**padrao, **dados}
    for nome, (lo, hi) in LIMITES.items():
        v = final[nome]
        if not isinstance(v, int | float) or not (lo <= v <= hi):
            raise Invalido(
                f"'{nome}' deve estar entre {lo} e {hi}.", codigo="CONFIG_REGRAS_INVALIDA"
            )
        final[nome] = type(padrao[nome])(v)
    return ConfigRegras(**final)
