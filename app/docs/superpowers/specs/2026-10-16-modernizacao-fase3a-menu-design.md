# Modernização da interface — fase 3a: menu lateral e mobile

Data: 2026-10-16
Status: aprovada; implementada no branch `claude/modernizacao-fase2-componentes` (mesmo MR da fase 2, !19395)
Antecedentes: fase 1 (tokens, mergeada) e fase 2 (componentes, !19395).
Depois: fase 3b (cabeçalho da página, action-links, rodapé) e fase 4 (sobras).

## Por quê

O usuário acha o menu lateral "esquisito", sem uma queixa específica. Ele escolheu a direção por comparação visual
sobre telas reais em 16/10/2026: **A — escuro refinado**, com um ajuste dele (página atual marcada por fonte teal sobre
fundo sutil, sem barrinha lateral). O objetivo é o menu parecer atual sem perder a identidade da barra escura do SUAP.

## Objetivo, não objetivos, antiobjetivos

- **Objetivo:** modernizar o visual do menu lateral (`aside#menu-lateral` em `comum/templates/admin/base.html`), do menu
  retraído (`body.hideSidebar`) e da barra inferior do celular (`#mobilemenu`) por **tokens CSS** no tema default,
  como nas fases 1 e 2.
- **Não objetivos:** mudar a organização ou a ordem dos itens; mudar o `menu.yaml` dos módulos; mudar o comportamento de
  abrir/fechar (`comum/static/comum/js/main.js`); mudar a posição da barra do celular (continua flutuando embaixo);
  cabeçalho da página, action-links e rodapé (fase 3b).
- **Antiobjetivos** (falha mesmo se "funcionar"): barra clara ou teal no Padrão (o usuário escolheu manter escura);
  marca/barrinha teal na página atual (o usuário rejeitou); perder o autofocus da busca do menu na página inicial
  (pedido do usuário na fase 0); foco por teclado menos visível que hoje; mudar o menu dos temas que já têm o seu.

## O que o usuário decidiu

1. Direção **A — escuro refinado** (entre Hoje, A e B — claro).
2. Página atual: **texto teal + fundo sutil**, **sem** a barrinha lateral teal.
3. O A completo como mostrado (seção Design), aprovado com "ficou bom".

## Design (Padrão)

Valores de referência da comparação aprovada; a captura final está em
`.superpowers/brainstorm/258852-1792120546/content/menu-a3.png` (fora do git). Cor só por token, nada de hex nem
`rgba()` literal: os fundos translúcidos do mockup (branco a 6–8% sobre `--grey-900`) viram os cinzas vizinhos da escala.

| Parte | Hoje | Fase 3a |
|---|---|---|
| Fundo da barra (`--aside-bg-color`) | `--grey-850` | `--grey-900` |
| Busca do menu | sublinhado `--grey-600`, fundo transparente | campo preenchido `--grey-850`, borda 1px `--grey-600` (3:1 sobre a barra; `--grey-800` dava ≈1,5:1), raio 10px, altura ≈38px, lupa dentro (à esquerda) |
| Item de 1º nível | sem fundo, sem raio | raio 10px, padding ~.95rem 1.2rem, peso 500, texto `--grey-200` |
| Hover de item (1º e 2º nível) | só muda a cor do texto (`--primary-400`) | fundo `--grey-850` e texto `--white` |
| Categoria aberta (`li.opened > a`) | sem destaque | fundo `--grey-800`, texto `--white`, ícone `--primary-300` |
| Ícone de 1º nível | `--primary-750` | `--grey-400` (aberto: `--primary-300`) |
| Subitens (2º nível em diante) | traço `--grey-900` entre itens | sem traços; uma linha-guia vertical 1px `--grey-750` à esquerda do bloco aberto; item com raio 8px, texto `--grey-300`, peso 400 |
| Página atual (`a[aria-current="page"]`) | texto `--primary-400` (via `.active`) | fundo `--grey-800`, texto `--primary-400` (9,0:1 sobre `--grey-800`), peso 600, **sem** barrinha |
| Perfil e "Minha conta" no topo | fundo `--usertools-bg-color` | mesmo token, raio 10px |
| Menu retraído (60px) | ícones | ícones centralizados no item, mesmas cores e estados acima |
| Barra do celular (`#mobilemenu`) | fundo `--primary-900`, raio 25px | fundo `--grey-900`, raio 18px, ícones `--grey-200`; sino com notificação continua `--danger` |

- **3º nível em diante** (decisão minha): mesmo estilo de subitem (`--grey-300`, peso 400), no lugar do
  `--menu-3-level-color`/peso 300 de hoje; vale também para o 4º ao 6º nível (cor e peso; os tamanhos de fonte seguem como
  estão). A linha-guia é desenhada em cada bloco aberto, em cada profundidade.
- **Menu retraído** (decisão minha): só o 1º nível aparece, e o link da página atual fica escondido. O item de 1º nível que
  contém a página atual (`li.active > a`) ganha o fundo de categoria aberta e o ícone `--primary-300`, para o teal
  indicar onde se está.
- **Celular com o menu aberto:** é o mesmo `aside.nav` sobreposto à página, então recebe o mesmo visual da tabela; não há
  estilo à parte.
- **Homologação** (`body.debug`, barra `--debug-color` vermelha): os fundos cinzas do menu viram vermelhos escuros
  (hover e busca `--danger-850`, categoria aberta e página atual `--danger-900`, linha-guia `--danger-650`, borda da busca
  `--grey-500`), pelos tokens `--menu-debug-*` e `--aside-search-debug-*`; os temas que mantêm o menu seguem com os seus.
- A página atual já é marcada pelo `open_menu_item` (`main.js`: `li.active` + `aria-current="page"` no link); o estilo
  usa esse marcador, nenhum JS novo.
- O foco por teclado continua com a regra da fase 0 (`aside.nav :focus-visible { outline-color: currentColor }`);
  conferir que o outline aparece sobre os fundos novos.
- Busca: sem anel de foco (decisão da fase 2); no foco/preenchida, borda `--grey-500` ou mais clara e texto `--white`;
  placeholder ≥ 4,5:1 sobre o fundo novo do campo (hoje `--aside-search-placeholder-color: var(--grey-400)`; subir o tom
  se a medição pedir).
- **Faixa escura no celular:** com o menu fechado, em 390px, aparecia uma faixa escura fina na borda esquerda da página
  (já existia). A causa não era a grade: o `aside.nav` nasce com a largura cheia e o `hideSidebar` só entrava depois da
  carga (jQuery ready), então o menu encolhia com a transição à vista. Um `<script>` inline logo após o `<body>` em
  `comum/templates/admin/base.html` põe o `hideSidebar` abaixo de 940px antes da primeira pintura; a correção vale
  para todos os temas, porque é defeito, não identidade.

## Alcance por tema

Mesma regra das fases 1 e 2: tema com valor próprio mantém o seu. Cada parte nova sai por token no `:root` do default;
os temas abaixo recebem, no próprio `:root`, as linhas que apontam os tokens novos para o que já mostram.

| Tema | Recebe a fase 3a? | Motivo |
|---|---|---|
| Padrão | sim | — |
| Modo Daltonismo | sim, menos as cores próprias | recebe formas, fundos, busca e barra do celular; mantém o ícone (`%nav-first-level-icon` em `--primary-250`, também no menu retraído) e o hover (`--primary-350`) que recolorem por acessibilidade — por isso ícone e texto de hover saem por token que ele redefine. O texto da página atual usa `--primary-300` (5,1:1; herdar `--primary-400` dava 3,6:1) |
| Alto Contraste, Aurora, Dunas, GovBR, IFS, Luna | não (mantêm o menu) | têm barra, cores de menu ou regras de `#mainmenu` próprias; GovBR, IFS e Dunas têm barra clara, onde o teal `--primary-400` não teria contraste |
| Todos | correção da faixa escura no celular | defeito |

"Mantém" é portão rígido para **todas** as propriedades novas, não só cor: raio, padding, peso, fundos de hover e de
aberto, linha-guia, busca e `#mobilemenu` (hoje com `--primary-900` fixo no default, sem override no Alto Contraste).
Cada propriedade nova sai por token cujo valor, em cada tema preservado, é o que ele mostra hoje. Como os temas
redefinem subconjuntos diferentes dos `%nav-*`, as linhas de preservação variam por tema. A medição base × HEAD dos
estilos computados nos 8 temas é o que prova; onde o herdado vazar, o tema ganha a linha que falta.

## Restrições

- Mesmo branch e MR da fase 2 (`claude/modernizacao-fase2-componentes`, !19395), a pedido do usuário; usa tokens da
  fase 2, como `--aside-search-placeholder-color`.
- Fonte do tema em `djtools/static/djtools/themes/` (o `static/` da raiz é saída gitignored).
- Ordem de import: `default/colors.css` → `<tema>/colors.scss` → `default/variables` → `<tema>/variables` →
  `default/pre` → `<tema>/pre` → `default/post` → `default/forms` → `<tema>/post`.
- Tokens novos no `:root` do `default/pre.scss`, perto dos de menu (`--mainmenu-link-color`, `--menu-3-level-color`…).
- Contraste: texto ≥ 4,5:1; limite de componente ≥ 3:1.
- Template só se for inevitável (ex.: lupa dentro do campo exigir elemento); preferir CSS. Foi inevitável uma vez: o
  script inline do `hideSidebar` no `base.html` (faixa escura do celular).
- Commits `[djtools] Gerúndio`, pt-BR, sem linhas de atribuição; C901 ≤ 10 e tipos nas defs tocadas (se houver Python).

## Fica para quem constrói

- Nomes dos tokens novos e em que placeholders (`%nav-first-level-link`, `%aside-menu-search`…) eles entram. Além dos
  da tabela de partes, a implementação criou tokens de geometria do subitem e do retraído (`--menu-subitem-indent`,
  `--menu-subitem-padding-x`, `--menu-sublist-*`, `--menu-3-level-weight`, `--menu-collapsed-*`); estão no `:root` e
  no `@mixin menu-classico` de `default/pre.scss`.
- Ajuste fino de espaçamentos (os valores da tabela são do mockup, aproximados).
- A causa exata da faixa escura no celular.
- Escolha de telas reais para o e2e.

## Fora desta fase

- O sino de notificação da barra do celular (`--danger` sobre `--grey-900`, 2,77:1; já era 2,82:1 sobre o fundo
  anterior) segue abaixo de 3:1 até a fase 4 (contrastes antigos).

## Verificação

1. Os 8 temas compilam.
2. e2e novo (padrão de `tests/e2e/test_tema_componentes.py`, helper `_token`): fundo da barra; página atual com fundo e
   texto `--primary-400` e sem `box-shadow`; categoria aberta com fundo; subitem sem `border-bottom`; busca com raio e
   sem anel; barra do celular `--grey-900` em 390px; menu retraído com ícone centralizado; sem faixa escura no celular
   fechado.
3. Os testes existentes da busca do menu (fase 2) e do autofocus na página inicial seguem verdes.
4. Gate axe (`tests/e2e/test_acessibilidade.py`) verde, e rodada sob Alto Contraste e Luna sem violação nova.
   `test_tela_sem_violacao_seria[inicio]` falhou no banco e2e reaproveitado (também na base) por causa de dados acumulados;
   num banco novo (`--create-db`) passam os 4 testes. Não é problema do código.
5. e2e `tests/e2e` + `comum/tests/e2e` verdes.
6. Medição base × HEAD nos 8 temas: o que a tabela marca "mantém" ficou idêntico.
7. Contraste medido: texto dos itens, página atual, placeholder da busca, ícones.
8. Screenshots antes/depois (menu aberto, retraído, celular fechado e aberto) em Padrão, Alto Contraste, GovBR e Luna,
   mostrados ao usuário antes do MR.
9. `pre-commit run --from-ref origin/master --to-ref HEAD`.
