-- Trimble TMX-2050 / PTx (monitor da Massey Ferguson e de outras marcas AGCO): os registros de
-- GPS da pasta Diagnostics (*_LogAg_*.tsip) viram arquivos processáveis.
alter table public.arquivos_brutos drop constraint arquivos_brutos_tipo_check;
alter table public.arquivos_brutos add constraint arquivos_brutos_tipo_check
    check (tipo in ('jdl', 'zip', 'masterdata', 'gjson', 'contorno', 'rcd', 'isoxml', 'tsip'));
