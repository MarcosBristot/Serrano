-- M1 · Dado limpo: sessões de trabalho e telemetria 1 Hz particionada por mês.
-- As medidas seguem o schema universal dos adapters (contrato entre marcas).

create table public.sessoes_trabalho (
    id uuid primary key default gen_random_uuid(),
    organizacao_id uuid not null references public.organizacoes (id) on delete cascade,
    arquivo_bruto_id uuid not null unique references public.arquivos_brutos (id) on delete cascade,
    maquina_id uuid not null references public.maquinas (id) on delete cascade,
    implemento_id uuid references public.implementos (id) on delete set null,
    operador_id uuid references public.operadores (id) on delete set null,
    talhao_id uuid references public.talhoes (id) on delete set null,
    talhao_origem text not null default 'nenhum'
        check (talhao_origem in ('gps', 'monitor', 'manual', 'nenhum')),
    talhao_monitor_id uuid references public.talhoes (id) on delete set null,
    talhao_confianca numeric(5, 4) check (talhao_confianca between 0 and 1),
    operacao text,
    inicio timestamptz not null,
    fim timestamptz not null,
    n_amostras integer not null default 0,
    adapter text not null,
    adapter_versao text not null,
    firmware text,
    caminho_limpo text,
    qualidade_score smallint check (qualidade_score between 0 and 100),
    qualidade jsonb not null default '{}',
    criado_em timestamptz not null default now(),
    atualizado_em timestamptz not null default now(),
    check (fim >= inicio)
);
create index sessoes_org_inicio_idx on public.sessoes_trabalho (organizacao_id, inicio desc);
create index sessoes_maquina_idx on public.sessoes_trabalho (maquina_id, inicio desc);
create index sessoes_talhao_idx on public.sessoes_trabalho (talhao_id);
create trigger sessoes_atualizado_em before update on public.sessoes_trabalho
    for each row execute function interno.tocar_atualizado_em();

create table public.telemetria (
    organizacao_id uuid not null,
    maquina_id uuid not null,
    sessao_id uuid not null,
    ts timestamptz not null,
    lat double precision,
    lon double precision,
    geom extensions.geography(Point, 4326) generated always as (
        case when lat is not null and lon is not null
            then extensions.st_setsrid(extensions.st_makepoint(lon, lat), 4326)::extensions.geography
        end
    ) stored,
    gps_valid boolean not null default false,
    speed_kmh real,
    speed_alt_kmh real,
    engine_rpm real,
    engine_load_pct real,
    fuel_rate_lph real,
    fuel_total_l double precision,
    fuel_level_l real,
    engine_hours double precision,
    engine_on boolean,
    talhao_id uuid,
    primary key (maquina_id, ts)
) partition by range (ts);

-- FKs no pai: a exclusão da sessão apaga a telemetria (reprocessamento idempotente).
alter table public.telemetria
    add constraint telemetria_sessao_fk foreign key (sessao_id)
        references public.sessoes_trabalho (id) on delete cascade,
    add constraint telemetria_org_fk foreign key (organizacao_id)
        references public.organizacoes (id) on delete cascade;

create index telemetria_sessao_idx on public.telemetria (sessao_id, ts);
create index telemetria_org_ts_idx on public.telemetria (organizacao_id, ts);
create index telemetria_geom_idx on public.telemetria using gist (geom);

create table public.telemetria_default partition of public.telemetria default;

-- Partições são acessadas só pelo pai: privilégios e RLS do pai valem;
-- acesso direto à partição contornaria a RLS, por isso tudo é revogado nela.
create or replace function interno.fechar_particao(p_tabela regclass) returns void
language plpgsql
set search_path = ''
as $$
begin
    execute format('alter table %s enable row level security', p_tabela);
    execute format(
        'revoke all on %s from public, anon, authenticated, service_role, campero_backend',
        p_tabela
    );
end
$$;
select interno.fechar_particao('public.telemetria_default');

-- Cria (se faltar) a partição mensal que contém p_ts. Chamada pelo worker antes do COPY.
create or replace function interno.garantir_particao(p_ts timestamptz) returns text
language plpgsql security definer
set search_path = ''
as $$
declare
    v_inicio date := date_trunc('month', p_ts at time zone 'UTC')::date;
    v_nome text := format('telemetria_y%sm%s', to_char(v_inicio, 'YYYY'), to_char(v_inicio, 'MM'));
begin
    if to_regclass('public.' || v_nome) is null then
        execute format(
            'create table public.%I partition of public.telemetria for values from (%L) to (%L)',
            v_nome,
            (v_inicio::timestamp at time zone 'UTC'),
            ((v_inicio + interval '1 month')::timestamp at time zone 'UTC')
        );
        perform interno.fechar_particao(('public.' || quote_ident(v_nome))::regclass);
    end if;
    return v_nome;
end
$$;
revoke all on function interno.garantir_particao(timestamptz) from public;
revoke all on function interno.fechar_particao(regclass) from public;
