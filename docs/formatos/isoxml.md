# ISOXML (ISO 11783-10): monitores ISOBUS de várias marcas

Estado: **leitor em produção** (`infrastructure/parsers/isoxml/`), validado com arquivos sintéticos
gerados conforme a norma. **Falta amostra real** de cada marca (Stara, Jacto, Case IH, New
Holland, Massey, Kuhn) para confirmar o que cada monitor grava.

## Por que ISOXML

É o formato aberto que monitores ISOBUS exportam no pendrive (pasta `TASKDATA`). Um leitor só
cobre várias marcas, e é por ele que entram frotas mistas: o diferencial do Serrano é juntar
tudo na mesma tela e na mesma conta de custo por saca.

## O que é lido

| Arquivo | Uso |
|---|---|
| `TASKDATA.XML` | Tarefa (`TSK`) que gravou cada `TLG`: cliente (`CTR`), fazenda (`FRM`), talhão (`PFD`), equipamento (`DVC` + `DET`, série no atributo `E`) |
| `TLGnnnnn.XML` | Cabeçalho `TIM`/`PTN`/`DLV` (DDI em hexadecimal; atributo vazio = vem em cada registro) |
| `TLGnnnnn.BIN` | Registros: `u32` ms + `u16` dias desde 1980, campos do `PTN` (latitude/longitude em 1e-7 graus), `u8` quantidade de DLV e pares `u8` índice + `i32` valor |

Na expansão do .zip, cada `TLG` com `.XML` e `.BIN` vira um arquivo do Serrano junto com o
`TASKDATA.XML` da mesma pasta (`domain.ingestao.empacotar_isoxml`, tipo `isoxml`).

## DDIs usados (ISO 11783-11)

| DDI | Nome | Uso |
|---|---|---|
| 149 | Instantaneous Fuel Consumption per Time (mm³/s) | `fuel_rate_lph` |
| 148 | Total Fuel Consumption (ml) | `fuel_total_l` (e vazão, se o 149 faltar) |
| 67 | Actual Working Width (mm) | largura do implemento (área) |
| 2 | Actual Volume Per Area Application Rate (mm³/m²) | marca pulverização; taxa média em L/ha no diagnóstico |

Velocidade vem da trilha GPS (distância por segundo, média móvel de 3 s): não depende de DDI de
fabricante. Os DDIs presentes em cada arquivo ficam no diagnóstico, para mapear os de cada marca
quando chegarem amostras reais.

## Em aberto

* Amostras reais por marca; DDIs de colheita (rendimento e umidade) e de plantio (população).
* Talhão a partir da geometria do `PFD` (`PLN`/`LSG`), hoje só pelo nome.
* Tarefas com mais de um `TLG` por máquina (hoje cada `TLG` é uma sessão; as jornadas juntam).
