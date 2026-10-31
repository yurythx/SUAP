#!/usr/bin/env bash
set -euo pipefail

DEPLOY_MODE="${1:-}"
SSH_PORT="${PROD_SSH_PORT:-22}"
SSH_OPTS="-o StrictHostKeyChecking=yes -o BatchMode=yes -o ConnectTimeout=30"

setup_ssh() {
    if ! ssh-add -l > /dev/null 2>&1; then
        eval "$(ssh-agent -s)" > /dev/null
        # Runner shell: sem isso cada job deixa um agente vivo com a chave de prod.
        trap 'ssh-agent -k > /dev/null' EXIT
        # Base64 numa linha: variável masked do GitLab não aceita espaço/quebra de linha.
        echo "$PROD_SSH_PRIVATE_KEY" | tr -d '\r' | base64 -d | ssh-add - > /dev/null
    fi

    mkdir -p ~/.ssh
    chmod 700 ~/.ssh

    if [ -n "${PROD_SSH_KNOWN_HOSTS:-}" ]; then
        echo "$PROD_SSH_KNOWN_HOSTS" | tr -d '\r' >> ~/.ssh/known_hosts
    fi
}

run_remote() {
    local host="$1"
    local commands="$2"

    # bash -s via stdin: garante bash (pipefail) seja qual for o shell de login remoto.
    # Bloco { }: bash lê o script inteiro antes de executar — senão um filho que lê
    # stdin (docker compose run do `make exec`) engole as linhas seguintes.
    ssh $SSH_OPTS -p "$SSH_PORT" "${PROD_SSH_USER}@${host}" bash -s <<< "{
${commands}
}"
}

# "a, b,,c" -> um host por linha, sem espaços/vazios.
split_hosts() {
    local host
    IFS=',' read -ra _hosts <<< "$1"
    for host in "${_hosts[@]}"; do
        host="$(echo "$host" | xargs)"
        [ -z "$host" ] || echo "$host"
    done
}

# Roda `commands` em todos os hosts em PARALELO e espera todos (não aborta no 1º);
# sai 1 listando os que falharam. Subshell sai com o status do ssh (PIPESTATUS[0]), não
# do sed; o prefixo [host] separa as saídas simultâneas no log do job.
run_parallel() {
    local label="$1" commands="$2" host i failed=""
    shift 2
    local -a hosts=("$@") pids=()
    for host in "${hosts[@]}"; do
        (
            run_remote "$host" "$commands" 2>&1 | sed -u "s/^/[$host] /"
            exit "${PIPESTATUS[0]}"
        ) &
        pids+=("$!")
    done
    for i in "${!hosts[@]}"; do
        wait "${pids[$i]}" || failed="$failed ${hosts[$i]}"
    done
    if [ -n "$failed" ]; then
        echo "=== $label FALHOU em:$failed ===" >&2
        return 1
    fi
}

# Drain do HAProxy é automático no suap_deploy (hooks do compose): `make down`
# marca deploy/status.txt=drain e espera DRAIN_SECONDS antes de parar o nginx;
# `make up` volta pra healthy. Sempre ciclar via make down/up — `docker compose
# up -d` direto recria o web sem drain.
deploy_master() {
    echo "=== DEPLOY MASTER: $PROD_SSH_HOST ==="
    run_remote "$PROD_SSH_HOST" "
        set -eo pipefail
        cd ${PROD_SSH_PATH}
        git pull origin master
        docker compose pull
        make down
        make exec COMMAND='python manage.py sync' 2>&1 | tee /tmp/run.log
        make up
    "
    echo "=== DEPLOY MASTER OK ==="
}

# Slaves em duas fases:
# 1. Preparação em PARALELO (git pull + docker compose pull): só baixa código e imagens,
#    não mexe no que está rodando. Se algum host falhar, aborta antes de reiniciar qualquer
#    um — nada de cluster com versões misturadas.
# 2. Restart UM POR VEZ (make down/up, com drain): nunca mais de um nó fora do pool, e
#    aborta na 1ª falha (não segue o rolling com um nó quebrado).
deploy_slaves() {
    local host
    local -a hosts=()
    mapfile -t hosts < <(split_hosts "${PROD_SSH_SLAVES:-}")

    if [ "${#hosts[@]}" -eq 0 ]; then
        echo "PROD_SSH_SLAVES vazia, pulando slaves."
        return 0
    fi

    echo "=== PREPARANDO SLAVES EM PARALELO: ${hosts[*]} ==="
    if ! run_parallel "PREPARAÇÃO" "
        set -eo pipefail
        cd ${PROD_SSH_PATH}
        git pull origin master
        docker compose pull
    " "${hosts[@]}"; then
        echo "=== nenhum slave foi reiniciado ===" >&2
        return 1
    fi

    for host in "${hosts[@]}"; do
        echo "=== RESTART SLAVE: $host ==="
        run_remote "$host" "
            set -eo pipefail
            cd ${PROD_SSH_PATH}
            make down
            make up
        "
        echo "=== RESTART SLAVE $host OK ==="
    done
}

# `make <alvo>` em todos os hosts em paralelo. Best-effort (paridade com o ignore_errors
# do ansible): falha num host não impede os demais; sai 1 no fim listando quais falharam.
make_on_hosts() {
    local target="$1"
    local -a hosts=()
    mapfile -t hosts < <(split_hosts "$2")
    echo "=== make $target EM PARALELO: ${hosts[*]} ==="
    run_parallel "make $target" "set -eo pipefail; cd ${PROD_SSH_PATH}; make $target" "${hosts[@]}"
}

case "$DEPLOY_MODE" in
    master)
        setup_ssh
        deploy_master
        ;;
    slaves)
        setup_ssh
        deploy_slaves
        ;;
    full)
        setup_ssh
        deploy_master
        deploy_slaves
        ;;
    stop-all)
        setup_ssh
        make_on_hosts down "${PROD_SSH_HOST},${PROD_SSH_SLAVES:-}"
        ;;
    start-all)
        setup_ssh
        make_on_hosts up "${PROD_SSH_HOST},${PROD_SSH_SLAVES:-}"
        ;;
    *)
        echo "Uso: $0 {master|slaves|full|stop-all|start-all}"
        exit 1
        ;;
esac
