"""
Biblioteca destinada a criação de gráficos nas páginas HTML.
Utiliza a bibliotea javascript Highchart disponível em http://www.highcharts.com.
Os gráficos gerados podem ser exportados para diversos formatos, inclusive JPG, PNG e PDF.
Duas categorias de gráficos foram definidas:
    - Gráficos 1D: Possuem apenas uma dimensão e podem ser exibidos sob a forma de Pizza
                ou Rosca (possuir uma cavidade sob o eixo central).
                  São adequados para exibir totalizadores. Ex: Número de servidores por UO.
    - Gráficos 2D: Possuem duas dimensões e podem ser exibidos sob a forma de Barra (colunas
                horizontais), Coluna (colunas verticais) e Linha (linhas verticais).
                  São adequados para exibir a evolução dos dados ao longo do tempo.
                  Ex: Número de servidores por UO nos primeiro e segundo simestre de um determinado
                  ano.
A seguir serão mostrados códigos para construção de gráficos 1D e 2D respectivamente.

g1 = Pizza()
g1.set_titulo('Gráfico de Navegadores')
g1.set_subtitulo('Estatística Trimestral')
g1.formatar_dica('<b>{rotulo}</b> : {valor} %')
g1.adicionar_dado("Firefox", 30)
g1.adicionar_dado("IE", 15)
g1.configurar_legenda(30, 10, 'vertical')
g1.set_tamanho(800, 400)

g2 = Linha()
g2.set_titulo('Gráfico de Navegadores')
g2.set_subtitulo('Estatística Trimestral')
g2.formatar_dica('<b>{rotulo}</b> : {valor} %')
g2.configurar_categorias('Número de Usuários', ['Primeiro', 'Segundo', 'Terceiro', 'Quarto'])
g2.adicionar_serie('Firefox', [3, 5, 7, 2])
g2.adicionar_serie('IE', [2, 4, 9, 5])
g2.configurar_legenda(30, 10, 'vertical')
g2.set_tamanho(800, 400)
"""

import json
from datetime import timedelta

from django.template import Context, Template
from django.utils.safestring import SafeString, mark_safe

from djtools.utils import render_to_string

"""
    Classe abstrata para os gráficos 1D e 2D.
    Não deve ser instanciada.
    Possui métodos comuns a todos os gráficos.
"""


class GraficoAgendamento:
    horas = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23]

    def __init__(self, limite_inferior, limite_superior):
        self.items = []
        self.limite_inferior = limite_inferior
        self.limite_superior = limite_superior
        self.dias = []
        self.js = ''
        data = limite_inferior
        while data <= limite_superior:
            self.dias.append(data.strftime('%d/%m/%Y'))
            data = data + timedelta(1)

    def get_limite_inferior_str(self):
        return self.limite_inferior.strftime('%d/%m/%Y')

    def get_limite_superior_str(self):
        return self.limite_superior.strftime('%d/%m/%Y')

    def get_tamanho_linha(self):
        return 220 + (len(self.dias) * 120)

    def set_items(self, items):
        for item in items:
            descricao = str(item)
            if len(descricao) > 30:
                descricao = descricao[0:25] + '...'
            self.items.append([item.id, descricao])

    def __str__(self):
        return render_to_string('graficos/grafico_agendamento.html', {'grafico': self}) + SafeString('<script>' + self.js + '</script>')

    def preencher_intervalo(self, item_id, cor, data_inicio, data_fim, texto):
        dinicio = data_inicio.strftime('%d/%m/%Y')
        hinicio = data_inicio.strftime('%H:%M')
        dfim = data_fim.strftime('%d/%m/%Y')
        hfim = data_fim.strftime('%H:%M')
        # texto é livre (descrição/justificativa da viagem); interpolá-lo cru numa string
        # JS quebrava o parse quando continha aspa/quebra de linha (Sentry SUAP-TDQ/TCA).
        # json.dumps gera um literal JS válido e escapado; o replace evita que um eventual
        # "</script>" no texto feche a tag inline.
        texto_js = json.dumps(texto).replace('</', '<\\/')
        self.js += (
            "paint_div('" + cor + "', " + str(item_id) + ", '" + dinicio + "', '" + hinicio + "', '" + dfim + "', '" + hfim + "', " + texto_js + ');'
        )


TEMPLATE = """
var chart{{ id }};
// Degrada graciosamente quando o highcharts.js não carregou (ex.: rede instável
// em mobile). Sem isto, o Highcharts.setOptions() abaixo — que roda no parse do
// <script> — estoura "Can't find variable: Highcharts" e quebra a página
// (Sentry SUAP-TAD). Quando carrega normalmente, o comportamento é idêntico.
if (typeof Highcharts !== 'undefined') {
var plotOptions{{ id }} = {{ plotOptions }};

if (plotOptions{{ id }}['pie']) {
    plotOptions{{ id }}['pie']['dataLabels']['formatter'] = function() {
            return (this.point.name.length > 30 ? this.point.name.substr(0, 30) + '...' : this.point.name) + ': <b>'+
                this.y + '{% if not compact %} de '+ this.total + ' (' + this.percentage.toFixed(2) + '%) {% endif %} </b>' ;
        };
    plotOptions{{ id }}['pie']['dataLabels']['style'] = {
            fontSize: '{% if compact %}9{% else %}14{% endif %}px'
        };
}

Highcharts.setOptions({
    lang: {
        decimalPoint: ',',
        thousandsSep: '.',
        numericSymbols: null,
    }
});

$(document).ready(function() {

    // Aplicando tema
    Highcharts.theme = {
        title: {
            style: {
                color: '#555555',
            }
        },
        subtitle: {
            style: {
                color: '#777777',
            }
        },
        legend: {
            itemStyle: {
                color: '#666666',
                fontWeight: 'normal',
            }
        },
    };
    Highcharts.setOptions(Highcharts.theme);

    //Aplicando formatação padrão para o Brasil.
    Highcharts.lang = {
        lang: {
            months: ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',  'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'],
            weekdays: ['Domingo', 'Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado'],
            decimalPoint: ',',
            thousandsSep: '.',
            loading: 'Carregando...',
            numericSymbols: null,
        }
    };
    Highcharts.setOptions(Highcharts.lang);

   chart{{ id }} = new Highcharts.Chart({
      chart: {{ chart }},
      {% if colors %}colors: {{ colors }},{% endif %}
      title: {{ title }},
      legend: {{ legend }},
      subtitle: {{ subtitle }},
      plotOptions: plotOptions{{ id }},
      series: {{ series }},
      nodes: {{ nodes }},
      xAxis: {{ xAxis }},
      yAxis: {{ yAxis }},
      tooltip: {{ tooltip }},
      credits : {{ credits }},
      exporting : {
          sourceWidth: 1000,
          scale: 2
      }
   });
});
}
"""


class Chart:
    def __init__(self, renderTo, **kwargs):
        self.chart = {'renderTo': renderTo}
        self.credits = {'enabled': False}
        self.labels = {}
        self.legend = {}
        self.plotOptions = {}
        self.series = {}
        self.nodes = []
        self.title = {}
        self.subtitle = {}
        self.xAxis = {}
        self.yAxis = {}
        self.title['text'] = kwargs.get('title')
        self.subtitle['text'] = kwargs.get('subtitle')
        self.compact = kwargs.get('compact', True)
        self.tooltip = kwargs.get('tooltip', {})
        self.tooltip['crosshairs'] = kwargs.get('showCrosshairs', True)

        self.plotOptions = {
            'series': {
                'dataLabels': {'enabled': kwargs.get('showDataLabels', False), 'format': kwargs.get('format', '{point.y}')},
                'minPointLength': kwargs.get('minPointLength', 0),
            }
        }
        plotOptions = kwargs.get('plotOptions', self.plotOptions)
        self.plotOptions.update(plotOptions)

        self.yAxis = {'title': {'text': kwargs.get('yAxis_title_text', 'Total')}}

    def __str__(self):
        ctx = {}
        if not self.compact:
            self.legend = {'enabled': False}
        for key in self.__dict__:
            # O JSON vai cru dentro de <script>: um "</script>" num rótulo (título digitado pelo
            # usuário) fecharia a tag e executaria o resto como HTML.
            ctx[key] = json.dumps(getattr(self, key)).replace('</', '<\\/')
        ctx['id'] = id(self)
        ctx['compact'] = self.compact

        return mark_safe(Template(TEMPLATE).render(Context(ctx, autoescape=False)))


class PieChart(Chart):
    def __init__(self, renderTo, **kwargs):
        """
        ``data``: [['Item 1', 10], ['Item 2', 20]]
        """
        if 'data' not in kwargs:
            raise ValueError('"data" param must be supplied.')

        show_legend = kwargs.pop('show_legend') if 'show_legend' in kwargs else True

        dataLabels = {}
        if 'dataLabels_format' in kwargs:
            dataLabels['format'] = kwargs.get('dataLabels_format')

        super().__init__(renderTo, **kwargs)
        self.kind = 'PieChart'
        self.plotOptions = {'pie': {'allowPointSelect': True, 'cursor': 'pointer', 'dataLabels': dataLabels, 'showInLegend': show_legend}}
        self.series = [{'type': 'pie', 'data': kwargs['data']}]
        tooltip_pointFormat = kwargs.get('tooltip_pointFormat', '<strong>{point.y}</strong> de {point.total} ({point.percentage:.2f}%)')
        self.tooltip['pointFormat'] = tooltip_pointFormat


class ColumnChart(Chart):
    def __init__(self, renderTo, **kwargs):
        """
        ``data``: [['Item 1', 10], ['Item 2', 20]]
        ``minPointLength``: 0
            Indica a altura mínima em pixels (mesmo se for valor zero)
        """
        if 'data' not in kwargs:
            raise ValueError('"data" param must be supplied.')

        super().__init__(renderTo, **kwargs)
        self.kind = 'ColumnChart'
        self.chart['defaultSeriesType'] = 'column'
        categories = []
        for i in kwargs['data']:
            if isinstance(i, dict):
                categories.append(i['name'])
            else:
                categories.append(i[0])
        self.xAxis = {'categories': categories}
        self.yAxis['title'] = {'text': 'Total'}
        self.series = [{'name': 'Total', 'data': kwargs['data']}]
        self.legend = {'enabled': False}


class BarChart(Chart):
    def __init__(self, renderTo, **kwargs):
        """
        ``data``: [['Item 1', 10], ['Item 2', 20]]
        ``minPointLength``: 0
            Indica a altura mínima em pixels (mesmo se for valor zero)
        """
        if 'data' not in kwargs:
            raise ValueError('"data" param must be supplied.')

        super().__init__(renderTo, **kwargs)
        self.kind = 'ColumnChart'
        self.chart['defaultSeriesType'] = 'bar'
        self.xAxis = {'categories': [i[0] for i in kwargs['data']]}
        self.yAxis['title'] = {'text': 'Total'}
        self.series = [{'name': 'Total', 'data': [i[1] for i in kwargs['data']]}]
        self.legend = {'enabled': False}


class GroupedColumnChart(Chart):
    def __init__(self, renderTo, **kwargs):
        # groups: ['Jan', 'Fev', 'Mar']
        # data: [['Store A', 10, 15, 20], ['Store B', 20, 25, 30], ['Store C', 30, 35, 40]]
        if 'data' not in kwargs:
            raise ValueError('"data" param must be supplied.')
        if 'groups' not in kwargs:
            raise ValueError('"groups" param must be supplied.')

        super().__init__(renderTo, **kwargs)
        self.kind = 'GroupedColumnChart'
        self.chart['defaultSeriesType'] = 'column'
        self.xAxis = {'categories': [i[0] for i in kwargs['data']]}
        self.yAxis = {'title': {'text': kwargs.get('yAxis_title_text', 'Total')}}

        disabled_groups = kwargs.get('disabled_groups', [])
        # Formatando series
        self.series = []
        for idx, category in enumerate(kwargs['groups']):
            self.series.append({'name': category, 'data': [i[idx + 1] for i in kwargs['data']], 'visible': category not in disabled_groups})


class LineChart(Chart):
    def __init__(self, renderTo, **kwargs):
        if 'data' not in kwargs:
            raise ValueError('"data" param must be supplied.')
        if 'groups' not in kwargs:
            raise ValueError('"groups" param must be supplied.')

        super().__init__(renderTo, **kwargs)
        self.kind = 'LineChart'
        self.chart['defaultSeriesType'] = 'line'
        self.xAxis = {'categories': [i[0] for i in kwargs['data']]}

        self.yAxis = {'title': {'text': kwargs.get('yAxis_title_text', 'Total')}}
        if 'yAxis_min' in kwargs:
            self.yAxis['min'] = kwargs['yAxis_min']
        if 'yAxis_max' in kwargs:
            self.yAxis['max'] = kwargs['yAxis_max']

        self.plotOptions['line'] = {
            'dataLabels': {
                'enabled': kwargs.get('plotOptions_line_dataLabels_enable', False),
                'enableMouseTracking': kwargs.get('plotOptions_line_enableMouseTracking', False),
            }
        }

        # Formatando series
        self.series = []
        for idx, category in enumerate(kwargs['groups']):
            self.series.append({'name': category, 'data': [i[idx + 1] for i in kwargs['data']]})


class StackedGroupedColumnChart(GroupedColumnChart):
    def __init__(self, renderTo, **kwargs):
        # groups: ['Jan', 'Fev', 'Mar']
        # data: [['Store A', 10, 15, 20], ['Store B', 20, 25, 30], ['Store C', 30, 35, 40]]
        super().__init__(renderTo, **kwargs)
        if 'column' not in self.plotOptions:
            self.plotOptions['column'] = {}

        self.plotOptions['column']['stacking'] = 'percent'
