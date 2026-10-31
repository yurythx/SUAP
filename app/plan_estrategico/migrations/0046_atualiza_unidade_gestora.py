from django.db import migrations


def atualiza_unidade_gestora_tipo(apps, schema_editor):
    UnidadeGestora = apps.get_model('plan_estrategico', 'UnidadeGestora')

    UnidadeGestora.objects.filter(tipo='Pró-Reitoria').update(tipo='Gestor Sistêmico')
    UnidadeGestora.objects.filter(tipo='Diretoria Sistêmica').update(tipo='Gestor Sistêmico')


class Migration(migrations.Migration):

    dependencies = [
        ('plan_estrategico', '0045_alter_atividadeetapa_options_and_more'),
    ]

    operations = [
        migrations.RunPython(atualiza_unidade_gestora_tipo),
    ]
