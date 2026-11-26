# Segurança da informação

## Resumo

| Camada | Mecanismo |
|---|---|
| Autenticação | Supabase Auth (e-mail e senha) emite um JWT; a API valida assinatura, emissor, audiência e validade pelas chaves públicas (JWKS, cache de 10 min). |
| Integrações | Chaves de API por organização (prefixo + hash, escopos, revogação, último uso). |
| Autorização | Papéis por organização (dono, gestor, leitor) com permissões explícitas em cada rota. |
| Isolamento entre clientes | Row Level Security (RLS) no PostgreSQL em todas as tabelas de cliente: cada transação roda com a organização ativa. |
| Auditoria | Registro automático de quem fez o quê (usuário, chave de API ou sistema) e registros de acesso (Marco Civil). |
| Transporte | HTTPS de ponta a ponta pela Cloudflare; a API não tem porta aberta na internet (Cloudflare Tunnel). |
| Abuso | Limite de requisições por minuto (geral, uploads e formulário público), cabeçalhos de segurança. |
| Arquivos | Limite de tamanho, upload em partes validadas, abertura de zip com proteção contra zip-bomb e path traversal. |
| Privacidade (LGPD) | Aceite de termos versionado, exportação dos próprios dados, pedido de exclusão, política de privacidade publicada. |
| Segredos | Somente em variáveis de ambiente fora do Git; rotação documentada. |

## Autenticação

1. O painel faz login no **Supabase Auth** (`@supabase/supabase-js`) e recebe um JWT de curta duração.
2. Cada chamada à API manda `Authorization: Bearer <JWT>`.
3. A API valida o token em `infrastructure/security/jwt.py`: assinatura pelas chaves públicas do
   Supabase (`/auth/v1/.well-known/jwks.json`), `exp`, `iss` e `aud`. Senhas nunca passam pela API.
4. A organização ativa vem do cabeçalho `X-Organizacao-Id` e só é aceita se o usuário for membro dela.

**Chaves de API** (integração com ERP e outros sistemas): o segredo é mostrado uma única vez; o
banco guarda só o **hash** e um prefixo para identificação (`interno.chaves_api`), com escopos,
data de último uso e revogação.

**Convites** de equipe: token aleatório guardado como hash, com prazo de validade.

## Autorização (papéis e permissões)

Definido em `domain/tenancy.py` e aplicado por dependência em cada rota (`exigir(Permissao.X)`):

| Permissão | Dono | Gestor | Leitor |
|---|:-:|:-:|:-:|
| Ler painéis, máquinas, talhões, alertas | ✅ | ✅ | ✅ |
| Exportar (CSV/XLSX) | ✅ | ✅ | ✅ |
| Operar: enviar arquivos, cadastro, ciclo de alertas, limiares, preço do diesel | ✅ | ✅ | ❌ |
| Administrar: equipe, chaves de API, plano | ✅ | ❌ | ❌ |

## Isolamento entre clientes (multiempresa)

- Toda tabela de cliente tem `organizacao_id` e **política RLS** no PostgreSQL
  ([`supabase/migrations`](../../supabase/migrations)).
- A API abre cada transação definindo a organização ativa; mesmo uma consulta sem `where
  organizacao_id = ...` só enxerga os dados daquela organização.
- A aplicação conecta com um papel sem superpoderes (`campero_backend`), com `GRANT`s mínimos.
- Tabelas internas (fila de jobs, chaves, auditoria, notificações) ficam no schema `interno`,
  sem acesso direto pelo cliente.
- Os **testes de integração rodam como cada papel** e verificam que uma organização não lê nem
  altera dados de outra (ex.: implemento de outra organização devolve 404).

## Proteção da API

- **Rate limit** por balde de fichas (token bucket): limite geral por minuto, limite separado para
  uploads e para o formulário público de contato (`interfaces/api/protecao.py`).
- **Cabeçalhos**: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Permissions-Policy` e `Cross-Origin-Opener-Policy`
  em todas as respostas; CORS restrito às origens configuradas (painel e site).
- **Erros** no formato `application/problem+json` com `request_id` para suporte, sem vazar detalhes
  internos.
- **Validação** de toda entrada com Pydantic (tipos, tamanhos, enums).

## Arquivos enviados

- Tamanho máximo configurável (`MAX_UPLOAD_MB`, hoje 10 GB) e envio em partes com checagem de
  ordem, tamanho de cada parte e tamanho final.
- Zip aberto com limites (`domain/services/zip_seguro.py`): número de entradas, tamanho total e
  por entrada, **taxa de compressão máxima (anti zip-bomb)** e bloqueio de caminhos perigosos.
- O arquivo bruto é guardado como chegou (com SHA-256) e nunca é alterado; o processamento trabalha
  numa cópia limpa.

## Notificações

Webhooks saem **assinados com HMAC-SHA256** (`X-Serrano-Assinatura: t=<timestamp>,v1=<assinatura>`),
o que permite ao sistema do cliente verificar a origem e evitar replay. Envio por outbox com novas
tentativas.

## Auditoria e LGPD

- `interno.auditoria`: ator (usuário, chave de API ou sistema), ação, entidade e quando.
- `interno.registros_acesso`: registros de acesso a aplicação (Marco Civil da Internet).
- `interno.aceites`: aceite dos Termos e da Política de Privacidade com a versão aceita.
- Direitos do titular na API (`/api/v1/eu/dados` e `/api/v1/eu/exclusao`): **exportar** os próprios dados e **pedir
  exclusão** da conta (com prazo e cancelamento).
- Política de privacidade e termos publicados no site; análise de riscos jurídicos em
  [`docs/juridico-riscos.md`](../juridico-riscos.md).

## Segredos e operação

- Segredos (`SUPABASE_*`, senhas do banco, SMTP, token do túnel) só em `.env`/`.env.casa`, fora do Git.
- Rotação de chave documentada em [`docs/seguranca-rotacao-de-chave.md`](../seguranca-rotacao-de-chave.md).
- CI com **auditoria de dependências** a cada push.
- Backup diário do banco e dos arquivos, com retenção de 7 dias ([infraestrutura](infraestrutura.md)).

## Pontos de atenção (próximos passos)

- O servidor de produção ainda é um notebook da equipe: precisa de criptografia de disco e senha
  forte, e migrar para uma máquina dedicada ou nuvem ([roadmap](roadmap.md)).
- Ativar a autenticação em dois fatores (MFA) no Supabase Auth para contas de dono.
- Política de retenção do arquivo bruto (hoje guardado indefinidamente).
- Teste de intrusão externo antes de escalar para cooperativas.
