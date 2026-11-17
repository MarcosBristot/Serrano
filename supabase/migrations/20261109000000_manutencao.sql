-- Manutenção pelo horímetro: planos por máquina (a cada N horas) e o histórico do que foi feito.

-- Horímetro informado pelo produtor (painel da máquina), para quem não grava o horímetro no
-- monitor (ex.: GreenStar 3): a Serrano soma as horas de motor registradas depois dessa leitura.
alter table public.maquinas
    add column horimetro_informado_h double precision,
    add column horimetro_informado_em timestamptz;

create table public.planos_manutencao (
    id              uuid primary key default gen_random_uuid(),
    organizacao_id  uuid not null references public.organizacoes (id) on delete cascade,
    maquina_id      uuid not null references public.maquinas (id) on delete cascade,
    nome            text not null check (length(nome) between 2 and 120),
    intervalo_h     double precision not null check (intervalo_h > 0),
    ultima_h        double precision,  -- horímetro na última vez que foi feita
    ultima_em       date,
    ativo           boolean not null default true,
    criado_em       timestamptz not null default now()
);
create index planos_manutencao_maquina_idx on public.planos_manutencao (organizacao_id, maquina_id);

create table public.manutencoes_feitas (
    id              uuid primary key default gen_random_uuid(),
    organizacao_id  uuid not null references public.organizacoes (id) on delete cascade,
    plano_id        uuid references public.planos_manutencao (id) on delete set null,
    maquina_id      uuid not null references public.maquinas (id) on delete cascade,
    nome            text not null,
    horimetro_h     double precision not null,
    feita_em        date not null,
    custo_rs        numeric(12, 2),
    observacao      text check (length(observacao) <= 500),
    criado_em       timestamptz not null default now()
);
create index manutencoes_feitas_maquina_idx on public.manutencoes_feitas (organizacao_id, maquina_id, feita_em desc);

alter table public.planos_manutencao enable row level security;
alter table public.manutencoes_feitas enable row level security;
create policy planos_manutencao_backend on public.planos_manutencao for all to campero_backend
    using (organizacao_id = (select public.app_org_atual()))
    with check (organizacao_id = (select public.app_org_atual()));
create policy planos_manutencao_membro_leitura on public.planos_manutencao for select to authenticated
    using (organizacao_id in (select public.orgs_do_usuario()));
create policy manutencoes_feitas_backend on public.manutencoes_feitas for all to campero_backend
    using (organizacao_id = (select public.app_org_atual()))
    with check (organizacao_id = (select public.app_org_atual()));
create policy manutencoes_feitas_membro_leitura on public.manutencoes_feitas for select to authenticated
    using (organizacao_id in (select public.orgs_do_usuario()));
grant select, insert, update, delete on public.planos_manutencao, public.manutencoes_feitas
    to campero_backend, service_role;
grant select on public.planos_manutencao, public.manutencoes_feitas to authenticated;
