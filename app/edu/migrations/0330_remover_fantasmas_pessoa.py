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
        ('edu', '0329_professordiario_diario_professor_uniq'),
    ]

    # ponytail: irreversível de propósito (sem reverse_sql); a recuperação é o backup do runbook.
    operations = [
        migrations.RunSQL(
            ["SET LOCAL lock_timeout = '10s'"]
            + [f'ALTER TABLE IF EXISTS {tabela} DROP COLUMN IF EXISTS {coluna}' for tabela, coluna in COLUNAS]
            + [f'DROP TABLE IF EXISTS {tabela}' for tabela in TABELAS]
        ),
    ]
