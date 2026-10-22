# ADR 0004 — Backend v1: fundação (M1)

Status: aceito em 21/10/2026 (plano M0 aprovado). Branch `rebuild/backend-v1`, criado de `main`.

## Decisões

| # | Decisão | Por quê |
|---|---|---|
| D1 | **psycopg 3 + SQL explícito**, sem ORM e sem `supabase-py`. Supabase só para Auth (JWT/JWKS) e Storage (REST via `httpx`, M3) | `COPY`, agregações e PostGIS ficam legíveis em SQL. O PostgREST causou truncamento em 1.000 linhas, o erro 42501 e chamadas por ponto |
| D1a | Papel **`campero_backend`** (LOGIN, sem BYPASSRLS, sem DDL) + `set_config('app.organizacao_id', …, true)` em toda transação | Defesa em profundidade: um `WHERE organizacao_id` esquecido é barrado pela RLS (teste `test_backend_update_esquecendo_where_fica_na_org`) |
| D1b | API e worker **síncronos** (`def` no threadpool + `psycopg_pool`) | Escala do piloto; o mesmo repositório serve API, worker e CLI |
| D1c | Conexão pelo **pooler Supavisor em modo sessão** (5432, IPv4) | A conexão direta do Supabase é só IPv6. Modo transação → `DB_MODO_POOLER=transacao` (desliga prepared statements) |
| D2 | Fila em **tabela Postgres** (`interno.jobs`, `FOR UPDATE SKIP LOCKED`, lease + heartbeat + reaper) | Transacional com o dado, zero infraestrutura nova. Implementação no M3 |
| D3 | **Migrations SQL versionadas** em `supabase/migrations/` (Supabase CLI em staging/prod) | RLS, policies, GRANTs, `SECURITY DEFINER`, buckets e PostGIS são SQL puro |
| D3a | `db/bootstrap_supabase_local.sql` recria no PostGIS comum o que o Supabase traz (papéis, `auth.uid()`, `storage.buckets`, privilégios padrão) | Testes de integração em banco vazio, como cada papel real |
| D4 | Erros `application/problem+json` (RFC 9457) com `code` estável; `X-Request-ID`; logs JSON; `/metrics` Prometheus | O frontend trata por código; suporte rastreia por request_id |

## Quem acessa o quê (RLS)

| Papel | Uso | Acesso |
|---|---|---|
| `anon` | — | nada |
| `authenticated` | frontend via Data API | **só SELECT**, nas orgs de que é membro (`orgs_do_usuario()`); não lê `telemetria`, `convites`, `destinos_notificacao` |
| `campero_backend` | API e worker | DML filtrado por `app.organizacao_id`; schema `interno` (jobs, chaves, outbox, auditoria só-acrescenta) |
| `service_role` | scripts administrativos | DML explícito (GRANT); BYPASSRLS no Supabase |

`app.organizacao_id` **não** é aceito para `authenticated` (teste `test_authenticated_nao_usa_app_organizacao_id`).
Partições de `telemetria` têm todos os privilégios revogados: só se acessa pelo pai, onde vale a RLS.

## Configuração de um ambiente Supabase (uma vez)

1. `supabase link --project-ref <ref>` e `supabase db push` (o CI faz isso no M9).
2. No SQL editor: `alter role campero_backend password '<gerada>';` e guarde no cofre/Railway.
3. `DATABASE_URL=postgresql://campero_backend.<ref>:<senha>@aws-0-sa-east-1.pooler.supabase.com:5432/postgres`
4. `SUPABASE_URL=https://<ref>.supabase.co` (JWKS). Migre para chaves de assinatura assimétricas.

## Consequências

- O código antigo (`feat/pipeline-ddd-integrado`) segue como referência para o M2 (parser JDL, sanitização,
  métricas). O MVP em Streamlit foi movido para `legacy/mvp/`.
- O frontend lê o Supabase diretamente apenas para SELECTs simples; toda escrita passa pela API.
