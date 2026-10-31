from django.shortcuts import get_object_or_404

from acervo_academico import tasks
from acervo_academico.forms import ProcessarRotinaForm
from acervo_academico.models import RotinaImportacao, ItemRotina
from django.urls import reverse

from djtools.utils import rtr, permission_required, httprr


@rtr()
@permission_required('acervo_academico.view_rotinaimportacao')
def visualizar_rotina(request, pk):
    title = f'Rotina de importação #{pk}'
    rotina = get_object_or_404(RotinaImportacao, pk=pk)
    url_admin_itemrotina = reverse('admin:acervo_academico_itemrotina_changelist')

    _status_a_exibir = [status for status in ItemRotina.STATUS_CHOICES if status[0] != ItemRotina.EM_PROCESSAMENTO]
    _detalhes_status = {
        # status: (icone, classe css)
        ItemRotina.AGUARDANDO_PROCESSAMENTO: ('hourglass-end', ''),
        ItemRotina.NA_FILA: ('tasks', 'warning'),
        ItemRotina.PROCESSADO: ('clipboard-check', 'success'),
        ItemRotina.FALHOU: ('exclamation-triangle', 'error'),
        ItemRotina.SIMULADO: ('flask', 'info'),
    }

    # formato do sumário:
    # {
    #     <campus_id: {"sigla": str, "total": int, "quantitativos": {<status>: {"icone": str, "classe": str, "display": str, "qtd": int}, [...] } },
    #     [...]
    # }
    quantitativos_por_campus = {}

    for quantitativo in rotina.get_quantitativo_de_itens_por_campus():
        # {'campus_id': 15, 'campus__sigla': 'PAR', 'status': 5, 'quantidade': 555}
        campus = quantitativo['campus_id']
        sigla_campus = quantitativo['campus__sigla']
        if campus not in quantitativos_por_campus:
            quantitativos_por_campus[campus] = {'sigla': sigla_campus, 'total': 0, 'quantitativos': {}}
            for status, display in _status_a_exibir:
                quantitativos_por_campus[campus]['quantitativos'][status] = {
                    'icone': _detalhes_status[status][0],
                    'classe': _detalhes_status[status][1],
                    'display': display,
                    'qtd': 0,
                }

        if quantitativo['status'] in quantitativos_por_campus[campus]['quantitativos']:
            quantitativos_por_campus[campus]['quantitativos'][quantitativo['status']]['qtd'] = quantitativo['quantidade']
            quantitativos_por_campus[campus]['total'] = quantitativos_por_campus[campus]['total'] + quantitativo['quantidade']

    return locals()


@rtr()
@permission_required('acervo_academico.change_rotinaimportacao, edu.add_arquivoaluno')
def processar_rotina(request, pk):
    rotina = get_object_or_404(RotinaImportacao, pk=pk)
    title = f'Processar {rotina}'
    if not rotina.pode_processar(request.user):
        return httprr(rotina.get_absolute_url(), 'Você não tem permissão para processar esta rotina.', 'error')

    ids_campi = request.GET['ids_campi'].split(',') if request.GET and 'ids_campi' in request.GET else None
    form = ProcessarRotinaForm(rotina, ids_campi, data=request.POST or None)
    if form.is_valid():
        return form.processar()

    return locals()


@rtr()
@permission_required('acervo_academico.change_rotinaimportacao')
def limpar_logs_rotina(request, pk):
    rotina = get_object_or_404(RotinaImportacao, pk=pk)
    rotina.logs.filter().delete()
    return httprr(rotina.get_absolute_url(), 'Logs apagados com sucesso.', 'success', close_popup=True)


@rtr()
@permission_required('acervo_academico.view_itemrotina')
def visualizar_item_rotina(request, pk):
    item_rotina = get_object_or_404(ItemRotina, pk=pk)
    title = f'Arquivo {item_rotina.nome_arquivo}'
    return locals()


@rtr()
@permission_required('acervo_academico.change_rotinaimportacao, edu.add_arquivoaluno')
def processar_item(request, pk):
    item_rotina = get_object_or_404(ItemRotina, pk=pk)
    return tasks.processar_item_rotina(item_rotina)
