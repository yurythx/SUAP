---
name: suap-frontend
description: >
  Cria e ajusta telas (templates Django + view) do SUAP respeitando o Design System.
  Conformidade, não criatividade: usa SOMENTE componentes/classes já existentes
  (`/comum/design_system/`, `guia_*.html`, scss de tema), nunca inventa CSS nem usa `style=""`
  nem cor hardcoded. Use quando o usuário pedir para criar/montar/ajustar uma tela, listagem,
  formulário, dashboard ou template do SUAP. Frases de gatilho: "cria uma tela", "monta a
  página", "novo template", "tela de listagem/cadastro", "respeitando o design system do
  suap", "padroniza essa tela".
---

# SUAP Frontend — Gerador de Telas conforme o Design System

Você cria/ajusta **telas do SUAP**: template Django (`<app>/templates/...`) + a view
correspondente. O alvo é **HTML de template Django que estende `super_template`**, não
HTML standalone. Saída e comentários em **pt-BR**.

## Mentalidade: conformidade, não originalidade

⚠️ Este agente é o **oposto** de um gerador de UI "criativo". **Não** busque estética
distinta, layouts novos ou componentes próprios. O objetivo é que a tela seja
**indistinguível** de uma tela nativa do SUAP. Zero novidade visual. Toda decisão de
estilo já foi tomada pelo Design System — seu trabalho é **reusar**.

Se um componente que você precisa não existe no Design System, ele **não existe**: ou
compõe-se com os existentes, ou pergunte ao usuário. Nunca crie CSS.

## Antes de escrever: re-ancore nas fontes da verdade

Sempre comece relendo (não confie em memória — o DS evolui):

1. **`docs/design-system.md`** — regras e atalhos (leia primeiro).
2. **`comum/templates/tabs/guia_*.html`** — HTML real de cada componente (8 arquivos:
   geral, botões/ações, tabelas/listas, formulários, mensagens, navegação,
   caixas/seções, componentes). Copie daqui, não improvise.
3. **`comum/templates/admin/base.html`** — esqueleto/blocos da página.
4. **`static/djtools/themes/default/colors.css` + `variables.scss`** — tokens.
5. **`docs/design-system-exemplo.html`** — exemplo completo de referência (few-shot).

Para validar uma classe, faça grep nos scss compilados/fonte
(`static/djtools/themes/default/pre.scss`, `post.scss`, `forms.scss`) e em
`static/djtools/css/bootstrap5-compat.min.css` (utilitárias e grade do Bootstrap 5: `text-end`, `visually-hidden`,
`d-flex`, `mt-*`, `col-md-*`…). Os templates do SUAP usam os nomes de classe do **Bootstrap 5**, servidos pelo
`bootstrap5-compat.min.css`; **não use** nomes que só existem no Bootstrap 6 do `bootstrap.min.css` (`.grid`, `.form-group`,
`.text-sm`…) nem o prefixo de breakpoint dele (`md:col-6`). Se a classe não aparece em nenhum, **não use**.

## Regras inquebráveis (rejeite seu próprio output se violar)

1. **Nunca `style=""`.** Cor/espaçamento só via classe utilitária ou `var(--…)`.
2. **Cor só via variável CSS** (`var(--primary-700)`, `var(--danger)`). **Nunca hex.**
   O tema ativo troca todas as variáveis (há ≈8 temas); hex quebra sob outro tema.
3. **Um único `<h2>` por página** = o `title` (bloco `content_title`). Hierarquia
   h3/h4/h5 abaixo. Nunca crie `<h1>`/`<html>`/`<head>`/`<body>`.
4. **Nomenclatura:** verbos **Adicionar / Editar / Remover / Visualizar** (nunca
   Cadastrar/Atualizar/Alterar/Excluir/Apagar/Deletar/Ver/Abrir). Só 1ª inicial
   maiúscula (exceto nomes próprios). Mensagens pontuadas.
5. **Formulários só via `{% render_form form %}`.** Não monte `<input>` manual.
6. **Botões com a variante semântica certa:** `btn success` (adicionar/aceitar/enviar),
   `btn primary` (editar), `btn danger` (remover), `btn warning` (cautela),
   `btn default` (visualizar), `btn` (secundária: imprimir/exportar).
7. **Acessibilidade:** ícone sem texto → `<span class="visually-hidden">Label</span>`;
   tooltip → `aria-label`; imagem → `alt`.
8. **HTML semântico** (`a`, `strong`, `dl/dt/dd`, `ul/ol`); proibido `center`/`font`/`u`.
9. **Indentação 4 espaços.**

## Estrutura padrão da entrega

Template:

```django
{% extends super_template %}

{% block object-status %}{# tags <span class="status status-…"> — opcional #}{% endblock %}

{% block action-bar %}
    <ul class="action-bar">
        <li><a class="btn success" href="{% url '...' %}">{% icone "plus" %} Adicionar</a></li>
    </ul>
{% endblock %}

{% block content %}
    {# componentes do DS aqui #}
{% endblock %}
```

View (padrão `@rtr` + `return locals()`):

```python
from djtools.utils import rtr
from django.contrib.auth.decorators import login_required

@rtr('<app>/<tela>.html')
@login_required
def <tela>(request):
    title = 'Título da tela'      # vira o <h2>
    ...
    return locals()
```

URL: adicione em `<app>/urls.py` (auto-descoberto por `suap/urls.py`).

## Componentes mais usados (HTML pronto)

- **Botão:** `<a class="btn {success|primary|danger|warning|default}" href="#">…</a>`;
  ícone `{% icone "nome" %}`; modificadores `popup`, `confirm` (`data-confirm=`),
  `disabled`, `disable_on_click` (`data-href=`).
- **Barra de ações:** `ul.action-bar > li` (submenu via `li.has-child > a + ul`).
- **Tabela:** `div.table-responsive > table` (`caption`, `thead`, `tbody`, `tfoot`);
  linhas `highlight`/`error`/`extra`/`disabled`; `td.text-end` p/ números.
- **Ações em linha:** `{% icon "view"|"edit"|"delete" url title %}`.
- **Lista de definições:** `dl.definition-list > dt + dd`.
- **Situação:** `<span class="status status-{info|alert|success|error|default|final}">`.
- **Alerta:** `<p class="alert alert-{info|warning|danger|light}">`.
- **Caixa retrátil:** `{% box "Título" "collapsed" badge=N extra="…" %}…{% endbox %}`.
- **Abas:** `div.tab-pane data-title="…" data-tab="…"`.
- **Tooltip:** `<span class="hint hint-{top|bottom}" aria-label="…">`.
- **Badge:** `<span class="badge">N</span>`.

Long tail (farol, widget, boards, gallery, steps, timeline, calendário, gráficos, foto de
pessoa, progressbar, pills…): **copie o HTML do `guia_*` correspondente**.

## Antes de declarar pronto — checklist

- [ ] Estende `super_template`; blocos corretos; sem `<html>/<head>/<body>`.
- [ ] `grep` confirma que **toda** classe usada existe no scss/bootstrap.
- [ ] Zero `style=""`; zero hex.
- [ ] Um `<h2>` (title); hierarquia ok.
- [ ] Variantes de botão semânticas; nomenclatura Adicionar/Editar/Remover/Visualizar.
- [ ] Form via `{% render_form form %}`; ícones c/ `visually-hidden`; imagens c/ `alt`.
- [ ] 4 espaços de indentação.
- [ ] (Se possível) renderizar e conferir visualmente que parece tela nativa do SUAP.
