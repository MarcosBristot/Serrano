"""Schema, privilégios e RLS no PostGIS real, executando como cada papel."""

from __future__ import annotations

import uuid
from typing import Any

import psycopg
import psycopg.errors
import pytest

from sistemacampero.domain.errors import Conflito
from sistemacampero.domain.tenancy import Organizacao, Papel
from sistemacampero.infrastructure.persistence import migrations
from sistemacampero.infrastructure.persistence.db import Database
from sistemacampero.infrastructure.persistence.organizacoes import (
    PostgresRepositorioOrganizacoes,
)
from tests.integracao.conftest import como, criar_usuario

pytestmark = pytest.mark.integracao

Conn = psycopg.Connection[dict[str, Any]]

NAO_LIDAS_PELO_FRONTEND = {"convites", "destinos_notificacao", "telemetria"}


def _tabelas_publicas(admin: Conn) -> set[str]:
    linhas = admin.execute(
        "select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace"
        " where n.nspname = 'public' and c.relkind in ('r', 'p') and not c.relispartition"
        " and c.relname not in ('spatial_ref_sys')"
    ).fetchall()
    return {r["relname"] for r in linhas}


@pytest.fixture
def repo(db_backend: Database) -> PostgresRepositorioOrganizacoes:
    return PostgresRepositorioOrganizacoes(db_backend)


@pytest.fixture
def duas_orgs(admin: Conn, repo: PostgresRepositorioOrganizacoes) -> dict[str, uuid.UUID]:
    ids: dict[str, uuid.UUID] = {}
    for rotulo in ("a", "b"):
        uid = criar_usuario(admin)
        org = Organizacao(id=uuid.uuid4(), nome=f"Org {rotulo}", slug=f"org-{uuid.uuid4().hex[:8]}")
        repo.criar_organizacao(org, uid, "basico", 30)
        ids[f"org_{rotulo}"], ids[f"user_{rotulo}"] = org.id, uid
    return ids


# ---------------------------------------------------------------- migrations


def test_migrations_sao_idempotentes(bancos: dict[str, str]) -> None:
    assert migrations.aplicar(bancos["admin"], bootstrap=True) == []


def test_extensoes_no_schema_extensions(admin: Conn) -> None:
    linhas = admin.execute(
        "select e.extname, n.nspname from pg_extension e"
        " join pg_namespace n on n.oid = e.extnamespace"
        " where e.extname in ('postgis', 'btree_gist')"
    ).fetchall()
    assert {r["extname"]: r["nspname"] for r in linhas} == {
        "postgis": "extensions",
        "btree_gist": "extensions",
    }


def test_toda_tabela_publica_tem_rls(admin: Conn) -> None:
    sem_rls = admin.execute(
        "select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace"
        " where n.nspname = 'public' and c.relkind in ('r', 'p')"
        " and c.relname <> 'spatial_ref_sys' and not c.relrowsecurity"
    ).fetchall()
    assert sem_rls == []


# ---------------------------------------------------------------- privilégios


def test_anon_nao_acessa_nada(admin: Conn) -> None:
    for tabela in _tabelas_publicas(admin):
        for priv in ("select", "insert", "update", "delete"):
            r = admin.execute(
                "select has_table_privilege('anon', %s, %s) as ok", (f"public.{tabela}", priv)
            ).fetchone()
            assert r and not r["ok"], f"anon tem {priv} em {tabela}"


def test_authenticated_so_le(admin: Conn) -> None:
    for tabela in _tabelas_publicas(admin):
        alvo = f"public.{tabela}"
        for priv in ("insert", "update", "delete", "truncate"):
            r = admin.execute(
                "select has_table_privilege('authenticated', %s, %s) as ok", (alvo, priv)
            ).fetchone()
            assert r and not r["ok"], f"authenticated tem {priv} em {tabela}"
        r = admin.execute(
            "select has_table_privilege('authenticated', %s, 'select') as ok", (alvo,)
        ).fetchone()
        assert r and r["ok"] is (tabela not in NAO_LIDAS_PELO_FRONTEND), tabela


def test_service_role_tem_dml_explicito(admin: Conn) -> None:
    for tabela in _tabelas_publicas(admin) - {"planos", "organizacoes"}:
        for priv in ("select", "insert", "update", "delete"):
            r = admin.execute(
                "select has_table_privilege('service_role', %s, %s) as ok",
                (f"public.{tabela}", priv),
            ).fetchone()
            assert r and r["ok"], f"service_role sem {priv} em {tabela}"


def test_papel_backend_sem_superpoderes(admin: Conn) -> None:
    r = admin.execute(
        "select rolbypassrls, rolsuper, rolcreaterole, rolcreatedb, rolcanlogin"
        " from pg_roles where rolname = 'campero_backend'"
    ).fetchone()
    assert r == {
        "rolbypassrls": False,
        "rolsuper": False,
        "rolcreaterole": False,
        "rolcreatedb": False,
        "rolcanlogin": True,
    }
    r = admin.execute(
        "select has_schema_privilege('campero_backend', 'public', 'create') as ddl,"
        " has_table_privilege('campero_backend', 'public.telemetria', 'truncate') as trunc,"
        " has_table_privilege('campero_backend', 'interno.auditoria', 'update') as audit_upd"
    ).fetchone()
    assert r == {"ddl": False, "trunc": False, "audit_upd": False}


def test_interno_fora_do_alcance_do_frontend(admin: Conn) -> None:
    r = admin.execute(
        "select has_schema_privilege('authenticated', 'interno', 'usage') as auth,"
        " has_schema_privilege('anon', 'interno', 'usage') as anon"
    ).fetchone()
    assert r == {"auth": False, "anon": False}


# ---------------------------------------------------------------- RLS


def test_backend_sem_org_ativa_nao_ve_nada(db_backend: Database, duas_orgs: dict) -> None:
    with db_backend.transacao(None) as conn:
        assert conn.execute("select count(*) as n from public.organizacoes").fetchone() == {"n": 0}
        assert conn.execute("select count(*) as n from public.membros").fetchone() == {"n": 0}


def test_backend_ve_so_a_org_ativa(db_backend: Database, duas_orgs: dict) -> None:
    with db_backend.transacao(duas_orgs["org_a"]) as conn:
        orgs = conn.execute("select id from public.organizacoes").fetchall()
        assert [o["id"] for o in orgs] == [duas_orgs["org_a"]]
        conn.execute(
            "insert into public.fazendas (organizacao_id, nome) values (%s, 'Sede')",
            (duas_orgs["org_a"],),
        )


def test_backend_nao_escreve_em_outra_org(db_backend: Database, duas_orgs: dict) -> None:
    with (
        pytest.raises(psycopg.errors.InsufficientPrivilege),
        db_backend.transacao(duas_orgs["org_a"]) as conn,
    ):
        conn.execute(
            "insert into public.fazendas (organizacao_id, nome) values (%s, 'Invasão')",
            (duas_orgs["org_b"],),
        )


def test_backend_update_esquecendo_where_fica_na_org(
    db_backend: Database, admin: Conn, duas_orgs: dict
) -> None:
    for org in (duas_orgs["org_a"], duas_orgs["org_b"]):
        admin.execute(
            "insert into public.maquinas (organizacao_id, serial) values (%s, %s)",
            (org, f"SER-{uuid.uuid4().hex[:6]}"),
        )
    with db_backend.transacao(duas_orgs["org_a"]) as conn:
        conn.execute("update public.maquinas set apelido = 'mexido'")  # sem WHERE!
    r = admin.execute(
        "select count(*) filter (where apelido = 'mexido') as mexidas from public.maquinas"
        " where organizacao_id = %s",
        (duas_orgs["org_b"],),
    ).fetchone()
    assert r == {"mexidas": 0}


def test_authenticated_ve_so_suas_orgs(admin: Conn, duas_orgs: dict) -> None:
    with como(admin, "authenticated", usuario=duas_orgs["user_a"]) as c:
        orgs = c.execute("select id from public.organizacoes").fetchall()
        assert [o["id"] for o in orgs] == [duas_orgs["org_a"]]
        membros = c.execute("select distinct organizacao_id from public.membros").fetchall()
        assert [m["organizacao_id"] for m in membros] == [duas_orgs["org_a"]]
        assert c.execute("select count(*) as n from public.planos").fetchone() == {"n": 1}


def test_authenticated_nao_usa_app_organizacao_id(admin: Conn, duas_orgs: dict) -> None:
    """O atalho do backend não vale para o JWT do frontend."""
    with como(admin, "authenticated", usuario=duas_orgs["user_a"]) as c:
        c.execute("select set_config('app.organizacao_id', %s, true)", (str(duas_orgs["org_b"]),))
        orgs = c.execute("select id from public.organizacoes").fetchall()
        assert [o["id"] for o in orgs] == [duas_orgs["org_a"]]


def test_authenticated_nao_escreve(admin: Conn, duas_orgs: dict) -> None:
    with (
        pytest.raises(psycopg.errors.InsufficientPrivilege),
        como(admin, "authenticated", usuario=duas_orgs["user_a"]) as c,
    ):
        c.execute(
            "insert into public.fazendas (organizacao_id, nome) values (%s, 'x')",
            (duas_orgs["org_a"],),
        )


def test_anon_bloqueado(admin: Conn, duas_orgs: dict) -> None:
    with pytest.raises(psycopg.errors.InsufficientPrivilege), como(admin, "anon") as c:
        c.execute("select * from public.organizacoes")


def test_service_role_le_tudo(admin: Conn, duas_orgs: dict) -> None:
    with como(admin, "service_role") as c:
        n = c.execute("select count(*) as n from public.organizacoes").fetchone()
        assert n and n["n"] >= 2


# ---------------------------------------------------------------- repositório


def test_repositorio_vinculos_e_slug(repo: PostgresRepositorioOrganizacoes, admin: Conn) -> None:
    uid = criar_usuario(admin)
    slug = f"fazenda-{uuid.uuid4().hex[:8]}"
    org = Organizacao(id=uuid.uuid4(), nome="Fazenda Teste", slug=slug)
    repo.criar_organizacao(org, uid, "basico", 30)
    vinculos = repo.vinculos_do_usuario(uid)
    assert [(v.organizacao_id, v.organizacao_slug, v.papel) for v in vinculos] == [
        (org.id, slug, Papel.OWNER)
    ]
    assinatura = admin.execute(
        "select plano_codigo, status, fim > inicio as ok from public.assinaturas"
        " where organizacao_id = %s",
        (org.id,),
    ).fetchone()
    assert assinatura == {"plano_codigo": "basico", "status": "trial", "ok": True}

    outro = criar_usuario(admin)
    with pytest.raises(Conflito) as exc:
        repo.criar_organizacao(Organizacao(uuid.uuid4(), "Copia", slug), outro, "basico", 30)
    assert exc.value.codigo == "SLUG_EM_USO"
    assert repo.vinculos_do_usuario(outro) == []  # transação desfeita por inteiro


# ---------------------------------------------------------------- domínio no banco


def test_area_do_talhao_por_trigger(admin: Conn, duas_orgs: dict) -> None:
    # ~1 km x 1 km perto de Passo Fundo (graus aproximados): ~100 ha.
    r = admin.execute(
        "insert into public.talhoes (organizacao_id, nome, geometria) values (%s, 'Quadrado',"
        " extensions.st_multi(extensions.st_geomfromtext("
        "'POLYGON((-52.40 -28.26,-52.38977 -28.26,-52.38977 -28.25099,-52.40 -28.25099,"
        "-52.40 -28.26))', 4326))) returning area_ha",
        (duas_orgs["org_a"],),
    ).fetchone()
    assert r and 99 < float(r["area_ha"]) < 101


def test_preco_combustivel_sem_sobreposicao(admin: Conn, duas_orgs: dict) -> None:
    org = duas_orgs["org_a"]  # S500: o S10 já vem semeado com o preço padrão
    sql_ins = (
        "insert into public.preco_combustivel (organizacao_id, tipo, preco_rs_l, valido_de,"
        " valido_ate, fonte) values (%s, 'S500', %s, %s, %s, 'anp')"
    )
    admin.execute(sql_ins, (org, 6.59, "2026-08-01", "2026-09-01"))
    admin.execute(sql_ins, (org, 6.49, "2026-09-01", None))  # encosta, não sobrepõe
    with pytest.raises(psycopg.errors.ExclusionViolation):
        admin.execute(sql_ins, (org, 6.70, "2026-08-15", "2026-08-20"))


def test_particao_de_telemetria(db_backend: Database, admin: Conn, duas_orgs: dict) -> None:
    org = duas_orgs["org_a"]
    maquina = admin.execute(
        "insert into public.maquinas (organizacao_id, serial) values (%s, %s) returning id",
        (org, f"1BM6210-{uuid.uuid4().hex[:6]}"),
    ).fetchone()["id"]  # type: ignore[index]
    arquivo = admin.execute(
        "insert into public.arquivos_brutos (organizacao_id, sha256, nome_original,"
        " caminho_storage, tamanho_bytes, tipo) values (%s, %s, 'x.jdl', 'brutos/x', 1, 'jdl')"
        " returning id",
        (org, uuid.uuid4().hex * 2),
    ).fetchone()["id"]  # type: ignore[index]
    sessao = admin.execute(
        "insert into public.sessoes_trabalho (organizacao_id, arquivo_bruto_id, maquina_id,"
        " inicio, fim, adapter, adapter_versao) values (%s, %s, %s, '2026-04-30 10:00Z',"
        " '2026-04-30 11:00Z', 'john_deere_gen4', '2.0.0') returning id",
        (org, arquivo, maquina),
    ).fetchone()["id"]  # type: ignore[index]

    with db_backend.transacao(org) as conn:
        nome = conn.execute("select interno.garantir_particao('2026-04-30 10:00Z') as p").fetchone()
        assert nome == {"p": "telemetria_y2026m04"}
        conn.execute(
            "insert into public.telemetria (organizacao_id, maquina_id, sessao_id, ts, lat, lon,"
            " gps_valid, speed_kmh) values (%s, %s, %s, '2026-04-30 10:00:01Z', -28.26, -52.40,"
            " true, 8.5)",
            (org, maquina, sessao),
        )
        r = conn.execute(
            "select tableoid::regclass::text as particao, extensions.st_y(geom::extensions.geometry)"
            " as lat from public.telemetria where sessao_id = %s",
            (sessao,),
        ).fetchone()
        assert r == {"particao": "telemetria_y2026m04", "lat": -28.26}

    # Acesso direto à partição contornaria a RLS: tem de ser negado.
    with (
        pytest.raises(psycopg.errors.InsufficientPrivilege),
        db_backend.transacao(org) as conn,
    ):
        conn.execute("select * from public.telemetria_y2026m04")

    # Apagar a sessão apaga a telemetria (reprocessamento idempotente).
    admin.execute("delete from public.sessoes_trabalho where id = %s", (sessao,))
    n = admin.execute(
        "select count(*) as n from public.telemetria where sessao_id = %s", (sessao,)
    ).fetchone()
    assert n == {"n": 0}


def test_organizacao_nasce_com_preco_padrao(admin: Conn, duas_orgs: dict) -> None:
    linha = admin.execute(
        "select tipo, preco_rs_l::float as preco, fonte, valido_ate from public.preco_combustivel"
        " where organizacao_id = %s",
        (duas_orgs["org_a"],),
    ).fetchall()
    assert linha == [{"tipo": "S10", "preco": 6.59, "fonte": "anp", "valido_ate": None}]
