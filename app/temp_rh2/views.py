from datetime import date, datetime

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models.query_utils import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from djtools import layout
from djtools.html.calendarios import Calendario
from djtools.utils import date_to_string, httprr, permission_required, render, rtr
from rh.models import Servidor, Situacao
from temp_rh2 import tasks
from temp_rh2.forms import GetInscricaoCompeticaoDesportivaForm, GetValidacaoInscricaoCompeticaoDesportivaForm, RelatorioInscritosModalidadeProvaForm
from temp_rh2.models import CompeticaoDesportiva, InscricaoCompeticaoDesportiva, Prova


@layout.inscricao()
def index_inscricoes(request):
    inscricoes = []

    hoje = datetime.now()
    if request.user.eh_servidor:
        servidor = request.user.get_relacionamento()
        if servidor.situacao.codigo in Situacao.SITUACOES_EM_EXERCICIO_NO_INSTITUTO:
            competicoes_desportivas_em_aberto = CompeticaoDesportiva.objects.filter(
                data_inicio_periodo_inscricoes__lte=hoje, data_fim_periodo_inscricoes__gte=hoje
            )
            if servidor.setor:
                competicoes_desportivas_em_aberto = competicoes_desportivas_em_aberto.filter(Q(uo=servidor.setor.uo) | Q(uo__isnull=True))
            else:
                competicoes_desportivas_em_aberto = competicoes_desportivas_em_aberto.filter(uo__isnull=True)
            inscricoes_realizadas = servidor.inscricaocompeticaodesportiva_set.filter(competicao_desportiva__in=competicoes_desportivas_em_aberto)
            for inscricao in inscricoes_realizadas:
                competicao = inscricao.competicao_desportiva
                inscricoes.append(
                    {
                        'url': f'/temp_rh2/competicao_desportiva/inscricao/{competicao.pk}/',
                        'titulo': f'Inscrição nos <strong>{competicao}</strong>.',
                        'prazo': date_to_string(competicao.data_fim_periodo_inscricoes),
                    }
                )
                competicoes_desportivas_em_aberto = competicoes_desportivas_em_aberto.exclude(pk=competicao.pk)

            for inscricao_competicao in competicoes_desportivas_em_aberto:
                inscricoes.append(
                    {
                        'url': f'/temp_rh2/competicao_desportiva/inscricao/{inscricao_competicao.pk}/',
                        'titulo': f'Inscrição nos <strong>{inscricao_competicao}</strong>.',
                        'prazo': date_to_string(inscricao_competicao.data_fim_periodo_inscricoes),
                    }
                )

    return inscricoes


@rtr()
@permission_required('rh.eh_servidor')
def inscricao_competicoes_desportivas(request, competicao_pk, inscricao_pk=None):
    competicao_desportiva = get_object_or_404(CompeticaoDesportiva.objects, pk=competicao_pk)
    if inscricao_pk:
        inscricao_desportiva = get_object_or_404(InscricaoCompeticaoDesportiva.objects, pk=inscricao_pk)
        return render('inscricao_competicao.html', locals())
    hoje = date.today()
    if not competicao_desportiva.data_inicio_periodo_inscricoes <= hoje <= competicao_desportiva.data_fim_periodo_inscricoes:
        raise PermissionDenied(f'Competição {competicao_desportiva} não está em período de inscrições.')
    servidor = request.user.get_relacionamento()
    if competicao_desportiva.uo:
        if (not request.user.get_vinculo().setor) or (competicao_desportiva.uo != request.user.get_vinculo().setor.uo):
            raise PermissionDenied(f'Competição disponível apenas para servidores do(a) {competicao_desportiva.uo.nome}.')
    if (
        not Servidor.objects.em_exercicio().filter(pk=servidor.pk).exists()
        and not Servidor.objects.substitutos_ou_temporarios().filter(pk=servidor.pk)
        and not Servidor.objects.visitantes().filter(pk=servidor.pk)
    ):
        raise PermissionDenied('Competicao disponível apenas para servidores.')

    title = f'Formulário de inscrição {competicao_desportiva.nome}'

    inscrito = False
    if InscricaoCompeticaoDesportiva.objects.filter(servidor=servidor, competicao_desportiva=competicao_desportiva).exists():
        inscricao_desportiva = InscricaoCompeticaoDesportiva.objects.get(
            servidor=request.user.get_relacionamento(), competicao_desportiva=competicao_desportiva
        )
        inscrito = True
    else:
        inscricao_desportiva = InscricaoCompeticaoDesportiva(servidor=request.user.get_relacionamento(), competicao_desportiva=competicao_desportiva)
    calendario_jogos = Calendario()

    meses = []

    css = 'recesso'
    if competicao_desportiva.data_inicio_periodo_inscricoes and competicao_desportiva.data_fim_periodo_inscricoes:
        calendario_jogos.adicionar_evento_calendario(
            competicao_desportiva.data_inicio_periodo_inscricoes,
            competicao_desportiva.data_fim_periodo_inscricoes,
            f'Período de inscrições {competicao_desportiva.nome}',
            css,
        )
        ano_mes = competicao_desportiva.data_inicio_periodo_inscricoes.strftime('%Y%m')
        if ano_mes not in meses:
            meses.append(ano_mes)
        ano_mes = competicao_desportiva.data_fim_periodo_inscricoes.strftime('%Y%m')
        if ano_mes not in meses:
            meses.append(ano_mes)
    css = 'feriado'
    if competicao_desportiva.data_inicio_periodo_validacao and competicao_desportiva.data_fim_periodo_validacao:
        calendario_jogos.adicionar_evento_calendario(
            competicao_desportiva.data_inicio_periodo_validacao,
            competicao_desportiva.data_fim_periodo_validacao,
            f'Período de validação {competicao_desportiva.nome}',
            css,
        )
        ano_mes = competicao_desportiva.data_inicio_periodo_validacao.strftime('%Y%m')
        if ano_mes not in meses:
            meses.append(ano_mes)
        ano_mes = competicao_desportiva.data_fim_periodo_validacao.strftime('%Y%m')
        if ano_mes not in meses:
            meses.append(ano_mes)

    css = 'recesso'
    if competicao_desportiva.data_inicio_confirmacao_inscritos and competicao_desportiva.data_fim_confirmacao_inscritos:
        calendario_jogos.adicionar_evento_calendario(
            competicao_desportiva.data_inicio_confirmacao_inscritos,
            competicao_desportiva.data_fim_confirmacao_inscritos,
            f'Período de confirmação dos inscritos {competicao_desportiva.nome}',
            css,
        )
        ano_mes = competicao_desportiva.data_inicio_confirmacao_inscritos.strftime('%Y%m')
        if ano_mes not in meses:
            meses.append(ano_mes)
        ano_mes = competicao_desportiva.data_fim_confirmacao_inscritos.strftime('%Y%m')
        if ano_mes not in meses:
            meses.append(ano_mes)

    css = 'feriado'
    if competicao_desportiva.data_inicio_reajustes and competicao_desportiva.data_fim_reajustes:
        calendario_jogos.adicionar_evento_calendario(
            competicao_desportiva.data_inicio_reajustes,
            competicao_desportiva.data_fim_reajustes,
            f'Período de de reajustes(pelo representante do campus) {competicao_desportiva.nome}',
            css,
        )
        ano_mes = competicao_desportiva.data_inicio_reajustes.strftime('%Y%m')
        if ano_mes not in meses:
            meses.append(ano_mes)
        ano_mes = competicao_desportiva.data_fim_reajustes.strftime('%Y%m')
        if ano_mes not in meses:
            meses.append(ano_mes)

    css = 'recesso'
    if competicao_desportiva.data_homologacao_inscricoes:
        calendario_jogos.adicionar_evento_calendario(
            competicao_desportiva.data_homologacao_inscricoes,
            competicao_desportiva.data_homologacao_inscricoes,
            f'Data limíte de homologação e consolidação das inscricoes {competicao_desportiva.nome}',
            css,
        )
        ano_mes = competicao_desportiva.data_homologacao_inscricoes.strftime('%Y%m')
        if ano_mes not in meses:
            meses.append(ano_mes)

    css = 'evento'
    if competicao_desportiva.data_inicio_periodo1_jogos and competicao_desportiva.data_fim_periodo1_jogos:
        calendario_jogos.adicionar_evento_calendario(
            competicao_desportiva.data_inicio_periodo1_jogos, competicao_desportiva.data_fim_periodo1_jogos, competicao_desportiva.nome, css
        )
        ano_mes = competicao_desportiva.data_inicio_periodo1_jogos.strftime('%Y%m')
        if ano_mes not in meses:
            meses.append(ano_mes)
        ano_mes = competicao_desportiva.data_fim_periodo1_jogos.strftime('%Y%m')
        if ano_mes not in meses:
            meses.append(ano_mes)

    if competicao_desportiva.data_inicio_periodo2_jogos and competicao_desportiva.data_fim_periodo2_jogos:
        calendario_jogos.adicionar_evento_calendario(
            competicao_desportiva.data_inicio_periodo2_jogos, competicao_desportiva.data_fim_periodo2_jogos, competicao_desportiva.nome, css
        )
        ano_mes = competicao_desportiva.data_inicio_periodo2_jogos.strftime('%Y%m')
        if ano_mes not in meses:
            meses.append(ano_mes)
        ano_mes = competicao_desportiva.data_fim_periodo2_jogos.strftime('%Y%m')
        if ano_mes not in meses:
            meses.append(ano_mes)

    calendarios = []
    for anomes in meses:
        calendarios.append(calendario_jogos.formato_mes(int(anomes[:4]), int(anomes[4:])))
    FormClass = GetInscricaoCompeticaoDesportivaForm(inscricao_desportiva, servidor, request)
    form = FormClass(request.POST or None, request.FILES or None, instance=inscricao_desportiva)
    municipios_pks = [9, 44, 8, 25, 17, 11, 2, 89, 1, 21, 318, 77]
    if form.is_valid():
        inscricao_desportiva.situacao = 1
        form.save()
        return httprr('..', 'Inscrição na competição realizada com sucesso!')
    return locals()


@rtr()
@permission_required('temp_rh2.pode_validar_inscricaocompeticaodesportiva')
def validar_homologar_inscricoes_desportivas(request, inscricao_pk):
    hoje = date.today()
    inscricao = get_object_or_404(InscricaoCompeticaoDesportiva.objects, pk=inscricao_pk)
    if (inscricao.competicao_desportiva.data_inicio_periodo_validacao <= hoje <= inscricao.competicao_desportiva.data_fim_periodo_validacao) or (
        inscricao.competicao_desportiva.data_inicio_confirmacao_inscritos <= hoje <= inscricao.competicao_desportiva.data_fim_confirmacao_inscritos
    ):
        FormClass = GetValidacaoInscricaoCompeticaoDesportivaForm()
    elif (inscricao.competicao_desportiva.data_inicio_reajustes <= hoje <= inscricao.competicao_desportiva.data_fim_reajustes) or (
        hoje == inscricao.competicao_desportiva.data_homologacao_inscricoes
    ):
        FormClass = GetValidacaoInscricaoCompeticaoDesportivaForm(etapa='homologacao')
    else:
        raise PermissionDenied(f'Não estamos em período de Validação nem de Homologação de inscrição no {inscricao.competicao_desportiva}')
    title = 'Validar/Homologar Inscrição'
    pode_ver_atestado_medico = inscricao.atestado_medico and InscricaoCompeticaoDesportiva.pode_ver_atestado_medico(request.user)
    form = FormClass(request.POST or None, instance=inscricao)
    if form.is_valid():
        if inscricao.situacao == 2:
            inscricao.homologado_por = None
            inscricao.homologado_em = None
            inscricao.rejeitado_em = None
            inscricao.rejeitado_por = None
            inscricao.observacao_rejeicao = ''

            inscricao.validado_por = request.user
            inscricao.validado_em = datetime.now()

        elif inscricao.situacao == 3:
            inscricao.homologado_por = request.user
            inscricao.homologado_em = datetime.now()
            inscricao.rejeitado_em = None
            inscricao.rejeitado_por = None
            inscricao.observacao_rejeicao = ''

        elif inscricao.situacao == 4:
            inscricao.homologado_por = None
            inscricao.homologado_em = None
            inscricao.validado_por = None
            inscricao.validado_em = None
            inscricao.rejeitado_por = request.user
            inscricao.rejeitado_em = datetime.now()

        form.save()
        return httprr('..', f'Inscrição {inscricao.get_situacao_display()}.')
    return locals()


@rtr()
@login_required()
@permission_required('temp_rh2.pode_validar_inscricaocompeticaodesportiva')
def relatorio_inscritos_por_modalidade_prova(request):
    title = 'Relatório de inscritos por modalidade e prova'
    form = RelatorioInscritosModalidadeProvaForm(request.POST or None)
    if form.is_valid():
        competicao_desportiva = form.cleaned_data.get('competicao_desportiva')
        inscricoes = InscricaoCompeticaoDesportiva.objects.filter(
            competicao_desportiva=competicao_desportiva,
        )
        modalidades = form.cleaned_data.get('modalidades', None)
        if modalidades:
            inscricoes = inscricoes.filter(modalidades__in=modalidades)
        uo = form.cleaned_data.get('uo', None)
        if uo:
            inscricoes = inscricoes.filter(uo=uo)
        return tasks.exportar_relatorio_inscritos_por_modalidades_provas_xls(inscricoes.distinct(), modalidades)

    return locals()


def escolha_provas_por_modalidades_ajax(request, competicao_desportiva_pk):
    modalidades_selecionadas = request.GET.getlist('modalidades[]', [])
    if not modalidades_selecionadas:
        return JsonResponse({'provas': []})

    provas = Prova.objects.filter(
        provas_competicao__pk=competicao_desportiva_pk, modalidade__id__in=[int(modalidade) for modalidade in modalidades_selecionadas]
    ).distinct()

    data = {'provas': [{'id': prova.id, 'nome': prova.nome} for prova in provas]}

    return JsonResponse(data)
