"""Manutenção pelo horímetro: situação por máquina e pendências da frota."""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol
from uuid import UUID

from sistemacampero.domain.errors import Invalido
from sistemacampero.domain.manutencao import MODELOS, Situacao, prever


class RepositorioManutencao(Protocol):
    def situacao(self, org: UUID, maquina_id: UUID) -> dict[str, Any]: ...
    def maquinas_com_planos(self, org: UUID) -> list[dict[str, Any]]: ...
    def criar_plano(
        self, org: UUID, maquina_id: UUID, nome: str, intervalo_h: float, ultima_h: float | None
    ) -> UUID: ...
    def editar_plano(self, org: UUID, plano_id: UUID, campos: dict[str, Any]) -> None: ...
    def registrar_feita(
        self,
        org: UUID,
        plano_id: UUID,
        horimetro_h: float,
        feita_em: date,
        custo_rs: float | None,
        observacao: str | None,
    ) -> None: ...
    def informar_horimetro(self, org: UUID, maquina_id: UUID, horimetro_h: float) -> None: ...


_ORDEM = {Situacao.VENCIDA: 0, Situacao.PROXIMA: 1, Situacao.SEM_REFERENCIA: 2, Situacao.EM_DIA: 3}


class ServicoManutencao:
    def __init__(self, repo: RepositorioManutencao) -> None:
        self._repo = repo

    def situacao(self, org: UUID, maquina_id: UUID) -> dict[str, Any]:
        s = self._repo.situacao(org, maquina_id)
        planos = []
        for p in s["planos"]:
            prev = prever(p["intervalo_h"], p["ultima_h"], s["horimetro_h"], s["uso_h_dia"])
            planos.append(
                {
                    **p,
                    "proxima_h": prev.proxima_h,
                    "faltam_h": prev.faltam_h,
                    "situacao": prev.situacao.value,
                    "dias_trabalho": prev.dias_trabalho,
                }
            )
        planos.sort(key=lambda p: (_ORDEM[Situacao(p["situacao"])], p["faltam_h"] or 0))
        return {**s, "planos": planos}

    def pendencias(self, org: UUID) -> list[dict[str, Any]]:
        """Itens vencidos ou próximos de toda a frota, o mais urgente primeiro."""
        saida = []
        for m in self._repo.maquinas_com_planos(org):
            s = self.situacao(org, m["id"])
            for p in s["planos"]:
                if p["situacao"] in (Situacao.VENCIDA, Situacao.PROXIMA):
                    saida.append(
                        {
                            "maquina_id": m["id"],
                            "serial": m["serial"],
                            "apelido": m["apelido"],
                            "modelo": m["modelo"],
                            "horimetro_h": s["horimetro_h"],
                            **{k: p[k] for k in ("id", "nome", "faltam_h", "situacao")},
                            "dias_trabalho": p["dias_trabalho"],
                        }
                    )
        return sorted(saida, key=lambda p: p["faltam_h"] or 0)

    def aplicar_modelo(self, org: UUID, maquina_id: UUID, tipo: str) -> int:
        """Cria os planos sugeridos para o tipo, contando a partir do horímetro de agora."""
        if tipo not in MODELOS:
            raise Invalido("Tipo de máquina sem modelo de manutenção.", codigo="TIPO_INVALIDO")
        atuais = {p["nome"] for p in self._repo.situacao(org, maquina_id)["planos"]}
        horimetro = self._repo.situacao(org, maquina_id)["horimetro_h"]
        criados = 0
        for nome, intervalo in MODELOS[tipo]:
            if nome not in atuais:
                self._repo.criar_plano(org, maquina_id, nome, intervalo, horimetro)
                criados += 1
        return criados

    def criar_plano(
        self, org: UUID, maquina_id: UUID, nome: str, intervalo_h: float, ultima_h: float | None
    ) -> UUID:
        return self._repo.criar_plano(org, maquina_id, nome.strip(), intervalo_h, ultima_h)

    def editar_plano(self, org: UUID, plano_id: UUID, campos: dict[str, Any]) -> None:
        self._repo.editar_plano(org, plano_id, campos)

    def registrar_feita(
        self,
        org: UUID,
        plano_id: UUID,
        horimetro_h: float,
        feita_em: date,
        custo_rs: float | None,
        observacao: str | None,
    ) -> None:
        self._repo.registrar_feita(org, plano_id, horimetro_h, feita_em, custo_rs, observacao)

    def informar_horimetro(self, org: UUID, maquina_id: UUID, horimetro_h: float) -> None:
        self._repo.informar_horimetro(org, maquina_id, horimetro_h)
