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
