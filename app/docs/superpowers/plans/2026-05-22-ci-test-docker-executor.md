# CI: estágio de testes em docker executor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrar todos os jobs de teste do `.gitlab-ci.yml` para o executor docker, com serviços (postgres/mailhog/pdfprinter) efêmeros e isolados por job, e publicar a imagem de teste no registry.

**Architecture:** Cada job de teste roda dentro de `image: $CI_REGISTRY_IMAGE/test:latest` e declara `services:` que o GitLab sobe isolados por job. Um job `build-test-image` (no master) publica a imagem. Templates ocultos (`.test-base`, `.behave-by-area`) + anchors de serviço (`*postgres-service`, `*mail-service`, `*pdf-service`) eliminam duplicação. Não há mais `bin/ci/test.sh`/`test-destroy.sh` no fluxo.

**Tech Stack:** GitLab CI (docker executor, services, extends, anchors), Docker, uv, Django `manage.py suap_check`.

**Spec:** `docs/superpowers/specs/2026-05-22-ci-test-docker-executor-design.md`

---

## Pré-requisitos de infraestrutura (NÃO são tarefas de código — apenas documentados aqui)

Estes itens dependem da infra e bloqueiam a execução real do pipeline, mas **não** impedem escrever/validar o YAML:

1. Registrar runners com **executor docker** e tag **`docker-v3`**.
2. No `config.toml` desses runners, no `[runners.docker]`, replicar os limites que o antigo `bin/ci/test.sh` passava ao `docker run` (não são expressáveis no YAML do job):
   - **`shm_size = 2147483648`** (2 GB) — necessário para o chromium dos testes behave (default de 64 MB faz o chromium crashar).
   - **`memory = "8g"`** e **`memory_reservation = "1g"`** — equivalente a `--memory=8g`/`--memory-reservation=1g` do test.sh.
   - **`ulimit = ["nofile=65535:65535"]`** — equivalente a `--ulimit nofile=65535:65535` do test.sh.
3. Garantir acesso ao registry privado para `image:` e para o serviço `pdfprinter` (job token costuma bastar para imagens do mesmo projeto; senão `DOCKER_AUTH_CONFIG`).
4. Rodar `build-test-image` ao menos uma vez (via pipeline manual no master) antes do primeiro pipeline de testes, para que `$CI_REGISTRY_IMAGE/test:latest` exista.

---

## File Structure

- **Modificar:** `.gitlab-ci.yml` — única fonte das mudanças. Bloco de testes reescrito (anchors de serviço, `.test-base`, jobs migrados, `build-test-image`). Stages `ai-review`/`homologate`/`build`/`deploy`/`containers`/`special-tasks` permanecem intactos, exceto pela adição do job `build-test-image` no stage `build`.
- **Mantidos sem mudança (saem do fluxo de CI, ficam para uso local):** `bin/ci/test.sh`, `bin/ci/test-destroy.sh`, `bin/ci/docker-compose.yaml`.

Todas as tarefas editam o mesmo arquivo `.gitlab-ci.yml`. A ordem garante que o arquivo permaneça **válido a cada commit**: primeiro adicionamos as novas definições, migramos os jobs um a um, e só então removemos os anchors antigos.

## Como validar (usado em todas as tarefas)

Validação autoritativa via MCP do GitLab:

> Ferramenta: `mcp__gitlab__validate_project_ci_lint`
> Argumentos: project = `cosinf/suap`, ref = `ci-test-docker-executor`, e o conteúdo atual do `.gitlab-ci.yml`.
> Esperado: `valid: true`, `errors: []`.

Checagem rápida de sintaxe YAML (fallback offline, não valida regras do GitLab):

```bash
python -c "import yaml; yaml.safe_load(open('.gitlab-ci.yml')); print('YAML OK')"
```
Esperado: `YAML OK`

---

## Task 1: Adicionar anchors de serviço e o template base `.test-base`

Adiciona as definições novas **sem** ainda alterar nenhum job existente. O arquivo continua válido (anchors são apenas definições; templates `.algo` são ignorados como jobs).

**Files:**
- Modify: `.gitlab-ci.yml` (inserir logo após o bloco `variables:` / antes de `.destroy-test`)

- [ ] **Step 1: Inserir os anchors de serviço e o template base**

Inserir o bloco abaixo imediatamente após a seção `stages:` (linha ≈25), antes de `.destroy-test`:

```yaml
# ============================================================
# Testes — docker executor (serviços isolados por job)
# ============================================================

# Entradas individuais de service (usadas via *anchor nas listas services: dos jobs)
.postgres-service: &postgres-service
  name: postgres:18
  alias: postgres
  command:
    - "postgres"
    - "-c"
    - "max_locks_per_transaction=1024"
    - "-c"
    - "fsync=off"
    - "-c"
    - "synchronous_commit=off"
    - "-c"
    - "full_page_writes=off"

.mail-service: &mail-service
  name: mailhog/mailhog
  alias: mail

.pdf-service: &pdf-service
  name: $CI_REGISTRY/cosinf/suap-pdf:latest
  alias: pdfprinter

# Template base de todo job de teste em docker executor
.test-base:
  image: $CI_REGISTRY_IMAGE/test:latest
  tags:
    - docker-v3
  variables:
    GIT_DEPTH: "0"
    GIT_SSL_NO_VERIFY: "true"
    DATABASE_HOST: postgres
    POSTGRES_HOST_AUTH_METHOD: trust
  before_script:
    # settings de teste
    - cp suap/settings_sample.py suap/settings.py
    # pre-commit (--from-ref origin/master) e "git diff origin/master.." precisam do ref de master
    - git fetch origin master:refs/remotes/origin/master || true
    # sincroniza dependências do MR (cobre mudanças de deps Python não presentes na imagem)
    - uv sync --all-groups
  script:
    - python manage.py suap_check
```

- [ ] **Step 2: Checagem de sintaxe YAML**

Run: `python -c "import yaml; yaml.safe_load(open('.gitlab-ci.yml')); print('YAML OK')"`
Expected: `YAML OK`

- [ ] **Step 3: Validar no GitLab CI lint**

Usar `mcp__gitlab__validate_project_ci_lint` (project `cosinf/suap`, ref `ci-test-docker-executor`, conteúdo do `.gitlab-ci.yml`).
Expected: `valid: true`. (Os jobs antigos ainda existem e continuam válidos.)

- [ ] **Step 4: Commit**

```bash
git add .gitlab-ci.yml
git commit -m "[ci] Adiciona anchors de serviço e template .test-base para docker executor"
```

---

## Task 2: Migrar `checagem-codigo` (SUAP_CHECK=code) para `.test-base`

**Files:**
- Modify: `.gitlab-ci.yml` (job `checagem-codigo`, hoje em ~linha 46)

- [ ] **Step 1: Substituir o job `checagem-codigo`**

Trocar o job atual (que usa `<<: *default_test`) por:

```yaml
checagem-codigo:
  extends: .test-base
  stage: quality-assurance
  services:
    - *postgres-service
  variables:
    SUAP_CHECK: code
  rules:
    - if: $CI_PIPELINE_SOURCE == 'merge_request_event'
      when: on_success
  allow_failure: false
```

Notas: `SUAP_CHECK=code` roda pre-commit, `python manage.py check`, dependências, migrations, imports, `sync_permissions --check` (usa DB → por isso `postgres`) e `collectstatic`. O `script` (`python manage.py suap_check`) vem do `.test-base`. As variáveis (`DATABASE_HOST`, etc.) fazem merge a partir do `.test-base`.

- [ ] **Step 2: Checagem de sintaxe YAML**

Run: `python -c "import yaml; yaml.safe_load(open('.gitlab-ci.yml')); print('YAML OK')"`
Expected: `YAML OK`

- [ ] **Step 3: Validar no GitLab CI lint**

`mcp__gitlab__validate_project_ci_lint` → Expected: `valid: true`.

- [ ] **Step 4: Commit**

```bash
git add .gitlab-ci.yml
git commit -m "[ci] Migra checagem-codigo para docker executor com postgres por job"
```

---

## Task 3: Migrar `django-geral` (SUAP_CHECK=django/geral) para `.test-base`

**Files:**
- Modify: `.gitlab-ci.yml` (job `django-geral`, hoje em ~linha 54)

- [ ] **Step 1: Substituir o job `django-geral`**

```yaml
django-geral:
  extends: .test-base
  stage: test
  services:
    - *postgres-service
    - *mail-service
    - *pdf-service
  variables:
    SUAP_CHECK: django
    SUAP_APPS: geral
  rules:
    - if: $CI_PIPELINE_SOURCE == 'merge_request_event'
      when: on_success
  allow_failure: false
  artifacts:
    when: always
    expire_in: 1 week
    paths:
      - artifacts
```

Notas: `EMAIL_HOST` **não** é definido → o backend de email de debug é usado (mesmo comportamento de hoje). O `mail`/`pdf` ficam disponíveis por paridade. Publica `artifacts/` (dados de coverage) consumidos pelo job `coverage`.

- [ ] **Step 2: Checagem de sintaxe YAML**

Run: `python -c "import yaml; yaml.safe_load(open('.gitlab-ci.yml')); print('YAML OK')"`
Expected: `YAML OK`

- [ ] **Step 3: Validar no GitLab CI lint**

`mcp__gitlab__validate_project_ci_lint` → Expected: `valid: true`.

- [ ] **Step 4: Commit**

```bash
git add .gitlab-ci.yml
git commit -m "[ci] Migra django-geral para docker executor com serviços full por job"
```

---

## Task 4: Migrar `coverage` (SUAP_CHECK=coverage) para `.test-base`

**Files:**
- Modify: `.gitlab-ci.yml` (job `coverage`, hoje em ~linha 64)

- [ ] **Step 1: Substituir o job `coverage`**

```yaml
coverage:
  extends: .test-base
  stage: coverage
  needs:
    - job: django-geral
      artifacts: true
  variables:
    SUAP_CHECK: coverage
    SUAP_APPS: geral
  rules:
    - if: $CI_PIPELINE_SOURCE == 'merge_request_event'
      when: on_success
  allow_failure: false
  artifacts:
    when: always
    expire_in: 1 week
    paths:
      - artifacts
    reports:
      coverage_report:
        coverage_format: cobertura
        path: artifacts/coverage.xml
```

Notas: **sem `services`** — `SUAP_CHECK=coverage`/`SUAP_APPS=geral` apenas lê `artifacts/.coverage*` e gera `coverage.xml`, não toca DB nem faz `git diff`. O `needs: [django-geral]` baixa os artifacts do job de testes. O `before_script` (de `.test-base`) faz `uv sync` para ter o pacote `coverage` disponível.

- [ ] **Step 2: Checagem de sintaxe YAML**

Run: `python -c "import yaml; yaml.safe_load(open('.gitlab-ci.yml')); print('YAML OK')"`
Expected: `YAML OK`

- [ ] **Step 3: Validar no GitLab CI lint**

`mcp__gitlab__validate_project_ci_lint` → Expected: `valid: true`.

- [ ] **Step 4: Commit**

```bash
git add .gitlab-ci.yml
git commit -m "[ci] Migra coverage para docker executor (needs django-geral)"
```

---

## Task 5: Migrar `behave-changed` (SUAP_CHECK=behave-changed) para `.test-base`

**Files:**
- Modify: `.gitlab-ci.yml` (job `behave-changed`, hoje em ~linha 79)

- [ ] **Step 1: Substituir o job `behave-changed`**

```yaml
behave-changed:
  extends: .test-base
  stage: test
  services:
    - *postgres-service
    - *mail-service
    - *pdf-service
  variables:
    SUAP_CHECK: behave-changed
  rules:
    - if: $CI_PIPELINE_SOURCE == 'merge_request_event'
      when: on_success
  allow_failure: false
  artifacts:
    when: on_failure
    expire_in: 1 week
    paths:
      - artifacts
```

Notas: `SUAP_CHECK=behave-changed` usa `git diff --name-only origin/master..` (coberto pelo `git fetch origin master` no `before_script`) e roda chromium → exige `shm_size` no runner (pré-requisito de infra).

- [ ] **Step 2: Checagem de sintaxe YAML**

Run: `python -c "import yaml; yaml.safe_load(open('.gitlab-ci.yml')); print('YAML OK')"`
Expected: `YAML OK`

- [ ] **Step 3: Validar no GitLab CI lint**

`mcp__gitlab__validate_project_ci_lint` → Expected: `valid: true`.

- [ ] **Step 4: Commit**

```bash
git add .gitlab-ci.yml
git commit -m "[ci] Migra behave-changed para docker executor com serviços full"
```

---

## Task 6: Migrar `.behave-by-area` e os 11 jobs de área

**Files:**
- Modify: `.gitlab-ci.yml` (template `.behave-by-area` ~linha 89 e os 11 jobs `tecnologia-da-informacao` … `documentos-e-processos-eletronicos`)

- [ ] **Step 1: Substituir o template `.behave-by-area`**

Trocar o anchor antigo `.behave-by-area: &behave-by-area` (que usa `<<: *default_test`) por um template baseado em `.test-base`:

```yaml
.behave-by-area:
  extends: .test-base
  stage: test
  services:
    - *postgres-service
    - *mail-service
    - *pdf-service
  variables:
    SUAP_CHECK: behave
    SUAP_APPS: $CI_JOB_NAME
  rules:
    - if: $CI_PIPELINE_SOURCE == 'web' || $CI_PIPELINE_SOURCE == 'api' || $CI_PIPELINE_SOURCE == 'external'
      when: manual
  allow_failure: false
  artifacts:
    when: on_failure
    expire_in: 1 week
    paths:
      - artifacts
```

Notas: `SUAP_APPS: $CI_JOB_NAME` faz cada job usar seu próprio nome como slug de área (igual ao comportamento atual, que passava `$CI_JOB_NAME`). `suap_check` resolve `areas[SUAP_APPS]`.

- [ ] **Step 2: Atualizar os 11 jobs de área para usar `extends`**

Cada um dos jobs abaixo deve ficar exatamente assim (trocar `<<: *behave-by-area` por `extends: .behave-by-area`):

```yaml
tecnologia-da-informacao:
  extends: .behave-by-area

comum:
  extends: .behave-by-area

gestao-de-pessoas:
  extends: .behave-by-area

administracao:
  extends: .behave-by-area

ensino:
  extends: .behave-by-area

desenvolvimento-institucional:
  extends: .behave-by-area

extensao:
  extends: .behave-by-area

atividades-estudantis:
  extends: .behave-by-area

pesquisa-e-inovacao:
  extends: .behave-by-area

comunicacao-social:
  extends: .behave-by-area

documentos-e-processos-eletronicos:
  extends: .behave-by-area
```

- [ ] **Step 3: Checagem de sintaxe YAML**

Run: `python -c "import yaml; yaml.safe_load(open('.gitlab-ci.yml')); print('YAML OK')"`
Expected: `YAML OK`

- [ ] **Step 4: Validar no GitLab CI lint**

`mcp__gitlab__validate_project_ci_lint` → Expected: `valid: true`.

- [ ] **Step 5: Commit**

```bash
git add .gitlab-ci.yml
git commit -m "[ci] Migra behave-by-area e jobs de área para docker executor"
```

---

## Task 7: Remover anchors antigos do modelo shell

Agora que nenhum job referencia os anchors antigos, eles são removidos.

**Files:**
- Modify: `.gitlab-ci.yml` (remover `.destroy-test`, `.default_script`, `.default_test`)

- [ ] **Step 1: Remover os três anchors antigos**

Apagar integralmente estes blocos (que ficavam entre `stages:` e `checagem-codigo`):

```yaml
.destroy-test: &destroy-test
  after_script:
    - bin/ci/test-destroy.sh $CI_MERGE_REQUEST_SOURCE_BRANCH_NAME $CI_JOB_NAME $CI_JOB_ID

.default_script: &default_script
  - bin/ci/test.sh $CI_MERGE_REQUEST_SOURCE_BRANCH_NAME $CI_MERGE_REQUEST_TARGET_BRANCH_NAME $CI_PROJECT_DIR $CI_JOB_ID $CI_JOB_NAME behave $CI_JOB_NAME

.default_test: &default_test
  <<: *destroy-test
  stage: test
  tags:
    - tests-v3
  script:
    - *default_script
  rules:
    - if: $CI_PIPELINE_SOURCE == 'merge_request_event'
      when: on_success
  allow_failure: false
```

- [ ] **Step 2: Confirmar que não há mais referências aos anchors/scripts antigos**

Run:
```bash
grep -nE 'default_test|default_script|destroy-test|test-destroy\.sh|test\.sh' .gitlab-ci.yml || echo "sem referências antigas"
```
Expected: `sem referências antigas`

- [ ] **Step 3: Checagem de sintaxe YAML**

Run: `python -c "import yaml; yaml.safe_load(open('.gitlab-ci.yml')); print('YAML OK')"`
Expected: `YAML OK`

- [ ] **Step 4: Validar no GitLab CI lint**

`mcp__gitlab__validate_project_ci_lint` → Expected: `valid: true`.

- [ ] **Step 5: Commit**

```bash
git add .gitlab-ci.yml
git commit -m "[ci] Remove anchors do modelo shell (test.sh/test-destroy.sh) do fluxo de testes"
```

---

## Task 8: Adicionar o job `build-test-image` (publica a imagem no registry)

**Files:**
- Modify: `.gitlab-ci.yml` (adicionar job no stage `build`, junto aos demais jobs de build/prod)

- [ ] **Step 1: Adicionar o job `build-test-image`**

Inserir (por exemplo logo antes de `build-base:` no fim do arquivo):

```yaml
build-test-image:
  stage: build
  tags:
    - tests-v3
  variables:
    GIT_STRATEGY: fetch
  rules:
    # rebuild automático no master quando deps/Dockerfiles mudam
    - if: $CI_COMMIT_BRANCH == 'master'
      changes:
        - uv.lock
        - pyproject.toml
        - bin/ci/Dockerfile
        - docker/Dockerfile
        - docker/Dockerfile.base
      when: on_success
    # permite rebuild manual (pipeline web/api/external) para bootstrap
    - if: $CI_PIPELINE_SOURCE == 'web' || $CI_PIPELINE_SOURCE == 'api' || $CI_PIPELINE_SOURCE == 'external'
      when: manual
  before_script:
    - docker login -u gitlab-ci-token -p "$CI_JOB_TOKEN" "$CI_REGISTRY"
  script:
    - docker pull "$CI_REGISTRY/cosinf/suap:base"
    - >
      docker build
      -f bin/ci/Dockerfile
      --target suap-test
      --build-arg base_image="$CI_REGISTRY/cosinf/suap:base"
      -t "$CI_REGISTRY_IMAGE/test:latest"
      .
    - docker push "$CI_REGISTRY_IMAGE/test:latest"
  after_script:
    - docker logout "$CI_REGISTRY" || true
```

Notas: roda em runner shell com docker (`tests-v3`, que já executa docker hoje). Usa o target `suap-test` do `bin/ci/Dockerfile` e a imagem base `suap:base` já publicada por `build-base`/`push-image-base`. A regra manual permite o bootstrap inicial (Task 9).

- [ ] **Step 2: Checagem de sintaxe YAML**

Run: `python -c "import yaml; yaml.safe_load(open('.gitlab-ci.yml')); print('YAML OK')"`
Expected: `YAML OK`

- [ ] **Step 3: Validar no GitLab CI lint**

`mcp__gitlab__validate_project_ci_lint` → Expected: `valid: true`.

- [ ] **Step 4: Commit**

```bash
git add .gitlab-ci.yml
git commit -m "[ci] Adiciona build-test-image (publica imagem de teste no registry)"
```

---

## Task 9: Validação real (requer infra) e push

Esta tarefa **depende dos pré-requisitos de infra** (runner `docker-v3` com `shm_size`, acesso ao registry). Documenta a sequência de validação manual. Não há código novo.

- [ ] **Step 1: Push da branch**

```bash
git push -u origin ci-test-docker-executor
```

- [ ] **Step 2: Bootstrap da imagem de teste**

Rodar manualmente o job `build-test-image` (pipeline web no master, botão manual) e confirmar que `$CI_REGISTRY_IMAGE/test:latest` foi publicado no registry.

- [ ] **Step 3: Abrir MR e validar o pipeline**

Abrir um MR da branch para o master e confirmar:
- `checagem-codigo` (code) sobe `postgres` e passa;
- `django-geral` passa e publica `artifacts/`;
- `coverage` baixa os artifacts (via `needs`) e gera `coverage.xml`;
- um job `behave-by-area` manual sobe `mail`/`pdfprinter`, roda chromium e passa (confirma o `shm_size`).

- [ ] **Step 4: Ajustes finos**

Se o chromium crashar → confirmar `shm_size` no runner. Se `image:`/`pdfprinter` falhar ao puxar → configurar `DOCKER_AUTH_CONFIG`. Registrar quaisquer ajustes em commits adicionais.

---

## Self-Review (preenchido pelo autor do plano)

**Spec coverage:**
- Imagem no registry → Task 8 (+ bootstrap Task 9). ✅
- Serviços por job (anchors) → Task 1 (defs) + Tasks 2–6 (uso). ✅
- Template `.test-base` (settings, fetch master, uv sync) → Task 1. ✅
- Jobs migrados (code/django/coverage/behave-changed/behave-by-area) → Tasks 2–6. ✅
- Remoção do modelo shell (test.sh/test-destroy.sh do fluxo) → Task 7. ✅
- DATABASE_HOST=postgres, DEFAULT_DATABASE_TEST default → Task 1 (não setamos DEFAULT_DATABASE_TEST). ✅
- Pré-requisitos de infra (runner docker-v3, shm_size, registry) → seção dedicada + Task 9. ✅
- Validação (CI lint + pipeline real) → passo de validação em toda tarefa + Task 9. ✅

**Placeholder scan:** Sem TBD/TODO; todo YAML está completo e literal.

**Consistência de tipos/nomes:** Aliases de serviço (`postgres`/`mail`/`pdfprinter`) consistentes entre anchors e `DATABASE_HOST`. Anchors `*postgres-service`/`*mail-service`/`*pdf-service` definidos na Task 1 e usados nas Tasks 3/5/6. `.test-base` definido na Task 1, estendido nas Tasks 2–6. `.behave-by-area` (Task 6) estende `.test-base`.

**Ordem/validade:** Cada tarefa deixa o `.gitlab-ci.yml` válido (novas defs antes do uso; remoção dos anchors antigos só após nenhum job os referenciar).
