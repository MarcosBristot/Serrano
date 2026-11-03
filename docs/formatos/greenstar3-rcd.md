# GreenStar 3 2630 (RCD) — anotações de engenharia reversa

Estado: **em estudo**, sem leitor ainda. Amostra: colheitadeira S540 (`1CQS540ATG0110336`),
safra de trigo 2022 (`CoxilhaGrand_Trigo22`), pasta `GS3_2630/<cliente>/RCD/`.

## Estrutura da pasta

| Caminho | Conteúdo |
|---|---|
| `RCD/EIC/Documentation/<xx>/<uuid>.fdl` | XML: cadastro (cliente, fazenda, talhão, cultura, máquina) e **lista de colunas** gravadas |
| `RCD/EIC/Documentation/<xx>/<uuid>.fdd` | Binário com os registros; o `.fdl` aponta para ele (`LogDataBlock logDataProcessor="EvenByteDelta"`) |
| `RCD/EIC/Documentation/<xx>/<uuid>.fdr` | Ainda não analisado (605 arquivos, sem `.fdl` correspondente) |
| `RCD/EIC/Fields`, `RCD/StoredMaps` | Contornos (`.fdshape`), linhas-guia (`.pth`) e mapas |

321 pares `.fdl`/`.fdd`; o maior `.fdd` tem 4 MB.

## Colunas declaradas no `.fdl` (exemplo da S540)

- Colheita: `vrHarvestMoisture` (%), `vrYieldWetMass` (kg), `dtHeaderStatus`, latência de 10 s nos sensores de rendimento e umidade.
- Plataforma: 5 seções de 1.520 mm (`vrSectionWidth`, `vrLateralOffset` de −3.040 a +3.040 mm), estado por seção (`dtRecordingStatus`).
- Máquina: `vrFuelRatePerHour` (L/h), `vrVehicleSpeed` (km/h).
- GPS: `vrLatitude`, `vrLongitude`, `vrHeading`, `vrDeltaDistance`, `vrElevation`, tipo de navegação e de sinal, precisão horizontal e vertical.
- Clima e solo (preenchidos à mão no monitor): umidade do ar, temperaturas, vento, céu e umidade do solo.

Cada coluna tem um `columnID` (ex.: `MeasElement929`, `GPSLatitude_5140`) que reaparece no `.fdd`.

## Cabeçalho do `.fdd`

Começa com UUIDs em texto (sessão, tarefa) e depois uma definição por coluna:

```
<tipo u16> <tam_total u16> <tam_nome u16> <nome ASCII> <flag u8?> <0x18 u16> <3 × float64>
```

Nos três `float64` de cada coluna numérica, o observado foi:

| Coluna | 1º | 2º | 3º |
|---|---|---|---|
| `GPSLatitude_5140` | 1,0e-9 (resolução?) | 4,5e-4 | −28,1129 (base) |
| `GPSLongitude_5140` | 1,0e-9 | 4,5e-4 | −52,93 (base) |
| `GPSHeading_5140` | 0,01 | 5,0 | 275,0 |

Hipótese: `valor = base + inteiro × resolução`, com os registros guardando **diferenças**
(daí o nome *EvenByteDelta*) em tamanho variável. A latitude absoluta aparece como `float64`
só no cabeçalho (bytes 1345 e 1925 da amostra).

## Próximos passos

1. Mapear o fim do cabeçalho e o início dos registros. Descobrir o tamanho de cada registro e
   como os deltas são codificados (provavelmente inteiros de 1, 2 ou 4 bytes conforme o
   tamanho do delta, alinhados em byte par).
2. Validar com o que se sabe do campo: a trilha GPS precisa ficar dentro do contorno de
   Coxilha Grande; a velocidade, entre 3 e 8 km/h colhendo; a umidade do trigo, entre 11% e 20%.
3. Só então escrever o adapter (`parsers/john_deere_gs3/`), com o rendimento e a umidade
   entrando como colunas novas no schema universal.
