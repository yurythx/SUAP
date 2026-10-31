from html.entities import entitydefs

from reportlab.lib import pagesizes
from reportlab.lib.units import cm, inch, mm
from reportlab.pdfgen import canvas


class Error(Exception):
    pass


class Error2(Exception):
    pass


LABELS_CHOICES = [
    ['62681', 'PIMACO - 6081/6181/0081/62581/62681'],
    ['A4255', 'PIMACO - 6080/6180/6280/0080/62580/62680/A4255/A4055'],
    ['A4366', 'PIMACO - A4655'],
]
LABELS = (
    {
        'cia': 'test',
        'models': ['9999'],
        'paper': pagesizes.letter,
        'columns': 4,
        'rows': 9,
        'height': 2.5,
        'width': 4,
        'topMargin': 1,
        'lateralMargin': 0.5,  # you may define a leftMargin and rightMargin
        'verticalSpacing': 0.25,  # defaults to 0
        'horizontalSpacing': 0.25,  # defaults to 0
        'horizontalPadding': 0.5,  # defaults to +/- 7% of width
        'verticalPadding': 0.5,  # defaults to +/- 7% of height
        'units': cm,  # defaults to mm
    },
    {
        'cia': 'Avery',
        'models': ['5160', '5260', '5970', '5971', '5972', '5979', '5980', '8160', '8460'],
        'paper': pagesizes.letter,
        'topMargin': 0.5,
        'lateralMargin': 0.1875,
        'columns': 3,
        'rows': 10,
        'height': 1,
        'width': 2.625,  # label width
        'verticalSpacing': 0,
        'horizontalSpacing': 0.125,
        'units': inch,
    },
    {
        'cia': 'Pimaco',
        'models': ['6081', '6181', '6281', '0081', '62581', '62681'],
        'paper': pagesizes.letter,
        'topMargin': 1.27,
        'bottomMargin': 1.20,
        'lateralMargin': 0.377,
        'leftMargin': 0.377,
        'rightMargin': 0.377,
        'columns': 2,
        'rows': 10,
        'height': 2.54,
        'width': 10.16,
        'units': cm,
    },
    {
        'cia': 'Pimaco',
        'models': ['6080', '6180', '6280', '0080', '62580', '62680', 'A4255', 'A4055'],
        'paper': pagesizes.letter,
        'topMargin': 1.20,
        'lateralMargin': 0.48,
        'columns': 3,
        'rows': 10,
        'height': 2.54,
        'width': 6.67,
        'verticalSpacing': 0,
        'horizontalSpacing': 0.31,
        'horizontalPadding': 0.25,
        'units': cm,
    },
    {
        'cia': 'Pimaco',
        'models': ['6082', '6182', '6282', '0082', '62582', '62682'],
        'paper': pagesizes.letter,
        'topMargin': 2.12,
        'bottomMargin': 2.12,
        'lateralMargin': 0.377,
        'leftMargin': 0.377,
        'rightMargin': 0.377,
        'verticalSpacing': 0,
        'horizontalSpacing': 0.516,
        'columns': 2,
        'rows': 7,
        'height': 3.39,
        'width': 10.16,
        'units': cm,
    },
    {
        'cia': 'Pimaco',
        'models': ['6083'],
        'paper': pagesizes.letter,
        'topMargin': 1.27,
        'bottomMargin': 1.27,
        'lateralMargin': 0.377,
        'verticalSpacing': 0,
        'horizontalSpacing': 0.516,
        'columns': 2,
        'rows': 5,
        'height': 5.08,
        'width': 10.16,
        'units': cm,
    },
    {
        'cia': 'Pimaco',
        'models': ['6287'],
        'paper': pagesizes.letter,
        'topMargin': 1.27,
        'bottomMargin': 1.27,
        'lateralMargin': 1.45,
        'verticalSpacing': 0.01,
        'horizontalSpacing': 0.31,
        'horizontalPadding': 1.50,
        'columns': 4,
        'rows': 20,
        'width': 4.44,
        'height': 1.27,
        'units': cm,
    },
    {
        'cia': 'Pimaco',
        'models': ['A4366'],
        'paper': pagesizes.letter,
        'topMargin': 1.27,
        'bottomMargin': 1.27,
        'lateralMargin': 1.45,
        'verticalSpacing': 0.01,
        'horizontalSpacing': 0.31,
        'horizontalPadding': 1.50,
        'columns': 2,
        'rows': 3,
        'width': 9.91,
        'height': 9.31,
        'units': cm,
    },
)


class LabelGenerator:
    smallestFont = 3

    def __init__(self, spec):
        self.cia = spec['cia']
        self.models = spec['models']
        self.paper = spec['paper']
        self.cols = spec['columns']  # labels em cada coluna
        self.rows = spec['rows']  # numero de linhas dos labels

        self.un = self.units = spec.get('units', mm)

        self.topMargin = spec['topMargin'] * self.un
        self.leftMargin = spec.get('leftMargin', spec['lateralMargin']) * self.un
        self.rightMargin = spec.get('rightMargin', spec['lateralMargin']) * self.un

        self.height = spec['height'] * self.un
        self.width = spec['width'] * self.un

        self.vertSpacing = spec.get('verticalSpacing', 0) * self.un
        self.horizSpacing = spec.get('horizontalSpacing', 0) * self.un

        self.font = 'Helvetica'
        self.size = 14
        self.leadingFactor = 1.1

        try:
            self.vertPadding = spec['verticalPadding'] * self.un
        except KeyError:
            self.vertPadding = self.height // 15
        try:
            self.horizPadding = spec['horizontalPadding'] * self.un
        except KeyError:
            self.horizPadding = self.width // 15

        self.maxTextWidth = self.width - 2 * self.horizPadding
        self.maxTextHeight = self.height - 2 * self.vertPadding

        self.grid = 0

    def start(self, filename):
        self.canvas = canvas.Canvas(filename, self.getPageSize())
        if hasattr(self, 'compress'):
            self.canvas.setPageCompression(self.compress)
        self.canvas.setFont(self.font, self.size, self.leadingFactor * self.size)

        self.pos = 0

    def setCompression(self):
        self.compress = 1

    def setVerticalPadding(self, value):
        self.vertPadding = value

    def setHorizontalPadding(self, value):
        self.horizPadding = value

    def fit(self, pdf, text):
        if type(text) is str:
            t = text.split('\n')
        else:
            t = text

        f = None
        fontSize = self.size
        while fontSize >= self.smallestFont:
            try:
                modifiedText = self.fitHorizontal(t, fontSize, f)
                textHeight = self.fitVertical(modifiedText, fontSize)
                pdf.setFont(self.font, fontSize, self.leadingFactor * fontSize)
                pdf.moveCursor(0, fontSize)
                pdf.moveCursor(0, (self.maxTextHeight - textHeight) // 2)
                pdf.textLines(modifiedText)
                return
            except Error:
                fontSize = fontSize - 1
            except Error2:
                fontSize = fontSize - 1
        raise Error(
            'Não é possível criar a etiqueta, ajuste o texto ou use um rótulo de maior \n'
            + repr(text)
            + ' '
            + repr(self.smallestFont)
            + ' '
            + repr(fontSize)
        )

    def fitHorizontal(self, t, fontSize, debugFile=None):
        modifiedText = []
        for line in t:
            if debugFile:
                debugFile.write(line + '\n')
                debugFile.flush()
            modifiedText = modifiedText + self.adaptHorizontal(line, fontSize, debugFile)
        return modifiedText

    def adaptHorizontal(self, line, fontSize, debugFile):
        if line == '':
            return ['']
        words = line.split()
        pos = len(words)
        if pos == 0:
            return [' '.join(words[:pos])]
        else:
            while pos > 0:
                width = self.canvas.stringWidth(removeAccents(' '.join(words[:pos])), self.font, fontSize)

                if debugFile:
                    debugFile.write(repr(width) + ':' + repr(self.maxTextWidth) + '\n')
                    debugFile.flush()

                if width > self.maxTextWidth:
                    pos = pos - 1
                elif pos == len(words):
                    return [' '.join(words[:pos])]
                else:
                    return [' '.join(words[:pos]), *self.adaptHorizontal(' '.join(words[pos:]), fontSize, debugFile)]
        raise Error('Não pode fazer a linha de ajuste no rótulo, cortar o texto ou usar um rótulo de maior')

    def fitVertical(self, text, fontSize):
        numLines = len(text)
        textHeight = self.leadingFactor * fontSize * numLines - (self.leadingFactor - 1) * fontSize
        if textHeight > self.maxTextHeight:
            raise Error2('Label muito alto')
        return textHeight

    def getPageSize(self):
        try:
            return self.paper
        except KeyError:
            raise Error('Não é possivel reorganizar o tamanho da página.')

    def getPageX(self):
        return self.paper[0]

    def getPageY(self):
        return self.paper[1]

    def getCoordinates(self):
        x0 = self.leftMargin
        y0 = self.getPageY() - self.topMargin

        col = self.pos % self.cols
        row = self.pos // self.cols

        x = x0 + col * (self.width + self.horizSpacing) + self.horizPadding
        y = y0 - row * (self.height + self.vertSpacing) - self.vertPadding
        return x, y

    def nextPos(self):
        self.pos = self.pos + 1
        if self.pos != self.pos % (self.cols * self.rows):
            self.canvas.showPage()
            self.pos = self.pos % (self.cols * self.rows)
            if self.grid:
                self.drawGrid()

    def generate(self, etiquetas, filename):
        self.start(filename)
        if self.grid:
            self.drawGrid()
        self.drawDistances()
        for i in etiquetas:
            x, y = self.getCoordinates()
            t = self.canvas.beginText(x, y)
            self.fit(t, i)
            self.canvas.drawText(t)
            self.nextPos()
        self.canvas.save()

    def setGrid(self, turnOn=1):
        self.grid = turnOn

    def drawGrid(self):
        borderX = []  # label border
        borderY = []
        frameX = []  # content area border, counting padding
        frameY = []
        bx = self.leftMargin
        by = self.getPageY() - self.topMargin
        borderX.append(bx)
        borderY.append(by)
        fx = bx + self.horizPadding
        fy = by - self.vertPadding
        frameX.append(fx)
        frameY.append(fy)
        for j in range(self.cols):
            bx = bx + self.width
            borderX.append(bx)
            bx = bx + self.horizSpacing
            borderX.append(bx)

            fx = fx + self.width
            frameX.append(fx - 2 * self.horizPadding)
            if j != self.cols - 1:
                fx = fx + self.horizSpacing
                frameX.append(fx)

        for i in range(self.rows):
            by = by - self.height
            borderY.append(by)
            by = by - self.vertSpacing
            borderY.append(by)

            fy = fy - self.height
            frameY.append(fy + 2 * self.vertPadding)
            if i != self.rows - 1:
                fy = fy - self.vertSpacing
                frameY.append(fy)
        self.canvas.grid(borderX, borderY)
        self.canvas.setStrokeGray(0.75)
        self.canvas.grid(frameX, frameY)
        self.canvas.setStrokeGray(0)

    def drawDistances(self):
        halfX = self.paper[0] // 2
        halfY = self.paper[1] // 2
        marginY = self.paper[1] - self.topMargin
        marginX = self.leftMargin
        # top border
        self.canvas.line(halfX, self.paper[1], halfX, marginY)
        self.canvas.line(marginX // 2, self.paper[1], marginX // 2, marginY)
        self.canvas.line(self.paper[0] - marginX // 2, self.paper[1], self.paper[0] - marginX // 2, marginY)
        # left border
        self.canvas.line(0, halfY, marginX, halfY)
        self.canvas.line(0, self.paper[1] - self.topMargin // 2, marginX, self.paper[1] - self.topMargin // 2)
        self.canvas.line(0, self.topMargin // 2, marginX, self.paper[1] - marginY // 2)


def findLabel(cia, labelsPerPage=None):
    found = []
    for spec in LABELS:
        if spec['cia'].lower() == cia.lower():
            if (labelsPerPage is None) or (labelsPerPage == spec['rows'] * spec['columns']):
                found.append(spec)
    return found


def labelTypes():
    lt = {}
    for spec in LABELS:
        t = lt.get(spec['cia'], [])
        for i in spec['models']:
            t.append((i, repr(spec['columns']) + 'x' + repr(spec['rows'])))
        lt[spec['cia']] = t
    return lt


def factory(cia, model):
    for spec in LABELS:
        if spec['cia'].lower() == cia.lower():
            if model in spec['models']:
                return LabelGenerator(spec)
    raise Error('Não é possível encontrar o modelo do label')


_convertEntitys = {j: i for i, j in entitydefs.items()}


def removeAccents(text):
    pos = i = 0
    newText = []
    while i < len(text):
        if ord(text[i]) > 128:
            newText.append(text[pos:i])
            try:
                newText.append(_convertEntitys[text[i]][0])
            except KeyError:
                pass
            pos = i + 1
        i = i + 1
    newText.append(text[pos:])

    return ''.join(newText)


# Testes retirados do PDF Label


def test():
    example = [
        'Testing the labels',
        'This is the example of a lot of lines\n11111111111111111\n2222222222222\n3333333333333333333\n4444444444444',
        'XXXXXXXXXXXXXXXXXXXX',
        'abc\nefg\nhij\nklm\n·',
        'Just another one',
    ]
    example = example * 16
    labels = LabelGenerator(findLabel('test')[0])
    labels.setGrid()
    labels.generate(example, 'labelstest.pdf')


def test2():
    example = [
        'Testing the labels',
        'This is the example of a lot of lines\n11111111111111111\n2222222222222\n3333333333333333333\n4444444444444',
        'XXXXXXXXXXXXXXXXXXXX',
        '￡b￧\n￩fg ￵\na￪￧￴\n',
        'abc\nefg o\naeco\naeiouecaao',
        'Just another one',
    ]
    example = example * 5
    labels = factory('Pimaco', '6080')
    labels.setGrid()
    import io

    f = io.BytesIO()
    # import sys; f=sys.stdout
    labels.generate(example, f)
    ff = open('labelstest2.pdf', 'wb')
    f.seek(0)
    # print f.read(),1
    ff.write(f.read())
    ff.close()
    f.close()


def test3():
    example = ['0001', '0002', '0003', '0004']
    example = example * 5
    labels = factory('Pimaco', '6287')
    labels.setGrid()
    import io

    f = io.BytesIO()
    # import sys; f=sys.stdout
    labels.generate(example, f)
    ff = open('labelstest2.pdf', 'wb')
    f.seek(0)
    # print f.read(),1
    ff.write(f.read())
    ff.close()
    f.close()


if __name__ == '__main__':
    test3()
