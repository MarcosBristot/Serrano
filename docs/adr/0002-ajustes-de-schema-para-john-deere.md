# ADR 0002 — Ajustes necessários no schema (models da branch `feat/inserção-e-tratamento-de-dados-inicial`)

O dado real do John Deere Gen4 (ADR 0001) não cabe em `LeituraTelemetria` como está. Nada foi alterado
naquela branch; esta lista é para a equipe decidir (o próprio `schema.py` avisa que foi escrito sem
acesso ao modelo validado). Rascunho SQL de referência: `docs/proposals/schema_universal_jd.sql`.

| Ponto | Hoje | Necessário | Motivo (dado real) |
|---|---|---|---|
| `geom` | NOT NULL | **nullable** + `gps_valid` | 55% dos arquivos (802 de 1.543 sessões com dados) não têm GPS |
| `horimetro`, `combustivel_consumido_l` | NOT NULL | nullable (ou derivados no ETL) | counters começam sem leitura; ficam NaN até o 1º valor |
| vazão instantânea | ausente | `vazao_l_h`, `rpm`, `carga_motor_pct`, `motor_ligado` | JD só informa **vazão**; litros = integral; RPM define motor ligado |
| nível de tanque | implícito | `nivel_tanque_l` **nullable** | JD Gen4 não tem sensor de nível |
| volume | 1 linha/amostra com UUID | PK composta (sessão, ts), particionar por mês, 1 Hz | ~1,18 M amostras a 1 Hz (329 h de motor/log) num único trator em 18 meses; 4.570 arquivos, 66% sem amostras |
| `TipoAnomalia` | consumo_excessivo, ociosidade, queda_suspeita_combustivel | + `vazao_alta`, `contador_divergente`, `gps_salto`, `sem_gps`, `l_ha_alto` | regras implementadas em `analytics/rules.py` |
| `Severidade` | baixa/media/alta | mapa info→baixa, atencao→media, alto→alta | — |
| `KpiOperacao` | combustível, horas, L/ha | + horas ociosas, área trabalhada (origem: estimada), ha/h, versão das regras | reprocessamento por `RuleConfig.version` |
| operador | ausente | fora do escopo | não há operador por sessão nos `.jdl` |
| `Maquina.identificador_externo` | livre | serial (1BM6210…) é a chave de deduplicação | mesmo serial em todos os 4.570 arquivos |
