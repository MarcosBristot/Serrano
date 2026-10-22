-- M7 · Equipe: e-mail dos membros (auth.users não é acessível ao papel da aplicação).

create or replace function interno.emails_dos_membros()
returns table (usuario_id uuid, email text)
language sql stable security definer
set search_path = ''
as $$
    select u.id, u.email::text
    from auth.users u
    join public.membros m on m.usuario_id = u.id
    where m.organizacao_id = public.app_org_atual()
$$;
revoke all on function interno.emails_dos_membros() from public;
grant execute on function interno.emails_dos_membros() to campero_backend, service_role;

create index if not exists auditoria_org_id_idx on interno.auditoria (organizacao_id, id desc);
