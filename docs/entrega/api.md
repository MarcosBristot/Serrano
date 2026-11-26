# Documentação da API

API REST da Serrano, em **FastAPI**, com especificação **OpenAPI 3** gerada a partir do código
(tipos, parâmetros e respostas vêm dos modelos Pydantic, então a documentação não fica
desatualizada).

| Onde | Link |
|---|---|
| Swagger UI (produção, interativo) | https://api.sistemaserrano.com.br/docs |
| ReDoc (produção, leitura) | https://api.sistemaserrano.com.br/redoc |
| Especificação OpenAPI (produção) | https://api.sistemaserrano.com.br/openapi.json |
| Cópia da especificação no repositório | [`docs/entrega/openapi.json`](openapi.json) |
| Swagger da cópia do repositório (sempre disponível) | https://petstore.swagger.io/?url=https://raw.githubusercontent.com/MarcosBristot/Serrano/main/docs/entrega/openapi.json |

> A API de produção roda no servidor da equipe. Se os links de produção estiverem fora do ar, use a
> cópia do repositório, que tem a mesma especificação.

## Convenções

- **Base:** `https://api.sistemaserrano.com.br/api/v1`
- **Autenticação:** `Authorization: Bearer <JWT do Supabase Auth>` (ou chave de API da organização).
- **Organização ativa:** cabeçalho `X-Organizacao-Id: <uuid>` quando o usuário participa de mais de uma.
- **Formato:** JSON (UTF-8). Datas em ISO 8601 com fuso; períodos de KPI em dia local (`AAAA-MM-DD`).
- **Paginação:** listas grandes usam `limit` e cursor, e devolvem `itens`.
- **Erros:** `application/problem+json` (RFC 9457) com `code` estável, `detail` em português e `request_id` para suporte.
- **Limite de uso:** requisições por minuto por usuário; uploads e formulário público têm limites próprios (HTTP 429).
- **Processamento assíncrono:** envios devolvem `202 Accepted` com `job_id`; o progresso sai em `GET /jobs/{job_id}`.

## Exemplos

### Saúde do serviço

```http
GET /health
```

```json
{"status": "ok", "versao": "1.0.0a1"}
```

### Enviar um pendrive grande (upload em partes)

A Cloudflare limita cada requisição a 100 MB, então arquivos grandes vão em partes de até 32 MB.

```http
POST /api/v1/telemetry/upload/partes
Authorization: Bearer eyJhbGciOi...
Content-Type: application/json

{"nome": "Trator JD 2026.zip", "tamanho": 1431306240}
```

```json
{"upload_id": "1b0c5b9e-7f7a-4a51-9a35-2c7e0f9d2a11", "tamanho_parte": 67108864}
```

Cada parte, em ordem (corpo binário):

```http
POST /api/v1/telemetry/upload/partes/1b0c5b9e-7f7a-4a51-9a35-2c7e0f9d2a11/0
Content-Type: application/octet-stream

<32 MB de bytes>
```

```json
{"recebido": 33554432}
```

Conclusão:

```http
POST /api/v1/telemetry/upload/partes/1b0c5b9e-7f7a-4a51-9a35-2c7e0f9d2a11/concluir
```

```json
{
  "job_id": "6f1d2a40-8a3b-4c8e-9d61-0f5e7b2c9a10",
  "arquivo_id": "3c8e51a2-0b7d-4f6e-9a41-7d2c5e8f1b90",
  "duplicado": false,
  "status": "recebido",
  "sha256": "9c1e…",
  "tipo": "zip",
  "arquivo": "Trator JD 2026.zip",
  "marca": null,
  "tecnologia": null
}
```

### Acompanhar o processamento

```http
GET /api/v1/jobs/6f1d2a40-8a3b-4c8e-9d61-0f5e7b2c9a10
```

```json
{
  "id": "6f1d2a40-8a3b-4c8e-9d61-0f5e7b2c9a10",
  "tipo": "expandir_zip",
  "status": "concluido",
  "tentativas": 1,
  "max_tentativas": 5,
  "progresso": {"entradas_lidas": 97, "resultado": {"status": "processado", "tsip": 97}},
  "erro": null,
  "arquivo_id": "3c8e51a2-0b7d-4f6e-9a41-7d2c5e8f1b90",
  "lote_id": null,
  "criado_em": "2026-11-24T00:13:10Z",
  "atualizado_em": "2026-11-24T00:21:42Z"
}
```

### Resumo do período (KPIs)

```http
GET /api/v1/kpis/resumo?inicio=2026-11-01&fim=2026-11-30
```

```json
{
  "motor_h": 77.4, "trabalho_h": 63.9, "ocioso_h": 13.5, "ociosidade_pct": 17.4,
  "litros": 4120.0, "litros_trabalho": 3810.0, "litros_ocioso": 310.0,
  "area_ha": 640.2, "distancia_km": 379.0,
  "l_ha": 6.4, "ha_h": 10.0, "lph_trabalho": 59.6, "lph_ocioso": 23.0,
  "custo_rs": 25132.0, "custo_ocioso_rs": 1891.0, "rs_ha": 39.3, "rs_h": 324.7,
  "sessoes": 97, "maquinas": 1,
  "primeiro_dia": "2026-11-10", "ultimo_dia": "2026-11-18", "dias_sem_preco": 0
}
```

*(valores ilustrativos)*

### Erro

```http
POST /api/v1/telemetry/upload/partes
{"nome": "pendrive.zip", "tamanho": 20000000000}
```

```http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/problem+json
```

```json
{
  "type": "about:blank",
  "title": "Unprocessable Content",
  "status": 422,
  "code": "ARQUIVO_GRANDE",
  "detail": "Arquivo maior que o limite de 10240 MB.",
  "request_id": "b71e0c4d9a2f4e10a8c6d5f3e2b1a907"
}
```

Sem token, qualquer rota protegida responde assim (resposta real da produção):

```json
{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "code": "NAO_AUTENTICADO",
  "detail": "Envie 'Authorization: Bearer <token>'.",
  "request_id": "56fa6d0e7ee24b3fa35cd23c8a6ab446"
}
```

## Endpoints

108 operações em 88 rotas, agrupadas por área.

### Admin

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/api/v1/admin/jobs` | Jobs Admin |
| `POST` | `/api/v1/admin/jobs/{job_id}/reenfileirar` | Reenfileirar |
| `POST` | `/api/v1/admin/reabrir-bloqueados` | Reabrir Bloqueados |

### Alertas

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/api/v1/alerts` | Listar |
| `GET` | `/api/v1/alerts/{alerta_id}` | Obter |
| `POST` | `/api/v1/alerts/{alerta_id}/comentarios` | Comentar |
| `POST` | `/api/v1/alerts/{alerta_id}/reabrir` | Reabrir alerta |
| `POST` | `/api/v1/alerts/{alerta_id}/reconhecer` | Reconhecer alerta |
| `POST` | `/api/v1/alerts/{alerta_id}/resolver` | Resolver alerta |
| `POST` | `/api/v1/analysis/run` | Reanalisar |
| `GET` | `/api/v1/config/regras` | Ler Regras |
| `PUT` | `/api/v1/config/regras` | Salvar Regras |
| `GET` | `/api/v1/destinos-notificacao` | Listar Destinos |
| `POST` | `/api/v1/destinos-notificacao` | Criar Destino |
| `DELETE` | `/api/v1/destinos-notificacao/{ident}` | Apagar Destino |
| `PATCH` | `/api/v1/destinos-notificacao/{ident}` | Editar Destino |
| `POST` | `/api/v1/destinos-notificacao/{ident}/teste` | Testar Destino |

### Cadastro

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/api/v1/fazendas` | Listar Fazendas |
| `POST` | `/api/v1/fazendas` | Criar Fazenda |
| `DELETE` | `/api/v1/fazendas/{ident}` | Apagar Fazenda |
| `PATCH` | `/api/v1/fazendas/{ident}` | Editar Fazenda |
| `GET` | `/api/v1/implementos` | Listar Implementos |
| `POST` | `/api/v1/implementos` | Criar Implemento |
| `DELETE` | `/api/v1/implementos/{ident}` | Apagar Implemento |
| `PATCH` | `/api/v1/implementos/{ident}` | Editar Implemento |
| `GET` | `/api/v1/maquinas` | Listar Maquinas |
| `PATCH` | `/api/v1/maquinas/{ident}` | Editar Maquina |
| `PUT` | `/api/v1/maquinas/{ident}/implemento-padrao` | Implemento usado quando o arquivo do monitor não informa (dá área, ha/h e L/ha) |
| `GET` | `/api/v1/operadores` | Listar Operadores |
| `POST` | `/api/v1/operadores` | Criar Operador |
| `PATCH` | `/api/v1/operadores/{ident}` | Editar Operador |
| `GET` | `/api/v1/talhoes` | Listar Talhoes |
| `POST` | `/api/v1/talhoes` | Criar Talhao |
| `POST` | `/api/v1/talhoes/agrupar` | Agrupar Talhoes |
| `GET` | `/api/v1/talhoes/linhas` | Linhas Dos Talhoes |
| `DELETE` | `/api/v1/talhoes/{ident}` | Apagar Talhao |
| `GET` | `/api/v1/talhoes/{ident}` | Obter Talhao |
| `PATCH` | `/api/v1/talhoes/{ident}` | Editar Talhao |
| `DELETE` | `/api/v1/talhoes/{ident}/contorno` | Remover Contorno |
| `PUT` | `/api/v1/talhoes/{ident}/contorno` | Definir Contorno |
| `PUT` | `/api/v1/talhoes/{ident}/contorno/arquivo` | Enviar Contorno |

### Conta

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/api/v1/me` | Me |
| `GET` | `/api/v1/organizacao-ativa` | Organizacao Ativa |
| `POST` | `/api/v1/organizacoes` | Criar Organizacao |

### Equipe

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/api/v1/auditoria` | Auditoria |
| `GET` | `/api/v1/chaves-api` | Chaves |
| `POST` | `/api/v1/chaves-api` | Criar Chave |
| `DELETE` | `/api/v1/chaves-api/{chave_id}` | Revogar Chave |
| `GET` | `/api/v1/convites` | Convites |
| `POST` | `/api/v1/convites` | Convidar |
| `DELETE` | `/api/v1/convites/{convite_id}` | Revogar Convite |
| `POST` | `/api/v1/convites/{token}/aceitar` | Aceitar |
| `GET` | `/api/v1/membros` | Membros |
| `DELETE` | `/api/v1/membros/{usuario_id}` | Remover |
| `PATCH` | `/api/v1/membros/{usuario_id}` | Mudar Papel |

### Exportação e qualidade

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/api/v1/exportacoes` | Listar |
| `POST` | `/api/v1/exportacoes` | Solicitar |
| `GET` | `/api/v1/exportacoes/csv` | CSV em streaming (volume pequeno/médio) |
| `GET` | `/api/v1/exportacoes/{ident}` | Situacao |
| `GET` | `/api/v1/qualidade/relatorio` | Arquivos vazios, sem GPS, problemas, por máquina |

### Ingestão

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/api/v1/arquivos` | Listar Arquivos |
| `POST` | `/api/v1/batches` | Criar Lote |
| `GET` | `/api/v1/batches/{lote_id}` | Status Lote |
| `GET` | `/api/v1/jobs/{job_id}` | Situacao Job |
| `POST` | `/api/v1/jobs/{job_id}/cancelar` | Cancelar Job |
| `POST` | `/api/v1/telemetry/upload` | Envia UM arquivo (.jdl ou .zip do pendrive); o processamento é assíncrono |
| `POST` | `/api/v1/telemetry/upload/partes` | Inicia um envio em partes (arquivos grandes) |
| `POST` | `/api/v1/telemetry/upload/partes/{upload_id}/concluir` | Junta as partes e processa como um upload comum |
| `PUT` | `/api/v1/telemetry/upload/partes/{upload_id}/{indice}` | Envia a parte `indice` (0, 1, 2…) em ordem; reenviar a última é aceito |

### Jornadas

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/api/v1/jornadas` | Listar |
| `GET` | `/api/v1/jornadas/{jornada_id}` | Obter |
| `GET` | `/api/v1/jornadas/{jornada_id}/track` | Trajeto |
| `GET` | `/api/v1/maquinas/visao` | Visao Maquinas |

### Kpis

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/api/v1/kpis/ranking` | Ranking |
| `GET` | `/api/v1/kpis/resumo` | Resumo |
| `GET` | `/api/v1/kpis/safras` | Safras |
| `GET` | `/api/v1/kpis/series` | Series |
| `GET` | `/api/v1/mapas/calor` | Grade hexagonal de L/ha (GeoJSON) |
| `GET` | `/api/v1/precos-combustivel` | Listar Precos |
| `POST` | `/api/v1/precos-combustivel` | Novo Preco |
| `PATCH` | `/api/v1/precos-combustivel/{preco_id}` | Corrigir Preco |
| `GET` | `/api/v1/sessions/{sessao_id}/track` | Trajeto decimado da sessão (GeoJSON) |

### Manutenção

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/api/v1/manutencao/pendencias` | Pendencias |
| `PATCH` | `/api/v1/manutencao/planos/{plano_id}` | Editar Plano |
| `POST` | `/api/v1/manutencao/planos/{plano_id}/feita` | Registrar Feita |
| `PUT` | `/api/v1/maquinas/{maquina_id}/horimetro` | Informar Horimetro |
| `GET` | `/api/v1/maquinas/{maquina_id}/manutencao` | Situacao |
| `POST` | `/api/v1/maquinas/{maquina_id}/manutencao/modelo` | Aplicar Modelo |
| `POST` | `/api/v1/maquinas/{maquina_id}/manutencao/planos` | Criar Plano |
| `GET` | `/api/v1/resumo-semanal` | Resumo Semanal |

### Meus dados

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/api/v1/eu/dados` | Exportar |
| `DELETE` | `/api/v1/eu/exclusao` | Cancelar |
| `GET` | `/api/v1/eu/exclusao` | Situacao |
| `POST` | `/api/v1/eu/exclusao` | Solicitar |

### Plataforma

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/api/v1/assinatura` | Plano atual, uso e planos |
| `POST` | `/api/v1/assinatura/pedidos` | Pede a contratação de um plano (a equipe Serrano entra em contato) |
| `GET` | `/api/v1/integracoes` | Formatos e sistemas que a Serrano lê, com o que já chegou de cada um |
| `GET` | `/api/v1/qualidade` | O que foi aproveitado, descartado ou corrigido nos dados recebidos |

### Safras

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/api/v1/safras` | Listar |
| `GET` | `/api/v1/safras/fechamento` | Fechamento |

### Saúde

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/health` | Health |
| `GET` | `/ready` | Ready |

### Sessões

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/api/v1/sessions` | Listar Sessoes |
| `GET` | `/api/v1/sessions/{sessao_id}` | Obter Sessao |
| `PATCH` | `/api/v1/sessions/{sessao_id}` | Corrigir Sessao |

### Site

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/api/v1/contatos` | Solicitar Demonstracao |

### Telemetria (contrato legado)

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/api/v1/telemetry/machine/{machine_serial}` | Machine Telemetry |
| `GET` | `/api/v1/telemetry/stats/{machine_serial}` | Machine Stats |
