"""Alertas (ciclo de vida, comentários), limiares por organização, reanálise e
destinos de notificação."""

from __future__ import annotations

import base64
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, Field, HttpUrl

from sistemacampero.domain.alertas import AcaoAlerta
from sistemacampero.domain.errors import Invalido
from sistemacampero.domain.services.rules import ConfigRegras
from sistemacampero.domain.tenancy import ContextoOrganizacao, Permissao
from sistemacampero.infrastructure.persistence.alertas import PostgresRepositorioAlertas
from sistemacampero.interfaces.api.deps import ContainerDep, exigir

router = APIRouter(tags=["alertas"])

LerDep = Annotated[ContextoOrganizacao, Depends(exigir(Permissao.LER))]
OperarDep = Annotated[ContextoOrganizacao, Depends(exigir(Permissao.OPERAR))]


def _repo(c: ContainerDep) -> PostgresRepositorioAlertas:
    assert c.repo_alertas is not None
    return c.repo_alertas


RepoDep = Annotated[PostgresRepositorioAlertas, Depends(_repo)]
Severidade = Literal["info", "atencao", "alto"]


class ComentarioOut(BaseModel):
    id: UUID
    autor_id: UUID | None
    texto: str
    criado_em: datetime


class AlertaOut(BaseModel):
    id: UUID
    sessao_id: UUID | None
    maquina_id: UUID | None
    serial: str | None
    apelido: str | None
    talhao_id: UUID | None
    talhao_nome: str | None
    tipo: str
    severidade: str
    status: str
    versao_regras: str
    inicio: datetime | None
    fim: datetime | None
    valor: float | None
    limiar: float | None
    mensagem: str
    detalhes: dict[str, Any]
    reconhecido_por: UUID | None
    reconhecido_em: datetime | None
    resolvido_por: UUID | None
    resolvido_em: datetime | None
    criado_em: datetime
    atualizado_em: datetime


class AlertaDetalheOut(AlertaOut):
    comentarios: list[ComentarioOut]


class PaginaAlertas(BaseModel):
    itens: list[AlertaOut]
    next_cursor: str | None


class ComentarioIn(BaseModel):
    texto: str = Field(min_length=1, max_length=4000)


@router.get("/alerts", response_model=PaginaAlertas)
def listar(
    repo: RepoDep,
    ctx: LerDep,
    status_: Annotated[
        Literal["aberto", "reconhecido", "resolvido", "invalidado"] | None, Query(alias="status")
    ] = None,
    tipo: str | None = None,
    severidade: Severidade | None = None,
    maquina_id: UUID | None = None,
    sessao_id: UUID | None = None,
    talhao_id: UUID | None = None,
    inicio: datetime | None = None,
    fim: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    cursor: str | None = None,
) -> PaginaAlertas:
    c = None
    if cursor:
        try:
            ts, ident = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
            c = (ts, UUID(ident))
        except (ValueError, UnicodeDecodeError):
            raise Invalido("Cursor inválido.", codigo="CURSOR_INVALIDO") from None
    f = {
        "status": status_,
        "tipo": tipo,
        "severidade": severidade,
        "maquina_id": maquina_id,
        "sessao_id": sessao_id,
        "talhao_id": talhao_id,
        "inicio": inicio,
        "fim": fim,
    }
    linhas = repo.listar(ctx.organizacao_id, f, limit + 1, c)
    proximo = None
    if len(linhas) > limit:
        linhas = linhas[:limit]
        u = linhas[-1]
        proximo = base64.urlsafe_b64encode(
            f"{u['criado_em'].isoformat()}|{u['id']}".encode()
        ).decode()
    return PaginaAlertas(itens=[AlertaOut.model_validate(x) for x in linhas], next_cursor=proximo)


@router.get("/alerts/{alerta_id}", response_model=AlertaDetalheOut)
def obter(repo: RepoDep, ctx: LerDep, alerta_id: UUID) -> dict[str, Any]:
    return repo.obter(ctx.organizacao_id, alerta_id)


def _acao(acao: AcaoAlerta):  # type: ignore[no-untyped-def]
    def rota(c: ContainerDep, ctx: OperarDep, alerta_id: UUID) -> dict[str, Any]:
        assert c.alertas is not None
        return c.alertas.mudar_status(ctx.organizacao_id, alerta_id, acao, ctx.usuario_id)

    return rota


for _a in AcaoAlerta:
    router.add_api_route(
        f"/alerts/{{alerta_id}}/{_a.value}",
        _acao(_a),
        methods=["POST"],
        response_model=AlertaDetalheOut,
        summary=f"{_a.value.capitalize()} alerta",
    )


@router.post("/alerts/{alerta_id}/comentarios", response_model=ComentarioOut, status_code=201)
def comentar(repo: RepoDep, ctx: OperarDep, alerta_id: UUID, corpo: ComentarioIn) -> dict[str, Any]:
    return repo.comentar(ctx.organizacao_id, alerta_id, ctx.usuario_id, corpo.texto)


# ------------------------------------------------------------------ regras
class RegrasIO(BaseModel):
    ociosidade_min_minutos: float = Field(
        20.0, description="motor ligado e parado por mais que isso"
    )
    ociosidade_tolerancia_s: int = 30
    vazao_desvio: float = Field(0.30, description="fração acima da linha de base")
    vazao_janela_min: int = 10
    vazao_min_amostras: int = 120
    gps_velocidade_max_kmh: float = 40.0
    gps_salto_min_m: float = 50.0
    l_ha_desvio: float = 0.30
    l_ha_min_sessoes: int = 5


class RegrasOut(RegrasIO):
    versao: str


def _regras_out(cfg: ConfigRegras) -> RegrasOut:
    from dataclasses import asdict

    return RegrasOut(**asdict(cfg), versao=cfg.versao)


@router.get("/config/regras", response_model=RegrasOut, tags=["regras"])
def ler_regras(c: ContainerDep, ctx: LerDep) -> RegrasOut:
    assert c.alertas is not None
    return _regras_out(c.alertas.regras(ctx.organizacao_id))


@router.put("/config/regras", response_model=RegrasOut, tags=["regras"])
def salvar_regras(c: ContainerDep, ctx: OperarDep, corpo: RegrasIO) -> RegrasOut:
    """Vale para os próximos processamentos; para o histórico, ``POST /analysis/run``."""
    assert c.alertas is not None
    return _regras_out(
        c.alertas.salvar_regras(ctx.organizacao_id, corpo.model_dump(), ctx.usuario_id)
    )


@router.post("/analysis/run", status_code=202, tags=["regras"])
def reanalisar(c: ContainerDep, ctx: OperarDep) -> dict[str, int]:
    """Reprocessa todas as sessões (a partir do bruto) com as regras atuais."""
    assert c.alertas is not None
    return {"sessoes_reenfileiradas": c.alertas.reprocessar(ctx.organizacao_id)}


# ------------------------------------------------------------------ destinos
class DestinoIn(BaseModel):
    tipo: Literal["email", "webhook", "whatsapp"]
    destino: str = Field(min_length=3, max_length=500, description="e-mail, URL ou telefone")
    segredo: str | None = Field(
        default=None, min_length=16, max_length=200, description="webhook: HMAC"
    )
    severidade_minima: Severidade = "atencao"
    ativo: bool = True


class DestinoPatch(BaseModel):
    destino: str | None = Field(default=None, min_length=3, max_length=500)
    severidade_minima: Severidade | None = None
    ativo: bool | None = None


class DestinoOut(BaseModel):
    id: UUID
    tipo: str
    destino: str
    severidade_minima: str
    ativo: bool
    tem_segredo: bool
    criado_em: datetime
    atualizado_em: datetime


def _validar_destino(tipo: str, destino: str) -> None:
    if tipo == "email" and ("@" not in destino or " " in destino):
        raise Invalido("E-mail inválido.", codigo="DESTINO_INVALIDO")
    if tipo == "webhook":
        url = HttpUrl(destino)
        if url.scheme != "https":
            raise Invalido("Webhook precisa ser https.", codigo="DESTINO_INVALIDO")


@router.get("/destinos-notificacao", response_model=list[DestinoOut], tags=["notificações"])
def listar_destinos(repo: RepoDep, ctx: LerDep) -> list[dict[str, Any]]:
    return repo.destinos(ctx.organizacao_id)


@router.post(
    "/destinos-notificacao", response_model=DestinoOut, status_code=201, tags=["notificações"]
)
def criar_destino(
    c: ContainerDep, repo: RepoDep, ctx: OperarDep, corpo: DestinoIn
) -> dict[str, Any]:
    _validar_destino(corpo.tipo, corpo.destino)
    dados = corpo.model_dump(exclude={"segredo"})
    if corpo.segredo:
        assert c.cifra is not None
        dados["segredo_cifrado"] = c.cifra.cifrar(corpo.segredo)
    return repo.criar_destino(ctx.organizacao_id, dados)


@router.patch("/destinos-notificacao/{ident}", response_model=DestinoOut, tags=["notificações"])
def editar_destino(
    repo: RepoDep, ctx: OperarDep, ident: UUID, corpo: DestinoPatch
) -> dict[str, Any]:
    dados = corpo.model_dump(exclude_unset=True)
    if "destino" in dados:
        atual = repo.destino_completo(ctx.organizacao_id, ident)
        _validar_destino(atual["tipo"], dados["destino"])
    return repo.atualizar_destino(ctx.organizacao_id, ident, dados)


@router.delete("/destinos-notificacao/{ident}", status_code=204, tags=["notificações"])
def apagar_destino(repo: RepoDep, ctx: OperarDep, ident: UUID) -> Response:
    repo.apagar_destino(ctx.organizacao_id, ident)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/destinos-notificacao/{ident}/teste", tags=["notificações"])
def testar_destino(c: ContainerDep, repo: RepoDep, ctx: OperarDep, ident: UUID) -> dict[str, Any]:
    """Envia agora um alerta fictício para este destino."""
    destino = repo.destino_completo(ctx.organizacao_id, ident)
    falso = {
        "id": "00000000-0000-0000-0000-000000000000",
        "tipo": "teste",
        "severidade": "info",
        "mensagem": "Teste de notificação do Sistema Campero.",
        "inicio": None,
    }
    assert c.notificador is not None
    try:
        c.notificador.enviar(falso, destino)
    except Exception as exc:
        return {"enviado": False, "erro": f"{type(exc).__name__}: {exc}"[:300]}
    return {"enviado": True, "erro": None}
