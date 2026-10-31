# CI: testes recortados por módulo e dependência — design

Data: 2026-09-14

## Problema

O job `django-geral` roda a suíte unitária inteira em todo MR (`pytest -n 4 -x -m "not e2e"`, sem
caminhos). Medido no job 433119: ≈40 s de preparo, ≈45 s de schema e **≈22 min de testes** (2406
itens). Nos últimos 15 pipelines de MR o job levou 23–35 min; `checagem-codigo`, com o mesmo
`before_script` e sem pytest, leva ≈3 min — o custo está na execução dos testes, que é o que um
recorte alcança.

O e2e já é recortado por módulo (matriz `e2e-modulo` + `rules:changes`), mas só pelo diretório do
próprio módulo: uma mudança em `materiais` não roda nada de `compras`, que tem FK para `materiais`.
E unitário e e2e decidem "o que rodar" por mecanismos diferentes (Python × YAML).

## Objetivo

Unitário e e2e com **o mesmo desenho**: um job `*-transversal` que roda sempre e um job `*-modulo`
que roda só o que o MR pode quebrar — os módulos tocados **e os que dependem diretamente deles**
segundo `module_dependencies.json` (invertido) — decidido por **um único command**. Ex.: alterou
`materiais` → roda `materiais` e `compras`.

| | Transversal (todo MR) | Por módulo (recortado) |
|---|---|---|
| Unitário | `unitario-transversal` (novo): `tests/`, `scripts/` | `unitario-modulo` (era `django-geral`) |
| e2e | `e2e-transversal` (existe): `tests/e2e/` | `e2e-modulo` (reescrito) |

Simulação sobre os últimos 150 merges no master, feita com uma versão **mais conservadora** da regra
(que ainda mandava `suap/`, `pyproject.toml` e `uv.lock` para o fallback): 23% caem no fallback
(tudo), 73% recortam (mediana de 6% da suíte, p90 27%), 5% não rodam teste de módulo. Média ≈ 33% da
suíte: ≈23 min → ≈9 min. A regra final só reduz a fatia de fallback, então esses números são um teto.

## Por que command e não matriz

Os jobs de teste rodam em **3 runners compartilhados** (`caico`, `fresno`, `tucson`) e já enfileiram
com ≤ 6 jobs por pipeline: 84 s e 274 s no `e2e-modulo: [edu]`, 11 min no `django-geral` do pipeline
60520. Uma matriz no unitário teria ≈55 entradas; nos 23% de fallback seriam ≈55 jobs pagando ≈1,5
min de preparo + schema cada, disputando 3 máquinas — mais lento que hoje. Uma matriz também exigiria
duplicar o JSON no YAML (`DEPS` por entrada), um gate de sincronia e depender de glob com chaves em
variável no `rules:changes`, não validado no GitLab do IFRN.

Com o command, a regra fica em Python testável, o número de jobs é fixo e módulo novo com teste
entra sem mexer no YAML.

## Candidatos

- **Transversais** (fixos, rodam sempre nos jobs `*-transversal`): unitário `tests/` e `scripts/`;
  e2e `tests/e2e/`.
- **Candidatos do unitário por módulo:** diretórios de topo que contêm arquivo versionado casando
  `test_*.py` ou `*_test.py` (os `python_files` do `pyproject.toml`) **fora de `*/tests/e2e/`** (módulo
  só com e2e, selecionado sozinho, faria o `pytest -m "not e2e"` sair com código 5), via `git ls-files`, **exceto**
  diretórios ocultos (`.claude`, `.codex`), os transversais (`tests`, `scripts`) e `suap`
  (`suap/settings_test.py` casa `*_test.py` sem ser teste). O critério é "tem arquivo de teste" e não
  "tem `tests/`": `eventos/` tem `test_*.py` na raiz do módulo, e `processmining/` tem `tests/` mas não
  está no JSON.
- **Candidatos do e2e por módulo:** diretórios que casam `*/tests/e2e/` (o glob não casa o
  `tests/e2e` da raiz).

## Regra de seleção (única para unitário e e2e por módulo)

Entrada: `git diff --name-only origin/master..` (já em `get_changed_files()`; o `before_script` faz
merge de `origin/master` antes, então o diff é o do MR).

| Arquivo tocado | `unitario-modulo` / `e2e-modulo` |
|---|---|
| `djtools/**`, `conftest.py` (raiz), `comum/**`, `rh/**` | **fallback**: todos os candidatos |
| diretório de topo `X` qualquer | `X` + dependentes diretos de `X`, filtrados pelos candidatos |
| arquivo na raiz (exceto `conftest.py`) | nada |

Consequências, sem regra especial: `suap/**`, `pyproject.toml`, `uv.lock`, `tests/**`, `scripts/**`,
`docs/**`, `.gitlab-ci.yml` não são candidatos nem têm dependentes → não selecionam nada nos jobs por
módulo; os transversais rodam de qualquer forma.

- **Dependentes diretos, 1 nível.** `dependentes[X]` = todo módulo `M` com `X ∈ JSON[M]`. Sem fecho
  transitivo (ele leva `documento_eletronico` a 97 módulos). O JSON vem só de FKs entre models;
  acoplamento por import/signal/template tag fica para o noturno.
- **Filtro pelos candidatos** descarta rótulos que não são diretório do repo (`auth`, `contenttypes`,
  `reversion`, `oauth2_provider`, `django_celery_beat`) e módulos sem teste do tipo em questão.
- **Fallback vence.** Se qualquer arquivo cair no fallback, o resultado é "todos os candidatos".
- Categorias diferentes no mesmo diff se somam (união).

## O command

Tudo em `comum/management/commands/suap_check.py`, que já tem `get_changed_files()`,
`test_django(apps)` e os modos por `SUAP_CHECK`/`SUAP_APPS`.

### Funções puras

```python
def candidatos_unitario(arquivos_versionados: Iterable[str]) -> set[str]: ...
def candidatos_e2e(arquivos_versionados: Iterable[str]) -> set[str]: ...
def motivo_fallback(arquivos: Iterable[str]) -> str | None: ...
def modulos_afetados(
    arquivos: Iterable[str],
    dependencias: Mapping[str, list[str]],
    candidatos: set[str],
) -> set[str]: ...
def distribuir_shards(pesos: Mapping[str, int], total: int) -> list[list[str]]: ...
```

- `modulos_afetados` já devolve `candidatos` inteiro no fallback — o chamador não distingue.
- Sem Django, sem git, sem I/O no núcleo; a leitura de `git ls-files`, do JSON e do diff fica no
  `handle()`. É o núcleo que os testes exercitam. (Assinaturas indicativas; o plano pode ajustar.)

### `SUAP_CHECK=django`

- `SUAP_APPS=dependentes` → `modulos_afetados(...)` com os candidatos do unitário.
- `SUAP_APPS=geral` → **todos os candidatos** (antes: pytest sem caminho). Assim o noturno não repete
  `tests/` e `scripts/`, que são do `unitario-transversal`. Único uso de `geral` hoje é o CI.
- `SUAP_APPS=<lista>` → como hoje (caminhos literais); é o que o `unitario-transversal` usa.
- Seleção vazia → imprime "nenhum módulo com testes afetado" e retorna sem chamar o pytest (evita o
  exit 5 de "no tests collected").
- Não vazia → `test_django(' '.join(sorted(sel)))`. `-m "not e2e"`, `-n 4`, `-x` e `--cov` ficam.
- Log: arquivos que causaram fallback (se houver), módulos tocados e dependentes puxados.

### `SUAP_CHECK=e2e`

1. **Seleção:** `dependentes` → `modulos_afetados(...)` com os candidatos do e2e; `geral` → todos.
2. **Shard:** lê `CI_NODE_INDEX`/`CI_NODE_TOTAL` (ausentes → 1/1). `distribuir_shards` é gulosa e
   determinística: suítes por peso decrescente (nº de `def test_` em `<modulo>/tests/e2e/test_*.py`),
   empate por nome; cada uma vai ao shard de menor carga (empate → menor índice). Pesos atuais: `edu`
   105, `almoxarifado` 36, `remanejamento` 35, `processo_eletronico` 26, `erros` 20, `ae` 17,
   `documento_eletronico` 13, `eventos` 5 — com 3 shards o `edu` fica sozinho.
3. **Execução:** **uma invocação de pytest por suíte**, em sequência, como no job atual:
   `pytest <modulo>/tests/e2e -m e2e --tracing=retain-on-failure --video=retain-on-failure --output=artifacts/e2e-<modulo>`.
   Só com `SUAP_APPS=geral` (noturno) acrescenta `--cov=. --cov-report=` e
   `COVERAGE_FILE=artifacts/.coverage.e2e-<modulo>`. Isolamento igual ao de hoje (banco e seed de
   sessão por suíte), sem descobrir agora se conftests de módulos diferentes convivem numa sessão.
   Suíte vermelha não interrompe as demais; o command falha no fim listando as vermelhas.
4. Shard sem suíte → imprime "nenhuma suíte e2e neste shard" e sai verde.
5. Log: seleção, motivo, pesos e a atribuição de **todos** os shards.

Risco aceito: a atribuição depende dos pesos no checkout de cada job; um commit no master que
acrescente `def test_` e2e entre o início de dois shards do mesmo pipeline pode fazer uma suíte rodar
duas vezes ou nenhuma. Janela de segundos (os shards começam juntos); o noturno cobre.

## `.gitlab-ci.yml`

```yaml
unitario-transversal:
  extends: .test-base
  stage: test
  services: [*postgres-service]
  variables:
    SUAP_CHECK: django
    SUAP_APPS: tests scripts
    COVERAGE_FILE: artifacts/.coverage.unitario-transversal
  rules:
    - if: $CI_PIPELINE_SOURCE == 'merge_request_event'
    - if: $CI_PIPELINE_SOURCE == 'schedule'
  # artifacts: iguais aos do unitario-modulo (paths + coverage_report)

unitario-modulo:            # era django-geral
  extends: .test-base
  stage: test
  services: [*postgres-service]
  variables:
    SUAP_CHECK: django
  rules:
    - if: $CI_PIPELINE_SOURCE == 'merge_request_event'
      variables: {SUAP_APPS: dependentes}
    - if: $CI_PIPELINE_SOURCE == 'schedule'
      variables: {SUAP_APPS: geral}
  # artifacts: como os do django-geral hoje

.e2e-base:                  # script comum aos dois jobs de e2e
  script:
    - playwright install chromium
    - python manage.py suap_check

e2e-transversal:
  extends: .e2e-base
  variables:
    SUAP_CHECK: e2e-transversal
  rules:
    - if: $CI_PIPELINE_SOURCE == 'merge_request_event'
      variables: {SUAP_APPS: dependentes}
    - if: $CI_PIPELINE_SOURCE == 'schedule'
      variables: {SUAP_APPS: geral}

e2e-modulo:
  extends: .e2e-base
  parallel: 3
  variables:
    SUAP_CHECK: e2e
  rules:
    - if: $CI_PIPELINE_SOURCE == 'merge_request_event'
      variables: {SUAP_APPS: dependentes}
    - if: $CI_PIPELINE_SOURCE == 'schedule'
      variables: {SUAP_APPS: geral}
```

- `unitario-transversal` precisa de `COVERAGE_FILE` próprio: sem ele grava `artifacts/.coverage`, o
  mesmo caminho do `unitario-modulo`, e no `cobertura-combinada` um artefato sobrescreveria o outro.
- `e2e-modulo` perde a matriz `MODULO` e o `rules:changes`: os 3 jobs existem em todo MR.
- `.e2e-base` mantém settings, banco e artefatos, e passa a rodar o `suap_check`; o `COVERAGE_FILE` é
  definido pelo command, por suíte (`artifacts/.coverage.e2e-<modulo>` e
  `artifacts/.coverage.e2e-transversal`). As variáveis `E2E_ALVO`/`E2E_ROTULO` saem, inclusive do `gerar-doc`.
- `e2e-transversal` também roda pelo command (`SUAP_CHECK=e2e-transversal`): sempre `tests/e2e`, sem
  seleção nem shard, com as mesmas regras do `e2e-modulo` (`dependentes` no MR, `geral` no noturno).
- Renomear `django-geral` quebra só referências por nome: `needs` do `cobertura-combinada`,
  comentários do `.gitlab-ci.yml` e `bin/ci/README.md` (linhas 62 e 178). Planos/specs antigos em
  `docs/superpowers/` são históricos e ficam como estão.

## Noturno: suíte completa

Rede de segurança para o que o recorte perde (acoplamento fora de FK).

- Schedule no GitLab: ref `master`, cron `0 2 * * *`. Não existe nenhum hoje; a criação é passo
  manual (UI) ou via `glab`, com ok explícito do dono do projeto.
- Rodam no schedule: `unitario-transversal`, `unitario-modulo` e `e2e-modulo` (com
  `SUAP_APPS: geral`), `e2e-transversal` e `cobertura-combinada`.
- `workflow:rules` já admite o pipeline (`$CI_COMMIT_BRANCH == 'master'`).
- **Exclusão obrigatória:** `build-test-image` e `build-opencode-image` usam
  `if: $CI_COMMIT_BRANCH == 'master'` + `changes:`, e `changes` é sempre verdadeiro em pipeline
  agendado — rebuildariam as imagens toda noite. Ambos ganham como primeira regra
  `- if: $CI_PIPELINE_SOURCE == 'schedule'` / `when: never`.
- Já estão seguros: deploy/homologação (exigem `web|api|external`), `update-demanda-spec` (exige
  `push`), jobs de MR. `behave-changed` e `checagem-codigo` não entram no noturno.
- Aviso de falha: notificação padrão do GitLab ao dono do schedule.

## Cobertura

Com recorte, a cobertura de um MR mede só o que rodou e engana. Decisão: **cobertura combinada só no
noturno**.

- `cobertura-combinada`: regra **só** `if: $CI_PIPELINE_SOURCE == 'schedule'`. `needs`:
  `unitario-modulo`, `unitario-transversal`, `e2e-transversal`, `e2e-modulo` (sem `optional`; um
  `needs` cobre todos os jobs do `parallel`). Script como hoje, acrescentando a cópia de
  `artifacts/.coverage.unitario-transversal` para `artifacts/combinado/`; checagens estritas e
  `coverage report` com o `TOTAL` ficam.
- `e2e-modulo`: no MR roda sem `--cov` — o dado seria descartado.
- `e2e-transversal`: como o `e2e-modulo`, no MR roda sem `--cov`; no noturno grava
  `artifacts/.coverage.e2e-transversal`.
- `unitario-modulo` e `unitario-transversal`: mantêm `--cov` e publicam `coverage_report` no MR — são
  as anotações de linha coberta/descoberta no diff, que já existem hoje e não dependem da combinação.
- **Fechamento da cobertura nos jobs unitários** (medido no pipeline 60597): o pytest terminava os
  testes e ainda levava 3,5 min (`unitario-transversal`, 31 testes) a 6 min (`unitario-modulo`) gerando
  `term-missing` + XML, porque `source = ["."]` faz o relatório analisar todo `.py` do repo (2.317
  arquivos), executado ou não. Agora o pytest só grava dados (`--cov=. --cov-report=`) e o command gera
  `artifacts/coverage.xml` com `include` restrito aos diretórios executados (medido localmente: XML de
  `scripts`+`tests` em 0,3 s contra 20 s do completo, com os mesmos caminhos relativos à raiz). Sem
  `term-missing` no MR. No `geral` (noturno) o `unitario-modulo` só grava dados — os relatórios saem
  do `cobertura-combinada`. `--cov=<diretório>` foi descartado: o XML passa a ter caminhos relativos a
  cada diretório e as anotações do diff deixam de casar. Como `-x` interrompe o xdist antes de o
  pytest-cov juntar os dados dos workers, o command faz `combine(keep=True)` antes do XML.
- `check_coverage` (não roda no CI hoje) **não muda**: tem complexidade ciclomática 20, e tocá-lo
  obrigaria a refatorá-lo inteiro (hook C901) por um ajuste que nenhum job usa.

## Testes

`comum/tests/test_suap_check_selecao.py`, sem banco:

- `candidatos_unitario`: `eventos/test_models.py` → inclui `eventos`; `suap/settings_test.py`,
  `tests/test_x.py`, `bin/scripts/test_x.py`, `.claude/hooks/test_x.py` → não incluem; `edu/tests/x.py`
  sem padrão de teste → não inclui.
- `modulos_afetados` (candidatos fixos no teste):
  - `materiais/models.py` → `{materiais, compras}`;
  - `comum/x.py`, `rh/x.py`, `djtools/x.py`, `conftest.py` → todos os candidatos;
  - `suap/settings_base.py`, `pyproject.toml`, `uv.lock`, `docs/x.md`, `tests/x.py` → vazio;
  - `suap/settings_base.py` + `materiais/x.py` → `{materiais, compras}`;
  - dependente `auth` e módulo fora dos candidatos não entram.
- `distribuir_shards`: pesos atuais em 3 shards → `edu` sozinho; toda suíte em exatamente um shard;
  `total=1` → tudo num shard; pesos vazios → shards vazios.

Código novo com complexidade ciclomática ≤ 10 e tipos nas defs tocadas.

### Validação no GitLab real

O MR desta mudança toca `comum/` e cai no fallback — prova o caminho "tudo" com shards, não o recorte.
Branches descartáveis, fechadas sem merge:

1. só `demandas/` → `unitario-modulo` roda `demandas` + `erros`; e2e só `erros` num shard, os outros 2
   no-op; transversais rodam; `cobertura-combinada` não aparece;
2. só `suap/settings_base.py` → `unitario-modulo` e os 3 shards no-op; transversais rodam;
3. schedule disparado manualmente ("Run") → tudo, `cobertura-combinada` publica o total, nenhum build
   de imagem.

## Documentação

- Comentários do `.gitlab-ci.yml` (`unitario-*`, `.e2e-base`, `e2e-modulo`, `cobertura-combinada`)
  reescritos para a regra do command, o shard e o noturno — os atuais descrevem a matriz.
- `bin/ci/README.md`: `django-geral` → `unitario-transversal`/`unitario-modulo`.
- `AGENTS.md` (entrada `e2e-tester`), `.claude/agents/e2e-tester.md` (passo 10 e o item de relatório
  que cita a matriz) e `.opencode/agent/e2e-tester.md`: o passo "registrar o módulo na matriz
  `e2e-modulo`" **sai** — suíte em `<modulo>/tests/e2e/` é descoberta pelo command.

## Fora do escopo

Fecho transitivo; matriz no unitário; child pipeline; `-n` dentro das suítes e2e; mudanças no
`behave-changed`; dependências fora de FK no JSON.
