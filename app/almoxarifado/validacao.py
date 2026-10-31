from datetime import datetime

from django.views.decorators.csrf import csrf_exempt

from almoxarifado.models import Empenho, EmpenhoConsumo, RequisicaoAlmoxUOMaterial, RequisicaoAlmoxUserMaterial
from djtools.utils import JsonResponse, str_to_dateBR
from patrimonio.models import EmpenhoPermanente


def is_blank(text):
    """
    Testa se o texto está em branco ou contém somente espaços
    """
    return len(text.strip()) == 0


@csrf_exempt
def req_pedido(request):
    if 'solicitante_hidden' in request.POST and is_blank(request.POST['solicitante_hidden']):
        return JsonResponse.invalid('O campo SOLICITANTE está inválido', 'solicitante')
    materiais_id = request.POST.getlist('itens_hidden')
    quantidades = request.POST.getlist('quantidades')
    for index in range(len(materiais_id)):
        if is_blank(materiais_id[index]):
            return JsonResponse.invalid('O campo MATERIAL está inválido', 'itens', index)
        if is_blank(quantidades[index]):
            return JsonResponse.invalid('O campo QTD está inválido', 'quantidades', index)
    return JsonResponse.valid()


@csrf_exempt
def requisicao_responder(request, requisicao_tipo):
    ids_requisicoes_material = request.POST.getlist('idRequisicoesMaterial')
    quantidades_aceitas = request.POST.getlist('quantidadesAceitas')
    if requisicao_tipo == 'uo':
        classe = RequisicaoAlmoxUOMaterial
    elif requisicao_tipo == 'user':
        classe = RequisicaoAlmoxUserMaterial
    for index in range(len(ids_requisicoes_material)):
        requisicao_material = classe.objects.get(id=ids_requisicoes_material[index])
        try:
            if is_blank(quantidades_aceitas[index]):
                return JsonResponse.invalid('A quantidade aceita está inválida', 'quantidadesAceitas', index)
            quantidade_aceita = int(quantidades_aceitas[index])
            if quantidade_aceita <= 0:
                return JsonResponse.invalid('A quantidade aceita está inválida', 'quantidadesAceitas', index)
            if requisicao_material.get_estoque() < quantidade_aceita:
                return JsonResponse.invalid('A quantidade aceita é maior que a qtd. em estoque', 'quantidadesAceitas', index)
        except IndexError:
            return JsonResponse.invalid('A quantidade aceita está inválida', 'quantidadesAceitas', index)
    return JsonResponse.valid()


def is_dateOK(text, msg):
    hoje = datetime.today()
    anoAtual = int(hoje.year)
    barras = str(text).split('-')
    if len(barras) == 3:
        dia = int(barras[2])
        mes = int(barras[1])
        ano = int(barras[0])
        if not (((dia > 0) and (dia < 32)) and ((mes > 0) and (mes < 13)) and ((ano >= 1996) and (ano <= anoAtual))):
            return 'O campo DATA' + msg + ' está inválido'
        elif ((ano % 4) == 0) and ((ano % 100) == 0) and ((ano % 400) == 0):
            if mes == 2:
                if dia > 29:
                    return 'O mês de fevereiro, do campo DATA' + msg + ', possui apenas 29 dias'
                else:
                    return 'OK'
            else:
                return 'OK'
        elif (ano % 100) != 0:
            if (ano % 4) == 0:
                if mes == 2:
                    if dia > 29:
                        return 'O mês de fevereiro, do campo DATA' + msg + ', possui apenas 29 dias'
                    else:
                        return 'OK'
                else:
                    return 'OK'
            elif mes == 2:
                if dia > 28:
                    return 'O mês de fevereiro, do campo DATA' + msg + ', possui apenas 28 dias'
                else:
                    return 'OK'
            else:
                return 'OK'
        elif mes == 2:
            if dia > 28:
                return 'O mês de fevereiro, do campo DATA' + msg + ', possui apenas 28 dias'
            else:
                return 'OK'
        else:
            return 'OK'
    else:
        return 'O campo DATA' + msg + ' está inválido'


@csrf_exempt
def entrada(request):
    # Validando data de entrada
    try:
        str_to_dateBR(request.POST['data_entrada'])
    except Exception as e:
        return JsonResponse.invalid(str(e), 'data_entrada')

    # COMPRA
    if is_blank(request.POST['empenho_hidden']):
        return JsonResponse.invalid('O campo EMPENHO está inválido', 'empenho')
    elif is_blank(request.POST['fornecedor_hidden']):
        return JsonResponse.invalid('O campo FORNECEDOR está vazio', 'vinculo_fornecedor')
    elif not Empenho.objects.filter(pk=request.POST['empenho_hidden'].upper()):
        return JsonResponse.invalid('O campo EMPENHO está inválido', 'empenho')
    if is_blank(request.POST['numero_nota']):
        return JsonResponse.invalid('O campo Nº NOTA FISCAL está inválido', 'numero_nota')
    validaData = is_dateOK(request.POST['data_nota'], ' NOTA FISCAL')

    if is_blank(request.POST['data_nota']) or len(request.POST['data_nota']) != 10:
        return JsonResponse.invalid('O campo DATA NOTA FISCAL está inválido', 'data_nota')
    elif validaData != 'OK':
        return JsonResponse.invalid(validaData, 'data_nota')
    empenho = Empenho.objects.get(id=request.POST['empenho_hidden'])
    if empenho.tipo_material.nome == 'consumo':
        empenhoitem = EmpenhoConsumo
    else:
        empenhoitem = EmpenhoPermanente
    if 'empenho_itens' not in request.POST:
        return JsonResponse.invalid('Pelo menos um item deve ser marcado')
    empenho_itens = request.POST.getlist('empenho_itens')
    qtds = request.POST.getlist('qtds')
    for index, id in enumerate(empenho_itens):
        if (
            index >= len(qtds)
            or not qtds[index].isdigit()
            or int(qtds[index]) == 0
            or empenhoitem.objects.get(id=int(id)).get_qtd_pendente() < int(qtds[index])
        ):
            return JsonResponse.invalid('O campo QUANTIDADE está inválido', 'qtds', index)
    return JsonResponse.valid()
