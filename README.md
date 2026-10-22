# 🚜 Campero Sistemas — backend v1

> **Fim da cegueira multimarca no campo.** Plataforma SaaS que unifica a telemetria de frotas
> agrícolas de diferentes fabricantes (pendrive do monitor) em métricas e alertas acionáveis.
> Operação inicial: Passo Fundo e região (RS).

Estado: **M1 (Fundação)** do plano do backend v1. Decisões em
[`docs/adr/0004-backend-v1-fundacao.md`](docs/adr/0004-backend-v1-fundacao.md).

| Marco | Conteúdo | Status |
|---|---|---|
| M1 Fundação | DDD, config, API (problem+json, request id, métricas), auth JWT (JWKS/HS256), org ativa, schema completo + RLS + GRANTs, Docker, CI | ✅ |
| M2 Parser + universal + sanitização | adapter JD Gen4, contrato de adapters, correção dos 3 defeitos conhecidos, regressão | próximo |
| M3–M9 | ingestão assíncrona, cadastro/geo, KPIs, alertas, equipe, exportação, operação | — |

## Estrutura

```
src/sistemacampero/
  domain/          entidades, portas (Protocol), erros tipados — sem FastAPI/psycopg/os.environ
  application/     casos de uso (tenancy; ingestion, analysis... nos próximos marcos)
  infrastructure/  config (pydantic-settings), persistence (psycopg 3), security (JWT), container
  interfaces/      api/ (FastAPI), cli.py
supabase/migrations/   schema versionado (fonte da verdade)
db/bootstrap_supabase_local.sql   só dev/teste: o que o Supabase já traz pronto
tests/unit/        sem I/O       tests/integracao/   PostGIS real, como cada papel
```

## Rodando local

Pré-requisitos: [uv](https://docs.astral.sh/uv/) e Docker.

```bash
uv sync
uv run pytest tests/unit                        # sem banco
docker compose up --build                       # PostGIS + migrations + API em http://localhost:8000/docs
```

Testes de integração (com o `db` do compose de pé; cada execução cria e apaga um banco próprio):

```bash
# PowerShell: $env:CAMPERO_TEST_DATABASE_URL="postgresql://postgres:postgres@localhost:54322/postgres"
export CAMPERO_TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:54322/postgres
uv run pytest
```

Qualidade (o CI roda o mesmo):

```bash
uv run ruff format --check src tests && uv run ruff check src tests && uv run mypy
```

Rodar a API fora do Docker: copie `.env.example` para `.env`, preencha e
`uv run sistemacampero api --reload`. Migrations num banco qualquer:
`uv run sistemacampero db migrar --database-url <dsn>` (`--bootstrap` só em PostGIS local).

## API (v1)

Prefixo `/api/v1`, OpenAPI em `/docs`. Autenticação: `Authorization: Bearer <JWT do Supabase>`.
Organização ativa: header `X-Organizacao-Id` (opcional se o usuário tiver uma só).

| Rota | Descrição |
|---|---|
| `GET /health` · `GET /ready` · `GET /metrics` | vivo · banco ok · Prometheus |
| `GET /api/v1/me` | usuário e organizações |
| `POST /api/v1/organizacoes` | cria a primeira organização (owner, plano básico em trial) |
| `GET /api/v1/organizacao-ativa` | organização e papel que valem para a requisição |

Erros seguem RFC 9457 (`application/problem+json`) com `code` estável, por exemplo
`NAO_AUTENTICADO`, `TOKEN_EXPIRADO`, `SEM_ORGANIZACAO`, `ORGANIZACAO_AMBIGUA`, `SLUG_EM_USO`.

## Segurança

- **Rotacione a chave `service_role`** exposta no histórico (commit `49fc79b`):
  [`docs/seguranca-rotacao-de-chave.md`](docs/seguranca-rotacao-de-chave.md).
- Nunca commite `.env`, `.jdl`, `.parquet` nem dados de clientes. O CI roda gitleaks e pip-audit.

## Equipe e fluxo Git

Marcos (negócios/legal) · Charles (vendas, operação pendrive) · João (frontend) ·
Raul (backend, PostGIS/APIs) · Guilherme (backend, IA/parser/métricas).

Branches `feat/`, `fix/`, `docs/`, `refactor/`; Conventional Commits; PR com 1 aprovação;
`main` protegida.
