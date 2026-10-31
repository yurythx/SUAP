import datetime

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.template.defaultfilters import pluralize

from comum.models import Configuracao
from comum.utils import get_uo
from demandas_externas.forms import (
    AtribuirDemandaForm,
    AtribuirPrioridadeForm,
    DemandaForm,
    IndicarCampusForm,
    MembroEquipeForm,
    RecusarDemandaForm,
    RegistrarAtendimentoForm,
)
from demandas_externas.models import Demanda, Equipe, Periodo
from djtools import layout
from djtools.utils import httprr, permission_required, rtr, send_mail, send_notification


@layout.servicos_anonimos()
def servicos_anonimos(request):
    servicos_anonimos = []
    servicos_anonimos.append(
        {'categoria': 'Extensão', 'url': '/demandas_externas/periodos_demanda/', 'icone': 'file-alt', 'titulo': 'Demandas da Comunidade'}
    )
    return servicos_anonimos


@layout.atribuidos_a_meus_grupos()
def index_atribuidos_a_meus_grupos(request):
    pendencias = []
    if not request.user.has_perm('demandas_externas.view_publicoalvo', ignore_superuser=True):
        return pendencias

    pode_add = request.user.has_perm('demandas_externas.add_publicoalvo', ignore_superuser=True)
    uo_filtro = None if pode_add else get_uo(request.user)

    pendentes_aceite = Demanda.objects.filter(situacao=Demanda.SUBMETIDA)
    if uo_filtro is not None:
        pendentes_aceite = pendentes_aceite.filter(campus_atendimento=uo_filtro)
    qtd_pendentes_aceite = pendentes_aceite.count()
    if qtd_pendentes_aceite:
        pendencias.append(
            {
                'titulo': f'Demanda{pluralize(qtd_pendentes_aceite)} Externa{pluralize(qtd_pendentes_aceite)}',
                'subtitulo': 'a avaliar',
                'qtd': qtd_pendentes_aceite,
                'url': '/admin/demandas_externas/demanda?tab=tab_submetidas',
            }
        )

    primeiro_pendente_campus = (
        Demanda.objects.filter(campus_atendimento__isnull=True)
        .exclude(situacao__in=[Demanda.SUBMETIDA, Demanda.NAO_ATENDIDA, Demanda.NAO_ACEITA])
        .values_list('id', flat=True)
        .first()
    )
    if primeiro_pendente_campus is not None:
        qtd_pendentes_campus = (
            Demanda.objects.filter(campus_atendimento__isnull=True)
            .exclude(situacao__in=[Demanda.SUBMETIDA, Demanda.NAO_ATENDIDA, Demanda.NAO_ACEITA])
            .count()
        )
        pendencias.append(
            {
                'titulo': f'Demanda{pluralize(qtd_pendentes_campus)} Externa{pluralize(qtd_pendentes_campus)}',
                'subtitulo': 'a indicar campus de atendimento',
                'qtd': qtd_pendentes_campus,
                'url': f'/demandas_externas/demanda/{primeiro_pendente_campus}/',
            }
        )

    pendentes_responsavel = Demanda.objects.filter(situacao__in=[Demanda.EM_ATENDIMENTO, Demanda.EM_ESPERA], responsavel__isnull=True)
    if uo_filtro is not None:
        pendentes_responsavel = pendentes_responsavel.filter(campus_atendimento=uo_filtro)
    primeiro_pendente_responsavel = pendentes_responsavel.values_list('id', flat=True).first()
    if primeiro_pendente_responsavel is not None:
        qtd_pendentes_responsavel = pendentes_responsavel.count()
        pendencias.append(
            {
                'titulo': f'Demanda{pluralize(qtd_pendentes_responsavel)} Externa{pluralize(qtd_pendentes_responsavel)}',
                'subtitulo': 'a indicar responsável',
                'qtd': qtd_pendentes_responsavel,
                'url': f'/demandas_externas/demanda/{primeiro_pendente_responsavel}/',
            }
        )

    return pendencias


@rtr()
def periodos_demanda(request):
    title = 'Adicionar Demanda da Comunidade'
    category = 'Solicitações'
    icon = 'file-alt'
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    hoje = datetime.datetime.now().date()
    periodos = Periodo.objects.filter(data_inicio__lte=hoje, data_termino__gte=hoje)
    return locals()


@rtr()
def cadastrar_demanda(request, periodo_id):
    title = 'Adicionar Demanda'
    periodo = get_object_or_404(Periodo, pk=periodo_id)
    sigla_instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
    form = DemandaForm(request.POST or None, periodo=periodo, sigla_instituicao=sigla_instituicao)
    if form.is_valid():
        o = form.save(False)
        o.cadastrada_em = datetime.datetime.now()
        o.periodo = periodo
        o.campus_atendimento = form.cleaned_data.get('campus_indicado')
        o.save()
        form.save_m2m()
        return httprr(
            '/demandas_externas/periodos_demanda/',
            'Demanda cadastrada com sucesso. Mensagens sobre o andamento da demanda serão enviadas para o email informado.',
        )

    return locals()


def pode_visualizar_demanda(request, demanda, uo):
    if not request.user.has_perm('demandas_externas.add_periodo'):
        if (
            demanda.situacao in [Demanda.SUBMETIDA, Demanda.NAO_ACEITA]
            and not request.user.has_perm('demandas_externas.view_publicoalvo')
            or (
                not request.user.has_perm('demandas_externas.add_publicoalvo')
                and not request.user.has_perm('demandas_externas.pode_ver_todas_demandas_externas')
                and demanda.campus_atendimento
                and demanda.campus_atendimento != uo
            )
            or (
                not request.user.has_perm('demandas_externas.view_publicoalvo')
                and not request.user.has_perm('demandas_externas.pode_ver_todas_demandas_externas')
                and ((demanda.campus_atendimento and demanda.campus_atendimento != uo) or (not demanda.campus_atendimento))
            )
        ):
            raise PermissionDenied


@rtr()
@permission_required('demandas_externas.view_demanda')
def demanda(request, demanda_id):
    title = 'Visualizar Demanda'
    demanda = get_object_or_404(Demanda, pk=demanda_id)
    uo = get_uo(request.user)
    pode_visualizar_demanda(request, demanda, uo)
    pode_aceitar = demanda.pode_ser_gerenciada() and (
        request.user.has_perm('demandas_externas.add_publicoalvo')
        or (request.user.has_perm('demandas_externas.view_publicoalvo') and (not demanda.campus_atendimento or demanda.campus_atendimento == uo))
    )

    return locals()


@rtr()
@permission_required('demandas_externas.view_publicoalvo')
def aceitar_demanda(request, demanda_id):
    demanda = get_object_or_404(Demanda, pk=demanda_id)
    if demanda.situacao == Demanda.SUBMETIDA:
        uo = get_uo(request.user)
        pode_visualizar_demanda(request, demanda, uo)
        demanda.situacao = Demanda.EM_ESPERA
        demanda.avaliada_em = datetime.datetime.now()
        demanda.avaliada_por = request.user.get_vinculo()
        demanda.save()
        titulo = '[SUAP] Registro de Demanda Externa'
        texto = (
            '<h1>Extensão</h1>'
            '<h2>Registro de Demanda Externa</h2>'
            f'<p>Descrição da Demanda: {demanda.descricao}'
            '<p>A demanda foi aceita. Novas informações sobre o andamento e a execução serão enviadas em emails posteriores.</p>'
        )
        send_mail(titulo, texto, settings.DEFAULT_FROM_EMAIL, [demanda.email])
        return httprr(f'/demandas_externas/demanda/{demanda.id}/', 'Demanda aceita com sucesso.')


@rtr()
@permission_required('demandas_externas.view_publicoalvo')
def nao_aceitar_demanda(request, demanda_id):
    demanda = get_object_or_404(Demanda, pk=demanda_id)
    if not demanda.pode_ser_gerenciada():
        raise PermissionDenied
    title = 'Não Aceitar Demanda'
    uo = get_uo(request.user)
    pode_visualizar_demanda(request, demanda, uo)
    form = RecusarDemandaForm(request.POST or None, instance=demanda)
    if form.is_valid():
        o = form.save(False)
        o.situacao = Demanda.NAO_ACEITA
        o.avaliada_em = datetime.datetime.now()
        o.avaliada_por = request.user.get_vinculo()
        o.save()
        titulo = '[SUAP] Registro de Demanda Externa'
        texto = (
            '<h1>Extensão</h1>'
            '<h2>Registro de Demanda Externa</h2>'
            f'<p>Descrição da Demanda: {demanda.descricao}'
            f'<p>A demanda não foi aceita. Motivo: {demanda.observacoes} </p>'
        )
        send_mail(titulo, texto, settings.DEFAULT_FROM_EMAIL, [demanda.email])
        return httprr(f'/demandas_externas/demanda/{demanda.id}/', 'Demanda não aceita com sucesso.')
    return locals()


@rtr()
@permission_required('demandas_externas.view_periodo')
def atribuir_demanda(request, demanda_id):
    title = 'Atribuir Demanda'
    demanda = get_object_or_404(Demanda, pk=demanda_id)
    if not demanda.pode_ser_gerenciada():
        raise PermissionDenied
    uo = get_uo(request.user)
    pode_visualizar_demanda(request, demanda, uo)
    form = AtribuirDemandaForm(request.POST or None, instance=demanda, request=request)
    if form.is_valid():
        o = form.save(False)
        o.atribuida_em = datetime.datetime.now()
        o.atribuida_por = request.user.get_vinculo()
        o.situacao = Demanda.EM_ATENDIMENTO
        o.save()
        titulo = '[SUAP] Responsável por Demanda Externa'
        texto = (
            '<h1>Extensão</h1>'
            '<h2>Indicação de Responsável por Demanda Externa</h2>'
            f'<p>Você foi indicado como responsável pela demanda: <a href="{settings.SITE_URL}/demandas_externas/demanda/{demanda.id}/">{demanda.descricao}</a>. Acesse o SUAP para mais detalhes.'
        )
        send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [o.responsavel])
        titulo = '[SUAP] Registro de Demanda Externa'
        texto = (
            '<h1>Extensão</h1>'
            '<h2>Registro de Demanda Externa</h2>'
            f'<p>Descrição da Demanda: {demanda.descricao}'
            '<p>A demanda está em atendimento. Novas informações sobre o andamento e a execução serão enviadas em emails posteriores.</p>'
        )
        send_mail(titulo, texto, settings.DEFAULT_FROM_EMAIL, [demanda.email])
        return httprr(f'/demandas_externas/demanda/{demanda.id}/', 'Demanda atribuída com sucesso.')
    return locals()


@rtr()
@permission_required('demandas_externas.view_publicoalvo')
def indicar_campus_atendimento(request, demanda_id):
    demanda = get_object_or_404(Demanda, pk=demanda_id)
    title = 'Indicar Campus de Atendimento'
    uo = get_uo(request.user)
    pode_visualizar_demanda(request, demanda, uo)
    if not demanda.pode_ser_gerenciada():
        raise PermissionDenied
    form = IndicarCampusForm(request.POST or None, instance=demanda)
    if form.is_valid():
        o = form.save(False)
        o.responsavel = None
        o.save()
        return httprr('/admin/demandas_externas/demanda/', 'Campus de atendimento indicado com sucesso.')
    return locals()


@rtr()
@permission_required('demandas_externas.view_publicoalvo')
def retornar_demanda(request, demanda_id):
    demanda = get_object_or_404(Demanda, pk=demanda_id)
    if not demanda.pode_ser_gerenciada():
        raise PermissionDenied
    uo = get_uo(request.user)
    pode_visualizar_demanda(request, demanda, uo)
    if demanda.campus_atendimento:
        demanda.campus_atendimento = None
        demanda.responsavel = None
        demanda.save()
        return httprr(f'/demandas_externas/demanda/{demanda.id}/', 'Demanda retornada com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@permission_required('demandas_externas.view_demanda')
def adicionar_membro(request, demanda_id):
    title = 'Adicionar Membro na Equipe'
    demanda = get_object_or_404(Demanda, pk=demanda_id)
    if demanda.responsavel == request.user.get_vinculo() and demanda.pode_ser_gerenciada():
        form = MembroEquipeForm(request.POST or None, demanda=demanda)
        if form.is_valid():
            for participante in form.cleaned_data.get('participantes'):
                if not Equipe.objects.filter(demanda=demanda, participante=participante).exists():
                    membro = Equipe()
                    membro.demanda = demanda
                    membro.participante = participante
                    membro.save()
            for membro in demanda.equipe_set.all():
                if membro.participante not in form.cleaned_data.get('participantes'):
                    membro.delete()

            return httprr(f'/demandas_externas/demanda/{demanda.id}/?tab=dados_equipe_demanda', 'Membro da equipe cadastrado com sucesso.')

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('demandas_externas.view_demanda')
def registrar_atendimento(request, demanda_id):
    title = 'Registrar Atendimento da Demanda'
    demanda = get_object_or_404(Demanda, pk=demanda_id)
    if not demanda.pode_ser_gerenciada():
        raise PermissionDenied
    if demanda.responsavel == request.user.get_vinculo() and not demanda.qtd_beneficiados_atendidos:
        form = RegistrarAtendimentoForm(request.POST or None, instance=demanda)
        if form.is_valid():
            o = form.save(False)
            o.concluida_em = datetime.datetime.now()
            o.situacao = Demanda.ATENDIDA
            o.save()
            titulo = '[SUAP] Registro de Demanda Externa'
            texto = (
                '<h1>Extensão</h1>'
                '<h2>Registro de Demanda Externa</h2>'
                f'<p>Descrição da Demanda: {demanda.descricao}'
                f'<p>Data da conclusão: {demanda.concluida_em} - Observações: {demanda.descricao_atendimento}.</p>'
            )
            send_mail(titulo, texto, settings.DEFAULT_FROM_EMAIL, [demanda.email])
            return httprr(f'/demandas_externas/demanda/{demanda.id}/?tab=dados_execucao_demanda', 'Atendimento da demanda registrado com sucesso.')

        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('demandas_externas.view_periodo')
def ver_periodo(request, periodo_id):
    title = 'Período de Recebimento'
    periodo = get_object_or_404(Periodo, pk=periodo_id)
    return locals()


@rtr()
@permission_required('demandas_externas.view_periodo')
def atribuir_prioridade(request, demanda_id):
    title = 'Atribuir Prioridade'
    demanda = get_object_or_404(Demanda, pk=demanda_id)
    if not demanda.pode_ser_gerenciada():
        raise PermissionDenied
    uo = get_uo(request.user)
    pode_visualizar_demanda(request, demanda, uo)
    form = AtribuirPrioridadeForm(request.POST or None, instance=demanda, request=request)
    if form.is_valid():
        form.save()
        return httprr(f'/demandas_externas/demanda/{demanda.id}/', 'Prioridade atribuída com sucesso.')
    return locals()
