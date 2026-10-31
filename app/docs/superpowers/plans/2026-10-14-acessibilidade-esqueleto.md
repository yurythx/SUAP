# Acessibilidade no esqueleto do SUAP — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Corrigir na fonte as 12 falhas WCAG do que toda tela herda (tema default, `base.html`, `render_form`, `TablePlus`) e travar regressão com um gate axe-core no e2e.

**Architecture:** O gate entra primeiro, vermelho, e mede a linha de base. As correções vêm por camada, cada uma com seu teste: tema SCSS, esqueleto (`base.html` + `main.js` + `messages.html`), formulário (`render_field`/`render_form`) e tabela. No fim o gate fica verde. Os 8 temas importam `default/{pre,post,forms}.scss`, então um diff só alcança todos.

**Tech Stack:** Django 5.2 templates, SCSS (libsass via `djtools.pipeline.LibSassCompiler`), jQuery, pytest + pytest-playwright 1.58, `axe-playwright-python` (novo, grupo `dev`).

**Spec:** `docs/superpowers/specs/2026-10-14-acessibilidade-esqueleto-design.md`

## Global Constraints

- Português (pt-BR) em identificadores, comentários, mensagens de commit e textos de UI.
- Commit no formato `[djtools] Frase no gerúndio` (ex.: `[djtools] Tornando o foco visível no tema`).
- Cor só por variável CSS (`var(--primary-700)`, `var(--grey-100)`); nunca hex; nunca `style=""`.
- Complexidade ciclomática ≤ 10 em toda função `.py` tocada. O hook `.claude/hooks/check_complexity.py` bloqueia o Edit se passar. `render_field` (12) e `render_form` (25) já passam do teto e **serão tocadas**, então a refatoração é obrigatória (Tasks 4 e 5).
- Tipar parâmetros e retorno das defs tocadas (`from __future__ import annotations` se útil).
- Ruff: linha 150, aspas simples.
- Testes unitários DB-free em `djtools/tests/<categoria>/`. Os e2e ficam em `tests/e2e/` e usam a fixture `logado` de `djtools/e2e_fixtures.py`.
- Rodar e2e exige `TEST_DATABASE_NAME` com `_e2e`: `TEST_DATABASE_NAME=test_suap_e2e DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest -m e2e --create-db tests/e2e/test_acessibilidade.py` (depois, `--reuse-db`). Se não houver Postgres local, usar o Docker do `AGENTS.md` (`docker run ... -c max_locks_per_transaction=4096 ...`).
- Unitários: `DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest -q -m "not e2e and not doc" <caminho>`.
- Compilar os temas para validar SCSS: `for t in default govbr alto_contraste luna; do uv run python -c "import sass; sass.compile(filename='djtools/static/djtools/themes/$t/main.scss')" && echo "$t ok"; done`.

## Desvio declarado da spec

A spec troca o `<h2>` do fieldset por `<legend>`. O plano usa `<legend><h3>…</h3></legend>`, por três motivos:
- A `legend` dá nome acessível ao grupo, que é o objetivo.
- O `h3` mantém a navegação por títulos do leitor de tela.
- Dezenas de e2e (`get_by_role('heading', name=…)` em edu, almoxarifado…) continuam encontrando o título, porque o papel *heading* casa qualquer nível.

Some o `h2` extra, que era a violação da regra "um único h2". O HTML permite heading dentro de `legend`.

`luna/post.scss:624` (`outline: 0` em células de calendário não focáveis) **não** é foco de teclado e fica de fora.

## Review Focus

1. **Clique de mouse não mostra anel; teclado mostra.** `:focus-visible` precisa casar só no teclado em botões e links. Teste em Task 7: `test_foco_por_teclado_e_visivel_e_clique_nao`.
2. **Widget que já traz `aria-describedby` nos `attrs`.** O id existente tem que ser preservado e concatenado, não sobrescrito. Teste em Task 4: `test_aria_describedby_existente_e_preservado`.
3. **Form com `auto_id=False` (campo sem id).** Não pode gerar `aria-describedby` apontando para id inexistente. Teste em Task 4: `test_form_sem_auto_id_nao_aponta_para_id_inexistente`.
4. **Estado da sidebar persistido na sessão (`request.session.retraido`) e tela estreita (≤ 940 px).** O `aria-expanded` precisa nascer coerente com `body.hideSidebar`. Testes em Task 7: `test_toggle_da_sidebar_anuncia_estado` e `test_tela_estreita_recolhe_a_sidebar`.
5. **Widget de múltiplas opções (`RadioSelect`) inválido.** O render não pode quebrar, e cada opção recebe `aria-invalid`. Teste em Task 4: `test_radioselect_invalido_renderiza_com_aria_invalid`.

---

### Task 1: Gate axe-core no e2e (vermelho, mede a linha de base)

**Files:**
- Modify: `pyproject.toml`, `uv.lock` (via `uv add`)
- Create: `tests/e2e/test_acessibilidade.py`

**Interfaces:**
- Produces: `tests/e2e/test_acessibilidade.py` com `TELAS: dict[str, Callable[[Page], None]]`, `REGRAS_DISPENSADAS: dict[str, str]` e `_violacoes(page) -> list[str]`. As Tasks 3 e 7 acrescentam testes neste arquivo.

- [ ] **Step 1: Adicionar a dependência**

```bash
uv add --group dev axe-playwright-python
```

Conferir a API instalada antes de escrever o teste:

```bash
uv run python -c "from axe_playwright_python.sync_playwright import Axe; import inspect; print(inspect.signature(Axe.run))"
```

Esperado: `(self, page, context=None, options=None)` ou equivalente. O retorno tem `.response['violations']`, uma lista de dicts com `id`, `impact` e `nodes[].target`. Se a API divergir, ajustar só `_violacoes`.

- [ ] **Step 2: Escrever o gate**

```python
"""Gate de acessibilidade do esqueleto: axe-core nas telas que todo módulo herda.

Por que estas telas: cada uma exercita uma camada compartilhada — início (``base.html``, menu,
rodapé), formulário com erro (``render_form``/``render_field``), listagem do admin
(changelist) e detalhe de objeto. Falha com violação ``serious``/``critical``; a mensagem
lista regra e seletor. Spec: ``docs/superpowers/specs/2026-10-14-acessibilidade-esqueleto-design.md``.
"""

from collections.abc import Callable

import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import Page

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

IMPACTOS_BLOQUEANTES = {'serious', 'critical'}

# Regra axe -> motivo. Só entra o que está FORA do esqueleto (spec, "Fora do escopo"), com motivo.
REGRAS_DISPENSADAS: dict[str, str] = {}


def _violacoes(page: Page) -> list[str]:
    resultado = Axe().run(page)
    return [
        f'{v["id"]} ({v["impact"]}): ' + ', '.join(str(no['target']) for no in v['nodes'])
        for v in resultado.response['violations']
        if v['impact'] in IMPACTOS_BLOQUEANTES and v['id'] not in REGRAS_DISPENSADAS
    ]


def _inicio(page: Page) -> None:
    page.goto('/')


def _formulario_com_erro(page: Page) -> None:
    page.goto('/djtools/give_permission/')
    page.click('input[name=atribuirpermissao_form]')


def _listagem_admin(page: Page) -> None:
    page.goto('/admin/rh/pessoajuridica/')


def _detalhe(page: Page) -> None:
    page.goto('/')
    page.click('a.user-profile')


TELAS: dict[str, Callable[[Page], None]] = {
    'inicio': _inicio,
    'formulario_com_erro': _formulario_com_erro,
    'listagem_admin': _listagem_admin,
    'detalhe': _detalhe,
}


@pytest.mark.parametrize('tela', TELAS)
def test_tela_sem_violacao_seria(logado, tela: str) -> None:
    page = logado('admin')
    TELAS[tela](page)
    page.wait_for_load_state('networkidle')
    assert _violacoes(page) == []
```

- [ ] **Step 3: Rodar e registrar a linha de base**

Run: `TEST_DATABASE_NAME=test_suap_e2e DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest -m e2e --create-db tests/e2e/test_acessibilidade.py -v 2>&1 | tee "$SCRATCH/axe-baseline.txt"`. `$SCRATCH` é o scratchpad da sessão.

Esperado: FAIL nas 4 telas, com a lista de regras (`label`, `aria-*`, `color-contrast`…). **Não** mexer em `REGRAS_DISPENSADAS` agora. A lista é o insumo da Task 7.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock tests/e2e/test_acessibilidade.py
git commit -m "[djtools] Adicionando o gate axe-core de acessibilidade no e2e"
```

---

### Task 2: Tema — foco visível, skip links, movimento reduzido, readonly, legend

**Files:**
- Modify: `djtools/static/djtools/themes/default/post.scss` (regra `a` ~linha 89-91; `#accesskeys` ~linha 477; `#mobilemenu` ~linha 961; fim do arquivo)
- Modify: `djtools/static/djtools/themes/default/forms.scss` (`input` ~linha 78-79; bloco `form { fieldset { > { h2, h3, h5 … } } }` linhas 1-13)
- Modify: `djtools/static/djtools/themes/default/pre.scss` (`%module-info-button`, linhas 1470-1472)

**Interfaces:**
- Produces: a classe `.toggleSidebar` estilizada também como `button` (consumida pela Task 3), e `form fieldset > legend > h3` estilizado como título de fieldset (consumido pela Task 5).

- [ ] **Step 1: Remover os `outline: 0` que escondem o foco**

Em `post.scss`, regra `a { … }`, apagar só a linha `    outline: 0 none;`.
Em `forms.scss`, regra `input { … }`, apagar só a linha `    outline: 0 none;`.
Em `pre.scss`, dentro de `%module-info-button`, apagar o bloco inteiro:

```scss
    &:focus-visible {
        outline: 0 none;
    }
```

- [ ] **Step 2: Skip links visíveis no foco**

Substituir em `post.scss`:

```scss
#accesskeys {
    position: absolute;
    left: -9999px;
}
```

por:

```scss
#accesskeys {
    position: absolute;
    left: -9999px;
    a:focus {
        background-color: var(--white);
        border-radius: var(--border-radius);
        color: var(--primary-700);
        left: 1rem;
        padding: 1rem 1.5rem;
        position: fixed;
        top: 1rem;
        z-index: 10001;
    }
}
```

(`10001` fica acima do `#mobilemenu`, que usa `z-index: 10000`.)

- [ ] **Step 3: Botão de toggle no menu mobile herda a cor dos links**

Em `post.scss`, dentro de `#mobilemenu { … }`, trocar o seletor `    a {` por `    a,\n    button.toggleSidebar {`, deixando o corpo como está. O resultado:

```scss
    a,
    button.toggleSidebar {
        color: var(--mobile-menu-color);
        font-size: 2rem;
        &.error {
            color: var(--danger);
        }
    }
```

- [ ] **Step 4: Anel de foco, movimento reduzido, readonly e reset do botão (fim de `post.scss`)**

Acrescentar ao fim de `post.scss`:

```scss
// Acessibilidade (WCAG 2.4.7, 2.3.3, 1.4.3): foco só por teclado, movimento reduzido e readonly por token.
:focus-visible {
    outline: 2px solid var(--primary-700);
    outline-offset: 2px;
}
@media (prefers-reduced-motion: reduce) {
    *,
    *::before,
    *::after {
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        scroll-behavior: auto !important;
        transition-duration: 0.01ms !important;
    }
}
input[readonly],
textarea[readonly] {
    background-color: var(--grey-100);
}
button.toggleSidebar {
    padding: 0;
}
```

- [ ] **Step 5: `legend` do fieldset com o visual do antigo título**

Em `forms.scss`, no bloco do topo:

```scss
form {
    …
    fieldset {
        > {
            h2,
            h3,
            h5 {
                @extend %fieldset-title;
            }
        }
```

acrescentar logo depois do `> { … }`, dentro de `fieldset {`:

```scss
        > legend {
            float: left;
            font-size: inherit;
            line-height: inherit;
            margin: 0;
            padding: 0;
            width: 100%;
            > h3 {
                @extend %fieldset-title;
            }
        }
```

(`float: left; width: 100%` evita que a `legend` caia sobre a borda do fieldset; o reboot do Bootstrap já aplica `legend + * { clear: left }`.)

- [ ] **Step 6: Compilar os temas**

Run: `for t in default govbr alto_contraste luna; do uv run python -c "import sass; sass.compile(filename='djtools/static/djtools/themes/$t/main.scss')" && echo "$t ok"; done`
Esperado: `default ok`, `govbr ok`, `alto_contraste ok`, `luna ok`.

- [ ] **Step 7: Commit**

```bash
git add djtools/static/djtools/themes/default/
git commit -m "[djtools] Tornando o foco visível e os atalhos de teclado acessíveis no tema"
```

---

### Task 3: Esqueleto — toggle como botão, rótulos, landmarks, mensagens anunciadas

**Files:**
- Modify: `comum/templates/admin/base.html` (linhas 66-69, 122-123, 151-152, 156, 167-168, 194-198, 310-312)
- Modify: `comum/static/comum/js/main.js` (handler `.toggleSidebar`, linhas 45-70)
- Modify: `djtools/templates/components/messages.html`
- Test: `djtools/tests/templatetags/tags/test_mensagens.py`

**Interfaces:**
- Consumes: `button.toggleSidebar` estilizado (Task 2).
- Produces: `#toggleSidebar` e `#mobilemenu .toggleSidebar` com `aria-expanded` sincronizado com `body.hideSidebar`; `aside#menu-lateral`; `nav#breadcrumbs`. A Task 7 testa esses ids.

- [ ] **Step 1: Teste das mensagens (falha)**

```python
"""Mensagens do esqueleto anunciadas a leitor de tela: erro interrompe, o resto é status."""

import pytest
from django.contrib import messages
from django.contrib.messages.storage.base import Message
from django.template.loader import render_to_string

TEMPLATE = 'djtools/templates/components/messages.html'


@pytest.mark.parametrize(
    ('nivel', 'classe', 'role'),
    [
        (messages.ERROR, 'alert', 'alert'),
        (messages.SUCCESS, 'alert', 'status'),
        (messages.INFO, 'errornote', 'alert'),
    ],
)
def test_mensagem_anuncia_com_role_conforme_gravidade(nivel: int, classe: str, role: str) -> None:
    html = render_to_string(TEMPLATE, {'messages': [Message(nivel, 'Texto.')], 'classe': classe})
    assert f'role="{role}"' in html
```

Criar `djtools/tests/templatetags/tags/__init__.py` se não existir.

- [ ] **Step 2: Rodar e ver falhar**

Run: `DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest -q djtools/tests/templatetags/tags/test_mensagens.py`
Esperado: 3 FAIL (`role=` ausente).

- [ ] **Step 3: `messages.html` com `role`**

```django
{% for message in messages %}
    <p class="{{ classe }} alert-{% if message.tags %}{{ message.tags }}{% endif %}"{% if id %} id="{{ id }}"{% endif %} role="{% if classe == 'errornote' or 'error' in message.tags %}alert{% else %}status{% endif %}">
        {{ message|safe_message }}
        <button type="button" class="btn btn-close">{% icone "times" %}<span class="visually-hidden">Fechar</span></button>
    </p>
{% endfor %}
```

- [ ] **Step 4: Rodar e ver passar**

Mesmo comando do Step 2. Esperado: 3 passed.

- [ ] **Step 5: `base.html` — toggle, label, landmarks, breadcrumb**

Linha 122:

```django
            <button type="button" id="toggleSidebar" class="toggleSidebar" aria-controls="menu-lateral" aria-expanded="{% if request.session.retraido %}false{% else %}true{% endif %}">{% icone "chevron-left" %} <span class="visually-hidden">Mostrar/Esconder barra lateral</span></button>
            <aside class="nav" id="menu-lateral">
```

Linhas 151-152:

```django
                    <form id="__buscar_menu__" action="" onsubmit="return false;" class="buscar_menu" role="search">
                        <label for="__filterinput__" class="visually-hidden">Buscar menu</label>
                        <input type="search" placeholder="Buscar menu" id="__filterinput__" {% block buscar_menu %}{% endblock %} />
```

Linha 156: `<nav id="mainmenu" aria-label="Menu principal">`.

Linha 168:

```django
                <button type="button" class="toggleSidebar" title="Mostrar/esconder barra lateral" aria-controls="menu-lateral" aria-expanded="{% if request.session.retraido %}false{% else %}true{% endif %}">{% icone "bars" %}<span class="visually-hidden">Mostrar/esconder barra lateral</span></button>
```

Linhas 194-198:

```django
        <nav id="breadcrumbs" aria-label="Trilha de navegação">
            {% for title, url in breadcrumbs %}
                <a href="{{ url }}"{% if forloop.last %} aria-current="page"{% endif %}>{{ title }}</a>
            {% endfor %}
        </nav>
```

Antes de salvar, conferir que nenhuma regra de `nav` genérica passa a pegar o breadcrumb: `git grep -nE "(^|[ ,>])nav( |\{|,|>|\.|:)" -- 'djtools/static/djtools/themes/**/*.scss' | grep -v "nav\.\|aside\|#mainmenu\|toplinks"`. Se aparecer regra de elemento `nav` solta, prefixar com `aside` nesse arquivo.

- [ ] **Step 6: `base.html` — trocar o sniff de user-agent por media query e remover o `#eee`**

Linhas 66-69 viram:

```javascript
    /* Menu principal: telas estreitas (mesmo breakpoint do layout em post.scss) começam recolhidas */
    if (window.matchMedia("(max-width: 940px)").matches) {
        jQuery("body").addClass("hideSidebar");
        jQuery(".toggleSidebar").attr("aria-expanded", "false");
    }
```

Apagar as linhas 310-312 (o comentário `// adicionar uma cor padrão…` e as duas chamadas `.css('background-color', '#eee')`). A regra `input[readonly]` da Task 2 cobre isso.

- [ ] **Step 7: `main.js` — sincronizar `aria-expanded`**

No handler `jQuery(".toggleSidebar").click(…)`, logo depois de `jQuery("body").toggleClass("hideSidebar");`, acrescentar:

```javascript
        jQuery(".toggleSidebar").attr("aria-expanded", String(!jQuery("body").hasClass("hideSidebar")));
```

- [ ] **Step 8: djLint nos templates tocados**

Run: `uv run pre-commit run djlint-django --files comum/templates/admin/base.html djtools/templates/components/messages.html` (se o id do hook divergir, `uv run pre-commit run --files <arquivos>`).
Esperado: Passed.

- [ ] **Step 9: Commit**

```bash
git add comum/templates/admin/base.html comum/static/comum/js/main.js djtools/templates/components/messages.html djtools/tests/templatetags/tags/
git commit -m "[djtools] Anunciando estado, rótulos e mensagens do esqueleto para tecnologia assistiva"
```

---

### Task 4: `render_field` liga erro e ajuda ao widget (e cai para C901 ≤ 10)

**Files:**
- Modify: `djtools/forms/utils/__init__.py:135-192` (`render_field`)
- Test: `djtools/tests/models/test_render_field_acessivel.py`

**Interfaces:**
- Produces: `render_field(form: forms.BaseForm, field_name: str) -> SafeString`, com a assinatura de hoje. Para campo visível o HTML é `erros + label + widget + ajuda`, com `<ul class="errorlist" id="{id}_erro">`, `<p class="help" id="{id}_ajuda">` e o widget com `aria-describedby`/`aria-invalid`. A Task 5 consome `render_field` sem mudança.
- Helpers novos (privados): `_label_do_campo(form, bf) -> str` e `_widget_acessivel(bf, erros, ajuda) -> tuple[str, str, str]`.

- [ ] **Step 1: Testes (falham)**

```python
"""``render_field`` liga erro e ajuda ao widget (WCAG 1.3.1, 3.3.1) — DB-free."""

from django import forms

from djtools.forms.utils import render_field


class _Form(forms.Form):
    nome = forms.CharField(help_text='Nome completo.')
    apelido = forms.CharField(required=False, help_text='Opcional.', widget=forms.TextInput(attrs={'aria-describedby': 'dica_externa'}))
    turno = forms.ChoiceField(choices=[('m', 'Manhã'), ('t', 'Tarde')], widget=forms.RadioSelect)


def test_campo_invalido_liga_erro_e_ajuda_ao_widget() -> None:
    html = render_field(_Form(data={}), 'nome')
    assert 'aria-invalid="true"' in html
    assert 'aria-required="true"' in html
    assert 'aria-describedby="id_nome_erro id_nome_ajuda"' in html
    assert '<ul class="errorlist" id="id_nome_erro">' in html
    assert '<p class="help" id="id_nome_ajuda">Nome completo.</p>' in html


def test_campo_valido_aponta_so_para_a_ajuda() -> None:
    html = render_field(_Form(data={'nome': 'Ana', 'turno': 'm'}), 'nome')
    assert 'aria-invalid' not in html
    assert 'errorlist' not in html
    assert 'aria-describedby="id_nome_ajuda"' in html


def test_aria_describedby_existente_e_preservado() -> None:
    html = render_field(_Form(data={'nome': 'Ana', 'turno': 'm'}), 'apelido')
    assert 'aria-describedby="dica_externa id_apelido_ajuda"' in html


def test_form_sem_auto_id_nao_aponta_para_id_inexistente() -> None:
    html = render_field(_Form(data={}, auto_id=False), 'nome')
    assert 'aria-invalid="true"' in html
    assert 'aria-describedby' not in html
    assert '_erro' not in html


def test_radioselect_invalido_renderiza_com_aria_invalid() -> None:
    html = render_field(_Form(data={}), 'turno')
    assert html.count('aria-invalid="true"') == 2  # uma por opção
    assert 'aria-required' not in html  # proibido em role=radio
    assert 'id="id_turno_erro"' in html


def test_campo_oculto_sai_sem_label_nem_ajuda() -> None:
    class _ComOculto(forms.Form):
        token = forms.CharField(widget=forms.HiddenInput, help_text='não aparece')

    html = render_field(_ComOculto(), 'token')
    assert html.startswith('<input type="hidden"')
    assert 'help' not in html
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest -q djtools/tests/models/test_render_field_acessivel.py`
Esperado: os 4 primeiros e o RadioSelect FAIL (sem `aria-*`/ids); `test_campo_oculto…` PASS.

- [ ] **Step 3: Implementar (substitui `render_field` inteira)**

Remove código morto: `errors_on_separate_row` era sempre `False`, `top_errors` nunca era emitido e `row_ender` não tem uso sem tabela. Isso derruba a complexidade de 12.

```python
def _label_do_campo(form: forms.BaseForm, bf: BoundField) -> str:
    if not bf.label:
        return ''
    label = conditional_escape(force_str(bf.label))
    # Só acrescenta o sufixo se o label não terminar em pontuação.
    if form.label_suffix and label[-1] not in ':?.!':
        label += form.label_suffix
    return bf.label_tag(label) or ''


def _widget_acessivel(bf: BoundField, erros: list[str], ajuda: str) -> tuple[str, str, str]:
    """Devolve ``(erros_html, widget_html, ajuda_html)`` com o widget apontando, via
    ``aria-describedby``, para os ids do erro e da ajuda — só quando o campo tem id."""
    widget = bf.field.widget
    id_ = widget.attrs.get('id') or bf.auto_id
    id_erro = f'{id_}_erro' if id_ and erros else ''
    id_ajuda = f'{id_}_ajuda' if id_ and ajuda else ''
    attrs: dict[str, str] = {}
    descritores = ' '.join(filter(None, [widget.attrs.get('aria-describedby'), id_erro, id_ajuda]))
    if descritores:
        attrs['aria-describedby'] = descritores
    # Sem o atributo `required` nativo: ele dispararia a validação do browser antes da do servidor.
    # Radio/checkbox múltiplo ficam de fora: aria-required não é permitido em role=radio (axe aria-allowed-attr).
    if bf.field.required and not isinstance(widget, forms.RadioSelect):
        attrs['aria-required'] = 'true'
    erros_html = ''
    if erros:
        attrs['aria-invalid'] = 'true'
        itens = ''.join(f'<li>{erro}</li>' for erro in erros)
        erros_html = f'<ul class="errorlist"{flatatt({"id": id_erro} if id_erro else {})}>{itens}</ul>'
    ajuda_html = f'<p class="help"{flatatt({"id": id_ajuda} if id_ajuda else {})}>{ajuda}</p>' if ajuda else ''
    widget_html = bf.as_widget(attrs=attrs)
    if bf.field.show_hidden_initial:
        widget_html += bf.as_hidden(only_initial=True)
    return erros_html, widget_html, ajuda_html


def render_field(form: forms.BaseForm, field_name: str) -> SafeString:
    """Renderiza erros, label, widget e ajuda de um campo, ligados por ``aria-describedby``."""
    field = form.fields[field_name]
    if hasattr(field, 'reload'):
        field.reload()
    bf = BoundField(form, field, field_name)
    if bf.is_hidden:
        return mark_safe(str(bf))
    erros = [conditional_escape(erro) for erro in bf.errors]
    ajuda = force_str(field.help_text) if field.help_text else ''
    erros_html, widget_html, ajuda_html = _widget_acessivel(bf, erros, ajuda)
    return mark_safe(f'{erros_html}{_label_do_campo(form, bf)}{widget_html}{ajuda_html}')
```

Acrescentar `SafeString` ao import existente: `from django.utils.safestring import SafeString, mark_safe`.

- [ ] **Step 4: Rodar e ver passar + complexidade**

Run: `DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest -q djtools/tests/models/test_render_field_acessivel.py`
Esperado: 6 passed.

Run: `uv run ruff check --select C901 --config 'lint.mccabe.max-complexity=10' djtools/forms/utils/__init__.py | grep -E "render_field|_label_do_campo|_widget_acessivel"`
Esperado: nenhuma linha.

- [ ] **Step 5: Regressão dos testes do djtools**

Run: `DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest -q -m "not e2e and not doc" djtools`
Esperado: tudo verde.

- [ ] **Step 6: Commit**

```bash
git add djtools/forms/utils/__init__.py djtools/tests/models/test_render_field_acessivel.py
git commit -m "[djtools] Ligando erro e ajuda ao campo via aria-describedby no render_field"
```

---

### Task 5: `render_form` com `<legend>` (refatorado para C901 ≤ 10 sob harness de caracterização)

**Files:**
- Modify: `djtools/forms/utils/__init__.py:195-305` (`render_form`)
- Modify: `djtools/e2e_ui.py:278` (xpath do fieldset, mudança aditiva)
- Create (temporário, fora do repo): `$SCRATCH/caracteriza_render_form.py`
- Test: `djtools/tests/models/test_render_field_acessivel.py` (acrescenta 1 teste)

**Interfaces:**
- Consumes: `render_field` (Task 4); `form fieldset > legend > h3` estilizado (Task 2).
- Produces: `render_form(form) -> SafeString`, com a assinatura de hoje. Fieldset nomeado vira `<legend><h3>{nome}</h3></legend>`.

- [ ] **Step 1: Harness de caracterização (captura antes)**

`$SCRATCH/caracteriza_render_form.py`:

```python
"""Prova que a refatoração de render_form só troca <h2>X</h2> por <legend><h3>X</h3></legend>."""

import json
import os
import re
from pathlib import Path

from django import forms

from djtools.forms.utils import render_form

SAIDA = Path(__file__).with_name('render_form_antes.json')


class Simples(forms.Form):
    nome = forms.CharField(help_text='Ajuda.')
    oculto = forms.CharField(widget=forms.HiddenInput, required=False)


class ComFieldsets(forms.Form):
    INFO = 'Informação.'
    ALERT = 'Alerta.'
    CRITICAL = 'Crítico.'
    a = forms.CharField()
    b = forms.CharField(required=False)
    c = forms.IntegerField()
    oculto = forms.CharField(widget=forms.HiddenInput, required=False)
    fieldsets = (
        ('Dados', {'fields': ('a', ('b', 'c'), 'inexistente', 'oculto'), 'classes': ('x', 'y'), 'description': 'Desc.'}),
        (None, {'fields': ('c',)}),
    )

    def clean(self):
        raise forms.ValidationError('Erro geral.')


CASOS = {
    'simples_vazio': lambda: Simples(),
    'simples_invalido': lambda: Simples(data={}),
    'fieldsets_vazio': lambda: ComFieldsets(),
    'fieldsets_invalido': lambda: ComFieldsets(data={'a': '', 'c': 'x'}),
}


def _normaliza(html: str) -> str:
    # Única diferença aceita: o título do fieldset (a captura roda depois da Task 4).
    return re.sub(r'<h2>(.*?)</h2>', r'<legend><h3>\1</h3></legend>', html)


def test_caracterizacao() -> None:
    atual = {nome: str(render_form(fabrica())) for nome, fabrica in CASOS.items()}
    if os.environ.get('MODO') == 'capturar':
        SAIDA.write_text(json.dumps({k: _normaliza(v) for k, v in atual.items()}, ensure_ascii=False, indent=1))
        return
    antes = json.loads(SAIDA.read_text())
    for nome in CASOS:
        assert atual[nome] == antes[nome], nome
```

Run (captura, **antes** de editar `render_form`): `MODO=capturar DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest -q --rootdir=. -c pyproject.toml -p no:cacheprovider "$SCRATCH/caracteriza_render_form.py"`
Esperado: 1 passed; `render_form_antes.json` criado com 4 chaves. (`'inexistente'` é string solta de propósito: é o caso que `render_form` pula em silêncio.)

- [ ] **Step 2: Teste do `legend` (falha)**

Acrescentar em `djtools/tests/models/test_render_field_acessivel.py`:

```python
from djtools.forms.utils import render_form


def test_fieldset_nomeado_vira_legend_com_h3() -> None:
    class _ComFieldset(forms.Form):
        nome = forms.CharField()
        fieldsets = (('Dados pessoais', {'fields': ('nome',)}),)

    html = render_form(_ComFieldset())
    assert '<legend><h3>Dados pessoais</h3></legend>' in html
    assert '<h2>' not in html
```

Run: `DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest -q djtools/tests/models/test_render_field_acessivel.py::test_fieldset_nomeado_vira_legend_com_h3`
Esperado: FAIL.

- [ ] **Step 3: Refatorar `render_form` (substitui a função inteira, mantendo a docstring)**

```python
def _campos_visiveis(form: forms.BaseForm) -> list[str]:
    """Campos do form sem ``fieldsets``: respeita ``Meta.fields``/``Meta.exclude`` para campos de model."""
    meta = getattr(form, '_meta', None)
    include_fields = meta.fields if meta and meta.fields else None
    exclude_fields = meta.exclude if meta and meta.exclude else None
    model = getattr(meta, 'model', None)
    model_fields = [model_field.name for model_field in model._meta.fields] if hasattr(model, '_meta') else None
    campos = []
    for nome_campo in list(form.fields.keys()):
        if model_fields and nome_campo in model_fields:
            if include_fields and nome_campo not in include_fields or exclude_fields and nome_campo in exclude_fields:
                continue
        campos.append(nome_campo)
    return campos


def _avisos(form: forms.BaseForm) -> list[str]:
    out = []
    if hasattr(form, 'INFO'):
        out.append(f'<div class="alert alert-info"><strong>Atenção: </strong>{form.INFO}</div>')
    if hasattr(form, 'ALERT'):
        out.append(f'<div class="alert alert-warning"><strong>Atenção: </strong>{form.ALERT}</div>')
    if hasattr(form, 'CRITICAL'):
        out.append(f'<div class="alert alert-danger"><strong>Atenção: </strong>{form.CRITICAL}</div>')
    if form.non_field_errors():
        out.append('<ul class="errorlist">')
        out.extend(f'<li>{error}</li>' for error in form.non_field_errors())
        out.append('</ul>')
    return out


def _caixa_do_campo(form: forms.BaseForm, linha: list[str], field_name: str) -> str:
    if field_name not in form.fields:
        raise KeyError(f'Field "{field_name}" not in form.')
    field_classes = []
    if len(linha) > 1:
        field_classes.append('field-box')
    field_classes.append('field-box-first' if field_name is linha[0] else 'field-box-later')
    if form.fields[field_name].required:
        field_classes.append('required')
    return f'<div class="{" ".join(field_classes)}">{render_field(form, field_name)}</div>'


def _linha(form: forms.BaseForm, line: str | Sequence[str]) -> str:
    if isinstance(line, str):
        field = form.fields.get(line)
        if field is None:
            return ''
        if isinstance(field.widget, forms.HiddenInput):
            # Hidden field has no div.form-row
            return render_field(form, line)
        line = [line]
    error_class = ''
    for field_name in line:
        try:
            if form.errors.get(field_name, form.error_class()):
                error_class = 'errors'
        except Exception:
            pass
    caixas = ''.join(_caixa_do_campo(form, line, field_name) for field_name in line)
    return f'<div class="form-row {" ".join(line)} {error_class}">{caixas}</div>'


def _fieldset(form: forms.BaseForm, fieldset_name: str | None, options: Mapping) -> str:
    classes = ' '.join(options.get('classes', ()))
    out = [f'<fieldset class="module aligned {classes}">']
    if fieldset_name:
        out.append(f'<legend><h3>{fieldset_name}</h3></legend>')
    fieldset_description = options.get('description', None)
    if fieldset_description:
        out.append(f'<div class="description">{fieldset_description}</div>')
    out.extend(_linha(form, line) for line in options['fields'])
    out.append('</fieldset>')
    return ''.join(out)


def render_form(form: forms.BaseForm) -> SafeString:
    """(manter a docstring atual, com o exemplo de fieldsets)"""
    fieldsets = form.fieldsets if hasattr(form, 'fieldsets') else [(None, {'fields': _campos_visiveis(form)})]
    out = _avisos(form)
    out.extend(_fieldset(form, nome, options) for nome, options in fieldsets)
    return mark_safe(''.join(out))
```

Imports no topo: `from collections.abc import Mapping, Sequence`. Ao colar, trocar a linha `"""(manter a docstring atual…)"""` pela docstring original de `render_form`, sem mudança.

- [ ] **Step 4: Harness compara (depois)**

Run: `DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest -q --rootdir=. -c pyproject.toml -p no:cacheprovider "$SCRATCH/caracteriza_render_form.py"`
Esperado: 1 passed (HTML idêntico ao capturado, a menos da troca de título normalizada).

**Atenção:** a captura do Step 1 roda **depois** da Task 4. O HTML capturado já tem os `aria-*` de `render_field`, então a comparação isola só a refatoração de `render_form`.

- [ ] **Step 5: Testes + complexidade**

Run: `DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest -q djtools/tests/models/test_render_field_acessivel.py`
Esperado: 7 passed.

Run: `uv run ruff check --select C901 --config 'lint.mccabe.max-complexity=10' djtools/forms/utils/__init__.py | grep -vE "show_form_data"`
Esperado: só `All checks passed` ou nada além de `show_form_data` (não tocada).

- [ ] **Step 6: `e2e_ui.py` — o quadro do fieldset reconhece `legend`**

Linha 278, de:

```python
        fieldset = f'//fieldset[contains(@class, "module") and h2[contains(normalize-space(.), "{nome}")]]'
```

para:

```python
        fieldset = f'//fieldset[contains(@class, "module") and (h2 | legend)[contains(normalize-space(.), "{nome}")]]'
```

Run: `DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest -q djtools/tests/models/test_e2e_ui.py`
Esperado: verde.

- [ ] **Step 7: Varredura de dependentes do `<h2>` de fieldset**

Run: `git grep -nE "fieldset[^,{;]*h2|'heading', name=" -- '*/tests/e2e/*.py' '*/tests/doc/*.py' djtools/e2e_ui.py | head -50`

Para cada `get_by_role('heading', name=X)`: se `X` for título de fieldset de `FormPlus`, continua casando, porque o `h3` é heading. Nenhuma ação, salvo se o teste fixar `level=2`: `git grep -n "level=2" -- '*/tests/e2e/*.py'`. Esperado: vazio. Se não estiver vazio, rodar a suíte daquele módulo.

- [ ] **Step 8: Commit**

```bash
git add djtools/forms/utils/__init__.py djtools/e2e_ui.py djtools/tests/models/test_render_field_acessivel.py
git commit -m "[djtools] Nomeando os fieldsets do render_form com legend"
```

---

### Task 6: `TablePlus` com cabeçalho de coluna explícito

**Files:**
- Modify: `comum/templates/table_plus.html:23,27`

- [ ] **Step 1: `scope="col"` nos dois `<th>`**

```django
                            <th scope="col" {{ column.attrs.th.as_html }}><a
                                    href="{% querystring table.prefixed_order_by_field=column.order_by_alias.next %}">{{ column.header }}</a>
                            </th>
                        {% else %}
                            <th scope="col" {{ column.attrs.th.as_html }}>{{ column.header }}</th>
```

Antes, conferir que nenhuma coluna já injeta `scope` (atributo duplicado é HTML inválido): `git grep -n "'scope'" -- '*.py' | grep -i "attrs\|th"`. Esperado: vazio.

- [ ] **Step 2: Commit**

```bash
git add comum/templates/table_plus.html
git commit -m "[djtools] Declarando o escopo dos cabeçalhos do TablePlus"
```

---

### Task 7: Gate verde + comportamentos de teclado e sidebar

**Files:**
- Modify: `tests/e2e/test_acessibilidade.py`

**Interfaces:**
- Consumes: `#accesskeys`, `#toggleSidebar`, `#mobilemenu .toggleSidebar`, `#topodapagina` (Tasks 2 e 3).

- [ ] **Step 1: Testes de comportamento (acrescentar ao arquivo)**

```python
import re

from playwright.sync_api import expect


def test_foco_por_teclado_e_visivel_e_clique_nao(logado) -> None:
    page = logado('admin')
    page.goto('/')
    page.keyboard.press('Tab')
    atalho = page.locator('#accesskeys a').first
    expect(atalho).to_be_focused()
    assert atalho.evaluate('e => getComputedStyle(e).outlineStyle') != 'none'
    assert atalho.bounding_box()['x'] >= 0  # o skip link aparece na tela

    botao = page.locator('#topodapagina')
    botao.click()
    assert botao.evaluate("e => e.matches(':focus-visible')") is False


def test_toggle_da_sidebar_anuncia_estado(logado) -> None:
    page = logado('admin')
    page.set_viewport_size({'width': 1280, 'height': 900})
    page.goto('/')
    botao = page.locator('#toggleSidebar')
    expect(botao).to_have_attribute('aria-expanded', 'true')
    with page.expect_response('**/comum/retrair_menu/'):
        botao.click()
    expect(botao).to_have_attribute('aria-expanded', 'false')
    # Restaura: o estado vai para a sessão do admin, que os outros testes compartilham.
    with page.expect_response('**/comum/expandir_menu/'):
        botao.click()
    expect(botao).to_have_attribute('aria-expanded', 'true')


def test_tela_estreita_recolhe_a_sidebar(logado) -> None:
    page = logado('admin')
    page.set_viewport_size({'width': 375, 'height': 800})
    page.goto('/')
    expect(page.locator('body')).to_have_class(re.compile(r'\bhideSidebar\b'))
    expect(page.locator('#mobilemenu .toggleSidebar')).to_have_attribute('aria-expanded', 'false')
```

(Mover `import re` e o `from playwright.sync_api import expect` para o topo, junto dos outros imports.)

- [ ] **Step 2: Rodar a suíte inteira do arquivo**

Run: `TEST_DATABASE_NAME=test_suap_e2e DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest -m e2e --reuse-db tests/e2e/test_acessibilidade.py -v 2>&1 | tee "$SCRATCH/axe-depois.txt"`

Esperado: os 3 testes de comportamento passam. Nas 4 telas do axe, comparar com `axe-baseline.txt`.

- [ ] **Step 3: Triagem do que restou no axe (decisão por regra)**

Para cada regra ainda listada:
- **Origem no esqueleto** (seletor em `base.html`, `#mainmenu`, `#footer`, `form.html`, `render_field`, `table_plus`, `messages`): corrigir no arquivo de origem, seguindo o padrão das Tasks 2-6, e rodar de novo.
- **Origem fora do esqueleto** (lib de terceiro como select2; template do módulo da tela, ex. `djtools/templates/give_permission.html`; contraste de token do tema que pede decisão do time de design): incluir em `REGRAS_DISPENSADAS` com o motivo e o seletor, ex.:

```python
REGRAS_DISPENSADAS: dict[str, str] = {
    'color-contrast': 'token --grey-500 em .help: ajuste de paleta é do time do design system (fora do escopo da v1)',
}
```

Uma regra dispensada vale para as 4 telas. Se ela também ocorrer no esqueleto, **não** dispensar: corrigir.

- [ ] **Step 4: Gate verde**

Mesmo comando do Step 2. Esperado: todos passed.

- [ ] **Step 5: Screenshots para o MR**

Acrescentar temporariamente (não commitar) um teste em `$SCRATCH` ou rodar no shell do Playwright: login como `admin` e captura de `/` com foco por Tab no primeiro link do menu, e de `/djtools/give_permission/` com erro, nos temas default, Alto Contraste e GovBR. O tema muda em `/comum/temas/`. Salvar em `$SCRATCH/screenshots/`. O foco precisa estar visível em todos, e a `legend` do fieldset precisa ter o mesmo visual do título antigo. Referência: a mesma tela capturada na `master` (outro worktree) ou em produção.

- [ ] **Step 6: Commit**

```bash
git add tests/e2e/test_acessibilidade.py
git commit -m "[djtools] Fechando o gate de acessibilidade do esqueleto"
```

---

### Task 8: Paridade com o CI

- [ ] **Step 1: pre-commit como o CI**

Run: `uv run pre-commit run --from-ref origin/master --to-ref HEAD`
Esperado: tudo Passed. Se o `ruff format` reescrever algo, commitar com `[djtools] Formatando`.

- [ ] **Step 2: Unitários do djtools e do comum**

Run: `DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest -q -m "not e2e and not doc" djtools comum`
Esperado: verde.

- [ ] **Step 3: e2e transversal inteiro**

Run: `TEST_DATABASE_NAME=test_suap_e2e DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest -m e2e --reuse-db tests/e2e`
Esperado: verde. Cobre login, formulário, cadastro e o resto do esqueleto sob o HTML novo.
