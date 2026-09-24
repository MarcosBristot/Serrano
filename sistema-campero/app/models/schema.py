"""
Modelos SQLAlchemy + GeoAlchemy2 para o Sistema Campero.

Camadas representadas (ver arquitetura do pipeline em 5 etapas):
    - Entidades operacionais: Fazenda, Talhao, Maquina
    - Etapa 1 (ingestão):     ArquivoImportado — controle do upload bruto
    - Etapa 3 (dado limpo):   LeituraTelemetria — schema universal, agnóstico
                              de fabricante
    - Etapa 5 (resultados):   KpiOperacao, AlertaAnomalia — separados do dado
                              bruto/limpo, para permitir reprocessamento sem
                              tocar no histórico original

IMPORTANTE: este é um schema inicial coerente com o contexto do projeto
(farm/talhão/máquina + as 5 tabelas do pipeline). Ajuste nomes e colunas
para bater exatamente com o modelo de entidades já validado em equipe,
caso haja diferenças — este arquivo foi escrito sem acesso a esse modelo
original.
"""

import enum
import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


def gerar_uuid() -> uuid.UUID:
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Fabricante(str, enum.Enum):
    JOHN_DEERE = "john_deere"
    NH = "nh"
    OUTRO = "outro"


class StatusArquivo(str, enum.Enum):
    RECEBIDO = "recebido"
    PROCESSANDO = "processando"
    PROCESSADO = "processado"
    ERRO = "erro"


class TipoAnomalia(str, enum.Enum):
    CONSUMO_EXCESSIVO = "consumo_excessivo"
    OCIOSIDADE = "ociosidade"
    QUEDA_SUSPEITA_COMBUSTIVEL = "queda_suspeita_combustivel"


class Severidade(str, enum.Enum):
    BAIXA = "baixa"
    MEDIA = "media"
    ALTA = "alta"


# ---------------------------------------------------------------------------
# Entidades operacionais
# ---------------------------------------------------------------------------

class Fazenda(Base):
    __tablename__ = "fazenda"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gerar_uuid)
    nome = Column(String(200), nullable=False)
    municipio = Column(String(120), nullable=False)  # ex: Passo Fundo, Não-Me-Toque
    criado_em = Column(DateTime, default=datetime.utcnow, nullable=False)

    talhoes = relationship("Talhao", back_populates="fazenda")
    maquinas = relationship("Maquina", back_populates="fazenda")


class Talhao(Base):
    """Área/polígono da fazenda — usado para cálculo de área (ha) e para
    associar cada leitura de GPS a um talhão (join espacial)."""

    __tablename__ = "talhao"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gerar_uuid)
    fazenda_id = Column(UUID(as_uuid=True), ForeignKey("fazenda.id"), nullable=False)
    nome = Column(String(120), nullable=False)
    area_ha = Column(Float, nullable=False)
    geom = Column(Geometry(geometry_type="POLYGON", srid=4326), nullable=False)

    fazenda = relationship("Fazenda", back_populates="talhoes")


class Maquina(Base):
    __tablename__ = "maquina"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gerar_uuid)
    fazenda_id = Column(UUID(as_uuid=True), ForeignKey("fazenda.id"), nullable=False)
    fabricante = Column(Enum(Fabricante), nullable=False)
    modelo = Column(String(120), nullable=False)
    identificador_externo = Column(String(120), nullable=True)  # ID/serial do fabricante

    fazenda = relationship("Fazenda", back_populates="maquinas")


# ---------------------------------------------------------------------------
# Etapa 1 — Ingestão (controle do arquivo bruto)
# ---------------------------------------------------------------------------

class ArquivoImportado(Base):
    __tablename__ = "arquivo_importado"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gerar_uuid)
    maquina_id = Column(UUID(as_uuid=True), ForeignKey("maquina.id"), nullable=False)
    fabricante = Column(Enum(Fabricante), nullable=False)
    nome_arquivo = Column(String(255), nullable=False)
    caminho_storage = Column(Text, nullable=False)  # path no Supabase Storage
    status = Column(Enum(StatusArquivo), default=StatusArquivo.RECEBIDO, nullable=False)
    linhas_aceitas = Column(Integer, default=0)
    linhas_rejeitadas = Column(Integer, default=0)
    recebido_em = Column(DateTime, default=datetime.utcnow, nullable=False)
    processado_em = Column(DateTime, nullable=True)


# ---------------------------------------------------------------------------
# Etapa 3 — Dado limpo (schema universal, agnóstico de fabricante)
# ---------------------------------------------------------------------------

class LeituraTelemetria(Base):
    __tablename__ = "leitura_telemetria"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gerar_uuid)
    arquivo_importado_id = Column(
        UUID(as_uuid=True), ForeignKey("arquivo_importado.id"), nullable=True
    )
    maquina_id = Column(UUID(as_uuid=True), ForeignKey("maquina.id"), nullable=False)
    talhao_id = Column(UUID(as_uuid=True), ForeignKey("talhao.id"), nullable=True)

    timestamp = Column(DateTime, nullable=False)
    geom = Column(Geometry(geometry_type="POINT", srid=4326), nullable=False)
    horimetro = Column(Float, nullable=False)  # horas acumuladas do motor
    combustivel_consumido_l = Column(Float, nullable=False)
    velocidade_kmh = Column(Float, nullable=True)

    __table_args__ = (
        UniqueConstraint("maquina_id", "timestamp", name="uq_leitura_maquina_timestamp"),
    )


# ---------------------------------------------------------------------------
# Etapa 5 — Resultados (separados do dado bruto/limpo)
# ---------------------------------------------------------------------------

class KpiOperacao(Base):
    __tablename__ = "kpi_operacao"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gerar_uuid)
    maquina_id = Column(UUID(as_uuid=True), ForeignKey("maquina.id"), nullable=False)
    talhao_id = Column(UUID(as_uuid=True), ForeignKey("talhao.id"), nullable=True)
    periodo_inicio = Column(DateTime, nullable=False)
    periodo_fim = Column(DateTime, nullable=False)
    combustivel_total_l = Column(Float, nullable=False)
    horas_trabalhadas = Column(Float, nullable=False)
    litros_por_hectare = Column(Float, nullable=True)
    calculado_em = Column(DateTime, default=datetime.utcnow, nullable=False)


class AlertaAnomalia(Base):
    __tablename__ = "alerta_anomalia"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gerar_uuid)
    maquina_id = Column(UUID(as_uuid=True), ForeignKey("maquina.id"), nullable=False)
    leitura_id = Column(UUID(as_uuid=True), ForeignKey("leitura_telemetria.id"), nullable=True)
    tipo = Column(Enum(TipoAnomalia), nullable=False)
    severidade = Column(Enum(Severidade), nullable=False)
    descricao = Column(Text, nullable=False)
    criado_em = Column(DateTime, default=datetime.utcnow, nullable=False)
