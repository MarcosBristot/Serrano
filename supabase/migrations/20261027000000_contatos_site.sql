-- Site institucional: pedidos de demonstração (público, sem login).
-- Fica em `interno`: não pertence a nenhuma organização e não aparece na Data API.

create table interno.contatos (
    id          uuid primary key default gen_random_uuid(),
    nome        text not null check (char_length(nome) between 2 and 120),
    email       text not null check (char_length(email) <= 254),
    telefone    text check (char_length(telefone) <= 40),
    fazenda     text check (char_length(fazenda) <= 160),
    hectares    integer check (hectares between 0 and 10000000),
    maquinas    integer check (maquinas between 0 and 100000),
    mensagem    text check (char_length(mensagem) <= 2000),
    origem      text not null default 'site' check (char_length(origem) <= 60),
    ip_hash     text,
    status      text not null default 'novo' check (status in ('novo', 'contatado', 'descartado')),
    criado_em   timestamptz not null default now()
);
create index contatos_criado_idx on interno.contatos (criado_em desc);

alter table interno.contatos enable row level security;
create policy contatos_backend on interno.contatos
    for all to campero_backend using (true) with check (true);

grant select, insert, update on interno.contatos to campero_backend, service_role;
