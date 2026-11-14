"""Repositório de cadastro (fazendas, talhões, máquinas, implementos, operadores, sessões).

Geometria trafega como WKB (shapely) para dentro e GeoJSON para fora da API. Contorno
definido pelo gestor (upload/desenho) nunca é sobrescrito pela importação do monitor.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import psycopg.errors
import shapely
from shapely.geometry import MultiPolygon

from sistemacampero.domain.cadastro import ImportacaoCadastro, OrigemContorno, ResumoImportacao
from sistemacampero.domain.errors import Conflito, NaoEncontrado
from sistemacampero.domain.services.geo import Contorno
from sistemacampero.domain.services.nomes import chave_talhao, mesmo_talhao
from sistemacampero.infrastructure.parsers.shapefile import nome_normalizado
from sistemacampero.infrastructure.persistence.db import Conexao, Database

_GEOM = "extensions.st_multi(extensions.st_geomfromwkb(%s, 4326))"
_GEOJSON = "extensions.st_asgeojson(geometria, 7)::json"

# Talhões ativos com o que decide qual é o principal num grupo de nomes iguais.
TALHOES_ATIVOS = (
    "select t.id, t.nome, t.geometria is not null as tem_contorno, t.criado_em,"
    " (select count(*) from public.sessoes_trabalho s"
    "   where s.talhao_id = t.id or s.talhao_monitor_id = t.id) as sessoes"
    " from public.talhoes t where t.organizacao_id = %s and t.ativo and t.agrupado_em is null"
)


def _prioridade(t: dict[str, Any]) -> tuple[bool, int, Any]:
    return (not t["tem_contorno"], -int(t["sessoes"]), t["criado_em"])


def achar_talhao(talhoes: list[dict[str, Any]], nome: str) -> dict[str, Any] | None:
    """O talhão ativo que é a mesma lavoura (com contorno e mais usado primeiro)."""
    chave = chave_talhao(nome)
    candidatos = [t for t in talhoes if mesmo_talhao(chave, chave_talhao(str(t["nome"])))]
    return min(candidatos, key=_prioridade) if candidatos else None


# Colunas editáveis por entidade (o resto é do sistema).
EDITAVEIS: dict[str, tuple[str, ...]] = {
    "fazendas": ("nome", "cliente_nome"),
    "talhoes": ("nome", "fazenda_id", "ativo"),
    "maquinas": ("apelido", "modelo"),
    "implementos": ("nome", "largura_m"),
    "operadores": ("nome", "ativo"),
}
COLUNAS_LISTA: dict[str, str] = {
    "fazendas": "id, nome, cliente_nome, external_guid, criado_em, atualizado_em",
    "talhoes": (
        "id, fazenda_id, nome, external_guid, area_ha, origem_contorno, ativo,"
        " geometria is not null as tem_contorno, criado_em, atualizado_em"
    ),
    "maquinas": (
        "id, serial, fabricante, modelo, tecnologia, apelido, ativa, primeira_atividade,"
        " ultima_atividade, criado_em, atualizado_em"
    ),
    "implementos": "id, nome, largura_m, external_guid, criado_em, atualizado_em",
    "operadores": "id, nome, external_guid, ativo, criado_em, atualizado_em",
}


def _wkb(geom: MultiPolygon) -> bytes:
    resultado: bytes = shapely.to_wkb(geom)
    return resultado


class PostgresRepositorioCadastro:
    def __init__(self, db: Database) -> None:
        self._db = db

    # ------------------------------------------------------------- CRUD genérico
    def listar(self, org: UUID, entidade: str, filtros: dict[str, Any]) -> list[dict[str, Any]]:
        where, params = ["true"], []
        for coluna, valor in filtros.items():
            if valor is not None:
                where.append(f"{coluna} = %s")
                params.append(valor)
        sql = (
            f"select {COLUNAS_LISTA[entidade]} from public.{entidade}"  # noqa: S608 - nomes fixos
            f" where {' and '.join(where)} order by nome nulls last, id limit 5000"
        )
        if entidade == "maquinas":
            sql = sql.replace("order by nome nulls last", "order by coalesce(apelido, serial)")
        with self._db.transacao(org) as conn:
            return conn.execute(sql, params).fetchall()

    def obter(
        self, org: UUID, entidade: str, ident: UUID, geometria: bool = False
    ) -> dict[str, Any]:
        extra = f", {_GEOJSON} as geometria" if geometria and entidade == "talhoes" else ""
        with self._db.transacao(org) as conn:
            linha = conn.execute(
                f"select {COLUNAS_LISTA[entidade]}{extra} from public.{entidade} where id = %s",
                (ident,),
            ).fetchone()
        if linha is None:
            raise NaoEncontrado(f"{entidade[:-1].capitalize()} não encontrado(a).")
        return linha

    def criar(self, org: UUID, entidade: str, dados: dict[str, Any]) -> dict[str, Any]:
        colunas = ["organizacao_id", *dados]
        try:
            with self._db.transacao(org) as conn:
                linha = conn.execute(
                    f"insert into public.{entidade} ({', '.join(colunas)})"
                    f" values ({', '.join(['%s'] * len(colunas))}) returning id",
                    (org, *dados.values()),
                ).fetchone()
        except psycopg.errors.ForeignKeyViolation as exc:
            raise NaoEncontrado("Referência inexistente.", codigo="REFERENCIA_INEXISTENTE") from exc
        assert linha is not None
        return self.obter(org, entidade, linha["id"])

    def atualizar(
        self, org: UUID, entidade: str, ident: UUID, dados: dict[str, Any]
    ) -> dict[str, Any]:
        campos = {k: v for k, v in dados.items() if k in EDITAVEIS[entidade]}
        if campos:
            sets = ", ".join(f"{c} = %s" for c in campos)
            try:
                with self._db.transacao(org) as conn:
                    n = conn.execute(
                        f"update public.{entidade} set {sets} where id = %s",
                        (*campos.values(), ident),
                    ).rowcount
            except psycopg.errors.ForeignKeyViolation as exc:
                raise NaoEncontrado(
                    "Referência inexistente.", codigo="REFERENCIA_INEXISTENTE"
                ) from exc
            if n == 0:
                raise NaoEncontrado(f"{entidade[:-1].capitalize()} não encontrado(a).")
        return self.obter(org, entidade, ident)

    def apagar(self, org: UUID, entidade: str, ident: UUID) -> None:
        try:
            with self._db.transacao(org) as conn:
                n = conn.execute(f"delete from public.{entidade} where id = %s", (ident,)).rowcount
        except psycopg.errors.ForeignKeyViolation as exc:
            raise Conflito("Ainda há registros ligados a este item.", codigo="EM_USO") from exc
        if n == 0:
            raise NaoEncontrado(f"{entidade[:-1].capitalize()} não encontrado(a).")

    # ------------------------------------------------------------- talhões/contornos
    def definir_contorno(
        self, org: UUID, talhao_id: UUID, geom: MultiPolygon | None, origem: OrigemContorno | None
    ) -> dict[str, Any]:
        with self._db.transacao(org) as conn:
            n = conn.execute(
                f"update public.talhoes set geometria = {_GEOM if geom is not None else '%s'},"
                " origem_contorno = %s where id = %s",
                (
                    _wkb(geom) if geom is not None else None,
                    origem.value if origem else None,
                    talhao_id,
                ),
            ).rowcount
        if n == 0:
            raise NaoEncontrado("Talhão não encontrado.")
        return self.obter(org, "talhoes", talhao_id, geometria=True)

    def contornos(self, org: UUID) -> list[Contorno]:
        with self._db.transacao(org) as conn:
            linhas = conn.execute(
                "select id, fazenda_id, extensions.st_asbinary(geometria) as wkb"
                " from public.talhoes where ativo and geometria is not null order by criado_em, id"
            ).fetchall()
        return [
            Contorno(
                talhao_id=linha["id"],
                geometria=shapely.from_wkb(bytes(linha["wkb"])),
                fazenda_id=linha["fazenda_id"],
            )
            for linha in linhas
        ]

    def importar(self, org: UUID, imp: ImportacaoCadastro) -> ResumoImportacao:
        novos = preservados = 0
        with self._db.transacao(org) as conn:
            fazendas: dict[str, UUID] = {}
            for f in imp.fazendas:
                fazendas[f.guid] = self._upsert(
                    conn, "fazendas", org, f.guid, {"nome": f.nome, "cliente_nome": f.cliente_nome}
                )
            for t in imp.talhoes:
                talhao_id = self._upsert(
                    conn,
                    "talhoes",
                    org,
                    t.guid,
                    {"nome": t.nome, "fazenda_id": fazendas.get(t.fazenda_guid or "")},
                )
                if t.contorno is None:
                    continue
                n = conn.execute(
                    f"update public.talhoes set geometria = {_GEOM}, origem_contorno = 'monitor'"
                    " where id = %s and (origem_contorno is null or origem_contorno = 'monitor')"
                    f"   and (geometria is null or not extensions.st_equals(geometria, {_GEOM}))",
                    (_wkb(t.contorno), talhao_id, _wkb(t.contorno)),
                ).rowcount
                if n:
                    novos += 1
                else:
                    origem = conn.execute(
                        "select origem_contorno from public.talhoes where id = %s", (talhao_id,)
                    ).fetchone()
                    preservados += int(
                        bool(origem and origem["origem_contorno"] in ("upload", "desenho"))
                    )
            for i in imp.implementos:
                self._upsert(
                    conn, "implementos", org, i.guid, {"nome": i.nome, "largura_m": i.largura_m}
                )
            for o in imp.operadores:
                self._upsert(conn, "operadores", org, o.guid, {"nome": o.nome})
        return ResumoImportacao(
            fazendas=len(imp.fazendas),
            talhoes=len(imp.talhoes),
            contornos_novos=novos,
            contornos_preservados=preservados,
            implementos=len(imp.implementos),
            operadores=len(imp.operadores),
        )

    def importar_contornos(
        self, org: UUID, itens: list[tuple[str, MultiPolygon]]
    ) -> dict[str, int]:
        """Contornos de outro equipamento (ex.: OMNI), casados pelo nome do talhão.

        Talhão sem contorno ganha o do arquivo; o que já tem (monitor, upload ou desenho)
        fica como está; talhão que não existe é criado. Reimportar não duplica nada.
        """
        novos = criados = preservados = 0
        with self._db.transacao(org) as conn:
            ativos = conn.execute(TALHOES_ATIVOS, (org,)).fetchall()
            for nome, geom in itens:
                chave = nome_normalizado(nome)
                t = achar_talhao(ativos, nome)
                if t is None:
                    conn.execute(
                        "insert into public.talhoes"
                        " (organizacao_id, external_guid, nome, geometria, origem_contorno)"
                        f" values (%s, %s, %s, {_GEOM}, 'upload')"
                        " on conflict (organizacao_id, external_guid) do nothing",
                        (org, f"contorno:{chave}", nome, _wkb(geom)),
                    )
                    criados += 1
                elif t["tem_contorno"]:
                    preservados += 1
                else:
                    conn.execute(
                        f"update public.talhoes set geometria = {_GEOM}, origem_contorno = 'upload'"
                        " where id = %s and geometria is null",
                        (_wkb(geom), t["id"]),
                    )
                    novos += 1
        return {
            "contornos_novos": novos,
            "talhoes_criados": criados,
            "preservados": preservados,
        }

    def importar_linhas(self, org: UUID, itens: list[tuple[str, list[dict[str, Any]]]]) -> int:
        """Cabeceira e linhas-guia do OMNI por talhão (casado pelo nome normalizado).

        Reimportar substitui as linhas do OMNI daquele talhão; talhão desconhecido é ignorado
        (o perímetro, quando existe, já o criou antes nesta mesma importação).
        """
        gravadas = 0
        with self._db.transacao(org) as conn:
            ativos = conn.execute(TALHOES_ATIVOS, (org,)).fetchall()
            for nome, linhas in itens:
                achado = achar_talhao(ativos, nome)
                if achado is None:
                    continue
                talhao = achado["id"]
                conn.execute(
                    "delete from public.linhas_talhao where talhao_id = %s and origem = 'omni'",
                    (talhao,),
                )
                for x in linhas:
                    conn.execute(
                        "insert into public.linhas_talhao (organizacao_id, talhao_id, tipo,"
                        " subtipo, gravado_em, geometria)"
                        " values (%s, %s, %s, %s, %s, extensions.st_geomfromwkb(%s, 4326))",
                        (org, talhao, x["tipo"], x["subtipo"], x["gravado_em"], x["geom"].wkb),
                    )
                    gravadas += 1
        return gravadas

    def agrupar_talhoes(self, org: UUID) -> tuple[dict[str, int], list[UUID]]:
        """Junta os talhões que são a mesma lavoura com outro nome ("Mae_Aveia22" = "Mãe").

        O principal é o que tem contorno, depois o mais usado. Os outros ficam inativos e
        apontam para ele (nada é apagado); a correção manual do gestor passa para o principal
        e as demais sessões voltam para a fila para serem refeitas. Devolve o resumo e os
        arquivos a reprocessar.
        """
        with self._db.transacao(org) as conn:
            ativos = sorted(conn.execute(TALHOES_ATIVOS, (org,)).fetchall(), key=_prioridade)
            grupos: list[list[dict[str, Any]]] = []
            for t in ativos:
                chave = chave_talhao(str(t["nome"]))
                grupo = next(
                    (g for g in grupos if mesmo_talhao(chave, chave_talhao(str(g[0]["nome"])))),
                    None,
                )
                if grupo is None:
                    grupos.append([t])
                else:
                    grupo.append(t)
            repetidos: list[UUID] = []
            for principal, *outros in (g for g in grupos if len(g) > 1):
                ids = [o["id"] for o in outros]
                repetidos += ids
                conn.execute(
                    "update public.talhoes set ativo = false, agrupado_em = %s where id = any(%s)",
                    (principal["id"], ids),
                )
                conn.execute(
                    "update public.talhoes set agrupado_em = %s where agrupado_em = any(%s)",
                    (principal["id"], ids),
                )
                conn.execute(
                    "update public.sessoes_trabalho set talhao_id = %s"
                    " where talhao_origem = 'manual' and talhao_id = any(%s)",
                    (principal["id"], ids),
                )
                tem_linhas = conn.execute(
                    "select 1 from public.linhas_talhao where talhao_id = %s limit 1",
                    (principal["id"],),
                ).fetchone()
                if tem_linhas is None:
                    conn.execute(
                        "update public.linhas_talhao set talhao_id = %s where talhao_id = any(%s)",
                        (principal["id"], ids),
                    )
            arquivos = [
                r["arquivo_bruto_id"]
                for r in conn.execute(
                    "select distinct arquivo_bruto_id from public.sessoes_trabalho"
                    " where talhao_origem <> 'manual'"
                    "   and (talhao_id = any(%s) or talhao_monitor_id = any(%s))",
                    (repetidos, repetidos),
                ).fetchall()
            ]
        resumo = {
            "grupos": sum(1 for g in grupos if len(g) > 1),
            "talhoes_agrupados": len(repetidos),
            "talhoes_ativos": len(grupos),
        }
        return resumo, arquivos

    def linhas_geojson(self, org: UUID, talhao_id: UUID | None = None) -> dict[str, Any]:
        """Camada do mapa: cabeceiras e linhas-guia dos talhões ativos."""
        with self._db.transacao(org) as conn:
            linha = conn.execute(
                """
                select coalesce(json_agg(json_build_object(
                    'type', 'Feature',
                    'geometry', extensions.st_asgeojson(l.geometria, 7)::json,
                    'properties', json_build_object('tipo', l.tipo, 'subtipo', l.subtipo,
                        'talhao', t.nome, 'gravado_em', l.gravado_em)
                ) order by l.tipo, l.gravado_em), '[]'::json) as features
                from public.linhas_talhao l
                join public.talhoes t on t.id = l.talhao_id and t.ativo
                where l.organizacao_id = %s and (%s::uuid is null or l.talhao_id = %s)
                """,
                (org, talhao_id, talhao_id),
            ).fetchone()
        assert linha is not None
        return {"type": "FeatureCollection", "features": linha["features"]}

    @staticmethod
    def _upsert(conn: Conexao, tabela: str, org: UUID, guid: str, campos: dict[str, Any]) -> UUID:
        nomes = ["organizacao_id", "external_guid", *campos]
        atualiza = ", ".join(f"{c} = coalesce(excluded.{c}, {tabela}.{c})" for c in campos)
        linha = conn.execute(
            f"insert into public.{tabela} ({', '.join(nomes)})"
            f" values ({', '.join(['%s'] * len(nomes))})"
            f" on conflict (organizacao_id, external_guid) do update set {atualiza} returning id",
            (org, guid, *campos.values()),
        ).fetchone()
        assert linha is not None
        ident: UUID = linha["id"]
        return ident

    # ------------------------------------------------------------- máquinas
    def ativar_maquina(self, org: UUID, maquina_id: UUID, ativa: bool) -> dict[str, Any]:
        with self._db.transacao(org) as conn:
            plano = conn.execute(
                "select coalesce(a.max_maquinas_override, p.max_maquinas) as limite"
                " from public.assinaturas a join public.planos p on p.codigo = a.plano_codigo"
                " where a.organizacao_id = %s for update of a",
                (org,),
            ).fetchone()
            atual = conn.execute(
                "select ativa from public.maquinas where id = %s", (maquina_id,)
            ).fetchone()
            if atual is None:
                raise NaoEncontrado("Máquina não encontrada.")
            if ativa and not atual["ativa"]:
                ativas = conn.execute(
                    "select count(*) as n from public.maquinas where ativa"
                ).fetchone()
                assert ativas is not None
                if plano is None or int(ativas["n"]) >= int(plano["limite"]):
                    raise Conflito(
                        "O plano já tem o máximo de máquinas ativas.",
                        codigo="PLANO_LIMITE_MAQUINAS",
                        limite=int(plano["limite"]) if plano else 0,
                    )
            conn.execute("update public.maquinas set ativa = %s where id = %s", (ativa, maquina_id))
        return self.obter(org, "maquinas", maquina_id)

    # ------------------------------------------------------------- sessões
    def listar_sessoes(
        self, org: UUID, filtros: dict[str, Any], limite: int, cursor: tuple[str, UUID] | None
    ) -> list[dict[str, Any]]:
        where, params = ["true"], []
        for coluna, valor in filtros.items():
            if valor is None:
                continue
            if coluna == "inicio":
                where.append("s.inicio >= %s")
            elif coluna == "fim":
                where.append("s.inicio < %s")
            else:
                where.append(f"s.{coluna} = %s")
            params.append(valor)
        if cursor:
            where.append("(s.inicio, s.id) < (%s::timestamptz, %s)")
            params.extend(cursor)
        sql = (
            "select s.id, s.arquivo_bruto_id, s.maquina_id, m.serial, m.apelido, s.implemento_id,"
            " s.operador_id, s.talhao_id, t.nome as talhao_nome, s.talhao_origem,"
            " s.talhao_confianca, s.operacao, s.inicio, s.fim, s.n_amostras, s.qualidade_score,"
            " ms.motor_h, ms.trabalho_h, ms.ocioso_h, ms.litros_integral, ms.area_cobertura_ha,"
            " ms.area_estimada_ha, ms.l_ha, ms.ha_h, ms.cobertura_gps"
            " from public.sessoes_trabalho s"
            " join public.maquinas m on m.id = s.maquina_id"
            " left join public.talhoes t on t.id = s.talhao_id"
            " left join public.metricas_sessao ms on ms.sessao_id = s.id and ms.vigente"
            f" where {' and '.join(where)} order by s.inicio desc, s.id desc limit %s"
        )
        with self._db.transacao(org) as conn:
            return conn.execute(sql, (*params, limite)).fetchall()

    def obter_sessao(self, org: UUID, sessao_id: UUID) -> dict[str, Any]:
        linhas = self.listar_sessoes(org, {"id": sessao_id}, 1, None)
        if not linhas:
            raise NaoEncontrado("Sessão não encontrada.", codigo="SESSAO_NAO_ENCONTRADA")
        with self._db.transacao(org) as conn:
            extra = conn.execute(
                "select s.qualidade, s.adapter, s.adapter_versao, s.firmware,"
                " ms.sobreposicao_pct, ms.area_metodo, ms.delta_horimetro_h, ms.litros_contador,"
                " ms.distancia_trabalho_km, ms.velocidade_media, ms.lph_trabalho, ms.lph_ocioso"
                " from public.sessoes_trabalho s"
                " left join public.metricas_sessao ms on ms.sessao_id = s.id and ms.vigente"
                " where s.id = %s",
                (sessao_id,),
            ).fetchone()
        return {**linhas[0], **(extra or {})}

    def corrigir_sessao(self, org: UUID, sessao_id: UUID, campos: dict[str, Any]) -> UUID:
        """Devolve o arquivo da sessão (para reprocessar quando o talhão muda)."""
        sets, params = [], []
        if "operador_id" in campos:
            sets.append("operador_id = %s")
            params.append(campos["operador_id"])
        if "talhao_id" in campos:
            if campos["talhao_id"] is None:  # volta para a localização automática
                sets.append("talhao_origem = 'nenhum', talhao_id = null, talhao_confianca = null")
            else:
                sets.append("talhao_origem = 'manual', talhao_id = %s, talhao_confianca = 1")
                params.append(campos["talhao_id"])
        try:
            with self._db.transacao(org) as conn:
                linha = conn.execute(
                    f"update public.sessoes_trabalho set {', '.join(sets) or 'id = id'}"
                    " where id = %s returning arquivo_bruto_id",
                    (*params, sessao_id),
                ).fetchone()
        except psycopg.errors.ForeignKeyViolation as exc:
            raise NaoEncontrado("Referência inexistente.", codigo="REFERENCIA_INEXISTENTE") from exc
        if linha is None:
            raise NaoEncontrado("Sessão não encontrada.", codigo="SESSAO_NAO_ENCONTRADA")
        arquivo: UUID = linha["arquivo_bruto_id"]
        return arquivo

    def talhao_manual(self, org: UUID, arquivo_id: UUID) -> UUID | None:
        with self._db.transacao(org) as conn:
            linha = conn.execute(
                "select talhao_id from public.sessoes_trabalho"
                " where arquivo_bruto_id = %s and talhao_origem = 'manual'",
                (arquivo_id,),
            ).fetchone()
        return None if linha is None else linha["talhao_id"]

    def arquivos_para_relocalizar(
        self, org: UUID, contorno: MultiPolygon | None = None, talhao_id: UUID | None = None
    ) -> list[UUID]:
        """Sessões não manuais com GPS: todas, ou as que tocam o contorno/estão no talhão."""
        with self._db.transacao(org) as conn:
            if contorno is None:
                linhas = conn.execute(
                    "select s.arquivo_bruto_id from public.sessoes_trabalho s"
                    " join public.metricas_sessao ms on ms.sessao_id = s.id and ms.vigente"
                    " where s.talhao_origem <> 'manual' and ms.cobertura_gps > 0"
                ).fetchall()
            else:
                # Caixa do contorno primeiro (barato, pelos índices da sessão); o ponto exato só
                # para quem cai dentro dela.
                x0, y0, x1, y1 = contorno.bounds
                linhas = conn.execute(
                    "select s.arquivo_bruto_id from public.sessoes_trabalho s"
                    " where s.talhao_origem <> 'manual' and (s.talhao_id = %s or exists ("
                    "   select 1 from public.telemetria t where t.sessao_id = s.id"
                    "   and t.lon between %s and %s and t.lat between %s and %s"
                    "   and extensions.st_intersects("
                    "     extensions.st_setsrid(extensions.st_makepoint(t.lon, t.lat), 4326),"
                    f"     {_GEOM})))",
                    (talhao_id, x0, x1, y0, y1, _wkb(contorno)),
                ).fetchall()
        return [linha["arquivo_bruto_id"] for linha in linhas]


def geojson(valor: Any) -> Any:
    """psycopg devolve json já decodificado; texto vira dict."""
    return json.loads(valor) if isinstance(valor, str) else valor
