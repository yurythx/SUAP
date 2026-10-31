# Banco mockado do SUAP

`python manage.py gerar_banco_mock` gera um arquivo `pg_dump -Fc` com um banco SUAP inteiro
de dados fictícios, para desenvolver sem dump de produção.

## O que vem no banco

- **Substrato:** seed global do e2e (`djtools/new_tests/test_initial_data.py`) + os seeds de
  sessão dos módulos com suíte e2e (um stub `tests/e2e/test_mock.py` por módulo).
- **Volume sintético:** model-bakery em todos os models dos apps SUAP (`--volume` por model),
  reusando linhas existentes nas FKs obrigatórias. O relatório no fim da execução lista os
  models que falharam; falha de volume não impede o dump.
- **Senha de todos os usuários:** `123`.

## Gerar

Requisitos: Postgres com `max_locks_per_transaction` alto (o mesmo dos testes, ver
`AGENTS.md`), `pg_dump` com major ≥ o do servidor, Playwright instalado (alguns seeds
usam fixtures do e2e). O command usa as variáveis `DATABASE_HOST/PORT/USER/PASSWORD` do
ambiente, como `suap/settings_test.py`.

    DATABASE_HOST=localhost DATABASE_PORT=5433 DATABASE_USER=postgres DATABASE_PASSWORD=postgres \
      uv run python manage.py gerar_banco_mock --saida suap_mock.dump

Flags: `--volume N` (padrão 20), `--semente S` (padrão 0; mesma semente + mesmo código =
mesmo dump), `--sem-volume` (só substrato), `--modulos saude,frota`, `--manter-banco`
(não dropa `test_suap_mock_e2e`, útil para inspecionar). Nunca escreve no banco de
desenvolvimento: tudo roda em `test_suap_mock_e2e`.

## Restaurar

    createdb suap_mock
    pg_restore -d suap_mock --no-owner suap_mock.dump

Depois, `DATABASE_NAME=suap_mock` no `.env`. O schema já tem todas as migrations registradas
(`migrate` não aplica nada).

## Logins

Senha `123` para qualquer usuário. Matrículas por papel: dicionário `PAPEIS` (ou `USUARIOS`)
no `tests/e2e/conftest.py` de cada módulo; servidores do seed global:
`djtools/new_tests/test_initial_data.py`.

## Datas

Cada seed roda com o relógio congelado na data-base do módulo; o dump sai com essas datas e,
hoje, prazos e períodos letivos aparecem vencidos. Para ver a tela "viva", rode o
`runserver` com o relógio na data-base do módulo.

| Módulo | Data-base |
|---|---|
| ae | 03/06/2024 |
| documento_eletronico | 08/01/2020 |
| edu | 10/03/2019 |
| frota | 25/11/2018 |
| pesquisa | 01/01/2018 |
| saude | 21/01/2019 |

## Adicionar um módulo

Crie `<modulo>/tests/e2e/test_mock.py` pedindo as fixtures de seed de sessão do módulo
(copie de `saude/tests/e2e/test_mock.py`). O command acha o stub sozinho.

## Limites conhecidos

- O volume sintético não cobre todos os models: na última execução, 1912/2147 models saíram
  sem falha (os demais entram no relatório com o primeiro erro, sem abortar o dump).
- `rh.Setor`, `rh.UnidadeOrganizacional`, `comum.Ano` e `comum.Configuracao` ficam fora do
  volume (`EXCLUIDOS` em `djtools/banco_mock.py`): são a árvore organizacional, os anos e as
  configurações (singleton por chave) que os próprios seeds montam; uma linha solta sorteada
  aí poluiria esse substrato.
- Cada model tem um limite de tempo (`TEMPO_MAXIMO_POR_MODELO`, 60s) que só interrompe
  **entre** consultas SQL — um laço em Python puro ou uma única consulta lenta não são
  cortados por ele.
- O nome do banco (`test_suap_mock_e2e`) é fixo; duas execuções do command ao mesmo tempo no
  mesmo servidor Postgres colidem.
- Objetos SQL que só existem em migrations (`RunSQL`, ex.: o trigger `check_identificador` de
  `documento_eletronico`) não vêm do schema por models; a etapa `volume` os recria a partir do
  inventário do `create_db` (`comum/management/commands/create_db.py`,
  `criar_objetos_sql_das_migrations`).
