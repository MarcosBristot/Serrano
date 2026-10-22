-- M1 · RLS e privilégios.
--
-- Quem acessa o quê:
--   anon            nada.
--   authenticated   (frontend via Data API) SÓ SELECT, e só nas orgs de que é membro.
--   campero_backend (API/worker, conexão direta) DML filtrado por app.organizacao_id.
--   service_role    (scripts administrativos via Data API) DML; tem BYPASSRLS no Supabase.
-- Toda escrita de usuário passa pela API.

-- 1) Começa do zero: nada para anon/authenticated/public em public e interno.
revoke all on all tables in schema public from anon, authenticated, public;
revoke all on all sequences in schema public from anon, authenticated, public;
revoke all on all functions in schema public from anon, authenticated, public;
revoke all on all tables in schema interno from anon, authenticated, public;
revoke all on all functions in schema interno from anon, authenticated, public;

-- 2) Funções usadas nas policies.
grant execute on function public.app_org_atual() to campero_backend, service_role;
grant execute on function public.orgs_do_usuario() to authenticated, service_role;
grant execute on function interno.vinculos_do_usuario(uuid) to campero_backend, service_role;
grant execute on function interno.garantir_particao(timestamptz) to campero_backend, service_role;

-- 3) Tabelas por organização: RLS + policies geradas.
do $$
declare
    t text;
    -- Lidas pelo frontend (authenticated). Fora da lista: convites (token),
    -- destinos_notificacao (segredo) e telemetria (volume: só pela API).
    leitura_frontend text[] := array[
        'assinaturas', 'membros', 'fazendas', 'talhoes', 'maquinas', 'implementos',
        'operadores', 'lotes_upload', 'arquivos_brutos', 'sessoes_trabalho',
        'execucoes_regras', 'metricas_sessao', 'coberturas_sessao', 'metricas_diarias',
        'alertas', 'alertas_comentarios', 'config_regras', 'preco_combustivel', 'exportacoes'
    ];
    por_org text[] := leitura_frontend || array['convites', 'destinos_notificacao', 'telemetria'];
begin
    foreach t in array por_org loop
        execute format('alter table public.%I enable row level security', t);
        execute format(
            'create policy %I on public.%I for all to campero_backend'
            ' using (organizacao_id = (select public.app_org_atual()))'
            ' with check (organizacao_id = (select public.app_org_atual()))',
            t || '_backend', t
        );
        execute format(
            'grant select, insert, update, delete on public.%I to campero_backend, service_role', t
        );
        if t = any (leitura_frontend) then
            execute format(
                'create policy %I on public.%I for select to authenticated'
                ' using (organizacao_id in (select public.orgs_do_usuario()))',
                t || '_membro_leitura', t
            );
            execute format('grant select on public.%I to authenticated', t);
        end if;
    end loop;
end
$$;

-- 4) organizacoes (a chave é "id") e planos (catálogo global).
alter table public.organizacoes enable row level security;
create policy organizacoes_backend on public.organizacoes for all to campero_backend
    using (id = (select public.app_org_atual()))
    with check (id = (select public.app_org_atual()));
create policy organizacoes_membro_leitura on public.organizacoes for select to authenticated
    using (id in (select public.orgs_do_usuario()));
grant select, insert, update on public.organizacoes to campero_backend;
grant select, insert, update, delete on public.organizacoes to service_role;
grant select on public.organizacoes to authenticated;

alter table public.planos enable row level security;
create policy planos_leitura on public.planos for select to authenticated, campero_backend
    using (true);
grant select on public.planos to authenticated, campero_backend;
grant select, insert, update, delete on public.planos to service_role;

-- 5) View de status do lote (security_invoker: aplica a RLS das tabelas de base).
grant select on public.lotes_upload_status to authenticated, campero_backend, service_role;

-- 6) Schema interno: só backend e service_role (não exposto ao Data API, sem RLS:
--    o worker reivindica jobs de qualquer org; a org é fixada antes de processar).
grant select, insert, update, delete on interno.jobs, interno.chaves_api, interno.notificacoes
    to campero_backend, service_role;
grant select, insert on interno.auditoria to campero_backend, service_role;  -- só acrescenta
grant usage on all sequences in schema interno to campero_backend, service_role;
