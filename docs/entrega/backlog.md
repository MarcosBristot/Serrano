# Backlog e gestão das atividades

A equipe trabalha com **pull requests no GitHub**: cada entrega é uma branch, passa pelo CI
(qualidade, testes, segurança e imagem) e só então entra na `main`. O histórico completo está em
[Pull requests](https://github.com/MarcosBristot/Serrano/pulls?q=is%3Apr) e as decisões técnicas em
[`docs/adr`](../adr).

## Concluído

| # | Entrega | Data | PR |
|---|---|---|---|
| 1 | README estruturado e modelo de ADR | 15/09/2026 | [#1](https://github.com/MarcosBristot/Serrano/pull/1) |
| 2 | Ambiente com `uv` | 16/09/2026 | [#3](https://github.com/MarcosBristot/Serrano/pull/3) |
| 3 | Dados de telemetria de exemplo e validação | 21 e 22/09/2026 | [#4](https://github.com/MarcosBristot/Serrano/pull/4), [#5](https://github.com/MarcosBristot/Serrano/pull/5) |
| 4 | Organização do código | 05/10/2026 | [#6](https://github.com/MarcosBristot/Serrano/pull/6) |
| 5 | **Backend v1 (M1 a M9)**: fundação, leitor John Deere, ingestão assíncrona, cadastro e geo, KPIs, alertas, equipe, exportação, operação | 22/10/2026 | [#7](https://github.com/MarcosBristot/Serrano/pull/7) |
| 6 | Configuração no Supabase real (RLS do schema interno, deploy e testes) | 28/10/2026 | [#8](https://github.com/MarcosBristot/Serrano/pull/8) |
| 7 | Painel do cliente, site e rota de contatos | 28/10/2026 | [#9](https://github.com/MarcosBristot/Serrano/pull/9) |
| 8 | Site, documentos legais e conformidade LGPD | 17/11/2026 | [#10](https://github.com/MarcosBristot/Serrano/pull/10) |
| 9 | Direitos do titular (LGPD) e registros de acesso (Marco Civil) | 17/11/2026 | [#11](https://github.com/MarcosBristot/Serrano/pull/11) |
| 10 | Carga do pendrive inteiro e talhão do monitor nas métricas | 17/11/2026 | [#12](https://github.com/MarcosBristot/Serrano/pull/12) |
| 11 | Jornadas de trabalho, banco enxuto e tela inicial do produtor | 17/11/2026 | [#13](https://github.com/MarcosBristot/Serrano/pull/13) |
| 12 | Cadastro no painel, visual novo e publicação (Cloudflare Workers) | 18/11/2026 | [#14](https://github.com/MarcosBristot/Serrano/pull/14) |
| 13 | Site focado em telemetria | 18/11/2026 | [#15](https://github.com/MarcosBristot/Serrano/pull/15) |
| 14 | Upload de pendrive grande em partes | 18/11/2026 | [#16](https://github.com/MarcosBristot/Serrano/pull/16) |
| 15 | Planos e assinatura, página de integrações e qualidade dos dados | 18/11/2026 | [#17](https://github.com/MarcosBristot/Serrano/pull/17) |
| 16 | Túnel da Cloudflare em HTTP/2 | 18/11/2026 | [#18](https://github.com/MarcosBristot/Serrano/pull/18) |
| 17 | Leitor do monitor Trimble (Massey Ferguson) e aviso de formato desconhecido | 19/11/2026 | [#19](https://github.com/MarcosBristot/Serrano/pull/19) |
| 18 | Implemento padrão da máquina (área para monitores sem implemento) | 24/11/2026 | [#20](https://github.com/MarcosBristot/Serrano/pull/20) |
| 19 | Documentação técnica para o DemoDay (esta pasta) | 26/11/2026 | branch `docs/entrega-demoday` |

Fora do código: validação em campo com produtores da região de Passo Fundo (pendrives reais de
John Deere e Massey Ferguson), pitch deck e apresentação técnica, materiais de redes sociais.

## A fazer (próximas entregas)

| Prioridade | Item | Por quê |
|---|---|---|
| Alta | **Planos novos (Essencial, Profissional, Completo, Grupo)** no banco, no painel e no site, com limite de máquinas e de usuários por plano | Nova política comercial ([roadmap](roadmap.md#planos-comerciais)) |
| Alta | Limite de descompactação do zip (hoje 4 GB) alinhado com o limite de envio (10 GB) | Pendrive muito grande pode ser recusado ao abrir |
| Alta | E-mail transacional (redefinição de senha, alertas) | Hoje só configurável por SMTP; produção sem provedor |
| Alta | Servidor dedicado ou nuvem | Produção não pode depender de notebook pessoal |
| Média | Política de retenção do arquivo bruto | Controlar crescimento do armazenamento |
| Média | Conta de demonstração com dados de exemplo | Avaliadores e prospects verem o painel cheio |
| Média | Dados da empresa no site (CNPJ, endereço) | Formalização |
| Média | Autenticação em dois fatores para donos de conta | Segurança |
| Baixa | Placeholders do pitch (mercado, rodada, equipe) | Material de captação |

## Em pesquisa

- Leitura de Case IH / New Holland (AFS, Intelliview), Climate FieldView, telemetria Stara e Jacto.
- Integração direta com a nuvem John Deere Operations Center (sem pendrive).
- Modelos de aprendizado de máquina para previsão de consumo e anomalias (ver [inteligência](inteligencia.md)).
