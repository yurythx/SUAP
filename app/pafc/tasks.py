import tempfile

from django.conf import settings
from django.template.defaultfilters import pluralize
from sentry_sdk import capture_exception

from djtools.assincrono import task


@task('Reprocessar bibliografia do PAFC')
def reprocessar_bibliografia_pafc(request, pafc, task=None):
    from pafc.models import MovimentacaoPAFC

    try:
        novos_ppc, atualizados_ppc, removidos_ppc = pafc.importar_bibliografia_do_ppc(task)
        novos_ultimo_pomc, atualizados_ultimo_pomc, removidos_ultimo_pomc = pafc.importar_bibliografia_do_pomc_anterior(task)

        total_novos = novos_ppc + novos_ultimo_pomc
        total_atualizados = atualizados_ppc + atualizados_ultimo_pomc
        total_removidos = removidos_ppc + removidos_ultimo_pomc

        str_criados = f'{total_novos} registro{pluralize(total_novos)} criado{pluralize(total_novos)}'
        str_atualizados = f'{total_atualizados} atualizado{pluralize(total_atualizados)}'
        str_removidos = f'{total_removidos} removido{pluralize(total_removidos)}'

        MovimentacaoPAFC.registrar_movimentacao(request.user, pafc, f'Bibliografia reprocessada ({str_criados}, {str_atualizados}, {str_removidos}).')

        return task.finalize('Bibliografia reprocessada com sucesso.')
    except Exception as e:
        if settings.DEBUG:
            raise e
        else:
            capture_exception(e)
        return task.finalize('Erro ao reprocessar bibliografia. Tente novamente mais tarde.', error=True)


@task('Gerar minuta de PAFC')
def gerar_minuta_pafc(request, pafc, task=None):
    from pafc import views

    task.start_progress(total=3)
    task.update_progress(1)
    pdf = views.minuta_pafc_pdf(request, pafc)
    task.update_progress(2)
    tmp = tempfile.NamedTemporaryFile(suffix='.pdf', mode='w+b', delete=False)
    tmp.write(pdf.content)
    tmp.close()
    task.update_progress(3)
    return task.finalize('Arquivo gerado com sucesso.', '..', file_path=tmp.name)
