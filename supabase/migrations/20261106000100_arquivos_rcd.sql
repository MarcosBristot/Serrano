-- Operações do GreenStar 3 (colheitadeira): par .fdl + .fdd empacotado na expansão do .zip.
alter table public.arquivos_brutos drop constraint arquivos_brutos_tipo_check;
alter table public.arquivos_brutos add constraint arquivos_brutos_tipo_check
    check (tipo in ('jdl', 'zip', 'masterdata', 'gjson', 'contorno', 'rcd'));
