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
