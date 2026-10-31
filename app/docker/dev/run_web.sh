#!/bin/bash
set -Eeuo pipefail

###############################################################################
# run_web.sh
# -----------------------------------------------------------------------------
# Sobe a aplicação SUAP no ambiente de desenvolvimento.
#
# Independente da opção escolhida, os seguintes containers são iniciados:
#   - vpn   : acesso à rede interna institucional
#   - db    : banco de dados PostgreSQL
#   - redis : cache e fila
#
# Opções de execução (menu interativo):
#   [1] Host   — roda manage.py runserver diretamente no host via uv
#   [2] Docker — sobe o container web via docker compose
#   [3] Testes — executa manage.py test_behave (host ou docker)
#
# Uso:
#   cd docker/dev
#   ./run_web.sh
###############################################################################

# =========================
# Cores e mensagens
# =========================
GREEN_COLOR='\033[0;32m'
ORANGE_COLOR='\033[0;33m'
RED_COLOR='\033[0;31m'
BLUE_COLOR='\033[0;34m'
NO_COLOR='\033[0m'

echo_warning() { echo -e "${ORANGE_COLOR}WARN: $*${NO_COLOR}" >&2; }
echo_error()   { echo -e "${RED_COLOR}DANG: $*${NO_COLOR}"   >&2; }
echo_info()    { echo -e "${BLUE_COLOR}INFO: $*${NO_COLOR}"  >&2; }
echo_success() { echo -e "${GREEN_COLOR}SUCC: $*${NO_COLOR}" >&2; }

# =========================
# Diretórios
# =========================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PYPROJECT_FILE="${PROJECT_ROOT}/pyproject.toml"
ENV_FILE="${SCRIPT_DIR}/.env"

# =========================
# Utilitários
# =========================
has_cmd() { command -v "$1" >/dev/null 2>&1; }

list_available_test_labels() {
  (
    cd "${PROJECT_ROOT}" || exit 1
    find . -mindepth 2 -maxdepth 2 -type d -name features -printf '%h\n' 2>/dev/null \
      | sed 's#^\./##' \
      | sort -u
  )
}

show_test_label_suggestions() {
  local suggestions
  suggestions="$(list_available_test_labels | head -n 8 || true)"
  if [ -n "${suggestions}" ]; then
    echo_info "Algumas apps/labels disponíveis:"
    while IFS= read -r item; do
      [ -n "${item}" ] && echo_info "  - ${item}"
    done <<< "${suggestions}"
  fi
}

validate_test_label() {
  local label="$1" candidate
  if [ -z "${label}" ]; then
    echo_error "App/label não informado."
    return 1
  fi

  if [[ "${label}" == *"/"* ]] || [[ "${label}" == *.feature ]]; then
    candidate="${PROJECT_ROOT}/${label}"
    if [ -d "${candidate}" ] || [ -f "${candidate}" ]; then
      return 0
    fi
    echo_error "App/label inválido: '${label}'."
    echo_info "Quando informar caminho, ele deve existir relativo à raiz do projeto."
    show_test_label_suggestions
    return 1
  fi

  candidate="${PROJECT_ROOT}/${label}/features"
  if [ -d "${candidate}" ]; then
    return 0
  fi

  echo_error "App/label inválido: '${label}'."
  echo_info "Esperado um app com pasta 'features/' (ex.: avaliacao_integrada) ou um caminho existente para feature."
  show_test_label_suggestions
  return 1
}

_abort() {
  echo_error "Python ${REQUIRED_PYTHON} é obrigatório. Abortando."
  echo_info "Alternativa: use a opção Docker neste menu."
  exit 1
}

python_satisfies_requirement() {
  local bin="$1" required="$2" actual
  actual="$("${bin}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")' 2>/dev/null)" || return 1
  [ "$(printf '%s\n' "${required}" "${actual}" | sort -V | head -n1)" = "${required}" ]
}

find_compatible_python() {
  local uv_py sys_py
  uv_py="$(uv python find "${PYTHON_MINOR}" 2>/dev/null || true)"
  if [ -n "${uv_py}" ] && python_satisfies_requirement "${uv_py}" "${REQUIRED_PYTHON}"; then
    echo "${uv_py}"; return 0
  fi
  sys_py="$(command -v "python${PYTHON_MINOR}" 2>/dev/null || true)"
  if [ -n "${sys_py}" ] && python_satisfies_requirement "${sys_py}" "${REQUIRED_PYTHON}"; then
    echo "${sys_py}"; return 0
  fi
  return 1
}

ensure_python() {
  if find_compatible_python > /dev/null 2>&1; then
    echo_success "Python compatível encontrado: $(find_compatible_python)"
    return 0
  fi
  echo_info "Python ${REQUIRED_PYTHON} não encontrado. Tentando instalar via uv..."
  if uv python install "${REQUIRED_PYTHON}" 2>/dev/null && find_compatible_python > /dev/null 2>&1; then
    echo_success "Python ${REQUIRED_PYTHON} instalado via uv."
    return 0
  fi
  echo_warning "Python ${REQUIRED_PYTHON} não disponível para download automático via uv."
  echo
  OS="$(uname -s)"
  case "${OS}" in
    Linux)
      if has_cmd apt-get; then
        echo_info "Instalação disponível via deadsnakes PPA (Ubuntu/Debian):"
        echo_info "  sudo add-apt-repository ppa:deadsnakes/ppa"
        echo_info "  sudo apt update && sudo apt install python${PYTHON_MINOR} python${PYTHON_MINOR}-venv python${PYTHON_MINOR}-dev"
        echo
        read -rp "Deseja instalar agora via deadsnakes? [S/n]: " resposta
        case "$resposta" in [Nn]* ) _abort ;; esac
        sudo add-apt-repository -y ppa:deadsnakes/ppa
        sudo apt-get update -q
        sudo apt-get install -y "python${PYTHON_MINOR}" "python${PYTHON_MINOR}-venv" "python${PYTHON_MINOR}-dev"
      else
        echo_error "Gerenciador de pacotes não suportado. Instale Python ${REQUIRED_PYTHON} manualmente."
        _abort
      fi
      ;;
    Darwin)
      if has_cmd brew; then
        echo_info "Instalação disponível via Homebrew:"
        echo_info "  brew install python@${PYTHON_MINOR}"
        echo
        read -rp "Deseja instalar agora via Homebrew? [S/n]: " resposta
        case "$resposta" in [Nn]* ) _abort ;; esac
        brew install "python@${PYTHON_MINOR}"
        brew link "python@${PYTHON_MINOR}" --force --overwrite || true
      else
        echo_error "Homebrew não encontrado. Instale em https://brew.sh e reexecute."
        _abort
      fi
      ;;
    *)
      echo_error "Sistema operacional '${OS}' não suportado para instalação automática."
      _abort
      ;;
  esac
  if ! find_compatible_python > /dev/null 2>&1; then
    echo_error "Instalação concluída mas Python ${REQUIRED_PYTHON} ainda não encontrado."
    exit 1
  fi
  echo_success "Python ${PYTHON_MINOR} instalado com sucesso."
}

_compose() {
  docker compose --env-file "${ENV_FILE}" -f "${SCRIPT_DIR}/docker-compose.yml" "$@"
}

_run() {
  echo_info "$ $*"
  "$@"
}

run_db_preflight() {
  local purpose="$1"
  echo_info "Validando acesso ao banco (${purpose})..."
  _run uv run python manage.py check_db_access --purpose "${purpose}"
}

build_test_behave_command() {
  local cmd arg
  cmd="uv sync --dev && uv run python manage.py test_behave"
  for arg in "${TEST_ARGS[@]}"; do
    printf -v cmd '%s %q' "${cmd}" "${arg}"
  done
  printf -v cmd '%s %q' "${cmd}" "${TEST_LABEL}"
  printf '%s' "${cmd}"
}

# Garante saída do Python sem buffering (migrate, collectstatic, runserver, etc.)
export PYTHONUNBUFFERED=1

setup_uv_and_python() {
  echo_info "Verificando uv..."
  if ! has_cmd uv; then
    echo_info "uv não encontrado. Instalando via script oficial..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="${HOME}/.local/bin:${PATH}"
    if ! has_cmd uv; then
      echo_error "Falha ao instalar uv. Instale manualmente: https://docs.astral.sh/uv/getting-started/installation/"
      exit 1
    fi
  fi
  echo_success "uv $(uv --version) disponível."

  if [ ! -f "${PYPROJECT_FILE}" ]; then
    echo_error "pyproject.toml não encontrado em ${PROJECT_ROOT}"
    exit 1
  fi
  REQUIRED_PYTHON="$(grep -E '^requires-python' "${PYPROJECT_FILE}" | head -n1 | sed -E 's/.*"([^"]+)".*/\1/' | sed -nE 's/.*>=([0-9]+\.[0-9]+\.[0-9]+).*/\1/p')"
  if [ -z "${REQUIRED_PYTHON}" ]; then
    echo_error "Não foi possível ler requires-python em ${PYPROJECT_FILE}"
    exit 1
  fi
  echo_info "Python requerido pelo projeto: ${REQUIRED_PYTHON}"
  PYTHON_MINOR="$(echo "${REQUIRED_PYTHON}" | cut -d. -f1-2)"
  ensure_python
}

# =========================
# Menu interativo (loop — opções 4-7 retornam ao menu)
# =========================
opcao=""
opcionais=""
TEST_LABEL=""
TEST_ARGS=()
TEST_EXEC_MODE=""
_first_menu=true

while true; do
  if [ "${_first_menu}" = "true" ]; then
    _first_menu=false
  else
    read -rp $'\nPressione Enter para voltar ao menu...' _ || true
  fi
  echo
  echo -e "${BLUE_COLOR}╔══════════════════════════════════════════╗${NO_COLOR}"
  echo -e "${BLUE_COLOR}║         SUAP — Ambiente de Dev           ║${NO_COLOR}"
  echo -e "${BLUE_COLOR}╠══════════════════════════════════════════╣${NO_COLOR}"
  echo -e "${BLUE_COLOR}║  Aplicação  (sobem vpn + db + redis):    ║${NO_COLOR}"
  echo -e "${BLUE_COLOR}║    [1] Host   (uv run manage.py)         ║${NO_COLOR}"
  echo -e "${BLUE_COLOR}║    [2] Docker (docker compose up web)    ║${NO_COLOR}"
  echo -e "${BLUE_COLOR}║    [3] Testes (test_behave)              ║${NO_COLOR}"
  echo -e "${BLUE_COLOR}╠══════════════════════════════════════════╣${NO_COLOR}"
  echo -e "${BLUE_COLOR}║  Serviços opcionais (Enter para nenhum): ║${NO_COLOR}"
  echo -e "${BLUE_COLOR}║    [p] pgadmin — administração do banco  ║${NO_COLOR}"
  echo -e "${BLUE_COLOR}║    [c] celery  — worker de filas         ║${NO_COLOR}"
  echo -e "${BLUE_COLOR}║  Ex: p, c, pc                            ║${NO_COLOR}"
  echo -e "${BLUE_COLOR}╠══════════════════════════════════════════╣${NO_COLOR}"
  echo -e "${BLUE_COLOR}║  Containers                              ║${NO_COLOR}"
  echo -e "${BLUE_COLOR}║    [4] Logs    (seguir logs em tempo real)║${NO_COLOR}"
  echo -e "${BLUE_COLOR}║    [5] Status  (docker compose ps)       ║${NO_COLOR}"
  echo -e "${BLUE_COLOR}║    [6] Down    (docker compose down)     ║${NO_COLOR}"
  echo -e "${BLUE_COLOR}║    [7] Build   (compilar imagens)        ║${NO_COLOR}"
  echo -e "${BLUE_COLOR}╠══════════════════════════════════════════╣${NO_COLOR}"
  echo -e "${BLUE_COLOR}║    [0] Sair                              ║${NO_COLOR}"
  echo -e "${BLUE_COLOR}╚══════════════════════════════════════════╝${NO_COLOR}"
  echo
  read -rp "Opção [0-7]: " opcao

  case "${opcao}" in
    0)
      echo_info "Saindo."
      exit 0
      ;;
    1|3)
      read -rp "Opcionais [p/c/pc/Enter]: " opcionais
      ;;
    2)
      read -rp "Opcionais [p/c/pc/Enter]: " opcionais
      # Monta profiles inline para executar dentro do loop
      _docker_profile_args=()
      _docker_optional_services=()
      if echo "${opcionais}" | grep -qi "p"; then
        _docker_profile_args+=(--profile pgadmin)
        _docker_optional_services+=(pgadmin)
      fi
      if echo "${opcionais}" | grep -qi "c"; then
        _docker_profile_args+=(--profile celery)
        _docker_optional_services+=(celery-dev)
      fi
      # Sobe suporte antes de subir web
      if has_cmd docker && [ -f "${ENV_FILE}" ]; then
        echo_info "Subindo serviços de suporte (vpn, db, redis)..."
        _compose up -d vpn db redis 2>&1 || echo_warning "Falha ao subir serviços Docker."
        db_retries=30
        until _compose ps db 2>/dev/null | grep -q "healthy" || [ "${db_retries}" -eq 0 ]; do
          sleep 2; db_retries=$((db_retries - 1))
        done
        [ "${db_retries}" -eq 0 ] && echo_warning "db ainda não está healthy, prosseguindo mesmo assim..."
      fi
      echo_info "$ docker compose up -d web ${_docker_optional_services[*]}"
      _compose "${_docker_profile_args[@]}" up -d web "${_docker_optional_services[@]}" || true
      echo_info "Use a opção [4] Logs para acompanhar a saída."
      continue
      ;;
    4)
      echo_info "Seguindo logs dos containers (Ctrl+C para sair)..."
      read -rp "Serviço(s) [Enter para todos, ou ex: web db redis]: " log_services
      # shellcheck disable=SC2086
      _compose logs -f --tail=100 ${log_services:-} || true
      continue
      ;;
    5)
      _compose ps || true
      continue
      ;;
    6)
      echo_warning "Isso irá parar e remover todos os containers do projeto."
      read -rp "Confirmar down? [s/N]: " confirm_down
      case "${confirm_down}" in
        [Ss]*) _compose down || true ;;
        *) echo_info "Cancelado." ;;
      esac
      continue
      ;;
    7)
      echo_info "$ ${SCRIPT_DIR}/build_images.sh"
      bash "${SCRIPT_DIR}/build_images.sh" || true
      continue
      ;;
    *)
      echo_error "Opção inválida: '${opcao}'. Use 0 a 7."
      continue
      ;;
  esac

  # Sub-menu de testes (opção 3)
  TEST_LABEL=""
  TEST_ARGS=()
  TEST_EXEC_MODE=""

  if [ "${opcao}" = "3" ]; then
    echo
    echo -e "${BLUE_COLOR}╔══════════════════════════════════════════════════════╗${NO_COLOR}"
    echo -e "${BLUE_COLOR}║           SUAP — Execução de Testes Behave           ║${NO_COLOR}"
    echo -e "${BLUE_COLOR}╠══════════════════════════════════════════════════════╣${NO_COLOR}"
    echo -e "${BLUE_COLOR}║  ATENÇÃO: --behave_stop sempre ativado               ║${NO_COLOR}"
    echo -e "${BLUE_COLOR}║  (para na primeira falha — obrigatório neste menu)   ║${NO_COLOR}"
    echo -e "${BLUE_COLOR}╠══════════════════════════════════════════════════════╣${NO_COLOR}"
    echo -e "${BLUE_COLOR}║  Estratégia de banco de teste:                       ║${NO_COLOR}"
    echo -e "${BLUE_COLOR}║    [1] --keepdb-with-data   (mantém dados)           ║${NO_COLOR}"
    echo -e "${BLUE_COLOR}║    [2] --keepdb-initial-only (restaura estado inicial)║${NO_COLOR}"
    echo -e "${BLUE_COLOR}║    [3] Sem keepdb            (execução padrão)       ║${NO_COLOR}"
    echo -e "${BLUE_COLOR}╠══════════════════════════════════════════════════════╣${NO_COLOR}"
    echo -e "${BLUE_COLOR}║  Onde executar?                                      ║${NO_COLOR}"
    echo -e "${BLUE_COLOR}║    [h] Host   (uv run)                               ║${NO_COLOR}"
    echo -e "${BLUE_COLOR}║    [d] Docker (compose run --rm web)                 ║${NO_COLOR}"
    echo -e "${BLUE_COLOR}╚══════════════════════════════════════════════════════╝${NO_COLOR}"
    echo
    read -rp "App/label a testar (ex: avaliacao_integrada): " TEST_LABEL
    if ! validate_test_label "${TEST_LABEL}"; then
      continue
    fi

    read -rp "Estratégia keepdb [1/2/3] (padrão: 1): " keepdb_opcao
    keepdb_opcao="${keepdb_opcao:-1}"
    case "${keepdb_opcao}" in
      1)
        TEST_ARGS+=(--keepdb-with-data)
        read -rp "Ativar --reuse-successful-scenarios? [S/n]: " reuse_resp
        case "${reuse_resp}" in
          [Nn]*) ;;
          *) TEST_ARGS+=(--reuse-successful-scenarios) ;;
        esac
        ;;
      2) TEST_ARGS+=(--keepdb-initial-only) ;;
      3) ;;
      *)
        echo_error "Estratégia inválida: '${keepdb_opcao}'. Use 1, 2 ou 3."
        continue
        ;;
    esac

    read -rp "Forçar recriação do banco (--force-drop-test-db)? [s/N]: " force_drop_resp
    case "${force_drop_resp}" in [Ss]*) TEST_ARGS+=(--force-drop-test-db) ;; esac

    TEST_ARGS+=(--behave_stop)

    read -rp "Executar no host (h) ou Docker (d)? [h/D]: " TEST_EXEC_MODE
    TEST_EXEC_MODE="${TEST_EXEC_MODE:-d}"
    case "${TEST_EXEC_MODE}" in
      h|d) ;;
      *)
        echo_error "Opção inválida: '${TEST_EXEC_MODE}'. Use h ou d."
        continue
        ;;
    esac
  fi

  break
done

# =========================
# Montar profiles e serviços opcionais
# =========================
COMPOSE_PROFILE_ARGS=()
OPTIONAL_SERVICES=()

if echo "${opcionais}" | grep -qi "p"; then
  COMPOSE_PROFILE_ARGS+=(--profile pgadmin)
  OPTIONAL_SERVICES+=(pgadmin)
fi
if echo "${opcionais}" | grep -qi "c"; then
  COMPOSE_PROFILE_ARGS+=(--profile celery)
  OPTIONAL_SERVICES+=(celery-dev)
fi

# =========================
# Serviços de suporte (vpn, db, redis) — ambas as opções
# =========================
if has_cmd docker && [ -f "${ENV_FILE}" ]; then
  echo_info "Subindo serviços de suporte (vpn, db, redis)..."
  _compose up -d vpn db redis 2>&1 || echo_warning "Falha ao subir serviços Docker. Verifique manualmente."
  echo_info "Aguardando db ficar pronto..."
  db_retries=30
  until _compose ps db 2>/dev/null | grep -q "healthy" || [ "${db_retries}" -eq 0 ]; do
    sleep 2
    db_retries=$((db_retries - 1))
  done
  [ "${db_retries}" -eq 0 ] && echo_warning "db ainda não está healthy, prosseguindo mesmo assim..."
  echo_success "Serviços de suporte prontos."
else
  echo_warning "Docker não encontrado ou .env ausente — suba vpn, db e redis manualmente."
fi

# =========================
# Variáveis de ambiente para modo host (opções 1 e 3-host)
# =========================
# No modo host, os nomes de serviço Docker (vpn, redis) não resolvem via DNS.
# Lemos as portas mapeadas dinamicamente via 'docker compose port'.
# Se não for possível detectar, solicita ao desenvolvedor.
if [ "${opcao}" = "1" ] || { [ "${opcao}" = "3" ] && [ "${TEST_EXEC_MODE}" = "h" ]; }; then
  DB_INTERNAL_PORT="$(grep -E '^DATABASE_PORT=' "${ENV_FILE}" | head -n1 | cut -d= -f2- | tr -d ' \r')"
  REDIS_INTERNAL_PORT="$(grep -E '^REDIS_PORT=' "${ENV_FILE}" | head -n1 | cut -d= -f2- | tr -d ' \r')"

  VPN_HOST_PORT="$(_compose port vpn "${DB_INTERNAL_PORT:-25432}" 2>/dev/null | cut -d: -f2 | tr -d ' \r' || true)"
  REDIS_HOST_PORT="$(_compose port redis "${REDIS_INTERNAL_PORT:-6379}" 2>/dev/null | cut -d: -f2 | tr -d ' \r' || true)"

  if [ -z "${VPN_HOST_PORT}" ]; then
    echo_warning "Não foi possível detectar a porta do banco via container vpn."
    read -rp "Informe a porta do banco exposta no host [${DB_INTERNAL_PORT:-25432}]: " VPN_HOST_PORT
    VPN_HOST_PORT="${VPN_HOST_PORT:-${DB_INTERNAL_PORT:-25432}}"
  fi

  if [ -z "${REDIS_HOST_PORT}" ]; then
    echo_warning "Não foi possível detectar a porta do Redis via container."
    read -rp "Informe a porta do Redis exposta no host [${REDIS_INTERNAL_PORT:-6379}]: " REDIS_HOST_PORT
    REDIS_HOST_PORT="${REDIS_HOST_PORT:-${REDIS_INTERNAL_PORT:-6379}}"
  fi

  export DATABASE_HOST=localhost
  export DATABASE_PORT="${VPN_HOST_PORT}"
  export REDIS_LOCATION="redis://localhost:${REDIS_HOST_PORT}/1"
  export SESSION_LOCATION="redis://localhost:${REDIS_HOST_PORT}/2"
  export CELERY_BROKER_URL="redis://localhost:${REDIS_HOST_PORT}/3"
  export CELERY_RESULT_BACKEND="redis://localhost:${REDIS_HOST_PORT}/4"
  echo_info "Modo host: banco → localhost:${DATABASE_PORT}, Redis → localhost:${REDIS_HOST_PORT}"
fi

# =========================
# Opção 3: Testes (test_behave)
# =========================
if [ "${opcao}" = "3" ]; then
  echo_warning "--behave_stop ativado: a suíte para na primeira falha."
  echo_info "Executando: manage.py test_behave ${TEST_ARGS[*]} ${TEST_LABEL}"

  if [ "${TEST_EXEC_MODE}" = "d" ]; then
    TEST_BEHAVE_CMD="$(build_test_behave_command)"
    echo_info "$ docker compose run --rm web bash -lc ${TEST_BEHAVE_CMD}"
    _compose run --rm web bash -lc "${TEST_BEHAVE_CMD}"
  else
    # Modo host: garantir uv e Python antes de executar
    setup_uv_and_python
    cd "${PROJECT_ROOT}"
    _run uv sync --dev
    echo_success "Dependências sincronizadas."
    run_db_preflight "test_behave"
    _run uv run python manage.py test_behave "${TEST_ARGS[@]}" "${TEST_LABEL}"
  fi
  exit 0
fi

# =========================
# Opção 1: Host
# =========================

# 1-3. Verificar/instalar uv, Python e sincronizar
setup_uv_and_python

# 4. Sincronizar dependências
cd "${PROJECT_ROOT}"
_run uv sync --dev
echo_success "Dependências sincronizadas."
run_db_preflight "runserver"

# 5. collectstatic e migrate
RUN_WEB_LOG="${HOME}/tmp/suap_run_web.log"
mkdir -p "${HOME}/tmp"
: > "${RUN_WEB_LOG}"
echo_info "Log: ${RUN_WEB_LOG}  (acompanhe em outro terminal: tail -f ${RUN_WEB_LOG})"

echo_info "$ uv run python manage.py collectstatic --no-input"
uv run python manage.py collectstatic --no-input 2>&1 | tee -a "${RUN_WEB_LOG}"

echo_info "$ uv run python manage.py migrate"
uv run python manage.py migrate 2>&1 | tee -a "${RUN_WEB_LOG}"

# 6. Validar configuração
_run uv run python manage.py check
echo_success "Configuração válida."

# 7. Serviços opcionais no modo host
if [ ${#OPTIONAL_SERVICES[@]} -gt 0 ]; then
  echo_info "Subindo serviços opcionais: ${OPTIONAL_SERVICES[*]}..."
  _compose "${COMPOSE_PROFILE_ARGS[@]}" up -d "${OPTIONAL_SERVICES[@]}" \
    2>&1 || echo_warning "Falha ao subir serviços opcionais."
  if echo "${opcionais}" | grep -qi "c"; then
    echo_warning "Celery no modo host requer um terminal separado:"
    echo_warning "  uv run celery -A suap worker -Q \${CELERY_QUEUE:-default}"
  fi
fi

# 8. Iniciar servidor
echo_success "Iniciando servidor em http://0.0.0.0:${APP_PORT:-8000} ..."
echo_info "$ uv run python manage.py runserver 0.0.0.0:${APP_PORT:-8000}"
echo_info "Ctrl+C encerra o acompanhamento de logs (o servidor continua rodando)."
uv run python manage.py runserver "0.0.0.0:${APP_PORT:-8000}" \
  >> "${RUN_WEB_LOG}" 2>&1 &
exec tail -f "${RUN_WEB_LOG}"
