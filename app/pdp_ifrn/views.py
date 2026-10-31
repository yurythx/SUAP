from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404

from comum.utils import get_uo
from djtools import layout
from djtools.utils import group_required, httprr, permission_required, rtr
from pdp_ifrn.forms import HistoricoStatusRespostaForm, RespostasPDPForm
from pdp_ifrn.models import PDP, HistoricoStatusResposta, Resposta
from rh.models import UnidadeOrganizacional


@layout.inscricao()
def index_inscricoes(request):
    inscricoes = []

    if request.user.eh_servidor:
        hoje = datetime.today().date()
        pdps = PDP.objects.filter(preenchimento_habilitado=True, data_inicial__lte=hoje, data_final__gte=hoje).order_by('ano__ano')
        for pdp in pdps:
            inscricoes.append(
                {
                    'url': f'/admin/pdp_ifrn/resposta/add/?pdp_id={pdp.id}',
                    'titulo': f'Contribua com o <strong>Plano de Desenvolvimento de Pessoas: {pdp}</strong>',
                    'prazo': pdp.data_final.strftime('%d/%m/%Y'),
                }
            )
    return inscricoes


@rtr()
@permission_required('pdp_ifrn.pode_deferir_respostas_pdp, pdp_ifrn.pode_aprovar_respostas_pdp, pdp_ifrn.pode_homologar_respostas_pdp')
def gerenciamento_respostas(request):
    title = 'Gerenciar Respostas do PDP'
    pode_deferir_respostas_pdp = request.user.has_perm('pdp_ifrn.pode_deferir_respostas_pdp')
    pode_aprovar_respostas_pdp = request.user.has_perm('pdp_ifrn.pode_aprovar_respostas_pdp')
    pode_homologar_respostas_pdp = request.user.has_perm('pdp_ifrn.pode_homologar_respostas_pdp')

    form = RespostasPDPForm(request=request, data=request.GET or None)
    if form.is_valid():
        pdp = form.cleaned_data.get('pdp')
        status = form.cleaned_data.get('status')
        campus = form.cleaned_data.get('campus')
        setor = form.cleaned_data.get('setor')
        necessidade = form.cleaned_data.get('necessidade')
        tipo_aprendizagem = form.cleaned_data.get('tipo_aprendizagem')

        if not request.user.is_superuser and not request.user.has_group_cached(['Coordenador de PDP Sistêmico', 'Homologador de PDP']):
            respostas = Resposta.objects.filter(campus=get_uo(request.user))
        else:
            respostas = Resposta.objects.all()

        if pdp:
            respostas = respostas.filter(pdp=pdp)
        if campus:
            respostas = respostas.filter(campus=campus)
        if setor:
            respostas = respostas.filter(servidor__setor=setor)
        if necessidade:
            respostas = respostas.filter(necessidade=necessidade)
        if tipo_aprendizagem:
            respostas = respostas.filter(tipo_aprendizagem=tipo_aprendizagem)

        if status:
            if status.upper() == 'TODOS':
                todos = []
                for st in HistoricoStatusResposta.STATUS_RESPOSTA:
                    todos.append(st[0])
                respostas = [x for x in respostas if x.get_ultimo_status in todos]
            else:
                respostas = [x for x in respostas if x.get_ultimo_status == status]

    return locals()


@rtr()
@login_required()
def registrar_historico(request, resposta_id, novo_status, status_selecionado):
    if not request.user.has_perm('pdp_ifrn.pode_deferir_respostas_pdp') and (novo_status == 'deferida' or novo_status == 'indeferida'):
        return HttpResponseForbidden()

    if not request.user.has_perm('pdp_ifrn.pode_aprovar_respostas_pdp') and (novo_status == 'aprovada' or novo_status == 'reprovada'):
        return HttpResponseForbidden()

    if not request.user.has_perm('pdp_ifrn.pode_homologar_respostas_pdp') and (novo_status == 'homologada' or novo_status == 'rejeitada'):
        return HttpResponseForbidden()

    resposta = Resposta.objects.get(id=resposta_id)
    novo_historico = HistoricoStatusResposta()

    if novo_status == 'indeferida':
        form = HistoricoStatusRespostaForm(request=request, data=request.POST or None)
        if request.method == 'GET':
            title = 'Informe a justificativa para o indeferimento'
            return locals()
        else:
            if form.is_valid():
                novo_historico.justificativa = form.cleaned_data.get('justificativa')
            else:
                return locals()

    novo_historico.resposta = resposta
    novo_historico.status = novo_status
    novo_historico.data = datetime.now()
    novo_historico.usuario = request.user
    novo_historico.save()

    return httprr(
        f'/pdp_ifrn/gerenciamento_respostas/?pdp={resposta.pdp.pk}&status={status_selecionado}&carregarespostaspdp_form=Aguarde...',
        f'Resposta {novo_status} com sucesso.',
        close_popup=True,
    )


@login_required()
def registrar_historico_selecionadas(request, novo_status, status_selecionado):
    qtd_registradas = 0

    if 'ids_respostas' in request.POST:
        ids_respostas = request.POST.getlist('ids_respostas')
        for id in ids_respostas:
            qtd_registradas += 1
            resposta = Resposta.objects.get(id=id)
            novo_historico = HistoricoStatusResposta()
            novo_historico.resposta = resposta
            novo_historico.status = novo_status
            novo_historico.data = datetime.now()
            novo_historico.usuario = request.user
            novo_historico.save()

    return httprr(
        f'/pdp_ifrn/gerenciamento_respostas/?status={status_selecionado}&carregarespostaspdp_form=Aguarde...',
        f'{qtd_registradas} Respostas {novo_status} com sucesso.',
    )


@rtr()
@login_required()
@group_required('Coordenador de PDP, Aprovador do PDP, Homologador de PDP, Coordenador de PDP Sistêmico')
def relatorio_geral_pdp(request):
    title = 'Relatório Geral do PDP'
    relatorio = []
    total = {
        'campus': 'total',
        'total': 0,
        'pendentes': 0,
        'deferidas': 0,
        'indeferidas': 0,
        'aprovadas': 0,
        'reprovadas': 0,
        'homologadas': 0,
        'rejeitadas': 0,
    }

    for uo in UnidadeOrganizacional.objects.suap().all():
        relatorio.append(
            {
                'campus': uo.sigla,
                'total': 0,
                'pendentes': 0,
                'deferidas': 0,
                'indeferidas': 0,
                'aprovadas': 0,
                'reprovadas': 0,
                'homologadas': 0,
                'rejeitadas': 0,
            }
        )

    for resposta in Resposta.objects.all():
        index_dict = next((index for (index, d) in enumerate(relatorio) if d['campus'] == resposta.campus.sigla), None)
        if index_dict:
            relatorio[index_dict]['total'] += 1
            ultimo_status = resposta.get_ultimo_status
            if ultimo_status == 'pendente':
                relatorio[index_dict]['pendentes'] += 1
            elif ultimo_status == 'deferida':
                relatorio[index_dict]['deferidas'] += 1
            elif ultimo_status == 'indeferida':
                relatorio[index_dict]['indeferidas'] += 1
            elif ultimo_status == 'aprovada':
                relatorio[index_dict]['aprovadas'] += 1
            elif ultimo_status == 'reprovada':
                relatorio[index_dict]['reprovadas'] += 1
            elif ultimo_status == 'homologada':
                relatorio[index_dict]['homologadas'] += 1
            elif ultimo_status == 'rejeitada':
                relatorio[index_dict]['rejeitadas'] += 1

    for r in relatorio:
        total['total'] += r['total']
        total['pendentes'] += r['pendentes']
        total['deferidas'] += r['deferidas']
        total['indeferidas'] += r['indeferidas']
        total['aprovadas'] += r['aprovadas']
        total['reprovadas'] += r['reprovadas']
        total['homologadas'] += r['homologadas']
        total['rejeitadas'] += r['rejeitadas']

    return locals()


@rtr()
@login_required()
@permission_required('pdp_ifrn.view_resposta')
def resposta(request, resposta_id):
    resposta = get_object_or_404(Resposta, pk=resposta_id)

    if (
        not request.user.is_superuser
        and request.user.get_relacionamento() != resposta.servidor
        and not request.user.has_group_cached(['Coordenador de PDP Sistêmico', 'Coordenador de PDP', 'Aprovador do PDP', 'Homologador de PDP'])
    ):
        return HttpResponseForbidden()

    return locals()


# @rtr()
# def consulta_pdp(request):
#     title = 'Consulta PDP'
#     servicos_anonimos = layout.gerar_servicos_anonimos(request)
#     form = ConsultaPDPForm(request=request, data=request.GET or None)
#
#     if form.is_valid():
#         respostas = form.processar()
#     else:
#         respostas = Resposta.objects.all()
#         respostas = [x for x in respostas if x.get_ultimo_status == 'homologada']
#
#     return locals()
#
#
@rtr()
def detalhes_pdp(request, resposta_id):
    resposta = Resposta.objects.get(id=resposta_id)
    return locals()


#
#
# @layout.servicos_anonimos()
# def servicos_anonimos(request):
#     servicos_anonimos = list()
#     servicos_anonimos.append(dict(
#         categoria='Consultas',
#         url="/pdp_ifrn/consulta/",
#         icone="file-alt",
#         titulo='Consulta PDP'
#     ))
#
#     return servicos_anonimos
