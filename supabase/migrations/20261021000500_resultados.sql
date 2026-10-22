-- M1 · Resultados (reprocessáveis): execuções de regras, métricas, coberturas, alertas.

create table public.execucoes_regras (
    id uuid primary key default gen_random_uuid(),
    organizacao_id uuid not null references public.organizacoes (id) on delete cascade,
    versao_regras text not null,
    config jsonb not null,
    config_hash text not null,
    escopo jsonb not null default '{}',
    iniciada_em timestamptz not null default now(),
    concluida_em timestamptz
);
create index execucoes_regras_org_idx on public.execucoes_regras (organizacao_id, iniciada_em desc);

create table public.metricas_sessao (
    sessao_id uuid not null references public.sessoes_trabalho (id) on delete cascade,
    versao_regras text not null,
    organizacao_id uuid not null references public.organizacoes (id) on delete cascade,
    execucao_id uuid references public.execucoes_regras (id) on delete set null,
    vigente boolean not null default true,
    duracao_h double precision,
    motor_h double precision,
    trabalho_h double precision,
    ocioso_h double precision,
    ociosidade_pct double precision,
    delta_horimetro_h double precision,
    litros_integral double precision,
    litros_contador double precision,
    litros_trabalho double precision,
    litros_ocioso double precision,
    lph_trabalho double precision,
    lph_ocioso double precision,
    distancia_trabalho_km double precision,
    velocidade_media double precision,
    area_cobertura_ha double precision,
    area_estimada_ha double precision,
    sobreposicao_pct double precision,
    area_metodo text,
    ha_h double precision,
    l_ha double precision,
    cobertura_gps double precision,
    criado_em timestamptz not null default now(),
    primary key (sessao_id, versao_regras)
);
create index metricas_sessao_org_idx on public.metricas_sessao (organizacao_id) where vigente;
create unique index metricas_sessao_vigente_uidx on public.metricas_sessao (sessao_id) where vigente;

create table public.coberturas_sessao (
    sessao_id uuid not null references public.sessoes_trabalho (id) on delete cascade,
    versao_regras text not null,
    organizacao_id uuid not null references public.organizacoes (id) on delete cascade,
    geometria extensions.geometry(MultiPolygon, 4326) not null,
    primary key (sessao_id, versao_regras)
);
create index coberturas_sessao_org_idx on public.coberturas_sessao (organizacao_id);

create table public.metricas_diarias (
    id uuid primary key default gen_random_uuid(),
    organizacao_id uuid not null references public.organizacoes (id) on delete cascade,
    dia date not null,  -- dia local (fuso da organização)
    maquina_id uuid not null references public.maquinas (id) on delete cascade,
    talhao_id uuid references public.talhoes (id) on delete cascade,
    operacao text,
    versao_regras text not null,
    sessoes integer not null default 0,
    motor_h double precision not null default 0,
    trabalho_h double precision not null default 0,
    ocioso_h double precision not null default 0,
    litros double precision not null default 0,
    litros_trabalho double precision not null default 0,
    litros_ocioso double precision not null default 0,
    area_ha double precision not null default 0,
    distancia_km double precision not null default 0,
    atualizado_em timestamptz not null default now(),
    unique nulls not distinct (organizacao_id, dia, maquina_id, talhao_id, operacao, versao_regras)
);
create index metricas_diarias_org_dia_idx on public.metricas_diarias (organizacao_id, dia);

create table public.alertas (
    id uuid primary key default gen_random_uuid(),
    organizacao_id uuid not null references public.organizacoes (id) on delete cascade,
    sessao_id uuid references public.sessoes_trabalho (id) on delete cascade,
    maquina_id uuid references public.maquinas (id) on delete cascade,
    talhao_id uuid references public.talhoes (id) on delete set null,
    tipo text not null,
    severidade text not null check (severidade in ('info', 'atencao', 'alto')),
    versao_regras text not null,
    execucao_id uuid references public.execucoes_regras (id) on delete set null,
    inicio timestamptz,
    fim timestamptz,
    valor double precision,
    limiar double precision,
    mensagem text not null,
    detalhes jsonb not null default '{}',
    impressao_digital text not null,
    status text not null default 'aberto'
        check (status in ('aberto', 'reconhecido', 'resolvido', 'invalidado')),
    reconhecido_por uuid references auth.users (id) on delete set null,
    reconhecido_em timestamptz,
    resolvido_por uuid references auth.users (id) on delete set null,
    resolvido_em timestamptz,
    criado_em timestamptz not null default now(),
    atualizado_em timestamptz not null default now(),
    unique (organizacao_id, impressao_digital)
);
create index alertas_org_status_idx on public.alertas (organizacao_id, status, criado_em desc);
create index alertas_sessao_idx on public.alertas (sessao_id);
create index alertas_maquina_idx on public.alertas (maquina_id, inicio desc);
create trigger alertas_atualizado_em before update on public.alertas
    for each row execute function interno.tocar_atualizado_em();

create table public.alertas_comentarios (
    id uuid primary key default gen_random_uuid(),
    alerta_id uuid not null references public.alertas (id) on delete cascade,
    organizacao_id uuid not null references public.organizacoes (id) on delete cascade,
    autor_id uuid references auth.users (id) on delete set null,
    texto text not null check (length(texto) between 1 and 4000),
    criado_em timestamptz not null default now()
);
create index alertas_comentarios_alerta_idx on public.alertas_comentarios (alerta_id, criado_em);
create index alertas_comentarios_org_idx on public.alertas_comentarios (organizacao_id);

create table public.config_regras (
    organizacao_id uuid primary key references public.organizacoes (id) on delete cascade,
    versao text not null,
    config jsonb not null,
    atualizado_por uuid references auth.users (id) on delete set null,
    atualizado_em timestamptz not null default now()
);
