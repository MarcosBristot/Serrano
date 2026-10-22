"""Qualidade da sessão (0-100) e checagens de consistência.

Em vez de publicar número errado, a sessão inconsistente tem a qualidade rebaixada e
gera um problema explicado (que vira alerta de dado). Checagens:

* horímetro x motor ligado: o horímetro só anda com o motor ligado (defeito 1);
* contador x integral da vazão: só com volume E duração mínimos, porque a resolução do
  contador (0,5 L) domina em sessões curtas (defeito 2);
* cobertura de GPS, canais essenciais, lacunas > 60 s, % descartado na sanitização;
* sessão curta (< 2 min) é marcada como fragmento e não acumula outras penalidades.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from sistemacampero.domain.services.metrics import MetricasSessao

ESSENCIAIS = ("speed_kmh", "fuel_rate_lph", "engine_rpm", "engine_hours", "fuel_total_l")
LACUNA_S = 60
SESSAO_CURTA_S = 120  # fragmentos (no dump de 2026, mediana de 2 s) não têm todos os canais

HORIMETRO_MIN_H = 0.25  # compara horímetro x motor só com 15 min ou mais de horímetro
HORIMETRO_TOLERANCIA = 0.20  # 20% (+ resolução do horímetro)
HORIMETRO_RESOLUCAO_H = 0.05

CONTADOR_MIN_L = 10.0
CONTADOR_MIN_MOTOR_H = 0.5
CONTADOR_TOLERANCIA = 0.15
CONTADOR_RESOLUCAO_L = 0.5


@dataclass(frozen=True, slots=True)
class Problema:
    codigo: str  # estável: o frontend explica por ele
    severidade: str  # info | atencao | alto
    mensagem: str
    penalidade: int
    valor: float | None = None


@dataclass(slots=True)
class Qualidade:
    score: int
    problemas: list[Problema] = field(default_factory=list)
    detalhes: dict[str, Any] = field(default_factory=dict)

    def tem(self, codigo: str) -> bool:
        return any(p.codigo == codigo for p in self.problemas)


def consistencia_horimetro(m: MetricasSessao) -> Problema | None:
    d = m.delta_horimetro_h
    if d is None or d < HORIMETRO_MIN_H:
        return None
    erro = abs(m.motor_h - d)
    if erro <= HORIMETRO_TOLERANCIA * d + HORIMETRO_RESOLUCAO_H:
        return None
    return Problema(
        "HORIMETRO_DIVERGE",
        "alto",
        f"O horímetro avançou {d:.2f} h, mas o motor aparece ligado por {m.motor_h:.2f} h. "
        "As horas e o consumo desta sessão não são confiáveis.",
        penalidade=50,
        valor=round(erro, 3),
    )


def consistencia_contador(m: MetricasSessao) -> Problema | None:
    c, i = m.litros_contador, m.litros_integral
    if c is None or i is None or pd.isna(c) or pd.isna(i):
        return None
    if c < CONTADOR_MIN_L or m.motor_h < CONTADOR_MIN_MOTOR_H:
        return None  # sessão curta: a resolução do contador domina a comparação
    erro = abs(c - i)
    if erro <= max(CONTADOR_TOLERANCIA * c, 2 * CONTADOR_RESOLUCAO_L):
        return None
    return Problema(
        "CONTADOR_DIVERGE",
        "atencao",
        f"Contador de combustível ({c:.1f} L) diverge {100 * erro / c:.0f}% da vazão "
        f"integrada ({i:.1f} L). Verificar lacunas de dados ou sensor.",
        penalidade=25,
        valor=round(100 * erro / c, 1),
    )


def _maior_lacuna_s(limpo: pd.DataFrame) -> int:
    sem_dado = limpo[list(ESSENCIAIS)].isna().all(axis=1).to_numpy()
    maior = atual = 0
    for vazio in sem_dado:
        atual = atual + 1 if vazio else 0
        maior = max(maior, atual)
    return maior


def avaliar(
    limpo: pd.DataFrame,
    metricas: MetricasSessao | None,
    relatorio_sanitizacao: dict[str, int],
    canais_ausentes: list[str],
) -> Qualidade:
    problemas: list[Problema] = []
    if len(limpo) < SESSAO_CURTA_S:
        problemas.append(
            Problema(
                "SESSAO_CURTA",
                "info",
                f"Sessão de {len(limpo)} s: fragmento, sem base para razões (L/h, L/ha).",
                penalidade=30,
                valor=float(len(limpo)),
            )
        )
        return Qualidade(score=70, problemas=problemas, detalhes={"amostras": len(limpo)})
    if canais_ausentes:
        problemas.append(
            Problema(
                "CANAIS_AUSENTES",
                "atencao",
                f"Canais ausentes no arquivo: {', '.join(canais_ausentes)}.",
                penalidade=10 * len(canais_ausentes),
            )
        )
    lacuna = _maior_lacuna_s(limpo) if not limpo.empty else 0
    if lacuna > LACUNA_S:
        problemas.append(
            Problema(
                "LACUNA_DE_DADOS",
                "info",
                f"Trecho de {lacuna / 60:.0f} min sem nenhuma medida do trator.",
                penalidade=10,
                valor=float(lacuna),
            )
        )
    descartadas = relatorio_sanitizacao.get("descartadas_por_mil", 0)
    if descartadas > 20:
        problemas.append(
            Problema(
                "MUITOS_DESCARTES",
                "atencao",
                f"{descartadas / 10:.1f}% das medidas foram descartadas na sanitização.",
                penalidade=min(30, descartadas // 10),
                valor=descartadas / 10,
            )
        )
    if metricas is not None:
        if metricas.motor_h >= 0.25 and metricas.cobertura_gps == 0:
            problemas.append(
                Problema(
                    "SEM_GPS",
                    "info",
                    f"{metricas.motor_h:.1f} h de motor ligado sem nenhuma posição: "
                    "sem talhão nem área por cobertura.",
                    penalidade=20,
                )
            )
        elif metricas.motor_h >= 0.25 and metricas.cobertura_gps < 0.8:
            problemas.append(
                Problema(
                    "GPS_PARCIAL",
                    "info",
                    f"Só {100 * metricas.cobertura_gps:.0f}% do tempo de motor tem posição.",
                    penalidade=10,
                    valor=round(metricas.cobertura_gps, 3),
                )
            )
        for checagem in (consistencia_horimetro(metricas), consistencia_contador(metricas)):
            if checagem is not None:
                problemas.append(checagem)

    score = max(0, 100 - sum(p.penalidade for p in problemas))
    return Qualidade(
        score=score,
        problemas=problemas,
        detalhes={"maior_lacuna_s": lacuna, "descartadas_por_mil": descartadas},
    )
