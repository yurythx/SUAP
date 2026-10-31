@AGENTS.md

# Claude Code

Tool-specific notes for Claude Code. The shared project guidance (commands, architecture,
conventions, tests, skills, subagents) lives in `AGENTS.md`, imported above; the shared hooks,
subagent bodies and skills live in `.agents/` (`## Configuração dos agentes`). `.claude/` keeps
only the Claude wiring: `settings.json`, `launch.json`, the skill symlinks and the subagent registrations.

## Skills

Claude Code discovers skills only from `.claude/skills/`, so every skill in `.agents/skills/` is exposed there via symlink (e.g. `.claude/skills/sentry-fix -> ../../.agents/skills/sentry-fix`), except `code-review`, which would shadow Claude Code's built-in skill. The domain experts (`ponto-expert`, `rsc-docente-expert`, `setor-expert`) were `/suap:*` commands and are now skills: `/ponto-expert` etc. Tool names in shared skills follow OpenCode conventions (`sentry_get_sentry_resource`, `gitlab_create_merge_request`); on Claude Code, resolve them to the MCP equivalents `mcp__sentry__*` / `mcp__gitlab__*` (load schemas via `ToolSearch` first). The skill catalog and triggers are in `AGENTS.md` (`## Skills`).

## Subagents

Registrations live in `.claude/agents/*.md`: Claude frontmatter (`tools`, `model` per the table below, `effort`) plus a one-line body telling the agent to read the shared prompt in `.agents/agents/<nome>.md`. Edit the prompt there, never here. The catalog and triggers are in `AGENTS.md` (`## Subagents`).

## Roteamento de modelos

Aplica o critério de `## Roteamento de modelos por risco` (`AGENTS.md`) aos modelos do Claude Code:

| Risco | Exemplos | Modelo |
|---|---|---|
| Baixo | busca/exploração (`Explore`), fan-out somente leitura, triagem de leitura | `haiku` |
| Médio | `suap-frontend` (classes validadas por grep), `documentador` (revisado no MR) | `sonnet` |
| Alto | `security-reviewer`, `migration-reviewer`, `query-perf-reviewer` (revisão de código), `e2e-tester` (`--rotas` é cego a `/admin/`), `documentador-usuario`, migrations, permissões | `opus` |

- Subagente: o modelo fica no frontmatter (`model:`) do registro em `.claude/agents/*.md` (nunca no corpo compartilhado em `.agents/agents/`); ao criar um, classifique-o por esta tabela.
- Ao despachar pela ferramenta `Agent`, passe `model` (`haiku` no risco baixo, `sonnet` no médio); no alto, omita (herda) ou use `opus`.
- `effort` (`xhigh`→`high`) é uma alavanca menor: reduza-o antes de rebaixar o modelo de um agente de alto risco.

## Config

- **Hooks** (`.claude/settings.json`) - Auto-runs `ruff format` on the edited `.py` and blocks (`exit 2`) edits to `.env`/`.env.*` by running the shared guard `.agents/hooks/protect_env.py`; a second `PreToolUse` hook (matcher `Bash`) runs the shared commit gate `.agents/hooks/commit_gate.py`, which prefixes every `git commit` segment with `uv run ruff format .`, `uv run ruff check . --fix --unsafe-fixes`, `git add -u` and `uv run pre-commit run --from-ref origin/master --to-ref HEAD` (`--no-verify`/`-n` skip). It returns only `updatedInput`, without `permissionDecision`, so the rewritten command still goes through the normal permission flow. Hooks receive the tool payload as JSON on stdin (`tool_input.file_path`); Claude Code exports no path env var, so an inline `$CLAUDE_TOOL_INPUT_PATH` is always empty (the old one-liners were silent no-ops). In desktop-app worktree sessions, settings and hooks are read from the main checkout's root, so a hook change only takes effect there after it reaches that checkout. `PostToolUse` also runs `.agents/hooks/check_complexity.py`, which **blocks** the edit when a touched function exceeds cyclomatic complexity 10 (ruff `C901`). A second `PostToolUse` hook (matcher `mcp__gitlab__create_merge_request|mcp__gitlab__update_merge_request|Bash`) runs `.agents/hooks/register_mr_time_spent.py --sob-pedido`, which records measured time spent on MR create/update via `/spend` — **on Claude Code only when asked**: the command must start with the inline prefix `REGISTRAR_TEMPO=True glab mr create|update ...` (first token of the command; `cd x && REGISTRAR_TEMPO=True ...` records nothing). Run `glab mr` directly through Bash — a wrapper that swallows its output hides the MR URL the hook reads. Through the GitLab MCP tool nothing is recorded on Claude Code. Codex and OpenCode call the script without the flag and record on every MR. How the hours are measured, the delta-on-update rule and the adapter contract are documented in the script's module docstring; its tests are `.agents/hooks/test_register_mr_time_spent.py` (run directly — pytest skips the hidden `.agents/` dir); `--horas [base]` and `--dry-run` are for manual runs. `$CLAUDE_PROJECT_DIR` points to the main checkout even in worktree sessions, so hook commands always run the main checkout's scripts. Hook scripts use the shebang `#!/usr/bin/env -S uv run --quiet python3`: ruff targets py314 (`except A, B:` without parentheses, PEP 758), so a plain `python3` shebang resolves to the system 3.12 and fails with `SyntaxError`.
- **MCP Servers** - nothing is committed: `.mcp.json` is gitignored and per-developer. context7 (live Django/Celery docs) comes from the `context7` plugin; Sentry (direct issue/trace queries, needs `SENTRY_AUTH_TOKEN`) and the `suap` MCP (GitLab/Sentry/PGD tools) are usually user-scoped in `~/.claude.json`.
- **`.worktreeinclude`** - gitignored files Claude Code copies into every new worktree (CLI `--worktree`, subagent `isolation: worktree`, desktop-app sessions): `suap/settings.py`. `.env` is left out: Django's `load_dotenv()` walks up and finds the main checkout's, but `make` targets (`make check-env`) need a `.env` at the worktree root — copy it by hand or run `make` from the main checkout.
- **`worktree.symlinkDirectories`** (`.claude/settings.json`) - `.venv` is symlinked (not copied) from the main checkout into every new worktree: a copied venv would cost ≈1.4 GB and still point to the main one (the `bin/` shebangs and `activate` carry the absolute path). The venv is shared, so `uv sync`/`uv run` in a worktree whose `uv.lock` differs changes the main checkout's venv too — for a dependency branch, `rm .venv && uv sync` in the worktree to get a private one.
