#!/bin/bash

# Habilitar a coleta de dados: Certifique-se de que as seguintes configurações estão definidas no arquivo de
# configuração do PostgreSQL (postgresql.conf):
# shared_preload_libraries = 'pg_stat_statements'
# track_activity_query_size = 1024
# pg_stat_statements.track = all

POSTGRES_DB=${DATABASE_NAME:-$POSTGRES_DB}
POSTGRES_USER=${DATABASE_USER:-$POSTGRES_USER}
POSTGRES_PASSWORD=${DATABASE_PASSWORD:-$POSTGRES_PASSWORD}
POSTGRES_HOST=${DATABASE_HOST:-$POSTGRES_HOST}
POSTGRES_PORT=${DATABASE_PORT:-$POSTGRES_PORT}

# Função para verificar se a extensão pg_stat_statements está habilitada
verificar_pg_stat_statements() {
    echo "Verificando se a extensão pg_stat_statements está habilitada..."
    extension_output=$(psql -h $POSTGRES_HOST -p $POSTGRES_PORT -U $POSTGRES_USER -d $POSTGRES_DB \
    -c "SELECT * FROM pg_extension WHERE extname = 'pg_stat_statements';" 2>&1)

    if echo "$extension_output" | grep -q "pg_stat_statements"; then
        echo "A extensão pg_stat_statements já está habilitada."
    else
        echo "A extensão pg_stat_statements não está habilitada. Tentando instalá-la..."
        install_output=$(psql -h $POSTGRES_HOST -p $POSTGRES_PORT -U $POSTGRES_USER -d $POSTGRES_DB \
        -c "CREATE EXTENSION pg_stat_statements;" 2>&1)

        if echo "$install_output" | grep -q "CREATE EXTENSION"; then
            echo "Extensão pg_stat_statements instalada com sucesso."
        else
            echo "Erro ao tentar instalar a extensão pg_stat_statements:"
            echo "$install_output"
        fi
    fi
}

# Verifica se o banco de dados é local ou remoto
if [ "$POSTGRES_DB" = "db" ]; then
    echo "Inicializando o banco de dados local..."
    docker-entrypoint.sh postgres -c port=$POSTGRES_PORT
else
    echo "Conectando ao banco de dados remoto..."

    while true; do
        # Tenta se conectar ao banco de dados remoto
        echo ">>> Verificando a conexão com o banco de dados remoto: $POSTGRES_DB no host $POSTGRES_HOST:$POSTGRES_PORT"

        export PGPASSWORD=$POSTGRES_PASSWORD
        psql_output=$(psql -e -h $POSTGRES_HOST -p $POSTGRES_PORT -U $POSTGRES_USER -d $POSTGRES_DB -c '\q' 2>&1)

        if [ $? -eq 0 ]; then
            echo "Conexão com o banco de dados remoto estabelecida com sucesso."
            echo "$psql_output"

            # Verifica se a extensão pg_stat_statements está habilitada, senão, instala
            verificar_pg_stat_statements

            # Exibindo os últimos comandos SQL executados via pg_stat_statements
            echo "Exibindo os últimos comandos SQL enviados ao banco de dados:"
            echo ">>> psql -h $POSTGRES_HOST -p $POSTGRES_PORT -U $POSTGRES_USER -d $POSTGRES_DB -c ..."

          psql_output=$(psql -h $POSTGRES_HOST -p $POSTGRES_PORT -U $POSTGRES_USER -d $POSTGRES_DB \
          -c "SELECT rolname, current_user, dbid, query, calls, total_exec_time, rows, \
          100.0 * shared_blks_hit / nullif(shared_blks_hit + shared_blks_read, 0) AS hit_percent \
          FROM pg_stat_statements \
          JOIN pg_roles pr ON (userid=oid) \
          WHERE query != 'SELECT unaccent(\$2, upper(\$1))' \
          ORDER BY calls DESC \
          LIMIT 5;" 2>&1 )
          #| sed ':a;N;$!ba;s/\n/ /g'
#          ORDER BY (blk_read_time + blk_write_time)/calls DESC \


            echo "$psql_output"
        else
            echo "Erro ao conectar ao banco de dados remoto:"
            echo "$psql_output"
        fi

        # Pausa de 5 segundos antes de repetir o loop
        sleep 5
    done
fi
