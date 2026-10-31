#!/bin/bash
#set -e
##############################################################################
### DEFINIÇÕES DE VARÍAVEIS GLOBAIS
##############################################################################
TAR_GZ=0

POSTGRES_DB=${DATABASE_NAME:-$POSTGRES_DB}
POSTGRES_USER=${DATABASE_USER:-$POSTGRES_USER}
POSTGRES_PASSWORD=${DATABASE_PASSWORD:-$POSTGRES_PASSWORD}
POSTGRES_HOST=${DATABASE_HOST:-$POSTGRES_HOST}
POSTGRES_PORT=${DATABASE_PORT:-$POSTGRES_PORT}

#Define valores padrão para conexão do banco
POSTGRES_DB=${POSTGRES_DB:-dbdefault}
POSTGRES_USER=${POSTGRES_USER:-postgres}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-postgres}
POSTGRES_HOST=${POSTGRES_HOST:-localhost}
POSTGRES_PORT=${POSTGRES_PORT:-5432}

export PGPASSWORD=$POSTGRES_PASSWORD

DIR_DUMP=${DATABASE_DUMP_DIR:-/dump}

UTILS_SH="utils.sh"

if [ -n "$PG_VERSION" ]; then
  echo "Executando via docker-compose"
  UTILS_SH="/scripts/utils.sh"
  DIR_DUMP='/dump'
fi
source "$UTILS_SH"

# 2>/dev/null: Redireciona apenas a saída padrão (stdout) para /dev/null, descartando todas
# as saídas normais, mas permitindo que os erros (stderr) ainda sejam exibidos.

ZIPDUMP=$(ls $DIR_DUMP/*.{bkp.gz,sql.gz,tar.gz} 2>/dev/null  | head -n 1)
SQLDUMP=$(ls $DIR_DUMP/*.sql 2>/dev/null)

echo "DIR_DUMP: $DIR_DUMP, ZIPDUMP: $ZIPDUMP, SQLDUMP: $SQLDUMP"

##############################################################################
### VALIDAÇÕES DE ARQUIVOS NECESSÁRIOS
##############################################################################
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
### DEFINIÇÕES DE FUNÇÕES
##############################################################################

# Função para retornar o caminho completo do arquivo SQLDUMP a partir de um arquivo zipdump
function get_sqldump_path() {
  local zipdump="$1"   # Recebe o caminho do arquivo zipdump
  local dir_dump="$2"  # Recebe o diretório onde o dump está localizado
  local -n sqldump="$3"   # passagem por referência

  # verifica se a variável NÃO está vazia ou nula.
  if [ -n "$sqldump" ]; then
    echo "$sqldump"
    return 0
  fi

  # Extrai o nome base do arquivo zipdump (remove o caminho)
  local filename=$(basename "$zipdump")

  # Extrai a extensão do arquivo
  local extension="${filename##*.}"

  # Remove as duas últimas extensões do nome do arquivo
  local filename_without_extension="${filename%.*}"
  filename_without_extension="${filename_without_extension%.*}"


  # Retorna o caminho completo do sqldump
  sqldump="$dir_dump/$filename_without_extension"
}

function is_tar_gz() {
    local file="$1"

    # Verifica se o arquivo é um .tar.gz e lista o primeiro conteúdo
    if tar tzf "$file" | head -n 1 &>/dev/null; then
        return 0
    else
        return 1
    fi
# if is_tar_gz "$FILE"; then
#    echo "O arquivo foi compactado com tar."
# fi
}

function is_gzip() {
    local file="$1"

    # Usa o comando 'file' para verificar se o arquivo é compactado com gzip
    if file "$file" | grep -q "gzip compressed data"; then
        return 0
    else
        return 1
    fi
# if is_gzip "$FILE"; then
#    echo "O arquivo foi compactado com gzip."
# fi
}

# Função para descompactar o arquivo de dump
function descompactar_tar_gz() {
  local zipdump=$1
  local dir_dump=$2
  local sqldump=$3

   echo ">>> ${FUNCNAME[0]} $zipdump $dir_dump $sqldump"

  # Verifica se o arquivo $zipdump existe e se é um arquivo regular
  if [ -f "$zipdump" ]; then
    # Cria o diretório se ele não existir.

    if [ ! -d "$sqldump" ]; then
      mkdir -p "$sqldump"
      exit_code=$?
      if [ "$exit_code" -eq 1 ]; then
        echo_error "Impossível criar o diretório!"
      fi
    fi

    # Extrai o nome do arquivo sem a extensão
    filename=$(basename "$zipdump")
    filename_without_extension="${filename%.*}"

    echo "--- Descompactando arquivo de dump $filename ..."
    mkdir -p "$dir_dump/$filename_without_extension"

    if is_script_initdb; then
      echo ">>> pigz -k -dc $dir_dump/$filename | tar -xvC $sqldump -f -"
      pigz -k -dc "$dir_dump/$filename" | tar -xvC "$sqldump" -f -
    else
      echo ">>> pigz -k -dc $dir_dump/$filename | pv | tar -C $sqldump -xf -"
      pigz -k -dc "$dir_dump/$filename" | pv | tar -C "$sqldump" -xf -
    fi
    exit_code=$?

    # Verifica o código de saída do comando anterior
    if [ "$exit_code" -eq 0 ]; then
      echo "Arquivo descompactado com sucesso para ${sqldump}."
      return 0 # Sucesso
    else
      echo "Erro durante a descompactação do arquivo."
      return 1  # Falha durante a descompactação do arquivo.
    fi
  else
    echo "Arquivo $zipdump não encontrado."
    return 1  # Falha, arquivo não encontrado
  fi
}

function descompactar_gzip() {
  local zipdump="$1"
  local dir_dump="$2"
  local sqldump="$3"

  echo ">>> ${FUNCNAME[0]} $zipdump $dir_dump $sqldump"

  # Verifica se o arquivo $zipdump existe e é um arquivo regular
  if [ -f "$zipdump" ]; then
    sqldump="$sqldump.sql"
    echo "--- Descompactando arquivo de dump ${sqldump} ..."

    if is_script_initdb; then
      echo ">>> gzip -d $zipdump > $sqldump"
      gzip -d "$zipdump" > "$sqldump"
    else
      # O pv monitora o progresso da leitura do arquivo e o envia para o gunzip
      echo ">>> pv $zipdump | gzip -d > $sqldump"
      pv "$zipdump" | gzip -d > "$sqldump"
    fi
    exit_code=$?

    # Verifica o código de saída do comando anterior para sucesso
    if [ "$exit_code" -eq 0 ]; then
      echo "Arquivo descompactado com sucesso para ${sqldump}."
      return 0 # sucesso
    else
      echo "Erro durante a descompactação do arquivo."
      echo "--- Verificando se o arquivo está corrompido, aguarde ..."

      # Verifica se o arquivo está corrompido usando gzip -t
      if ! gzip -t "$zipdump" 2>/dev/null; then
        echo "O arquivo $zipdump está corrompido ou incompleto."
      fi
      return 1 # Falha na descompactação ou arquivo corrompido
    fi
  else
    echo "sqldump = $sqldump"
    echo "zipdump = $zipdump"
    echo "Arquivo de dump não encontrado no diretório $dir_dump ou arquivo dump já foi restaurado."
    return 1  # Falha, arquivo não encontrado
  fi
}

# Função para criar ou recriar o banco de dados
function criar_recriar_database() {
    local host="$1"
    local postgres_port="$2"
    local postgres_db="$3"
    local postgres_user="$4"
    local pg_command

    pg_command="psql -v ON_ERROR_STOP=1 --host $host --port $postgres_port --username $postgres_user"

    echo ">>> ${FUNCNAME[0]} $postgres_db $postgres_user"

    # Executa o comando SQL para excluir e recriar o banco de dados
    $pg_command <<-EOSQL
    DROP DATABASE IF EXISTS $postgres_db;
    CREATE DATABASE $postgres_db;
    GRANT ALL PRIVILEGES ON DATABASE $postgres_db TO $postgres_user;
EOSQL

    check_command_status_on_error_exit "Falha ao excluir ou criar o banco de dados $postgres_db." "Banco de dados $postgres_db criado ou recriado com sucesso."
}

# Função para verificar se a extensão postgis está instalada e instalá-la caso não esteja
function verificar_instalar_postgis() {
    local postgres_port="$1"
    local host="$2"
    local postgres_user="$3"
    local pg_command

    pg_command="psql -v ON_ERROR_STOP=1 --host $host --port $postgres_port --username $postgres_user"

    echo "--- Verificando se a extensão postgis está instalada ..."

    # Executa a consulta para verificar se a extensão postgis está instalada
    echo ">>> $pg_command -t -c \"SELECT count(*) FROM pg_extension WHERE extname = 'postgis';\""
    resultado=$($pg_command -t -c "SELECT count(*) FROM pg_extension WHERE extname = 'postgis';")

    # Se o resultado for zero, significa que a extensão não está instalada
    # shellcheck disable=SC2317
    if [ "$resultado" -eq 0 ]; then
        echo "--- Instalando extensão postgis ..."
        echo ">>> $pg_command -t -c \"CREATE EXTENSION IF NOT EXISTS postgis;\""

        # Comando para criar a extensão postgis
        $pg_command -t -c "CREATE EXTENSION IF NOT EXISTS postgis;"
        exit_code=$?

        # Verifica se o comando foi executado com sucesso
        if [ "$exit_code" -eq 0 ]; then
            echo "Extensão postgis instalada com sucesso."
            return 1  # Sucesso
        else
            echo_warning "Erro ao instalar a extensão postgis."
            return 0  # Falha
        fi
    else
        echo "Extensão postgis já está instalada."
        return 1  # Sucesso
    fi
}

# Função para restaurar dump com pg_restore
function restaurar_dump_pg_restore() {
  local sqldump="$1"
  local host="$2"
  local postgres_port="$3"
  local postgres_user="$4"
  local postgres_db="$5"

  echo ">>> ${FUNCNAME[0]} $sqldump $host $postgres_port $postgres_user $postgres_db"

  # Verifica se a variável sqldump não está vazia
  # shellcheck disable=SC2317
  if [ ! -z "$sqldump" ]; then
    echo "--- Restaurando dump tar_gz $sqldump ..."

    # Executa o pg_restore e salva o log de saída em /dump/restore.log
    # Executa pg_restore com paralelismo (4 processos - -j 4)
    if is_script_initdb; then
       # 2>&1: redireciona a saída de erro (stderr) para onde a saída padrão (stdout) está indo.
       # Isso faz com que tanto stdout quanto stderr sejam combinados e enviados para o mesmo destino

      # O comando tee, além de salvar o log na saída /dump/restore.log, exibe também no terminal
      echo ">>> pg_restore -h $host -p $postgres_port -U $postgres_user -d $postgres_db -j 4 -Fd -O $sqldump -v 2>&1 | tee /dump/restore.log"
      echo_warning "Para acompanhar o progresso, use o comando tail -f "
      pg_restore -h "$host" -p "$postgres_port" -U "$postgres_user" -d "$postgres_db" -j 4 -Fd -O "$sqldump" -v 2>&1 | tee /dump/restore.log
#      exit_code="${PIPESTATUS[0]}" # Captura o código de saída de pg_restore, que é o primeiro comando do pipe
    else
      # Uso do comando PV para acompanhar a progressão
      echo ">>> pg_restore -h $host -p $postgres_port -U $postgres_user -d $postgres_db -j 4  -Fd $sqldump -v 2>&1 | pv -ptealr -s $(du -sb $sqldump | awk '{print $1}') > /dump/restore.log"
      pg_restore -h "$host" -p "$postgres_port" -U "$postgres_user"  -d "$postgres_db" -j 4 -Fd "$sqldump" -v 2>&1 | pv -s $(du -sb "$sqldump" | awk '{print $1}') > "/dump/restore.log"
#      exit_code="${PIPESTATUS[0]}" # Captura o código de saída de pg_restore, que é o primeiro comando do pipe
    fi
    exit_code=$?

    # Verifica se o comando foi executado com sucesso
    if [ "$exit_code" -eq 0 ]; then
      echo_success "Dump restaurado com sucesso."
#      echo "Excluindo arquivos restaurados"
#      echo ">>> rm -rf $sqldump/"
#      rm -rf "${sqldump:?}/" #Usando "${sqldump:?}", o Bash emitirá um erro e interromperá o script se a variável estiver vazia ou indefinida.
    else
      echo_error "Falha na execução do pg_restore.  Código de saída: $exit_code"
      exit $exit_code # Falha
    fi
  else
    echo_error "Arquivo de dump não encontrado. Código de saída: $exit_code"
    exit $exit_code # Falha
  fi
}

function restaurar_dump_psql() {
  local sqldump="$1"
  local host="$2"
  local postgres_port="$3"
  local postgres_user="$4"
  local postgres_db="$5"
  local exit_code=0
  local pg_command

  pg_command="psql -v ON_ERROR_STOP=1 --host $host --port $postgres_port --username $postgres_user"

  echo ">>> ${FUNCNAME[0]} $sqldump $host $postgres_port $postgres_user $postgres_db"

  # Verifica se o dump SQL existe
  # shellcheck disable=SC2317
  if [ ! -z "$sqldump" ]; then
    echo "--- Restaurando dump $sqldump ..."

    if is_script_initdb; then
      echo ">>> $pg_command -d $postgres_db < $sqldump 2>&1 | tee /dump/restore.log"
      $pg_command -d "$postgres_db" < "$sqldump" 2>&1 | tee /dump/restore.log
    else
      # Usa o comando pv para monitorar o progresso da restauração com psql
      echo ">>> pv $sqldump | $pg_command -d $postgres_db > /dump/restore.log 2>&1"
      pv "$sqldump" | $pg_command -d "$postgres_db" > /dump/restore.log 2>&1
    fi
    exit_code=$?

    # Verifica o código de retorno
    if [ "$exit_code" -eq 0 ]; then
       echo_success "Restauração concluída com sucesso."
    else
      # Exibe o conteúdo do log em caso de erro
      cat /dump/restore.log
      echo_error "Falha ao restaurar o dump $sqldump, veja o erro acima."
      exit 1
    fi

  else
    echo_warning "Arquivos de dump não encontrados."
  fi
}

##############################################################################
### INSTALAÇÃO DE COMANDOS NECESSÁRIOS
##############################################################################
#install_command_pigz
#install_command_tar
#install_command_file
#install_command_pv
#install_command_ps
#install_command_postgis

##############################################################################
### MAIN
##############################################################################
# SQLDUMP - passagem por referência
get_sqldump_path "$ZIPDUMP" "$DIR_DUMP" SQLDUMP

echo "dir_dump = $DIR_DUMP"
echo "SQLDUMP = $SQLDUMP"
echo "ZIPDUMP = $ZIPDUMP"

# Chamar a função para obter o host e a prota correta
read host port <<< $(get_host_port "$POSTGRES_HOST" "$POSTGRES_PORT" "$POSTGRES_USER" "$POSTGRES_PASSWORD")
if [ $? -gt 0 ]; then
  echo_error "Não foi possível conectar ao banco de dados."
  exit 1
fi

#host_value="${host#*=}"
check_db_exists "$POSTGRES_USER" "$POSTGRES_DB" "$host" "$port"
db_exists=$?

# SE este script script está sendo chamado pelo script de inicialização do container postres
# E o banco já existir,
# ENTÃO não faça nada.
if is_script_initdb && [ "$db_exists" -eq 0 ]; then
  echo_warning "Banco de dados $POSTGRES_DB já existe. No entanto, existe dump pronto para ser restaurado."
  echo_warning "Use o comando './service db restore' para restaurar."
  exit 0
fi

has_restore=0

echo "--- Iniciando processo de restauração do dump ..."
# -e verifica se um caminho (arquivo ou diretório) existe.
# Só realiza a descompactação do arquivo se o mesmo ainda não tiver sido descompactado.
if [ ! -e "$SQLDUMP" ] && [ -e "$ZIPDUMP" ]; then
  # echo "A variável SQLDUMP está vazia."
  if is_tar_gz "$ZIPDUMP"; then
    descompactar_tar_gz "$ZIPDUMP" "$DIR_DUMP" "$SQLDUMP"
    has_restore=$?  # Captura o código de retorno da função
    TAR_GZ=1
  elif is_gzip "$ZIPDUMP"; then
    descompactar_gzip "$ZIPDUMP" "$DIR_DUMP" "$SQLDUMP"
    has_restore=$?  # Captura o código de retorno da função
  fi
  check_command_status_on_error_exit "Falha na descompactação." "Descompactação concluída com sucesso!"
fi

if [ "$has_restore" -eq 0 ] && [ ! -e "$SQLDUMP" ]; then
  echo_warning "Não foi encontrado arquivo de dump!"
  #Interropção com código de saída difente de zero para indicar um erro.
  exit 1
elif [ -e "$SQLDUMP" ]; then
  echo_info "Arquivo dump descompactado encontrado!"
fi

echo "--- Apagando base $POSTGRES_DB, caso exista"
echo "--- Recriando base $POSTGRES_DB"

# Chamar a função e verificar o resultado
criar_recriar_database "$host" "$port" "$POSTGRES_DB" "$POSTGRES_USER"
verificar_instalar_postgis "$port" "$host" "$POSTGRES_USER"

echo "--- Iniciando processo de restauração do dump ..."

# Verificar se foi descompactado com tar ou o dump descompactado é um diretório.
if [ "$TAR_GZ" -eq 1 ] || [ -d "$SQLDUMP" ]; then
  restaurar_dump_pg_restore "$SQLDUMP" "$host" "$port" "$POSTGRES_USER" "$POSTGRES_DB"
else
  restaurar_dump_psql "$SQLDUMP" "$host" "$port" "$POSTGRES_USER" "$POSTGRES_DB"
  # Verifica se o log contém "pg_restore", indicando formato incompatível com psql
  if grep -q "pg_restore" /dump/restore.log; then
    echo_warning "Formato do dump não é compatível com psql."
    echo_warning "Tentando restaurar usando pg_restore ..."
    restaurar_dump_pg_restore "$SQLDUMP" "$host" "$port" "$POSTGRES_USER" "$POSTGRES_DB"
  fi
fi
