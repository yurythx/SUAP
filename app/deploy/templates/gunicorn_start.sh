#!/bin/bash
set -e
LOGFILE=/var/opt/suap/deploy/logs/gunicorn/gunicorn.log
LOGDIR=$(dirname $LOGFILE)
NUM_WORKERS=17 # idealmente deve ser 2n + 1 (n = qtd de processadores)
USER=www-data
GROUP=www-data
cd /var/opt/suap
test -d $LOGDIR || mkdir -p $LOGDIR
. /etc/default/locale
export LANG
export LC_ALL
exec ./.venv/bin/gunicorn suap.wsgi:application -w $NUM_WORKERS \
  --user=$USER --group=$GROUP --log-level=critical \
  --max-requests=1000 --max-requests-jitter=30 \
  --log-file=$LOGFILE 2>>$LOGFILE \
  --timeout=1800
