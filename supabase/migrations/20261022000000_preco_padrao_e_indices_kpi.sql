-- M5 · Preço padrão do diesel por organização e índices para KPIs.
--
-- Referência: ANP, levantamento semanal do RS (coleta de 28/08/2026), S10 a R$ 6,586/L
-- (preço de bomba). Arredondado para R$ 6,59/L e editável pelo gestor: fazenda que compra
-- de distribuidora (TRR) costuma pagar menos; o ideal é cadastrar o preço da nota.
-- valido_de antigo para cobrir o histórico importado do pendrive.

create or replace function interno.semear_preco_combustivel() returns trigger
language plpgsql
set search_path = ''
as $$
begin
    insert into public.preco_combustivel (organizacao_id, tipo, preco_rs_l, valido_de, fonte)
    values (new.id, 'S10', 6.59, date '2000-01-01', 'anp');
    return new;
end
$$;
revoke all on function interno.semear_preco_combustivel() from public;
grant execute on function interno.semear_preco_combustivel() to campero_backend, service_role;

create trigger organizacoes_preco_padrao after insert on public.organizacoes
    for each row execute function interno.semear_preco_combustivel();

-- Organizações que já existem.
insert into public.preco_combustivel (organizacao_id, tipo, preco_rs_l, valido_de, fonte)
select o.id, 'S10', 6.59, date '2000-01-01', 'anp'
from public.organizacoes o
where not exists (
    select 1 from public.preco_combustivel p where p.organizacao_id = o.id and p.tipo = 'S10'
);

create index if not exists metricas_diarias_org_maquina_dia_idx
    on public.metricas_diarias (organizacao_id, maquina_id, dia);
create index if not exists metricas_diarias_org_talhao_dia_idx
    on public.metricas_diarias (organizacao_id, talhao_id, dia);
create index if not exists preco_combustivel_org_tipo_idx
    on public.preco_combustivel (organizacao_id, tipo, valido_de);
