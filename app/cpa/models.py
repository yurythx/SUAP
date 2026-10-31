import datetime
import re

from djtools.db import models
from djtools.utils import to_ascii
from rh.models import UnidadeOrganizacional


class Questionario(models.ModelPlus):
    GERAL = 0
    ALUNO = 1
    TECNICO = 2
    DOCENTE = 3
    PAI_ALUNO = 4
    EMPRESA = 5
    PUBLICO_CHOICES = [
        [GERAL, 'Geral'],
        [ALUNO, 'Alunos'],
        [TECNICO, 'Técnicos'],
        [DOCENTE, 'Docentes'],
    ]  # , [PAI_ALUNO, u'Pais de Alunos'], [EMPRESA, u'Empresas']]

    REGEX = re.compile("'[^']*'")

    descricao = models.CharField(verbose_name='Descrição', max_length=255)
    titulo_alerta = models.CharField(
        verbose_name='Título do alerta',
        help_text='Será exibido na página inicial -  Ex: Avalie o nível de satisfação com a instituição nesse trimestre',
        max_length=255,
        default='Realize sua avaliação institucional',
    )
    texto_explicativo = models.TextField(
        verbose_name='Texto explicativo',
        help_text='Será exibido na página do questionário como uma introdução',
        null=True,
        blank=True,
    )
    publico = models.IntegerField(choices=PUBLICO_CHOICES, verbose_name='Público')
    ano = models.IntegerField()
    data_inicio = models.DateField(verbose_name='Data de Início')
    data_fim = models.DateField(verbose_name='Data de Término')
    dicionario = models.TextField(null=True, blank=True, verbose_name='Dicionário', help_text='Ex: IFRN: Instituto Federal do...')
    campus = models.ManyToManyFieldPlus('rh.UnidadeOrganizacional', verbose_name='Campus', blank=True)
    aceitar_apenas_uma_resposta = models.BooleanField(
        verbose_name='Aceitar apenas uma resposta',
        help_text='Se marcado, o usuário só poderá responder uma vez',
        default=False,
    )

    class Meta:
        verbose_name = 'Questionário'
        verbose_name_plural = 'Questionários'

    def __str__(self):
        return f'{self.descricao} {self.get_publico_display()} {self.get_campus()}'

    def get_dicionario(self):
        dicionario = {}
        if self.dicionario:
            for linha in self.dicionario.split('\r\n'):
                tokens = linha.split(':')
                if tokens and len(tokens) > 1:
                    dicionario[to_ascii(tokens[0])] = tokens[1]
        return dicionario

    def get_perguntas_agrupadas_por_categoria(self):
        categorias = self.get_categorias()
        for categoria in categorias:
            categoria.perguntas = self.pergunta_set.filter(categoria=categoria).order_by('ordem')
        return categorias

    def get_respostas_objetivas(self, identificador):
        qs = Resposta.objects.filter(pergunta__questionario=self, pergunta__objetiva=True)
        qs = qs.filter(identificador=identificador)
        return qs

    def get_percentual_respondido(self, user):
        total = Pergunta.objects.filter(questionario=self, objetiva=True).count()
        if not total:
            return 0
        respondido = self.get_respostas_objetivas(user.username).count()
        return int(respondido * 100 / total)

    def get_categorias(self):
        return Categoria.objects.filter(questionariocategoria__questionario=self).order_by('questionariocategoria__ordem')

    def get_opcoes(self):
        return Opcao.objects.filter(questionarioopcao__questionario=self).order_by('questionarioopcao__ordem')

    @staticmethod
    def get_pendente(user):
        publico = None
        try:
            # TODO: fazer uma função que retorne o tipo de usuário, pois cada um está fazendo de um jeito
            if user.eh_aluno:
                publico = Questionario.ALUNO
            elif user.eh_docente:
                publico = Questionario.DOCENTE
            elif user.eh_tecnico_administrativo:
                publico = Questionario.TECNICO
        except Exception:
            pass
        setor_usuario = user.get_vinculo().setor
        if not setor_usuario:
            return None
        publico_alvo = [Questionario.GERAL]
        if publico:
            publico_alvo.append(publico)

        qs = Questionario.objects.filter(
            data_inicio__lte=datetime.datetime.today(), data_fim__gte=datetime.datetime.today(), publico__in=publico_alvo
        )
        qs = qs.filter(campus=setor_usuario.uo)
        if qs.exists():
            return qs.latest('id')
        return None

    def get_absolute_url(self):
        return f'/cpa/questionario/{self.id}/'

    def get_campus(self):
        return ', '.join(self.campus.values_list('sigla', flat=True))

    @staticmethod
    def questionario_pode_ser_respondido(user, questionario):
        if questionario.aceitar_apenas_uma_resposta:
            return not Resposta.objects.filter(identificador=user.username, pergunta__questionario=questionario).exists()
        return True


class Categoria(models.ModelPlus):
    nome = models.CharField(max_length=255)

    class Meta:
        verbose_name_plural = 'Categorias'
        verbose_name = 'Categoria'

    def __str__(self):
        return self.nome

    def get_perguntas(self, ano_referencia):
        return self.pergunta_set.filter(ano=ano_referencia).order_by('id')


class QuestionarioCategoria(models.ModelPlus):
    questionario = models.ForeignKeyPlus(Questionario, on_delete=models.CASCADE)
    categoria = models.ForeignKeyPlus(Categoria, on_delete=models.CASCADE)
    ordem = models.IntegerField()

    class Meta:
        verbose_name_plural = 'Categoria do questionário'
        verbose_name = 'Categorias do questionário'
        ordering = ('ordem',)

    def __str__(self):
        return ''


class Opcao(models.ModelPlus):
    nome = models.CharField(max_length=255)
    emoji = models.CharFieldPlus('Emoji', max_length=10, null=True, blank=True)

    class Meta:
        verbose_name_plural = 'Opção'
        verbose_name = 'Opções'
        ordering = ('nome',)

    def __str__(self):
        return f'{self.emoji} {self.nome}' if self.emoji else self.nome


class QuestionarioOpcao(models.ModelPlus):
    questionario = models.ForeignKeyPlus(Questionario, on_delete=models.CASCADE)
    opcao = models.ForeignKeyPlus(Opcao, on_delete=models.CASCADE)
    ordem = models.IntegerField()
    agrupamento = models.CharField(
        'Nome do Agrupamento', max_length=255, help_text='Os gráficos dos resultados agrupados irão levar esse campo em consideração', blank=True
    )

    class Meta:
        verbose_name_plural = 'Opção de resposta'
        verbose_name = 'Opções de resposta'
        ordering = ('ordem',)

    def __str__(self):
        return ''


class Pergunta(models.ModelPlus):
    questionario = models.ForeignKeyPlus(Questionario, on_delete=models.CASCADE)
    categoria = models.ForeignKeyPlus(Categoria, on_delete=models.CASCADE)
    texto = models.TextField(help_text="Palavras relacionadas ao dicionário de dados devem estar entre aspas simples. Ex: 'IFRN'")
    objetiva = models.BooleanField(default=False)
    ordem = models.IntegerField()
    identificador = models.CharField(max_length=255)

    class Meta:
        verbose_name_plural = 'Perguntas'
        verbose_name = 'Pergunta'
        ordering = ('ordem',)

    def __str__(self):
        return f'{self.ordem:d} - {self.texto}'

    def get_html(self):
        """
        Retorna o texto da pergunta em formato HTML com os "helps" correspondentes ao dicionário do questionário
        """
        dicionario = self.questionario.get_dicionario()
        html = self.texto
        for token in Questionario.REGEX.findall(self.texto):
            key = to_ascii(token.replace("'", ''))
            html = html.replace(
                token,
                "<strong class='text hint hint-bottom' aria-label='{}'>{}</strong>".format(
                    key in dicionario and dicionario[key] or '', token.replace("'", '')
                ),
            )
        return html

    def get_resposta(self, request):
        if request.user.is_authenticated:
            if hasattr(request.user.get_relacionamento(), 'curso_campus'):
                uo = request.user.get_relacionamento().curso_campus.diretoria.setor.uo
            else:
                uo = request.user.get_relacionamento().setor.uo
            identificador = request.user.username
            referencia = None
        else:
            uo = UnidadeOrganizacional.objects.suap().get(pk=request.GET['uo'])
            identificador = request.GET['identificador']
            referencia = request.GET['referencia']
        qs = self.resposta_set.filter(identificador=identificador, uo=uo)
        if qs:
            resposta = qs[0]
        else:
            resposta = Resposta()
            resposta.pergunta = self
            resposta.resposta = ''
        resposta.identificador = identificador
        resposta.uo = uo
        resposta.referencia = referencia
        return resposta


class Resposta(models.ModelPlus):
    identificador = models.CharField(max_length=255)
    referencia = models.CharField(max_length=255, null=True, blank=True)
    pergunta = models.ForeignKeyPlus(Pergunta, on_delete=models.CASCADE)
    uo = models.ForeignKeyPlus(UnidadeOrganizacional, related_name='respostaautoavaliacao_uo_set', null=True, on_delete=models.CASCADE)
    resposta = models.TextField(help_text='Resposta')
    opcao = models.ForeignKeyPlus(Opcao, null=True, help_text='Resposta objetiva', on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Resposta'
        verbose_name_plural = 'Respostas'

    def __str__(self):
        return self.resposta

    def is_valida(self):
        if self.pergunta.objetiva:
            return bool(self.opcao)
        else:
            return True
