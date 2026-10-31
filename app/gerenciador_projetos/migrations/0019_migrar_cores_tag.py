# Generated manually

from django.db import migrations

MAPA_CORES = {
    '#f1c40f': 'warning',
    '#3498db': 'info',
    '#e67e22': 'extra',
    '#8e44ad': 'violet',
    '#2ecc71': 'success',
    '#e74c3c': 'error',
    'nenhum': 'none',
}

MAPA_CORES_REVERSO = {novo: antigo for antigo, novo in MAPA_CORES.items()}


def migrar_cores(apps, schema_editor):
    Tag = apps.get_model('gerenciador_projetos', 'Tag')
    for cor_antiga, cor_nova in MAPA_CORES.items():
        Tag.objects.filter(cor=cor_antiga).update(cor=cor_nova)


def reverter_cores(apps, schema_editor):
    Tag = apps.get_model('gerenciador_projetos', 'Tag')
    for cor_nova, cor_antiga in MAPA_CORES_REVERSO.items():
        Tag.objects.filter(cor=cor_nova).update(cor=cor_antiga)


class Migration(migrations.Migration):

    dependencies = [
        ('gerenciador_projetos', '0018_alter_tag_cor'),
    ]

    operations = [migrations.RunPython(migrar_cores, reverter_cores)]
