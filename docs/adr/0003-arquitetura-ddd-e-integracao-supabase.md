# ADR 0003 — Arquitetura DDD e integração com Supabase/PostGIS

## Camadas (`src/sistemacampero/`)

| Camada | Conteúdo | Depende de |
|---|---|---|
| `domain/` | entidades (`WorkSession`, `FieldBoundary`, `SessionMetrics`, `Alert`), portas (`ports.py`), serviços de domínio: sanitização, métricas, regras, junção espacial (`FieldLocator`), decimação | nada externo |
| `application/` | casos de uso: `IngestionService` (etapas 1–3), `AnalysisService` (4–5), `PublishingService`, `TelemetryProcessor` (ponta a ponta) | domínio |
| `infrastructure/` | parser/adapter JDL, leitor de contornos do monitor, `LocalWorkspace` (Parquet), repositórios Supabase, `config`, `container` (raiz de composição) | domínio + aplicação |
| `interfaces/` | API FastAPI (`api/app.py`, entrada `api/main.py`) e CLI (`cli.py`) | tudo, via `container` |

Estilo: PEP 8 verificado com Ruff (`ruff check`, `ruff format`; regras E, W, F, I, N, UP, B, SIM, C4).

## O que mudou em relação ao commit `49fc79b` (extração por varredura de bytes)

- O parser por "pattern matching" de `double` foi **removido**: devolvia vazão 15,0, velocidade 8,0 e
  RPM 1800 fixos e `timestamp=None`, então toda métrica seria fictícia. O formato `.jdl` é protobuf
  padrão com enquadramento (ver ADR 0001), e é lido por `jdl.py`; `telemetry.proto`/`telemetry_pb2.py`
  (tags "provisórias") e as dependências `grpcio-tools`/`protobuf` saíram.
- Junção espacial **em memória** (STRtree) com os talhões carregados uma vez por processamento, em vez
  de uma chamada RPC `get_talhao_by_point` por ponto GPS (dezenas de milhares por arquivo).
- Contornos: só `boundarytype == "Exterior"`; o importador antigo também gravava as cabeceiras
  geradas pelo monitor como se fossem talhões e usava propriedades (`Farm`, `Client`) que não existem
  no `.gjson`. Agora fazenda/cliente vêm do `MasterData.xml`, com upsert por GUID.
- Upload: nome físico por UUID (sem colisão nem path traversal), limite de tamanho, só `.jdl`,
  remoção do temporário em `finally`, job com status consultável, API key opcional.
- KPIs (`/stats`) vêm das métricas por sessão; antes eram calculados sobre as primeiras 1.000 linhas
  (limite padrão do PostgREST), truncando em silêncio.
- Sem `create_client` no import: sem credenciais o sistema roda local.

## Contrato de API preservado

`POST /api/v1/telemetry/upload?marca=&tecnologia=` (um arquivo por chamada, em paralelo pelo
frontend), `GET /api/v1/telemetry/machine/{serial}`, `GET /api/v1/telemetry/stats/{serial}`.
Novos: `GET /api/v1/jobs/{id}`, `/sessions`, `/alerts`, `POST /api/v1/analysis/run`, `/health`.

## Pendências conhecidas

- Os arquivos brutos ficam no workspace em disco; em Render/Railway o disco é efêmero sem volume.
  Falta enviar o bruto ao Supabase Storage.
- Sem autenticação por usuário/organização (só API key única); RLS ligado e sem policies.
- Não foi possível testar contra um Supabase real neste ambiente: o cliente é coberto por dublê nos
  testes; rode `supabase db push` e um upload real para validar.
