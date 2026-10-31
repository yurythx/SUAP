# Build das imagens (base/latest/tags) em DinD — design

**Data:** 2026-06-15
**Status:** aprovado p/ implementação
**Escopo:** mover o build das imagens do SUAP (`base`, `latest`, tags de versão) do
runner *shell* (stockton) para *docker executor* + Docker-in-Docker, sem exigir nada
no runner além do Docker. Preservar **exatamente** o versionamento e a geração de tags.

## Objetivo / motivação

Hoje os jobs de build (`build-base`, `build-prod`, `minor-tag`, `major-tag`,
`full-deploy-prod`) rodam em runner **shell** (`tags: prod`) que precisa de
`docker`, `docker compose`, `make`, `curl`, `jq`, `uv` e um checkout do repo
instalados. Queremos que o runner de build só tenha **Docker** (executor docker),
no mesmo molde já adotado em `build-test-image`/`build-opencode-image`.

## Decisões (acordadas)

1. **`docker build` direto** no lugar de `make`/`docker compose build`.
2. Imagem do job: **`docker:27-cli`** + `apk add` das ferramentas no job (sem imagem
   nova pra manter). `uv` instalado via `apk` só no job da base.
3. **Manter `uv audit`** antes do build da base.
4. Tag/runner: build em **runners docker agnósticos**, reusando a tag **`tests-v3`**
   (ex.: caico) — **sem registração nova** e sem config extra (caico já tem
   `privileged=true`, `allowed_pull_policies` com ambas e o TLS-off vem do
   `.docker-build`). Stockton **não** builda — fica só com a registração **shell**
   (tag `prod`) para deploy.
5. **`full-deploy-prod` continua existindo, mas sem o build.** Vira o job de "deploy
   completo" no `prod` shell: executa **deploy master → deploy slaves** em sequência
   (`*script-deploy-master` depois `*script-deploy-slaves`). Perde o passo de build
   (`*script-build`), que agora é dos jobs `build-*` no docker executor.

## Pré-requisitos no runner

**Nenhuma mudança de runner.** Os jobs de build usam `tags: tests-v3`, atendidos por
runners docker já configurados (caico): `privileged = true`, `allowed_pull_policies =
["always","if-not-present"]`; o TLS-off (`DOCKER_TLS_CERTDIR=""`) já vem do anchor
`.docker-build`. Para escalar, basta marcar outros runners docker com `tests-v3`.

Stockton permanece **shell** (tag `prod`) apenas para os jobs de deploy.

## Fluxo de release

1. Pipeline web no `master` → dispara manualmente **`build-prod`** (ou `minor-tag`/
   `major-tag`) em `tests-v3`: builda/empurra `:latest` + `:NEXT_TAG` e cria a git
   tag/changelog.
2. Em seguida, dispara o **`full-deploy-prod`** (tag `prod`, stockton shell), que faz
   **deploy master → deploy slaves** puxando a imagem recém-publicada via ansible.
   (Ou os jobs individuais `deploy-prod-master`/`deploy-prod-slaves`.)

## Arquitetura (`.gitlab-ci.yml`)

### `.build-dind` (novo anchor)

Estende o `.docker-build` já existente (DinD TLS-off: `docker:27-cli` +
`docker:27-dind`, `DOCKER_TLS_CERTDIR=""`, `DOCKER_HOST=tcp://docker:2375`) e acrescenta:

```yaml
.build-dind:
  extends: .docker-build
  tags: [tests-v3]
  variables:
    GIT_STRATEGY: fetch
  rules:    # idênticas ao .prod
    - if: ($CI_PIPELINE_SOURCE == 'web' || $CI_PIPELINE_SOURCE == 'api' || $CI_PIPELINE_SOURCE == 'external') && $CI_COMMIT_BRANCH == 'master' && ($GITLAB_USER_LOGIN == 'hugo.sena' || $GITLAB_USER_LOGIN == 'lucas.pereira' || $GITLAB_USER_LOGIN == 'augusto.medeiros')
      when: manual
  before_script:
    - apk add --no-cache curl jq
    - docker login -u gitlab-ci-token -p "$CI_JOB_TOKEN" "$CI_REGISTRY"
```

### Anchors de lógica compartilhada (POSIX sh — roda em `ash` do alpine e em bash)

O `docker:27-cli` usa `ash` (busybox), não `bash`. A aritmética de versão é reescrita
**sem arrays** e sem `[[ ]]`, preservando o resultado:

```sh
# .ci-current-tag (before/script comum)
HEADER_TOKEN="PRIVATE-TOKEN:${SUAP_BOT_TOKEN}"
TAG_URL="$CI_API_V4_URL/projects/$CI_PROJECT_ID/repository/tags"
CHANGELOG_URL="$CI_API_V4_URL/projects/$CI_PROJECT_ID/repository/changelog"
CURRENT_TAG="$(curl -s --header "$HEADER_TOKEN" "$TAG_URL" | jq -r '.[0].name')"
MAJOR="$(echo "$CURRENT_TAG" | cut -d. -f1)"
MINOR="$(echo "$CURRENT_TAG" | cut -d. -f2)"
PATCH="$(echo "$CURRENT_TAG" | cut -d. -f3)"
```

- **patch:** `NEXT_TAG="$MAJOR.$MINOR.$((PATCH+1))"`
- **minor:** `NEXT_TAG="$MAJOR.$((MINOR+1)).0"`
- **major:** `NEXT_TAG="$((MAJOR+1)).0.0"`

Guard de mudanças (só patch), preservado:
```sh
HAS_CHANGE="$(curl -s -d "version=$NEXT_TAG" -G --header "$HEADER_TOKEN" "$CHANGELOG_URL" | grep -c 'No changes')"
[ "$HAS_CHANGE" -eq 1 ] && { echo "Tag não foi alterada"; exit 1; }
```

Build + push do prod (write VERSION → entra no `ADD . .` do Dockerfile):
```sh
echo "$NEXT_TAG" > VERSION
docker build -f docker/Dockerfile --target suap-app \
  --build-arg BASE_IMAGE="$CI_REGISTRY_IMAGE:base" \
  -t "$CI_REGISTRY_IMAGE:latest" .
docker tag "$CI_REGISTRY_IMAGE:latest" "$CI_REGISTRY_IMAGE:$NEXT_TAG"
docker push "$CI_REGISTRY_IMAGE:$NEXT_TAG"
docker push "$CI_REGISTRY_IMAGE:latest"
```

Changelog + resumo Gemini + criação da tag (**porte verbatim** do `*script-build`
atual; só troca de `$SUAP_IMAGE`→`$CI_REGISTRY_IMAGE` e remoção do `cp .env`):
```sh
CURRENT_CHANGES="$(curl -s --request GET --header "$HEADER_TOKEN" --data "version=${NEXT_TAG}" "$CHANGELOG_URL" | jq '.notes')"
curl -s --request POST --header "$HEADER_TOKEN" --data "version=${NEXT_TAG}" "$CHANGELOG_URL"
# ... montagem do prompt + chamada $LLM_URL?key=$LLM_KEY + fallback ...
curl -s --request POST --header "$HEADER_TOKEN" --data "tag_name=${NEXT_TAG}&ref=${CI_COMMIT_REF_NAME}&message=${FORMATTED_CHANGES}" "$TAG_URL"
```

### Jobs

| Job | Tag | Executor | Build |
|-----|-----|----------|-------|
| `build-base` | `tests-v3` | docker/DinD | `apk add uv` → `uv audit` → `docker build -f docker/Dockerfile.base -t $CI_REGISTRY_IMAGE:base .` → push base |
| `build-prod` (patch) | `tests-v3` | docker/DinD | tag patch + guard + build/push + changelog/tag |
| `minor-tag` | `tests-v3` | docker/DinD | tag minor + build/push + changelog/tag |
| `major-tag` | `tests-v3` | docker/DinD | tag major + build/push + changelog/tag |
| `deploy-prod-*` | `prod` | shell | inalterado (ansible) |
| `full-deploy-prod` | `prod` | shell | **sem build**: `*script-deploy-master` → `*script-deploy-slaves` |

`build-base` segue em `stage: special-tasks`; `build-prod` em `stage: build`;
`minor-tag`/`major-tag` em `special-tasks` (como hoje).

## Caminho único de build (sem drift)

A sequência "compute tag → build/push → changelog/tag" vira um único anchor de script
(POSIX sh), consumido por `build-prod` / `minor-tag` / `major-tag`. Como nenhum job de
build roda mais no shell, **não há mais caminho de build via shell**: remove-se o anchor
`*script-build` e o passo de build do `full-deploy-prod` (que passa a só fazer
deploy master → slaves). O anchor `.build` (que só agregava o `before_script` de tag +
`docker login` + `after_script` de prune ao `*prod`) é substituído pelo `.build-dind`.
Os alvos `make build`/`push-image`/`build-base` (compose) deixam de ser usados pelo CI
(continuam disponíveis para uso local).

## Fora de escopo

- `deploy-prod-*`, `stop/start-*`, homologação: inalterados.
- Não alterar a semântica de ordenação de tags da API (`.[0].name`) — porte verbatim.

## Riscos / validação

- **ash vs bash:** validar a aritmética de versão num container `docker:27-cli` antes
  de mergear (rodar o pipeline web na branch e disparar `build-base`/`build-prod`).
- **pull da base no build prod:** mesmo projeto → job token cobre; com
  `DOCKER_TLS_CERTDIR=""` o dind sobe sem volume de certs.
- **Doc:** atualizar `bin/ci/README.md` (seção de imagens) cobrindo os jobs de build
  em `tests-v3`, o fluxo de release em dois passos e o novo papel do `full-deploy-prod`
  (deploy master → slaves, sem build).
