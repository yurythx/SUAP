#!/bin/bash

SERVICE_DB_NAME="db"
POSTGRES_DB=${DATABASE_NAME:-$POSTGRES_DB}
POSTGRES_USER=${DATABASE_USER:-$POSTGRES_USER}
POSTGRES_PASSWORD=${DATABASE_PASSWORD:-$POSTGRES_PASSWORD}
POSTGRES_HOST=${DATABASE_HOST:-$POSTGRES_HOST}
POSTGRES_PORT=${DATABASE_PORT:-$POSTGRES_PORT}

UTILS_SH="/scripts/utils.sh"
DIR_DUMP='/dump'

##############################################################################
### VALIDAÇÕES DE ARQUIVOS NECESSÁRIOS
##############################################################################
source "$UTILS_SH"

RED_COLOR='\033[0;31m'     # Cor vermelha para erros
NO_COLOR='\033[0m'         # Cor neutra para resetar as cores no terminal

function echo_error() {
  echo "${@:3}" -e "$RED_COLOR DANG: $1$NO_COLOR"
}

if [ ! -f "$UTILS_SH" ]; then
  echo_error "Shell script $UTILS_SH não existe.
  Esse arquivo possui as funções utilitárias necessárias.
  Impossível continuar!"
  exit 1
fi

if [ ! -d "$DIR_DUMP" ]; then
    echo_error "O diretório dump $DIR_DUMP não existe."
    exit 1
fi

##############################################################################
### FUNÇÕES UTILITÁRIAS
##############################################################################
verificar_conexao_postgres() {
    local postgresql="postgresql://$POSTGRES_USER:********@$POSTGRES_HOST:$POSTGRES_PORT/"
    echo ">>> Verificando a conexão com o banco de dados remoto: $postgresql"

    # Define uma variável para verificar o status da conexão
    local conexao_estabelecida=1

    # Loop até que a conexão seja bem-sucedida
    while [ $conexao_estabelecida -ne 0 ]; do
        # Tenta conectar ao banco de dados remoto usando psql
        export PGPASSWORD=$POSTGRES_PASSWORD
        psql_output=$(psql -e -h $POSTGRES_HOST -p $POSTGRES_PORT -U $POSTGRES_USER -d $POSTGRES_DB -c '\q' 2>&1)

        if [ $? -eq 0 ]; then
            echo "Conexão com o banco de dados remoto estabelecida com sucesso."
            echo "$psql_output"
            conexao_estabelecida=0
        else
            echo "Erro ao conectar ao banco de dados remoto. Tentando novamente em 5 segundos..."
            echo "$psql_output"
            sleep 5
        fi
    done
}

##############################################################################
### INSTALAÇÃO DE COMANDOS NECESSÁRIOS
##############################################################################
# Adicionar permissões de escrita para todos os usuários (não recomendado para produção)
chmod 777 "$DIR_DUMP"

install_command_pigz
install_command_tar
install_command_file
install_command_pv
install_command_ps
install_command_postgis

# docker exec -it suap-db-1 bash -c "route -n"

##############################################################################
### ADICIONA ROTAS PARA O CONTAINER VPN E ROUTE NETWORK
##############################################################################

##############################################################################
### MAIN
##############################################################################

process_hosts_and_routes "$ETC_HOSTS" "$VPN_GATEWAY" "$ROUTE_NETWORK"

# Verifica se o banco de dados é local ou remoto
if [ "$POSTGRES_HOST" = "db" ]; then
    echo "Inicializando o banco de dados local..."
    docker-entrypoint.sh postgres -c port=$POSTGRES_PORT
else
#    install_command_iptables
#
#    postgres_ip=$(dict_get "$POSTGRES_HOST" "${DICT_ETC_HOSTS[*]}")
#    echo "postgres_ip = $postgres_ip"
#
#    echo "--- Criando regra de redirecionamento de pacotes (DNAT) que chegam na porta 5432 para o host remoto..."
#    # ria uma regra de redirecionamento de pacotes (DNAT), de modo que qualquer tráfego TCP destinado à porta 5432
#    # do servidor original seja redirecionado para o endereço e porta do servidor PostgreSQL,
#    # definidos pelas variáveis $postgres_ip e $POSTGRES_PORT.
#    iptables-legacy -t nat -A PREROUTING -p tcp --dport 5432 -j DNAT --to-destination $postgres_ip:$POSTGRES_PORT
#    iptables-legacy -t nat -A POSTROUTING -j MASQUERADE
#    iptables-legacy -t nat -L -n -v

    echo "--- Conectando ao banco de dados remoto..."
    verificar_conexao_postgres

    while true; do
        export PGPASSWORD=$POSTGRES_PASSWORD
        psql_output=$(psql -e -h $POSTGRES_HOST -p $POSTGRES_PORT -U $POSTGRES_USER -d $POSTGRES_DB -c '\q' 2>&1)

        if [ $? -eq 0 ]; then
            echo "Exibindo as sessões/conexões ativas no PostgreSQL:"
#            echo ">>> psql -h $POSTGRES_HOST -p $POSTGRES_PORT -U $POSTGRES_USER -d $POSTGRES_DB -c ... \"select * from pg_stat_activity where datname = '$POSTGRES_DB'\""

            psql_output=$(psql -h $POSTGRES_HOST -p $POSTGRES_PORT -U $POSTGRES_USER -d $POSTGRES_DB \
            -c "SELECT COUNT(*) FROM pg_stat_activity WHERE pid <> pg_backend_pid() and datname = '$POSTGRES_DB'"  2>&1 )
#            -c "SELECT
#                    pid, state, usename, datname, application_name, backend_start, wait_event, wait_event_type, client_addr
#                FROM pg_stat_activity
#                WHERE pid <> pg_backend_pid()
#                    and datname = '$POSTGRES_DB'
#                order by backend_start DESC
#                ;" 2>&1 )

              echo "$psql_output"
        else
            echo "Erro ao conectar ao banco de dados remoto:"
            echo "$psql_output"
        fi

        # Pausa de 10 segundos antes de repetir o loop
        sleep 100
    done
fi
