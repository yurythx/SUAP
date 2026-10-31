# Design System do SUAP

Guia para construir telas no SUAP com identidade visual padronizada. **Não reinventa CSS**:
o SUAP já tem um design system vivo e mantido. Este doc destila as regras e aponta para as
fontes da verdade.

> **Regra de ouro:** monte telas **apenas** com classes/componentes já existentes. Se algo
> não existe no styleguide, ele não existe. Não crie CSS novo nem use `style=""`.

---

## 1. Fontes da verdade (sempre conferir aqui)

Estas fontes são versionadas e atualizadas pela equipe; este doc pode defasar — na dúvida, valem elas.

| O quê | Onde |
|---|---|
| Styleguide vivo (renderizado) | `/comum/design_system/` (logado) |
| Galeria de componentes (HTML real) | `comum/templates/tabs/guia_*.html` (8 arquivos) |
| Tokens de cor (paletas) | `static/djtools/themes/default/colors.css` |
| Tokens de layout/espaçamento/fontes | `static/djtools/themes/default/variables.scss` |
| Componentes (estilos) | `static/djtools/themes/default/pre.scss`, `post.scss`, `forms.scss` |
| Layout base (esqueleto da página) | `comum/templates/admin/base.html` |
| Template tags (`box`, `icone`, `render_form`…) | `djtools/templatetags/tags/utils.py` |
| Whitelist de classes (gerar sob demanda) | `grep -rhoE "\.[a-zA-Z][a-zA-Z0-9_-]+" static/djtools/themes/default/{pre,post,forms}.scss static/djtools/css/bootstrap5-compat.min.css \| sed 's/^\.//' \| sort -u` (utilitárias e grade do Bootstrap **5** em `static/djtools/css/bootstrap5-compat.min.css`, gerado por `bin/scripts/gerar_bootstrap5_compat.py`) |

> **Bootstrap 5 nos templates.** O SUAP carrega o Bootstrap 6 (`bootstrap.min.css`), mas os templates seguem os nomes de classe do
> **Bootstrap 5**, servidos pelo `bootstrap5-compat.min.css` (`text-center`, `mt-4`, `col-md-6`, `d-lg-none`, `form-select`,
> `btn-primary`...). Não use nomes que só existem no 6 (`.grid`, `.form-group`, `.text-sm`...) nem o prefixo de breakpoint do 6
> (`md:col-6`, `lg:d-none`): o tema neutraliza alguns desses nomes porque o 6 lhes deu estilo próprio, mas o resultado é o do 5.

O styleguide tem 8 abas: **Geral, Botões e ações, Tabelas e Listas, Formulários, Mensagens,
Navegação, Caixas/Seções, Componentes**. O *long tail* (timeline, calendário, gráficos, passos,
foto de pessoa, avaliação por estrelas…) está documentado lá com HTML pronto — consulte na hora de usar.

---

## 2. Regras inquebráveis

Estas são as que um gerador erra. Valem para qualquer tela.

1. **Nunca usar `style=""`** em tag HTML. Cor/espaçamento só via classe utilitária ou variável CSS.
2. **Cor só via variável CSS** (`var(--primary-700)`, `var(--danger)`). **Nunca hex hardcoded.**
   O SUAP tem ≈8 temas (default teal, Dunas, Luna, Aurora, GovBR, IFs, Alto Contraste, Daltonismo);
   o tema ativo troca **todas** as variáveis. Hex fixo quebra sob outro tema.
3. **Um único `<h2>` por página** = o título (vem do bloco `content_title`/`title`). O `<h1>` é o
   sistema (template). Hierarquia abaixo: `h3` → `h4` → `h5`.
4. **Nomenclatura** (títulos/labels): só a 1ª inicial maiúscula (exceto nomes próprios); pontuar mensagens.
   Verbos de ação:

   | Use | Não use |
   |---|---|
   | Adicionar | ~~Cadastrar~~ |
   | Editar | ~~Atualizar~~, ~~Alterar~~ |
   | Remover | ~~Excluir~~, ~~Apagar~~, ~~Deletar~~ |
   | Visualizar | ~~Ver~~, ~~Abrir~~ |
5. **Formulários sempre via `{% render_form form %}`** — não montar `<input>` à mão.
6. **HTML semântico**: `a`, `strong`, `em`, `small`, `abbr`, `dl/dt/dd`, `ol/ul/li`. Tags `center`,
   `font`, `u` são proibidas (depreciadas).
7. **Indentação: 4 espaços**, nunca tab.
8. **Acessibilidade**: ícone sem texto exige `<span class="visually-hidden">Label</span>`; tooltip via
   `aria-label`; imagem com `alt`.

---

## 3. Tokens

### Cores — convenção `--{paleta}-{step}`

Paletas: `primary, grey, info, success, warning, caution, danger, violet, lime, pink, cyan, brown, steel`.
Steps: `50, 75, 100, 150, 200, 250, 300, 350, 400, 450, 500, 550, 600, 650, 700, 750, 800, 850, 900`
(50 = mais claro, 900 = mais escuro).

Aliases semânticos (use **estes** em vez do step quando houver intenção semântica):

| Alias | Resolve p/ | Uso |
|---|---|---|
| `--primary` | `--primary-700` | marca / ação principal |
| `--info` | `--info-600` | informação (azul) |
| `--success` | `--success-600` | sucesso (verde) |
| `--warning` | `--warning-600` | atenção (amarelo) |
| `--caution` | `--caution-600` | cautela (laranja) |
| `--danger` | `--danger-600` | erro/remoção (vermelho) |
| `--grey` / `--black` / `--white` | — | neutros |
| `--{paleta}-bg` | `--{paleta}-100` | fundo suave da paleta |

Ex.: `color: var(--danger);` / `background-color: var(--primary-100);`. **Nunca** `#0A7F70`.

### Layout / espaçamento / tipografia (de `variables.scss`)

- Fonte: `--primary-font-family: "Open Sans", "Lato", sans-serif`; mono: `--monospace-font-family`.
- Ícones: **Font Awesome 5 Free (Solid)** via tag `{% icone "nome" %}`. Para adicionar
    classes CSS ao `<span>` do ícone, use o argumento opcional `extra_class`, por exemplo
    `{% icone "home" extra_class="minha-classe" %}`.
- Raio: `--border-radius: 5px`; sombra: `--box-shadow`.
- Larguras: `--basis-nav: 270px`, `--basis-aside: 380px`, `--labels-width: 170px`, `--filter-width: 200px`.
- Espaçamentos: `--main-p: 4rem`, `--card-padding: 2.5rem`, `--gap: 1rem`, `--regular-margin: 2rem`.
- Utilitárias (Bootstrap-like, já no projeto): `mt-*`, `mb-*`, `pt-*`, `ms-auto`, `text-end`,
  `text-center`, `text-white`, `float-end`, `d-flex`, `flex-wrap`, `gap-*`, `w-100`, `visually-hidden`,
  `fw-light/medium/bold`. Prefira estas a `style=""`.

---

## 4. Esqueleto da página (template Django)

Toda tela "de sistema" estende `super_template` (resolvido pelo decorator `@rtr`) e preenche blocos.
**Não** crie `<html>`/`<head>`/`<body>` — isso é do `admin/base.html`.

```django
{% extends super_template %}

{% block object-status %}
    {# tags de situação ao lado do título — opcional #}
    <span class="status status-success">Ativo</span>
{% endblock %}

{% block action-bar %}
    <ul class="action-bar">
        <li><a class="btn success" href="{% url 'minha_app_adicionar' %}">{% icone "plus" %} Adicionar</a></li>
    </ul>
{% endblock %}

{% block content %}
    {# conteúdo principal aqui #}
{% endblock %}
```

Blocos úteis do base: `content_title` (já renderiza o `<h2>{{ title }}</h2>`), `object-status`,
`action-bar`, `subtitle`, `content`, `action-links`, `extracss`, `extrascripts`.

### View canônica

```python
from djtools.utils import rtr
from django.contrib.auth.decorators import login_required

@rtr('minha_app/minha_tela.html')
@login_required
def minha_tela(request):
    title = 'Minha tela'          # vira o <h2> da página
    objetos = MeuModel.objects.all()
    return locals()               # tudo no locals() vai pro contexto
```

Layout global (de `base.html`): `.holder` → `aside.nav` (menu lateral) + `main#content`
(breadcrumbs, `title-container`, conteúdo, `action-links`) + `footer`.

---

## 5. Componentes de alta frequência (com código)

> Verifique sempre na aba correspondente do styleguide; abaixo, o essencial verificado contra o scss.

### Botões — `btn` + variante

```html
<a class="btn success" href="#">Confirmação</a>   <!-- fluxo principal: adicionar/aceitar/enviar -->
<a class="btn primary" href="#">Edição</a>         <!-- editar/alterar -->
<a class="btn" href="#">Ação secundária</a>        <!-- imprimir/exportar/relatório -->
<a class="btn default" href="#">Informações</a>    <!-- visualizar -->
<a class="btn danger" href="#">Remoção</a>         <!-- remover (confirma sozinho) -->
<a class="btn warning" href="#">Atenção</a>        <!-- ação que pede cautela -->
```

Modificadores: `disabled`, `disable_on_click` (com `data-href`), `popup` (abre em popup),
`confirm` (com `data-confirm="msg"`). Ícone: `{% icone "home" %} Início`. Só ícone:
`{% icone "home" %}<span class="visually-hidden">Início</span>`.

### Barra de ações — `ul.action-bar` (dentro de `{% block action-bar %}`)

```html
<ul class="action-bar">
    <li><a class="btn primary" href="#">Editar</a></li>
    <li class="has-child">
        <a class="btn" href="#">Outras opções</a>
        <ul>
            <li><a href="#">Subação 1</a></li>
            <li><a href="#">Subação 2</a></li>
        </ul>
    </li>
    <li><a class="btn danger" href="#">Remover</a></li>
</ul>
```

### Ícones de ação em listas/tabelas — tag `{% icon %}`

```django
{% icon "view" "{{ obj.get_absolute_url }}" "Visualizar" %}
{% icon "edit" "{{ url_editar }}" %}
{% icon "delete" "{{ url_remover }}" %}
```

Os argumentos **não são variáveis de template**: a tag tira o primeiro e o último caractere de
cada um (as aspas) e renderiza o resto como template. A URL vai sempre entre aspas e com `{{ }}`.
Sem aspas, `obj.get_absolute_url` vira o link relativo `.get_absolute_ur` (404).

### Tabelas — `div.table-responsive > table`

```html
<div class="table-responsive">
    <table>
        <caption>Título da tabela</caption>
        <thead>
            <tr><th>#</th><th>Nome</th><th>Valor</th></tr>
        </thead>
        <tbody>
            <tr><td>1</td><td>Item</td><td class="text-end">250</td></tr>
            <tr class="highlight"><td>2</td><td>Destacado</td><td class="text-end">100</td></tr>
            <tr class="error"><td>3</td><td>Erro</td><td class="text-end">50</td></tr>
            <tr class="disabled"><td>4</td><td>Inativo</td><td class="text-end">0</td></tr>
        </tbody>
        <tfoot><tr><td colspan="2">Total:</td><td>450</td></tr></tfoot>
    </table>
</div>
```

`tfoot` já vem negrito/à direita. Linhas: `highlight`, `error`, `extra`, `disabled`.

### Lista de definições — `dl.definition-list`

```html
<dl class="definition-list">
    <dt>Nome:</dt><dd>Lorem Ipsum</dd>
    <dt>E-mail:</dt><dd>loremipsum@exemplo.com.br</dd>
</dl>
```

### Situação / status — `span.status status-{tipo}`

```html
<span class="status status-info">Informação</span>
<span class="status status-alert">Alerta</span>
<span class="status status-success">Sucesso</span>
<span class="status status-error">Erro</span>
<span class="status status-default" aria-label="Detalhe ao passar o mouse">Normal</span>
<span class="status status-final">Final</span>
<span class="status disabled">Desabilitado</span>
```

Dica: o CSS já mapeia nomes de situação comuns (`status-concluido`, `status-cancelado`,
`status-deferido`…) — basta hifenizar o valor do modelo.

### Alertas (na própria página) — `.alert .alert-{tipo}`

```html
<p class="alert alert-warning"><strong>Atenção:</strong> mensagem.</p>
<p class="alert alert-danger"><strong>Atenção:</strong> mensagem.</p>
<div class="alert alert-info"><strong>Informação:</strong> mensagem com <ul><li>itens</li></ul></div>
<p class="alert alert-light"><strong>Dica:</strong> mensagem neutra.</p>
```

### Feedback (telas públicas) — `.feedback .{success|danger}`

```html
<div class="feedback success">
    <h3 class="title">Inscrição realizada com sucesso.</h3>
    <p class="description">Detalhes.</p>
    <ul class="action-bar"><li><a href="#" class="btn">Voltar</a></li></ul>
</div>
```

### Caixa retrátil — tag `{% box %}`

```django
{% box "Título da caixa" "collapsed" badge=3 extra="Atualizado em 02/10/2025" %}
    <p>Conteúdo da caixa.</p>
{% endbox %}
```

Args posicionais: `title` (obrig.), `class` (`collapsed` = inicia fechada), `boxid`, `badge`;
nomeados: `badge=`, `extra=`. Renderiza um accordion Bootstrap.

### Abas dinâmicas — `div.tab-pane`

```html
<div class="tab-pane" data-title="Resumo" data-tab="resumo" data-counter="4">…</div>
<div class="tab-pane" data-title="Detalhes" data-tab="detalhes">…</div>
```

`data-title` (obrig.), `data-tab` (vira parâmetro de URL), `data-counter`, `data-checked`,
`data-hide-tab-on-counter-zero`.

### Formulário

```django
{% render_form form %}
```

Componentes de form do styleguide: `switch` (`label.switch > input + span.slider`),
`custom-checkbox`, `checkboxes` (radios/checkbox inline), `markall-container`.

### Tooltip / hint

```html
<span class="hint hint-top" aria-label="Texto do tooltip">Passe o mouse</span>
<span class="hint hint-bottom" aria-label="Texto do tooltip">…</span>
```

### Badge

```html
<span class="badge">12</span>
```

---

## 6. Long tail (consultar styleguide antes de usar)

Existem e estão documentados em `/comum/design_system/` (aba e arquivo `guia_*`):
**farol** (`div.farol .success/.warning/.danger` + `{% progressbar N %}`), **widget**, **painel**
(`boards > board-container`), **galeria de fotos** (`gallery > gallery-item`), **checklist**,
**passos/steps**, **timeline**, **calendário**, **gráficos**, **foto de pessoa**, **avaliação por
estrelas**, **barra de progresso/carregamento** (`page-loader`, `loader`), **listas de links**
(`counter-container`, `numbered-list`), **âncoras**, **pills**, **copy to clipboard**
(`data-clipboard`). Copie o HTML do guia correspondente — não improvise.

---

## 7. Checklist de conformidade (antes de entregar uma tela)

- [ ] Template estende `super_template` e usa os blocos certos (sem `<html>/<head>/<body>`).
- [ ] Zero `style=""`; zero hex hardcoded (cor só via `var(--…)` / classe utilitária).
- [ ] Um único `<h2>` (o `title`); hierarquia h3/h4/h5 abaixo.
- [ ] Toda classe usada existe no scss (`pre/post/forms`) — conferir contra a whitelist.
- [ ] Botões com a variante semântica certa (`success` p/ adicionar, `danger` p/ remover…).
- [ ] Nomenclatura: Adicionar/Editar/Remover/Visualizar; 1ª maiúscula; mensagens pontuadas.
- [ ] Formulários via `{% render_form form %}`.
- [ ] Ícones sem texto têm `visually-hidden`; imagens têm `alt`; tooltips usam `aria-label`.
- [ ] Indentação 4 espaços.

---

## 8. Exemplo completo verificado

Veja `docs/design-system-exemplo.html` — uma tela de listagem real montada só com componentes do DS
(title via view, `object-status`, `action-bar`, tabela, `box`, `status`, `definition-list`). Serve de
referência e *few-shot* para o agente. Todas as classes dela foram conferidas contra o scss.
