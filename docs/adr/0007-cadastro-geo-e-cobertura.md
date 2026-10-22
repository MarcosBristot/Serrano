# ADR 0007 — Cadastro, importação Gen4, localização por GPS e área por cobertura (M4)

Status: aceito em 21/10/2026.

## Importação do cadastro do monitor

O zip do pendrive gera o job `importar_gen4` (prioridade 60: depois de expandir o zip e **antes** dos
`.jdl`, que já localizam com os contornos). Fonte: `MasterData.xml` + `SpatialFiles/Boundary*.gjson`.

| Do MasterData | Vira | Observação |
|---|---|---|
| `Farm` (+ `Client`) | `fazendas` | upsert por GUID |
| `Field` (+ `<Farm>`) | `talhoes` | 12 no pendrive de 2026 |
| `OperationalBoundary` → `.gjson` | `talhoes.geometria` | só `boundarytype=Exterior` (5 de 12 talhões; cabeceiras não). |
| `Implement` | `implementos` | `PhysicalImplementWidth` (m) ou linhas x espaçamento |
| `Operator` | `operadores` | sem CPF |
| `Machine` | — | `SerialNumber` vazio; a máquina nasce pelo serial do `.jdl` |

- **GUIDs normalizados** (minúsculo, sem chaves) nos dois lados: o importador antigo tirava as chaves
  do MasterData e o `.jdl` as mantinha (`{f139b790-...}`), então o talhão do cabeçalho e o importado
  viravam dois registros.
- **Contorno do gestor vence**: talhão com `origem_contorno` = `upload`/`desenho` não é sobrescrito pela
  reimportação (contado em `contornos_preservados`).
- Implemento do `.jdl` casa com o do cadastro **pelo nome** (o `.jdl` não traz GUID do implemento).
- Reimportação: a chave do job é o zip, e os `.gjson` vão no payload. Um `.gjson` repetido entre dois
  pendrives continua "filho" do primeiro zip, então a busca por irmãos perdia contornos (bug achado
  no teste).
- XML com DTD/ENTITY é recusado (expansão de entidades).

## Localização da sessão

`LocalizadorDeTalhoes` (STRtree em memória, talhões da organização carregados uma vez por job):
o talhão da sessão é o que contém a **maioria dos pontos de trabalho** com posição; `talhao_confianca`
é essa fração. Ordem de precedência: **manual** (nunca sobrescrito) > **gps** > **monitor** (talhão
selecionado no monitor, do cabeçalho do `.jdl`) > nenhum. Cada ponto da telemetria recebe o seu
`talhao_id`.

Mudou um contorno, importou cadastro ou o gestor corrigiu o talhão: as sessões afetadas são
**reprocessadas a partir do bruto** (idempotente), para que área, L/ha e alertas acompanhem.

## Área por cobertura

Trechos de trabalho (motor ligado, ≥ 1 km/h, com posição; quebra em lacuna > 3 s ou salto > 30 m)
viram linhas em UTM (zona pelo centróide; Passo Fundo = EPSG:32722), com buffer de meia largura e
pontas retas, unidas com `union_all`. `sobreposicao_pct = 1 − união / (comprimento × largura)`.

**A área da sessão é a cobertura total, sem recorte pelo talhão.** No pendrive real, recortar pelo
talhão principal deu 73 ha contra 156 ha estimados nas sessões localizadas: os arquivos atravessam
vários talhões (confiança média de 0,78). Recortar inflaria o L/ha. A parte dentro do talhão vai em
`qualidade.detalhes.dentro_do_talhao_ha`, e confiança < 0,8 gera o aviso `VARIOS_TALHOES` (sem
penalidade). ha/h e L/ha usam a cobertura quando há trilha GPS e a estimada quando não há.

## Resultado no pendrive de 2026 (compose, ponta a ponta)

- Cadastro: 2 fazendas, 12 talhões (5 com contorno, 130,8 ha), 4 implementos, 4 operadores.
- 29 sessões localizadas por GPS (38,0 h de motor); as outras 525 ficam com o talhão do monitor
  (a maioria são fragmentos curtos ou trabalho em talhões sem contorno).
- Área: cobertura de 258,8 ha contra 279,3 ha estimados; sobreposição mediana de 2%; L/ha mediano
  passou de 4,02 para 4,26. Só 27,9% dos pontos com GPS caem em talhões com contorno: os outros 7
  talhões precisam de contorno (desenho ou upload) para a localização por GPS valer em toda a fazenda.

## Limites e pendências

- Sem o sinal de implemento levantado/abaixado, cabeceiras e deslocamentos em estrada com motor ligado
  a ≥ 1 km/h entram na cobertura e na área estimada. Próximo passo: decodificar os canais de seção/área
  do plantio no `.jdl` (o "Plantio" aparece nos grupos de canais) e usar como máscara.
- Importação de KML/Shapefile (o que o gestor costuma ter, do Google Earth ou do CAR) ficou para depois.
