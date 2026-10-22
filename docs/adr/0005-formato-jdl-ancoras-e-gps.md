# ADR 0005 — Formato `.jdl`: âncoras, trilha GPS e correção dos defeitos do M0

Status: aceito em 21/10/2026 (M2). Base: dump real de 2026 (1.586 `.jdl`, trator 6210, Gen4 10.x),
fora do Git. Leitor: `infrastructure/parsers/john_deere_gen4/jdl.py`.

## O que o leitor antigo não sabia

| Campo | Antes | Verificado no dump |
|---|---|---|
| Entrada de canal, campo **1** (double) | ignorado | **âncora de valor**: o valor bruto acumulado antes do bloco. Em 6.444 de 6.444 blocos do arquivo `106a770c` ela é igual à soma dos deltas |
| Entrada de canal, campo **12** (int64) | ignorado | **âncora de tempo**: início do bloco em ms desde o início do arquivo (pode ser negativo, ~−2 s no 1º bloco) |
| Bloco, campos **6/7** | "posição no início/fim do bloco" | **cantos sudoeste e nordeste** de uma caixa: em 9.100 de 9.100 blocos, lat e lon de 7 ≥ de 6 |
| Canal **sem definição** no cabeçalho com campos 10/12/13 | descartado | **trilha GPS a ~5 Hz**: deltas zigzag de tempo (ms), latitude e longitude (nanograus), contínuos entre blocos, com âncoras nos campos 1, 2 (lat/lon) e 26 (tempo) |
| Canais com outra codificação (resumos, ex.: caixa por canal) | quebravam a leitura sem filtro | ignorados e contados em `entradas_ignoradas` |

**Validação da trilha GPS** (4 arquivos, 500 mil pontos): velocidade derivada da trilha ÷ velocidade da roda
= 0,996–1,000, erro mediano de 0,1 km/h, atraso 0 s, maior salto entre amostras de 5 Hz = 3 m.
Em aberto: só ~82% dos pontos caem dentro da caixa do próprio bloco (a caixa parece cobrir uma janela
de tempo deslocada). Não afeta nada, porque a posição vem da trilha.

## Defeitos do M0 (seção 0.2) — causa e correção

1. **"Motor ligado" falhava em silêncio** (`106a770c`: RPM ≤ 709, 0,29 h de motor em 8,9 h).
   Causa: o 1º bloco já trazia a âncora de valor e o leitor somava os deltas a partir de 0, então toda
   a série ficava deslocada (−1.546 RPM). Não era escala nem canal diferente. Afetava outros arquivos:
   no dump inteiro, o motor passou de 59,0 h para 74,8 h, contra 74,3 h de horímetro.
   Correção: âncoras de valor e de tempo a cada bloco. Defesa extra: `engine_on` cruza RPM → vazão →
   horímetro, e a checagem horímetro × motor rebaixa a qualidade e gera `qualidade_dado`.
2. **Contador × integral** (1.057 L × 864 L). Causa principal: o mesmo deslocamento da vazão.
   Agora: 1.151 L × 1.136 L, mediana de 1,022 nas sessões comparáveis. A checagem exige ≥ 10 L **e**
   ≥ 0,5 h de motor, com tolerância de max(15%, 2 × 0,5 L).
3. **`gps_salto` com 165 de 169 falsos**. Causa: os cantos da caixa eram lidos como fim/início de
   trajetória. Agora a posição vem da trilha de 5 Hz (fallback: centro da caixa), e a regra usa a
   velocidade implícita entre posições distintas consecutivas. Saltos seguidos viram um alerta.
   No dump: 0 alertas.

Cada defeito tem teste de regressão sintético em `tests/regressao/test_defeitos_m0.py`.

## Linha de base de 2026 (congelada)

`scripts/linha_base/subconjunto_2026.json` (só números por sha256, sem nomes). Resumo:

| | código antigo (preliminar) | M2 |
|---|---|---|
| Motor / horímetro | 59,0 h / — | 74,8 h / 74,3 h |
| Trabalho / ocioso | 47,3 h / 7,6 h | 59,9 h / 9,9 h |
| Integral da vazão / contador | 878 L / 1.144 L | 1.136 L / 1.151 L |
| Área estimada | 216 ha | 279 ha |
| Mediana L/ha · ha/h | 3,91 · 4,60 | 4,02 · 4,64 |
| `gps_salto` | 169 | 0 |
| Sessões com dado | 554 | 554, das quais **464 são fragmentos < 2 min** |
| Sem amostra do trator ("só cabeçalho") | 1.032 | 1.032 |

Arquivo grande da Cabana (30/04): 10,19 h de motor, 168,3 L integrados (172 L no contador),
40,5 ha estimados, 4,16 L/ha. Rodar: `uv run python scripts/regressao_dump.py "<JD-Data/log>"`.

## Consequências

- A área por cobertura (M4) e a localização de talhão passam a usar trilha real de 5 Hz, e não uma
  interpolação de 30 s. O risco de "GPS de 30 s cortando curvas" do plano deixa de existir quando
  há trilha (201 de 554 sessões; 15 só têm a caixa).
- Versões: adapter `john_deere_gen4` 2.0.0, sanitizador 3, regras 2. Reprocessar o histórico com elas.
- Outros firmwares podem codificar diferente: o diagnóstico por arquivo (`ancoras_divergentes`,
  `entradas_ignoradas`, canais ausentes) aparece na qualidade em vez de virar número errado.
