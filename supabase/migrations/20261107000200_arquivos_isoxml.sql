-- ISOXML (ISOBUS): cada TLG da pasta TASKDATA vira um arquivo processável, de qualquer marca.
alter table public.arquivos_brutos drop constraint arquivos_brutos_tipo_check;
alter table public.arquivos_brutos add constraint arquivos_brutos_tipo_check
    check (tipo in ('jdl', 'zip', 'masterdata', 'gjson', 'contorno', 'rcd', 'isoxml'));
