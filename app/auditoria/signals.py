from django.apps import apps
from django.db import transaction
from django.db.models.signals import m2m_changed, pre_save

Setor = apps.get_model(app_label='rh', model_name='Setor')
Recomendacao = apps.get_model(app_label='auditoria', model_name='Recomendacao')
Monitoramento = apps.get_model(app_label='auditoria', model_name='Monitoramento')
Posicionamento = apps.get_model(app_label='auditoria', model_name='Posicionamento')
Relatorio = apps.get_model(app_label='auditoria', model_name='Relatorio')
HistoricoRelatorioAuditoria = apps.get_model(app_label='auditoria', model_name='HistoricoRelatorioAuditoria')


def on_transaction_commit(func):
    def inner(*args, **kwargs):
        transaction.on_commit(lambda: func(*args, **kwargs))

    #
    return inner


def handle_recomendacao_unidades_change(sender, instance, action, reverse, model, pk_set, **kwargs):
    if action == 'pre_remove':
        # Verifica se as unidades a serem removidas estão em algum monitoramento iniciado
        for pk in pk_set:
            unidade = Setor.objects.suap_ativos().get(pk=pk)
            monitoramento = Monitoramento.objects.filter(unidade=unidade, recomendacao=instance).first()
            if monitoramento:
                if not monitoramento.registrado:
                    raise ValueError(f'Não é possível remover a unidade {unidade} porque existe um monitoramento iniciado para ela.')
                #
                monitoramento.delete()
    if action == 'pre_add':
        # Cria monitoramentos para as novas unidades
        for pk in pk_set:
            unidade = Setor.objects.suap_ativos().get(pk=pk)
            Monitoramento.objects.get_or_create(unidade=unidade, recomendacao=instance)


m2m_changed.connect(handle_recomendacao_unidades_change, sender=Recomendacao.unidades.through, dispatch_uid='handle_recomendacao_unidades_change')


def salvar_historico_relatorio(sender, instance, **kwargs):
    if instance.pk:
        relatorio_antigo = Relatorio.objects.get(pk=instance.pk)
        for field in instance._meta.fields:
            nome_campo = field.name
            valor_antigo = getattr(relatorio_antigo, nome_campo)
            valor_novo = getattr(instance, nome_campo)
            if valor_antigo != valor_novo:
                HistoricoRelatorioAuditoria.objects.create(
                    relatorio=instance,
                    campo_editado=nome_campo,
                    valor_antigo=valor_antigo,
                    valor_novo=valor_novo,
                    modificado_por=instance.modificado_por,
                )


pre_save.connect(salvar_historico_relatorio, sender=Relatorio, dispatch_uid='salvar_historico_relatorio')
