# Como adicionar uma marca (adapter de telemetria)

Um adapter lê o arquivo de um fabricante/tecnologia e devolve o **schema universal**
(`domain/telemetry.py`). Nada depois dele (sanitização, métricas, regras, banco) conhece a marca.

## Checklist

1. **Amostras reais** do monitor (várias sessões, inclusive uma sem GPS e uma só de cabeçalho).
   Ficam fora do Git: são dado de cliente.
2. Pacote `src/sistemacampero/infrastructure/parsers/<marca>_<tecnologia>/` com:
   - leitor de baixo nível (formato, sem significado dos canais);
   - mapeamento de canais → colunas do schema universal, com a validação feita registrada no docstring;
   - `adapter.py` implementando `TelemetryAdapter` (`domain/ports.py`):
     `brand`, `technology`, `version`, `can_parse(head, filename)`, `parse(data, ctx)`.
3. Regras do contrato (o teste `tests/contrato` verifica):
   - 1 linha por segundo, `ts` em UTC, estritamente crescente;
   - unidades: km/h, L, L/h, h, graus WGS84; colunas e tipos de `COLUNAS_UNIVERSAIS`;
   - **ausência = NaN, nunca 0**; `engine_on = <NA>` se o fabricante não informa (a sanitização deriva);
   - mesmo arquivo → mesmo resultado (idempotente);
   - arquivo válido sem amostras → `EmptyFile` com `motivo` e `explicacao`;
   - arquivo corrompido → `ArquivoInvalido` (nunca `IndexError`/`struct.error` vazando);
   - `Diagnostico` preenchido: canais usados (DDI/escala/offset), canais ausentes, fonte da posição.
4. Registrar em `registry.registro_padrao()`.
5. Gerador sintético em `tests/sinteticos/` e entrada em `AMOSTRAS` de
   `tests/contrato/test_contrato_adapters.py` (trabalho de 30 min a 8 km/h, 22 L/h e 1.800 RPM;
   sem o canal de RPM; só cabeçalho).
6. Regressão com o dump real (`scripts/regressao_dump.py`) e linha de base congelada por marca.
7. ADR com o que foi descoberto do formato e o que ficou em aberto.

## Candidato: ISOXML (ISO 11783-10, TASKDATA + TLG)

Padrão aberto exportado por vários monitores (CNH, Case IH, Trimble, Stara…). Um adapter cobriria
várias marcas. Ainda não se sabe se o ISOXML desses monitores traz consumo de combustível: é preciso
conferir com amostras reais das máquinas do piloto.
