# Inventário de custo de seed e2e por módulo

Levantamento **medido** (não estimado no olho) de quanto custa semear cada módulo do SUAP que
tem diretório `features/` para escrever testes e2e no padrão de `tests/e2e/` +
`djtools/e2e_ui.py` / `djtools/e2e_fixtures.py`.

Este documento **mede**; ele não decide a ordem de execução (isso é o ticket #16976).

- Fonte: o próprio repositório, na revisão `3fbaa69310` (branch `master`).
- Escopo: os **52** diretórios `*/features` existentes. `almoxarifado` e `edu` já foram feitos
  (`almoxarifado/tests/e2e/`, `edu/tests/e2e/`) e aparecem marcados **FEITO** como linha de
  referência/calibração.
- Coleta: script Python descartável (`ast` para o Python, máquina de estados linha a linha para
  o Gherkin, `yaml.safe_load` para o `permissions.yaml`). O script não foi commitado, só o resultado.

## Como cada coluna foi medida

- **`.feature`** — arquivos com extensão `.feature` sob `<app>/features/`, recursivo. Somam **224**.
  O repo tem 230 no total; os 6 restantes estão em `remanejamento/old_features/` e
  `compras/old_features/` (17 cenários), fora do escopo — nenhum desses dois apps tem diretório
  `features/`, então não entram nos 52. É essa a diferença entre o `grep -c` cru por
  `Cenário:`/`Cenario:` (995) e os 978 cenários simples contados aqui.
  Correção de premissa: **nenhum app usa a extensão `.features`**. `.features` no SUAP é nome de
  *diretório* — só em `almoxarifado`, que tem `01.Autorizacao.features/`, `02.Validacao.features/` e
  `03.FluxoPrincipal.features/` como subpastas contendo `.feature` de verdade. Por isso `almoxarifado`
  aparece com 42 arquivos.
- **Cenários** — fórmula literal do ticket, aditiva:
  `Cenário:`/`Cenario:`/`Scenario:` **+** `Esquema do Cenário:`/`Scenario Outline:` **+** linhas de
  dados de `Exemplos:`/`Examples:`. A **primeira** linha `|...|` depois de `Exemplos:` é o cabeçalho da
  tabela e foi excluída. Linhas comentadas (`#`) são ignoradas — é o que faz `almoxarifado` contar 0
  outlines, pois os dele estão comentados. Nota: a fórmula superconta um pouco cada outline
  (1 outline + 3 linhas = 4, contra 3 execuções reais). No repo inteiro isso vale só
  **15 outlines / 30 linhas de exemplo**, concentrados em `plan_v2`, `pesquisa` e `demandas_externas`;
  os outros ≈978 cenários são simples.
- **`test_initial_data.py`** — existe `<app>/features/test_initial_data.py`. Confirmado: só **3**
  (`almoxarifado`, `enquete`, `progressoes`).
- **`given.py` LOC / defs topo / replay ORM / encadeia UI** — `ast.parse` de
  `<app>/features/steps/given.py`, iterando só `tree.body` (defs de topo, sem helpers aninhados).
  Classificação de cada def pelo seu próprio código-fonte:
  - **encadeia UI** = chama `context.execute_steps` → não é chamável fora do behave;
  - **replay ORM** = não chama `execute_steps` e toca `.objects.` / `.get_or_create(` / `.create(` →
    é reaproveitável como fixture pytest (o padrão que `almoxarifado` e `edu` usaram).
  Reportado como três números em vez de um sim/não porque `almoxarifado` e `edu` são **mistos**
  (o step de usuários encadeia uma tabela de UI, o resto faz replay ORM).
- **replay ORM (todo `steps/`)** — mesma classificação aplicada a **todos** os `steps/*.py`, não só
  `given.py`. Existe porque alguns apps põem setup ORM em `when.py`/`then.py`; sem essa coluna a
  anterior mentiria.
- **Apps externos nos steps** — imports absolutos em `features/steps/*.py` cuja raiz é outro app de
  `APPS_SUAP` (`suap/settings_base.py`). **A dependência do seed global
  (`djtools/new_tests/test_initial_data.py`) não virou coluna porque é universal, e isso está
  verificado, não inferido:** `suap/settings_base.py:746` já inicializa
  `TEST_INITIAL_DATA = ['djtools.new_tests.test_initial_data.start_database', '...initial_data']`;
  `djtools/new_tests/runner.py:180-190` apenas **acrescenta** a essa lista o
  `<app>/features/test_initial_data.py` quando ele existe; e `djtools/new_tests/keepdb_manager.py:900`
  executa tudo que estiver na lista. Ou seja, o seed global roda incondicionalmente para os 52 apps
  (todos têm `features/environment.py`), e a coluna informaria zero. Em troca, o que varia — e por isso
  virou coluna — é de qual **outro domínio** o app depende. `rh` e `comum` são quase universais e por
  si só não são sinal de custo; `edu` é.
- **Grupos `permissions.yaml`** — chaves de topo do YAML (cada uma é um grupo; `app_manager` e
  `description` são aninhados). Proxy de fixture de papéis pesada, como aconteceu no almoxarifado.
- **Steps UI próprios** — decoradores `@given`/`@when`/`@then`/`@step` em `features/steps/*.py`.
  Proxy do vocabulário que a camada `Tela` (`djtools/e2e_ui.py`) talvez ainda não cubra.

## Critério do custo de seed

Escala ordinal por pontos. Cada regra soma (ou subtrai) e o total classifica.
**Isto pontua o custo de construir o *seed*, não o esforço e2e total** — o volume de cenários entra
apenas como proxy da largura de dados a semear, não do número de asserts a escrever.

| Regra | Pontos |
| --- | --- |
| Cenários: `< 10` / `10–29` / `30–59` / `≥ 60` | `0` / `+1` / `+2` / `+3` |
| Já tem material de seed: existe `test_initial_data.py` **ou** `≥ 4` defs de replay ORM em `steps/` | `−1` |
| Não tem **nenhuma** def de replay ORM em `steps/` (seed escrito do zero) | `+1` |
| `permissions.yaml` com `≥ 20` grupos | `+1` |
| Importa o domínio de `edu` nos steps | `+1` |
| Importa `≥ 3` apps externos além de `rh`/`comum` | `+1` |
| `≥ 10` steps de UI próprios | `+1` |

**Classificação:** `≤ 1` = **baixo** · `= 2` = **médio** · `≥ 3` = **alto**.

Os limiares foram **calibrados contra os dois módulos já feitos**, não escolhidos a priori:
aplicado mecanicamente, o critério coloca `almoxarifado` em **baixo** (0 pontos — 220 LOC de
`conftest.py`, ≈45 testes) e `edu` em **alto** (4 pontos — 418 LOC de `conftest.py`, ≈112 testes),
que é a ordem observada na prática. Ressalva: as LOC de `conftest.py` foram medidas agora, mas os
números de testes **coletados** vêm de execuções anteriores da suíte (aqui só foram conferidas as
36 e 86 defs `def test_`, que a parametrização expande para ≈45 e ≈112).

## Tabela

| Módulo | `.feature` | Cenários | `test_initial_data.py` | `given.py` LOC | defs topo | replay ORM | encadeia UI | replay ORM (todo `steps/`) | Apps externos nos steps | Grupos `permissions.yaml` | Steps UI próprios | Pontos | Custo de seed |
| --- | ---: | ---: | :---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | --- |
| **edu** (FEITO) | 13 | 132 | não | 1103 | 30 | 28 | 1 | 29 | `comum`, `rh` | 71 | 24 | 4 | alto |
| pesquisa | 16 | 132 | não | 193 | 4 | 4 | 0 | 4 | `almoxarifado`, `cnpq`, `comum`, `financeiro`, `patrimonio`, `rh` | 23 | 4 | 4 | alto |
| saude | 4 | 77 | não | 179 | 18 | 17 | 1 | 17 | `comum`, `rh` | 26 | 18 | 4 | alto |
| estagios | 9 | 46 | não | 288 | 1 | 1 | 0 | 1 | `comum`, `edu`, `rh` | 14 | 2 | 3 | alto |
| comum | 5 | 39 | não | 22 | 2 | 1 | 1 | 1 | — | 41 | 2 | 3 | alto |
| projetos | 10 | 58 | não | 71 | 1 | 1 | 0 | 1 | `comum`, `financeiro` | 15 | 1 | 2 | médio |
| projetos_ensino | 10 | 54 | não | 61 | 1 | 1 | 0 | 1 | `comum`, `financeiro` | 12 | 1 | 2 | médio |
| demandas | 4 | 31 | não | 22 | 1 | 1 | 0 | 2 | `comum` | 11 | 3 | 2 | médio |
| ae | 2 | 27 | não | 103 | 2 | 2 | 0 | 2 | `comum`, `edu`, `rh` | 11 | 2 | 2 | médio |
| catalogo_provedor_servico | 3 | 16 | não | 455 | 10 | 7 | 2 | 7 | `comum`, `documento_eletronico`, `edu`, `processo_eletronico`, `processo_seletivo`, `rh` | 3 | 4 | 2 | médio |
| solenidades | 2 | 15 | não | — | 0 | 0 | 0 | 0 | — | 5 | 0 | 2 | médio |
| centralservicos | 1 | 14 | não | — | 0 | 0 | 0 | 0 | — | 10 | 0 | 2 | médio |
| clipping | 3 | 14 | não | — | 0 | 0 | 0 | 0 | — | 1 | 0 | 2 | médio |
| demandas_externas | 5 | 11 | não | 28 | 1 | 1 | 0 | 1 | `edu`, `projetos` | 6 | 1 | 2 | médio |
| plan_v2 | 6 | 49 | não | 219 | 7 | 6 | 1 | 6 | `comum`, `financeiro`, `rh` | 5 | 8 | 1 | baixo |
| processo_eletronico | 3 | 29 | não | 144 | 3 | 3 | 0 | 3 | `comum`, `documento_eletronico`, `rh` | 13 | 3 | 1 | baixo |
| documento_eletronico | 3 | 25 | não | 73 | 3 | 1 | 2 | 1 | `rh` | 12 | 1 | 1 | baixo |
| eleicao | 1 | 15 | não | 24 | 2 | 1 | 1 | 1 | `comum` | 2 | 3 | 1 | baixo |
| contratos | 4 | 13 | não | 65 | 1 | 1 | 0 | 1 | `processo_eletronico`, `rh`, `tesouro_gerencial` | 8 | 1 | 1 | baixo |
| professor_titular | 4 | 12 | não | 13 | 1 | 1 | 0 | 1 | — | 6 | 1 | 1 | baixo |
| materiais | 5 | 11 | não | 34 | 1 | 1 | 0 | 1 | `financeiro` | 3 | 1 | 1 | baixo |
| portaria | 2 | 9 | não | — | 0 | 0 | 0 | 0 | — | 5 | 0 | 1 | baixo |
| erros | 2 | 7 | não | 121 | 2 | 1 | 1 | 1 | `comum`, `edu`, `rh` | 4 | 4 | 1 | baixo |
| pedagogia | 2 | 6 | não | 16 | 1 | 1 | 0 | 1 | `comum`, `edu` | 1 | 1 | 1 | baixo |
| cpa | 2 | 5 | não | — | 0 | 0 | 0 | 0 | — | 5 | 0 | 1 | baixo |
| etep | 4 | 5 | não | — | 0 | 0 | 0 | 0 | — | 8 | 0 | 1 | baixo |
| acumulocargo | 2 | 4 | não | — | 0 | 0 | 0 | 0 | — | 3 | 0 | 1 | baixo |
| boletim_servico | 1 | 4 | não | — | 0 | 0 | 0 | 0 | — | 3 | 0 | 1 | baixo |
| rh | 1 | 4 | não | 10 | 1 | 1 | 0 | 1 | `comum` | 41 | 1 | 1 | baixo |
| egressos | 1 | 3 | não | — | 0 | 0 | 0 | 0 | — | 4 | 0 | 1 | baixo |
| gestao | 1 | 3 | não | — | 0 | 0 | 0 | 0 | — | 4 | 0 | 1 | baixo |
| auxilioemergencial | 1 | 2 | não | 8 | 1 | 0 | 0 | 0 | `ae` | 4 | 1 | 1 | baixo |
| **almoxarifado** (FEITO) | 42 | 28 | sim | 92 | 5 | 4 | 1 | 4 | `protocolo`, `rh` | 9 | 5 | 0 | baixo |
| progressoes | 1 | 10 | sim | 30 | 1 | 1 | 0 | 1 | — | 5 | 1 | 0 | baixo |
| encceja | 4 | 9 | não | 9 | 1 | 1 | 0 | 1 | — | 2 | 1 | 0 | baixo |
| eventos | 5 | 9 | não | 56 | 1 | 1 | 0 | 1 | — | 6 | 1 | 0 | baixo |
| rsc | 3 | 9 | não | 15 | 1 | 1 | 0 | 1 | — | 8 | 1 | 0 | baixo |
| avaliacao_integrada | 2 | 8 | não | 41 | 1 | 1 | 0 | 1 | `comum` | 3 | 1 | 0 | baixo |
| frota | 5 | 8 | não | 54 | 1 | 1 | 0 | 1 | — | 8 | 1 | 0 | baixo |
| arquivo | 3 | 7 | não | 44 | 1 | 1 | 0 | 1 | — | 3 | 1 | 0 | baixo |
| cnpq | 1 | 7 | não | 11 | 1 | 1 | 0 | 1 | — | 3 | 1 | 0 | baixo |
| orcamento | 3 | 7 | não | 69 | 1 | 1 | 0 | 1 | `financeiro` | 2 | 1 | 0 | baixo |
| processo_seletivo | 5 | 7 | não | 8 | 1 | 1 | 0 | 1 | `comum` | 13 | 1 | 0 | baixo |
| acompanhamentofuncional | 2 | 6 | não | 8 | 1 | 1 | 0 | 1 | `rh` | 4 | 1 | 0 | baixo |
| sica | 3 | 6 | não | 19 | 1 | 1 | 0 | 1 | — | 1 | 1 | 0 | baixo |
| avaliacao_cursos | 2 | 5 | não | 8 | 1 | 1 | 0 | 1 | `comum` | 2 | 1 | 0 | baixo |
| temp_rh2 | 2 | 5 | não | 18 | 2 | 2 | 0 | 2 | `rh` | 4 | 2 | 0 | baixo |
| convenios | 4 | 4 | não | 25 | 1 | 1 | 0 | 1 | — | 8 | 1 | 0 | baixo |
| estacionamento | 1 | 4 | não | 8 | 1 | 1 | 0 | 1 | — | 1 | 1 | 0 | baixo |
| chaves | 1 | 2 | não | 14 | 1 | 1 | 0 | 1 | `comum`, `rh` | 4 | 1 | 0 | baixo |
| ponto | 1 | 2 | não | 13 | 1 | 1 | 0 | 1 | `rh` | 15 | 1 | 0 | baixo |
| enquete | 2 | 8 | sim | 12 | 1 | 0 | 1 | 0 | — | 5 | 1 | −1 | baixo |

## Leitura

O esforço total é de **1.023 cenários** em 52 apps; descontando os dois já feitos (160 cenários),
restam **863 cenários em 50 módulos**. A distribuição é fortemente assimétrica e é o dado principal:
a **mediana é de 9 cenários por módulo restante**, mas os cinco maiores (`pesquisa` 132, `saude` 77,
`projetos` 58, `projetos_ensino` 54, `plan_v2` 49) somam 370 — **43% de todo o esforço restante em 10%
dos módulos**. Pelo critério acima os módulos restantes se agrupam em **4 alto** (`pesquisa`, `saude`,
`estagios`, `comum`; 294 cenários), **9 médio** (240 cenários) e **37 baixo** (329 cenários): a cauda
longa é composta de módulos com uma única feature, um único step `@given` e um `given.py` de 8–20 LOC,
que na prática são "criar 2–3 objetos e clicar num menu".

Outliers em ambas as direções. **Caros e não óbvios:** `saude` — só 4 arquivos `.feature`, mas 77
cenários e 18 steps de UI próprios dentro deles, ou seja, o volume está escondido dentro dos arquivos,
não no número deles; e `comum`, que tem `given.py` de apenas 22 LOC mas **41 grupos** de permissão, o
mesmo perfil que fez a fixture de papéis do almoxarifado ser cara. **Baratos e não óbvios:**
`catalogo_provedor_servico` importa 6 apps externos (incluindo `edu`) e parece assustador, mas já tem
**455 LOC / 7 defs de replay ORM** prontas — o seed em grande parte já está escrito, só precisa sair do
behave; e `plan_v2`, com 49 cenários (5º maior) mas 6 defs de replay ORM e só 5 grupos de permissão.
No extremo oposto, **10 módulos não têm `given.py` nenhum** (`solenidades`, `centralservicos`,
`clipping`, `portaria`, `cpa`, `etep`, `acumulocargo`, `boletim_servico`, `egressos`, `gestao`) — nesses
o seed é escrito do zero, embora 6 deles tenham menos de 10 cenários.

Sobre a materialização do custo, os dois módulos feitos dão uma régua: `almoxarifado` converteu
28 cenários em ≈45 testes coletados com 220 LOC de `conftest.py`; `edu` converteu 132 cenários em ≈112
testes com 418 LOC de `conftest.py` (LOC medidas aqui, testes coletados em execuções anteriores). Ou seja, **a razão cenário → teste fica em torno de 1:1** (o
almoxarifado subiu para ≈1,6:1 porque desdobrou permissões em matriz), mas **o `conftest.py` de seed
não escala com o número de cenários** — dobra apenas de 220 para 418 LOC enquanto os cenários quase
quintuplicam. O custo do seed é função da **profundidade do grafo de domínio** (quantas entidades
precisam existir antes do primeiro clique), não do volume de asserts, e é exatamente isso que as
colunas de replay ORM, apps externos e grupos de permissão tentam capturar.
