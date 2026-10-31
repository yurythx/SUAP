#!/bin/bash
# O erro bad interpreter: No such file or directory ocorre porque o script service.sh foi provavelmente criado
# ou editado em um ambiente Windows, onde o final de linha é CRLF (\r\n), enquanto no Linux o final de linha
# padrão é LF (\n). O caractere ^M representa o \r (Carriage Return) que está causando o problema.
#
# Correção:
# >>> sed -i 's/\r//' service.sh
# >>> sed -i 's/\r//' docker/dev/scripts/utils.sh
# >>> sed -i 's/\r//' docker/dev/scripts/init_database.sh

# garantir que o Git não altere os fins de linha automaticamente ao fazer checkout ou commit.
git config --global core.autocrlf false


DOCKER_DEV_DIR="docker/dev"

utils_sh="$DOCKER_DEV_DIR/scripts/utils.sh"
source $utils_sh

RED_COLOR='\033[0;31m'     # Cor vermelha para erros
NO_COLOR='\033[0m'         # Cor neutra para resetar as cores no terminal

function echo_error() {
  echo "${@:3}" -e "$RED_COLOR DANG: $1$NO_COLOR"
}

if [ ! -f "$utils_sh" ]; then
  echo_error "Shell script $utils_sh não existe.
  Esse arquivo possui as funções utilitárias necessárias.
  Impossível continuar!"
  exit 1
fi


# Obtém o diretório do script
#ROOT_DIR=$(dirname "$(realpath "$BASH_SOURCE")")
ROOT_DIR=$(pwd -P)
echo_info "ROOT_DIR: $ROOT_DIR"

PROJECT_NAME=$(basename $ROOT_DIR)
DEFAULT_BASE_DIR="$ROOT_DIR/$PROJECT_NAME"

_CURRENT_FILE_NAME=$(basename $0)
CURRENT_FILE_NAME="${_CURRENT_FILE_NAME%.*}"
CURRENT_FILE_NAME_PATH="$ROOT_DIR/$CURRENT_FILE_NAME.sh"

##############################################################################
### FUÇÕES UTILITÁRIAS
##############################################################################

function get_server_name() {
  local _input="$1"

  # Verifique se a entrada está vazia
  if [ -z "$_input" ]; then
    return 1
  fi

  _service_name_parse=$(dict_get "$_input" "${DICT_ARG_SERVICE_PARSE[*]}")
  echo "${_service_name_parse:-$_input}"
}

# Função para verificar se o serviço existe
function check_service_validity() {
  local arg_count=$1
  local services_local=("$2")
  local specific_commands_local=("$3")

  # As variáveis de erro são passadas por referência
  local -n error_danger_message=$4
  local -n error_warning_message=$5

  if ! in_array "$ARG_SERVICE" "${services_local[*]}"; then
    error_danger_message="Serviço [$ARG_SERVICE] não existe."
    error_warning_message="Serviços disponíveis: ${services_local[*]}"
    return 1 # falha - serviço não existe
  else
    return 0 # sucesso - serviço existe
  fi
}

# Função para verificar a validade do comando
function check_command_validity() {
  local arg_count=$1
  local specific_commands_local=("$2")
  local all_commands_local=("$3")
  local service_exists=$4

  # As variáveis de erro são passadas por referência
  local -n error_danger_message=$5
  local -n error_warning_message=$6

  if [ "$service_exists" -eq 0 ] && [ "$arg_count" -ge 2 ]; then
    if ! in_array "$ARG_COMMAND" "${all_commands_local[*]}"; then
      error_danger_message="Comando [$ARG_COMMAND] não existe para o serviço [$ARG_SERVICE]."
      error_warning_message="Comandos disponíveis: \n\t\tcomuns: ${COMMANDS_COMUNS[*]} \n\t\tespecíficos: ${specific_commands_local[*]}"
      return 1 # Falha, comando não é valido
    fi
  fi
  return 0 # Sucesso, comando válido
}

# Função para verificar e validar argumentos
function verify_arguments() {
  local arg_count=$1
  # Copia os argumentos para um array local
  local services_local=("$2")
  local specific_commands_local=("$3")
  local all_commands_local=("$4")

  # As variáveis de erro são passadas por referência
  local -n error_message_danger=$5
  local -n error_message_warning=$6

  # Verifica se o serviço existe
  check_service_validity "$arg_count" "${services_local[*]}" "${specific_commands_local[*]}" error_message_danger error_message_warning
  local _service_ok=$?


  if [ $arg_count -eq 0 ]; then
    error_message_danger="Argumento [NOME_SERVICO] não informado."
    error_message_warning="Serviços disponíveis: ${services_local[@]}"
    return 1
  elif [ $arg_count -eq 1 ]; then
    if [ $_service_ok -eq 0 ]; then # serviço existe
      error_message_danger="Argumento [COMANDOS] não informado."
      error_message_warning="Service $ARG_SERVICE\n\tComandos disponíveis: \n\t\tcomuns: ${COMMANDS_COMUNS[*]} \n\t\tespecíficos: ${specific_commands_local[*]}"
    fi
    return 1 # falha
  elif [ $arg_count -eq 2 ]; then
    # Verifica validade do comando
    check_command_validity "$arg_count" "${specific_commands_local[*]}" "${all_commands_local[*]}" "$_service_ok" error_message_danger error_message_warning
    local _command_ok=$?
    if [ $_command_ok -eq 0 ]; then
      return 0 # sucesso
    fi
    return 1 # falha
  fi
  return 0 #sucesso
}

function imprimir_orientacao_uso() {
  local __usage="
  Usar: $CURRENT_FILE_NAME [NOME_SERVICO] [COMANDOS] [OPCOES]
  Nome do serviço:
    all                         Representa todos os serviços
    web                         Serviço rodando a aplicação SUAP
    db                          Serviço rodando o banco PostgreSQL
    pgadmin                     [Só é iniciado sob demanda]. Deve ser iniciado após o *db* , usar o endereço http://localhost:8001 , usuário **admin@pgadmin.org** , senha **admin** .
    redis                       Serviço rodando o cache Redis
    celery                      [Só é iniciado sob demanda]. Serviço rodando a aplicacão SUAP ativando a fila de tarefa assíncrona gerenciada pelo Celery

  Comandos:

    Comando comuns: Comandos comuns a todos os serciços, exceto **all**
      up                        Sobe o serviço [NOME_SERVICO] em **foreground**
      down                      Para o serviço [NOME_SERVICO]
      restart                   Para e reinicar o serviço [NOME_SERVICO] em **background**
      exec                      Executar um comando usando o serviço [NOME_SERVICO] já subido antes, caso não tenha um container em execução, o comando é executado em em um novo container
      run                       Executa um comando usando a imagem do serviço [NOME_SERVICO] em um **novo** serviço
      logs                      Exibe o log do serviço [NOME_SERVICO]
      shell                     Inicia o shell (bash) do serviço [NOME_SERVICO]

    Comandos específicos:

      all:
        deploy                  Implanta os serviços, deve ser executado no primeiro uso, logo após o
        undeploy                Para tudo e apaga o banco, útil para quando você quer fazer um reset no ambiente
        redeploy                Faz um **undeploy** e um **deploy**
        status                  Lista o status dos serviços
        restart                 Reinicia todos os serviços em ****background***
        logs                    Mostra o log de todos os serviços
        up                      Sobe todos os serviços em **foreground**
        down                    Para todos os serviços

      web:
        build                Constrói a imagem da aplicação web
        makemigrations       Executa o **manage.py makemigrations**
        manage               Executa o **manage.py**
        migrate              Executa o **manage.py migrate**
        shell_plus           Executa o **manage.py shell_plus**
        debug                Inicia um serviço com a capacidade de usar o **breakpoint()** para **debug**

      db:
        psql                 Executa o comando **psql** no serviço
        wait                 Prende o console até que o banco suba, útil para evitar executar **migrate** antes que o banco tenha subido completamente
        dump               Realiza o dump do banco no arquivo $DIR_DUMP/$POSTGRES_DB.sql.gz
        restore              Restaura o banco do arquivo *.sql ou *.gz que esteja no diretório $DIR_DUMP

  Opções: faz uso das opções disponíveis para cada [COMANDOS]

  ˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆˆ
  "
  echo_info "$__usage"
}

# Função para imprimir erros
function print_error_messages() {
  local error_danger_message=$1
  local error_info_message=$2

  if [ ! -z "$error_info_message" ]; then
    imprimir_orientacao_uso
    echo_error "$error_danger_message"
    echo_warning "$error_info_message

    Usar: $CURRENT_FILE_NAME [NOME_SERVICO] [COMANDOS] [OPCOES]
    Role para cima para demais detalhes dos argumentos [NOME_SERVICO] [COMANDOS] [OPCOES]
    "
    exit 1
  fi
}

# Função para processar o comando com base no serviço e argumentos
function process_command() {
  local arg_count=$1
  local service_exists=$2
  _service_name=$(get_server_name "${ARG_SERVICE}")

  if [ "$ARG_COMMAND" = "up" ]; then
    service_up "${_service_name}" "$ARG_OPTIONS"
  elif [ "$ARG_COMMAND" = "down" ]; then
    service_down "${_service_name}" "$ARG_OPTIONS"
  elif [ "$ARG_COMMAND" = "restart" ]; then
    service_restart "${_service_name}" "$ARG_OPTIONS"
  elif [ "$ARG_COMMAND" = "exec" ]; then
    service_exec "${_service_name}" "$ARG_OPTIONS"
  elif [ "$ARG_COMMAND" = "run" ]; then
    service_run "${_service_name}" "$ARG_OPTIONS"
  elif [ "$ARG_COMMAND" = "logs" ]; then
    service_logs "${_service_name}" "$ARG_OPTIONS"
  elif [ "$ARG_COMMAND" = "shell" ]; then
    service_shell "${_service_name}" "$ARG_OPTIONS"

  #for all containers
  elif [ "$ARG_COMMAND" = "status" ]; then
    service_status "${_service_name}" "$ARG_OPTIONS"
  elif [ "$ARG_COMMAND" = "undeploy" ]; then
    service_undeploy "${_service_name}" "$ARG_OPTIONS"
  elif [ "$ARG_COMMAND" = "deploy" ]; then
    service_deploy "${_service_name}" "$ARG_OPTIONS"
  elif [ "$ARG_COMMAND" = "redeploy" ]; then
    service_redeploy "${_service_name}" "$ARG_OPTIONS"

  #for db containers
  elif [ "$ARG_COMMAND" = "psql" ]; then
    command_db_psql "${_service_name}" "$ARG_OPTIONS"
  elif [ "$ARG_COMMAND" = "restore" ]; then
    database_db_restore "${_service_name}" "$ARG_OPTIONS"
  elif [ "$ARG_COMMAND" = "dump" ]; then
    database_db_dump "${_service_name}" "$ARG_OPTIONS"
  elif [ "$ARG_COMMAND" = "copy" ]; then
    database_db_scp "${_service_name}" "$ARG_OPTIONS"

  #for web containers
  elif [ "$ARG_COMMAND" = "build" ]; then
    service_web_build "${_service_name}" "$ARG_OPTIONS"
  elif [ "$ARG_COMMAND" = "manage" ]; then
    command_web_django_manage "${_service_name}" "$ARG_OPTIONS"
  elif [ "$ARG_COMMAND" = "makemigrations" ]; then
    command_web_django_manage "${_service_name}" makemigrations "$ARG_OPTIONS"
  elif [ "$ARG_COMMAND" = "migrate" ]; then
    command_web_django_manage  "${_service_name}" "migrate" "$ARG_OPTIONS"
  elif [ "$ARG_COMMAND" = "shell_plus" ]; then
    command_web_django_manage "${_service_name}" "shell_plus" "$ARG_OPTIONS"
  elif [ "$ARG_COMMAND" = "debug" ]; then
    command_web_django_debug "${_service_name}" "$ARG_OPTIONS"
  elif [ "$ARG_COMMAND" = "pre-commit" ]; then
    command_pre_commit "${_service_name}" "$ARG_OPTIONS"
  elif [ "$ARG_COMMAND" = "git" ]; then
    command_git "${_service_name}" "$ARG_OPTIONS"
  else
    echo_warning "Comando $ARG_COMMAND sem função associada"
  fi
}

##############################################################################
### EXPORTANDO VARIÁVEIS DE AMBIENTE DO ARQUIVO $DOCKER_DEV_DIR/.env
##############################################################################

if [ ! -f "$DOCKER_DEV_DIR/.env.dev.sample" ]; then
  echo_error "Arquivo $DOCKER_DEV_DIR/.env.dev.sample não existe. Impossível continuar!"
  exit 1
fi

# Verifica se o arquivo $DOCKER_DEV_DIR/.env NÃO EXISTE. Se sim, procede com a cópia
if [ ! -f "$DOCKER_DEV_DIR/.env" ]; then
  echo ">>> cp $DOCKER_DEV_DIR/.env.dev.sample  $DOCKER_DEV_DIR/.env"
  cp "$DOCKER_DEV_DIR/.env.dev.sample" $DOCKER_DEV_DIR/.env
fi

sleep .5

# exportar as variáveis de ambiente presentes no arquivo .env, o que permite que o bash
# reconheça as variáveis no ambiente de execução.
# O conteúdo multilinha (como a variável SERVICES_DEPENDENCIES) pode não ser corretamente
# interpretado devido ao formato de leitura do xargs.
export $(xargs -0 < $DOCKER_DEV_DIR/.env) 2> /dev/null
# Carrega o conteúdo do arquivo .env diretamente no script, permitindo que variáveis com múltiplas linhas,
# como SERVICES_DEPENDENCIES, sejam interpretadas corretamente, preservando a formatação.
source $DOCKER_DEV_DIR/.env 2>/dev/null

imprime_variaveis_env() {
  while IFS= read -r line; do
    # Ignora linhas em branco ou comentários
    if [[ -n "$line" && "$line" != \#* ]]; then
      # Extrai o nome da variável e o valor, com base no formato "chave=valor"
      var_name=$(echo "$line" | cut -d'=' -f1)
      var_value=$(echo "$line" | cut -d'=' -f2-)

      # Verifica se o nome da variável é válido
      # operador =~ é utilizado no Bash para realizar uma comparação com expressão regular.
      if [[ "$var_name" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]]; then
          echo "$var_name=$var_value"
#        fi
      else
        # Se o nome da variável for inválido, apenas exibe a linha lida
         echo "$var_name"
      fi
    fi
  done <"$DOCKER_DEV_DIR/.env"
}
#imprime_variaveis_env
# ver apenas as variáveis definidas no próprio script,
#set


# ver todas as variáveis, incluindo as variáveis locais e as de ambiente no script,
#declare -p
  # declare -x:
  #Função: Exporta a variável, tornando-a disponível para processos filhos.
  #Exemplo: declare -x VAR="value" faz com que VAR seja visível para qualquer processo que o script iniciar.
  #
  #declare -i:
  #Função: Faz com que a variável seja tratada como um inteiro (número).
  #Exemplo: declare -i NUM=10 significa que NUM só aceitará valores inteiros. Se você tentar atribuir um valor não numérico, ele será interpretado como zero.
  #
  #declare --:
  #Função: Usado para marcar o fim das opções, útil quando uma variável pode começar com um -. Isso impede que o Bash interprete o valor da variável como uma opção de comando.
  #Exemplo: declare -- VAR="value" assegura que "VAR" não será tratado como uma opção.
  #
  #declare -r:
  #Função: Torna a variável somente leitura. Não pode ser alterada após sua atribuição.
  #Exemplo: declare -r VAR="value" significa que você não pode modificar VAR posteriormente.
  #
  #declare -ir:
  #Função: Combina as opções -i e -r, tornando a variável um número inteiro e somente leitura.
  #Exemplo: declare -ir NUM=100 significa que NUM é um inteiro e não pode ser modificado.
  #
  #declare -a:
  #Função: Define a variável como um array indexado numericamente.
  #Exemplo: declare -a ARRAY define ARRAY como um array, permitindo atribuir e acessar valores como ARRAY[0], ARRAY[1], etc.
  #
  #declare -A:
  #Função: Define a variável como um array associativo (ou hash), onde as chaves podem ser strings.
  #Exemplo: declare -A HASH permite que você use chaves do tipo string, como HASH["key"]="value".
  #
  #declare -ar:
  #Função: Define a variável como um array somente leitura.
  #Exemplo: declare -ar ARRAY significa que o array ARRAY não pode ser alterado após sua criação.

##############################################################################
### CONVERTENDO ARRAY DO .ENV NA TAD DICT
##############################################################################
# String multilinha SERVICES_DEPENDENCIES: Quando uma string multilinha como SERVICES_DEPENDENCIES é usada em uma
# iteração (for e in ${SERVICES_DEPENDENCIES[@]}; do), o Bash separa cada linha e trata-a como um único item.
# Como o valor de SERVICES_DEPENDENCIES tem quebras de linha, ele trata cada linha como uma entrada.
#
# Array DICT_SERVICES_DEPENDENCIES: Já o array DICT_SERVICES_DEPENDENCIES contém exatamente os mesmos elementos que foram
# adicionados de forma explícita no loop anterior.
# Como cada linha de SERVICES_DEPENDENCIES foi adicionada como um item separado ao array, o comportamento na iteração
# também será o mesmo, porque o array contém os mesmos elementos que estavam nas linhas da string.
#
# Com array, podemos fazer as seguintes operações
# 1. Acesso a Elementos Específicos: echo "${DICT_SERVICES_DEPENDENCIES[0]}"
# 2. Iteração Elemento por Elemento:
# 3. Adicionar ou Remover Elementos: DICT_SERVICES_DEPENDENCIES+=("new_service")
# 4. Substituição de Elementos Específicos: DICT_SERVICES_DEPENDENCIES[1]="new_value"
# 5. Verificar o Número de Elementos: echo "Total de serviços: ${#DICT_SERVICES_DEPENDENCIES[@]}"
# 6. Ordenação: IFS=$'\n' sorted=($(sort <<<"${DICT_SERVICES_DEPENDENCIES[*]}"))

# Declarações das variáveis de arrays
DICT_COMPOSES_FILES=()
DICT_SERVICES_COMMANDS=()
DICT_SERVICES_DEPENDENCIES=()
DICT_ARG_SERVICE_PARSE=()

#Conversão das string multilinhas para array
convert_multiline_to_array "$COMPOSES_FILES" DICT_COMPOSES_FILES
convert_multiline_to_array "$SERVICES_COMMANDS" DICT_SERVICES_COMMANDS
convert_multiline_to_array "$SERVICES_DEPENDENCIES" DICT_SERVICES_DEPENDENCIES
convert_multiline_to_array "$ARG_SERVICE_PARSE" DICT_ARG_SERVICE_PARSE

##############################################################################
### Funções para trabalhar com os arrays
##############################################################################

get_service_names() {
  # Função que retorna um array de nomes de serviços (excluindo "all")
  local _services=($(dict_keys "${DICT_SERVICES_COMMANDS[*]}"))
  local result=()

  for (( idx=${#_services[@]}-1 ; idx>=0 ; idx-- )); do
    local _name_service=${_services[$idx]}
    local _service_name_parse=$(dict_get $_name_service "${DICT_ARG_SERVICE_PARSE[*]}")

    for _parsed_service in ${_service_name_parse[*]}; do
      _name_service=$_parsed_service
    done

    # Adicionar ao array apenas se o nome do serviço não for "all"
    if [ "$_name_service" != "all" ]; then
      result+=("$_name_service")
    fi
  done

  echo "${result[@]}"  # Retorna o array de nomes
}

##############################################################################
### DEFINIÇÕES DE VARIÁVEIS GLOBAIS
##############################################################################

COMMANDS_COMUNS=(up down restart exec run logs shell)

POSTGRES_DB=${DATABASE_NAME:-$POSTGRES_DB}
POSTGRES_USER=${DATABASE_USER:-$POSTGRES_USER}
POSTGRES_PASSWORD=${DATABASE_PASSWORD:-$POSTGRES_PASSWORD}
POSTGRES_HOST=${DATABASE_HOST:-$POSTGRES_HOST}
POSTGRES_PORT=${DATABASE_PORT:-$POSTGRES_PORT}

POSTGRESQL="postgresql://$POSTGRES_USER:$POSTGRES_PASSWORD@$POSTGRES_HOST:$POSTGRES_PORT/"
#echo "$POSTGRESQL"

POSTGRES_DUMP_DIR=${DATABASE_DUMP_DIR:-docker/dump}
DIR_DUMP=${POSTGRES_DUMP_DIR:-docker/dump}

ARG_SERVICE="$1"
ARG_COMMAND="$2"
ARG_OPTIONS="${@:3}"
SERVICE_NAME=$(get_server_name "${ARG_SERVICE}")
SERVICE_WEB_NAME=$(get_server_name "web")
SERVICE_DB_NAME=$(get_server_name "db")

BASE_DIR=${BASE_DIR:-$DEFAULT_BASE_DIR}
if [ ! -d "$BASE_DIR" ]; then
  echo_error "Diretório base do projeto $BASE_DIR não existe.!"
  echo_warning "Defina o nome dele na variável \"BASE_DIR\" em \"$DOCKER_DEV_DIR/.env\""
  exit 1
fi
#echo "ARG_SERVICE = $ARG_SERVICE"
#echo "ARG_COMMAND = $ARG_COMMAND"
#echo "ARG_OPTIONS = $ARG_OPTIONS"
#echo "SERVICE_NAME = $SERVICE_NAME"
#echo "SERVICE_WEB_NAME = $SERVICE_WEB_NAME"
#echo "SERVICE_DB_NAME = $SERVICE_DB_NAME"
#echo "PROJECT_NAME = $PROJECT_NAME"
#echo "BASE_DIR = $BASE_DIR"

file_env_revisado=${REVISADO:-0}
#Se não existir o arquivo $DOCKER_DEV_DIR/.env, copie de $CURRENT_DIRECTORY/.env.dev.sample
if [ "$file_env_revisado" -eq 0 ]; then
  imprime_variaveis_env
  echo_warning "Acima segue TODO os valores das variáveis definidas no arquivo \"$DOCKER_DEV_DIR/.env\"."
  echo_warning "Segue abaixo as princípais variáveis:"
  echo_warning "\tVariável de configuração de caminho de arquivos:"
  echo_warning "\t\tDATABASE_DUMP_DIR = $DIR_DUMP;"
  echo_warning "\t\t[OPCIONAL] VPN_WORKDIR = $VPN_WORKDIR;"
  echo_warning "\t\tFILE_REQUIREMENTS_TXT = $FILE_REQUIREMENTS_TXT;"

  echo_warning "\tVariável de configuração de banco:"
  echo_warning "\t\tDATABASE_NAME = $DATABASE_NAME;"
  echo_warning "\t\tDATABASE_HOST = $DATABASE_HOST;"
  echo_warning "\t\tDATABASE_PORT = $DATABASE_PORT;"
  echo_warning "\t\tDATABASE_USER = $DATABASE_USER;"
  echo_warning "\t\tDATABASE_PASSWORD = $DATABASE_PASSWORD;"

  echo_warning "\tDemais varíaveis:"
  echo_warning "\t\tDJANGO_PROJECT_NAME: $PROJECT_NAME"
  echo_warning "Antes de prosseguir, revise o conteúdo das variáveis apresentadas acima."
  echo_warning "Altere o valor da variável \"REVISADO=$REVISADO\" para 1 para prosseguir"
  echo_warning "Tecle [ENTER] para continuar"
  read
fi

##############################################################################
### Início do tratamento para recuperar os arquivos docker-compose
##############################################################################

#ln -sf $CURRENT_FILE_NAME_PATH /usr/local/bin/container

_services=($(dict_keys "${DICT_SERVICES_COMMANDS[*]}"))
_composes_files=()

for s in ${_services[*]}; do
  _file=$(dict_get "$s" "${DICT_COMPOSES_FILES[*]}")
  if [ ! -z "$_file" ]; then
    _composes_files+=("-f $DOCKER_DEV_DIR/$_file")
  fi
done

COMPOSE="docker compose ${_composes_files[*]}"

#### fim

##############################################################################
### COPIANDO ARQUIVOS NECESSÁRIOS
##############################################################################
if [ ! -f "$DOCKER_DEV_DIR/.env.dev.sample" ]; then
  echo_error "Arquivo $DOCKER_DEV_DIR/.env.dev.sample não existe. Impossível continuar!"
  exit 1
fi

file_requirements_txt=${FILE_REQUIREMENTS_TXT:-"requirements.txt")}

settings_sample_local_file="${SETTINGS_SAMPLE_LOCAL_FILE:-settings_sample.py}"
if [ ! -f "$BASE_DIR/$settings_sample_local_file" ]; then
  echo_warning "Arquivo $BASE_DIR/$settings_sample_local_file não existe.!"
  echo_warning "Defina o nome dele na variável \"SETTINGS_SAMPLE_LOCAL_FILE\" em \"$DOCKER_DEV_DIR/.env\""
  echo_warning "Tecle [ENTER] para continuar."
  read
fi

settings_local_file="${SETTINGS_LOCAL_FILE:-settings.py}"
if [ ! -f "$BASE_DIR/$settings_local_file" ]; then
  echo_warning "Arquivo $BASE_DIR/$settings_local_file não existe.!"
  echo_warning "Defina o nome dele na variável \"SETTINGS_LOCAL_FILE\" em \"$DOCKER_DEV_DIR/.env\""
  echo_warning "Tecle [ENTER] para continuar."
  read
fi

if [ ! -f "$BASE_DIR/$settings_sample_local_file" ]; then
  echo ">>> cp $BASE_DIR/$settings_sample_local_file $BASE_DIR/$settings_local_file"
  cp "$BASE_DIR/$settings_sample_local_file" "$BASE_DIR/$settings_local_file"
fi


if [ ! -f "$DOCKER_DEV_DIR/scripts/init_database.sh" ]; then
  echo_warning "Arquivo $DOCKER_DEV_DIR/scripts/init_database.sh não existe. Sem ele, torna-se impossível realizar dump ou restore do banco.!"
  echo_warning "Tecle [ENTER] para continuar."
  read
fi

##############################################################################
### FUNÇÕES RESPONSÁVEIS POR INSTACIAR OS SERVIÇOS
##############################################################################
function check_option_d() {
  local _option="$1"

  if [[ $_option =~ "-d" ]]; then
    return 0  # Verdadeiro (True)
  else
    return 1  # Falso (False)
  fi
}

function is_container_running() {
  # usar:
  # if ! is_container_running "$_service_name"; then
  # ...
  # fi
  local _service_name="$1"
  echo ">>> ${FUNCNAME[0]} $_service_name"

  # Verifica se o container está rodando
  if ! $COMPOSE ps | grep -q "${_service_name}.*Up"; then
    echo_warning "O container \"$_service_name\" não está inicializado."
    return 1
  fi
  return 0
}

function container_failed_to_initialize() {
  local exit_code=$?
  local _option="${@:2}"
  local _service_name=$1

  echo ">>> ${FUNCNAME[0]} $_service_name $_option"

  declare -a _name_services
  dict_get_and_convert "$_service_name" "${DICT_SERVICES_DEPENDENCIES[*]}" _name_services

  if [ $exit_code -ne 0 ]; then
      # Exibe a mensagem de erro e interrompe a execução do script
      echo_error "Falha ao inicializar o container."

      echo_warning "Parando todos os serviços dependentes de $_service_name que estão em execução ..."
      for _nservice in "${_name_services[@]}"; do
        service_stop "$_nservice" "$_option"
      done
      service_stop "$_service_name" "$_option"
      exit 1 # falha ocorrida
  fi
}

function service_run() {
  local _service_name="$1"
  shift # Remover o primeiro argumento posicional ($1) -- Remove o nome do serviço da lista de argumentos
  local _option="$@"
  echo ">>> ${FUNCNAME[0]} $_service_name $_option"

  if [ "$_service_name" = "$SERVICE_WEB_NAME" ]; then
    echo ">>> $COMPOSE run --rm $_service_name $_option"
    $COMPOSE run --rm "$_service_name" $_option
  else
    echo ">>> $COMPOSE run $_service_name $_option"
    $COMPOSE run "$_service_name" $_option
  fi
}

function service_web_exec() {
  local _option="${@:2}"
  local _service_name=$1
  echo ">>> ${FUNCNAME[0]} $_service_name $_option"

  if [ "$(docker container ls | grep ${COMPOSE_PROJECT_NAME}-${_service_name}-1)" ]; then
    echo ">>> $COMPOSE exec $_service_name $_option"
    $COMPOSE exec "$_service_name" $_option
  else
    echo_warning "O serviço não está em execução"
  fi
}

function _service_exec() {
  local _service_name="$1"
  shift # Remover o primeiro argumento posicional ($1) -- Remove o nome do serviço da lista de argumentos
  local _option="$@"
  echo ">>> ${FUNCNAME[0]} $_service_name $_option"

#  if [ "$(docker container ls | grep "${COMPOSE_PROJECT_NAME}-${_service_name}-1")" ]; then
  if docker container ls | grep -q "${COMPOSE_PROJECT_NAME}-${_service_name}-1"; then
    if [ "$ARG_SERVICE" = "pgadmin" ]; then
      _option=$(echo "$_option" | sed 's/bash/\/bin\/sh/')
    fi
    echo ">>> $COMPOSE exec $_service_name $_option"
    $COMPOSE exec "$_service_name" $_option
  else
    service_run "$_service_name" $_option
  fi
}

function service_exec() {
  local _service_name="$1"
  shift # Remover o primeiro argumento posicional ($1) -- Remove o nome do serviço da lista de argumentos
  local _option="$@"
  echo ">>> ${FUNCNAME[0]} $_service_name $_option"

  if [ "$ARG_SERVICE" = "$SERVICE_WEB_NAME" ]; then
    service_web_exec "$_service_name" $_option
  else
    _service_exec "$_service_name" $_option
  fi
}

function service_shell() {
  local _option="${@:2}"
  local _service_name=$1
  echo ">>> ${FUNCNAME[0]} "$_service_name" $_option"

  if ! is_container_running "$_service_name"; then
    echo_error "Container $_service_name não está em execução!"
  fi

  if [[ $(docker container ls | grep ${COMPOSE_PROJECT_NAME}-${_service_name}-1) ]]; then
    service_exec "$_service_name" bash $_option
  else
    service_run "$_service_name" bash $_option
  fi

  #OCI runtime exec failed: exec failed: container_linux.go:380: starting container process caused: exec: "bash": executable file not found in $PATH: unknown
}

function service_logs() {
  local _option="${@:2}"
  local _service_name=$1
  echo ">>> ${FUNCNAME[0]} "$_service_name" $_option"

  if [ "$_service_name" = "all" ]; then
    echo_info "Status dos serviços"
    $COMPOSE logs -f $_option
  else
    if ! is_container_running "$_service_name"; then
      echo_error "Container $_service_name não está em execução!"
    fi
    $COMPOSE logs -f $_option "$_service_name"
  fi
}

function service_stop() {
  local _option="${@:2}"
  local _service_name=$1
  echo ">>> ${FUNCNAME[0]} $_service_name $_option"

  # Para o segundo caso com _service_name
  declare -a _name_services
  dict_get_and_convert "$_service_name" "${DICT_SERVICES_DEPENDENCIES[*]}" _name_services

  for _name_service in "${_name_services[@]}"; do
    if [[ $(docker container ls | grep ${COMPOSE_PROJECT_NAME}-${_service_name}-1) ]]; then
      echo ">>> docker stop ${COMPOSE_PROJECT_NAME}-${_service_name}-1"
      docker stop ${COMPOSE_PROJECT_NAME}-${_service_name}-1
    fi
  done
    if [[ $(docker container ls | grep ${COMPOSE_PROJECT_NAME}-${_service_name}-1) ]]; then
      echo ">>> docker stop ${COMPOSE_PROJECT_NAME}-${_service_name}-1"
      docker stop ${COMPOSE_PROJECT_NAME}-${_service_name}-1
    fi
}

function service_db_wait() {
  local _service_name=$SERVICE_DB_NAME
  local host
  local port

  echo ">>> ${FUNCNAME[0]} $_service_name $_option"

  echo "--- Aguardando a base de dados ..."

  # Chamar a função para obter o host e a porta correta
  _return_func=1

  echo ">>> [LOOP] $COMPOSE exec -T $SERVICE_DB_NAME bash -c \"source /scripts/utils.sh && get_host_port '$POSTGRES_HOST' '$POSTGRES_PORT' '$POSTGRES_USER' '$POSTGRES_DB' '*********'\""
  # Loop until para continuar tentando até que _return_func seja igual a 1
  until [ $_return_func -eq 0 ]; do
    echo_warning "Tentando conectar ao banco de dados..."
    # Executa o comando dentro do contêiner
    psql_output=$($COMPOSE exec -T "$SERVICE_DB_NAME" bash -c "source /scripts/utils.sh && get_host_port '$POSTGRES_HOST' '$POSTGRES_PORT' '$POSTGRES_USER' '$POSTGRES_DB' '$POSTGRES_PASSWORD'")
    _return_func=$?

    # Se a função retornar com sucesso (_return_func igual a 1)
    if [ $_return_func -eq 0 ]; then
      # Extrai o host e a porta do output
      read -r host port <<< "$psql_output"
    fi

    # Pequena pausa antes de tentar novamente (opcional)
    sleep 2
  done

  psql_command="psql -v ON_ERROR_STOP=1 --host=$host --port=$port --username=$POSTGRES_USER --dbname=$POSTGRES_DB"

  echo ">>> [LOOP] $COMPOSE exec -T $SERVICE_DB_NAME bash -c \"PGPASSWORD=$POSTGRES_PASSWORD $psql_command -tc 'SELECT 1;'\" 2>&1"
  until sql_output=$($COMPOSE exec -T "$SERVICE_DB_NAME" bash -c "PGPASSWORD=$POSTGRES_PASSWORD $psql_command -tc 'SELECT 1;'" 2>&1); do
    psql_output=$(echo "$psql_output" | xargs)  # remove espaços
    echo "Detalhes do erro: $psql_output"
    echo_warning "Postgres não disponível - aguardando... "
    sleep 2
  done

  echo_success "Postgres está pronto e aceitando conexões."
}

function database_db_scp() {
  local _option="${@:2}"
  local _service_name=$SERVICE_DB_NAME
#  local _service_name=$1
  echo ">>> ${FUNCNAME[0]} $_service_name $_option"

  if ! is_container_running "$_service_name"; then
    echo_info "Inicializando o container db automaticamente ..."
    echo ">>> service_up $_service_name $_option -d"
    service_up $_service_name $_option -d
  fi

  service_db_wait

  echo "$COMPOSE exec $_service_name sh -c \"
    apt-get update > /dev/null && apt-get install -y openssh-client > /dev/null
    scp -i /tmp/dbuser.pem dbuser@$DOMAIN_NAME:/var/opt/backups/$DATABASE_REMOTE_HOST.tar.gz /dump/$DATABASE_REMOTE_HOST.tar.gz
    \""
  $COMPOSE exec $_service_name sh -c "
    apt-get update > /dev/null && apt-get install -y openssh-client > /dev/null
    scp -i /tmp/dbuser.pem dbuser@$DOMAIN_NAME:/var/opt/backups/$DATABASE_REMOTE_HOST.tar.gz /dump/$DATABASE_REMOTE_HOST.tar.gz
    "

}

function database_db_dump() {
  local _option="$@"
  local _service_name=$SERVICE_DB_NAME
  echo ">>> ${FUNCNAME[0]} "$_service_name" $_option"

  echo "--- Realizando o dump do banco $POSTGRES_DB ... "

  _psql="psql -h $POSTGRES_HOST -p $POSTGRES_PORT -U $POSTGRES_USER"

  # Definindo a consulta para pegar o tamanho do banco de dados
  psql_cmd="$_psql -d postgres -tc \"SELECT pg_database_size('$POSTGRES_DB');\""

  # Executando o comando dentro do container Docker para obter o tamanho do banco de dados
  result=$($COMPOSE exec -e PGPASSWORD=$POSTGRES_PASSWORD $_service_name sh -c "$psql_cmd")

  # Verificando se a variável result contém um valor válido
  result=$(echo $result | xargs)  # Remove espaços extras

  # Definir o comando pg_dump com pv e gzip
  pg_dump_cmd="pg_dump -U $POSTGRES_USER -h $POSTGRES_HOST -p $POSTGRES_PORT $POSTGRES_DB | \
  pv -c -s $result -N dump | \
  gzip > /dump/$POSTGRES_DB.sql.gz"

  if is_container_running "$_service_name"; then
    echo ">>> Executando: $COMPOSE exec -e PGPASSWORD=$POSTGRES_PASSWORD $_service_name sh -c \"$pg_dump_cmd\""
    $COMPOSE exec -e PGPASSWORD="$POSTGRES_PASSWORD" $_service_name sh -c "
    apt-get update && apt-get install -y pv gzip &&
    $pg_dump_cmd"
  else
    $COMPOSE run -e PGPASSWORD="$POSTGRES_PASSWORD" $_service_name sh -c "
    apt-get update && apt-get install -y pv gzip &&
    $pg_dump_cmd"
  fi

  echo ">>> service_exec $_service_name chmod 644 /dump/$POSTGRES_DB.sql.gz"
  service_exec "$_service_name" chmod 644 /dump/$POSTGRES_DB.sql.gz

  # Verifica se o código de saída do comando anterior foi executado com falha
  if [ $? -ne 0 ]; then
    echo_warning "Falha ao restaurar dump do banco $POSTGRES_DB"
  else
    echo_info "Backup realizado com sucesso!"
  fi
}

function database_wait() {
  local _service_name=$SERVICE_DB_NAME
  echo ">>> ${FUNCNAME[0]} "$_service_name" $_option"

  service_db_wait

  # Chamar a função para obter o host e a porta correta
  echo ">>> $COMPOSE exec -T $SERVICE_DB_NAME bash -c \"source /scripts/utils.sh && get_host_port '$POSTGRES_HOST' '$POSTGRES_PORT' '$POSTGRES_USER' '$POSTGRES_DB' '*********'\""
  psql_output=$($COMPOSE exec -T "$SERVICE_DB_NAME" bash -c "source /scripts/utils.sh && get_host_port '$POSTGRES_HOST' '$POSTGRES_PORT' '$POSTGRES_USER' '$POSTGRES_DB' '$POSTGRES_PASSWORD'")
  _return_func=$?
  if [ $_return_func -eq 0 ]; then
    read host port <<< $psql_output
  else
    echo_error "Não foi possível conectar ao banco de dados."
    exit 1
  fi

  local _psql="psql -h $host -p $port -U $POSTGRES_USER -d $POSTGRES_DB"

  # Definindo o comando psql para verificar a presença de migrações
  local psql_cmd="$_psql -tc 'SELECT COUNT(*) > 0 FROM django_migrations;'"

  echo "--- Aguardando o banco de dados ficar pronto..."
  # Loop até que a consulta retorne verdadeiro (ou seja, 't')
  echo ">>> [LOOP] $COMPOSE exec -e PGPASSWORD=********* $SERVICE_DB_NAME  sh -c  $psql_cmd  | grep -q 't'"
  until psql_output=$($COMPOSE exec -e PGPASSWORD=$POSTGRES_PASSWORD "$SERVICE_DB_NAME" sh -c "$psql_cmd" | grep -q 't'); do
    psql_output=$(echo "$psql_output" | xargs)  # remove espaços
    echo "Detalhes do erro: $psql_output"
    echo_warning "O banco de dados ainda não está pronto, aguardando... "
    sleep 2
  done
  echo_success "Banco de dados $POSTGRES_DB está pronto para uso."
}

function database_db_restore() {
  local _service_name=$SERVICE_DB_NAME
  echo ">>> ${FUNCNAME[0]} $_service_name $_option"

  if ! is_container_running "$_service_name"; then
    echo_info "Inicializando o container db automaticamente ..."
    echo ">>> service_up $_service_name $_option -d"
    service_up $_service_name $_option -d
  fi

  service_db_wait

  service_exec "$_service_name" touch /dump/restore.log
  service_exec "$_service_name" chmod 777 /dump/restore.log

  local _success=0
  local _retorno_func=0
  echo "--- Iniciando processo de restauração do dump ..."


  service_exec "$_service_name" /docker-entrypoint-initdb.d/init_database.sh

  # Verifica o código de saída do comando anterior foi executado com sucesso
  _retorno_func=$?
  echo "Código de retorno:  $_retorno_func"
  if [ "$_retorno_func" -eq 0 ]; then
    _success=1
    echo_success "A restauração foi realizada com sucesso!"
    echo ""
    echo "Deseja visualizar o arquivo de log gerado? (Digite 's' para sim ou qualquer digite qualquer tecla para finalizar.)"
    read resposta

    if [ "$resposta" = "s" ]; then
      cat "$DIR_DUMP/restore.log"
    fi
  else
    echo_error "Falha ao executar $DOCKER_DEV_DIR/scripts/init_database.sh"
  fi
  #  else
  #    echo "Arquivo de dump não encontrado."
  #  fi
  return $_success

}

function _service_db_up() {
  local _option="${@:2}"
  local _service_name=$1
  echo ">>> ${FUNCNAME[0]} $_service_name $_option"

  if [[ $(docker container ls | grep ${COMPOSE_PROJECT_NAME}-${_service_name}-1) ]]; then
    echo_warning "O container Postgres já está em execução"
  else
    echo "$COMPOSE up $_option $_service_name"
    $COMPOSE up $_option $_service_name
    container_failed_to_initialize $_service_name $_option
  fi

  if [ "$_service_name" != "db" ] && is_container_running "$_service_name"; then
    service_db_wait
  fi

}

function command_web_django_manage() {
  local _service_name="$1"
  shift # Remover o primeiro argumento posicional ($1) -- Remove o nome do serviço da lista de argumentos
  local _option="$@"
  echo ">>> ${FUNCNAME[0]} $_service_name $_option"

  database_wait

  if [[ $(docker container ls | grep ${COMPOSE_PROJECT_NAME}-${_service_name}-1) ]]; then
    service_exec "$_service_name" python manage.py $_option
  else
    service_run "$_service_name" python manage.py $_option
  fi
}

function command_web_django_debug() {
  local _service_name="$1"
  shift # Remover o primeiro argumento posicional ($1) -- Remove o nome do serviço da lista de argumentos
  local _port="$1"
  shift
  local _option="$*"
  local execucao_liberada=true
  echo ">>> ${FUNCNAME[0]} $_service_name $_port $_option"

  if [ -z "$_port" ]; then
    _port="$APP_PORT"
    echo_warning "Porta não fornecida, usando valor default $_port."
  fi
  if ! check_port "$_port"; then
    echo_error "A porta $_port está em uso. Impossível continuar!"
    echo_info "Execute o comando novamente passando um número de porta diferente ou
    encerre o serviço que está usando essa porta."
    exit 1
  fi

  declare -a _name_services
  get_dependent_services "$SERVICE_WEB_NAME" _name_services
  for _sname in "${_name_services[@]}"; do
    is_container_running "$_sname"
    _return_func=$?
    if [ "$_return_func" -eq 1 ]; then
      execucao_liberada=false
    fi
  done
  if [ "$execucao_liberada" == false ]; then
    echo_warning "Este comando (${_service_name}) depende dos serviços listados acima para funcionar."
    echo_info "Você pode inicializar todos eles subindo o serviço \"${_service_name}\"
    ou subir somente o serviço \"${SERVICE_DB_NAME}\" (<<service docker>> ${SERVICE_DB_NAME} up)."
    exit 99
  fi

  database_wait
  export "APP_PORT=${_port}"
  echo ">>> $COMPOSE run --rm --service-ports $_service_name python manage.py runserver_plus 0.0.0.0:${_port} $_option"
  $COMPOSE run --rm --service-ports "$_service_name" python manage.py runserver_plus 0.0.0.0:${_port} $_option
  export "APP_PORT=${APP_PORT}"
}

function command_pre_commit() {
  local _service_name="$1"
  shift # Remover o primeiro argumento posicional ($1) -- Remove o nome do serviço da lista de argumentos
  local _option="$@"
  echo ">>> ${FUNCNAME[0]} $_service_name $_option"

  if [[ $(docker container ls | grep ${COMPOSE_PROJECT_NAME}-${_service_name}-1) ]]; then
    echo ">>> $COMPOSE exec $_service_name bash -c \"id && git config --global --add safe.directory $WORKDIR && pre-commit run $_option --from-ref origin/master --to-ref HEAD\""
    $COMPOSE exec "$_service_name" bash -c "id && git config --global --add safe.directory $WORKDIR && pre-commit run $_option --from-ref origin/master --to-ref HEAD"
  else
    echo ">>> $COMPOSE run --rm $_service_name \"id && git config --global --add safe.directory $WORKDIR && pre-commit run $_option --from-ref origin/master --to-ref HEAD\""
    $COMPOSE run --rm  "$_service_name" bash -c "id && git config --global --add safe.directory $WORKDIR && pre-commit run $_option --from-ref origin/master --to-ref HEAD"
  fi
}

function command_git() {
  local _service_name="$1"
  shift # Remover o primeiro argumento posicional ($1) -- Remove o nome do serviço da lista de argumentos
  local _option="$@"
  echo ">>> ${FUNCNAME[0]} $_service_name $_option"

  command_pre_commit "${_service_name}"

  if [[ $(docker container ls | grep ${COMPOSE_PROJECT_NAME}-${_service_name}-1) ]]; then
    echo ">>> $COMPOSE exec $_service_name git $_option"
    $COMPOSE exec "$_service_name" git "$_option"
  else
    echo ">>> $COMPOSE run $_service_name git $_option"
    $COMPOSE runt "$_service_name" git "$_option"
  fi
}

function _service_web_up() {
  local _option="${@:2}"
  local _service_name=$1
  echo ">>> ${FUNCNAME[0]} $_service_name $_option"

  database_wait

  echo ">>> $COMPOSE up $_option $_service_name"
  $COMPOSE up $_option $_service_name
  container_failed_to_initialize $_service_name $_option
}

function _service_all_up() {
  local _option="${@:1}"
  echo ">>> ${FUNCNAME[0]} $_option"

  # Chama a função e captura o array retornado
  service_names=($(get_service_names))

  # Itera sobre o array retornado pela função
  for _name_service in "${service_names[@]}"; do
    _service_up $_name_service -d $_option
  done
}

function _service_up() {
  local _option="${@:2}"
  local _service_name="$1"
  echo ">>> ${FUNCNAME[0]} $_service_name $_option"

  if [ $_service_name = "all" ]; then
    _service_all_up $_option
#    $COMPOSE up $_option
  elif [ $_service_name = "db" ]; then
    _service_db_up $_service_name $_option
  elif [ $_service_name = $SERVICE_WEB_NAME ]; then
    _service_web_up $_service_name $_option
  else
    local _nservice=$(get_server_name ${_service_name})
    echo ">>> $COMPOSE up $_option $_nservice"
    $COMPOSE up $_option $_nservice
    container_failed_to_initialize $_service_name $_option
  fi
}

function service_up() {
  local _option="${@:2}"
  local _service_name=$1
#  local _name_services=($(string_to_array $(dict_get "$ARG_SERVICE" "${DICT_SERVICES_DEPENDENCIES[*]}")))

  echo ">>> ${FUNCNAME[0]} $_service_name $_option"

  declare -a _name_services
  dict_get_and_convert "$ARG_SERVICE" "${DICT_SERVICES_DEPENDENCIES[*]}" _name_services

  for _nservice in "${_name_services[@]}"; do
    _service_up $_nservice -d
  done
  _service_up $_service_name $_option
}

function _service_down() {
  local _option="${@:2}"
  local _service_name=$1
  echo ">>> ${FUNCNAME[0]} $_service_name $_option"

  if [ $_service_name = "all" ]; then
    echo ">>> $COMPOSE down --remove-orphans $_option"
    $COMPOSE down --remove-orphans $_option
  else
    if [[ $(docker container ls | grep ${COMPOSE_PROJECT_NAME}-${_service_name}-1) ]]; then
      echo ">>> docker stop ${COMPOSE_PROJECT_NAME}-${_service_name}-1"
      docker stop ${COMPOSE_PROJECT_NAME}-${_service_name}-1

      echo ">>> docker rm ${COMPOSE_PROJECT_NAME}-${_service_name}-1"
      docker rm ${COMPOSE_PROJECT_NAME}-${_service_name}-1
    else
      echo ">>> $COMPOSE down ${_service_name} $_option"
      $COMPOSE down ${_service_name} $_option
    fi
  fi
}

function service_down() {
  local _option="${@:2}"
  local _service_name=$1
  echo ">>> ${FUNCNAME[0]} $_service_name $_option"

  declare -a _name_services
  dict_get_and_convert "$_service_name" "${DICT_SERVICES_DEPENDENCIES[*]}" _name_services

  for _name_service in "${_name_services[@]}"; do
    _service_down $_name_service $_option
  done
  _service_down $_service_name $_option
}

function service_restart() {
  local _option="${@:2}"
  local _service_name=$1
  echo ">>> ${FUNCNAME[0]} $_service_name $_option"

  #  if [ $_service_name = "all" ]; then
  service_down $_service_name $_option
  service_up $_service_name -d $_option
  #  else
  #    service_down $_service_name $_option
  #    service_up $_service_name -d $_option
  #  fi

}

function service_web_build() {
  local _option="${@:2}"
  local _service_name=$1
  echo ">>> ${FUNCNAME[0]} $_service_name $_option"

  echo ">>> $COMPOSE build --no-cache $SERVICE_WEB_NAME $_option"
  $COMPOSE build --no-cache $SERVICE_WEB_NAME $_option
  container_failed_to_initialize $_service_name $_option

  service_up $SERVICE_WEB_NAME $_option
}

function service_deploy() {
  local _option="${@:2}"
  local _service_name=$1
  echo ">>> ${FUNCNAME[0]} $_service_name $_option"
  service_down $_service_name -v $_option
  service_web_build $SERVICE_WEB_NAME $_option
}

function service_redeploy() {
  local _option="${@:2}"
  local _service_name=$1
  echo ">>> ${FUNCNAME[0]} $_service_name $_option"
  service_undeploy
  service_deploy
}

function service_undeploy() {
  local _option="${@:2}"
  local _service_name=$1
  echo ">>> ${FUNCNAME[0]} $_service_name $_option"
  # Opção -v remove todos os volumens atachado
  service_down $_service_name -v $_option

  rm -rf docker/volumes
}

function service_status() {
  local _option="${@:2}"
  local _service_name=$1
  echo ">>> ${FUNCNAME[0]} $_service_name $_option"

  echo ">>> $COMPOSE ps -a"
  $COMPOSE ps -a
}

function command_db_psql() {
  local _option="${@:2}"
  local _service_name=$1
  echo ">>> ${FUNCNAME[0]} $_service_name $_option"

  service_db_wait

  echo ">>> service_exec $_service_name psql -U $POSTGRES_USER $_option"
  service_exec "$_service_name" psql -U $POSTGRES_USER $_option
  #-d $POSTGRES_DB $@
}

##############################################################################
### Tratamento para Ctrl+C
##############################################################################

# Função que será chamada quando o script for interrompido
function handle_sigint {
  local _option="${@:2}"
  local _service_name=$1
  echo ">>> ${FUNCNAME[0]} $_service_name $_option"

  echo "Interrompido com Ctrl+C. "
  if [ $ARG_COMMAND = "up" ]; then
   service_stop "${_service_name}" "$ARG_OPTIONS"
  fi
  exit 1
}

# Configura o trap para capturar o sinal SIGINT (Ctrl+C)
trap handle_sigint SIGINT

##############################################################################
### Função principal que orquestra a execução
##############################################################################

function main() {
#  set -x  # Ativa o modo de depuração para verificar a execução
  local arg_count=$#
  declare -a specific_commands_local
  dict_get_and_convert "$ARG_SERVICE" "${DICT_SERVICES_COMMANDS[*]}" specific_commands_local

  local services_local=($(dict_keys "${DICT_SERVICES_COMMANDS[*]}"))
  local all_commands_local=("${specific_commands_local[@]}")
  all_commands_local+=("${COMMANDS_COMUNS[@]}")

  create_pre_push_hook "$COMPOSE" "$SERVICE_WEB_NAME" "$WORK_DIR" "$GIT_BRANCH_NAME"

  error_danger=""
  error_warning=""

  verify_arguments "$arg_count"  "${services_local[*]}"  "${specific_commands_local[*]}" "${all_commands_local[*]}" error_danger error_warning
  argumento_valido=$?

  # Verifica o código de saída da função
  if [ $argumento_valido -ne 1 ]; then
    # Processa os comandos recebidos
    process_command "$arg_count" "$service_exists"
  else
    print_error_messages "$error_danger" "$error_warning"
  fi
  exit 1

}

# Chama a função principal
main "$@"
