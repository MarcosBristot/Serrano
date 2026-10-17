# ADR 0001 — Adapter John Deere Gen4 (`.jdl`) e schema universal

- Status: proposto (validado em 1 trator, serial 1BM6210…, monitor Gen4 firmware 10.30)
- Contexto: o pendrive do monitor Gen4 traz `JD-Data/log/*.jdl`, `Gen4/MasterData.xml` e `Gen4/SpatialFiles/*.gjson`.

## Formato `.jdl` (engenharia reversa; não documentado pela John Deere)
Sequência de blocos `0x0D | uint32_le tamanho | mensagem protobuf`. Tipos: 3 versão, 1 cabeçalho
(árvore de dispositivos/canais com DDI, escala, offset, unidade; cliente/fazenda/talhão; implemento e
largura), 2 dados (~30 s), 4 rodapé. Dados em colunas por canal: deltas de tempo (unidade 0,5 ms) e
valores zigzag em **delta**, com soma contínua entre blocos. `valor = bruto/escala + offset`;
`-2^31` = não disponível. Cada bloco traz só ponto inicial/final de GPS (resolução ~30 s).

## Validações feitas (arquivo de 15,3 h)
- Velocidade (DDI 561) ≈ velocidade pelo GPS (8–9 km/h em plantio).
- Contador de combustível (DDI 100) +335 L ≈ integral da vazão (DDI 99, mediana 22 L/h × 15,3 h).
- Horímetro (DDI 247) +15,35 h ≈ duração do arquivo. Horário do cabeçalho = nome do arquivo (UTC−3).

## Decisões
1. **Sem nível de tanque no JD Gen4**: `fuel_level_l` fica NULL; a regra "queda de combustível" do protótipo
   é substituída por divergência contador × integral e vazão fora do padrão do trator.
2. Schema universal em `sistemacampero.schema.universal`; amostras limpas a **1 Hz**.
3. Pipeline em 5 etapas isoladas; etapas 4–5 reprocessáveis com outra `RuleConfig` (versão gravada).
4. Upload em partes + processamento em segundo plano (dump real: 605 MB / 4.570 arquivos).
5. Dados reais de clientes não entram no Git (`.gitignore`); testes usam `.jdl` sintético.

## Lacunas conhecidas
- Operador por sessão: não encontrado nos `.jdl` (só cadastro no MasterData).
- Contornos (`Boundary*.gjson`) existem só para alguns talhões; área trabalhada é estimada por
  distância × largura do implemento (cabeceiras e sobreposição inflam o valor).
- Escala da vazão (L/h) validada contra o contador, não contra abastecimento real.
- Formato pode mudar entre firmwares (10.28 vs 10.30 lidos sem diferença até aqui).
