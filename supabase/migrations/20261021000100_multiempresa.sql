-- M1 · Multiempresa: organizações, planos, assinaturas, membros, convites, chaves de API.

create table public.organizacoes (
    id uuid primary key default gen_random_uuid(),
    nome text not null check (length(nome) between 2 and 120),
    slug text not null unique check (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    fuso text not null default 'America/Sao_Paulo',
    inicio_safra_mes smallint not null default 7 check (inicio_safra_mes between 1 and 12),
    criado_em timestamptz not null default now()
);

create table public.planos (
    codigo text primary key,
    nome text not null,
    max_maquinas integer not null check (max_maquinas > 0),
    preco_mensal_centavos integer not null check (preco_mensal_centavos >= 0)
);

insert into public.planos (codigo, nome, max_maquinas, preco_mensal_centavos)
values ('basico', 'Básico', 5, 40000);

create table public.assinaturas (
    id uuid primary key default gen_random_uuid(),
    organizacao_id uuid not null unique references public.organizacoes (id) on delete cascade,
    plano_codigo text not null references public.planos (codigo),
    status text not null check (status in ('trial', 'ativa', 'suspensa', 'cancelada')),
    inicio timestamptz not null default now(),
    fim timestamptz,
    max_maquinas_override integer check (max_maquinas_override > 0),
    atualizado_em timestamptz not null default now()
);
create trigger assinaturas_atualizado_em before update on public.assinaturas
    for each row execute function interno.tocar_atualizado_em();

create table public.membros (
    organizacao_id uuid not null references public.organizacoes (id) on delete cascade,
    usuario_id uuid not null references auth.users (id) on delete cascade,
    papel text not null check (papel in ('owner', 'gestor', 'leitor')),
    criado_em timestamptz not null default now(),
    primary key (organizacao_id, usuario_id)
);
create index membros_usuario_idx on public.membros (usuario_id);

create table public.convites (
    id uuid primary key default gen_random_uuid(),
    organizacao_id uuid not null references public.organizacoes (id) on delete cascade,
    email text not null,
    papel text not null check (papel in ('gestor', 'leitor')),
    token_hash text not null unique,
    expira_em timestamptz not null,
    aceito_em timestamptz,
    criado_por uuid references auth.users (id) on delete set null,
    criado_em timestamptz not null default now()
);
create index convites_org_idx on public.convites (organizacao_id);

create table interno.chaves_api (
    id uuid primary key default gen_random_uuid(),
    organizacao_id uuid not null references public.organizacoes (id) on delete cascade,
    nome text not null,
    prefixo text not null unique,
    hash text not null unique,
    escopos text[] not null default '{}',
    criado_por uuid references auth.users (id) on delete set null,
    criado_em timestamptz not null default now(),
    ultimo_uso_em timestamptz,
    revogada_em timestamptz
);
create index chaves_api_org_idx on interno.chaves_api (organizacao_id);

-- Organizações do usuário do JWT (frontend). SECURITY DEFINER: lê membros sem recursão de RLS.
create or replace function public.orgs_do_usuario() returns setof uuid
language sql stable security definer
set search_path = ''
as $$
    select m.organizacao_id from public.membros m where m.usuario_id = (select auth.uid())
$$;

-- Vínculos de um usuário para o backend resolver a org ativa antes de fixá-la.
create or replace function interno.vinculos_do_usuario(p_usuario_id uuid)
returns table (organizacao_id uuid, nome text, slug text, papel text)
language sql stable security definer
set search_path = ''
as $$
    select o.id, o.nome, o.slug, m.papel
    from public.membros m
    join public.organizacoes o on o.id = m.organizacao_id
    where m.usuario_id = p_usuario_id
$$;
