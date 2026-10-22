"""KPIs: soma em ``metricas_diarias`` + razões calculadas num lugar só (domínio)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Protocol
from uuid import UUID

import pandas as pd

from sistemacampero.domain.errors import Invalido, NaoEncontrado
from sistemacampero.domain.services.kpis import (
    Indicadores,
    Somas,
    derivar,
    intervalo_da_safra,
    safra,
)
from sistemacampero.domain.services.mapas import mapa_de_calor, trajeto

MAX_DIAS_HORA = 31
MAX_DIAS_MAPA = 366
GRANULARIDADES = {"dia": "day", "semana": "week", "mes": "month"}
RANKINGS = ("maquina", "talhao", "operacao")


class ConsultasKpi(Protocol):
    def inicio_safra_mes(self, org: UUID) -> int: ...
    def resumo(self, org: UUID, f: dict[str, Any]) -> dict[str, Any]: ...
    def serie(self, org: UUID, f: dict[str, Any], granularidade: str) -> list[dict[str, Any]]: ...
    def serie_horaria(self, org: UUID, f: dict[str, Any]) -> list[dict[str, Any]]: ...
    def ranking(self, org: UUID, f: dict[str, Any], por: str) -> list[dict[str, Any]]: ...
    def por_safra(self, org: UUID, f: dict[str, Any], inicio_mes: int) -> list[dict[str, Any]]: ...
    def pontos_mapa(self, org: UUID, f: dict[str, Any], celula_m: float) -> pd.DataFrame: ...
    def pontos_sessao(self, org: UUID, sessao_id: UUID) -> pd.DataFrame | None: ...


SomasDe = Any  # callable linha -> Somas (infraestrutura)


@dataclass(frozen=True, slots=True)
class Filtros:
    inicio: date | None = None
    fim: date | None = None
    maquina_id: UUID | None = None
    talhao_id: UUID | None = None
    operacao: str | None = None

    def validar(self) -> None:
        if self.inicio and self.fim and self.fim < self.inicio:
            raise Invalido("'fim' antes de 'inicio'.", codigo="PERIODO_INVALIDO")


class ServicoKpis:
    def __init__(self, consultas: ConsultasKpi, somas_de: SomasDe, versao_regras: str) -> None:
        self._q = consultas
        self._somas = somas_de
        self._versao = versao_regras

    def _f(self, f: Filtros) -> dict[str, Any]:
        f.validar()
        return {
            "versao": self._versao,
            "inicio": f.inicio,
            "fim": f.fim,
            "maquina_id": f.maquina_id,
            "talhao_id": f.talhao_id,
            "operacao": f.operacao,
        }

    def _ind(self, linha: dict[str, Any]) -> Indicadores:
        s: Somas = self._somas(linha)
        return derivar(s)

    def resumo(self, org: UUID, f: Filtros) -> dict[str, Any]:
        linha = self._q.resumo(org, self._f(f))
        return {
            **self._ind(linha).como_dict(),
            "sessoes": linha["sessoes"],
            "maquinas": int(linha["maquinas"]),
            "primeiro_dia": linha["primeiro_dia"],
            "ultimo_dia": linha["ultimo_dia"],
            "dias_sem_preco": int(linha["dias_sem_preco"]),
        }

    def serie(self, org: UUID, f: Filtros, granularidade: str) -> list[dict[str, Any]]:
        if granularidade == "hora":
            if not (f.inicio and f.fim) or (f.fim - f.inicio) > timedelta(days=MAX_DIAS_HORA):
                raise Invalido(
                    f"Série por hora exige 'inicio' e 'fim' com até {MAX_DIAS_HORA} dias.",
                    codigo="PERIODO_INVALIDO",
                )
            linhas = self._q.serie_horaria(org, self._f(f))
        elif granularidade in GRANULARIDADES:
            linhas = self._q.serie(org, self._f(f), GRANULARIDADES[granularidade])
        else:
            raise Invalido(
                "Granularidade: hora, dia, semana ou mes.", codigo="GRANULARIDADE_INVALIDA"
            )
        return [{"periodo": x["periodo"], **self._ind(x).como_dict()} for x in linhas]

    def ranking(self, org: UUID, f: Filtros, por: str) -> list[dict[str, Any]]:
        if por not in RANKINGS:
            raise Invalido("Ranking por: maquina, talhao ou operacao.", codigo="RANKING_INVALIDO")
        return [
            {
                "id": x["id"],
                "nome": x["nome"],
                "sessoes": int(x["sessoes"] or 0),
                **self._ind(x).como_dict(),
            }
            for x in self._q.ranking(org, self._f(f), por)
        ]

    def safras(self, org: UUID, f: Filtros, comparar: list[str] | None) -> list[dict[str, Any]]:
        mes = self._q.inicio_safra_mes(org)
        filtros = self._f(f)
        out = []
        for x in self._q.por_safra(org, filtros, mes):
            rotulo = safra(date(int(x["ano"]), mes, 1), mes)
            if comparar and rotulo not in comparar:
                continue
            inicio, fim = intervalo_da_safra(rotulo, mes)
            out.append({"safra": rotulo, "inicio": inicio, "fim": fim, **self._ind(x).como_dict()})
        return out

    def mapa_calor(self, org: UUID, f: Filtros, tamanho_m: float) -> dict[str, Any]:
        if not (f.inicio and f.fim) or (f.fim - f.inicio) > timedelta(days=MAX_DIAS_MAPA):
            raise Invalido(
                f"Mapa de calor exige 'inicio' e 'fim' com até {MAX_DIAS_MAPA} dias.",
                codigo="PERIODO_INVALIDO",
            )
        if not 10 <= tamanho_m <= 2000:
            raise Invalido("tamanho_m entre 10 e 2000.", codigo="TAMANHO_INVALIDO")
        return mapa_de_calor(self._q.pontos_mapa(org, self._f(f), tamanho_m / 5), tamanho_m)

    def trajeto(self, org: UUID, sessao_id: UUID, max_pontos: int) -> dict[str, Any]:
        pontos = self._q.pontos_sessao(org, sessao_id)
        if pontos is None:
            raise NaoEncontrado("Sessão não encontrada.", codigo="SESSAO_NAO_ENCONTRADA")
        return trajeto(pontos, max_pontos)
