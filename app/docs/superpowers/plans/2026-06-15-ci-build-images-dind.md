# Build das imagens (base/latest/tags) em DinD — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mover os jobs de build das imagens do SUAP (`base`, `latest`, tags de versão) do runner shell para docker executor + DinD (tag `tests-v3`), com `docker build` direto, preservando verbatim o versionamento/changelog/tag; `full-deploy-prod` vira deploy-only.

**Architecture:** Novo anchor `.build-dind` (estende `.docker-build`, já com DinD TLS-off) define tag/rules/login. Três anchors de script POSIX-sh (`&script-current-tag`, `&script-build-push`, `&script-changelog-tag`) compõem os jobs `build-prod`/`minor-tag`/`major-tag`. `build-base` builda a base. Removem-se `.build`/`.script-build`; `full-deploy-prod` passa a só fazer deploy master→slaves.

**Tech Stack:** GitLab CI (`.gitlab-ci.yml`), docker:27-cli + docker:27-dind, busybox `ash` (POSIX sh), curl, jq, uv; GitLab API (tags/changelog), LLM (Gemini).

**Spec:** `docs/superpowers/specs/2026-06-15-ci-build-images-dind-design.md`

**Nota de validação (adaptação TDD p/ CI):** não há teste unitário de YAML. Cada task valida com `python3 -c "import yaml; yaml.safe_load(open('.gitlab-ci.yml'))"` e, no fim, com o GitLab CI lint (MCP `validate_project_ci_lint` após push) + execução manual do pipeline. A lógica de versão é validada extraindo o snippet e rodando-o em `ash`.

---

## Contexto de arquivos

- **Modificar:** `.gitlab-ci.yml` (anchors + jobs de build/deploy)
- **Modificar:** `bin/ci/README.md` (doc dos jobs de build, fluxo de release)
- Branch: `ci/build-images-dind` (já criada, contém a spec)

Linhas de referência (podem deslocar conforme edições — reconfirme com grep):
- `.prod: &prod` ≈294; `.build: &build` ≈304; `.script-build: &script-build` ≈328
- `.script-deploy-master` ≈347; `.script-deploy-slaves` ≈351
- `build-prod` ≈355; `full-deploy-prod` ≈373; `.docker-build` ≈440
- `build-base` ≈513; `minor-tag` ≈526; `major-tag` ≈557

---

## Task 1: Anchors `.build-dind` e scripts compartilhados

**Files:**
- Modify: `.gitlab-ci.yml` (inserir após o bloco `.docker-build`, antes de `build-opencode-image`)

- [ ] **Step 1: Inserir os anchors logo após `.docker-build`**

Localize o fim do bloco `.docker-build` (a última linha `DOCKER_HOST: tcp://docker:2375`) e insira **depois dele** (linha em branco antes):

```yaml
# Base p/ jobs de build de imagem (docker executor / DinD, tag tests-v3).
# Reaproveita o .docker-build (TLS-off) e adiciona regras de produção + login.
.build-dind:
  extends: .docker-build
  tags:
    - tests-v3
  needs: []
  allow_failure: false
  variables:
    GIT_STRATEGY: fetch
  rules:
    - if: ($CI_PIPELINE_SOURCE == 'web' || $CI_PIPELINE_SOURCE == 'api' || $CI_PIPELINE_SOURCE == 'external') && $CI_COMMIT_BRANCH == 'master' && ($GITLAB_USER_LOGIN == 'hugo.sena' || $GITLAB_USER_LOGIN == 'lucas.pereira' || $GITLAB_USER_LOGIN == 'augusto.medeiros')
      when: manual
  before_script:
    - apk add --no-cache curl jq
    - docker login -u gitlab-ci-token -p "$CI_JOB_TOKEN" "$CI_REGISTRY"

# Tag atual + componentes (POSIX sh; roda no ash do docker:27-cli).
.script-current-tag: &script-current-tag
  - |
    HEADER_TOKEN="PRIVATE-TOKEN:${SUAP_BOT_TOKEN}"
    TAG_URL="$CI_API_V4_URL/projects/$CI_PROJECT_ID/repository/tags"
    CHANGELOG_URL="$CI_API_V4_URL/projects/$CI_PROJECT_ID/repository/changelog"
    CURRENT_TAG="$(curl -s --header "$HEADER_TOKEN" "$TAG_URL" | jq -r '.[0].name')"
    echo "CURRENT_TAG=$CURRENT_TAG"
    MAJOR="$(echo "$CURRENT_TAG" | cut -d. -f1)"
    MINOR="$(echo "$CURRENT_TAG" | cut -d. -f2)"
    PATCH="$(echo "$CURRENT_TAG" | cut -d. -f3)"

# Build + push da imagem prod (latest + NEXT_TAG). VERSION entra no ADD . . do Dockerfile.
.script-build-push: &script-build-push
  - |
    echo "NEXT_TAG=$NEXT_TAG"
    echo "$NEXT_TAG" > VERSION
    docker build -f docker/Dockerfile --target suap-app \
      --build-arg BASE_IMAGE="$CI_REGISTRY_IMAGE:base" \
      -t "$CI_REGISTRY_IMAGE:latest" .
    docker tag "$CI_REGISTRY_IMAGE:latest" "$CI_REGISTRY_IMAGE:$NEXT_TAG"
    docker push "$CI_REGISTRY_IMAGE:$NEXT_TAG"
    docker push "$CI_REGISTRY_IMAGE:latest"

# Changelog + resumo via LLM + criação da git tag (porte verbatim, POSIX sh).
.script-changelog-tag: &script-changelog-tag
  - |
    CURRENT_CHANGES="$(curl -s --request GET --header "$HEADER_TOKEN" --data "version=${NEXT_TAG}" "$CHANGELOG_URL" | jq '.notes')"
    curl -s --request POST --header "$HEADER_TOKEN" --data "version=${NEXT_TAG}" "$CHANGELOG_URL"
    MESSAGE="Converta e resuma o seguinte texto em markdown para um formato em texto simples, removendo links caso apareçam:\n ${CURRENT_CHANGES}"
    GEMINI_URL="${LLM_URL}?key=${LLM_KEY}"
    GEMINI_API_MESSAGE=$(jq -n --arg msg "$MESSAGE" '{contents: [{parts: [{text: $msg}]}]}')
    FORMATTED_CHANGES="$(curl -s "$GEMINI_URL" -H 'Content-Type: application/json' -X POST -d "$GEMINI_API_MESSAGE" | jq '.candidates[0].content.parts[0].text' | sed 's/\\n/\n/g' | sed 's/^"//;s/"$//')"
    if [ -z "$FORMATTED_CHANGES" ] || [ "$FORMATTED_CHANGES" = "null" ]; then
      FORMATTED_CHANGES="Atualização para a versão ${NEXT_TAG}"
    fi
    curl -s --request POST --header "$HEADER_TOKEN" --data "tag_name=${NEXT_TAG}&ref=${CI_COMMIT_REF_NAME}&message=${FORMATTED_CHANGES}" "$TAG_URL"
```

- [ ] **Step 2: Validar YAML**

Run: `python3 -c "import yaml; yaml.safe_load(open('.gitlab-ci.yml')); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Validar a aritmética de versão no `ash`**

Run:
```bash
docker run --rm alpine:latest sh -c 'CURRENT_TAG=4.12.9; MAJOR=$(echo "$CURRENT_TAG"|cut -d. -f1); MINOR=$(echo "$CURRENT_TAG"|cut -d. -f2); PATCH=$(echo "$CURRENT_TAG"|cut -d. -f3); echo "patch=$MAJOR.$MINOR.$((PATCH+1)) minor=$MAJOR.$((MINOR+1)).0 major=$((MAJOR+1)).0.0"'
```
Expected: `patch=4.12.10 minor=4.13.0 major=5.0.0`

- [ ] **Step 4: Commit**

```bash
git add .gitlab-ci.yml
git commit -m "[ci] Anchors .build-dind e scripts de build/tag em POSIX sh"
```

---

## Task 2: Converter `build-base`

**Files:**
- Modify: `.gitlab-ci.yml` (job `build-base`)

- [ ] **Step 1: Substituir o job `build-base`**

De:
```yaml
build-base:
  <<: *build
  stage: special-tasks
  script:
    # Compilando imagem base
    - cp .env.dev.sample .env
    - sed -i "s/gitlab.instituicao.edu.br/$CI_SERVER_HOST/g" .env
    - echo $NEXT_TAG > VERSION
    - uv audit
    - make build-base
    # Enviando imagem base para o repositório
    - make push-image-base
```
Para:
```yaml
build-base:
  extends: .build-dind
  stage: special-tasks
  script:
    - apk add --no-cache uv
    - uv audit
    - docker build -f docker/Dockerfile.base -t "$CI_REGISTRY_IMAGE:base" .
    - docker push "$CI_REGISTRY_IMAGE:base"
```

- [ ] **Step 2: Validar YAML**

Run: `python3 -c "import yaml; yaml.safe_load(open('.gitlab-ci.yml')); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add .gitlab-ci.yml
git commit -m "[ci] build-base: docker build direto em DinD (tests-v3)"
```

---

## Task 3: Converter `build-prod` (patch)

**Files:**
- Modify: `.gitlab-ci.yml` (job `build-prod`)

- [ ] **Step 1: Substituir o job `build-prod`**

De:
```yaml
build-prod:
  <<: *build
  stage: build
  script:
    - *script-build
```
Para:
```yaml
build-prod:
  extends: .build-dind
  stage: build
  script:
    - *script-current-tag
    - |
      NEXT_TAG="$MAJOR.$MINOR.$((PATCH+1))"
      HAS_CHANGE="$(curl -s -d "version=$NEXT_TAG" -G --header "$HEADER_TOKEN" "$CHANGELOG_URL" | grep -c 'No changes')"
      if [ "$HAS_CHANGE" -eq 1 ]; then echo "Tag não foi alterada"; exit 1; fi
    - *script-build-push
    - *script-changelog-tag
```

- [ ] **Step 2: Validar YAML**

Run: `python3 -c "import yaml; yaml.safe_load(open('.gitlab-ci.yml')); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add .gitlab-ci.yml
git commit -m "[ci] build-prod: patch tag + build/push + changelog em DinD"
```

---

## Task 4: Converter `minor-tag`

**Files:**
- Modify: `.gitlab-ci.yml` (job `minor-tag`)

- [ ] **Step 1: Substituir o job `minor-tag`** (todo o bloco `minor-tag:` atual, incluindo o script `|` longo)

Para:
```yaml
minor-tag:
  extends: .build-dind
  stage: special-tasks
  script:
    - *script-current-tag
    - |
      NEXT_TAG="$MAJOR.$((MINOR+1)).0"
    - *script-build-push
    - *script-changelog-tag
```

- [ ] **Step 2: Validar YAML**

Run: `python3 -c "import yaml; yaml.safe_load(open('.gitlab-ci.yml')); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add .gitlab-ci.yml
git commit -m "[ci] minor-tag: minor tag + build/push + changelog em DinD"
```

---

## Task 5: Converter `major-tag`

**Files:**
- Modify: `.gitlab-ci.yml` (job `major-tag`)

- [ ] **Step 1: Substituir o job `major-tag`** (todo o bloco `major-tag:` atual)

Para:
```yaml
major-tag:
  extends: .build-dind
  stage: special-tasks
  script:
    - *script-current-tag
    - |
      NEXT_TAG="$((MAJOR+1)).0.0"
    - *script-build-push
    - *script-changelog-tag
```

- [ ] **Step 2: Validar YAML**

Run: `python3 -c "import yaml; yaml.safe_load(open('.gitlab-ci.yml')); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add .gitlab-ci.yml
git commit -m "[ci] major-tag: major tag + build/push + changelog em DinD"
```

---

## Task 6: `full-deploy-prod` deploy-only + remover anchors `.build`/`.script-build`

**Files:**
- Modify: `.gitlab-ci.yml` (job `full-deploy-prod`; remover `.build`/`.script-build`)

- [ ] **Step 1: Substituir o job `full-deploy-prod`**

De:
```yaml
full-deploy-prod:
  <<: *build
  stage: build
  script:
    - set -e
    - echo "===== 1/3 BUILD ====="
    - *script-build
    - echo "===== 2/3 DEPLOY MASTER ====="
    - *script-deploy-master
    - echo "===== 3/3 DEPLOY SLAVES ====="
    - *script-deploy-slaves
```
Para:
```yaml
full-deploy-prod:
  <<: *prod
  stage: deploy
  script:
    - set -e
    - echo "===== 1/2 DEPLOY MASTER ====="
    - *script-deploy-master
    - echo "===== 2/2 DEPLOY SLAVES ====="
    - *script-deploy-slaves
```

- [ ] **Step 2: Remover os anchors `.build`/`&build` e `.script-build`/`&script-build`**

Apague os dois blocos inteiros (de `.build: &build` até o fim do `after_script: docker system prune -f`, e de `.script-build: &script-build` até a linha do `curl ... $TAG_URL`). Mantenha `.prod`, `.script-deploy-master`, `.script-deploy-slaves`.

- [ ] **Step 3: Confirmar que não há mais referência a `*build`/`*script-build`**

Run: `grep -n "\*build\b\|\*script-build\b\|&build\b\|&script-build\b" .gitlab-ci.yml`
Expected: nenhuma saída (vazio).

- [ ] **Step 4: Validar YAML**

Run: `python3 -c "import yaml; yaml.safe_load(open('.gitlab-ci.yml')); print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add .gitlab-ci.yml
git commit -m "[ci] full-deploy-prod deploy-only; remove anchors .build/.script-build"
```

---

## Task 7: Atualizar `bin/ci/README.md`

**Files:**
- Modify: `bin/ci/README.md` (seção "Imagens de CI")

- [ ] **Step 1: Atualizar a tabela de imagens e a seção de build**

Na seção "Imagens de CI (build e atualização)", adicione a `base` e as imagens versionadas à tabela, e documente que os jobs `build-base`/`build-prod`/`minor-tag`/`major-tag` rodam em `tests-v3` (docker/DinD, `docker build` direto), e o fluxo de release: `build-prod` (ou `minor/major-tag`) → `full-deploy-prod` (deploy master→slaves). Texto a inserir:

```markdown
### Imagens de produção (base / latest / tags de versão)

| Imagem | Job | Dockerfile | Tag runner |
|--------|-----|------------|------------|
| `$CI_REGISTRY_IMAGE:base` | `build-base` | `docker/Dockerfile.base` | `tests-v3` |
| `$CI_REGISTRY_IMAGE:latest` + `:X.Y.Z` | `build-prod` (patch) / `minor-tag` / `major-tag` | `docker/Dockerfile` (target `suap-app`) | `tests-v3` |

Os jobs de build rodam em **docker executor / DinD** (anchor `.build-dind`), com
`docker build` direto (sem `make`/compose) e `apk add` das ferramentas no job
(`curl`, `jq`, e `uv` na base). Regras: pipeline `web`/`api`/`external` no `master`,
manual, restrito aos mantenedores. Versionamento e changelog/tag são gerados via API
do GitLab + resumo LLM (idêntico ao fluxo anterior).

**Fluxo de release:**
1. Pipeline web no `master` → dispare `build-prod` (patch) ou `minor-tag`/`major-tag`:
   builda e publica `:latest` + `:X.Y.Z` e cria a git tag/changelog.
2. Dispare `full-deploy-prod` (tag `prod`, runner shell): faz **deploy master → slaves**
   (sem build) puxando a imagem publicada. (Ou `deploy-prod-master`/`-slaves`.)

> O `build-base` deve ser publicado ao menos uma vez antes do primeiro `build-prod`
> (o build do prod usa `--build-arg BASE_IMAGE=$CI_REGISTRY_IMAGE:base`).
```

- [ ] **Step 2: Commit**

```bash
git add bin/ci/README.md
git commit -m "[ci] Doc: jobs de build em tests-v3 e fluxo de release"
```

---

## Task 8: Validação final (CI lint + MR + pipeline manual)

**Files:** nenhum (validação/entrega)

- [ ] **Step 1: Push da branch**

```bash
git push -u origin ci/build-images-dind
```

- [ ] **Step 2: Validar com o GitLab CI lint (conteúdo da branch)**

Use o MCP `validate_project_ci_lint` (project `cosinf/suap`, `content_ref: ci/build-images-dind`, `dry_run: true`, `dry_run_ref: master`). Expected: `valid: true`, sem erros de sintaxe; jobs `build-base`/`build-prod`/`minor-tag`/`major-tag`/`full-deploy-prod` presentes.

- [ ] **Step 3: Abrir o MR** (via MCP `create_merge_request`, base `master`), título `[ci] Build das imagens em DinD (tests-v3); full-deploy-prod deploy-only`, com descrição no padrão SUAP referenciando a spec.

- [ ] **Step 4: (manual, usuário) Validar no pipeline**

Pipeline web na branch `ci/build-images-dind`:
- Dispare `build-base` → confirme `uv audit`, build e push de `:base`.
- Dispare `build-prod` → confirme cálculo de `NEXT_TAG`, build/push de `:latest`+`:X.Y.Z`, changelog e criação da git tag.
Expected: jobs verdes; imagens e tag publicadas. Se ok, mergear.

---

## Self-review (cobertura da spec)

- Decisão 1 (docker build direto): Tasks 2–5 ✓
- Decisão 2 (docker:27-cli + apk): `.build-dind` before_script + build-base ✓
- Decisão 3 (manter uv audit): Task 2 ✓
- Decisão 4 (tests-v3, sem runner novo): `.build-dind` tags ✓
- Decisão 5 (full-deploy-prod deploy-only): Task 6 ✓
- Versionamento patch/minor/major + guard HAS_CHANGE: Tasks 3–5 ✓
- Changelog/Gemini/tag verbatim (POSIX sh): `&script-changelog-tag` ✓
- Remoção de `.build`/`.script-build`: Task 6 ✓
- Doc: Task 7 ✓
