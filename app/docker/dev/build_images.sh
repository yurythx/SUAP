#!/bin/bash
set -Eeuo pipefail

###############################################################################
# build_images.sh
# -----------------------------------------------------------------------------
# Lida com perfis do Docker Compose, lista serviços e compila imagens
# perguntando ao usuário quando a imagem já existe localmente.
# Também executa serviços utilitários de forma one-shot (ex.: pull da base).
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
# Perfis do Docker Compose
# =========================
ENABLE_DEV_PROFILE="${ENABLE_DEV_PROFILE:-false}"
COMPOSE_ARGS=()
if [ "${ENABLE_DEV_PROFILE}" = "true" ]; then
  export COMPOSE_PROFILES="dev"
  COMPOSE_ARGS+=(--profile dev)
  echo_info "Perfil 'dev' habilitado (COMPOSE_PROFILES=dev)."
else
  echo_warning "Perfil 'dev' desabilitado (ENABLE_DEV_PROFILE=false)."
fi

# =========================
# Diretórios
# =========================
COMPOSE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$COMPOSE_DIR" || { echo_error "Não foi possível acessar ${COMPOSE_DIR}"; exit 1; }
PROJECT_ROOT="$(cd "${COMPOSE_DIR}/../.." && pwd)"
PYPROJECT_FILE="${PROJECT_ROOT}/pyproject.toml"
BASE_IMAGE_SOURCE="${BASE_IMAGE_SOURCE:-local}"  # local|registry

# =========================
# Utilitários
# =========================
has_cmd() { command -v "$1" >/dev/null 2>&1; }

# Retorna o registry hostname da primeira instrução FROM de um Dockerfile.
# Ex.: "FROM ghcr.io/astral-sh/uv:3.14" → "ghcr.io"
# Retorna vazio quando o FROM usa variável (${ARG}) — nesses casos o check é ignorado.
dockerfile_base_registry() {
  local dockerfile="$1"
  [ ! -f "$dockerfile" ] && return 1
  local from_image
  from_image="$(grep -m1 '^FROM ' "$dockerfile" | awk '{print $2}')"
  # Se o FROM usa variável (${...}), não é possível determinar o registry estático
  [[ "$from_image" == *'${'* ]] && return 0
  # Remove tag/digest
  local image_ref="${from_image%%:*}"
  image_ref="${image_ref%%@*}"
  # Se o primeiro segmento (antes de /) contém ponto ou ':', é registry explícito
  local first_seg="${image_ref%%/*}"
  if [[ "$first_seg" == *.* ]] || [[ "$first_seg" == *:* ]]; then
    echo "$first_seg"
  fi
  # Sem registry explícito e sem variável = Docker Hub; não fazemos check
  # pois o Docker pode usar a imagem do cache local sem precisar de rede
}

# Obtém o caminho absoluto do Dockerfile de um serviço via docker compose config.
# O campo 'dockerfile' é relativo ao 'context', que pode ser absoluto ou relativo ao COMPOSE_DIR.
get_service_dockerfile() {
  local service_name="$1"
  local df="" ctx=""
  if has_cmd jq; then
    local cfg_json
    cfg_json="$(docker compose "${COMPOSE_ARGS[@]}" config --format json 2>/dev/null || true)"
    df="$(echo "$cfg_json"  | jq -r --arg s "$service_name" '.services[$s].build.dockerfile // empty' 2>/dev/null || true)"
    ctx="$(echo "$cfg_json" | jq -r --arg s "$service_name" '.services[$s].build.context   // empty' 2>/dev/null || true)"
  fi
  [ -z "$df" ] && return 1
  # Resolve: context absoluto + dockerfile relativo ao context
  if [ -n "$ctx" ]; then
    [[ "$ctx" != /* ]] && ctx="${COMPOSE_DIR}/${ctx}"
    df="${ctx}/${df#./}"
  fi
  [ ! -f "$df" ] && return 1
  echo "$df"
}

# Checa se um registry hostname está acessível via HTTPS (timeout 5s).
registry_reachable() {
  local host="$1"
  if has_cmd curl; then
    curl -sf --max-time 5 --head "https://${host}" >/dev/null 2>&1
  elif has_cmd wget; then
    wget -q --timeout=5 --spider "https://${host}" >/dev/null 2>&1
  else
    return 0  # sem ferramenta de teste, assume acessível
  fi
}

get_required_python_minor() {
  local req
  req="$(grep -E '^requires-python' "${PYPROJECT_FILE}" | head -n1 | sed -E 's/.*"([^"]+)".*/\1/')"
  if [ -z "${req}" ]; then
    echo_error "Não foi possível ler requires-python em ${PYPROJECT_FILE}"
    exit 1
  fi
  echo "${req}" | sed -nE 's/.*>=([0-9]+\.[0-9]+)\.[0-9]+.*/\1/p'
}

validate_base_python() {
  local expected_minor="$1"
  local suap_image="${SUAP_IMAGE:-gitlab.ifrn.edu.br:4567/cosinf/suap}"
  local base_image="${suap_image}:base"
  local actual

  actual="$(docker run --rm --entrypoint python "${base_image}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
  if [ -z "${actual}" ]; then
    echo_error "Não foi possível validar Python da imagem base ${base_image}."
    exit 1
  fi

  if [ "${actual}" != "${expected_minor}" ]; then
    echo_error "Incompatibilidade de Python na imagem base."
    echo_error "pyproject.toml exige ${expected_minor}.x e a imagem base fornece ${actual}.x."
    echo_error "Use BASE_IMAGE_SOURCE=local para reconstruir uma base compatível."
    exit 1
  fi
}

validate_dev_python() {
  local expected_minor="$1"
  local dev_image="${DEV_IMAGE:-suap-local:dev}"
  local actual

  actual="$(docker run --rm --entrypoint python "${dev_image}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
  if [ -z "${actual}" ]; then
    echo_error "Não foi possível validar Python da imagem de desenvolvimento ${dev_image}."
    exit 1
  fi

  if [ "${actual}" != "${expected_minor}" ]; then
    echo_error "Imagem de desenvolvimento desatualizada (${dev_image})."
    echo_error "pyproject.toml exige ${expected_minor}.x e a imagem fornece ${actual}.x."
    echo_error "Rebuild sugerido: docker compose build --no-cache suap-dev-builder web"
    exit 1
  fi
}

service_exists() {
  local svc="$1"
  docker compose "${COMPOSE_ARGS[@]}" config --services | grep -Fxq "$svc"
}

# Obtém o nome da imagem efetiva do serviço (usa jq se disponível; fallback awk)
resolve_service_image_name() {
  local service_name="$1"
  local project_name="${COMPOSE_PROJECT_NAME:-$(basename "$PWD")}"
  local img=""

  if docker compose "${COMPOSE_ARGS[@]}" config --format json >/dev/null 2>&1; then
    if has_cmd jq; then
      img="$(docker compose "${COMPOSE_ARGS[@]}" config --format json \
            | jq -r --arg s "$service_name" '.services[$s].image // empty')"
    fi
  fi

  if [ -z "$img" ]; then
    img="$(docker compose "${COMPOSE_ARGS[@]}" config 2>/dev/null \
          | awk -v s="$service_name" '
              $0 ~ "^services:" {in_services=1}
              in_services && $0 ~ "^  " s ":" {in_target=1; next}
              in_target && $0 ~ "^  [^ ]" {exit}
              in_target && $1=="image:" {print $2; exit}
            ')"
  fi

  if [ -z "$img" ]; then
    img="${project_name}_${service_name}:latest"
  fi

  printf '%s\n' "$img"
}

image_exists() {
  local image_ref="$1"
  if docker image inspect "$image_ref" >/dev/null 2>&1; then
    return 0
  fi
  if [[ "$image_ref" != *:* ]]; then
    docker image inspect "${image_ref}:latest" >/dev/null 2>&1 && return 0
  fi
  return 1
}

image_python_minor() {
  local image_ref="$1"
  docker run --rm --entrypoint python "${image_ref}" \
    -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true
}

should_rebuild_image() {
  local service_name="$1"
  local image_name
  image_name="$(resolve_service_image_name "$service_name")"

  if image_exists "$image_name"; then
    local actual_minor
    actual_minor="$(image_python_minor "$image_name")"
    if [ -n "${actual_minor}" ] && [ "${actual_minor}" != "${required_minor}" ]; then
      echo_warning "Imagem '${image_name}' tem Python ${actual_minor}.x mas pyproject.toml exige ${required_minor}.x — rebuild forçado."
      return 0
    fi
    read -rp "Imagem/serviço '${service_name}' (imagem: '${image_name}') já existe. Deseja recompilar? [s/N]: " resposta
    case "$resposta" in
      [Ss]* ) return 0 ;;
      * )     return 1 ;;
    esac
  else
    return 0
  fi
}

build_image_if_needed() {
  local service_name="$1"
  local force="${2:-false}"
  if service_exists "$service_name"; then
    echo_info "Processando build da imagem/serviço '${service_name}'..."
    if [ "${force}" = "true" ] || should_rebuild_image "$service_name"; then
      [ "${force}" = "true" ] && echo_warning "Rebuild forçado de '${service_name}' (dependência reconstruída)."

      # Checa antecipadamente se o registry da imagem base está acessível.
      # Evita tentar o build quando a rede bloqueia o registry (ex.: ghcr.io 403).
      local svc_dockerfile registry_host
      svc_dockerfile="$(get_service_dockerfile "$service_name" 2>/dev/null || true)"
      if [ -n "$svc_dockerfile" ] && [ -f "$svc_dockerfile" ]; then
        registry_host="$(dockerfile_base_registry "$svc_dockerfile" 2>/dev/null || true)"
        if [ -n "$registry_host" ] && ! registry_reachable "$registry_host"; then
          local image_name_pre
          image_name_pre="$(resolve_service_image_name "$service_name")"
          if image_exists "${image_name_pre}"; then
            echo_warning "Registry '${registry_host}' inacessível na rede atual — pulando build de '${service_name}' e usando imagem local existente."
            return 1  # não foi reconstruído, mas há fallback local
          else
            echo_error "Registry '${registry_host}' inacessível e sem imagem local para '${service_name}'. Abortando."
            echo_error "Dica: conecte-se a uma rede com acesso a '${registry_host}' ou use BASE_IMAGE_SOURCE=registry."
            return 2
          fi
        fi
      fi

      echo_info "Construindo ${service_name}..."
      local build_exit=0
      docker compose "${COMPOSE_ARGS[@]}" build --no-cache "${service_name}" || build_exit=$?
      if [ "${build_exit}" -ne 0 ]; then
        echo_error "Build de ${service_name} falhou (exit ${build_exit})."
        # Fallback automático: se já existe imagem local, continua sem perguntar.
        local image_name
        image_name="$(resolve_service_image_name "$service_name")"
        if image_exists "${image_name}"; then
          echo_warning "Imagem '${image_name}' encontrada localmente — continuando com versão existente (pode estar desatualizada)."
          return 1  # não foi reconstruído, mas há fallback local
        fi
        return 2  # falhou e sem fallback local
      fi
      echo_success "Build de ${service_name} concluído."
      return 0  # foi reconstruído
    else
      echo_info "Pulando build de ${service_name} (imagem já existente)."
      return 1  # não foi reconstruído
    fi
  else
    echo_warning "Serviço '${service_name}' não existe no docker-compose atual (perfil ativo considerado)."
    return 1
  fi
}

up_once_if_exists() {
  local service_name="$1"
  if service_exists "$service_name"; then
    echo_info "Executando '${service_name}' com --abort-on-container-exit..."
    docker compose "${COMPOSE_ARGS[@]}" up --abort-on-container-exit "$service_name"
  else
    echo_warning "Serviço '${service_name}' não existe no docker-compose atual (perfil ativo considerado)."
  fi
}

# =========================
# Execução
# =========================
echo_info "Serviços disponíveis no docker-compose (considerando perfil ativo):"
docker compose "${COMPOSE_ARGS[@]}" config --services || true
echo

required_minor="$(get_required_python_minor)"
echo_info "Python requerido no pyproject.toml: ${required_minor}.x"

case "${BASE_IMAGE_SOURCE}" in
  local)
    base_build_status=0
    build_image_if_needed "suap-base-builder" || base_build_status=$?
    if [ "${base_build_status}" -eq 2 ]; then
      echo_error "Build de suap-base-builder falhou e nenhuma imagem local disponível como fallback. Abortando."
      echo_error "Dica: use BASE_IMAGE_SOURCE=registry para obter a imagem base do registry remoto."
      exit 1
    fi
    ;;
  registry)
    up_once_if_exists "suap-base-pull-image"
    ;;
  *)
    echo_error "BASE_IMAGE_SOURCE inválido: ${BASE_IMAGE_SOURCE}. Use 'local' ou 'registry'."
    exit 1
    ;;
esac

validate_base_python "${required_minor}"
dev_builder_rebuilt=false
build_image_if_needed "suap-dev-builder" && dev_builder_rebuilt=true
validate_dev_python "${required_minor}"
build_image_if_needed "web" "${dev_builder_rebuilt}" || true   # forçado se dev-builder foi reconstruído

echo_success "Imagens processadas com sucesso."
