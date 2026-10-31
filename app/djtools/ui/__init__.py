import io
from collections import OrderedDict

from django.conf import settings
from django.http import HttpResponse

from djtools.utils import render_to_string


class Component:
    """
    Classe base para contrução de componentes de tabela de horários.
    """

    def render(self, template_name):
        """
        Renderiza a tabela em **HTML**.

        Args:
            template_name (string): nome do template.

        Returns:
             String contendo o conteúdo em **HTML**.
        """
        return render_to_string(template_name, {'self': self})

    def as_pdf(self):
        """
        Renderiza a tabela em **PDF**.

        Returns:
             HttpResponse com o arquivo **PDF** anexado.
        """
        from weasyprint import HTML

        self.pdf = True
        html = self.__str__()
        pdf_bytes = io.BytesIO()
        HTML(string=html, base_url=settings.SITE_URL).write_pdf(pdf_bytes)
        pdf_bytes.seek(0)
        return HttpResponse(pdf_bytes, content_type='application/pdf')


class TabelaHorario(Component):
    """
    Classe para tratamento de tabelas de horário.

    Attributes:
        titulo (string): título da tabela;
        filtros ():;
        turnos (OrderedDict): dicionário com os turnos;
        legenda (OrderedDict): dicionário com as legendas;
        export_to_pdf (bool): indica se a saída será no formato **PDF**;
        request (HttpRequest): request da requisição;
        pdf (bool): indica se é um **PDF**.

    Examples::

        tabela_horarios = TabelaHorario()
        tabela_horarios.adicionar_horario('Matutino', '07:00', '08:00')
        tabela_horarios.adicionar_horario('Matutino', '08:00', '09:00')
        tabela_horarios.adicionar_horario('Vespertino', '13:00', '14:00')
        tabela_horarios.adicionar_horario('Vespertino', '14:00', '15:00')
        tabela_horarios.adicionar_registro('XXXX', '3M1')
        tabela_horarios.adicionar_registro('XXXX', '3M1', '#')
        tabela_horarios.adicionar_registro('XXXX', '4M1', '#')
        tabela_horarios.adicionar_registro('YYYY', '5V2')
    """

    DIAS_SEMANA = 'SEG', 'TER', 'QUA', 'QUI', 'SEX', 'SAB', 'DOM'  #:

    def __init__(self, export_to_pdf=False, request=None):
        """
        Construtor da classe.

        Args:
            export_to_pdf (bool): indica que a saída será no formato **PDF**;
            request (HttpRequest): request da requisição.
        """
        self.titulo = ''
        self.filtros = None
        self.turnos = OrderedDict()
        self.legenda = OrderedDict()
        self.export_to_pdf = export_to_pdf
        self.request = request
        self.pdf = False

    def adicionar_horario(self, turno, hora_inicio, hora_fim):
        """
        Adiciona um horário com base no turno.

        Args:
            turno (tuple): dados do turno;
            hora_inicio (datetime): horário inicial;
            hora_fim (datetime): horário final.
        """
        sigla_turno = turno[0]
        if sigla_turno not in self.turnos:
            self.turnos[sigla_turno] = (turno, [])
        self.turnos[sigla_turno][1].append([f'{hora_inicio} - {hora_fim}', [], [], [], [], [], [], []])

    def adicionar_registro(self, label, horario, url=None, hint=None):
        """
        Adiciona um registro para um horário.

        Args:
            label (string): rótulo para o registro;
            horario (tupla): dados do horário;
            url (string): URL para o evento;
            hint (string): dica para o horário.
        """
        dia, sigla_turno, horario = int(horario[0]) - 1, horario[1], int(horario[2])
        self.turnos[sigla_turno][1][horario - 1][dia].append((label, url, hint))
        if label not in self.legenda:
            self.legenda[label] = hint

    def __str__(self):
        """
        Representação humana para o objeto.

        Returns:
            String com a representação do objeto.
        """
        return self.render('tabela_horarios.html')


class TabelasHorario(Component):
    def __init__(self, request=None):
        """
        Construtor da classe.

        Args:
            request (HttpRequest): request da requisição.
        """
        self.tabelas = []

    def adicionar(self, tabela):
        """
        Adiciona a tabela.

        Args:
            tabela ():
        """
        self.tabelas.append(tabela)

    def __str__(self):
        """
        Representação humana para o objeto.

        Returns:
            String com a representação do objeto.
        """
        return self.render('tabelas_horarios.html')

    def as_pdf(self):
        """
        Renderiza a tabela em **PDF**.

        Returns:
             HttpResponse com o arquivo **PDF** anexado.
        """
        for tabela in self.tabelas:
            tabela.pdf = True
        return super().as_pdf()
