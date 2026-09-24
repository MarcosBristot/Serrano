# Sistema Campero — backend (passo 1: schema + dados fictícios)

Entregável do **passo 1** do roteiro: schema versionado (models + migration)
e dados fictícios para destravar o desenvolvimento em paralelo, já que ainda
não há arquivos reais de máquina.

## Estrutura

```
app/
  models/schema.py        # models SQLAlchemy + GeoAlchemy2 (entidades + pipeline)
  db/session.py           # engine/sessão (lê DATABASE_URL do ambiente)
migrations/
  env.py                  # config do Alembic apontando para os models
  versions/0001_initial_schema.py   # cria todas as tabelas + extensão PostGIS
scripts/
  gerar_arquivos_brutos_ficticios.py   # CSVs fictícios simulando 2 "dialetos" (JD/CNH)
  seed_dados_ficticios.py              # popula o banco já no schema limpo + KPIs + alertas
```

## Como rodar (com `uv`)

```bash
uv sync
export DATABASE_URL="postgresql://postgres:<senha>@<host-supabase>:5432/postgres"

# aplica o schema no banco
uv run alembic upgrade head

# gera CSVs fictícios (fixtures para os adapters, na pasta dados_ficticios/brutos/)
uv run python scripts/gerar_arquivos_brutos_ficticios.py

# popula o banco com dado limpo fictício (fazenda, talhão, máquina, leituras, KPI, alerta)
uv run python scripts/seed_dados_ficticios.py
```

> **Atenção:** o schema de entidades (`Fazenda`, `Talhao`, `Maquina`) foi
> inferido a partir do contexto do projeto, pois não tive acesso ao modelo
> exato já validado em equipe. Comparem `app/models/schema.py` com o que
> foi validado e ajustem nomes/colunas antes de rodar a migration em cima
> do banco real do Supabase.

## Divisão de trabalho sugerida (Raul / Guilherme)

A ideia é que, com o seed rodando, o Guilherme não precisa esperar o parser
real ficar pronto para começar a API — ele já tem dado no banco no formato
final.

**Raul** (dono do schema e dos dados de entrada)
1. ✅ Schema versionado + migration (este entregável)
2. ✅ Dados fictícios — CSVs por marca + seed do banco (este entregável)
3. Adapter John Deere (usando `dados_ficticios/brutos/john_deere_*.csv` como fixture)
4. Camada de pré-validação/limpeza (sanitização de GPS, conversão de unidades)
5. Fechar o pipeline ponta a ponta para 1 fabricante (upload → limpo → KPI)
6. Adapter CNH (segunda marca, provando a abstração)

**Guilherme** (dono da API e do motor de regras — pode começar em paralelo,
direto sobre o resultado do seed)
2. Esqueleto do FastAPI (`api/`), endpoint de upload básico, docs OpenAPI
7. Motor de regras de anomalia (consumo excessivo, ociosidade, queda
   suspeita de combustível) — rodando sobre `leitura_telemetria` do seed
8. Endpoints estáveis (`kpi_operacao`, `alerta_anomalia`) para o João
   integrar o frontend, e testes com dado real assim que a prospecção trouxer

Os números acima seguem a numeração do roteiro de 8 passos já combinado.
