# SUAP CI

## Instalação comum (desenvolvimento e homologação)

### Gere um token de acesso no Gitlab e realize o clone do repositório utilizando o token

```bash
git clone https://oauth2:{token}@gitlab.instituicao.edu.br/cosinf/suap.git /opt/suap
```

### Acesse o diretório do projeto

```bash
cd /opt/suap
```

### Instale os softwares necessários

```bash
bin/ci/configure.sh
```

### Edite o arquivo .env criado na raíz do projeto

```bash
vim .env
```

### Inicialize o gitlab-runner e os containers

```bash
bin/ci/register.sh
bin/ci/start.sh
```

## Ambiente de testes

> **Nota:** os comandos abaixo (`build.sh test`, `test.sh`, `test-destroy.sh`) são para **execução local** dos testes. No GitLab CI, o estágio de testes roda em **runners docker** (tag `docker-v3`) — veja a seção [Runner de testes (docker executor)](#runner-de-testes-docker-executor--tag-docker-v3).

### Gere as imagens do SUAP de testes

```bash
bin/ci/build.sh test
```

### Execute os testes

```bash
bin/ci/test.sh {branch-a-testar} master /tmp/ci/ {job-id} test behave administracao
```

### Limpe os containers de teste

```bash
bin/ci/test-destroy.sh {branch-a-testar} test {job-id}
```

---

## Runner de testes (docker executor — tag `docker-v3`)

O estágio de testes do `.gitlab-ci.yml` (`checagem-codigo`, `unitario-transversal`, `unitario-modulo`, `cobertura-combinada`, `behave-changed` e os jobs `behave-by-area`) roda em **runners com executor docker**, com tag **`docker-v3`**. Cada job roda dentro da imagem de teste e o GitLab sobe os serviços (`postgres`, `mailhog`, `pdfprinter`) **isolados por job** — sem estado compartilhado entre execuções concorrentes.

### Visão geral

| Item | Valor |
|------|-------|
| Tag do runner | `docker-v3` |
| Executor | `docker` |
| Imagem dos jobs | `$CI_REGISTRY_IMAGE/test:latest` (publicada pelo job `build-test-image`) |
| Serviços por job | `postgres:18` (alias `postgres`), `mailhog/mailhog` (alias `mail`), `suap-pdf` (alias `pdfprinter`) |

> O job `build-test-image` (tag `tests-v3`, runner **docker** via Docker-in-Docker — requer `privileged = true`) constrói e publica a imagem de teste. Ele roda no `master` quando `uv.lock`/`pyproject.toml`/Dockerfiles mudam, e pode ser disparado manualmente (pipeline web) para o **bootstrap inicial**. Detalhes em [Imagens de CI (build e atualização)](#imagens-de-ci-build-e-atualização).

### 1. Criar o runner na UI do GitLab

A partir do GitLab 17, runners são criados na UI (gera um *authentication token* `glrt-…`); os *registration tokens* antigos foram descontinuados.

- **Project runner:** `cosinf/suap` → **Settings → CI/CD → Runners → New project runner**
- **Instance runner** (compartilhado): **Admin → CI/CD → Runners → New instance runner**

Configure:
- **Tags:** `docker-v3`
- **Run untagged jobs:** desmarcado
- Salve e copie o **authentication token** (`glrt-...`).

### 2. Instalar o gitlab-runner na máquina

Numa máquina com Docker instalado:

```bash
# Debian/Ubuntu
curl -L "https://packages.gitlab.com/install/repositories/runner/gitlab-runner/script.deb.sh" | sudo bash
sudo apt-get install gitlab-runner
```

### 3. Registrar com executor docker

```bash
sudo gitlab-runner register \
  --non-interactive \
  --url "https://gitlab.ifrn.edu.br" \
  --token "glrt-SEU_TOKEN_AQUI" \
  --executor "docker" \
  --docker-image "alpine:latest" \
  --description "docker-v3 (suap testes)"
```

`--docker-image` é apenas a imagem padrão de fallback; cada job de teste define a sua via `image:`.

### 4. Ajustar o `config.toml`

Edite `/etc/gitlab-runner/config.toml` na seção desse runner. Os limites abaixo replicam o que o antigo `bin/ci/test.sh` passava ao `docker run` (não são expressáveis no YAML do job):

```toml
[[runners]]
  name = "docker-v3 (suap testes)"
  url = "https://gitlab.ifrn.edu.br"
  token = "glrt-..."
  executor = "docker"
  [runners.docker]
    image = "alpine:latest"
    # precisa incluir AMBAS: o .gitlab-ci.yml pede pull_policy [always, if-not-present]
    # (always detecta rebuild publicado; if-not-present é o fallback offline).
    # Sem ambas o job falha: "pull policy (...) is not allowed".
    # A política efetiva fica no .gitlab-ci.yml (.test-base.image.pull_policy).
    allowed_pull_policies = ["if-not-present", "always"]
    shm_size = 2147483648         # 2 GB — necessário para o chromium dos testes behave
    memory = "8g"
    memory_reservation = "1g"
    [runners.docker.ulimit]
      "nofile" = "65535:65535"
```

> ℹ️ A imagem de teste usa `pull_policy: [always, if-not-present]` no `.gitlab-ci.yml`:
> após um novo `build-test-image`, `always` faz o runner consultar o registry (só
> manifest/digests) e baixar **apenas as layers alteradas** — não precisa mais limpar
> o cache (`docker rmi`) nem migrar para tag por commit. Já os **services**
> (`postgres`, `mailhog`, `pdfprinter`) ainda usam `pull_policy: if-not-present`: o
> **primeiro** pull ocorre (e o `pdfprinter` exige `DOCKER_AUTH_CONFIG`, passo 5);
> depois usam cache. Se precisar atualizar um service de tag mutável, limpe o cache do
> runner (`docker rmi ...`). Ver detalhes em [Como os runners detectam uma imagem nova](#como-os-runners-detectam-uma-imagem-nova).

Aplique:

```bash
sudo gitlab-runner verify
sudo gitlab-runner restart
```

### 5. Acesso ao registry privado

- **`image: $CI_REGISTRY_IMAGE/test:latest`** é do **próprio projeto** suap → o runner autentica automaticamente com o job token; nenhuma configuração extra.
- **Serviço `pdfprinter`** (`$CI_REGISTRY/cosinf/suap-pdf`) é de **outro projeto** → precisa de credencial. Em **Settings → CI/CD → Variables**, crie a variável **`DOCKER_AUTH_CONFIG`** (tipo *Variable*, *masked* se possível):

```json
{"auths":{"gitlab.ifrn.edu.br:4567":{"auth":"BASE64_DE_usuario:token"}}}
```

onde `BASE64_DE_usuario:token` é gerado com:

```bash
echo -n "usuario:personal_access_token" | base64
```

Use um deploy token ou PAT com escopo `read_registry`.

### 6. Bootstrap da imagem de teste

Antes do primeiro pipeline de testes, publique a imagem ao menos uma vez:

- Rode um **pipeline web** no `master` e dispare manualmente o job **`build-test-image`**.
- Confirme que `$CI_REGISTRY_IMAGE/test:latest` foi publicado no registry do projeto.

### 7. Verificação

- O runner aparece **online** com a tag `docker-v3` em **Settings → CI/CD → Runners**.
- Abra um MR e confirme que `checagem-codigo`/`unitario-transversal`/`unitario-modulo` saem de `pending` e executam.

### Troubleshooting

| Sintoma | Causa provável | Solução |
|---------|----------------|---------|
| Jobs ficam em `pending` | Nenhum runner online com a tag `docker-v3` | Verifique o registro/online em Runners; confira a tag |
| `ERROR: failed to pull image ...test:latest` | Imagem de teste não publicada | Rode `build-test-image` (bootstrap) no master |
| `pull policy (if-not-present) is not allowed` | `allowed_pull_policies` do runner não inclui `if-not-present` | Adicione `allowed_pull_policies = ["if-not-present", "always"]` no `config.toml` (passo 4) |
| Runner não pega a nova `test:latest` | `allowed_pull_policies` sem `always` (o `[always, if-not-present]` cai no fallback de cache) | Adicione `always` ao `allowed_pull_policies` (passo 4); `always` detecta o rebuild automaticamente |
| Service de tag mutável não atualiza | `postgres`/`mailhog`/`pdfprinter` usam `if-not-present` | `docker rmi <imagem>` no runner para forçar o re-pull |
| `pull access denied` no serviço `pdfprinter` | Falta `DOCKER_AUTH_CONFIG` (registry de outro projeto) | Configure a variável `DOCKER_AUTH_CONFIG` (passo 5) |
| `build-*-image`: dind não sobe (`Service ... probably didn't start properly`, health check timeout, logs do dind com `mount: permission denied`, `AppArmor ... --privileged mode might break`, e depois `/certs/client/ca.pem: no such file or directory`) | Runner que atende `tests-v3` está com `privileged = false` (o `docker:dind` precisa de privileged para iniciar o daemon) | Defina `privileged = true` no `config.toml` **do runner correto** (o que executou o job — veja a linha `on <runner>` no log, não necessariamente o que você editou) e `gitlab-runner restart` |
| `build-*-image`: `unable to resolve docker endpoint: open /certs/client/ca.pem: no such file or directory` | dind com TLS, mas o `/certs/client` não é compartilhado com o job (não é automático no executor docker) | Use TLS off (`DOCKER_TLS_CERTDIR: ""` + `DOCKER_HOST: tcp://docker:2375`, já no `.docker-build`) **ou** monte `volumes = ["/certs/client", "/cache"]` no runner |
| Testes behave/chromium crasham (`Target closed`, SIGBUS) | `/dev/shm` pequeno (default 64 MB) | Defina `shm_size = 2147483648` no `config.toml` |
| Testes com OOM / `Killed` | Sem limite de memória adequado | Ajuste `memory`/`memory_reservation` |
| `Too many open files` | `nofile` baixo | Configure `[runners.docker.ulimit]` com `nofile = "65535:65535"` |
| `pre-commit`/`git diff origin/master` falha | `origin/master` ausente no clone | `GIT_DEPTH: 0` + `git fetch origin master` já estão no `.test-base`; confirme que não foram removidos |

## Ambiente de homologação

### Gere as imagens do SUAP de homologação

```bash
bin/ci/build.sh base
```

### Crie o banco de log

```bash
bin/ci/createlog.sh
```

### Crie o banco template

```bash
python manage.py create_db
```

### Crie um ambiente de homologação para testar a instalação

```bash
bin/ci/deploy.sh --branch "master" --owner "admin" --database "suap_dev"  --password "123"
```

### Remova o ambiente provisoriamente

```bash
bin/ci/undeploy.sh --branch "master" --owner "admin"
```

### Recrie o ambiente de teste

```bash
bin/ci/deploy.sh --branch "master" --owner "admin" --database "suap_dev"  --password "123"
```

### Remova o ambiente definitivamente

```bash
bin/ci/destroy.sh --branch "master" --owner "admin"
```

### Registre os containers no nginx

```bash
bin/ci/index.sh
```

---

## AI Skills — OpenCode no GitLab CI

Este diretório também contém scripts para execução de skills do **OpenCode** no GitLab CI, automatizando tarefas de IA como formatação de MRs (`/mr-format`) e revisão de código (`/code-review`).

### Requisitos do Runner

O runner que executará os jobs (`tag: ia-v3`) precisa ter:

- **Node.js ≥ 20** (para `npx`)
- **GitLab personal access token** com permissões `api` e `read_repository`
- **Acesso à internet** para baixar o MCP `@zereight/mcp-gitlab`

### Instalação do OpenCode

No runner `ia-v3` (ou na imagem Docker usada por ele):

```bash
# Instalação via npm (recomendado)
npm install -g @opencode-ai/cli

# Ou via bun
bun install -g @opencode-ai/cli

# Verificar instalação
opencode --version
```

#### Variante: Docker

Se o runner usar containers, crie uma imagem base com OpenCode pré-instalado:

```dockerfile
FROM node:20-slim
RUN npm install -g @opencode-ai/cli
# Copie o repositório ou monte como volume
```

### Configuração do MCP GitLab

O script `opencode-skill.sh` **gera o `opencode.json` dinamicamente** a cada execução, usando variáveis do GitLab CI:

| Variável | Fonte no GitLab CI |
|----------|--------------------|
| `GITLAB_TOKEN` | `$SUAP_BOT_TOKEN` (CI/CD variable) |
| `GITLAB_API_URL` | `$CI_SERVER_URL/api/v4` |

Não é necessário configurar manualmente o `~/.config/opencode/opencode.json` no runner — o script faz isso sozinho.

### Variáveis de Ambiente no GitLab

No projeto GitLab, vá em **Settings → CI/CD → Variables** e adicione:

| Key | Tipo | Obrigatório | Descrição |
|-----|------|-------------|-----------|
| `SUAP_BOT_TOKEN` | Variable | Sim | Personal access token do bot GitLab |
| `OPENCODE_PROVIDER` | Variable | Não | Provedor LLM (ex: `openai`, `google`, `anthropic`) |
| `OPENCODE_MODEL` | Variable | Não | Modelo LLM (ex: `gpt-4o`, `gemini-1.5-pro`, `claude-sonnet-5`) |
| `OPENCODE_API_KEY` | Variable | Sim* | Chave de API do provedor LLM (*obrigatória se provider for definido) |

As demais variáveis (`CI_SERVER_URL`, `CI_MERGE_REQUEST_IID`, etc.) são fornecidas automaticamente pelo GitLab CI.

> **Nota:** Se `OPENCODE_PROVIDER` e `OPENCODE_MODEL` não forem definidos, o opencode usará o modelo padrão configurado localmente ou o primeiro disponível.

#### Mapeamento de chaves de API por provider

O script converte `OPENCODE_API_KEY` automaticamente para a variável esperada por cada provedor:

| Provider | Variável exportada |
|----------|-------------------|
| `openai` | `OPENAI_API_KEY` |
| `google` / `gemini` | `GOOGLE_GENERATIVE_AI_API_KEY` |
| `anthropic` / `claude` | `ANTHROPIC_API_KEY` |

### Como Funciona

#### `opencode-skill.sh`

```bash
bin/ci/opencode-skill.sh <skill-name> <mr-iid> <project-id> <gitlab-url> <gitlab-token> [provider] [model] [api-key]
```

1. Monta a URL do MR: `${GITLAB_URL}/${PROJECT_ID}/-/merge_requests/${MR_IID}`
2. Gera `~/.config/opencode/opencode.json` com o MCP GitLab apontando para o token
3. Se `provider` e `model` forem fornecidos (via argumento ou variável de ambiente), passa `-m provider/model`
4. Exporta a chave de API em `OPENCODE_API_KEY` (provedores `opencode`/`opencode-go`; o OpenCode 2.x não lê mais o `auth.json`)
5. Executa: `opencode run "/<skill> <mr-url>" --standalone --auto`, com a saída em texto direto no log do job; falha da sessão sai com código ≠ 0

#### Jobs no `.gitlab-ci.yml`

| Job | Skill | Gatilho |
|-----|-------|---------|
| `mr-format` | `/mr-format` | Automático em MRs não-draft |
| `ai-code-review` | `/code-review` | Manual (não bloqueia pipeline) |

### Teste Local (opcional)

Para simular a execução localmente:

```bash
export SUAP_BOT_TOKEN="glpat-xxxxxxxxxxxxxxxxxxxx"
export CI_SERVER_URL="https://gitlab.ifrn.edu.br"
export CI_MERGE_REQUEST_IID="123"
export CI_MERGE_REQUEST_PROJECT_ID="cosinf/suap"
export OPENCODE_PROVIDER="openai"
export OPENCODE_MODEL="gpt-4o"
export OPENCODE_API_KEY="sk-xxxxxxxxxxxxxxxxxxxxxxxx"

bin/ci/opencode-skill.sh mr-format \
    "$CI_MERGE_REQUEST_IID" \
    "$CI_MERGE_REQUEST_PROJECT_ID" \
    "$CI_SERVER_URL" \
    "$SUAP_BOT_TOKEN" \
    "$OPENCODE_PROVIDER" \
    "$OPENCODE_MODEL" \
    "$OPENCODE_API_KEY"
```

### Troubleshooting

| Sintoma | Causa provável | Solução |
|---------|----------------|---------|
| `opencode: command not found` | OpenCode não instalado no runner | Instale globalmente ou na imagem Docker |
| `404 Project Not Found` | `project_id` incorreto no `opencode.json` | Verifique se `CI_MERGE_REQUEST_PROJECT_ID` está correto |
| `401 Unauthorized` | Token inválido ou sem permissões `api` | Gere um novo PAT com escopo `api` |
| MCP GitLab não responde | `npx` bloqueado ou sem internet | Verifique conectividade e permissões do `npx` |
| Skill carrega mas não executa | Falta `--dangerously-skip-permissions` | Script já inclui; verifique se está sendo chamado corretamente |
| Job fica esperando input | Skill não reconheceu a URL sozinha | Verifique se a skill SKILL.md tem a seção "Autonomia no CI" |
| `Model not found` ou erro de provider | `OPENCODE_PROVIDER`/`OPENCODE_MODEL` inválidos | Verifique os valores com `opencode models <provider>` |
| Respostas de baixa qualidade | Modelo inadequado para code review | Use modelos maiores (ex: `gpt-4o`, `claude-opus-5`) |

### Atualização do OpenCode

```bash
opencode upgrade
# ou para versão específica
opencode upgrade 1.2.3
```

### Referências

- OpenCode CLI: https://opencode.ai
- MCP GitLab: https://github.com/zereight/mcp-gitlab

## Imagens de CI (build e atualização)

A pipeline depende de duas imagens próprias publicadas no registry do projeto:

| Imagem | Job que gera | Dockerfile | Consumida por |
|--------|--------------|------------|---------------|
| `$CI_REGISTRY_IMAGE/test:latest` | `build-test-image` | `bin/ci/Dockerfile` (target `suap-test`) | jobs de teste (`.test-base`) |
| `$CI_REGISTRY_IMAGE/opencode:latest` | `build-opencode-image` | `bin/ci/Dockerfile.opencode` | jobs `ai-review` (`.opencode-skill`) |

Ambos os jobs de build rodam no **executor docker** (`tags: tests-v3`) e usam
**Docker-in-Docker** (template `.docker-build` no `.gitlab-ci.yml`):

```yaml
.docker-build:
  image: docker:27-cli
  services:
    - docker:27-dind
  variables:
    DOCKER_TLS_CERTDIR: ""
    DOCKER_HOST: tcp://docker:2375
```

> **Pré-requisito do runner — `privileged = true`.** O serviço `docker:dind` só
> sobe se o runner que atende `tests-v3` estiver com `privileged = true` no
> `config.toml`. Com `privileged = false` o daemon dind não inicia (health check
> timeout, `mount: permission denied` no log do dind). Ajuste em
> `/etc/gitlab-runner/config.toml` **do runner que executa o job**:
>
> ```toml
> [runners.docker]
>   privileged = true
> ```
>
> Sem DinD/`docker` na imagem, o sintoma é `docker: not found` (exit 127), pois o
> job cai na imagem default `alpine:latest`.

> **TLS desabilitado (`DOCKER_TLS_CERTDIR: ""`).** No executor docker, o
> compartilhamento do diretório de certs (`/certs/client`) entre o service `dind`
> e o container do job **não** é automático — manter TLS exigiria montar
> `volumes = ["/certs/client", "/cache"]` no `config.toml` de **cada** runner de
> build. Sem TLS, o dind escuta em `tcp://docker:2375` na rede isolada do job e
> nenhum runner precisa de config extra. Sintoma de manter TLS sem o volume:
> `unable to resolve docker endpoint: open /certs/client/ca.pem: no such file or directory`.

### Quando as imagens são reconstruídas

`build-test-image` e `build-opencode-image` rodam automaticamente **no master**
quando os arquivos relevantes mudam (`rules: changes:`) — `uv.lock`,
`pyproject.toml`, `bin/ci/Dockerfile`, `docker/Dockerfile*` (test) ou
`bin/ci/Dockerfile.opencode` (opencode) — e podem ser disparados manualmente em
pipelines `web`/`api`/`external`. Em MRs comuns a imagem **não** é reconstruída;
o delta de dependências é coberto pelo `uv sync --all-groups` no `before_script`
dos jobs de teste.

### Como os runners detectam uma imagem nova

As tags são **mutáveis** (`:latest`). Para que um runner pegue um rebuild
recém-publicado sem rebaixar ≈3.6 GB a cada job, os jobs consumidores usam:

```yaml
pull_policy: [always, if-not-present]
```

- `always` faz o runner consultar o registry antes do job: busca apenas o
  **manifest** e compara digests das layers. Se nada mudou, **zero download**
  (só um round-trip de segundos); se houve rebuild, baixa **só as layers
  alteradas**, uma vez por runner, e cacheia.
- `if-not-present` é o fallback: usa a imagem em cache se o registry estiver
  inacessível.

> **Pré-requisito do runner — `allowed_pull_policies`.** Precisa incluir **ambas**
> as políticas, senão o job erra ao resolver a `pull_policy`:
>
> ```toml
> [runners.docker]
>   allowed_pull_policies = ["if-not-present", "always"]
> ```
- GitLab CI variables: https://docs.gitlab.com/ee/ci/variables/

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

## Deploy de produção (SSH via variáveis CI/CD)

Todos os jobs de produção (tag `prod`) conectam nos servidores via SSH usando
variáveis de ambiente configuradas no GitLab CI/CD — sem `suap-ansible`. O script
`bin/ci/deploy-remote.sh <modo>` configura o SSH agent a partir dessas variáveis e
executa o fluxo em cada servidor.

| Job | Modo | Hosts | Faz |
|-----|------|-------|-----|
| `deploy-prod-master` | `master` | `PROD_SSH_HOST` | deploy + `sync` |
| `deploy-prod-slaves` | `slaves` | `PROD_SSH_SLAVES` | download em paralelo, restart um por vez |
| `full-deploy-prod` | `master` + `slaves` | ambos | os dois acima, em ordem |
| `stop-all` / `start-all` | `stop-all` / `start-all` | `PROD_SSH_HOST` + `PROD_SSH_SLAVES` | `make down` / `make up`, em paralelo |

Deploy aborta na primeira falha (não segue o rolling com um nó quebrado). Stop/start
rodam em paralelo em todos os hosts (saída prefixada com `[host]`) e são best-effort:
tentam todos e o job falha no fim listando os que falharam. Os restarts do deploy são
sempre um host por vez — com o drain automático, cada `make down` de nó com nginx leva
~`DRAIN_SECONDS` (20s) a mais. Nos slaves, o download (`git pull` +
`docker compose pull`) roda antes, em paralelo em todos os hosts.

O deploy do pdfprinter fica no projeto `cosinf/suap-pdf` (job `deploy-prod`).

### Variáveis CI/CD

Em **Settings → CI/CD → Variables**, adicione:

| Key | Tipo | Masked | Descrição |
|-----|------|--------|-----------|
| `PROD_SSH_HOST` | Variable | Não | Hostname/IP do servidor master |
| `PROD_SSH_USER` | Variable | Não | Usuário SSH |
| `PROD_SSH_PRIVATE_KEY` | Variable | Sim | Chave privada SSH (sem senha) **em base64 numa linha** (`base64 -w0`) — masked não aceita espaço/quebra de linha |
| `PROD_SSH_KNOWN_HOSTS` | Variable | Não | Saída de `ssh-keyscan <host>` (verificação de host key). Chave pública, não é segredo — e tem espaços, então não dá pra mascarar |
| `PROD_SSH_PORT` | Variable | Não | Porta SSH (opcional, default: `22`) |
| `PROD_SSH_SLAVES` | Variable | Não | Slaves separados por vírgula (ex: `host1,host2`) |
| `PROD_SSH_PATH` | Variable | Não | Diretório do `suap_deploy` nos servidores (ex: `/opt/suap_deploy`) |

### Fluxo de deploy por servidor

**Master:**
```bash
git pull origin master
docker compose pull
make down
make exec COMMAND='python manage.py sync'
make up
```

**Slaves**, em duas fases:
```bash
# 1. Em paralelo, em todos os slaves (não afeta o que está rodando):
git pull origin master
docker compose pull

# 2. Um slave por vez (tira o nó do pool durante o restart):
make down
make up
```

Se a fase 1 falhar em qualquer slave, nenhum é reiniciado. A saída de cada host na
fase 1 aparece no log prefixada com `[host]`.

O drain do balanceador é automático no `suap_deploy` (hooks do compose): `make down`
marca `deploy/status.txt=drain` e espera `DRAIN_SECONDS` (default 20) antes de parar
o nginx; `make up` volta pra `healthy`. Não há mais `drain.sh`/`sleep`/`healthy.sh`
no fluxo. Ver `contrib/multi-node/README.md` no `suap_deploy` (inclui a config do HAProxy).

### Gerando as variáveis

```bash
# Host key do servidor
ssh-keyscan -p 22 master.exemplo.edu.br

# Chave privada (já deve existir no servidor; gere se necessário)
ssh-keygen -t ed25519 -C "suap-deploy" -f ~/.ssh/suap_deploy -N ""
base64 -w0 ~/.ssh/suap_deploy; echo   # uma linha → PROD_SSH_PRIVATE_KEY (Masked + Protected)
cat ~/.ssh/suap_deploy.pub  # adicionar ao ~/.ssh/authorized_keys do servidor
```

### Troubleshooting

| Sintoma | Causa provável | Solução |
|---------|----------------|---------|
| `Host key verification failed` | `PROD_SSH_KNOWN_HOSTS` ausente ou incorreta | Gere com `ssh-keyscan <host>` e atualize a variável |
| `Unable to create masked variable ... whitespace characters` (ao cadastrar) | Chave privada colada em texto puro | Cadastre a saída de `base64 -w0 ~/.ssh/suap_deploy` |
| `base64: invalid input` / `Error loading key "(stdin)"` | `PROD_SSH_PRIVATE_KEY` não está em base64 (ou foi cortada) | Regere com `base64 -w0` e cole a linha inteira |
| `Permission denied (publickey)` | Chave privada inválida ou não autorizada no servidor | Verifique se a chave pública está no `authorized_keys` do usuário |
| `PROD_SSH_SLAVES vazia, pulando slaves` | Variável não configurada | Normal se não houver slaves; configure se necessário |
| `make down FALHOU em: host1 host2` | Stop/start falhou nesses hosts (os demais foram processados) | Veja o log do host no job e repita |
| `make: command not found` no servidor remoto | Make não instalado no servidor | Instale `make` ou adapte os comandos no script |
