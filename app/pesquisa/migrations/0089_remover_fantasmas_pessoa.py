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
