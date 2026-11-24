-- Implemento padrão da máquina: usado quando o arquivo do monitor não diz qual implemento estava
-- engatado (ex.: registros do Trimble TMX-2050 só trazem GPS). Com a largura dele a Serrano
-- calcula área, ha/h e L/ha; sem ele essas métricas ficam vazias.
alter table public.maquinas
    add column if not exists implemento_padrao_id uuid
        references public.implementos (id) on delete set null;

comment on column public.maquinas.implemento_padrao_id is
    'Implemento usado nas sessões cujo arquivo não informa implemento nem largura.';
