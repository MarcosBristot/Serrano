-- Colheita por sessão (monitor da colheitadeira): base do Fechamento da Safra por talhão.
create table public.colheitas (
    sessao_id        uuid primary key references public.sessoes_trabalho (id) on delete cascade,
    organizacao_id   uuid not null references public.organizacoes (id) on delete cascade,
    cultura          text,               -- soja, trigo, milho... (normalizada)
    variedade        text,
    safra            text not null,      -- "2025/26" (verão) ou "Inverno 2025"
    massa_umida_kg   double precision not null,
    umidade_pct      double precision,
    massa_seca_kg    double precision not null,  -- na umidade de comercialização da cultura
    area_colhida_ha  double precision not null,  -- só com a plataforma abaixada
    criado_em        timestamptz not null default now()
);
create index colheitas_org_safra_idx on public.colheitas (organizacao_id, safra);

alter table public.colheitas enable row level security;
create policy colheitas_backend on public.colheitas for all to campero_backend
    using (organizacao_id = (select public.app_org_atual()))
    with check (organizacao_id = (select public.app_org_atual()));
create policy colheitas_membro_leitura on public.colheitas for select to authenticated
    using (organizacao_id in (select public.orgs_do_usuario()));
grant select, insert, update, delete on public.colheitas to campero_backend, service_role;
grant select on public.colheitas to authenticated;
