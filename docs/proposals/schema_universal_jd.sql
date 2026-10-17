-- RASCUNHO de referência (NÃO é migration). O schema oficial é o da branch
-- feat/inserção-e-tratamento-de-dados-inicial (Alembic); ver docs/adr/0002 para as diferenças necessárias.
-- Estágios: raw -> telemetry (limpo, universal) -> sessões/métricas/alertas (resultados).

create extension if not exists postgis;

create table organizations (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  created_at timestamptz not null default now()
);

create table machines (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id),
  manufacturer text not null,
  serial text not null,
  model_hint text,
  display_serial text,
  unique (organization_id, manufacturer, serial)
);

create table fields (                       -- talhões
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id),
  external_guid text,                       -- GUID do Gen4 (MasterData), quando houver
  name text not null,
  boundary geography(MultiPolygon, 4326),   -- contorno (SpatialFiles/Boundary*.gjson)
  area_ha numeric generated always as (ST_Area(boundary) / 10000.0) stored,
  unique (organization_id, external_guid)
);

create table raw_files (                    -- etapa 1: bruto imutável (o arquivo fica no Storage)
  sha256 text primary key,
  organization_id uuid not null references organizations(id),
  original_name text not null,
  storage_path text not null,
  size_bytes bigint not null,
  uploaded_at timestamptz not null default now()
);

create table work_sessions (                -- 1 arquivo = 1 sessão
  sha256 text primary key references raw_files(sha256),
  organization_id uuid not null references organizations(id),
  machine_id uuid references machines(id),
  field_id uuid references fields(id),
  adapter text not null,
  adapter_version text not null,
  operation text,
  implement_name text,
  implement_width_m numeric,
  started_at timestamptz not null,
  ended_at timestamptz not null,
  quality jsonb not null default '{}'::jsonb
);

create table telemetry_samples (            -- etapa 3: limpo, 1 Hz, agnóstico de fabricante
  session_sha256 text not null references work_sessions(sha256) on delete cascade,
  ts timestamptz not null,
  geom geography(Point, 4326),
  gps_valid boolean not null,
  speed_kmh real, speed_alt_kmh real,
  engine_rpm real, engine_load_pct real,
  fuel_rate_lph real, fuel_total_l real,
  fuel_level_l real,                        -- NULL em John Deere Gen4 (sem sensor de nível)
  engine_hours double precision,
  engine_on boolean not null,
  primary key (session_sha256, ts)
) partition by range (ts);
create index telemetry_geom_gix on telemetry_samples using gist (geom);

-- Resultados (etapa 5): separados do dado limpo; reprocessáveis por versão de regras.
create table rule_runs (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id),
  rules_version text not null,
  config jsonb not null,
  created_at timestamptz not null default now()
);

create table session_metrics (
  rule_run_id uuid not null references rule_runs(id) on delete cascade,
  session_sha256 text not null references work_sessions(sha256) on delete cascade,
  engine_on_h real, work_h real, idle_h real, engine_hours_delta real,
  fuel_integral_l real, fuel_counter_l real, fuel_work_l real, fuel_idle_l real,
  lph_work real, lph_idle real, work_distance_km real, avg_speed_work_kmh real,
  worked_area_ha real, ha_per_h real, l_per_ha real, l_per_ha_work real,
  gps_coverage real,
  primary key (rule_run_id, session_sha256)
);

create table alerts (
  id uuid primary key default gen_random_uuid(),
  rule_run_id uuid not null references rule_runs(id) on delete cascade,
  session_sha256 text not null references work_sessions(sha256) on delete cascade,
  kind text not null,
  severity text not null check (severity in ('info','atencao','alto')),
  start_utc timestamptz, end_utc timestamptz,
  value double precision,
  message text not null,
  details jsonb not null default '{}'::jsonb
);
create index alerts_run_kind on alerts (rule_run_id, kind);
