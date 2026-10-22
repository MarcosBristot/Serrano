"""Cadastro (fazendas, talhões, máquinas, implementos, operadores) e sessões."""

from __future__ import annotations

import base64
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from pydantic import BaseModel, Field

from sistemacampero.domain.cadastro import OrigemContorno
from sistemacampero.domain.errors import Invalido
from sistemacampero.domain.tenancy import ContextoOrganizacao, Permissao
from sistemacampero.infrastructure.persistence.cadastro import (
    PostgresRepositorioCadastro,
    geojson,
)
from sistemacampero.interfaces.api.deps import ContainerDep, exigir

router = APIRouter(tags=["cadastro"])
sessoes = APIRouter(prefix="/sessions", tags=["sessões"])

LerDep = Annotated[ContextoOrganizacao, Depends(exigir(Permissao.LER))]
OperarDep = Annotated[ContextoOrganizacao, Depends(exigir(Permissao.OPERAR))]


def _repo(c: ContainerDep) -> PostgresRepositorioCadastro:
    assert c.cadastro is not None
    return c.cadastro


RepoDep = Annotated[PostgresRepositorioCadastro, Depends(_repo)]


# ------------------------------------------------------------------ esquemas
class FazendaIn(BaseModel):
    nome: str = Field(min_length=1, max_length=200)
    cliente_nome: str | None = Field(default=None, max_length=200)


class FazendaPatch(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=200)
    cliente_nome: str | None = Field(default=None, max_length=200)


class FazendaOut(BaseModel):
    id: UUID
    nome: str
    cliente_nome: str | None
    external_guid: str | None
    criado_em: datetime
    atualizado_em: datetime


class TalhaoIn(BaseModel):
    nome: str = Field(min_length=1, max_length=200)
    fazenda_id: UUID | None = None
    geometria: dict[str, Any] | None = Field(
        default=None, description="GeoJSON (Polygon/MultiPolygon/Feature/FeatureCollection)"
    )


class TalhaoPatch(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=200)
    fazenda_id: UUID | None = None
    ativo: bool | None = None


class TalhaoOut(BaseModel):
    id: UUID
    fazenda_id: UUID | None
    nome: str
    external_guid: str | None
    area_ha: float | None
    origem_contorno: str | None
    ativo: bool
    tem_contorno: bool
    criado_em: datetime
    atualizado_em: datetime
    geometria: dict[str, Any] | None = None
    sessoes_relocalizadas: int | None = None


class ContornoIn(BaseModel):
    geometria: dict[str, Any] = Field(description="GeoJSON; de FeatureCollection usa 'Exterior'")
    origem: OrigemContorno = OrigemContorno.DESENHO


class MaquinaPatch(BaseModel):
    apelido: str | None = Field(default=None, max_length=100)
    modelo: str | None = Field(default=None, max_length=100)
    ativa: bool | None = None


class MaquinaOut(BaseModel):
    id: UUID
    serial: str
    fabricante: str | None
    modelo: str | None
    tecnologia: str | None
    apelido: str | None
    ativa: bool
    primeira_atividade: datetime | None
    ultima_atividade: datetime | None
    criado_em: datetime
    atualizado_em: datetime
    arquivos_reabertos: int | None = None


class ImplementoIn(BaseModel):
    nome: str = Field(min_length=1, max_length=200)
    largura_m: float | None = Field(default=None, gt=0, lt=100)


class ImplementoPatch(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=200)
    largura_m: float | None = Field(default=None, gt=0, lt=100)


class ImplementoOut(BaseModel):
    id: UUID
    nome: str
    largura_m: float | None
    external_guid: str | None
    criado_em: datetime
    atualizado_em: datetime


class OperadorIn(BaseModel):
    nome: str = Field(min_length=1, max_length=200)


class OperadorPatch(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=200)
    ativo: bool | None = None


class OperadorOut(BaseModel):
    id: UUID
    nome: str
    external_guid: str | None
    ativo: bool
    criado_em: datetime
    atualizado_em: datetime


def _dados(modelo: BaseModel) -> dict[str, Any]:
    return modelo.model_dump(exclude_unset=True)


# ------------------------------------------------------------------ fazendas
@router.get("/fazendas", response_model=list[FazendaOut])
def listar_fazendas(repo: RepoDep, ctx: LerDep) -> list[dict[str, Any]]:
    return repo.listar(ctx.organizacao_id, "fazendas", {})


@router.post("/fazendas", response_model=FazendaOut, status_code=status.HTTP_201_CREATED)
def criar_fazenda(repo: RepoDep, ctx: OperarDep, corpo: FazendaIn) -> dict[str, Any]:
    return repo.criar(ctx.organizacao_id, "fazendas", _dados(corpo))


@router.patch("/fazendas/{ident}", response_model=FazendaOut)
def editar_fazenda(
    repo: RepoDep, ctx: OperarDep, ident: UUID, corpo: FazendaPatch
) -> dict[str, Any]:
    return repo.atualizar(ctx.organizacao_id, "fazendas", ident, _dados(corpo))


@router.delete("/fazendas/{ident}", status_code=status.HTTP_204_NO_CONTENT)
def apagar_fazenda(repo: RepoDep, ctx: OperarDep, ident: UUID) -> Response:
    repo.apagar(ctx.organizacao_id, "fazendas", ident)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------ talhões
def _talhao(linha: dict[str, Any]) -> dict[str, Any]:
    if linha.get("geometria") is not None:
        linha["geometria"] = geojson(linha["geometria"])
    return linha


@router.get("/talhoes", response_model=list[TalhaoOut])
def listar_talhoes(
    repo: RepoDep, ctx: LerDep, fazenda_id: UUID | None = None, ativo: bool | None = None
) -> list[dict[str, Any]]:
    return repo.listar(ctx.organizacao_id, "talhoes", {"fazenda_id": fazenda_id, "ativo": ativo})


@router.get("/talhoes/{ident}", response_model=TalhaoOut)
def obter_talhao(repo: RepoDep, ctx: LerDep, ident: UUID) -> dict[str, Any]:
    return _talhao(repo.obter(ctx.organizacao_id, "talhoes", ident, geometria=True))


@router.post("/talhoes", response_model=TalhaoOut, status_code=status.HTTP_201_CREATED)
def criar_talhao(c: ContainerDep, repo: RepoDep, ctx: OperarDep, corpo: TalhaoIn) -> dict[str, Any]:
    dados = _dados(corpo)
    geometria = dados.pop("geometria", None)
    talhao = repo.criar(ctx.organizacao_id, "talhoes", dados)
    if geometria is None:
        return talhao
    assert c.servico_cadastro is not None
    return _talhao(
        c.servico_cadastro.definir_contorno(
            ctx.organizacao_id, talhao["id"], geometria, OrigemContorno.DESENHO
        )
    )


@router.patch("/talhoes/{ident}", response_model=TalhaoOut)
def editar_talhao(repo: RepoDep, ctx: OperarDep, ident: UUID, corpo: TalhaoPatch) -> dict[str, Any]:
    return repo.atualizar(ctx.organizacao_id, "talhoes", ident, _dados(corpo))


@router.put("/talhoes/{ident}/contorno", response_model=TalhaoOut)
def definir_contorno(
    c: ContainerDep, ctx: OperarDep, ident: UUID, corpo: ContornoIn
) -> dict[str, Any]:
    """Desenhado no mapa ou GeoJSON. Reprocessa as sessões afetadas."""
    assert c.servico_cadastro is not None
    return _talhao(
        c.servico_cadastro.definir_contorno(
            ctx.organizacao_id, ident, corpo.geometria, corpo.origem
        )
    )


@router.put("/talhoes/{ident}/contorno/arquivo", response_model=TalhaoOut)
def enviar_contorno(
    c: ContainerDep,
    ctx: OperarDep,
    ident: UUID,
    arquivo: Annotated[UploadFile, File(description=".gjson do monitor ou .geojson")],
) -> dict[str, Any]:
    import json

    conteudo = arquivo.file.read(20 * 1024**2 + 1)
    if len(conteudo) > 20 * 1024**2:
        raise Invalido("Arquivo de contorno grande demais.", codigo="GEOMETRIA_INVALIDA")
    try:
        dados = json.loads(conteudo)
    except (ValueError, UnicodeDecodeError):
        raise Invalido("O arquivo não é GeoJSON.", codigo="GEOMETRIA_INVALIDA") from None
    assert c.servico_cadastro is not None
    return _talhao(
        c.servico_cadastro.definir_contorno(ctx.organizacao_id, ident, dados, OrigemContorno.UPLOAD)
    )


@router.delete("/talhoes/{ident}/contorno", response_model=TalhaoOut)
def remover_contorno(c: ContainerDep, ctx: OperarDep, ident: UUID) -> dict[str, Any]:
    assert c.servico_cadastro is not None
    return _talhao(c.servico_cadastro.definir_contorno(ctx.organizacao_id, ident, None))


@router.delete("/talhoes/{ident}", status_code=status.HTTP_204_NO_CONTENT)
def apagar_talhao(repo: RepoDep, ctx: OperarDep, ident: UUID) -> Response:
    repo.apagar(ctx.organizacao_id, "talhoes", ident)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------ máquinas
@router.get("/maquinas", response_model=list[MaquinaOut])
def listar_maquinas(repo: RepoDep, ctx: LerDep, ativa: bool | None = None) -> list[dict[str, Any]]:
    return repo.listar(ctx.organizacao_id, "maquinas", {"ativa": ativa})


@router.patch("/maquinas/{ident}", response_model=MaquinaOut)
def editar_maquina(
    c: ContainerDep, repo: RepoDep, ctx: OperarDep, ident: UUID, corpo: MaquinaPatch
) -> dict[str, Any]:
    """A máquina nasce no 1º arquivo do serial. Reativar respeita o limite do plano (409)."""
    dados = _dados(corpo)
    ativa = dados.pop("ativa", None)
    maquina = repo.atualizar(ctx.organizacao_id, "maquinas", ident, dados)
    if ativa is not None and ativa != maquina["ativa"]:
        assert c.servico_cadastro is not None
        maquina = c.servico_cadastro.ativar_maquina(ctx.organizacao_id, ident, ativa)
    return maquina


# ------------------------------------------------------------------ implementos
@router.get("/implementos", response_model=list[ImplementoOut])
def listar_implementos(repo: RepoDep, ctx: LerDep) -> list[dict[str, Any]]:
    return repo.listar(ctx.organizacao_id, "implementos", {})


@router.post("/implementos", response_model=ImplementoOut, status_code=status.HTTP_201_CREATED)
def criar_implemento(repo: RepoDep, ctx: OperarDep, corpo: ImplementoIn) -> dict[str, Any]:
    return repo.criar(ctx.organizacao_id, "implementos", _dados(corpo))


@router.patch("/implementos/{ident}", response_model=ImplementoOut)
def editar_implemento(
    repo: RepoDep, ctx: OperarDep, ident: UUID, corpo: ImplementoPatch
) -> dict[str, Any]:
    return repo.atualizar(ctx.organizacao_id, "implementos", ident, _dados(corpo))


@router.delete("/implementos/{ident}", status_code=status.HTTP_204_NO_CONTENT)
def apagar_implemento(repo: RepoDep, ctx: OperarDep, ident: UUID) -> Response:
    repo.apagar(ctx.organizacao_id, "implementos", ident)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------ operadores
@router.get("/operadores", response_model=list[OperadorOut])
def listar_operadores(
    repo: RepoDep, ctx: LerDep, ativo: bool | None = None
) -> list[dict[str, Any]]:
    return repo.listar(ctx.organizacao_id, "operadores", {"ativo": ativo})


@router.post("/operadores", response_model=OperadorOut, status_code=status.HTTP_201_CREATED)
def criar_operador(repo: RepoDep, ctx: OperarDep, corpo: OperadorIn) -> dict[str, Any]:
    return repo.criar(ctx.organizacao_id, "operadores", _dados(corpo))


@router.patch("/operadores/{ident}", response_model=OperadorOut)
def editar_operador(
    repo: RepoDep, ctx: OperarDep, ident: UUID, corpo: OperadorPatch
) -> dict[str, Any]:
    return repo.atualizar(ctx.organizacao_id, "operadores", ident, _dados(corpo))


# ------------------------------------------------------------------ sessões
class SessaoOut(BaseModel):
    id: UUID
    arquivo_bruto_id: UUID
    maquina_id: UUID
    serial: str
    apelido: str | None
    implemento_id: UUID | None
    operador_id: UUID | None
    talhao_id: UUID | None
    talhao_nome: str | None
    talhao_origem: str
    talhao_confianca: float | None
    operacao: str | None
    inicio: datetime
    fim: datetime
    n_amostras: int
    qualidade_score: int | None
    motor_h: float | None
    trabalho_h: float | None
    ocioso_h: float | None
    litros_integral: float | None
    area_cobertura_ha: float | None
    area_estimada_ha: float | None
    l_ha: float | None
    ha_h: float | None
    cobertura_gps: float | None


class SessaoDetalheOut(SessaoOut):
    qualidade: dict[str, Any] | None
    adapter: str
    adapter_versao: str
    firmware: str | None
    sobreposicao_pct: float | None
    area_metodo: str | None
    delta_horimetro_h: float | None
    litros_contador: float | None
    distancia_trabalho_km: float | None
    velocidade_media: float | None
    lph_trabalho: float | None
    lph_ocioso: float | None


class PaginaSessoes(BaseModel):
    itens: list[SessaoOut]
    next_cursor: str | None


class SessaoPatch(BaseModel):
    talhao_id: UUID | None = Field(
        default=None, description="Talhão manual; null volta para a localização automática"
    )
    operador_id: UUID | None = None


class SessaoCorrigidaOut(BaseModel):
    sessao: SessaoDetalheOut
    reprocessamento_agendado: bool


def _cursor(valor: str | None) -> tuple[str, UUID] | None:
    if not valor:
        return None
    try:
        ts, ident = base64.urlsafe_b64decode(valor.encode()).decode().split("|")
        return ts, UUID(ident)
    except (ValueError, UnicodeDecodeError):
        raise Invalido("Cursor inválido.", codigo="CURSOR_INVALIDO") from None


@sessoes.get("", response_model=PaginaSessoes)
def listar_sessoes(
    repo: RepoDep,
    ctx: LerDep,
    maquina_id: UUID | None = None,
    talhao_id: UUID | None = None,
    operacao: str | None = None,
    inicio: datetime | None = None,
    fim: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    cursor: str | None = None,
) -> PaginaSessoes:
    filtros = {
        "maquina_id": maquina_id,
        "talhao_id": talhao_id,
        "operacao": operacao,
        "inicio": inicio,
        "fim": fim,
    }
    linhas = repo.listar_sessoes(ctx.organizacao_id, filtros, limit + 1, _cursor(cursor))
    proximo = None
    if len(linhas) > limit:
        ultimo = linhas[limit - 1]
        proximo = base64.urlsafe_b64encode(
            f"{ultimo['inicio'].isoformat()}|{ultimo['id']}".encode()
        ).decode()
        linhas = linhas[:limit]
    return PaginaSessoes(itens=[SessaoOut.model_validate(x) for x in linhas], next_cursor=proximo)


@sessoes.get("/{sessao_id}", response_model=SessaoDetalheOut)
def obter_sessao(repo: RepoDep, ctx: LerDep, sessao_id: UUID) -> dict[str, Any]:
    return repo.obter_sessao(ctx.organizacao_id, sessao_id)


@sessoes.patch("/{sessao_id}", response_model=SessaoCorrigidaOut)
def corrigir_sessao(
    c: ContainerDep, repo: RepoDep, ctx: OperarDep, sessao_id: UUID, corpo: SessaoPatch
) -> SessaoCorrigidaOut:
    """Talhão manual nunca é sobrescrito; área e L/ha são refeitos com o novo talhão."""
    assert c.servico_cadastro is not None
    n = c.servico_cadastro.corrigir_sessao(ctx.organizacao_id, sessao_id, _dados(corpo))
    return SessaoCorrigidaOut(
        sessao=SessaoDetalheOut.model_validate(repo.obter_sessao(ctx.organizacao_id, sessao_id)),
        reprocessamento_agendado=n > 0,
    )
