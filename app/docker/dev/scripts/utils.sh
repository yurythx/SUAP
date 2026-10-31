#!/bin/bash

##############################################################################
### FUÇÕES PARA TRATAMENTO DE PERSONALIZAÇÃO DE CORES DOS TEXTOS NO TERMINAL
##############################################################################

# Definição de cores para a saída no terminal
GREEN_COLOR='\033[1;32m'   # Cor verde para sucesso
ORANGE_COLOR='\033[0;33m'  # Cor laranja para avisos
RED_COLOR='\033[0;31m'     # Cor vermelha para erros
BLUE_COLOR='\033[1;34m'    # Cor azul para informações
NO_COLOR='\033[0m'         # Cor neutra para resetar as cores no terminal

# Função para exibir avisos com a cor laranja
function echo_warning() {
  echo "${@:3}" -e "$ORANGE_COLOR WARN: $1$NO_COLOR"
}

# Função para exibir erros com a cor vermelha
function echo_error() {
  echo "${@:3}" -e "$RED_COLOR DANG: $1$NO_COLOR"
}

# Função para exibir informações com a cor azul
function echo_info() {
  echo "${@:3}" -e "$BLUE_COLOR INFO: $1$NO_COLOR"
}

# Função para exibir mensagens de sucesso com a cor verde
function echo_success() {
  echo "${@:3}" -e "$GREEN_COLOR SUCC: $1$NO_COLOR"
}

##############################################################################
### FUÇÕES PARA TRATAMENTO DE INSTALAÇÃOES DE COMANDOS UTILITÁRIOS
##############################################################################

# Função para obter o nome do sistema operacional
# Dependendo do sistema operacional (Linux, MacOS, etc.), o script retorna o nome correspondente.
function get_os_name() {
  unameOut="$(uname -s)"
  case "${unameOut}" in
  Linux*) machine=Linux ;;      # Se for Linux
  Darwin*) machine=Mac ;;       # Se for MacOS
  CYGWIN*) machine=Cygwin ;;    # Se for Cygwin
  MINGW*) machine=MinGw ;;      # Se for MinGW (Windows)
  *) machine="UNKNOWN:${unameOut}" ;;  # Se não for identificado
  esac
  echo ${machine}
}

# Variável que indica se o apt-get já foi atualizado durante a execução do script
apt_get_has_update=false

# Função genérica para instalar um comando caso ele não esteja disponível
# Recebe como parâmetros o nome do comando e outras opções (caso necessárias).
function install_command() {
  local _option="${@:2}"  # Pega as opções a partir do segundo argumento
  local _command=$1       # O primeiro argumento é o nome do comando a ser instalado
  echo ">>> ${FUNCNAME[0]} $_command $_option"

  # Verifica se o comando já está instalado
  echo ">>> command -v $_command"
  if command -v $_command &>/dev/null; then
    echo "O comando $_command está disponível."
    return
  else
    echo "O comando $_command não está disponível."
    echo "--- Iniciando processo de instalação do comando $_command ..."
  fi

  # Instalação via MacPorts (para sistemas MacOS)
  if command -v port &>/dev/null; then
    echo ">>> sudo port install $_command"
    sudo port install $_command

  # Instalação via Homebrew (para MacOS/Linux com brew)
  elif command -v brew &>/dev/null; then
    echo ">>> brew install $_command"
    brew install $_command

  # Instalação via apt-get (para distribuições Linux que utilizam apt-get)
  elif command -v apt-get &>/dev/null; then
    # Atualiza o apt-get se ainda não foi feito
    if [[ ! "$apt_get_has_update" == true ]]; then
      echo ">>> apt-get update > /dev/null"
      apt-get update -y > /dev/null
      apt_get_has_update=true
    fi
    echo ">>> apt-get install -y $_command > /dev/null"
    apt-get install -y $_command > /dev/null
  fi
}

# Funções específicas para instalar determinados comandos se não estiverem presentes no sistema

# Verifica se o comando 'ps' está instalado, e o instala caso necessário
function install_command_ps() {
  if ! command -v ps &>/dev/null; then
    install_command procps
  fi
}

# Instala o comando 'pv' (Pipeline Viewer) que monitora o progresso de dados em uma pipeline
function install_command_pv() {
  install_command pv
}

# Instala o comando 'pigz' (Parallel Gzip), uma versão paralela do gzip para compressão de dados
function install_command_pigz() {
  install_command pigz
}

# Instala o comando 'tar' para manipulação de arquivos tar
function install_command_tar() {
  install_command tar
}

# Instala o comando 'file', que identifica o tipo de arquivo
function install_command_file() {
  install_command file
}

# Instala o comando 'postgis', uma extensão do PostgreSQL para dados geoespaciais
function install_command_postgis() {
  install_command postgis
}

function install_command_net_tools() {
  # comando route
  install_command net-tools
}

function install_command_iptables() {
  install_command iptables
}

##############################################################################
### FUÇÕES PARA TRATAMENTO DE ARRAYS
##############################################################################

function in_array {
  ARRAY="$2"
  for e in ${ARRAY[*]}; do
    if [ "$e" = "$1" ]; then
      return 0
    fi
  done
  return 1
}

function dict_get() {
  # Função para buscar o valor associado a uma chave específica dentro de um "dicionário" (representado como um array de pares chave:valor).
  #
  # Parâmetros:
  #   _argkey: A chave cujo valor deseja buscar.
  #   _dict: O "dicionário" representado como um array de strings no formato "chave:valor".
  #
  # Retorno:
  #   Retorna uma lista de valores associados à chave especificada.
  #
  # Exemplo de uso:
  #   _dict=("nome:Maria" "idade:30" "cidade:Natal")
  #   cidade=$(dict_get "cidade "${_dict[@]}") # Retorna "Natal"

  local _argkey=$1  # A chave para a busca
  local _dict=$2    # O array representando o dicionário
  local _result=()  # Inicializa um array vazio para armazenar os valores encontrados

  # Loop através de cada item do array _dict
  for item in ${_dict[*]}; do
    # Extrai a chave antes do primeiro caractere ':'
    local key="${item%%:*}"

    # Extrai o valor após o primeiro caractere ':'
    local value="${item##*:}"

    # Verifica se a chave extraída corresponde à chave buscada (_argkey)
    if [ "$key" = "$_argkey" ]; then
      _result+=("$value")  # Se a chave for igual, adiciona o valor ao array _result
    fi
  done

  # Imprime os valores encontrados
  echo "${_result[@]}"
}

function dict_keys() {
  local _dict=$1
  local _keys=()

  # Itera sobre o dicionário e separa as chaves dos valores
  for item in ${_dict[*]}; do
    local key="${item%%:*}"  # Pega o que está antes do ":"
    _keys+=($key)            # Adiciona a chave ao array _keys
  done

  # Imprime todas as chaves
  echo ${_keys[*]}
}

function dict_values() {
  local _dict=$1
  local _values=()
  for item in ${_dict[*]}; do
    #    local key="${item%%:*}"
    local value="${item##*:}"
    _values+=($value)
  done
  echo ${_values[*]}
}

function string_to_array() {
  local _value=$1

  _array=(${_value//;/ })
  echo ${_array[*]}
}

function convert_semicolon_to_array() {
  local _value="$1"
  local -n _array_ref="$2"  # Usando nameref para passar o array por referência

  # Substitui os  ";" (pontos e vírgulas) por espaços: O operador ${_value//;/ } faz uma substituição de todos os ; por espaços.
  _array_ref=(${_value//;/ })

  # Exemplo de uso:
  #SERVICES="web;vpn;db;redis"
  #ARRAY_RESULT=()
  #
  #convert_semicolon_to_array "$SERVICES" ARRAY_RESULT
  #
  ## Verifica o conteúdo do array:
  #echo "${ARRAY_RESULT[@]}"
}

function convert_multiline_to_array() {
  local multiline_string="$1"
  local -n array_ref="$2"  # Utiliza 'nameref' para passar o array por referência

  # Modifica o IFS para tratar as quebras de linha como delimitadores
  IFS=$'\n'

  # Itera sobre cada linha da string e armazena no array
  for line in $multiline_string; do
      array_ref+=("$line")
  done

  # Reseta o IFS para o valor padrão
  unset IFS

  # Exemplo de uso:
  #
  #SERVICES_DEPENDENCIES="
  #web:vpn;db;redis
  #db:vpn;pgadmin
  #"
  #
  #DICT_SERVICES_DEPENDENCIES=()
  #
  ## Chama a função para converter a string multilinha em array
  #convert_multiline_to_array "$SERVICES_DEPENDENCIES" DICT_SERVICES_DEPENDENCIES
}

# Função: dict_get_and_convert
#
# Descrição:
# A função `dict_get_and_convert` busca um valor associado a uma chave específica em um dicionário e, em seguida, converte esse valor em um array.
# O array resultante é passado por referência para ser utilizado fora da função.
# A função utiliza outra função auxiliar `dict_get` para localizar a chave e valor no dicionário.
# Caso a chave não seja encontrada, o array resultante será vazio.
#
# Parâmetros:
# 1. _argkey (string): A chave que está sendo procurada no dicionário.
# 2. _dict (string): O dicionário no formato de um array onde cada item contém "chave:valor".
# 3. _result_array (array por referência): O array onde o valor associado à chave será armazenado, após a conversão.
#
# Retorno:
# - Retorna 0 em caso de sucesso, mesmo que a chave não seja encontrada (neste caso, o array resultante estará vazio).
#
# Exemplo de uso:
# # Definir o array que armazenará o resultado
# declare -a commands_array
# dict_get_and_convert "db" "${DICT_SERVICES_COMMANDS[*]}" commands_array
# # Exibir o array resultante
# for command in "${commands_array[@]}"; do
#   echo "$command"
# done

function dict_get_and_convert() {
  local _argkey=$1
  local _dict=$2
  local -n _result_array=$3  # Array de saída passado por referência

  # Obtém o valor do dicionário, retorna uma string com separadores ";"
  _dict_value=$(dict_get "$_argkey" "$_dict")

  if [ -n "$_dict_value" ]; then
    # Converte a string para um array, separando pelos pontos e vírgula
    IFS=";" read -ra _result_array <<< "$_dict_value"
  else
    # Retorna um array vazio se a chave não for encontrada
    _result_array=()
    return 0
  fi
}


##############################################################################
### FUNÇÕES RELACIONADAS COM INTERAÇÕES COM O POSTGRES
##############################################################################
function check_db_exists() {
    local postgres_user="$1"
    local postgres_db="$2"
    local postgres_host="${3:-localhost}"
    local postgres_port=${4:-5432}

    # Use psql to check if the database exists
    result=$(psql -U "$postgres_user" -h "$postgres_host" -p "$postgres_port" -tAc "SELECT 1 FROM pg_database WHERE datname='$postgres_db';")

    if [ "$result" = "1" ]; then
        return 0
    else
        return 1
    fi
}

function is_script_initdb() {
    # Verifica se o script foi chamado pelo script de inicialização do container Postgres
    if ps -ef | grep -v grep | grep "/usr/local/bin/docker-entrypoint.sh" > /dev/null; then
        return 0  # Sucesso, foi chamado pelo script de inicialização
    # Verifica se o script foi chamado pelo comando exec ou run do docker
    elif ps -ef | grep -v grep | grep "/docker-entrypoint-initdb.d/init_database.sh" > /dev/null; then
        return 1  # Foi chamado por outro comando
    else
        echo "Chamada desconhecida."
        ps -ef
        return 1  # Retorna 1 se a chamada não for reconhecida
    fi
  # if is_script_initdb; then
  #   echo "INITDB"
  # fi
}

function is_first_initialization() {
    # Caminho para o diretório de dados do PostgreSQL
#    local PG_DATA="/var/lib/postgresql/data"

    # Verifica se o arquivo PG_VERSION existe, indicando que o PostgreSQL já foi inicializado
    if [ -f "$PG_DATA/PG_VERSION" ]; then
        echo "O PostgreSQL já foi inicializado anteriormente. Continuando normalmente..."
        return 1  # Não é a primeira inicialização
    else
        echo "O PostgreSQL está sendo inicializado pela primeira vez."
        return 0  # Primeira inicialização
    fi
}

# Função para testar conexão ao PostgreSQL e ajustar comando psql_command
#testar_conexao_postgres()
function get_host_port() {
    local postgres_host="$1"
    local postgres_port="$2"
    local postgres_user="$3"
    local postgres_db="$4"
    local postgres_password="$5"
    local psql_command
    local psql_output

    export PGPASSWORD=$postgres_password

    # Testar conexão com o host fornecido e a porta fornecida
    psql_command="psql -v ON_ERROR_STOP=1 --host=$postgres_host --port=$postgres_port --username=$postgres_user --dbname=$postgres_db"
    psql_output=$($psql_command -tc "SELECT 1;" )
    # Remove espaços em branco da variável 'psql_output'
    psql_output=$(echo "$psql_output" | xargs)
    if [ "$psql_output" == "1" ]; then
        echo "$postgres_host $postgres_port"
        return 0
    fi

    # Testar conexão sem host e a porta fornecida
    psql_command="psql -v ON_ERROR_STOP=1 --port=$postgres_port --username=$postgres_user"
    psql_output=$($psql_command -tc "SELECT 1;" 2>&1)
    psql_output=$(echo "$psql_output" | xargs)
    if [ "$psql_output" == "1" ]; then
        echo "$postgres_host $postgres_port"
        return 0
    fi

    # Testar conexão com localhost e a porta fornecida
    psql_command="psql -v ON_ERROR_STOP=1 --host=localhost --port=$postgres_port --username=$postgres_user"
    psql_output=$($psql_command -tc "SELECT 1;"  2>&1)
    psql_output=$(echo "$psql_output" | xargs)
    if [ "$psql_output" == "1" ]; then
        echo "localhost $postgres_port"
        return 0
    fi

    # Testar conexão com localhost e porta 5432 (default)
    psql_command="psql -v ON_ERROR_STOP=1 --host=localhost --port=5432 --username=$postgres_user"
    psql_output=$($psql_command -tc "SELECT 1;"  2>&1)
    psql_output=$(echo "$psql_output" | xargs)
    if [ "$psql_output" == "1" ]; then
        echo "localhost 5432"
        return 0
    fi

    # Testar conexão com o host fornecido e porta 5432 (default)
    psql_command="psql -v ON_ERROR_STOP=1 --host=$postgres_host --port=5432 --username=$postgres_user"
    psql_output=$($psql_command -tc "SELECT 1;" 2>&1)
    psql_output=$(echo "$psql_output" | xargs)
    if [ "$psql_output" == "1" ]; then
        echo "$postgres_host port=5432"
        return 0
    fi

    # Testar conexão sem host e porta 5432 (default)
    psql_command="psql -v ON_ERROR_STOP=1  --port=5432 --username=$postgres_user"
    psql_output=$($psql_command -tc "SELECT 1;" 2>&1)
    psql_output=$(echo "$psql_output" | xargs)
    if [ "$psql_output" == "1" ]; then
        echo "$postgres_host 5432"
        return 0
    fi

    # Se todas as tentativas falharem
    echo "Falha ao conectar ao PostgreSQL."
    return 1
}


##############################################################################
### FUNÇÕES PARA TRATAMENTO DE ROTAS E DOMÍNOS (/etc/hosts)
##############################################################################
# Função para adicionar uma rota
function add_route() {
    local vpn_gateway="$1"
    local route_network="$2"

    if [ -n "$vpn_gateway" ] && [ -n "$route_network" ]; then
        echo "Adicionando rota para $route_network via $vpn_gateway"
        echo ">>> route add -net $route_network gw $vpn_gateway"
        route add -net $route_network gw "$vpn_gateway"
    fi
}

# Função para atualizar o arquivo /etc/hosts
function update_hosts_file() {
# Adicionar domínio no /etc/hosts
# O arquivo /etc/hosts é usado para mapear nomes de domínio a endereços IP localmente no sistema.
# Adiciona uma nova entrada, permitindo que o sistema resolva $domain_name para o endereço IP especificado em $ip.
# Isso é útil em configurações de rede onde se deseja resolver um nome de domínio personalizado,
# como em ambientes de desenvolvimento ou em situações onde o DNS público não é utilizado.

    local domain_name="$1"
    local ip="$2"

    if [ -n "$domain_name" ] && [ -n "$ip" ]; then
        echo "Adicionando $domain_name ao /etc/hosts"
        echo ">>> echo \"$ip $domain_name\" >> /etc/hosts"
        echo "$ip $domain_name" >> /etc/hosts
    fi
}

# Função para atualizar o /etc/hosts e verificar a tabela de rotas
function process_hosts_and_routes() {
    local etc_hosts="$1"  # Entrada multilinear com os domínios e IPs
    local vpn_gateway="$2"
    local route_nework="$3"
    local dict_etc_hosts=()

    install_command_net_tools

    add_route "$vpn_gateway" "$route_nework"

    # Converte o conteúdo do /etc/hosts em um array
    convert_multiline_to_array "$etc_hosts" dict_etc_hosts

    # Itera sobre cada entrada para atualizar o /etc/hosts
    for entry in "${dict_etc_hosts[@]}"; do
        local domain_name="${entry%%:*}"  # Extrai o domínio
        local ip="${entry##*:}"  # Extrai o IP
        update_hosts_file "$domain_name" "$ip"
    done

    # Verifica a tabela de rotas
    route -n
    sleep 2  # Aguarda 2 segundos
}

##############################################################################
### FUNÇÕES PARA ENCONTRAR UM IP DISPONÍVEL NO CONTAINER.
##############################################################################
# **verificar_ip_em_uso**: Verifica se um determinado intervalo de IP já está em uso,
# verificando as redes do Docker com o driver bridge.
# **encontrar_ip_disponivel**: Tenta encontrar um intervalo de IP não utilizado,
# começando em um determinado intervalo base (172.19.0.0/16, neste exemplo).
# Se o intervalo inicial (172.18.0.0/16) estiver em uso, a função tenta encontrar
# outro intervalo de IP (172.19.0.0/16, 172.20.0.0/16, etc.).
# O resultado é impresso e pode ser usado no arquivo Docker Compose.

# Função para verificar se um IP específico está em uso
function verificar_gateway_em_uso() {
    local gateway_ip="$1"
    docker network inspect --format '{{json .IPAM.Config}}' $(docker network ls -q) | grep -q "\"Gateway\":\"$gateway_ip\"" && return 0
    return 1  # Retorna 1 se o IP do gateway não estiver em uso
}

# Função para verificar se uma sub-rede está em uso
function verificar_ip_em_uso() {
    local subnet="$1"
    docker network ls --filter driver=bridge -q | while read -r network_id; do
        docker network inspect "$network_id" --format '{{(index .IPAM.Config 0).Subnet}}' | grep -q "^$subnet$" && return 0
    done
    return 1  # Retorna 1 se a sub-rede não estiver em uso
}

# Função para encontrar uma sub-rede e IP de gateway disponíveis
# Rede clase C, prefixo /16
function encontrar_ip_disponivel() {
    local base_ip="$1"  # Ex: "172.19"
    local mask="$2"     # Ex: "16"
    local terceiro_octeto=0
    # Testar uma série de sub-redes começando no base_ip
    while [ "$terceiro_octeto" -lt 255 ]; do
        # Construir a sub-rede e o IP do gateway
        subnet="${base_ip}.${terceiro_octeto}.0/${mask}"
        gateway_ip="${base_ip}.${terceiro_octeto}.2"

        # Verificar se a sub-rede ou o gateway já estão em uso
        if ! verificar_ip_em_uso "$subnet" && ! verificar_gateway_em_uso "$gateway_ip"; then
            echo "$subnet $gateway_ip"
            return 0  # Retornar a sub-rede e o IP do gateway disponíveis
        fi

        # Incrementar o segundo octeto para tentar o próximo intervalo de IP
        terceiro_octeto=$((terceiro_octeto + 1))
    done

    echo "Erro: Nenhuma sub-rede ou IP de gateway disponível encontrado."
    return 1
}

# Função para determinar a sub-rede e o IP do gateway
function determinar_gateway_vpn() {
    local default_vpn_gateway_faixa_ip="172.19.0.0/16"
    local default_vpn_gateway_ip="172.19.0.2"
    local base_ip="172.19"
    local mask="16"

    # Verificar se o gateway inicial está em uso
    if verificar_gateway_em_uso "$default_vpn_gateway_ip"; then
        echo_warning "IP do gateway $default_vpn_gateway_ip já está em uso."

        # Encontrar um novo IP de gateway disponível
        local resultado=$(encontrar_ip_disponivel "$base_ip" "$mask")

        if [ $? -eq 0 ]; then
            default_vpn_gateway_faixa_ip=$(echo "$resultado" | cut -d ' ' -f 1)
            default_vpn_gateway_ip=$(echo "$resultado" | cut -d ' ' -f 2)
            echo_warning "Nova sub-rede e IP de gateway disponíveis: $default_vpn_gateway_faixa_ip, Gateway: $default_vpn_gateway_ip"
        else
            echo_error "Não foi possível encontrar uma sub-rede ou IP de gateway disponível."
            exit 1
        fi
    else
        echo_info "Sub-rede $default_vpn_gateway_faixa_ip e gateway $default_vpn_gateway_ip estão disponíveis."
    fi

    # Retornar os valores
    echo "$default_vpn_gateway_faixa_ip $default_vpn_gateway_ip"

# # Exemplo de uso da função
  #resultado=$(determinar_gateway_vpn)
  #vpn_gateway_faixa_ip=$(echo "$resultado" | cut -d ' ' -f 1)
  #vpn_gateway_ip=$(echo "$resultado" | cut -d ' ' -f 2)
  #
  #echo "VPN Gateway Faixa IP: $vpn_gateway_faixa_ip"
  #echo "VPN Gateway IP: $vpn_gateway_ip"
}

##############################################################################
### OUTRAS FUNÇÕES
##############################################################################

function check_command_status_on_error_exit() {
  # Com mensagem de sucesso:
  # some_command
  # check_command_status "Falha ao executar o comando." "Comando executado com sucesso!"
  #
  # Sem mensagem de sucesso:
  # some_command
  # check_command_status "Falha ao executar o comando."

  local exit_code=$?
  local error_message="$1"
  local success_message="$2"

  if [ $exit_code -ne 0 ]; then
      # Exibe a mensagem de erro e interrompe a execução do script
      echo_error "$error_message"
      exit 1
  else
      # Se sucesso e a mensagem de sucesso foi fornecida, exibe a mensagem de sucesso
      if [ -n "$success_message" ]; then
          echo_success "$success_message"
      fi
  fi
}

# Função para inserir o texto no início do arquivo .env, caso não exista
function insert_text_if_not_exists() {
    local force="false"
    if [ "$1" = "--force" ]; then
        force="true"
        shift  # Remove o parâmetro --force da lista de argumentos
    fi
    local text="$1"
    local env_file="$2"
    local key=$(echo "$text" | cut -d '=' -f 1)

    # Verificar se a chave está definida no arquivo, se não for forçado
    # Força a inserção sem verificação se a chave existe no arquivo $env_file
    if [ "$force" == "true" ]; then
        # Verifica se o texto está vazio.
        if [ -z "$text" ]; then
          # Adiciona uma quebra de linha
          sed -i '1i\\' "$env_file"
        else
          sed -i "1i$text" "$env_file"
        fi
        echo_warning "-- Texto '$text' adicionado ao início do arquivo $env_file (forçado)"
    elif ! grep -q "^$key=" "$env_file"; then
        # Se a chave não estiver definida, inserir no início do arquivo
        sed -i "1i$text" "$env_file"
        echo_warning "-- Texto '$text' adicionado ao início do arquivo $env_file"
    fi
# Exemplo de uso:
# insert_text_if_not_exists "UID=1000" ".env"
# insert_text_if_not_exists --force "UID=1000" ".env"
}

## Função para ler o arquivo ini e preencher arrays associativos, passando o array por referência
#function read_ini() {
#    local file=$1
#    local section=$2
#    local key=$3
#
#    # Extract the value using grep and sed
#    value=$(sed -nr "/^\[$section\]/ { :l /^$key[ ]*=/ { s/.*=[ ]*//; p; q;}; n; b l;}" $file)
#    echo $value
#}

# Função para verificar o comando de inicialização da aplicação no ambiente de desenvolvimento
function verificar_comando_inicializacao_ambiente_dev() {
    local root_dir="$1"
    local mensagem=""
    local codigo_retorno=1  # Definido como falha por padrão

    # Verifica se o arquivo manage.py existe (Django)
    if [[ -f "$root_dir/manage.py" ]]; then
        mensagem="Django detectado no diretório: $root_dir"
        codigo_retorno=0

    # Verifica se o arquivo index.php existe (PHP)
    elif [[ -f "$root_dir/index.php" ]]; then
        mensagem="PHP detectado no diretório: $root_dir"
        codigo_retorno=0

    # Verifica se o arquivo package.json existe (Node.js)
    elif [[ -f "$root_dir/package.json" ]]; then
        mensagem="Node.js detectado no diretório: $root_dir"
        codigo_retorno=0

    # Verifica se o arquivo composer.json existe (PHP com Composer)
    elif [[ -f "$root_dir/composer.json" ]]; then
        mensagem="PHP com Composer detectado no diretório: $root_dir"
        codigo_retorno=0

    # Verifica se o arquivo Gemfile existe (Ruby on Rails)
    elif [[ -f "$root_dir/Gemfile" ]]; then
        mensagem="Ruby on Rails detectado no diretório: $root_dir"
        codigo_retorno=0

    # Verifica se o arquivo config.ru existe (Rack ou Sinatra - Ruby)
    elif [[ -f "$root_dir/config.ru" ]]; then
        mensagem="Rack/Sinatra detectado no diretório: $root_dir"
        codigo_retorno=0

    else
        mensagem="Nenhum comando de inicialização detectado no diretório $root_dir."
        codigo_retorno=1
    fi

    # Retorna a mensagem e o código de retorno
    echo "$mensagem"
    return $codigo_retorno

#    # Exemplo de uso:
     #root_dir="/caminho/do/diretorio"
     #mensagem=$(verificar_comando_inicializacao_ambiente_dev "$root_dir")
     #codigo_retorno=$?
     #
     #if [ $codigo_retorno -eq 0 ]; then
     #    echo "Iniciando aplicação detectada..."
     #    echo "$mensagem"
     #else
     #    echo "Erro: Nenhuma aplicação detectada."
     #    echo "$mensagem"
     #fi
}

# Função para exibir as opções de imagens e retornar a escolha do usuário
function escolher_imagem_base() {
    echo >&2 "Selecione uma das opções de imagem base para seu projeto:"
    echo >&2 "1. Imagem base de desenvolvimento Python"
    echo >&2 "2. Imagem base de desenvolvimento Python com Node.js."
    echo >&2 "3. Vou usar minha própria imagem."

    # Solicitar entrada do usuário
    read -p "Digite o número correspondente à sua escolha: " escolha

    # Definir a imagem base com base na escolha
    case $escolha in
        1)
            imagem_base="python_base_dev"
            ;;
        2)
            imagem_base="python_nodejs_dev"
            ;;
        3)
            imagem_base="default"
            ;;
        *)
            echo_warning >&2 "Escolha inválida. Por favor, escolha uma opção válida."
            escolher_imagem_base  # Chama a função novamente em caso de escolha inválida
            return
            ;;
    esac

    # Retorna a imagem base selecionada
    echo "$imagem_base"

# Exemplo de uso
#resultado=$(escolher_imagem_base)
#imagem_base=$(echo $resultado | awk '{print $1}')
#nome_base=$(echo $resultado | awk '{print $2}')
#
#echo "Imagem selecionada: $imagem_base"
#echo "Nome base: $nome_base"
}

function create_pre_push_hook() {
  local compose_command="$1"
  local service_name="$2"
  local workdir="$3"
  local gitbranch_name="$4"

  # Verifica se o arquivo pre-push já existe
  if [ ! -f .git/hooks/pre-push ]; then
    # Cria o arquivo pre-push com o conteúdo necessário
    cat <<EOF > .git/hooks/pre-push
#!/bin/sh

# Execute o comando pre-commit customizado
# - "git config --global --add safe.directory" permite que o diretório especificado seja marcado como seguro, permitindo que o Git execute operações nesse diretório.
# - "--from-ref origin/\${GIT_BRANCH_MAIN:-master}" especifica o commit de origem para a comparação.
#  Por padrão, o commit de origem será a referência da branch principal
# - "--to-ref HEAD" define que o commit final para comparação é o HEAD, ou seja, o commit mais recente na branch atual.
# - "pre-commit run" executa os hooks de pre-commit definidos no arquivo .pre-commit-config.yaml
if [ -d "$workdir" ]; then
  git config --global --add safe.directory ${workdir:-/opt/suap} && pre-commit run --from-ref origin/${gitbranch_name:-master} --to-ref HEAD
else
  $compose_command exec -T $service_name bash -c "git config --global --add safe.directory ${workdir:-/opt/suap} && pre-commit run --from-ref origin/${gitbranch_name:-master} --to-ref HEAD"
fi

# Verifica se o script foi executado com sucesso
if [ \$? -ne 0 ]; then
  echo "Falha no pre-commit, push abortado."
  exit 1
fi
EOF
    # Torna o arquivo pre-push executável
    chmod +x .git/hooks/pre-push
    echo "Arquivo pre-push criado com sucesso."
#  else
#    echo "Arquivo pre-push já existe."
  fi
}

function imprime_variaveis_env() {
  local env_file_path="$1"

  while IFS= read -r line; do
    # Ignora linhas em branco ou comentários
    if [[ -n "$line" && "$line" != \#* ]]; then
      # Extrai o nome da variável e o valor, com base no formato "chave=valor"
      var_name=$(echo "$line" | cut -d'=' -f1)
      var_value=$(echo "$line" | cut -d'=' -f2-)

      # Verifica se o nome da variável é válido
      if [[ "$var_name" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]]; then
          echo "$var_name=$var_value"
      else
        # Se o nome da variável for inválido, apenas exibe a linha lida
         echo "$var_name"
      fi
    fi
  done <"$env_file_path"

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
}

function get_project_file() {
    local dir_path="$1"
    local ini_file_path="$2"
    local section="$3"
    local key="$4"

    # Lê o valor da chave "default" na seção "envfile"
    local default_filename=$(read_ini "$ini_file_path" "$section" "default" | tr -d '\r')
    if [ -z "$default_filename" ]; then
        default_filename=".env.sample"
    fi
    default_filename="${dir_path}/${default_filename}"

    # Lê o valor da chave correspondente ao projeto na seção "envfile"
    local _project_file=$(read_ini "$ini_file_path" "$section" "$key" | tr -d '\r')
    if [ -z "$_project_file" ]; then
        _project_file="$default_filename"
    fi

    # Retorna o valor da variável _project_file
    echo "$_project_file"
}
