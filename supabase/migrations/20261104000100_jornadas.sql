-- Jornadas: o que o produtor chama de "operação". O monitor abre um .jdl a cada ligada da
-- chave, reinício ou troca de configuração (às vezes vários em paralelo); a jornada junta
-- os arquivos da mesma máquina separados por menos de 15 min. Métricas vêm da telemetria
-- (sem dupla contagem de arquivos sobrepostos), como em metricas_diarias.
create table public.jornadas (
    id              uuid primary key default gen_random_uuid(),
    organizacao_id  uuid not null references public.organizacoes (id) on delete cascade,
    maquina_id      uuid not null references public.maquinas (id) on delete cascade,
    versao_regras   text not null,
    inicio          timestamptz not null,
    fim             timestamptz not null,
    talhao_id       uuid references public.talhoes (id) on delete set null, -- onde mais trabalhou
    talhoes         integer not null default 0,
    operacao        text,
    arquivos        integer not null,
    motor_h         double precision not null default 0,
    trabalho_h      double precision not null default 0,
    ocioso_h        double precision not null default 0,
    litros          double precision not null default 0,
    litros_trabalho double precision not null default 0,
    litros_ocioso   double precision not null default 0,
    area_ha         double precision not null default 0,
    distancia_km    double precision not null default 0,
    criado_em       timestamptz not null default now(),
    check (fim >= inicio)
);
create index jornadas_org_inicio_idx on public.jornadas (organizacao_id, inicio desc);
create index jornadas_maquina_idx on public.jornadas (maquina_id, versao_regras, inicio);

alter table public.jornadas enable row level security;
create policy jornadas_backend on public.jornadas for all to campero_backend
    using (organizacao_id = (select public.app_org_atual()))
    with check (organizacao_id = (select public.app_org_atual()));
create policy jornadas_membro_leitura on public.jornadas for select to authenticated
    using (organizacao_id in (select public.orgs_do_usuario()));
grant select, insert, update, delete on public.jornadas to campero_backend, service_role;
grant select on public.jornadas to authenticated;
