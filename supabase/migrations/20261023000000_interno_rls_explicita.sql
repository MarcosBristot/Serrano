-- Schema interno: RLS explícita com política para o backend.
--
-- O schema não é exposto ao Data API e o worker precisa ver jobs de todas as
-- organizações, então a política do campero_backend é ampla (o isolamento por org
-- é feito no código para essas tabelas). Ligar a RLS aqui, com política, deixa o
-- ambiente igual mesmo quando o SQL Editor do Supabase oferece "Run and enable RLS"
-- (que liga a RLS sem política e bloqueava a fila: "new row violates row-level
-- security policy for table jobs").

do $$
declare
    t text;
begin
    foreach t in array array['jobs', 'chaves_api', 'notificacoes', 'auditoria'] loop
        execute format('alter table interno.%I enable row level security', t);
        execute format('drop policy if exists %I on interno.%I', t || '_backend', t);
        execute format(
            'create policy %I on interno.%I for all to campero_backend using (true) with check (true)',
            t || '_backend', t
        );
    end loop;
end
$$;
