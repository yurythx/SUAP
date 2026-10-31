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
