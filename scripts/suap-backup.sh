#!/bin/bash
# Backup do PostgreSQL da homologação da prefeitura.
# Roda no suap-db. A cópia para outro LXC é feita por suap-backup-pull.sh.
set -euo pipefail
dest=/var/backups/suap
mkdir -p "$dest"
chmod 700 "$dest"
stamp=$(date +%Y%m%d-%H%M)
arquivo="$dest/suap-$stamp.dump"
runuser -u postgres -- pg_dump -Fc --dbname=suap > "$arquivo"
ln -sfn "$(basename "$arquivo")" "$dest/suap-latest.dump"
find "$dest" -type f -name 'suap-*.dump' -mtime +7 -delete
echo "BACKUP_OK $arquivo"
