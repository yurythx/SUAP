#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR/.." rev-parse --show-toplevel 2>/dev/null || pwd)"
REPO_NAME="$(basename "$REPO_ROOT")"
REPO_PARENT="$(dirname "$REPO_ROOT")"
SESSIONS_DIR="$REPO_ROOT/.sessions"
WORKTREE_ROOT="$REPO_PARENT/${REPO_NAME}-worktrees"
PORT_START="${DEV_SESSION_PORT_START:-8100}"
PORT_END="${DEV_SESSION_PORT_END:-8999}"
BASE_BRANCH="${DEV_SESSION_BASE_BRANCH:-master}"

usage() {
    cat <<'EOF'
Uso:
  bin/dev-session.sh create <nome>
  bin/dev-session.sh print-env <nome>
  bin/dev-session.sh enter <nome>
  bin/dev-session.sh runserver <nome> [args...]
  bin/dev-session.sh test <nome> [args...]
  bin/dev-session.sh status [nome]
  bin/dev-session.sh list
  bin/dev-session.sh remove <nome>
EOF
}

die() {
    printf 'Erro: %s\n' "$*" >&2
    exit 1
}

slugify() {
    local input="$1"
    input="$(printf '%s' "$input" | tr '[:upper:]' '[:lower:]')"
    input="$(printf '%s' "$input" | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//; s/-+/-/g')"
    [ -n "$input" ] || die 'Nome de sessão inválido.'
    printf '%s\n' "$input"
}

session_file_path() {
    local slug="$1"
    printf '%s/%s.env\n' "$SESSIONS_DIR" "$slug"
}

quote_shell() {
    printf '%q' "$1"
}

write_session_file() {
    local session_file="$1"
    mkdir -p "$SESSIONS_DIR"
    cat > "$session_file" <<EOF
export SESSION_NAME=$(quote_shell "$SESSION_NAME")
export SESSION_SLUG=$(quote_shell "$SESSION_SLUG")
export SESSION_WORKTREE=$(quote_shell "$SESSION_WORKTREE")
export SESSION_BRANCH=$(quote_shell "$SESSION_BRANCH")
export APP_PORT=$(quote_shell "$APP_PORT")
export TEST_DATABASE_NAME=$(quote_shell "$TEST_DATABASE_NAME")
EOF
}

load_session() {
    local slug="$1"
    SESSION_FILE="$(session_file_path "$slug")"
    [ -f "$SESSION_FILE" ] || die "Sessão '$slug' não encontrada."
    # shellcheck source=/dev/null
    source "$SESSION_FILE"
}

port_in_use() {
    local port="$1"
    python - "$port" <<'PY'
import socket
import sys

port = int(sys.argv[1])
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    sock.bind(('127.0.0.1', port))
except OSError:
    sys.exit(0)
finally:
    sock.close()
sys.exit(1)
PY
}

reserve_port() {
    local port
    for ((port = PORT_START; port <= PORT_END; port++)); do
        if ! port_in_use "$port"; then
            printf '%s\n' "$port"
            return 0
        fi
    done
    die "Nenhuma porta livre entre ${PORT_START} e ${PORT_END}."
}

sync_base_branch() {
    local local_ref="refs/heads/$BASE_BRANCH"
    local remote_ref="refs/remotes/origin/$BASE_BRANCH"
    local local_sha
    local remote_sha

    git -C "$REPO_ROOT" remote get-url origin >/dev/null 2>&1 || die "Remote 'origin' não encontrada."
    git -C "$REPO_ROOT" fetch origin "$BASE_BRANCH" >/dev/null
    git -C "$REPO_ROOT" show-ref --verify --quiet "$remote_ref" || die "Branch remota 'origin/$BASE_BRANCH' não encontrada."

    remote_sha="$(git -C "$REPO_ROOT" rev-parse "$remote_ref")"

    if ! git -C "$REPO_ROOT" show-ref --verify --quiet "$local_ref"; then
        git -C "$REPO_ROOT" branch "$BASE_BRANCH" "$remote_ref" >/dev/null
        return 0
    fi

    local_sha="$(git -C "$REPO_ROOT" rev-parse "$local_ref")"
    if [ "$local_sha" = "$remote_sha" ]; then
        return 0
    fi

    if git -C "$REPO_ROOT" merge-base --is-ancestor "$BASE_BRANCH" "$remote_ref"; then
        git -C "$REPO_ROOT" branch -f "$BASE_BRANCH" "$remote_ref" >/dev/null 2>&1 || die "Não foi possível atualizar '$BASE_BRANCH'. Verifique se ela está checkout em outro worktree."
        return 0
    fi

    die "Branch local '$BASE_BRANCH' divergiu de origin/$BASE_BRANCH. Resolva isso antes de criar nova sessão."
}

ensure_worktree() {
    mkdir -p "$WORKTREE_ROOT"

    git -C "$REPO_ROOT" show-ref --verify --quiet "refs/heads/$BASE_BRANCH" || die "Branch base '$BASE_BRANCH' não encontrada."

    if [ -d "$SESSION_WORKTREE/.git" ] || [ -f "$SESSION_WORKTREE/.git" ]; then
        return 0
    fi

    if git -C "$REPO_ROOT" show-ref --verify --quiet "refs/heads/$SESSION_BRANCH"; then
        git -C "$REPO_ROOT" worktree add "$SESSION_WORKTREE" "$SESSION_BRANCH" >/dev/null
    else
        git -C "$REPO_ROOT" worktree add -b "$SESSION_BRANCH" "$SESSION_WORKTREE" "$BASE_BRANCH" >/dev/null
    fi
}

print_env_exports() {
    cat <<EOF
export SESSION_NAME=$(quote_shell "$SESSION_NAME")
export SESSION_SLUG=$(quote_shell "$SESSION_SLUG")
export SESSION_WORKTREE=$(quote_shell "$SESSION_WORKTREE")
export SESSION_BRANCH=$(quote_shell "$SESSION_BRANCH")
export APP_PORT=$(quote_shell "$APP_PORT")
export TEST_DATABASE_NAME=$(quote_shell "$TEST_DATABASE_NAME")
EOF
}

show_session_summary() {
    printf 'Sessão: %s\n' "$SESSION_SLUG"
    printf 'Worktree: %s\n' "$SESSION_WORKTREE"
    printf 'Base: %s\n' "$BASE_BRANCH"
    printf 'Branch: %s\n' "$SESSION_BRANCH"
    printf 'Runserver: http://127.0.0.1:%s\n' "$APP_PORT"
    printf 'Banco de teste: %s\n' "$TEST_DATABASE_NAME"
}

cmd_create() {
    local name="$1"
    local db_slug
    SESSION_NAME="$name"
    SESSION_SLUG="$(slugify "$name")"
    db_slug="${SESSION_SLUG//-/_}"
    SESSION_WORKTREE="$WORKTREE_ROOT/$SESSION_SLUG"
    SESSION_BRANCH="opencode/$SESSION_SLUG"
    SESSION_FILE="$(session_file_path "$SESSION_SLUG")"

    sync_base_branch

    if [ -f "$SESSION_FILE" ]; then
        # shellcheck source=/dev/null
        source "$SESSION_FILE"
        ensure_worktree
        show_session_summary
        printf 'Use: source <(bin/dev-session.sh print-env %s)\n' "$SESSION_SLUG"
        return 0
    fi

    APP_PORT="$(reserve_port)"
    TEST_DATABASE_NAME="test_suap_${db_slug}"

    ensure_worktree
    write_session_file "$SESSION_FILE"

    show_session_summary
    printf 'Use: source <(bin/dev-session.sh print-env %s)\n' "$SESSION_SLUG"
}

cmd_print_env() {
    local slug
    slug="$(slugify "$1")"
    load_session "$slug"
    print_env_exports
}

cmd_enter() {
    local slug
    slug="$(slugify "$1")"
    load_session "$slug"
    print_env_exports
    printf 'cd %q\n' "$SESSION_WORKTREE"
}

cmd_runserver() {
    local slug="$1"
    shift || true
    slug="$(slugify "$slug")"
    load_session "$slug"
    ensure_worktree

    if port_in_use "$APP_PORT"; then
        die "Porta ${APP_PORT} já está em uso. Escolha nova sessão ou libere a porta."
    fi

    (
        cd "$SESSION_WORKTREE"
        export APP_PORT TEST_DATABASE_NAME
        python manage.py runserver "0.0.0.0:${APP_PORT}" "$@"
    )
}

cmd_test() {
    local slug="$1"
    shift || true
    slug="$(slugify "$slug")"
    load_session "$slug"
    ensure_worktree

    (
        cd "$SESSION_WORKTREE"
        export TEST_DATABASE_NAME
        python manage.py test_suap --noinput --failfast "$@"
    )
}

cmd_list() {
    local file
    [ -d "$SESSIONS_DIR" ] || return 0

    for file in "$SESSIONS_DIR"/*.env; do
        [ -e "$file" ] || continue
        unset SESSION_NAME SESSION_SLUG SESSION_WORKTREE SESSION_BRANCH APP_PORT TEST_DATABASE_NAME
        # shellcheck source=/dev/null
        source "$file"
        printf '%s\t%s\t%s\t%s\n' "$SESSION_SLUG" "$APP_PORT" "$SESSION_BRANCH" "$SESSION_WORKTREE"
    done
}

cmd_status() {
    local slug="${1:-}"
    local file
    local dirty_state
    local branch_name

    if [ -n "$slug" ]; then
        slug="$(slugify "$slug")"
        load_session "$slug"
        if [ -d "$SESSION_WORKTREE" ]; then
            branch_name="$(git -C "$SESSION_WORKTREE" branch --show-current 2>/dev/null || true)"
            if [ -n "$(git -C "$SESSION_WORKTREE" status --short 2>/dev/null || true)" ]; then
                dirty_state='dirty'
            else
                dirty_state='clean'
            fi
        else
            branch_name='missing'
            dirty_state='missing'
        fi

        printf 'Sessão: %s\n' "$SESSION_SLUG"
        printf 'Worktree: %s\n' "$SESSION_WORKTREE"
        printf 'Branch: %s\n' "$branch_name"
        printf 'Porta: %s\n' "$APP_PORT"
        printf 'Banco de teste: %s\n' "$TEST_DATABASE_NAME"
        printf 'Estado: %s\n' "$dirty_state"
        return 0
    fi

    [ -d "$SESSIONS_DIR" ] || return 0
    for file in "$SESSIONS_DIR"/*.env; do
        [ -e "$file" ] || continue
        unset SESSION_NAME SESSION_SLUG SESSION_WORKTREE SESSION_BRANCH APP_PORT TEST_DATABASE_NAME
        # shellcheck source=/dev/null
        source "$file"

        if [ -d "$SESSION_WORKTREE" ]; then
            branch_name="$(git -C "$SESSION_WORKTREE" branch --show-current 2>/dev/null || true)"
            if [ -n "$(git -C "$SESSION_WORKTREE" status --short 2>/dev/null || true)" ]; then
                dirty_state='dirty'
            else
                dirty_state='clean'
            fi
        else
            branch_name='missing'
            dirty_state='missing'
        fi

        printf '%s\t%s\t%s\t%s\t%s\n' "$SESSION_SLUG" "$APP_PORT" "$branch_name" "$dirty_state" "$SESSION_WORKTREE"
    done
}

cmd_remove() {
    local slug
    local status_output
    slug="$(slugify "$1")"
    load_session "$slug"

    if [ -d "$SESSION_WORKTREE" ]; then
        status_output="$(git -C "$SESSION_WORKTREE" status --short)"
        if [ -n "$status_output" ]; then
            die "Worktree '${SESSION_WORKTREE}' possui mudanças não commitadas."
        fi

        git -C "$REPO_ROOT" worktree remove "$SESSION_WORKTREE" >/dev/null
    fi

    rm -f "$SESSION_FILE"
    printf 'Sessão removida: %s\n' "$slug"
}

main() {
    local command="${1:-}"
    case "$command" in
        create)
            [ $# -ge 2 ] || die 'Informe nome da sessão.'
            shift
            cmd_create "$1"
            ;;
        print-env)
            [ $# -ge 2 ] || die 'Informe nome da sessão.'
            shift
            cmd_print_env "$1"
            ;;
        enter)
            [ $# -ge 2 ] || die 'Informe nome da sessão.'
            shift
            cmd_enter "$1"
            ;;
        runserver)
            [ $# -ge 2 ] || die 'Informe nome da sessão.'
            shift
            cmd_runserver "$@"
            ;;
        test)
            [ $# -ge 2 ] || die 'Informe nome da sessão.'
            shift
            cmd_test "$@"
            ;;
        status)
            shift || true
            cmd_status "${1:-}"
            ;;
        list)
            cmd_list
            ;;
        remove)
            [ $# -ge 2 ] || die 'Informe nome da sessão.'
            shift
            cmd_remove "$1"
            ;;
        -h|--help|help|'')
            usage
            ;;
        *)
            die "Comando inválido: $command"
            ;;
    esac
}

main "$@"
