from django.db import migrations


def revalidar_assinaturas(apps, schema_editor):
    # roda no deploy; usa o command (modelo real) para revalidar só as divergências de ordem.
    # ATENÇÃO: esta migração depende do command 'revalidar_assinaturas_progressao_docente';
    # não remova o command sem antes neutralizar/squashar esta migração (rebuild de DB do zero a executa).
    from django.core.management import call_command

    call_command('revalidar_assinaturas_progressao_docente')


class Migration(migrations.Migration):
    dependencies = [
        ('progressao_docente', '0041_avaliacao_preenchimento_expirado'),
    ]

    operations = [
        migrations.RunPython(revalidar_assinaturas, migrations.RunPython.noop),
    ]
