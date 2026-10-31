# Modernização — fase 1: tokens visuais — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aplicar seis ajustes visuais (texto 14px, sombra discreta, cabeçalho de caixa branco com divisória, título grafite, `th` em caixa alta pequena, realce da linha) por tokens CSS no tema default, herdados pelos 8 temas.

**Architecture:** Cada ajuste é um token em `:root` do `default/pre.scss` (ou o token existente que já controla aquilo), lido pela regra correspondente. Temas que já têm valor próprio mantêm o seu; tema onde o herdado falha contraste redefine o token. Um teste e2e trava os tokens numa tela real; uma medição por tema (descartável) e screenshots fecham a verificação.

**Tech Stack:** SCSS (libsass via `djtools.pipeline.LibSassCompiler`), Bootstrap 5.3 accordion, pytest + Playwright.

**Spec:** `docs/superpowers/specs/2026-10-15-modernizacao-fase1-tokens-design.md`

## Global Constraints

- Tema versionado em `djtools/static/djtools/themes/<tema>/` (o `static/` da raiz é saída gitignored do collectstatic — nunca editar lá).
- Ordem de import de cada tema: `default/colors.css` → `<tema>/colors.scss` → `default/variables.scss` → `<tema>/variables.scss` → `default/pre.scss` → `<tema>/pre.scss` → `default/post.scss` → `default/forms.scss` → `<tema>/post.scss`.
- Cor só por variável CSS; nunca hex; nunca `style=""` em template.
- Tokens novos em `:root` do `default/pre.scss`, perto dos que já existem.
- pt-BR em comentários e commits; commit `[djtools] Frase no gerúndio`; sem linhas de atribuição.
- Compilar os 8 temas: `for t in default govbr alto_contraste luna aurora dunas ifs modo_daltonismo; do uv run python -c "import sass; sass.compile(filename='djtools/static/djtools/themes/$t/main.scss')" && echo "$t ok"; done`.
- e2e: `TEST_DATABASE_NAME=test_suap_e2e DATABASE_PORT=5434 DATABASE_USER=postgres DATABASE_PASSWORD=postgres DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest -m e2e --reuse-db <arquivos>` (container `suap-test-db-axe`; se não existir: `docker run -d --name suap-test-db-axe --shm-size=1g -p 5434:5432 -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres postgres:18 -c max_locks_per_transaction=4096 -c shared_preload_libraries=pg_stat_statements` e `--create-db` na 1ª vez).
- Contraste mínimo: 4,5:1 para texto, 3:1 para divisória/borda (WCAG 1.4.3 / 1.4.11).

## Desvio declarado da spec

A spec nomeia `--box-header-divider: 1px solid var(--grey-150)`. A divisória do cabeçalho aberto do accordion já existe no Bootstrap como `box-shadow: inset 0 -1px 0 var(--bs-accordion-border-color)` (`.accordion-button:not(.collapsed)`). O plano troca só a **cor** dela, pelo token `--box-header-divider-color: var(--grey-150)`, e mantém a geometria do Bootstrap. Temas que já pintam essa linha com a própria cor de borda redefinem o token (Task 2).

## Review Focus

1. **Linhas com estado** (`.error`, `.extra`, `.info`, `.highlight`, `.selected`) continuam com a cor delas ao passar o mouse — Task 3 testa `.highlight` e `.error` no harness.
2. **Calendário e timeline** não ganham o realce — Task 3 confere `table.calendario-anual` e `.calendario-mensal > table` no harness.
3. **Alto Contraste**: realce amarelo sobre texto amarelo — Task 4 mede e redefine.
4. **Luna (escuro)**: cabeçalho de caixa branco num tema escuro — Task 4 mede; Luna já sobrescreve o accordion, deve ficar intacto.
5. **Quebra de linha com 14px** em labels de largura fixa e tabelas densas — Task 5 screenshots antes/depois.

---

### Task 1: Texto 14px, sombra discreta e título grafite (ajustes 1, 2, 4) + teste dos tokens

**Files:**
- Modify: `djtools/static/djtools/themes/default/pre.scss` (`:root`, `--title-container-color` ~linha 30; acrescentar `--body-font-size`)
- Modify: `djtools/static/djtools/themes/default/post.scss:~81-86` (`body`)
- Modify: `djtools/static/djtools/themes/default/variables.scss:~78` (`--box-shadow`)
- Create: `tests/e2e/test_tema_visual.py`

**Interfaces:**
- Produces: tokens `--body-font-size`; `tests/e2e/test_tema_visual.py` com a constante `LISTAGEM = '/admin/rh/pessoajuridica/'` e o teste `test_listagem_usa_os_tokens_visuais`, que as Tasks 2 e 3 estendem.

- [ ] **Step 1: Teste (falha)**

```python
"""Tokens visuais da fase 1 da modernização, numa tela real (tema Padrão).

Trava o que a spec ``docs/superpowers/specs/2026-10-15-modernizacao-fase1-tokens-design.md`` decidiu:
texto base 14px, título da página em grafite, sombra discreta. As Tasks seguintes acrescentam
cabeçalho de caixa, cabeçalho de tabela e realce de linha.
"""

import pytest
from playwright.sync_api import expect

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

LISTAGEM = '/admin/rh/pessoajuridica/'


def _token(page, nome: str) -> str:
    """Valor computado de um token CSS no :root, normalizado como cor/medida computada num elemento sonda."""
    return page.evaluate(
        """nome => { const s = document.createElement('span'); s.style.color = `var(${nome})`; document.body.append(s);
                    const v = getComputedStyle(s).color; s.remove(); return v; }""",
        nome,
    )


def test_listagem_usa_os_tokens_visuais(logado) -> None:
    page = logado('admin')
    page.goto(LISTAGEM)

    expect(page.locator('body')).to_have_css('font-size', '14px')
    expect(page.locator('.title-container h2')).to_have_css('color', _token(page, '--grey-850'))
```

Run: `TEST_DATABASE_NAME=test_suap_e2e DATABASE_PORT=5434 DATABASE_USER=postgres DATABASE_PASSWORD=postgres DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest -m e2e --reuse-db tests/e2e/test_tema_visual.py -q`
Expected: FAIL (`font-size` "13px").

- [ ] **Step 2: Implementar**

Em `default/pre.scss`, `:root`, trocar `--title-container-color: var(--black);` por `--title-container-color: var(--grey-850);` e acrescentar, logo antes de `// Button Colors`:

```scss
    // Texto base (fase 1 da modernização: 13 → 14px)
    --body-font-size:        1.4rem;
```

Em `default/post.scss`, no `body { ... }` do topo: `font-size: 1.3rem;` → `font-size: var(--body-font-size);`.

Em `default/variables.scss`: `--box-shadow:               10px 10px 35px 0 rgba(0, 0, 0, 0.05);` → `--box-shadow:               0 1px 2px rgb(0 0 0 / .06), 0 2px 8px rgb(0 0 0 / .04);`.

- [ ] **Step 3: Compilar os 8 temas** (comando nas Global Constraints). Expected: 8× `ok`.

- [ ] **Step 4: Teste passa** — mesmo comando do Step 1. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add djtools/static/djtools/themes/default/ tests/e2e/test_tema_visual.py
git commit -m "[djtools] Aumentando o texto base, suavizando a sombra e o título da página"
```

---

### Task 2: Cabeçalho de caixa branco com divisória (ajuste 3)

**Files:**
- Modify: `djtools/static/djtools/themes/default/pre.scss` (`:root` e `%accordion` ~linha 239-260)
- Modify: `djtools/static/djtools/themes/{alto_contraste,ifs,dunas,aurora}/pre.scss` e `modo_daltonismo/pre.scss` (`:root`: preservar a cor de divisória de cada um)
- Test: `tests/e2e/test_tema_visual.py`

**Interfaces:**
- Consumes: `LISTAGEM`, `_token` (Task 1).
- Produces: tokens `--box-header-bg`, `--box-header-divider-color`.

- [ ] **Step 1: Teste (falha)** — acrescentar a `tests/e2e/test_tema_visual.py`:

```python
CAIXA = '/comum/acessibilidade/'  # tem {% box %} aberto, sem dado dependente de seed


def test_cabecalho_de_caixa_aberta_e_branco_com_divisoria(logado) -> None:
    page = logado('admin')
    page.goto(CAIXA)
    cabecalho = page.locator('.accordion-button:not(.collapsed)').first

    expect(cabecalho).to_have_css('background-color', _token(page, '--white'))
    expect(cabecalho).to_have_css('box-shadow', f'{_token(page, "--grey-150")} 0px -1px 0px 0px inset')
```

Run: comando da Task 1 com `tests/e2e/test_tema_visual.py`. Expected: FAIL (fundo `--primary-50`).

- [ ] **Step 2: Implementar no default**

`:root` do `default/pre.scss`, junto de `--body-font-size`:

```scss
    // Cabeçalho de caixa ({% box %} = accordion) aberto: fundo e cor da linha divisória
    --box-header-bg:            var(--white);
    --box-header-divider-color: var(--grey-150);
```

No `%accordion`: `--bs-accordion-active-bg: var(--primary-50);` → `--bs-accordion-active-bg: var(--box-header-bg);` e, dentro de `.accordion-button { ... }`, acrescentar:

```scss
        &:not(.collapsed) {
            box-shadow: inset 0 -1px 0 var(--box-header-divider-color);
        }
```

- [ ] **Step 3: Preservar a divisória dos temas que já a pintavam com a própria borda**

Acrescentar no início do `:root` de cada `pre.scss` (o valor é o mesmo que o tema já usa em `--bs-accordion-border-color`):

| Arquivo | Linha a acrescentar |
|---|---|
| `alto_contraste/pre.scss` | `--box-header-divider-color: var(--primary-800);` |
| `ifs/pre.scss` | `--box-header-divider-color: var(--grey-100);` |
| `dunas/pre.scss` | `--box-header-divider-color: var(--primary-300);` |
| `aurora/pre.scss` | `--box-header-divider-color: var(--primary-100);` |
| `modo_daltonismo/pre.scss` | `--box-header-divider-color: var(--primary-450);` |

Luna não precisa: o `luna/post.scss` (~linha 454-466) já define o accordion inteiro, inclusive o `box-shadow` do botão, e vem depois. Alto Contraste, Dunas e Aurora também definem `--bs-accordion-active-bg` no próprio `%accordion`, que vence o do default (vem depois) — conferir no Step 5.

- [ ] **Step 4: Compilar os 8 temas.** Expected: 8× `ok`.

- [ ] **Step 5: Conferir herança no CSS compilado**

```bash
for t in alto_contraste dunas aurora luna; do uv run python -c "
import sass,re; c=sass.compile(filename='djtools/static/djtools/themes/$t/main.scss')
print('$t', re.findall(r'--bs-accordion-active-bg:\s*([^;]+);', c))"; done
```

Expected: em cada tema, o **último** valor listado é o do próprio tema (não `var(--box-header-bg)`).

- [ ] **Step 6: Teste passa.** Expected: 2 passed.

- [ ] **Step 7: Commit**

```bash
git add djtools/static/djtools/themes/ tests/e2e/test_tema_visual.py
git commit -m "[djtools] Deixando branco o cabeçalho da caixa aberta, com divisória discreta"
```

---

### Task 3: Cabeçalho de tabela em caixa alta pequena e realce da linha (ajustes 5 e 6)

**Files:**
- Modify: `djtools/static/djtools/themes/default/pre.scss` (`:root` e `%table-thead` ~linha 1974)
- Modify: `djtools/static/djtools/themes/default/post.scss` (regra de hover nova, logo após o bloco `/* Tables */ table { ... }` que começa ~linha 216)
- Test: `tests/e2e/test_tema_visual.py`; harness descartável em `$SCRATCH/fase1/hover.py`

**Interfaces:**
- Consumes: `LISTAGEM`, `_token`.
- Produces: tokens `--table-thead-transform`, `--table-thead-font-size`, `--table-thead-letter-spacing`, `--table-row-hover-color`.

- [ ] **Step 1: Teste (falha)** — acrescentar:

```python
def test_tabela_tem_cabecalho_em_caixa_alta_e_realce_da_linha(logado) -> None:
    page = logado('admin')
    page.goto(LISTAGEM)
    expect(page.locator('#result_list tbody tr').first).to_be_visible()  # o seed cria uma PJ

    expect(page.locator('#result_list thead th').last).to_have_css('text-transform', 'uppercase')
    celula = page.locator('#result_list tbody tr').first.locator('td').last
    celula.hover()
    expect(celula).to_have_css('background-color', _token(page, '--primary-50'))
```

Expected no RED: FAIL (`text-transform` "none").

- [ ] **Step 2: Implementar**

`:root` do `default/pre.scss`:

```scss
    // Tabelas: cabeçalho em caixa alta pequena e realce da linha sob o mouse
    --table-thead-transform:      uppercase;
    --table-thead-font-size:      1.15rem;
    --table-thead-letter-spacing: .04em;
    --table-row-hover-color:      var(--primary-50);
```

`%table-thead`, acrescentar:

```scss
    font-size: var(--table-thead-font-size);
    letter-spacing: var(--table-thead-letter-spacing);
    text-transform: var(--table-thead-transform);
```

`default/post.scss`, logo depois do fechamento do bloco `table { ... }` de `/* Tables */`:

```scss
// Realce da linha sob o mouse (fase 1 da modernização). Calendários e timeline ficam de fora,
// como no hover próprio do Luna. A exclusão vai em :where() para não somar especificidade:
// (0,1,4) perde para `table tbody tr.highlight:hover td` (0,2,4) e para .error/.extra/.info (!important),
// então linhas com estado continuam com a cor delas.
:where(*:not(.calendario-mensal)) > table:where(:not(.calendario-anual):not(.timeline-horizontal)) tbody tr:hover > td,
:where(*:not(.calendario-mensal)) > table:where(:not(.calendario-anual):not(.timeline-horizontal)) tbody tr:hover > th {
    background-color: var(--table-row-hover-color);
}
```

- [ ] **Step 3: Harness de precedência (descartável, não commitar)** — `$SCRATCH/fase1/hover.py` (`$SCRATCH` = scratchpad da sessão):

```python
import sass, sys
from playwright.sync_api import sync_playwright
raiz = sys.argv[1]
html = '''<main>
<table id="comum"><tbody><tr id="n"><td>a</td></tr><tr class="error" id="e"><td>b</td></tr><tr class="highlight" id="h"><td>c</td></tr></tbody></table>
<table class="calendario-anual"><tbody><tr id="cal"><td>d</td></tr></tbody></table>
<div class="calendario-mensal"><table><tbody><tr id="mes"><td>e</td></tr></tbody></table></div></main>'''
with sync_playwright() as p:
    pg = p.chromium.launch().new_page()
    pg.set_content(html)
    pg.add_style_tag(path=f'{raiz}/djtools/static/djtools/themes/default/colors.css')
    pg.add_style_tag(content=sass.compile(filename=f'{raiz}/djtools/static/djtools/themes/default/main.scss'))
    for alvo in ['#n', '#e', '#h', '#cal', '#mes']:
        antes = pg.locator(f'{alvo} td').evaluate('e => getComputedStyle(e).backgroundColor')
        pg.hover(f'{alvo} td')
        depois = pg.locator(f'{alvo} td').evaluate('e => getComputedStyle(e).backgroundColor')
        print(alvo, antes, '->', depois)
```

Run: `uv run python -I $SCRATCH/fase1/hover.py $PWD`
Expected: `#n` muda para o `--primary-50`; `#e` e `#h` mantêm a cor de estado; `#cal` e `#mes` não mudam no hover.

- [ ] **Step 4: Compilar os 8 temas; teste passa.** Expected: 8× `ok`; 3 passed.

- [ ] **Step 5: Commit**

```bash
git add djtools/static/djtools/themes/default/ tests/e2e/test_tema_visual.py
git commit -m "[djtools] Destacando a linha da tabela sob o mouse e suavizando o cabeçalho das colunas"
```

---

### Task 4: Contraste por tema e redefinições

**Files:**
- Modify (conforme a medição): `djtools/static/djtools/themes/<tema>/pre.scss` (`:root`)
- Harness descartável: `$SCRATCH/fase1/contraste.py`

- [ ] **Step 1: Medir** — `$SCRATCH/fase1/contraste.py` compila os 8 temas (injetando `default/colors.css` antes do CSS do tema) sobre o HTML:

```html
<main><div class="accordion"><div class="accordion-item"><h2 class="accordion-header"><button class="accordion-button" type="button">Título da caixa</button></h2></div></div>
<table><thead><tr><th>Coluna</th></tr></thead><tbody><tr><td>Valor</td></tr></tbody></table></main>
```

e, para cada tema, imprime: contraste do texto do `.accordion-button` sobre o fundo dele; contraste da divisória (`--box-header-divider-color`) sobre o fundo do botão; contraste do texto do `td` sobre o `--table-row-hover-color` com a linha em hover; contraste do texto do `th` sobre o fundo do `th`. Contraste pela fórmula WCAG (luminância relativa: `L = 0.2126R + 0.7152G + 0.0722B` com canais linearizados; razão `(L1+0.05)/(L2+0.05)`).

Run: `uv run python -I $SCRATCH/fase1/contraste.py $PWD`

- [ ] **Step 2: Redefinir onde falhar**

Para cada tema/ponto abaixo do mínimo (4,5 texto; 3 divisória), redefinir no `:root` do `<tema>/pre.scss` o token correspondente (`--table-row-hover-color`, `--box-header-bg`, `--box-header-divider-color`) com outro token **existente** da paleta do tema que passe. Esperado pela spec: Alto Contraste precisa redefinir `--table-row-hover-color` (o `--primary-50` dele é amarelo); ponto de partida: `var(--grey-800)` — confirme pela medição. Pontos que já falhavam antes da fase 1 (medir o base `origin/master` com o mesmo harness, se precisar) apenas listar no relatório.

- [ ] **Step 3: Medir de novo** — todos os pontos introduzidos pela fase 1 ≥ mínimo nos 8 temas.

- [ ] **Step 4: Commit**

```bash
git add djtools/static/djtools/themes/
git commit -m "[djtools] Ajustando os tokens da fase 1 nos temas que pedem contraste próprio"
```

(Se nenhum tema precisar, sem commit — registrar a tabela de medição no relatório.)

---

### Task 5: Verificação completa e screenshots

- [ ] **Step 1: Gate e e2e**

Run: comando e2e das Global Constraints com `tests/e2e comum/tests/e2e`. Expected: tudo verde (falha conhecida e alheia: a regra `definition-list` na tela inicial só aparece quando os e2e do `comum` rodam antes no mesmo banco — se aparecer, rodar `tests/e2e/test_acessibilidade.py` isolado com `--create-db` para confirmar).

- [ ] **Step 2: Gate sob Alto Contraste e Luna (rodada única, não commitar)** — teste temporário em `tests/e2e/test_zz_tmp.py` (apagar depois) que troca o tema do `admin` via `/comum/alterar_tema/?theme=alto-contraste` e `?theme=luna`, roda o `_violacoes` de `tests/e2e/test_acessibilidade.py` nas 4 telas e restaura `padrao` num `finally`. Expected: nenhuma violação nova em relação ao `origin/master` (comparar com a mesma rodada no master se aparecer algo).

- [ ] **Step 3: Screenshots antes/depois** — num teste temporário (apagar depois), com o mesmo seed: changelist (`/admin/rh/pessoajuridica/`), formulário com fieldsets (`/djtools/give_permission/` submetido vazio), tela inicial (`/`), página de acessibilidade (`/comum/acessibilidade/`), nos temas Padrão, Alto Contraste, GovBR e Luna, viewport 1366×768. "Antes" = rodar o mesmo script com o CSS do `origin/master` (worktree temporário via `git worktree add $SCRATCH/master origin/master`, removido no fim). Salvar em `$SCRATCH/fase1/screenshots/{antes,depois}/<tema>-<tela>.png`.

- [ ] **Step 4: Paridade com o CI** — `uv run pre-commit run --from-ref origin/master --to-ref HEAD`. Expected: Passed.

- [ ] **Step 5: Mostrar ao usuário** — enviar as screenshots (pares antes/depois) e apontar qualquer quebra de linha nova; nada de MR antes do ok dele.
