# Produção em casa (custo zero)

Para o piloto com 1 a 3 produtores: banco, arquivos do pendrive, API e worker numa máquina sua,
com `docker-compose.casa.yml`. Só o **login** fica no Supabase (plano grátis). O acesso pela internet
é por túnel: a máquina abre a conexão para fora pela porta 443, sem abrir porta no roteador. Funciona
em redes que bloqueiam o Postgres (como a da ATITUS), porque o banco nunca sai da máquina.

| Peça | Onde | Custo |
|---|---|---|
| Banco, arquivos, API, worker, backup | esta máquina (Docker) | zero |
| Login | Supabase Auth, plano grátis | zero |
| Endereço da API | Cloudflare Tunnel em `api.sistemaserrano.com.br` (ou ngrok, sem domínio) | domínio ~R$ 40/ano |
| Painel e landing | Cloudflare Workers: `app.sistemaserrano.com.br` (Worker `app`) e `sistemaserrano.com.br` + `www.` (Worker `www`) | zero |

Hoje (nov/2026): DNS do `sistemaserrano.com.br` na Cloudflare (plano Free), túnel `serrano-casa` com a rota
`api.sistemaserrano.com.br` → `http://api:8000`, `COMPOSE_PROFILES=cloudflare` e `TUNNEL_TOKEN` no `.env.casa`.
A Cloudflare grátis recusa requisição acima de **100 MB**: o painel manda pendrive grande em partes de 32 MB.

Sem limite de 50 MB por arquivo nem de 1 GB no total: o limite é o disco. Medido: pendrive de 45 MB
processa em ~73 s; 4.309 arquivos de trator e colheitadeira em 10 min com 4 workers.

**O que você assume**: a máquina fica **ligada e na tomada** (nada de suspender); o backup é seu
(aponte para HD externo ou Google Drive); o envio do produtor depende do upload da sua internet; com
dado de cliente, ative o **BitLocker** no disco.

## 1. Preparar a máquina (uma vez)

1. Docker Desktop: **Settings > General > Start Docker Desktop when you sign in**.
2. Windows: **Energia > Suspender: Nunca** (na tomada). Notebook: **fechar a tampa: não fazer nada**.
3. Windows Update: defina o horário ativo para não reiniciar no meio do dia. Depois de reiniciar,
   o Docker sobe tudo sozinho (`restart: unless-stopped`).

## 2. Login (Supabase, plano grátis)

Use o projeto que já existe ou crie um (qualquer região serve: só o login passa por ele).
Em **Authentication > URL Configuration**: Site URL = endereço do painel (passo 5).
Anote a **Project URL** e a **Publishable key** (`sb_publishable_...`).

## 3. Endereço público da API

**ngrok** (grátis, endereço fixo, sem domínio; recomendado para começar):

1. Crie a conta em ngrok.com (login com Google/GitHub).
2. **Your Authtoken**: copie para `NGROK_AUTHTOKEN`.
3. **Domains**: o plano grátis já traz um domínio fixo (`algo.ngrok-free.app`). Copie com `https://`
   para `NGROK_DOMINIO`. No `.env.casa`, `COMPOSE_PROFILES=ngrok`.
4. O endereço da API é esse domínio. O painel e a landing mandam o cabeçalho
   `ngrok-skip-browser-warning`, então a página de aviso do plano grátis não aparece para o produtor.

**Cloudflare Tunnel** (quando tiver domínio): **Zero Trust > Networks > Tunnels > Create**,
tipo Cloudflared, copie o token (`TUNNEL_TOKEN`), e em **Public hostname** aponte
`api.seudominio.com.br` para `http://api:8000`. No `.env.casa`, `COMPOSE_PROFILES=cloudflare`.

**Tailscale Funnel** (perfil `tailscale`): ficou configurado, mas no teste de 17/11/2026 os servidores
do Funnel não entregaram o tráfego para a máquina. Use o ngrok.

## 4. Subir

```bash
cp .env.casa.example .env.casa      # e preencha (senhas só com letras e números)
docker compose -f docker-compose.casa.yml --env-file .env.casa up -d --build
docker compose -f docker-compose.casa.yml --env-file .env.casa ps
curl https://<nome>.ngrok-free.app/ready      # {"status":"ok","checks":{"banco":"ok","storage":"ok"}}
```

Na primeira subida o `migrate` cria o banco e as tabelas; o `backup` faz a primeira cópia logo em
seguida. Atualizar depois de um `git pull`: o mesmo `up -d --build`.

## 5. Painel e landing (Cloudflare Workers, grátis)

Endereço sem o seu nome: em **Workers & Pages > Account details > Subdomain > Change**, troque o
subdomínio da conta (ex.: `serranoagro`). Os endereços ficam `https://app.serranoagro.workers.dev`
(painel) e `https://www.serranoagro.workers.dev` (landing). Os nomes `app` e `www` vêm dos
`wrangler.jsonc` de `frontend/` e `site/`: o Worker na Cloudflare precisa ter o mesmo nome.

| Worker | Root directory | Build command | Deploy command | Variáveis do build |
|---|---|---|---|---|
| `app` | `frontend` | `npm ci && npm run build` | `npx wrangler deploy` | `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY`, `VITE_API_URL=https://<nome>.ngrok-free.app/api/v1`, `VITE_SITE_URL=https://www.<subdominio>.workers.dev` |
| `www` | `site` | `npm ci && npm run build` | `npx wrangler deploy` | `VITE_API_URL=https://<nome>.ngrok-free.app/api/v1`, `VITE_APP_URL=https://app.<subdominio>.workers.dev` |

As variáveis ficam em **Settings > Build > Variables and secrets** (são lidas na hora do build; depois
de mudar, faça um deploy novo). No `.env.casa`: `FRONTEND_URL` = endereço do painel e
`CORS_ORIGENS=["https://app.<subdominio>.workers.dev","https://www.<subdominio>.workers.dev"]`
(a landing também chama a API, no formulário de demonstração); suba de novo. No Supabase, Site URL =
endereço do painel.

## 6. Backup e restauração

Todo dia às `BACKUP_HORA` (e ao subir, se o dia ainda não tem cópia): o banco em
`BACKUP_DIR/AAAA-MM-DD/campero.dump` (mantém `BACKUP_DIAS` dias, padrão 7) e os pendrives em
`BACKUP_DIR/arquivos/`, um espelho que só copia os arquivos novos (cada arquivo bruto tem o nome do
seu sha256 e nunca muda). Para a cópia sair da máquina, aponte `BACKUP_DIR` para uma **subpasta** do
OneDrive ou do Google Drive (ex.: `C:/Users/<você>/OneDrive/SerranoBackups`, com barras normais), ou
para um HD externo.

Restaurar (Git Bash no Windows; testado apagando banco e arquivos e voltando de um backup da pilha):

```bash
export MSYS_NO_PATHCONV=1                 # Git Bash: não converter os caminhos do docker
C="docker compose -f docker-compose.casa.yml --env-file .env.casa"
D="$(pwd -W)/backups/AAAA-MM-DD"          # o dia escolhido, dentro do BACKUP_DIR
$C stop api worker backup
$C exec db psql -U postgres -c "drop database campero with (force)" -c "create database campero"
$C cp "$D/campero.dump" db:/tmp/campero.dump
$C exec db pg_restore -U postgres -d campero /tmp/campero.dump
A="$(pwd -W)/backups/arquivos"           # o espelho dos pendrives, dentro do BACKUP_DIR
$C run --rm --no-deps -v "$A:/a:ro" api sh -c "find /app/storage -mindepth 1 -delete && cp -a /a/. /app/storage/"
$C up -d
```

## 7. Planos e assinatura

Conta nova ganha 30 dias de teste do plano Fazenda. Teste ou assinatura vencida bloqueia novos envios
(os dados continuam visíveis). O pagamento ainda é combinado direto (PIX ou boleto): o produtor pede o
plano em **Plano e assinatura** no painel e você ativa depois de receber.

```bash
C="docker compose -f docker-compose.casa.yml --env-file .env.casa"
$C exec api sistemacampero assinatura pedidos --database-url "postgresql://postgres:$POSTGRES_SENHA@db:5432/campero"
$C exec api sistemacampero assinatura ativar <slug-da-fazenda> --plano fazenda --meses 12 --database-url "..."
$C exec api sistemacampero assinatura suspender <slug-da-fazenda> --database-url "..."
```

Preços e recursos ficam na tabela `public.planos` (migration `20261118000000_planos_comerciais.sql`);
os da landing estão escritos em `site/index.html`: mude os dois juntos.

## 8. Como funciona o login

O painel faz login no Supabase e manda o token para a API. A API confere a assinatura pelo JWKS do
Supabase e, com `HOSPEDAGEM=casa`, copia o usuário para `auth.users` do banco local no primeiro
acesso (função `auth.espelhar_usuario`, só no banco local). Nenhum dado da fazenda vai ao Supabase.

## 9. Quando mudar para a nuvem

Primeiro cliente pagante, mais de ~5 fazendas ou a máquina não puder ficar ligada: siga
[deploy.md](deploy.md) (Supabase Pro em São Paulo + Fly.io). Os dados vêm deste banco com `pg_dump`
e os arquivos com o `arquivos.tar.gz` do backup.
