# Modernização da interface — fase 2: componentes centrais

Data: 2026-10-15
Status: aprovada; implementada no branch `claude/modernizacao-fase2-componentes`
Antecedente: fase 1 (`docs/superpowers/specs/2026-10-15-modernizacao-fase1-tokens-design.md`, mergeada).
Depois: fase 3 (layout e navegação).

## Objetivo

Modernizar os quatro grupos de componentes mais usados do SUAP — botões (1.152 templates), formulários (todo
`{% render_form %}` e o admin), mensagens (1.438 templates) e abas/caixas (todo `tabs.js` e `{% box %}`) —
mantendo a identidade, por **tokens CSS** no tema default, como na fase 1.

## O que o usuário decidiu × suposições

- Decidido (comparação visual sobre telas reais, 15/10/2026): botões **A (refinado)**, formulários **B (moderno)**,
  mensagens **B (moderno)**, abas e caixas **A (refinado)**.
- Decidido: temas que já têm valor próprio para um componente **mantêm o seu** (mesma regra da fase 1).
- Consequência registrada: Aurora, Dunas, GovBR, IFS, Luna e Alto Contraste já redefinem botão (`--btn-color`) e campo
  (`%inputs`); nesses dois componentes a mudança aparece de fato no **Padrão** e no **Modo Daltonismo**.

## Design

Tokens novos vão no `:root` do `djtools/static/djtools/themes/default/pre.scss`. Cor só por variável; nada de hex.

### 1. Botões — A (refinado)

**Desfeito em 16/10/2026, a pedido:** o `.btn` sem variante voltou ao preenchimento escuro de antes (`%btn`, `--btn-color`), sem
o contorno; os tokens `--btn-secondary-*` e a regra saíram, inclusive as linhas de preservação dos temas.

Só o botão **secundário** (`.btn` sem variante) muda; pílula, cores das variantes (`success`, `primary`, `danger`,
`warning`, `default`) e tamanhos ficam.

| Token | Valor no Padrão | Antes |
|---|---|---|
| `--btn-secondary-color` (novo) | `var(--white)` | `--btn-color` (`var(--grey-700)`) |
| `--btn-secondary-text-color` (novo) | `var(--grey-850)` | (usava `--btn-text-color`, branco) |
| `--btn-secondary-border-color` (novo) | `var(--grey-500)` (3,95:1 sobre branco) | sem contorno |
| `--btn-secondary-hover-color` (novo) | `var(--grey-100)` | `--btn-active-color` (preto) + texto branco |
| `--btn-secondary-hover-text-color` (novo) | `var(--grey-900)` | branco |
| `--btn-secondary-hover-shadow` (novo) | `inset 0 0 0 1px var(--grey-600)` | — |

- `--btn-color` **não muda**: ele também pinta `input[type=submit]` sem `.btn` (122 templates), que segue preenchido
  como ação principal. O secundário ganha token próprio (`--btn-secondary-color`).
- O contorno é `box-shadow: inset 0 0 0 1px var(--btn-secondary-border-color)` (não muda a altura do botão); no hover,
  fundo `--grey-100` e contorno `--grey-600`. A regra só pega `.btn` sem variante: variantes, `.disabled`, `:disabled` e
  `[disabled]` ficam de fora (o botão desabilitado não ganha contorno).
- `--btn-text-color` continua branco: as variantes o usam (`--btn-danger-text-color: var(--btn-text-color)` etc.).
- Temas que definem `--btn-color` próprio (Aurora, Dunas, GovBR, IFS, Luna, Alto Contraste) ganham no `:root` as linhas
  que apontam os tokens secundários para o que já usam (`--btn-secondary-color: var(--btn-color)`,
  `--btn-secondary-text-color: var(--btn-text-color)`, `--btn-secondary-border-color: transparent`,
  `--btn-secondary-hover-color: var(--btn-active-color)` e o texto e a sombra de hover que já tinham), para não mudar.

### 2. Formulários — B (moderno)

Campo preenchido que fica branco no foco.

| Token | Valor no Padrão | Antes |
|---|---|---|
| `--input-bg-color` (existe) | `var(--grey-50)` | `var(--white)` |
| `--input-border-color` (novo) | `var(--grey-150)` (topo e laterais) | `var(--grey-300)` fixo |
| `--input-border-bottom-color` (novo) | `var(--grey-500)` (3,95:1, WCAG 1.4.11) | `var(--grey-300)` |
| `--input-placeholder-color` (novo) | `var(--grey-600)` (5,6:1 sobre `--grey-50`) | o do navegador (4,49:1) |
| `--input-radius` (novo) | `8px` | `var(--border-radius)` (5px) |
| `--input-focus-bg-color` (novo) | `var(--white)` | — |
| `--input-focus-border-color` (novo) | `var(--primary)` | — (borda do select2 no foco) |
| `--input-focus-ring` (novo) | `0 0 0 1px var(--primary-100)` | — (só borda teal) |
| `--input-error-bg-color` (novo) | `var(--danger-50)` | fundo amarelo da linha do form |

- Vale para `%inputs` (texto, número, data, e-mail, senha, busca), `select`, `textarea` e o contêiner do select2
  (`.select2-selection`). O campo de busca interno do select2 (`.select2-search__field`) fica de fora (borda dupla).
- Só a borda inferior chega a 3:1 (convenção de campo preenchido); topo e laterais ficam suaves. Vale também para o
  select2.
- Foco: fundo `--input-focus-bg-color`, borda `--primary` (no select2, `--input-focus-border-color`), anel
  `--input-focus-ring` como `box-shadow` — não é `outline`, então convive com o `--campo-foco-outline-style` da fase 1
  (sem anel duplo). No select2 o outline do `:focus-visible` sai pelo token `--select2-foco-outline-style` (`none` no
  Padrão; `solid` nos temas sem anel e com borda de foco neutra, onde o outline é o único indicador).
- Campo somente leitura mantém o fundo `--grey-400`, também focado.
- Erro (`.form-row.errors`): fundo `--input-error-bg-color` só nos campos de digitação (os tipos do `%inputs`, `select`,
  `textarea`; fora de botão, somente leitura e desabilitado), borda `--false-color`; a mensagem (`.errorlist`) ganha
  ícone (`\f06a`, Font Awesome) **em todos os temas** e fica em `--false-color` (`--danger-600`, 5,9:1 sobre o amarelo
  da linha de erro).
- Busca do menu lateral: sem o anel de foco (a borda inferior já indica) e placeholder em
  `--aside-search-placeholder-color` (`--grey-400`, 5,3:1 sobre a barra `--grey-850`); temas preservados mantêm o que
  já tinham.
- Temas com `%inputs` próprio (Aurora, Dunas, GovBR, IFS, Luna, Alto Contraste) mantêm o seu (exceto o ícone da
  `.errorlist`).

### 3. Mensagens — B (moderno)

- `%msg`: `border-radius: var(--msg-border-radius)`, com `--msg-border-radius: 8px` (antes `var(--border-radius)`).
- Ícone e fundo suave continuam como estão. Aurora, Dunas, GovBR e Luna mantêm o raio próprio
  (`--msg-border-radius: var(--border-radius)`).

### 4. Abas e caixas — A (refinado)

**Abas trocadas em 16/10/2026, a pedido (a aba ativa ficava pouco clara):** aba de pasta — a ativa é branca, colada no
painel (borda de baixo branca) e com faixa de 3px `--tabs-indicator-color` no topo; as inativas quase brancas (`--grey-50`) com
borda `--grey-200`, para não parecerem desabilitadas; linha de base `--grey-300`. Só Padrão e Modo Daltonismo; os outros seis
temas incluem `@mixin abas-classicas` e mantêm as abas (medido: estilos das abas idênticos). O sublinhado de 2px abaixo foi
substituído; as caixas seguem como descrito.

| Token | Valor no Padrão | Onde |
|---|---|---|
| `--tabs-indicator-color` (novo) | `var(--primary-700)` | `%nav-tabs`: aba ativa com sublinhado de 2px |
| `--tabs-baseline-color` (novo) | `var(--grey-200)` | linha de base de 1px sob as abas |
| `--tabs-link-bg-color` (novo) | `transparent` | fundo da aba inativa |
| `--tabs-link-active-bg-color` (novo) | `transparent` | fundo da aba ativa no hover (Aurora e GovBR: `--white`) |
| `--tabs-index-border` (novo) | `2px solid var(--tabs-indicator-color)` | aba ativa sob `body.index` (Aurora, Dunas, GovBR, Luna: `1px solid var(--grey-200)`) |
| `--box-border-color` (novo) | `var(--grey-200)` | `%accordion`: `--bs-accordion-border-color` (era `--primary-600`) |

- **Largura estática (16/10/2026, a pedido, acessibilidade):** a aba já nasce com a largura do rótulo em negrito
  (`.rotulo-aba` + `::after` invisível no peso `--tabs-link-active-weight`, montado pelo `tabs.js`), então selecionar não alarga
  nem empurra as vizinhas; temas com peso próprio na aba ativa (GovBR, Luna, Aurora) redefinem o token.
- Aba: sem a "orelha" com borda; inativa com texto `--primary-800` (atual) e fundo transparente; ativa com texto
  `--grey-900`, peso 600 e o sublinhado. O foco por teclado da aba continua visível (`:focus-visible` da fase 1).
- Sob `body.index` a aba ativa usa `--tabs-index-border`, então o sublinhado aparece também na tela inicial; o Alto
  Contraste ganha ali o sublinhado de 2px que já mostra nas outras telas.
- Temas com `%nav-tabs` próprio (Aurora, Dunas, GovBR, Luna) e com `%accordion`/borda de accordion própria
  (Alto Contraste, Aurora, Dunas, IFS, Luna, Modo Daltonismo) mantêm os seus.

## Alcance por tema

| Tema | Botão secundário | Campo | Mensagem | Abas | Caixa |
|---|---|---|---|---|---|
| Padrão | muda | muda | muda | muda | muda |
| Modo Daltonismo | muda | muda | muda | muda | mantém (borda própria) |
| IFS | mantém | mantém | muda | muda | mantém |
| GovBR | mantém | mantém | mantém | mantém | muda |
| Aurora, Dunas, Luna | mantêm | mantêm | mantêm | mantêm | mantêm |
| Alto Contraste | mantém | mantém | muda | muda (também sob `body.index`) | mantém |

(A medição por tema na implementação confirma esta tabela; onde o herdado falhar contraste, o tema redefine o token.)
Em todos os temas a mensagem de erro do campo (`.errorlist`) ganha o ícone.

## Riscos

- **Botão secundário em contorno** em telas onde ele é a ação principal visível (barras de ação só com `.btn`): perde
  peso visual. Mitigação: screenshots das barras de ação; é a intenção (cor fica para ação com significado).
- **Especificidade**: lição da fase 1 — regra nova no default pode vencer estado de Bootstrap ou de tema (foco, `.active`,
  `:disabled`). Conferir no CSS compilado e em teste que foco, desabilitado e ativo continuam visíveis.
- **select2**: estilo próprio de foco e de seleção múltipla; conferir na tela de formulário real.
- **Contraste do campo preenchido**: texto e placeholder sobre `--grey-50`; borda `--grey-150` é limite do componente
  (WCAG 1.4.11 pede 3:1 para identificar o campo) — medir; se falhar, o anel de foco e o fundo diferenciado são o que
  identifica o campo, e a borda sobe para um tom que passe.

## Fora do escopo

Layout e navegação (fase 3); cores e formato pílula das variantes de botão; tabelas (já tratadas na fase 1);
badges; templates de módulo.

## Verificação

1. Os 8 temas compilam.
2. e2e novo por componente (no padrão de `tests/e2e/test_tema_visual.py`): secundário com contorno e hover;
   campo preenchido, foco com anel e erro com fundo; raio da mensagem; aba ativa sublinhada; borda da caixa.
3. Gate axe (`tests/e2e/test_acessibilidade.py`) verde, e rodada única sob Alto Contraste e Luna sem violação nova.
4. e2e `tests/e2e` + `comum/tests/e2e` verdes.
5. Contraste medido por tema (texto e placeholder no campo; borda do campo; texto do secundário; sublinhado da aba).
6. Screenshots antes/depois das mesmas quatro cenas reais (design system: botões e mensagens; formulário com erro;
   detalhe de servidor: abas e caixas) em Padrão, Alto Contraste, GovBR e Luna — mostrados ao usuário antes do MR.
7. `pre-commit run --from-ref origin/master --to-ref HEAD`.
