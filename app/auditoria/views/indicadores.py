import pandas as pd
import plotly.express as px
from django.db.models import Count, DecimalField, F, Q, QuerySet, Sum, Value
from django.db.models.functions import Coalesce, ExtractYear

from auditoria.models.beneficio import ParcelaFinanceira
from djtools.utils import permission_required, rtr

from ..forms import EstoqueBeneficioFilterForm, EstoqueMonitoramentoFilterForm
from ..models import (
    Beneficio,
    BeneficioStatus,
    DetalhamentoFinanceiro,
    DetalhamentoQualitativo,
    Monitoramento,
    MonitoramentoStatus,
    NaturezaFinanceira,
    TipoBeneficio,
)


def truncar(texto, max_len=25):
    return texto if len(texto) <= max_len else texto[:max_len].rstrip() + '...'


def _generate_status_chart_base(queryset, status_choices, config, status_field='status'):
    status_data = queryset.values(status_field).annotate(count=Count('id'))
    if status_data:
        status_labels = [status_choices[status['status']] for status in status_data]
        status_counts = [status['count'] for status in status_data]
        y_max = max(status_counts) * 1.1 if status_counts else 1

        fig = px.bar(x=status_labels, y=status_counts, labels={'x': 'Status', 'y': 'Quantidade'})
        fig.update_layout(width=500, height=400, bargap=0.2, yaxis={'range': [0, y_max]})
        fig.update_traces(
            hovertemplate='Status: %{x}<br>Quantidade: %{y}<extra></extra>',
            text=status_counts,
            textposition='outside',
            marker={'opacity': 0.5},
            hoverlabel={'bgcolor': 'lightyellow'},
        )
    else:
        fig = px.bar(x=['Sem dados'], y=[0], labels={'x': 'Status', 'y': 'Quantidade'})
        fig.update_layout(width=500, height=400, title='Nenhum dado disponível')

    fig.update_layout(autosize=True)
    return fig.to_html(full_html=False, config=config)


def generate_status_chart_monitoramento(monitoramentos, config):
    return _generate_status_chart_base(monitoramentos, MonitoramentoStatus.CHOICES, config)


def _generate_campus_chart_base(queryset, campus_field, config):
    data = queryset.annotate(campus=F(campus_field)).values('campus').annotate(count=Count('id')).order_by('-count')

    if data:
        campus_labels = [item['campus'] for item in data]
        campus_counts = [item['count'] for item in data]
        labels = {'x': 'Quantidade', 'y': 'Campus'}

        fig = px.bar(x=campus_counts, y=campus_labels, orientation='h', labels=labels)
        total_barras = len(campus_labels)
        altura_grafico = 800
        altura_por_label = 30
        nticks_ideal = max(2, min(int(altura_grafico / altura_por_label), total_barras))

        fig.update_layout(
            height=altura_grafico,
            xaxis={'tickangle': -45, 'automargin': True},
            yaxis={'categoryorder': 'total ascending', 'automargin': True, 'gridcolor': 'lightgray', 'gridwidth': 1.5, 'nticks': nticks_ideal},
        )
        fig.update_traces(
            cliponaxis=False,
            text=campus_counts,
            textposition='inside',
            textfont={'size': 14, 'color': 'white'},
            insidetextanchor='middle',
        )
    else:
        fig = px.bar(x=['Sem dados'], y=[0], labels={'x': 'Status', 'y': 'Quantidade'})
        fig.update_layout(height=400, title='Nenhum dado disponível')

    fig.update_layout(autosize=True)
    return fig.to_html(full_html=False, config=config)


def generate_campus_chart_monitoramento(monitoramentos, config):
    return _generate_campus_chart_base(monitoramentos, 'unidade__uo__sigla', config)


def _generate_pie_chart_base(queryset, label_filters, config, empty_label='Sem dados'):
    """
    label_filters: dict[str, dict] - exemplo:
        {
            "Concluído": {"status": MonitoramentoStatus.CONCLUIDO},
            "Pendente": {"status__in": [MonitoramentoStatus.PENDENTE, MonitoramentoStatus.EM_ANDAMENTO]},
            "Cancelado": {"status": MonitoramentoStatus.CANCELADO},
        }
    """
    total_count = queryset.count()
    data = {'Status': [], 'Quantidade': []}

    for label, filtro in label_filters.items():
        count = queryset.filter(**filtro).count()
        data['Status'].append(label)
        data['Quantidade'].append(count)

    if total_count > 0 and any(q > 0 for q in data['Quantidade']):
        df = pd.DataFrame(data)
        fig = px.pie(df, names='Status', values='Quantidade', color='Status')
        fig.update_layout(legend={'orientation': 'h', 'y': -0.2, 'x': 0.5, 'xanchor': 'center'})
    else:
        fig = px.pie(names=[empty_label], values=[1], color_discrete_sequence=['gray'])
        fig.update_layout(title='Nenhum dado disponível')
    fig.update_layout(autosize=True)
    return fig.to_html(full_html=False, config=config)


def generate_pie_chart_monitoramento(monitoramentos, config):
    label_filters = {
        'Concluído': {'status': MonitoramentoStatus.CONCLUIDO},
        'Pendente': {'status__in': [MonitoramentoStatus.EM_MONITORAMENTO]},
        'Cancelado': {'status': MonitoramentoStatus.CANCELADO},
    }
    return _generate_pie_chart_base(monitoramentos, label_filters, config, empty_label='Sem informações')


def _generate_line_chart_base(queryset, ano_field, config):
    data = queryset.annotate(ano=F(ano_field)).values('ano').annotate(count=Count('id')).order_by('ano')
    df = pd.DataFrame(list(data))

    if not df.empty:
        fig = px.line(df, x='ano', y='count', labels={'ano': 'Ano', 'count': 'Número de Recomendações'})
        fig.update_traces(mode='lines+markers+text', text=df['count'], textposition='top center')
        fig.update_layout(margin={'l': 20, 'r': 20, 't': 50, 'b': 50})
        fig.update_xaxes(tickmode='linear')
        fig.update_layout(autosize=True)
        return fig.to_html(full_html=False, config=config)
    else:
        return '<p>Sem dados para exibir</p>'


def generate_line_chart_monitoramento(monitoramentos, config):
    return _generate_line_chart_base(monitoramentos, 'recomendacao__relatorio__ano__ano', config)


def _generate_grouped_bar_chart_base(queryset, ano_field, auditor_field, config):
    data = queryset.annotate(ano=F(ano_field), auditor=F(auditor_field)).values('ano', 'auditor').annotate(count=Count('id')).order_by('ano')
    df = pd.DataFrame(list(data))

    if not df.empty:
        fig = px.bar(
            df,
            x='ano',
            y='count',
            color='auditor',
            barmode='group',
            labels={'ano': 'Ano', 'count': 'Número de Recomendações', 'auditor': 'Auditor'},
            color_discrete_sequence=px.colors.qualitative.Vivid + px.colors.qualitative.Bold,
        )

        fig.update_layout(
            height=800,
            margin={'l': 20, 'r': 20, 't': 50, 'b': 50},
            xaxis_title='Ano',
            yaxis_title='Número de Recomendações',
            bargap=0.01,
            bargroupgap=0.05,
            font={'size': 14},
            legend={'orientation': 'h', 'yanchor': 'top', 'y': -0.2, 'xanchor': 'center', 'x': 0.5},
        )
        fig.update_layout(autosize=True)
        fig.update_xaxes(tickmode='linear')
        fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='LightGray')
        fig.update_traces(textposition='auto', textfont_size=18, marker_line_width=1.5, marker_line_color='black')
        fig.update_layout(autosize=True)
        return fig.to_html(full_html=False, config=config)
    else:
        return '<p>Sem dados para exibir</p>'


def generate_grouped_bar_chart_monitoramento(monitoramentos, config):
    return _generate_grouped_bar_chart_base(
        monitoramentos, ano_field='recomendacao__relatorio__ano__ano', auditor_field='recomendacao__monitor__pessoa__nome_usual', config=config
    )


@rtr('auditoria/templates/dashboard/monitoramentos.html')
@permission_required('comum.is_auditor')
def dashboard_monitoramento_view(request):
    title = 'Dashboard de Monitoramento da Recomendações'
    form = EstoqueMonitoramentoFilterForm(request.GET or None)
    monitoramentos = Monitoramento.objects.all()
    if form.is_valid():
        monitoramentos = form.filter_queryset(monitoramentos)

    recomendacoes = monitoramentos.aggregate(
        concluidos=Count('id', filter=Q(status=MonitoramentoStatus.CONCLUIDO)),
        finalizados=Count('id', filter=Q(status=MonitoramentoStatus.FINALIZADO)),
        pendentes=Count(
            'id',
            filter=Q(
                status__in=[
                    MonitoramentoStatus.EM_MONITORAMENTO,
                    MonitoramentoStatus.AGUARDANDO_REVISAO,
                    MonitoramentoStatus.EM_REVISAO,
                    MonitoramentoStatus.REVISADO,
                ]
            ),
        ),
    )

    config = {
        'displayModeBar': True,  # Exibir a barra de ferramentas
        'showLink': False,  # Remover link externo
        'displaylogo': False,  # Remove o logotipo "Produced with Plotly
    }

    total_recomendacoes = monitoramentos.count()
    graph1 = generate_status_chart_monitoramento(monitoramentos, config)
    graph2 = generate_campus_chart_monitoramento(monitoramentos, config)
    graph3 = generate_pie_chart_monitoramento(monitoramentos, config)
    graph4 = generate_line_chart_monitoramento(monitoramentos, config)
    graph5 = generate_grouped_bar_chart_monitoramento(monitoramentos, config)

    #
    return locals()


def generate_status_chart_beneficio(beneficios, config):
    return _generate_status_chart_base(beneficios, BeneficioStatus.CHOICES, config)


def generate_pie_chart_conclusao_beneficio(beneficios, config):
    label_filters = {
        'Concluído': {'status': BeneficioStatus.CONCLUIDO},
        'Não Concluído': {'status': BeneficioStatus.FINALIZADO},
        'Em Monitoramento': {'status': BeneficioStatus.EM_MONITORAMENTO},
    }
    return _generate_pie_chart_base(beneficios, label_filters, config)


def generate_pie_chart_tipo_beneficio(beneficios, config):
    label_filters = {
        'Financeiro': {'tipo': TipoBeneficio.FINANCEIRO},
        'Qualitativo': {'tipo': TipoBeneficio.QUALITATIVO},
    }
    return _generate_pie_chart_base(beneficios, label_filters, config, empty_label='Sem informações')


def generate_valor_planejado_efetivo_chart(beneficios, config=None):
    # Carrega os dados dos benefícios financeiros com parcelas relacionadas
    qs = DetalhamentoFinanceiro.objects.filter(beneficio__in=beneficios).select_related('beneficio').prefetch_related('parcelas')

    data = []
    for detalhamento in qs:
        beneficio = detalhamento.beneficio
        valor_planejado = detalhamento.valor_beneficio
        valor_efetivo = detalhamento.total_efetivo()

        data.append(
            {
                'Benefício': f'{beneficio.id}',
                'Planejado': float(valor_planejado),
                'Efetivo': float(valor_efetivo),
            }
        )

    df = pd.DataFrame(data)

    if df.empty:
        return '<p>Sem dados para exibir</p>'

    # Transforma para gráfico agrupado
    df_long = df.melt(id_vars='Benefício', value_vars=['Planejado', 'Efetivo'], var_name='Tipo', value_name='Valor')

    fig = px.bar(df_long, x='Benefício', y='Valor', color='Tipo', barmode='group', labels={'Valor': 'Valor (R$)'})

    fig.update_layout(
        xaxis_tickangle=-45,
        margin={'l': 30, 'r': 30, 't': 60, 'b': 200},
        height=600,
    )

    fig.update_traces(texttemplate='R$ %{y:,.2f}', textposition='outside')
    fig.update_layout(autosize=True)
    return fig.to_html(full_html=False, config=config)


def generate_valor_planejado_efetivo_agg_chart(beneficios, config=None):
    qs = DetalhamentoFinanceiro.objects.filter(beneficio__in=beneficios).select_related('beneficio').prefetch_related('parcelas')

    total_planejado = 0
    total_efetivo = 0

    for detalhamento in qs:
        total_planejado += detalhamento.valor_beneficio or 0
        total_efetivo += detalhamento.total_efetivo() or 0

    if total_planejado == 0 and total_efetivo == 0:
        return '<p>Sem dados para exibir</p>'

    df = pd.DataFrame({'Tipo': ['Planejado', 'Efetivo'], 'Valor': [float(total_planejado), float(total_efetivo)]})

    fig = px.bar(df, x='Tipo', y='Valor', color='Tipo', text='Valor', labels={'Valor': 'Valor (R$)'})

    fig.update_layout(
        xaxis_title='',  # Remove o título do eixo x
        xaxis={'type': 'category', 'showgrid': False},  # Força categórico e remove a grade
        height=500,
        margin={'l': 30, 'r': 30, 't': 60, 'b': 60},
    )

    fig.update_traces(texttemplate='R$ %{y:,.2f}', textposition='outside')
    fig.update_layout(autosize=True)
    return fig.to_html(full_html=False, config=config)


def graph_qualitativo_por_unidade(beneficios, config=None):
    qs = (
        DetalhamentoQualitativo.objects.filter(beneficio__in=beneficios)
        .values('unidade_afetada__nome')
        .annotate(total=Count('id'))
        .order_by('-total')
    )
    if not qs:
        return '<p>Sem dados disponíveis</p>'

    df = pd.DataFrame(list(qs))
    fig = px.bar(df, x='unidade_afetada__nome', y='total', labels={'unidade_afetada__nome': 'Unidade', 'total': 'Total'}, title='')
    fig.update_layout(
        xaxis_tickangle=-45,
        height=500,
        margin={'l': 30, 'r': 30, 't': 60, 'b': 60},
    )
    fig.update_layout(autosize=True)
    return fig.to_html(full_html=False, config=config)


def graph_qualitativo_por_estrategia(beneficios, config=None):
    qs = (
        DetalhamentoQualitativo.objects.filter(beneficio__in=beneficios)
        .values('alcance_estrategico__descricao')
        .annotate(total=Count('id'))
        .order_by('-total')
    )
    if not qs:
        return '<p>Sem dados disponíveis</p>'

    df = pd.DataFrame(list(qs))
    fig = px.pie(df, names='alcance_estrategico__descricao', values='total', title='')
    fig.update_layout(
        height=500,
        margin={'t': 60, 'b': 60},
        legend={'orientation': 'h', 'y': -0.2, 'x': 0.5, 'xanchor': 'center'},
    )
    fig.update_layout(autosize=True)
    return fig.to_html(full_html=False, config=config)


def generate_bar_chart_por_natureza_ano(beneficios, config=None):
    qs = (
        ParcelaFinanceira.objects.filter(
            detalhamento__beneficio__in=beneficios,
            data_pagamento__isnull=False,
        )
        .annotate(ano=ExtractYear('data_pagamento'))
        .values('ano', 'detalhamento__natureza')
        .annotate(total=Coalesce(Sum('valor_efetivo'), Value(0), output_field=DecimalField()))
    )

    data = list(qs)
    if not data:
        return '<p>Sem dados para exibir</p>'

    df = pd.DataFrame(data)

    # Mapeia os valores da natureza para label legível
    natureza_labels = dict(NaturezaFinanceira.choices)
    df['Natureza'] = df['detalhamento__natureza'].map(natureza_labels)

    # Pivot para garantir que todos os anos tenham as duas naturezas
    pivot_df = df.pivot_table(index='ano', columns='Natureza', values='total', aggfunc='sum', fill_value=0).reset_index()
    # Garante que TODAS as naturezas esperadas estejam como colunas (até se não existirem)
    for natureza in natureza_labels.values():
        if natureza not in pivot_df.columns:
            pivot_df[natureza] = 0

    pivot_df = pivot_df.reset_index(drop=False)
    pivot_df = pivot_df.drop(columns=['index'])

    # Transforma o pivot para formato long para plotly
    df_long = pivot_df.melt(id_vars='ano', var_name='Natureza', value_name='Valor')
    df_long['ano'] = df_long['ano'].astype(str)  # força eixo X categórico

    fig = px.bar(
        df_long,
        x='ano',
        y='Valor',
        color='Natureza',
        barmode='group',
        labels={'ano': 'Ano', 'Valor': 'Valor (R$)', 'Natureza': 'Tipo de Gasto'},
        title='',
    )
    fig.update_xaxes(type='category')  # reforça que o eixo X é categórico
    fig.update_layout(
        height=500,
        xaxis_title='Ano',
        yaxis_title='Valor (R$)',
        margin={'l': 30, 'r': 30, 't': 60, 'b': 60},
    )
    fig.update_traces(texttemplate='R$ %{y:,.2f}', textposition='outside')
    fig.update_layout(autosize=True)
    return fig.to_html(full_html=False, config=config)


def generate_line_chart_por_natureza_ano(beneficios, config=None):
    qs = (
        ParcelaFinanceira.objects.filter(
            detalhamento__beneficio__in=beneficios,
            data_pagamento__isnull=False,
        )
        .annotate(ano=ExtractYear('data_pagamento'))
        .values('ano', 'detalhamento__natureza')
        .annotate(total=Coalesce(Sum('valor_efetivo'), Value(0), output_field=DecimalField()))
    )

    data = list(qs)
    if not data:
        return '<p>Sem dados para exibir</p>'

    df = pd.DataFrame(data)

    # Mapeia os valores da natureza para labels legíveis
    natureza_labels = dict(NaturezaFinanceira.choices)
    df['Natureza'] = df['detalhamento__natureza'].map(natureza_labels)

    # Pivot para garantir que todos os anos tenham as duas naturezas
    pivot_df = df.pivot_table(index='ano', columns='Natureza', values='total', aggfunc='sum', fill_value=0).reset_index()
    for natureza in natureza_labels.values():
        if natureza not in pivot_df.columns:
            pivot_df[natureza] = 0

    pivot_df = pivot_df.reset_index(drop=True)

    # Transforma o pivot para formato long para plotly
    df_long = pivot_df.melt(id_vars='ano', var_name='Natureza', value_name='Valor')
    df_long['ano'] = df_long['ano'].astype(str)  # eixo y será categórico agora

    fig = px.line(
        df_long,
        y='ano',
        x='Valor',
        color='Natureza',
        markers=True,
        labels={'ano': 'Ano', 'Valor': 'Valor (R$)', 'Natureza': 'Tipo de Gasto'},
        title='',
    )

    fig.update_layout(
        height=500,
        yaxis_title='Ano',
        xaxis_title='Valor (R$)',
        margin={'l': 30, 'r': 30, 't': 60, 'b': 60},
        autosize=True,
    )

    fig.update_traces(mode='lines+markers', line_shape='linear')
    return fig.to_html(full_html=False, config=config)


def generate_chart_por_estrategia_por_ano(beneficios, config=None):
    qs = (
        DetalhamentoQualitativo.objects.filter(beneficio__in=beneficios)
        .values('beneficio__ano', 'alcance_estrategico__descricao')
        .annotate(total=Count('id'))
        .order_by('beneficio__ano', 'alcance_estrategico__descricao')
    )

    data = list(qs)
    if not data:
        return '<p>Sem dados disponíveis</p>'

    df = pd.DataFrame(data)
    df.rename(columns={'beneficio__ano': 'Ano', 'alcance_estrategico__descricao': 'Estratégia', 'total': 'Total'}, inplace=True)

    df['Ano'] = df['Ano'].astype(str)  # Garante que o eixo X será categórico

    fig = px.bar(
        df,
        x='Ano',
        y='Total',
        color='Estratégia',
        barmode='group',
        labels={'Ano': 'Ano', 'Total': 'Qtd de Benefícios', 'Estratégia': 'Alcance Estratégico'},
        title='Evolução dos Benefícios Qualitativos por Estratégia',
    )

    fig.update_layout(height=500, margin={'l': 30, 'r': 30, 't': 60, 'b': 60}, xaxis={'type': 'category'})
    fig.update_traces(textposition='outside', texttemplate='%{y}')
    fig.update_layout(autosize=True)
    return fig.to_html(full_html=False, config=config)


def generate_chart_relacional_unidade_estrategia(beneficios, config=None):
    qs = (
        DetalhamentoQualitativo.objects.filter(beneficio__in=beneficios)
        .values('unidade_afetada__nome', 'alcance_estrategico__descricao')
        .annotate(total=Count('id'))
    )

    data = list(qs)
    if not data:
        return '<p>Sem dados para exibir</p>'

    df = pd.DataFrame(data)
    df.rename(columns={'unidade_afetada__nome': 'Unidade', 'alcance_estrategico__descricao': 'Estratégia', 'total': 'Total'}, inplace=True)

    df['Unidade'] = df['Unidade'].apply(truncar)
    df['Estratégia'] = df['Estratégia'].apply(truncar)

    fig = px.density_heatmap(
        df,
        x='Unidade',
        y='Estratégia',
        z='Total',
        color_continuous_scale='Blues',
        text_auto=True,
        labels={'Unidade': 'Unidade Afetada', 'Estratégia': 'Alcance Estratégico', 'Total': 'Qtd de Benefícios'},
        title='',
    )
    fig.update_coloraxes(colorbar_title=None)
    # Exibe hover com os nomes originais
    fig.update_traces(hovertemplate='<b>Unidade</b>: %{x}<br><b>Estratégia</b>: %{y}<br><b>Total</b>: %{z}<extra></extra>')
    fig.update_layout(
        xaxis={'tickangle': -45, 'automargin': True},
        yaxis={'automargin': True},
        height=600,
        margin={'l': 40, 'r': 40, 't': 80, 'b': 100},
        xaxis_tickangle=-45,
    )
    fig.update_layout(autosize=True)
    return fig.to_html(full_html=False, config=config)


def generate_chart_evolucao_por_tipo(beneficios: QuerySet[Beneficio], config: dict[str, bool] | None = None) -> str:
    TIPOS_DICT = {
        TipoBeneficio.FINANCEIRO: 'Financeiro',
        TipoBeneficio.QUALITATIVO: 'Qualitativo',
    }

    # Consulta com anotação
    qs = beneficios.values('ano', 'tipo').annotate(total=Count('id'))

    data = list(qs)
    if not data:
        return '<p>Sem dados para exibir</p>'

    # Converte para DataFrame
    df = pd.DataFrame.from_records(data)

    # Cria DataFrame com todas as combinações ano x tipo
    anos = sorted(df['ano'].unique())  # ordena os anos
    tipos = list(TIPOS_DICT.keys())
    all_combinations = pd.MultiIndex.from_product([anos, tipos], names=['ano', 'tipo']).to_frame(index=False)

    # Faz merge com os dados reais
    df_complete = pd.merge(all_combinations, df, on=['ano', 'tipo'], how='left')
    df_complete['total'] = df_complete['total'].fillna(0).astype(int)

    # Mapeia nomes dos tipos
    df_complete['tipo_nome'] = df_complete['tipo'].map(lambda t: TIPOS_DICT.get(t, 'Desconhecido'))

    # Garante que ano seja string para o eixo X categórico
    df_complete['ano'] = df_complete['ano'].astype(str)
    df_complete = df_complete.sort_values(by=['ano', 'tipo'])

    # Gera gráfico
    fig = px.line(
        df_complete,
        x='ano',
        y='total',
        color='tipo_nome',
        markers=True,
        labels={'ano': 'Ano', 'total': 'Quantidade', 'tipo_nome': 'Tipo de Benefício'},
        title='Evolução de Benefícios por Tipo e Ano',
    )
    fig.update_traces(mode='lines+markers+text', textposition='top center')
    fig.update_xaxes(type='category', tickmode='linear')
    fig.update_layout(legend_title_text='Tipo de Benefício', autosize=True)

    return fig.to_html(full_html=False, config=config)


@rtr('auditoria/templates/dashboard/beneficios.html')
@permission_required('comum.is_auditor')
def dashboard_beneficio_view(request):
    title = 'Dashboard de Benefícios'

    beneficios_qs = Beneficio.objects.all()
    form = EstoqueBeneficioFilterForm(request.GET or None)
    if form.is_valid():
        beneficios_qs = form.filter_queryset(beneficios_qs)
    # Configurando os gráficos.
    config = {
        'displayModeBar': True,  # Exibir a barra de ferramentas
        'showLink': False,  # Remover link externo
        'displaylogo': False,  # Remove o logotipo "Produced with Plotly
    }
    beneficios = beneficios_qs.aggregate(
        concluidos=Count('id', filter=Q(status=BeneficioStatus.CONCLUIDO)),
        finalizados=Count('id', filter=Q(status=BeneficioStatus.FINALIZADO)),
        pendentes=Count(
            'id',
            filter=Q(
                status__in=[
                    BeneficioStatus.EM_MONITORAMENTO,
                    BeneficioStatus.PLANEJADO,
                ]
            ),
        ),
    )
    total_beneficios = beneficios_qs.count()
    total_beneficios_qualitativos = beneficios_qs.filter(tipo=TipoBeneficio.QUALITATIVO).count()
    totais_por_natureza = (
        DetalhamentoFinanceiro.objects.filter(beneficio__in=beneficios_qs)
        .values('natureza')
        .annotate(total=Coalesce(Sum('parcelas__valor_efetivo'), Value(0), output_field=DecimalField()))
    )

    # Converte direto em dicionário com valores por natureza
    totais_dict = {item['natureza']: item['total'] for item in totais_por_natureza}

    # Extrai com fallback zero
    total_recuperado = totais_dict.get(NaturezaFinanceira.RECUPERADO, 0)
    total_evitado = totais_dict.get(NaturezaFinanceira.EVITADO, 0)
    total_beneficios_financeiros = total_recuperado + total_evitado

    beneficios_por_unidade = (
        DetalhamentoQualitativo.objects.filter(beneficio__in=beneficios_qs)
        .values('unidade_afetada__nome')
        .annotate(total=Count('id'))
        .order_by('-total')
    )
    total_beneficios_unidade = sum(item['total'] for item in beneficios_por_unidade)

    beneficios_por_estrategia = (
        DetalhamentoQualitativo.objects.filter(beneficio__in=beneficios_qs)
        .values('alcance_estrategico__descricao')
        .annotate(total=Count('id'))
        .order_by('-total')
    )
    total_beneficios_por_estrategia = sum(item['total'] for item in beneficios_por_estrategia)
    # Benefícios - Status e Tipos
    chart_status_por_etapa = generate_status_chart_beneficio(beneficios_qs, config)
    chart_conclusao_porcentagem = generate_pie_chart_conclusao_beneficio(beneficios_qs, config)
    chart_tipos_de_beneficio = generate_pie_chart_tipo_beneficio(beneficios_qs, config)
    chart_planejado_vs_efetivo = generate_valor_planejado_efetivo_agg_chart(beneficios_qs, config)
    # Benefícios Qualitativos
    chart_qualitativo_por_unidade = graph_qualitativo_por_unidade(beneficios_qs, config)
    chart_qualitativo_por_estrategia = graph_qualitativo_por_estrategia(beneficios_qs, config)
    chart_estrategia_por_ano = generate_chart_por_estrategia_por_ano(beneficios_qs, config)
    chart_relacao_unidade_estrategia = generate_chart_relacional_unidade_estrategia(beneficios_qs, config)
    # Benefícios Financeiros
    chart_valores_por_natureza_bar = generate_bar_chart_por_natureza_ano(beneficios_qs, config)
    chart_valores_por_natureza_linha = generate_line_chart_por_natureza_ano(beneficios_qs, config)
    chart_evolucao_por_tipo = generate_chart_evolucao_por_tipo(beneficios_qs, config)
    return locals()
