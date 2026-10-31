# Generated manually

from django.db import migrations


def migrar_cor(apps, schema_editor):
    Tag = apps.get_model('gerenciador_projetos', 'Tag')
    Tag.objects.filter(cor='violet').update(cor='extra2')


def reverter_cor(apps, schema_editor):
    Tag = apps.get_model('gerenciador_projetos', 'Tag')
    Tag.objects.filter(cor='extra2').update(cor='violet')


class Migration(migrations.Migration):

    dependencies = [
        ('gerenciador_projetos', '0021_alter_tag_cor'),
    ]

    operations = [migrations.RunPython(migrar_cor, reverter_cor)]
