import html
from calendar import HTMLCalendar
from collections import OrderedDict
from datetime import date, datetime, timedelta

from django.utils.safestring import mark_safe
import pydantic
from ninja.schema import Schema

from djtools.utils import daterange, get_datetime_now


class Calendario(HTMLCalendar):
    meses_extenso = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
    eventos = OrderedDict()
    eventos_por_mes = OrderedDict()
    tipos_eventos_calendario = OrderedDict()
    mostrar_mes_ano_cabecalho_mes = False

    def adicionar_tipo_evento(self, css, tipo_evento):
        if css not in self.tipos_eventos_calendario:
            self.tipos_eventos_calendario[css] = str(tipo_evento)

    def resetar_listas(self):
        self.eventos = OrderedDict()
        self.eventos_por_mes = OrderedDict()
        self.tipos_eventos_calendario = OrderedDict()
        # self.tipos_eventos_calendario['hoje'] = 'Hoje'
        if self.tipos_eventos_default:
            self.tipos_eventos_calendario['evento'] = 'Evento/Data Comemorativa'
            self.tipos_eventos_calendario['extra'] = 'Liberação Por Documento Legal / Parcial'
            self.tipos_eventos_calendario['ferias'] = 'Férias'
            self.tipos_eventos_calendario['recesso'] = 'Recesso'
            self.tipos_eventos_calendario['feriado'] = 'Feriado'
            self.tipos_eventos_calendario['extra5'] = 'Cronograma da Folha'
            self.tipos_eventos_calendario['afastamento'] = 'Afastamento'

    def __init__(self, firstweekday=6, tipos_eventos_default=True):
        self.firstweekday = firstweekday
        self.tipos_eventos_default = tipos_eventos_default
        self.tipos_eventos_usados = set()
        self.resetar_listas()
        self.escape_html = True

    def retirar_numeros_string(self, valor):
        for num in range(10):
            valor = valor.replace(str(num), '')
        return valor

    def adicionar_evento_calendario(self, data_inicio, data_fim, descricao, css_class, title=''):
        hoje = get_datetime_now().date()
        data_fim = data_fim or (hoje + timedelta(days=365))
        self.tipos_eventos_usados.add(css_class)
        """
        Metodo que montará o evento no calendario.
        """
        # Tratamento do CSS
        for data in daterange(data_inicio, data_fim):
            if self.eventos.get(str(data)):
                if css_class not in self.eventos.get(str(data))['css']:
                    self.eventos[str(data)]['css'] += ' ' + css_class
                else:
                    padrao_css = self.retirar_numeros_string(css_class)
                    if f'{padrao_css} extra6' not in self.eventos.get(str(data))['css']:
                        self.eventos[str(data)]['css'] += f' {padrao_css} extra6'
                    elif f'{padrao_css}_conflito_varios' not in self.eventos.get(str(data))['css']:
                        self.eventos[str(data)]['css'] += f' {padrao_css}_conflito_varios'

                self.eventos[str(data)]['title'] += f' | {title}'
            else:
                self.eventos[str(data)] = {'data': data, 'css': css_class, 'title': title}

        if self.escape_html:
            descricao = html.escape(descricao)
        else:
            descricao = mark_safe(descricao)
        # Tratamento dos Eventos Verificar se as datas inicial e final estao no mesmo mês e ano
        if data_inicio and data_fim:
            if data_inicio.year == data_fim.year:
                if data_inicio.month == data_fim.month:
                    ano_mes = str(data_inicio.year) + str(data_inicio.month)
                    if not self.eventos_por_mes.get(ano_mes):
                        self.eventos_por_mes[ano_mes] = []
                    self.eventos_por_mes[ano_mes].append(
                        {'data_inicio': data_inicio, 'data_fim': data_fim, 'descricao': descricao, 'css': css_class, 'title': title}
                    )
                else:
                    for mes in range(data_inicio.month, data_fim.month + 1):
                        if not self.eventos_por_mes.get(str(data_inicio.year) + str(mes)):
                            self.eventos_por_mes[str(data_inicio.year) + str(mes)] = []
                        self.eventos_por_mes[str(data_inicio.year) + str(mes)].append(
                            {'data_inicio': data_inicio, 'data_fim': data_fim, 'descricao': descricao, 'css': css_class, 'title': title}
                        )
            else:
                for mes in range(data_inicio.month, 13):
                    if not self.eventos_por_mes.get(str(data_inicio.year) + str(mes)):
                        self.eventos_por_mes[str(data_inicio.year) + str(mes)] = []
                    self.eventos_por_mes[str(data_inicio.year) + str(mes)].append(
                        {'data_inicio': data_inicio, 'data_fim': data_fim, 'descricao': descricao, 'css': css_class, 'title': title}
                    )

                for mes in range(1, data_fim.month + 1):
                    if not self.eventos_por_mes.get(str(data_fim.year) + str(mes)):
                        self.eventos_por_mes[str(data_fim.year) + str(mes)] = []
                    self.eventos_por_mes[str(data_fim.year) + str(mes)].append(
                        {'data_inicio': data_inicio, 'data_fim': data_fim, 'descricao': descricao, 'css': css_class, 'title': title}
                    )

    def montar_dia(self, dia, dia_da_semana, mes, ano):
        """
        Retorna o dia como um tipo <td>
        """
        if dia == 0:
            return self.celula_do_dia('', '', '&nbsp;', dia_da_semana)
        else:
            cssclass = []
            titles = []
            hoje = datetime.now()

            if hoje.day == dia and hoje.month == mes and hoje.year == ano:
                cssclass.append('hoje')
                titles.append('Hoje')

            if dia_da_semana == 5 or dia_da_semana == 6:
                cssclass.append('fds')

            data = []
            data.append(str(dia))
            data.append(str(mes))
            data.append(str(ano))
            try:
                data = datetime.strptime('-'.join(data), '%d-%m-%Y').date()
                if self.eventos.get(str(data)):
                    cssclass.append(self.eventos[str(data)]['css'])
                    titles.append(self.eventos[str(data)].get('title') or self.eventos[str(data)]['css'].title())
            except Exception:
                pass
            return self.celula_do_dia(' '.join(cssclass), '&#13;'.join(titles), dia, dia_da_semana)  # '&#13;' quebra a linha no title

    def celula_do_dia(self, cssclass, titles, dia, dia_da_semana, conteudo=''):
        celula_dia = []
        if dia_da_semana == 0:
            semana = 'calendario-segunda'
        elif dia_da_semana == 1:
            semana = 'calendario-terca'
        elif dia_da_semana == 2:
            semana = 'calendario-quarta'
        elif dia_da_semana == 3:
            semana = 'calendario-quinta'
        elif dia_da_semana == 4:
            semana = 'calendario-sexta'
        elif dia_da_semana == 5:
            semana = 'calendario-sabado'
        elif dia_da_semana == 6:
            semana = 'calendario-domingo'
            celula_dia.append('<tr>')

        if dia:
            dia = f'<span>{dia}</span>'

        celula_dia.append(f'<td class="calendario-dia {cssclass}" title="{titles}" headers="{semana}">{dia}{conteudo}</td>')
        if dia_da_semana == 5:
            celula_dia.append('</tr>')

        return '\n'.join(celula_dia)

    def montar_calendario_mes(self, mes, ano):
        html_code = ['<div class = "calendario">']
        html_code.append('<table class="calendario-anual">')
        if self.mostrar_mes_ano_cabecalho_mes:
            html_code.append(f'<caption>{self.meses_extenso[int(mes) - 1]}/{ano}</caption>')
        else:
            html_code.append(f'<caption>{self.meses_extenso[int(mes) - 1]}</caption>')

        html_code.append('<thead>')
        html_code.append('<tr>')
        html_code.append('<th id="calendario-domingo">Dom</th>')
        html_code.append('<th id="calendario-segunda">Seg</th>')
        html_code.append('<th id="calendario-terca">Ter</th>')
        html_code.append('<th id="calendario-quarta">Qua</th>')
        html_code.append('<th id="calendario-quinta">Qui</th>')
        html_code.append('<th id="calendario-sexta">Sex</th>')
        html_code.append('<th id="calendario-sabado">Sab</th>')
        html_code.append('</tr>')
        html_code.append('</thead>')
        html_code.append('<tbody>')
        return '\n'.join(html_code)

    def fechar_calendario_mes(self):
        html_code = ['</tbody></table>']
        return '\n'.join(html_code)

    def legenda_tipos_eventos(self):
        html_code = []
        if self.tipos_eventos_usados:  # verifica se existe algum evento sendo usado
            html_code.append('<div class="legenda">')
            html_code.append('<p>Legenda:</p>')
            html_code.append('<ul>')
            for css_evento in self.tipos_eventos_calendario:
                if (
                    css_evento not in ('evento', 'extra', 'ferias', 'recesso', 'feriado', 'extra5', 'afastamento')
                    or css_evento in self.tipos_eventos_usados
                ):
                    html_code.append(
                        f'<li class="{css_evento}"><span class="visually-hidden">{css_evento}</span> {self.tipos_eventos_calendario.get(css_evento)}</li>'
                    )
            html_code.append('</ul>')
            html_code.append('</div>')
        return '\n '.join(html_code)

    def fechar_div_calendario_mes(self):
        html_code = ['</div>']
        return '\n'.join(html_code)

    def montar_legenda(self, mes, ano):
        ano_mes = str(ano) + str(mes)
        if self.eventos_por_mes.get(ano_mes):
            html_code = ['<ul class="legenda">']
            #
            eventos = self.eventos_por_mes.get(ano_mes)
            eventos_clean = []
            for evento in eventos:
                if evento not in eventos_clean:  # remove eventos IDÊNTICOS
                    eventos_clean.append(evento)
            eventos_clean = sorted(eventos_clean, key=lambda e: e['data_inicio'])  # ordena por data_inicio
            #
            for evento in eventos_clean:
                sr_only = self.tipos_eventos_calendario.get(evento['css'], evento['css'])
                if evento['data_inicio'] == evento['data_fim'] or evento['data_fim'] is None:
                    css = evento['css']
                    di = str(evento['data_inicio'].day)
                    desc = evento['descricao']
                    html_code.append(f'<li class="{css}"><span class="visually-hidden">{sr_only}</span> Dia {di}: {desc}</li>')
                else:
                    css = evento['css']
                    di = str(evento['data_inicio'].day)
                    mi = str(evento['data_inicio'].month)
                    df = str(evento['data_fim'].day)
                    mf = str(evento['data_fim'].month)
                    desc = evento['descricao']
                    html_code.append(f'<li class="{css}"><span class="visually-hidden">{sr_only}</span> De {di}/{mi} a {df}/{mf}: {desc}</li>')
            html_code.append('</ul>')
            return '\n'.join(html_code)
        return ' '

    def formato_mes(self, ano, mes, exibir_legenda=False):
        html_code = self.montar_calendario_mes(mes, ano)
        for semana in self.monthdays2calendar(ano, mes):
            for dia, dia_da_semana in semana:
                html_code += self.montar_dia(dia, dia_da_semana, mes, ano)

        html_code += self.fechar_calendario_mes()
        html_code += self.montar_legenda(mes, ano)
        if exibir_legenda:
            html_code += self.legenda_tipos_eventos()
        html_code += self.fechar_div_calendario_mes()
        return html_code

    def formato_ano(self, ano):
        html_code = []
        html_code.append(self.legenda_tipos_eventos())
        for cont in range(12):
            if cont == 0:
                html_code.append(self.abrir_div_container())
            html_code.append(self.formato_mes(ano, cont + 1))
            if cont == 11:
                html_code.append(self.fechar_div_container())

        return ' '.join(html_code)

    def formato_ano_calendario_compras(self, ano):
        html_code = []
        for cont in range(12):
            if cont == 0:
                html_code.append(self.abrir_div_container())
            html_code.append(self.formato_mes(ano, cont + 1))
            if cont == 11:
                html_code.append(self.fechar_div_container())

        return ' '.join(html_code)

    def formato_periodo(self, mes_inicio, ano_inicio, mes_fim, ano_fim):
        html_code = []
        mes_inicial_ano = mes_inicio
        for ano in range(ano_inicio, ano_fim + 1):
            mes_final_ano = 12
            if ano == ano_fim:
                mes_final_ano = mes_fim

            for mes in range(mes_inicial_ano, mes_final_ano + 1):
                html_code.append(self.formato_mes(ano, mes))

            mes_inicial_ano = 1  # recomeça em janeiro

        return ' '.join(html_code)

    def abrir_div_container(self):
        html_code = []
        html_code.append('<div class="calendarios-container">')
        return ' '.join(html_code)

    def fechar_div_container(self):
        html_code = []
        html_code.append('</div>')
        return ' '.join(html_code)

    def __str__(self):
        return self.formato_ano(datetime.today().year)


class CalendarioPlus(Calendario):
    mostrar_mes_e_ano = False  # cabeçalho do calendário de um mês --> ex.'Outubro/2013' ou 'Outubro'
    destacar_hoje = True
    destacar_fim_de_semana = True
    ocultar_titles_dia = False
    ocultar_legenda_eventos = False
    envolve_mes_em_um_box = False

    def __init__(self, firstweekday=6, tipos_eventos_default=False):
        super().__init__(firstweekday=firstweekday, tipos_eventos_default=tipos_eventos_default)

    def adicionar_evento_calendario(self, data_inicio, data_fim, descricao, css_class, title=None, dia_todo=None, url=None, evento_id=None):
        """
        Metodo que montará o evento no calendario.
        """
        # garante que as datas serão do tipo datetime
        if type(data_inicio) is not datetime:
            # redefine data_inicio
            data_inicio = datetime(data_inicio.year, data_inicio.month, data_inicio.day, 0, 0, 0)  # hour,minute,second

        if not data_fim:
            data_fim = data_inicio
        else:
            if type(data_fim) is not datetime:
                # redefine data_fim
                data_fim = datetime(data_fim.year, data_fim.month, data_fim.day, 0, 0, 0)  # hour,minute,second

        # nesse ponto, as datas são datetime

        """
            eventos = {'todos': [{},{},{}],
                       'ano-mes': [{},{},{}],
                       'dias-atualizados': {
                            'dia': [{}, {}, {}]
                       }
                      }
            evento = {
                        'data_inicio': dia/mes/ano hora:min:sec,
                        'data_fim': dia/mes/ano hora:min:sec,
                        'descricao_evento': 'evento 1',
                        'css_class': 'css_class 1',
                        'title': '?',
                        'url': None,
                        'evento_id': '?'
                     }

            'ano-mes' obtido de data_inicio

            ** possibilidade de eventos paralelos em um mesmo dia

            Montando o mês:
             _____________
            |  mês[/ano]  |
             -------------
            | dias        |
             -------------

            Montando o dia:
                - hoje?
                    [css hoje]
                - fim de semana?
                    [css fds]
                - aplicar css_class do último evento (por enquanto 09/10/2013)
                    - eventos do dia/mês/ano --> eventos['todos'][evento X][data_inicio] <= dia/mes/ano <= eventos['todos'][evento X][data_fim]
                        - último evento
                            - aplicar css_class
                - [titles]
                    - eventos do dia/mês/ano --> eventos['todos'][evento X][data_inicio] <= dia/mes/ano <= eventos['todos'][evento X][data_fim]
                        - para cada evento
                            - concatena 'title' ou 'css_class'
                    - aplica concatenação

            [Montando a legenda do mês]
                - eventos do mês/ano --> eventos['ano-mes']
                    - para cada evento
                        - data_inicio = data_fim
                            - Dia X[,hora:min inicio à hora:min fim]: descricao_evento
                        - data_inicio <> data_fim
                            - mesmo mês?
                                - Dia X[, hora:min inicio] até Dia Y[, hora:min fim]: descricao_evento
                            - meses diferentes
                                - Dia X/mês A[, hora:min inicio] até Dia Y/mês B[, hora:min fim]: descricao_evento
                        - aplica css_class

            obtendo calendários:
                - obter calendário de um mês específico (mes/ano)
                    - monta o mês/ano
                - obter calendários de um ano específico (ano)
                    monta o ano
                        monta jan/ano
                        monta fev/ano
                        ...
                        monta dez/ano
                - obter calendários de um período específico (mes/ano inicio, mes/ano fim)
        """

        self.tipos_eventos_usados.add(css_class)

        evento = {
            'data_inicio': data_inicio,
            'data_fim': data_fim,
            'descricao_evento': descricao,
            'css_class': css_class,
            'title': title,
            'dia_todo': dia_todo,
            'url': url,
            'evento_id': evento_id,
        }
        # todos
        if 'todos' not in self.eventos:
            self.eventos['todos'] = []
        self.eventos['todos'].append(dict(**evento))

        # por mês
        ano_mes = str(data_inicio.date().year) + str(data_inicio.date().month)
        if ano_mes not in self.eventos:
            self.eventos[ano_mes] = []
        self.eventos[ano_mes].append(dict(**evento))

    def atualizar_evento(self, evento_id, data_inicio, data_fim, descricao, css_class, title=None, dia_todo=None, url=None):
        for data in daterange(data_inicio, data_fim):
            evento = [evento for evento in self.eventos_da_data(data) if evento.get('evento_id') == evento_id]
            if evento:
                upd_evento = dict(**evento[0])
                upd_evento['descricao_evento'] = ' '.join([_ for _ in [upd_evento['descricao_evento'], descricao or ''] if _])
                upd_evento['css_class'] = ' '.join(list({_ for _ in [upd_evento['css_class'], css_class or ''] if _}))
                upd_evento['title'] = ' | '.join([_ for _ in [upd_evento['title'], title or ''] if _])
                upd_evento['dia_todo'] = dia_todo or upd_evento['dia_todo']
                upd_evento['url'] = url or upd_evento['url']
                if 'dias-atualizados' not in self.eventos:
                    self.eventos['dias-atualizados'] = {}
                if str(data) not in self.eventos['dias-atualizados']:
                    self.eventos['dias-atualizados'][str(data)] = []
                self.eventos['dias-atualizados'][str(data)].append(upd_evento)

    def eventos_da_data(self, data):
        eventos = []
        if 'todos' in self.eventos:
            # garante que 'data' seja um 'date'
            if type(data) is datetime:
                data = data.date()
            for evento in self.eventos['todos']:
                if data >= evento['data_inicio'].date() and data <= evento['data_fim'].date():
                    eventos.append(evento)
        return eventos

    def montar_dia(self, dia, dia_da_semana, mes, ano):
        """
        Retorna o dia como um tipo <td>
        """
        if dia == 0:
            return self.celula_do_dia('vazio', '', '', dia_da_semana)
        else:
            cssclass = set()

            if self.destacar_hoje:
                hoje = datetime.now()
                if hoje.day == dia and hoje.month == mes and hoje.year == ano:
                    cssclass.add('hoje')
            if self.destacar_fim_de_semana:
                if dia_da_semana == 5 or dia_da_semana == 6:
                    cssclass.add('fds')

            data = []
            data.append(str(dia))
            data.append(str(mes))
            data.append(str(ano))
            data = datetime.strptime('-'.join(data), '%d-%m-%Y').date()

            eventos = sorted(self.eventos_da_data(data), key=lambda e: e['data_inicio'])

            final_eventos_dia = []
            for evento in eventos:
                final_evento = dict(**evento)
                if evento.get('evento_id'):
                    for evento_atualizado in self.eventos.get('dias-atualizados', {}).get(str(data), []):
                        if evento_atualizado.get('evento_id') == evento.get('evento_id'):
                            final_evento = dict(**evento_atualizado)
                final_eventos_dia.append(final_evento)

            cssclass.add(self.eh_dia_todo(final_eventos_dia, data))
            conteudo = self.montar_eventos(final_eventos_dia)

            return self.celula_do_dia(' '.join(cssclass), '', dia, dia_da_semana, conteudo)

    def eh_dia_todo(self, eventos, data):
        if len(eventos) <= 1:
            for evento in eventos:
                if evento['dia_todo']:
                    return evento['css_class']

        return ''

    def qtd_cssclass(self, cssclass):
        """
        Retorna a quantidade de classes dos eventos, ou seja, excluindo os colocados pelo calendário (hoje e fds)
        """
        cssclass_extra = cssclass.copy()
        cssclass_extra.discard('hoje')
        cssclass_extra.discard('fds')
        return len(cssclass_extra)

    def montar_calendario_mes(self, mes, ano):
        html_code = ['<div class="calendario calendario-mensal">']
        html_code.append('<table>')
        if not self.envolve_mes_em_um_box:
            if self.mostrar_mes_e_ano:
                html_code.append(f'<caption>{self.meses_extenso[int(mes) - 1]}/{ano}</caption>')
            else:
                html_code.append(f'<caption>{self.meses_extenso[int(mes) - 1]}</caption>')
        html_code.append('<thead>')
        html_code.append('<tr>')
        html_code.append('<th class="semana">Dom</th>')
        html_code.append('<th class="semana">Seg</th>')
        html_code.append('<th class="semana">Ter</th>')
        html_code.append('<th class="semana">Qua</th>')
        html_code.append('<th class="semana">Qui</th>')
        html_code.append('<th class="semana">Sex</th>')
        html_code.append('<th class="semana">Sab</th>')
        html_code.append('</tr>')
        html_code.append('</thead>')
        html_code.append('<tbody>')
        return '\n'.join(html_code)

    def montar_eventos(self, eventos):
        legendas = []
        for evento in eventos:
            descricao = evento['descricao_evento']
            url = evento.get('url')
            if url:
                descricao_completa = f'<a href="{url}" class="popup">{descricao}</a>'
            else:
                descricao_completa = descricao
            legendas.append(f'<li class="calendario-item {evento["css_class"]}" title="{evento["title"]}">{descricao_completa}</li>')

        html_code = ['<ul class="calendario-eventos">', *legendas, '</ul>']
        return '\n'.join(html_code)

    def formato_mes(self, ano, mes):
        html_code = self.montar_calendario_mes(mes, ano)
        for semana in self.monthdays2calendar(ano, mes):
            for dia, dia_da_semana in semana:
                html_code += self.montar_dia(dia, dia_da_semana, mes, ano)
        html_code += self.fechar_calendario_mes()
        html_code += self.fechar_div_calendario_mes()
        if self.envolve_mes_em_um_box:
            if self.mostrar_mes_e_ano:
                title_box = f'{self.meses_extenso[int(mes) - 1]}/{ano}'
            else:
                title_box = f'{self.meses_extenso[int(mes) - 1]}'
            html_code = f'<div class="box"><h3>{title_box}</h3>{html_code}</div>'
        return html_code

    def formato_periodo(
        self,
        mes_inicio,
        ano_inicio,
        mes_fim,
        ano_fim,
        omite_mes_sem_eventos=False,
        mostrar_legenda_no_comeco_de_cada_mes=False,
        mostrar_legenda_no_final_de_cada_mes=False,
    ):
        html_code = []
        mes_inicial_ano = mes_inicio
        for ano in range(ano_inicio, ano_fim + 1):
            mes_final_ano = 12
            if ano == ano_fim:
                mes_final_ano = mes_fim
            for mes in range(mes_inicial_ano, mes_final_ano + 1):
                if omite_mes_sem_eventos:
                    omite_mes = True
                    for evento in self.eventos['todos']:
                        if (
                            evento['data_inicio'].month == mes
                            and evento['data_inicio'].year == ano
                            or evento['data_fim'].month == mes
                            and evento['data_fim'].year == ano
                        ):
                            omite_mes = False
                            break
                    if omite_mes:
                        continue
                if mostrar_legenda_no_comeco_de_cada_mes:
                    html_code.append(self.legenda_tipos_eventos())
                html_code.append(self.formato_mes(ano, mes))
                if mostrar_legenda_no_final_de_cada_mes:
                    html_code.append(self.legenda_tipos_eventos())
            mes_inicial_ano = 1  # recomeça em janeiro
        return ' '.join(html_code)


class ValidatableObject(Schema):
    """Trata-se de um pydantic.Schema que possui os seguintes recursos:
    - construtor que aceita parâmetros conforme os fields/atributos definidos na classe.
    - validação de valor e tipo conforme os fields/atributos definidos na classe.
    - métodos dict(), json() e errors()
    - entre outros recursos (https://docs.pydantic.dev/latest/)
    """

    def __init__(self, *args, **kwargs):
        try:
            super().__init__(*args, **kwargs)
        except pydantic.ValidationError:
            raise Exception('Dados inválidos.')

    def dict(self, exclude_none=False):
        return super().dict(exclude_none=exclude_none)


class CalendarioMixTipoEvento(ValidatableObject):
    id: str
    descricao: str
    css_class: str


class CalendarioMixEventoAtualizacao(ValidatableObject):
    descricao: str
    css_class: str


class CalendarioMixEvento(ValidatableObject):
    id: str
    tipo_evento_id: str
    data_inicio: date
    data_fim: date
    descricao: str
    url: str = None
    atualizacoes: list[CalendarioMixEventoAtualizacao] = []


class CalendarioMix:
    """
    Interface simplificada (Facade) para utilização das classes de Calendário.

    https://refactoring.guru/pt-br/design-patterns/facade

    Adiciona um evento no calendário.
    Um evento abrange um período dentro do calendário, tem um tipo e uma descrição.
    Um evento pode receber uma ou mais atualizações no nível de um dia específico.
    """

    # formatos conforme definição em https://suap.ifrn.edu.br/comum/guia/?tab=componentes
    FORMATO_MENSAL = 1
    FORMATO_ANUAL = 2

    LEGENDA_NAO_EXIBIR = 1
    LEGENDA_NO_COMECO = 2
    LEGENDA_NO_FINAL = 3
    LEGENDA_NO_COMECO_DO_MES = 4
    LEGENDA_NO_FINAL_DO_MES = 5
    LEGENDA_DENTRO_CALENDARIO = 6

    tipos_eventos: list[CalendarioMixTipoEvento]
    eventos: list[CalendarioMixEvento]
    eventos_por_dia: dict[str, dict[str, list[CalendarioMixEvento]]]

    def __init__(
        self,
        formato,
        legenda=LEGENDA_NAO_EXIBIR,
    ):
        self.formato = formato
        self.legenda = legenda
        self.tipos_eventos = []
        self.eventos = []
        self.eventos_por_dia = {}

    def obter_tipo_evento(self, tipo_evento_id: str) -> CalendarioMixTipoEvento:
        tipo_evento = [tipo_evento for tipo_evento in self.tipos_eventos if tipo_evento.id == tipo_evento_id]
        return tipo_evento[0] if tipo_evento else None

    def obter_evento(self, evento_id: str) -> CalendarioMixEvento:
        evento = [evento for evento in self.eventos if evento.id == evento_id]
        return evento[0] if evento else None

    def obter_evento_por_dia(self, evento_id: str, data: date) -> CalendarioMixEvento:
        evento = [evento for evento in self.eventos_por_dia.get(str(data), []) if evento.id == evento_id]
        return evento[0] if evento else None

    def adicionar_tipo_evento(self, tipo_evento: CalendarioMixTipoEvento):
        self.tipos_eventos.append(CalendarioMixTipoEvento(**tipo_evento.dict()))

    def adicionar_evento(self, evento: CalendarioMixEvento):
        self.eventos.append(CalendarioMixEvento(**evento.dict()))
        for dia in daterange(evento.data_inicio, evento.data_fim):
            dia_key = str(dia)
            if dia_key not in self.eventos_por_dia:
                self.eventos_por_dia[dia_key] = []
            self.eventos_por_dia[dia_key].append(CalendarioMixEvento(**evento.dict()))

    def atualizar_evento(self, evento_id: str, evento_atualizacao: CalendarioMixEventoAtualizacao, data_inicio: date, data_fim: date):
        for dia in daterange(data_inicio, data_fim):
            evento = self.obter_evento_por_dia(evento_id, dia)
            if evento:
                if not evento.atualizacoes:
                    evento.atualizacoes = []
                evento.atualizacoes.append(CalendarioMixEventoAtualizacao(**evento_atualizacao.dict()))

    def get_html_formato_mensal(self):
        cal = CalendarioPlus()
        cal.mostrar_mes_e_ano = True
        cal.envolve_mes_em_um_box = True

        for tipo_evento in self.tipos_eventos:
            cal.adicionar_tipo_evento(tipo_evento.css_class, tipo_evento.descricao)

        menor_dia = None
        maior_dia = None

        for evento in self.eventos:
            tipo_evento = self.obter_tipo_evento(evento.tipo_evento_id)

            cal.adicionar_evento_calendario(
                evento_id=evento.id,
                data_inicio=evento.data_inicio,
                data_fim=evento.data_fim,
                descricao=evento.descricao,
                css_class=tipo_evento.css_class if tipo_evento else '',
                title=tipo_evento.descricao if tipo_evento else '',
                url=evento.url,
            )
            for dia in daterange(evento.data_inicio, evento.data_fim):
                evento_por_dia = self.obter_evento_por_dia(evento.id, dia)
                if evento_por_dia and evento_por_dia.atualizacoes:
                    for atualizacao in evento_por_dia.atualizacoes:
                        cal.atualizar_evento(
                            evento.id,
                            dia,
                            dia,
                            atualizacao.descricao,
                            atualizacao.css_class,
                        )
                menor_dia = min(menor_dia, dia) if menor_dia else dia
                maior_dia = max(maior_dia, dia) if maior_dia else dia

        out_html = ''

        if menor_dia and maior_dia:
            if self.legenda == CalendarioMix.LEGENDA_NO_COMECO:
                out_html += cal.legenda_tipos_eventos()

            out_html += cal.formato_periodo(
                mes_inicio=menor_dia.month,
                ano_inicio=menor_dia.year,
                mes_fim=maior_dia.month,
                ano_fim=maior_dia.year,
                mostrar_legenda_no_comeco_de_cada_mes=self.legenda == CalendarioMix.LEGENDA_NO_COMECO_DO_MES,
                mostrar_legenda_no_final_de_cada_mes=self.legenda == CalendarioMix.LEGENDA_NO_FINAL_DO_MES,
            )

            if self.legenda == CalendarioMix.LEGENDA_NO_FINAL:
                out_html += cal.legenda_tipos_eventos()

        return mark_safe(out_html or '<p class="alert alert-warning">Nenhuma informação a ser exibida.</p>')

    def dia_atualizacoes(self, atualizacoes: list[CalendarioMixEventoAtualizacao]) -> list[CalendarioMixEventoAtualizacao]:
        for atualizacao in atualizacoes:
            # conflito tem ordem de prioridade maior na "pintura" do dia no formato anual
            if atualizacao.css_class == 'extra6':
                return [atualizacao]
        return atualizacoes

    def get_html_formato_anual(self):
        cal = Calendario(tipos_eventos_default=False)

        for tipo_evento in self.tipos_eventos:
            cal.adicionar_tipo_evento(tipo_evento.css_class, tipo_evento.descricao)

        anos_meses = []
        dias_atualizacoes = {}  # {dia: [atualizacao, atualizacao]}

        for evento in self.eventos:
            tipo_evento = self.obter_tipo_evento(evento.tipo_evento_id)

            cal.adicionar_evento_calendario(
                data_inicio=evento.data_inicio,
                data_fim=evento.data_fim,
                descricao=evento.descricao,
                css_class=tipo_evento.css_class if tipo_evento else '',
                title=tipo_evento.descricao if tipo_evento else '',
            )

            for dia in daterange(evento.data_inicio, evento.data_fim):
                evento_por_dia = self.obter_evento_por_dia(evento.id, dia)
                if evento_por_dia and evento_por_dia.atualizacoes:
                    if str(dia) in cal.eventos:
                        for atualizacao in evento_por_dia.atualizacoes:
                            if dia not in dias_atualizacoes:
                                dias_atualizacoes[dia] = []
                            dias_atualizacoes[dia].append(atualizacao)
                ano_mes = f'{dia.year}'.zfill(4) + '_' + f'{dia.month}'.zfill(2)
                anos_meses.append(ano_mes)

        for dia_atualizacao, atualizacoes in dias_atualizacoes.items():
            if self.formato == CalendarioMix.FORMATO_ANUAL:
                for atualizacao in self.dia_atualizacoes(atualizacoes):
                    cal.eventos[str(dia_atualizacao)]['css'] = atualizacao.css_class
                    cal.eventos[str(dia_atualizacao)]['title'] += ' ' + atualizacao.descricao

        out_html = ''

        if self.legenda == CalendarioMix.LEGENDA_NO_COMECO:
            out_html += cal.legenda_tipos_eventos()

        for ano_mes in sorted(set(anos_meses)):
            ano = int(ano_mes.split('_')[0])
            mes = int(ano_mes.split('_')[1])

            if self.legenda == CalendarioMix.LEGENDA_NO_COMECO_DO_MES:
                out_html += cal.legenda_tipos_eventos()

            out_html += cal.formato_mes(ano, mes, exibir_legenda=self.legenda == CalendarioMix.LEGENDA_DENTRO_CALENDARIO)

            if self.legenda == CalendarioMix.LEGENDA_NO_FINAL_DO_MES:
                out_html += cal.legenda_tipos_eventos()

        if self.legenda == CalendarioMix.LEGENDA_NO_FINAL:
            out_html += cal.legenda_tipos_eventos()

        return mark_safe(out_html or '<p class="alert alert-warning">Nenhuma informação a ser exibida.</p>')

    def __str__(self):
        return self.get_html_formato_mensal() if self.formato == CalendarioMix.FORMATO_MENSAL else self.get_html_formato_anual()
