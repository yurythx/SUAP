import io
import numbers
from datetime import datetime
from html import escape
from io import BytesIO
from os.path import join

from django.apps import apps
from django.conf import settings
from django.utils.html import escape as escape_html
from reportlab.lib import colors, pagesizes
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Flowable, Frame, Image, LongTable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, TableStyle

from djtools.utils.strings import human_str

STYLES = getSampleStyleSheet()


def space(height):
    return Spacer(0, height * mm)


def page_break():
    return PageBreak()


def montar_paragrafo(texto, alinhamento='left', estilo='BodyText', tamanho=None, negrito=False, autoescape=True):
    """
    Cria um parágrafo no padrão ReportLAB.

    Args:
        texto (string): texto do parágrafo;
        alinhamento (string): estilo do alinhamento;
        estilo (string): estilo do texto do parágrafo;
        tamanho (string): tamanho do texto;
        negrito (bool): indica que o texto deve estar em negrito;
        autoescape (bool): indica se deve-se realizar o '*escape*' do texto.

    Returns:
        Paragraph com base nos argumentos passados.
    """
    if autoescape and isinstance(texto, str) and '<br/>' not in texto:
        texto = escape(texto)
    template = '<para alignment=%(alinhamento)s %(fontSize)s>%(texto)s</para>'
    fontSize = tamanho and f'fontSize={tamanho}' or ''
    if negrito:
        texto = f'<b>{texto}</b>'
    contexto = {'fontSize': fontSize, 'alinhamento': alinhamento, 'texto': texto}

    return Paragraph(template % (contexto), STYLES[estilo])


def montar_tabela_pdf(tabela):
    """
    Cria uma tabela, no formato do ReportLAB, com os dados passados.

    Args:
        tabela (dict): dicionário com os dados para montagem da tabela.

    Returns:
        LongTable com os dados passados.
    """
    # Saída: lista de tabelas; uma para cada cabeçalho e uma para os dados.

    tabelas = []
    cabecalhos = tabela['cabecalhos']
    dados = tabela['dados']

    # Montar as tabelas para cada cabeçalho
    for c in cabecalhos:
        item = []
        larguras = []
        for col in c:
            item.append(montar_paragrafo(col['valor'], alinhamento='center', negrito=True))
            larguras.append(col['largura'])
        tabela = LongTable([item], [i * mm for i in larguras])
        tabela.setStyle(
            TableStyle(
                [
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.black),
                    ('BOX', (0, 0), (-1, -1), 0.25, colors.black),
                ]
            )
        )
        tabelas.append(tabela)

    # Montar a tabela do corpo
    for linha in dados:
        for i, coluna in enumerate(linha):
            coluna = str(coluna)
            coluna = len(coluna) > 600 and coluna[:600] + '...' or coluna
            linha[i] = montar_paragrafo(coluna, alinhamento=c[i]['alinhamento'])

    tabela = LongTable(dados, [i * mm for i in larguras])
    tabela.setStyle(
        TableStyle(
            [('VALIGN', (0, 0), (-1, -1), 'TOP'), ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.black), ('BOX', (0, 0), (-1, -1), 0.25, colors.black)]
        )
    )

    tabelas.append(tabela)
    return tabelas


def para(text, style='BodyText', bulletText=None, caseSensitive=0, escape=True, **para_args):
    """
    ``text``: texto do parágrafo
    ``style``: estilo do paragrafo
               opções: ['bu', 'df', 'h1', 'h2', 'h3', 'title', 'BodyText',
                        'Bullet', 'Code', 'Definition', 'Heading1', 'Heading2',
                        'Heading3', 'Italic', 'Normal', 'Title']
    ``para_args``: dict com atributos e valores para a tag `<para>`

    ****************************************************************************
    Class Paragraph:

    Paragraph(text, style, bulletText=None, caseSensitive=1)

    text a string of stuff to go into the paragraph. style is a style definition
    as in reportlab.lib.styles. bulletText is an optional bullet defintion.
    caseSensitive set this to 0 if you want the markup tags and their attributes
    to be case-insensitive.

    This class is a flowable that can format a block of text into a paragraph with
    a given style.

    The paragraph Text can contain XML-like markup including the tags:
    <b> ... </b> - bold
    <i> ... </i> - italics
    <u> ... </u> - underline
    <strike> ... </strike> - strike through
    <super> ... </super> - superscript
    <sub> ... </sub> - subscript
    <font name=fontfamily/fontname color=colorname size=float>
    <onDraw name=callable label="a label"/>
    <index [name="callablecanvasattribute"] label="a label"/>
    <link>link text</link> attributes of links
        size/fontSize=num
        name/face/fontName=name
        fg/textColor/color=color
        backcolor/backColor/bgcolor=color
        dest/destination/target/href/link=target
    <a>anchor text</a> attributes of anchors
        fontSize=num
        fontName=name
        fg/textColor/color=color
        backcolor/backColor/bgcolor=color
        href=href
    <a name="anchorpoint"/>
    <unichar name="unicode character name"/>
    <unichar value="unicode code point"/>
    <img src="path" width="1in" height="1in" valign="bottom"/>
    The whole may be surrounded by <para> </para> tags
    The <b> and <i> tags will work for the built-in fonts (Helvetica /Times / Courier).
    For other fonts you need to register a family of 4 fonts using
    reportlab.pdfbase.pdfmetrics.registerFont; then use the addMapping function to
    tell the library that these 4 fonts form a family e.g.
        from reportlab.lib.fonts import addMapping
        addMapping('Vera', 0, 0, 'Vera')	#normal
        addMapping('Vera', 0, 1, 'Vera-Italic')	#italic
        addMapping('Vera', 1, 0, 'Vera-Bold')	#bold
        addMapping('Vera', 1, 1, 'Vera-BoldItalic')	#italic and bold
    It will also be able to handle any MathML specified Greek characters.
    """
    text = human_str(text)

    alignments = {'l': 'left', 'r': 'right', 'c': 'center'}

    if not text.upper().startswith('<PARA'):
        para_args_formatted = []
        for key, value in list(para_args.items()):
            if key.lower() in ['align', 'alignment'] and value.lower() in alignments:
                value = alignments[value.lower()]
            para_args_formatted.append(f'{key}="{value}"')
        if escape:
            text = escape_html(text)
        text = '<para {}>{}</para>'.format(' '.join(para_args_formatted), text)

    return Paragraph(text=text, style=STYLES[style], bulletText=bulletText, caseSensitive=caseSensitive)


def table(rows, w=None, h=None, grid=1, head=0, count=0, zebra=0, auto_align=1, blank='-', a=None, fontSize=8, escape=True):
    """
    w: colWidths
    h: rowHeight
    grid: mostrar grades da tabela
    head: indica se a primeira lista de `rows` é o cabeçalho
    count: mostra o contador das linhas
    zebra: a tabela fica zebrada
    auto_align: alinha automaticamente a célula de acordo com seu valor
    blank: valor caso a célula esteja em branco (ou None)
    a: alinhamentos
    """
    number_of_columns = len(rows[0])

    # Validating rows
    for row_n, row in enumerate(rows[1:]):
        if len(row) != number_of_columns:
            raise Exception(f'Rows must have {number_of_columns} columns, got {len(row)} on row {row_n + 2}')

    # Validating w
    if w:
        if len(w) != number_of_columns:
            raise Exception(f'Param `w` must have len {number_of_columns}, got {len(w)}')

    # Validating a
    if a:
        if len(a) != number_of_columns:
            raise Exception(f'Param `a` must have len {number_of_columns}, got {len(a)}')

    def get_auto_align(value):
        if isinstance(value, str):
            # String: 0,00 or 0.00
            return value.replace(',', '').replace('.', '').isdigit() and 'right' or 'left'
        return isinstance(value, numbers.Number) and 'right' or 'left'

    formatted_rows = []

    for index, row in enumerate(rows):  # Body
        # HEAD
        if index == 0 and head:
            if count and w:
                w = [10, *w]
            formatted_row = []
            row = count and (['#', *row]) or row
            for cell in row:
                text = f'<para fontSize="{fontSize}" alignment="center"><b>{cell}</b></para>'
                formatted_row.append(para(text, escape=False))
            formatted_rows.append(formatted_row)
            continue

        # ROW
        formatted_row = []
        if count:
            order = head and index or index + 1
            text = f'<para fontSize="{fontSize}" alignment="right">{order}</para>'
            formatted_row = [para(text, escape=False)]
        for row_count, cell in enumerate(row):
            # If cell insn't a reportlab element
            if cell.__class__.__module__.split('.')[0] != 'reportlab':
                para_args = {'fontSize': fontSize, 'escape': escape}
                if not cell:  # valor em branco
                    cell = blank
                    if a:
                        para_args['align'] = a[row_count]
                    else:
                        para_args['align'] = 'c'
                else:
                    if a:
                        para_args['align'] = a[row_count]
                    elif auto_align:
                        para_args['align'] = get_auto_align(cell)
                cell = para(cell, **para_args)
            formatted_row.append(cell)
        formatted_rows.append(formatted_row)

    # Constructor args to table <LongTable>
    constructor_args = {}
    if w:
        constructor_args['colWidths'] = [i * mm for i in w]
    if h:
        constructor_args['rowHeights'] = h * mm
    if head:
        # repeat table header after page breaks
        constructor_args['repeatRows'] = 1

    # Creating the table
    table = LongTable(formatted_rows, **constructor_args)
    table.setStyle(
        TableStyle(
            [('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('BOTTOMPADDING', (0, 0), (-1, -1), 0.25, 0.25), ('TOPADDING', (0, 0), (-1, -1), 0.25, 0.25)]
        )
    )

    if grid:
        table.setStyle(TableStyle([('INNERGRID', (0, 0), (-1, -1), 0.1, colors.gray), ('BOX', (0, 0), (-1, -1), 0.25, colors.black)]))

    if head:
        table.setStyle(TableStyle([('ROWBACKGROUNDS', (0, 0), (-1, 0), (0xCCCCCC,))]))

    if zebra:
        table.setStyle(TableStyle([('ROWBACKGROUNDS', (0, 1), (-1, -1), (0xEEEEEE, None))]))

    return table


class RelatorioPDF:
    """
    Gera um relatório reportlab em formato de tabela a partir
    de um dicionário de dados
    Converte o dict 'dados' em atributos da instância.

    A chave 'elementos' contém uma lista de itens que serão adicionados ao
    documento. Caso o item seja do tipo basestring, ele será convertido num
    parágrafo, caso seja dict, será uma tabela.

    Args:
        dados (dict or string) : dados da tabela ou parágrafo
        paisagem (bool) : formato do relatório
    """

    valores_padrao = {
        'cidade': 'Natal',
        'altura_pagina': 210 * mm,
        'largura_pagina': 297 * mm,
        'margem_esquerda': 15 * mm,
        'margem_direita': 15 * mm,
        'margem_superior': 20 * mm,
        'margem_inferior': 20 * mm,
        'elementos': [],
    }

    def __init__(self, dados, paisagem=False):
        self.paisagem = paisagem
        for chave, valor in list(RelatorioPDF.valores_padrao.items()):
            dados.setdefault(chave, valor)
        for chave, valor in list(dados.items()):
            self.__setattr__(chave, valor)

        self.data_assinatura = f'{self.cidade}, ______ de ____________________ de __________'

    def desenhar_brasao(self, canvas):
        """
        Desenha a imagem do brasão no canto superior esquerdo.

        Args:
            canvas (reportlab.pdfgen.canvas) : Documento PDF parcial
        """
        imagem = join(settings.STATIC_ROOT, 'comum/img/brasao_cinza.jpg')
        if self.paisagem:
            canvas.drawImage(imagem, self.largura_pagina - 250 * mm, self.altura_pagina - 38 * mm, 15.96 * mm, 17.4 * mm)
        else:
            canvas.drawImage(imagem, self.largura_pagina - 185 * mm, self.altura_pagina - 170 * mm, 15.96 * mm, 17.4 * mm)

    def montar_cabecalho(self, canvas):
        """
        Desenha o cabeçalho do relatório

        Args:
            canvas (reportlab.pdfgen.canvas) : Documento PDF parcial
        """
        self.desenhar_brasao(canvas)
        story = []
        for item in ['orgao', 'uo', 'setor']:
            item = montar_paragrafo(self.cabecalho.get(item, ''), alinhamento='center', tamanho=12)
            story.append(item)
        f = Frame(
            20 * mm,
            self.altura_pagina - 45 * mm,
            230 * mm,
            25 * mm,
            leftPadding=1 * mm,
            bottomPadding=1 * mm,
            rightPadding=1 * mm,
            topPadding=1 * mm,
            showBoundary=0,
        )
        f.addFromList(story, canvas)
        canvas.setFont('Times-Roman', 9)
        canvas.drawRightString(self.largura_pagina - 21 * mm, self.altura_pagina - 43 * mm, self.data)

    def montar_rodape(self, canvas):
        """
        As subclasses podem implementar este método.

        Args:
            canvas (reportlab.pdfgen.canvas) : Documento PDF parcial
        """

    def montar_primeira_pagina(self, canvas, doc):
        """
        Monta a primeira página do relatório que pode ser diferente das demais

        Args:
            canvas (pdf_document) : Documento PDF parcial
        """
        canvas.saveState()
        self.montar_cabecalho(canvas)
        self.montar_rodape(canvas)
        canvas.setFont('Times-Roman', 16)
        canvas.drawCentredString(self.largura_pagina / 2, self.altura_pagina - 60 * mm, self.titulo)
        canvas.restoreState()

    def montar_paginas_seguintes(self, canvas, doc):
        """
        Monta as demais páginas do relatório

        Args:
            canvas (reportlab.pdfgen.canvas) : Documento PDF parcial
        """
        canvas.saveState()
        self.montar_rodape(canvas)
        canvas.restoreState()

    def montar(self):
        """
        Monta o pdf do relatório

        Returns:
            Documento PDF
        """
        arquivoPDF = BytesIO()
        if self.paisagem:
            doc = SimpleDocTemplate(
                arquivoPDF,
                showBoundary=0,
                leftMargin=self.margem_esquerda,
                rightMargin=self.margem_direita,
                topMargin=self.margem_superior,
                bottomMargin=self.margem_inferior,
                pagesize=landscape(A4),
            )
        else:
            doc = SimpleDocTemplate(
                arquivoPDF,
                showBoundary=0,
                leftMargin=self.margem_esquerda,
                rightMargin=self.margem_direita,
                topMargin=self.margem_superior,
                bottomMargin=self.margem_inferior,
            )

        story = [Spacer(1, 48 * mm)]  # Espaçamento para o título

        for e in self.elementos[::-1]:
            if isinstance(e, dict):
                ultimo_dict = e
                break
        # Varrendo os elementos do relatório
        for e in self.elementos:
            # O elemento é um parágrafo
            if isinstance(e, str):
                story.append(montar_paragrafo(e))
            # O elemento é uma tabela
            elif isinstance(e, dict):
                story.append(Spacer(1, 5 * mm))
                story += montar_tabela_pdf(e)
                if e != ultimo_dict:
                    story.append(PageBreak())
                story.append(Spacer(1, 5 * mm))
        doc.build(story, onFirstPage=self.montar_primeira_pagina, onLaterPages=self.montar_paginas_seguintes)
        return arquivoPDF.getvalue()


class ImageFullBackground(Flowable):
    """
    Draw a image to fill the first page in a document section.
    """

    def __init__(self, filename):
        Flowable.__init__(self)
        self.filename = filename
        self.styles = getSampleStyleSheet()

    def coord(self, x, y, unit=1):
        """
        http://stackoverflow.com/questions/4726011/wrap-text-in-a-table-reportlab
        Helper class to help position flowables in Canvas objects
        """
        x, y = x * unit, self.height - y * unit
        return x, y

    def draw(self):
        """
        Draw the image and text.
        """
        draw_width, draw_height = self.canv._pagesize
        i = Image(self.filename, draw_width, draw_height)
        i.wrapOn(self.canv, draw_width, draw_height)
        i.drawOn(self.canv, *self.coord(-12.5 * mm, draw_height - (12.5 * mm)))


class PagesCountCanvas(canvas.Canvas):
    """
    Imprime "página X de Y" no canto inferior esquerdo de cada página
    Créditos: http://code.activestate.com/recipes/576832/
    """

    def __init__(self, *args, **kwargs):
        canvas.Canvas.__init__(self, *args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        """add page info to each page (page x of y)"""
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_page_number(self, page_count):
        self.setFont('Helvetica', 7)
        self.drawRightString(self._pagesize[0] - 8 * mm, 8 * mm, f'Página {self._pageNumber} de {page_count}')


class PdfReport:
    def __init__(self, body, header_args=None, footer_args=None, paper='A4', pages_count=1, creation_date=0, filename=None):
        """
        body <list>:
            lista com elementos que compõem o corpo do PDF.
        header_args & footer_args <function|dict>:
            representam elementos que aparecerão em todas as páginas.
            se for <function>:
                a função receber ao menos os parâmetros `canvas` e `doc`, devendo
                retornar algo como o ``body`` e deve ter o atributo ``height``
            se for <dict>:
                height, story, function, args
        paper <string>:
            uma opção de reportlab.lib.pagesizes (caso tenha um "-" antes da opção,
            será ententido como formato paisagem - o default é retrato): ['A0',
            'A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'B0', 'B1', 'B2', 'B3', 'B4',
            'B5', 'B6', 'ELEVENSEVENTEEN', 'LEGAL'])
        pages_count <bool>:
            indica se o PDF usará ``PagesCountCanvas`` para mostrar o contador de
            páginas
        """
        self._set_paper(paper)
        self.body = body
        self.show_pages_count = pages_count
        self.show_creation_date = creation_date
        self.creation_date = datetime.now()
        self.filename = filename
        # header_args
        self.header_args = header_args
        self._set_header_or_footer_args('header')
        # footer_args
        self.footer_args = footer_args
        self._set_header_or_footer_args('footer')

    def _set_paper(self, paper):
        paper = paper.upper()
        if paper.startswith('-'):
            landscape = True
            paper = paper[1:]
        else:
            landscape = False
        self.pagesize = getattr(pagesizes, paper)
        if landscape:
            self.pagesize = pagesizes.landscape(self.pagesize)

    def _set_header_or_footer_args(self, option):
        assert option in ('header', 'footer')
        args_name = option + '_args'
        args = getattr(self, args_name)
        if args:
            if callable(args):  # args é uma função
                try:
                    height = args.height
                except AttributeError:
                    raise AttributeError(f'Função `{args_name}` deve ter atributo `height`')
            elif isinstance(args, dict):  # args é um dicionário
                if 'function' in args:  # args tem chave `function`
                    if not callable(args['function']):
                        raise ValueError(f'Chave `function` de {args_name} deve ser uma função')
                    if hasattr(args['function'], 'height'):
                        if 'height' in args:
                            raise ValueError('Chave `height` é inválida porque `function` tem atributo `height`')
                        height = args['function'].height
                else:  # args não tem chave `function`
                    if 'story' not in args:
                        raise ValueError('%s args_name deve ter chave `story` quando não tem `function`')
                    height = args['height']
        else:
            height = 0
        setattr(self, option + '_height', height * mm)

    def _get_header_or_footer_story(self, option, canvas, doc):
        assert option in ('header', 'footer')
        args = getattr(self, option + '_args')
        if args:
            if callable(args) or 'function' in args:
                func_args = {'canvas': canvas, 'doc': doc}
                if callable(args):
                    function = args
                elif 'function' in args:
                    function = args['function']
                    func_args.update(args['args'])
                story = function(**func_args)
                if not isinstance(story, list):
                    raise ValueError('Função deve retornar lista')
                return story
            else:
                return args['story']
        else:
            return []

    def has_header(self):
        return self.header_height > 0 * mm

    def has_footer(self):
        return self.footer_height > 0 * mm

    def set_header(self, canvas, doc):
        if not self.has_header():
            return

        f = Frame(  # (x1,y1) <-- lower left corner
            x1=doc.leftMargin,
            y1=doc.pagesize[1] - self.header_height - 10 * mm,
            width=doc.width,  # doc.width = doc.pagesize[1] - doc.leftMargin - doc.rightMargin
            height=self.header_height,
            leftPadding=1,
            bottomPadding=1,
            rightPadding=1,
            topPadding=1,
            id=None,
            showBoundary=1,
            overlapAttachedSpace=None,
            _debug=None,
        )
        f.addFromList(self._get_header_or_footer_story('header', canvas, doc)[:], canvas)

    def set_footer(self, canvas, doc):
        if not self.has_footer():
            return

        f = Frame(  # (x1,y1) <-- lower left corner
            x1=doc.leftMargin,
            y1=doc.bottomMargin - self.footer_height,
            width=doc.width,  # doc.width = doc.pagesize[1] - doc.leftMargin - doc.rightMargin
            height=self.footer_height,
            leftPadding=1,
            bottomPadding=1,
            rightPadding=1,
            topPadding=1,
            id=None,
            showBoundary=0,
            overlapAttachedSpace=None,
            _debug=None,
        )
        f.addFromList(self._get_header_or_footer_story('footer', canvas, doc)[:], canvas)

    def onFirstPage(self, canvas, doc):
        canvas.saveState()
        self.set_header(canvas, doc)
        self.set_footer(canvas, doc)
        if self.show_creation_date:
            self.set_creation_date(canvas, doc)
        canvas.restoreState()

    def onLaterPages(self, canvas, doc):
        canvas.saveState()
        self.set_header(canvas, doc)
        self.set_footer(canvas, doc)
        if self.show_creation_date:
            self.set_creation_date(canvas, doc)
        canvas.restoreState()

    def set_creation_date(self, canvas, doc):
        canvas.setFont('Helvetica', 7)
        horario = self.creation_date.strftime('%d/%m/%Y %H:%M:%S')
        canvas.drawString(10 * mm, 8 * mm, f'Documento gerado em {horario}')

    def generate(self):
        """
        SimpleDocTemplate extends BaseDocTemplate

        BaseDocTemplate(self, filename, pagesize=defaultPageSize,
            pageTemplates=[], showBoundary=0, leftMargin=inch, rightMargin=inch, topMargin=inch,
            bottomMargin=inch, allowSplitting=1, title=None, author=None, _pageBreakQuick=1, encrypt=None)
        """
        pdf_file = io.BytesIO()
        doc = SimpleDocTemplate(
            pdf_file,
            pagesize=self.pagesize,
            # Margens que delimitam a área útil (sem header e footer)
            leftMargin=10 * mm,
            rightMargin=10 * mm,
            topMargin=10 * mm + self.header_height,
            bottomMargin=10 * mm + self.footer_height,
        )
        story = list(self.body).copy()
        # Preparing to build()
        build_args = {'flowables': story, 'onFirstPage': self.onFirstPage, 'onLaterPages': self.onLaterPages}
        if self.show_pages_count:
            build_args['canvasmaker'] = PagesCountCanvas
        doc.build(**build_args)

        if self.filename:
            f = open(self.filename, 'wb')
            f.write(pdf_file.getvalue())
            f.close()
        else:
            return pdf_file.getvalue()


def get_topo_pdf(titulo=None):
    # Mover para um módulo pdf_utils?
    # Deve ser utilizado com papel A4
    IMAGE_PATH = join(settings.STATIC_ROOT, 'comum/img/brasao_cinza.jpg')
    TITULO = apps.get_model('comum', 'configuracao').get_valor_por_chave('comum', 'instituicao')
    image = Image(IMAGE_PATH, width=15.96 * mm, height=17.4 * mm)

    tabela_imagem = table([[image, para(TITULO, align='center', fontsize='12', escape=False)]], w=[25, 165], grid=0)

    elementos = [tabela_imagem, space(4)]

    if titulo:
        elementos.append(para(titulo, style='h2', align='center', escape=False))
        elementos.append(space(4))

    return elementos
