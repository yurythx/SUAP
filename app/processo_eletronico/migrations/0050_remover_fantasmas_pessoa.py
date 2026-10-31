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
