-- Marco Civil (art. 15): registros de acesso à aplicação guardados por 6 meses, em sigilo.
-- LGPD (art. 18): exportação dos dados do titular e exclusão da conta com carência.

-- ------------------------------------------------------------------ registros de acesso
create table interno.registros_acesso (
    id              bigint generated always as identity primary key,
    ocorrido_em     timestamptz not null,
    ip              inet,
    usuario_id      uuid,
    organizacao_id  uuid,
    metodo          text not null,
    rota            text not null, -- modelo da rota (/api/v1/sessions/{id}), sem IDs nem query string
    status          smallint not null,
    request_id      text
);
create index registros_acesso_tempo_idx on interno.registros_acesso (ocorrido_em);
create index registros_acesso_usuario_idx on interno.registros_acesso (usuario_id, ocorrido_em desc)
    where usuario_id is not null;

alter table interno.registros_acesso enable row level security;
create policy registros_acesso_backend on interno.registros_acesso
    for all to campero_backend using (true) with check (true);
grant select, insert, delete on interno.registros_acesso to campero_backend, service_role;

-- ------------------------------------------------------------------ pedidos de exclusão
create table interno.solicitacoes_exclusao (
    id              uuid primary key default gen_random_uuid(),
    usuario_id      uuid not null,
    email           text,
    organizacoes    uuid[] not null default '{}', -- organizações em que o titular é o único membro
    status          text not null default 'agendada'
                    check (status in ('agendada', 'cancelada', 'concluida', 'erro')),
    agendada_para   timestamptz not null,
    criado_em       timestamptz not null default now(),
    concluida_em    timestamptz,
    erro            text
);
create unique index solicitacoes_exclusao_ativa_idx on interno.solicitacoes_exclusao (usuario_id)
    where status = 'agendada';
create index solicitacoes_exclusao_vencidas_idx on interno.solicitacoes_exclusao (agendada_para)
    where status = 'agendada';

alter table interno.solicitacoes_exclusao enable row level security;
create policy solicitacoes_exclusao_backend on interno.solicitacoes_exclusao
    for all to campero_backend using (true) with check (true);
grant select, insert, update on interno.solicitacoes_exclusao to campero_backend, service_role;

-- ------------------------------------------------------------------ exportação (portabilidade)
-- SECURITY DEFINER: junta dados do titular de todas as organizações; só lê o que é dele.
create or replace function interno.dados_do_titular(p_usuario uuid)
returns jsonb
language sql stable security definer
set search_path = ''
as $$
    select jsonb_build_object(
        'gerado_em', now(),
        'conta', (
            select jsonb_build_object('usuario_id', u.id, 'email', u.email, 'criado_em', u.created_at)
            from auth.users u where u.id = p_usuario
        ),
        'organizacoes', coalesce((
            select jsonb_agg(jsonb_build_object(
                'organizacao_id', o.id, 'nome', o.nome, 'papel', m.papel, 'membro_desde', m.criado_em
            ) order by o.nome)
            from public.membros m join public.organizacoes o on o.id = m.organizacao_id
            where m.usuario_id = p_usuario
        ), '[]'::jsonb),
        'aceites', coalesce((
            select jsonb_agg(jsonb_build_object(
                'documento', a.documento, 'versao', a.versao, 'aceito_em', a.aceito_em
            ) order by a.aceito_em)
            from interno.aceites a where a.usuario_id = p_usuario
        ), '[]'::jsonb),
        'comentarios_em_alertas', coalesce((
            select jsonb_agg(jsonb_build_object(
                'organizacao_id', c.organizacao_id, 'alerta_id', c.alerta_id,
                'texto', c.texto, 'criado_em', c.criado_em
            ) order by c.criado_em)
            from public.alertas_comentarios c where c.autor_id = p_usuario
        ), '[]'::jsonb),
        'acoes_registradas', coalesce((
            select jsonb_agg(x.j order by x.quando desc) from (
                select a.criado_em as quando, jsonb_build_object(
                    'quando', a.criado_em, 'organizacao_id', a.organizacao_id, 'acao', a.acao,
                    'recurso', a.recurso_tipo, 'ip', host(a.ip)
                ) as j
                from interno.auditoria a
                where a.ator_id = p_usuario and a.ator_tipo = 'usuario'
                order by a.criado_em desc limit 5000
            ) x
        ), '[]'::jsonb),
        'acessos_ultimos_6_meses', coalesce((
            select jsonb_agg(x.j order by x.quando desc) from (
                select r.ocorrido_em as quando, jsonb_build_object(
                    'quando', r.ocorrido_em, 'ip', host(r.ip), 'metodo', r.metodo, 'rota', r.rota,
                    'status', r.status
                ) as j
                from interno.registros_acesso r
                where r.usuario_id = p_usuario and r.ocorrido_em > now() - interval '6 months'
                order by r.ocorrido_em desc limit 5000
            ) x
        ), '[]'::jsonb),
        'pedido_de_exclusao', (
            select jsonb_build_object('status', s.status, 'agendada_para', s.agendada_para)
            from interno.solicitacoes_exclusao s where s.usuario_id = p_usuario
            order by s.criado_em desc limit 1
        )
    )
$$;

-- O que acontece com cada organização se o titular excluir a conta.
create or replace function interno.impacto_exclusao(p_usuario uuid)
returns table (organizacao_id uuid, nome text, papel text, outros_membros integer, outros_donos integer)
language sql stable security definer
set search_path = ''
as $$
    select o.id, o.nome, m.papel,
        (select count(*)::int from public.membros x
            where x.organizacao_id = o.id and x.usuario_id <> p_usuario),
        (select count(*)::int from public.membros x
            where x.organizacao_id = o.id and x.usuario_id <> p_usuario and x.papel = 'owner')
    from public.membros m join public.organizacoes o on o.id = m.organizacao_id
    where m.usuario_id = p_usuario
    order by o.nome
$$;

-- Apaga a organização (cascata em todo o banco) e devolve os arquivos a remover do Storage.
create or replace function interno.excluir_organizacao(p_org uuid)
returns table (bucket text, caminho text)
language plpgsql security definer
set search_path = ''
as $$
begin
    return query
        select 'brutos'::text, a.caminho_storage from public.arquivos_brutos a where a.organizacao_id = p_org
        union all
        select 'limpos'::text, p_org::text || '/' || a.sha256 || '.parquet'
            from public.arquivos_brutos a where a.organizacao_id = p_org
        union all
        select 'exportacoes'::text, e.caminho_storage from public.exportacoes e
            where e.organizacao_id = p_org and e.caminho_storage is not null;
    delete from public.organizacoes where id = p_org;
end
$$;

-- Apaga a conta (vínculos caem em cascata; autoria em alertas/comentários vira nula) e
-- pedidos de demonstração com o mesmo e-mail. Aceites e registros de acesso ficam pelo
-- prazo legal (prova e Marco Civil).
create or replace function interno.excluir_titular(p_usuario uuid, p_email text)
returns void
language plpgsql security definer
set search_path = ''
as $$
begin
    if p_email is not null then
        delete from interno.contatos where lower(email) = lower(p_email);
    end if;
    delete from auth.users where id = p_usuario;
end
$$;

revoke all on function interno.dados_do_titular(uuid) from public;
revoke all on function interno.impacto_exclusao(uuid) from public;
revoke all on function interno.excluir_organizacao(uuid) from public;
revoke all on function interno.excluir_titular(uuid, text) from public;
grant execute on function interno.dados_do_titular(uuid) to campero_backend, service_role;
grant execute on function interno.impacto_exclusao(uuid) to campero_backend, service_role;
grant execute on function interno.excluir_organizacao(uuid) to campero_backend, service_role;
grant execute on function interno.excluir_titular(uuid, text) to campero_backend, service_role;
