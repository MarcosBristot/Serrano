# Deploy (Supabase + Fly.io + Cloudflare Pages)

Tudo em **São Paulo**: banco e storage no Supabase `sa-east-1`, API e worker no Fly.io `gru`.
Banco e worker longe um do outro foi o que deixou o processamento lento no piloto (worker no Brasil,
banco no Canadá: ~10 arquivos/min com 6 workers; 875 arquivos levaram mais de 1 h). Na mesma região,
o pendrive de uma fazenda nova (45 MB) processou em 73 s.

| Peça | Onde | Custo aproximado |
|---|---|---|
| Banco, Auth, Storage | Supabase **Pro**, `sa-east-1` | US$ 25/mês |
| API (1 máquina, 512 MB) e worker (1 máquina, 1 GB) | Fly.io, `gru` | ~US$ 10/mês |
| Painel (estático) | Cloudflare Pages | grátis |

**Por que Pro**: no plano free o Storage recusa arquivo acima de **50 MB** (o zip da colheitadeira
passa disso), o projeto **pausa após 7 dias sem uso** e não há backup diário. Para teste interno o
free funciona, dividindo zips grandes.

Ambientes: **dev** (docker compose local) · **staging** e **prod** (cada um com seu projeto Supabase
e seu app no Fly).

## 1. Supabase (uma vez por ambiente)

A região de um projeto Supabase não muda depois de criado: para sair do Canadá, crie um projeto novo
(ver [Sair do projeto atual](#5-sair-do-projeto-atual-canadá)).

1. Criar o projeto na região **South America (São Paulo)**. Em **Settings > API**, usar as chaves
   novas (`sb_publishable_...` no frontend, `sb_secret_...` só no backend) e ativar **JWT signing
   keys assimétricas** (o backend valida pelo JWKS).
2. Migrations (do repositório, nunca à mão):
   ```bash
   supabase link --project-ref <ref>
   supabase db push
   ```
   O workflow `.github/workflows/migrations.yml` faz isso: staging em push na `main`, produção em tag `v*`.
   **Rede bloqueando a porta 5432?** (comum em redes de empresa/faculdade) Gere o script único com
   `uv run python scripts/gerar_sql_supabase.py` e rode `configurar_supabase.sql` no **SQL Editor**
   (pelo navegador). O arquivo contém a senha do `campero_backend` e está no `.gitignore`.
3. Senha do papel da aplicação (SQL editor, uma vez; guardar no cofre):
   ```sql
   alter role campero_backend password '<senha forte gerada>';
   ```
4. **Storage > Settings** (Pro): subir o limite global de tamanho de arquivo para 1 GB. Os buckets
   `brutos`, `limpos` e `exportacoes` são criados pela migration (privados).
5. **Auth > URL Configuration**: Site URL = URL do painel; em Redirect URLs, a mesma URL com `/**`.

## 2. Fly.io (API e worker)

Uma imagem, dois processos (`fly.toml` na raiz): `api` (HTTP, sempre 1 máquina ligada) e `worker`
(sem HTTP, lê a fila). Memória medida reprocessando 4.309 arquivos (trator e colheitadeira): pico de
464 MB no worker e 153 MB na API, por isso 1 GB e 512 MB. Com banco ao lado, 4 workers levaram 10 min.

```bash
fly auth login
fly apps create serrano-api            # ou outro nome; ajuste "app" no fly.toml
fly platform regions | grep gru        # confere se São Paulo está disponível
```

Segredos (uma vez; valem para os dois processos):

```bash
fly secrets set \
  DATABASE_URL="postgresql://campero_backend.<ref>:<senha>@aws-0-sa-east-1.pooler.supabase.com:6543/postgres" \
  SUPABASE_URL="https://<ref>.supabase.co" \
  SUPABASE_SECRET_KEY="sb_secret_..." \
  CHAVE_CIFRAGEM="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')" \
  FRONTEND_URL="https://<painel>" \
  CORS_ORIGENS='["https://<painel>"]'
# E-mail (alertas, convites, resumo de segunda): SMTP_HOST SMTP_PORTA SMTP_USUARIO SMTP_SENHA SMTP_REMETENTE
```

`DATABASE_URL` usa o pooler em **modo transação** (porta **6543**). O `fly.toml` já define
`DB_MODO_POOLER=transacao` e o pool de cada processo (3 na API, 2 no worker).

Primeiro deploy e escala:

```bash
fly deploy
fly scale count api=1 worker=1
fly logs                                # acompanhar
```

Depois disso, o workflow `.github/workflows/deploy.yml` faz o deploy sozinho quando uma tag `v*`
passa pelas migrations (segredo `FLY_API_TOKEN` no environment `producao` do GitHub:
`fly tokens create deploy`).

**Escala**: cada worker a mais processa em paralelo (`SKIP LOCKED`): `fly scale count worker=3` na
época de colheita. Cada worker usa 2 conexões; no plano Pro o pooler aguenta folgado. A API tem
limite de requisições **por instância** (memória); com mais de uma máquina de API, mover o limite
para o proxy.

**Conexões no plano gratuito** (medido no piloto, 1.586 arquivos): o pooler em modo sessão
(porta 5432) recusa clientes (`EMAXCONNSESSION max clients reached`) com API e vários workers.
Por isso modo transação com pools pequenos. A aplicação não usa recursos de sessão (advisory
locks, `LISTEN`, `SET` fora de transação): a organização ativa vai em `set_config(..., true)`.

## 3. Painel (Cloudflare Pages)

Em **Workers & Pages > Create > Pages > Connect to Git**, escolher o repositório:

| Campo | Valor |
|---|---|
| Root directory | `frontend` |
| Build command | `npm ci && npm run build` |
| Output directory | `dist` |
| Variáveis | `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY`, `VITE_API_URL=https://serrano-api.fly.dev/api/v1`, `VITE_SITE_URL` |

As variáveis `VITE_*` são públicas (vão para o navegador): nunca coloque a `sb_secret_...` aqui.
Sem `404.html`, o Pages devolve o `index.html` em qualquer rota (o React Router cuida do resto).
`frontend/public/_headers` define cache longo para `/assets` e cabeçalhos de segurança.
O site institucional (`site/`) é outro projeto do Pages com root `site`.

Domínio próprio: `app.seudominio.com.br` no Pages e `api.seudominio.com.br` no Fly
(`fly certs add api.seudominio.com.br`). Atualize `CORS_ORIGENS`, `FRONTEND_URL`, `VITE_API_URL`
e a Site URL do Auth.

## 4. Verificação pós-deploy

```bash
curl https://<api>/ready                         # {"status":"ok","checks":{"banco":"ok","storage":"ok"}}
curl -H "Authorization: Bearer <jwt>" https://<api>/api/v1/me
```

Depois: entrar no painel, criar a fazenda, enviar o pendrive em `.zip` e acompanhar em
**Arquivos do monitor** até tudo ficar processado. `fly logs -i <máquina do worker>` mostra cada job.

## 5. Sair do projeto atual (Canadá)

O projeto do piloto (`ca-central-1`) só tem dados de teste e o usuário do próprio time. O caminho
mais simples e seguro é **começar limpo** no projeto novo:

1. Criar o projeto em São Paulo e seguir as seções 1 a 4.
2. Criar a conta no painel novo e a organização.
3. Reenviar os pendrives (as pastas originais estão com o time; nada de dado de cliente no git).
   Com worker e banco na mesma região, isso leva minutos, não horas.
4. Conferir colheitas e totais com os números do projeto antigo (312 colheitas, ~167,8 mil sacas).
5. Pausar o projeto antigo e apagá-lo depois de uma semana sem problemas.

Copiar o banco (`pg_dump` de `public`, `interno`, `auth` e `storage`) só vale a pena quando já houver
produtor de verdade usando, porque os usuários do Auth e os arquivos do Storage precisam ir juntos.
