-- Telemetria compacta: cada linha representa uma janela de até 10 s com o mesmo estado
-- (desligado, parado, trabalhando, sem velocidade) e o mesmo talhão. ``peso_s`` diz quantos
-- segundos ela vale; velocidade e vazão são médias da janela (soma / peso), então horas,
-- litros e distância continuam exatos. Linhas antigas (1 Hz) valem 1 s.
alter table public.telemetria add column peso_s smallint not null default 1
    check (peso_s between 1 and 600);
