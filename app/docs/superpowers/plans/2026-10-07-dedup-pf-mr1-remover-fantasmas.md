# Dedup PF — MR 1: remoção das colunas fantasmas — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apagar do banco as 100 colunas e 5 tabelas `through` que ainda apontam para `pessoa`/`pessoa_fisica`, mas que o state do Django já não conhece, para que o dedup (MR 2) possa apagar PFs perdedoras sem violar FK.

**Architecture:** Uma migration `RunSQL` por app dono da tabela, com a lista explícita (verificada contra a migration que tirou cada item do state) e `IF EXISTS`. Um teste DB-free garante que nenhum item da lista é coluna ou tabela viva de model. Saem dois métodos mortos que liam uma das colunas.

**Tech Stack:** Django 5.2 migrations (`RunSQL`), PostgreSQL 18, pytest.

**Spec:** `docs/superpowers/specs/2026-10-07-deduplicacao-pessoa-fisica-design.md`, seção 0.

## Global Constraints

- Multi-instituição: nada calibrado no IFRN; lista explícita, nunca calculada em tempo de execução.
- Uma migration por app dono; dependência = a última migration do próprio app.
- SQL: `SET LOCAL lock_timeout = '10s'`; `ALTER TABLE IF EXISTS <t> DROP COLUMN IF EXISTS <c>`; `DROP TABLE IF EXISTS <t>`. Precedente: `edu/migrations/0151_auto_20230831_0830.py`.
- Irreversível: sem `reverse_sql`.
- `financeiro_empenho`, `temp_rh_resposta` e `temp_enquete_cnat_resposta` **não** entram (nenhuma migration as cria).
- Os comandos `processo_eletronico_dump_pessoafisica` e `dump_documento_pessoafisica` **ficam**: `processo_eletronico/0032` e `documento_eletronico/0027` os chamam via `call_command`.
- Código, comentários e commits em pt-BR. Ruff: linha 150, aspas simples.
- Testes: `pytest`, nunca `manage.py test`. Banco de teste: Postgres com `max_locks_per_transaction` alto (ver `AGENTS.md`, `## Commands`).

---

### Task 1: Migrations de remoção + teste de segurança

**Files:**
- Create: as 12 migrations listadas no Step 3
- Create: `tests/test_remover_fantasmas_pessoa.py`

**Interfaces:**
- Produces: cada migration expõe as constantes de módulo `COLUNAS: list[tuple[str, str]]` e `TABELAS: list[str]`, lidas pelo teste.

- [ ] **Step 1: Escrever o teste (falha porque as migrations não existem)**

```python
"""Garante que as migrations de remoção de fantasmas só apagam o que nenhum model conhece."""

import importlib

import pytest
from django.apps import apps

MIGRACOES = [
    'ae.migrations.0047_remover_fantasmas_pessoa',
    'cnpq.migrations.0010_remover_fantasmas_pessoa',
    'convenios.migrations.0007_remover_fantasmas_pessoa',
    'documento_eletronico.migrations.0040_remover_fantasmas_pessoa',
    'edu.migrations.0328_remover_fantasmas_pessoa',
    'estacionamento.migrations.0003_remover_fantasmas_pessoa',
    'frota.migrations.0008_remover_fantasmas_pessoa',
    'pesquisa.migrations.0089_remover_fantasmas_pessoa',
    'ponto.migrations.0026_remover_fantasmas_pessoa',
    'processo_eletronico.migrations.0050_remover_fantasmas_pessoa',
    'projetos.migrations.0075_remover_fantasmas_pessoa',
    'saude.migrations.0039_remover_fantasmas_pessoa',
]


def _colunas_e_tabelas_vivas() -> tuple[set[tuple[str, str]], set[str]]:
    colunas, tabelas = set(), set()
    for model in apps.get_models(include_auto_created=True):
        tabelas.add(model._meta.db_table)
        for campo in model._meta.local_fields:
            colunas.add((model._meta.db_table, campo.column))
    return colunas, tabelas


@pytest.mark.parametrize('caminho', MIGRACOES)
def test_fantasma_nao_e_coluna_nem_tabela_viva(caminho: str) -> None:
    migracao = importlib.import_module(caminho)
    colunas_vivas, tabelas_vivas = _colunas_e_tabelas_vivas()

    assert not set(migracao.COLUNAS) & colunas_vivas
    assert not set(migracao.TABELAS) & tabelas_vivas
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest -q tests/test_remover_fantasmas_pessoa.py --create-db`
Expected: 12 FAIL com `ModuleNotFoundError`.

- [ ] **Step 3: Criar as 12 migrations**

Antes de criar, confira se o master ganhou migration nova em algum desses apps desde 07/10/2026 (`ls <app>/migrations | tail -1`). Se ganhou, ajuste o número do arquivo, a `dependencies`, a lista `MIGRACOES` do teste e a tabela do Step 1. Cada comentário de item cita a migration que o tirou do state.

#### `ae/migrations/0047_remover_fantasmas_pessoa.py`

```python
from django.db import migrations

# Referências a rh.Pessoa/rh.PessoaFisica que saíram do state em SeparateDatabaseAndState (a migration
# citada em cada item) e ficaram no banco como recuperação de falha. Apagadas antes da deduplicação
# de pessoas: docs/superpowers/specs/2026-10-07-deduplicacao-pessoa-fisica-design.md, seção 0.
COLUNAS = [
    ('ae_acaoeducativa', 'cancelada_por_id'),  # ae/0016_auto_20220713_0932
    ('ae_atividadediversa', 'cancelada_por_id'),  # ae/0016_auto_20220713_0932
    ('ae_demandaalunoatendida', 'responsavel_id'),  # ae/0016_auto_20220713_0932
    ('ae_documentoinscricaoaluno', 'cadastrado_por_id'),  # ae/0016_auto_20220713_0932
    ('ae_historicofaltasalimentacao', 'justificada_por_id'),  # ae/0016_auto_20220713_0932
    ('ae_historicosuspensoesalimentacao', 'liberado_por_id'),  # ae/0016_auto_20220713_0932
    ('ae_inscricao', 'parecer_autor_id'),  # ae/0016_auto_20220713_0932
    ('ae_participacaoalimentacao', 'liberado_por_id'),  # ae/0016_auto_20220713_0932
    ('ae_solicitacaorefeicaoaluno', 'avaliador_id'),  # ae/0016_auto_20220713_0932
]
TABELAS = []


class Migration(migrations.Migration):
    dependencies = [
        ('ae', '0046_participacaoalimentacao_qtd_faltas_alimentacao_and_more'),
    ]

    # ponytail: irreversível de propósito (sem reverse_sql); a recuperação é o backup do runbook.
    operations = [
        migrations.RunSQL(
            ["SET LOCAL lock_timeout = '10s'"]
            + [f'ALTER TABLE IF EXISTS {tabela} DROP COLUMN IF EXISTS {coluna}' for tabela, coluna in COLUNAS]
            + [f'DROP TABLE IF EXISTS {tabela}' for tabela in TABELAS]
        ),
    ]
```

#### `cnpq/migrations/0010_remover_fantasmas_pessoa.py`

```python
from django.db import migrations

# Referências a rh.Pessoa/rh.PessoaFisica que saíram do state em SeparateDatabaseAndState (a migration
# citada em cada item) e ficaram no banco como recuperação de falha. Apagadas antes da deduplicação
# de pessoas: docs/superpowers/specs/2026-10-07-deduplicacao-pessoa-fisica-design.md, seção 0.
COLUNAS = [
    ('cnpq_curriculovittaelattes', 'pessoa_fisica_id'),  # cnpq/0007_remove_curriculovittaelattes_pessoa_fisica
]
TABELAS = []


class Migration(migrations.Migration):
    dependencies = [
        ('cnpq', '0009_alter_classificacaoperiodico_options_and_more'),
    ]

    # ponytail: irreversível de propósito (sem reverse_sql); a recuperação é o backup do runbook.
    operations = [
        migrations.RunSQL(
            ["SET LOCAL lock_timeout = '10s'"]
            + [f'ALTER TABLE IF EXISTS {tabela} DROP COLUMN IF EXISTS {coluna}' for tabela, coluna in COLUNAS]
            + [f'DROP TABLE IF EXISTS {tabela}' for tabela in TABELAS]
        ),
    ]
```

#### `convenios/migrations/0007_remover_fantasmas_pessoa.py`

```python
from django.db import migrations

# Referências a rh.Pessoa/rh.PessoaFisica que saíram do state em SeparateDatabaseAndState (a migration
# citada em cada item) e ficaram no banco como recuperação de falha. Apagadas antes da deduplicação
# de pessoas: docs/superpowers/specs/2026-10-07-deduplicacao-pessoa-fisica-design.md, seção 0.
COLUNAS = [
    ('convenios_profissionalliberal', 'pessoa_id'),  # convenios/0004_auto_20220727_1137
]
TABELAS = []


class Migration(migrations.Migration):
    dependencies = [
        ('convenios', '0006_auto_20241029_1344'),
    ]

    # ponytail: irreversível de propósito (sem reverse_sql); a recuperação é o backup do runbook.
    operations = [
        migrations.RunSQL(
            ["SET LOCAL lock_timeout = '10s'"]
            + [f'ALTER TABLE IF EXISTS {tabela} DROP COLUMN IF EXISTS {coluna}' for tabela, coluna in COLUNAS]
            + [f'DROP TABLE IF EXISTS {tabela}' for tabela in TABELAS]
        ),
    ]
```

#### `documento_eletronico/migrations/0040_remover_fantasmas_pessoa.py`

```python
from django.db import migrations

# Referências a rh.Pessoa/rh.PessoaFisica que saíram do state em SeparateDatabaseAndState (a migration
# citada em cada item) e ficaram no banco como recuperação de falha. Apagadas antes da deduplicação
# de pessoas: docs/superpowers/specs/2026-10-07-deduplicacao-pessoa-fisica-design.md, seção 0.
COLUNAS = [
    ('documento_eletronico_assinatura', 'pessoa_id'),  # documento_eletronico/0028_auto_20230523_1605
    ('documento_eletronico_compartilhamentodocumentodigitalizadop7c65', 'pessoa_permitida_id'),  # documento_eletronico/0028_auto_20230523_1605
    ('documento_eletronico_compartilhamentodocumentopessoa', 'pessoa_permitida_id'),  # documento_eletronico/0028_auto_20230523_1605
    ('documento_eletronico_compartilhamentosetorpessoa', 'pessoa_permitida_id'),  # documento_eletronico/0028_auto_20230523_1605
    ('documento_eletronico_documentodigitalizado', 'dono_documento_pessoa_id'),  # documento_eletronico/0028_auto_20230523_1605
    ('documento_eletronico_documentodigitalizado_interessados', 'pessoa_id'),  # documento_eletronico/0028_auto_20230523_1605
    ('documento_eletronico_documentotexto_interessados', 'pessoa_id'),  # documento_eletronico/0028_auto_20230523_1605
    ('documento_eletronico_solicitacaoassinatura', 'solicitado_pessoa_id'),  # documento_eletronico/0028_auto_20230523_1605
    ('documento_eletronico_solicitacaocompartilhamentodocumentodifd0c', 'pessoa_solicitante_id'),  # documento_eletronico/0028_auto_20230523_1605
    ('documento_eletronico_solicitacaorevisao', 'avaliador_pessoa_id'),  # documento_eletronico/0028_auto_20230523_1605
    ('documento_eletronico_solicitacaorevisao', 'revisor_pessoa_id'),  # documento_eletronico/0028_auto_20230523_1605
]
TABELAS = []


class Migration(migrations.Migration):
    dependencies = [
        ('documento_eletronico', '0039_remover_assinaturadigital'),
    ]

    # ponytail: irreversível de propósito (sem reverse_sql); a recuperação é o backup do runbook.
    operations = [
        migrations.RunSQL(
            ["SET LOCAL lock_timeout = '10s'"]
            + [f'ALTER TABLE IF EXISTS {tabela} DROP COLUMN IF EXISTS {coluna}' for tabela, coluna in COLUNAS]
            + [f'DROP TABLE IF EXISTS {tabela}' for tabela in TABELAS]
        ),
    ]
```

#### `edu/migrations/0328_remover_fantasmas_pessoa.py`

```python
from django.db import migrations

# Referências a rh.Pessoa/rh.PessoaFisica que saíram do state em SeparateDatabaseAndState (a migration
# citada em cada item) e ficaram no banco como recuperação de falha. Apagadas antes da deduplicação
# de pessoas: docs/superpowers/specs/2026-10-07-deduplicacao-pessoa-fisica-design.md, seção 0.
COLUNAS = [
    ('edu_assinaturaataeletronica', 'pessoa_fisica_remover_id'),  # edu/0145_auto_20230824_1022
    ('edu_projetofinal', 'examinador_externo_remover_id'),  # edu/0145_auto_20230824_1022
    ('edu_projetofinal', 'examinador_interno_remover_id'),  # edu/0145_auto_20230824_1022
    ('edu_projetofinal', 'suplente_externo_remover_id'),  # edu/0145_auto_20230824_1022
    ('edu_projetofinal', 'suplente_interno_remover_id'),  # edu/0145_auto_20230824_1022
    ('edu_projetofinal', 'terceiro_examinador_remover_id'),  # edu/0145_auto_20230824_1022
    ('edu_projetofinal', 'terceiro_suplente_remover_id'),  # edu/0145_auto_20230824_1022
    ('edu_registroemissaodiploma', 'dirigente_maximo_remover_id'),  # edu/0145_auto_20230824_1022
    ('edu_registroemissaodiploma', 'responsavel_emissao_remover_id'),  # edu/0145_auto_20230824_1022
    ('edu_registroemissaodiploma', 'responsavel_registro_remover_id'),  # edu/0145_auto_20230824_1022
]
TABELAS = []


class Migration(migrations.Migration):
    dependencies = [
        ('edu', '0326_abonofaltas_data_avaliacao'),
    ]

    # ponytail: irreversível de propósito (sem reverse_sql); a recuperação é o backup do runbook.
    operations = [
        migrations.RunSQL(
            ["SET LOCAL lock_timeout = '10s'"]
            + [f'ALTER TABLE IF EXISTS {tabela} DROP COLUMN IF EXISTS {coluna}' for tabela, coluna in COLUNAS]
            + [f'DROP TABLE IF EXISTS {tabela}' for tabela in TABELAS]
        ),
    ]
```

#### `estacionamento/migrations/0003_remover_fantasmas_pessoa.py`

```python
from django.db import migrations

# Referências a rh.Pessoa/rh.PessoaFisica que saíram do state em SeparateDatabaseAndState (a migration
# citada em cada item) e ficaram no banco como recuperação de falha. Apagadas antes da deduplicação
# de pessoas: docs/superpowers/specs/2026-10-07-deduplicacao-pessoa-fisica-design.md, seção 0.
COLUNAS = []
TABELAS = [
    'estacionamento_veiculo_condutores',  # estacionamento/0002_remove_veiculo_condutores
]


class Migration(migrations.Migration):
    dependencies = [
        ('estacionamento', '0002_remove_veiculo_condutores'),
    ]

    # ponytail: irreversível de propósito (sem reverse_sql); a recuperação é o backup do runbook.
    operations = [
        migrations.RunSQL(
            ["SET LOCAL lock_timeout = '10s'"]
            + [f'ALTER TABLE IF EXISTS {tabela} DROP COLUMN IF EXISTS {coluna}' for tabela, coluna in COLUNAS]
            + [f'DROP TABLE IF EXISTS {tabela}' for tabela in TABELAS]
        ),
    ]
```

#### `frota/migrations/0008_remover_fantasmas_pessoa.py`

```python
from django.db import migrations

# Referências a rh.Pessoa/rh.PessoaFisica que saíram do state em SeparateDatabaseAndState (a migration
# citada em cada item) e ficaram no banco como recuperação de falha. Apagadas antes da deduplicação
# de pessoas: docs/superpowers/specs/2026-10-07-deduplicacao-pessoa-fisica-design.md, seção 0.
COLUNAS = [
    ('frota_viagem', 'motorista_id'),  # frota/0003_remove_viagem_motorista
]
TABELAS = []


class Migration(migrations.Migration):
    dependencies = [
        ('frota', '0007_viatura_prazo_revisao_viatura_quantidade_km_revisao'),
    ]

    # ponytail: irreversível de propósito (sem reverse_sql); a recuperação é o backup do runbook.
    operations = [
        migrations.RunSQL(
            ["SET LOCAL lock_timeout = '10s'"]
            + [f'ALTER TABLE IF EXISTS {tabela} DROP COLUMN IF EXISTS {coluna}' for tabela, coluna in COLUNAS]
            + [f'DROP TABLE IF EXISTS {tabela}' for tabela in TABELAS]
        ),
    ]
```

#### `pesquisa/migrations/0089_remover_fantasmas_pessoa.py`

```python
from django.db import migrations

# Referências a rh.Pessoa/rh.PessoaFisica que saíram do state em SeparateDatabaseAndState (a migration
# citada em cada item) e ficaram no banco como recuperação de falha. Apagadas antes da deduplicação
# de pessoas: docs/superpowers/specs/2026-10-07-deduplicacao-pessoa-fisica-design.md, seção 0.
COLUNAS = [
    ('pesquisa_avaliacao', 'avaliador_id'),  # pesquisa/0022_auto_20220714_1007
    ('pesquisa_avaliadorexterno', 'pessoa_fisica_id'),  # pesquisa/0022_auto_20220714_1007
    ('pesquisa_avaliadorindicado', 'pessoa_fisica_id'),  # pesquisa/0022_auto_20220714_1007
    ('pesquisa_edital', 'autorizado_por_id'),  # pesquisa/0022_auto_20220714_1007
    ('pesquisa_edital', 'cadastrado_por_id'),  # pesquisa/0022_auto_20220714_1007
    ('pesquisa_editalarquivo', 'autor_id'),  # pesquisa/0022_auto_20220714_1007
    ('pesquisa_obra', 'aceita_editora_realizada_por_id'),  # pesquisa/0022_auto_20220714_1007
    ('pesquisa_obra', 'autenticidade_verificada_por_id'),  # pesquisa/0022_auto_20220714_1007
    ('pesquisa_obra', 'cancelada_por_id'),  # pesquisa/0022_auto_20220714_1007
    ('pesquisa_obra', 'diagramacao_realizada_por_id'),  # pesquisa/0022_auto_20220714_1007
    ('pesquisa_obra', 'julgamento_conselho_realizado_por_id'),  # pesquisa/0022_auto_20220714_1007
    ('pesquisa_obra', 'responsavel_id'),  # pesquisa/0022_auto_20220714_1007
    ('pesquisa_obra', 'revisao_realizada_por_id'),  # pesquisa/0022_auto_20220714_1007
    ('pesquisa_obra', 'submetido_por_id'),  # pesquisa/0022_auto_20220714_1007
    ('pesquisa_obra', 'termos_assinados_realizado_por_id'),  # pesquisa/0022_auto_20220714_1007
    ('pesquisa_parecerobra', 'parecer_realizado_por_id'),  # pesquisa/0022_auto_20220714_1007
    ('pesquisa_participacao', 'pessoa_id'),  # pesquisa/0022_auto_20220714_1007
    ('pesquisa_projeto', 'autor_pre_avaliacao_id'),  # pesquisa/0022_auto_20220714_1007
    ('pesquisa_projeto', 'coordenador_id'),  # pesquisa/0022_auto_20220714_1007
    ('pesquisa_projeto', 'supervisor_id'),  # pesquisa/0022_auto_20220714_1007
    ('pesquisa_projetoanexo', 'membro_equipe_id'),  # pesquisa/0022_auto_20220714_1007
    ('pesquisa_reconhecimentodiploma', 'requerente_id'),  # pesquisa/0047_remove_reconhecimentodiploma_requerente
]
TABELAS = [
    'pesquisa_comissaoeditalpesquisa_membros',  # pesquisa/0022_auto_20220714_1007
]


class Migration(migrations.Migration):
    dependencies = [
        ('pesquisa', '0088_corrigir_rpi_prefixo_software'),
    ]

    # ponytail: irreversível de propósito (sem reverse_sql); a recuperação é o backup do runbook.
    operations = [
        migrations.RunSQL(
            ["SET LOCAL lock_timeout = '10s'"]
            + [f'ALTER TABLE IF EXISTS {tabela} DROP COLUMN IF EXISTS {coluna}' for tabela, coluna in COLUNAS]
            + [f'DROP TABLE IF EXISTS {tabela}' for tabela in TABELAS]
        ),
    ]
```

#### `ponto/migrations/0026_remover_fantasmas_pessoa.py`

```python
from django.db import migrations

# Referências a rh.Pessoa/rh.PessoaFisica que saíram do state em SeparateDatabaseAndState (a migration
# citada em cada item) e ficaram no banco como recuperação de falha. Apagadas antes da deduplicação
# de pessoas: docs/superpowers/specs/2026-10-07-deduplicacao-pessoa-fisica-design.md, seção 0.
COLUNAS = [
    ('ponto_documentoanexo', 'pessoa_id'),  # ponto/0010_auto_20220525_1519
]
TABELAS = []


class Migration(migrations.Migration):
    dependencies = [
        ('ponto', '0025_solicitacaoabonoparcial_chefes_data_aplicacao_and_more'),
    ]

    # ponytail: irreversível de propósito (sem reverse_sql); a recuperação é o backup do runbook.
    operations = [
        migrations.RunSQL(
            ["SET LOCAL lock_timeout = '10s'"]
            + [f'ALTER TABLE IF EXISTS {tabela} DROP COLUMN IF EXISTS {coluna}' for tabela, coluna in COLUNAS]
            + [f'DROP TABLE IF EXISTS {tabela}' for tabela in TABELAS]
        ),
    ]
```

#### `processo_eletronico/migrations/0050_remover_fantasmas_pessoa.py`

```python
from django.db import migrations

# Referências a rh.Pessoa/rh.PessoaFisica que saíram do state em SeparateDatabaseAndState (a migration
# citada em cada item) e ficaram no banco como recuperação de falha. Apagadas antes da deduplicação
# de pessoas: docs/superpowers/specs/2026-10-07-deduplicacao-pessoa-fisica-design.md, seção 0.
COLUNAS = [
    ('processo_eletronico_comentarioprocesso', 'pessoa_id'),  # processo_eletronico/0033_auto_20221017_2041
    ('processo_eletronico_compartilhamentoprocessoeletronicolog', 'pessoa_permitida_id'),  # processo_eletronico/0033_auto_20221017_2041
    ('processo_eletronico_compartilhamentoprocessoeletronicopodercbef', 'pessoa_permitida_id'),  # processo_eletronico/0033_auto_20221017_2041
    ('processo_eletronico_compartilhamentoprocessoeletronicosetorcbc1', 'pessoa_permitida_id'),  # processo_eletronico/0033_auto_20221017_2041
    ('processo_eletronico_processo_acompanhantes_processo', 'pessoa_id'),  # processo_eletronico/0033_auto_20221017_2041
    ('processo_eletronico_processo_interessados', 'pessoa_id'),  # processo_eletronico/0033_auto_20221017_2041
    ('processo_eletronico_requerimentodigitalizado_compartilhamento', 'pessoa_id'),  # processo_eletronico/0033_auto_20221017_2041
    ('processo_eletronico_solicitacaoassinaturacomanexacaoprocesso', 'pessoa_para_distribuir_id'),  # processo_eletronico/0033_auto_20221017_2041
    ('processo_eletronico_solicitacaociencia', 'pessoa_cancelada_por_id'),  # processo_eletronico/0033_auto_20221017_2041
    ('processo_eletronico_solicitacaociencia', 'solicitado_pessoa_id'),  # processo_eletronico/0033_auto_20221017_2041
    ('processo_eletronico_solicitacaodespacho', 'destinatario_pessoa_tramite_id'),  # processo_eletronico/0033_auto_20221017_2041
    ('processo_eletronico_solicitacaodespacho', 'remetente_pessoa_id'),  # processo_eletronico/0033_auto_20221017_2041
    ('processo_eletronico_solicitacaodespacho', 'solicitado_pessoa_id'),  # processo_eletronico/0033_auto_20221017_2041
    ('processo_eletronico_solicitacaojuntada', 'pessoa_cancelada_por_id'),  # processo_eletronico/0033_auto_20221017_2041
    ('processo_eletronico_solicitacaojuntada', 'solicitado_pessoa_id'),  # processo_eletronico/0033_auto_20221017_2041
    ('processo_eletronico_solicitacaojuntadadocumento', 'pessoa_avaliado_por_id'),  # processo_eletronico/0033_auto_20221017_2041
    ('processo_eletronico_tramite', 'destinatario_pessoa_id'),  # processo_eletronico/0033_auto_20221017_2041
    ('processo_eletronico_tramite', 'pessoa_atribuido_para_id'),  # processo_eletronico/0033_auto_20221017_2041
    ('processo_eletronico_tramite', 'pessoa_atribuido_por_id'),  # processo_eletronico/0033_auto_20221017_2041
    ('processo_eletronico_tramite', 'pessoa_recebimento_id'),  # processo_eletronico/0033_auto_20221017_2041
    ('processo_eletronico_tramite', 'remetente_pessoa_id'),  # processo_eletronico/0033_auto_20221017_2041
    ('processo_eletronico_tramitedistribuicao', 'pessoa_para_distribuir_id'),  # processo_eletronico/0033_auto_20221017_2041
]
TABELAS = []


class Migration(migrations.Migration):
    dependencies = [
        ('processo_eletronico', '0049_remover_parecer'),
    ]

    # ponytail: irreversível de propósito (sem reverse_sql); a recuperação é o backup do runbook.
    operations = [
        migrations.RunSQL(
            ["SET LOCAL lock_timeout = '10s'"]
            + [f'ALTER TABLE IF EXISTS {tabela} DROP COLUMN IF EXISTS {coluna}' for tabela, coluna in COLUNAS]
            + [f'DROP TABLE IF EXISTS {tabela}' for tabela in TABELAS]
        ),
    ]
```

#### `projetos/migrations/0075_remover_fantasmas_pessoa.py`

```python
from django.db import migrations

# Referências a rh.Pessoa/rh.PessoaFisica que saíram do state em SeparateDatabaseAndState (a migration
# citada em cada item) e ficaram no banco como recuperação de falha. Apagadas antes da deduplicação
# de pessoas: docs/superpowers/specs/2026-10-07-deduplicacao-pessoa-fisica-design.md, seção 0.
COLUNAS = [
    ('projetos_avaliacao', 'avaliador_id'),  # projetos/0021_auto_20220621_1149
    ('projetos_avaliacaoaluno', 'avaliado_por_id'),  # projetos/0021_auto_20220621_1149
    ('projetos_avaliadorexterno', 'pessoa_fisica_id'),  # projetos/0021_auto_20220621_1149
    ('projetos_avaliadorindicado', 'pessoa_fisica_id'),  # projetos/0021_auto_20220621_1149
    ('projetos_historicoalteracaoperiodoprojeto', 'registrado_por_id'),  # projetos/0021_auto_20220621_1149
    ('projetos_itemavaliacao', 'responsavel_alteracao_id'),  # projetos/0021_auto_20220621_1149
    ('projetos_participacao', 'pessoa_id'),  # projetos/0021_auto_20220621_1149
    ('projetos_projeto', 'autor_avaliacao_id'),  # projetos/0021_auto_20220621_1149
    ('projetos_projeto', 'autor_pre_avaliacao_id'),  # projetos/0021_auto_20220621_1149
    ('projetos_projeto', 'coordenador_id'),  # projetos/0021_auto_20220621_1149
    ('projetos_projeto', 'monitor_id'),  # projetos/0021_auto_20220621_1149
    ('projetos_projetoanexo', 'membro_equipe_id'),  # projetos/0021_auto_20220621_1149
]
TABELAS = [
    'projetos_areatematica_pessoa_fisica',  # projetos/0021_auto_20220621_1149
    'projetos_comissaoedital_membros',  # projetos/0021_auto_20220621_1149
]


class Migration(migrations.Migration):
    dependencies = [
        ('projetos', '0074_projeto_finalizacao_sistemica_em_and_more'),
    ]

    # ponytail: irreversível de propósito (sem reverse_sql); a recuperação é o backup do runbook.
    operations = [
        migrations.RunSQL(
            ["SET LOCAL lock_timeout = '10s'"]
            + [f'ALTER TABLE IF EXISTS {tabela} DROP COLUMN IF EXISTS {coluna}' for tabela, coluna in COLUNAS]
            + [f'DROP TABLE IF EXISTS {tabela}' for tabela in TABELAS]
        ),
    ]
```

#### `saude/migrations/0039_remover_fantasmas_pessoa.py`

```python
from django.db import migrations

# Referências a rh.Pessoa/rh.PessoaFisica que saíram do state em SeparateDatabaseAndState (a migration
# citada em cada item) e ficaram no banco como recuperação de falha. Apagadas antes da deduplicação
# de pessoas: docs/superpowers/specs/2026-10-07-deduplicacao-pessoa-fisica-design.md, seção 0.
COLUNAS = [
    ('saude_anexopsicologia', 'cadastrado_por_id'),  # saude/0020_auto_20220608_0956
    ('saude_bloqueioatendimentosaude', 'paciente_id'),  # saude/0020_auto_20220608_0956
    ('saude_bloqueioatendimentosaude', 'profissional_id'),  # saude/0020_auto_20220608_0956
    ('saude_documentoprontuario', 'cadastrado_por_id'),  # saude/0020_auto_20220608_0956
    ('saude_horarioatendimento', 'cadastrado_por_id'),  # saude/0020_auto_20220608_0956
    ('saude_horarioatendimento', 'paciente_id'),  # saude/0020_auto_20220608_0956
    ('saude_odontograma', 'atendido_por_id'),  # saude/0020_auto_20220608_0956
    ('saude_prontuario', 'cadastrado_por_id'),  # saude/0020_auto_20220608_0956
    ('saude_prontuario', 'pessoa_fisica_id'),  # saude/0020_auto_20220608_0956
    ('saude_registroadministrativo', 'profissional_id'),  # saude/0020_auto_20220608_0956
]
TABELAS = [
    'saude_atividadegrupo_responsaveis',  # saude/0020_auto_20220608_0956
]


class Migration(migrations.Migration):
    dependencies = [
        ('saude', '0038_adiciona_unicidade_cartaovacinal_vacina'),
    ]

    # ponytail: irreversível de propósito (sem reverse_sql); a recuperação é o backup do runbook.
    operations = [
        migrations.RunSQL(
            ["SET LOCAL lock_timeout = '10s'"]
            + [f'ALTER TABLE IF EXISTS {tabela} DROP COLUMN IF EXISTS {coluna}' for tabela, coluna in COLUNAS]
            + [f'DROP TABLE IF EXISTS {tabela}' for tabela in TABELAS]
        ),
    ]
```

- [ ] **Step 4: Rodar o teste e ver passar**

Run: `DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest -q tests/test_remover_fantasmas_pessoa.py --reuse-db`
Expected: 12 passed.

- [ ] **Step 5: Conferir que o state não mudou**

Run: `DJANGO_SETTINGS_MODULE=suap.settings_test uv run python manage.py makemigrations --check --dry-run`
Expected: `No changes detected`. `RunSQL` não altera state; qualquer outra saída indica migration pendente alheia, a investigar antes de seguir.

- [ ] **Step 6: Commit**

```bash
git add */migrations/*_remover_fantasmas_pessoa.py tests/test_remover_fantasmas_pessoa.py
git commit -m "[comum] Removendo colunas fantasmas que apontam para pessoa"
```

### Task 2: Remover os métodos mortos que liam `pessoa_permitida_id`

`DocumentoTexto.obter_pessoas_podem_ler` e `obter_pessoas_podem_editar` (`documento_eletronico/models.py:638-658`) fazem `values_list('pessoa_permitida_id')` em `CompartilhamentoDocumentoPessoa`/`CompartilhamentoSetorPessoa`, que hoje só têm `vinculo_permitido`. Não têm chamador; se chamados, levantam `FieldError`.

**Files:**
- Modify: `documento_eletronico/models.py:638-658`

- [ ] **Step 1: Confirmar que não há chamador**

Run: `grep -rn "obter_pessoas_podem_ler\|obter_pessoas_podem_editar" --include='*.py' --include='*.html' .`
Expected: só as duas linhas `def` em `documento_eletronico/models.py`.

- [ ] **Step 2: Apagar os dois métodos inteiros**

Remover de `def obter_pessoas_podem_ler(self):` até o `return Pessoa.objects.filter(...) | ...` de `obter_pessoas_podem_editar`, inclusive.

- [ ] **Step 3: Conferir se o import de `Pessoa` ainda é usado**

Run: `grep -n "\bPessoa\b" documento_eletronico/models.py | grep -v "PessoaFisica\|PessoaJuridica\|Pessoa[A-Z]"`
Expected: se a única ocorrência restante for o import (`from rh.models import Pessoa, Servidor`), troque-o por `from rh.models import Servidor`. O `ruff check` aponta F401 se sobrar.

- [ ] **Step 4: Varredura de outras leituras ORM de colunas fantasmas**

Run:
```bash
for c in $(uv run python - <<'PY'
import importlib, sys
sys.path.insert(0, '.')
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'suap.settings_test'); django.setup()
for m in [
    'ae.migrations.0047_remover_fantasmas_pessoa',
    'cnpq.migrations.0010_remover_fantasmas_pessoa',
    'convenios.migrations.0007_remover_fantasmas_pessoa',
    'documento_eletronico.migrations.0040_remover_fantasmas_pessoa',
    'edu.migrations.0328_remover_fantasmas_pessoa',
    'estacionamento.migrations.0003_remover_fantasmas_pessoa',
    'frota.migrations.0008_remover_fantasmas_pessoa',
    'pesquisa.migrations.0089_remover_fantasmas_pessoa',
    'ponto.migrations.0026_remover_fantasmas_pessoa',
    'processo_eletronico.migrations.0050_remover_fantasmas_pessoa',
    'projetos.migrations.0075_remover_fantasmas_pessoa',
    'saude.migrations.0039_remover_fantasmas_pessoa',
]:
    for t, c in importlib.import_module(m).COLUNAS:
        print(c)
PY
); do grep -rnE "['\"]${c}['\"]|['\"]${c%_id}(__|['\"])" --include='*.py' . | grep -v "/migrations/\|/management/commands/processo_eletronico_dump_pessoafisica.py\|/management/commands/dump_documento_pessoafisica.py"; done | sort -u
```
Expected: cada ocorrência precisa ser de um **outro** model que tem um campo vivo com o mesmo nome (ex.: `vinculo_permitido` em outro model, `coordenador` de `etep`). Leitura de campo fantasma (como os dois métodos do Step 2) é apagada da mesma forma. Anote no MR as ocorrências conferidas.

- [ ] **Step 5: Lint e testes do app**

Run: `uv run ruff check documento_eletronico/models.py && DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest -q -n 3 documento_eletronico --reuse-db`
Expected: ruff sem erro; testes verdes.

- [ ] **Step 6: Commit**

```bash
git add documento_eletronico/models.py
git commit -m "[documento_eletronico] Removendo métodos mortos que liam pessoa_permitida_id"
```

### Task 3: Verificar as migrations num banco com fantasmas

A suíte roda com `--no-migrations` e o `gerar_banco_mock` é construído a partir dos models, então nenhum dos dois tem colunas fantasmas. A verificação real é num banco restaurado de produção ou homologação.

**Files:** nenhum.

- [ ] **Step 1: Ver o SQL gerado**

Run: `DJANGO_SETTINGS_MODULE=suap.settings_test uv run python manage.py sqlmigrate saude 0039`
Expected: `SET LOCAL lock_timeout = '10s'`, os `ALTER TABLE IF EXISTS saude_... DROP COLUMN IF EXISTS ...` e `DROP TABLE IF EXISTS saude_atividadegrupo_responsaveis`, dentro de `BEGIN`/`COMMIT`.

- [ ] **Step 2: `migrate` a partir de banco vazio (instituição nova)**

A ordem entre apps não é garantida. Num banco novo, as 12 migrations de drop não podem quebrar nenhuma migration histórica de **outro** app que leia uma coluna fantasma por SQL. Os `dump_*` chamados por `processo_eletronico/0032` e `documento_eletronico/0027` leem colunas do próprio app, e o drop vem numa migration posterior do mesmo app, então para eles a ordem está garantida.

Run:
```bash
docker exec suap-test-db psql -U postgres -c 'CREATE DATABASE suap_migrate_vazio'
DATABASE_PORT=5433 DATABASE_NAME=suap_migrate_vazio DJANGO_SETTINGS_MODULE=suap.settings_test uv run python manage.py migrate
docker exec suap-test-db psql -U postgres -c 'DROP DATABASE suap_migrate_vazio'
```
Expected: `migrate` completo sem erro (`settings_test` lê `DATABASE_NAME`). Se uma migration histórica de outro app quebrar por coluna inexistente, acrescente na migration de drop correspondente a dependência `('<app>', '<migration histórica>')`.

- [ ] **Step 3: Migrar uma cópia restaurada de prod/homologação**

Com um banco restaurado de prod (ex.: o `suap_dev` do container local, se for cópia recente) apontado por `DATABASE_NAME`/`DATABASE_PORT`:

Run: `DJANGO_SETTINGS_MODULE=suap.settings uv run python manage.py migrate`
Expected: as 12 migrations `*_remover_fantasmas_pessoa` aplicadas sem erro.

- [ ] **Step 4: Conferir o que sobrou no catálogo**

Run, no mesmo banco:
```sql
SELECT c.confrelid::regclass AS alvo, c.conrelid::regclass AS tabela, a.attname AS coluna
FROM pg_constraint c JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
WHERE c.contype = 'f' AND c.confrelid IN ('pessoa_fisica'::regclass, 'pessoa'::regclass)
ORDER BY 1, 2, 3;
```
Expected: só as 13 FKs que o ORM conhece (`comum_vinculo.pessoa_id`, `edu_aluno.pessoa_fisica_id`, `servidor.pessoa_fisica_id`, `comum_prestadorservico.pessoa_fisica_id`, `rh_pessoaexterna.pessoa_fisica_id`, `comum_contatoemergencia.pessoa_fisica_id`, `rh_biometria.pessoa_fisica_id`, `rh_biometriasolicitacao.pessoa_fisica_id`, `comum_pessoaendereco.pessoa_id`, `comum_pessoatelefone.pessoa_id`, `rh_pessoainfocomplementar.pessoa_id`, `pessoa_fisica.pessoa_ptr_id`, `pessoa_juridica.pessoa_ptr_id`), mais as tabelas fora de migration da instituição (no IFRN: `financeiro_empenho`, `temp_rh_resposta`, `temp_enquete_cnat_resposta`).

- [ ] **Step 5: Gate de CI local**

Run: `pre-commit run --from-ref origin/master --to-ref HEAD`
Expected: tudo `Passed`.

### Task 4: Abrir o MR

- [ ] **Step 1: Push e MR**

```bash
git push -u origin HEAD
REGISTRAR_TEMPO=True glab mr create --title "[comum] Remove colunas fantasmas que apontam para pessoa" --description "$(cat <<'MD'
# Descrição

## Sumário
Apaga do banco 100 colunas e 5 tabelas `through` que apontam para `pessoa`/`pessoa_fisica` mas saíram do state do Django em migrations `SeparateDatabaseAndState`. É o MR 1 da deduplicação de pessoas.

## Problema
O dedup (MR 2) apaga PFs duplicadas. As FKs fantasmas continuam no banco e bloqueiam o DELETE, e o ORM não as enxerga para reapontar.

## Alterações
- 12 migrations `RunSQL`, uma por app, com lista explícita e `IF EXISTS`; cada item cita a migration que o tirou do state. Irreversíveis: façam backup antes de atualizar.
- Teste DB-free garantindo que nenhum item é coluna/tabela viva.
- Remove `DocumentoTexto.obter_pessoas_podem_ler/editar`, mortos e quebrados.
- **Não** toca `financeiro_empenho` nem tabelas criadas à mão (`temp_*`).

## Refs
Spec: `docs/superpowers/specs/2026-10-07-deduplicacao-pessoa-fisica-design.md`, seção 0.
MD
)"
```
Expected: URL do MR na saída. Confira o `time_stats` do MR depois.
