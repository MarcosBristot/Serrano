-- Talhão repetido (mesma lavoura com outro nome no monitor: "Mae_Aveia22" = "Mãe") aponta para
-- o principal. Fica inativo e guarda o external_guid, para o próximo arquivo cair no certo.
alter table public.talhoes add column agrupado_em uuid references public.talhoes (id) on delete set null;
create index talhoes_agrupado_idx on public.talhoes (agrupado_em) where agrupado_em is not null;
