# Modernização — fase 2: componentes centrais — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modernizar botão secundário (A), campos de formulário (B), mensagens (B) e abas/caixas (A) por tokens CSS no tema default, preservando os temas que já têm valor próprio.

**Architecture:** Cada componente ganha tokens no `:root` do `default/pre.scss` e regras que os leem. Temas com valor próprio recebem linhas de preservação no próprio `:root` (padrão da fase 1). Um e2e trava cada componente numa tela real; uma medição base×HEAD nos 8 temas prova que nada mudou fora do alcance da spec; screenshots fecham.

**Tech Stack:** SCSS (libsass via `djtools.pipeline.LibSassCompiler`), Bootstrap 5.3, select2, pytest + Playwright.

**Spec:** `docs/superpowers/specs/2026-10-15-modernizacao-fase2-componentes-design.md`

## Global Constraints

- Tema versionado em `djtools/static/djtools/themes/<tema>/` (o `static/` da raiz é saída gitignored; nunca editar lá).
- Ordem de import de cada tema: `default/colors.css` → `<tema>/colors.scss` → `default/variables.scss` → `<tema>/variables.scss` → `default/pre.scss` → `<tema>/pre.scss` → `default/post.scss` → `default/forms.scss` → `<tema>/post.scss`.
- Cor só por variável CSS; nada de hex em código novo; nada de `style=""` em template.
- Tokens novos no `:root` do `default/pre.scss`, perto dos existentes do mesmo assunto.
- Temas que já têm valor próprio mantêm o seu (tabela "Alcance por tema" da spec).
- pt-BR em comentários e commits; commit `[djtools] Frase no gerúndio`; sem linhas de atribuição.
- Compilar os 8 temas: `for t in default govbr alto_contraste luna aurora dunas ifs modo_daltonismo; do uv run python -c "import sass; sass.compile(filename='djtools/static/djtools/themes/$t/main.scss')" && echo "$t ok"; done`.
- e2e: `TEST_DATABASE_NAME=test_suap_e2e DATABASE_PORT=5434 DATABASE_USER=postgres DATABASE_PASSWORD=postgres DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest -m e2e --reuse-db <arquivos>` (container `suap-test-db-axe`; `docker start suap-test-db-axe` se parado).
- Medição fora do Django: injetar `djtools/static/djtools/themes/default/colors.css` ANTES do CSS compilado (o `@import "colors.css"` não resolve em página sintética).
- Contraste: texto ≥ 4,5:1; limite de componente (borda que identifica o campo) ≥ 3:1.

## Esclarecimento da spec (botão secundário)

A spec diz "só o `.btn` sem variante muda" e lista `--btn-color → var(--white)`. Mas `%btn` (que usa `--btn-color`) também estiliza `input[type="submit"]`, `.add-row a`, `.deletelink` etc. **sem** a classe `.btn` — 197 templates têm `type="submit"` e só ≈75 deles usam `.btn`; o submit genérico (ex.: `give_permission.html`, "Confirmar") ficaria em contorno branco e perderia peso de ação principal. Por isso o plano **não** muda `--btn-color`: cria `--btn-secondary-color` e uma regra própria para `.btn` sem variante, com `:where()` (especificidade (0,1,1)), de modo que variantes, `.disabled` e regras de tema continuam vencendo e o submit genérico mantém o preenchimento escuro.

## Review Focus

1. **Submit genérico** (`input[type="submit"]` sem `.btn`) continua escuro e preenchido — Task 1 testa um `input[type=submit]` sem `.btn` de uma tela real.
2. **Botão de variante no hover** (ex.: `.btn.danger`) não ganha contorno cinza — Task 1 testa.
3. **Foco por teclado** em botão secundário, campo e aba continua visível — Tasks 1-3 testam (`:focus-visible` da fase 1 e anel do campo).
4. **Temas com valor próprio** não mudam em botão/campo/aba/caixa — Task 4 mede base×HEAD nos 8 temas.
5. **select2** (campo de múltipla escolha) acompanha o campo novo sem borda dupla — Task 2 testa no `give_permission`.

---

### Task 1: Botão secundário em contorno (componente 1, direção A)

**Files:**
- Modify: `djtools/static/djtools/themes/default/pre.scss` (`:root`, bloco `// Button Colors`)
- Modify: `djtools/static/djtools/themes/default/forms.scss` (logo após o bloco `.btn.warning { ... }` da seção `// Button Colors`, ~linha 1080)
- Modify: `djtools/static/djtools/themes/{aurora,dunas,govbr,ifs,luna,alto_contraste}/pre.scss` (`:root`)
- Create: `tests/e2e/test_tema_componentes.py`

**Interfaces:**
- Produces: tokens `--btn-secondary-color`, `--btn-secondary-text-color`, `--btn-secondary-border-color`, `--btn-secondary-hover-color`, `--btn-secondary-hover-text-color`, `--btn-secondary-hover-shadow`; arquivo de teste `tests/e2e/test_tema_componentes.py` com `from tests.e2e.test_tema_visual import _token` e as constantes `FORMULARIO = '/djtools/give_permission/'`, `DETALHE = '/rh/servidor/7000001/'`, `CAIXA = '/comum/acessibilidade/'`, `GUIA = '/comum/design_system/?tab={}'` — as Tasks 2 e 3 acrescentam testes neste arquivo.

- [ ] **Step 1: Teste (falha)** — `tests/e2e/test_tema_componentes.py`:

```python
"""Componentes da fase 2 da modernização, numa tela real (tema Padrão).

Spec: ``docs/superpowers/specs/2026-10-15-modernizacao-fase2-componentes-design.md``.
"""

import pytest
from playwright.sync_api import expect

from tests.e2e.test_tema_visual import _token

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

FORMULARIO = '/djtools/give_permission/'
DETALHE = '/rh/servidor/7000001/'
CAIXA = '/comum/acessibilidade/'
GUIA = '/comum/design_system/?tab={}'


def test_botao_secundario_em_contorno_e_submit_generico_preenchido(logado) -> None:
    page = logado('admin')
    page.goto(FORMULARIO)

    secundario = page.locator('#topodapagina')  # <button class="btn"> do rodapé de toda tela
    expect(secundario).to_have_css('background-color', _token(page, '--white'))
    expect(secundario).to_have_css('color', _token(page, '--grey-850'))
    expect(secundario).to_have_css('box-shadow', f'{_token(page, "--grey-400")} 0px 0px 0px 1px inset')
    secundario.hover()
    expect(secundario).to_have_css('background-color', _token(page, '--grey-100'))

    # Submit genérico (input[type=submit] sem .btn) mantém o preenchimento escuro. O implementer confirma no template
    # um que apareça sem interação numa tela do admin (se não houver em FORMULARIO, use outra tela e ajuste o goto).
    generico = page.locator('input[type=submit]:not(.btn)').first
    expect(generico).to_have_css('background-color', _token(page, '--grey-700'))


def test_botao_de_variante_nao_ganha_contorno(logado) -> None:
    page = logado('admin')
    page.goto(GUIA.format('botoes_e_acoes'))
    page.evaluate("() => document.querySelector('#botoes_e_acoes-tab-pane .accordion-collapse').classList.add('show')")
    remocao = page.locator('#botoes_e_acoes-tab-pane .btn.danger').first

    expect(remocao).to_have_css('background-color', _token(page, '--danger'))
    assert remocao.evaluate('e => getComputedStyle(e).boxShadow') == 'none'
    remocao.hover()
    assert _token(page, '--grey-400') not in remocao.evaluate('e => getComputedStyle(e).boxShadow')
```

Run: comando e2e com `tests/e2e/test_tema_componentes.py`. Expected: FAIL (fundo do `#topodapagina` é `--grey-700`).

- [ ] **Step 2: Tokens no default** — `:root` do `default/pre.scss`, logo depois de `--btn-warning-text-color`:

```scss
    // Botão secundário (.btn sem variante; fase 2 da modernização): contorno no lugar do preenchimento escuro.
    // `--btn-color` fica como está: ele também pinta `input[type=submit]` sem `.btn`, que segue preenchido.
    --btn-secondary-color:            var(--white);
    --btn-secondary-text-color:       var(--grey-850);
    --btn-secondary-border-color:     var(--grey-400);
    --btn-secondary-hover-color:      var(--grey-100);
    --btn-secondary-hover-text-color: var(--grey-900);
    --btn-secondary-hover-shadow:     inset 0 0 0 1px var(--grey-500);
```

- [ ] **Step 3: Regra** — `default/forms.scss`, logo após o bloco `.btn.warning { ... }`:

```scss
// Botão secundário (fase 2): só `.btn` sem variante. O `:where()` não soma especificidade (fica (0,1,1)/(0,2,1)),
// então variantes (`.btn.danger` etc.), `.disabled` e regras próprias de tema continuam vencendo, e
// `input[type=submit]` sem `.btn` mantém o preenchimento de `%btn`.
:is(a, button, input).btn:where(:not(.success, .primary, .danger, .warning, .default, .disabled, .unchecked, .btn-close, .btn-link)) {
    background-color: var(--btn-secondary-color);
    box-shadow: inset 0 0 0 1px var(--btn-secondary-border-color);
    color: var(--btn-secondary-text-color);
    &:active,
    &:hover {
        background-color: var(--btn-secondary-hover-color);
        box-shadow: var(--btn-secondary-hover-shadow);
        color: var(--btn-secondary-hover-text-color);
    }
}
```

- [ ] **Step 4: Preservar os temas com botão próprio** — no início do `:root` de `aurora`, `dunas`, `govbr`, `ifs`, `luna` e `alto_contraste` (`pre.scss`):

```scss
    // Mantém o botão secundário do tema (fase 2 só muda o Padrão): os tokens apontam para o que o tema já usava.
    --btn-secondary-color:            var(--btn-color);
    --btn-secondary-text-color:       var(--btn-text-color);
    --btn-secondary-border-color:     transparent;
    --btn-secondary-hover-color:      var(--btn-active-color);
    --btn-secondary-hover-text-color: var(--btn-text-color);
    --btn-secondary-hover-shadow:     inset 0 0 10px rgba(0, 0, 0, .25);
```

(`rgba(0, 0, 0, .25)` é o mesmo valor do `%btn-active` atual; IFS não define `--btn-text-color`/`--btn-active-color` e herda branco/preto do default, que é o que usava.)

- [ ] **Step 5: Compilar os 8 temas; teste passa.** Expected: 8× `ok`; 2 passed.

- [ ] **Step 6: Commit**

```bash
git add djtools/static/djtools/themes/ tests/e2e/test_tema_componentes.py
git commit -m "[djtools] Deixando em contorno o botão secundário do tema Padrão"
```

---

### Task 2: Campo de formulário preenchido (componente 2, direção B)

**Files:**
- Modify: `djtools/static/djtools/themes/default/pre.scss` (`:root` `// Form Colors`; `%inputs` ~linha 1183; `%inputs-focus` ~linha 1261)
- Modify: `djtools/static/djtools/themes/default/forms.scss` (select2 `.select2-selection--single`/`--multiple` ~linhas 1186-1240; `.form-row .errorlist` ~linha 607)
- Modify: `djtools/static/djtools/themes/default/post.scss` (`.errors { ... }` ~linha 4612)
- Modify: `djtools/static/djtools/themes/{aurora,dunas,govbr,ifs,luna,alto_contraste}/pre.scss` (`:root`)
- Test: `tests/e2e/test_tema_componentes.py`

**Interfaces:**
- Consumes: `_token`, `FORMULARIO` (Task 1).
- Produces: tokens `--input-border-color`, `--input-radius`, `--input-focus-bg-color`, `--input-focus-ring`, `--input-error-bg-color` (e o existente `--input-bg-color` com novo valor).

- [ ] **Step 1: Teste (falha)** — acrescentar:

```python
def test_campo_preenchido_fica_branco_no_foco_e_vermelho_claro_no_erro(logado) -> None:
    page = logado('admin')
    page.goto(FORMULARIO)
    page.click('input[name=atribuirpermissao_form]')  # submete vazio: "usuarios" é obrigatório (como em test_formulario.py)
    expect(page.locator('.form-row.errors').first).to_be_visible()

    campo_erro = page.locator('.form-row.errors textarea').first
    expect(campo_erro).to_have_css('background-color', _token(page, '--danger-50'))
    expect(campo_erro).to_have_css('border-top-left-radius', '8px')
    icone = page.locator('.form-row .errorlist li').first.evaluate("e => getComputedStyle(e, '::before').content")
    assert icone not in ('none', 'normal', '""'), icone

    selecao = page.locator('.select2-selection').first  # campo de múltipla escolha (select2)
    expect(selecao).to_have_css('background-color', _token(page, '--grey-50'))
    assert page.locator('.select2-search__field').first.evaluate('e => getComputedStyle(e).borderTopStyle') in ('none', 'hidden')

    campo_erro.focus()
    expect(campo_erro).to_have_css('background-color', _token(page, '--white'))
    assert _token(page, '--primary-100') in campo_erro.evaluate('e => getComputedStyle(e).boxShadow')
```

Expected no RED: FAIL (fundo do textarea com erro não é `--danger-50`).

- [ ] **Step 2: Tokens no default** — `:root` do `default/pre.scss`, bloco `// Form Colors`: `--input-bg-color:        var(--white);` → `var(--grey-50);` e acrescentar:

```scss
    // Campo preenchido (fase 2 da modernização): fundo claro que fica branco no foco
    --input-border-color:    var(--grey-150);
    --input-radius:          8px;
    --input-focus-bg-color:  var(--white);
    --input-focus-ring:      0 0 0 3px var(--primary-100);
    --input-error-bg-color:  var(--danger-50);
```

- [ ] **Step 3: Regras**

`%inputs`: `border: 1px solid var(--grey-300);` → `border: 1px solid var(--input-border-color);` e `border-radius: var(--border-radius);` → `border-radius: var(--input-radius);`.

`%inputs-focus`:

```scss
%inputs-focus {
    background-color: var(--input-focus-bg-color);
    border-color: var(--primary);
    box-shadow: var(--input-focus-ring);
}
```

select2 (`default/forms.scss`, dentro de `.select2-container.select2-container--default`): em `.select2-selection--single` e `.select2-selection--multiple`, borda → `1px solid var(--input-border-color) !important`, raio → `var(--input-radius) !important`, fundo → `var(--input-bg-color) !important` (mantendo o `!important` que já existe nessas regras). Acrescentar no mesmo bloco:

```scss
        &.select2-container--focus .select2-selection {
            background-color: var(--input-focus-bg-color) !important;
            border-color: var(--primary) !important;
            box-shadow: var(--input-focus-ring);
        }
```

Erro (`default/post.scss`, `.errors { ... }`): no seletor `input, select, textarea` que já define `border-color: var(--false-color);`, acrescentar `background-color: var(--input-error-bg-color);`. E em `default/forms.scss`, após `.form-row .errorlist { ... }`:

```scss
.form-row .errorlist li::before {
    content: "\f06a";
    font-family: var(--awesome-font-family);
    font-weight: 900;
    margin-right: .5rem;
}
```

- [ ] **Step 4: Preservar os temas com `%inputs` próprio** — no `:root` de `aurora`, `dunas`, `govbr`, `ifs` (que não definem `--input-bg-color`):

```scss
    // Mantém o campo do tema (fase 2 só muda o Padrão)
    --input-bg-color:        var(--white);
    --input-border-color:    var(--grey-300);
    --input-radius:          var(--border-radius);
    --input-focus-bg-color:  var(--input-bg-color);
    --input-focus-ring:      none;
    --input-error-bg-color:  var(--input-bg-color);
```

e em `luna` e `alto_contraste` (que já definem `--input-bg-color` próprio — **não** repetir essa linha):

```scss
    // Mantém o campo do tema (fase 2 só muda o Padrão)
    --input-border-color:    var(--grey-300);
    --input-radius:          var(--border-radius);
    --input-focus-bg-color:  var(--input-bg-color);
    --input-focus-ring:      none;
    --input-error-bg-color:  var(--input-bg-color);
```

- [ ] **Step 5: Compilar os 8 temas; teste passa.** Expected: 8× `ok`; 3 passed.

- [ ] **Step 6: Commit**

```bash
git add djtools/static/djtools/themes/ tests/e2e/test_tema_componentes.py
git commit -m "[djtools] Preenchendo o campo de formulário do tema Padrão, com foco branco e erro destacado"
```

---

### Task 3: Mensagens com cantos de 8px (B), abas sublinhadas e caixa com borda cinza (A)

**Files:**
- Modify: `djtools/static/djtools/themes/default/pre.scss` (`:root`; `%msg` ~linha 1496; `%nav-tabs` ~linha 2046; `%nav-link` ~linha 2088; `%nav-link-active`; `%accordion` ~linha 251)
- Modify: `djtools/static/djtools/themes/{govbr,aurora,dunas,luna}/pre.scss` (`:root`, conforme Step 4)
- Test: `tests/e2e/test_tema_componentes.py`

**Interfaces:**
- Consumes: `_token`, `DETALHE`, `CAIXA`, `GUIA` (Task 1).
- Produces: tokens `--msg-border-radius`, `--tabs-indicator-color`, `--tabs-baseline-color`, `--tabs-link-bg-color`, `--tabs-link-active-bg-color`, `--box-border-color`.

- [ ] **Step 1: Teste (falha)** — acrescentar:

```python
def test_mensagem_com_cantos_de_8px(logado) -> None:
    page = logado('admin')
    page.goto(GUIA.format('mensagens'))
    page.evaluate("() => document.querySelector('#mensagens-tab-pane .accordion-collapse').classList.add('show')")
    expect(page.locator('#mensagens-tab-pane .alert').first).to_have_css('border-top-left-radius', '8px')


def test_aba_ativa_sublinhada_e_caixa_com_borda_cinza(logado) -> None:
    page = logado('admin')
    page.goto(DETALHE)
    ativa = page.locator('.nav-tabs .nav-link.active').first
    expect(ativa).to_have_css('border-bottom-color', _token(page, '--primary-700'))
    expect(ativa).to_have_css('border-bottom-width', '2px')
    expect(ativa).to_have_css('background-color', 'rgba(0, 0, 0, 0)')
    expect(page.locator('.nav-tabs .nav-link:not(.active)').first).to_have_css('background-color', 'rgba(0, 0, 0, 0)')

    ativa.focus()
    page.keyboard.press('Shift+Tab')
    page.keyboard.press('Tab')  # modalidade teclado
    expect(ativa).to_be_focused()
    contorno, sombra = ativa.evaluate('e => [getComputedStyle(e).outlineStyle, getComputedStyle(e).boxShadow]')
    assert contorno == 'solid' or sombra != 'none', (contorno, sombra)  # o Bootstrap troca o outline por box-shadow em .nav-link

    page.goto(CAIXA)
    expect(page.locator('.accordion-item').first).to_have_css('border-top-color', _token(page, '--grey-200'))
```

Expected no RED: FAIL (raio do alerta 5px).

- [ ] **Step 2: Tokens no default** — `:root` do `default/pre.scss` (junto de `--box-header-bg`):

```scss
    // Fase 2 da modernização: mensagens, abas e caixas
    --msg-border-radius:         8px;
    --tabs-indicator-color:      var(--primary-700);
    --tabs-baseline-color:       var(--grey-200);
    --tabs-link-bg-color:        transparent;
    --tabs-link-active-bg-color: transparent;
    --box-border-color:          var(--grey-200);
```

- [ ] **Step 3: Regras**

`%msg`: `border-radius: var(--border-radius);` → `border-radius: var(--msg-border-radius);`.

`%accordion`: `--bs-accordion-border-color: var(--primary-600);` → `--bs-accordion-border-color: var(--box-border-color);`.

`%nav-tabs`, acrescentar às variáveis do Bootstrap já declaradas ali:

```scss
    --bs-nav-tabs-border-color: var(--tabs-baseline-color);
    --bs-nav-tabs-link-active-bg: var(--tabs-link-active-bg-color);
    --bs-nav-tabs-link-active-border-color: transparent transparent var(--tabs-indicator-color);
    --bs-nav-tabs-link-active-color: var(--grey-900);
```

(substituindo a linha `--bs-nav-tabs-link-active-color: var(--black);` existente).

`%nav-link`: `background-color: var(--grey-75);` → `background-color: var(--tabs-link-bg-color);`; `border-bottom: 1px solid var(--bs-border-color);` → `border-bottom: 2px solid transparent;`; e acrescentar `border-top: 0; border-left: 0; border-right: 0;`.

`%nav-link-active`, acrescentar `border-bottom-color: var(--tabs-indicator-color); font-weight: 600;` e, no `&:hover`, `background-color: var(--white);` → `background-color: var(--tabs-link-active-bg-color);`.

- [ ] **Step 4: Preservar os temas**

`govbr/pre.scss` `:root` (tem `%msg` próprio):

```scss
    --msg-border-radius:         var(--border-radius);
```

`aurora`, `dunas`, `govbr`, `luna` (`pre.scss`, `:root`; têm `%nav-tabs` próprio):

```scss
    // Mantém as abas do tema (fase 2 só muda quem não tem aba própria)
    --tabs-indicator-color:      var(--bs-border-color);
    --tabs-baseline-color:       var(--bs-border-color);
    --tabs-link-bg-color:        var(--grey-75);
    --tabs-link-active-bg-color: var(--white);
```

(A Task 4 confere por medição que as abas desses temas ficaram iguais ao base; se algum ainda diferir, ajuste ali o valor do token com o que o tema mostrava.) Temas com borda de accordion própria (Alto Contraste, Aurora, Dunas, IFS, Luna, Modo Daltonismo) não precisam de linha: a declaração deles vem depois e vence.

- [ ] **Step 5: Compilar os 8 temas; testes passam.** Expected: 8× `ok`; 5 passed.

- [ ] **Step 6: Commit**

```bash
git add djtools/static/djtools/themes/ tests/e2e/test_tema_componentes.py
git commit -m "[djtools] Arredondando as mensagens, sublinhando a aba ativa e acinzentando a borda das caixas"
```

---

### Task 4: Medição base×HEAD nos 8 temas e contraste

**Files:**
- Modify (conforme a medição): `djtools/static/djtools/themes/<tema>/pre.scss`
- Harness descartável: `$SCRATCH/fase2/camadas.py`

- [ ] **Step 1: Harness** — compila cada tema no `origin/master` (via `git show origin/master:<arquivo>` para um diretório temporário) e no HEAD; injeta `bootstrap.min.css` (`djtools/static/djtools/css/bootstrap.min.css`), `default/colors.css` e o CSS do tema numa página sintética com:

```html
<main>
  <button class="btn" id="sec">Secundário</button> <a class="btn danger" id="dan">Remover</a>
  <input type="submit" value="Confirmar" id="sub">
  <div class="form-row errors"><textarea id="erro"></textarea></div> <input type="text" id="txt" placeholder="Digite">
  <p class="alert alert-info" id="msg">Mensagem</p>
  <ul class="nav nav-tabs" role="tablist"><li class="nav-item" role="presentation"><button class="nav-link active" role="tab" id="ativa">Geral</button></li><li class="nav-item" role="presentation"><button class="nav-link" role="tab" id="inativa">Outra</button></li></ul>
  <div class="accordion"><div class="accordion-item" id="caixa"><h2 class="accordion-header"><button class="accordion-button" type="button">Caixa</button></h2></div></div>
</main>
```

e imprime, por tema e por versão, os estilos computados de: `#sec` (fundo, cor, box-shadow; e no hover), `#dan` (fundo, box-shadow; e no hover), `#sub` (fundo, cor), `#txt` (fundo, borda, raio; e no foco: fundo, box-shadow), `#erro` (fundo, borda), `#msg` (raio), `#ativa` e `#inativa` (fundo, borda inferior, cor, peso), `#caixa` (cor da borda).

- [ ] **Step 2: Comparar com a tabela "Alcance por tema" da spec** — toda diferença base×HEAD num tema/componente marcado "mantém" é defeito: corrija com o token de preservação daquele tema (no `:root` dele) até o HEAD igualar o base. Toda célula marcada "muda" deve mostrar o valor novo.

- [ ] **Step 3: Contraste** (fórmula WCAG) no Padrão e no Modo Daltonismo: texto do `#sec` sobre o fundo dele e no hover; texto e placeholder do `#txt` sobre `--grey-50`; borda do `#txt` (`--grey-150`) sobre o fundo da página — se < 3:1, suba `--input-border-color` para o primeiro tom da paleta cinza que passe e registre; texto da aba ativa e inativa; sublinhado da aba (≥ 3:1).

- [ ] **Step 4: Commit** (se houver correção)

```bash
git add djtools/static/djtools/themes/
git commit -m "[djtools] Ajustando os tokens da fase 2 nos temas que pedem valor próprio"
```

---

### Task 5: Verificação completa e screenshots

- [ ] **Step 1: e2e** — `tests/e2e` + `comum/tests/e2e` (comando das Global Constraints). Expected: verde.

- [ ] **Step 2: Gate axe sob Alto Contraste e Luna** (rodada única, teste temporário `tests/e2e/test_zz_*.py` apagado depois; tema via `/comum/alterar_tema/?theme=<slug>`, restaurando `padrao` num `finally`). Expected: nenhuma violação nova em relação ao `origin/master`.

- [ ] **Step 3: Screenshots antes/depois** — as quatro cenas reais (design system: aba `botoes_e_acoes`, primeira tabela, e aba `mensagens`, primeiro `.accordion-body`, ambas com a seção expandida; formulário `/djtools/give_permission/` submetido vazio; detalhe `/rh/servidor/7000001/` recortado em 620px de altura) em Padrão, Alto Contraste, GovBR e Luna, viewport 1366×900. "Antes" = worktree temporário do `origin/master` (`git worktree add $SCRATCH/master origin/master`, removido no fim). Montar `comparacao-<tema>.png` (antes à esquerda, depois à direita) em `$SCRATCH/fase2/screenshots/`.

- [ ] **Step 4: Paridade com o CI** — `uv run pre-commit run --from-ref origin/master --to-ref HEAD`.

- [ ] **Step 5: Mostrar ao usuário** — enviar as comparações e apontar qualquer quebra; sem MR antes do ok dele.
