"""schema inicial — entidades + pipeline de telemetria

Revision ID: 0001
Revises:
Create Date: 2026-09-24
"""

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

# identificadores da revisão, usados pelo Alembic
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


fabricante_enum = postgresql.ENUM(
    "john_deere", "nh", "outro", name="fabricante"
)
status_arquivo_enum = postgresql.ENUM(
    "recebido", "processando", "processado", "erro", name="statusarquivo"
)
tipo_anomalia_enum = postgresql.ENUM(
    "consumo_excessivo", "ociosidade", "queda_suspeita_combustivel",
    name="tipoanomalia",
)
severidade_enum = postgresql.ENUM("baixa", "media", "alta", name="severidade")


def upgrade() -> None:
    # extensão PostGIS — pré-requisito de todas as colunas de geometria
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    bind = op.get_bind()
    fabricante_enum.create(bind, checkfirst=True)
    status_arquivo_enum.create(bind, checkfirst=True)
    tipo_anomalia_enum.create(bind, checkfirst=True)
    severidade_enum.create(bind, checkfirst=True)

    op.create_table(
        "fazenda",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("nome", sa.String(200), nullable=False),
        sa.Column("municipio", sa.String(120), nullable=False),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "talhao",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "fazenda_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("fazenda.id"), nullable=False,
        ),
        sa.Column("nome", sa.String(120), nullable=False),
        sa.Column("area_ha", sa.Float(), nullable=False),
        sa.Column("geom", Geometry(geometry_type="POLYGON", srid=4326), nullable=False),
    )

    op.create_table(
        "maquina",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "fazenda_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("fazenda.id"), nullable=False,
        ),
        sa.Column("fabricante", fabricante_enum, nullable=False),
        sa.Column("modelo", sa.String(120), nullable=False),
        sa.Column("identificador_externo", sa.String(120), nullable=True),
    )

    op.create_table(
        "arquivo_importado",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "maquina_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("maquina.id"), nullable=False,
        ),
        sa.Column("fabricante", fabricante_enum, nullable=False),
        sa.Column("nome_arquivo", sa.String(255), nullable=False),
        sa.Column("caminho_storage", sa.Text(), nullable=False),
        sa.Column(
            "status", status_arquivo_enum, nullable=False,
            server_default="recebido",
        ),
        sa.Column("linhas_aceitas", sa.Integer(), server_default="0"),
        sa.Column("linhas_rejeitadas", sa.Integer(), server_default="0"),
        sa.Column("recebido_em", sa.DateTime(), nullable=False),
        sa.Column("processado_em", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "leitura_telemetria",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "arquivo_importado_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("arquivo_importado.id"), nullable=True,
        ),
        sa.Column(
            "maquina_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("maquina.id"), nullable=False,
        ),
        sa.Column(
            "talhao_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("talhao.id"), nullable=True,
        ),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("geom", Geometry(geometry_type="POINT", srid=4326), nullable=False),
        sa.Column("horimetro", sa.Float(), nullable=False),
        sa.Column("combustivel_consumido_l", sa.Float(), nullable=False),
        sa.Column("velocidade_kmh", sa.Float(), nullable=True),
        sa.UniqueConstraint("maquina_id", "timestamp", name="uq_leitura_maquina_timestamp"),
    )

    op.create_table(
        "kpi_operacao",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "maquina_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("maquina.id"), nullable=False,
        ),
        sa.Column(
            "talhao_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("talhao.id"), nullable=True,
        ),
        sa.Column("periodo_inicio", sa.DateTime(), nullable=False),
        sa.Column("periodo_fim", sa.DateTime(), nullable=False),
        sa.Column("combustivel_total_l", sa.Float(), nullable=False),
        sa.Column("horas_trabalhadas", sa.Float(), nullable=False),
        sa.Column("litros_por_hectare", sa.Float(), nullable=True),
        sa.Column("calculado_em", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "alerta_anomalia",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "maquina_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("maquina.id"), nullable=False,
        ),
        sa.Column(
            "leitura_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("leitura_telemetria.id"), nullable=True,
        ),
        sa.Column("tipo", tipo_anomalia_enum, nullable=False),
        sa.Column("severidade", severidade_enum, nullable=False),
        sa.Column("descricao", sa.Text(), nullable=False),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("alerta_anomalia")
    op.drop_table("kpi_operacao")
    op.drop_table("leitura_telemetria")
    op.drop_table("arquivo_importado")
    op.drop_table("maquina")
    op.drop_table("talhao")
    op.drop_table("fazenda")

    bind = op.get_bind()
    severidade_enum.drop(bind, checkfirst=True)
    tipo_anomalia_enum.drop(bind, checkfirst=True)
    status_arquivo_enum.drop(bind, checkfirst=True)
    fabricante_enum.drop(bind, checkfirst=True)
