# Modernização — fase 3a: menu lateral e mobile — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aplicar ao menu lateral, ao menu retraído e à barra do celular a direção "A — escuro refinado" (página atual com fundo sutil e texto teal), por tokens no tema default, sem mudar os temas que já têm menu próprio.

**Architecture:** Cada parte nova lê um token do `:root` do `default/pre.scss`. Um mixin `menu-classico` (no `default/pre.scss`) reúne os valores de hoje desses tokens; os seis temas preservados o incluem no topo do próprio `:root` e, onde mostram outra coisa, redefinem o token depois. Um e2e trava o Padrão numa tela real; a medição base × HEAD nos 8 temas prova que os preservados não mudaram.

**Tech Stack:** SCSS (libsass via `djtools.pipeline.LibSassCompiler`), jQuery do menu (`comum/static/comum/js/main.js`, sem mudança), pytest + Playwright.

**Spec:** `docs/superpowers/specs/2026-10-16-modernizacao-fase3a-menu-design.md`

## Global Constraints

- Branch `claude/modernizacao-fase2-componentes` (mesmo MR da fase 2, !19395; usa tokens dela).
- Tema versionado em `djtools/static/djtools/themes/<tema>/` (o `static/` da raiz é saída gitignored; nunca editar lá).
- Ordem de import: `default/colors.css` → `<tema>/colors.scss` → `default/variables` → `<tema>/variables` → `default/pre` → `<tema>/pre` → `default/post` → `default/forms` → `<tema>/post`.
- Cor só por token: nada de hex nem `rgba()` literal em código novo; nada de `style=""`; JS do menu e `menu.yaml` não mudam.
- Tokens novos no `:root` do `default/pre.scss`, perto de `--mainmenu-link-color` / `--menu-3-level-color`.
- Temas preservados: Alto Contraste, Aurora, Dunas, GovBR, IFS, Luna — **todas** as propriedades novas idênticas a hoje (cor, raio, padding, peso, fundos, linha-guia, busca, `#mobilemenu`). Modo Daltonismo recebe tudo menos o ícone (`--primary-250`) e o texto de hover (`--mainmenu-link-hover-color`, `--primary-350`).
- Correção da faixa escura do celular vale para os 8 temas.
- Contraste: texto ≥ 4,5:1; limite de componente ≥ 3:1.
- Manter: autofocus da busca do menu em `/` (`index.html`); `aside.nav :focus-visible { outline-color: currentColor }` (fase 0); busca sem anel de foco (fase 2).
- pt-BR em comentários e commits; commit `[djtools] Frase no gerúndio`; sem linhas de atribuição; não commitar `tests/e2e/test_zz_*.py`.
- Compilar os 8 temas: `for t in default govbr alto_contraste luna aurora dunas ifs modo_daltonismo; do uv run python -c "import sass; sass.compile(filename='djtools/static/djtools/themes/$t/main.scss')" && echo "$t ok"; done`.
- e2e: `TEST_DATABASE_NAME=test_suap_e2e DATABASE_PORT=5434 DATABASE_USER=postgres DATABASE_PASSWORD=postgres DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest -m e2e --reuse-db <arquivos>` (container `suap-test-db-axe`; `docker start suap-test-db-axe` se parado).

## Tokens (contrato entre as tasks)

| Token | Padrão (fase 3a) | `menu-classico` (= default de hoje) | Task |
|---|---|---|---|
| `--aside-bg-color` (existe) | `var(--grey-900)` | `var(--grey-850)` | 1 |
| `--menu-list-padding` | `1.2rem .8rem` | `var(--regular-margin) 0` | 1 |
| `--menu-item-margin` | `1px 0` | `0 var(--menu-margin)` | 1 |
| `--menu-item-padding` | `.95rem 1.2rem` | `1rem 0` | 1 |
| `--menu-item-radius` | `10px` | `0` | 1 |
| `--menu-item-weight` | `500` | `inherit` | 1 |
| `--menu-item-text-color` | `var(--grey-200)` | `var(--mainmenu-link-color)` | 1 |
| `--menu-item-hover-bg` | `var(--grey-850)` | `transparent` | 1 |
| `--menu-item-hover-text-color` | `var(--white)` | `var(--mainmenu-link-hover-color)` | 1 |
| `--menu-item-open-bg` | `var(--grey-800)` | `transparent` | 1 |
| `--menu-item-open-text-color` | `var(--white)` | `var(--mainmenu-link-color)` | 1 |
| `--menu-icon-color` | `var(--grey-400)` | `var(--primary-750)` | 1 |
| `--menu-icon-open-color` | `var(--primary-300)` | `var(--primary-750)` | 1 |
| `--menu-subitem-divider` | `0 none` | `1px solid var(--grey-900)` | 1 |
| `--menu-subitem-guide` | `1px solid var(--grey-750)` | `0 none` | 1 |
| `--menu-subitem-radius` | `8px` | `0` | 1 |
| `--menu-subitem-text-color` | `var(--grey-300)` | (2º nível: `--mainmenu-link-color`; 3º: `--menu-3-level-color`) | 1 |
| `--menu-current-bg` | `var(--grey-800)` | `transparent` | 1 |
| `--menu-current-text-color` | `var(--primary-400)` | `var(--primary-400)` | 1 |
| `--menu-current-weight` | `600` | `inherit` | 1 |
| `--usertools-radius` | `10px` | `var(--border-radius)` | 1 |
| `--aside-search-bg-color` | `var(--grey-850)` | `transparent` | 2 |
| `--aside-search-border` | `1px solid var(--grey-800)` | (só `border-bottom: 1px solid var(--grey-600)`) | 2 |
| `--aside-search-radius` | `10px` | `0` | 2 |
| `--aside-search-height` | `38px` | `31px` | 2 |
| `--mobile-menu-bg-color` | `var(--grey-900)` | `var(--primary-900)` | 3 |
| `--mobile-menu-radius` | `18px` | `25px` | 3 |
| `--mobile-menu-color` (existe) | `var(--grey-200)` | `var(--white)` | 3 |

Onde a coluna do meio não cabe num só valor (ex.: `--menu-subitem-text-color`, `--aside-search-border`), quem implementa escolhe a forma (dois tokens, ou `initial` + fallback no `var()`), desde que o clássico renderize igual a hoje. Valores em `rem`/`px` são do mockup aprovado e podem ser afinados.

## Review Focus

1. **Item de 1º nível com página atual dentro, menu retraído** — o link atual some (`nav ul ul` escondido); o pai precisa mostrar fundo de aberto e ícone teal. Task 3 testa.
2. **Tema claro herdando o teal** (GovBR, IFS, Dunas): `--primary-400` sobre branco não tem contraste. Task 4 mede base × HEAD; Task 1 já inclui o mixin nesses temas.
3. **Foco por teclado sobre os fundos novos** (`--grey-800`/`--grey-850`): o outline `currentColor` precisa continuar visível no item atual e no aberto. Task 1 testa.
4. **Estado retraído preso na sessão do admin** (`/comum/retrair_menu/`) contaminando outros testes. Tasks 3 restaura com `/comum/expandir_menu/` em `try/finally` (padrão de `test_acessibilidade.py`).
5. **Sino com notificação no celular** perdendo o vermelho quando `--mobile-menu-color` muda. Task 3 testa.

---

### Task 1: Barra, itens, subitens e página atual (computador)

**Files:**
- Modify: `djtools/static/djtools/themes/default/pre.scss` (`:root`; mixin `menu-classico`; placeholders `%nav-first-level`, `%nav-first-level-link`, `%nav-first-level-icon`, `%nav-second-level`, `%nav-second-level-link`, `%nav-third-level-link`)
- Modify: `djtools/static/djtools/themes/default/post.scss` (`#mainmenu`, ~linha 825)
- Modify: `djtools/static/djtools/themes/{alto_contraste,aurora,dunas,govbr,ifs,luna}/pre.scss` (`@include menu-classico;` no topo do `:root`, mais o que a medição pedir)
- Modify: `djtools/static/djtools/themes/modo_daltonismo/pre.scss` (`:root`: `--menu-icon-color`/`--menu-icon-open-color: var(--primary-250)`, `--menu-item-hover-text-color: var(--mainmenu-link-hover-color)`)
- Create: `tests/e2e/test_tema_menu.py`

**Interfaces:**
- Consumes: `_token(page, nome)` de `tests/e2e/test_tema_visual.py`; fixture `logado`.
- Produces: tokens da tabela marcados "1"; `@mixin menu-classico` (as Tasks 2 e 3 acrescentam as linhas delas nele); `tests/e2e/test_tema_menu.py` com `PAGINA = '/admin/rh/pessoajuridica/'` e o helper `_abrir_pagina_pelo_menu(page) -> Locator` (abre uma categoria e clica num subitem real, para o `breadcrumbs_reset` gravar `menu_item_id` na sessão; devolve o `<a aria-current="page">`).

- [ ] **Step 1: Testes (falham)** em `tests/e2e/test_tema_menu.py` (docstring citando a spec; `pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]`):

```python
def test_barra_escura_e_pagina_atual_com_fundo_e_texto_teal(logado) -> None:
    page = logado('admin')
    atual = _abrir_pagina_pelo_menu(page)
    expect(page.locator('aside.nav')).to_have_css('background-color', _token(page, '--grey-900'))
    expect(atual).to_have_css('color', _token(page, '--primary-400'))
    expect(atual).to_have_css('background-color', _token(page, '--grey-800'))
    expect(atual).to_have_css('font-weight', '600')
    expect(atual).to_have_css('box-shadow', 'none')  # sem a barrinha teal que o usuário rejeitou
    expect(page.locator('header #user-tools .minha-conta')).to_have_css('border-radius', '10px')


def test_categoria_aberta_com_fundo_e_subitens_sem_traco(logado) -> None:
    page = logado('admin')
    _abrir_pagina_pelo_menu(page)
    aberta = page.locator('#mainmenu > ul > li.opened > a').first
    expect(aberta).to_have_css('background-color', _token(page, '--grey-800'))
    expect(aberta).to_have_css('border-radius', '10px')
    sub = page.locator('#mainmenu > ul > li.opened li').first
    expect(sub).to_have_css('border-bottom-style', 'none')
    expect(page.locator('#mainmenu > ul > li.opened > ul').first).to_have_css('border-left-color', _token(page, '--grey-750'))


def test_hover_de_item_ganha_fundo(logado) -> None:
    page = logado('admin')
    page.goto(PAGINA)
    item = page.locator('#mainmenu > ul > li.menu-inicio > a')
    item.hover()
    expect(item).to_have_css('background-color', _token(page, '--grey-850'))
    expect(item).to_have_css('color', _token(page, '--white'))


def test_foco_por_teclado_visivel_no_item_atual(logado) -> None:
    page = logado('admin')
    atual = _abrir_pagina_pelo_menu(page)
    atual.focus()  # Playwright foca como teclado: :focus-visible casa
    expect(atual).to_have_css('outline-style', 'solid')
    expect(atual).to_have_css('outline-color', _token(page, '--primary-400'))  # currentColor
```

- [ ] **Step 2: Rodar** `tests/e2e/test_tema_menu.py` — esperado FAIL (fundo `--grey-850`, sem fundo no atual).
- [ ] **Step 3: Implementar.** Tokens "1" no `:root`; os placeholders e o `#mainmenu` do `post.scss` passam a ler os tokens (item de 1º nível: margem, padding, raio, peso, cor; hover e `li.opened > a`; ícone e ícone aberto; `#mainmenu > ul` com `--menu-list-padding`; subitens com `--menu-subitem-divider` no lugar do `border-bottom` fixo, linha-guia `--menu-subitem-guide` como `border-left` de cada `ul` aberto em qualquer profundidade, raio e cor de subitem — o 3º nível também, sem o peso 300; página atual por `#mainmenu a[aria-current="page"]`; perfil e "Minha conta" do topo (`header #user-tools`, `post.scss` ~linha 586) com `--usertools-radius`). `@mixin menu-classico` com a coluna do meio; `@include menu-classico;` no topo do `:root` dos seis preservados; linhas do Daltonismo.
- [ ] **Step 4: Rodar** `tests/e2e/test_tema_menu.py tests/e2e/test_tema_componentes.py tests/e2e/test_acessibilidade.py` — PASS; compilar os 8 temas — 8 "ok".
- [ ] **Step 5: Commit** `[djtools] Refinando o menu lateral escuro: itens, subitens e página atual com fundo e texto teal`.

### Task 2: Busca do menu

**Files:**
- Modify: `djtools/static/djtools/themes/default/pre.scss` (`:root`; `menu-classico`; `%aside-menu-search`, `%aside-menu-search-active`, `%aside-menu-search-icon`)
- Modify: `djtools/static/djtools/themes/default/post.scss` (`aside.nav .buscar_menu`, padding ~linha 760)
- Modify: temas preservados só se a medição da Task 4 apontar vazamento (AC, Dunas e IFS já redefinem placeholders da busca)
- Modify: `tests/e2e/test_tema_menu.py`; `tests/e2e/test_tema_componentes.py` (`test_busca_do_menu_sem_anel_e_com_placeholder_legivel`, se o token do placeholder mudar)

**Interfaces:**
- Consumes: `menu-classico` e `PAGINA` da Task 1; `--aside-search-placeholder-color` da fase 2.
- Produces: tokens "2".

- [ ] **Step 1: Teste (falha)**

```python
def test_busca_do_menu_preenchida_arredondada_e_sem_anel(logado) -> None:
    page = logado('admin')
    page.goto(PAGINA)
    busca = page.locator('aside.nav .buscar_menu input[type=search]')
    expect(busca).to_have_css('background-color', _token(page, '--grey-850'))
    expect(busca).to_have_css('border-radius', '10px')
    expect(busca).to_have_css('border-top-color', _token(page, '--grey-800'))
    busca.focus()
    expect(busca).to_have_css('box-shadow', 'none')
```

- [ ] **Step 2: Rodar** — FAIL (fundo transparente).
- [ ] **Step 3: Implementar.** Tokens "2"; campo preenchido com lupa dentro, à esquerda (ajustar `left`/`bottom` do `:before` e o `padding-left` do campo); foco/preenchida com borda `--grey-500` ou mais clara e texto `--white`; medir o placeholder sobre `--grey-850` (`#262626`): se `--grey-400` ficar < 4,5:1, subir o tom em `--aside-search-placeholder-color` e atualizar o teste da fase 2. Linhas da busca no `menu-classico`.
- [ ] **Step 4: Rodar** `tests/e2e/test_tema_menu.py tests/e2e/test_tema_componentes.py tests/e2e/test_acessibilidade.py` (inclui o autofocus da busca em `/`) — PASS; compilar os 8 — "ok".
- [ ] **Step 5: Commit** `[djtools] Transformando a busca do menu em campo preenchido e arredondado`.

### Task 3: Menu retraído, barra do celular e faixa escura

**Files:**
- Modify: `djtools/static/djtools/themes/default/pre.scss` (`:root`; `menu-classico`; `%hidesidebar-nav-first-level`, `%hidesidebar-nav-first-level-icon`)
- Modify: `djtools/static/djtools/themes/default/post.scss` (`body.hideSidebar` ~linha 5083; `#mobilemenu` ~linha 1000; media `max-width: 940px` ~linha 6652 — causa da faixa)
- Modify: `djtools/static/djtools/themes/{aurora,govbr,luna}/post.scss` só se a correção da faixa precisar (eles têm regras próprias de `aside.nav`/`.holder` sob `hideSidebar`)
- Modify: `tests/e2e/test_tema_menu.py`

**Interfaces:**
- Consumes: tokens "1", `menu-classico`, `_abrir_pagina_pelo_menu`.
- Produces: tokens "3".

- [ ] **Step 1: Testes (falham)**

```python
def test_menu_retraido_marca_a_categoria_da_pagina_atual(logado) -> None:
    page = logado('admin')
    _abrir_pagina_pelo_menu(page)
    try:
        page.locator('#toggleSidebar').click()
        expect(page.locator('body')).to_have_class(re.compile(r'\bhideSidebar\b'))
        pai = page.locator('#mainmenu > ul > li.active > a').first
        expect(pai).to_have_css('background-color', _token(page, '--grey-800'))
        expect(pai.locator('.icone')).to_have_css('color', _token(page, '--primary-300'))
        expect(pai).to_have_css('justify-content', 'center')
    finally:
        page.request.get('/comum/expandir_menu/')


def test_barra_do_celular_escura_neutra_e_sino_vermelho(logado) -> None:
    page = logado('admin')
    page.set_viewport_size({'width': 390, 'height': 844})
    page.goto(PAGINA)
    barra = page.locator('#mobilemenu')
    expect(barra).to_have_css('background-color', _token(page, '--grey-900'))
    expect(barra).to_have_css('border-top-left-radius', '18px')
    expect(barra.locator('a[href="/"]')).to_have_css('color', _token(page, '--grey-200'))
    sino = barra.locator('a.error')  # o admin do seed tem notificação não lida (a captura mostrou o contador "1")
    if sino.count():
        expect(sino).to_have_css('color', _token(page, '--danger'))


def test_celular_com_menu_fechado_sem_faixa_escura(logado) -> None:
    page = logado('admin')
    page.set_viewport_size({'width': 390, 'height': 844})
    page.goto(PAGINA)
    assert page.locator('aside.nav').evaluate('e => e.getBoundingClientRect().width') == 0
    assert page.locator('main#content').evaluate('e => e.getBoundingClientRect().left') == 0
```

(Se o sino do seed não tiver `.error`, criar a notificação no teste com a factory do `comum` em vez do `if`.)

- [ ] **Step 2: Rodar** — FAIL (barra `--primary-900`; faixa à esquerda).
- [ ] **Step 3: Implementar.** Retraído: ícones centralizados com os estados da Task 1; `body.hideSidebar #mainmenu > ul > li.active > a` com `--menu-item-open-bg` e ícone `--menu-icon-open-color`. `#mobilemenu` lendo `--mobile-menu-bg-color`, `--mobile-menu-radius`, `--mobile-menu-color` (o `.error` continua `--danger`). Faixa: achar a causa (provável coluna `--basis-nav-collapsed` da grade sob `hideSidebar` abaixo de 940px) e corrigir na raiz, para os 8 temas. Linhas "3" no `menu-classico`; o Luna já tem `--mobile-menu-color` próprio e o mantém.
- [ ] **Step 4: Rodar** `tests/e2e/test_tema_menu.py tests/e2e/test_acessibilidade.py` (inclui `test_tela_estreita_recolhe_a_sidebar` e o toggle) — PASS; compilar os 8 — "ok".
- [ ] **Step 5: Commit** `[djtools] Ajustando o menu retraído e a barra do celular e removendo a faixa escura no celular`.

### Task 4: Medição base × HEAD nos 8 temas e contraste

**Files:**
- Modify: `djtools/static/djtools/themes/<tema>/pre.scss` dos preservados (linhas de preservação que faltarem)
- Scratch (não commitar): harness no scratchpad, no padrão das fases 1/2 — compila base (`claude/modernizacao-fase2-componentes`) e HEAD, injeta `bootstrap.min.css` e `default/colors.css` antes do CSS do tema, `body class="theme-<slug>"`

**Interfaces:**
- Consumes: tudo das Tasks 1–3.

- [ ] **Step 1:** Medir, em base e HEAD, os estilos computados (cor, fundo, raio, padding, margem, peso, bordas, `box-shadow`, outline) de: `aside.nav`; item de 1º nível normal/hover/aberto; ícone normal/aberto; subitem de 2º e 3º nível; link `aria-current`; busca vazia/foco/preenchida e placeholder; `body.hideSidebar` com item ativo; `#mobilemenu` e seus ícones a 390px; largura do `aside.nav` e posição do `main` a 390px fechado.
- [ ] **Step 2:** Esperado: AC, Aurora, Dunas, GovBR, IFS e Luna **idênticos** em tudo, exceto a faixa escura corrigida; Modo Daltonismo igual ao Padrão menos ícone e texto de hover. Cada diferença inesperada vira linha de preservação no tema; repetir até zerar.
- [ ] **Step 3:** Contraste no Padrão e no Daltonismo: texto de item (`--grey-200`), subitem (`--grey-300`), página atual (`--primary-400` sobre `--grey-800`), ícones, placeholder da busca, ícones da barra do celular — texto ≥ 4,5:1. Anotar os números para o MR.
- [ ] **Step 4:** Compilar os 8; rodar `tests/e2e/test_tema_menu.py` — PASS.
- [ ] **Step 5: Commit** (se houve linha nova) `[djtools] Preservando o menu dos temas com visual próprio`.

### Task 5: Verificação final e screenshots

**Files:**
- Modify: `docs/superpowers/specs/2026-10-16-modernizacao-fase3a-menu-design.md` (status "aprovada; implementada" e decisões tomadas na implementação)

- [ ] **Step 1:** e2e `tests/e2e` + `comum/tests/e2e` — tudo PASS.
- [ ] **Step 2:** Gate axe (`tests/e2e/test_acessibilidade.py`) no Padrão e numa rodada sob Alto Contraste e Luna — sem violação nova em relação à base.
- [ ] **Step 3:** Screenshots antes/depois (menu aberto com página atual, retraído, celular fechado e aberto) em Padrão, Alto Contraste, GovBR e Luna, montados lado a lado no scratchpad, para o controlador mostrar ao usuário antes do MR.
- [ ] **Step 4:** `pre-commit run --from-ref origin/master --to-ref HEAD` — verde.
- [ ] **Step 5: Commit** `[djtools] Atualizando a spec da fase 3a com as decisões tomadas na implementação`.
