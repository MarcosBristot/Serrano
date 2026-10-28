# 🚜 Serrano — backend v1

> **Fim da cegueira multimarca no campo.** Plataforma SaaS que unifica a telemetria de frotas
> agrícolas de diferentes fabricantes (pendrive do monitor) em métricas e alertas acionáveis.
> Operação inicial: Passo Fundo e região (RS).

Estado: **primeira versão completa (M1–M9)** do plano do backend v1. Deploy: [`docs/deploy.md`](docs/deploy.md) ·
operação: [`docs/runbook.md`](docs/runbook.md) · piloto: [`docs/checklist-piloto.md`](docs/checklist-piloto.md). Decisões em
[`docs/adr/0004`](docs/adr/0004-backend-v1-fundacao.md) (fundação),
[`docs/adr/0005`](docs/adr/0005-formato-jdl-ancoras-e-gps.md) (formato `.jdl` e defeitos corrigidos) e
[`docs/adr/0006`](docs/adr/0006-ingestao-assincrona.md) (ingestão assíncrona) e
[`docs/adr/0007`](docs/adr/0007-cadastro-geo-e-cobertura.md) (cadastro, localização e cobertura).

| Marco | Conteúdo | Status |
|---|---|---|
| M1 Fundação | DDD, config, API (problem+json, request id, métricas), auth JWT (JWKS/HS256), org ativa, schema completo + RLS + GRANTs, Docker, CI | ✅ |
| M2 Parser + universal + sanitização | adapter JD Gen4 (âncoras, trilha GPS 5 Hz), registro e contrato de adapters, sanitização, métricas, qualidade, regras, 3 defeitos corrigidos, linha de base de 2026 | ✅ |
| M3 Ingestão assíncrona | Storage (local + Supabase), fila durável com lease/reaper/backoff/dead-letter, worker, upload/lote/zip seguro, dedupe, cancelamento, limite do plano | ✅ |
| M4 Cadastro + geo | CRUD, importação Gen4 (MasterData + contornos), contorno por desenho/GeoJSON, localização por GPS, correção manual, relocalização, área por cobertura | ✅ |
| M5 Métricas + KPIs | métricas diárias (dia local, talhão por ponto), resumo, séries (hora/dia/semana/mês), ranking, safras, trajeto GeoJSON, mapa de calor de L/ha, preço do diesel e R$/ha, rotas legadas `/telemetry/*` | ✅ |
| M6 Regras + alertas | ciclo de vida, comentários, limiares por organização, linhas de base (vazão, L/ha), reanálise, notificações (webhook HMAC, e-mail) com outbox | ✅ |
| M7 Equipe | convites, papéis, chaves de API, auditoria automática | ✅ |
| M8 Exportação + qualidade | CSV em streaming (Excel pt-BR), CSV/XLSX assíncrono com link, relatório de qualidade explicado | ✅ |
| M9 Operação | rate limit, cabeçalhos de segurança, deploy (Supabase + Railway + CI de migrations), runbook, checklist do piloto | ✅ |

## Estrutura

```
src/sistemacampero/
  domain/          entidades, schema universal, portas (Protocol), erros tipados
    services/      sanitization, metrics, quality, rules, geo — sem FastAPI/psycopg/os.environ
  application/     casos de uso (tenancy, processamento de arquivo)
  infrastructure/  config, persistence (psycopg 3), security (JWT), parsers/ (adapters), container
  interfaces/      api/ (FastAPI), cli.py
supabase/migrations/   schema versionado (fonte da verdade)
db/bootstrap_supabase_local.sql   só dev/teste: o que o Supabase já traz pronto
tests/unit/  sem I/O · tests/contrato/  todo adapter · tests/regressao/  defeitos do M0
tests/sinteticos/  gerador de .jdl · tests/integracao/  PostGIS real, como cada papel
scripts/regressao_dump.py   regressão com o dump real (fora do Git) x linha de base congelada
```

## Rodando local

Pré-requisitos: [uv](https://docs.astral.sh/uv/) e Docker.

```bash
uv sync
uv run pytest tests/unit                        # sem banco
docker compose up --build                       # PostGIS + migrations + API + worker (http://localhost:8000/docs)
```

Testes de integração (com o `db` do compose de pé; cada execução cria e apaga um banco próprio):

```bash
# PowerShell: $env:CAMPERO_TEST_DATABASE_URL="postgresql://postgres:postgres@localhost:54322/postgres"
export CAMPERO_TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:54322/postgres
uv run pytest
```

Qualidade (o CI roda o mesmo):

```bash
uv run ruff format --check src tests scripts && uv run ruff check src tests scripts && uv run mypy
```

Regressão com um dump real de pendrive (a pasta não vai para o Git):

```bash
uv run python scripts/regressao_dump.py "<pasta JD-Data/log>"
```

Nova marca: [`docs/como-adicionar-marca.md`](docs/como-adicionar-marca.md).

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
| `POST /api/v1/telemetry/upload?marca=&tecnologia=&lote_id=` | **um** `.jdl` ou `.zip` por chamada; 202 com `job_id`, `arquivo_id`, `duplicado` |
| `POST /api/v1/batches` · `GET /api/v1/batches/{id}` | lote de uploads e status agregado |
| `GET /api/v1/jobs/{id}` · `POST /api/v1/jobs/{id}/cancelar` | situação do processamento |
| `GET /api/v1/arquivos?status=&limit=&cursor=` | arquivos recebidos (paginação por cursor) |
| `GET/POST/PATCH/DELETE /api/v1/fazendas`, `/talhoes`, `/implementos`, `/operadores` | cadastro (talhão com GeoJSON) |
| `PUT /api/v1/talhoes/{id}/contorno` · `PUT .../contorno/arquivo` · `DELETE .../contorno` | contorno desenhado ou `.gjson`; reprocessa as sessões afetadas |
| `GET /api/v1/maquinas` · `PATCH /api/v1/maquinas/{id}` | apelido, ativar/desativar (respeita o plano) |
| `GET /api/v1/sessions` · `GET /api/v1/sessions/{id}` · `PATCH /api/v1/sessions/{id}` | sessões; talhão manual e operador |
| `GET /api/v1/kpis/resumo` · `/kpis/series?granularidade=` · `/kpis/ranking?por=` · `/kpis/safras?comparar=` | KPIs (filtros: `inicio`, `fim`, `maquina_id`, `talhao_id`, `operacao`) |
| `GET /api/v1/mapas/calor` · `GET /api/v1/sessions/{id}/track` | mapa de calor de L/ha e trajeto (GeoJSON) |
| `GET/POST/PATCH /api/v1/precos-combustivel` | preço do diesel por período (padrão: ANP RS, S10 R$ 6,59/L) |
| `GET /api/v1/telemetry/machine/{serial}` · `GET /api/v1/telemetry/stats/{serial}` | contrato legado do frontend |
| `GET /api/v1/alerts` · `GET /alerts/{id}` · `POST /alerts/{id}/reconhecer\|resolver\|reabrir` · `POST /alerts/{id}/comentarios` | alertas |
| `GET/PUT /api/v1/config/regras` · `POST /api/v1/analysis/run` | limiares e reanálise |
| `GET/POST/PATCH/DELETE /api/v1/destinos-notificacao` · `POST .../{id}/teste` | e-mail/webhook |
| `GET /api/v1/membros` · `POST /convites` · `POST /convites/{token}/aceitar` · `/chaves-api` · `/auditoria` | equipe |
| `GET /api/v1/exportacoes/csv` · `POST /exportacoes` · `GET /exportacoes/{id}` · `GET /qualidade/relatorio` | exportação e qualidade |
| `GET /api/v1/admin/jobs?status=morto` · `POST /api/v1/admin/jobs/{id}/reenfileirar` · `POST /api/v1/admin/reabrir-bloqueados` | operação (só owner) |

Erros seguem RFC 9457 (`application/problem+json`) com `code` estável, por exemplo
`NAO_AUTENTICADO`, `TOKEN_EXPIRADO`, `SEM_ORGANIZACAO`, `ORGANIZACAO_AMBIGUA`, `SLUG_EM_USO`,
`FORMATO_NAO_SUPORTADO`, `ARQUIVO_GRANDE_DEMAIS` (413), `PAPEL_SEM_PERMISSAO`,
`GEOMETRIA_INVALIDA`, `PLANO_LIMITE_MAQUINAS` (409), `REFERENCIA_INEXISTENTE`.

## Segurança

- **Rotacione a chave `service_role`** exposta no histórico (commit `49fc79b`):
  [`docs/seguranca-rotacao-de-chave.md`](docs/seguranca-rotacao-de-chave.md).
- Nunca commite `.env`, `.jdl`, `.parquet` nem dados de clientes. O CI roda gitleaks e pip-audit.

## Equipe e fluxo Git

Marcos (negócios/legal) · Charles (vendas, operação pendrive) · João (frontend) ·
Raul (backend, PostGIS/APIs) · Guilherme (backend, IA/parser/métricas).

Branches `feat/`, `fix/`, `docs/`, `refactor/`; Conventional Commits; PR com 1 aprovação;
`main` protegida.
