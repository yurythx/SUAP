#!/bin/bash
pkill -f migrate-skip-bad-data || true
pkill -f 'manage.py migrate' || true
sleep 2
cd /opt/suap/src
nohup /opt/suap/src/.venv/bin/python /root/migrate-skip-bad-data-fast.py >/tmp/migrate16.log 2>&1 &
echo "STARTED pid=$!"
sleep 3
tail -20 /tmp/migrate16.log
