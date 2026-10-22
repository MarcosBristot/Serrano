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

-- M8 · Exportações vencidas (o worker limpa o Storage e marca 'expirada').
create or replace function interno.exportacoes_vencidas(p_limite integer)
returns table (id uuid, organizacao_id uuid, caminho_storage text)
language sql stable security definer
set search_path = ''
as $$
    select e.id, e.organizacao_id, e.caminho_storage from public.exportacoes e
    where e.status = 'concluida' and e.expira_em < now()
    order by e.expira_em limit p_limite
$$;
revoke all on function interno.exportacoes_vencidas(integer) from public;
grant execute on function interno.exportacoes_vencidas(integer) to campero_backend, service_role;
