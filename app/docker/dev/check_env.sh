#!/usr/bin/env bash
set -euo pipefail

# Valida o .env usado por docker/dev/docker-compose.yml.
# Uso:
#   ./check_env.sh
#   ./check_env.sh /caminho/para/.env

GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

info() { echo -e "${BLUE}INFO:${NC} $*"; }
warn() { echo -e "${YELLOW}WARN:${NC} $*"; }
err() { echo -e "${RED}ERRO:${NC} $*"; }
ok() { echo -e "${GREEN}OK:${NC} $*"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${1:-${SCRIPT_DIR}/.env}"

if [[ ! -f "${ENV_FILE}" ]]; then
  err "Arquivo de env não encontrado: ${ENV_FILE}"
  echo "Dica: cp ${SCRIPT_DIR}/.env.minimal.sample ${SCRIPT_DIR}/.env"
  exit 1
fi

info "Validando env file: ${ENV_FILE}"

set -a
# shellcheck source=/dev/null
source "${ENV_FILE}"
set +a

errors=0
warnings=0

required_vars=(
  COMPOSE_PROJECT_NAME
  DOCKER_VPN_WORKDIR
  DOCKER_VPN_IP
  DOCKER_IPAM_CONFIG_SUBNET
  DOCKER_IPAM_CONFIG_GATEWAY_IP
  SDOCKER_WORKDIR
  DATABASE_NAME
  DATABASE_USER
  DATABASE_PASSWORD
  DATABASE_HOST
  DATABASE_PORT
  WORK_DIR
  APP_PORT
  SUAP_IMAGE
  USER_BASE_DIR_NAME
  USER_NAME
  USER_UID
  USER_GID
  LOCAL_DBUSER_PEM_PATH
)

check_required_var() {
  local var_name="$1"
  local value="${!var_name:-}"
  if [[ -z "${value}" ]]; then
    err "Variável obrigatória ausente/vazia: ${var_name}"
    errors=$((errors + 1))
    return
  fi
  if [[ "${value}" == *"/ABS/PATH/"* || "${value}" == *"change_me"* || "${value}" == *"your_"* ]]; then
    err "Variável ${var_name} parece placeholder não ajustado: ${value}"
    errors=$((errors + 1))
    return
  fi
  ok "${var_name}=${value}"
}

for v in "${required_vars[@]}"; do
  check_required_var "${v}"
done

check_file() {
  local label="$1"
  local path="$2"
  if [[ -f "${path}" ]]; then
    ok "${label}: arquivo encontrado (${path})"
  else
    err "${label}: arquivo não encontrado (${path})"
    errors=$((errors + 1))
  fi
}

check_dir() {
  local label="$1"
  local path="$2"
  if [[ -d "${path}" ]]; then
    ok "${label}: diretório encontrado (${path})"
  else
    err "${label}: diretório não encontrado (${path})"
    errors=$((errors + 1))
  fi
}

check_dir "DOCKER_VPN_WORKDIR" "${DOCKER_VPN_WORKDIR:-}"
check_file "DOCKER_VPN_WORKDIR/docker-compose.yaml" "${DOCKER_VPN_WORKDIR:-}/docker-compose.yaml"

check_dir "SDOCKER_WORKDIR" "${SDOCKER_WORKDIR:-}"
check_dir "SDOCKER_WORKDIR/scripts" "${SDOCKER_WORKDIR:-}/scripts"
check_file "db_entrypoint.sh montado via SDOCKER_WORKDIR" "${SDOCKER_WORKDIR:-}/scripts/db_entrypoint.sh"

check_file "LOCAL_DBUSER_PEM_PATH" "${LOCAL_DBUSER_PEM_PATH:-}"

if [[ "${DATABASE_HOST:-}" == "vpn" ]]; then
  if [[ -z "${ETC_HOSTS:-}" ]]; then
    warn "DATABASE_HOST=vpn sem ETC_HOSTS definido. O container db pode não resolver hosts internos."
    warnings=$((warnings + 1))
  fi
  if [[ -z "${ROUTE_NETWORK:-}" ]]; then
    warn "DATABASE_HOST=vpn sem ROUTE_NETWORK definido. Rotas podem não ser aplicadas no container db."
    warnings=$((warnings + 1))
  fi
fi

if [[ -z "${GITLAB_USER:-}" || -z "${GITLAB_PASSWORD:-}" ]]; then
  warn "GITLAB_USER/GITLAB_PASSWORD ausentes: o serviço suap-base-pull-image pode falhar."
  warnings=$((warnings + 1))
fi

echo
if [[ "${errors}" -gt 0 ]]; then
  err "Validação falhou: ${errors} erro(s), ${warnings} aviso(s)."
  exit 1
fi

ok "Validação concluída com sucesso: 0 erro(s), ${warnings} aviso(s)."
