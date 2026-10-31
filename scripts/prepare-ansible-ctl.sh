#!/bin/bash
set -euo pipefail

if [ -f /root/.ssh/id_ed25519 ]; then
  KEY=/root/.ssh/id_ed25519
elif [ -f /root/.ssh/id_rsa ]; then
  KEY=/root/.ssh/id_rsa
else
  ssh-keygen -t ed25519 -N "" -f /root/.ssh/id_ed25519
  KEY=/root/.ssh/id_ed25519
fi
echo "using $KEY"
PUB="${KEY}.pub"

cat > /opt/suap-iac/ansible/inventory.ini <<EOF
[suap]
suap-hml ansible_host=192.168.100.50 ansible_user=deploy ansible_ssh_private_key_file=${KEY}

[suap:vars]
ansible_python_interpreter=/usr/bin/python3
ansible_ssh_common_args=-o StrictHostKeyChecking=accept-new
EOF

if ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -i "$KEY" deploy@192.168.100.50 "echo REMOTE_OK"; then
  echo KEY_OK
else
  echo "NEED_AUTHORIZE"
  cat "$PUB"
fi
