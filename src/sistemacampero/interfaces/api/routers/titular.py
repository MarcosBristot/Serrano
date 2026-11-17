"""Meus dados (LGPD art. 18): exportar e excluir a conta. Só exige login, sem organização."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field

from sistemacampero.application.titular import ServicoTitular
from sistemacampero.interfaces.api.deps import ContainerDep, PrincipalDep

router = APIRouter(prefix="/eu", tags=["meus dados"])


class ExclusaoIn(BaseModel):
    confirmacao: str = Field(max_length=40, description='Digite "EXCLUIR"')


def _servico(c: ContainerDep) -> ServicoTitular:
    assert c.titular is not None
    return c.titular


@router.get("/dados")
def exportar(c: ContainerDep, quem: PrincipalDep) -> Response:
    """Cópia dos seus dados pessoais em JSON (portabilidade)."""
    corpo = json.dumps(_servico(c).exportar(quem), ensure_ascii=False, indent=2, default=str)
    nome = f"serrano_meus_dados_{date.today().isoformat()}.json"
    return Response(
        corpo,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


@router.get("/exclusao")
def situacao(c: ContainerDep, quem: PrincipalDep) -> dict[str, Any]:
    """Pedido de exclusão em andamento e o que acontece com cada organização."""
    return _servico(c).situacao(quem)


@router.post("/exclusao", status_code=status.HTTP_202_ACCEPTED)
def solicitar(c: ContainerDep, quem: PrincipalDep, corpo: ExclusaoIn) -> dict[str, Any]:
    """Agenda a exclusão da conta. Pode ser cancelada até a data agendada."""
    return _servico(c).solicitar_exclusao(quem, corpo.confirmacao)


@router.delete("/exclusao", status_code=status.HTTP_204_NO_CONTENT)
def cancelar(c: ContainerDep, quem: PrincipalDep) -> Response:
    _servico(c).cancelar(quem)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
