#!/usr/bin/env bash
# Backup diário do banco (pg_dump) e dos arquivos do pendrive (tar), em /backups/AAAA-MM-DD.
# Roda uma vez ao subir (se o dia ainda não tem backup) e depois todo dia em BACKUP_HORA.
# Restaurar: docs/producao-em-casa.md.
set -euo pipefail

fazer_backup() {
    local dia destino
    dia="$(date +%F)"
    destino="/backups/$dia"
    [ -f "$destino/ok" ] && return 0
    mkdir -p "$destino"
    echo "$(date '+%F %T') backup: banco"
    pg_dump -Fc -d campero -f "$destino/campero.dump.tmp"
    mv "$destino/campero.dump.tmp" "$destino/campero.dump"
    echo "$(date '+%F %T') backup: arquivos"
    tar -czf "$destino/arquivos.tar.gz.tmp" -C /storage .
    mv "$destino/arquivos.tar.gz.tmp" "$destino/arquivos.tar.gz"
    du -sh "$destino"/* > "$destino/ok"
    echo "$(date '+%F %T') backup pronto: $(tr '\n' ' ' < "$destino/ok")"
    # Mantém os últimos BACKUP_DIAS dias (nomes AAAA-MM-DD ordenam por data).
    ls -1d /backups/????-??-?? | head -n -"${BACKUP_DIAS:-14}" | xargs -r rm -rf
}

fazer_backup
while true; do
    sleep 600
    if [ "$(date +%H)" = "${BACKUP_HORA:-03}" ]; then
        fazer_backup
    fi
done
