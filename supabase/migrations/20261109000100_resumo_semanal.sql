-- Resumo semanal: o worker manda uma vez por semana (segunda de manhã) para os destinos ativos.
create table interno.resumos_semanais (
    organizacao_id  uuid not null references public.organizacoes (id) on delete cascade,
    semana          text not null,          -- ISO: "2026-W46"
    enviado_em      timestamptz not null default now(),
    destinos        int not null default 0,
    texto           text not null,
    primary key (organizacao_id, semana)
);
alter table interno.resumos_semanais enable row level security;
create policy resumos_semanais_backend on interno.resumos_semanais
    for all to campero_backend using (true) with check (true);
grant select, insert on interno.resumos_semanais to campero_backend, service_role;

-- SECURITY DEFINER: o worker não tem organização ativa; só devolve id e fuso de quem tem
-- destino de e-mail ou webhook ligado (nada do conteúdo).
create or replace function interno.orgs_com_destino_ativo()
returns table (organizacao_id uuid, fuso text)
language sql stable security definer
set search_path = ''
as $$
    select distinct o.id, o.fuso
    from public.organizacoes o
    join public.destinos_notificacao d on d.organizacao_id = o.id
    where d.ativo and d.tipo in ('email', 'webhook')
$$;
revoke all on function interno.orgs_com_destino_ativo() from public;
grant execute on function interno.orgs_com_destino_ativo() to campero_backend, service_role;
