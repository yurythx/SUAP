from django.db import migrations
import tqdm

def popula_prazo_atual(apps, schema_editor):
    SolicitacaoProvidencia = apps.get_model('auditoria', 'SolicitacaoProvidencia')
    for solicitacao in tqdm.tqdm(SolicitacaoProvidencia.objects.all()):
        # Se a última prorrogação não for nula, usa o prazo da última prorrogação
        prazo = solicitacao.ultima_prorrogacao.prazo if solicitacao.ultima_prorrogacao else solicitacao.prazo_atendimento
        solicitacao.prazo_atual = prazo
        solicitacao.save(update_fields=["prazo_atual"])


class Migration(migrations.Migration):

    dependencies = [
        ('auditoria', '0014_beneficios'),
    ]

    operations = [
        migrations.RunPython(popula_prazo_atual),
    ]
