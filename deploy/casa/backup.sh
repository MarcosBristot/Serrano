#!/usr/bin/env bash
# Backup diário do banco (pg_dump) em /backups/AAAA-MM-DD e espelho dos arquivos do pendrive em
# /backups/arquivos. Os arquivos brutos nunca mudam (nome = sha256 do conteúdo), então o espelho só
# copia os novos: o backup cresce com os pendrives novos, não com os dias.
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
    echo "$(date '+%F %T') backup: arquivos (só os novos)"
    mkdir -p /backups/arquivos
    cp -an /storage/. /backups/arquivos/
    # o que saiu do storage (exclusão de conta, LGPD) sai do espelho também
    (cd /backups/arquivos && find . -type f) | while IFS= read -r f; do
        [ -e "/storage/$f" ] || rm -f "/backups/arquivos/$f"
    done
    find /backups/arquivos -mindepth 1 -type d -empty -delete
    { du -sh "$destino/campero.dump"; du -sh /backups/arquivos; } > "$destino/ok"
    echo "$(date '+%F %T') backup pronto: $(tr '\n' ' ' < "$destino/ok")"
    # Mantém os últimos BACKUP_DIAS dias (nomes AAAA-MM-DD ordenam por data).
    ls -1d /backups/????-??-?? | head -n -"${BACKUP_DIAS:-7}" | xargs -r rm -rf
}

fazer_backup
while true; do
    sleep 600
    if [ "$(date +%H)" = "${BACKUP_HORA:-03}" ]; then
        fazer_backup
    fi
done
