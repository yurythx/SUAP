#!/bin/bash
echo "Stating postgresql service"

if [[ "$OSTYPE" == "darwin"* ]]; then
    pg_ctl start
    echo "Stating Redis service"
    brew services start redis
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo "Stating postgresql service"
    sudo systemctl start postgresql.service
    echo "Stating Redis service"
    sudo systemctl start redis.service
fi
echo "DONE"
