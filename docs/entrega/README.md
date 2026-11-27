# Serrano: documentação técnica (Nano de Negócios Inovadores, DemoDay)

**Serrano** é uma plataforma SaaS que lê os dados que os monitores das máquinas agrícolas já gravam,
de marcas diferentes, e mostra ao produtor quanto cada máquina trabalhou, quanto ficou parada e
quanto custou cada hectare. Feita em Passo Fundo (RS).

> 📄 **Versões em PDF e Word:** [Dossiê técnico completo (PDF)](arquivos/Serrano%20-%20Dossi%C3%AA%20t%C3%A9cnico%20completo.pdf)
> e todos os documentos separados em [`arquivos/`](arquivos). Diagramas em PNG em [`diagramas/`](diagramas).

| Item da submissão | Documento | Links |
|---|---|---|
| 💻 Repositório de código | Este repositório (público) | https://github.com/MarcosBristot/Serrano |
| 🏗️ Arquitetura da solução | [arquitetura.md](arquitetura.md) | Diagramas de componentes, camadas e fluxo de envio |
| 🗄️ Banco de dados (DER) | [banco-de-dados.md](banco-de-dados.md) | 39 tabelas, 76 chaves estrangeiras, gerado das migrations |
| 🔌 Documentação das APIs | [api.md](api.md) | [Swagger (produção)](https://api.sistemaserrano.com.br/docs) · [Swagger (cópia no GitHub)](https://petstore.swagger.io/?url=https://raw.githubusercontent.com/MarcosBristot/Serrano/main/docs/entrega/openapi.json) · [openapi.json](openapi.json) |
| 🤖 Inteligência artificial | [inteligencia.md](inteligencia.md) | Algoritmos estatísticos e de regras (sem ML/LLM em produção, por decisão) |
| 🧪 Plano de testes | [plano-de-testes.md](plano-de-testes.md) | 314 testes, 91% de cobertura, 22 cenários |
| 🔐 Segurança da informação | [seguranca.md](seguranca.md) | JWT, papéis, RLS, chaves de API, auditoria, LGPD |
| ☁️ Infraestrutura e deploy | [infraestrutura.md](infraestrutura.md) | Docker Compose, Cloudflare, Supabase Auth, CI/CD |
| 🚀 MVP em funcionamento | | Painel: https://app.sistemaserrano.com.br · Site: https://sistemaserrano.com.br |
| 🎬 Vídeo demonstrativo | Roteiro abaixo | (link do vídeo gravado pela equipe) |
| 📋 Backlog e gestão | [backlog.md](backlog.md) | [Pull requests](https://github.com/MarcosBristot/Serrano/pulls?q=is%3Apr) |
| 📈 Roadmap | [roadmap.md](roadmap.md) | Inclui a nova política de planos |

Documentação complementar já existente: [ADRs](../adr), [deploy em nuvem](../deploy.md),
[produção atual](../producao-em-casa.md), [runbook](../runbook.md),
[como adicionar uma marca](../como-adicionar-marca.md), [formatos](../formatos),
[riscos jurídicos](../juridico-riscos.md).

## Tecnologias

| Área | Tecnologias |
|---|---|
| Backend | Python 3.11, FastAPI, Pydantic v2, psycopg 3, numpy, pandas, PyArrow, Shapely, pyproj |
| Banco | PostgreSQL 16, PostGIS, Row Level Security, telemetria particionada por mês |
| Frontend | React 18, TypeScript, Vite, TanStack Query, MapLibre GL, Recharts |
| Autenticação | Supabase Auth (JWT validado por JWKS) |
| Infraestrutura | Docker Compose, Cloudflare (DNS, Tunnel, Workers), GitHub Actions |
| Qualidade | pytest, pytest-cov, ruff, mypy, auditoria de dependências |

## Roteiro do vídeo demonstrativo (3 a 4 min)

Gravar a tela do painel em produção (Windows: `Win + Alt + R`; ou OBS), com narração:

1. **Problema (20 s):** cada máquina de uma marca, cada monitor num formato; o produtor decide na média.
2. **Site (15 s):** https://sistemaserrano.com.br, proposta e planos.
3. **Cadastro e login (20 s):** criar conta e a fazenda; 30 dias grátis.
4. **Envio do pendrive (40 s):** "Enviar dados", arrastar o zip; mostrar o envio em partes e o
   processamento; formatos de várias marcas reconhecidos sozinhos.
5. **Início e KPIs (40 s):** horas de motor x trabalho, tempo parado, diesel, L/ha e R$/ha.
6. **Mapa e talhões (30 s):** trajeto, mapa de calor do consumo, talhão achado pelo GPS.
7. **Máquina (30 s):** página da máquina, operações, implemento padrão, manutenção pelo horímetro.
8. **Alertas e qualidade (20 s):** alerta de ociosidade e de consumo acima da linha de base; nota de
   qualidade do dado.
9. **Integrações e plano (15 s):** página de integrações, exportação, plano e assinatura.
10. **Bastidores técnicos (20 s):** Swagger da API e o CI verde no GitHub.

Publicar no YouTube como **não listado** (ou Google Drive com acesso a quem tiver o link) e colocar
o link na tabela acima.

## Acesso para a avaliação

- O repositório é **público**; nenhum convite é necessário.
- O MVP permite **criar conta** pelo próprio site (teste grátis de 30 dias).
- A produção do piloto roda num servidor da equipe: se a API estiver fora do ar no momento da
  avaliação, a documentação da API continua disponível pela cópia no GitHub.
