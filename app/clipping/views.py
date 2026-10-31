from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.defaultfilters import pluralize

from clipping import tasks
from clipping.forms import RelatorioForm
from clipping.models import Classificacao, PalavraChave, Publicacao, PublicacaoDigital, PublicacaoEletronica, PublicacaoImpressa, Veiculo
from djtools import layout
from djtools.html.graficos import GroupedColumnChart, PieChart
from djtools.utils import group_required, rtr, somar_dias


@layout.atribuidos_a_meus_grupos()
def index_atribuidos_a_meus_grupos(request):
    pendencias = []
    if request.user.has_group_cached('Gerente de Clipping', ignore_groups_if_superuser=False):
        publicacoes = PublicacaoDigital.objects.filter(classificacao__id__isnull=False).count()
        if publicacoes:
            pendencias.append(
                {
                    'titulo': f'Publicaç{pluralize(publicacoes, "ão,ões")} Digita{pluralize(publicacoes, "l,is")}',
                    'subtitulo': 'a classificar',
                    'qtd': publicacoes,
                    'url': '/admin/clipping/publicacaodigital/',
                }
            )

    return pendencias


@layout.quadro('Clipping', icone='newspaper', pode_esconder=True, global_cache=3600)
def index_quadros(quadro, request):
    publicacoes = (
        Publicacao.objects.filter(classificacao__id__isnull=False, classificacao__visivel=True)
        .select_related('veiculo', 'editorial', 'publicacaodigital', 'publicacaoeletronica', 'publicacaoimpressa')
        .order_by('-data')[0:5]
    )
    for publicacao in publicacoes:
        chapeu = '{} {}'.format(publicacao.data.strftime('%d/%m/%Y'), publicacao.veiculo)
        if publicacao.editorial:
            chapeu += f' ({publicacao.editorial})'
        quadro.add_item(
            layout.ItemNoticia(
                titulo=publicacao.titulo,
                url=publicacao.get_link(),
                chapeu=chapeu,
            )
        )
    return quadro


@rtr()
@group_required('Gerente de Clipping')
def player(request, publicacao_id):
    publicacao = get_object_or_404(PublicacaoEletronica.objects, pk=publicacao_id)
    eh_video = publicacao.arquivo.name.lower().endswith(('.mp4', '.mov', '.avi', '.wmv', '.flv', '.webm'))
    eh_audio = publicacao.arquivo.name.lower().endswith(('.mp3', '.wav', '.wma', '.aac', '.ogg'))
    return locals()


@group_required('Gerente de Clipping')
def importar(request):
    return tasks.importar()


@group_required('Gerente de Clipping')
def classificar(request, publicacao_id, classificacao_id):
    publicacao = PublicacaoDigital.objects.get(pk=publicacao_id)
    if classificacao_id:
        classificacao = Classificacao.objects.get(pk=classificacao_id)
        publicacao.classificacao = classificacao
        publicacao.save()
    return HttpResponse('OK')


@rtr()
@login_required()
def index(request):
    pds = Publicacao.objects.filter(classificacao__id__isnull=False).exclude(classificacao__id=4).order_by('-data')
    return locals()


@rtr()
@group_required('Gerente de Clipping')
def relatorio_periodo(request):
    title = 'Relatório por Período'
    form = RelatorioForm(data=request.POST or None)
    if form.is_valid():
        d = {}
        uo = form.cleaned_data['uo']
        data_inicio = form.cleaned_data['data_inicio']
        data_fim = form.cleaned_data['data_fim']
        omitir_graficos = form.cleaned_data['omitir_graficos']
        data_fim = somar_dias(data_fim, 1)
        data_inicio_sql = data_inicio.strftime('%Y-%m-%d')
        data_fim_sql = data_fim.strftime('%Y-%m-%d')
        title = 'Clipagem do período {} à {}'.format(data_inicio.strftime('%d/%m/%Y'), data_fim.strftime('%d/%m/%Y'))

        queries = []
        series = []
        ps = Publicacao.objects.filter(data__gte=data_inicio, data__lte=data_fim, classificacao__id__isnull=False, classificacao__visivel=True)
        if uo:
            title = f'{title} ({uo.nome})'
            ps = ps.filter(uos=uo)
        for classificacao in Classificacao.objects.filter(visivel=True):
            series.append([classificacao.descricao, ps.filter(classificacao__id=classificacao.id).count()])
        queries.append(['Quantitativo de Inserções por Classificação', 'Total de publicações por classificação', series])

        series = []
        for veiculo in Veiculo.objects.all():
            n = ps.filter(veiculo__id=veiculo.id).count()
            if n:
                series.append([veiculo.nome, n])
        queries.append(['Quantitativo de Inserções por Veículo', 'Total de publicações por veículo', series])

        series = []
        for palavra_chave in PalavraChave.objects.all():
            n = ps.filter(palavras_chaves__id=palavra_chave.id).count()
            if n:
                series.append([palavra_chave.descricao, n])
        queries.append(['Quantitativo de Inserções por Palavras-Chaves', 'Total de publicações por palavras-chaves', series])

        for query in queries:
            series = query[2]
            grafico = PieChart(f'grafico{len(d):d}', title=query[0], subtitle=query[1], minPointLength=0, data=series)
            grafico.id = f'grafico{len(d):d}'
            d[len(d)] = grafico

        series = []
        veiculos = Veiculo.objects.all()
        if uo:
            ps = ps.filter(uos=uo)
        for veiculo in veiculos:
            if ps.filter(veiculo__id=veiculo.id).exists():
                series.append(
                    [
                        veiculo.nome,
                        ps.filter(classificacao__descricao='Positivo', veiculo__id=veiculo.id).count(),
                        ps.filter(classificacao__descricao='Negativo', veiculo__id=veiculo.id).count(),
                        ps.filter(classificacao__descricao='Neutro', veiculo__id=veiculo.id).count(),
                    ]
                )
        grafico = GroupedColumnChart(
            f'grafico{len(d):d}', title='Qualitativo de Inserções por Veículo', data=series, groups=['Positivo', 'Negativo', 'Neutro']
        )
        grafico.id = f'grafico{len(d):d}'
        d[len(d)] = grafico

        series = []
        pds = PublicacaoDigital.objects.filter(
            data__gte=data_inicio, data__lte=data_fim, classificacao__id__isnull=False, classificacao__visivel=True
        )
        if uo:
            pds = pds.filter(uos=uo)
        series.append(
            [
                'Publicação Digital',
                pds.filter(classificacao__descricao='Positivo').count(),
                pds.filter(classificacao__descricao='Negativo').count(),
                pds.filter(classificacao__descricao='Neutro').count(),
            ]
        )
        pis = PublicacaoImpressa.objects.filter(
            data__gte=data_inicio, data__lte=data_fim, classificacao__id__isnull=False, classificacao__visivel=True
        )
        if uo:
            pis = pis.filter(uos=uo)
        series.append(
            [
                'Publicação Impressa',
                pis.filter(classificacao__descricao='Positivo').count(),
                pis.filter(classificacao__descricao='Negativo').count(),
                pis.filter(classificacao__descricao='Neutro').count(),
            ]
        )
        pes = PublicacaoEletronica.objects.filter(
            data__gte=data_inicio, data__lte=data_fim, classificacao__id__isnull=False, classificacao__visivel=True
        )
        if uo:
            pes = pes.filter(uos=uo)
        series.append(
            [
                'Publicação Eletrônica',
                pes.filter(classificacao__descricao='Positivo').count(),
                pes.filter(classificacao__descricao='Negativo').count(),
                pes.filter(classificacao__descricao='Neutro').count(),
            ]
        )

        grafico = GroupedColumnChart(
            f'grafico{len(d):d}', title='Qualitativo de Inserções por Tipo de Veículo', data=series, groups=['Positivo', 'Negativo', 'Neutro']
        )
        grafico.id = f'grafico{len(d):d}'
        d[len(d)] = grafico

        if not omitir_graficos:
            graficos = [d[2], d[0], d[1], d[4]]
            graficos2 = [d[3]]
        else:
            graficos = graficos2 = []

        if pds.exists() or pis.exists() or pes.exists():
            form = None

    return locals()
