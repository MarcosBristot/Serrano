-- M1 · Fundação: extensões, schema interno, papel da aplicação e funções de RLS.
--
-- Papel campero_backend: LOGIN, SEM BYPASSRLS, sem DDL. A senha NÃO fica aqui:
--   alter role campero_backend password '<gerada>';   (painel/SQL editor, uma vez por ambiente)
-- No pooler do Supabase o usuário é "campero_backend.<project_ref>".

create extension if not exists postgis with schema extensions;
create extension if not exists btree_gist with schema extensions;
create extension if not exists pgcrypto with schema extensions;

do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'campero_backend') then
        create role campero_backend login noinherit nobypassrls nocreatedb nocreaterole;
    end if;
end
$$;

-- Fecha o que o Supabase concede por padrão em objetos novos criados por postgres.
alter default privileges in schema public revoke all on tables from anon, authenticated, public;
alter default privileges in schema public revoke all on sequences from anon, authenticated, public;
alter default privileges in schema public revoke all on functions from anon, authenticated, public;
alter default privileges revoke execute on functions from public;

-- Schema não exposto ao Data API: jobs, chaves de API, auditoria, outbox.
create schema if not exists interno;
revoke all on schema interno from public, anon, authenticated;
grant usage on schema interno to campero_backend, service_role;

grant usage on schema public to campero_backend;
grant usage on schema extensions to campero_backend;
alter role campero_backend set search_path = public, extensions;
alter role campero_backend set statement_timeout = '60s';
alter role campero_backend set idle_in_transaction_session_timeout = '120s';

-- Organização ativa da transação do backend (set_config('app.organizacao_id', ..., true)).
create or replace function public.app_org_atual() returns uuid
language sql stable
set search_path = ''
as $$
    select nullif(current_setting('app.organizacao_id', true), '')::uuid
$$;

-- updated_at genérico
create or replace function interno.tocar_atualizado_em() returns trigger
language plpgsql
set search_path = ''
as $$
begin
    new.atualizado_em := now();
    return new;
end
$$;
