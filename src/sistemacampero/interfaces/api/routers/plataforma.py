"""Plano e assinatura, integrações (fontes de dados) e saúde dos dados da organização."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from sistemacampero.domain.errors import Invalido
from sistemacampero.domain.tenancy import ContextoOrganizacao, Permissao
from sistemacampero.infrastructure.persistence.plataforma import FRAGMENTO_S, PostgresPlataforma
from sistemacampero.interfaces.api.deps import ContainerDep, exigir

router = APIRouter(tags=["plataforma"])
LerDep = Annotated[ContextoOrganizacao, Depends(exigir(Permissao.LER))]
AdministrarDep = Annotated[ContextoOrganizacao, Depends(exigir(Permissao.ADMINISTRAR))]


def _repo(c: ContainerDep) -> PostgresPlataforma:
    assert c.plataforma is not None
    return c.plataforma


RepoDep = Annotated[PostgresPlataforma, Depends(_repo)]

SITUACOES_QUE_ENVIAM = {"trial", "ativa", None}


def exigir_assinatura_ativa(repo: PostgresPlataforma, org: UUID) -> None:
    """Teste vencido, assinatura vencida ou suspensa: os dados continuam visíveis, o envio não."""
    situacao = repo.situacao(org)
    if situacao in SITUACOES_QUE_ENVIAM:
        return
    raise Invalido(
        "O período de teste ou a assinatura terminou. Escolha um plano em Plano e assinatura "
        "para voltar a enviar pendrives; os dados já enviados continuam disponíveis.",
        codigo="ASSINATURA_INATIVA",
    )


# ------------------------------------------------------------------ plano e assinatura
class PlanoOut(BaseModel):
    codigo: str
    nome: str
    descricao: str
    max_maquinas: int
    preco_mensal_centavos: int
    preco_anual_centavos: int | None
    destaque: bool
    sob_consulta: bool
    recursos: list[str]


class UsoOut(BaseModel):
    maquinas: int
    envios: int
    armazenamento_bytes: int
    hectares: float
    usuarios: int


class PedidoAbertoOut(BaseModel):
    plano_codigo: str
    ciclo: str
    criado_em: datetime


class AssinaturaOut(BaseModel):
    plano_codigo: str
    plano_nome: str
    status: str
    situacao: str
    inicio: datetime
    fim: datetime | None
    dias_restantes: int | None
    max_maquinas: int
    uso: UsoOut
    pedido_aberto: PedidoAbertoOut | None
    planos: list[PlanoOut]


class PedidoIn(BaseModel):
    plano_codigo: str = Field(min_length=1, max_length=40)
    ciclo: Literal["mensal", "anual"] = "mensal"
    telefone: str | None = Field(default=None, max_length=40)
    mensagem: str | None = Field(default=None, max_length=2000)


class PedidoOut(BaseModel):
    id: UUID
    plano_codigo: str
    ciclo: str
    criado_em: datetime


@router.get("/assinatura", response_model=AssinaturaOut, summary="Plano atual, uso e planos")
def assinatura(repo: RepoDep, ctx: LerDep) -> dict[str, Any]:
    a = repo.assinatura(ctx.organizacao_id)
    fim: datetime | None = a["fim"]
    dias = None
    if fim is not None:
        dias = max(0, (fim - datetime.now(fim.tzinfo)).days)
    return {**a, "dias_restantes": dias, "planos": repo.planos()}


@router.post(
    "/assinatura/pedidos",
    response_model=PedidoOut,
    status_code=status.HTTP_201_CREATED,
    summary="Pede a contratação de um plano (a equipe Serrano entra em contato)",
)
def pedir_plano(repo: RepoDep, ctx: AdministrarDep, corpo: PedidoIn) -> dict[str, Any]:
    return repo.pedir(
        ctx.organizacao_id,
        ctx.usuario_id,
        corpo.plano_codigo,
        corpo.ciclo,
        (corpo.mensagem or "").strip() or None,
        (corpo.telefone or "").strip() or None,
    )


# ------------------------------------------------------------------ integrações
# O diferencial: dados de marcas e formatos diferentes num painel só. "ativa" é o que a
# Serrano já lê hoje; "roteiro" é o que está planejado (o painel mostra como "em breve").
CATALOGO: list[dict[str, Any]] = [
    {
        "id": "john_deere_gen4",
        "categoria": "monitor",
        "nome": "John Deere Gen4",
        "detalhe": "Monitores CommandCenter e 4640: arquivos .jdl do pendrive.",
        "status": "ativa",
    },
    {
        "id": "john_deere_gs3",
        "categoria": "monitor",
        "nome": "John Deere GreenStar 3",
        "detalhe": "Monitor 2630 das colheitadeiras: pasta GS3_2630 com produtividade e umidade.",
        "status": "ativa",
    },
    {
        "id": "isoxml",
        "categoria": "monitor",
        "nome": "ISOBUS (ISO 11783)",
        "detalhe": "TASKDATA.XML de terminais ISOBUS de várias marcas.",
        "status": "ativa",
    },
    {
        "id": "contornos",
        "categoria": "mapa",
        "nome": "Contornos de talhão",
        "detalhe": "Talhões gravados no monitor, shapefile (.zip), KML ou GeoJSON.",
        "status": "ativa",
    },
    {
        "id": "planilha",
        "categoria": "saida",
        "nome": "Planilhas (CSV)",
        "detalhe": "Exporte operações, máquinas e custos para o Excel ou para o seu ERP.",
        "status": "ativa",
    },
    {
        "id": "webhook",
        "categoria": "saida",
        "nome": "Webhook e e-mail",
        "detalhe": "Alertas enviados na hora para e-mail ou para outro sistema.",
        "status": "ativa",
    },
    {
        "id": "api",
        "categoria": "saida",
        "nome": "API REST",
        "detalhe": "Chaves de API para o seu sistema ler os dados da Serrano.",
        "status": "ativa",
    },
    {
        "id": "operations_center",
        "categoria": "nuvem",
        "nome": "John Deere Operations Center",
        "detalhe": "Dados direto da nuvem John Deere, sem pendrive.",
        "status": "roteiro",
    },
    {
        "id": "cnh",
        "categoria": "monitor",
        "nome": "Case IH e New Holland",
        "detalhe": "Monitores AFS e Intelliview (pasta do pendrive).",
        "status": "roteiro",
    },
    {
        "id": "fieldview",
        "categoria": "nuvem",
        "nome": "Climate FieldView",
        "detalhe": "Operações registradas pelo FieldView Drive.",
        "status": "roteiro",
    },
    {
        "id": "telemetria_nacional",
        "categoria": "nuvem",
        "nome": "Telemetria Stara e Jacto",
        "detalhe": "Máquinas nacionais conectadas.",
        "status": "roteiro",
    },
]


class IntegracaoOut(BaseModel):
    id: str
    categoria: str
    nome: str
    detalhe: str
    status: Literal["ativa", "roteiro"]
    em_uso: bool
    sessoes: int
    maquinas: int
    ultimo_dado: datetime | None
    ultimo_envio: datetime | None


@router.get(
    "/integracoes",
    response_model=list[IntegracaoOut],
    summary="Formatos e sistemas que a Serrano lê, com o que já chegou de cada um",
)
def integracoes(repo: RepoDep, ctx: LerDep) -> list[dict[str, Any]]:
    uso = {f["fonte"]: f for f in repo.fontes(ctx.organizacao_id)}
    saida = []
    for item in CATALOGO:
        f = uso.get(item["id"], {})
        saida.append(
            {
                **item,
                "em_uso": bool(f.get("sessoes")),
                "sessoes": f.get("sessoes", 0),
                "maquinas": f.get("maquinas", 0),
                "ultimo_dado": f.get("ultimo_dado"),
                "ultimo_envio": f.get("ultimo_envio"),
            }
        )
    return saida


# ------------------------------------------------------------------ saúde dos dados
class QualidadeOut(BaseModel):
    fragmento_s: int
    arquivos: dict[str, int]
    sessoes: dict[str, float | int | None]
    sobreposicao: dict[str, float]
    problemas: list[dict[str, Any]]
    motivos_vazios: list[dict[str, Any]]
    confiabilidade_pct: float | None


@router.get(
    "/qualidade",
    response_model=QualidadeOut,
    summary="O que foi aproveitado, descartado ou corrigido nos dados recebidos",
)
def qualidade(
    repo: RepoDep, ctx: LerDep, inicio: datetime | None = None, fim: datetime | None = None
) -> dict[str, Any]:
    q = repo.qualidade(ctx.organizacao_id, inicio, fim)
    s = q["sessoes"]
    motor = float(s["motor_h"] or 0)
    q["confiabilidade_pct"] = (
        round(100 * float(s["motor_h_confiavel"]) / motor, 1) if motor > 0 else None
    )
    q["sessoes"] = {k: (float(v) if v is not None else None) for k, v in s.items()}
    q["sobreposicao"] = {k: float(v) for k, v in q["sobreposicao"].items()}
    q["fragmento_s"] = FRAGMENTO_S
    return q
