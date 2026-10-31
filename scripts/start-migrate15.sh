#!/bin/bash
pkill -f '/root/migrate-skip-bad-data.py' || true
pkill -f 'manage.py migrate' || true
sleep 1
cd /opt/suap/src
nohup /opt/suap/src/.venv/bin/python /root/migrate-skip-bad-data.py >/tmp/migrate15.log 2>&1 &
echo "STARTED pid=$!"
sleep 2
ls -la /tmp/migrate15.log
head -20 /tmp/migrate15.log
