# Banco de dados (DER)

PostgreSQL 16 + PostGIS. O esquema é versionado em [`supabase/migrations`](../../supabase/migrations) e este documento é **gerado a partir dele** por [`scripts/gerar_der.py`](../../scripts/gerar_der.py).

- **39 tabelas** (`public`: dados do cliente; `interno`: fila, auditoria, chaves, LGPD), **76 chaves estrangeiras**.
- **Multiempresa:** toda tabela de cliente tem `organizacao_id` e política de Row Level Security. Para o diagrama ficar legível, a ligação de cada tabela com `organizacoes` só aparece no primeiro diagrama.
- **Telemetria particionada por mês** (`telemetria_yAAAAmMM`): consultas por período leem só as partições do intervalo.
- **Geometria:** contornos de talhão, linhas e coberturas em `geometry` (PostGIS, SRID 4326).
- `PK` = chave primária, `FK` = chave estrangeira.

## Organização, acesso, plano e LGPD

Quem usa o sistema, com que papel, em qual plano, e os registros exigidos por lei.

```mermaid
erDiagram
    organizacoes |o--o{ interno_auditoria : "organizacao_id"
    auth_users |o--o{ interno_chaves_api : "criado_por"
    organizacoes ||--o{ interno_chaves_api : "organizacao_id"
    organizacoes ||--o{ assinaturas : "organizacao_id"
    planos ||--o{ assinaturas : "plano_codigo"
    auth_users |o--o{ convites : "criado_por"
    organizacoes ||--o{ convites : "organizacao_id"
    organizacoes ||--o{ membros : "organizacao_id"
    auth_users ||--o{ membros : "usuario_id"
    organizacoes ||--o{ pedidos_assinatura : "organizacao_id"
    planos ||--o{ pedidos_assinatura : "plano_codigo"
    organizacoes {
        uuid id PK
        text nome
        text slug
        text fuso
        smallint inicio_safra_mes
        timestamptz criado_em
    }
    membros {
        uuid organizacao_id PK
        uuid usuario_id PK
        text papel
        timestamptz criado_em
    }
    convites {
        uuid id PK
        uuid organizacao_id FK
        text email
        text papel
        text token_hash
        timestamptz expira_em
        timestamptz aceito_em
        uuid criado_por FK
        timestamptz criado_em
    }
    assinaturas {
        uuid id PK
        uuid organizacao_id FK
        text plano_codigo FK
        text status
        timestamptz inicio
        timestamptz fim
        int max_maquinas_override
        timestamptz atualizado_em
    }
    planos {
        text codigo PK
        text nome
        int max_maquinas
        int preco_mensal_centavos
        text descricao
        smallint ordem
        bool destaque
        bool sob_consulta
        bool publico
        int preco_anual_centavos
        array recursos
    }
    pedidos_assinatura {
        uuid id PK
        uuid organizacao_id FK
        text plano_codigo FK
        text ciclo
        text mensagem
        text telefone
        uuid solicitado_por
        text status
        timestamptz criado_em
    }
    interno_chaves_api {
        uuid id PK
        uuid organizacao_id FK
        text nome
        text prefixo
        text hash
        array escopos
        uuid criado_por FK
        timestamptz criado_em
        timestamptz ultimo_uso_em
        timestamptz revogada_em
    }
    interno_auditoria {
        bigint id PK
        uuid organizacao_id FK
        uuid ator_id
        text ator_tipo
        text acao
        text recurso_tipo
        text recurso_id
        jsonb dados
        inet ip
        text request_id
        timestamptz criado_em
    }
    interno_registros_acesso {
        bigint id PK
        timestamptz ocorrido_em
        inet ip
        uuid usuario_id
        uuid organizacao_id
        text metodo
        text rota
        smallint status
        text request_id
    }
    interno_aceites {
        uuid id PK
        uuid usuario_id
        text documento
        text versao
        text ip_hash
        timestamptz aceito_em
    }
    interno_solicitacoes_exclusao {
        uuid id PK
        uuid usuario_id
        text email
        array organizacoes
        text status
        timestamptz agendada_para
        timestamptz criado_em
        timestamptz concluida_em
        text erro
    }
    interno_contatos {
        uuid id PK
        text nome
        text email
        text telefone
        text fazenda
        int hectares
        int maquinas
        text mensagem
        text origem
        text ip_hash
        text status
        timestamptz criado_em
        text politica_versao
        bool aceita_novidades
    }
```

## Frota, talhões e dados de operação

O que vem dos monitores: arquivos, sessões de trabalho, telemetria e métricas calculadas.

```mermaid
erDiagram
    arquivos_brutos |o--o{ arquivos_brutos : "arquivo_pai_id"
    lotes_upload |o--o{ arquivos_brutos : "lote_id"
    sessoes_trabalho ||--o{ coberturas_sessao : "sessao_id"
    sessoes_trabalho ||--o{ colheitas : "sessao_id"
    maquinas ||--o{ jornadas : "maquina_id"
    talhoes |o--o{ jornadas : "talhao_id"
    talhoes ||--o{ linhas_talhao : "talhao_id"
    auth_users |o--o{ lotes_upload : "criado_por"
    maquinas ||--o{ manutencoes_feitas : "maquina_id"
    planos_manutencao |o--o{ manutencoes_feitas : "plano_id"
    implementos |o--o{ maquinas : "implemento_padrao_id"
    maquinas ||--o{ metricas_diarias : "maquina_id"
    talhoes |o--o{ metricas_diarias : "talhao_id"
    execucoes_regras |o--o{ metricas_sessao : "execucao_id"
    sessoes_trabalho ||--o{ metricas_sessao : "sessao_id"
    maquinas ||--o{ planos_manutencao : "maquina_id"
    arquivos_brutos ||--o{ sessoes_trabalho : "arquivo_bruto_id"
    implementos |o--o{ sessoes_trabalho : "implemento_id"
    maquinas ||--o{ sessoes_trabalho : "maquina_id"
    operadores |o--o{ sessoes_trabalho : "operador_id"
    talhoes |o--o{ sessoes_trabalho : "talhao_id"
    talhoes |o--o{ sessoes_trabalho : "talhao_monitor_id"
    talhoes |o--o{ talhoes : "agrupado_em"
    fazendas |o--o{ talhoes : "fazenda_id"
    sessoes_trabalho ||--o{ telemetria : "sessao_id"
    fazendas {
        uuid id PK
        uuid organizacao_id FK
        text nome
        text cliente_nome
        text external_guid
        timestamptz criado_em
        timestamptz atualizado_em
    }
    talhoes {
        uuid id PK
        uuid organizacao_id FK
        uuid fazenda_id FK
        text nome
        text external_guid
        geometry geometria
        numeric area_ha
        text origem_contorno
        bool ativo
        timestamptz criado_em
        timestamptz atualizado_em
        uuid agrupado_em FK
    }
    linhas_talhao {
        uuid id PK
        uuid organizacao_id FK
        uuid talhao_id FK
        text tipo
        smallint subtipo
        timestamp gravado_em
        text origem
        geometry geometria
        timestamptz criado_em
    }
    maquinas {
        uuid id PK
        uuid organizacao_id FK
        text serial
        text fabricante
        text modelo
        text tecnologia
        text apelido
        bool ativa
        timestamptz primeira_atividade
        timestamptz ultima_atividade
        timestamptz criado_em
        timestamptz atualizado_em
        float horimetro_informado_h
        timestamptz horimetro_informado_em
        uuid implemento_padrao_id FK
    }
    implementos {
        uuid id PK
        uuid organizacao_id FK
        text nome
        numeric largura_m
        text external_guid
        timestamptz criado_em
        timestamptz atualizado_em
    }
    operadores {
        uuid id PK
        uuid organizacao_id FK
        text nome
        text external_guid
        bool ativo
        timestamptz criado_em
        timestamptz atualizado_em
    }
    lotes_upload {
        uuid id PK
        uuid organizacao_id FK
        uuid criado_por FK
        text origem
        timestamptz criado_em
    }
    arquivos_brutos {
        uuid id PK
        uuid organizacao_id FK
        uuid lote_id FK
        uuid arquivo_pai_id FK
        text sha256
        text nome_original
        text caminho_storage
        bigint tamanho_bytes
        text tipo
        text marca
        text tecnologia
        text status
        text motivo
        timestamptz criado_em
        timestamptz atualizado_em
    }
    sessoes_trabalho {
        uuid id PK
        uuid organizacao_id FK
        uuid arquivo_bruto_id FK
        uuid maquina_id FK
        uuid implemento_id FK
        uuid operador_id FK
        uuid talhao_id FK
        text talhao_origem
        uuid talhao_monitor_id FK
        numeric talhao_confianca
        text operacao
        timestamptz inicio
        timestamptz fim
        int n_amostras
        text adapter
        text adapter_versao
        text firmware
        text caminho_limpo
        smallint qualidade_score
        jsonb qualidade
        timestamptz criado_em
        timestamptz atualizado_em
    }
    telemetria {
        uuid organizacao_id FK
        uuid maquina_id PK
        uuid sessao_id FK
        timestamptz ts PK
        float lat
        float lon
        bool gps_valid
        float speed_kmh
        float speed_alt_kmh
        float engine_rpm
        float engine_load_pct
        float fuel_rate_lph
        float fuel_total_l
        float fuel_level_l
        float engine_hours
        bool engine_on
        uuid talhao_id
        smallint peso_s
    }
    metricas_sessao {
        uuid sessao_id PK
        text versao_regras PK
        uuid organizacao_id FK
        uuid execucao_id FK
        bool vigente
        float duracao_h
        float motor_h
        float trabalho_h
        float ocioso_h
        float ociosidade_pct
        float delta_horimetro_h
        float litros_integral
        float litros_contador
        float litros_trabalho
        float litros_ocioso
        float lph_trabalho
        float lph_ocioso
        float distancia_trabalho_km
        float velocidade_media
        float area_cobertura_ha
        float area_estimada_ha
        float sobreposicao_pct
        text area_metodo
        float ha_h
        float l_ha
        float cobertura_gps
        timestamptz criado_em
    }
    metricas_diarias {
        uuid id PK
        uuid organizacao_id FK
        date dia
        uuid maquina_id FK
        uuid talhao_id FK
        text operacao
        text versao_regras
        int sessoes
        float motor_h
        float trabalho_h
        float ocioso_h
        float litros
        float litros_trabalho
        float litros_ocioso
        float area_ha
        float distancia_km
        timestamptz atualizado_em
    }
    coberturas_sessao {
        uuid sessao_id PK
        text versao_regras PK
        uuid organizacao_id FK
        geometry geometria
    }
    colheitas {
        uuid sessao_id PK
        uuid organizacao_id FK
        text cultura
        text variedade
        text safra
        float massa_umida_kg
        float umidade_pct
        float massa_seca_kg
        float area_colhida_ha
        timestamptz criado_em
    }
    jornadas {
        uuid id PK
        uuid organizacao_id FK
        uuid maquina_id FK
        text versao_regras
        timestamptz inicio
        timestamptz fim
        uuid talhao_id FK
        int talhoes
        text operacao
        int arquivos
        float motor_h
        float trabalho_h
        float ocioso_h
        float litros
        float litros_trabalho
        float litros_ocioso
        float area_ha
        float distancia_km
        timestamptz criado_em
    }
    preco_combustivel {
        uuid id PK
        uuid organizacao_id FK
        text tipo
        numeric preco_rs_l
        date valido_de
        date valido_ate
        text fonte
        timestamptz criado_em
    }
    planos_manutencao {
        uuid id PK
        uuid organizacao_id FK
        uuid maquina_id FK
        text nome
        float intervalo_h
        float ultima_h
        date ultima_em
        bool ativo
        timestamptz criado_em
    }
    manutencoes_feitas {
        uuid id PK
        uuid organizacao_id FK
        uuid plano_id FK
        uuid maquina_id FK
        text nome
        float horimetro_h
        date feita_em
        numeric custo_rs
        text observacao
        timestamptz criado_em
    }
```

## Alertas, notificações e processamento

Regras, alertas e o que sai do sistema (e-mail, webhook, exportações), mais a fila de jobs.

```mermaid
erDiagram
    lotes_upload |o--o{ interno_jobs : "lote_id"
    alertas ||--o{ interno_notificacoes : "alerta_id"
    destinos_notificacao ||--o{ interno_notificacoes : "destino_id"
    execucoes_regras |o--o{ alertas : "execucao_id"
    maquinas |o--o{ alertas : "maquina_id"
    auth_users |o--o{ alertas : "reconhecido_por"
    auth_users |o--o{ alertas : "resolvido_por"
    sessoes_trabalho |o--o{ alertas : "sessao_id"
    talhoes |o--o{ alertas : "talhao_id"
    alertas ||--o{ alertas_comentarios : "alerta_id"
    auth_users |o--o{ alertas_comentarios : "autor_id"
    auth_users |o--o{ config_regras : "atualizado_por"
    auth_users |o--o{ exportacoes : "solicitado_por"
    alertas {
        uuid id PK
        uuid organizacao_id FK
        uuid sessao_id FK
        uuid maquina_id FK
        uuid talhao_id FK
        text tipo
        text severidade
        text versao_regras
        uuid execucao_id FK
        timestamptz inicio
        timestamptz fim
        float valor
        float limiar
        text mensagem
        jsonb detalhes
        text impressao_digital
        text status
        uuid reconhecido_por FK
        timestamptz reconhecido_em
        uuid resolvido_por FK
        timestamptz resolvido_em
        timestamptz criado_em
        timestamptz atualizado_em
    }
    alertas_comentarios {
        uuid id PK
        uuid alerta_id FK
        uuid organizacao_id FK
        uuid autor_id FK
        text texto
        timestamptz criado_em
    }
    config_regras {
        uuid organizacao_id PK
        text versao
        jsonb config
        uuid atualizado_por FK
        timestamptz atualizado_em
    }
    execucoes_regras {
        uuid id PK
        uuid organizacao_id FK
        text versao_regras
        jsonb config
        text config_hash
        jsonb escopo
        timestamptz iniciada_em
        timestamptz concluida_em
    }
    destinos_notificacao {
        uuid id PK
        uuid organizacao_id FK
        text tipo
        text destino
        text segredo_cifrado
        text severidade_minima
        bool ativo
        timestamptz criado_em
        timestamptz atualizado_em
    }
    interno_notificacoes {
        uuid id PK
        uuid organizacao_id FK
        uuid alerta_id FK
        uuid destino_id FK
        text status
        smallint tentativas
        timestamptz proxima_tentativa
        timestamptz enviado_em
        text erro
        timestamptz criado_em
    }
    interno_jobs {
        uuid id PK
        uuid organizacao_id FK
        uuid lote_id FK
        text tipo
        jsonb payload
        text status
        smallint prioridade
        smallint tentativas
        smallint max_tentativas
        timestamptz proxima_tentativa
        text locked_by
        timestamptz locked_at
        timestamptz lease_ate
        bool cancelamento_solicitado
        jsonb progresso
        text erro
        text chave_idempotencia
        timestamptz criado_em
        timestamptz atualizado_em
    }
    exportacoes {
        uuid id PK
        uuid organizacao_id FK
        uuid solicitado_por FK
        text formato
        jsonb filtros
        text status
        text caminho_storage
        bigint linhas
        timestamptz expira_em
        text erro
        timestamptz criado_em
        timestamptz atualizado_em
        text tipo
    }
    interno_resumos_semanais {
        uuid organizacao_id PK
        text semana PK
        timestamptz enviado_em
        int destinos
        text texto
    }
```
