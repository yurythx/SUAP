from django.utils.timezone import now

from djtools.assincrono import task
from djtools.utils import XlsResponse
from suap import celery_app


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def atualizar_solicitacoes_expiradas(self):
    from auditoria.models import SolicitacaoProvidencia, SolicitacaoProvidenciaStatus

    hoje = now().date()
    qs = SolicitacaoProvidencia.objects.filter(
        status__in=[
            SolicitacaoProvidenciaStatus.STATUS_ESPERANDO,
            SolicitacaoProvidenciaStatus.STATUS_CIENTE,
        ]
    )
    for solicitacao in qs:
        if solicitacao.prazo_atual < hoje:
            solicitacao.expirar()
            solicitacao.save()


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def verificar_recomendacoes_expiradas(self):
    from auditoria.models.recomendacao import Recomendacao, RecomendacaoStatus

    qs = Recomendacao.objects.filter(status=RecomendacaoStatus.EM_MONITORAMENTO)
    for recomendacao in qs:
        recomendacao.verificar_expiracao()


@task('Exportar Relatório de Recomendações por setor para XLS')
def recomendacoes_por_setor_to_xls(registros, task=None):
    colunas = ['#', 'Setor', 'Campus', 'Total Monitoramento']
    rows = [colunas]
    contador = 1
    for registro in task.iterate(registros):
        row = [contador, registro['setor'], registro['campus'], registro['total_em_monitoramento']]
        rows.append(row)
        contador += 1
    #
    return XlsResponse(rows, processo=task)


@task('Exportar Relatório de Recomendações por setor para XLS')
def relatorio_raint_to_xls(registros, totais, task=None):
    rows = [list(registros[0].keys())]
    for registro in task.iterate(registros):
        rows.append(list(registro.values()))
    # Adiciona linha de totais
    rows.append(
        [
            'Total Geral',
            '',
            '',
            totais['total_registradas'],
            totais['total_em_monitoramento'],
            totais['total_atendidas'],
            totais['total_nao_atendidas'],
            totais['total_canceladas'],
            totais['total'],
        ]
    )
    return XlsResponse(rows, processo=task)


@task('Exportar Estoque de Monitoramentos por setor para XLS')
def estoque_monitoramentos_to_xls(registros, task=None):
    rows = [list(registros[0].keys())]
    for registro in task.iterate(registros):
        rows.append(list(registro.values()))
    return XlsResponse(rows, processo=task)


@task('Exportar Estoque de Recomendações para XLS')
def estoque_recomendacoes_to_xls(registros, task=None):
    rows = [list(registros[0].keys())]
    for registro in task.iterate(registros):
        rows.append(list(registro.values()))
    return XlsResponse(rows, processo=task)


@task('Exportar Estoque de Benefícios Financeiros para XLS')
def estoque_beneficios_financeiros_to_xls(registros, task=None):
    rows = [list(registros[0].keys())]
    for registro in task.iterate(registros):
        rows.append(list(registro.values()))
    return XlsResponse(rows, processo=task)


@task('Exportar Estoque de Benefícios Qualitativos para XLS')
def estoque_beneficios_qualitativos_to_xls(registros, task=None):
    rows = [list(registros[0].keys())]
    for registro in task.iterate(registros):
        rows.append(list(registro.values()))
    return XlsResponse(rows, processo=task)
