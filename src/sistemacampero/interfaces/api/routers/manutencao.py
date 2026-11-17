"""Manutenção pelo horímetro: planos por máquina, registro do que foi feito e pendências."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field

from sistemacampero.application.manutencao import ServicoManutencao
from sistemacampero.domain.tenancy import ContextoOrganizacao, Permissao
from sistemacampero.interfaces.api.deps import ContainerDep, exigir

router = APIRouter(tags=["manutenção"])
LerDep = Annotated[ContextoOrganizacao, Depends(exigir(Permissao.LER))]
OperarDep = Annotated[ContextoOrganizacao, Depends(exigir(Permissao.OPERAR))]


def _servico(c: ContainerDep) -> ServicoManutencao:
    assert c.manutencao is not None
    return c.manutencao


ServicoDep = Annotated[ServicoManutencao, Depends(_servico)]


class PlanoOut(BaseModel):
    id: UUID
    nome: str
    intervalo_h: float
    ultima_h: float | None
    ultima_em: date | None
    proxima_h: float | None
    faltam_h: float | None
    situacao: Literal["em_dia", "proxima", "vencida", "sem_referencia"]
    dias_trabalho: float | None


class FeitaOut(BaseModel):
    id: UUID
    nome: str
    horimetro_h: float
    feita_em: date
    custo_rs: float | None
    observacao: str | None


class SituacaoOut(BaseModel):
    horimetro_h: float | None
    fonte: Literal["monitor", "informado"] | None
    em: datetime | None
    uso_h_dia: float | None
    planos: list[PlanoOut]
    historico: list[FeitaOut]


class PendenciaOut(BaseModel):
    maquina_id: UUID
    serial: str
    apelido: str | None
    modelo: str | None
    horimetro_h: float | None
    id: UUID
    nome: str
    faltam_h: float | None
    situacao: Literal["proxima", "vencida"]
    dias_trabalho: float | None


class PlanoIn(BaseModel):
    nome: str = Field(min_length=2, max_length=120)
    intervalo_h: float = Field(gt=0, le=20_000)
    ultima_h: float | None = Field(default=None, ge=0, description="horímetro da última vez")


class PlanoPatch(BaseModel):
    nome: str | None = Field(default=None, min_length=2, max_length=120)
    intervalo_h: float | None = Field(default=None, gt=0, le=20_000)
    ultima_h: float | None = Field(default=None, ge=0)
    ativo: bool | None = None


class FeitaIn(BaseModel):
    horimetro_h: float = Field(ge=0)
    feita_em: date
    custo_rs: float | None = Field(default=None, ge=0)
    observacao: str | None = Field(default=None, max_length=500)


class HorimetroIn(BaseModel):
    horimetro_h: float = Field(ge=0, le=200_000)


class ModeloIn(BaseModel):
    tipo: Literal["trator", "colheitadeira", "pulverizador"]


@router.get("/maquinas/{maquina_id}/manutencao", response_model=SituacaoOut)
def situacao(servico: ServicoDep, ctx: LerDep, maquina_id: UUID) -> dict[str, Any]:
    return servico.situacao(ctx.organizacao_id, maquina_id)


@router.post("/maquinas/{maquina_id}/manutencao/modelo")
def aplicar_modelo(
    servico: ServicoDep, ctx: OperarDep, maquina_id: UUID, corpo: ModeloIn
) -> dict[str, int]:
    """Cria os planos sugeridos para o tipo de máquina (contando do horímetro atual)."""
    return {"criados": servico.aplicar_modelo(ctx.organizacao_id, maquina_id, corpo.tipo)}


@router.post("/maquinas/{maquina_id}/manutencao/planos", status_code=status.HTTP_201_CREATED)
def criar_plano(
    servico: ServicoDep, ctx: OperarDep, maquina_id: UUID, corpo: PlanoIn
) -> dict[str, UUID]:
    ident = servico.criar_plano(
        ctx.organizacao_id, maquina_id, corpo.nome, corpo.intervalo_h, corpo.ultima_h
    )
    return {"id": ident}


@router.put("/maquinas/{maquina_id}/horimetro", status_code=status.HTTP_204_NO_CONTENT)
def informar_horimetro(
    servico: ServicoDep, ctx: OperarDep, maquina_id: UUID, corpo: HorimetroIn
) -> Response:
    """Leitura do painel, para máquina cujo monitor não grava o horímetro."""
    servico.informar_horimetro(ctx.organizacao_id, maquina_id, corpo.horimetro_h)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/manutencao/planos/{plano_id}", status_code=status.HTTP_204_NO_CONTENT)
def editar_plano(
    servico: ServicoDep, ctx: OperarDep, plano_id: UUID, corpo: PlanoPatch
) -> Response:
    servico.editar_plano(ctx.organizacao_id, plano_id, corpo.model_dump(exclude_unset=True))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/manutencao/planos/{plano_id}/feita", status_code=status.HTTP_204_NO_CONTENT)
def registrar_feita(
    servico: ServicoDep, ctx: OperarDep, plano_id: UUID, corpo: FeitaIn
) -> Response:
    """Registra no histórico e reinicia a contagem a partir desse horímetro."""
    servico.registrar_feita(
        ctx.organizacao_id,
        plano_id,
        corpo.horimetro_h,
        corpo.feita_em,
        corpo.custo_rs,
        corpo.observacao,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class ResumoSemanalOut(BaseModel):
    inicio: date
    fim: date
    texto: str
    acoes: list[str]
    trabalho_h: float
    litros: float
    custo_rs: float | None
    area_ha: float
    sacas: float


@router.get("/resumo-semanal", response_model=ResumoSemanalOut, tags=["resumo"])
def resumo_semanal(c: ContainerDep, ctx: LerDep, fim: date | None = None) -> dict[str, Any]:
    """O texto da semana (7 dias até ``fim``, ontem por padrão), pronto para o WhatsApp."""
    assert c.resumo_semanal is not None
    return c.resumo_semanal.montar(ctx.organizacao_id, fim)


@router.get("/manutencao/pendencias", response_model=list[PendenciaOut])
def pendencias(servico: ServicoDep, ctx: LerDep) -> list[dict[str, Any]]:
    """Itens vencidos ou próximos de toda a frota, o mais urgente primeiro."""
    return servico.pendencias(ctx.organizacao_id)
