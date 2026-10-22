from __future__ import annotations

import uuid

import pytest

from sistemacampero.application.tenancy import ServicoTenancy
from sistemacampero.domain.errors import Conflito, Invalido, Proibido
from sistemacampero.domain.tenancy import (
    ContextoOrganizacao,
    Papel,
    Permissao,
    Principal,
    gerar_slug,
    papel_permite,
    validar_slug,
)
from tests.conftest import RepositorioEmMemoria


@pytest.fixture
def servico(repo: RepositorioEmMemoria) -> ServicoTenancy:
    return ServicoTenancy(repo)


def test_slug_remove_acentos_e_pontuacao() -> None:
    assert gerar_slug("Fazenda São João Ltda.") == "fazenda-sao-joao-ltda"
    assert gerar_slug("  Agro   Coxilha--Grande  ") == "agro-coxilha-grande"


@pytest.mark.parametrize("slug", ["ab", "Maiuscula", "com espaco", "-hifen", "a" * 61])
def test_slug_invalido(slug: str) -> None:
    with pytest.raises(Invalido):
        validar_slug(slug)


def test_permissoes_por_papel() -> None:
    assert papel_permite(Papel.OWNER, Permissao.ADMINISTRAR)
    assert papel_permite(Papel.GESTOR, Permissao.OPERAR)
    assert not papel_permite(Papel.GESTOR, Permissao.ADMINISTRAR)
    assert papel_permite(Papel.LEITOR, Permissao.EXPORTAR)
    assert not papel_permite(Papel.LEITOR, Permissao.OPERAR)
    with pytest.raises(Proibido) as exc:
        ContextoOrganizacao(uuid.uuid4(), Papel.LEITOR).exigir(Permissao.OPERAR)
    assert exc.value.codigo == "PAPEL_SEM_PERMISSAO"


def test_org_unica_dispensa_header(servico: ServicoTenancy, repo: RepositorioEmMemoria) -> None:
    uid = uuid.uuid4()
    org = repo.adicionar("Agro Um", uid, Papel.GESTOR)
    ctx = servico.resolver_organizacao(Principal(uid), None)
    assert ctx == ContextoOrganizacao(org, Papel.GESTOR)


def test_varias_orgs_exigem_header(servico: ServicoTenancy, repo: RepositorioEmMemoria) -> None:
    uid = uuid.uuid4()
    repo.adicionar("Agro Um", uid, Papel.GESTOR)
    org2 = repo.adicionar("Agro Dois", uid, Papel.LEITOR)
    with pytest.raises(Invalido) as exc:
        servico.resolver_organizacao(Principal(uid), None)
    assert exc.value.codigo == "ORGANIZACAO_AMBIGUA"
    assert servico.resolver_organizacao(Principal(uid), org2).papel == Papel.LEITOR


def test_org_alheia_e_proibida(servico: ServicoTenancy, repo: RepositorioEmMemoria) -> None:
    dono, intruso = uuid.uuid4(), uuid.uuid4()
    org = repo.adicionar("Agro Um", dono, Papel.OWNER)
    repo.adicionar("Agro Intruso", intruso, Papel.OWNER)
    with pytest.raises(Proibido) as exc:
        servico.resolver_organizacao(Principal(intruso), org)
    assert exc.value.codigo == "ORGANIZACAO_PROIBIDA"
    # Org inexistente: mesma resposta (não revela existência).
    with pytest.raises(Proibido) as exc:
        servico.resolver_organizacao(Principal(intruso), uuid.uuid4())
    assert exc.value.codigo == "ORGANIZACAO_PROIBIDA"


def test_sem_organizacao(servico: ServicoTenancy) -> None:
    with pytest.raises(Proibido) as exc:
        servico.resolver_organizacao(Principal(uuid.uuid4()), None)
    assert exc.value.codigo == "SEM_ORGANIZACAO"


def test_cria_primeira_organizacao(servico: ServicoTenancy, repo: RepositorioEmMemoria) -> None:
    uid = uuid.uuid4()
    org = servico.criar_primeira_organizacao(Principal(uid), "  Fazenda Cabaña  ")
    assert org.nome == "Fazenda Cabaña"
    assert org.slug == "fazenda-cabana"
    assert repo.membros[(org.id, uid)] == Papel.OWNER
    with pytest.raises(Conflito) as exc:
        servico.criar_primeira_organizacao(Principal(uid), "Outra")
    assert exc.value.codigo == "JA_TEM_ORGANIZACAO"


def test_slug_duplicado(servico: ServicoTenancy) -> None:
    servico.criar_primeira_organizacao(Principal(uuid.uuid4()), "Agro Sul")
    with pytest.raises(Conflito) as exc:
        servico.criar_primeira_organizacao(Principal(uuid.uuid4()), "Agro Sul")
    assert exc.value.codigo == "SLUG_EM_USO"
