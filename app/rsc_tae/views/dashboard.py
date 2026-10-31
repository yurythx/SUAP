import json
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.db.models.functions import TruncMonth
from django.utils import timezone
from django.views.decorators.http import require_GET

from djtools.utils.response import rtr

from rsc_tae.enums import SituacaoProcesso
from rsc_tae.models import ComissaoRSCTae, ConfiguracaoRSCTae, ProcessoRSCTae
from rsc_tae.views.dashboard_avaliadores import montar_painel_avaliadores
from rsc_tae.views.dashboard_comissao import montar_painel_comissao

_MESES_PT = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']


def _fmt_mes(ano_mes: str) -> str:
    """Converte '2025-04' → 'Abr/25'."""
    y, m = ano_mes.split('-')
    return f'{_MESES_PT[int(m) - 1]}/{y[2:]}'


@rtr('rsc_tae/dashboard.html')
@login_required
@require_GET
def dashboard(request):
    # Sistêmica (RH) e membros da CRSC (grupo "Membro CRSC TAE" tem definir_avaliador_processorsctae).
    if not (request.user.has_perm('rh.eh_rh_sistemico') or request.user.has_perm('rsc_tae.definir_avaliador_processorsctae')):
        raise PermissionDenied('Permissão negada.')

    # ------------------------------------------------------------------ #
    # KPIs                                                                 #
    # ------------------------------------------------------------------ #
    total_processos = ProcessoRSCTae.objects.count()
    total_ativos = ProcessoRSCTae.objects.exclude(situacao__in=SituacaoProcesso.FINAIS).count()
    total_deferidos = ProcessoRSCTae.objects.filter(situacao=SituacaoProcesso.DEFERIDO).count()
    total_indeferidos = ProcessoRSCTae.objects.filter(situacao=SituacaoProcesso.INDEFERIDO).count()
    finalizados = total_deferidos + total_indeferidos
    taxa_deferimento = round(total_deferidos / finalizados * 100) if finalizados else None

    comissao_ativa = ComissaoRSCTae.objects.filter(ativa=True).first()
    total_membros_ativos = comissao_ativa.membros.filter(ativo=True).count() if comissao_ativa else 0

    # ------------------------------------------------------------------ #
    # Gráfico 1 — distribuição por situação (donut)                        #
    # ------------------------------------------------------------------ #
    situacao_label = dict(SituacaoProcesso.LABELS)
    por_situacao = ProcessoRSCTae.objects.values('situacao').annotate(total=Count('id'))
    situacao_chart_data = [
        {'name': situacao_label.get(row['situacao'], str(row['situacao'])), 'y': row['total']} for row in por_situacao if row['total'] > 0
    ]

    # ------------------------------------------------------------------ #
    # Gráfico 2 — evolução mensal de abertura e finalização (12 meses)     #
    # ------------------------------------------------------------------ #
    doze_meses_atras = timezone.now() - timedelta(days=365)

    abertos_qs = (
        ProcessoRSCTae.objects.filter(data_cadastro__gte=doze_meses_atras)
        .annotate(mes=TruncMonth('data_cadastro'))
        .values('mes')
        .annotate(total=Count('id'))
        .order_by('mes')
    )
    finalizados_qs = (
        ProcessoRSCTae.objects.filter(
            data_finalizacao_avaliacao__gte=doze_meses_atras,
            situacao__in=SituacaoProcesso.FINAIS,
        )
        .annotate(mes=TruncMonth('data_finalizacao_avaliacao'))
        .values('mes')
        .annotate(total=Count('id'))
        .order_by('mes')
    )

    meses_abertos = {row['mes'].strftime('%Y-%m'): row['total'] for row in abertos_qs}
    meses_finalizados = {row['mes'].strftime('%Y-%m'): row['total'] for row in finalizados_qs}
    all_months = sorted(set(list(meses_abertos) + list(meses_finalizados)))

    evolucao_categorias = json.dumps([_fmt_mes(m) for m in all_months])
    evolucao_abertos = json.dumps([meses_abertos.get(m, 0) for m in all_months])
    evolucao_finalizados = json.dumps([meses_finalizados.get(m, 0) for m in all_months])

    # ------------------------------------------------------------------ #
    # Gráfico 3 — processos por nível RSC (barras)                         #
    # ------------------------------------------------------------------ #
    por_nivel = (
        ProcessoRSCTae.objects.values('nivel_requisitado__nome', 'nivel_requisitado__ordem')
        .annotate(total=Count('id'))
        .order_by('nivel_requisitado__ordem')
    )
    nivel_labels = json.dumps([row['nivel_requisitado__nome'] or f'Nível {row["nivel_requisitado__ordem"]}' for row in por_nivel])
    nivel_totais = json.dumps([row['total'] for row in por_nivel])

    # ------------------------------------------------------------------ #
    # SLA — carrega apenas processos ativos para calcular alertas          #
    # ------------------------------------------------------------------ #
    # A configuração e a data de entrada na situação vêm resolvidas de uma vez: sem isso,
    # get_sla_status faria duas consultas por processo.
    configuracao = ConfiguracaoRSCTae.objects.first()
    processos_qs = list(
        ProcessoRSCTae.anotar_sla_data_entrada(
            ProcessoRSCTae.objects.exclude(situacao__in=SituacaoProcesso.FINAIS)
            .select_related('vinculo__pessoa', 'nivel_requisitado')
            .order_by('situacao', 'data_cadastro')
        )
    )
    processos_em_andamento = [{'processo': proc, 'sla': proc.get_sla_status(configuracao=configuracao)} for proc in processos_qs]

    # ------------------------------------------------------------------ #
    # Tabela de alertas SLA — processos atrasados ou com prazo crítico     #
    # ------------------------------------------------------------------ #
    _responsavel_por_situacao = {
        SituacaoProcesso.AGUARDANDO_PREENCHIMENTO: 'Servidor',
        SituacaoProcesso.AGUARDANDO_CORRECAO: 'Servidor',
        SituacaoProcesso.AGUARDANDO_VALIDACAO_DOCUMENTO_PRELIMINAR: 'RH',
        SituacaoProcesso.EM_ANALISE: 'Avaliadores',
    }

    alertas_sla = []
    for item in processos_em_andamento:
        sla = item['sla']
        if sla and (sla['atrasado'] or sla['alerta']):
            alertas_sla.append(
                {
                    **item,
                    'responsavel': _responsavel_por_situacao.get(item['processo'].situacao, '—'),
                }
            )
    # mais atrasados primeiro
    alertas_sla.sort(key=lambda x: x['sla']['dias_restantes'])

    total_sla_estourado = sum(1 for x in alertas_sla if x['sla']['atrasado'])
    total_sla_alerta = sum(1 for x in alertas_sla if x['sla']['alerta'])

    # ------------------------------------------------------------------ #
    # Gráfico 5 — conformidade SLA por etapa (ok / alerta / estourado)    #
    # ------------------------------------------------------------------ #
    _sla_label_por_situacao = {
        SituacaoProcesso.AGUARDANDO_PREENCHIMENTO: 'Preenchimento',
        SituacaoProcesso.AGUARDANDO_CORRECAO: 'Correção',
        SituacaoProcesso.AGUARDANDO_VALIDACAO_DOCUMENTO_PRELIMINAR: 'Validação RH',
        SituacaoProcesso.EM_ANALISE: 'Em Análise',
    }
    sla_por_etapa = {}
    for item in processos_em_andamento:
        sla = item['sla']
        if not sla:
            continue
        etapa = _sla_label_por_situacao.get(item['processo'].situacao, '—')
        bucket = sla_por_etapa.setdefault(etapa, {'ok': 0, 'alerta': 0, 'estourado': 0})
        if sla['atrasado']:
            bucket['estourado'] += 1
        elif sla['alerta']:
            bucket['alerta'] += 1
        else:
            bucket['ok'] += 1

    sla_etapa_labels = json.dumps(list(sla_por_etapa.keys()))
    sla_serie_ok = json.dumps([v['ok'] for v in sla_por_etapa.values()])
    sla_serie_alerta = json.dumps([v['alerta'] for v in sla_por_etapa.values()])
    sla_serie_estourado = json.dumps([v['estourado'] for v in sla_por_etapa.values()])

    return {
        'title': 'Dashboard RSC-TAE',
        # KPIs
        'total_processos': total_processos,
        'total_ativos': total_ativos,
        'total_deferidos': total_deferidos,
        'total_indeferidos': total_indeferidos,
        'taxa_deferimento': taxa_deferimento,
        'total_membros_ativos': total_membros_ativos,
        'comissao_ativa': comissao_ativa,
        'total_sla_estourado': total_sla_estourado,
        'total_sla_alerta': total_sla_alerta,
        # Dados dos gráficos (JSON para Highcharts)
        'situacao_chart_data': json.dumps(situacao_chart_data),
        'evolucao_categorias': evolucao_categorias,
        'evolucao_abertos': evolucao_abertos,
        'evolucao_finalizados': evolucao_finalizados,
        'nivel_labels': nivel_labels,
        'nivel_totais': nivel_totais,
        'sla_etapa_labels': sla_etapa_labels,
        'sla_serie_ok': sla_serie_ok,
        'sla_serie_alerta': sla_serie_alerta,
        'sla_serie_estourado': sla_serie_estourado,
        # Processos em andamento
        'processos_em_andamento': processos_em_andamento,
        # Alertas
        'alertas_sla': alertas_sla,
        # Aba "Avaliadores"
        'painel_avaliadores': montar_painel_avaliadores(request),
        # Aba "Comissão"
        'painel_comissao': montar_painel_comissao(),
    }
