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
