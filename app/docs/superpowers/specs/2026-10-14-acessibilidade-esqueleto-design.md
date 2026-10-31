# Acessibilidade no esqueleto do SUAP — design

Data: 2026-10-14
Status: aguardando revisão

## Objetivo

Levar o que **todas** as telas herdam (tema default, `base.html`, `render_form`, `TablePlus`) a
WCAG 2.2 AA nos pontos medidos abaixo, e travar regressão com um gate axe-core no e2e.
Um único diff alcança os ≈90 apps porque os 8 temas importam `default/{pre,post,forms}.scss`.

## O que o usuário pediu × suposições

- Pedido: interface "mais moderna, acessível e usável"; primeira frente escolhida: **acessibilidade
  no esqueleto**; critério: **gate axe no e2e**; escopo inclui **tabelas**; axe **via pip**.
- Suposição: o anel de foco e a `<legend>` mudarem o visual é aceitável, desde que validado em
  screenshots (default, Alto Contraste, GovBR) antes do MR.

## Problemas medidos (linha de base)

| # | Problema | Onde | WCAG |
|---|---|---|---|
| 1 | `outline: 0 none` global em `a`, `input` e `%module-info-button` — foco invisível | `default/post.scss:91`, `default/forms.scss:79`, `default/pre.scss:1471`, `luna/post.scss` | 2.4.7, 2.4.11 |
| 2 | Links de atalho (`#accesskeys`) em `left:-9999px` mesmo com foco | `default/post.scss:477` | 2.4.1, 2.4.7 |
| 3 | Toggle da sidebar é `<a href="#">` sem estado | `base.html:122,168`, `comum/static/comum/js/main.js:49` | 4.1.2 |
| 4 | Busca do menu só com placeholder | `base.html:152` | 1.3.1, 3.3.2 |
| 5 | Breadcrumb sem `nav`/`aria-current`; `#mainmenu` sem nome | `base.html:156,194` | 1.3.1, 2.4.8 |
| 6 | Mensagens sem `role` — leitor de tela não anuncia | `djtools/templates/components/messages.html` | 4.1.3 |
| 7 | Readonly pintado `#eee` via JS (quebra Alto Contraste) | `base.html:311-312` | 1.4.3 |
| 8 | Sidebar mobile decidida por user-agent | `base.html:67` | 1.4.10 |
| 9 | Sem `prefers-reduced-motion` | tema | 2.3.3 |
| 10 | Erro e ajuda do campo não associados ao widget | `djtools/forms/utils/__init__.py:135` (`render_field`) | 1.3.1, 3.3.1 |
| 11 | Fieldset titulado por `<h2>` (sem `<legend>`; viola "um único h2") | `djtools/forms/utils/__init__.py:252` | 1.3.1 |
| 12 | `<th>` sem `scope` | `comum/templates/table_plus.html:23` | 1.3.1 |

O changelist do admin usa o `result_list` do Django, que já emite `scope="col"` — fora do escopo
salvo o que o gate acusar.

## Design

### 1. Tema (`djtools/static/djtools/themes/default/*.scss`, `luna/post.scss`)

- Remover os `outline: 0` dos itens 1.
- Anel global, só para teclado:
  `:focus-visible { outline: 2px solid var(--primary-700); outline-offset: 2px; }`
  (clique de mouse não mostra anel; tema troca a cor pela variável).
- `#accesskeys a:focus`: posição fixa no topo, visível.
- `@media (prefers-reduced-motion: reduce)`: `transition`/`animation` zerados.
- Readonly: regra SCSS `input[readonly], textarea[readonly] { background-color: var(--grey-100); }`.
- `legend > h3` de fieldset estilizado igual ao antigo `fieldset > h2` (visual inalterado).

### 2. Esqueleto (`comum/templates/admin/base.html`, `main.js`, `messages.html`)

- Toggles da sidebar → `<button type="button" class="toggleSidebar" aria-expanded aria-controls="…">`;
  o handler em `main.js` atualiza `aria-expanded`.
- Busca do menu: `<label for="__filterinput__" class="visually-hidden">Buscar menu</label>`.
- `#breadcrumbs` → `<nav id="breadcrumbs" aria-label="Trilha de navegação">`, último item com
  `aria-current="page"`; `#mainmenu` com `aria-label="Menu principal"`.
- Mensagens: `role="alert"` para `error`/`errornote`, `role="status"` para as demais.
- Remover o sniff de user-agent (se o CSS responsivo não cobrir, trocar por
  `matchMedia('(max-width: …)')`) e as linhas `.css('background-color', '#eee')`.

### 3. Formulários e tabelas

- `render_field`: com erro, `<ul class="errorlist" id="{id}_erro">`; ajuda `<p class="help" id="{id}_ajuda">`;
  o widget recebe `aria-describedby` (ids existentes, separados por espaço) e `aria-invalid="true"`
  quando inválido. Manter complexidade ≤ 10 (extrair helper) e tipar a def tocada.
- `render_form`: `<h2>{nome}</h2>` do fieldset → `<legend><h3>{nome}</h3></legend>` (a legend nomeia o grupo; o h3 preserva a navegação por títulos e os e2e que buscam `get_by_role('heading')`).
- `render_field`: campo obrigatório ganha `aria-required="true"` (não o `required` nativo, que dispararia a validação do browser), exceto `RadioSelect`/`CheckboxSelectMultiple`.
- `table_plus.html`: `<th scope="col">`.

### 4. Gate

- Dependência dev: `axe-playwright-python` (`uv add --group dev`), que empacota o axe-core.
- `tests/e2e/test_acessibilidade.py`, parametrizado por tela: início, formulário com erro,
  changelist admin, detalhe de objeto. Falha se houver violação com `impact in {serious, critical}`;
  a mensagem lista regra + seletor.
- Teste unitário em `djtools/tests/views/` (ou `models/`, DB-free): form com erro renderizado por
  `render_field` tem `aria-invalid="true"` e `aria-describedby` apontando para ids presentes no HTML.

## Fora do escopo (v1)

- `change_form` do admin e templates de módulo (≈2.900) — entram depois, guiados pelo relatório do gate.
- Refresh visual de tokens (tipografia, densidade) — frente separada, com o time do design system.

## Verificação

1. `pytest -q djtools/tests/...` (unitário de `render_field`).
2. `TEST_DATABASE_NAME=test_suap_e2e pytest -m e2e tests/e2e/test_acessibilidade.py` verde.
3. Teclado: Tab desde o topo mostra skip link → menu → conteúdo com anel visível.
4. Screenshots em default, Alto Contraste e GovBR anexados ao MR.
5. `pre-commit run --from-ref origin/master --to-ref HEAD`.

## Riscos

- Mudança visual do foco e da `legend`: mitigada por screenshots e pelo `:focus-visible`.
- Templates de módulo que estilizam `fieldset > h2` diretamente perdem o estilo: buscar por
  `fieldset h2`/`fieldset > h2` no SCSS e nos templates antes de trocar.
- `aria-describedby` em widgets compostos (select2, MultiWidget): aplicar só quando o widget
  aceita `attrs`; o gate e o teste unitário cobrem o caso simples.
