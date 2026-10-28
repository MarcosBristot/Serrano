-- LGPD: registro de aceite dos documentos legais, consentimento no formulário do site
-- e retenção limitada dos pedidos de demonstração.

-- Quem aceitou o quê, em qual versão (Termos de Serviço + Política de Privacidade).
create table interno.aceites (
    id          uuid primary key default gen_random_uuid(),
    usuario_id  uuid not null,
    documento   text not null check (documento in ('termos', 'privacidade')),
    versao      text not null check (char_length(versao) between 1 and 40),
    ip_hash     text,
    aceito_em   timestamptz not null default now()
);
create index aceites_usuario_idx on interno.aceites (usuario_id, documento, aceito_em desc);

alter table interno.aceites enable row level security;
create policy aceites_backend on interno.aceites
    for all to campero_backend using (true) with check (true);
grant select, insert on interno.aceites to campero_backend, service_role;  -- só acrescenta

-- Formulário do site: versão da política exibida e opt-in (desmarcado por padrão) de novidades.
alter table interno.contatos
    add column politica_versao text check (char_length(politica_versao) <= 40),
    add column aceita_novidades boolean not null default false;

-- Retenção: pedidos de demonstração não convertidos são apagados após o prazo.
grant delete on interno.contatos to campero_backend, service_role;
