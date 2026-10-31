from django.db import migrations
from django.conf import settings
from django.apps import apps
import tqdm, sys


def get_apps_suap(area = None):
    """Replicação intencional do método djtools.utils.get_apps_suap
    para fins de execução garantida no contexto das migrations."""
    modulos = []
    for app in apps.get_app_configs():
        if app.label in (*settings.INSTALLED_APPS_SUAP, 'djtools'):
            if not hasattr(app, 'icon'):
                app.icon = 'list'
            if (not area) or (getattr(app, 'area', 'Tecnologia da Informação') == area.get('area')):
                modulos.append(app)
    return sorted(modulos, key=lambda x: (x.verbose_name, getattr(x, 'area', '')))


def get_auto_apps_relacionadas(tag_nome: str) -> str:
    """Replicação intencional do método demandas.utils.get_auto_apps_relacionadas
    para fins de execução garantida no contexto das migrations."""
    return ','.join([app.label for app in get_apps_suap() if getattr(app, 'verbose_name', None) == tag_nome])


def popular_atributo_apps_relacionadas(apps, schema):
    bd = schema.connection.alias
    lote_tags = []
    lote_tamanho = 1000
    
    Tag_ = apps.get_model("demandas", "Tag")
    sys.stdout.write('\nAtualizando o atributo "apps_relacionadas" de todas as Tags\n')
    for tag_ in tqdm.tqdm(Tag_.objects.using(bd).all()):
        tag_.apps_relacionadas = get_auto_apps_relacionadas(tag_.nome)
        lote_tags.append(tag_)

        if len(lote_tags) == lote_tamanho:
            Tag_.objects.using(bd).bulk_update(
                lote_tags, 
                ["apps_relacionadas"]
            )
            lote_tags.clear()

    if lote_tags:
        Tag_.objects.using(bd).bulk_update(
            lote_tags, 
            ["apps_relacionadas"]
        )
        lote_tags.clear()


def rollback(apps, schema):
    Tag_ = apps.get_model("demandas", "Tag")
    Tag_.objects.all().update(apps_relacionadas='')    


class Migration(migrations.Migration):

    dependencies = [
        ('demandas', '0049_alter_tag_options_alter_tag_apps_relacionadas'),
    ]

    operations = [
        migrations.RunPython(
            popular_atributo_apps_relacionadas,
            reverse_code=rollback,
        )
    ]
