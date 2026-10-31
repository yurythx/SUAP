from datetime import datetime, timedelta

from django.shortcuts import get_object_or_404

from comum.utils import get_setor, get_todos_setores
from djtools import layout
from djtools.utils import httprr, permission_required, render, render_to_string, rtr
from protocolo import pdf, pdfa3
from protocolo.etiqueta import imprimir_etiqueta
from protocolo.forms import (
    ProcessoFormFinalizar,
    ProtocoloForm,
    TramiteFormEncaminharFactory,
    TramiteFormInformarRecebimentoExterno,
    TramiteFormReceber,
    TramiteFormRetornarProcessoParaAmbitoInterno,
)
from protocolo.models import Processo, Tramite
from rh.models import Setor


@layout.servicos_anonimos()
def servicos_anonimos(request):
    servicos_anonimos = []

    servicos_anonimos.append(
        {'categoria': 'Consultas gerais', 'url': '/protocolo/consulta_publica', 'icone': 'file-alt', 'titulo': 'Processos Físicos'}
    )

    return servicos_anonimos


@layout.quadro('Protocolo', icone='file', pode_esconder=True, session_cache=24 * 3600)
def index_quadros(quadro, request):
    if request.user.has_perm('protocolo.pode_tramitar_processo', ignore_superuser=True):
        vinculo = request.user.get_vinculo()
        setor = get_setor(request.user)
        if (vinculo.eh_servidor() or vinculo.eh_prestador()) and setor:
            meus_setores = (Setor.objects.suap_ativos().filter(pk=setor.pk) | vinculo.setores_adicionais.all()).distinct()
            qtd_processos_aguardando_recebimento = (
                Tramite.get_caixa_entrada(meus_setores)
                .filter(data_recebimento__isnull=True, data_encaminhamento__gte=datetime.today() - timedelta(90))
                .count()
            )

            if qtd_processos_aguardando_recebimento:
                quadro.add_item(
                    layout.ItemContador(
                        titulo='Processos a receber',
                        subtitulo='Dos últimos 90 dias',
                        qtd=qtd_processos_aguardando_recebimento,
                        url='/protocolo/caixa_entrada_saida/?tab=0&setor=todos',
                    )
                )
            qtd_processos_aguardando_encaminhamento = (
                Tramite.get_caixa_entrada(meus_setores)
                .filter(data_recebimento__isnull=False, data_encaminhamento__gte=datetime.today() - timedelta(90))
                .count()
            )
            if qtd_processos_aguardando_encaminhamento:
                quadro.add_item(
                    layout.ItemContador(
                        titulo='Processos a encaminhar',
                        subtitulo='Dos últimos 90 dias',
                        qtd=qtd_processos_aguardando_encaminhamento,
                        url='/protocolo/caixa_entrada_saida/?tab=1&setor=todos',
                    )
                )

    if request.user.has_group_cached('Cadastrador de processos', ignore_groups_if_superuser=False) and request.user.has_perm(
        'protocolo.add_processo', ignore_superuser=True
    ):
        quadro.add_item(layout.ItemAcessoRapido(titulo='Adicionar Processo', icone='plus', url='/admin/protocolo/processo/add/', classe='success'))

    return quadro


@rtr()
@permission_required('protocolo.pode_ver_processo')
def processo(request, processo_id):
    processo = get_object_or_404(Processo, id=processo_id)

    if processo.tem_vinculo_com_processo_eletronico:
        return httprr(processo.get_absolute_url())

    title = f'Processo {processo}'
    tramites_processo = processo.tramite_set.order_by('ordem')
    if not request.user.has_group_cached(['Tramitador de processos', 'Cadastrador de processos']):
        if not Processo.objects.filter(id=processo_id, interessado_documento=request.user.get_profile().cpf).exists():
            return httprr('..', 'Você não tem permissão para visualizar este processo.', 'error')

    if tramites_processo:
        ultimo_tramite = processo.get_ultimo_tramite()
        if get_setor():
            caixas = Tramite.get_caixas()
            if ultimo_tramite in caixas['entrada']:
                na_caixa_entrada = True
            if ultimo_tramite in caixas['saida'] or ultimo_tramite in Tramite.get_caixa_tramitacao_externa():
                na_caixa_saida = True

    if request.user.has_perm('protocolo.pode_gerar_capa'):
        link_capa_processo = f'/protocolo/capa_processo/{processo.id}/'
        link_capa_processo_a3 = f'/protocolo/capa_processo_a3/{processo.id}/'

    if processo.pode_editar_processo(request.user):
        link_processo_editar = f'/admin/protocolo/processo/{processo.id}/'

    if (processo.status == Processo.STATUS_FINALIZADO) and (ultimo_tramite.orgao_interno_recebimento in get_todos_setores(request.user)):
        link_processo_remover_finalizacao = f'/protocolo/processo_remover_finalizacao/{processo.id}'

    if processo.status in [Processo.STATUS_FINALIZADO, Processo.STATUS_ARQUIVADO]:
        processo_dados_finalizacao = {}
        processo_dados_finalizacao['ordem'] = len(tramites_processo) + 1
        processo_dados_finalizacao['setor'] = tramites_processo.order_by('-ordem')[0].orgao_interno_recebimento
        processo_dados_finalizacao['data_finalizacao'] = processo.data_finalizacao
        processo_dados_finalizacao['vinculo_finalizacao'] = processo.vinculo_finalizacao
        processo_dados_finalizacao['observacao_finalizacao'] = processo.observacao_finalizacao

    arquivos_processo = processo.arquivo_set.all()

    return locals()


@permission_required('protocolo.pode_gerar_capa, rsc.add_processorsc')
def processo_capa(request, processo_id):
    """Gera a capa PDF do Processo"""
    return pdf.imprimir_capa(Processo.objects.get(pk=processo_id))


@permission_required('protocolo.pode_gerar_capa')
def processo_capa_a3(request, processo_id):
    """Gera a capa PDF do Processo"""
    return pdfa3.imprimir_capa_a3(Processo.objects.get(pk=processo_id))


@rtr()
@permission_required('protocolo.pode_tramitar_processo')
def caixa_entrada_saida(request):
    title = 'Caixa de Entrada / Saída'
    setor = get_setor(request.user)
    if setor is not None:
        if request.GET.get('setor') is not None:
            try:
                setores_ids = int(request.GET.get('setor'))
            except Exception:
                setores_ids = None
            if setores_ids:
                setor_escolhido = Setor.objects.suap_ativos().get(pk=setores_ids)
                setores = Setor.objects.suap_ativos().filter(pk=setores_ids)  # deve ser queryset
            else:
                setores = Setor.objects.suap_ativos().filter(pk=setor.id)  # deve ser queryset
        else:
            setor_escolhido = Setor.objects.suap_ativos().get(pk=setor.id)
            setores = Setor.objects.suap_ativos().filter(pk=setor.id)

        caixas = Tramite.get_caixas(setores=setores)
        cx_entrada = caixas['entrada'].order_by('data_encaminhamento')
        cx_entrada_nao_recebidos = cx_entrada.filter(data_recebimento__isnull=True).order_by('data_encaminhamento')
        cx_entrada_recebidos = cx_entrada.filter(data_recebimento__isnull=False).order_by('data_encaminhamento')
        cx_saida = caixas['saida'].order_by('data_encaminhamento')
        setores_visiveis = get_todos_setores(request.user)
    return locals()


@rtr('protocolo/templates/caixa_tramitacao_externa.html')
@permission_required('protocolo.pode_tramitar_processo')
def caixa_tramitacao_externa(request):
    tramitacao_externa_list = Tramite.get_caixa_tramitacao_externa()
    return locals()


@rtr()
@permission_required('protocolo.pode_tramitar_processo')
def processo_receber(request, tramite_id):
    tramite = get_object_or_404(Tramite, id=tramite_id)
    title = f'Receber Processo {tramite.processo!s}'

    if tramite.data_recebimento:
        return httprr(tramite.processo.get_absolute_url(), 'A operação não pode ser realizada porque o processo já foi recebido.')

    if request.method == 'POST':
        form = TramiteFormReceber(request.POST, instance=tramite, request=request)
        if form.is_valid():
            form.save()
            if 'receber_e_encaminhar' in request.POST:
                return httprr(
                    f'/protocolo/processo_encaminhar/{tramite.id}/interno/', 'Processo recebido com sucesso. Agora você já pode encaminhá-lo.'
                )
            elif 'receber_e_finalizar' in request.POST:
                return httprr(
                    f'/protocolo/processo_finalizar/{tramite.processo.id}/', 'Processo recebido com sucesso. Agora você já pode finalizá-lo.'
                )
            else:
                return httprr(tramite.processo.get_absolute_url(), 'Processo recebido com sucesso.')
    else:
        form = TramiteFormReceber(instance=tramite, request=request)

    return locals()


@rtr()
@permission_required('protocolo.pode_tramitar_processo')
def processo_encaminhar_primeiro_tramite(request, processo_id, tipo_encaminhamento_descricao):
    processo = get_object_or_404(Processo, id=processo_id)
    title = f'Encaminhar Processo {processo!s} (primeiro trâmite)'

    if Tramite.objects.filter(processo=processo, ordem=1):
        return httprr(processo.get_absolute_url(), 'A operação não pode ser realizada porque o processo já teve o seu primeiro trâmite realizado.')

    if processo.tem_vinculo_com_processo_eletronico:
        return httprr(processo.get_absolute_url(), 'A operação não pode ser realizada porque o processo possui vínculo com processo eletrônico.')

    tramite_novo = Tramite()
    tramite_novo.processo = processo
    tramite_novo.ordem = 1
    if tipo_encaminhamento_descricao == 'interno':
        tramite_novo.tipo_encaminhamento = Tramite.TIPO_ENCAMINHAMENTO_INTERNO
        tramite_novo.orgao_interno_encaminhamento = get_setor()
    elif tipo_encaminhamento_descricao == 'externo':
        tramite_novo.tipo_encaminhamento = Tramite.TIPO_ENCAMINHAMENTO_EXTERNO
        tramite_novo.orgao_interno_encaminhamento = get_setor()

    if request.method == 'POST':
        form = TramiteFormEncaminharFactory(tramite=tramite_novo, request_method=request.POST, request=request)
        if form.is_valid():
            form.save()
            return httprr(processo.get_absolute_url(), 'Processo encaminhado com sucesso.')
    else:
        form = TramiteFormEncaminharFactory(tramite=tramite_novo, request_method=None, request=request)
    return locals()


@rtr()
@permission_required('protocolo.pode_tramitar_processo')
def processo_encaminhar(request, tramite_id, tipo_encaminhamento_descricao):
    # Último trâmite realizado por completo.
    tramite = get_object_or_404(Tramite, id=tramite_id)
    title = f'Encaminhar Processo {tramite.processo!s}'
    nova_ordem = tramite.ordem + 1

    if Tramite.objects.filter(processo=tramite.processo, ordem=nova_ordem):
        return httprr(tramite.processo.get_absolute_url(), 'A operação não pode ser realizada porque o processo já foi encaminhado.')

    if tramite.processo.tem_vinculo_com_processo_eletronico:
        return httprr(
            tramite.processo.get_absolute_url(), 'A operação não pode ser realizada porque o processo possui vínculo com processo eletrônico.'
        )

    # Novo trâmite que se inicia, com base nos dados do último tramite
    # realizado por completo.
    tramite_novo = Tramite()
    tramite_novo.processo = tramite.processo
    tramite_novo.ordem = nova_ordem

    if tipo_encaminhamento_descricao == 'interno':
        tramite_novo.tipo_encaminhamento = Tramite.TIPO_ENCAMINHAMENTO_INTERNO
    elif tipo_encaminhamento_descricao == 'externo':
        tramite_novo.tipo_encaminhamento = Tramite.TIPO_ENCAMINHAMENTO_EXTERNO
    tramite_novo.orgao_interno_encaminhamento = tramite.orgao_interno_recebimento
    form = TramiteFormEncaminharFactory(tramite=tramite_novo, request_method=request.POST or None, request=request)
    if form.is_valid():
        form.save()
        return httprr(tramite.processo.get_absolute_url(), 'Processo encaminhado com sucesso.')

    return locals()


@rtr()
@permission_required('protocolo.pode_tramitar_processo')
def processo_editar_encaminhamento(request, tramite_id):
    tramite = get_object_or_404(Tramite, id=tramite_id)
    title = f'Editar Encaminhamento do Processo {tramite.processo!s}'

    if tramite.data_recebimento:
        return httprr(tramite.processo.get_absolute_url(), 'A operação não pode ser realizada porque o processo já foi recebido.')

    if tramite.processo.tem_vinculo_com_processo_eletronico:
        return httprr(
            tramite.processo.get_absolute_url(), 'A operação não pode ser realizada porque o processo possui vínculo com processo eletrônico.'
        )

    if request.method == 'POST':
        form = TramiteFormEncaminharFactory(tramite=tramite, request_method=request.POST, request=request)
        if form.is_valid():
            form.save()
            return httprr(tramite.processo.get_absolute_url(), 'Processo encaminhado com sucesso.')
    else:
        form = TramiteFormEncaminharFactory(tramite=tramite, request_method=None, request=request)

    return locals()


@rtr()
@permission_required('protocolo.pode_tramitar_processo')
def processo_informar_recebimento_externo(request, tramite_id):
    tramite = get_object_or_404(Tramite, id=tramite_id)
    title = f'Informar Recebimento de Processo {tramite.processo} no Órgão Externo {tramite.orgao_vinculo_externo_recebimento}'

    if request.method == 'POST':
        form = TramiteFormInformarRecebimentoExterno(data=request.POST, instance=tramite)
        if form.is_valid():
            form.save()
            return httprr(tramite.processo.get_absolute_url(), 'Processo encaminhado com sucesso')
    else:
        form = TramiteFormInformarRecebimentoExterno(instance=tramite)

    return locals()


@rtr()
@permission_required('protocolo.pode_tramitar_processo')
def processo_retornar_para_ambito_interno(request, tramite_id):
    tramite = get_object_or_404(Tramite, id=tramite_id)

    title = f'Retornar Processo {tramite.processo!s} para Âmbito Interno'
    nova_ordem = tramite.ordem + 1

    if Tramite.objects.filter(processo=tramite.processo, ordem=nova_ordem):
        return httprr(tramite.processo.get_absolute_url(), 'A operação não pode ser realizada porque o processo já foi encaminhado.')

    # Novo trâmite que se inicia, com base nos dados do último tramite realizado.
    tramite_novo = Tramite()
    tramite_novo.processo = tramite.processo
    tramite_novo.ordem = nova_ordem
    tramite_novo.tipo_encaminhamento = Tramite.TIPO_ENCAMINHAMENTO_INTERNO

    # fields = ['orgao_vinculo_externo_encaminhamento', 'vinculo_encaminhamento', 'data_encaminhamento', 'observacao_encaminhamento', 'observacao_recebimento']
    tramite_novo.orgao_vinculo_externo_encaminhamento = tramite.orgao_vinculo_externo_encaminhamento
    if tramite.vinculo_recebimento:
        tramite_novo.vinculo_encaminhamento = tramite.vinculo_recebimento
    else:
        tramite_novo.vinculo_encaminhamento = tramite.orgao_interno_recebimento
    tramite_novo.data_encaminhamento = datetime.today()

    if request.method == 'POST':
        form = TramiteFormRetornarProcessoParaAmbitoInterno(data=request.POST, instance=tramite_novo, request=request)
        if form.is_valid():
            form.save()
            return httprr(tramite.processo.get_absolute_url(), 'O retorno do processo foi cadastrado com sucesso.')
    else:
        form = TramiteFormRetornarProcessoParaAmbitoInterno(instance=tramite_novo, request=request)

    return locals()


@permission_required('protocolo.pode_tramitar_processo')
def processo_remover_encaminhamento(request, tramite_id):
    tramite = get_object_or_404(Tramite, id=tramite_id)
    if tramite.data_recebimento:
        return httprr(tramite.processo.get_absolute_url(), 'A operação não pode ser realizada porque o processo já foi recebido.')
    tramite.delete()
    return httprr(tramite.processo.get_absolute_url(), 'Encaminhamento removido com sucesso.')


@rtr()
@permission_required('protocolo.pode_tramitar_processo')
def processo_finalizar(request, processo_id):
    processo = get_object_or_404(Processo, id=processo_id)
    title = f'Finalizar Processo {processo!s}'
    if processo.status != Processo.STATUS_EM_TRAMITE:
        return httprr(processo.get_absolute_url(), 'O processo não pode ser finalizado porque não está mais "em trâmite".')

    if request.method == 'POST':
        form = ProcessoFormFinalizar(request.POST, instance=processo, request=request)
        if form.is_valid():
            form.save()
            return httprr(processo.get_absolute_url(), 'Processo finalizado com sucesso.')
    else:
        form = ProcessoFormFinalizar(instance=processo, request=request)

    return locals()


@permission_required('protocolo.pode_tramitar_processo')
def processo_remover_finalizacao(request, processo_id):
    processo = get_object_or_404(Processo, id=processo_id)

    if processo.status != Processo.STATUS_FINALIZADO:
        return httprr(processo.get_absolute_url(), 'A operação não pode ser realizada porque o processo não está finalizado.')

    processo.remover_finalizacao()
    return httprr(processo.get_absolute_url(), 'Finalização removida com sucesso.')


@permission_required('protocolo.pode_gerar_capa')
def processo_imprimir_etiqueta(request, processo_id):
    processo = get_object_or_404(Processo, id=processo_id)
    return imprimir_etiqueta(processo)


# utilizado pelo webservice no site SuapExterno (https://suap.ifrn.edu.br/)
# Essa função será depreciada já que o SUAP deixará de funcionar somente na intranet
def processo_consulta_publica(numero_processo, documento):
    processos = Processo.objects.filter(interessado_documento=documento, numero_processo=numero_processo)

    if processos:
        processo = processos[0]
        processo.get_orgao_responsavel_atual()
        ultima_ordem = len(processo.tramite_set.all()) + 1
        conteudo_html = str(
            render_to_string('protocolo/templates/processo_detalhe_externo.html', {'processo': processo, 'ultima_ordem': ultima_ordem})
        )
        return {'ok': True, 'conteudo_html': conteudo_html}
    else:
        return {'ok': False, 'msg': 'Processo não encontrado.'}


@rtr()
def consulta_publica(request):
    title = 'Consulta de Processos Físicos'
    category = 'Consultas'
    icon = 'file-alt'
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    form = ProtocoloForm(request.POST or None)
    if form.is_valid():
        # quando o método "processo_consulta_publica" for depreciado (webservice deixar de existir),
        # seu conteúdo será transferido para esse local
        try:
            conteudo = processo_consulta_publica(form.cleaned_data['numero_processo'], form.cleaned_data['documento'])['conteudo_html']
            return render('protocolo/templates/processo_detalhe.html', locals())

        except KeyError:
            return httprr('.', 'Processo não encontrado.', 'error')

    return locals()


@rtr()
def visualizar_processo_consulta_publica(request, processo_id):
    title = 'Processo Físico'
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    processo = Processo.objects.filter(id=processo_id).first()
    if not processo:
        return httprr('..', 'Processo não encontrado.', 'error')
    return locals()
