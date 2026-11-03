# Deploy (Supabase + Railway)

Ambientes: **dev** (docker compose local) · **staging** (Supabase + Railway) · **prod** (Supabase
**Pro**, região `sa-east-1` + Railway). Projeto Supabase free pausa após 1 semana sem uso e não tem
backup diário: para o piloto, use Pro.

## 1. Supabase (uma vez por ambiente)

1. Criar o projeto (região São Paulo). Em **Settings > API**, usar as chaves novas
   (`sb_publishable_...` no frontend, `sb_secret_...` só no backend) e ativar **JWT signing keys
   assimétricas** (o backend valida pelo JWKS).
2. Migrations (do repositório, nunca à mão):
   ```bash
   supabase link --project-ref <ref>
   supabase db push
   ```
   O workflow `.github/workflows/migrations.yml` faz isso: staging em push na `main`, produção em tag `v*`.
   **Rede bloqueando a porta 5432?** (comum em redes de empresa/faculdade) Gere o script único com
   `uv run python scripts/gerar_sql_supabase.py` e rode `configurar_supabase.sql` no **SQL Editor**
   (pelo navegador). O arquivo contém a senha do `campero_backend` e está no `.gitignore`. Nesse caso a
   API também não roda na sua máquina contra o Supabase: use outra rede ou o Railway.
3. Senha do papel da aplicação (SQL editor, uma vez; guardar no cofre):
   ```sql
   alter role campero_backend password '<senha forte gerada>';
   ```
4. **Storage > Settings**: subir o limite global de tamanho de arquivo para ≥ 1 GB (o zip do
   pendrive passa de 50 MB). Os buckets `brutos`, `limpos` e `exportacoes` são criados pela migration
   (privados).
5. Auth: e-mail/senha ou magic link; URL do site = URL do frontend.

## 2. Railway

Dois serviços **da mesma imagem** (Dockerfile do repositório), deploy só com CI verde ("Wait for CI"):

| Serviço | Start command | Healthcheck |
|---|---|---|
| `api` | `sistemacampero api` | `/ready` |
| `worker` | `sistemacampero worker` | — (sem HTTP) |

Variáveis (nos dois, exceto onde indicado):

| Variável | Valor |
|---|---|
| `AMBIENTE` | `staging` ou `prod` |
| `DATABASE_URL` | `postgresql://campero_backend.<ref>:<senha>@aws-0-sa-east-1.pooler.supabase.com:5432/postgres` (pooler, **modo sessão**) |
| `SUPABASE_URL` | `https://<ref>.supabase.co` |
| `SUPABASE_SECRET_KEY` | `sb_secret_...` |
| `STORAGE_BACKEND` | `supabase` |
| `CHAVE_CIFRAGEM` | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `FRONTEND_URL` | URL do frontend (links de convite/alerta) |
| `SMTP_HOST`, `SMTP_PORTA`, `SMTP_USUARIO`, `SMTP_SENHA`, `SMTP_REMETENTE` | provedor de e-mail com SPF/DKIM no domínio |
| `CORS_ORIGENS` | `["https://app.seudominio.com.br"]` (só `api`) |
| `DB_POOL_MAX` | `10` (api), `4` (worker) |

Escala: mais réplicas do `worker` processam em paralelo (`SKIP LOCKED`). A API tem limite de
requisições **por instância** (memória); com mais de uma réplica, mover o limite para o proxy.

**Conexões no plano gratuito do Supabase** (medido na carga do pendrive real, 1.586 arquivos):
o pooler em **modo sessão** (porta 5432) aceita poucos clientes. Com a API e mais de um worker,
cada processo com `DB_POOL_MAX=10`, ele recusa conexões (`EMAXCONNSESSION max clients reached`)
e tudo para. Use o **modo transação** (porta 6543) com pools pequenos:

| Processo | `DATABASE_URL` (porta) | `DB_MODO_POOLER` | `DB_POOL_MAX` |
|---|---|---|---|
| `api` | `...pooler.supabase.com:6543/postgres` | `transacao` | `3` |
| `worker` (cada réplica) | `...pooler.supabase.com:6543/postgres` | `transacao` | `2` |

A aplicação não usa recursos de sessão (advisory locks, `LISTEN`, `SET` fora de transação):
a organização ativa vai em `set_config(..., true)`, local à transação. Com 6 a 8 workers, a
carga processou de 15 a 28 arquivos por minuto (banco no Canadá; cada arquivo faz várias idas
ao banco e ao Storage). O pool insiste na reconexão por até 24 h, então uma queda de rede longa
não deixa o worker preso.

**Latência**: o Railway pode não ter região na América do Sul. Com API nos EUA e banco em São Paulo,
cada consulta custa ~120 ms; as rotas foram feitas com poucas consultas e agregados prontos
(`metricas_diarias`). Medir no staging antes do piloto.

## 3. Verificação pós-deploy

```bash
curl https://<api>/ready                         # {"status":"ok","checks":{"banco":"ok","storage":"ok"}}
curl -H "Authorization: Bearer <jwt>" https://<api>/api/v1/me
```
Depois: criar a organização, enviar um `.jdl` pequeno e ver `GET /api/v1/jobs/{id}` chegar a `concluido`.
