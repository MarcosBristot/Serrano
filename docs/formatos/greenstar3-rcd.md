# GreenStar 3 2630 (RCD): formato decifrado

Estado: **leitor em produção** (`infrastructure/parsers/john_deere_gs3/`), validado em 321
operações reais de uma colheitadeira S540 (`1CQS540ATG0110336`), safras 2022 a 2026: todas
decodificadas por inteiro (3,67 milhões de registros, ~1.000 h de colheita).

## Estrutura da pasta

| Caminho | Conteúdo |
|---|---|
| `RCD/EIC/Documentation/<xx>/<uuid>.fdl` | XML: cadastro (cliente, fazenda, talhão, cultura, máquina, plataforma), colunas e **hora de início de cada bloco** (`LogTaskRegion@timeStamp`, UTC) |
| `RCD/EIC/Documentation/<xx>/<uuid>.fdd` | Binário `EvenByteDelta` com os registros |
| `RCD/EIC/Documentation/<xx>/<uuid>.fdr` | Não analisado (sem `.fdl` correspondente) |
| `RCD/EIC/Fields`, `RCD/StoredMaps` | Contornos (`.fdshape`), linhas-guia (`.pth`) e mapas: não lidos ainda |

Na expansão do .zip o par `.fdl` + `.fdd` vira um arquivo só (`domain.ingestao.empacotar_rcd`,
tipo `rcd`, tecnologia `gs3`); metade sem par é ignorada. Enviar `.fdd` avulso é recusado com
orientação para mandar a pasta `GS3_2630` em .zip.

## `.fdd`

Uma sequência de **blocos** (um por `LogTaskRegion` do `.fdl`, na mesma ordem). Cada bloco:

1. `u16` 1 (primeiro bloco) ou 4 (seguintes), UUIDs em texto (`u16` tamanho + ASCII).
2. Lista de colunas: `01 00 02 00 <u16 n>` e, por coluna,
   `u16 tipo, u16 _, u16 tam_nome, nome, u8 cru`, depois
   * numérica (tipos 3, 4, 5): `u16 24` + 3 × `float64` (**resolução**, ?, **base**);
   * enumerada (tipo 1): `u16 qtd, u16 tamanho`, opções (`u16` + texto). Índice 0 = ligado.
3. Registros de ~1 s (`ElapsedTime` sobe 1001-1003 ms):

| Campo | Formato |
|---|---|
| cabeçalho | `u16 2`, `u8 n_controle`, `u8 omitidas`, `u32` (0x70 ou 0xE0, não usado) |
| máscara A | `u32`: coluna crua que **repete** o valor anterior |
| máscara B | `u24`: coluna cujo valor vem **absoluto** no fim do registro |
| bloco fixo | uma entrada por coluna não crua, na ordem: `i16` (tipo 3) ou `i32` (tipo 4) com o **delta**; `u16` com o estado **absoluto** (enumeradas) |
| controle | `n_controle` valores marcados (`u16 tipo, u16 tamanho, dados`) |
| crus | um valor marcado por bit de B, em ordem crescente (`float64`, `float32` ou inteiro) |

* As máscaras começam na **9ª coluna** (bit 0 = coluna 8), com 5 ou 6 seções na plataforma.
* Coluna não crua com bit em B sai do bloco fixo e o valor cru zera a referência do delta (é
  assim que o rumo passa de 359° para 0°).
* Coluna crua fora de A e de B fica **ausente** naquele registro.
* `omitidas` é uma máscara das primeiras colunas que não vêm (registro de **evento**, de menos de
  1 s, quando a plataforma sobe ou desce): a coluna fica nula e o próximo delta parte do **valor
  físico zero** (não da base do bloco; com base de 13 % de umidade o erro seria de 13 pontos).
* Valor físico = `base + soma_dos_deltas × resolução`.

## Colunas (S540, plataforma 625F de 7,6 m)

| Representação no `.fdl` | Unidade | Uso no Serrano |
|---|---|---|
| `vrHarvestMoisture` | % | diagnóstico (umidade média ponderada pela massa) |
| `vrYieldWetMass` | kg por registro | diagnóstico (massa úmida total) |
| `dtHeaderStatus`, `dtRecordingStatus` (5-6 seções) | enumerado | ainda não usado |
| `vrFuelRatePerHour` | L/h | `fuel_rate_lph` |
| `vrVehicleSpeed` | km/h | `speed_kmh` |
| `vrDistanceTraveled` (`DeltaDistance`) | cm por registro | `speed_alt_kmh` |
| `vrLatitude`/`vrLongitude` `_5140` | graus | posição (o `_5141` é a projeção na plataforma) |
| clima e solo (`TgtElement20..32`) | — | digitados no monitor; ignorados |

Conferência com a realidade (trigo, Coxilha Grande, 2022): 12,7 h, 528 L (41,5 L/h, 13,4 L/ha),
39,3 ha a 4,4 km/h e 200,6 t de massa úmida a 17,9 % de umidade (5,1 t/ha). A plataforma fica
ligada 96 % do tempo a 4,4 km/h e levantada nas manobras a ~7 km/h.

## Validação da produtividade

Massa seca (umidade de comercialização: soja 14 %, trigo 13 %) sobre a área colhida com a
plataforma baixa, mediana por safra: soja 32,6 (21/22, seca), 29,5 (22/23, seca), 79,2 (23/24),
51,0 (24/25, seca) e 81,5 sc/ha (25/26); trigo 70,2 (2022), 34,2 (2023, El Niño), 59,5 (2024) e
68,9 sc/ha (2025). Bate com o histórico do RS.

## Em aberto

* Mapa de produtividade ponto a ponto (hoje o resumo é por operação).
* Significado do 2º `float64` das colunas e do `u32` do cabeçalho do registro.
* `.fdr`, `.fdshape` e `.pth`.
