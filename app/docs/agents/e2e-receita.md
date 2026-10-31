# Receita e2e — o que reusar ao cobrir um módulo novo

Destilado dos dois módulos já mapeados (`almoxarifado` e `edu`) e dos fluxos transversais
(`tests/e2e/`). Serve de base para um gerador de testes e2e: o que aqui está marcado como
**receita** vale para qualquer módulo; o que está em **(e) Ad-hoc** existe por acidente
histórico e não deve ser copiado.

Regra de ouro: a receita **reusa** `djtools/e2e_fixtures.py` e `djtools/e2e_ui.py`. Camada
nova só com justificativa explícita — há exatamente uma lacuna apontada, no fim da seção 1.

Fontes primárias lidas: `djtools/e2e_fixtures.py`, `djtools/e2e_ui.py`, os três conftests
(`almoxarifado/tests/e2e/`, `edu/tests/e2e/`, `tests/e2e/`), os 29 arquivos `test_*.py`
dessas três árvores, `almoxarifado/features/001.almoxarifado.cadastros_basicos.feature`,
`edu/features/001.EDU.configurar-diretoria.feature`, `suap/settings_test.py`,
`pyproject.toml` e `.gitlab-ci.yml`.

---

## 0. O mapa da infra que já existe

Duas camadas em `djtools/`, e nenhuma delas é plugin global — o escopo por diretório é
deliberado (`djtools/e2e_fixtures.py:13-16`).

| Camada | Arquivo | O que entrega |
|---|---|---|
| Banco + browser + sessão | `djtools/e2e_fixtures.py` | `e2e_banco`, `e2e_seed`, `semear_base`, `campus`, `setor`, `servidor_com_login`, `criar_servidores`, `live_server`, `base_url`, `login_ui`, `storage_states`, `logado`, os overrides `_django_db_helper` / `_exige_banco_de_e2e`, e 4 helpers de página |
| Localizadores da UI | `djtools/e2e_ui.py` | a classe `Tela` (navegação, recortes, cliques, formulário, asserções) |

O acesso é sempre por **star-import no conftest do módulo** (`djtools/e2e_fixtures.py:3-11`):

```python
from djtools.e2e_fixtures import *  # noqa: F403
```

Tem de ser star-import **em conftest**, não `pytest_plugins`: é a precedência de conftest
sobre plugin que faz os overrides valerem (`djtools/e2e_fixtures.py:8-11`). O `__all__` em
`djtools/e2e_fixtures.py:58-72` lista nomes com underscore de propósito — `import *` não
exporta nomes privados, e sem `_django_db_helper` no conftest a suíte volta a dar flush por
teste (`djtools/e2e_fixtures.py:53-57`).

O `e2e_seed` do djtools é o seed por factories (#17486): `semear_base()` — catálogos,
`Configuracao`, raiz e o `admin` (senha `SENHA_E2E`). O módulo monta o resto num seed de sessão
próprio que depende de `e2e_seed`, com `campus`/`setor`/`criar_servidores` e as factories dele
(ex.: `erros/tests/e2e/conftest.py`). `djtools/new_tests/` é só do behave: não importe.

---

## 1. A tradução behave → pytest (o coração da receita)

`djtools/e2e_ui.py:13-19` já traz a tabela de correspondência, e ela confere com as
`.feature` reais. Verificado contra
`almoxarifado/features/001.almoxarifado.cadastros_basicos.feature` e
`edu/features/001.EDU.configurar-diretoria.feature`:

| Passo behave | Vira | Evidência |
|---|---|---|
| `Quando acesso a página "/url/"` | `tela.ir('/url/')` | `e2e_ui.py:73-75` |
| `Quando acesso o menu "Ensino::Cadastros::X"` | `tela.ir('/url/')` — o menu **não** é portado | `e2e_ui.py:21-22` |
| `E clico no botão "Salvar"` | `tela.clicar_botao('Salvar')` | `e2e_ui.py:160-165` |
| `E clico no link "X"` | `tela.clicar_link('X')` | `e2e_ui.py:167-171` |
| `E clico na aba "Direção"` | `tela.clicar_aba('Direção')` | `e2e_ui.py:173-179` |
| `E clico no ícone de edição` | `tela.clicar_icone('edição')` | `e2e_ui.py:181-185`, `ICONES` em `:44` |
| `E olho para o popup` | `tela.popup()` | `e2e_ui.py:119-123` |
| `E olho para o quadro "X"` | `tela.quadro('X')` | `e2e_ui.py:94-102` |
| `E olho a linha "X"` | `tela.linha('X')` | `e2e_ui.py:107-111` |
| `E seleciono o item da lista` | `tela.selecionar_item('X')` | `e2e_ui.py:196-201` |
| `E preencho o formulário com os dados \| Campo \| Tipo \| Valor \|` | `tela.preencher('Campo', 'tipo', 'Valor')` ou `tela.preencher_formulario([...])` | `e2e_ui.py:234-256` |
| `Então vejo mensagem de sucesso "X"` | `tela.sucesso('X')` | `e2e_ui.py:321-336` |
| `Quando a data do sistema for "dd/mm/aaaa"` | `freeze_time` (ver seção 3, relógio) | `edu/tests/e2e/conftest.py:84-88` |
| `Dado os seguintes usuários \| ... \|` | fixture de papéis do conftest | `almoxarifado/tests/e2e/conftest.py:58-74` |
| `@do_document` | **nada** — os screenshots são a razão de o behave continuar existindo | `e2e_ui.py:22-23` |
| `Quando acesso o menu "Sair"` | **nada** — cada teste tem contexto novo | `e2e_fixtures.py:20-23` |

Os tipos aceitos em `preencher` estão em `_PREENCHEDORES` (`e2e_ui.py:379-392`): `texto`,
`senha`, `número`, `textarea`, `lista`, `checkbox`, `radio`, `checkbox multiplo`, `data`,
`arquivo`, `autocomplete`, `autocomplete multiplo` — os mesmos rótulos da coluna `Tipo` das
tabelas do behave. `data` recebe `dd/mm/aaaa` e converte para ISO internamente
(`e2e_ui.py:275-278`).

### As três regras de granularidade

Estas não estão escritas em lugar nenhum e são o que mais muda ao portar. Derivadas da
comparação entre as `.feature` e os testes:

**Regra 1 — uma CADEIA de cenários vira UM teste.** A feature 001 do almoxarifado tem 13
cenários; `almoxarifado/tests/e2e/test_cadastros.py` tem 3 testes. Os cenários
`Cadastrar` → `Visualizar` → `Editar` → `Apagar` de Unidade de Medida
(`001.almoxarifado.cadastros_basicos.feature:13-47`) viram o único
`test_unidade_de_medida_ciclo_completo` (`test_cadastros.py:24-46`), cuja docstring diz
exatamente isso: *"o ciclo que a feature 001 cobre em 4 cenários"* (`:25`). O motivo é
estrutural: no behave os cenários compartilham banco e sessão e a ordem importa
(`e2e_fixtures.py:18-23`); no pytest cada teste é independente, então um cenário que só faz
sentido depois do anterior não pode ser um teste sozinho.

**Regra 2 — cenários IRMÃOS viram um `parametrize`.** `Vincular Diretor Geral`,
`Vincular Diretor Acadêmico` e `Vincular Coordenador de Curso`
(`edu/features/001.EDU.configurar-diretoria.feature:40-75`) são três cenários idênticos a
menos do par (aba, grupo), encadeados por `Dado a atual página`. Viraram um único
`test_vincula_papel_da_diretoria` parametrizado por `('aba', 'grupo')`
(`edu/tests/e2e/test_01_diretoria.py:69-77`). A docstring justifica: *"o que se está
verificando é exatamente o par (aba, grupo)"* (`:81`).

**Regra 3 — o cenário de setup vira fixture, nunca teste.** O primeiro cenário de toda
feature (`Adiciona os usuarios necessarios para essa funcionalidade` em
`001.almoxarifado.cadastros_basicos.feature:7-10`; `Configuração inicial para execução dos
cenários do edu` em `001.EDU.configurar-diretoria.feature:5-19`) só cria usuários e loga.
Vira fixture de conftest: `servidores_almox`
(`almoxarifado/tests/e2e/conftest.py:58-74`) e o replay `edu_seed`
(`edu/tests/e2e/conftest.py:131-154`).

**Corolário — nomes fixos viram nomes únicos.** A feature grava
`Teste Unidade de Medida` (`:19`); o teste grava `f'E2E Unidade {uuid4().hex[:8]}'`
(`test_cadastros.py:20,26`). Porque a suíte e2e **não dá flush** (seção 4) e o segundo
`--reuse-db` encontraria o registro da run anterior.

### A coluna `Tipo`: normalização, e o que a `Tela` preenche

**Escreva o tipo como a `.feature` escreve.** `Tela.preencher` normaliza caixa e resolve os
aliases (`Texto` → `texto`, `TextArea` → `textarea`, `Numero` → `número`), porque as features
capitalizam a coluna — só `Texto` são 595 ocorrências — e as chaves de `_PREENCHEDORES` são
minúsculas. Tipo desconhecido falha alto, listando os conhecidos.

**Autocomplete com busca diferente do rótulo**: `preencher(campo, 'autocomplete', busca,
opcao='texto do resultado')`. Sem `opcao`, digita-se e escolhe-se o mesmo texto — o que não
serve quando o campo é pesquisável por um valor que não aparece no resultado (o autocomplete
de setor exibe o setor superior; o de matriz, a descrição e não o código). Na tabela de
`preencher_formulario`, a linha vira uma tupla de **4**. Era essa lacuna que fazia 8 dos 14
arquivos do `edu` misturarem `Tela` com `e2e_fixtures.escolher_autocomplete`; testes novos não
precisam mais disso.

**Tipos cobertos (18):** texto, senha, número, textarea, lista, checkbox, radio, checkbox
multiplo, **checkbox popup**, data, **data e hora**, hora, arquivo, **arquivo real**,
autocomplete, autocomplete multiplo, **filteredselectmultiple** e **texto rico**. Os cinco em
negrito entraram por medição, não por demanda: `filteredselectmultiple` e `texto rico` somam 66
usos em 20 módulos (#16983), e `data e hora` é o `input[type=datetime-local]` de
`DateTimeFieldPlus` — que `data` não preenche, e de que o edital de Remoção Interna tem 12 num
formulário só. Ele omite os segundos quando são zero: o Chromium normaliza `...T08:00:00` para
`...T08:00` e o `fill` do Playwright, que relê o valor depois de escrever, rejeita a diferença
com `Error: Malformed value`.

**`arquivo` × `arquivo real`:** `arquivo` resolve o valor por extensão em `ARQUIVOS` (quatro
arquivos genéricos) e serve para provar que o upload acontece; `arquivo real` sobe o caminho que
se passar (relativo ao `BASE_DIR` ou absoluto) e é o que serve quando a tela processa o
**conteúdo**. Foi a fatia de assinatura digital do `comum` que o exigiu: a tela de verificação
precisa de um PDF *assinado*, e com o PDF genérico ela responde — corretamente — "assinatura não
identificada", o que faria o teste afirmar o caminho vazio.

**O que ainda não existe:** `captcha` (1 uso, que nem o behave trata) — e ele raramente atrapalha,
porque `ReCaptchaField.validate` (`djtools/forms/fields/captcha.py`) devolve `True` sob teste
antes mesmo da checagem de obrigatoriedade. Ao esbarrar em outro tipo, estenda de forma
**aditiva** ou registre dispensa com motivo.

---

## (a) Esqueleto de `<modulo>/tests/e2e/conftest.py`

O mínimo é só o star-import (o `e2e_seed` do djtools já dá a base). O que segue é o esqueleto
de um módulo com seed e papéis próprios, por factories (#17486). Os pontos de variação estão
marcados com `# VARIA:`.

```python
"""Substrato dos e2e do <modulo>: <uma linha sobre o que o módulo precisa além da base>.

Rodar (invocação separada da suíte unitária — ver ``djtools/e2e_fixtures.py``)::

    TEST_DATABASE_NAME=test_suap_e2e DJANGO_SETTINGS_MODULE=suap.settings_test \\
        uv run pytest <modulo>/tests/e2e --reuse-db
"""

from __future__ import annotations

import pytest

# Traz `logado`, `login_ui`, `live_server`, `e2e_banco`, `e2e_seed` e os overrides de
# `_django_db_helper`/`_exige_banco_de_e2e`. Precisa ser star-import em conftest: é a
# precedência de conftest sobre plugin que faz os overrides valerem.
from djtools.e2e_fixtures import *  # noqa: F403
from djtools.e2e_fixtures import campus, criar_servidores

# VARIA: nome legível -> matrícula, para os testes não ficarem cheios de números mágicos.
# Faixa de matrículas PRÓPRIA do módulo: o job de doc roda vários módulos num banco só, e a
# `ServidorFactory` é get-or-create pela matrícula.
PAPEIS = {...}

# VARIA: matrícula -> (nome, grupos) — a tabela `os seguintes usuários` do behave.
SERVIDORES = {...}


@pytest.fixture(scope='session')
def <modulo>_seed(e2e_seed):
    """VARIA — o seed do módulo, por factories, sobre a base do `e2e_seed`.

    O `e2e_seed` dá catálogos, `Configuracao`, a raiz e o `admin`; o resto vem de
    `<modulo>/tests/factories.py` (e das factories dos apps donos: `rh`, `comum`...). Não
    importe `djtools.new_tests`. O banco já está aberto (`e2e_banco`). Sempre IDEMPOTENTE:
    a suíte não dá flush e o banco é compartilhado entre os módulos da rodada.

    Papéis EAGER aqui dentro, antes da primeira request: o SUAP resolve permissão com cache
    por processo, então atribuir grupo no meio da sessão dá resultado dependente de ordem
    (`almoxarifado/tests/e2e/conftest.py:60-68`). Senha de todos: `SENHA_E2E` (é a que o
    `logado` usa; confirmações de senha nas telas também). Sem e-mail nem `setor_lotacao`.
    """
    # Siglas da árvore comum aos módulos (CEN, CZN, A0, DIAC/CEN...): `campus`/`setor` reencontram
    # o setor de mesma sigla, então módulos que dividem banco não duplicam a árvore.
    criar_servidores(campus('CEN', 'Campus Central'), SERVIDORES)


@pytest.fixture
def logado_<modulo>(logado, <modulo>_seed):
    """`(papel) -> Page` autenticada. `logado` já acha a senha (`SENHA_E2E`)."""

    def _logado(papel: str):
        assert papel in PAPEIS, f'papel desconhecido: {papel}; declare em PAPEIS'
        return logado(PAPEIS[papel])

    return _logado
```

Pontos de variação, resumidos: **(1)** o que o seed do módulo cria além da base; **(2)** papéis e grupos;
**(3)** precisa congelar o relógio? (então `logado_<modulo>` não pode usar `storage_states`
— ver (c)); **(4)** fixtures de estado de domínio por teste (`requisicao_pendente` em
`almoxarifado/tests/e2e/conftest.py:127-144`, `setor_livre` em
`edu/tests/e2e/conftest.py:345-371`), que existem só porque não há flush.

---

## (b) Esqueleto de um arquivo de teste

```python
"""Fluxo: <o que este arquivo cobre> (feature <NNN> do behave).

<Por que este fluxo importa para o módulo — 2 a 4 linhas. Qual regressão ele pega.>
"""

import pytest
from playwright.sync_api import expect

from djtools.e2e_ui import Tela

# Obrigatório e SEMPRE nesta forma — os 29 arquivos e2e do repo usam exatamente esta linha.
# `e2e` é o que separa a suíte da unitária (`pyproject.toml:308`, `.gitlab-ci.yml:169`).
# `django_db(databases='__all__')` é o que faz o banco de teste ser criado: sem o marker,
# `aliases` fica vazio e o browser roda contra o banco de desenvolvimento
# (`djtools/e2e_fixtures.py:177-181`).
pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# VARIA: só em módulo com relógio congelado — a data que ESTE arquivo precisa.
# A fixture autouse `data_do_modulo` a lê de `request.module.DATA`
# (`edu/tests/e2e/conftest.py:329-342`).
DATA = '10/03/2019'

# URLs no topo, como constantes: elas se repetem entre os testes do arquivo.
LISTAGEM = '/admin/<modulo>/<model>/'
FORM = '/admin/<modulo>/<model>/add/'


def test_<acao>_<objeto>(logado_<modulo>):
    """<O que o teste afirma, e o detalhe não óbvio que justifica ele existir.>"""
    from <modulo>.models import <Model>

    tela = Tela(logado_<modulo>('<papel>')).ir(FORM)
    tela.preencher_formulario([
        ('Nome', 'texto', 'E2E ...'),
        ('Categoria', 'autocomplete', '...'),
    ])
    tela.clicar_botao('Salvar')

    # ASSERÇÃO DUPLA, sempre nesta ordem: a mensagem da UI e depois o ORM.
    tela.sucesso('Cadastro realizado com sucesso')
    assert <Model>.objects.filter(nome='E2E ...').exists(), 'a UI disse que salvou, mas não persistiu'
```

Convenções que os 29 arquivos seguem:

- **Docstring de módulo obrigatória**, dizendo qual feature do behave o arquivo cobre e por
  que o fluxo importa. Exemplos: `almoxarifado/tests/e2e/test_cadastros.py:1-6`,
  `edu/tests/e2e/test_01_diretoria.py:1-7`.
- **Docstring de teste** só quando há algo não óbvio (uma armadilha, uma escolha de dado, um
  achado). Testes triviais não têm — `edu/tests/e2e/test_01_diretoria.py:62-66`.
- **Import de model dentro do corpo do teste**, não no topo. É o padrão em todos os arquivos
  (`test_cadastros.py:43,71,101`; `test_01_diretoria.py:26,48,135`). O import de `Tela` e dos
  helpers, esse é de topo — `edu/tests/e2e/test_12_credito.py:23` prova que funciona mesmo
  em módulo com relógio congelado.
- **Asserção dupla UI + ORM.** A mensagem recorrente é
  `'a UI disse que salvou, mas não persistiu'` (`test_cadastros.py:74`,
  `test_01_diretoria.py:37`). Afirmar só a mensagem de sucesso não prova persistência;
  afirmar só o ORM não prova que a tela funciona.
- **Afirme sempre o fato POSITIVO.** Ausência de mensagem de erro não é prova de sucesso —
  dá falso verde e falso vermelho conforme o timing do submit
  (`djtools/e2e_fixtures.py:137-138`).
- **Permissão se testa por status HTTP**, não por texto: `page.goto(url).status == 403`
  (`almoxarifado/tests/e2e/test_permissoes.py:54-58`, `test_01_diretoria.py:193`).
- **Matriz de acesso como `parametrize` de uma lista nomeada**, medida no navegador e não
  deduzida do YAML — documentação executável (`almoxarifado/tests/e2e/test_permissoes.py:24-58`).

### Nome de arquivo: `test_NN_dominio.py` ou `test_dominio.py`?

Os dois existem: `edu/tests/e2e/test_01_diretoria.py` … `test_14_enade.py` contra
`almoxarifado/tests/e2e/test_cadastros.py`.

**Vence o prefixo `NN` só quando a cadeia for realmente sequencial.** O prefixo não é
cosmético no edu — é o mecanismo de ordenação: `edu/tests/e2e/conftest.py:315-317` diz que
*"o nome do arquivo é o que ordena"*, e `curso_credito` (`:311-326`) falha com mensagem
explícita se `test_12` não rodou antes de `test_13`/`test_14`. No almoxarifado os cinco
arquivos são independentes (cada um casa 1:1 com uma feature, sem estado compartilhado
entre eles), e aí o prefixo seria ruído. Regra para o gerador: **numere se e somente se um
arquivo depender do estado que outro produziu**; e, se numerar, diga isso na docstring do
conftest.

---

## (c) Decisões que o gerador tem de tomar por módulo

1. **Origem do seed.** Sempre factories, num `<modulo>_seed(e2e_seed)` de sessão: a base vem do
   `e2e_seed` (`semear_base`), a árvore de `campus`/`setor`, os servidores de
   `criar_servidores`/`servidor_com_login` e o domínio das factories do módulo e dos apps donos.
   Replay ORM dos `given.py` do **próprio** módulo ainda é aceito onde existe (edu, projetos),
   mas `djtools.new_tests` (`given_comum`, `test_initial_data`) não: sai com o behave (#17486).

2. **Papéis, grupos e permissões.** A base só tem o `admin` (superusuário): todo papel do
   módulo é um servidor próprio, com matrícula própria. O módulo é governado por grupo? Se for, precisa de fixture eager de papéis — e ela tem de rodar
   **antes da primeira request** por causa do cache de permissão por processo
   (`almoxarifado/tests/e2e/conftest.py:60-68`). Atenção ao escopo: o edu resolve permissão
   por `UsuarioGrupoSetor` (grupo **com setor**), o resto do SUAP por grupo global
   (`edu/tests/e2e/test_01_diretoria.py:4-6`, `edu/tests/e2e/conftest.py:374-396`).

3. **Relógio.** Congele **só se** o domínio do módulo tiver data embutida no seed. O edu
   congela porque todo o mundo dele vive em 2019 (`edu/tests/e2e/conftest.py:28-29`); o
   almoxarifado não congela nada. Se congelar, três consequências obrigatórias:
   - o relógio é **da sessão**, não do teste — a sessão de login é validada contra
     `expire_date` no banco, e cookie emitido numa data e lido noutra é sessão expirada
     (`edu/tests/e2e/conftest.py:94-98`);
   - por isso **não** dá para usar `storage_states`; tem de logar de verdade a cada teste
     (`edu/tests/e2e/conftest.py:399-407`), o que só é barato por causa do hasher MD5 de
     `suap/settings_test.py:56-59`;
   - precisa de uma fixture autouse que fixe a data por módulo e **descongele no fim de cada
     teste**, senão 2019 vaza para os e2e transversais coletados depois numa run
     `pytest -m e2e` (`edu/tests/e2e/conftest.py:329-342`).

4. **Encadeamento e ordem.** Decidir se os arquivos são independentes (almoxarifado) ou uma
   cadeia (edu). Se for cadeia, o padrão é uma **escada de fixtures session-scoped**, cada
   uma dependendo da anterior: `edu_seed` → `seed_periodo_executado` →
   `seed_periodo_fechado` → `seed_matricula_renovada`
   (`edu/tests/e2e/conftest.py:131,156,170,179`). Isso é receita. Cada degrau precisa de uma
   **sentinela** que o torne idempotente, e a sentinela tem de ser escolhida com cuidado: em
   `seed_conceito` o guard é a aluna e não a turma, porque `test_03_turmas` cria turma no
   mesmo curso e guardar pela turma tornaria o seed um no-op
   (`edu/tests/e2e/conftest.py:205-209`).

5. **Granularidade.** As três regras da seção 1: cadeia de cenários → um teste; cenários
   irmãos → `parametrize`; cenário de setup → fixture.

6. **Papel por teste.** Cada teste declara o papel com que loga. Nos dois módulos isso é
   sempre explícito na primeira linha do corpo (`logado_almox('ContadorAdministra')`,
   `logado_edu('admin_academico')`) — nunca um default implícito, porque o papel é metade do
   que o teste afirma.

---

## (d) Armadilhas já conhecidas

**1. Override no-op de `_django_db_helper`.** `djtools/e2e_fixtures.py:165-186`. O
pytest-django força `transaction=True` quando `live_server` é pedido, e o teardown do
`TransactionTestCase` dá flush em todas as tabelas — apagaria `auth_group`,
`comum.GroupDetail` e `comum.GerenciamentoGrupo`, que o `post_migrate` não recria. O
override anula isso. Duas consequências: **(a)** o marker
`django_db(databases='__all__')` continua obrigatório em todo teste, senão o browser roda
contra o banco de **desenvolvimento** (`:177-181`); **(b)** é acoplamento a nome privado do
pytest-django — um rename futuro reativa o flush silenciosamente (`:183-184`). Os dois
testes de `tests/e2e/test_login.py:31-44` existem só para provar que o par
visibilidade/sem-flush funciona.

**2. `TEST_DATABASE_NAME` com sufixo `_e2e` é obrigatório.** Guard session-scoped autouse em
`djtools/e2e_fixtures.py:189-211` que falha alto sem ele. Motivo: o seed do e2e e a fixture
`suap_data` de `comum/pytest_fixtures.py` montam a mesma árvore organizacional de formas
incompatíveis, e compartilhar banco estoura `UniqueViolation` em
`unidadeorganizacional_setor_id_key`. O CI já passa isso (`.gitlab-ci.yml:159`). Note que a
separação vem da env, **não** de um override de `django_db_modify_db_settings`: aquele
override era session-scoped e, com os e2e espalhados por vários conftests irmãos, era
instanciado uma vez por conftest, mandando cada subárvore para um banco diferente
(`:198-204`).

**3. Cache de permissão por processo.** Criar o vínculo de grupo sob demanda, no meio da
sessão, dá resultado dependente de ordem: uma tela que já respondeu 403 continua 403 mesmo
depois de o usuário entrar no grupo. Observado na prática — a mesma URL deu 403 e depois 200
conforme o momento da atribuição (`almoxarifado/tests/e2e/conftest.py:60-68`). Por isso a
fixture de papéis é eager e session-scoped.

**4. freezegun × django-ninja.** `edu/tests/e2e/conftest.py:107-121`. `freeze_time` troca
`datetime.date` por `FakeDate`; `suap/urls.py` importa `suap/api.py`, que monta os schemas
pydantic, e o pydantic não reconhece `FakeDate` → `PydanticSchemaGenerationError`. Como esse
import é preguiçoso (só na primeira request), sem aquecer a urlconf **antes** do primeiro
congelamento ele cai dentro dele. Pior: o import falho deixa `suap.api` pela metade e toda
request seguinte falha com `ConfigError: Router@'' has already been attached`. O aquecimento
é uma linha (`get_resolver().url_patterns`), mas tem de vir antes.

**5. `live_server` força `transactional_db` → flush.** É a causa raiz de (1); ver
`djtools/e2e_fixtures.py:168-172`, que cita `pytest_django/fixtures.py:237,639` e
`django/test/testcases.py:1253`.

**6. `collectstatic` é desnecessário — mas `DJANGO_SETTINGS_MODULE=suap.settings_test` não
é.** `djtools/e2e_fixtures.py:36-39`: com `settings_test` o bundling do pipeline fica
desligado, os templates referenciam os arquivos-fonte e os finders os servem direto dos
`<app>/static/`. O detalhe traiçoeiro é que `PIPELINE_ENABLED = not DEBUG` é resolvido no
*import* (`pipeline/conf.py:10`), logo depende do **módulo de settings**, não do `DEBUG` em
runtime — que o pytest-django força para `False`. Há um assert que falha com mensagem
explícita (`djtools/e2e_fixtures.py:284-286`) e a explicação longa em
`suap/settings_test.py:46-54`. Sem isso: 404 em todo CSS/JS, jQuery não carrega, nenhum
widget interativo funciona.

**7. Postgres com `max_locks_per_transaction` alto.** `suap/settings_test.py:16-22`: o
schema completo é criado numa única transação e o default 64 estoura. O comando de Postgres
efêmero está lá (`-c max_locks_per_transaction=4096`).

**8. Não há flush entre testes — seeds idempotentes, estado mutável nunca compartilhado.**
Esta não estava na lista do ticket e é, pela evidência, a que um gerador erra primeiro. Três
consequências independentes, cada uma já paga em código:
   - **Seed dedicado em vez de compartilhado.** `almoxarifado/tests/e2e/conftest.py:106-118`
     cria o empenho `2019NE000777` só para a fixture, porque usar o `20193012RE` do seed
     fazia `test_entradas` consumir o saldo e quebrar quem rodasse depois
     (*"Compartilhar recurso mutável entre testes é dependência de ordem"*).
   - **Nada de `get_or_create` para estado consumível.** `requisicao_pendente`
     (`almoxarifado/tests/e2e/conftest.py:127-134`) cria uma requisição NOVA a cada teste:
     uma requisição atendida deixa de estar pendente.
   - **Limpar o que a run anterior deixou.** `_limpar_credito`
     (`edu/tests/e2e/conftest.py:296-308`) apaga a cadeia "Licenciatura em Geografia" antes
     de recriá-la, porque os nomes são fixos e a segunda execução falharia no cadastro.
   O mesmo motivo explica o `uuid4` nos nomes dos testes de cadastro
   (`almoxarifado/tests/e2e/test_cadastros.py:20`).

**9. Não rode a suíte e2e com `-n` (xdist).** `pytest-xdist` está instalado
(`pyproject.toml:118`) e a suíte unitária o usa, mas o job e2e do CI roda em processo único
(`.gitlab-ci.yml:169`). A cadeia 12→13→14 do edu depende de ordem de coleta
(`edu/tests/e2e/conftest.py:315-317`), e as fixtures session-scoped de seed seriam
instanciadas uma vez por worker.

**9b. Diagnosticar vermelho: três coisas antes de culpar o teste.** Medido em 31/07/2026,
diagnosticando os "10 vermelhos" do `edu` (#16979) — que não existiam.

- **`--maxfail=10` está no `addopts`** (`pyproject.toml:305`). A execução aborta na décima
  falha, então numa suíte grande você lê o **teto do runner** como se fosse a contagem de
  problemas: a primeira rodada do `edu` deu "10 failed, 35 passed" com 112 testes na suíte.
  Rode com `--maxfail=200` antes de tirar qualquer conclusão sobre quantos são.
- **Vermelho em branch desatualizada não é vermelho** — o simétrico da armadilha 13. A suíte
  depende de settings compartilhados (`suap/settings_test.py`), e uma correção de infra que
  entrou no `master` ontem transforma 10 telas de admin em 500 na branch que não a tem. Foi
  exatamente isso: sem `'DISABLE_SERVER_SIDE_CURSORS': True`, todo formulário que itera
  queryset por cursor devolve 500. Mescle o `master` **antes** de diagnosticar.
- **`Rótulos na tela: []` significa página sem formulário — quase sempre um 500**, não
  seletor errado. A mesma leitura vale para `Botões na tela: ['Share this traceback on a
  public website']`. É para isso que `rotulos_na_tela`/`ver_titulo` trazem diagnóstico na
  mensagem de falha.

Com as três, o `edu` foi de "10 vermelhos" a **112/112 verdes** sem tocar em nenhum teste.

**10. Ordem dos alvos de botão.** `djtools/e2e_ui.py:127-148`: submit vem antes de link, e
âncora com texto **exato** antes de âncora por `contains`. Sem isso, "Salvar" casa com
"Salvar em PDF" e o teste navega em vez de gravar. Já está resolvido em `Tela.botao` — a
armadilha é escrever o seletor à mão em vez de usar `clicar_botao`.

**11. `DJANGO_ALLOW_ASYNC_UNSAFE` tem de valer em import-time.** `djtools/e2e_fixtures.py:45-48`:
o loop greenlet do Playwright sync dispara o `@async_unsafe` do Django em
`ensure_connection`. Já resolvido pelo `os.environ.setdefault` no topo do módulo — só não
funciona se alguém tentar fazer isso numa fixture.

**12. `quadro()` abre escopo NOVO; `linha()`/`aba()`/`filtros()` compõem com o anterior.**
`linha()` (`e2e_ui.py:109`), `filtros()` (`:105`) e `aba()` (`:116`) montam o recorte como
`f'{self.escopo}//...'`, então encadear preserva o recorte anterior. `quadro()` (`:100`) não
faz isso — e **não pode**: as quatro formas de renderizar um quadro são unidas em
`({modulo}|{accordion}|{alertas}|{fieldset})`, e prefixar um caminho antes de um grupo
parentetizado não é XPath válido. É limitação por construção, não descuido. Consequência
prática para o gerador: `tela.quadro('A').quadro('B')` busca `B` na página inteira, não
dentro de `A`. Para aninhar quadro em quadro é preciso compor o XPath à mão. Nenhum dos 14
arquivos do edu precisa disso hoje.

**13. Verde em `--reuse-db` não é verde.** Medido na geração da suíte do `eventos` (!18635):
5/5 passaram num banco quente e o `--create-db` seguinte reprovou 2 — um banco reusado carrega
efeito colateral das execuções anteriores e escondia um 500 no arranque frio. **Antes de
declarar entrega, rode ao menos uma vez com `--create-db`**, que é a condição do CI. O inverso
também vale, e está em 9b: vermelho em branch desatualizada não é vermelho.

**14. `Tela.popup()` não espera o conteúdo.** Ele afirma que o `body` do iframe está visível — e
o body de um iframe recém-criado já está, vazio. Qualquer chamada de **leitura** logo depois
(`rotulos_na_tela`, `botoes_na_tela`) fotografa o documento vazio e devolve `[]`. Preenchimento
não sofre, porque cada campo tem `expect` com retry. Ancore com uma asserção com retry antes de
ler o popup.

**15. Salvar num popup exige sincronizar com o desfecho — e há DOIS desfechos.** O clique no
`Salvar` do fancybox retorna com a resposta ainda em voo; a asserção seguinte começa a contar
o próprio timeout no documento **antigo**, que nunca terá o banner. Foi a causa medida da
instabilidade de `edu/tests/e2e/test_01_diretoria.py` (#16990): em 3 de 6 falhas capturadas o
banner estava presente, único e **visível**, só que já depois dos 15s do `expect`.

Use `Tela.salvar_no_popup('Salvar')` (ou `esperar_desfecho_do_popup(page)`, no idioma de
`e2e_fixtures`) em vez de `clicar_botao` seguido de `sucesso`. A espera aceita **qualquer um
dos dois desfechos** que `djtools/static/djtools/fancybox/custom.js:1-9` define —
`close_fancybox` recarrega a página de trás, `close_fancybox_noreload` injeta a mensagem por
JS sem recarregar. Esperar só pelo reload penduraria os testes do segundo caminho.

Sintoma quando falta: falha intermitente que **muda de teste** a cada execução, porque quem
perde a corrida depende da carga da máquina. Se você está caçando uma flake que troca de lugar,
suspeite de corrida não sincronizada antes de suspeitar do teste.

**16. Diagnóstico de falha nunca pode levantar.** Todo coletor de evidência roda dentro de um
`except` — quando o teste já falhou — e página navegando é justamente o estado que produz a
falha. Uma leitura one-shot (`all_inner_texts`) nesse instante levanta
`Error: Execution context was destroyed` e **substitui** a `AssertionError` original: o
relatório perde a mensagem que dizia o que não aconteceu. `djtools/e2e_ui.py` e
`djtools/e2e_fixtures.py` já protegem os seus; qualquer coletor novo tem de fazer o mesmo.

**17. `ruff --unsafe-fixes` apaga cobertura do gate de rotas.** A UP032 reescreve
`'/comum/sala/visualizar/{}/'.format(pk)` como f-string, e uma f-string deixa no AST só o
pedaço `'/comum/sala/visualizar/'` — que não casa o padrão ancorado de
`bin/scripts/paridade_e2e.py`. Medido no `comum`: **cinco rotas saíram de "cobertas" para
"descobertas" só por rodar o lint**, com a suíte intacta e verde. O sintoma (gate regride
sem ninguém tocar em teste) não aponta para o lint. Defesa: a rota vai numa **constante de
módulo** e o teste chama `ROTA_SALA.format(pk)` — o `.format` incide sobre um nome, a UP032
não dispara, e a constante literal continua visível para o gate.

---

## (e) O que é ad-hoc e não deve virar receita

**1. O estilo Playwright cru do almoxarifado.** É o item mais importante desta seção.
`djtools/e2e_ui.py` foi criado no commit `e1535b7631` (o do edu), enquanto
`almoxarifado/tests/e2e/conftest.py` e seus testes vieram de `643104607e`, anterior. Nenhum
arquivo do almoxarifado importa `Tela` — verificado por grep em todo o repo: as 16
ocorrências de `djtools.e2e_ui` estão todas em `edu/tests/e2e/`. Logo o `page.locator(...)` /
`page.get_by_role(...)` do almoxarifado é **acidente cronológico, não alternativa de
desenho**. O gerador deve escrever no idioma `Tela`. (Corolário honesto: os arquivos do edu
misturam `Tela` com os helpers soltos de `e2e_fixtures` — 8 dos 14 importam ambos, e
`test_01_diretoria.py` usa os dois estilos em testes vizinhos. A mistura não é principiada;
o que a sustenta é a lacuna do `opcao=` descrita na seção 1.)

**2. `_Relogio.execute_steps`** (`edu/tests/e2e/conftest.py:84-88`). Existe só porque os
steps de `edu/features/steps/given.py` andam com a data chamando
`context.execute_steps('Quando a data do sistema for ...')`. É um adaptador para reusar o
replay do behave sem subir o behave. Módulo cujo seed não venha de `given.py` não precisa
disso — precisa apenas de `freeze_time` direto.

**3. `_fechar_2019_1()`** (`edu/tests/e2e/conftest.py:214-230`). Reparar o que a execução
anterior desfez pela interface (`test_06_encerramento` pode ter reaberto o período) é
sintoma de "sem flush + `--reuse-db`", não padrão a copiar. A lição generalizável é a
armadilha 8; este reparo específico é do edu.

**4. `_cpf_para` / dependência de `pycpfcnpj`** (`almoxarifado/tests/e2e/conftest.py:206-220`).
O raciocínio é bom e vale a pena repetir (CPF derivado de md5 da matrícula, estável entre
sessões, porque `hash()` de str é randomizado por processo e `gen.cpf()` é aleatório). Mas
como **código**, é específico de quem precisa cunhar servidores — o edu não precisa, porque
os CPFs vêm da tabela da feature 001. Classificação: helper reusável morando no lugar
errado. Enquanto for um módulo só, deixe onde está; se um terceiro módulo precisar, aí sim
sobe para `djtools`.

**5. `almoxarifado_a0`** (`almoxarifado/tests/e2e/conftest.py:77-124`), com o
`item.efetuar_entrada(...)` imperativo. É modelagem de domínio do almoxarifado (creditar
estoque mantendo invariante), não infra. O padrão generalizável é apenas *"credite estado de
domínio pelo domínio, não por factory crua, quando houver invariante"*.

**6. `setor_livre`** (`edu/tests/e2e/conftest.py:345-371`). A busca por setor **folha** cuja
sigla não seja substring de outra é específica do autocomplete de setor do edu, que exibe o
setor superior no rótulo. Generaliza como princípio (o rótulo do autocomplete pode conter
mais que o campo buscado — ver a armadilha do `opcao=`), não como código.

**7. `tests/e2e/test_login.py`.** Está declarado na própria docstring como
*"Spike/canário do harness"* (`:1`) — os dois testes existem para provar o desenho do
`_django_db_helper`, não para cobrir uma tela. Não replique o padrão por módulo. O análogo
legítimo é `edu/tests/e2e/test_smoke.py`, que é canário de uma **premissa do módulo** (o
relógio congelado vale na thread do servidor): módulo que introduza premissa de infra nova
merece um canário; módulo comum, não.

---

## Como rodar

```bash
# módulo isolado
TEST_DATABASE_NAME=test_suap_e2e DJANGO_SETTINGS_MODULE=suap.settings_test \
    uv run pytest <modulo>/tests/e2e --reuse-db

# tudo, como no CI (.gitlab-ci.yml:174)
pytest -m e2e --tracing=retain-on-failure --video=retain-on-failure --output=artifacts/e2e
```

A invocação é **sempre separada** da suíte unitária — o job `e2e` do CI e o `-m "not e2e"`
do `suap_check` garantem isso (`djtools/e2e_fixtures.py:30-33`).

## O que não deu para verificar

- Não executei a suíte (exige Postgres tunado + browsers do Playwright). Tudo acima é
  leitura de código; onde a fonte é uma docstring que relata medição (por exemplo a matriz
  de acesso de `almoxarifado/tests/e2e/test_permissoes.py:7-9`, ou o 403→200 do cache de
  permissão), está atribuído como tal e não reconfirmado.
- O comportamento de escopo do item 12 foi deduzido da leitura de `loc`/`_recorte`, não
  observado em execução.
- Li 2 das 18 `.feature` dos dois módulos (a 001 de cada). As regras de granularidade da
  seção 1 estão verificadas nessas duas e são consistentes com os 24 arquivos de teste, mas
  não foram checadas cenário a cenário nas 16 restantes.
