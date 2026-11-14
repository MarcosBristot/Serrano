"""Fechamento da safra: produtividade e custo de máquina por talhão, em sacas."""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from sistemacampero.domain.colheita import KG_POR_SACA
from sistemacampero.domain.errors import NaoEncontrado


class ConsultasFechamento(Protocol):
    def safras(self, org: UUID) -> list[dict[str, Any]]: ...
    def talhoes(
        self, org: UUID, safra: str, cultura: str | None, versao: str
    ) -> list[dict[str, Any]]: ...


def _div(a: float | None, b: float | None) -> float | None:
    return a / b if a is not None and b else None


class ServicoFechamento:
    def __init__(self, q: ConsultasFechamento, versao_regras: str) -> None:
        self._q = q
        self._versao = versao_regras

    def safras(self, org: UUID) -> list[dict[str, Any]]:
        return [{**s, "sc_ha": _div(s["sacas"], s["area_colhida_ha"])} for s in self._q.safras(org)]

    def fechamento(self, org: UUID, safra: str, cultura: str | None = None) -> dict[str, Any]:
        linhas = self._q.talhoes(org, safra, cultura, self._versao)
        if not linhas:
            raise NaoEncontrado("Nenhuma colheita nesta safra.", codigo="SAFRA_SEM_COLHEITA")
        talhoes = []
        for t in linhas:
            sacas = t["massa_seca_kg"] / KG_POR_SACA
            ops = t["operacoes_maquina"]
            litros = sum(o["litros"] or 0 for o in ops)
            custo = sum(o["custo_rs"] or 0 for o in ops) if ops else None
            area = t["area_colhida_ha"]
            talhoes.append(
                {
                    "talhao_id": t["talhao_id"],
                    "talhao_nome": t["talhao_nome"],
                    "cultura": t["cultura"],
                    "variedades": t["variedades"] or [],
                    "area_talhao_ha": t["area_talhao_ha"],
                    "area_colhida_ha": area,
                    "sacas": sacas,
                    "sc_ha": _div(sacas, area),
                    "umidade_pct": t["umidade_pct"],
                    "colheita_inicio": t["colheita_inicio"],
                    "colheita_fim": t["colheita_fim"],
                    "janela_inicio": t["janela_inicio"],
                    "motor_h": sum(o["motor_h"] or 0 for o in ops),
                    "litros": litros,
                    "custo_diesel_rs": custo,
                    "l_ha": _div(litros, area),
                    "custo_diesel_ha": _div(custo, area),
                    "custo_diesel_saca": _div(custo, sacas),
                    "operacoes_maquina": ops,
                }
            )
        area = sum(t["area_colhida_ha"] for t in talhoes)
        sacas = sum(t["sacas"] for t in talhoes)
        custo = sum(t["custo_diesel_rs"] or 0 for t in talhoes)
        horas = sum(t["motor_h"] for t in talhoes)
        media = _div(sacas, area)
        for t in talhoes:  # quanto cada talhão ficou acima/abaixo da média da fazenda
            t["vs_media_pct"] = (
                100 * (t["sc_ha"] / media - 1) if t["sc_ha"] is not None and media else None
            )
        return {
            "safra": safra,
            "cultura": cultura,
            "area_colhida_ha": area,
            "sacas": sacas,
            "sc_ha": media,
            "motor_h": horas,
            "litros": sum(t["litros"] for t in talhoes),
            "custo_diesel_rs": custo or None,
            "custo_diesel_saca": _div(custo, sacas),
            "horas_ha": _div(horas, area),
            "talhoes": talhoes,
        }
