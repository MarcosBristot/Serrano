-- Planos comerciais e pedidos de assinatura feitos pelo painel. Lançamento (nov/2026): um preço
-- só, R$ 400/mês no plano Fazenda, até o benchmark; o Produtor fica pronto, fora da vitrine.
-- O pagamento ainda não é automático: o pedido chega à equipe Serrano, que ativa a assinatura
-- (comando `sistemacampero assinatura ativar`). O limite de máquinas já era aplicado.

alter table public.planos
    add column descricao text not null default '',
    add column ordem smallint not null default 0,
    add column destaque boolean not null default false,
    add column sob_consulta boolean not null default false,
    add column publico boolean not null default true,
    add column preco_anual_centavos integer check (preco_anual_centavos >= 0),
    add column recursos text[] not null default '{}';

-- "basico" era o plano único do começo: fica fora da vitrine (assinaturas antigas continuam válidas).
update public.planos set publico = false, ordem = 99 where codigo = 'basico';

insert into public.planos (codigo, nome, max_maquinas, preco_mensal_centavos, preco_anual_centavos,
    descricao, ordem, destaque, sob_consulta, recursos)
values
    ('produtor', 'Produtor', 3, 24900, 249000,
     'Para quem está começando a medir a frota.', 1, false, false,
     array['Até 3 máquinas', 'Todas as marcas e formatos de monitor', 'Custo por hectare e mapa de calor',
           'Alertas de ociosidade e consumo', 'Usuários ilimitados']),
    ('fazenda', 'Fazenda', 10, 40000, 400000,
     'A frota inteira num painel só, com tudo incluído.', 2, true, false,
     array['Até 10 máquinas', 'Todas as marcas e formatos de monitor', 'Custo por hectare e mapa de calor',
           'Alertas de ociosidade e consumo', 'Manutenção pelo horímetro', 'Resumo semanal por e-mail',
           'Planilhas e exportação dos dados', 'Usuários ilimitados']),
    ('grupo', 'Grupo e cooperativa', 200, 0, null,
     'Várias fazendas, frotas grandes e integrações sob medida.', 3, false, true,
     array['Mais de 10 máquinas', 'Várias fazendas e unidades', 'Integração com o seu ERP',
           'Implantação acompanhada', 'Suporte dedicado'])
on conflict (codigo) do nothing;
update public.planos set publico = false where codigo = 'produtor';

-- Quem ainda está no teste do plano antigo passa a testar o "Fazenda" (o padrão das contas novas).
update public.assinaturas set plano_codigo = 'fazenda'
where plano_codigo = 'basico' and status = 'trial';

create table public.pedidos_assinatura (
    id              uuid primary key default gen_random_uuid(),
    organizacao_id  uuid not null references public.organizacoes (id) on delete cascade,
    plano_codigo    text not null references public.planos (codigo),
    ciclo           text not null check (ciclo in ('mensal', 'anual')),
    mensagem        text check (char_length(mensagem) <= 2000),
    telefone        text check (char_length(telefone) <= 40),
    solicitado_por  uuid,
    status          text not null default 'aberto' check (status in ('aberto', 'atendido', 'cancelado')),
    criado_em       timestamptz not null default now()
);
create index pedidos_assinatura_org_idx on public.pedidos_assinatura (organizacao_id, criado_em desc);

alter table public.pedidos_assinatura enable row level security;
create policy pedidos_assinatura_backend on public.pedidos_assinatura
    for all to campero_backend
    using (organizacao_id = (select public.app_org_atual()))
    with check (organizacao_id = (select public.app_org_atual()));
grant select, insert on public.pedidos_assinatura to campero_backend;
grant select, insert, update, delete on public.pedidos_assinatura to service_role;
create policy pedidos_assinatura_membro_leitura on public.pedidos_assinatura
    for select to authenticated
    using (organizacao_id in (select public.orgs_do_usuario()));
grant select on public.pedidos_assinatura to authenticated;
