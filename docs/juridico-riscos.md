# Conformidade e riscos jurídicos — site e plataforma Serrano

Documento interno (não publicar). Atualizado em 29/10/2026, junto com a versão `2026-10-29` dos documentos legais.

> Os textos legais foram redigidos como **minuta técnica**, a partir do que o sistema faz hoje. Antes de publicar,
> peça a revisão de um advogado (LGPD e consumidor). Este documento não é parecer jurídico.

## Bloqueios antes de publicar o site

1. **Preencher `site/empresa.json`**: razão social, CNPJ, endereço, cidade/UF, e-mail de contato, encarregado (DPO)
   e e-mail dele, comarca do foro, provedor de hospedagem da API e provedor de e-mail. O build avisa enquanto houver
   campo entre colchetes, e eles aparecem no rodapé e nas políticas.
2. **Nomear o encarregado (DPO)** e criar um e-mail que alguém de fato leia (por exemplo, `privacidade@…`).
   Agentes de pequeno porte podem ter dispensa (Res. CD/ANPD nº 2/2022), mas precisam manter um canal de comunicação.
3. **Confirmar as regras comerciais** da [política de reembolso](../site/reembolso.html), que são decisões de negócio
   redigidas como padrão:
   - mensal sem multa e sem reembolso do mês em curso;
   - anual com devolução proporcional dos meses não iniciados;
   - estorno solicitado em até 10 dias úteis;
   - 30 dias para exportar os dados após o encerramento.
4. **Contratos com suboperadores**: aceitar o DPA (acordo de tratamento de dados) da Supabase e do provedor de
   hospedagem e de e-mail, com cláusulas para a transferência internacional (Res. CD/ANPD nº 19/2024).
5. **Domínio e HTTPS**: publicar o site e a API em HTTPS e trocar `VITE_API_URL`, `VITE_APP_URL` (site) e
   `VITE_SITE_URL` (painel) para os endereços reais. Incluir a origem do site em `CORS_ORIGENS`.

## Checklist do que foi pedido

| Item | Situação | Onde |
|---|---|---|
| Política de privacidade | Feita (LGPD: bases legais, papéis controlador/operador, direitos do art. 18, retenção, transferência internacional, incidentes) | `site/privacidade.html` |
| Termos de serviço | Feitos (uso permitido, dados do cliente, limites dos indicadores, responsabilidade compatível com o CDC, foro) | `site/termos.html` |
| Política de reembolso | Feita (arrependimento de 7 dias, CDC art. 49; cobrança indevida, art. 42); falta confirmar as regras comerciais | `site/reembolso.html` |
| Aviso de cookies | Feito; informa que não há rastreamento e guarda só a escolha (essencial) | `site/src/consentimento.ts` |
| Scripts de tracking | Nenhum. Fontes servidas pelo próprio site (antes iam ao Google, que recebia o IP). Qualquer script futuro só carrega com consentimento, via `CATEGORIAS` | `site/src/base.ts`, `consentimento.ts` |
| Formulários na LGPD | Aviso de finalidade junto ao formulário, link para a política, opt-in de novidades desmarcado, versão da política gravada | `site/index.html`, `interno.contatos` |
| Só dados necessários | Obrigatórios só nome e e-mail; o resto está marcado como opcional. IP guardado só como hash truncado | formulário e `routers/contatos.py` |
| Conformidade LGPD (plataforma) | Aceite obrigatório dos Termos e da Política ao criar a organização, registrado com versão e data em `interno.aceites`. Pedidos de demonstração apagados após 12 meses (worker, diário) | migration `20261028000000_lgpd.sql` |
| Dados da empresa | Rodapé de todas as páginas lê de `empresa.json` (falta preencher) | `site/partes/rodape.html` |
| Sem avaliações falsas | Não há depoimentos, notas, logos de clientes nem contadores de usuários. Não incluir sem autorização escrita do cliente citado | — |
| Sem promessas falsas | Removidos “em minutos” e “respondemos em até um dia útil”. Números rotulados como uma operação real com ressalva; alerta rotulado “exemplo ilustrativo”; painel 3D rotulado “Simulação”. Os Termos dizem que os indicadores não substituem medição oficial nem garantem economia | `site/index.html`, `termos.html` §6 |
| Copyright das imagens | Não há fotos nem imagens de banco: a cena 3D, as texturas e a marca são geradas por código. Licenças creditadas: fontes OFL, three.js MIT, imagens Esri no painel | `termos.html#creditos` |
| Alt nas imagens | Não há `<img>`. SVGs e canvas decorativos têm `aria-hidden`; os logos têm `aria-label`. Qualquer imagem futura deve ter `alt` (vazio se decorativa) | — |
| Contraste corrigido | Paleta nova com pares ≥ 4,5:1 (medidos no navegador) | `site/src/estilo.css` |
| Navegação por teclado | Link “Pular para o conteúdo”, foco visível, menu com `aria-expanded` que fecha com Esc, trilho com links reais, diálogo de cookies nativo | `site/index.html`, `main.ts` |
| Acessibilidade | Declaração publicada (LBI, WCAG 2.1 AA como meta), respeito a “reduzir movimento”, erros de formulário ligados ao campo | `site/acessibilidade.html` |
| Riscos jurídicos | Este documento | — |

## Riscos e pendências

| Risco | Gravidade | O que fazer |
|---|---|---|
| Publicar com dados da empresa em branco (CDC art. 31; Decreto 7.962/2013 exige identificação de quem vende on-line) | Alta | Preencher `empresa.json` antes do deploy |
| ~~Marco Civil, art. 15~~ **feito**: cada chamada à API grava data, hora, IP, rota e usuário em `interno.registros_acesso` (em lote, a cada 5 s), com expurgo após `RETENCAO_ACESSOS_MESES` (6, mínimo legal) | — | Em produção atrás de proxy, confirmar que o IP real chega (a API já usa `proxy_headers`); acesso à tabela só pelo backend |
| Transferência internacional (Supabase no Canadá; hospedagem possivelmente nos EUA) | Média | DPA com cláusulas-padrão da ANPD. Avaliar mover o banco para São Paulo, o que já estava no plano do piloto |
| Dados de operadores (nome, localização GPS das operações) | Média | A política e os Termos já põem o cliente como controlador. Pôr no contrato comercial o dever do cliente de informar os operadores |
| ~~Direitos do titular sem ferramenta~~ **feito**: no painel, Configurações → Privacidade e meus dados: exportação em JSON e exclusão da conta com 7 dias de carência (`CARENCIA_EXCLUSAO_DIAS`), executada pelo worker | — | Correção, anonimização e informação sobre compartilhamento continuam pelo e-mail do DPO |
| Pedidos de demonstração e direito de oposição | Baixa | Atender por e-mail; expurgo automático em 12 meses já ativo |
| Uso da marca John Deere | Baixa | Uso nominativo só para indicar compatibilidade, com aviso de não afiliação (feito). Não usar logo nem as cores da marca |
| Imagens de satélite Esri no painel | Baixa | Atribuição exibida no mapa. Conferir os termos da Esri para uso comercial e volume; se preciso, contratar um plano ou trocar de provedor |
| Limitação de responsabilidade frente ao CDC | Baixa | Redigida com ressalva para consumidor (produtor pessoa física). Revisar com advogado |
| Alterações futuras dos documentos | Baixa | Ao mudar, subir `versaoDocumentos` em `site/empresa.json` **e** `VERSAO_DOCUMENTOS` em `frontend/src/lib/legal.ts`; mudança relevante exige aviso por e-mail |
| Incidente de segurança | Variável | Ter um plano de resposta: comunicar a ANPD e os titulares em prazo razoável (Res. CD/ANPD nº 15/2024, 3 dias úteis) |

## Onde os dados ficam

- `interno.contatos`: pedidos do site. Campos opcionais em branco quando não informados; `ip_hash`; `politica_versao`; `aceita_novidades` (padrão falso). Expurgo após `RETENCAO_CONTATOS_MESES` (12).
- `interno.aceites`: `usuario_id`, documento (`termos` ou `privacidade`), versão, `ip_hash` e data. Só recebe inserções, para servir de prova do aceite.
- O painel guarda no navegador só a sessão de login e a organização selecionada (essenciais).
