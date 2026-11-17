"""Agendamento do resumo semanal: segunda a partir das 7 h locais, uma vez por semana."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sistemacampero.application.resumo_semanal import ServicoResumoSemanal


class RepoFalso:
    def __init__(self) -> None:
        self.org = uuid4()
        self.registros: list[tuple[UUID, str, int]] = []

    def orgs_com_destino(self) -> list[dict[str, Any]]:
        return [{"organizacao_id": self.org, "fuso": "America/Sao_Paulo"}]

    def ja_enviado(self, org: UUID, semana: str) -> bool:
        return any(r[1] == semana for r in self.registros)

    def registrar(self, org: UUID, semana: str, destinos: int, texto: str) -> None:
        self.registros.append((org, semana, destinos))

    def destinos(self, org: UUID) -> list[dict[str, Any]]:
        return [
            {"id": 1, "tipo": "email", "destino": "a@b.c", "ativo": True},
            {"id": 2, "tipo": "whatsapp", "destino": "+55", "ativo": True},  # sem provedor: pula
        ]

    def nome_org(self, org: UUID) -> str:
        return "Fazenda Teste"


class EnviadorFalso:
    def __init__(self) -> None:
        self.enviados: list[str] = []

    def resumo(self, destino: dict[str, Any], titulo: str, texto: str) -> None:
        self.enviados.append(destino["tipo"])


def _servico() -> tuple[ServicoResumoSemanal, RepoFalso, EnviadorFalso]:
    repo, env = RepoFalso(), EnviadorFalso()
    s = ServicoResumoSemanal(repo, None, None, env, "https://app")  # type: ignore[arg-type]
    s.montar = lambda org, fim=None: {"texto": "oi"}  # type: ignore[method-assign]
    return s, repo, env


def test_envia_segunda_depois_das_7h_e_so_uma_vez() -> None:
    s, repo, env = _servico()
    segunda_6h = datetime(2026, 11, 9, 9, 0, tzinfo=UTC)  # 06:00 em Brasília
    assert s.enviar_da_semana(segunda_6h) == 0
    segunda_8h = datetime(2026, 11, 9, 11, 0, tzinfo=UTC)
    assert s.enviar_da_semana(segunda_8h) == 1
    assert env.enviados == ["email"] and repo.registros[0][1:] == ("2026-W46", 1)
    assert s.enviar_da_semana(segunda_8h) == 0  # mesma semana: não repete


def test_nao_envia_em_outro_dia() -> None:
    s, _, env = _servico()
    assert s.enviar_da_semana(datetime(2026, 11, 10, 12, 0, tzinfo=UTC)) == 0  # terça
    assert env.enviados == []
