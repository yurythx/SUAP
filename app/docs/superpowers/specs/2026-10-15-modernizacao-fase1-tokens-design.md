# Modernização da interface — fase 1: tokens visuais

Data: 2026-10-15
Status: aprovada; implementada no branch claude/modernizacao-fase1-tokens
Antecede: fase 2 (componentes centrais) e fase 3 (layout e navegação), cada uma com spec e MR próprios.

## Objetivo

Dar ao SUAP um visual mais atual sem trocar a identidade: texto base por token (mantido em 13px), sombra discreta,
cabeçalho de caixa limpo, título em grafite, cabeçalho de tabela leve e realce da linha sob o mouse.
Tudo por **tokens CSS** no tema default, que os 8 temas importam; um tema recusa um ajuste
redefinindo o token.

## O que o usuário decidiu × suposições

- Decidido: modernizar "tudo, em etapas" (tokens → componentes → layout); todos os temas herdam;
  base visual **A (atual)** com os **seis ajustes**; abordagem por **tokens** num MR.
- Suposição: o texto do cabeçalho de caixa continua teal (só o fundo vira branco com divisória).
- Correção registrada: no tema real o título da página já é preto (`--title-container-color: var(--black)`);
  o ajuste 4 suaviza para grafite.

## Os seis ajustes

| # | Ajuste | Token | Valor no Padrão | Antes | Onde é lido |
|---|---|---|---|---|---|
| 1 | Texto base pelo token (mantido em 13px) | `--body-font-size` (novo) | `1.3rem` | `1.3rem` fixo | `body` (`default/post.scss:~85`) |
| 2 | Sombra discreta | `--box-shadow` (existe) | `0 1px 2px rgb(0 0 0 / .06), 0 2px 8px rgb(0 0 0 / .04)` | `10px 10px 35px 0 rgba(0,0,0,.05)` | `default/variables.scss:~78` |
| 3 | Cabeçalho de caixa branco com divisória | `--box-header-bg`, `--box-header-divider-color` (novos; o segundo é só a cor, a geometria é a do Bootstrap: inset de 1px) | `var(--white)`, `var(--grey-150)` | `--bs-accordion-active-bg: var(--primary-50)` | `%accordion` (`default/pre.scss:~239`): `--bs-accordion-active-bg` e o `box-shadow` inset do `.accordion-button:not(.collapsed)` |
| 4 | Título da página em grafite | `--title-container-color` (existe) | `var(--grey-850)` | `var(--black)` | `default/pre.scss:~30` |
| 5 | Cabeçalho de tabela em caixa alta pequena (**desfeito em 16/10/2026, a pedido: o th voltou à caixa, ao tamanho e ao espaçamento normais**) | `--table-thead-transform`, `--table-thead-font-size`, `--table-thead-letter-spacing` (novos) | `uppercase`, `1.15rem`, `.04em` | sem transformação | `%table-thead` (`default/pre.scss:~1974`) |
| 6 | Realce da linha sob o mouse | `--table-row-hover-color` (novo) | `var(--primary-50)` | inexistente no Padrão | regra nova em `default/post.scss` |

Tokens novos vão em `:root` do `default/pre.scss`, junto de `--menu-logout-color` e
`--campo-foco-outline-style` (padrão do MR !19390). Cor só por variável; nada de hex.

### Regra do ajuste 6

Mesma exclusão que o Luna já usa (calendários e timeline ficam de fora), dentro de `:where()` para não somar especificidade e não vencer o hover de `.highlight`/`.selected`:

```scss
:where(*:not(.calendario-mensal)) > table:where(:not(.calendario-anual):not(.timeline-horizontal)) tbody tr:hover > td,
:where(*:not(.calendario-mensal)) > table:where(:not(.calendario-anual):not(.timeline-horizontal)) tbody tr:hover > th {
    background-color: var(--table-row-hover-color);
}
```

Linhas com estado (`.error`, `.extra`, `.info`, `.highlight`, `.selected`) vencem o realce por `!important`;
o `:where()` serve só para as exclusões não somarem especificidade. Conferido no e2e (`tr.selected` sob o mouse).

A zebra de `table.info` (`tr:nth-child(even) td`, especificidade (0,2,3)) vence a regra acima (0,1,4) e deixaria o
realce só nas linhas ímpares. Uma regra a mais, `table.info … tbody tr:hover > td` (0,2,4), cobre as linhas pares
e continua perdendo para as linhas/células de estado.

### Anel de foco no cabeçalho de caixa aberto

O `.accordion-button:not(.collapsed)` (0,3,0) fixa o `box-shadow` da divisória e apagaria o anel de foco do
Bootstrap. No `:focus` o `box-shadow` soma os dois: divisória + `var(--bs-accordion-btn-focus-box-shadow)`.

> **Atualização (Bootstrap 6.0.0-alpha.1).** O 6 não tem mais `--bs-accordion-btn-focus-box-shadow`: o foco do botão da caixa é o
> `:focus-visible` global do tema (`post.scss`, `outline: 2px solid var(--primary-700)`), que o `box-shadow` da divisória não
> apaga. O `box-shadow` somado acima deixou de existir.

## Ajuste 7 — fonte Inter (decidido em 15/10/2026, após comparação visual)

**Desfeito em 16/10/2026, a pedido:** a fonte voltou a ser a Open Sans, agora hospedada no SUAP
(`comum/static/comum/font/open-sans/`, variável, pesos 300 a 800, latin e latin-ext, da Fontsource 5.3.0), sem o import do
Google Fonts. Os números tabulares nas tabelas continuam.

Comparadas lado a lado a 13px: Open Sans (atual), Inter, Source Sans 3 e IBM Plex Sans. Escolhida a **Inter**.

- `--primary-font-family: "Inter", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif` (`default/variables.scss`).
- Hospedada no SUAP: `comum/static/comum/font/inter/InterVariable.woff2` e `InterVariable-Italic.woff2`, do release
  oficial v4.1 (https://github.com/rsms/inter, licença SIL OFL 1.1, `LICENSE.txt` ao lado). Os arquivos são os do release,
  sem alteração.
- Sai o `@import` do Google Fonts (Open Sans) do `default/post.scss`: nenhuma página pede fonte a terceiros (privacidade
  do usuário e uma dependência externa a menos). As `@font-face` da Lato continuam, porque ainda há quem a cite.
- Tabelas com `font-variant-numeric: tabular-nums` (`%table`): CPF, CNPJ e valores alinham na coluna.
- GovBR continua com a Rawline (token próprio).
- Efeito colateral corrigido: com a fonte local, o gate axe passou a enxergar as abas montadas pelo `tabs.js` na tela
  de detalhe, e elas tinham um defeito antigo de ARIA (`<li>` sem `role="presentation"` entre o `tablist` e a `tab`).

## Herança por tema

| Tema | 1 fonte | 2 sombra | 3 caixa | 4 título | 5 th | 6 hover |
|---|---|---|---|---|---|---|
| Padrão | herda | herda | herda | herda | herda | herda |
| Aurora | herda | mantém o seu (`--box-shadow` próprio) | mantém (`%accordion` próprio) | herda | herda | herda |
| Dunas | herda | mantém | mantém sem divisória (token `transparent`) | herda | mantém caixa normal (`%box-title` próprio + `--table-thead-letter-spacing: normal`) | herda |
| GovBR | herda | mantém | herda | mantém (`--title-container-color` próprio) | recusa (`--table-thead-transform: none`) | herda |
| IFS | herda | herda | herda | mantém | herda | herda |
| Luna (escuro) | herda | mantém | **redefinir** `--box-header-bg`/`--box-header-divider-color` se o branco aparecer no tema escuro | herda | herda | mantém (hover próprio `--grey-900`) |
| Alto Contraste | herda | herda | mantém (`%accordion` próprio) | herda | herda | não redefine; o tema força `td` transparente (`!important`), então o realce não aparece |
| Modo Daltonismo | herda | herda | herda | herda | herda | herda |

Regra geral: onde o valor herdado ficar abaixo de 4,5:1 (texto) ou 3:1 (borda/divisória), o tema
redefine o token com outro token existente da própria paleta.

## Riscos

- **Tamanho do texto (ajuste 1)**: depois de ver o resultado, o usuário preferiu manter 13px (15/10/2026); o token fica, valendo `1.3rem`. O risco abaixo valia para 14px: larguras fixas (`--labels-width: 170px`, `--filter-width: 200px`) e tabelas
  densas podem quebrar linha. Mitigação: screenshots antes/depois; se uma tela crítica quebrar, ajustar
  o token de largura no default (não por template).
- **Caixa alta (ajuste 5)**: cabeçalhos longos ocupam mais largura; `1.15rem` + espaçamento compensa.
  `text-transform` não muda o texto lido pelo leitor de tela.
- **Hover (ajuste 6)**: tabelas com fundo próprio por célula (ex.: quadros com cor) podem conflitar;
  coberto pela exclusão e pela checagem visual.

## Fora do escopo

Componentes (fase 2), layout e navegação (fase 3), templates de módulo. (A troca de família de fonte entrou depois, como ajuste 7.)

## Verificação

1. Os 8 temas compilam (`sass.compile` de `djtools/static/djtools/themes/<tema>/main.scss`).
2. Gate axe `tests/e2e/test_acessibilidade.py` verde no Padrão e numa rodada única sob Alto Contraste e Luna.
3. e2e `tests/e2e` + `comum/tests/e2e` verdes.
4. Medição por tema (Playwright + CSS compilado, com `default/colors.css` injetado): contraste do texto
   sobre `--table-row-hover-color` e sobre `--box-header-bg`, e da divisória.
5. Screenshots antes/depois (mesmo seed) de changelist, formulário com fieldsets, tela inicial e uma
   listagem densa, em Padrão, Alto Contraste, GovBR e Luna — mostrados ao usuário antes do MR.
6. `pre-commit run --from-ref origin/master --to-ref HEAD`.
