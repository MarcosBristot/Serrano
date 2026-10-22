-- M1 · Buckets privados do Storage. Sem policy para authenticated:
-- download só por URL assinada emitida pela API. Caminhos: <bucket>/<org>/<sha256>.<ext>.
-- A limpeza de exportações vencidas (7 dias) é um job do worker (M8).

insert into storage.buckets (id, name, public, file_size_limit)
values
    ('brutos', 'brutos', false, 1073741824),
    ('limpos', 'limpos', false, 1073741824),
    ('exportacoes', 'exportacoes', false, 536870912)
on conflict (id) do nothing;
