# AGENTS.md — SUAP

Single source of agent guidance for this repo. **Codex**, **OpenCode** and **Antigravity** read this
`AGENTS.md` natively; **Claude Code** and the **Gemini CLI** read it via the `@AGENTS.md` import at the top of
`CLAUDE.md` / `GEMINI.md`. Tool-specific notes live in `CLAUDE.md`, `GEMINI.md` and in the sections below.
Everything the agents share (hooks, subagents, skills, rules) lives in `.agents/` — see `## Configuração dos agentes`.

SUAP is a large Django 5.2 monolith (≈90 apps) for academic and public administration at IFRN. Python is pinned to 3.14.3; dependencies are managed with `uv` and locked in `uv.lock`.

## Commands

Setup / run:
- `uv sync --all-groups` — install deps (uses `pyproject.toml` groups: `dev`, `prod`).
- `python manage.py sync` — full project bootstrap, NOT just migrations (migrate + initial_data + sync_permissions + collectstatic + carregar_apis). Run this before the first `runserver`.
- `python manage.py runserver` — local dev server.
- `make runserver` / `make run` — full Docker stack (db + redis + celery + web). All `make` Docker targets require a root `.env` (copy `.env.dev.sample`); `make check-env` blocks otherwise. See `make help` for the full target list.
- `python manage.py gerar_banco_mock` — gera um dump (`pg_dump -Fc`) com um banco SUAP inteiro de dados fictícios (seeds e2e + volume sintético, senha `123`). Ver `docs/banco-mock.md`.

Tests (use `pytest`, NOT `python manage.py test`):
- `pytest -q app/tests/test_file.py::TestClass::test_name` — single test.
- `pytest -q -m "not e2e and not doc" app` — one app's unit tests (without `-m`, the app's e2e/doc tests are collected too and error out on the guard below).
- e2e/doc suites need a `TEST_DATABASE_NAME` with `_e2e` in it (`test_suap_e2e`, `test_suap_doc_e2e`): the `_exige_banco_de_e2e` guard (`djtools/e2e_fixtures.py`) aborts before creating or seeding the DB otherwise. See item 2 of the traps in `docs/agents/e2e-receita.md`.
- Test settings auto-activate under pytest: `MIGRATE=False`, `--no-migrations` (see `[tool.pytest.ini_options]`). Migrations are skipped, so the schema comes from current models.
- `USE_CELERY` is forced to `False` in both test settings paths — unconditionally in `suap/settings_test.py`, and in `suap/settings_sample.py` via the test override block, whose condition is `'test_behave' in sys.argv or 'pytest' in sys.modules` (so `suap.settings` only gets it if your personal copy has that condition) — so `@task` runs synchronously. It is needed because `load_dotenv()` walks up parent directories: a worktree in `.claude/worktrees/` picks up the main checkout's `.env` (`USE_CELERY=True`), and without a worker the task is enqueued and never runs. The guard lives in the settings module, not in `conftest.py`, because pytest-django calls `django.setup()` before the root conftest and `djtools/assincrono` reads the flag at import. That block also applies the rest of the behave overrides under pytest with `suap.settings`: `DEBUG=False`, `USE_REDIS`/`USE_SENTRY=False`, `OAUTH2_PROVIDER_APPLICATION_MODEL='oauth2_provider.Application'`, fixed storage/cookie names. `suap.settings_test` does not inherit the sample, so only `USE_CELERY` is forced there.
- BDD/behave: `python manage.py test_behave --behave_stop --noinput <app>`.
- **No populated DB needed, but a Postgres is.** `--no-migrations` builds the whole schema (≈100 apps) in ONE transaction, which needs Postgres `max_locks_per_transaction` well above the default (64) — otherwise `OperationalError: out of shared memory`. The schema is created fresh from the models, so no `manage.py sync`/dump is required; only a reachable Postgres with the lock budget raised. The shared dev DB usually can't be tuned, so point tests at a dedicated/tuned Postgres via the env-driven `suap/settings_test.py` (committed; inherits `settings_base`, reads `DATABASE_HOST/PORT/USER/PASSWORD/NAME`, builds a throwaway `test_suap`). With nothing installed locally, an ephemeral Docker Postgres works:
  - `docker run --rm -d --name suap-test-db -p 5433:5432 -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres postgres:18 -c max_locks_per_transaction=4096 -c shared_preload_libraries=pg_stat_statements`
  - `DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest --create-db <app>` (use `--reuse-db` on later runs).

Lint / CI parity (order matters — pre-commit is fail-fast):
- `ruff format .` → `ruff check . --fix --unsafe-fixes` → djlint/hooks/prints.
- `pre-commit run --from-ref origin/master --to-ref HEAD` — the exact CI check (also `make pre-commit-ci`).
- `python manage.py suap_check` — full check; modes via `SUAP_CHECK=code|django|e2e|e2e-transversal|behave|behave-changed|coverage` (default runs all). Changed-file logic compares against `origin/master` (`git diff --name-only origin/master..`). `SUAP_CHECK=django` with `SUAP_APPS=dependentes` runs only the modules touched plus their **direct** dependents in `module_dependencies.json` (inverted); files in `djtools/`, `comum/`, `rh/` or the root `conftest.py` run everything. `SUAP_APPS=tocados` (what the MR e2e jobs use) runs only the modules the diff touches — no dependents, no fallback: with them nearly every MR ran all 15 e2e suites (≈45 min per shard); the nightly covers the rest. `SUAP_APPS=geral` runs everything. Under `parallel` (`CI_NODE_TOTAL > 1`), `django` with `dependentes`/`geral` splits the selected tests across shards with pytest-split (`--splitting-algorithm least_duration`, weights in `unitario_duracoes.json`, promoted by hand from the nightly's `artifacts/unitario-duracoes-*.json`). `e2e` splits the selected suites across `CI_NODE_INDEX/CI_NODE_TOTAL`; `e2e-transversal` always runs `tests/e2e` (no selection, no shards). Both e2e modes record coverage only with `SUAP_APPS=geral`. MR jobs: `unitario-transversal`, `unitario-modulo` (3 shards), `e2e-transversal`, `e2e-modulo` (3 shards); the full run and `cobertura-combinada` happen only in the nightly scheduled pipeline.

## Architecture

**App layout.** Each top-level directory in `APPS_SUAP` (`suap/settings_base.py`) is a Django app. Apps follow conventions beyond standard Django:
- `menu.yaml` — declares the app's navigation menu entries (91 apps have one).
- `permissions.yaml` — declares the app's permission groups (92 apps have one); loaded by `sync_permissions`.
- `models/` is often a package, not a single `models.py` (e.g. `edu/models/`).

**Base model layer.** Models inherit from `djtools.db.models.ModelPlus` (`from djtools.db import models`, used in ≈247 files), NOT `django.db.models`. `djtools` is SUAP's framework layer: custom model/field classes, admin (`ModelAdminPlus`), forms, tables, PDF/report generation, middleware, security, and async (`assincrono`) helpers. It is listed in `PRE_INSTALLED_APPS_SUAP` and must load before `django.contrib.admin`.

**`comum`** is the shared-domain app: core entities (`PessoaFisica`, `Configuracao`, `Municipio`, etc.), the login views, healthcheck, webservice (XML-RPC) handler, and the global 403/404/500 handlers. `rh` (people/HR), `edu` (academics) are the other foundational domain apps that most others depend on.

**URL wiring (`suap/urls.py`).** URLs are auto-discovered: the loop over `settings.INSTALLED_APPS` includes each app's `urls.py` at `/{app}/` if it exists, plus an optional LPS override at `{app}/lps/{LPS}/urls.py`. You do not register an app's urls manually. The API (`django-ninja`, `suap/api.py`) mounts at `/api/`, admin at `/admin/`.

**App-order rewrite.** `suap/__init__.py` rewrites `INSTALLED_APPS` to `PRE_INSTALLED_APPS_SUAP + APPS_SUAP + POS_INSTALLED_APPS_SUAP` ONLY for `makemigrations`, `migrate`, and `sync`. At runtime the order in `settings_base.py` applies. When adding/removing an app, keep `APPS_SUAP` and `module_dependencies.json` in sync — validated by `python manage.py module_dependencies --check --all`.

**Async / background.** Celery (`suap/celery_app.py`) for tasks; Redis is the broker/cache. Scheduled tasks run on **Celery Beat** (`django-celery-beat`, `beat` app): each app registers its own in `<app>/beat.py` (`load_tasks_schedule` + `carregar_call_command(nome, comando, crontab={...})`, e.g. `demandas/beat.py`). `crontab=` there is only Beat's schedule syntax — the system cron (and the legacy `cron` app / `bin/ci/cron.sh`) is dead: don't add scheduled jobs there.

## Conventions / guardrails

- **Ruff is non-default:** line length 150, single quotes, `*/migrations/*` excluded. Don't fight these.
- **Complexidade ciclomática ≤ 10:** ao escrever/editar uma função `.py`, mantenha a complexidade ciclomática (ruff `C901`) **≤ 10**. A regra **não** está no `ruff` do repo (o legado tem ≈1552 funções acima disso). Para todos, o hook `complexidade-nova` do pre-commit (`bin/scripts/complexidade-nova.py`) barra função **nova** acima de 10, a que **passou** de 10 e a legada acima de 10 cuja complexidade **aumentou** (compara com a base por qualname; legado complexo editado sem piorar passa). Para agentes vale a regra mais estrita: toda **função tocada** (diff vs `HEAD`). Se uma função sua passar de 10, refatore (extraia helpers, simplifique ramos) antes de prosseguir. Núcleo compartilhado em `.agents/hooks/check_complexity.py`; Claude Code, Codex, OpenCode e Antigravity possuem somente adaptadores para acioná-lo (o do Antigravity roda no hook `Stop`, ver `## Antigravity`). No terminal: `.agents/hooks/check_complexity.py` sem argumentos checa os `.py` modificados vs `HEAD` e os não rastreados; com argumentos, só os arquivos passados (caminho relativo ao cwd). Nos dois modos só conta função tocada (arquivo rastreado sem diff não tem nenhuma; arquivo novo conta inteiro); para o arquivo inteiro use `ruff check --select C901 --config lint.mccabe.max-complexity=10 <arquivo>`. Exit 0 = ok, 2 = função tocada acima de 10, 1 = não deu para checar (ruff/git ausente, argumento que não é `.py` existente, nada para checar) — 1 não é aprovação.
- **Pyright cobre todo o repo, mas reporta seletivamente:** `pyrightconfig.json` usa `typeCheckingMode: "off"` no global e ativa as regras (≈17 `reportXxx` como `warning`) via `executionEnvironments` apenas em `comum/`, `djtools/` e `suap/`. Outros apps são parseados (para resolver imports/cycles) mas silenciados. Para tipar progressivamente um novo módulo, adicione-o como `executionEnvironment` com as mesmas regras.
- **Tipagem progressiva (boundary-typing):** ao editar qualquer `.py` no SUAP — mesmo em módulo silenciado pelo pyright — anote tipos nas defs **tocadas** (parâmetros + retorno). Não tipe arquivo inteiro de uma vez; foque na fronteira que você está alterando. Quando um módulo atingir cobertura razoável (a maioria das funções públicas anotadas) e `uv run pyright` apresentar 0 erros nele, promova-o adicionando um `executionEnvironment` em `pyrightconfig.json` espelhando o de `comum/djtools/suap`. Convenções: usar `from __future__ import annotations` quando útil; `from collections.abc import Iterable, Mapping`; `Model | None` em vez de `Optional[Model]`; evitar `Any` salvo em fronteiras com libs sem stubs.
- The repo is Portuguese-first: code identifiers, comments, commit messages, and docs are in pt-BR. Match the surrounding language.
- **Markdown (docs, MR, issue, comentário):** não escreva valor aproximado como `~1 min` / `~341 mil`. O GitLab lê `~N` como referência ao label de id N e troca o número pelo nome do label (`~547 mil` virou `wayfinder:map mil`). Use `≈1 min` ou "cerca de 1 min"; dentro de código (crase ou bloco cercado) não há problema.
- Settings: edit `suap/settings_base.py` (shared) / `suap/settings.py`; never commit secrets — `suap/settings_sample.py` is the template.
- **Scripts avulsos** (gates, geradores, utilitários de CI/dev fora de app Django) vão em `bin/scripts/`, rodados da raiz do repo (`python bin/scripts/<script>.py`); o teste vai em `tests/scripts/test_<script>.py` (sem banco, importa o script via `sys.path`, como os existentes) e roda sempre no job `unitario-transversal`. Se precisar de outro app/model, prefira um management command no app dono. `bin/` guarda só os `.sh` de serviço; `bin/ci/` é do pipeline.

## Testes

Regras para escrever testes novos (e para mexer nos existentes). Como rodar está em `## Commands`.

### Estrutura por categoria

Todo teste pytest fica em `<modulo>/tests/<categoria>/test_*.py`, criando só as categorias que se aplicam:

| Categoria | O que testa | Estilo |
|---|---|---|
| `models/` | lógica de model, managers, métodos, services puros | DB-free sempre que possível (`Factory.build()`) |
| `views/` | views, forms, endpoints da API | `client`/`RequestFactory`; DB só quando a view precisa |
| `tasks/` | tasks Celery e management commands | chamar a função `@task` direto, nunca `.delay()` (Celery é síncrono em teste) |
| `fluxos/` | fluxo de negócio de ponta a ponta (`view → ORM → banco → response`), arquivos `test_fluxo_*.py` | DB-backed |
| `e2e/` | fluxo de browser (pytest + Playwright) | ver `### e2e` abaixo |
| `doc/` | roteiros que navegam o sistema para gerar `<modulo>/docs/usuario.md` e as capturas (subagente `documentador-usuario`); **não** é regressão | marker `doc` (`pytest -m doc`), banco próprio `test_suap_doc_e2e`; reusa `djtools/e2e_fixtures.py` e o seed do `e2e/` do módulo, quando houver |

- `<modulo>/tests/conftest.py` fica na raiz de `tests/` e vale para todas as categorias; o que for de uma categoria só vai em `<modulo>/tests/<categoria>/conftest.py`.
- Nome do arquivo = o fluxo ou o alvo testado, não o bug nem o arquivo-fonte.
- Ao acrescentar teste num módulo ainda flat (`<modulo>/tests/test_*.py`), mova os existentes para as categorias (`git mv`). Referência: `edu/tests/`.
- Não crie classe-base `*TestCase` compartilhada: o pytest a coleta e roda de novo em cada módulo que a importa.

### Dados de teste: factories, não fixtures

Dados de teste são criados com **factories** (`factory_boy`, `DjangoModelFactory`), não com fixtures pytest nem com `Model.objects.create(...)` espalhado pelos testes.

- Cada app mantém as factories dos **seus** models em `<modulo>/tests/factories.py`; quem precisa de um model de outro app importa a factory do app dono (`from comum.tests.factories import AnoFactory`). Não duplique factory de model alheio. Exemplos: `auditoria/tests/factories.py`, `almoxarifado/tests/factories.py`, `rh/tests/factories.py`.
- Cada teste constrói só o que usa, explicitamente, no próprio corpo: `RelatorioFactory(ano=AnoFactory())`. Sobrescreva só os campos que importam para o teste.
- `Factory.build()` quando o teste não precisa de banco; `Factory()`/`.create()` quando precisa.
- Valores únicos via `factory.Sequence`/`LazyFunction`; `django_get_or_create` para models com chave natural (ano, nome de tipo).
- Pytest fixture fica para **infraestrutura** (cliente logado, relógio, `live_server`, seed de sessão do e2e) ou para compartilhar um grafo caro entre vários testes, e mesmo assim o corpo da fixture chama factories.
- `suap_data`/`light_data` (`comum.pytest_fixtures`) são legado: pesados (≈1 s por classe), com escopo de classe e commitados sem teardown (flakeiam sob `-n 4` em asserts de contagem global). Não use em teste novo. O substrato de pessoal tem factories em `rh/tests/factories.py`: `SetorFactory` (já com campus), `SetorSiapeFactory`, `ServidorFactory` (cria `User` e `Vinculo`). Referência de migração: `auditoria/tests/`, que ao sair do `suap_data` caiu de 51 s para 42 s.
- `ServidorFactory` exige a fixture `sync_permissions` (o `save` busca grupos por nome) e custa ≈140 ms: crie só os servidores que o teste usa. As factories ganham porque o teste monta 2–3 objetos em vez do grafo inteiro, não porque criar objeto seja barato: um teste que precise de muitos servidores pode sair mais lento.

### Estilo

- Teste o **comportamento observável** (request HTTP, command, task, endpoint), não detalhe de implementação: nada de assert em atributo, kwarg ou método privado introduzido pela mudança.
- Um teste por fluxo, não um por função ou branch alterado.
- Não mocke a unidade sob teste. Mock só em fronteira externa (rede, serviço externo, tempo, filesystem). Usuário com permissão é um usuário real com a permissão, não `has_perm` mockado.
- Nem o ORM: nada de `patch.object(Model.objects, 'filter')` + `MagicMock` nem `Form.__new__(Form)` para simular queryset quando a unidade executa queries. Mock no ORM esconde regressão de semântica SQL (`exclude` em campo anulável, join, herança multi-tabela) e acopla o teste à escrita da query; nada de `assert_called_once_with` nos kwargs do ORM.
- Se já existe teste do fluxo, estenda o arquivo em vez de criar outro.
- Asserts de contagem: espelhe o ORM (`Model.objects.filter(...).count()`), não fixe magnitudes absolutas.

### Ambiente de teste (`conftest.py` raiz)

- Sem migrations: schema vindo dos models atuais (ADR-0002).
- Forces `USUARIOGRUPO_AS_ABSTRACT=1` and `USE_EDU_LOG=False`.
- Patches `oauth2_provider.decorators.protected_resource` to a no-op.
- Creates PG extensions (`unaccent`, `pg_trgm`, `pg_stat_statements`), the `ignore_accents_case` ICU collation, and the `f_unaccent` function in the test DB.
- Tests using the `suap_data` / `light_data` fixtures (from `comum.pytest_fixtures`) auto-get `@pytest.mark.django_db(databases='__all__')`.

### e2e (pytest + Playwright)

Browser flows live in `<modulo>/tests/e2e/` (plus the cross-cutting `tests/e2e/`) and reuse `djtools/e2e_fixtures.py` + `djtools/e2e_ui.py`. Before writing e2e tests for a module, read `docs/agents/e2e-receita.md`: behave→pytest mapping, commented conftest/test skeletons, the per-module decisions (seed, roles, clock, chaining), and the known traps. Gate: `python bin/scripts/paridade_e2e.py <modulo> --rotas` with zero uncovered routes. Here the session seed is a fixture by necessity (`live_server`), but it builds its data with the module's factories.

## Configuração dos agentes (`.agents/`)

O SUAP é desenvolvido com vários harnesses (Claude Code, Codex, OpenCode, Antigravity/Gemini). Para que todos se comportem igual, **tudo o que é compartilhado vive uma vez só em `.agents/`**; `.claude/`, `.codex/`, `.opencode/` e `GEMINI.md` guardam só o que é específico do harness (manifesto de hooks, adaptadores finos, registros de subagente com frontmatter próprio, symlinks).

| Caminho | Conteúdo | Quem lê |
|---|---|---|
| `.agents/hooks/` | núcleo Python dos hooks: `check_complexity.py` (C901), `protect_env.py` (`.env*`), `commit_gate.py` (checagens antes de `git commit`), `register_mr_time_spent.py` (time spent do MR), `hook_payload.py` (normaliza payload), e os testes `test_*.py` | adaptadores de cada harness |
| `.agents/agents/<nome>.md` | corpo canônico de cada subagente, frontmatter neutro (`name`, `description`) | Antigravity nativo; os outros por ponteiro |
| `.agents/skills/<nome>/` | skills | Codex, OpenCode, Antigravity nativo; Claude Code por symlink |
| `.agents/rules/suap.md` | guardrails operacionais (sempre ativos) | Antigravity nativo; Gemini CLI via `GEMINI.md` |
| `.agents/hooks.json`, `.agents/hooks/antigravity_*.py` | manifesto e adaptador do Antigravity: `.agents/` é a pasta nativa dele, então o que é só dele mora aqui | Antigravity |
| `.agents/templates/<agente>/` | templates dos subagentes (hoje só o `documentador`) | o subagente |

Regras:
- Mudou comportamento? Mude o núcleo em `.agents/`, nunca o adaptador. Adaptador só traduz payload/saída do harness.
- Subagente novo: corpo em `.agents/agents/<nome>.md` + um registro em `.claude/agents/`, `.opencode/agent/` e `.codex/agents/`, todos com a **mesma** `description`. Skill nova: pasta em `.agents/skills/` + symlink em `.claude/skills/` (exceto `code-review`, que colide com a skill embutida do Claude Code). `tests/test_configuracao_agentes.py` (job `unitario-transversal`) barra a divergência.
- Os testes em `.agents/hooks/` ficam em diretório oculto, que o pytest não coleta sozinho: rode-os direto (`.agents/hooks/test_check_complexity.py`, `.agents/hooks/test_register_mr_time_spent.py`) ou nomeando o arquivo (`pytest .agents/hooks/test_guardas.py`).
- `hook_payload.py`, `protect_env.py`, `commit_gate.py` e `antigravity_check_complexity.py` rodam no `python3` do sistema (3.12) a cada chamada: nada de sintaxe só do 3.14 (`except A, B:`). Os outros usam o shebang `uv run`.

## Skills

Skills live in `.agents/skills/<name>/SKILL.md`, read natively by Codex, OpenCode and Antigravity; Claude Code sees them through symlinks in `.claude/skills/` (see `CLAUDE.md`).

Workflow:
- **sentry-fix** — given a Sentry issue URL, fixes it end-to-end: fetch → analyze → fix branch → code fix (no tests) → pre-commit → push → open GitLab MR, referencing the issue ID. Trigger: `/sentry-fix <url>`, "fix this sentry error", "corrige esse erro do sentry".
- **code-review** — multi-language PR review guidance (read-only). Trigger: reviewing PRs / code changes.
- **mr-format** — formats GitLab MR title/description to SUAP convention (`[module] Brief description` + Descrição sections). Trigger: `/mr-format <url>`, "padronizar mr".
- **carga-horaria** — esforço da tarefa pelo tempo ativo medido (`.agents/hooks/register_mr_time_spent.py --horas`); não mexe no MR. Trigger: `/carga-horaria`, "quanto tempo levou".
- **pgd-rit** — lança a execução (RIT) de um MR no PGD, com dry-run e confirmação antes de gravar; modo lote por mês. Trigger: `/pgd-rit`, `/pgd-rit lote AAAA-MM`, "lançar execução no pgd".
- **pgd-rit-merge** — headless no CI após o merge: só comenta no MR o RIT lançado (ou lembra o lançamento manual). Trigger: `/pgd-rit-merge`.
- **migration-check** — roda `makemigrations --check --dry-run` nos apps tocados e lista migrations faltando antes do CI (`checagem-codigo`); só reporta, não gera. Trigger: `/migration-check`, "checar migrações", "faltam migrations".
- **loop-bugfix** — corrige uma fila de issues numa janela deslizante de N MRs em voo; só o usuário dispara. Trigger: `/loop-bugfix <issues> [janela=N]`, "loop de bugfix".

Especialistas de domínio (assumem o papel e respondem com o mapa do módulo):
- **ponto-expert** — módulo `ponto` (frequência, abonos, compensação, recessos, REP). Trigger: `/ponto-expert`.
- **rsc-docente-expert** — módulo `rsc` (RSC docente EBTT; não é o `rsc_tae`). Trigger: `/rsc-docente-expert`.
- **setor-expert** — `rh.Setor`: impacto na hierarquia e unificação SUAP→SIAPE. Trigger: `/setor-expert`.


### Issue tracker

Issues for this repo are tracked in GitLab and managed via `glab`. See `docs/agents/issue-tracker.md`.

### Triage labels

Triage uses canonical labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Domain docs use single-context layout (`CONTEXT.md` + `docs/adr/` at repo root). See `docs/agents/domain.md`.

## Subagents

The prompt body of each subagent lives once in `.agents/agents/<nome>.md` (frontmatter neutro: só `name` e `description`; o Antigravity lê esse diretório nativamente). Each other tool has a thin registration that carries its own frontmatter (model, tools, permissions) and tells the agent to read that body: Claude Code `.claude/agents/<nome>.md`, OpenCode `.opencode/agent/<nome>.md`, Codex `.codex/agents/<nome>.toml`. Catalog:

- **documentador** — docs técnicos de um módulo em `<modulo>/docs/` (README, HLA, glossário, fluxos, ERD, fronteira); templates em `.agents/templates/documentador/`. Trigger: "documentar o módulo <x>", "atualizar HLA", "ERD do módulo".
- **documentador-usuario** — manual de usuário final (`<modulo>/docs/usuario.md`) navegando o sistema com Playwright, sessão pytest `doc` no banco `test_suap_doc_e2e`. **Nunca contra homologação ou produção** (o site publicado é público). Trigger: "gera o manual do <modulo>", "doc de usuário do <modulo>".
- **e2e-tester** — suíte e2e (pytest + Playwright, idioma `Tela`) cobrindo todas as rotas de um módulo, até o gate `bin/scripts/paridade_e2e.py <modulo> --rotas` zerar; paridade 1:1 com o behave só se pedida. Trigger: "gera os e2e do <modulo>", "cobre as telas do <modulo>".
- **suap-frontend** — telas (template + view) estritamente no Design System (`docs/design-system.md`): só classes existentes, sem `style=""` nem cor fixa. Trigger: "cria uma tela", "padroniza essa tela".
- **migration-reviewer** — revisão só de leitura de migrations e schema (perda de dado, índice/UNIQUE perdido, `CASCADE` implícito, lock; remoção de model é só de state). Trigger: "revisa as migrations".
- **query-perf-reviewer** — revisão só de leitura de N+1 e queries, cada achado medido com `CaptureQueriesContext`. Trigger: "tem N+1 aqui?", "essa tela está lenta".
- **security-reviewer** — revisão só de leitura de segurança (bypass de autenticação, permissão, IDOR, injeção SQL, input inseguro em task Celery). Trigger: "revisa a segurança", MR que toca auth/views com GET/POST/API Ninja/tasks.

## Roteamento de modelos por risco

O modelo de um agente é escolhido pelo **risco** da tarefa, não pela dificuldade: "um erro passaria despercebido?". Risco **baixo** (saída conferida no olho, revisada no MR, ou somente leitura) → modelo barato; risco **alto** (auth, permissão, migration, dado de produção, segurança, revisão de código, gate sabidamente fraco) → modelo forte; na dúvida, suba um nível. No CI o padrão (`OPENCODE_MODEL`) já é barato; `bin/ci/opencode-skill.sh` sobe o `code-review` para `OPENCODE_MODEL_ALTO_RISCO` quando definida. O mapeamento para os modelos do Claude Code está em `CLAUDE.md`.

## Codex

- **Instruction loading.** Codex reads this `AGENTS.md` natively. `.codex/` contains only project adapters, hook tests and thin custom-agent registrations; credentials, logs, cache and personal settings remain ignored.
- **Hooks** (`.codex/hooks.json`): `PreToolUse` blocks `.env*` edits (shared `.agents/hooks/protect_env.py`) and rewrites `git commit` to run the project gate (`.codex/hooks/pre_commit.py` → shared `commit_gate.py`, answering `allow` as Codex requires); `PostToolUse` invokes the shared C901 checker after `apply_patch`. These are blocking guardrails. MR time registration also runs on `PostToolUse`, but asynchronously and best-effort: failures are diagnostic and never block MR creation/update.
- **Shared core.** Everything lives in `.agents/hooks/` (see `## Configuração dos agentes`). Codex adapters under `.codex/hooks/` must stay thin.
- **Trust.** Repo hooks run only after the user reviews and trusts the project `.codex/` layer. Inspect them with `/hooks` when Codex reports pending review.
- **Subagents** (`.codex/agents/*.toml`): one thin registration per `.agents/agents/*.md`, pointing to the body instead of copying it.

## Antigravity

- **Instruction loading.** Antigravity reads this `AGENTS.md`, `GEMINI.md` and `.agents/rules/*.md` natively (rules need `trigger:` frontmatter); subagents from `.agents/agents/` and skills from `.agents/skills/`.
- **Hooks** (`.agents/hooks.json`, carregado só depois que o workspace é marcado como confiável): o `PostToolUse` do Antigravity não bloqueia nem devolve nada ao modelo, então o C901 roda no `Stop`. `.agents/hooks/antigravity_check_complexity.py` (adaptador; fica em `.agents/` porque é a pasta nativa do Antigravity) chama o núcleo `.agents/hooks/check_complexity.py` no modo sem argumentos e, no exit 2, responde `{"decision": "continue", "reason": ...}`, que devolve o agente ao loop com o relatório; árvore limpa ou falha deixam encerrar. O `command` assume caminho relativo a `.agents/` (inferido dos exemplos da documentação, **não testado ao vivo**); o adaptador roda no `python3` do sistema e chama o núcleo pelo `.venv/bin/python`, sem depender do `uv` no PATH do hook.

## OpenCode

- **Instruction loading.** OpenCode reads this `AGENTS.md` natively. `opencode.json` defines its subagents and MCP servers; no `instructions` field is needed.
- **Subagents** (`.opencode/agent/*.md`): um ponteiro fino por `.agents/agents/*.md` (os revisores só leitura com `edit: deny`). Frontmatter em YAML (`---`): o OpenCode não lê TOML (`+++`) e carrega o agente como `primary`, sem descrição. `mode: all` deixa o agente delegável e selecionável como principal; restrição de ferramentas vai em `permission` (`tools` é deprecated). Confira com `opencode debug agents`.
- **Modelos por agente** (`## Roteamento de modelos por risco`): o mapeamento é pessoal, em `agent.<nome>.model` no `~/.config/opencode/opencode.json`. Não fixe `model` em `.opencode/agent/*.md`: o CI autentica um único provedor (`OPENCODE_PROVIDER`) e o subagente sem `model` herda o modelo de quem o chamou.
- **Plugins** (`.opencode/plugin/*.ts`): each file has a single `export default { id, setup, server }` that serves both plugin APIs — `setup(ctx)` is OpenCode 2.x (registers `ctx.tool.hook('execute.before'|'execute.after', ...)`), `server(input)` is the 1.x object form (returns `tool.execute.before`/`tool.execute.after`), kept for local 1.x installs; the CI image runs 2.x (`GITLAB_OPENCODE_VERSION` in `bin/ci/Dockerfile.opencode`, where the provider key comes from `OPENCODE_API_KEY`, not `auth.json`); each loader reads only its own key. On 2.x the shell tool is `shell` (1.x: `bash`), `edit`/`write` take `input.path` (1.x: `args.filePath`) and a v2 hook must never throw — a rejection becomes a defect that kills the turn, not a tool error. Every file in the folder is loaded as a plugin, so don't put shared helper modules there. When a worktree lives inside the main checkout, 2.x discovers both `.opencode/` dirs and keeps only the first plugin per `id` (the main checkout's, per the 2.0.18 source), reporting the other as `Duplicate plugin ID`: a plugin edit in such a worktree only takes effect once the main checkout has it too.
  - `pre-commit.ts` — rewrites `git commit` commands through the shared `.agents/hooks/commit_gate.py` (`ruff format` → `ruff check --fix --unsafe-fixes` → `git add -u` → `pre-commit`, via `uv run`); `--no-verify`/`-n` skip.
  - `check-complexity.ts` — after-execution hook that flags when a touched `.py` function exceeds cyclomatic complexity 10 (ruff `C901`), reusing the shared `.agents/hooks/check_complexity.py`. On 1.x it blocks via `throw`; on 2.x (where only `execute.before` may fail) it appends the ruff report to the tool result the model receives. Covers `edit`/`write` and, on 2.x, `patch` (the patch text goes to the Python side as `command`).
  - `register-mr-time-spent.ts` — after `gitlab_create_merge_request`/`gitlab_update_merge_request` and shell `glab mr create|update`, records the MR's time spent via the shared `.agents/hooks/register_mr_time_spent.py` (measurement, delta-on-update and iid harvesting are documented in its module docstring). Fire-and-forget, never throws. OpenCode exposes no transcript, so it falls back to LOC backfiring (≈50 LOC/hour). Mirrored on Claude Code via `.claude/settings.json` (see `CLAUDE.md`).
- **CI.** GitLab CI stages include `ai-review`; MR automation jobs call OpenCode skills via `bin/ci/opencode-skill.sh`.
