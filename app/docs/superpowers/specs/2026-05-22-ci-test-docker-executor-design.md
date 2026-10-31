# Refatoração do estágio de testes para docker executor com isolamento por job

**Data:** 2026-05-22
**Branch:** `ci-test-docker-executor`
**Autor:** Hugo Tacito (com Claude)

## Objetivo

Refatorar todos os jobs de teste do `.gitlab-ci.yml` para rodar em **runners com executor docker**, maximizando o isolamento entre execuções concorrentes. Substituir o modelo atual (shell executor + `docker run` manual + estado compartilhado) por jobs que rodam dentro de um container de imagem versionada, com serviços (`postgres`, `mailhog`, `pdfprinter`) efêmeros e isolados por job.

## Estado atual e problemas

O modelo atual usa **shell executor** (tags `tests-v3`, `qa-v3`). Cada job chama `bin/ci/test.sh`, que:

- faz `docker run` de uma imagem `suap-test` **construída localmente** no runner (nunca publicada no registry);
- **bind-monta o checkout** do runner (`$CI_PROJECT_DIR:/suap`);
- junta o container à rede compartilhada e persistente `ci_suap-network`;
- usa serviços **compartilhados** entre todos os jobs: `postgres`, `web`, `pdfprinter`, `mail` (subidos via `bin/ci/docker-compose.yaml`, projeto `ci`);
- isola o banco apenas pelo **nome** (`DEFAULT_DATABASE_TEST = nome do container`) dentro do mesmo servidor postgres;
- gerencia o ciclo de vida manualmente (`test.sh` cria, `test-destroy.sh` no `after_script` para e dropa o DB).

Problemas decorrentes:

1. **Vazamento de permissões** — arquivos criados pelo container (root) no bind-mount quebram o checkout do próximo pipeline (`Permission denied`). Já mitigado parcialmente, mas é sintoma do modelo.
2. **Contenção no postgres único** — todos os jobs concorrentes batem no mesmo servidor; conexões/locks de um job afetam outros.
3. **Cross-talk** — `mailhog`/`pdfprinter`/`web` únicos compartilhados entre jobs.
4. **Lifecycle frágil** — nomes de container derivados de branch+job, `chown`/`dropdb` manuais, dependência de estado entre `test.sh` e `test-destroy.sh`.

## Decisões tomadas

| Decisão | Escolha |
|---|---|
| Executor | Docker executor (runners a registrar) |
| Imagem de teste | Reconstruída no master + `uv sync` em runtime (Abordagem A) |
| Escopo | Todos os jobs de teste (qa, test, coverage, behave-by-area) |
| Tag dos runners docker | `docker-v3` |
| Serviços django/behave | `full` (postgres + mailhog + pdfprinter) |

Fora de escopo: stages `ai-review`, `homologate`, `build`, `deploy`, `containers`, `special-tasks` — permanecem em shell executor.

## Arquitetura nova

Cada job de teste roda **dentro** de um container definido por `image:`. O GitLab sobe os `services:` declarados em **instâncias efêmeras, isoladas por job**, numa rede dedicada criada e destruída automaticamente pelo runner. O checkout do código acontece dentro do container do job (sem bind-mount do host).

Ganhos: postgres/mail/pdf novos a cada job; sem estado compartilhado; descarte automático; **sem `test-destroy`, sem `chown`, sem `docker run` manual**.

### Componentes

#### 1. Imagem de teste no registry — `$CI_REGISTRY_IMAGE/test:latest`

Novo job `build-test-image`:
- roda em runner **shell com docker** (tag `tests-v3`, que já executa docker hoje);
- `rules`: apenas no `master` **e** quando mudam `uv.lock`, `pyproject.toml`, `bin/ci/Dockerfile` ou `docker/Dockerfile*` (`rules: changes:`);
- passos: login no registry (`docker login -u gitlab-ci-token -p $CI_JOB_TOKEN $CI_REGISTRY`), `docker build -f bin/ci/Dockerfile --target suap-test --build-arg base_image=$SUAP_IMAGE:base -t $CI_REGISTRY_IMAGE/test:latest .`, `docker push`.
- A imagem (target `suap-test` do `bin/ci/Dockerfile`) já traz: chromium/playwright, cache do pre-commit (`PRE_COMMIT_HOME`), venv base via `uv sync`.

Mudanças de dependências Python dentro de um MR são cobertas pelo `uv sync --all-groups` no `before_script`. Mudanças de dependências **de sistema** (apt/playwright) só entram na imagem no próximo rebuild do master — caso raro e aceitável.

#### 2. Serviços por job (YAML anchors)

```yaml
.svc-postgres: &svc-postgres
  - name: postgres:18
    alias: postgres
    command: ["postgres", "-c", "max_locks_per_transaction=1024", "-c", "fsync=off",
              "-c", "synchronous_commit=off", "-c", "full_page_writes=off"]

.svc-full: &svc-full
  - *svc-postgres entries (postgres)
  - name: mailhog/mailhog
    alias: mail
  - name: <registry>/cosinf/suap-pdf:latest
    alias: pdfprinter
```

Variáveis de serviço: `POSTGRES_HOST_AUTH_METHOD=trust`. Aliases definem o hostname interno: `postgres`, `mail`, `pdfprinter`.

> Nota de implementação: `services:` no GitLab não suporta merge de listas via anchor da mesma forma que mapas. Será resolvido na fase de plano (provavelmente repetindo a lista por job-template ou usando `extends` + listas explícitas). O design fixa **quais serviços** cada job recebe; a mecânica YAML exata fica para o plano.

#### 3. Template base `.test`

```yaml
.test:
  image: $CI_REGISTRY_IMAGE/test:latest
  tags: [docker-v3]
  variables:
    GIT_DEPTH: "0"
    DATABASE_HOST: postgres
  before_script:
    - cp suap/settings_sample.py suap/settings.py
    - git fetch origin master:refs/remotes/origin/master   # pre-commit / git diff origin/master..
    - uv sync --all-groups
  script:
    - python manage.py suap_check     # SUAP_CHECK / SUAP_APPS por job
```

Sem `after_script` de destroy.

`settings_sample.py` lê `DATABASE_HOST` (default `127.0.0.1`) → `postgres`. `DEFAULT_DATABASE_TEST` mantém o default `test_suap_dev` (cada job tem postgres próprio, não há mais necessidade de isolar por nome).

#### 4. Jobs migrados

| Job | Stage | SUAP_CHECK | SUAP_APPS | Services | Observações |
|---|---|---|---|---|---|
| `checagem-codigo` | quality-assurance | `code` | — | postgres | `sync_permissions --check` usa DB; pre-commit usa histórico git |
| `django-geral` | test | `django` | `geral` | full | publica `artifacts/` (coverage data) |
| `behave-changed` | test | `behave-changed` | — | full | artifacts `on_failure` |
| `coverage` | coverage | `coverage` | `geral` | nenhum | `needs: [django-geral]` p/ baixar `artifacts/.coverage`; reports cobertura |
| `tecnologia-da-informacao`, `comum`, `gestao-de-pessoas`, `administracao`, `ensino`, `desenvolvimento-institucional`, `extensao`, `atividades-estudantis`, `pesquisa-e-inovacao`, `comunicacao-social`, `documentos-e-processos-eletronicos` | test | `behave` | nome da área | full | manuais (`.behave-by-area`), `on web/api/external` |

As `rules` de cada job (MR auto, manual etc.) são preservadas como hoje.

## Fluxo de dados

1. MR dispara pipeline → jobs de teste agendados em runners `docker-v3`.
2. Runner puxa `image: .../test:latest` e sobe `services:` (rede isolada do job).
3. `before_script` prepara settings, histórico git e venv.
4. `script` roda `suap_check` contra o `postgres` (e `mail`/`pdfprinter`) do próprio job.
5. `django-geral` publica `artifacts/`; `coverage` consome via `needs:`.
6. Fim do job → runner destrói container + serviços + rede.

## Tratamento de erros / edge cases

- **Histórico git**: `code` (pre-commit `--from-ref origin/master`) e `coverage`/`behave-changed` (`git diff --name-only origin/master..`) exigem `origin/master`. Garantido por `GIT_DEPTH: 0` + `git fetch origin master:refs/remotes/origin/master` no `before_script`.
- **Registry privado**: `image:` e o serviço `pdfprinter` vêm do registry da instituição. Imagens do mesmo projeto costumam autenticar via `$CI_JOB_TOKEN`; se necessário, configurar `DOCKER_AUTH_CONFIG` no runner. **Pré-requisito de infra.**
- **Falta de runner `docker-v3`**: até registrar, os jobs ficam `pending`. Pré-requisito de infra.
- **Imagem desatualizada**: deps Python cobertas por `uv sync` em runtime; deps de sistema dependem do rebuild no master.

## Pré-requisitos de infraestrutura (fora do código)

1. Registrar runners com **executor docker** e tag **`docker-v3`**.
2. Garantir acesso do runner ao registry privado (job token ou `DOCKER_AUTH_CONFIG`) para `image:` e serviço `pdfprinter`.

## Impacto em arquivos existentes

- `.gitlab-ci.yml`: reescrita do bloco de testes (anchors `.destroy-test`, `.default_script`, `.default_test`, `.behave-by-area` e jobs correspondentes). Demais stages intactos.
- `bin/ci/test.sh`, `bin/ci/test-destroy.sh`: deixam de ser chamados pelo CI (mantidos para uso local). Referências removidas do `.gitlab-ci.yml`.
- Possível novo arquivo/target para o `build-test-image` (reuso de `bin/ci/build.sh` ou bloco inline).

## Validação

1. `validate_project_ci_lint` no `.gitlab-ci.yml` refatorado (sintaxe + regras).
2. Após registrar **1 runner `docker-v3`**: rodar um pipeline real num MR de teste e confirmar:
   - serviço `postgres` sobe e é alcançável em `DATABASE_HOST=postgres`;
   - `checagem-codigo` (code), `django-geral`, `coverage` passam;
   - um `behave-by-area` manual sobe `mail`/`pdfprinter` e roda chromium.
3. Confirmar que `build-test-image` publica `test:latest` ao mudar `uv.lock` no master.

## Critérios de sucesso

- Jobs de teste rodam em docker executor, cada um com postgres/mail/pdf próprios.
- Sem bind-mount do host, sem `chown`, sem `test-destroy`.
- Pipelines de MR não falham por estado compartilhado/permissões.
- Tempo de pipeline comparável ao atual (imagem pré-construída; só `uv sync` em runtime).
