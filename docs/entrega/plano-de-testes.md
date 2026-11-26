# Plano de testes

## Resultado atual

| Indicador | Valor |
|---|---|
| Testes automatizados | **314 passando**, 0 falhando |
| Cobertura de código (backend) | **91%** (6.892 de 7.575 linhas) |
| Tempo da suíte completa | ~5 min 30 s (com PostgreSQL + PostGIS real) |
| Execução | Em todo push e pull request (GitHub Actions) |

Medido em 26/11/2026 sobre a `main`, com `pytest --cov=sistemacampero` e um PostGIS descartável.

### Cobertura por camada

| Camada | Cobertura | O que é |
|---|---:|---|
| `domain` (entidades e serviços puros) | 97% a 98% | Sanitização, métricas, qualidade, regras, geo, cobertura |
| `infrastructure/parsers` (leitores de formato) | 93% | John Deere Gen4 e GS3, ISOBUS, Trimble, shapefile/KML |
| `infrastructure/persistence` (banco) | 91% | Repositórios em SQL com RLS |
| `infrastructure/security` (JWT) | 92% | Validação de token |
| `application` (casos de uso) | 92% | Ingestão, processamento, cadastro, alertas, equipe |
| `interfaces/api` (rotas HTTP) | 94% | 108 operações da API |
| `interfaces` (CLI e laço do worker) | 37% | Pontos de entrada de linha de comando, exercitados em uso manual |

## Estratégia

```mermaid
flowchart LR
    U["Unitários<br/>sem I/O"] --> C["Contrato<br/>todo leitor de formato"]
    C --> R["Regressão<br/>dados reais x linha de base"]
    R --> I["Integração<br/>API + worker + PostGIS real,<br/>como cada papel"]
    I --> M["Manual / campo<br/>pendrives reais dos pilotos"]
```

| Nível | Pasta | O que garante |
|---|---|---|
| Unitário | [`tests/unit`](../../tests/unit) | Regras de negócio puras (métricas, qualidade, alertas, geo, nomes de talhão, zip, JWT, tenancy) e a própria arquitetura (`domain` não importa FastAPI nem psycopg). |
| Contrato | [`tests/contrato`](../../tests/contrato) | Todo leitor de formato devolve o mesmo schema universal, trata arquivo vazio e corrompido, e respeita canais que o formato não grava. Marca nova entra só passando nesse contrato. |
| Regressão | [`tests/regressao`](../../tests/regressao) | Os 3 defeitos encontrados no código original (motor ligado, contador de combustível e saltos de GPS) não voltam. Script extra compara um pendrive real com a linha de base congelada. |
| Integração | [`tests/integracao`](../../tests/integracao) | API, worker e banco de verdade: cada teste cria um banco novo, aplica todas as migrations e roda como usuário anônimo, autenticado, backend e administrador. |
| Dados sintéticos | [`tests/sinteticos`](../../tests/sinteticos) | Geradores de arquivos de monitor (`.jdl`, GS3, TSIP do Trimble) com cenários controlados (velocidade, tempo, falhas). |

## Cenários de teste

| ID | Funcionalidade | Cenário | Resultado esperado | Critério de validação | Teste automatizado |
|---|---|---|---|---|---|
| CT01 | Isolamento entre clientes | Usuário da organização A consulta e altera dados | Só enxerga e altera dados da A; `update` sem `where` fica restrito à A | Nenhuma linha da B lida ou alterada | `test_banco.py::test_backend_ve_so_a_org_ativa`, `test_backend_update_esquecendo_where_fica_na_org` |
| CT02 | Segurança do banco | Toda tabela pública | Tem RLS ativo; anônimo não acessa nada | Consulta ao catálogo sem exceções | `test_banco.py::test_toda_tabela_publica_tem_rls`, `test_anon_nao_acessa_nada` |
| CT03 | Autenticação | Requisição sem token, com token expirado ou de outro emissor | 401 `NAO_AUTENTICADO` | Nenhum dado devolvido | `tests/unit/test_jwt.py` |
| CT04 | Papéis | Leitor tenta enviar arquivo | 403 | Arquivo não é criado | `test_ingestao.py::test_leitor_nao_fazupload` |
| CT05 | Envio de pendrive | Zip com arquivos de monitor | Cada arquivo vira sessão com métricas, qualidade e alertas | Contagens e totais conferem com o cenário sintético | `test_ingestao.py::test_upload_processa_e_grava_tudo`, `test_zip_do_pendrive` |
| CT06 | Envio grande em partes | Arquivo acima de 100 MB em partes de 32 MB | Resultado idêntico ao upload simples | Mesmo SHA-256 e mesma sessão | `test_upload_partes.py::test_partes_juntas_viram_o_mesmo_arquivo_do_upload_simples` |
| CT07 | Envio inválido | Parte fora de ordem, envio incompleto, acima do limite | Recusado com código explicativo | 422 com `code` correto | `test_upload_partes.py` |
| CT08 | Arquivo malicioso | Zip-slip (`../`), zip-bomba, zip corrompido | Recusado sem gravar fora da pasta | Nenhum arquivo fora do storage | `test_storage_e_zip.py::test_zip_slip_recusado`, `test_zip_bomba_recusada` |
| CT09 | Duplicidade | Mesmo arquivo enviado duas vezes | Segundo envio marcado como duplicado | Sem sessões duplicadas | `test_ingestao.py::test_reenvio_e_duplicado_por_organizacao` |
| CT10 | Fila resiliente | Worker morre no meio do job; erro temporário | Job retomado; novas tentativas com backoff; dead-letter no limite | Nenhum job perdido nem pego duas vezes | `test_ingestao.py::test_worker_morto_no_meio_do_job_e_retomado`, `test_skip_locked_nenhum_job_pego_duas_vezes`, `test_retentativa_com_backoff_e_dead_letter` |
| CT11 | Limite do plano | Máquina além do limite do plano | Arquivo fica `bloqueado_plano` com motivo | Máquina não é criada | `test_ingestao.py::test_limite_de_maquinas_do_plano` |
| CT12 | Alertas | Ociosidade, consumo acima da linha de base | Alerta com valor, limiar e versão da regra; ciclo reconhecer/resolver | Estado e comentários persistidos | `test_alertas.py` |
| CT13 | Notificações | Alerta com destino webhook/e-mail | Entra no outbox e é enviado com assinatura HMAC | Status de envio registrado | `test_alertas.py::test_outbox_de_notificacoes` |
| CT14 | Equipe | Convite, aceite, troca de papel, chave de API | Permissões aplicadas; auditoria sem dados pessoais | Auditoria registra a ação | `test_equipe.py` |
| CT15 | Talhão por GPS | Contorno desenhado ou importado (shapefile/KML) | Sessões relocalizadas no talhão, área por cobertura | Área coberta ≈ área esperada (±2%) | `test_cadastro.py`, `test_contornos_shp.py` |
| CT16 | Leitores de formato | John Deere Gen4, GS3, ISOBUS, Trimble | Mesmo schema universal; canais ausentes informados | Passa no contrato | `test_contrato_adapters.py`, `test_isoxml.py`, `test_colheitadeira_gs3.py`, `test_trimble.py` |
| CT17 | Implemento padrão | Trimble sem implemento + padrão de 9 m | 20 min a 8 km/h = 2,4 ha e 7,2 ha/h | Valores dentro de 5% | `test_trimble.py::test_implemento_padrao_da_maquina_da_area_ao_trimble` |
| CT18 | KPIs | Período com várias sessões | Resumo, séries, ranking e mapa coerentes com as sessões | Somas batem com as métricas por sessão | `test_kpis.py`, `test_jornadas.py` |
| CT19 | Exportação | CSV e XLSX | Arquivo com cabeçalhos em português e números no padrão brasileiro | Conteúdo confere | `test_exportacao.py` |
| CT20 | LGPD | Exportar meus dados, pedir e cancelar exclusão | Dados do titular exportados; exclusão agendada e cancelável | Registros em `interno.solicitacoes_exclusao` | `test_titular.py` |
| CT21 | Migrations | Rodar duas vezes | Nada muda na segunda | Idempotência | `test_banco.py::test_migrations_sao_idempotentes` |
| CT22 | Regressão dos defeitos do código original | Arquivo real com os 3 defeitos | Motor ligado, contador e GPS corretos | Igual à linha de base congelada | `tests/regressao/test_defeitos_m0.py` |

## Testes manuais e de campo

| Cenário | Como | Resultado |
|---|---|---|
| Pendrive real John Deere (Gen4 e GS3) | Envio pelo painel em produção | Processado; confiabilidade dos dados 99,7% após a reanálise |
| Pendrive real Massey Ferguson (Trimble, 1,36 GB, 97 arquivos) | Envio em partes pela internet | 97 de 97 arquivos lidos; 77,4 h de motor, 63,9 h trabalhando, 379 km |
| Formato desconhecido (Case IH/New Holland) | Zip sem formato suportado | Recusado com explicação do que foi encontrado |
| Painel no celular | Navegação nas telas principais | Layout responsivo |

## Critérios de aceite de uma entrega

1. `ruff format --check`, `ruff check` e `mypy` sem erros.
2. Toda a suíte passando no CI (unitários, contrato, regressão e integração com PostGIS).
3. Funcionalidade nova com teste de integração do caminho principal e do caso de erro.
4. Leitor de formato novo passando no teste de contrato.

## Como rodar

```bash
uv sync
uv run pytest tests/unit                                   # rápido, sem banco
export CAMPERO_TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:54322/postgres
uv run pytest --cov=sistemacampero                         # tudo, com cobertura
```
