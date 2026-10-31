# Banco mockado do SUAP (`gerar_banco_mock`) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `manage.py gerar_banco_mock` gera um arquivo `pg_dump -Fc` de um banco SUAP inteiro com dados fictícios: substrato dos seeds e2e + volume sintético (model-bakery) em todos os models, senha `123` para todos os usuários.

**Architecture:** O command é um orquestrador: roda cada etapa que escreve num processo filho sob `suap.settings_test` apontado para `test_suap_mock_e2e` — (1) `pytest -m mock` sobre stubs por módulo que só pedem as fixtures de seed de sessão do e2e, (2) `gerar_banco_mock --etapa volume` (bakery + senhas), (3) `migrate --fake`, (4) `pg_dump`, (5) drop. A lógica de volume/senhas mora em `djtools/banco_mock.py`, testável sem o orquestrador.

**Tech Stack:** Django 5.2, pytest + pytest-django (`--no-migrations`), model-bakery 1.20.5, factory-boy, psycopg 3, PostgreSQL 18 (`pg_dump` 18).

**Spec:** `docs/superpowers/specs/2026-09-19-banco-mock-design.md`

## Global Constraints

- Idioma: identificadores, docstrings, comentários, mensagens de commit em pt-BR. Commit no formato `[djtools] Descrição` (ou `[<modulo>]` quando só toca o módulo).
- Ruff: linha 150, aspas simples. Pre-commit roda no commit; não use `--no-verify`.
- Complexidade ciclomática (ruff C901) ≤ 10 por função tocada — o hook `.claude/hooks/check_complexity.py` bloqueia a edição se passar.
- Tipagem progressiva: anote parâmetros e retorno de toda def nova/tocada. `from __future__ import annotations`; `X | None`, não `Optional`.
- Testes: pytest, **com factories** (factory-boy), **sem** `suap_data`/`light_data`.
- Banco mockado: nome exato `test_suap_mock_e2e`; sufixo de guarda `_mock_e2e`.
- Senha de todos os usuários no dump: `123`, hash **PBKDF2** (`PBKDF2PasswordHasher`), nunca o MD5 do `settings_test`.
- Processos filhos recebem sempre `DJANGO_SETTINGS_MODULE=suap.settings_test` e `EMAIL_BACKEND=django.core.mail.backends.locmem.EmailBackend`.
- Defaults do command: `--saida suap_mock.dump`, `--volume 20`, `--semente 0`.

**Ambiente para rodar testes** (o `.env` do checkout principal aponta `DATABASE_HOST=db`, que não resolve fora do Docker; o Postgres de teste é o container `suap-test-db` na porta 5433). Todo comando de teste abaixo usa este prefixo, aqui abreviado como `$T`:

```bash
export T="DATABASE_HOST=localhost DATABASE_PORT=5433 DATABASE_USER=postgres DATABASE_PASSWORD=postgres DJANGO_SETTINGS_MODULE=suap.settings_test"
```

Na primeira execução de testes com banco use `--create-db` (cria `test_suap` do zero, alguns minutos); depois `--reuse-db`.

---

## File Structure

| Arquivo | Ação | Responsabilidade |
|---|---|---|
| `djtools/banco_mock.py` | Create | Seleção e ordenação de models, geradores do bakery, volume, relatório, senhas, guarda do banco |
| `djtools/management/commands/gerar_banco_mock.py` | Create | Orquestração das etapas em processos filhos; `--etapa volume` |
| `djtools/tests/test_banco_mock.py` | Create | Testes de `banco_mock` (factories) |
| `djtools/tests/test_gerar_banco_mock.py` | Create | Testes da orquestração (`subprocess.run` via monkeypatch) |
| `comum/tests/factories.py` | Modify | `UserFactory` |
| `conftest.py` (raiz) | Modify | `_deselecionar_mock` chamado no `pytest_collection_modifyitems` |
| `pyproject.toml` | Modify | Registrar marker `mock` |
| `<modulo>/tests/e2e/test_mock.py` × 12 | Create | Stubs que pedem os seeds de sessão |
| `docs/banco-mock.md` | Create | Guia do dev |
| `AGENTS.md` | Modify | Uma linha em `## Commands` |

---

### Task 1: Ordenação de models por FK obrigatória

**Files:**
- Create: `djtools/banco_mock.py`
- Test: `djtools/tests/test_banco_mock.py`

**Interfaces:**
- Produces:
  - `fks_obrigatorias(modelo: type[models.Model]) -> list[models.Field]` — FK/O2O não nulas, sem default, exceto `parent_link`.
  - `ordenar(grafo: Mapping[str, Iterable[str]]) -> list[str]` — Kahn; nós presos em ciclo vão ao fim em ordem alfabética.
  - `ordenar_modelos(modelos: Iterable[type[models.Model]]) -> list[type[models.Model]]`.

- [ ] **Step 1: Write the failing tests**

`djtools/tests/test_banco_mock.py`:

```python
"""Testes do volume sintético e das senhas do banco mockado (``djtools/banco_mock.py``)."""

from __future__ import annotations

from auditoria.models import Acao, TipoServico
from rh.models import PessoaFisica

from djtools.banco_mock import fks_obrigatorias, ordenar, ordenar_modelos


def test_ordenar_pai_antes_do_filho_e_ciclo_no_fim():
    grafo = {
        'filho': {'pai'},
        'pai': set(),
        'a': {'b'},
        'b': {'a'},
        'orfao': {'fora_do_grafo'},
        'eu': {'eu'},
    }
    assert ordenar(grafo) == ['eu', 'orfao', 'pai', 'filho', 'a', 'b']


def test_fks_obrigatorias_de_acao():
    assert [campo.name for campo in fks_obrigatorias(Acao)] == ['tipo_servico']


def test_fks_obrigatorias_ignora_parent_link():
    assert PessoaFisica._meta.parents  # herança multi-tabela (pessoa_ptr)
    assert not any(campo.remote_field.parent_link for campo in fks_obrigatorias(PessoaFisica))


def test_ordenar_modelos_pai_primeiro():
    assert ordenar_modelos([Acao, TipoServico]) == [TipoServico, Acao]
```

- [ ] **Step 2: Run to verify it fails**

Run: `env $T uv run pytest djtools/tests/test_banco_mock.py -q --create-db`
Expected: FAIL — `ModuleNotFoundError: No module named 'djtools.banco_mock'`.

- [ ] **Step 3: Write minimal implementation**

`djtools/banco_mock.py`:

```python
"""Volume sintético e senhas do banco mockado gerado por ``manage.py gerar_banco_mock``.

Tudo aqui roda num processo filho sob ``suap.settings_test`` apontado para
``test_suap_mock_e2e`` (ver o command). ``exigir_banco_mock`` é a guarda que impede rodar
contra qualquer outro banco.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from django.db import models


def fks_obrigatorias(modelo: type[models.Model]) -> list[models.Field]:
    """FK/O2O que precisam de valor no INSERT.

    O ``parent_link`` de herança multi-tabela fica de fora: reusar uma linha-pai existente
    colaria dois filhos no mesmo pai; o bakery cria o pai.
    """
    return [
        campo
        for campo in modelo._meta.concrete_fields
        if campo.is_relation and not campo.null and not campo.has_default() and not campo.remote_field.parent_link
    ]


def ordenar(grafo: Mapping[str, Iterable[str]]) -> list[str]:
    """Kahn: cada nó depois das suas dependências.

    ``graphlib`` levanta ``CycleError`` em qualquer ciclo; aqui o que fica preso em ciclo
    (e quem depende dele) vai para o fim, em ordem alfabética. Dependência fora do grafo e
    auto-referência são ignoradas.
    """
    pendentes = {no: set(deps) & (grafo.keys() - {no}) for no, deps in grafo.items()}
    ordem: list[str] = []
    while prontos := sorted(no for no, deps in pendentes.items() if not deps):
        ordem.extend(prontos)
        for no in prontos:
            del pendentes[no]
        for deps in pendentes.values():
            deps.difference_update(prontos)
    return ordem + sorted(pendentes)


def ordenar_modelos(modelos: Iterable[type[models.Model]]) -> list[type[models.Model]]:
    """Models em ordem de criação: pai (alvo de FK obrigatória) antes do filho."""
    por_label = {modelo._meta.label: modelo for modelo in modelos}
    grafo = {label: {campo.related_model._meta.label for campo in fks_obrigatorias(modelo)} for label, modelo in por_label.items()}
    return [por_label[label] for label in ordenar(grafo)]
```

- [ ] **Step 4: Run to verify it passes**

Run: `env $T uv run pytest djtools/tests/test_banco_mock.py -q --reuse-db`
Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add djtools/banco_mock.py djtools/tests/test_banco_mock.py
git commit -m "[djtools] Ordenação de models por FK obrigatória para o banco mockado"
```

---

### Task 2: Volume sintético com bakery

**Files:**
- Modify: `djtools/banco_mock.py`
- Test: `djtools/tests/test_banco_mock.py`

**Interfaces:**
- Consumes: `fks_obrigatorias`, `ordenar_modelos` (Task 1).
- Produces:
  - `EXCLUIDOS: frozenset[str]` — labels fora do volume.
  - `@dataclass class Resultado: modelo: str; criados: int = 0; erro: str = ''`.
  - `modelos_do_suap() -> list[type[models.Model]]`.
  - `registrar_geradores(modelos: Iterable[type[models.Model]]) -> None`.
  - `gerar_volume(modelos: Iterable[type[models.Model]], n: int, semente: int = 0) -> list[Resultado]` — na ordem de `ordenar_modelos`.
  - `formatar_relatorio(resultados: list[Resultado], n: int) -> str`.

- [ ] **Step 1: Write the failing tests** (acrescentar a `djtools/tests/test_banco_mock.py`)

Imports novos no topo do arquivo (juntar aos existentes):

```python
import pytest
from auditoria.tests.factories import TipoServicoFactory
from django.db import models as django_models
from model_bakery import generators

from djtools.banco_mock import Resultado, formatar_relatorio, gerar_volume, modelos_do_suap, registrar_geradores
from djtools.db.models.fields.string import CharFieldPlus
```

Testes:

```python
def test_modelos_do_suap_filtra_excluidos_proxy_e_nao_gerenciados():
    modelos = modelos_do_suap()
    labels = {modelo._meta.label for modelo in modelos}
    assert 'auditoria.Acao' in labels
    assert 'comum.Configuracao' not in labels
    assert not any(modelo._meta.proxy or not modelo._meta.managed for modelo in modelos)


def test_registrar_geradores_herda_do_ancestral():
    registrar_geradores(modelos_do_suap())
    assert generators.get(CharFieldPlus) is generators.get_type_mapping()[django_models.CharField]


@pytest.mark.django_db
def test_fk_obrigatoria_reusa_linha_existente():
    tipos = TipoServicoFactory.create_batch(3)
    assert gerar_volume([Acao], n=5) == [Resultado('auditoria.Acao', criados=5)]
    assert TipoServico.objects.count() == 3
    assert set(Acao.objects.values_list('tipo_servico', flat=True)) <= {tipo.pk for tipo in tipos}


@pytest.mark.django_db
def test_alvo_vazio_bakery_cria_o_pai():
    assert gerar_volume([Acao], n=1) == [Resultado('auditoria.Acao', criados=1)]
    assert TipoServico.objects.count() == 1


@pytest.mark.django_db
def test_falha_de_um_model_vai_para_o_relatorio_e_os_demais_seguem(monkeypatch):
    TipoServicoFactory()

    def explodir(self, *args, **kwargs):
        raise ValueError('boom')

    monkeypatch.setattr(TipoServico, 'save', explodir)
    assert gerar_volume([Acao, TipoServico], n=2) == [
        Resultado('auditoria.TipoServico', criados=0, erro='ValueError: boom'),
        Resultado('auditoria.Acao', criados=2),
    ]


def test_formatar_relatorio_falhas_primeiro():
    texto = formatar_relatorio([Resultado('a.Ok', 2), Resultado('b.Falha', 0, 'ValueError: x')], n=2)
    linhas = texto.splitlines()
    assert linhas[0].startswith('b.Falha') and linhas[0].endswith('ValueError: x')
    assert linhas[1].startswith('a.Ok')
    assert linhas[-1] == '1/2 models sem falha; 1 com falha.'
```

- [ ] **Step 2: Run to verify it fails**

Run: `env $T uv run pytest djtools/tests/test_banco_mock.py -q --reuse-db`
Expected: FAIL — `ImportError: cannot import name 'Resultado' from 'djtools.banco_mock'`.

- [ ] **Step 3: Write minimal implementation** (acrescentar a `djtools/banco_mock.py`)

Imports (substituir o bloco de imports do módulo):

```python
from __future__ import annotations

import random
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from django.apps import apps
from django.conf import settings
from django.db import models, router, transaction
from model_bakery import baker, generators
```

Código (depois de `ordenar_modelos`):

```python
# Labels fora do volume sintético, cada um com o motivo.
EXCLUIDOS = frozenset(
    {
        'comum.Configuracao',  # singleton por (app, chave); os seeds já gravam as chaves necessárias
    }
)


@dataclass
class Resultado:
    """Uma linha do relatório: quantas instâncias do model saíram e o primeiro erro."""

    modelo: str
    criados: int = 0
    erro: str = ''


def _elegivel(modelo: type[models.Model]) -> bool:
    opcoes = modelo._meta
    return (
        opcoes.app_label in settings.APPS_SUAP
        and opcoes.managed
        and not opcoes.proxy
        and not opcoes.swapped
        and opcoes.label not in EXCLUIDOS
        and router.db_for_write(modelo) == 'default'  # tira os models LDAP (ldapdb)
    )


def modelos_do_suap() -> list[type[models.Model]]:
    """Models concretos dos apps SUAP que recebem volume sintético."""
    return [modelo for modelo in apps.get_models() if _elegivel(modelo)]


def registrar_geradores(modelos: Iterable[type[models.Model]]) -> None:
    """Ensina ao bakery as subclasses de campo do SUAP (``ForeignKeyPlus``, ``CharFieldPlus``…).

    O bakery escolhe o gerador pela classe *exata* do campo e levanta ``TypeError`` para
    subclasses. Aqui cada classe desconhecida herda o gerador do ancestral mais próximo que
    ele conhece. Sem ancestral conhecido, o model falha e vai para o relatório.
    """
    mapa = generators.get_type_mapping()
    for classe in {type(campo) for modelo in modelos for campo in modelo._meta.concrete_fields}:
        if classe in mapa or generators.get(classe):
            continue
        ancestral = next((base for base in classe.__mro__[1:] if base in mapa), None)
        if ancestral is not None:
            generators.user_mapping[classe] = mapa[ancestral]


def _sortear(queryset: models.QuerySet) -> models.Model | None:
    """Linha aleatória reprodutível pela semente do ``random`` (não usa ``ORDER BY random()``)."""
    total = queryset.count()
    return queryset.order_by('pk')[random.randrange(total)] if total else None


def _valores_de_fk(modelo: type[models.Model]) -> dict[str, models.Model]:
    """Uma linha existente para cada FK obrigatória; alvo vazio fica para o bakery criar.

    Reusar linhas existentes é o que impede o volume de fabricar ``Setor`` e
    ``UnidadeOrganizacional`` aleatórios dentro da árvore que os seeds montaram. O2O só
    reusa alvo que o model ainda não referencia.
    """
    valores: dict[str, models.Model] = {}
    for campo in fks_obrigatorias(modelo):
        alvos = campo.related_model._base_manager.all()
        if campo.one_to_one:
            alvos = alvos.exclude(pk__in=modelo._base_manager.values(campo.attname))
        escolhido = _sortear(alvos)
        if escolhido is not None:
            valores[campo.name] = escolhido
    return valores


def _resumir(erro: Exception) -> str:
    primeira_linha = (str(erro).strip().splitlines() or [''])[0]
    return f'{type(erro).__name__}: {primeira_linha}'[:200]


def _gerar_modelo(modelo: type[models.Model], n: int) -> Resultado:
    """Até ``n`` instâncias, cada uma no seu savepoint; a primeira falha encerra o model."""
    resultado = Resultado(modelo._meta.label)
    for _ in range(n):
        try:
            with transaction.atomic():
                baker.make(modelo, _fill_optional=False, **_valores_de_fk(modelo))
        except Exception as erro:  # qualquer falha do model vira linha do relatório
            resultado.erro = _resumir(erro)
            break
        resultado.criados += 1
    return resultado


def gerar_volume(modelos: Iterable[type[models.Model]], n: int, semente: int = 0) -> list[Resultado]:
    """``n`` instâncias sintéticas por model, pais antes de filhos."""
    random.seed(semente)
    modelos = list(modelos)
    registrar_geradores(modelos)
    return [_gerar_modelo(modelo, n) for modelo in ordenar_modelos(modelos)]


def formatar_relatorio(resultados: list[Resultado], n: int) -> str:
    """Tabela ``model  criados/n  erro``, falhas primeiro, com o placar na última linha."""
    ordenados = sorted(resultados, key=lambda resultado: (not resultado.erro, resultado.modelo))
    linhas = [f'{r.modelo:<60} {r.criados:>4}/{n}  {r.erro}'.rstrip() for r in ordenados]
    falhas = sum(1 for resultado in resultados if resultado.erro)
    linhas.append(f'{len(resultados) - falhas}/{len(resultados)} models sem falha; {falhas} com falha.')
    return '\n'.join(linhas)
```

- [ ] **Step 4: Run to verify it passes**

Run: `env $T uv run pytest djtools/tests/test_banco_mock.py -q --reuse-db`
Expected: `10 passed`.
Se `test_fk_obrigatoria_reusa_linha_existente` falhar com `IntegrityError` em `auditoria_acao.nome` (unique), é colisão de string aleatória — não deveria ocorrer com 5 instâncias; investigue antes de mexer no teste.

- [ ] **Step 5: Lint e commit**

Run: `uv run ruff check djtools/banco_mock.py djtools/tests/test_banco_mock.py`
Expected: `All checks passed!` (se o bandit acusar algo, corrija ou ponha `# noqa: <código>` **só** na linha acusada).

```bash
git add djtools/banco_mock.py djtools/tests/test_banco_mock.py
git commit -m "[djtools] Volume sintético do banco mockado com model-bakery"
```

---

### Task 3: Senhas e guarda do banco

**Files:**
- Modify: `djtools/banco_mock.py`
- Modify: `comum/tests/factories.py`
- Test: `djtools/tests/test_banco_mock.py`

**Interfaces:**
- Produces:
  - `SUFIXO_BANCO = '_mock_e2e'`, `SENHA = '123'`.
  - `exigir_banco_mock(nome: str) -> None` — levanta `CommandError` se `nome` não termina em `SUFIXO_BANCO`.
  - `redefinir_senhas(senha: str = SENHA) -> int` — nº de usuários atualizados.
  - `comum.tests.factories.UserFactory`.

- [ ] **Step 1: Write the failing tests**

Em `comum/tests/factories.py`, trocar o import `from comum.models import Ano` por `from comum.models import Ano, User` e acrescentar ao fim:

```python
class UserFactory(DjangoModelFactory):
    class Meta:
        model = User
        django_get_or_create = ('username',)

    username = factory.Sequence(lambda n: f'usuario_{n}')
```

Em `djtools/tests/test_banco_mock.py`, imports novos:

```python
from comum.models import User
from comum.tests.factories import UserFactory
from django.contrib.auth.hashers import PBKDF2PasswordHasher
from django.core.management.base import CommandError

from djtools.banco_mock import exigir_banco_mock, redefinir_senhas
```

Testes:

```python
def test_exigir_banco_mock_recusa_outro_banco():
    exigir_banco_mock('test_suap_mock_e2e')
    with pytest.raises(CommandError, match='não é o banco mockado'):
        exigir_banco_mock('suap')


@pytest.mark.django_db
def test_redefinir_senhas_grava_pbkdf2_de_123():
    UserFactory.create_batch(2)
    assert redefinir_senhas() == User.objects.count()
    # check_password não serve: o settings de teste só conhece MD5. O dump é lido sob
    # suap.settings, cujo hasher padrão é PBKDF2.
    hasher = PBKDF2PasswordHasher()
    for senha in User.objects.values_list('password', flat=True):
        assert senha.startswith('pbkdf2_sha256$')
        assert hasher.verify('123', senha)
```

- [ ] **Step 2: Run to verify it fails**

Run: `env $T uv run pytest djtools/tests/test_banco_mock.py -q --reuse-db`
Expected: FAIL — `ImportError: cannot import name 'exigir_banco_mock'`.

- [ ] **Step 3: Write minimal implementation**

Em `djtools/banco_mock.py`, imports novos:

```python
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import PBKDF2PasswordHasher
from django.core.management.base import CommandError
```

Constantes logo abaixo dos imports:

```python
SUFIXO_BANCO = '_mock_e2e'
SENHA = '123'
```

Funções no fim do módulo:

```python
def exigir_banco_mock(nome: str) -> None:
    """Recusa gerar volume/senhas fora do banco mockado."""
    if not nome.endswith(SUFIXO_BANCO):
        raise CommandError(f'banco {nome!r} não é o banco mockado (*{SUFIXO_BANCO}); recusando escrever nele.')


def redefinir_senhas(senha: str = SENHA) -> int:
    """Mesma senha para todos os usuários, inclusive os criados pelo bakery.

    Hash PBKDF2 instanciado direto: este processo roda sob ``suap.settings_test``, cujo
    ``PASSWORD_HASHERS`` é só MD5, e um hash MD5 no dump não autentica sob ``suap.settings``.
    """
    hasher = PBKDF2PasswordHasher()
    return get_user_model()._base_manager.update(password=hasher.encode(senha, hasher.salt()))
```

- [ ] **Step 4: Run to verify it passes**

Run: `env $T uv run pytest djtools/tests/test_banco_mock.py -q --reuse-db`
Expected: `12 passed`.

- [ ] **Step 5: Commit**

```bash
git add djtools/banco_mock.py djtools/tests/test_banco_mock.py comum/tests/factories.py
git commit -m "[djtools] Senha única e guarda de banco no banco mockado"
```

---

### Task 4: Stubs de seed por módulo e marker `mock`

**Files:**
- Modify: `pyproject.toml` (lista `markers` em `[tool.pytest.ini_options]`)
- Modify: `conftest.py` (raiz; função `pytest_collection_modifyitems`, ~linha 158)
- Create: 12 × `<modulo>/tests/e2e/test_mock.py`

**Interfaces:**
- Produces: arquivos `*/tests/e2e/test_mock.py` com um teste `test_mock` marcado `mock` (o command os acha por glob). Itens `mock` só são coletados quando a expressão `-m` contém `mock`.

- [ ] **Step 1: Registrar o marker**

Em `pyproject.toml`, na lista `markers`, depois da linha do `doc`:

```toml
    "mock: stubs que materializam os seeds e2e para o manage.py gerar_banco_mock; fora da coleta salvo com -m mock",
```

- [ ] **Step 2: Deselecionar `mock` por padrão**

Em `conftest.py` (raiz), acima do `@pytest.hookimpl(tryfirst=True)` do `pytest_collection_modifyitems`:

```python
def _deselecionar_mock(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Stubs do ``gerar_banco_mock`` só rodam quando pedidos (``-m mock``).

    Não dá para usar ``-m "not mock"`` no addopts: qualquer ``-m`` da linha de comando o
    sobrescreve (o ``-m "not e2e"`` do job unitário do ``suap_check``, o ``-m e2e`` do job
    e2e). E o stub não pode rodar no job e2e: pedir ``seed_periodo_fechado`` antes da hora
    mudaria o estado para os testes do ``edu``.
    """
    if 'mock' in (config.option.markexpr or ''):
        return
    fora = [item for item in items if item.get_closest_marker('mock')]
    if fora:
        config.hook.pytest_deselected(items=fora)
        items[:] = [item for item in items if not item.get_closest_marker('mock')]
```

E trocar a assinatura/abertura do hook existente:

```python
@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config, items):
    _deselecionar_mock(config, items)
    db_fixtures = {'suap_data', 'light_data'}
```

(o resto do corpo fica como está).

- [ ] **Step 3: Criar os 12 stubs**

Modelo (troque `<modulo>` e a lista de fixtures pela tabela abaixo):

```python
"""Stub do ``manage.py gerar_banco_mock``: materializa os seeds e2e de sessão do <modulo>.

Só é coletado com ``-m mock`` (ver ``_deselecionar_mock`` no ``conftest.py`` raiz).
"""

import pytest


@pytest.mark.mock
@pytest.mark.django_db(databases='__all__')
def test_mock(<fixtures>) -> None:
    """Pede as fixtures de seed; o corpo é vazio de propósito."""
```

| Arquivo | `<fixtures>` |
|---|---|
| `ae/tests/e2e/test_mock.py` | `ae_seed` |
| `almoxarifado/tests/e2e/test_mock.py` | `almox_seed` |
| `centralservicos/tests/e2e/test_mock.py` | `centralservicos_seed` |
| `documento_eletronico/tests/e2e/test_mock.py` | `documento_seed, estado_documento_seed` |
| `edu/tests/e2e/test_mock.py` | `edu_seed, seed_periodo_executado, seed_periodo_fechado, seed_matricula_renovada, seed_conceito, seed_de_rotas` |
| `erros/tests/e2e/test_mock.py` | `erros_seed` |
| `eventos/tests/e2e/test_mock.py` | `eventos_seed` |
| `frota/tests/e2e/test_mock.py` | `frota_seed` |
| `pesquisa/tests/e2e/test_mock.py` | `pesquisa_seed` |
| `processo_eletronico/tests/e2e/test_mock.py` | `processo_seed` |
| `remanejamento/tests/e2e/test_mock.py` | `remanejamento_seed` |
| `saude/tests/e2e/test_mock.py` | `saude_seed` |

Antes de escrever cada stub, confirme que as fixtures existem e são `scope='session'`:
Run: `grep -n "scope='session'" -A1 <modulo>/tests/e2e/conftest.py | grep "def "`
Os parâmetros ficam sem uso no corpo de propósito (o ruff não acusa parâmetro de teste não usado).

- [ ] **Step 4: Verificar a exclusão por padrão**

Run: `env $T uv run pytest --collect-only -q saude/tests/e2e 2>&1 | grep -c test_mock`
Expected: `0`

Run: `env $T uv run pytest --collect-only -q -m "not e2e" saude/tests/e2e 2>&1 | grep -c test_mock`
Expected: `0` (é o caso do job unitário, que sobrescreve o addopts).

Run: `env $T uv run pytest --collect-only -q -m mock saude/tests/e2e 2>&1 | grep -c test_mock`
Expected: `1`

- [ ] **Step 5: Verificar que os 12 compõem num banco só**

Run:
```bash
env $T TEST_DATABASE_NAME=test_suap_mock_e2e uv run pytest -m mock -n 0 -p no:randomly --create-db --reuse-db */tests/e2e/test_mock.py
```
Expected: `12 passed` (≈3 min).

Se o stub do `edu` falhar: remova do fim da lista a fixture mais profunda da cadeia (`seed_de_rotas`, depois `seed_conceito`, `seed_matricula_renovada`, …) e rode só `edu/tests/e2e/test_mock.py` com `--create-db` até passar. Para cada fixture removida, registre na docstring do stub o erro observado, numa linha: `Fora: <fixture> — <exceção resumida>`. Repita a run completa e exija `12 passed`.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml conftest.py */tests/e2e/test_mock.py
git commit -m "[djtools] Stubs de seed e2e para o banco mockado (marker mock)"
```

---

### Task 5: Command `gerar_banco_mock`

**Files:**
- Create: `djtools/management/commands/gerar_banco_mock.py`
- Test: `djtools/tests/test_gerar_banco_mock.py`

**Interfaces:**
- Consumes: `banco_mock.SUFIXO_BANCO`, `SENHA`, `exigir_banco_mock`, `modelos_do_suap`, `gerar_volume`, `formatar_relatorio`, `redefinir_senhas` (Tasks 2–3); stubs `*/tests/e2e/test_mock.py` (Task 4).
- Produces (nível de módulo, para os testes trocarem via monkeypatch):
  - `BANCO = 'test_suap_mock_e2e'`
  - `parametros_pg() -> dict[str, str]`
  - `caminhos_dos_stubs(modulos: str) -> list[Path]`
  - `checar_pg_dump() -> None`
  - `dropar_banco() -> None`

- [ ] **Step 1: Write the failing tests**

`djtools/tests/test_gerar_banco_mock.py`:

```python
"""Testes da orquestração do ``manage.py gerar_banco_mock`` (sem subprocessos de verdade)."""

from __future__ import annotations

import io
import subprocess
from types import SimpleNamespace

import pytest
from comum.tests.factories import UserFactory
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection

from djtools import banco_mock
from djtools.management.commands import gerar_banco_mock as cmd

LOCMEM = 'django.core.mail.backends.locmem.EmailBackend'
ETAPAS = ('makemigrations', 'pytest', 'gerar_banco_mock', 'migrate', 'pg_dump')


def _etapa(comando: list[str]) -> str:
    return next(parte for parte in comando if parte in ETAPAS)


@pytest.fixture
def execucao(monkeypatch):
    registro = SimpleNamespace(chamadas=[], falhar=set(), dropados=[])

    def rodar(comando, **kwargs):
        registro.chamadas.append((comando, kwargs['env']))
        return subprocess.CompletedProcess(comando, 1 if _etapa(comando) in registro.falhar else 0)

    monkeypatch.setattr(cmd.subprocess, 'run', rodar)
    monkeypatch.setattr(cmd, 'checar_pg_dump', lambda: None)
    monkeypatch.setattr(cmd, 'dropar_banco', lambda: registro.dropados.append(cmd.BANCO))
    return registro


def test_orquestra_as_etapas_em_ordem_e_dropa(execucao, tmp_path):
    call_command('gerar_banco_mock', saida=str(tmp_path / 'x.dump'), modulos='saude', stdout=io.StringIO())
    assert [_etapa(comando) for comando, _ in execucao.chamadas] == list(ETAPAS)
    assert execucao.dropados == [cmd.BANCO]


def test_filhos_nunca_apontam_para_o_banco_de_dev(execucao, tmp_path):
    call_command('gerar_banco_mock', saida=str(tmp_path / 'x.dump'), modulos='saude', stdout=io.StringIO())
    ambientes = {_etapa(comando): env for comando, env in execucao.chamadas}
    assert all(env['EMAIL_BACKEND'] == LOCMEM for env in ambientes.values())
    assert all(env['DJANGO_SETTINGS_MODULE'] == 'suap.settings_test' for env in ambientes.values())
    assert ambientes['pytest']['TEST_DATABASE_NAME'] == cmd.BANCO
    assert ambientes['pytest']['DATABASE_NAME'] == 'postgres'
    assert ambientes['gerar_banco_mock']['DATABASE_NAME'] == cmd.BANCO
    assert ambientes['migrate']['DATABASE_NAME'] == cmd.BANCO


def test_seeds_rodam_so_os_stubs_pedidos(execucao, tmp_path):
    call_command('gerar_banco_mock', saida=str(tmp_path / 'x.dump'), modulos='saude', stdout=io.StringIO())
    pytest_cmd = next(comando for comando, _ in execucao.chamadas if _etapa(comando) == 'pytest')
    assert pytest_cmd[-1].endswith('saude/tests/e2e/test_mock.py')
    assert {'-m', 'mock', '--create-db', '--reuse-db'} <= set(pytest_cmd)


def test_falha_nos_seeds_mantem_o_banco_e_nao_faz_dump(execucao, tmp_path):
    execucao.falhar.add('pytest')
    with pytest.raises(CommandError, match="etapa 'seeds' falhou"):
        call_command('gerar_banco_mock', saida=str(tmp_path / 'x.dump'), modulos='saude', stdout=io.StringIO())
    assert 'pg_dump' not in [_etapa(comando) for comando, _ in execucao.chamadas]
    assert execucao.dropados == []


def test_sem_volume_repassa_a_flag(execucao, tmp_path):
    call_command('gerar_banco_mock', saida=str(tmp_path / 'x.dump'), modulos='saude', sem_volume=True, stdout=io.StringIO())
    volume = next(comando for comando, _ in execucao.chamadas if _etapa(comando) == 'gerar_banco_mock')
    assert '--sem-volume' in volume


def test_manter_banco_nao_dropa(execucao, tmp_path):
    call_command('gerar_banco_mock', saida=str(tmp_path / 'x.dump'), modulos='saude', manter_banco=True, stdout=io.StringIO())
    assert execucao.dropados == []


def test_modulo_sem_stub_e_recusado(execucao):
    with pytest.raises(CommandError, match='módulo sem stub'):
        call_command('gerar_banco_mock', modulos='nao_existe', stdout=io.StringIO())
    assert execucao.chamadas == []


def test_todos_os_stubs_por_padrao():
    assert len(cmd.caminhos_dos_stubs('')) == 12


def test_etapa_volume_recusa_banco_que_nao_e_mock():
    with pytest.raises(CommandError, match='não é o banco mockado'):
        call_command('gerar_banco_mock', etapa='volume', stdout=io.StringIO())


@pytest.mark.django_db
def test_etapa_volume_sem_volume_so_redefine_senhas(monkeypatch):
    UserFactory()
    monkeypatch.setitem(connection.settings_dict, 'NAME', cmd.BANCO)

    def nao_chamar(*args, **kwargs):
        raise AssertionError('gerar_volume não deveria rodar com --sem-volume')

    monkeypatch.setattr(banco_mock, 'gerar_volume', nao_chamar)
    saida = io.StringIO()
    call_command('gerar_banco_mock', etapa='volume', sem_volume=True, stdout=saida)
    assert "Senha '123' definida para" in saida.getvalue()
```

- [ ] **Step 2: Run to verify it fails**

Run: `env $T uv run pytest djtools/tests/test_gerar_banco_mock.py -q --reuse-db`
Expected: FAIL — `ImportError: cannot import name 'gerar_banco_mock'`.

- [ ] **Step 3: Write minimal implementation**

`djtools/management/commands/gerar_banco_mock.py`:

```python
"""Gera um dump (``pg_dump -Fc``) de um banco SUAP inteiro com dados fictícios.

Guia: ``docs/banco-mock.md``. Desenho: ``docs/superpowers/specs/2026-09-19-banco-mock-design.md``.

O processo que o dev chama só orquestra. Toda etapa que escreve roda num processo filho
sob ``suap.settings_test`` apontado para ``BANCO`` — nunca para o banco de desenvolvimento —
e com e-mail em memória (fora do pytest o ``settings_test`` herda o SMTP do ``.env``).
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any  # fronteira com o parser do Django: options é dict não tipado

import psycopg
from django.conf import settings
from django.core.management.base import CommandError
from django.db import connection

from djtools import banco_mock
from djtools.management.commands import BaseCommandPlus

BANCO = f'test_suap{banco_mock.SUFIXO_BANCO}'
LOCMEM = 'django.core.mail.backends.locmem.EmailBackend'


def parametros_pg() -> dict[str, str]:
    """Conexão com as mesmas variáveis e defaults de ``suap/settings_test.py``."""
    return {
        'host': os.environ.get('DATABASE_HOST', '127.0.0.1'),
        'port': os.environ.get('DATABASE_PORT', '5432'),
        'user': os.environ.get('DATABASE_USER', 'postgres'),
        'password': os.environ.get('DATABASE_PASSWORD', ''),
    }


def _conectar() -> psycopg.Connection:
    """Conexão ao banco de manutenção ``postgres`` (nunca ao de dev nem ao mockado)."""
    return psycopg.connect(dbname='postgres', autocommit=True, **parametros_pg())


def caminhos_dos_stubs(modulos: str) -> list[Path]:
    """Stubs de seed dos módulos pedidos (vírgula); vazio = todos os que existem."""
    base = Path(settings.BASE_DIR)
    if not modulos:
        return sorted(base.glob('*/tests/e2e/test_mock.py'))
    caminhos = [base / nome.strip() / 'tests' / 'e2e' / 'test_mock.py' for nome in modulos.split(',') if nome.strip()]
    faltando = [str(caminho.relative_to(base)) for caminho in caminhos if not caminho.exists()]
    if faltando:
        raise CommandError(f'módulo sem stub de seed: {", ".join(faltando)}')
    return caminhos


def _major(versao: str) -> int:
    achado = re.search(r'\d+', versao)
    if achado is None:
        raise CommandError(f'versão ilegível: {versao!r}')
    return int(achado.group())


def checar_pg_dump() -> None:
    """``pg_dump`` no PATH e com major ≥ o do servidor (falha antes dos ~3 min de seeds)."""
    if shutil.which('pg_dump') is None:
        raise CommandError('pg_dump não está no PATH; instale o postgresql-client da mesma versão do servidor.')
    cliente = _major(subprocess.run(['pg_dump', '--version'], capture_output=True, text=True, check=True).stdout)
    with _conectar() as conexao:
        servidor = conexao.info.server_version // 10000
    if cliente < servidor:
        raise CommandError(f'pg_dump {cliente} é mais antigo que o servidor PostgreSQL {servidor}.')


def dropar_banco() -> None:
    with _conectar() as conexao:
        conexao.execute(f'DROP DATABASE IF EXISTS "{BANCO}" WITH (FORCE)')


class Command(BaseCommandPlus):
    help = 'Gera um dump de um banco SUAP inteiro com dados fictícios (seeds e2e + volume sintético).'

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--saida', default='suap_mock.dump', help='arquivo de saída (pg_dump -Fc)')
        parser.add_argument('--volume', type=int, default=20, help='instâncias sintéticas por model')
        parser.add_argument('--semente', type=int, default=0, help='semente do random (reprodutibilidade)')
        parser.add_argument('--sem-volume', action='store_true', help='só o substrato dos seeds, sem bakery')
        parser.add_argument('--modulos', default='', help='módulos separados por vírgula; vazio = todos com stub')
        parser.add_argument('--manter-banco', action='store_true', help=f'não dropa {BANCO} ao fim')
        parser.add_argument('--etapa', choices=['volume'], help=argparse.SUPPRESS)

    def handle(self, *args: str, **options: Any) -> None:
        if options['etapa'] == 'volume':
            self._etapa_volume(options)
        else:
            self._orquestrar(options)

    def _etapa_volume(self, options: dict[str, Any]) -> None:
        """Roda no filho, já conectado a ``BANCO``."""
        banco_mock.exigir_banco_mock(connection.settings_dict['NAME'])
        if not options['sem_volume']:
            resultados = banco_mock.gerar_volume(banco_mock.modelos_do_suap(), options['volume'], options['semente'])
            self.stdout.write(banco_mock.formatar_relatorio(resultados, options['volume']))
        total = banco_mock.redefinir_senhas()
        self.stdout.write(f'Senha {banco_mock.SENHA!r} definida para {total} usuários.')

    def _orquestrar(self, options: dict[str, Any]) -> None:
        stubs = caminhos_dos_stubs(options['modulos'])
        checar_pg_dump()
        manage = [sys.executable, 'manage.py']
        self._rodar('makemigrations --check', [*manage, 'makemigrations', '--check', '--dry-run'], DATABASE_NAME='postgres')
        seeds = [sys.executable, '-m', 'pytest', '-m', 'mock', '-n', '0', '-p', 'no:randomly', '--create-db', '--reuse-db', *map(str, stubs)]
        self._rodar('seeds', seeds, DATABASE_NAME='postgres', TEST_DATABASE_NAME=BANCO)
        volume = [*manage, 'gerar_banco_mock', '--etapa', 'volume', '--volume', str(options['volume']), '--semente', str(options['semente'])]
        self._rodar('volume', volume + (['--sem-volume'] if options['sem_volume'] else []), DATABASE_NAME=BANCO)
        self._rodar('migrate --fake', [*manage, 'migrate', '--fake'], DATABASE_NAME=BANCO)
        saida = Path(options['saida']).resolve()
        pg = parametros_pg()
        dump = ['pg_dump', '-Fc', '-h', pg['host'], '-p', pg['port'], '-U', pg['user'], '-f', str(saida), BANCO]
        self._rodar('pg_dump', dump, PGPASSWORD=pg['password'])
        if not options['manter_banco']:
            dropar_banco()
        self.stdout.write(f'Dump gerado em {saida}. Restaure com: createdb suap_mock && pg_restore -d suap_mock --no-owner {saida}')

    def _rodar(self, nome: str, comando: list[str], **ambiente: str) -> None:
        """Processo filho com saída no terminal; código ≠ 0 aborta mantendo o banco."""
        self.stdout.write(f'>>> {nome}')
        env = {**os.environ, 'DJANGO_SETTINGS_MODULE': 'suap.settings_test', 'EMAIL_BACKEND': LOCMEM, **ambiente}
        codigo = subprocess.run(comando, cwd=settings.BASE_DIR, env=env, check=False).returncode
        if codigo != 0:
            raise CommandError(f'etapa {nome!r} falhou (código {codigo}); {BANCO}, se já criado, foi mantido para inspeção (dropdb {BANCO}).')
```

- [ ] **Step 4: Run to verify it passes**

Run: `env $T uv run pytest djtools/tests/test_gerar_banco_mock.py djtools/tests/test_banco_mock.py -q --reuse-db`
Expected: `22 passed`.

- [ ] **Step 5: Lint, pyright e commit**

Run: `uv run ruff check djtools/ && uv run pyright djtools/banco_mock.py djtools/management/commands/gerar_banco_mock.py`
Expected: ruff `All checks passed!`; pyright `0 errors` (warnings do tipo `reportAttributeAccessIssue` em `_meta` são aceitáveis se já existem em código vizinho — não use `Any` para calá-las). Se o bandit acusar `S603`/`S607`/`S608` nas linhas do `subprocess.run`/`DROP DATABASE`, ponha `# noqa: <código>` só nelas (os comandos e o nome do banco são constantes do módulo, não entrada do usuário).

```bash
git add djtools/management/commands/gerar_banco_mock.py djtools/tests/test_gerar_banco_mock.py
git commit -m "[djtools] Command gerar_banco_mock: orquestra seeds, volume, migrate --fake e pg_dump"
```

---

### Task 6: Primeira execução real e triagem do volume

**Files:**
- Modify (só se a triagem pedir): `djtools/banco_mock.py` (`EXCLUIDOS`, `registrar_geradores`)
- Test (se mudar código): `djtools/tests/test_banco_mock.py`

- [ ] **Step 1: Rodar o command de ponta a ponta mantendo o banco**

Run:
```bash
S=/tmp/banco-mock; mkdir -p $S
env $T uv run python manage.py gerar_banco_mock --saida $S/suap_mock.dump --manter-banco 2>&1 | tee $S/run.log
```
Expected: termina com `Dump gerado em /tmp/banco-mock/suap_mock.dump`. Anote o tempo total e o tamanho (`ls -lh $S/suap_mock.dump`).

- [ ] **Step 2: Ler o placar e agrupar as falhas**

Run: `grep -E "models sem falha" $S/run.log`
Run: `grep -E "^\S+\s+[0-9]+/20  \S" $S/run.log | sed -E 's/^\S+\s+[0-9]+\/20  //' | cut -c1-80 | sort | uniq -c | sort -rn | head -20`

- [ ] **Step 3: Tratar só as falhas sistêmicas**

Regra de decisão, por grupo de erro:
- **Mesma causa em ≥ 10 models** (ex.: `TypeError: field X type <Y> is not supported by baker` para uma classe sem ancestral no mapa; erro de threadlocal/usuário corrente em `save()`): corrija na raiz em `djtools/banco_mock.py` — gerador explícito em `registrar_geradores` (`generators.user_mapping[Classe] = gerador`) ou pré-condição — **com um teste** em `test_banco_mock.py` que reproduza o caso com um model real que o exiba, e rode de novo.
- **Model que polui o substrato** (cria linhas em `rh.Setor`, `rh.UnidadeOrganizacional`, `comum.Configuracao` apesar das FKs reusadas) **ou demora > 30 s**: adicione o label a `EXCLUIDOS` com o motivo em comentário.
- **Falha isolada** (validação de negócio em `save()`, constraint específica): deixe no relatório. O spec aceita.

Não persiga 100%: pare quando não houver mais grupo com ≥ 10 models.

- [ ] **Step 4: Conferir que o substrato não foi poluído**

Run:
```bash
docker exec suap-test-db psql -U postgres -d test_suap_mock_e2e -Atc "select count(*) from rh_setor"
```
Compare com a mesma contagem numa run `--sem-volume --manter-banco` (rode-a e anote). Expected: igual. Se diferente, ache o model que cria `Setor` (`select id, sigla from rh_setor order by id desc limit 5`) e aplique a regra "polui o substrato".

- [ ] **Step 5: Commit (se houve mudança)**

```bash
git add djtools/banco_mock.py djtools/tests/test_banco_mock.py
git commit -m "[djtools] Banco mockado: geradores e exclusões da primeira execução real"
```

---

### Task 7: Documentação e validação de restauração + login

**Files:**
- Create: `docs/banco-mock.md`
- Modify: `AGENTS.md` (seção `## Commands`, bloco "Setup / run")

- [ ] **Step 1: Validar restauração**

Run:
```bash
docker exec suap-test-db dropdb -U postgres --if-exists suap_mock
docker exec suap-test-db createdb -U postgres suap_mock
docker cp /tmp/banco-mock/suap_mock.dump suap-test-db:/tmp/suap_mock.dump
docker exec suap-test-db pg_restore -U postgres -d suap_mock --no-owner /tmp/suap_mock.dump; echo exit=$?
```
Expected: `exit=0`.

Run: `env $T DATABASE_NAME=suap_mock uv run python manage.py migrate --plan | tail -1`
Expected: `  No planned migration operations.`

- [ ] **Step 2: Validar login com senha `123` via runserver**

O worktree não tem `suap/settings.py` (pessoal, ignorado pelo git). Copie o do checkout principal:
Run: `cp ../../../suap/settings.py suap/settings.py && git check-ignore suap/settings.py`
Expected: `suap/settings.py`.

Crie/atualize `.claude/launch.json` com a configuração abaixo e suba com a ferramenta de preview (`preview_start {name: "suap-mock"}`), nunca via Bash:

```json
{
  "version": "0.0.1",
  "configurations": [
    {
      "name": "suap-mock",
      "runtimeExecutable": "env",
      "runtimeArgs": ["DATABASE_HOST=localhost", "DATABASE_PORT=5433", "DATABASE_USER=postgres", "DATABASE_PASSWORD=postgres", "DATABASE_NAME=suap_mock", "uv", "run", "python", "manage.py", "runserver", "8001"],
      "port": 8001
    }
  ]
}
```

No browser: abrir `/accounts/login/`, entrar com usuário `111002` (Médico do seed do Saúde) e senha `123`. Expected: cai na página inicial logada; screenshot como prova. Repita com um servidor do seed global:
`docker exec suap-test-db psql -U postgres -d suap_mock -Atc "select username from comum_user where eh_servidor order by id limit 1"`.

- [ ] **Step 3: Escrever `docs/banco-mock.md`**

```markdown
# Banco mockado do SUAP

`python manage.py gerar_banco_mock` gera um arquivo `pg_dump -Fc` com um banco SUAP inteiro
de dados fictícios, para desenvolver sem dump de produção.

## O que vem no banco

- **Substrato:** seed global do e2e (`djtools/new_tests/test_initial_data.py`) + os seeds de
  sessão dos módulos com suíte e2e (um stub `tests/e2e/test_mock.py` por módulo).
- **Volume sintético:** model-bakery em todos os models dos apps SUAP (`--volume` por model),
  reusando linhas existentes nas FKs obrigatórias. O relatório no fim da execução lista os
  models que falharam; falha de volume não impede o dump.
- **Senha de todos os usuários:** `123`.

## Gerar

Requisitos: Postgres com `max_locks_per_transaction` alto (o mesmo dos testes, ver
`AGENTS.md`), `pg_dump` com major ≥ o do servidor, Playwright instalado (alguns seeds
usam fixtures do e2e). O command usa as variáveis `DATABASE_HOST/PORT/USER/PASSWORD` do
ambiente, como `suap/settings_test.py`.

    DATABASE_HOST=localhost DATABASE_PORT=5433 DATABASE_USER=postgres DATABASE_PASSWORD=postgres \
      uv run python manage.py gerar_banco_mock --saida suap_mock.dump

Flags: `--volume N` (padrão 20), `--semente S` (padrão 0; mesma semente + mesmo código =
mesmo dump), `--sem-volume` (só substrato), `--modulos saude,frota`, `--manter-banco`
(não dropa `test_suap_mock_e2e`, útil para inspecionar). Nunca escreve no banco de
desenvolvimento: tudo roda em `test_suap_mock_e2e`.

## Restaurar

    createdb suap_mock
    pg_restore -d suap_mock --no-owner suap_mock.dump

Depois, `DATABASE_NAME=suap_mock` no `.env`. O schema já tem todas as migrations registradas
(`migrate` não aplica nada).

## Logins

Senha `123` para qualquer usuário. Matrículas por papel: dicionário `PAPEIS` (ou `USUARIOS`)
no `tests/e2e/conftest.py` de cada módulo; servidores do seed global:
`djtools/new_tests/test_initial_data.py`.

## Datas

Cada seed roda com o relógio congelado na data-base do módulo; o dump sai com essas datas e,
hoje, prazos e períodos letivos aparecem vencidos. Para ver a tela "viva", rode o
`runserver` com o relógio na data-base do módulo.

| Módulo | Data-base |
|---|---|
| ae | 03/06/2024 |
| documento_eletronico | 08/01/2020 |
| edu | 10/03/2019 |
| frota | 25/11/2018 |
| pesquisa | 01/01/2018 |
| saude | 21/01/2019 |

## Adicionar um módulo

Crie `<modulo>/tests/e2e/test_mock.py` pedindo as fixtures de seed de sessão do módulo
(copie de `saude/tests/e2e/test_mock.py`). O command acha o stub sozinho.
```

- [ ] **Step 4: Linha no `AGENTS.md`**

Em `## Commands`, bloco "Setup / run", depois da linha do `make runserver`:

```markdown
- `python manage.py gerar_banco_mock` — gera um dump (`pg_dump -Fc`) com um banco SUAP inteiro de dados fictícios (seeds e2e + volume sintético, senha `123`). Ver `docs/banco-mock.md`.
```

- [ ] **Step 5: Limpar e commitar**

Run: `docker exec suap-test-db dropdb -U postgres --if-exists test_suap_mock_e2e`
(`suap/settings.py` e `.claude/launch.json` ficam fora do commit: o primeiro é ignorado; confira `git status` e não adicione o segundo se não for rastreado.)

```bash
git add docs/banco-mock.md AGENTS.md
git commit -m "[djtools] Documentação do banco mockado (gerar_banco_mock)"
```
