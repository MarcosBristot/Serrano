# Funcionalidades inteligentes (IA e algoritmos)

## Transparência: o que é e o que não é IA hoje

**A Serrano não usa, em produção, modelos de aprendizado de máquina treinados nem LLMs.** As
funcionalidades "inteligentes" do MVP são **algoritmos determinísticos e estatísticos** que tomam
decisões automáticas sobre dados ruidosos de máquinas: reconhecer o formato do arquivo, limpar
leituras impossíveis, separar trabalho de ociosidade, achar o talhão pelo GPS, comparar cada
operação com o histórico da própria máquina e explicar a confiabilidade de cada número.

A escolha foi intencional nesta fase:

- **Explicável:** o produtor e o agrônomo precisam entender por que um alerta disparou. Cada alerta
  guarda o valor medido, o limiar e a versão da regra.
- **Pouco dado por cliente:** uma fazenda tem poucas máquinas e poucas safras. Medianas robustas
  funcionam com 5 a 50 operações; um modelo precisaria de muito mais dado rotulado.
- **Reprocessável:** toda regra tem versão (hash da configuração). Mudar um limiar refaz as análises
  a partir do dado bruto, sem perder histórico.

O [roadmap](roadmap.md) prevê modelos de aprendizado de máquina quando houver base suficiente.

## Funcionalidades implementadas

| # | Funcionalidade | Como funciona | Código |
|---|---|---|---|
| 1 | **Reconhecimento automático de formato** | Olha o nome e os primeiros bytes de cada arquivo (e o conteúdo de zips) e escolhe o leitor certo entre os formatos suportados (ISOBUS, Trimble, John Deere Gen4 e GreenStar 3). Formato desconhecido vira uma explicação ("parece Case IH/New Holland, ainda não suportado"). | `infrastructure/parsers/registry.py`, `application/ingestao.py` |
| 2 | **Sanitização de sinais** | Valores fisicamente impossíveis (ex.: velocidade acima de 40 km/h, vazão acima de 90 L/h, RPM acima de 3.500) viram "sem valor" e são contados num relatório de auditoria; o bruto nunca é alterado. Quando o fabricante não informa "motor ligado", o sistema deduz cruzando RPM, vazão de diesel e avanço do horímetro. | `domain/services/sanitization.py` |
| 3 | **Separação trabalho x ociosidade** | Motor ligado e velocidade abaixo do limiar de trabalho = parado. Junta paradas separadas por pausas curtas (tolerância de 30 s) e só alerta acima de 20 min. | `domain/services/rules.py` (`ociosidade`) |
| 4 | **Linha de base estatística por máquina** | Para cada máquina e tipo de operação, calcula a **mediana** (percentil 50) da vazão de diesel (L/h) e do L/ha nas **últimas 50 operações** com pelo menos 30 min de trabalho. | `infrastructure/persistence/alertas.py` (`linhas_base`) |
| 5 | **Detecção de anomalia de consumo** | Alerta quando a vazão sustentada (janela de 10 min) ou o L/ha da operação passa **30% acima** da linha de base da própria máquina, com no mínimo 5 operações de histórico. | `domain/services/rules.py` (`vazao_alta`, `l_ha_acima`) |
| 6 | **Detecção de salto de GPS** | Calcula a velocidade implícita entre posições consecutivas (distância / tempo). Acima de 40 km/h com deslocamento maior que 50 m é erro de receptor, não movimento real. Esta abordagem eliminou 165 de 169 falsos alertas do código original. | `domain/services/rules.py` (`gps_salto`), [ADR 0005](../adr/0005-formato-jdl-ancoras-e-gps.md) |
| 7 | **Nota de qualidade do dado (0 a 100)** | Cada operação recebe uma nota com penalidades explicadas: sessão curta (fragmento), canais ausentes, lacunas longas, linhas descartadas, horímetro inconsistente com o motor, contador de combustível divergente. Canais que o formato nunca grava não penalizam. | `domain/services/quality.py` |
| 8 | **Localização do talhão por GPS** | Cruza os pontos de trabalho com os contornos dos talhões (ponto-em-polígono, PostGIS/Shapely) e devolve o talhão com a **confiança** (fração dos pontos dentro). Correção manual do gestor tem prioridade. | `domain/services/geo.py` |
| 9 | **Unificação de nomes de talhão** | "CoxilhaGrand_Trigo22", "Coxilha Grande" e "COXILHA GRANDE" são a mesma lavoura: normaliza acentos e caixa, remove sufixo de safra e aceita nome cortado pelo monitor. | `domain/services/nomes.py` |
| 10 | **Área por cobertura real** | A trilha GPS vira faixas com a largura do implemento (buffer geométrico em UTM). A área coberta desconta a **sobreposição** (passadas repetidas), que também é reportada em %. | `domain/services/coverage.py` |
| 11 | **Mapa de calor do consumo** | Agrega L/ha por célula da lavoura para mostrar onde a máquina gastou mais. | `domain/services/mapas.py` |
| 12 | **Implemento padrão** | Quando o monitor não informa o implemento (ex.: Trimble), usa o padrão cadastrado na máquina para estimar área, ha/h e L/ha, e recalcula o histórico. | `application/processamento.py` |

## Integrações

| Integração | Direção | Como |
|---|---|---|
| Monitores de várias marcas: ISOBUS (ISO 11783), Trimble TMX-2050/PTx (Massey Ferguson), John Deere Gen4 e GreenStar 3 | Entrada | Hoje: arquivos do monitor enviados pelo produtor no painel ou pela API (upload em partes, zip). |
| Nuvem das fabricantes (planejada) | Entrada | Conector por fabricante com autorização do produtor (OAuth) e sincronização agendada, rumo ao zero trabalho manual ([roadmap](roadmap.md)). |
| Contornos de talhão | Entrada | Shapefile (.zip), KML, GeoJSON, ou desenho no mapa. |
| Webhooks | Saída | Alertas enviados com assinatura HMAC-SHA256, com fila de saída (outbox) e novas tentativas. |
| E-mail | Saída | Alertas e resumo semanal por SMTP. |
| Planilhas | Saída | CSV em streaming (Excel pt-BR) e XLSX assíncrono com link. |
| API REST | Saída | Chaves de API por organização para o sistema do cliente (ERP) ler os dados. |

## Validação

As regras e leitores são cobertos por testes unitários, de contrato (todo leitor passa pelo mesmo
contrato) e de **regressão com dados reais** de pendrive, comparados com uma linha de base
congelada (ver [plano de testes](plano-de-testes.md)). Em campo, a reanálise de todas as sessões
depois da correção de canais "fora do formato" levou a confiabilidade dos dados de 7% para 99,7%.
