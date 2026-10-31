# Banco mockado do SUAP (`gerar_banco_mock`) — design

Data: 2026-09-19 · Branch: `claude/mock-suap-database-command-721157`

## Objetivo

Um management command que gera um **arquivo de dump** (`pg_dump -Fc`) de um banco SUAP
inteiro com dados fictícios, para o dev restaurar e desenvolver sem depender de dump de
produção nem de banco vazio.

Conteúdo do banco:

1. **Substrato** — o seed global do e2e (`djtools/new_tests/test_initial_data.py`:
   `loaddata initial_data`, `sync_permissions`, árvore organizacional, servidores base) +
   os seeds de sessão dos 12 módulos com suíte e2e. Dados coerentes, com usuários e papéis
   prontos para login.
2. **Volume sintético** — `model_bakery` em todos os models concretos dos apps SUAP.

Senha de **todos** os usuários no dump: `123`.

Fora de escopo: dump de produção anonimizado; rodar as suítes e2e para gerar dados "de
movimento"; deslocar datas para o presente.

## Evidência (spike de 2026-09-19)

| Checagem | Resultado |
|---|---|
| 12 seeds de sessão num banco só (`pytest --setup-only`, `-n 0`) | 0 erro, 2 min 23 s |
| `makemigrations --check` | sem mudanças (models = migrations) |
| `migrate --fake` no banco seedado | 12 s, 2327 migrations registradas; `migrate --plan` vazio |
| Tamanho do substrato | 175 MB |
| Colisão de matrícula entre módulos | nenhuma (faixas já separadas por módulo) |

O spike instanciou só a fixture de seed de entrada de cada módulo; as fixtures encadeadas do
`edu` (`seed_periodo_*` etc.) não foram exercitadas — ver "Stubs".

## Arquitetura

```
manage.py gerar_banco_mock [--saida suap_mock.dump] [--volume 20] [--semente 0]
                           [--sem-volume] [--modulos saude,frota] [--manter-banco]
  0. pré-checagens: pg_dump no PATH (major ≥ servidor); makemigrations --check
  1. filho: pytest -m mock -n 0 -p no:randomly --create-db --reuse-db <paths dos stubs>
  2. filho: manage.py gerar_banco_mock --etapa volume   (bakery + senhas)
  3. filho: manage.py migrate --fake
  4. pg_dump -Fc -f <saida>
  5. DROP DATABASE test_suap_mock_e2e   (pulado com --manter-banco)
```

**Isolamento do banco de dev.** O processo pai só orquestra e nunca abre conexão de escrita.
Todas as etapas que escrevem rodam em processos filhos com env explícito:
`DJANGO_SETTINGS_MODULE=suap.settings_test`, `TEST_DATABASE_NAME=test_suap_mock_e2e` (etapa 1)
e `DATABASE_NAME=test_suap_mock_e2e` (etapas 2–3). O nome contém `_e2e`, o que satisfaz a
guarda `_exige_banco_de_e2e` (`djtools/e2e_fixtures.py`). A etapa `volume` recusa rodar se o
banco conectado não terminar em `_mock_e2e`.
Os filhos também recebem `EMAIL_BACKEND=django.core.mail.backends.locmem.EmailBackend`: fora do
pytest, o `settings_test` herda o SMTP de `settings_base` (lido do env), e signals disparados
pelo bakery mandariam e-mail de verdade. E recebem `DATABASE_NAME=postgres` na etapa 1, porque
o `DATABASE_NAME` do `.env` do dev pode não existir no servidor de teste.

Antes de cada `subprocess.run` de etapa, o command dá `self.stdout.flush()`: sem isso a linha
`>>> etapa` do orquestrador sai *depois* da saída do próprio filho no terminal.

**Flags da etapa 1 que não são detalhe.** `--reuse-db` (senão o pytest-django dropa o banco
ao fim e não sobra nada para o dump); `--create-db` (parte sempre de banco novo); `-n 0` (com
xdist cada worker teria banco próprio `_gw<N>`); `-p no:randomly` (ordem estável).

**Schema.** Vem dos models (`--no-migrations` do addopts), não das migrations. A etapa 3
registra todas as migrations como aplicadas; a pré-checagem `makemigrations --check` garante
só que o **estado dos models** bate com elas — não enxerga objetos que só existem em `RunSQL`
(ex.: o trigger `check_identificador` de `documento_eletronico`/0029), que sem tratamento
ficariam ausentes do dump mesmo com `migrate --fake` marcando a migration como aplicada. A
etapa `volume` recria esses objetos reusando o inventário do `create_db`
(`OBJETOS_SQL_DAS_MIGRATIONS`/`criar_objetos_sql_das_migrations` em
`comum/management/commands/create_db.py`), a mesma função que o `create_db` usa para montar
um banco de dev do zero. Com drift de model, o command aborta antes de gastar tempo nos seeds.

## Componentes

| Arquivo | Responsabilidade |
|---|---|
| `djtools/management/commands/gerar_banco_mock.py` | Orquestração (etapas 0–5), parsing de flags, `--etapa volume` |
| `djtools/banco_mock.py` | `modelos_do_suap()`, `ordenar_modelos()`, `gerar_volume(modelos, n, semente) -> list[Resultado]`, `formatar_relatorio()`, `redefinir_senhas()`, `exigir_banco_mock()` |
| `<modulo>/tests/e2e/test_mock.py` (12) | Stub `@pytest.mark.mock` que só pede as fixtures de seed do módulo |
| `pyproject.toml` | Registro do marker `mock` |
| `conftest.py` (raiz) | `_deselecionar_mock`: tira os itens `mock` da coleta salvo quando a expressão `-m` cita `mock` |
| `docs/banco-mock.md` | Como gerar, restaurar, senha, data-base por módulo |
| `djtools/tests/test_banco_mock.py` | Testes (factories, sem `suap_data`/`light_data`) |
| `djtools/tests/test_gerar_banco_mock.py` | Testes da orquestração (`subprocess.run` trocado por monkeypatch, sem banco) |

### Stubs

Fixture de conftest é visível só no diretório dela, então não existe registry central: cada
módulo tem um stub no próprio `tests/e2e/` (mesmo idioma do marker `doc`). Módulo novo com
e2e entra criando o stub.

```python
@pytest.mark.mock
@pytest.mark.django_db(databases='__all__')
def test_mock(saude_seed): ...
```

Regra: o stub pede **todas** as fixtures de seed de sessão do módulo. Fixtures atuais:

| Módulo | Fixtures de seed | Data-base |
|---|---|---|
| ae | `ae_seed` | 03/06/2024 |
| almoxarifado | `almox_seed` | — |
| centralservicos | `centralservicos_seed` | — |
| documento_eletronico | `documento_seed`, `estado_documento_seed` | 08/01/2020 |
| edu | `edu_seed`, `seed_periodo_executado`, `seed_periodo_fechado`, `seed_matricula_renovada`, `seed_conceito`, `seed_de_rotas` | 10/03/2019 |
| erros | `erros_seed` | — |
| eventos | `eventos_seed` | — |
| frota | `frota_seed` | 25/11/2018 |
| pesquisa | `pesquisa_seed` | 01/01/2018 |
| processo_eletronico | `processo_seed` | — |
| remanejamento | `remanejamento_seed` | — |
| saude | `saude_seed` | 21/01/2019 |

Se alguma combinação não compuser (as do `edu` não foram exercitadas no spike), o stub fica
com a cadeia mais longa que passa, e a docstring do stub registra qual fixture ficou de fora
e por quê.

Os stubs ficam fora das runs normais por um hook no `conftest.py` raiz, que deseleciona
itens `mock` salvo quando a expressão `-m` cita `mock`. Não dá para usar `-m "not mock"` no
addopts: qualquer `-m` da linha de comando o sobrescreve (o `-m "not e2e"` do job unitário do
`suap_check`, o `-m e2e` do job e2e). E o stub não pode rodar no job e2e: pedir
`seed_periodo_fechado` antes da hora mudaria o estado para os testes do `edu`. O command
passa `-m mock`. `--modulos` restringe os paths de stub passados ao pytest.

### Volume sintético (`djtools/banco_mock.py`)

- **Models:** `apps.get_models()` dos apps em `APPS_SUAP`, concretos, `managed=True`, não
  proxy, não swapped, menos `EXCLUIDOS` (`frozenset` no módulo; cada item com o motivo em
  comentário): `comum.Configuracao` (singleton por chave, preenchida pelos seeds),
  `comum.Ano` (ano sorteado não é ano de verdade; o `Ano` corrente vem de
  `_preparar_substrato`), `rh.Setor` e `rh.UnidadeOrganizacional` (árvore organizacional dos
  seeds; linha solta sorteada aí a polui).
- **Ordem:** Kahn sobre as FKs/O2O obrigatórias (pai antes do filho). `graphlib` foi
  descartado porque levanta `CycleError` em qualquer ciclo; com Kahn, o que sobra preso em
  ciclo (e seus dependentes) vai para o fim, em ordem alfabética de `app_label.Model`.
- **FKs obrigatórias:** para cada instância, sorteia uma linha **existente** do alvo e a passa
  a `baker.make`. Só quando o alvo está vazio o bakery cria o pai, e o gerador de FK/O2O
  (`_reusar_ou_criar`) faz o mesmo em cascata: o pai criado pelo bakery reusa linha existente
  para as próprias FKs obrigatórias, então nunca cria um `EXCLUIDOS` (`Setor`/`UnidadeOrganizacional`/
  `Ano`/`Configuracao`) por baixo — se não sobrar alvo livre para um O2O (ex.: `pdp_ifrn.PDP.ano`,
  `portaria.ConfiguracaoSistemaPortaria.campus`), o gerador levanta erro e o model vai para o
  relatório em vez de fabricar um `EXCLUIDOS`. `_fill_optional=False`: FKs opcionais e M2M
  ficam vazios. Exceções: o `parent_link` de herança multi-tabela (ex.:
  `rh.PessoaFisica.pessoa_ptr`) nunca reusa linha, o bakery cria o pai; O2O só reusa alvo
  ainda não referenciado pelo model.
- **Models elegíveis:** também só os roteados para o banco `default`
  (`router.db_for_write`), o que tira os models LDAP.
- **Quantidade e colisão de unique:** `--volume N` por model (padrão 20). Cada instância num
  savepoint próprio (`transaction.atomic()`); se o `INSERT` colide em `unique`/`unique_together`
  (`UniqueViolation`), a instância é sorteada de novo, até `TENTATIVAS_UNIQUE` (5) vezes antes
  de desistir do model. Qualquer outra falha (ou o esgotamento das tentativas) encerra aquele
  model (as instâncias já criadas ficam) e vira a linha do relatório, sem repetir o mesmo erro
  N vezes.
- **Campos numéricos e texto:** inteiro (`IntegerField` e variantes) sorteia de 1 a 20; se o
  campo entra em algum `unique`/`unique_together`/`UniqueConstraint` do model, a faixa sobe
  para 1–32767 (cabe em qualquer coluna inteira) para reduzir colisão. `CharField`/`TextField`
  saem com até 8 caracteres — o padrão do bakery (encher `max_length`) estoura colunas que um
  `save()` compõe ou copia (`Categoria.codigo_completo`, `User.first_name` a partir de
  `PessoaFisica.nome`).
- **Campos custom do djtools:** o bakery escolhe gerador pela classe *exata* do campo, e o
  SUAP usa subclasses (`ForeignKeyPlus` 3724×, `CharFieldPlus` 1910×, …). `registrar_geradores`
  registra, para cada classe de campo desconhecida, o gerador do ancestral mais próximo que o
  bakery conhece. Campo sem ancestral conhecido faz o model falhar e ir para o relatório.
- **Usuário corrente:** durante o volume, o primeiro superusuário (ou, sem nenhum, o primeiro
  usuário) fica no threadlocal (`djtools/middleware/threadlocals.py`) como usuário logado —
  muitos `save()` leem `tl.get_user()`/`tl.get_request()` sem guarda (autoria, histórico,
  `CurrentUserField`) e quebrariam com `None`. O threadlocal anterior é restaurado ao final.
- **Reprodutibilidade:** `--semente S` (padrão 0) aplica `random.seed(S)` e `baker.seed(S)`.
  O sorteio de FK é feito em Python (`count` + offset em `order_by('pk')`), não com
  `ORDER BY random()`; o bakery usa o próprio `random` da stdlib para os valores dos campos.
- **Limite de tempo por model:** `TEMPO_MAXIMO_POR_MODELO` (60s) por model, via
  `execute_wrapper`: a exceção nasce só entre consultas SQL, nunca via SIGALRM (que cairia no
  meio do `Atomic.__exit__` e vazaria a instância) — controle de transação
  (`SAVEPOINT`/`RELEASE`/`ROLLBACK`) nunca é barrado, senão o próprio rollback do savepoint
  seria impedido. Isso significa que um laço em Python puro (`range(self.qtd)` de
  `CriacaoVagaRemanescente` e afins) ou uma única consulta lenta não são interrompidos por ele;
  a solução real seria rodar cada model num subprocesso com timeout — não feito aqui.
- **Relatório:** ao fim, tabela no stdout `model | criados/N | primeiro erro`, falhas primeiro.
  Falha de volume **não** aborta o dump. `--sem-volume` pula a etapa inteira.
- **Senhas:** depois do volume, `User._base_manager.update(password=<hash>)`, que cobre
  também os usuários criados pelo bakery. Roda mesmo com `--sem-volume`. O hash é gerado com
  `PBKDF2PasswordHasher` instanciado direto: o processo roda sob `suap.settings_test`, cujo
  `PASSWORD_HASHERS` é só MD5, e um hash MD5 no dump não autentica sob `suap.settings`
  (hasher padrão do Django).

## Erros

| Onde | Comportamento |
|---|---|
| `pg_dump` ausente ou major < servidor | `CommandError` antes de qualquer etapa |
| `makemigrations --check` ≠ 0 | `CommandError` antes de qualquer etapa |
| Etapa 1 (pytest) ≠ 0 | `CommandError`; banco **mantido**; a saída do pytest já saiu no terminal |
| Model do volume falha | Entra no relatório; segue |
| Etapa 3 ou 4 ≠ 0 | `CommandError`; banco **mantido** |
| Sucesso | Drop do banco, salvo `--manter-banco` |

## Uso pelo dev (vai para `docs/banco-mock.md`)

```bash
createdb suap_mock && pg_restore -d suap_mock --no-owner suap_mock.dump
```

Depois, `DATABASE_NAME=suap_mock` no `.env`. Login com qualquer matrícula dos `PAPEIS` do
conftest e2e do módulo, senha `123`.

**Datas:** o dump sai com a data-base de cada seed (tabela acima). Em 2026, prazos, períodos
letivos e agendas aparecem vencidos. Quem precisa da tela "viva" roda o `runserver` com o
relógio congelado na data-base do módulo. Decisão consciente: deslocar datas foi descartado
(offset por módulo quebra tabelas compartilhadas).

## Testes (`djtools/tests/test_banco_mock.py`)

Dados montados com factories (`auditoria/tests/factories.py` existentes + `UserFactory` nova em
`comum/tests/factories.py`), sem `suap_data`/`light_data`.

1. FK obrigatória reusa linha existente: com 3 `auditoria.TipoServico` de factory, gerar
   volume de `auditoria.Acao` não cria `TipoServico` novo. Com o alvo vazio, o bakery cria o pai.
2. Model que levanta exceção vai para o relatório com o erro, e os demais seguem criados.
3. `ordenar_models` põe pai antes de filho; ciclo não trava e vai para o fim.
4. `redefinir_senhas()`: `PBKDF2PasswordHasher().verify('123', user.password)` para todos os
   usuários. `check_password` não serve aqui, porque o settings de teste só conhece MD5.
5. `--etapa volume` recusa banco cujo nome não termina em `_mock_e2e`.
6. Orquestração com `subprocess.run` mockado: ordem das etapas; falha no pytest mantém o banco
   e não chama `pg_dump`; `--sem-volume` pula o bakery mas não as senhas.

Validação ponta a ponta: uma execução real do command, `pg_restore` num banco novo e login
com uma matrícula de papel e senha `123` via `runserver`.
