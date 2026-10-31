# Cobertura do vocabulário da camada `Tela` nos demais módulos

Levantamento para a issue #16973. **Só levantamento**: não decide se a `Tela`
(`djtools/e2e_ui.py`) cresce, nem quem pode editar `djtools/`. Isso é decisão de outro
ticket.

## Escopo e método

- Fonte primária: o código. Nada aqui vem de leitura secundária.
- **Steps comuns**: os 67 `@given`/`@when`/`@then` de `djtools/new_tests/common_steps/`
  (`given.py`, `when.py`, `then.py`).
- **Steps próprios**: os 112 `@given`/`@when`/`@then` definidos em `<app>/features/steps/*.py`
  — **todos**, de todos os 52 módulos, não uma amostra (o ticket pedia amostragem; enumerar
  saiu mais barato que amostrar).
- **Volume**: ocorrências reais nos 224 arquivos `.feature` do repo.
  - Para os steps comuns, a contagem **exclui `edu` e `almoxarifado`** (são os módulos já
    portados; contá-los mediria o que já existe).
  - Para os steps próprios, a contagem é **total** (cada step só é usado no seu próprio módulo).
- Contagem por regex sobre as linhas Gherkin. Conferido que o repo não usa a forma
  `Dado que ...` (0 ocorrências), então o casamento `palavra-chave + texto do step` é exato,
  não um piso.

Scripts de apuração são descartáveis (não commitados); os números abaixo saem de
`grep`/AST sobre `*/features/steps/*.py` e `*/features/**/*.feature`.

## 1. Cobertura dos steps comuns (67)

### 1.1 Cobertos pela `Tela` — 29 steps

Ocorrências fora de `edu`/`almoxarifado`.

| Step comum | Método da `Tela` | Usos | Coberto |
|---|---|---:|---|
| `@when clico no botão "{nome}"` (`when.py:258`) | `clicar_botao` (`e2e_ui.py:160`) | 1241 | sim |
| `@then vejo a página "{nome}"` (`then.py:33`) | `ver_titulo` (`e2e_ui.py:362`) | 937 | sim |
| `@then vejo mensagem de {tipo} "{msg}"` (`then.py:56`) | `sucesso` / `erro` (`e2e_ui.py:321`, `:348`) | 609 | sim, com ressalva (§1.4) |
| `@when preencho o formulário com os dados` (`when.py:381`) | `preencher_formulario` (`e2e_ui.py:252`) | 552 | sim, com lacuna de tipos (§3) |
| `@then vejo o botão "{nome}"` (`then.py:42`) | `ver_botao` (`e2e_ui.py:366`) | 574 | sim |
| `@given acesso a página "{url}"` (`given.py:31`) | `ir` (`e2e_ui.py:73`) | 403 | sim |
| `@when acesso a página "{url}"` (`when.py:626`) | `ir` | 403 | sim |
| `@when clico na aba "{nome}"` (`when.py:337`) | `clicar_aba` (`e2e_ui.py:173`) | 216 | sim |
| `@when olho a linha "{texto}"` (`when.py:103`) | `linha` (`e2e_ui.py:107`) | 189 | sim |
| `@when clico no ícone de {tipo}` (`when.py:321`) | `clicar_icone` (`e2e_ui.py:181`) | 187 | sim |
| `@when olho para o popup` (`when.py:114`) | `popup` (`e2e_ui.py:119`) | 119 | sim |
| `@when clico no link "{nome}"` (`when.py:293`) | `clicar_link` (`e2e_ui.py:167`) | 111 | sim |
| `@then vejo o texto "{texto}"` (`then.py:110`) | `ver_texto` (`e2e_ui.py:353`) | 43 | sim |
| `@then vejo o texto {texto}` (`then.py:361`) | `ver_texto` | 43 | sim |
| `@when olho para a aba "{nome}"` (`when.py:122`) | `aba` (`e2e_ui.py:113`) | 40 | sim |
| `@then vejo a linha "{texto}"` (`then.py:157`) | `linha` | 39 | sim |
| `@when olho para o quadro "{nome}"` (`when.py:48`) | `quadro` (`e2e_ui.py:94`) | 23 | sim |
| `@given a atual página` (`given.py:244`) | volta à `Tela` de fora do popup | 21 | sim |
| `@when olho para a página` (`when.py:41`) | a própria `tela` (escopo vazio) | 20 | sim |
| `@when seleciono o item "{obj}" da lista` (`when.py:664`) | `selecionar_item` (`e2e_ui.py:196`) | 15 | sim |
| `@when clico no botão de submit "{nome}"` (`when.py:286`) | `clicar_botao` (submit é a 1ª prioridade, `e2e_ui.py:136`) | 11 | sim |
| `@then vejo o quadro "{nome}"` (`then.py:127`) | `quadro` (já faz `expect(...).to_be_visible()`) | 10 | sim |
| `@when clico no botão de ação "{nome}"` (`when.py:279`) | `clicar_acao` (`e2e_ui.py:187`) | 4 | sim |
| `@when aguardo o conteúdo ajax carregar` (`when.py:644`) | `esperar` (`e2e_ui.py:77`) | 4 | sim |
| `@when preencho as linhas do quadro "{obj}" com os dados` (`when.py:352`) | `quadro` + `preencher_linha` (`e2e_ui.py:305`) | 2 | sim |
| `@when olho para os filtros` (`when.py:59`) | `filtros` (`e2e_ui.py:104`) | 2 | sim |
| `@when olho e clico no botão "{nome}"` (`when.py:272`) | `clicar_botao` | 1 | sim |
| `@given acesso a página ajax "{url}"` (`given.py:46`) | `ir` + `esperar` | 0 | sim |
| `@when o popup é fechado` (`when.py:143`) | volta à `Tela` de fora do popup | 0 | sim |

### 1.2 Fora do escopo por decisão do porte — 7 steps

`djtools/e2e_ui.py:21-23` declara o que **não** foi portado. Não são lacunas da `Tela`; são
escolha registrada. Ficam fora dos três baldes (ver §5, que trata `acesso o menu` à parte).

| Step comum | Situação | Usos |
|---|---|---:|
| `@when acesso o menu "{item}"` (`when.py:216`) | não portado; substituto é `tela.ir(url)` | 760 (50 módulos) |
| `@then vejo o item de menu "{item}"` (`then.py:149`) | asserção sobre o menu; sem substituto | 11 (6 módulos) |
| `@when gero um screenshot - "{marcador}"` (`when.py:654`) | documentação (`@do_document`) | 0 |
| `@given/@when/@then abro o debugger` (`given.py:254`, `when.py:688`, `then.py:342`) | ferramenta de dev (3 steps) | 0 |
| `@when gero um erro` (`when.py:659`) | autoteste do runner | 0 |

### 1.3 Sem equivalente — 31 steps

Classificação nos baldes em §4. Aqui a lista crua, com o volume:

| Step comum | Balde | Usos | Módulos |
|---|---|---:|---:|
| `@when realizo o login com o usuário "{u}" e senha "{s}"` (`when.py:172`) | c | 343 | 50 |
| `@then vejo os seguintes campos no formulário` (`then.py:90`) | a | 231 | 29 |
| `@when a data do sistema for "{data}"` (`when.py:152`) | b | 125 | 27 |
| `@when olho para a listagem` (`when.py:70`) | a | 88 | 13 |
| `@given os seguintes usuários` (`given.py:63`) | c | 55 | 43 |
| `@when olho para a tabela` (`when.py:81`) | a | 51 | 9 |
| `@then vejo mais de {n} resultados na tabela` (`then.py:354`) | a | 32 | 1 |
| `@then vejo os seguintes erros no formulário` (`then.py:101`) | a (parcial: `erros_na_tela` devolve lista plana, asserir campo↔mensagem exige o seletor do par) | 26 | 7 |
| `@then vejo a aba "{nome}"` (existência) (`then.py:119`) | a | 23 | 6 |
| `@then vejo o status "{status}"` (barra `.steps`) (`then.py:347`) | a | 23 | 2 |
| `@then ...obrigatoriedades atendidas e preencho com` (`then.py:192`) | b | 8 | 3 |
| `@when clico no checkbox` (`when.py:671`) | a | 5 | 1 |
| `@when clico no link "{x}" na listagem das áreas` (`when.py:678`) | a | 4 | 2 |
| `@when seleciono o custom checkbox "{nome}"` (`when.py:693`) | a | 4 | 2 |
| `@when preencho o formulário inline "{nome}" com os dados` (`when.py:536`) | b | 3 | 2 |
| `@when fecho o popup` (`when.py:134`) | a | 2 | 1 |
| `@then vejo a caixa de informações "{box}" com "{info}"` (`then.py:134`) | a | 2 | 1 |
| `@when olho para a tabela "{id}"` (`when.py:92`) | a | 1 | 1 |
| `@when clico no indicador "{nome}"` (`when.py:314`) | a | 1 | 1 |
| `@when atualizo a página` (`when.py:649`) | a | 1 | 1 |
| `@then vejo o indicador "{nome}"` (`then.py:23`) | a | 1 | 1 |
| `@then vejo o indicador "{nome}" com o valor "{v}"` (`then.py:11`) | a | 1 | 1 |
| `@when baixo um arquivo clicando no botão "{nome}"` (`when.py:265`) | a | 0 | 0 |
| `@when clico no link h4 "{nome}"` (`when.py:300`) | a | 0 | 0 |
| `@when clico no quadro "{nome}"` (`when.py:307`) | a | 0 | 0 |
| `@when removo o item "{i}" no autocomplete "{a}"` (`when.py:345`) | a | 0 | 0 |
| `@when retorna a data do sistema` (`when.py:164`) | b | 0 | 0 |
| `@then vejo o botão de ação "{nome}"` (`then.py:49`) | a | 0 | 0 |
| `@then nao vejo mensagem de {tipo} "{msg}"` (`then.py:73`) | a | 0 | 0 |
| `@then vejo o item "{i}" no autocomplete "{a}"` (`then.py:142`) | a | 0 | 0 |
| `@then ...obrigatoriedades atendidas` (`then.py:164`) | b | 0 | 0 |

**11 dos 31 têm 0 uso fora de `edu`/`almoxarifado`** — são vocabulário morto do behave. Sem a
coluna de uso, a lacuna aparente inflaria em ≈35%.

### 1.4 Ressalva semântica: mensagem de alerta

`Tela.sucesso` (`e2e_ui.py:321-336`) casa o banner "que **não** é erro" —
`p#feedback_message:not(.alert-error):not(.alert-danger)`. As 21 ocorrências de
`vejo mensagem de alerta` nas features casariam como sucesso. Distinguir alerta de sucesso é
um seletor a mais (balde a); hoje é uma conflação, não uma falha.

## 2. Steps próprios dos módulos (112)

**101 são `@given` e 11 são `@when`/`@then`.** Essa é a descoberta central: o vocabulário
próprio dos módulos é quase inteiramente **seed de dados**, não interação de tela.

Verificado por grep (`execute_steps|context.page|context.browser|context.xpath|force_fill|click(`)
em todos os `given.py`: **um único `@given` toca UI** —
`comum/features/steps/given.py:18` (`acesso o link enviado por email`), que lê o token de
`TrocarSenha` no ORM e delega a navegação a `Dado acesso a página "{url}"` (já coberto por
`Tela.ir`). Os demais `execute_steps` encontrados só encadeiam outro seed
(`Dado os seguintes usuários`) ou o congelamento de data
(`Quando a data do sistema for`, ver §4-b) — em `almoxarifado:23`, `eleicao:8`, `enquete:6`,
`documento_eletronico:15`, `plan_v2:143`, `saude:29`, `catalogo_provedor_servico:47`,
`erros:13`.

### 2.1 Os 11 `@when`/`@then` próprios

| Step próprio | Módulo | Balde | Usos |
|---|---|---|---:|
| `@when clico no label "{valor}" da etapa "{n}"` (`catalogo_provedor_servico/features/steps/when.py:6`) | catalogo_provedor_servico | b | 7 |
| `@when olho para o objetivo estratégico do planejamento "{nome}"` (`plan_v2/features/steps/when.py:4`) | plan_v2 | a | 3 |
| `@when seto o status da linha de avaliação para "{status}"` (`catalogo_provedor_servico/features/steps/when.py:11`) | catalogo_provedor_servico | a | 1 |
| `@when olho para a textarea "{nome}" e preencho com "{texto}"` (`erros/features/steps/when.py:6`) | erros | a | 1 |
| `@then vejo mensagem na timeline "{msg}"` (`erros/features/steps/then.py:6`) | erros | a | 1 |
| `@then vejo os seguintes campos no formulário preenchidos com` (`eleicao/features/steps/then.py:4`) | eleicao | a | 1 |
| `@then vejo o status "{msg}" acima do título` (`erros/features/steps/then.py:16`) | erros | a | 0 |
| `@then vejo o status do estágio "{status}"` (`estagios/features/steps/then.py:4`) | estagios | a (duplicata de `then.py:347`) | 0 |
| `@when digito "{texto}" no editor de texo` (`demandas/features/steps/when.py:6`) | demandas | b | 0 |
| `@when forço o status da demanda "{t}" para "{s}"` (`demandas/features/steps/when.py:35`) | demandas | c (ORM puro) | 1 |
| `@when altero a senha do aluno "{mat}" para "{senha}"` (`edu/features/steps/when.py:6`) | edu | c (ORM puro) | 1 |

Os dois de balde (b): `catalogo_provedor_servico` roda JS na página
(`context.page.evaluate("checkAllRadios(...)")`) sobre uma tabela de avaliação dinâmica;
`demandas` dirige o editor de texto rico dentro de um `iframe` (e ainda usa a API antiga
`browser.driver.switch_to.frame`, herdada do Selenium).

### 2.2 Os 101 `@given` (seed)

A lista completa, com `arquivo:linha` e volume, está no **Apêndice A** (é homogênea demais para
o corpo do texto). Distribuição por módulo:

`edu` 24, `saude` 18, `plan_v2` 7, `almoxarifado` 5, `pesquisa` 4, `processo_eletronico` 3,
`eleicao` 2, `ae` 2, `comum` 2, `catalogo_provedor_servico` 2, `temp_rh2` 2, `demandas` 1,
`erros` 1, `documento_eletronico` 1, e mais 33 módulos com exatamente 1 (`arquivo`,
`convenios`, `estagios`, `projetos`, `projetos_ensino`, `frota`, `contratos`, `rh`, `rsc`,
`ponto`, `orcamento`, `materiais`, `sica`, `eventos`, `chaves`, `pedagogia`, `progressoes`,
`encceja`, `cnpq`, `enquete`, `estacionamento`, `professor_titular`, `processo_seletivo`,
`auxilioemergencial`, `avaliacao_cursos`, `avaliacao_integrada`, `demandas_externas`,
`acompanhamentofuncional`).

Todos são `Model.objects.get_or_create(...)` / factories — o nome já entrega
(`os dados básicos para X`, `os usuários de X`, `os cadastros iniciais de X`). Isso é
**balde (c)**: vira fixture de seed no `conftest.py` do e2e, exatamente como já foi feito em
`edu/tests/e2e/conftest.py` e `almoxarifado/tests/e2e/conftest.py`. Não é problema da `Tela`.

## 3. Lacuna interna do `preencher_formulario`

`Tela._PREENCHEDORES` cobre 13 tipos: texto, senha, número, textarea, lista, checkbox, radio,
checkbox multiplo, data, **hora**, arquivo, autocomplete, autocomplete multiplo. (`hora` entrou
com a suíte do `eventos`, MR !18635.)

**Recontagem de 31/07/2026 (#16983).** A tabela abaixo substitui a anterior, que superestimava
`filteredselectmultiple` (dizia 51) e `texto rico` (dizia 38). A contagem tem de ser
**insensível a caixa**: as `.feature` escrevem `FilteredSelectMultiple`, `Texto Rico`,
`TextArea` — um grep pelo nome minúsculo do preenchedor devolve quase zero e engana.

**Atualização de 31/07/2026 (!MR desta branch):** `texto rico` e `filteredselectmultiple` **passaram a ser cobertos** — a decisão de #16983 era justamente essa. Restam três lacunas, somando 8 usos. A tabela abaixo fica como registro do que foi medido e do que sobrou.

Tipos que estavam fora quando este levantamento foi feito:

| Tipo | Usos | Módulos | Balde | Nota |
|---|---:|---:|---|---|
| ~~`texto rico`~~ (coberto) | 37 | 8 | b | `iframe` do editor (`when.py:526-530`). `pesquisa`, `projetos`, `projetos_ensino`, `saude`, `demandas`, `centralservicos`, `demandas_externas`, `documento_eletronico` |
| ~~`filteredselectmultiple`~~ (coberto) | 29 | 14 | b | select duplo do admin + botão "Adicionar" (`when.py:490-499`). `ae`, `saude`, `pesquisa`, `frota`, `contratos`, `eleicao`, `etep`, `materiais` e mais 6 |
| `arquivo real` | 5 | 4 | a | usa caminho real em vez do arquivo sintético. `cnpq`, `contratos`, `processo_eletronico`, `eventos` |
| `checkbox popup` | 2 | 2 | b | popup de múltipla escolha + "Confirmar" (`when.py:450-460`). `pesquisa`, `processo_eletronico` |
| `captcha` | 1 | 1 | — | `eventos/features/005.EVENTOS.inscrever_evento_publico.feature:17`; **nenhum dos dois mundos trata**: não há ramo para `captcha` em `when.py:437-533`, o step simplesmente não faz nada. Não é seed nem lacuna da `Tela` |

**São 5 tipos e 74 usos no total — e 30 dos 52 módulos não têm lacuna de campo nenhuma.**
Os limpos: `acompanhamentofuncional`, `almoxarifado`, `arquivo`, `avaliacao_cursos`,
`catalogo_provedor_servico`, `chaves`, `clipping`, `comum`, `convenios`, `edu`, `egressos`,
`encceja`, `enquete`, `erros`, `estacionamento`, `estagios`, `gestao`, `orcamento`,
`pedagogia`, `plan_v2`, `ponto`, `portaria`, `processo_seletivo`, `professor_titular`,
`progressoes`, `rh`, `rsc`, `sica`, `solenidades`, `temp_rh2`.

Consequência: **`catalogo_provedor_servico` não é inviável por campo** — o obstáculo dele é o
`clico no label da etapa` (JS via `page.evaluate`), balde (b). E os demais módulos citados como
inviáveis (`pesquisa`, `projetos`, `projetos_ensino`, `saude`, `ae`) são tocados por poucos
usos cada, não por muros.

**Armadilha: a coluna `Tipo` é capitalizada nas features.** As chaves de `_PREENCHEDORES` são
minúsculas, mas as `.feature` escrevem `Texto` (595 usos), `Lista` (277), `Autocomplete` (261),
`Data` (242), `TextArea` (154) e `Numero` sem acento. Um gerador que copie a coluna literalmente
quebra em todas elas — hoje ninguém tropeça porque quem portou escreveu minúsculo à mão.
#16983 decidiu normalizar a caixa dentro de `Tela.preencher`.

Observação menor: `Tela._preencher_data` (`e2e_ui.py:275-278`) só converte `dd/mm/aaaa`; o
behave também trata `datetime-local` (`when.py:467-472`). Medido: **0** ocorrências de valor
com hora em coluna `data` fora dos módulos portados — não bloqueia ninguém hoje.

## 4. Volume por balde

Somando steps comuns sem equivalente (31) + steps próprios (112):

| Balde | Steps | Ocorrências | O que é |
|---|---:|---:|---|
| **(a)** só um seletor/método a mais | **31** | 503 | 24 comuns (496) + 7 próprios (7) |
| **(b)** interação genuinamente nova | **7** | 143 | 5 comuns (136) + 2 próprios (7) — mais 3 tipos de campo, §3 |
| **(c)** domínio/seed, não é UI | **105** | 561 | 2 comuns (398) + 103 próprios (163) |

Fora dos baldes: **29** steps comuns já cobertos e **7** deixados de fora por decisão do porte
(§1.2).

Detalhe do balde (b) — as 7 interações novas:

1. `a data do sistema for` / `retorna a data do sistema` (`when.py:152`, `:164`) — 125 usos,
   27 módulos. Congelamento de tempo, infra de teste, não UI. É o item de (b) com maior
   alcance, e os e2e do `edu` já esbarraram em atrito de congelamento de tempo.
2. `preencho o formulário inline "{nome}"` (`when.py:536`) — inline do Django admin, tabular e
   stacked, com select2 dentro. 3 usos, 2 módulos.
3. `...obrigatoriedades atendidas` e `...obrigatoriedades atendidas e preencho com`
   (`then.py:164`, `:192`) — macro-steps que clicam Salvar, conferem "Este campo é
   obrigatório" campo a campo e depois preenchem. 8 usos, 3 módulos.
4. `clico no label da etapa` (`catalogo_provedor_servico/.../when.py:6`) — `page.evaluate` de
   função JS da própria tela sobre tabela dinâmica. 7 usos.
5. `digito no editor de texo` (`demandas/.../when.py:6`) — editor rico em `iframe`. 0 usos.

Mais os três tipos de campo de §3: `filteredselectmultiple`, `texto rico`, `checkbox popup`.

### Wizard/assistente: o risco conhecido do `edu` não se repete

A premissa do ticket (o assistente "Gerar Turmas" do `edu` é a raiz de 10 e2e vermelhos) **não
se generaliza**. Medição: `assistente|wizard` aparece em features de apenas **2 módulos** —
`ae` (2 arquivos) e `auxilioemergencial` (1). As 30+ linhas com "etapa" que o grep pega são
vocabulário de domínio (etapa de demanda, etapa de avaliação do catálogo), não navegação de
wizard. O artefato de wizard mais próximo é a barra de progresso `.steps`
(`then.py:347`, 23 usos em `demandas` e `erros`, mais a duplicata em `estagios`) — e ela é um
seletor único, balde (a). Não há evidência de wizard como categoria de risco fora do `edu`.

## 5. `acesso o menu` — o item isolado, e o maior número do levantamento

760 ocorrências em 50 módulos. Não é lacuna da `Tela`: `e2e_ui.py:21-23` diz que o menu por
título não foi portado de propósito, porque depende do menu renderizado e os testes de pytest
vão direto na URL. O substituto (`tela.ir(url)`) já existe e já é o step mais usado depois de
`clicar_botao`.

O custo, porém, não some — ele **muda de lugar**: sai da `Tela` e vira trabalho por cenário.
Cada `Quando acesso o menu "Ensino::Cadastros Gerais::Núcleos"` portado exige descobrir a URL
correspondente. Multiplicado por 760 linhas em 50 módulos, é o maior item de esforço do
levantamento — maior que os baldes (a) e (b) somados —, e é linear no número de cenários
portados, não no número de métodos da `Tela`.

Junto vem `vejo o item de menu` (11 usos, 6 módulos): asserção **sobre o menu em si**, que não
tem substituto por URL. Cenários que testam visibilidade de item de menu por perfil precisam do
menu renderizado.

## 6. Leitura

**A `Tela` cobre o grosso do vocabulário de UI, sim.** Os 5 steps comuns mais usados fora dos
módulos já portados — `clico no botão` (1241), `vejo a página` (937), `vejo mensagem de {tipo}`
(609), `vejo o botão` (574), `preencho o formulário com os dados` (552) — estão todos cobertos,
e sozinhos somam 3913 das 7621 ocorrências de steps comuns fora dos módulos já portados (51%).
Dos 67 steps comuns, 29 têm equivalente
direto, 7 estão fora por decisão registrada, e dos 31 restantes **24 são balde (a)** — um
seletor. Dos 112 steps próprios dos módulos, **103 (92%) são balde (c)**: seed de dados que já
tem caminho conhecido (fixture no `conftest.py` do e2e, como em `edu/tests/e2e/conftest.py` e
`almoxarifado/tests/e2e/conftest.py`). O vocabulário de **interação** genuinamente novo é 7
steps mais 3 tipos de campo. Em números: o que falta de vocabulário de tela são 31 seletores
(balde a) e 7 interações (balde b).

**O que trava não é o tamanho da `Tela`.** São três itens de infra, nesta ordem:

1. **`acesso o menu` (760 usos, 50 módulos)** — não é lacuna da `Tela`, mas impõe um mapa
   menu→URL por cenário portado. Atinge todos os 50 módulos igualmente; é o item de maior
   esforço agregado e o que define o ritmo de porte.
2. **`a data do sistema for` (125 usos, 27 módulos)** — mais da metade dos módulos com feature
   depende de congelar o relógio. Sem isso resolvido, esses cenários não têm como ser portados
   fielmente.
3. **`realizo o login` (343 usos) + `os seguintes usuários` (55 usos, 43 módulos)** — balde (c),
   mas pré-requisito universal: nenhum módulo roda sem seed de usuário e sessão autenticada. Os
   e2e de `edu` e `almoxarifado` já resolveram isso; a nota de memória do projeto registra que
   o cache de permissão por processo exige criar os grupos no seed de sessão.

**Módulos inviáveis sem trabalho de infra antes** (além dos três itens universais acima):

- **`pesquisa`** (16 features, prioridade do ticket): `texto rico` 12, `filteredselectmultiple` 8,
  `hora` 4, `checkbox popup` 1. É o módulo que mais acumula tipos de campo não cobertos.
- **`projetos`** (10 features) e **`projetos_ensino`** (10 features), ambos prioridade do
  ticket: `texto rico` 8 cada. Os fluxos de projeto giram em torno do editor rico.
- **`saude`** (4 features, mas 18 steps próprios de seed): `filteredselectmultiple` 6,
  `texto rico` 5, `hora` 3 — e o maior volume de seed próprio depois do `edu`.
- **`ae`**: `filteredselectmultiple` 13, o pior caso isolado do repo.
- **`catalogo_provedor_servico`**: depende de `page.evaluate` de JS da própria tela sobre a
  tabela de avaliação (`when.py:6`) — é o único módulo cujo step próprio de UI não é
  transcritível como seletor.
- **`estagios`** (9 features, prioridade do ticket) **não** está nessa lista: seu único step
  próprio (`then.py:4`) é duplicata de `then.py:347` e é balde (a); não usa nenhum tipo de
  campo fora dos 12 cobertos. É dos maiores candidatos "limpos".

O balde (a), com 31 steps, é o mais numeroso dos que faltam mas o de menor peso: se coberto,
cada um custa aproximadamente um seletor. E 11 desses 31 têm 0 uso fora dos módulos já
portados — o custo real do balde (a) é menor que a contagem sugere.

## Apêndice A — os 101 `@given` de seed (balde c)

101 steps, 161 ocorrências nas features. Todos são `get_or_create`/factories, exceto
`comum/features/steps/given.py:18`, que lê o token no ORM e delega a navegação a
`Dado acesso a página "{url}"` (coberto por `Tela.ir`).

| Módulo | Step | `arquivo:linha` | Usos |
|---|---|---|---:|
| `acompanhamentofuncional` | `os dados basicos cadastrados` | `acompanhamentofuncional/features/steps/given.py:6` | 1 |
| `ae` | `os cadastros de tipos de demandas do aluno` | `ae/features/steps/given.py:29` | 1 |
| `ae` | `os dados basicos cadastrados do ae` | `ae/features/steps/given.py:41` | 1 |
| `almoxarifado` | `os usuarios do Almoxarifado` | `almoxarifado/features/steps/given.py:20` | 5 |
| `almoxarifado` | `o cadastro de processo` | `almoxarifado/features/steps/given.py:47` | 1 |
| `almoxarifado` | `o cadastro de entrada de compra` | `almoxarifado/features/steps/given.py:53` | 1 |
| `almoxarifado` | `o cadastro de entrada de doacao` | `almoxarifado/features/steps/given.py:67` | 1 |
| `almoxarifado` | `o cadastro de requisicao` | `almoxarifado/features/steps/given.py:81` | 1 |
| `arquivo` | `os dados básicos para arquivos` | `arquivo/features/steps/given.py:13` | 1 |
| `auxilioemergencial` | `os dados básicos do auxílio emergencial` | `auxilioemergencial/features/steps/given.py:6` | 1 |
| `avaliacao_cursos` | `os dados basicos cadastrados da avaliacao de cursos` | `avaliacao_cursos/features/steps/given.py:6` | 1 |
| `avaliacao_integrada` | `os dados básicos para avaliacao integrada` | `avaliacao_integrada/features/steps/given.py:7` | 1 |
| `catalogo_provedor_servico` | `os cadastros básicos do catálogo digital` | `catalogo_provedor_servico/features/steps/given.py:434` | 1 |
| `catalogo_provedor_servico` | `informações corrigidas da Matrícula EAD` | `catalogo_provedor_servico/features/steps/given.py:445` | 1 |
| `chaves` | `Salas e Servidores já existentes` | `chaves/features/steps/given.py:7` | 1 |
| `cnpq` | `os cadastros básicos do cnpq` | `cnpq/features/steps/given.py:7` | 1 |
| `comum` | `os dados básicos para o app comum` | `comum/features/steps/given.py:10` | 1 |
| `comum` | `acesso o link enviado por email` | `comum/features/steps/given.py:18` | 1 |
| `contratos` | `os cadastros básicos do módulo contratos` | `contratos/features/steps/given.py:21` | 1 |
| `convenios` | `os dados básicos para convênios` | `convenios/features/steps/given.py:9` | 1 |
| `demandas` | `os cadastros básicos do módulo de demandas` | `demandas/features/steps/given.py:4` | 1 |
| `demandas_externas` | `os dados básicos para a demanda externa` | `demandas_externas/features/steps/given.py:8` | 1 |
| `documento_eletronico` | `os cadastros básicos do documento eletrônico` | `documento_eletronico/features/steps/given.py:27` | 2 |
| `edu` | `as configurações da Avaliação por Conceito` | `edu/features/steps/given.py:1009` | 2 |
| `edu` | `o cadastro do diário com avaliação por conceito` | `edu/features/steps/given.py:1014` | 1 |
| `edu` | `o cadastro de área de curso de formação superior` | `edu/features/steps/given.py:1091` | 1 |
| `edu` | `os cadastros da funcionalidade 001` | `edu/features/steps/given.py:127` | 10 |
| `edu` | `os cadastros da funcionalidade 002` | `edu/features/steps/given.py:163` | 8 |
| `edu` | `os cadastros da funcionalidade 003` | `edu/features/steps/given.py:354` | 7 |
| `edu` | `os cadastros de Pais e Estado` | `edu/features/steps/given.py:40` | 2 |
| `edu` | `os cadastros da funcionalidade 004` | `edu/features/steps/given.py:428` | 6 |
| `edu` | `os cadastros da funcionalidade 005` | `edu/features/steps/given.py:485` | 4 |
| `edu` | `os cadastros da funcionalidade 006` | `edu/features/steps/given.py:525` | 3 |
| `edu` | `os cadastros da funcionalidade 008` | `edu/features/steps/given.py:560` | 2 |
| `edu` | `a matrícula do aluno regime de crédito` | `edu/features/steps/given.py:622` | 1 |
| `edu` | `os cadastros iniciais de banco` | `edu/features/steps/given.py:648` | 1 |
| `edu` | `os cadastros iniciais de tipo de componente` | `edu/features/steps/given.py:655` | 1 |
| `edu` | `os cadastros iniciais de componente` | `edu/features/steps/given.py:663` | 1 |
| `edu` | `os cadastros iniciais de componente curricular` | `edu/features/steps/given.py:757` | 2 |
| `edu` | `os cadastros iniciais de turno` | `edu/features/steps/given.py:829` | 0 |
| `edu` | `os cadastros iniciais de calendário acadêmico` | `edu/features/steps/given.py:837` | 1 |
| `edu` | `os cadastros iniciais de prédio` | `edu/features/steps/given.py:888` | 1 |
| `edu` | `os cadastros iniciais de sala` | `edu/features/steps/given.py:897` | 1 |
| `edu` | `as configurações iniciais de diário` | `edu/features/steps/given.py:905` | 1 |
| `edu` | `os horários de aula "{horarios}" do diário "{diario}"` | `edu/features/steps/given.py:929` | 1 |
| `edu` | `os cadastros iniciais de raça` | `edu/features/steps/given.py:940` | 1 |
| `eleicao` | `um Público cadastrado` | `eleicao/features/steps/given.py:22` | 1 |
| `eleicao` | `os usuarios das Eleições` | `eleicao/features/steps/given.py:6` | 0 |
| `encceja` | `os dados básicos para encceja` | `encceja/features/steps/given.py:7` | 1 |
| `enquete` | `os usuarios de Enquete` | `enquete/features/steps/given.py:4` | 2 |
| `erros` | `os cadastros de usuários do módulo de erros` | `erros/features/steps/given.py:16` | 1 |
| `estacionamento` | `os dados básicos do estacionamento` | `estacionamento/features/steps/given.py:6` | 1 |
| `estagios` | `os dados básicos para os estágios` | `estagios/features/steps/given.py:32` | 1 |
| `eventos` | `os dados básicos para eventos` | `eventos/features/steps/given.py:16` | 1 |
| `frota` | `os dados básicos para frota` | `frota/features/steps/given.py:32` | 1 |
| `materiais` | `os dados básicos para materiais` | `materiais/features/steps/given.py:19` | 1 |
| `orcamento` | `os dados básicos para orçamento` | `orcamento/features/steps/given.py:29` | 1 |
| `pedagogia` | `os dados basicos cadastrados da pedagogia` | `pedagogia/features/steps/given.py:7` | 2 |
| `pesquisa` | `os dados básicos para a editora` | `pesquisa/features/steps/given.py:180` | 1 |
| `pesquisa` | `os ajustes para o laboratório` | `pesquisa/features/steps/given.py:191` | 1 |
| `pesquisa` | `os dados básicos para a pesquisa` | `pesquisa/features/steps/given.py:32` | 1 |
| `pesquisa` | `os usuários da pesquisa` | `pesquisa/features/steps/given.py:94` | 1 |
| `plan_v2` | `os usuários do planejamento` | `plan_v2/features/steps/given.py:141` | 5 |
| `plan_v2` | `um PDI cadastrado` | `plan_v2/features/steps/given.py:158` | 5 |
| `plan_v2` | `as unidades administrativas` | `plan_v2/features/steps/given.py:163` | 4 |
| `plan_v2` | `os macroprocessos` | `plan_v2/features/steps/given.py:182` | 3 |
| `plan_v2` | `os objetivos estratégicos` | `plan_v2/features/steps/given.py:190` | 2 |
| `plan_v2` | `as ações no PDI` | `plan_v2/features/steps/given.py:214` | 1 |
| `plan_v2` | `os dados básicos para o planejamento` | `plan_v2/features/steps/given.py:31` | 6 |
| `ponto` | `dados do ponto` | `ponto/features/steps/given.py:9` | 0 |
| `processo_eletronico` | `os dados básicos para o processo eletronico` | `processo_eletronico/features/steps/given.py:20` | 0 |
| `processo_eletronico` | `os usuários do processo eletronico` | `processo_eletronico/features/steps/given.py:44` | 1 |
| `processo_eletronico` | `os cadastros de documentos eletronicos` | `processo_eletronico/features/steps/given.py:66` | 1 |
| `processo_seletivo` | `os dados básicos do processo seletivo` | `processo_seletivo/features/steps/given.py:6` | 1 |
| `professor_titular` | `os dados básicos para professor titular` | `professor_titular/features/steps/given.py:6` | 1 |
| `progressoes` | `os cadastros básicos de progressões` | `progressoes/features/steps/given.py:14` | 1 |
| `projetos` | `os dados básicos para a extensão` | `projetos/features/steps/given.py:20` | 1 |
| `projetos_ensino` | `os dados básicos para projetos de ensino` | `projetos_ensino/features/steps/given.py:14` | 1 |
| `rh` | `os dados basicos cadastrados do rh` | `rh/features/steps/given.py:6` | 1 |
| `rsc` | `os dados básicos para RSC` | `rsc/features/steps/given.py:6` | 1 |
| `saude` | `as seguintes receitas nutricionais` | `saude/features/steps/given.py:101` | 1 |
| `saude` | `as seguintes avaliações gastrointestinais` | `saude/features/steps/given.py:110` | 1 |
| `saude` | `as seguintes restrições alimentares` | `saude/features/steps/given.py:119` | 1 |
| `saude` | `os seguintes motivos do atendimento nutricional` | `saude/features/steps/given.py:128` | 1 |
| `saude` | `os seguintes diagnósticos nutricionais` | `saude/features/steps/given.py:137` | 1 |
| `saude` | `os seguintes procedimentos odontológicos` | `saude/features/steps/given.py:146` | 1 |
| `saude` | `os seguintes motivos de chegada psicológo` | `saude/features/steps/given.py:155` | 1 |
| `saude` | `as seguintes queixas psicológicas` | `saude/features/steps/given.py:164` | 1 |
| `saude` | `os seguintes procedimentos de enfermagem` | `saude/features/steps/given.py:173` | 1 |
| `saude` | `os usuarios do SAUDE` | `saude/features/steps/given.py:27` | 3 |
| `saude` | `os seguintes campi` | `saude/features/steps/given.py:47` | 1 |
| `saude` | `os seguintes tipos de atividades em grupo` | `saude/features/steps/given.py:55` | 1 |
| `saude` | `os seguintes anos de referencia` | `saude/features/steps/given.py:60` | 1 |
| `saude` | `os seguintes objetivos` | `saude/features/steps/given.py:65` | 1 |
| `saude` | `as seguintes perguntas` | `saude/features/steps/given.py:70` | 0 |
| `saude` | `as seguintes categorias de exames` | `saude/features/steps/given.py:75` | 1 |
| `saude` | `os seguintes pacientes bloqueados` | `saude/features/steps/given.py:80` | 1 |
| `saude` | `as seguintes orientacoes nutricionais` | `saude/features/steps/given.py:92` | 2 |
| `sica` | `os dados básicos do sica` | `sica/features/steps/given.py:11` | 1 |
| `temp_rh2` | `os dados de sexo do servidor está populado` | `temp_rh2/features/steps/given.py:14` | 1 |
| `temp_rh2` | `os dados básicos para competição desportiva` | `temp_rh2/features/steps/given.py:9` | 1 |
