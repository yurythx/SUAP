#!/usr/bin/env bash
set -axe

# Script helper para executar skills do opencode no GitLab CI.
# Uso: opencode-skill.sh <skill-name> <mr-iid> <project-id> <gitlab-url> <gitlab-token> [provider] [model] [api-key]
#
# Exemplo:
#   opencode-skill.sh mr-format 42 123 https://gitlab.ifrn.edu.br TOKEN openai gpt-4o sk-xxx
#
# Variáveis de ambiente opcionais:
#   OPENCODE_PROVIDER - provedor LLM (ex: openai, google, anthropic)
#   OPENCODE_MODEL    - modelo LLM (ex: gpt-4o, gemini-1.5-pro, claude-sonnet-5)
#   OPENCODE_API_KEY  - chave de API do provedor LLM

SKILL_NAME="${1}"
MR_IID="${2}"
PROJECT_ID="${3}"
GITLAB_URL="${4}"
GITLAB_TOKEN="${5}"
PROVIDER="${6:-${OPENCODE_PROVIDER:-}}"
MODEL="${7:-${OPENCODE_MODEL:-}}"
{ set +x; } 2>/dev/null  # não logar a chave
API_KEY="${8:-${OPENCODE_API_KEY:-}}"
set -x

# Roteamento por risco (AGENTS.md, "Roteamento de modelos por risco"): o padrão
# (OPENCODE_MODEL) já é barato; skills de alto risco sobem para OPENCODE_MODEL_ALTO_RISCO
# quando definida (id sem prefixo, mesmo provedor de OPENCODE_PROVIDER).
case "$SKILL_NAME" in
    code-review) MODEL="${OPENCODE_MODEL_ALTO_RISCO:-$MODEL}" ;;
esac

if [[ -z "$SKILL_NAME" || -z "$MR_IID" || -z "$PROJECT_ID" || -z "$GITLAB_URL" || -z "$GITLAB_TOKEN" ]]; then
    echo "Uso: $0 <skill-name> <mr-iid> <project-id> <gitlab-url> <gitlab-token> [provider] [model] [api-key]"
    echo ""
    echo "Variáveis de ambiente opcionais:"
    echo "  OPENCODE_PROVIDER - provedor LLM (ex: openai, google, anthropic)"
    echo "  OPENCODE_MODEL    - modelo LLM (ex: gpt-4o, gemini-1.5-pro)"
    echo "  OPENCODE_API_KEY  - chave de API do provedor LLM"
    exit 1
fi

MR_URL="${GITLAB_URL}/${PROJECT_ID}/-/merge_requests/${MR_IID}"

# ----------------------------------------------------------------------------
# Bootstrap git: permite que skills façam `git commit` / `git push` direto.
# - Identidade do bot (override via GIT_BOT_NAME / GIT_BOT_EMAIL).
# - Autenticação via header HTTP (PRIVATE-TOKEN) -> evita gravar token no remote.
# - Checkout do source_branch do MR (CI usa detached HEAD em refs/merge-requests).
# ----------------------------------------------------------------------------
git config --global user.name "${GIT_BOT_NAME:-SUAP Bot}"
git config --global user.email "${GIT_BOT_EMAIL:-suap-bot@ifrn.edu.br}"
git config --global --add safe.directory "${CI_PROJECT_DIR:-$PWD}"

# Header de auth p/ HTTPS — silencia set -x p/ não logar o token
{ set +x; } 2>/dev/null
git remote set-url origin "https://oauth2:${GITLAB_TOKEN}@gitlab.ifrn.edu.br/cosinf/suap.git"
git config --global http.extraheader "PRIVATE-TOKEN: ${GITLAB_TOKEN}"
set -x

# MR pipeline: traz o branch real e faz checkout (out of detached HEAD)
if [[ -n "${CI_MERGE_REQUEST_SOURCE_BRANCH_NAME:-}" ]]; then
    git fetch origin "${CI_MERGE_REQUEST_SOURCE_BRANCH_NAME}" \
        && git checkout -B "${CI_MERGE_REQUEST_SOURCE_BRANCH_NAME}" \
            "origin/${CI_MERGE_REQUEST_SOURCE_BRANCH_NAME}" \
        || echo "Aviso: falha ao fazer checkout do source_branch; skill seguirá em HEAD atual."
fi

# Garantir diretório de config do opencode
mkdir -p ~/.config/opencode

# Bloco MCP do Sentry: opcional, ativado quando SENTRY_MCP_TOKEN está presente.
# As vars SENTRY_MCP_HOST e SENTRY_MCP_DISABLE_SKILLS são opcionais.
SENTRY_MCP_BLOCK=""
if [[ -n "${SENTRY_MCP_TOKEN:-}" ]]; then
    SENTRY_HOST_ARG=""
    if [[ -n "${SENTRY_MCP_HOST:-}" ]]; then
        SENTRY_HOST_ARG=", \"--host=${SENTRY_MCP_HOST}\""
    fi
    SENTRY_SKILLS_ARG=""
    if [[ -n "${SENTRY_MCP_DISABLE_SKILLS:-}" ]]; then
        SENTRY_SKILLS_ARG=", \"--disable-skills=${SENTRY_MCP_DISABLE_SKILLS}\""
    fi
    SENTRY_MCP_BLOCK=",
    \"sentry\": {
      \"type\": \"local\",
      \"command\": [
        \"sentry-mcp\",
        \"--access-token=${SENTRY_MCP_TOKEN}\"${SENTRY_HOST_ARG}${SENTRY_SKILLS_ARG}
      ]
    }"
fi

# Gerar opencode.json dinamicamente com MCPs (gitlab sempre, sentry opcional).
# Binários `mcp-gitlab` e `sentry-mcp` vêm pré-instalados na imagem custom
# ($CI_REGISTRY_IMAGE/opencode), evitando download via npx a cada job.
#
# As três ferramentas de PUBLICAÇÃO de draft note ficam escondidas do agente via
# `--tool-policy-hidden` (o servidor as omite do tools/list). Motivo: `bulk_publish`
# do GitLab é assíncrono e responde 204 / `[]`; o agente lia "vazio" como falha,
# repetia o bulk e ainda caía no fallback list -> publish individual, publicando
# cada comentário 3x (job 425507, MR !18709). Quem publica é este script, uma única
# vez, depois do `opencode run`. Exige mcp-gitlab >= 2.1.46 (pin no Dockerfile).
cat > ~/.config/opencode/opencode.json <<EOF
{
  "\$schema": "https://opencode.ai/config.json",
  "permission": {
    "edit": "allow",
    "bash": "allow",
    "webfetch": "allow"
  },
  "mcp": {
    "gitlab": {
      "type": "local",
      "command": [
        "mcp-gitlab",
        "--token=${GITLAB_TOKEN}",
        "--api-url=${GITLAB_URL}/api/v4",
        "--tool-policy-hidden=bulk_publish_draft_notes,publish_draft_note,list_draft_notes"
      ]
    }${SENTRY_MCP_BLOCK}
  }
}
EOF

# OpenCode 2.x não lê mais o ~/.local/share/opencode/auth.json: a chave dos provedores
# opencode/opencode-go vem de OPENCODE_API_KEY (e `opencode auth login` exige terminal
# interativo). Outro provedor precisa da variável dele (ex.: OPENAI_API_KEY).
{ set +x; } 2>/dev/null
export OPENCODE_API_KEY="${API_KEY}"
set -x

# Montar argumento do modelo se provider e model foram fornecidos
MODEL_ARG=""
if [[ -n "$PROVIDER" && -n "$MODEL" ]]; then
    MODEL_ARG="-m ${PROVIDER}/${MODEL}"
    echo "Usando modelo: ${PROVIDER}/${MODEL}"
fi

# Executar a skill com auto-aprovação de permissões; a saída texto do opencode vai direto
# para o log do job (o 2.x imprime texto e ferramentas legíveis fora de TTY).
# SKILL_ARG sobrescreve MR_URL quando a skill não usa URL de MR (ex: uma skill que recebe a branch base)
SKILL_PROMPT_ARG="${SKILL_ARG:-${MR_URL}}"
echo "Executando skill /${SKILL_NAME} com arg: ${SKILL_PROMPT_ARG}"
# Sem `set -e` aqui: se o opencode morrer (crash, OOM, kill), a publicação dos rascunhos
# ainda precisa rodar — senão a revisão fica órfã. O código de saída é cobrado no fim
# do script (o 2.x sai com 1 quando a sessão falha, ex.: chave inválida).
OPENCODE_EXIT=0
# --standalone: no 2.x o padrão é conectar num serviço em background, que não existe no
# contêiner do job. --auto: aprova as permissões não negadas (job headless).
opencode run "/${SKILL_NAME} ${SKILL_PROMPT_ARG}" \
    --standalone \
    --auto \
    --title "CI: ${SKILL_NAME} MR !${MR_IID}" \
    ${MODEL_ARG} || OPENCODE_EXIT=$?

# ----------------------------------------------------------------------------
# Publicar os draft notes da revisão — UMA vez, incondicionalmente, daqui.
# O agente só cria rascunhos (as ferramentas de publicação são escondidas dele
# acima); sem rascunho pendente a chamada é um no-op (204). Não checar antes: o
# bulk_publish é assíncrono, então "ainda há rascunho" não significa "não
# publicado" — foi exatamente esse sinal que o agente leu errado e duplicou.
# Roda antes do check de erro para não deixar rascunho órfão quando a skill falha.
# Só a code-review cria draft notes; as demais skills nem sempre têm MR_IID real.
# ----------------------------------------------------------------------------
if [[ "${SKILL_NAME}" == "code-review" ]]; then
    { set +x; } 2>/dev/null
    PUBLISH_HTTP="$(curl --silent --output /dev/null --write-out '%{http_code}' \
        --max-time 60 \
        --request POST \
        --header "PRIVATE-TOKEN: ${GITLAB_TOKEN}" \
        "${GITLAB_URL}/api/v4/projects/${PROJECT_ID}/merge_requests/${MR_IID}/draft_notes/bulk_publish" || true)"
    set -x
    echo "bulk_publish dos draft notes -> HTTP ${PUBLISH_HTTP}"
    if [[ "${PUBLISH_HTTP}" != 2?? ]]; then
        echo "Falha ao publicar os draft notes do MR !${MR_IID} (HTTP ${PUBLISH_HTTP:-sem resposta})."
        echo "HTTP 500 aqui costuma ser rascunho com âncora fora do diff: o GitLab aceita na criação,"
        echo "quebra na publicação e descarta só aquela nota. Confira os rascunhos pendentes do MR."
        exit 1
    fi
fi

# Falha do processo do opencode só é cobrada aqui, depois de publicar os rascunhos.
if [[ "${OPENCODE_EXIT}" -ne 0 ]]; then
    echo "opencode saiu com código ${OPENCODE_EXIT}."
    exit "${OPENCODE_EXIT}"
fi
