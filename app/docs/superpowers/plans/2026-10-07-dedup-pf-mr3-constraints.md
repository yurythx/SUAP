# Dedup PF — MR 3 (SUAP 4.0.0): constraints de documento (Release 2) — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Garantir no banco: `cpf` nulo ou único, `(pais_origem, passaporte)` único, `documento_identificador` não nulo e único, e país de origem obrigatório para quem não tem CPF (exceto documento sintético). Também passa a valer de fato o `UniqueConstraint(pessoa, api_origem)` de `PessoaInfoComplementar`.

**Architecture:** Uma migration do `rh`. Ela começa com uma pré-verificação só de leitura, que aborta com números e roteiro se a instituição ainda não rodou o `deduplicar_pessoas`, e depois altera os campos. A pré-verificação é uma função testável que recebe um cursor e não usa o ORM, porque é importada pela migration.

**Tech Stack:** Django 5.2 migrations, PostgreSQL 18, pytest.

**Spec:** `docs/superpowers/specs/2026-10-07-deduplicacao-pessoa-fisica-design.md`, seção 4.

**Pré-requisito:** MR 2 (`docs/superpowers/plans/2026-10-07-dedup-pf-mr2-comando-e-entrada.md`) numa release **anterior**, já instalada nas instituições. Este MR vai em release própria.

## Global Constraints

- A migration nunca mescla nada: só verifica e altera o schema.
- **Banco vazio/novo passa direto.** Isso vale para o CI (`--no-migrations`) e para uma instituição nova.
- Mensagem de erro em pt-BR com os números e o roteiro do runbook (`docs/operacoes/deduplicar-pessoas.md`).
- `db_index=True` sai de `cpf` e de `documento_identificador`, porque o índice único o substitui.
- Testes:
  - duplicatas só com a fixture `sem_unicidade_pessoa` (conftest raiz, MR 2);
  - rodar com `DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test TEST_DATABASE_NAME=test_suap_dedup uv run pytest …`.
- Código, comentários e commits em pt-BR. Complexidade ≤ 10 e tipos nas defs tocadas.

---

### Task 1: Pré-verificação

**Files:**
- Create: `rh/deduplicacao/verificacao.py`
- Test: `rh/tests/tasks/test_preverificacao_constraints.py`

**Interfaces:**
- Produces: `pendencias(cursor) -> dict[str, int]`, com as chaves `cpf_repetido`, `passaporte_repetido` (por país + passaporte), `documento_repetido`, `cpf_ou_passaporte_vazio`, `sem_documento`, `sem_cpf_sem_pais`, `info_complementar_repetida` e `deduplicacao_pendente`.

- [ ] **Step 1: Testes**

```python
import pytest
from django.db import connection

from comum.models import APIExterna
from rh.deduplicacao.verificacao import pendencias
from rh.models import DeduplicacaoPessoa, PessoaFisica, PessoaInfoComplementar
from rh.tests.factories import PessoaFisicaFactory

pytestmark = pytest.mark.usefixtures('sem_unicidade_pessoa')


def _pendencias() -> dict[str, int]:
    with connection.cursor() as cursor:
        return {chave: total for chave, total in pendencias(cursor).items() if total}


def test_base_deduplicada_nao_tem_pendencia() -> None:
    PessoaFisicaFactory(), PessoaFisicaFactory()

    assert _pendencias() == {}


def test_aponta_cada_tipo_de_pendencia() -> None:
    PessoaFisicaFactory(cpf='529.982.247-25'), PessoaFisicaFactory(cpf='529.982.247-25')
    sem = PessoaFisicaFactory()
    PessoaFisica.objects.filter(pk=sem.pk).update(cpf=None, documento_identificador=None)
    DeduplicacaoPessoa.objects.create(pf_id=1, acao=DeduplicacaoPessoa.ERRO)

    assert _pendencias() == {'cpf_repetido': 1, 'documento_repetido': 1, 'sem_documento': 1, 'deduplicacao_pendente': 1}


def test_sem_cpf_e_sem_pais_so_passa_com_sintetico() -> None:
    sintetica, sem_pais = PessoaFisicaFactory(), PessoaFisicaFactory()
    PessoaFisica.objects.filter(pk=sintetica.pk).update(cpf=None, documento_identificador='SEMDOC-1')
    PessoaFisica.objects.filter(pk=sem_pais.pk).update(cpf=None, passaporte='AB123456', documento_identificador='AB123456')

    assert _pendencias() == {'sem_cpf_sem_pais': 1}


def test_campo_descartado_nao_e_pendencia() -> None:
    DeduplicacaoPessoa.objects.create(pf_id=1, acao=DeduplicacaoPessoa.CAMPO_DESCARTADO)

    assert _pendencias() == {}


def test_info_complementar_repetida() -> None:
    api = APIExterna.objects.first() or pytest.skip('sem APIExterna no banco de teste')
    pessoa = PessoaFisicaFactory()
    PessoaInfoComplementar.objects.create(pessoa=pessoa, api_origem=api, informacoes={})
    PessoaInfoComplementar.objects.create(pessoa=pessoa, api_origem=api, informacoes={})

    assert _pendencias() == {'info_complementar_repetida': 1}
```

(Se `APIExterna` precisar de campos obrigatórios, crie-a no teste em vez do `skip`, conferindo o model em `comum/models.py`.)

- [ ] **Step 2: Rodar e ver falhar.** Expected: `ModuleNotFoundError: rh.deduplicacao.verificacao`.

- [ ] **Step 3: Implementar**

```python
"""Pré-verificação da Release 2 (constraints de documento). SQL puro: é importada pela migration rh/0110."""

from __future__ import annotations

CONSULTAS = {
    'cpf_repetido': 'SELECT count(*) FROM (SELECT cpf FROM pessoa_fisica WHERE cpf IS NOT NULL GROUP BY cpf HAVING count(*) > 1) g',
    'passaporte_repetido': (
        'SELECT count(*) FROM (SELECT pais_origem_id, passaporte FROM pessoa_fisica '
        'WHERE passaporte IS NOT NULL AND pais_origem_id IS NOT NULL GROUP BY 1, 2 HAVING count(*) > 1) g'
    ),
    'sem_cpf_sem_pais': (
        'SELECT count(*) FROM pessoa_fisica WHERE cpf IS NULL AND pais_origem_id IS NULL '
        "AND documento_identificador !~ '^(SEMDOC|CONFLITO|INVALIDO)-'"
    ),
    'documento_repetido': (
        'SELECT count(*) FROM (SELECT documento_identificador FROM pessoa_fisica '
        'WHERE documento_identificador IS NOT NULL GROUP BY documento_identificador HAVING count(*) > 1) g'
    ),
    'cpf_ou_passaporte_vazio': "SELECT count(*) FROM pessoa_fisica WHERE cpf = '' OR passaporte = ''",
    'sem_documento': "SELECT count(*) FROM pessoa_fisica WHERE documento_identificador IS NULL OR documento_identificador = ''",
    'info_complementar_repetida': (
        'SELECT count(*) FROM (SELECT pessoa_id, api_origem_id FROM rh_pessoainfocomplementar GROUP BY 1, 2 HAVING count(*) > 1) g'
    ),
    'deduplicacao_pendente': "SELECT count(*) FROM rh_deduplicacaopessoa WHERE aplicado_em IS NULL AND acao <> 'campo_descartado'",
}


def pendencias(cursor) -> dict[str, int]:
    totais = {}
    for chave, sql in CONSULTAS.items():
        cursor.execute(sql)
        totais[chave] = cursor.fetchone()[0]
    return totais
```

- [ ] **Step 4: Rodar e ver passar.** Mesmo comando. Expected: verde.

- [ ] **Step 5: Commit**

```bash
git add rh/deduplicacao/verificacao.py rh/tests/tasks/test_preverificacao_constraints.py
git commit -m "[rh] Pré-verificação das constraints de documento de pessoa"
```

### Task 2: Constraints e migration com trava

**Files:**
- Modify: `rh/models/pessoa/pessoa_fisica.py` (campos `cpf`, `passaporte`, `documento_identificador`)
- Modify: `rh/models/pessoa/info.py:24-27` (`Meta.constraints`)
- Create: `rh/migrations/0110_documento_pessoa_unico.py` (gerada + `RunPython`)

- [ ] **Step 1: Campos**

Em `rh/models/pessoa/pessoa_fisica.py`:

```python
    cpf = models.CharField(max_length=20, null=True, unique=True, verbose_name='CPF', blank=False)
    passaporte = models.CharFieldPlus(max_length=50, verbose_name='Nº do Passaporte', null=True, blank=True)
    # CPF, senão passaporte/país, senão sintético (SEMDOC-/CONFLITO-/INVALIDO-): ver rh/deduplicacao/documentos.py
    documento_identificador = models.CharFieldPlus(max_length=80, null=False, blank=False, unique=True)
```

e, no `Meta` de `PessoaFisica` (junto de `db_table`, `permissions` etc.):

```python
        constraints = [
            # passaporte só identifica junto com o país emissor
            models.UniqueConstraint(fields=['pais_origem', 'passaporte'], name='pessoa_fisica_pais_passaporte_unico'),
            # sem CPF, o país é obrigatório; documento sintético (legado sem documento) fica isento
            models.CheckConstraint(
                condition=Q(cpf__isnull=False) | Q(pais_origem__isnull=False) | Q(documento_identificador__regex=r'^(SEMDOC|CONFLITO|INVALIDO)-'),
                name='pessoa_fisica_sem_cpf_exige_pais',
            ),
        ]
```

(`from django.db.models import Q`; confira que `models.CheckConstraint`/`models.UniqueConstraint` chegam por `djtools.db.models`, senão importe de `django.db.models`). Teste do CHECK em `rh/tests/models/test_pessoa_fisica_documento.py`: uma PF com CPF e outra com passaporte e país salvam; um `update(cpf=None, pais_origem=None, documento_identificador='X')` levanta `IntegrityError`.

Em `rh/models/pessoa/info.py`, trocar a linha solta `UniqueConstraint(fields=['pessoa', 'api_origem'], name='unique_info_api_govbr')` por:

```python
        constraints = [models.UniqueConstraint(fields=['pessoa', 'api_origem'], name='unique_info_api_govbr')]
```

(confira que `models.UniqueConstraint` existe via `djtools.db.models`; se não existir, `from django.db.models import UniqueConstraint`).

- [ ] **Step 2: Gerar a migration e acrescentar a trava**

Run: `DJANGO_SETTINGS_MODULE=suap.settings_test uv run python manage.py makemigrations rh -n documento_pessoa_unico`
Expected: `rh/migrations/0110_documento_pessoa_unico.py` com `AlterField` de `cpf` e `documento_identificador`, 2 `AddConstraint` em `pessoafisica` (par país+passaporte e CHECK) e 1 `AddConstraint` em `pessoainfocomplementar`.

Editar o arquivo gerado: acrescentar no topo a função e, como **primeira** operação, o `RunPython`:

```python
def verificar_deduplicacao(apps, schema_editor):
    from rh.deduplicacao.verificacao import pendencias

    with schema_editor.connection.cursor() as cursor:
        achadas = {chave: total for chave, total in pendencias(cursor).items() if total}
    if achadas:
        resumo = ', '.join(f'{chave}={total}' for chave, total in achadas.items())
        raise RuntimeError(
            f'Deduplicação de pessoas pendente ({resumo}). O SUAP 4.0.0 exige a deduplicação feita (introduzida na 3.21.0): '
            'rode `python manage.py deduplicar_pessoas planejar`, `relatorio` e `aplicar` e repita o migrate. '
            'Roteiro: docs/operacoes/deduplicar-pessoas.md, seção "Instalou a Release 2 sem ter deduplicado".'
        )
```

```python
    dependencies = [
        ('rh', '0109_indice_pessoaexterna_pessoa_fisica'),
        # Release 1 (MR 1): colunas fantasmas apagadas ANTES da trava. Quem recebe as duas versões de uma vez tem o
        # migrate parado aqui com a Release 1 já aplicada, e o planejar (trava de catálogo) roda sem acusar fantasmas.
        # Runbook: "Instalou a Release 2 sem ter deduplicado".
        ('ae', '0047_remover_fantasmas_pessoa'),
        ('cnpq', '0010_remover_fantasmas_pessoa'),
        ('convenios', '0007_remover_fantasmas_pessoa'),
        ('documento_eletronico', '0041_remover_fantasmas_pessoa'),
        ('edu', '0328_remover_fantasmas_pessoa'),
        ('estacionamento', '0003_remover_fantasmas_pessoa'),
        ('frota', '0008_remover_fantasmas_pessoa'),
        ('pesquisa', '0089_remover_fantasmas_pessoa'),
        ('ponto', '0026_remover_fantasmas_pessoa'),
        ('processo_eletronico', '0050_remover_fantasmas_pessoa'),
        ('projetos', '0075_remover_fantasmas_pessoa'),
        ('saude', '0039_remover_fantasmas_pessoa'),
    ]

    operations = [
        migrations.RunPython(verificar_deduplicacao, migrations.RunPython.noop),
        # … operações geradas pelo makemigrations …
    ]
```

Confira os nomes contra `ls */migrations/*_remover_fantasmas_pessoa.py` no momento da implementação (renumerações por conflito com o master acontecem: a de `documento_eletronico` já virou 0041). Teste: `MigrationLoader` mostra cada uma das 12 como ancestral de `('rh', '0110_documento_pessoa_unico')`.

- [ ] **Step 3: Conferir a trava num banco com duplicata**

Num banco local de desenvolvimento que tenha o MR 2 migrado (ex.: `suap_mock`), **sem** rodar o `deduplicar_pessoas`:

Run: `DJANGO_SETTINGS_MODULE=suap.settings uv run python manage.py migrate rh 0110`
Expected: se a base tiver duplicata ou PF sem documento, `RuntimeError: Deduplicação de pessoas pendente (…)` e nada alterado. Depois rode `deduplicar_pessoas planejar` e `aplicar` e repita: a migration aplica.

Se o `suap_mock` não tiver duplicatas, crie duas PFs com o mesmo CPF via `manage.py shell` (`PessoaFisica.objects.filter(pk=…).update(cpf=…)`) antes de migrar.

- [ ] **Step 4: Commit**

```bash
git add rh/models/pessoa/pessoa_fisica.py rh/models/pessoa/info.py rh/migrations/0110_documento_pessoa_unico.py
git commit -m "[rh] CPF, passaporte e documento identificador únicos"
```

### Task 3: Testes que a UNIQUE quebra

O spike do MR 2 mediu, com estas constraints, 9 testes que quebram por UNIQUE. Destes, os 4 fluxos do `edu` são corrigidos pelo MR 2. Sobram os abaixo.

**Files:**
- Modify: `pnp/tests/tasks/test_matching_matriculas.py:33-38` (`criar_aluno`)
- Modify: `patrimonio/tests/views/test_migrador.py:410` (teste de CPF duplicado)
- Modify: `edu/tests/fluxos/conftest.py` e as 4 classes de fluxo (remover `com_cpf_unico`, agora redundante)

- [ ] **Step 1: Rodar e ver falhar**

Run: `… uv run pytest -q pnp/tests/tasks/test_matching_matriculas.py patrimonio/tests/views/test_migrador.py --create-db`
Expected: 5 FAIL com `duplicate key value violates unique constraint` em `pessoa_fisica_cpf…`.

- [ ] **Step 2: Mesma pessoa com vários alunos no `pnp`**

```python
def criar_aluno(nome: str, cpf: str, matricula: str, curso: CursoCampus) -> Aluno:
    pessoa_fisica, _ = PessoaFisica.objects.obter_ou_criar({'nome': nome, 'cpf': cpf}, Politica.PREENCHER)
    ano, _ = Ano.objects.get_or_create(ano=2024)
    situacao = SituacaoMatriculaFactory()
    return Aluno.objects.create(
        matricula=matricula, pessoa_fisica=pessoa_fisica, curso_campus=curso, ano_letivo=ano, periodo_letivo=1, situacao=situacao
    )
```

(import `from rh.deduplicacao.entrada import Politica`). É a realidade depois do dedup: um CPF, uma pessoa, vários alunos.

- [ ] **Step 3: Teste de CPF duplicado do migrador de patrimônio**

O teste `test_escolhe_sempre_a_mesma_pessoa_fisica_quando_o_cpf_esta_duplicado` cobre base legada com duplicata. Ele continua valendo para a instituição que ainda está na Release 1, então ganha a fixture:

```python
@pytest.mark.usefixtures('sem_unicidade_pessoa')
def test_escolhe_sempre_a_mesma_pessoa_fisica_quando_o_cpf_esta_duplicado(cenario):
```

e o docstring troca "A base não tem UNIQUE em cpf" por "Base legada, antes da deduplicação (Release 1), ainda pode ter CPF repetido".

- [ ] **Step 4: Remover a UNIQUE temporária dos fluxos do `edu`**

Apagar `edu/tests/fluxos/conftest.py` (só tinha `com_cpf_unico`) e o `@pytest.mark.usefixtures('com_cpf_unico')` das 4 classes. A UNIQUE real cobre agora o mesmo caso.

- [ ] **Step 5: Suíte inteira**

Run: `DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test TEST_DATABASE_NAME=test_suap_dedup uv run pytest -n 3 -q -m "not e2e and not doc" --maxfail=100000 --create-db`
Expected: mesmo resultado do master.

- [ ] **Step 6: e2e dos módulos tocados**

Run: `SUAP_CHECK=e2e SUAP_APPS=geral python manage.py suap_check`. O seed do e2e cria muitas pessoas, e a UNIQUE pode pegar seed que repete CPF.
Expected: verde. Seed que repete CPF passa a usar `obter_ou_criar` ou CPF único (`cpf_valido(n)`).

- [ ] **Step 7: Commit**

```bash
git add pnp patrimonio edu/tests/fluxos
git commit -m "[rh] Testes adequados à unicidade de documento de pessoa"
```

### Task 4: Release note e MR

- [ ] **Step 1: Release note**

Acrescentar ao runbook `docs/operacoes/deduplicar-pessoas.md` uma seção "Release 2". Ela diz que o `migrate` **para** com `Deduplicação de pessoas pendente (…)` enquanto o `deduplicar_pessoas aplicar` não terminar sem pendências, e que a instituição precisa voltar à Release 1 ou rodar o comando antes de seguir.

- [ ] **Step 2: Gate e MR**

Run: `pre-commit run --from-ref origin/master --to-ref HEAD`.

```bash
git push -u origin HEAD
REGISTRAR_TEMPO=True glab mr create --title "[rh] CPF, passaporte e documento identificador únicos" --description "<skill mr-format: Sumário, Problema, Alterações (constraints + trava), Refs (spec, MR 1, MR 2, runbook), aviso de que o migrate trava sem o deduplicar_pessoas, Changelog>"
```
