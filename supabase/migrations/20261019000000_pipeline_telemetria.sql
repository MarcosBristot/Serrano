-- Migration do pipeline de telemetria (schema como código: não alterar em produção na mão).
-- Aplicar com:  supabase db push   (ou colar no SQL Editor, uma única vez, em ordem).
--
-- ATENÇÃO antes de aplicar em um banco que já tem dados:
--   1. A tabela legada `telemetria` recebeu, em execuções anteriores, linhas com valores
--      PLACEHOLDER (vazão 15.0 / velocidade 8.0 / RPM 1800 fixos). Elas são dados falsos.
--      Recomenda-se limpar:  truncate table telemetria;   (revise antes: o comando apaga tudo)
--   2. `talhoes` pode ter duplicatas (importação antiga inseria também os polígonos de
--      cabeceira). Recomenda-se:  delete from talhoes where external_guid is null;
--      e reimportar com:  sistemacampero import-boundaries <pasta Gen4>

create extension if not exists postgis;

-- ---------------------------------------------------------------- talhões
alter table talhoes add column if not exists external_guid text;
alter table talhoes add column if not exists area_ha numeric;
alter table talhoes add column if not exists fazenda text;
alter table talhoes add column if not exists cliente text;

create unique index if not exists talhoes_external_guid_uq on talhoes (external_guid)
  where external_guid is not null;
create index if not exists talhoes_geometria_gix on talhoes using gist (geometria);

-- Upsert por GUID do monitor (idempotente). O GeoJSON entra como jsonb.
create or replace function upsert_talhao(
  p_external_guid text, p_nome text, p_fazenda text, p_cliente text,
  p_area_ha numeric, p_geojson jsonb
) returns uuid
language plpgsql security definer set search_path = public, extensions as $$
declare v_id uuid;
begin
  insert into talhoes (external_guid, nome, fazenda, cliente, area_ha, geometria)
  values (p_external_guid, p_nome, p_fazenda, p_cliente, p_area_ha,
          ST_SetSRID(ST_GeomFromGeoJSON(p_geojson::text), 4326))
  on conflict (external_guid) where external_guid is not null do update
    set nome = excluded.nome, fazenda = excluded.fazenda, cliente = excluded.cliente,
        area_ha = excluded.area_ha, geometria = excluded.geometria
  returning id into v_id;
  return v_id;
end $$;

-- Talhões como GeoJSON para a junção espacial feita em memória pelo backend
-- (substitui uma chamada RPC por ponto GPS).
create or replace function listar_talhoes_geojson()
returns table (id uuid, nome text, fazenda text, cliente text, area_ha numeric,
               external_guid text, geometry jsonb)
language sql stable security definer set search_path = public, extensions as $$
  select id, nome, fazenda, cliente, area_ha, external_guid,
         ST_AsGeoJSON(geometria)::jsonb
  from talhoes where geometria is not null;
$$;

revoke all on function upsert_talhao(text, text, text, text, numeric, jsonb) from public, anon, authenticated;
revoke all on function listar_talhoes_geojson() from public, anon, authenticated;
grant execute on function upsert_talhao(text, text, text, text, numeric, jsonb) to service_role;
grant execute on function listar_talhoes_geojson() to service_role;

-- ---------------------------------------------------------------- sessões
create table if not exists sessoes_trabalho (
  source_sha256     text primary key,            -- sha256 do arquivo bruto (idempotência)
  source_file       text not null,
  machine_serial    text not null,
  talhao_id         uuid references talhoes(id) on delete set null,
  adapter           text not null,
  adapter_version   text not null,
  operation         text,
  implement_name    text,
  implement_width_m numeric,
  started_at        timestamptz not null,
  ended_at          timestamptz not null,
  created_at        timestamptz not null default now()
);
create index if not exists sessoes_machine_started on sessoes_trabalho (machine_serial, started_at desc);

-- ---------------------------------------------------------------- telemetria (dado limpo)
-- Mantém o nome e a chave de conflito já usados pela API: (machine_serial, timestamp).
create table if not exists telemetria (
  id              bigint generated always as identity primary key,
  machine_serial  text not null,
  "timestamp"     timestamptz not null,
  created_at      timestamptz not null default now()
);
alter table telemetria add column if not exists session_sha256  text references sessoes_trabalho(source_sha256) on delete cascade;
alter table telemetria add column if not exists talhao_id       uuid references talhoes(id) on delete set null;
alter table telemetria add column if not exists latitude        double precision;
alter table telemetria add column if not exists longitude       double precision;
alter table telemetria add column if not exists speed_kmh       real;
alter table telemetria add column if not exists speed_alt_kmh   real;
alter table telemetria add column if not exists engine_rpm      real;
alter table telemetria add column if not exists engine_load_pct real;
alter table telemetria add column if not exists fuel_rate_lph   real;
alter table telemetria add column if not exists fuel_total_l    double precision;
alter table telemetria add column if not exists engine_hours    double precision;
alter table telemetria add column if not exists engine_on       boolean not null default false;

create unique index if not exists telemetria_machine_ts_uq on telemetria (machine_serial, "timestamp");
create index if not exists telemetria_talhao_ts on telemetria (talhao_id, "timestamp");

-- ---------------------------------------------------------------- resultados (reprocessáveis)
create table if not exists metricas_sessao (
  session_sha256      text not null references sessoes_trabalho(source_sha256) on delete cascade,
  rules_version       text not null,
  machine_serial      text not null,
  talhao_id           uuid references talhoes(id) on delete set null,
  field_name          text, field_guid text, operation text, implement_name text,
  implement_width_m   numeric,
  duration_h real, engine_on_h real, work_h real, idle_h real, engine_hours_delta real,
  fuel_integral_l real, fuel_counter_l real, fuel_work_l real, fuel_idle_l real,
  lph_work real, lph_idle real, work_distance_km real, avg_speed_work_kmh real,
  worked_area_ha real, ha_per_h real, l_per_ha real, l_per_ha_work real, gps_coverage real,
  primary key (session_sha256, rules_version)
);
create index if not exists metricas_machine on metricas_sessao (machine_serial);

create table if not exists alertas (
  id             text primary key,                -- hash determinístico (sem duplicar ao reprocessar)
  session_sha256 text not null references sessoes_trabalho(source_sha256) on delete cascade,
  rules_version  text not null,
  kind           text not null,
  severity       text not null check (severity in ('info', 'atencao', 'alto')),
  start_utc      timestamptz,
  end_utc        timestamptz,
  value          double precision,
  message        text not null,
  details        jsonb not null default '{}'::jsonb
);
create index if not exists alertas_session on alertas (session_sha256);
create index if not exists alertas_kind_start on alertas (kind, start_utc desc);

-- ---------------------------------------------------------------- segurança
-- RLS ligado e SEM policies: só a service_role (backend) acessa. Quando o frontend ler
-- direto do Supabase, crie policies por organização (não existe organization_id ainda).
alter table talhoes          enable row level security;
alter table sessoes_trabalho enable row level security;
alter table telemetria       enable row level security;
alter table metricas_sessao  enable row level security;
alter table alertas          enable row level security;
