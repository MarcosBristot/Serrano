-- M1 · Cadastro: fazendas, talhões, máquinas, implementos, operadores.

create table public.fazendas (
    id uuid primary key default gen_random_uuid(),
    organizacao_id uuid not null references public.organizacoes (id) on delete cascade,
    nome text not null,
    cliente_nome text,
    external_guid text,
    criado_em timestamptz not null default now(),
    atualizado_em timestamptz not null default now(),
    unique (organizacao_id, external_guid)
);
create index fazendas_org_idx on public.fazendas (organizacao_id, nome);
create trigger fazendas_atualizado_em before update on public.fazendas
    for each row execute function interno.tocar_atualizado_em();

create table public.talhoes (
    id uuid primary key default gen_random_uuid(),
    organizacao_id uuid not null references public.organizacoes (id) on delete cascade,
    fazenda_id uuid references public.fazendas (id) on delete set null,
    nome text not null,
    external_guid text,
    geometria extensions.geometry(MultiPolygon, 4326),
    area_ha numeric(12, 4),
    origem_contorno text check (origem_contorno in ('monitor', 'upload', 'desenho')),
    ativo boolean not null default true,
    criado_em timestamptz not null default now(),
    atualizado_em timestamptz not null default now(),
    unique (organizacao_id, external_guid),
    check (geometria is null or extensions.st_isvalid(geometria))
);
create index talhoes_org_idx on public.talhoes (organizacao_id, fazenda_id);
create index talhoes_geom_idx on public.talhoes using gist (geometria);

create or replace function interno.talhoes_calcular_area() returns trigger
language plpgsql
set search_path = ''
as $$
begin
    new.area_ha := case
        when new.geometria is null then null
        else round((extensions.st_area(new.geometria::extensions.geography) / 10000)::numeric, 4)
    end;
    new.atualizado_em := now();
    return new;
end
$$;
create trigger talhoes_area before insert or update on public.talhoes
    for each row execute function interno.talhoes_calcular_area();

create table public.maquinas (
    id uuid primary key default gen_random_uuid(),
    organizacao_id uuid not null references public.organizacoes (id) on delete cascade,
    serial text not null,
    fabricante text,
    modelo text,
    tecnologia text,
    apelido text,
    ativa boolean not null default true,
    primeira_atividade timestamptz,
    ultima_atividade timestamptz,
    criado_em timestamptz not null default now(),
    atualizado_em timestamptz not null default now(),
    unique (organizacao_id, serial)
);
create index maquinas_org_ativa_idx on public.maquinas (organizacao_id) where ativa;
create trigger maquinas_atualizado_em before update on public.maquinas
    for each row execute function interno.tocar_atualizado_em();

create table public.implementos (
    id uuid primary key default gen_random_uuid(),
    organizacao_id uuid not null references public.organizacoes (id) on delete cascade,
    nome text not null,
    largura_m numeric(8, 3) check (largura_m > 0 and largura_m < 100),
    external_guid text,
    criado_em timestamptz not null default now(),
    atualizado_em timestamptz not null default now(),
    unique (organizacao_id, external_guid)
);
create index implementos_org_idx on public.implementos (organizacao_id);
create trigger implementos_atualizado_em before update on public.implementos
    for each row execute function interno.tocar_atualizado_em();

-- Sem CPF: LGPD, só o necessário.
create table public.operadores (
    id uuid primary key default gen_random_uuid(),
    organizacao_id uuid not null references public.organizacoes (id) on delete cascade,
    nome text not null,
    external_guid text,
    ativo boolean not null default true,
    criado_em timestamptz not null default now(),
    atualizado_em timestamptz not null default now(),
    unique (organizacao_id, external_guid)
);
create index operadores_org_idx on public.operadores (organizacao_id);
create trigger operadores_atualizado_em before update on public.operadores
    for each row execute function interno.tocar_atualizado_em();
