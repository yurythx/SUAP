from django.db import migrations

REQUISICAO_INDEFERIDA = 3
REQUISICAO_CANCELADA = 5
ITEM_REJEITADO = 2
ITEM_CANCELADO = 4


def corrigir_situacao_itens(apps, schema_editor):
    """Itens de requisição indeferida ou cancelada que ficaram com a situação de antes do encerramento (ex.: Pendente)."""
    RequisicaoItem = apps.get_model('patrimonio', 'RequisicaoItem')
    RequisicaoItem.objects.filter(requisicao__status=REQUISICAO_INDEFERIDA).exclude(situacao=ITEM_REJEITADO).update(situacao=ITEM_REJEITADO)
    RequisicaoItem.objects.filter(requisicao__status=REQUISICAO_CANCELADA).exclude(situacao=ITEM_CANCELADO).update(situacao=ITEM_CANCELADO)


class Migration(migrations.Migration):
    dependencies = [
        ('patrimonio', '0015_alter_inventario_options'),
    ]

    operations = [
        migrations.RunPython(corrigir_situacao_itens, migrations.RunPython.noop),
    ]
