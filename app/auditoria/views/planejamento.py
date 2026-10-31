from calendar import monthrange
from datetime import date

from django.http import HttpRequest
from django.shortcuts import get_object_or_404

from djtools.db.models import Prefetch
from djtools.utils import DateInterval, httprr, permission_required, rtr
from rh.models import Servidor

from ..models import AfastamentoPlanejado, PlanejamentoAnual, PlanejamentoMensal, StatusAfastamento
from .paint import calcular_planejamento_de_auditor


@permission_required('comum.is_auditor')
def sincronizar_planejamento(request, planejamento_id):
    planejamento: PlanejamentoAnual = get_object_or_404(PlanejamentoAnual, pk=planejamento_id)
    auditor: Servidor = planejamento.auditor
    url_target = planejamento.get_absolute_url()
    if planejamento.pode_editar(request.user.get_vinculo()):
        return httprr(url_target, f'Planejamento de {auditor} já está sincronizado com o PAINT.', tag='info')
    try:
        paint = planejamento.paint
        calcular_planejamento_de_auditor(
            paint=paint,
            auditor=auditor,
            user_vinculo=request.user.get_vinculo(),
        )
        msg = f'CH de {auditor} recalculada com sucesso.'
        return httprr(url_target, msg)
    except Exception as exc:
        return httprr(url_target, f'Falha ao recalcular {auditor}: {exc}', tag='error')


@rtr('auditoria/templates/planejamento/anual_auditor.html')
@permission_required('comum.is_auditor')
def planejamento_anual_auditor(request: HttpRequest, planejamento_id: int) -> dict[str, object]:
    mensais_qs = (
        PlanejamentoMensal.objects.only('id', 'mes', 'carga_horaria_prevista', 'carga_horaria_homologada')
        .order_by('mes')
        .prefetch_related(
            Prefetch(
                'afastamentos',
                queryset=(
                    AfastamentoPlanejado.objects.only('id', 'data_inicio', 'data_fim', 'status', 'tipo_afastamento')
                    .select_related('tipo_afastamento')
                    .filter(status__in=[StatusAfastamento.PENDENTE, StatusAfastamento.HOMOLOGADO])
                    .order_by('data_inicio', 'data_fim', 'id')
                ),
                to_attr='afastamentos_validos',
            ),
            Prefetch(
                'afastamentos',
                queryset=(
                    AfastamentoPlanejado.objects.only('id', 'data_inicio', 'data_fim', 'status', 'tipo_afastamento')
                    .select_related('tipo_afastamento')
                    .filter(status=StatusAfastamento.REJEITADO)
                    .order_by('data_inicio', 'data_fim', 'id')
                ),
                to_attr='afastamentos_rejeitados',
            ),
        )
    )
    planejamento: PlanejamentoAnual = get_object_or_404(
        PlanejamentoAnual.objects.select_related('auditor__jornada_trabalho', 'paint__ano').prefetch_related(
            Prefetch('planejamentos_mensais', queryset=mensais_qs)
        ),
        pk=planejamento_id,
    )

    title = f'Planejamento Anual - {planejamento.auditor} - {planejamento.paint.ano}'
    ano = planejamento.paint.ano.ano
    servidor: Servidor = planejamento.auditor
    ch_diaria = servidor.jornada_trabalho.get_jornada_trabalho_diaria()

    mensais_com_resumo = []
    ch_afastada_total = 0
    total_dias_afastado = 0
    for mensal in planejamento.planejamentos_mensais.all():
        mes = mensal.mes
        inicio_mes = date(ano, mes, 1)
        fim_mes = date(ano, mes, monthrange(ano, mes)[1])
        periodo = DateInterval(inicio_mes, fim_mes)
        ch_mensal = mensal.carga_horaria_prevista or 0
        horas_afastadas = 0
        dias_uteis_afastados = 0
        for afastamento in getattr(mensal, 'afastamentos_validos', []):
            horas_afastadas += afastamento.duracao_em_horas()
            dias_uteis_afastados += afastamento.dias_uteis()

        # Horas líquidas do mês = previstas - homologadas
        ch_liquida_mensal = ch_mensal - horas_afastadas
        ch_afastada_total += horas_afastadas
        # Monta resumo do mês
        afastamentos_list = list(getattr(mensal, 'afastamentos_validos', [])) + list(getattr(mensal, 'afastamentos_rejeitados', []))
        mensais_com_resumo.append(
            {
                'mensal': mensal,
                'ch_mensal': ch_mensal,
                'ch_liquida_mensal': ch_liquida_mensal,
                'horas_afastadas': horas_afastadas,
                'dias_uteis': dias_uteis_afastados,
                'afastamentos': afastamentos_list,
                'horas_dia': mensal.jornada_trabalho,
            }
        )
        total_dias_afastado += dias_uteis_afastados

    # Total anual líquido
    ch_liquida_prevista_total = sum(item['ch_liquida_mensal'] for item in mensais_com_resumo)

    return locals()


@permission_required('comum.is_auditor')
def enviar_para_homologacao(request, planejamento_id):
    planejamento: PlanejamentoAnual = get_object_or_404(PlanejamentoAnual, pk=planejamento_id)
    target_url = planejamento.get_absolute_url()
    if not planejamento.pode_enviar_para_homologacao(request.user):
        return httprr(target_url, 'Só é possível enviar planejamentos em rascunho.', tag='error', close_popup=True)
    try:
        planejamento.enviar_para_aprovacao()
        planejamento.save()
        return httprr(target_url, 'Planejamento enviado para homologação com sucesso.', tag='success', close_popup=True)
    except Exception as e:
        return httprr(target_url, f'Erro ao enviar para homologação: {e!s}', tag='error', close_popup=True)


@permission_required('comum.is_auditor')
def analisar_planejamento(request, planejamento_id):
    planejamento: PlanejamentoAnual = get_object_or_404(PlanejamentoAnual, pk=planejamento_id)
    target_url = planejamento.get_absolute_url()
    if not planejamento.pode_analisar(request.user):
        return httprr(target_url, 'Só é possível analisar os planejamentos que requisitaram análises.', tag='error', close_popup=True)
    try:
        planejamento.analisar()
        planejamento.save()
        return httprr(target_url, 'Planejamento recebido para análise com sucesso.', tag='success', close_popup=True)
    except Exception as e:
        return httprr(target_url, f'Erro ao receber planejamento: {e!s}', tag='error', close_popup=True)


@permission_required('comum.is_auditor')
def deferir_planejamento(request, planejamento_id):
    planejamento: PlanejamentoAnual = get_object_or_404(PlanejamentoAnual, pk=planejamento_id)
    target_url = planejamento.get_absolute_url()
    if not planejamento.pode_concluir(request.user):
        return httprr(target_url, 'Existem pendências a serem resolvidas no planejamento em questão.', tag='error', close_popup=True)
    try:
        planejamento.aprovar()
        planejamento.save()
        return httprr(target_url, 'Planejamento deferido com sucesso.', tag='success', close_popup=True)
    except Exception as e:
        return httprr(target_url, f'Erro ao deferir planejamento: {e!s}', tag='error', close_popup=True)


@permission_required('comum.is_auditor')
def indeferir_planejamento(request, planejamento_id):
    planejamento: PlanejamentoAnual = get_object_or_404(PlanejamentoAnual, pk=planejamento_id)
    target_url = planejamento.get_absolute_url()
    if not planejamento.pode_concluir(request.user):
        return httprr(target_url, 'Existem pendências a serem resolvidas no planejamento em questão.', tag='error', close_popup=True)
    try:
        planejamento.reprovar()
        planejamento.save()
        return httprr(target_url, 'Planejamento indeferido com sucesso.', tag='success', close_popup=True)
    except Exception as e:
        return httprr(target_url, f'Erro ao indeferir planejamento: {e!s}', tag='error', close_popup=True)


@permission_required('comum.is_auditor')
def retornar_para_rascunho(request, planejamento_id):
    planejamento: PlanejamentoAnual = get_object_or_404(PlanejamentoAnual, pk=planejamento_id)
    target_url = planejamento.get_absolute_url()
    if not planejamento.pode_retornar_para_rascunho(request.user):
        return httprr(target_url, 'Você não possui permissão para editar este planejamento.', tag='error', close_popup=True)
    try:
        planejamento.retornar_para_rascunho()
        planejamento.save()
        return httprr(target_url, 'Planejamento retornado para rascunho com sucesso.', tag='success', close_popup=True)
    except Exception as e:
        return httprr(target_url, f'Erro ao retornar planejamento para rascunho: {e!s}', tag='error', close_popup=True)
