# ADR 0006 — Ingestão assíncrona (M3)

Status: aceito em 21/10/2026.

## Fluxo

```
POST /api/v1/telemetry/upload (.jdl ou .zip, 202)
  -> sha256 + limite de tamanho + assinatura do conteúdo
  -> Storage brutos/<org>/<sha256>.<ext>                      (etapa 1, imutável)
  -> arquivos_brutos + interno.jobs NA MESMA transação         (dedupe por org+sha256)
worker (sistemacampero worker)
  expandir_zip       -> cada .jdl vira arquivo filho + job; MasterData/.gjson ficam guardados (M4)
  processar_arquivo  -> adapter -> sanitização -> métricas/qualidade/regras (M2)
                     -> Parquet 1 Hz em limpos/<org>/<sha256>.parquet
                     -> sessão + telemetria + métricas + alertas numa transação
```

## Decisões

- **Fila em `interno.jobs`** (ADR 0004/D2). `reivindicar` em transação curta com
  `FOR UPDATE SKIP LOCKED`; processamento fora dela; **lease** de 10 min renovado por heartbeat a
  cada 60 s; **reaper** devolve jobs de worker morto; retentativa com backoff `30 s·2^(n-1)` (teto de
  1 h, jitter ±20%); 5 tentativas e depois `morto` (dead-letter, reenfileirável pela rota admin).
- **Erros de formato não são retentados**: arquivo corrompido vira `rejeitado`, sem `.jdl` útil vira
  `vazio` (com o motivo explicado). Só falhas inesperadas (banco, Storage) entram no backoff.
- **Idempotência**: upsert da sessão por arquivo, troca da telemetria da sessão, upsert de métricas por
  versão de regras e de alertas por impressão digital. Reprocessar não duplica, e um alerta
  reconhecido continua reconhecido.
- **Telemetria**: `COPY` não é permitido em tabela com RLS. O `COPY` vai para uma tabela temporária e
  um `INSERT ... SELECT` (sujeito à RLS) copia para `telemetria`.
- **Limite do plano**: `FOR UPDATE` na linha da assinatura serializa uploads paralelos. Serial novo
  acima do limite vira `bloqueado_plano` (`PLANO_LIMITE_MAQUINAS`). `POST /admin/reabrir-bloqueados`
  reprocessa depois de upgrade ou desativação (M4 chama isso automaticamente ao desativar máquina).
- **Zip seguro**: sem caminhos absolutos ou `..`, limites de entradas, tamanho total e por entrada,
  taxa de compressão e leitura com teto (o tamanho declarado pode mentir). O nome do cliente nunca
  vira caminho.
- **Storage**: `ArmazenamentoLocal` (dev/compose/testes) e `ArmazenamentoSupabase` (REST via httpx,
  chave secreta só no servidor, buckets privados). Zip grande é baixado em streaming.

## Verificado

- Dump real (zip de 54 MB, 1.586 `.jdl`) pela API do compose: 554 processados, 1.032 vazios,
  45 `.gjson` + 1 MasterData guardados; totais **idênticos** à linha de base do M2 (74,8 h, 1.135,9 L,
  1.151,0 L, 279,3 ha); 277.759 linhas de telemetria; 206 s com 1 worker.
- `kill -9` real do container do worker no meio do processamento: o job em andamento voltou à fila
  quando o lease venceu e foi refeito; totais idênticos, 0 sessões duplicadas.
- Testes de integração: dedupe por organização, isolamento, reprocessamento, zip, zip slip, arquivo
  corrompido, limite do plano, backoff e dead-letter, cancelamento, `SKIP LOCKED` com 5 consumidores,
  paginação por cursor.

## Pendências / riscos

- **Supabase Storage**: o limite global de tamanho de arquivo do projeto vem baixo por padrão
  (Settings > Storage). Precisa subir para ≥ 1 GB para o zip do pendrive. O upload padrão (sem TUS)
  é menos robusto para arquivos de centenas de MB; se der problema no piloto, trocar por upload
  resumível ou por URL assinada (o plano já previa).
- Upload com URL assinada direto para o Storage (`POST /uploads`) ficou fora, como na trilha do piloto.
- Vazão: ~8 arquivos/s com 1 worker. Mais réplicas do worker escalam linearmente (`SKIP LOCKED`).
- O teste de integração contra o Supabase real (`pytest -m supabase`) continua pendente de acesso.
