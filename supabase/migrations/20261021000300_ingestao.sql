-- M1 · Ingestão: lotes, arquivos brutos (dedupe por sha256) e fila de jobs.

create table public.lotes_upload (
    id uuid primary key default gen_random_uuid(),
    organizacao_id uuid not null references public.organizacoes (id) on delete cascade,
    criado_por uuid references auth.users (id) on delete set null,
    origem text not null check (origem in ('api', 'zip', 'cli')),
    criado_em timestamptz not null default now()
);
create index lotes_upload_org_idx on public.lotes_upload (organizacao_id, criado_em desc);

create table public.arquivos_brutos (
    id uuid primary key default gen_random_uuid(),
    organizacao_id uuid not null references public.organizacoes (id) on delete cascade,
    lote_id uuid references public.lotes_upload (id) on delete set null,
    arquivo_pai_id uuid references public.arquivos_brutos (id) on delete cascade,
    sha256 text not null check (sha256 ~ '^[0-9a-f]{64}$'),
    nome_original text not null,  -- só exibição; nunca vira caminho
    caminho_storage text not null,
    tamanho_bytes bigint not null check (tamanho_bytes >= 0),
    tipo text not null check (tipo in ('jdl', 'zip', 'masterdata', 'gjson')),
    marca text,
    tecnologia text,
    status text not null default 'recebido' check (status in (
        'recebido', 'processando', 'processado', 'vazio', 'rejeitado', 'erro', 'bloqueado_plano'
    )),
    motivo text,
    criado_em timestamptz not null default now(),
    atualizado_em timestamptz not null default now(),
    unique (organizacao_id, sha256)
);
create index arquivos_brutos_lote_idx on public.arquivos_brutos (lote_id);
create index arquivos_brutos_status_idx on public.arquivos_brutos (organizacao_id, status);
create index arquivos_brutos_pai_idx on public.arquivos_brutos (arquivo_pai_id);
create trigger arquivos_brutos_atualizado_em before update on public.arquivos_brutos
    for each row execute function interno.tocar_atualizado_em();

-- Fila durável (FOR UPDATE SKIP LOCKED, lease renovado por heartbeat). Ver ADR 0004.
create table interno.jobs (
    id uuid primary key default gen_random_uuid(),
    organizacao_id uuid not null references public.organizacoes (id) on delete cascade,
    lote_id uuid references public.lotes_upload (id) on delete set null,
    tipo text not null,
    payload jsonb not null default '{}',
    status text not null default 'pendente' check (status in (
        'pendente', 'executando', 'concluido', 'erro', 'morto', 'cancelado'
    )),
    prioridade smallint not null default 100,
    tentativas smallint not null default 0,
    max_tentativas smallint not null default 5,
    proxima_tentativa timestamptz not null default now(),
    locked_by text,
    locked_at timestamptz,
    lease_ate timestamptz,
    cancelamento_solicitado boolean not null default false,
    progresso jsonb not null default '{}',
    erro text,
    chave_idempotencia text,
    criado_em timestamptz not null default now(),
    atualizado_em timestamptz not null default now(),
    unique (organizacao_id, tipo, chave_idempotencia)
);
create index jobs_fila_idx on interno.jobs (status, proxima_tentativa, prioridade)
    where status = 'pendente';
create index jobs_lease_idx on interno.jobs (lease_ate) where status = 'executando';
create index jobs_lote_idx on interno.jobs (lote_id);
create trigger jobs_atualizado_em before update on interno.jobs
    for each row execute function interno.tocar_atualizado_em();

-- Status agregado do lote (security_invoker: respeita a RLS de quem consulta).
create view public.lotes_upload_status with (security_invoker = true) as
select
    l.id,
    l.organizacao_id,
    l.origem,
    l.criado_em,
    count(a.id) as arquivos,
    count(a.id) filter (where a.status = 'processado') as processados,
    count(a.id) filter (where a.status = 'vazio') as vazios,
    count(a.id) filter (where a.status in ('erro', 'rejeitado')) as com_erro,
    count(a.id) filter (where a.status = 'bloqueado_plano') as bloqueados,
    count(a.id) filter (where a.status in ('recebido', 'processando')) as pendentes
from public.lotes_upload l
left join public.arquivos_brutos a on a.lote_id = l.id
group by l.id;
