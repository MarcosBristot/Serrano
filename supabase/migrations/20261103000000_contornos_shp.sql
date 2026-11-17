-- Perímetros de talhão em shapefile (ex.: controlador OMNI do pulverizador) dentro do .zip.
alter table public.arquivos_brutos drop constraint arquivos_brutos_tipo_check;
alter table public.arquivos_brutos add constraint arquivos_brutos_tipo_check
    check (tipo in ('jdl', 'zip', 'masterdata', 'gjson', 'contorno'));
