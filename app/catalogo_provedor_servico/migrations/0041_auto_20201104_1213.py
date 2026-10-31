
import json
import tqdm
from django.db import migrations


def atualizar_dados(apps, schema):
    SolicitacaoEtapa = apps.get_model('catalogo_provedor_servico.SolicitacaoEtapa')
    for solicitacao_etapa in tqdm.tqdm(SolicitacaoEtapa.objects.all().order_by('id')):
        campos = json.loads(solicitacao_etapa.dados)
        for i, field in enumerate(campos['formulario']):
            if 'html' in field:
                campos['formulario'][i]['help_text'] = campos['formulario'][i].pop('html')
        solicitacao_etapa.dados = json.dumps(campos, indent=4)
        solicitacao_etapa.save()


class Migration(migrations.Migration):

    dependencies = [
        ('catalogo_provedor_servico', '0040_auto_20201015_1421'),
    ]

    operations = [
        migrations.RunPython(atualizar_dados)
    ]
