-- Telemetria enxuta: o ponto PostGIS repetia lat/lon (29 bytes por linha) e o índice espacial
-- dele era o maior da tabela. Os três usos calculam o ponto na hora (com pré-filtro por caixa).
-- O índice (organizacao_id, ts) sobrava: as partições mensais já cortam por data.
alter table public.telemetria drop column geom;
drop index if exists public.telemetria_org_ts_idx;
