"""Fixtures comuns: configuração sem ambiente, dublês e emissão de JWT de teste."""

from __future__ import annotations

import time
import uuid
from typing import Any
from uuid import UUID

import jwt
import pytest

from sistemacampero.application.tenancy import ServicoTenancy
from sistemacampero.domain.errors import Conflito
from sistemacampero.domain.tenancy import Organizacao, Papel, Vinculo
from sistemacampero.infrastructure.config import Settings
from sistemacampero.infrastructure.container import Container
from sistemacampero.infrastructure.security.jwt import VerificadorJwtSupabase

SEGREDO = "segredo-de-teste-com-pelo-menos-32-bytes!"
ISSUER = "https://projeto-teste.supabase.co/auth/v1"


class RepositorioEmMemoria:
    def __init__(self) -> None:
        self.orgs: dict[UUID, Organizacao] = {}
        self.membros: dict[tuple[UUID, UUID], Papel] = {}

    def vinculos_do_usuario(self, usuario_id: UUID) -> list[Vinculo]:
        return sorted(
            (
                Vinculo(org_id, self.orgs[org_id].nome, self.orgs[org_id].slug, papel)
                for (org_id, uid), papel in self.membros.items()
                if uid == usuario_id
            ),
            key=lambda v: v.organizacao_nome,
        )

    def criar_organizacao(
        self, org: Organizacao, dono_id: UUID, plano_codigo: str, dias_trial: int
    ) -> None:
        if any(o.slug == org.slug for o in self.orgs.values()):
            raise Conflito("Slug já está em uso.", codigo="SLUG_EM_USO")
        self.orgs[org.id] = org
        self.membros[(org.id, dono_id)] = Papel.OWNER

    def adicionar(self, nome: str, usuario_id: UUID, papel: Papel) -> UUID:
        org = Organizacao(id=uuid.uuid4(), nome=nome, slug=nome.lower().replace(" ", "-"))
        self.orgs[org.id] = org
        self.membros[(org.id, usuario_id)] = papel
        return org.id


class ProntidaoFalsa:
    def __init__(self) -> None:
        self.checks = {"banco": "ok"}

    def verificar(self) -> dict[str, str]:
        return dict(self.checks)


def emitir_token(
    sub: UUID | str,
    *,
    email: str | None = "gestor@example.com",
    role: str = "authenticated",
    aud: str = "authenticated",
    iss: str = ISSUER,
    exp_em_s: int = 3600,
    segredo: str = SEGREDO,
    **extra: Any,
) -> str:
    agora = int(time.time())
    claims: dict[str, Any] = {
        "sub": str(sub),
        "role": role,
        "aud": aud,
        "iss": iss,
        "iat": agora,
        "exp": agora + exp_em_s,
        **extra,
    }
    if email:
        claims["email"] = email
    return jwt.encode(claims, segredo, algorithm="HS256")


@pytest.fixture
def settings() -> Settings:
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        ambiente="test",
        database_url="postgresql://ninguem@localhost:1/nada",
        supabase_url="https://projeto-teste.supabase.co",
        supabase_jwt_secret=SEGREDO,
        log_json=False,
    )


@pytest.fixture
def repo() -> RepositorioEmMemoria:
    return RepositorioEmMemoria()


@pytest.fixture
def container(settings: Settings, repo: RepositorioEmMemoria) -> Container:
    return Container(
        settings=settings,
        tenancy=ServicoTenancy(repo),
        verificador_token=VerificadorJwtSupabase(
            audience="authenticated", issuer=ISSUER, jwks=None, segredo_hs256=SEGREDO
        ),
        prontidao=ProntidaoFalsa(),
    )
