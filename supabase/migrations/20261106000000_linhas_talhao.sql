-- Cabeceira e linhas-guia do talhão (ex.: controlador OMNI do pulverizador), para o mapa.
create table public.linhas_talhao (
    id              uuid primary key default gen_random_uuid(),
    organizacao_id  uuid not null references public.organizacoes (id) on delete cascade,
    talhao_id       uuid not null references public.talhoes (id) on delete cascade,
    tipo            text not null check (tipo in ('cabeceira', 'linha_guia')),
    subtipo         smallint,            -- linha-guia do OMNI: 1 = reta AB, 0 = curva
    gravado_em      timestamp,           -- hora local do controlador
    origem          text not null default 'omni',
    geometria       extensions.geometry(LineString, 4326) not null,
    criado_em       timestamptz not null default now()
);
create index linhas_talhao_talhao_idx on public.linhas_talhao (organizacao_id, talhao_id, tipo);

alter table public.linhas_talhao enable row level security;
create policy linhas_talhao_backend on public.linhas_talhao for all to campero_backend
    using (organizacao_id = (select public.app_org_atual()))
    with check (organizacao_id = (select public.app_org_atual()));
create policy linhas_talhao_membro_leitura on public.linhas_talhao for select to authenticated
    using (organizacao_id in (select public.orgs_do_usuario()));
grant select, insert, update, delete on public.linhas_talhao to campero_backend, service_role;
grant select on public.linhas_talhao to authenticated;
