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
        ('documento_eletronico', '0040_alter_tipovinculodocumento_modo_uso'),
    ]

    # ponytail: irreversível de propósito (sem reverse_sql); a recuperação é o backup do runbook.
    operations = [
        migrations.RunSQL(
            ["SET LOCAL lock_timeout = '10s'"]
            + [f'ALTER TABLE IF EXISTS {tabela} DROP COLUMN IF EXISTS {coluna}' for tabela, coluna in COLUNAS]
            + [f'DROP TABLE IF EXISTS {tabela}' for tabela in TABELAS]
        ),
    ]
