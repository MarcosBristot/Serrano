-- M6-M8 · Apoio a alertas, equipe (convites/chaves) e exportação.

-- Convite aceito por quem ainda não é membro: o backend não conhece a org antes de achar o
-- convite. Função SECURITY DEFINER devolve só o convite do hash informado.
create or replace function interno.convite_por_hash(p_hash text)
returns table (id uuid, organizacao_id uuid, email text, papel text, expira_em timestamptz,
               aceito_em timestamptz)
language sql stable security definer
set search_path = ''
as $$
    select c.id, c.organizacao_id, c.email, c.papel, c.expira_em, c.aceito_em
    from public.convites c where c.token_hash = p_hash
$$;
revoke all on function interno.convite_por_hash(text) from public;
grant execute on function interno.convite_por_hash(text) to campero_backend, service_role;

create index if not exists alertas_org_criado_idx on public.alertas (organizacao_id, criado_em desc, id);
create index if not exists alertas_org_tipo_idx on public.alertas (organizacao_id, tipo, status);
create index if not exists sessoes_maquina_implemento_idx
    on public.sessoes_trabalho (maquina_id, implemento_id, operacao, inicio desc);

-- Notificações: estado intermediário enquanto um worker envia.
alter table interno.notificacoes drop constraint if exists notificacoes_status_check;
alter table interno.notificacoes add constraint notificacoes_status_check
    check (status in ('pendente', 'enviada', 'erro', 'morta'));

-- Exportação: tipo do conteúdo.
alter table public.exportacoes add column if not exists tipo text not null default 'sessoes'
    check (tipo in ('sessoes', 'diarias', 'alertas', 'telemetria'));
