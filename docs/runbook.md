# Runbook de operação

## Sinais

- `GET /ready` (banco e Storage) · `GET /metrics` (Prometheus: requisições e latência por rota).
- Logs em JSON no Railway: filtrar por `request_id` (vem no cabeçalho `X-Request-ID` e no corpo de
  todo erro) ou `job_id` (worker).
- Fila (SQL editor, como `postgres`):
  ```sql
  select status, tipo, count(*) from interno.jobs group by 1, 2 order by 1, 2;
  select id, organizacao_id, tipo, tentativas, erro from interno.jobs where status = 'morto';
  select status, count(*) from interno.notificacoes group by 1;
  ```

## Incidentes comuns

| Sintoma | Causa provável | Ação |
|---|---|---|
| Jobs parados em `pendente` | worker fora do ar | Railway: reiniciar `worker`; ver logs |
| Jobs em `executando` há muito tempo | worker morreu no meio | nada: o reaper devolve quando o lease (10 min) vence |
| Jobs `morto` | erro repetido (Storage/banco) | corrigir a causa; `POST /api/v1/admin/jobs/{id}/reenfileirar` |
| Arquivo `rejeitado` | `.jdl` corrompido (cópia interrompida) | pedir nova cópia do pendrive |
| Arquivo `bloqueado_plano` | serial novo acima do limite | upgrade do plano ou desativar máquina; `POST /admin/reabrir-bloqueados` |
| Muitos `vazio` | normal (~65% dos arquivos do monitor) | explicar ao gestor (`GET /qualidade/relatorio`) |
| `HORIMETRO_DIVERGE` em sessão | firmware/canal diferente do conhecido | separar o arquivo (fora do Git), abrir issue com o sha256, rodar `scripts/regressao_dump.py` |
| Notificações `morta` | SMTP/webhook do cliente fora | `POST /destinos-notificacao/{id}/teste`; corrigir destino |
| 429 para um cliente | integração em laço | ver chave de API em `/auditoria`; revogar se preciso |

## Reprocessar

- Uma organização inteira com as regras atuais: `POST /api/v1/analysis/run`.
- Depois de mudar o leitor/métricas (nova versão do adapter/sanitizador): rodar `analysis/run` por
  organização. O bruto é imutável no Storage; tudo o mais é refeito a partir dele.

## Backup e restauração

- Supabase Pro: backup diário (7 dias). Ativar PITR quando houver cliente pagante.
- O bruto no Storage permite refazer tudo: restaurar o banco a partir do backup e, se faltar algo,
  reenfileirar `processar_arquivo` dos arquivos (`/admin`).
- Ensaio de restauração (trimestral): restaurar o backup num projeto de staging, apontar o
  `DATABASE_URL` de staging e conferir `/ready` e os KPIs de uma organização.

## Segurança

- **Rotacionar a chave `service_role` exposta no histórico (commit `49fc79b`)**: ver
  `docs/seguranca-rotacao-de-chave.md`. Pendente até ser feito no painel.
- Rotação da senha do `campero_backend`: `alter role ... password ...` e atualizar o Railway.
- Vazamento de chave de API de cliente: `DELETE /api/v1/chaves-api/{id}` (efeito imediato).
- LGPD: dados de produtor (nomes, localização). Buckets privados, logs e auditoria sem PII; pedidos
  de exclusão: apagar a organização (`delete from public.organizacoes where id = ...` como `postgres`
  apaga tudo em cascata) e os objetos de `brutos/<org>`, `limpos/<org>`, `exportacoes/<org>`.
