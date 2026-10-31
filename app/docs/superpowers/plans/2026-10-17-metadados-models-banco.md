# Metadados dos models no banco — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gravar no banco, a cada `sync`, quatro tabelas `metadados_*` com o que só o Python sabe dos
models (nomes legíveis, docstring, help_text, choices, transições FSM, GFK, default, editable, auto_now).

**Architecture:** Quatro models simples em `djtools/models.py` (uma migration). Um coletor puro em
`djtools/metadados.py` transforma cada model Django em instâncias não salvas desses quatro models. O
comando `gerar_metadados` chama o coletor para todos os models no escopo, deduplica, e troca o conteúdo
das tabelas numa transação (`DELETE` + `bulk_create`). O `sync` chama o comando logo após o `migrate`.

**Tech Stack:** Django 5.2, PostgreSQL, pytest + pytest-django, django_fsm (só por duck typing).

**Spec:** `docs/superpowers/specs/2026-10-17-metadados-models-banco-design.md`

## Global Constraints

- Sem `COMMENT ON`, `db_comment` ou `db_table_comment`; nenhum app além de `djtools` e `comum` (sync) muda.
- Tabelas com `db_table` explícito: `metadados_tabelas`, `metadados_campos`, `metadados_choices`, `metadados_transicoes`.
- Models são `models.Model` (de `djtools.db import models`), **não** `ModelPlus`: sem permissões, History, admin, menu.
- `CharField` sem `max_length` (Postgres aceita; ver `PushSubscription`) para nunca truncar.
- Recriação é `DELETE` + `bulk_create` dentro de `transaction.atomic()`; **nunca** `TRUNCATE`.
- Erro ao coletar um model: avisa e segue; o comando não aborta o `sync`.
- `valor` de choice: `'true'`/`'false'` para bool, `.value` para Enum/`Choices`, `str(v)` para o resto, `None` fica nulo.
- Textos lazy viram `str` com `translation.override('pt-br')`.
- pt-BR em nomes, mensagens e docstrings; tipagem nas defs tocadas; complexidade ciclomática ≤ 10 por função (o hook bloqueia).
- Testes: `djtools/tests/models/` (DB-free) e `djtools/tests/tasks/` (comando). Rodar contra Postgres dedicado:
  `docker run --rm -d --name suap-test-db-metadados -p 5435:5432 -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres postgres:18 -c max_locks_per_transaction=4096 -c shared_preload_libraries=pg_stat_statements`
  e `DATABASE_PORT=5435 TEST_DATABASE_NAME=test_suap_metadados DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest --create-db <alvo>` (`--reuse-db` depois).
  Abreviado abaixo como `PYTEST <alvo>`.

## Review Focus

1. JOIN com `coluna::text` em campo bool: o Postgres escreve `true`/`false`, não `True` — teste SQL na Task 3.
2. Choice com valor `None` (12 fields): grava `valor` nulo sem quebrar a chave única nem a deduplicação — Task 2 e Task 3.
3. `verbose_name` lazy de app de terceiros (`auth.Permission` → `permissão`) precisa sair em pt-BR, não em inglês — Task 3.
4. Choices no `base_field` de `ArrayField` (`boletim_servico.BoletimProgramado.nivel_acesso`) não podem sumir — Task 2.
5. Um model que explode na coleta não pode levar os outros junto — Task 3.

---

### Task 1: Models e migration

**Files:**
- Modify: `djtools/models.py` (acrescentar ao fim)
- Create: `djtools/migrations/0015_metadados.py` (gerada)
- Test: `djtools/tests/tasks/test_gerar_metadados.py`

**Interfaces:**
- Produces (todos em `djtools.models`, campos `CharField` sem `max_length` salvo indicação):
  - `MetadadoTabela`: `tabela` (unique), `app`, `model`, `verbose_name`, `verbose_name_plural`, `docstring` (`TextField`, blank).
  - `MetadadoCampo`: `tabela`, `coluna`, `app`, `model`, `campo`, `tipo`, `verbose_name`, `help_text` (`TextField`, blank), `default` (`TextField`, null), `default_callable` (bool), `editable` (bool), `auto_now` (bool), `auto_now_add` (bool), `tabela_relacionada` (null), `limit_choices_to` (`TextField`, null), `generic_foreign_key` (null). `UniqueConstraint(tabela, coluna)`.
  - `MetadadoChoice`: `tabela`, `coluna`, `valor` (`TextField`, null), `rotulo` (`TextField`), `ordem` (`PositiveIntegerField`), `grupo` (`TextField`, null). `UniqueConstraint(tabela, coluna, valor)`.
  - `MetadadoTransicao`: `tabela`, `coluna`, `nome`, `origem`, `destino` (null). `UniqueConstraint(tabela, coluna, nome, origem)`.
  - Cada um com `verbose_name`/`verbose_name_plural` em pt-BR e uma docstring de uma linha (eles descrevem a si mesmos).

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.django_db
def test_choice_repetido_viola_chave_unica() -> None:
    MetadadoChoice.objects.create(tabela='t', coluna='c', valor='1', rotulo='A', ordem=0)
    with pytest.raises(IntegrityError):
        MetadadoChoice.objects.create(tabela='t', coluna='c', valor='1', rotulo='B', ordem=1)
```

- [ ] **Step 2: Run it — FAIL (`ImportError: MetadadoChoice`)**

Run: `PYTEST djtools/tests/tasks/test_gerar_metadados.py`

- [ ] **Step 3: Add the four models to `djtools/models.py`, then generate the migration**

Run: `uv run python manage.py makemigrations djtools -n metadados`
Expected: cria `djtools/migrations/0015_metadados.py` só com os 4 `CreateModel`.

- [ ] **Step 4: Run test — PASS; and `uv run python manage.py makemigrations --check --dry-run` → "No changes detected"**

- [ ] **Step 5: Commit**

```bash
git add djtools/models.py djtools/migrations/0015_metadados.py djtools/tests/tasks/test_gerar_metadados.py
git commit -m "[djtools] Models das tabelas de metadados"
```

---

### Task 2: Coletor de metadados

**Files:**
- Create: `djtools/metadados.py`
- Test: `djtools/tests/models/test_metadados.py` (DB-free: só instâncias não salvas)

**Interfaces:**
- Consumes: os 4 models da Task 1.
- Produces (em `djtools.metadados`):
  - `models_no_escopo() -> list[type[Model]]` — `apps.get_models(include_auto_created=True)`, sem proxy, com `router.allow_migrate_model(DEFAULT_DB_ALIAS, m)` (exclui `managed=False` e `ldapdb`).
  - `valor_choice(valor: object) -> str | None` — regra de Global Constraints; bool testado antes de int.
  - `@dataclass class Metadados: tabela: MetadadoTabela; campos: list[MetadadoCampo]; choices: list[MetadadoChoice]; transicoes: list[MetadadoTransicao]`
  - `coletar(model: type[Model]) -> Metadados` — não toca o banco; não força tradução (quem chama faz o `override`).
  - `deduplicar(objetos: list[T], chave: Callable[[T], tuple]) -> tuple[list[T], list[str]]` — mantém o primeiro de cada chave, devolve avisos `'<tabela>.<coluna>: chave repetida <chave>'`.

Regras do `coletar` que o implementador não deduz sozinho:
- Campos: `model._meta.local_concrete_fields` (coluna física, declarada neste model). M2M não gera linha (a tabela `through` gera).
- `docstring`: `model.__doc__` limpo com `inspect.cleandoc`; vazio quando começa com `f'{model.__name__}('` (assinatura que o Django gera).
- `default`: `None` se `not f.has_default()`; callable → `f'{d.__module__}.{d.__qualname__}'` e `default_callable=True`; senão `repr(d)`.
- `limit_choices_to`: vazio → `None`; callable → `módulo.qualname` (**nunca chamar**); senão `repr`.
- `tabela_relacionada`: `f.related_model._meta.db_table` quando `f.is_relation`.
- `generic_foreign_key`: para cada `GenericForeignKey` em `model._meta.private_fields`, o nome do GFK nas linhas cujo `campo` é `ct_field` ou `fk_field`.
- Choices: `f.choices`, ou `f.base_field.choices` quando o field tiver `base_field`; grupo `(rótulo_grupo, [(v, r), ...])` vira linhas com `grupo=rótulo_grupo`; `ordem` é a posição global (0, 1, 2…).
- Transições: fields com `get_all_transitions` (django_fsm); para cada `t` em `f.get_all_transitions(model)`: `nome=t.name`, `origem=str(t.source)`, `destino=None if t.target is None else str(t.target)`.

- [ ] **Step 1: Write the failing tests**

```python
def test_valor_choice() -> None:
    class Cor(models.IntegerChoices):
        AZUL = 1
    class Letra(enum.Enum):
        A = 'x'
    assert [valor_choice(v) for v in (True, False, 1, 'A', None, Cor.AZUL, Letra.A)] == ['true', 'false', '1', 'A', None, '1', 'x']

def test_choices_de_componente_curricular() -> None:
    m = coletar(ComponenteCurricular)
    tipo = [(c.tabela, c.valor, c.rotulo) for c in m.choices if c.coluna == 'tipo']
    assert tipo[0] == ('edu_componentecurricular', '1', 'Regular')
    assert len(tipo) == len(ComponenteCurricular._meta.get_field('tipo').choices)

def test_choice_bool() -> None:
    m = coletar(RequerimentoAproveitamentoEstudo)
    assert ('true', 'Nesta instituição') in {(c.valor, c.rotulo) for c in m.choices if c.coluna == 'interno'}

def test_choices_do_base_field_de_array() -> None:
    m = coletar(BoletimProgramado)
    assert {c.coluna for c in m.choices} >= {'nivel_acesso'}

def test_docstring_real_e_assinatura_automatica() -> None:
    assert coletar(Permission).tabela.docstring.startswith('The permissions system')
    assert coletar(ComponenteCurricular).tabela.docstring == ''

def test_atributos_de_campo() -> None:
    campos = {c.campo: c for c in coletar(Task).campos}
    assert (campos['uuid'].default, campos['uuid'].default_callable) == ('uuid.uuid4', True)
    assert campos['start'].editable is False
    assert campos['user'].coluna == 'user_id'
    assert {c.campo: c for c in coletar(EmailEnviadoLog).campos}['data'].auto_now_add is True

def test_generic_foreign_key_e_limit_choices_to() -> None:
    campos = {c.campo: c for c in coletar(Vinculo).campos}
    assert campos['tipo_relacionamento'].generic_foreign_key == 'relacionamento'
    assert campos['id_relacionamento'].generic_foreign_key == 'relacionamento'
    assert campos['tipo_relacionamento'].tabela_relacionada == 'django_content_type'
    assert "('app_label', 'rh')" in campos['tipo_relacionamento'].limit_choices_to

def test_transicoes_de_chamado() -> None:
    m = coletar(Chamado)
    assert ('status', 'cancelar_chamado_transition', '1', '7') in {(t.coluna, t.nome, t.origem, t.destino) for t in m.transicoes}

def test_escopo() -> None:
    escopo = models_no_escopo()
    assert Group.permissions.through in escopo and MetadadoChoice in escopo
    assert not any(m._meta.proxy or not m._meta.managed for m in escopo)

def test_deduplicar_mantem_o_primeiro() -> None:
    a = MetadadoChoice(tabela='t', coluna='c', valor=None, rotulo='A', ordem=0)
    b = MetadadoChoice(tabela='t', coluna='c', valor=None, rotulo='B', ordem=1)
    mantidos, avisos = deduplicar([a, b], lambda c: (c.tabela, c.coluna, c.valor))
    assert mantidos == [a] and len(avisos) == 1
```

Imports: `edu.models.ComponenteCurricular`, `edu.models.RequerimentoAproveitamentoEstudo`,
`boletim_servico.models.BoletimProgramado`, `django.contrib.auth.models.Permission, Group`,
`djtools.models.Task, EmailEnviadoLog, MetadadoChoice`, `comum.models.Vinculo`,
`centralservicos.models.Chamado`.

- [ ] **Step 2: Run — FAIL (`ModuleNotFoundError: djtools.metadados`)**

Run: `PYTEST djtools/tests/models/test_metadados.py`

- [ ] **Step 3: Implement `djtools/metadados.py` per the Interfaces block** (helpers pequenos por regra para ficar em C901 ≤ 10)

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: Commit**

```bash
git add djtools/metadados.py djtools/tests/models/test_metadados.py
git commit -m "[djtools] Coletor de metadados dos models"
```

---

### Task 3: Comando `gerar_metadados` e chamada no `sync`

**Files:**
- Create: `djtools/management/commands/gerar_metadados.py`
- Modify: `comum/management/commands/sync.py:29` (nova linha logo após o `migrate`)
- Test: `djtools/tests/tasks/test_gerar_metadados.py` (estende o da Task 1)

**Interfaces:**
- Consumes: `models_no_escopo`, `coletar`, `deduplicar`, `Metadados` (Task 2); os 4 models (Task 1).
- Produces: `class Command(BaseCommandPlus)` em `gerar_metadados`; `handle` sem argumentos.

Comportamento:
- Tudo dentro de `translation.override('pt-br')`.
- Para cada model: `try: coletar(m)` / `except Exception as e:` guarda `f'{m._meta.label}: {e}'` e segue.
- Deduplica cada lista pelas chaves únicas da Task 1; avisos no stdout.
- `with transaction.atomic():` `.delete()` nos 4 models e `bulk_create(..., batch_size=2000)` nos 4.
- Última linha no stdout: `Metadados: {n} tabelas, {n} campos, {n} choices, {n} transições; {n} models com erro`, seguida de uma linha por erro.
- No `sync`: `print_and_call_command('gerar_metadados')` logo após `print_and_call_command('migrate', interactive=False)`.

- [ ] **Step 1: Write the failing tests**

```python
def _conteudo() -> list:
    return [sorted(M.objects.values_list(*[f.name for f in M._meta.fields if f.name != 'id']))
            for M in (MetadadoTabela, MetadadoCampo, MetadadoChoice, MetadadoTransicao)]

@pytest.mark.django_db
def test_gerar_metadados_popula_e_e_idempotente() -> None:
    call_command('gerar_metadados', stdout=StringIO())
    assert MetadadoChoice.objects.filter(tabela='edu_componentecurricular', coluna='tipo', valor='1', rotulo='Regular').exists()
    assert MetadadoChoice.objects.filter(tabela='edu_componentecurricular', coluna='tipo').count() == len(ComponenteCurricular._meta.get_field('tipo').choices)
    assert MetadadoCampo.objects.filter(tabela='edu_componentecurricular', coluna='tipo').exists()
    assert MetadadoTabela.objects.get(tabela='auth_permission').verbose_name == 'permissão'
    assert MetadadoChoice.objects.filter(valor__isnull=True).exists()
    antes = _conteudo()
    call_command('gerar_metadados', stdout=StringIO())
    assert _conteudo() == antes

@pytest.mark.django_db
def test_join_de_choice_bool_com_cast_do_postgres() -> None:
    call_command('gerar_metadados', stdout=StringIO())
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT rotulo FROM metadados_choices WHERE tabela = 'edu_requerimentoaproveitamentoestudo' "
            "AND coluna = 'interno' AND valor = true::text"
        )
        assert cursor.fetchone() == ('Nesta instituição',)

@pytest.mark.django_db
def test_erro_num_model_nao_aborta(monkeypatch: pytest.MonkeyPatch) -> None:
    original = gerar_metadados.coletar
    def coletar_falhando(model):
        if model is ComponenteCurricular:
            raise ValueError('quebrado')
        return original(model)
    monkeypatch.setattr(gerar_metadados, 'coletar', coletar_falhando)
    saida = StringIO()
    call_command('gerar_metadados', stdout=saida)
    assert 'edu.ComponenteCurricular: quebrado' in saida.getvalue()
    assert MetadadoTabela.objects.filter(tabela='djtools_task').exists()
    assert not MetadadoTabela.objects.filter(tabela='edu_componentecurricular').exists()
```

(`gerar_metadados` = `djtools.management.commands.gerar_metadados`; o comando importa `coletar` pelo
nome do módulo-nível para o `monkeypatch` valer.)

- [ ] **Step 2: Run — FAIL (`Unknown command: 'gerar_metadados'`)**

Run: `PYTEST djtools/tests/tasks/test_gerar_metadados.py`

- [ ] **Step 3: Implement the command and add the call to `sync.py`**

- [ ] **Step 4: Run — PASS; also `PYTEST djtools/tests/models/test_metadados.py` still PASS**

- [ ] **Step 5: Smoke manual no banco de dev (opcional, só leitura do resultado)**

Run: `uv run python manage.py gerar_metadados`
Expected: última linha `Metadados: ~2200 tabelas, ~18000 campos, ...; 0 models com erro` em poucos segundos.

- [ ] **Step 6: Lint e commit**

```bash
uv run ruff format djtools comum/management/commands/sync.py && uv run ruff check djtools comum/management/commands/sync.py
git add djtools/management/commands/gerar_metadados.py comum/management/commands/sync.py djtools/tests/tasks/test_gerar_metadados.py
git commit -m "[djtools] Comando gerar_metadados chamado no sync"
```
