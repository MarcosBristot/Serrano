"""Regras da exclusão de conta (sem banco)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any
from uuid import UUID

import pytest

from sistemacampero.application.titular import ServicoTitular, classificar
from sistemacampero.domain.errors import Conflito, Invalido
from sistemacampero.domain.tenancy import Principal
from sistemacampero.interfaces.api.middleware import evento_acesso


class RepoFalso:
    def __init__(self, impacto: list[dict[str, Any]]) -> None:
        self._impacto = impacto
        self.agendado: dict[str, Any] | None = None
        self.excluidas: list[UUID] = []
        self.titular_excluido = False
        self.concluidos: list[tuple[UUID, str | None]] = []

    def dados(self, usuario_id: UUID) -> dict[str, Any]:
        return {}

    def impacto(self, usuario_id: UUID) -> list[dict[str, Any]]:
        return self._impacto

    def pedido_ativo(self, usuario_id: UUID) -> dict[str, Any] | None:
        return self.agendado

    def agendar(
        self, usuario_id: UUID, email: str | None, organizacoes: list[UUID], quando: datetime
    ) -> dict[str, Any]:
        self.agendado = {
            "id": uuid.uuid4(),
            "usuario_id": usuario_id,
            "email": email,
            "organizacoes": organizacoes,
            "agendada_para": quando,
        }
        return self.agendado

    def cancelar(self, usuario_id: UUID) -> bool:
        return True

    def vencidas(self, limite: int = 20) -> list[dict[str, Any]]:
        return [self.agendado] if self.agendado else []

    def excluir_organizacao(self, organizacao_id: UUID) -> list[tuple[str, str]]:
        self.excluidas.append(organizacao_id)
        return [("brutos", f"{organizacao_id}/a.jdl")]

    def excluir_titular(self, usuario_id: UUID, email: str | None) -> None:
        self.titular_excluido = True

    def concluir(self, pedido_id: UUID, erro: str | None = None) -> None:
        self.concluidos.append((pedido_id, erro))


class StorageFalso:
    def __init__(self) -> None:
        self.apagados: list[str] = []

    def apagar(self, bucket: str, caminho: str) -> None:
        self.apagados.append(f"{bucket}/{caminho}")


def _org(papel: str, outros: int, donos: int) -> dict[str, Any]:
    return {
        "organizacao_id": uuid.uuid4(),
        "nome": "Faz",
        "papel": papel,
        "outros_membros": outros,
        "outros_donos": donos,
    }


def test_classificacao() -> None:
    assert classificar(_org("owner", 0, 0)) == "excluida"
    assert classificar(_org("owner", 2, 0)) == "bloqueia"
    assert classificar(_org("owner", 2, 1)) == "sai"
    assert classificar(_org("leitor", 3, 1)) == "sai"


def test_exige_confirmacao_e_bloqueia_dono_unico() -> None:
    quem = Principal(usuario_id=uuid.uuid4(), email="a@b.com")
    with pytest.raises(Invalido):
        ServicoTitular(RepoFalso([]), StorageFalso()).solicitar_exclusao(quem, "ok")
    with pytest.raises(Conflito):
        ServicoTitular(RepoFalso([_org("owner", 1, 0)]), StorageFalso()).solicitar_exclusao(
            quem, "EXCLUIR"
        )


def test_executa_apagando_so_as_organizacoes_do_titular() -> None:
    sozinha, compartilhada = _org("owner", 0, 0), _org("gestor", 2, 1)
    repo, storage = RepoFalso([sozinha, compartilhada]), StorageFalso()
    servico = ServicoTitular(repo, storage, carencia_dias=7)
    pedido = servico.solicitar_exclusao(Principal(uuid.uuid4(), "a@b.com"), " excluir ")
    assert pedido["organizacoes"] == [sozinha["organizacao_id"]]
    assert servico.executar_vencidas() == 1
    assert repo.excluidas == [sozinha["organizacao_id"]]
    assert storage.apagados == [f"brutos/{sozinha['organizacao_id']}/a.jdl"]
    assert repo.titular_excluido and repo.concluidos[0][1] is None


def test_evento_de_acesso_so_para_a_api() -> None:
    base = {"type": "http", "method": "GET", "client": ("200.1.2.3", 1), "state": {}}
    assert evento_acesso({**base, "path": "/health"}, 200, "r") is None
    ev = evento_acesso({**base, "path": "/api/v1/me", "state": {"usuario_id": "u"}}, 200, "r")
    assert ev is not None and ev["ip"] == "200.1.2.3" and ev["usuario_id"] == "u"
