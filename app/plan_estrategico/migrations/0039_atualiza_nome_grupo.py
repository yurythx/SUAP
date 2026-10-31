from django.db import migrations
from django.contrib.auth.models import Group


def atualizar_nome_grupo(apps, schema_editor):
    Group.objects.filter(name='Administrador de Planejamento Estrategico').update(name='Administrador de Planejamento Estratégico')
    Group.objects.filter(name='Gestor Estrategico Local').update(name='Gestor Estratégico Local')
    Group.objects.filter(name='Gestor Estrategico Sistemico').update(name='Gestor Estratégico Sistêmico')


def desfazer_nome_grupo(apps, schema_editor):
    Group.objects.filter(name='Administrador de Planejamento Estratégico').update(name='Administrador de Planejamento Estrategico')
    Group.objects.filter(name='Gestor Estratégico Local').update(name='Gestor Estratégico Local')
    Group.objects.filter(name='Gestor Estratégico Sistêmico').update(name='Gestor Estrategico Sistemico')


class Migration(migrations.Migration):

    dependencies = [
        ('plan_estrategico', '0038_auto_20211223_1521'),
    ]

    operations = [
        migrations.RunPython(atualizar_nome_grupo, desfazer_nome_grupo),
    ]
