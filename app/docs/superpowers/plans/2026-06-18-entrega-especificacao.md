# Vínculo Entrega ↔ Especificação — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir que uma `Entrega` registre, opcionalmente, quais `Especificacao` do DoD da demanda estão incluídas no pacote (rastreabilidade pura).

**Architecture:** Novo `ManyToManyField` `especificacoes` em `Entrega`, escopado por demanda no `EntregaForm`, gravado pelo `EntregaService.criar` (a view usa o service, não `form.save()`), e exibido read-only na aba de Entregas. Sem acoplamento ao ciclo de vida da especificação.

**Tech Stack:** Django 5.2, `djtools` (`ModelPlus`, `ModelFormPlus`, `MultipleModelChoiceFieldPlus`), pytest + pytest-django.

## Global Constraints

- Idioma pt-BR em identificadores, comentários e mensagens.
- Modelos herdam de `djtools.db.models` (`ModelPlus`), não `django.db.models`.
- Ruff: line length 150, aspas simples; `*/migrations/*` excluído.
- Complexidade ciclomática ≤ 10 nas funções tocadas.
- `USE_TZ = False` no projeto — usar `timezone.now().date()` para datas.
- Testes com `pytest` (NÃO `manage.py test`); marcar `@pytest.mark.django_db(databases='__all__')` quando tocar o banco.
- Fixtures `demanda` e `usuario` já existem em `demandas/tests/conftest.py`.
- Spec de referência: `docs/superpowers/specs/2026-06-18-entrega-especificacao-design.md`.

## File Structure

- Modify: `demandas/models/entrega.py` — campo M2M `especificacoes`.
- Create: `demandas/migrations/0047_entrega_especificacoes.py` (via `makemigrations`).
- Modify: `demandas/services.py:29-93` — param `especificacoes` em `EntregaService.criar`.
- Modify: `demandas/forms.py` — campo `especificacoes` em `EntregaForm` (já importa `Especificacao`).
- Modify: `demandas/views.py:2663-2688` — passar `especificacoes` ao service.
- Modify: `demandas/templates/tabs/entregas.html` — exibir especificações vinculadas.
- Create: `demandas/tests/test_entrega_especificacao.py` — testes de modelo, service e form.

---

### Task 1: Modelo — campo M2M `especificacoes`

**Files:**
- Modify: `demandas/models/entrega.py` (classe `Entrega`, após o bloco "Rastreabilidade", antes de `class Meta`)
- Create: `demandas/migrations/0047_entrega_especificacoes.py`
- Test: `demandas/tests/test_entrega_especificacao.py`

**Interfaces:**
- Produces: `Entrega.especificacoes` (M2M manager) e reverse `Especificacao.entregas`.

- [ ] **Step 1: Escrever o teste que falha**

Criar `demandas/tests/test_entrega_especificacao.py`:

```python
"""Vínculo Entrega ↔ Especificação (rastreabilidade)."""

from unittest import mock

import pytest

from demandas.forms import EntregaForm
from demandas.models import Demanda, Entrega, Situacao
from demandas.models.consolidacao import DoD, Especificacao
from demandas.models.entrega import StatusEntrega
from demandas.services import EntregaService


@pytest.mark.django_db(databases='__all__')
def test_entrega_vincula_e_lista_especificacoes(demanda, usuario):
    dod = DoD.objects.create(demanda=demanda, descricao='DoD')
    e1 = Especificacao.objects.create(dod=dod, nome='Login', ordem=1)
    e2 = Especificacao.objects.create(dod=dod, nome='Relatório', ordem=2)

    entrega = Entrega.objects.create(
        demanda=demanda,
        titulo='Pacote 1',
        status=StatusEntrega.ENVIADA,
        cadastrada_por=usuario,
    )
    entrega.especificacoes.set([e1, e2])

    assert set(entrega.especificacoes.all()) == {e1, e2}
    assert list(e1.entregas.all()) == [entrega]
```

- [ ] **Step 2: Rodar o teste e confirmar a falha**

Run: `uv run pytest -q demandas/tests/test_entrega_especificacao.py::test_entrega_vincula_e_lista_especificacoes`
Expected: FAIL — `AttributeError: 'Entrega' object has no attribute 'especificacoes'`.

- [ ] **Step 3: Adicionar o campo M2M ao modelo**

Em `demandas/models/entrega.py`, dentro de `class Entrega`, logo após o campo `cadastrada_por` (bloco "Rastreabilidade") e antes de `class Meta`:

```python
    # ── Rastreabilidade de escopo ────────────────────────────────────────────
    especificacoes = models.ManyToManyField(
        'demandas.Especificacao',
        verbose_name='Especificações entregues',
        blank=True,
        related_name='entregas',
        help_text='Especificações do DoD incluídas neste pacote de entrega.',
    )
```

- [ ] **Step 4: Gerar a migration**

Run: `uv run python manage.py makemigrations demandas`
Expected: cria `demandas/migrations/0047_entrega_especificacoes.py` adicionando o M2M.

- [ ] **Step 5: Rodar o teste e confirmar que passa**

Run: `uv run pytest -q demandas/tests/test_entrega_especificacao.py::test_entrega_vincula_e_lista_especificacoes`
Expected: PASS (testes usam `--no-migrations`; o schema vem do modelo).

- [ ] **Step 6: Commit**

```bash
git add demandas/models/entrega.py demandas/migrations/0047_entrega_especificacoes.py demandas/tests/test_entrega_especificacao.py
git commit -m "[demandas] Entrega: vínculo M2M com Especificação (rastreabilidade)"
```

---

### Task 2: Service — `EntregaService.criar(especificacoes=...)`

**Files:**
- Modify: `demandas/services.py:29-93`
- Test: `demandas/tests/test_entrega_especificacao.py`

**Interfaces:**
- Consumes: `Entrega.especificacoes` (Task 1).
- Produces: `EntregaService.criar(..., especificacoes: Iterable[Especificacao] | None = None) -> Entrega`.

- [ ] **Step 1: Escrever o teste que falha**

Acrescentar em `demandas/tests/test_entrega_especificacao.py`:

```python
@pytest.mark.django_db(databases='__all__')
def test_service_criar_vincula_especificacoes(demanda, usuario):
    demanda.situacao = Situacao.ESTADO_EM_DESENVOLVIMENTO
    demanda.save()
    dod = DoD.objects.create(demanda=demanda, descricao='DoD')
    e1 = Especificacao.objects.create(dod=dod, nome='Login', ordem=1)

    with mock.patch('demandas.services.adicionar_comentario'):
        entrega = EntregaService.criar(
            demanda=demanda,
            titulo='Pacote',
            usuario=usuario,
            especificacoes=[e1],
        )

    assert list(entrega.especificacoes.all()) == [e1]


@pytest.mark.django_db(databases='__all__')
def test_service_criar_sem_especificacoes_nao_vincula(demanda, usuario):
    demanda.situacao = Situacao.ESTADO_EM_DESENVOLVIMENTO
    demanda.save()

    with mock.patch('demandas.services.adicionar_comentario'):
        entrega = EntregaService.criar(demanda=demanda, titulo='Pacote', usuario=usuario)

    assert entrega.especificacoes.count() == 0
```

- [ ] **Step 2: Rodar e confirmar a falha**

Run: `uv run pytest -q demandas/tests/test_entrega_especificacao.py::test_service_criar_vincula_especificacoes`
Expected: FAIL — `TypeError: criar() got an unexpected keyword argument 'especificacoes'`.

- [ ] **Step 3: Adicionar o parâmetro e o vínculo**

Em `demandas/services.py`, na assinatura de `criar` (após `versionamento: str = '',`), adicionar o parâmetro:

```python
        versionamento: str = '',
        especificacoes=None,
    ) -> Entrega:
```

E, após `entrega.save()` (antes do `HistoricoEntrega.objects.create(...)`), adicionar:

```python
        if especificacoes:
            entrega.especificacoes.set(especificacoes)
```

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `uv run pytest -q demandas/tests/test_entrega_especificacao.py -k service`
Expected: PASS (2 testes).

- [ ] **Step 5: Commit**

```bash
git add demandas/services.py demandas/tests/test_entrega_especificacao.py
git commit -m "[demandas] EntregaService.criar: vincula especificações"
```

---

### Task 3: Form — campo `especificacoes` escopado à demanda

**Files:**
- Modify: `demandas/forms.py` (classe `EntregaForm`, ~linha 1119)
- Test: `demandas/tests/test_entrega_especificacao.py`

**Interfaces:**
- Consumes: `Especificacao` (já importado em `forms.py`), `Entrega.especificacoes`.
- Produces: `EntregaForm.fields['especificacoes']` (presente só quando a demanda tem especificações), disponível em `cleaned_data['especificacoes']`.

- [ ] **Step 1: Escrever os testes que falham**

Acrescentar em `demandas/tests/test_entrega_especificacao.py`:

```python
@pytest.mark.django_db(databases='__all__')
def test_form_especificacoes_escopadas_a_demanda(demanda):
    dod = DoD.objects.create(demanda=demanda, descricao='DoD')
    e1 = Especificacao.objects.create(dod=dod, nome='Login', ordem=1)
    outra = Demanda.objects.create(titulo='Outra', descricao='x')
    dod2 = DoD.objects.create(demanda=outra, descricao='DoD2')
    Especificacao.objects.create(dod=dod2, nome='Fora', ordem=1)

    form = EntregaForm(demanda=demanda, request=None)

    assert 'especificacoes' in form.fields
    assert form.fields['especificacoes'].required is False
    assert list(form.fields['especificacoes'].queryset) == [e1]


@pytest.mark.django_db(databases='__all__')
def test_form_remove_campo_sem_especificacoes(demanda):
    form = EntregaForm(demanda=demanda, request=None)
    assert 'especificacoes' not in form.fields
```

- [ ] **Step 2: Rodar e confirmar a falha**

Run: `uv run pytest -q demandas/tests/test_entrega_especificacao.py -k form`
Expected: FAIL — `KeyError: 'especificacoes'` (campo não existe).

- [ ] **Step 3: Declarar o campo e escopá-lo no `__init__`**

Em `demandas/forms.py`, na classe `EntregaForm`, declarar o campo como atributo de classe (logo abaixo da docstring, antes de `class Meta`):

```python
    especificacoes = forms.MultipleModelChoiceFieldPlus(
        label='Especificações entregues',
        queryset=Especificacao.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text='Selecione as especificações do DoD incluídas nesta entrega.',
    )
```

No `__init__`, ao final do método (após o loop dos campos de GitLab), adicionar:

```python
        especs = Especificacao.objects.filter(dod__demanda=self.demanda)
        if especs.exists():
            self.fields['especificacoes'].queryset = especs
        else:
            del self.fields['especificacoes']
```

(O campo NÃO entra em `Meta.fields` — fica fora do save do ModelForm; a view o repassa ao service.)

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `uv run pytest -q demandas/tests/test_entrega_especificacao.py -k form`
Expected: PASS (2 testes).

- [ ] **Step 5: Commit**

```bash
git add demandas/forms.py demandas/tests/test_entrega_especificacao.py
git commit -m "[demandas] EntregaForm: seleção de especificações escopada à demanda"
```

---

### Task 4: View + Template — fiação e exibição

**Files:**
- Modify: `demandas/views.py:2663-2688` (`criar_enrega`)
- Modify: `demandas/templates/tabs/entregas.html`

**Interfaces:**
- Consumes: `EntregaService.criar(especificacoes=...)` (Task 2), `EntregaForm` (Task 3), `entrega.especificacoes` (Task 1).

Esta task é cola fina entre camadas já cobertas por testes unitários (service/form); a verificação é manual no `runserver`.

- [ ] **Step 1: Repassar `especificacoes` ao service**

Em `demandas/views.py`, na chamada `EntregaService.criar(...)` dentro de `criar_enrega`, adicionar o argumento (após `versionamento=...`):

```python
                versionamento=form.cleaned_data.get('versionamento', ''),
                especificacoes=form.cleaned_data.get('especificacoes'),
            )
```

- [ ] **Step 2: Exibir as especificações na aba de Entregas**

Em `demandas/templates/tabs/entregas.html`, dentro do `<dl class="definition-list flex">` da entrega pendente, após o bloco `{% if entrega_pendente.notas %}...{% endif %}` (antes de `url_validacao`), adicionar:

```django
            {% if entrega_pendente.especificacoes.all %}
                <div class="list-item flex-basis-100">
                    <dt>Especificações entregues</dt>
                    <dd>
                        <ul>
                            {% for espec in entrega_pendente.especificacoes.all %}
                                <li>{{ espec }}</li>
                            {% endfor %}
                        </ul>
                    </dd>
                </div>
            {% endif %}
```

- [ ] **Step 3: Verificação manual**

Run: `uv run python manage.py runserver`
Verificar numa demanda em desenvolvimento/homologação: abrir "Nova entrega" (popup), marcar especificações, salvar → popup fecha, a página recarrega e a aba Entregas lista as especificações vinculadas. Confirmar que, numa demanda sem especificações no DoD, o campo não aparece.

- [ ] **Step 4: Garantir lint e suíte do arquivo de testes**

Run: `uv run ruff format demandas/views.py demandas/forms.py demandas/services.py demandas/models/entrega.py && uv run ruff check demandas/views.py demandas/forms.py demandas/services.py demandas/models/entrega.py`
Run: `uv run pytest -q demandas/tests/test_entrega_especificacao.py`
Expected: ruff "All checks passed!"; pytest todos PASS.

- [ ] **Step 5: Commit**

```bash
git add demandas/views.py demandas/templates/tabs/entregas.html
git commit -m "[demandas] Entrega: seleção e exibição de especificações na aba"
```

---

## Self-Review

- **Spec coverage:** Modelo M2M (Task 1) ✓; migration (Task 1) ✓; service (Task 2) ✓; form escopado + opcional + removido sem specs (Task 3) ✓; view + template (Task 4) ✓; testes modelo/service/form ✓. Fora de escopo (ciclo de vida, API Ninja, edição pós-criação) permanece fora — sem tasks, como desejado.
- **Placeholder scan:** sem TBD/TODO; todo passo de código mostra o código.
- **Type consistency:** `especificacoes` (M2M) / reverse `entregas` consistentes entre Tasks 1–4; `EntregaService.criar(..., especificacoes=None)` idêntico entre Task 2 e Task 4.
