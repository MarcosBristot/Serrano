"""Site institucional: formulário público "Solicitar demonstração"."""

from __future__ import annotations

import hashlib

from fastapi import APIRouter, Request, status
from pydantic import BaseModel, EmailStr, Field

from sistemacampero.interfaces.api.deps import ContainerDep

router = APIRouter(tags=["site"])


class ContatoIn(BaseModel):
    nome: str = Field(min_length=2, max_length=120)
    email: EmailStr
    telefone: str | None = Field(None, max_length=40)
    fazenda: str | None = Field(None, max_length=160)
    hectares: int | None = Field(None, ge=0, le=10_000_000)
    maquinas: int | None = Field(None, ge=0, le=100_000)
    mensagem: str | None = Field(None, max_length=2000)
    origem: str = Field("site", max_length=60)
    # Armadilha para robôs: o campo fica escondido no site; pessoas não o preenchem.
    website: str | None = Field(None, max_length=200)


@router.post("/contatos", status_code=status.HTTP_202_ACCEPTED)
def solicitar_demonstracao(c: ContainerDep, request: Request, corpo: ContatoIn) -> dict[str, str]:
    """Público (sem login). Limitado por IP no middleware de proteção."""
    if corpo.website:  # robô: responde igual, não grava
        return {"status": "recebido"}
    assert c.contatos is not None
    ip = request.client.host if request.client else None
    ip_hash = hashlib.sha256(ip.encode()).hexdigest()[:24] if ip else None
    dados = corpo.model_dump(exclude={"website"})
    dados["email"] = dados["email"].lower()
    c.contatos.registrar(dados, ip_hash)
    return {"status": "recebido"}
