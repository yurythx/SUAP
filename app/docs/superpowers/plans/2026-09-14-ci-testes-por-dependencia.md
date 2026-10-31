# CI: testes recortados por módulo e dependência — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unitário e e2e rodam, em MR, só os testes dos módulos tocados e dos que dependem diretamente deles (`module_dependencies.json` invertido), decididos por um único command; a suíte completa e a cobertura combinada passam a rodar só no pipeline agendado (noturno).

**Architecture:** Funções puras de seleção em `comum/management/commands/suap_check.py` (candidatos, fallback, dependentes diretos, shards), usadas por dois modos do command: `SUAP_CHECK=django` e `SUAP_CHECK=e2e`, com `SUAP_APPS=dependentes|geral`. No `.gitlab-ci.yml`: `django-geral` vira `unitario-modulo`, nasce `unitario-transversal`, `e2e-modulo` troca a matriz por `parallel: 3`, e `cobertura-combinada` passa a rodar só no schedule.

**Tech Stack:** Python 3.14, Django 5.2 management command, pytest + pytest-django, GitLab CI (`parallel`, `rules:variables`, `needs`), `glab`.

**Spec:** `docs/superpowers/specs/2026-09-14-ci-testes-por-dependencia-design.md`

## Global Constraints

- Idioma pt-BR em identificadores, comentários, docstrings, commits e docs.
- Ruff do repo: linha 150, aspas simples; rode `uv run ruff format <arquivo>` e `uv run ruff check <arquivo> --fix` antes de commitar.
- Complexidade ciclomática (ruff C901) **≤ 10** em toda função tocada — o hook `.claude/hooks/check_complexity.py` bloqueia a edição acima disso. `Command.handle` já está em **10**: cada ramo novo tem de sair em método próprio, compensando o `if` interno removido.
- Não tocar `Command.check_coverage` (complexidade 20).
- Tipos em toda def nova/tocada (parâmetros + retorno); `from collections.abc import Iterable, Mapping`; `X | None`.
- Nenhuma dependência nova.
- Dependentes **diretos** (1 nível), nunca fecho transitivo.
- Fallback (todos os candidatos): arquivos em `djtools/`, `comum/`, `rh/` ou o `conftest.py` da raiz.
- Transversais do unitário: `tests` e `scripts`. Não candidatos do unitário: diretórios ocultos, `tests`, `scripts`, `suap`; arquivos em `*/tests/e2e/` não tornam um módulo candidato do unitário.
- Padrão de arquivo de teste = `python_files` do `pyproject.toml`: `test_*.py` e `*_test.py`.
- `parallel: 3` no `e2e-modulo`; schedule no master com cron `0 2 * * *`.
- Rodar os testes locais com o Postgres de teste já de pé (`suap-test-db`, porta 5433):
  `DATABASE_PORT=5433 DATABASE_USER=postgres DATABASE_PASSWORD=postgres DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest -q <alvo>`
  (os testes deste plano não usam banco; a rodada leva ≈12 s).
- Push, abertura de MR, branches descartáveis e criação do schedule **só com ok explícito do usuário** no chat.

---

## File Structure

| Arquivo | Papel |
|---|---|
| `comum/management/commands/suap_check.py` (modificar) | Funções puras de seleção + I/O fino (`git ls-files`, JSON, peso) + métodos `selecionar`, `executar_django`, `executar_e2e`, `rodar_suite_e2e`; `handle` despacha |
| `comum/tests/test_suap_check_selecao.py` (criar) | Testes sem banco das funções puras e da fiação dos modos (com `run_command` substituído) |
| `.gitlab-ci.yml` (modificar) | Jobs `unitario-transversal`, `unitario-modulo`, `e2e-modulo` (parallel), regras de schedule, exclusão nos builds, `cobertura-combinada` noturno, comentários |
| `bin/ci/README.md`, `AGENTS.md`, `.claude/agents/e2e-tester.md`, `.opencode/agent/e2e-tester.md` (modificar) | Nome dos jobs e fim do passo "registrar módulo na matriz" |

---

### Task 1: Funções puras de seleção

**Files:**
- Modify: `comum/management/commands/suap_check.py` (imports no topo; funções novas logo após `get_changed_files`, antes de `class Command`)
- Create: `comum/tests/test_suap_check_selecao.py`

**Interfaces:**
- Consumes: nada.
- Produces (módulo `comum.management.commands.suap_check`):
  - `FALLBACK_DIRETORIOS: frozenset[str]`, `FALLBACK_ARQUIVOS: frozenset[str]`, `NAO_CANDIDATOS_UNITARIO: frozenset[str]`
  - `candidatos_unitario(arquivos_versionados: Iterable[str]) -> set[str]`
  - `candidatos_e2e(arquivos_versionados: Iterable[str]) -> set[str]`
  - `motivo_fallback(arquivos: Iterable[str]) -> str | None`
  - `modulos_afetados(arquivos: Iterable[str], dependencias: Mapping[str, Iterable[str]], candidatos: set[str]) -> set[str]`
  - `distribuir_shards(pesos: Mapping[str, int], total: int) -> list[list[str]]`

- [ ] **Step 1: Escrever os testes que falham**

Criar `comum/tests/test_suap_check_selecao.py`:

```python
"""Seleção de testes por módulo e dependência do ``suap_check`` — sem banco."""

import pytest

from comum.management.commands.suap_check import (
    candidatos_e2e,
    candidatos_unitario,
    distribuir_shards,
    modulos_afetados,
    motivo_fallback,
)

# `auth` é chave do JSON real mas não é diretório do repo: nunca pode virar caminho do pytest.
DEPENDENCIAS = {
    'auth': ['materiais'],
    'compras': ['comum', 'materiais', 'processo_eletronico', 'rh'],
    'edu': ['comum', 'rh'],
    'erros': ['comum', 'demandas'],
    'materiais': ['comum', 'rh'],
}
CANDIDATOS = {'compras', 'demandas', 'edu', 'erros', 'materiais'}


def test_candidatos_unitario_sao_diretorios_de_topo_com_arquivo_de_teste():
    arquivos = [
        'eventos/test_models.py',
        'edu/tests/test_diarios.py',
        'edu/tests/helpers.py',
        'almoxarifado/features/test_initial_data.py',
        'processmining/tests/test_a.py',
        'ae/tests/e2e/test_ae.py',
        'rsc/tests.py',
        'protocolo/models.py',
        'suap/settings_test.py',
        'tests/test_servidor_save.py',
        'bin/scripts/test_papeis.py',
        '.claude/hooks/test_x.py',
        'test_na_raiz.py',
    ]

    assert candidatos_unitario(arquivos) == {'almoxarifado', 'edu', 'eventos', 'processmining'}


def test_candidatos_e2e_sao_modulos_com_tests_e2e():
    arquivos = [
        'edu/tests/e2e/test_diretoria.py',
        'edu/tests/e2e/conftest.py',
        'erros/tests/e2e/test_navegacao.py',
        'ae/tests/test_models.py',
        'tests/e2e/test_login.py',
        'ponto/tests/e2e/conftest.py',
    ]

    assert candidatos_e2e(arquivos) == {'edu', 'erros'}


@pytest.mark.parametrize(
    ('arquivos', 'esperado'),
    [
        (['docs/x.md', 'rh/models.py'], 'rh/models.py'),
        (['comum/views.py'], 'comum/views.py'),
        (['djtools/e2e_ui.py'], 'djtools/e2e_ui.py'),
        (['conftest.py'], 'conftest.py'),
        (['remanejamento/conftest.py'], None),
        (['suap/settings_base.py', 'pyproject.toml', 'uv.lock'], None),
        (['', 'edu/models.py'], None),
    ],
)
def test_motivo_fallback(arquivos, esperado):
    assert motivo_fallback(arquivos) == esperado


@pytest.mark.parametrize(
    ('arquivos', 'esperado'),
    [
        (['materiais/models.py'], {'materiais', 'compras'}),
        (['demandas/views.py'], {'demandas', 'erros'}),
        (['comum/models.py'], CANDIDATOS),
        (['rh/models.py'], CANDIDATOS),
        (['djtools/utils.py'], CANDIDATOS),
        (['conftest.py'], CANDIDATOS),
        (['suap/settings_base.py'], set()),
        (['pyproject.toml', 'uv.lock'], set()),
        (['docs/x.md', '.gitlab-ci.yml'], set()),
        (['tests/test_servidor_save.py', 'bin/scripts/test_papeis.py'], set()),
        (['suap/settings_base.py', 'materiais/x.py'], {'materiais', 'compras'}),
        (['processo_eletronico/models.py'], {'compras'}),
        ([], set()),
    ],
)
def test_modulos_afetados(arquivos, esperado):
    assert modulos_afetados(arquivos, DEPENDENCIAS, CANDIDATOS) == esperado


def test_modulos_afetados_nao_devolve_rotulo_que_nao_e_candidato():
    assert 'auth' not in modulos_afetados(['materiais/models.py'], DEPENDENCIAS, CANDIDATOS)


def test_modulos_afetados_so_um_nivel():
    dependencias = {'a': ['b'], 'b': ['c']}

    assert modulos_afetados(['c/x.py'], dependencias, {'a', 'b', 'c'}) == {'b', 'c'}


PESOS_ATUAIS = {
    'edu': 105,
    'almoxarifado': 36,
    'remanejamento': 35,
    'processo_eletronico': 26,
    'erros': 20,
    'ae': 17,
    'documento_eletronico': 13,
    'eventos': 5,
}


def test_distribuir_shards_isola_a_suite_mais_pesada():
    shards = distribuir_shards(PESOS_ATUAIS, 3)

    assert shards[0] == ['edu']
    assert sorted(s for shard in shards for s in shard) == sorted(PESOS_ATUAIS)


def test_distribuir_shards_e_deterministico():
    assert distribuir_shards(PESOS_ATUAIS, 3) == distribuir_shards(dict(reversed(PESOS_ATUAIS.items())), 3)


def test_distribuir_shards_com_um_shard_so():
    assert distribuir_shards({'b': 1, 'a': 1}, 1) == [['a', 'b']]


def test_distribuir_shards_sem_suites():
    assert distribuir_shards({}, 3) == [[], [], []]


def test_distribuir_shards_espalha_suites_de_peso_zero():
    assert distribuir_shards({'a': 0, 'b': 0, 'c': 0}, 3) == [['a'], ['b'], ['c']]
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `DATABASE_PORT=5433 DATABASE_USER=postgres DATABASE_PASSWORD=postgres DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest -q comum/tests/test_suap_check_selecao.py`
Expected: erro de coleta `ImportError: cannot import name 'candidatos_e2e' from 'comum.management.commands.suap_check'`.

- [ ] **Step 3: Implementar**

Em `comum/management/commands/suap_check.py`, trocar o bloco de imports do topo:

```python
import glob
import json
import os
import shlex
import subprocess
import sys
```

por:

```python
import glob
import json
import os
import shlex
import subprocess
import sys
from collections.abc import Iterable, Mapping
```

E inserir, logo depois da função `get_changed_files()` e antes de `class Command(BaseCommandPlus):`:

```python
# Seleção de testes por módulo e dependência (SUAP_APPS=dependentes). Ver
# docs/superpowers/specs/2026-09-14-ci-testes-por-dependencia-design.md.
#
# Mudança nestes lugares afeta todo módulo, então roda todos os candidatos.
FALLBACK_DIRETORIOS = frozenset({'djtools', 'comum', 'rh'})
FALLBACK_ARQUIVOS = frozenset({'conftest.py'})
# `tests` e `scripts` são dos jobs transversais; `suap/settings_test.py` casa `*_test.py` sem ser teste.
NAO_CANDIDATOS_UNITARIO = frozenset({'tests', 'scripts', 'suap'})


def _eh_arquivo_de_teste(caminho: str) -> bool:
    """Replica o ``python_files`` do pytest (``test_*.py`` e ``*_test.py``)."""
    nome = caminho.rsplit('/', 1)[-1]
    return nome.endswith('.py') and (nome.startswith('test_') or nome.endswith('_test.py'))


def candidatos_unitario(arquivos_versionados: Iterable[str]) -> set[str]:
    """Diretórios de topo com arquivo de teste unitário, fora ocultos, transversais e ``suap``.

    Arquivos em ``*/tests/e2e/`` não contam: um módulo só com e2e, selecionado sozinho, faria o
    ``pytest -m "not e2e"`` sair com código 5 (nada coletado).
    """
    candidatos = set()
    for caminho in arquivos_versionados:
        topo, separador, _resto = caminho.partition('/')
        if not separador or topo.startswith('.') or topo in NAO_CANDIDATOS_UNITARIO or '/tests/e2e/' in caminho:
            continue
        if _eh_arquivo_de_teste(caminho):
            candidatos.add(topo)
    return candidatos


def candidatos_e2e(arquivos_versionados: Iterable[str]) -> set[str]:
    """Módulos com arquivo de teste em ``<modulo>/tests/e2e/`` (o ``tests/e2e`` da raiz não casa)."""
    candidatos = set()
    for caminho in arquivos_versionados:
        partes = caminho.split('/')
        if len(partes) >= 4 and partes[1:3] == ['tests', 'e2e'] and _eh_arquivo_de_teste(caminho):
            candidatos.add(partes[0])
    return candidatos


def motivo_fallback(arquivos: Iterable[str]) -> str | None:
    """Primeiro arquivo do diff que obriga a rodar todos os candidatos, ou ``None``."""
    for caminho in arquivos:
        if caminho in FALLBACK_ARQUIVOS or ('/' in caminho and caminho.split('/')[0] in FALLBACK_DIRETORIOS):
            return caminho
    return None


def modulos_afetados(arquivos: Iterable[str], dependencias: Mapping[str, Iterable[str]], candidatos: set[str]) -> set[str]:
    """Candidatos que o diff pode quebrar: diretórios tocados e seus dependentes DIRETOS.

    ``dependencias`` é o ``module_dependencies.json`` (módulo -> de quem ele depende); aqui ele é
    invertido. Fallback devolve todos os candidatos.
    """
    arquivos = [caminho for caminho in arquivos if caminho]
    if motivo_fallback(arquivos):
        return set(candidatos)
    dependentes: dict[str, set[str]] = {}
    for modulo, deps in dependencias.items():
        for dep in deps:
            dependentes.setdefault(dep, set()).add(modulo)
    selecionados = set()
    for topo in {caminho.split('/')[0] for caminho in arquivos}:
        selecionados |= {topo, *dependentes.get(topo, ())}
    return selecionados & candidatos


def distribuir_shards(pesos: Mapping[str, int], total: int) -> list[list[str]]:
    """Distribuição gulosa e determinística: mais pesada primeiro, sempre no shard menos carregado."""
    shards: list[list[str]] = [[] for _ in range(total)]
    cargas = [0] * total
    for suite in sorted(pesos, key=lambda nome: (-pesos[nome], nome)):
        indice = cargas.index(min(cargas))
        shards[indice].append(suite)
        # ponytail: peso 0 conta como 1, senão suítes sem `def test_` iriam todas para o shard 1.
        cargas[indice] += max(pesos[suite], 1)
    return shards
```

Observação: em `distribuir_shards({'b': 1, 'a': 1}, 1)` a ordenação por nome dá `['a', 'b']`.

- [ ] **Step 4: Rodar e ver passar**

Run: `DATABASE_PORT=5433 DATABASE_USER=postgres DATABASE_PASSWORD=postgres DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest -q comum/tests/test_suap_check_selecao.py`
Expected: `29 passed`.

- [ ] **Step 5: Lint e complexidade**

Run: `uv run ruff format comum/management/commands/suap_check.py comum/tests/test_suap_check_selecao.py && uv run ruff check comum/management/commands/suap_check.py comum/tests/test_suap_check_selecao.py --fix && uv run ruff check --select C901 --config 'lint.mccabe.max-complexity=10' comum/management/commands/suap_check.py`
Expected: a última linha reporta só `check_coverage is too complex (20 > 10)` (legado, não tocado); nenhuma função nova listada.

- [ ] **Step 6: Commit**

```bash
git add comum/management/commands/suap_check.py comum/tests/test_suap_check_selecao.py
git commit -m "[ci] Seleção de testes por módulo e dependentes diretos no suap_check"
```

---

### Task 2: Modos `django` e `e2e` do command

**Files:**
- Modify: `comum/management/commands/suap_check.py` (I/O fino após `distribuir_shards`; métodos novos na classe `Command`, depois de `test_behave`; ramo `django` do `handle`)
- Modify: `comum/tests/test_suap_check_selecao.py` (acrescentar testes ao final)

**Interfaces:**
- Consumes (Task 1): `candidatos_unitario`, `candidatos_e2e`, `motivo_fallback`, `modulos_afetados`, `distribuir_shards`.
- Produces:
  - funções de módulo `arquivos_versionados() -> list[str]`, `carregar_dependencias() -> dict[str, list[str]]`, `peso_e2e(modulo: str) -> int`
  - métodos `Command.selecionar(self, candidatos: set[str]) -> set[str]`, `Command.executar_django(self) -> None`, `Command.executar_e2e(self) -> None`, `Command.rodar_suite_e2e(self, modulo: str) -> bool`
  - contrato de ambiente usado pelo CI (Task 3): `SUAP_CHECK=django|e2e`; `SUAP_APPS=dependentes|geral|<caminhos separados por espaço>`; `CI_NODE_INDEX`/`CI_NODE_TOTAL` (1-based, ausentes = 1/1).

- [ ] **Step 1: Escrever os testes que falham**

Acrescentar ao final de `comum/tests/test_suap_check_selecao.py`:

```python
from comum.management.commands import suap_check  # noqa: E402

VERSIONADOS = [
    'compras/tests/test_compras.py',
    'materiais/tests/test_materiais.py',
    'edu/tests/test_edu.py',
    'edu/tests/e2e/test_edu_e2e.py',
    'erros/tests/e2e/test_erros_e2e.py',
    'ae/tests/e2e/test_ae_e2e.py',
    'tests/test_servidor_save.py',
]


@pytest.fixture
def executados(monkeypatch):
    """Troca o I/O do command por dados fixos e grava os comandos em vez de executá-los."""
    comandos = []
    monkeypatch.setattr(suap_check.Command, 'run_command', lambda self, cmd: comandos.append(cmd))
    monkeypatch.setattr(suap_check, 'arquivos_versionados', lambda: VERSIONADOS)
    monkeypatch.setattr(suap_check, 'carregar_dependencias', lambda: DEPENDENCIAS)
    monkeypatch.setattr(suap_check, 'peso_e2e', lambda modulo: {'edu': 10, 'erros': 3, 'ae': 2}[modulo])
    monkeypatch.delenv('CI_NODE_INDEX', raising=False)
    monkeypatch.delenv('CI_NODE_TOTAL', raising=False)
    return comandos


def test_django_dependentes_roda_modulo_e_dependentes(executados, monkeypatch):
    monkeypatch.setenv('SUAP_APPS', 'dependentes')
    monkeypatch.setattr(suap_check, 'get_changed_files', lambda: ['materiais/models.py'])

    suap_check.Command().executar_django()

    assert len(executados) == 1
    assert '-m "not e2e"' in executados[0]
    assert executados[0].endswith(' compras materiais')


def test_django_dependentes_sem_modulo_afetado_nao_chama_pytest(executados, monkeypatch):
    monkeypatch.setenv('SUAP_APPS', 'dependentes')
    monkeypatch.setattr(suap_check, 'get_changed_files', lambda: ['suap/settings_base.py', 'docs/x.md'])

    suap_check.Command().executar_django()

    assert executados == []


def test_django_geral_roda_todos_os_candidatos_sem_transversais(executados, monkeypatch):
    monkeypatch.setenv('SUAP_APPS', 'geral')

    suap_check.Command().executar_django()

    assert executados[0].endswith(' compras edu materiais')


def test_django_lista_literal_continua_como_antes(executados, monkeypatch):
    monkeypatch.setenv('SUAP_APPS', 'tests scripts')

    suap_check.Command().executar_django()

    assert executados[0].endswith(' tests scripts')


def test_e2e_geral_roda_so_as_suites_do_shard_com_cobertura(executados, monkeypatch):
    monkeypatch.setenv('SUAP_APPS', 'geral')
    monkeypatch.setenv('CI_NODE_TOTAL', '2')
    monkeypatch.setenv('CI_NODE_INDEX', '2')

    suap_check.Command().executar_e2e()

    assert [cmd.split('pytest ')[1].split()[0] for cmd in executados] == ['erros/tests/e2e', 'ae/tests/e2e']
    assert executados[0].startswith('COVERAGE_FILE=artifacts/.coverage.e2e-erros pytest ')
    assert '--cov=.' in executados[0]
    assert '--output=artifacts/e2e-erros' in executados[0]


def test_e2e_dependentes_roda_sem_cobertura(executados, monkeypatch):
    monkeypatch.setenv('SUAP_APPS', 'dependentes')
    monkeypatch.setattr(suap_check, 'get_changed_files', lambda: ['demandas/models.py'])

    suap_check.Command().executar_e2e()

    assert len(executados) == 1
    assert executados[0].startswith('pytest erros/tests/e2e -m e2e ')
    assert '--cov' not in executados[0]


def test_e2e_shard_vazio_sai_sem_rodar(executados, monkeypatch):
    monkeypatch.setenv('SUAP_APPS', 'dependentes')
    monkeypatch.setenv('CI_NODE_TOTAL', '3')
    monkeypatch.setenv('CI_NODE_INDEX', '3')
    monkeypatch.setattr(suap_check, 'get_changed_files', lambda: ['demandas/models.py'])

    suap_check.Command().executar_e2e()

    assert executados == []


def test_e2e_suite_vermelha_nao_interrompe_as_demais(executados, monkeypatch):
    monkeypatch.setenv('SUAP_APPS', 'geral')
    monkeypatch.setenv('CI_NODE_TOTAL', '2')
    monkeypatch.setenv('CI_NODE_INDEX', '2')

    def run_command(self, cmd):
        executados.append(cmd)
        if 'erros/tests/e2e' in cmd:
            raise Exception('falhou')

    monkeypatch.setattr(suap_check.Command, 'run_command', run_command)

    with pytest.raises(Exception, match='erros'):
        suap_check.Command().executar_e2e()

    assert len(executados) == 2


def test_peso_e2e_conta_testes_da_suite(tmp_path, monkeypatch):
    suite = tmp_path / 'edu' / 'tests' / 'e2e'
    suite.mkdir(parents=True)
    (suite / 'test_a.py').write_text('def test_um():\n    pass\n\n\ndef test_dois():\n    pass\n')
    (suite / 'test_b.py').write_text('async def test_tres():\n    pass\n')
    (suite / 'conftest.py').write_text('def test_nao_conta():\n    pass\n')
    monkeypatch.chdir(tmp_path)

    assert suap_check.peso_e2e('edu') == 3
```

Mover o `from comum.management.commands import suap_check` para junto dos outros imports no topo do arquivo (e remover o `# noqa`) — o ruff reordena; ele fica aqui só para o passo ser colável.

- [ ] **Step 2: Rodar e ver falhar**

Run: `DATABASE_PORT=5433 DATABASE_USER=postgres DATABASE_PASSWORD=postgres DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest -q comum/tests/test_suap_check_selecao.py`
Expected: os 9 testes novos falham (`AttributeError: ... has no attribute 'arquivos_versionados'` no fixture / `'Command' object has no attribute 'executar_django'`); os 29 da Task 1 passam.

- [ ] **Step 3: Implementar o I/O fino**

Em `suap_check.py`, logo após `distribuir_shards`:

```python
def arquivos_versionados() -> list[str]:
    """Arquivos rastreados pelo git (ignora .venv, artefatos e afins)."""
    return subprocess.run(['git', 'ls-files'], capture_output=True, text=True, check=True).stdout.splitlines()


def carregar_dependencias() -> dict[str, list[str]]:
    with open('module_dependencies.json') as arquivo:
        return json.load(arquivo)


def peso_e2e(modulo: str) -> int:
    """Número de testes da suíte e2e do módulo — proxy de duração para distribuir os shards."""
    total = 0
    for caminho in glob.glob(f'{modulo}/tests/e2e/test_*.py'):
        with open(caminho) as arquivo:
            total += arquivo.read().count('def test_')
    return total
```

- [ ] **Step 4: Implementar os métodos da classe**

Em `class Command`, logo depois do método `test_behave`:

```python
    def selecionar(self, candidatos: set[str]) -> set[str]:
        """Aplica ``SUAP_APPS`` (``geral`` = todos; qualquer outro = recorte por dependência) e registra o motivo."""
        if os.environ.get('SUAP_APPS') == 'geral':
            return set(candidatos)
        arquivos = get_changed_files()
        motivo = motivo_fallback(arquivos)
        if motivo:
            self.print_success(f'>>> Fallback (todos os candidatos) por causa de: {motivo}')
        selecionados = modulos_afetados(arquivos, carregar_dependencias(), candidatos)
        self.print_success(f'>>> Selecionados: {", ".join(sorted(selecionados)) or "nenhum"}')
        return selecionados

    def executar_django(self) -> None:
        """``SUAP_CHECK=django``: ``dependentes``/``geral`` calculam os módulos; outro valor é lista literal de caminhos."""
        suap_apps = os.environ['SUAP_APPS']
        if suap_apps not in ('dependentes', 'geral'):
            self.test_django(suap_apps)
            return
        selecionados = self.selecionar(candidatos_unitario(arquivos_versionados()))
        if not selecionados:
            self.print_success('>>> Nenhum módulo com testes afetado.')
            return
        self.test_django(' '.join(sorted(selecionados)))

    def executar_e2e(self) -> None:
        """``SUAP_CHECK=e2e``: seleciona as suítes, distribui entre os shards do job e roda as deste shard."""
        selecionados = self.selecionar(candidatos_e2e(arquivos_versionados()))
        pesos = {modulo: peso_e2e(modulo) for modulo in selecionados}
        total = int(os.environ.get('CI_NODE_TOTAL', '1'))
        indice = int(os.environ.get('CI_NODE_INDEX', '1'))
        shards = distribuir_shards(pesos, total)
        for numero, suites in enumerate(shards, start=1):
            self.print_success(f'>>> Shard {numero}/{total}: {", ".join(f"{s} ({pesos[s]})" for s in suites) or "vazio"}')
        if not shards[indice - 1]:
            self.print_success('>>> Nenhuma suíte e2e neste shard.')
            return
        vermelhas = [modulo for modulo in shards[indice - 1] if not self.rodar_suite_e2e(modulo)]
        if vermelhas:
            raise Exception(f'Suítes e2e com falha: {", ".join(vermelhas)}')

    def rodar_suite_e2e(self, modulo: str) -> bool:
        """Uma invocação de pytest por suíte, isolada como no job por módulo antigo. Cobertura só no ``geral``."""
        cmd = f'pytest {modulo}/tests/e2e -m e2e --tracing=retain-on-failure --video=retain-on-failure --output=artifacts/e2e-{modulo}'
        if os.environ.get('SUAP_APPS') == 'geral':
            cmd = f'COVERAGE_FILE=artifacts/.coverage.e2e-{modulo} {cmd} --cov=. --cov-report='
        self.print_success(f'>>> e2e de {modulo} com "{cmd}"...')
        try:
            self.run_command(cmd)
        except Exception:
            return False
        return True
```

- [ ] **Step 5: Despachar no `handle`**

Em `Command.handle`, trocar:

```python
            elif os.environ.get('SUAP_CHECK') == 'django':
                if os.environ['SUAP_APPS'] == 'geral':
                    self.test_django()
                else:
                    self.test_django(os.environ['SUAP_APPS'])
```

por:

```python
            elif os.environ.get('SUAP_CHECK') == 'django':
                self.executar_django()
            elif os.environ.get('SUAP_CHECK') == 'e2e':
                self.executar_e2e()
```

(O `if` interno sai e um `elif` entra: `handle` continua em complexidade 10.)

- [ ] **Step 6: Rodar e ver passar**

Run: `DATABASE_PORT=5433 DATABASE_USER=postgres DATABASE_PASSWORD=postgres DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest -q comum/tests/test_suap_check_selecao.py`
Expected: `38 passed`.

- [ ] **Step 7: Conferir a seleção real do repo (sem rodar testes)**

Run:
```bash
DATABASE_PORT=5433 DATABASE_USER=postgres DATABASE_PASSWORD=postgres DJANGO_SETTINGS_MODULE=suap.settings_test uv run python manage.py shell -c "
from comum.management.commands.suap_check import candidatos_unitario, candidatos_e2e, arquivos_versionados, carregar_dependencias, modulos_afetados, distribuir_shards, peso_e2e
v = arquivos_versionados(); c = candidatos_unitario(v); e = candidatos_e2e(v); d = carregar_dependencias()
print(len(c), sorted(e))
print(sorted(modulos_afetados(['demandas/models.py'], d, c)), sorted(modulos_afetados(['demandas/models.py'], d, e)))
print(sorted(modulos_afetados(['materiais/models.py'], d, c)))
print(distribuir_shards({m: peso_e2e(m) for m in e}, 3))
" 2>&1 | tail -4
```
Expected (medido em 2026-09-14 replicando a lógica):
```
54 ['ae', 'almoxarifado', 'documento_eletronico', 'edu', 'erros', 'eventos', 'processo_eletronico', 'remanejamento']
['demandas', 'erros'] ['erros']
[]
[['edu'], ['almoxarifado', 'erros', 'ae', 'eventos'], ['remanejamento', 'processo_eletronico', 'documento_eletronico']]
```
(`materiais` → `[]` porque nem `materiais` nem `compras` têm arquivo de teste hoje.) Se `master` tiver ganho testes desde então, os números podem mudar; o formato não.

- [ ] **Step 8: Lint e complexidade**

Run: `uv run ruff format comum/management/commands/suap_check.py comum/tests/test_suap_check_selecao.py && uv run ruff check comum/management/commands/suap_check.py comum/tests/test_suap_check_selecao.py --fix && uv run ruff check --select C901 --config 'lint.mccabe.max-complexity=10' comum/management/commands/suap_check.py`
Expected: só `check_coverage is too complex (20 > 10)`.

- [ ] **Step 9: Commit**

```bash
git add comum/management/commands/suap_check.py comum/tests/test_suap_check_selecao.py
git commit -m "[ci] Modos django e e2e do suap_check com recorte por dependência e shards"
```

---

### Task 3: `.gitlab-ci.yml`

**Files:**
- Modify: `.gitlab-ci.yml` — comentário do stage `coverage` (~l.19-20), `django-geral` (~l.103-124), cabeçalho e variáveis/script da `.e2e-base` (~l.186-235), `e2e-transversal` (~l.236-248), `e2e-modulo` (~l.250-282), `cobertura-combinada` (~l.284-340), `build-opencode-image` e `build-test-image` (`rules`, ~l.783-825).

**Interfaces:**
- Consumes (Task 2): `SUAP_CHECK=django|e2e`, `SUAP_APPS=dependentes|geral|tests scripts`, `CI_NODE_INDEX`/`CI_NODE_TOTAL` (o GitLab define em jobs com `parallel`).
- Produces: jobs `unitario-transversal`, `unitario-modulo`, `e2e-transversal`, `e2e-modulo` (3 instâncias `e2e-modulo 1/3..3/3`), `cobertura-combinada` só no schedule.

- [ ] **Step 1: Comentário do stage `coverage`**

Trocar:
```yaml
  # `coverage` soma os dados das duas suítes: a unitária escreve o arquivo no `django-geral`
  # e o e2e no seu próprio job — ambos no stage `test`, em paralelo.
  - coverage
```
por:
```yaml
  # `coverage` soma os dados das suítes unitária e e2e — só no pipeline agendado (noturno), que
  # roda tudo; em MR os testes são recortados e um total combinado mediria só o que rodou.
  - coverage
```

- [ ] **Step 2: Substituir `django-geral` pelos dois jobs unitários**

Trocar o bloco inteiro que começa em `django-geral:` e termina antes de `behave-changed:` por:

```yaml
# Suíte unitária em dois jobs, no mesmo desenho do e2e:
#
# - `unitario-transversal` roda SEMPRE: `tests/` e `scripts/`, que não pertencem a módulo.
# - `unitario-modulo` roda só o que o MR pode quebrar: os módulos tocados e os que dependem
#   DIRETAMENTE deles em `module_dependencies.json` (invertido). Quem decide é o `suap_check`
#   (SUAP_APPS=dependentes); arquivo em djtools/, comum/, rh/ ou o conftest.py da raiz roda todos.
#   Um job só, e não matriz: os 3 runners de teste já enfileiram, e ~55 jobs multiplicariam
#   preparo + schema.
#
# No pipeline agendado (noturno) os dois rodam completos. Ver
# docs/superpowers/specs/2026-09-14-ci-testes-por-dependencia-design.md.
unitario-transversal:
  extends: .test-base
  stage: test
  services:
    - *postgres-service
  variables:
    SUAP_CHECK: django
    SUAP_APPS: tests scripts
    # Arquivo próprio: sem ele grava `artifacts/.coverage`, o mesmo do `unitario-modulo`, e no
    # `cobertura-combinada` um artefato sobrescreveria o outro.
    COVERAGE_FILE: artifacts/.coverage.unitario-transversal
  rules:
    - if: $CI_PIPELINE_SOURCE == 'merge_request_event'
      when: on_success
    - if: $CI_PIPELINE_SOURCE == 'schedule'
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

unitario-modulo:
  extends: .test-base
  stage: test
  services:
    - *postgres-service
  variables:
    SUAP_CHECK: django
  rules:
    - if: $CI_PIPELINE_SOURCE == 'merge_request_event'
      variables:
        SUAP_APPS: dependentes
      when: on_success
    - if: $CI_PIPELINE_SOURCE == 'schedule'
      variables:
        SUAP_APPS: geral
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

- [ ] **Step 3: Cabeçalho e cobertura da `.e2e-base`**

Trocar o comentário que vai de `# Suíte e2e (pytest + Playwright), independente do behave.` até `# Ver tests/e2e/conftest.py.` por:

```yaml
# Suíte e2e (pytest + Playwright), independente do behave, no mesmo desenho do unitário:
# `e2e-transversal` roda sempre; `e2e-modulo` roda só as suítes `<modulo>/tests/e2e/` que o MR
# pode quebrar, escolhidas pelo `suap_check` com a mesma regra do `unitario-modulo`.
#
# Ver tests/e2e/conftest.py.
```

Na `.e2e-base`, trocar o comentário acima de `COVERAGE_FILE` (as 6 linhas de `# Arquivo de dados PRÓPRIO por job:` até `` # `e2e-modulo: [edu]`, com espaço e colchete, que não serve para nome de arquivo. ``) por:

```yaml
    # Arquivo de dados PRÓPRIO por job, para o `cobertura-combinada` (noturno) somar sem que um
    # artefato sobrescreva o outro. No `e2e-modulo` quem define o arquivo, por suíte, é o
    # `suap_check`.
```

E trocar o comentário acima do `pytest $E2E_ALVO ...` (de `` # `--cov` sem relatório: `` até `# exercitados pelo browser entram na conta, que é justamente o que o unitário não alcança.`) por:

```yaml
    # `--cov` sem relatório: o e2e só GRAVA os dados; quem emite o XML é o
    # `cobertura-combinada`, no noturno. Medir aqui vale porque o `live_server` roda o Django
    # numa thread do próprio processo — o que o browser exercita entra na conta.
```

- [ ] **Step 4: `e2e-transversal` ganha o schedule**

Trocar:
```yaml
e2e-transversal:
  extends: .e2e-base
  variables:
    E2E_ALVO: tests/e2e
    E2E_ROTULO: transversal
  rules:
    - if: $CI_PIPELINE_SOURCE == 'merge_request_event'
      when: on_success
```
por:
```yaml
e2e-transversal:
  extends: .e2e-base
  variables:
    E2E_ALVO: tests/e2e
    E2E_ROTULO: transversal
  rules:
    - if: $CI_PIPELINE_SOURCE == 'merge_request_event'
      when: on_success
    - if: $CI_PIPELINE_SOURCE == 'schedule'
      when: on_success
```

- [ ] **Step 5: `e2e-modulo` com `parallel: 3`**

Trocar o bloco inteiro, do comentário `# UM job para todos os módulos, expandido por` até a última linha de `rules:changes` (`        - conftest.py`), por:

```yaml
# e2e por módulo: 3 jobs fixos. O `suap_check` (SUAP_CHECK=e2e) escolhe as suítes
# `<modulo>/tests/e2e/` pela regra do `unitario-modulo`, distribui entre os 3 por peso (nº de
# testes; o `edu` fica sozinho) e cada job roda as suas — uma invocação de pytest por suíte. Não há
# lista de módulos aqui: suíte nova entra sozinha. Shard sem suíte sai verde em segundos, e o log de
# qualquer shard mostra a atribuição de todos. No noturno (SUAP_APPS=geral) roda tudo, com cobertura.
e2e-modulo:
  extends: .e2e-base
  parallel: 3
  variables:
    SUAP_CHECK: e2e
  script:
    # No-op na imagem de CI; mantido para a imagem não virar dependência oculta.
    - playwright install chromium
    - python manage.py suap_check
  rules:
    - if: $CI_PIPELINE_SOURCE == 'merge_request_event'
      variables:
        SUAP_APPS: dependentes
      when: on_success
    - if: $CI_PIPELINE_SOURCE == 'schedule'
      variables:
        SUAP_APPS: geral
      when: on_success
```

- [ ] **Step 6: `cobertura-combinada` só no noturno**

Trocar o bloco inteiro, do comentário `# Soma a cobertura das duas suítes.` até o fim do job (`        path: artifacts/coverage.xml`, antes do próximo job), por:

```yaml
# Soma a cobertura das suítes unitária e e2e. SÓ no pipeline agendado (noturno): em MR os testes são
# recortados por módulo, e um total combinado mediria só o que rodou. As anotações de linha no diff
# do MR continuam vindo do `coverage_report` dos jobs unitários.
cobertura-combinada:
  extends: .test-base
  stage: coverage
  # Sem `services`: não roda teste, só soma arquivos de dados já produzidos.
  # `needs` (e não `dependencies`): baixa os mesmos artefatos, mas dispara assim que as suítes
  # terminam. Um `needs` em `e2e-modulo` cobre os 3 jobs do `parallel`.
  needs:
    - unitario-modulo
    - unitario-transversal
    - e2e-transversal
    - e2e-modulo
  script:
    # Falha explícita se um dos lados não veio: combinar só um deles publicaria um número
    # menor como se fosse o total, que é pior que não publicar.
    - test -f artifacts/.coverage || { echo "❌ dados de cobertura do unitario-modulo ausentes"; exit 1; }
    - test -f artifacts/.coverage.unitario-transversal || { echo "❌ dados de cobertura do unitario-transversal ausentes"; exit 1; }
    - ls artifacts/.coverage.e2e-* >/dev/null 2>&1 || { echo "❌ nenhum dado de cobertura de e2e presente"; exit 1; }
    # Todos os arquivos vão para um diretório só, com nomes casando `<data_file>.*` — é esse
    # o padrão que `coverage combine <dir>` procura, derivado do `data_file` do
    # pyproject.toml (`artifacts/.coverage`). O resultado é escrito no próprio `data_file`.
    - mkdir -p artifacts/combinado
    - cp artifacts/.coverage artifacts/combinado/.coverage.unitario
    - cp artifacts/.coverage.unitario-transversal artifacts/combinado/
    - cp artifacts/.coverage.e2e-* artifacts/combinado/
    - coverage combine artifacts/combinado
    - coverage xml -o artifacts/coverage.xml
    - coverage report
  rules:
    - if: $CI_PIPELINE_SOURCE == 'schedule'
      when: on_success
  # Cobertura é informação, não portão.
  allow_failure: true
  coverage: '/TOTAL.*\s+(\d+\.\d+)%/'
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

- [ ] **Step 7: Builds de imagem fora do schedule**

Em `build-opencode-image` **e** em `build-test-image`, inserir como primeira entrada de `rules:` (antes do comentário `# manual tem prioridade`):

```yaml
    # `changes` vale sempre true em pipeline agendado: sem isto o noturno rebuildaria a imagem.
    - if: $CI_PIPELINE_SOURCE == 'schedule'
      when: never
```

- [ ] **Step 8: Nenhuma referência ao nome antigo**

Run: `git grep -n "django-geral\|MODULO\|E2E_GATILHOS" .gitlab-ci.yml`
Expected: nenhuma linha.

- [ ] **Step 9: Validar sintaxe**

Run: `uv run --quiet python -c "import yaml; d = yaml.safe_load(open('.gitlab-ci.yml')); print(sorted(k for k in d if k.startswith(('unitario', 'e2e', 'cobertura'))), d['e2e-modulo']['parallel'])"`
Expected: `['cobertura-combinada', 'e2e-modulo', 'e2e-transversal', 'unitario-modulo', 'unitario-transversal'] 3`

Run: `glab ci lint .gitlab-ci.yml`
Expected: `✓ CI/CD YAML is valid!` (valida pela API do GitLab do projeto, sem criar pipeline).

- [ ] **Step 10: Commit**

```bash
git add .gitlab-ci.yml
git commit -m "[ci] Jobs unitario-transversal/unitario-modulo, e2e-modulo por shards e suíte completa no noturno"
```

---

### Task 4: Documentação

**Files:**
- Modify: `bin/ci/README.md` (l.62 e l.178)
- Modify: `AGENTS.md` (linha do `suap_check` em `## Commands` e entrada `e2e-tester` em `## Subagents`)
- Modify: `.claude/agents/e2e-tester.md` (passo 10 e item 2 do relatório)
- Modify: `.opencode/agent/e2e-tester.md` (mesmos trechos)

**Interfaces:**
- Consumes: nomes de jobs da Task 3; comportamento do `SUAP_CHECK=e2e` da Task 2.
- Produces: nada consumido por código.

- [ ] **Step 1: `bin/ci/README.md`**

Na linha 62, trocar `` `checagem-codigo`, `django-geral`, `coverage`, `` por `` `checagem-codigo`, `unitario-transversal`, `unitario-modulo`, `cobertura-combinada`, ``.
Na linha 178, trocar `` `checagem-codigo`/`django-geral`/`coverage` `` por `` `checagem-codigo`/`unitario-transversal`/`unitario-modulo` ``.

- [ ] **Step 2: `AGENTS.md`**

Em `## Commands`, trocar:
```
- `python manage.py suap_check` — full check; modes via `SUAP_CHECK=code|django|behave|behave-changed|coverage` (default runs all). Changed-file logic compares against `origin/master` (`git diff --name-only origin/master..`).
```
por:
```
- `python manage.py suap_check` — full check; modes via `SUAP_CHECK=code|django|e2e|behave|behave-changed|coverage` (default runs all). Changed-file logic compares against `origin/master` (`git diff --name-only origin/master..`). `SUAP_CHECK=django|e2e` with `SUAP_APPS=dependentes` runs only the modules touched plus their **direct** dependents in `module_dependencies.json` (inverted); files in `djtools/`, `comum/`, `rh/` or the root `conftest.py` run everything; `SUAP_APPS=geral` runs everything. `e2e` splits the selected suites across `CI_NODE_INDEX/CI_NODE_TOTAL`. MR jobs: `unitario-transversal`, `unitario-modulo`, `e2e-transversal`, `e2e-modulo` (3 shards); the full run and `cobertura-combinada` happen only in the nightly scheduled pipeline.
```

Na entrada `e2e-tester`, trocar:
```
Also registers the module in the `e2e-modulo` matrix of `.gitlab-ci.yml` (one word in the `MODULO` list) when it isn't there yet — without it the new suite never runs on any MR.
```
por:
```
No CI registration: the `e2e-modulo` job discovers every `<modulo>/tests/e2e/` suite and runs it when the MR touches the module or one of its direct dependencies in `module_dependencies.json`.
```

- [ ] **Step 3: `.claude/agents/e2e-tester.md`**

Trocar o passo 10 inteiro (de `**10. Registrar o módulo no CI.**` até `já estiver na matriz, não mexa no arquivo — e diga isso no relatório.`) por:

~~~markdown
**10. CI — nada a registrar.** O job `e2e-modulo` descobre sozinho toda suíte em
`<modulo>/tests/e2e/` (`suap_check`, `SUAP_CHECK=e2e`) e a roda quando o MR toca o módulo ou algo de
que ele depende diretamente em `module_dependencies.json`. **Não mexa no `.gitlab-ci.yml`** para
acrescentar o módulo. Para conferir que a suíte será vista:

```bash
uv run python -c "from comum.management.commands.suap_check import candidatos_e2e, arquivos_versionados; print(sorted(candidatos_e2e(arquivos_versionados())))"
```
~~~

No relatório final, apagar as duas linhas:
```
   Inclui o `.gitlab-ci.yml`: diga se você acrescentou o módulo à matriz `e2e-modulo` ou se ele
   já estava lá.
```

- [ ] **Step 4: `.opencode/agent/e2e-tester.md`**

Aplicar exatamente as mesmas duas substituições do Step 3 (o texto é idêntico: passo 10 em ~l.130-141 e as duas linhas do relatório em ~l.242-243).

- [ ] **Step 5: Conferir**

Run: `git grep -n "django-geral\|matriz .e2e-modulo\|MODULO. list\|lista .MODULO" -- AGENTS.md bin/ci/README.md .claude/agents/e2e-tester.md .opencode/agent/e2e-tester.md`
Expected: nenhuma linha.

- [ ] **Step 6: Commit**

```bash
git add bin/ci/README.md AGENTS.md .claude/agents/e2e-tester.md .opencode/agent/e2e-tester.md
git commit -m "[ci] Documenta seleção por dependência e fim do registro de e2e na matriz"
```

---

### Task 5: Validação no GitLab (requer ok do usuário)

**Files:** nenhum no branch principal.

**Interfaces:**
- Consumes: Tasks 1–4 publicadas no branch.
- Produces: evidência (IDs de pipeline e jobs) para a descrição do MR.

Cada passo com push, MR ou schedule **só depois de ok explícito do usuário** no chat.

- [ ] **Step 1: Pre-commit como no CI**

Run: `git fetch -q origin master && uv run pre-commit run --from-ref origin/master --to-ref HEAD`
Expected: todos `Passed` (ou `Skipped`).

- [ ] **Step 2: Push e MR (com ok)**

```bash
git push -u origin claude/django-job-performance-deps-597ee6
glab mr create --title "[ci] Testes recortados por módulo e dependência" --fill --yes
```
Rodar `glab mr create` direto no Bash (o hook de time spent lê a URL da saída).
Expected no pipeline do MR: toca `comum/` → fallback. Jobs `unitario-transversal`, `unitario-modulo` (log com `Fallback (todos os candidatos) por causa de: comum/...`), `e2e-transversal`, `e2e-modulo 1/3..3/3` (log com a atribuição; `edu` sozinho), sem `cobertura-combinada`. Tudo verde.

Conferir com:
```bash
glab api "projects/cosinf%2Fsuap/pipelines/<ID>/jobs?per_page=100" | uv run python -c "import json,sys; [print(j['name'], j['status']) for j in json.load(sys.stdin)]"
```

- [ ] **Step 3: Branch descartável — só `demandas/` (com ok, APÓS o merge do MR da feature)**

Antes do merge não há como provar o recorte: o job faz `git diff origin/master..`, e todo branch
com o command novo carrega a mudança em `comum/` (fallback). Depois do merge, a partir de `master`:

```bash
git fetch -q origin master
git switch -c tmp/ci-recorte-demandas origin/master
printf '\n' >> demandas/__init__.py
git commit -am "[tmp] valida recorte demandas"
git push -u origin tmp/ci-recorte-demandas
glab mr create --title "[tmp] valida recorte demandas" --description "Descartável, fechar sem merge." --target-branch master --yes
```
Expected: `unitario-modulo` loga `Selecionados: demandas, erros` e roda `pytest ... demandas erros`; `e2e-modulo` loga `Shard 1/3: erros (20)` e roda só `erros` no job `e2e-modulo 1/3`; os outros dois dizem `Nenhuma suíte e2e neste shard.`; transversais rodam; `cobertura-combinada` não aparece.

- [ ] **Step 4: Branch descartável — só `suap/settings_base.py` (com ok, após o merge)**

```bash
git switch -c tmp/ci-recorte-suap origin/master
printf '\n' >> suap/settings_base.py
git commit -am "[tmp] valida recorte suap"
git push -u origin tmp/ci-recorte-suap
glab mr create --title "[tmp] valida recorte suap" --description "Descartável, fechar sem merge." --target-branch master --yes
```
Expected: `unitario-modulo` imprime `Nenhum módulo com testes afetado.`; os 3 shards de `e2e-modulo` imprimem `Nenhuma suíte e2e neste shard.`; transversais rodam.

- [ ] **Step 4b: Branch descartável — só `gestao/` (com ok, após o merge)**

`gestao` é candidato pelo nome dos arquivos, mas não coleta teste nenhum (classes `*Tests`); prova o
caminho do exit 5 aceito (revisão final, achado C1).

```bash
git switch -c tmp/ci-recorte-gestao origin/master
printf '\n' >> gestao/__init__.py
git commit -am "[tmp] valida recorte gestao"
git push -u origin tmp/ci-recorte-gestao
glab mr create --title "[tmp] valida recorte gestao" --description "Descartável, fechar sem merge." --target-branch master --yes
```
Expected: `unitario-modulo` loga `Selecionados: gestao` (mais dependentes com testes, se houver), o pytest termina com "no tests ran" e o job fica **verde**.

- [ ] **Step 5: Schedule noturno (com ok, após o merge)**

```bash
glab api -X POST "projects/cosinf%2Fsuap/pipeline_schedules" -f description="Suíte completa noturna" -f ref=master -f cron="0 2 * * *" -f cron_timezone="America/Fortaleza" -f active=true
glab api -X POST "projects/cosinf%2Fsuap/pipeline_schedules/<SCHEDULE_ID>/play"
```
Expected: pipeline com `unitario-transversal`, `unitario-modulo` (`SUAP_APPS=geral`), `e2e-transversal`, `e2e-modulo 1/3..3/3`, `cobertura-combinada` publicando `TOTAL`; **sem** `build-test-image`/`build-opencode-image`.

- [ ] **Step 6: Limpeza**

Fechar os MRs descartáveis sem merge e apagar os branches `tmp/ci-recorte-*` (local e remoto) — com ok do usuário, pois apagar branch remoto não se desfaz.
