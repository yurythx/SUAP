#!/bin/bash
# Puxa o dump mais recente do suap-db para este host, fora do disco do banco.
set -euo pipefail
dest=/var/backups/suap
remoto=root@192.168.110.30
chave=/root/.ssh/suap_backup
mkdir -p "$dest"
chmod 700 "$dest"
ssh -i "$chave" -o StrictHostKeyChecking=accept-new "$remoto" /usr/local/sbin/suap-backup.sh
nome=$(ssh -i "$chave" -o StrictHostKeyChecking=accept-new "$remoto" readlink -f /var/backups/suap/suap-latest.dump)
base=$(basename "$nome")
scp -i "$chave" -o StrictHostKeyChecking=accept-new "$remoto:$nome" "$dest/$base"
ln -sfn "$base" "$dest/suap-latest.dump"
find "$dest" -type f -name 'suap-*.dump' -mtime +7 -delete
echo "PULL_OK $dest/$base"
