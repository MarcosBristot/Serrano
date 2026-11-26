# Arquitetura da solução

A Serrano lê os arquivos que os monitores das máquinas agrícolas já gravam (de marcas e formatos
diferentes), limpa esses dados e transforma tudo em métricas por máquina, talhão e safra: horas de
motor, tempo parado, distância, área, diesel por hectare (L/ha), custo por hectare (R$/ha) e alertas.

## Visão geral

```mermaid
flowchart LR
    subgraph Usuario["Produtor / gestor"]
        NAV["Navegador<br/>(celular ou computador)"]
    end

    subgraph CF["Cloudflare"]
        WWW["Worker www<br/>sistemaserrano.com.br<br/>(site institucional)"]
        APP["Worker app<br/>app.sistemaserrano.com.br<br/>(painel React)"]
        TUN["Cloudflare Tunnel<br/>api.sistemaserrano.com.br"]
    end

    subgraph SB["Supabase (nuvem)"]
        AUTH["Supabase Auth<br/>cadastro, login, JWT"]
    end

    subgraph Servidor["Servidor de produção (Docker Compose)"]
        API["API FastAPI<br/>/api/v1 + OpenAPI"]
        WK["Workers (2x)<br/>fila de jobs"]
        DB[("PostgreSQL 16 + PostGIS<br/>RLS por organização")]
        ST[("Armazenamento<br/>brutos e limpos (Parquet)")]
        BK["Backup diário<br/>pg_dump + espelho"]
        MIG["migrate<br/>(migrations versionadas)"]
    end

    EXT["Webhooks e e-mail<br/>(alertas)"]

    NAV --> WWW
    NAV --> APP
    APP -- "login" --> AUTH
    APP -- "HTTPS + Bearer JWT" --> TUN --> API
    API -- "valida JWT (JWKS)" --> AUTH
    API --> DB
    API --> ST
    API -- "enfileira job" --> DB
    WK -- "reivindica job<br/>(SKIP LOCKED)" --> DB
    WK --> ST
    WK --> EXT
    MIG --> DB
    BK --> DB
    BK --> ST
```

## Componentes

| Componente | Tecnologia | Papel |
|---|---|---|
| Site institucional | TypeScript + Vite, hospedado num Worker da Cloudflare | Apresenta a solução, planos, contato e documentos legais (LGPD). |
| Painel do cliente | React 18, Vite, TanStack Query, MapLibre GL, Recharts, Supabase JS | Envio de arquivos, mapa de calor, KPIs, máquinas, talhões, alertas, plano e equipe. |
| Autenticação | Supabase Auth | Cadastro, login e emissão de JWT. A API só valida o token (JWKS). |
| API | Python 3.11, FastAPI, Pydantic v2, psycopg 3 | 88 endpoints REST em `/api/v1`, documentação OpenAPI em `/docs`. |
| Worker | Mesmo código da API (`sistemacampero worker`) | Processa a fila: expande zip, lê cada arquivo, calcula métricas, grava resultados, envia notificações. |
| Leitores de formato (adapters) | Python, numpy, pandas | John Deere Gen4 (`.jdl`), John Deere GreenStar 3, ISOBUS (TASKDATA.XML), Trimble TMX-2050/PTx (Massey Ferguson), contornos de talhão (shapefile, KML, GeoJSON). |
| Banco de dados | PostgreSQL 16 + PostGIS | Dados multiempresa com Row Level Security; telemetria particionada por mês. |
| Armazenamento | Volume local (produção atual) ou Supabase Storage (nuvem) | Arquivo bruto original e o dado limpo em Parquet. |
| Exposição na internet | Cloudflare Tunnel | Publica a API sem abrir portas no servidor. |
| CI | GitHub Actions | Formatação, lint, tipos, testes com PostGIS real, auditoria de dependências e imagem Docker. |

## Camadas do backend (DDD)

O código segue camadas com dependência só para dentro:

```mermaid
flowchart TB
    I["interfaces<br/>API FastAPI, CLI, worker"] --> A["application<br/>casos de uso: ingestão, processamento,<br/>cadastro, alertas, equipe, plano"]
    A --> D["domain<br/>entidades, schema universal, portas (Protocol),<br/>serviços puros: sanitização, métricas, qualidade,<br/>regras, geo, cobertura"]
    INF["infrastructure<br/>config, persistência (psycopg), JWT,<br/>leitores de formato, storage, container"] --> A
    INF --> D
```

- `domain/` não conhece FastAPI, banco nem variáveis de ambiente: é testável sem I/O.
- `infrastructure/parsers/` tem um adapter por marca/formato, todos convertendo para o mesmo
  **schema universal** (`ParsedSession`). Uma marca nova não muda o resto do sistema
  ([como adicionar uma marca](../como-adicionar-marca.md)).

Código: [`src/sistemacampero/`](../../src/sistemacampero).

## Fluxo de um envio de arquivo

```mermaid
sequenceDiagram
    autonumber
    participant P as Painel
    participant A as API
    participant F as Fila (interno.jobs)
    participant W as Worker
    participant DB as PostgreSQL
    participant S as Storage

    P->>A: POST /telemetry/upload/partes (tamanho, nome)
    loop partes de 32 MB
        P->>A: POST /telemetry/upload/partes/{id}/{indice}
    end
    P->>A: POST /telemetry/upload/partes/{id}/concluir
    A->>S: grava o bruto (sha256)
    A->>DB: arquivo_bruto + job EXPANDIR_ZIP
    A-->>P: 202 Accepted (job_id)
    W->>F: reivindica job (FOR UPDATE SKIP LOCKED, lease)
    W->>S: lê o zip, abre com limites de segurança
    W->>F: um job PROCESSAR_ARQUIVO por arquivo reconhecido
    W->>W: detecta o formato, lê, sanitiza, calcula métricas, qualidade e alertas
    W->>S: grava o dado limpo (Parquet)
    W->>DB: sessão, telemetria, métricas, alertas (transação com RLS)
    P->>A: GET /jobs/{id} (progresso)
    P->>A: GET /kpis/resumo, /sessions, /alertas
```

O envio em partes existe porque a Cloudflare limita cada requisição a 100 MB, e pendrives reais
passam de 1 GB. A fila é durável: lease com renovação, reaper para worker que morreu, nova tentativa
com backoff e dead-letter ([ADR 0006](../adr/0006-ingestao-assincrona.md)).

## Decisões de arquitetura (ADRs)

- [ADR 0004: fundação do backend v1](../adr/0004-backend-v1-fundacao.md)
- [ADR 0005: formato `.jdl`, âncoras e GPS](../adr/0005-formato-jdl-ancoras-e-gps.md)
- [ADR 0006: ingestão assíncrona](../adr/0006-ingestao-assincrona.md)
- [ADR 0007: cadastro, localização por GPS e cobertura](../adr/0007-cadastro-geo-e-cobertura.md)

Formatos documentados: [GreenStar 3](../formatos/greenstar3-rcd.md), [ISOBUS / ISOXML](../formatos/isoxml.md).
