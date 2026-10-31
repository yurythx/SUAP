from django.db import migrations


class Migration(migrations.Migration):
    """Remove da origem os 8 campos migrados para comum.Vinculo (codemod S1-S4).

    Consolida os RemoveFields das antigas 0102-0105 numa única migration; o
    backfill (comum/0115) copia os valores para o Vinculo ANTES de qualquer
    remoção, então esta migration depende dele.
    """

    dependencies = [
        ('rh', '0101_pessoafisica_orcid'),
        # backfill copia Pessoa/PessoaFisica.<campo> -> Vinculo antes de remover da origem
        ('comum', '0115_backfill_campos_vinculo'),
    ]

    operations = [
        # Pessoa (base compartilhada com PessoaJuridica)
        migrations.RemoveField(model_name='pessoa', name='email'),
        migrations.RemoveField(model_name='pessoa', name='email_secundario'),
        migrations.RemoveField(model_name='pessoa', name='setores_adicionais'),
        migrations.RemoveField(model_name='pessoa', name='sistema_origem'),
        # PessoaFisica
        migrations.RemoveField(model_name='pessoafisica', name='deficiencia'),
        migrations.RemoveField(model_name='pessoafisica', name='foto'),
        migrations.RemoveField(model_name='pessoafisica', name='povo_indigena'),
        migrations.RemoveField(model_name='pessoafisica', name='raca'),
    ]
