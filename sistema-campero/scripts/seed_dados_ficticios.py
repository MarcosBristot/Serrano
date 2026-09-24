"""
Popula o banco diretamente no schema limpo/de resultados (Etapas 3 e 5),
pulando o parser (Etapa 2) — que ainda não existe. Serve para:
  - o Guilherme desenvolver e testar API/endpoints já com dado real no banco
  - o João plugar o frontend em cima de dados plausíveis
  - qualquer teste de KPI/anomalia sem depender de arquivo bruto

Uso:
    export DATABASE_URL=postgresql://...   # connection string do Supabase
    python scripts/seed_dados_ficticios.py
"""

import random
import uuid
from datetime import datetime, timedelta

from app.db.session import get_session
from app.models.schema import (
    AlertaAnomalia,
    ArquivoImportado,
    Fabricante,
    Fazenda,
    KpiOperacao,
    LeituraTelemetria,
    Maquina,
    Severidade,
    StatusArquivo,
    Talhao,
    TipoAnomalia,
)
from geoalchemy2.shape import from_shape
from shapely.geometry import Point, Polygon

random.seed(7)

# Coordenadas aproximadas de referência (Passo Fundo / Não-Me-Toque, RS)
FAZENDAS_REF = [
    {"nome": "Fazenda Santa Rita", "municipio": "Passo Fundo", "lat": -28.263, "lon": -52.406},
    {"nome": "Fazenda Boa Esperança", "municipio": "Não-Me-Toque", "lat": -28.459, "lon": -52.826},
]


def _talhao_poligono(lat: float, lon: float, lado: float = 0.01) -> Polygon:
    """Gera um quadrado simples ao redor do ponto de referência — só para
    ter um polígono plausível, não representa um talhão real."""
    return Polygon(
        [
            (lon - lado, lat - lado),
            (lon + lado, lat - lado),
            (lon + lado, lat + lado),
            (lon - lado, lat + lado),
            (lon - lado, lat - lado),
        ]
    )


def seed():
    session = get_session()

    maquinas_criadas = []

    for ref in FAZENDAS_REF:
        fazenda = Fazenda(
            id=uuid.uuid4(),
            nome=ref["nome"],
            municipio=ref["municipio"],
            criado_em=datetime.utcnow(),
        )
        session.add(fazenda)
        session.flush()  # garante fazenda.id disponível

        talhao = Talhao(
            id=uuid.uuid4(),
            fazenda_id=fazenda.id,
            nome=f"Talhão 1 — {ref['nome']}",
            area_ha=round(random.uniform(40, 120), 1),
            geom=from_shape(_talhao_poligono(ref["lat"], ref["lon"]), srid=4326),
        )
        session.add(talhao)

        maquina_jd = Maquina(
            id=uuid.uuid4(),
            fazenda_id=fazenda.id,
            fabricante=Fabricante.JOHN_DEERE,
            modelo="John Deere 6110J",
            identificador_externo="JD-0001",
        )
        maquina_nh = Maquina(
            id=uuid.uuid4(),
            fazenda_id=fazenda.id,
            fabricante=Fabricante.nh,
            modelo="New Holland TL75E",
            identificador_externo="nh-0001",
        )
        session.add_all([maquina_jd, maquina_nh])
        session.flush()

        maquinas_criadas.append((maquina_jd, talhao, ref))
        maquinas_criadas.append((maquina_nh, talhao, ref))

    # --- leituras de telemetria fictícias (já no schema limpo/universal) ---
    for maquina, talhao, ref in maquinas_criadas:
        arquivo = ArquivoImportado(
            id=uuid.uuid4(),
            maquina_id=maquina.id,
            fabricante=maquina.fabricante,
            nome_arquivo=f"ficticio_{maquina.identificador_externo}.csv",
            caminho_storage=f"ficticios/{maquina.identificador_externo}.csv",
            status=StatusArquivo.PROCESSADO,
            linhas_aceitas=120,
            linhas_rejeitadas=3,
            recebido_em=datetime.utcnow(),
            processado_em=datetime.utcnow(),
        )
        session.add(arquivo)
        session.flush()

        horimetro = round(random.uniform(500, 3000), 1)
        momento = datetime(2026, 9, 1, 7, 0, 0)
        combustivel_total = 0.0
        horas_trabalhadas = 0.0

        for _ in range(120):
            lat = ref["lat"] + random.uniform(-0.005, 0.005)
            lon = ref["lon"] + random.uniform(-0.005, 0.005)
            horimetro += round(random.uniform(0.01, 0.05), 3)
            consumo = round(random.uniform(0.5, 3.0), 2)  # L nesse intervalo
            combustivel_total += consumo
            horas_trabalhadas += 1 / 60  # 1 leitura por minuto

            leitura = LeituraTelemetria(
                id=uuid.uuid4(),
                arquivo_importado_id=arquivo.id,
                maquina_id=maquina.id,
                talhao_id=talhao.id,
                timestamp=momento,
                geom=from_shape(Point(lon, lat), srid=4326),
                horimetro=horimetro,
                combustivel_consumido_l=consumo,
                velocidade_kmh=round(random.uniform(0, 12), 1),
            )
            session.add(leitura)
            momento += timedelta(minutes=1)

        session.flush()

        # KPI agregado do período gerado
        kpi = KpiOperacao(
            id=uuid.uuid4(),
            maquina_id=maquina.id,
            talhao_id=talhao.id,
            periodo_inicio=datetime(2026, 9, 1, 7, 0, 0),
            periodo_fim=momento,
            combustivel_total_l=round(combustivel_total, 2),
            horas_trabalhadas=round(horas_trabalhadas, 2),
            litros_por_hectare=round(combustivel_total / talhao.area_ha, 3),
            calculado_em=datetime.utcnow(),
        )
        session.add(kpi)

        # Um alerta fictício por máquina, para o Guilherme já ter algo a exibir
        alerta = AlertaAnomalia(
            id=uuid.uuid4(),
            maquina_id=maquina.id,
            leitura_id=leitura.id,  # última leitura gerada
            tipo=random.choice(list(TipoAnomalia)),
            severidade=random.choice(list(Severidade)),
            descricao=(
                "Alerta fictício gerado para desenvolvimento/teste "
                "(sem dado real por trás)."
            ),
            criado_em=datetime.utcnow(),
        )
        session.add(alerta)

    session.commit()
    print(f"Seed concluído: {len(maquinas_criadas)} máquinas, "
          f"{len(maquinas_criadas) * 120} leituras fictícias.")


if __name__ == "__main__":
    seed()
