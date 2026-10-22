-- M1 · Operação: preço do combustível, exportações, notificações e auditoria.

create table public.preco_combustivel (
    id uuid primary key default gen_random_uuid(),
    organizacao_id uuid not null references public.organizacoes (id) on delete cascade,
    tipo text not null check (tipo in ('S10', 'S500')),
    preco_rs_l numeric(10, 4) not null check (preco_rs_l > 0),
    valido_de date not null,
    valido_ate date,
    fonte text not null check (fonte in ('manual', 'anp')),
    criado_em timestamptz not null default now(),
    check (valido_ate is null or valido_ate > valido_de),
    constraint preco_combustivel_sem_sobreposicao exclude using gist (
        organizacao_id with =,
        tipo with =,
        daterange(valido_de, valido_ate, '[)') with &&
    )
);

create table public.exportacoes (
    id uuid primary key default gen_random_uuid(),
    organizacao_id uuid not null references public.organizacoes (id) on delete cascade,
    solicitado_por uuid references auth.users (id) on delete set null,
    formato text not null check (formato in ('csv', 'xlsx')),
    filtros jsonb not null default '{}',
    status text not null default 'pendente'
        check (status in ('pendente', 'executando', 'concluida', 'erro', 'expirada')),
    caminho_storage text,
    linhas bigint,
    expira_em timestamptz,
    erro text,
    criado_em timestamptz not null default now(),
    atualizado_em timestamptz not null default now()
);
create index exportacoes_org_idx on public.exportacoes (organizacao_id, criado_em desc);
create trigger exportacoes_atualizado_em before update on public.exportacoes
    for each row execute function interno.tocar_atualizado_em();

create table public.destinos_notificacao (
    id uuid primary key default gen_random_uuid(),
    organizacao_id uuid not null references public.organizacoes (id) on delete cascade,
    tipo text not null check (tipo in ('email', 'webhook', 'whatsapp')),
    destino text not null,
    segredo_cifrado text,
    severidade_minima text not null default 'atencao'
        check (severidade_minima in ('info', 'atencao', 'alto')),
    ativo boolean not null default true,
    criado_em timestamptz not null default now(),
    atualizado_em timestamptz not null default now()
);
create index destinos_notificacao_org_idx on public.destinos_notificacao (organizacao_id);
create trigger destinos_notificacao_atualizado_em before update on public.destinos_notificacao
    for each row execute function interno.tocar_atualizado_em();

-- Outbox: o alerta e a notificação nascem na mesma transação.
create table interno.notificacoes (
    id uuid primary key default gen_random_uuid(),
    organizacao_id uuid not null references public.organizacoes (id) on delete cascade,
    alerta_id uuid not null references public.alertas (id) on delete cascade,
    destino_id uuid not null references public.destinos_notificacao (id) on delete cascade,
    status text not null default 'pendente'
        check (status in ('pendente', 'enviada', 'erro', 'morta')),
    tentativas smallint not null default 0,
    proxima_tentativa timestamptz not null default now(),
    enviado_em timestamptz,
    erro text,
    criado_em timestamptz not null default now(),
    unique (alerta_id, destino_id)
);
create index notificacoes_fila_idx on interno.notificacoes (proxima_tentativa)
    where status = 'pendente';

-- Auditoria: "dados" nunca leva PII (e-mail, nome de produtor, coordenadas).
create table interno.auditoria (
    id bigint generated always as identity primary key,
    organizacao_id uuid references public.organizacoes (id) on delete set null,
    ator_id uuid,
    ator_tipo text not null check (ator_tipo in ('usuario', 'chave_api', 'sistema')),
    acao text not null,
    recurso_tipo text,
    recurso_id text,
    dados jsonb not null default '{}',
    ip inet,
    request_id text,
    criado_em timestamptz not null default now()
);
create index auditoria_org_idx on interno.auditoria (organizacao_id, criado_em desc);
