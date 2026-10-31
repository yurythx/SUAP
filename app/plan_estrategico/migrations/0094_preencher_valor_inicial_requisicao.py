from django.db import migrations
from django.db.models.functions import Coalesce


def preencher_valor_inicial(apps, schema_editor) -> None:
    """Preenche o valor inicial das requisições que ficaram sem ele.

    A migration 0083 copiou ``valor`` para ``valor_inicial``, mas as dotações provisórias criadas antes dela só
    tinham ``valor_provisorio``. Ao gerar a requisição definitiva, o tipo muda para dotação para empenho e o
    valor inicial nulo passa a ser usado no cálculo do saldo, quebrando o detalhamento da requisição.
    O valor inicial da provisória é o valor provisório, como já faz o cadastro atual.
    """
    RequisicaoDespesa = apps.get_model('plan_estrategico', 'RequisicaoDespesa')
    RequisicaoDespesa.objects.filter(valor_inicial__isnull=True).update(valor_inicial=Coalesce('valor_provisorio', 'valor'))


class Migration(migrations.Migration):
    dependencies = [
        ('plan_estrategico', '0093_alter_arquivometa_options'),
    ]

    operations = [
        migrations.RunPython(preencher_valor_inicial, migrations.RunPython.noop),
    ]
