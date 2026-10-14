# Documentação do Sistema Campero - Processamento de Telemetria John Deere (Gen4)

Este documento descreve o estado atual da arquitetura, os fluxos implementados e as pendências do projeto. O objetivo é fornecer o contexto técnico completo para continuidade do desenvolvimento.

## 1. Visão Geral e Arquitetura
O sistema foi refatorado para seguir os princípios de **Domain-Driven Design (DDD)** e padrões **PEP 8**, substituindo um protótipo monolítico que sofria com erros de memória (OOM) ao processar ficheiros grandes (>600 MB).

*   **Linguagem/Framework:** Python 3.11+, FastAPI.
*   **Base de Dados:** Supabase (PostgreSQL + extensão PostGIS habilitada).
*   **Estratégia de Processamento:** Assíncrona. A API recebe o ficheiro e delega a extração binária e as consultas espaciais para *BackgroundTasks*, libertando o *frontend*.
*   **Estratégia de Extração Binária:** O uso de compiladores Protobuf estritos foi abandonado devido à estrutura proprietária e encapsulada (Varint) do formato `.jdl`. O sistema utiliza um *Parser* otimizado que faz varredura estrutural na memória bruta (*Pattern Matching*) à procura de padrões de coordenadas em precisão `double` (64 bits).

## 2. Estrutura de Diretórios (Domain-Driven Design)
O projeto está modularizado na diretoria `src/sistemacampero/`:

*   `domain/entities.py`: Contém a entidade principal `TelemetryReading` agnóstica de infraestrutura.
*   `application/services.py`: Arquivo destinado para as regras de orquestração (atualmente estão no `main.py` da API, mas devem migrar para cá).
*   `infrastructure/parsers/jdl_parser.py`: O "coração" da extração binária. Lê o ficheiro em *chunks* de 1MB, extrai o Chassi via Regex no cabeçalho e isola as coordenadas GPS.
*   `infrastructure/repositories.py`: Contém `SpatialRepository`, responsável pela comunicação com o Supabase e chamadas RPC espaciais.
*   `interfaces/api/main.py`: Endpoints REST (`POST /upload`, `GET /machine/{id}`, `GET /stats/{id}`).

## 3. Banco de Dados (Supabase / PostGIS)
**Tabelas Implementadas:**
*   `talhoes`: Armazena os polígonos das propriedades. Colunas essenciais: `id` (UUID), `geometria` (Geometry/Polygon, SRID 4326).
*   `telemetria`: Armazena os pontos consolidados. Colunas: `id`, `machine_serial`, `timestamp`, `talhao_id`, `latitude`, `longitude`, `speed_kmh`, `fuel_rate_lph`, `engine_on`, `created_at`.

**Funções RPC (Stored Procedures):**
*   `get_talhao_by_point(lat float, lon float)`: Função no PostgreSQL que utiliza `ST_Intersects` e `ST_MakePoint` para descobrir em milissegundos se a coordenada lida pelo parser está dentro de algum talhão.

## 4. Fluxo de Execução Atual (O que está funcional)
1.  **Upload:** O *frontend* envia o `.jdl` via `POST /api/v1/telemetry/upload`. O ficheiro é salvo temporariamente em `data/temp/`.
2.  **Identificação da Máquina:** O `JohnDeereJDLParser` lê os primeiros 4KB do ficheiro e captura o número de Chassi/VIN (ex: `1BM6210...`) via expressão regular.
3.  **Extração de GPS:** O parser varre o ficheiro em blocos de 1MB à procura de valores `double` que se enquadrem nas latitudes e longitudes válidas para a região sul do Brasil (-35 a -15 Lat, -60 a -40 Lon). O salto estrutural entre Lat e Lon foi mapeado como sendo de exatos 9 bytes.
4.  **Associação Espacial:** Para cada GPS encontrado, o repositório consulta o Supabase (`get_talhao_by_point`) e obtém o `talhao_id`.
5.  **Inserção em Lotes:** Os dados são acumulados na memória e disparados para a tabela `telemetria` em blocos de 2000 registos (*Batch Insert*), garantindo estabilidade e rapidez.

---

## 5. Dívida Técnica e Ajustes Necessários (Próximos Passos)

**A. Correção do Bug de Extração da Data (Urgente)**
*   **Problema:** A extração do `timestamp` pelo nome do ficheiro está a atribuir a mesma data a ficheiros diferentes em cenários de testes múltiplos.
*   **Causa provável:** Concorrência no salvamento temporário. A função `upload_telemetry` salva os ficheiros com o `file.filename` original. Se ocorrerem vários uploads simultâneos, a lógica em *Background Task* pode ler o nome do ficheiro errado ou falhar na correspondência da Regex (`r"(\d{4}_\d{2}_\d{2})_\[(\d{2}_\d{2})\]"`).
*   **Solução sugerida:** Gerar um UUID único para o nome físico do ficheiro ao guardá-lo em `data/temp/`, mas passar o `file.filename` original como argumento explícito para a função `processar_arquivo_jdl` extrair a data correta.

**B. Mapeamento Físico de Sensores (Crítico)**
*   **Problema:** Atualmente, a entidade `TelemetryReading` gerada no `jdl_parser.py` possui *placeholders* *hardcoded* para as grandezas do motor. Os campos `speed_kmh` e `fuel_rate_lph` estão fixos em `8.0` e `15.0`.
*   **Causa:** A engenharia reversa encontrou o bloco do GPS, mas ainda não se determinou o *offset* exato da velocidade e do combustível.
*   **Solução sugerida:** Criar um script para varrer os bytes imediatamente anteriores e posteriores ao GPS encontrado (ex: `-30` a `+30` bytes de distância) procurando floats ou doubles que representem valores de velocidade lógicos (ex: 0 a 30 km/h). Atualizar a extração no `JohnDeereJDLParser` após essa identificação.

**C. Limpeza de Ficheiros Temporários**
*   **Problema:** A API salva ficheiros em `data/temp/` mas não os apaga após o processamento, o que eventualmente causará saturação do disco.
*   **Solução sugerida:** Adicionar um bloco `finally:` na função `processar_arquivo_jdl` para executar `os.remove(file_path)`.

**D. Refatoração da Camada Application**
*   **Problema:** A função `processar_arquivo_jdl` está atualmente alojada dentro de `interfaces/api/main.py`.
*   **Solução sugerida:** De acordo com o padrão DDD, extrair essa lógica de orquestração para uma classe de serviço (ex: `TelemetryOrchestratorService`) no ficheiro `application/services.py`.