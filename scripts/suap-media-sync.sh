#!/bin/bash
set -euo pipefail
dest="${1:?informe o IP do worker}"
chave=/root/.ssh/suap_backup
ssh_cmd="ssh -i ${chave} -o StrictHostKeyChecking=accept-new"
rsync -a -e "${ssh_cmd}" /opt/suap/src/deploy/media/ "root@${dest}:/opt/suap/src/deploy/media/"
rsync -a -e "${ssh_cmd}" "root@${dest}:/opt/suap/src/deploy/media/" /opt/suap/src/deploy/media/
