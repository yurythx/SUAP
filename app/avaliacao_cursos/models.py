from datetime import date

from comum import utils
from comum.models import Ano, UsuarioGrupo
from djtools.db import models
from djtools.forms.widgets import CheckboxSelectMultiplePlus
from edu.models import Aluno, ComponenteCurricular, Diretoria, Professor, ProfessorDiario
from edu.models.cadastros_gerais import Modalidade
from edu.models.cursos import CursoCampus, Matriz
from rh.models import Servidor, Setor


class Segmento(models.ModelPlus):
    ALUNO = 1
    PROFESSOR = 2
    COORDENADOR_CURSO = 3
    DIRETOR_ENSINO = 4
    DIRETOR_ACADEMICO = 5
    COORDENADOR_PEDAGOGICO = 6
    MEMBRO_ETEP = 7
    TECNICO_ADMINISTRATIVO = 8
    DIRETOR_GERAL = 9

    descricao = models.CharFieldPlus('Descrição')
    forma_identificacao = models.TextField('Forma de Identificação', null=True, blank=False)

    class Meta:
        verbose_name = 'Segmento Respondente'
        verbose_name_plural = 'Segmentos Respondentes'
        ordering = ('id',)

    def __str__(self):
        return self.descricao


class Avaliacao(models.ModelPlus):
    ano = models.ForeignKeyPlus(Ano, verbose_name='Ano', on_delete=models.CASCADE, related_name='ano_avaliacao_set')
    descricao = models.CharFieldPlus(verbose_name='Descrição')

    explicacao_introducao = models.TextField(
        verbose_name='Explicação - Introdução', help_text='Texto explicativo da introdução do questionário', null=True, blank=True
    )
    explicacao_parte_1 = models.TextField(
        verbose_name='Explicação - PARTE 1', help_text='Texto explicativo da primeira parte (avaliação das matrizes)', null=True, blank=True
    )
    explicacao_parte_2 = models.TextField(
        verbose_name='Explicação - PARTE 2', help_text='Texto explicativo da segunda parte (questionário livre)', null=True, blank=True
    )

    class Meta:
        verbose_name = 'Avaliação'
        verbose_name_plural = 'Avaliações'
        ordering = ('id',)

    def __str__(self):
        return self.descricao

    def get_absolute_url(self):
        return f'/avaliacao_cursos/avaliacao/{self.pk}/'

    def get_segmentos(self):
        segmentos = Segmento.objects.filter(pk__in=self.questionario_set.values_list('segmentos', flat=True))
        return ', '.join([segmento.descricao for segmento in segmentos])

    def get_modalidades(self):
        modalidades = Modalidade.objects.filter(pk__in=self.questionario_set.values_list('modalidades', flat=True))
        return ', '.join([modalidade.descricao for modalidade in modalidades])

    def get_qtd_respondentes(self, uo=None, segmento=None):
        qs = Respondente.objects.filter(questionario__avaliacao=self)
        if uo:
            qs = qs.filter(setor__uo=uo)
        if segmento:
            qs = qs.filter(segmento=segmento)
        return qs.count()

    def get_qtd_finalizados(self, uo=None, segmento=None):
        qs = Respondente.objects.filter(questionario__avaliacao=self, finalizado=True)
        if uo:
            qs = qs.filter(setor__uo=uo)
        if segmento:
            qs = qs.filter(segmento=segmento)
        return qs.count()

    def get_qtd_iniciado(self, uo=None, segmento=None):
        qs = Resposta.objects.filter(respondente__questionario__avaliacao=self)
        if uo:
            qs = qs.filter(respondente__setor__uo=uo)
        if segmento:
            qs = qs.filter(respondente__segmento=segmento)
        return qs.values_list('respondente').order_by('respondente').distinct().count()

    def get_qtd_respondentes_discente(self, uo=None, modalidade=None):
        qs = Respondente.objects.filter(questionario__avaliacao=self)
        if uo:
            qs = qs.filter(setor__uo=uo)
        if modalidade:
            ids_alunos = Aluno.objects.filter(curso_campus__modalidade=modalidade).values_list('id', flat=True)
            qs = qs.filter(vinculo__tipo_relacionamento__model='aluno', vinculo__id_relacionamento__in=ids_alunos)
        return qs.count()

    def get_qtd_finalizados_discente(self, uo=None, modalidade=None):
        qs = Respondente.objects.filter(questionario__avaliacao=self, finalizado=True)
        if uo:
            qs = qs.filter(setor__uo=uo)
        if modalidade:
            ids_alunos = Aluno.objects.filter(curso_campus__modalidade=modalidade).values_list('id', flat=True)
            qs = qs.filter(vinculo__tipo_relacionamento__model='aluno', vinculo__id_relacionamento__in=ids_alunos)
        return qs.count()

    def get_qtd_iniciado_discente(self, uo=None, modalidade=None):
        qs = Resposta.objects.filter(respondente__questionario__avaliacao=self)
        if uo:
            qs = qs.filter(respondente__setor__uo=uo)
        if modalidade:
            ids_alunos = Aluno.objects.filter(curso_campus__modalidade=modalidade).values_list('id', flat=True)
            qs = qs.filter(respondente__vinculo__tipo_relacionamento__model='aluno', respondente__vinculo__id_relacionamento__in=ids_alunos)
        return qs.values_list('respondente').order_by('respondente').distinct().count()

    def get_matrizes_avaliadas_por_alunos(self):
        pks = (
            AvaliacaoComponenteCurricular.objects.filter(respondente__questionario__avaliacao=self)
            .order_by('componente_curricular__matriz')
            .values_list('componente_curricular__matriz', flat=True)
            .distinct()
        )
        return Matriz.objects.filter(pk__in=pks)


class Questionario(models.ModelPlus):
    avaliacao = models.ForeignKeyPlus(Avaliacao, verbose_name='Avaliação', on_delete=models.CASCADE, null=True)
    segmentos = models.ManyToManyField(Segmento, verbose_name='Segmentos')
    modalidades = models.ManyToManyField(Modalidade, verbose_name='Modalidades')

    data_inicio = models.DateFieldPlus(verbose_name='Data de Início')
    data_termino = models.DateFieldPlus(verbose_name='Data de Término')

    matrizes = models.ManyToManyFieldPlus(Matriz, verbose_name='Matrizes', blank=True)

    class Meta:
        verbose_name = 'Questionário'
        verbose_name_plural = 'Questionários'
        ordering = ('id',)

    def identificar_respondentes(self, excluir=False):
        if excluir:
            Respondente.objects.filter(questionario=self, resposta__isnull=True).delete()

        for segmento in self.segmentos.all():
            if segmento.pk == Segmento.DIRETOR_GERAL:
                for diretoria in Diretoria.objects.all():
                    if diretoria.diretor_geral:
                        Respondente.objects.get_or_create(
                            questionario=self, segmento=segmento, vinculo=diretoria.diretor_geral.get_vinculo(), setor=diretoria.setor
                        )

            # Tratamento necessário para a DE/CNAT.
            elif segmento.pk == Segmento.DIRETOR_ENSINO:
                diretoria = Diretoria.objects.filter(setor__sigla__contains='DE/')
                if diretoria.exists() and diretoria[0].diretor_academico:
                    Respondente.objects.get_or_create(
                        questionario=self, segmento=segmento, vinculo=diretoria[0].diretor_academico.get_vinculo(), setor=diretoria[0].setor
                    )

            elif segmento.pk == Segmento.DIRETOR_ACADEMICO:
                for diretoria in Diretoria.objects.exclude(pk=27):
                    if diretoria.diretor_academico:
                        Respondente.objects.get_or_create(
                            questionario=self, segmento=segmento, vinculo=diretoria.diretor_academico.get_vinculo(), setor=diretoria.setor
                        )

            elif segmento.pk == Segmento.COORDENADOR_CURSO:
                for curso_campus in CursoCampus.objects.filter(
                    coordenador__isnull=False,
                    modalidade__in=self.modalidades.all(),
                    matrizcurso__matriz__in=self.matrizes.values_list('id', flat=True),
                ):
                    if curso_campus.coordenador:
                        Respondente.objects.get_or_create(
                            questionario=self, segmento=segmento, vinculo=curso_campus.coordenador, setor=curso_campus.diretoria.setor
                        )

            elif segmento.pk == Segmento.MEMBRO_ETEP:
                qs = UsuarioGrupo.objects.filter(group__name='Membro ETEP')
                for usuario_grupo in qs:
                    if not usuario_grupo.user.eh_docente:
                        vinculo = usuario_grupo.user.get_vinculo()
                        if vinculo.setor and vinculo.setor.uo:
                            Respondente.objects.get_or_create(questionario=self, segmento=segmento, vinculo=vinculo, setor=vinculo.setor.uo.setor)

            elif segmento.pk == Segmento.PROFESSOR:
                ids = (
                    ProfessorDiario.objects.filter(diario__componente_curricular__matriz__in=self.matrizes.values_list('id', flat=True))
                    .filter(diario__turma__curso_campus__modalidade__in=self.modalidades.all())
                    .values_list('professor__pk', flat=True)
                    .distinct()
                )
                for professor in Professor.objects.filter(pk__in=ids):
                    if professor.vinculo.setor:
                        Respondente.objects.get_or_create(
                            questionario=self, segmento=segmento, vinculo=professor.vinculo, setor=professor.vinculo.setor
                        )

            elif segmento.pk == Segmento.ALUNO:
                periodo_atual = 3
                for aluno in Aluno.ativos.filter(
                    periodo_atual__gte=periodo_atual,
                    curso_campus__modalidade__in=self.modalidades.all(),
                    matriz__in=self.matrizes.values_list('id', flat=True),
                ):
                    Respondente.objects.get_or_create(
                        questionario=self, segmento=segmento, vinculo=aluno.get_vinculo(), setor=aluno.curso_campus.diretoria.setor
                    )

            elif segmento.pk == Segmento.COORDENADOR_PEDAGOGICO:
                diretoria = Diretoria.objects.filter(setor__sigla__contains='DE/')
                if diretoria.exists():
                    qs = UsuarioGrupo.objects.filter(group__name='Pedagogo', setores=diretoria[0].setor)
                    for usuario_grupo in qs:
                        Respondente.objects.get_or_create(
                            questionario=self, segmento=segmento, vinculo=usuario_grupo.user.get_vinculo(), setor=diretoria[0].setor
                        )

            elif segmento.pk == Segmento.TECNICO_ADMINISTRATIVO:
                qs = Servidor.objects.tecnicos_administrativos().exclude(setor__uo__sigla=utils.get_sigla_reitoria())
                for servidor in qs:
                    if servidor.setor and servidor.setor.uo:
                        Respondente.objects.get_or_create(
                            questionario=self, segmento=segmento, vinculo=servidor.get_vinculo(), setor=servidor.setor.uo.setor
                        )

    def get_absolute_url(self):
        return f'/avaliacao_cursos/questionario/{self.pk}/'

    def get_segmentos(self):
        return ', '.join([segmento.descricao for segmento in self.segmentos.all()])

    def get_modalidades(self):
        return ', '.join([modalidade.descricao for modalidade in self.modalidades.all()])

    def __str__(self):
        return f'Questionário de {self.avaliacao.ano} ({self.get_segmentos()})'


class GrupoPergunta(models.ModelPlus):
    questionario = models.ForeignKeyPlus(Questionario, verbose_name='Questionário', on_delete=models.CASCADE)
    descricao = models.TextField('Descrição')

    class Meta:
        verbose_name = 'Grupo de Pergunta'
        verbose_name_plural = 'Grupo de Pergunta'
        ordering = ('id',)

    def __str__(self):
        return self.descricao

    def possui_pergunta_com_escala_padrao(self):
        return self.pergunta_set.filter(tipo_resposta=Pergunta.RESPOSTA_ESCALA_PADRAO).exists()


class Pergunta(models.ModelPlus):
    RESPOSTA_BOOLEANA_CHOICES = (('', ''), ('Sim', 'Sim'), ('Não', 'Não'))
    RESPOSTA_ESCALA_PADRAO_CHOICES = (
        ('', ''),
        ('Desconheço', 'Desconheço'),
        ('Insuficiente', 'Insuficiente'),
        ('Regular', 'Regular'),
        ('Bom', 'Bom'),
        ('Ótimo', 'Ótimo'),
    )
    RESPOSTA_FAIXA_1_CHOICES = [(x, x) for x in ('', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'Não sei avaliar', 'Não se aplica')]
    RESPOSTA_FAIXA_2_CHOICES = [(x, x) for x in ('', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'Não sei avaliar', 'Não se aplica')]

    RESPOSTA_BOOLENADA = 1
    RESPOSTA_ESCALA_PADRAO = 2
    RESPOSTA_SUBJETIVA = 3
    RESPOSTA_OBJETIVA = 4

    RESPOSTA_ESCALA_QUALIDADE = 5
    RESPOSTA_ESCALA_SUFICIENCIA = 6
    RESPOSTA_ESCALA_SATISFACAO = 7
    RESPOSTA_ESCALA_CONCORDANCIA = 8

    TIPO_RESPOSTA_CHOICES = (
        (RESPOSTA_BOOLENADA, 'SIM/NÃO'),
        (RESPOSTA_ESCALA_PADRAO, 'ESCALA PADRÃO'),
        (RESPOSTA_ESCALA_SUFICIENCIA, 'ESCALA DE SUFICIÊNCIA'),
        (RESPOSTA_ESCALA_SATISFACAO, 'ESCALA DE SATISFAÇÃO'),
        (RESPOSTA_ESCALA_QUALIDADE, 'ESCALA DE QUALIDADE'),
        (RESPOSTA_ESCALA_CONCORDANCIA, 'ESCALA DE CONCORDÂNCIA'),
        (RESPOSTA_SUBJETIVA, 'SUBJETIVA'),
        (RESPOSTA_OBJETIVA, 'OBJETIVA'),
    )

    enunciado = models.CharFieldPlus('Enunciado')
    grupo_pergunta = models.ForeignKeyPlus(GrupoPergunta, verbose_name='Grupo de Pergunta', on_delete=models.CASCADE)
    tipo_resposta = models.IntegerField('Tipo de Resposta', choices=TIPO_RESPOSTA_CHOICES)
    multipla_escolha = models.BooleanField(verbose_name='Múltipla Escolha?', default=False)
    obrigatoria = models.BooleanField(verbose_name='Obrigatória?', default=False)

    class Meta:
        verbose_name = 'Pergunta'
        verbose_name_plural = 'Perguntas'
        ordering = ('id',)

    def __str__(self):
        return self.enunciado

    def get_choices(self):
        choices = []
        qs = self.opcaorespostapergunta_set.all()

        for valor in qs.values_list('valor', flat=True):
            choices.append([valor, valor])
        return choices

    def get_form_field(self, initial=None):
        from djtools import forms as fields

        if self.tipo_resposta == Pergunta.RESPOSTA_BOOLENADA:
            field = fields.ChoiceField(choices=Pergunta.RESPOSTA_BOOLEANA_CHOICES, label=self.enunciado, required=False, initial=initial)
        elif self.tipo_resposta == Pergunta.RESPOSTA_ESCALA_PADRAO:
            field = fields.ChoiceField(choices=Pergunta.RESPOSTA_ESCALA_PADRAO_CHOICES, label=self.enunciado, required=False, initial=initial)
        elif self.tipo_resposta == Pergunta.RESPOSTA_ESCALA_CONCORDANCIA or self.tipo_resposta == Pergunta.RESPOSTA_ESCALA_SATISFACAO:
            field = fields.ChoiceField(choices=Pergunta.RESPOSTA_FAIXA_1_CHOICES, label=self.enunciado, required=False, initial=initial)
        elif self.tipo_resposta == Pergunta.RESPOSTA_ESCALA_QUALIDADE or self.tipo_resposta == Pergunta.RESPOSTA_ESCALA_SUFICIENCIA:
            field = fields.ChoiceField(choices=Pergunta.RESPOSTA_FAIXA_2_CHOICES, label=self.enunciado, required=False, initial=initial)
        elif self.tipo_resposta == Pergunta.RESPOSTA_SUBJETIVA:
            field = fields.CharField(label=self.enunciado, required=False, widget=fields.Textarea(), initial=initial)
        elif self.tipo_resposta == Pergunta.RESPOSTA_OBJETIVA:
            if self.multipla_escolha:
                field = fields.MultipleChoiceField(
                    label=self.enunciado, choices=self.get_choices(), required=False, widget=CheckboxSelectMultiplePlus(), initial=initial
                )
            else:
                field = fields.ChoiceField(
                    label=self.enunciado, choices=self.get_choices(), required=False, widget=fields.RadioSelect(), initial=initial
                )

        return field


class OpcaoRespostaPergunta(models.ModelPlus):
    pergunta = models.ForeignKeyPlus(Pergunta, verbose_name='Pergunta', on_delete=models.CASCADE)
    valor = models.CharFieldPlus()

    class Meta:
        verbose_name = 'Opção de Resposta para uma Pergunta'
        verbose_name_plural = 'Opções de Resposta para uma Pergunta'
        ordering = ('id',)


class Respondente(models.ModelPlus):
    SEARCH_FIELDS = ['segmento__descricao', 'questionario__avaliacao__descricao']
    questionario = models.ForeignKeyPlus(Questionario, verbose_name='Questionário', on_delete=models.CASCADE)
    segmento = models.ForeignKeyPlus(Segmento, verbose_name='Segmento', on_delete=models.CASCADE)
    vinculo = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Vínculo', on_delete=models.CASCADE)
    finalizado = models.BooleanField('Questionário Finalizado', default=False)
    setor = models.ForeignKeyPlus(Setor, verbose_name='Setor', null=True, on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Respondente'
        verbose_name_plural = 'Respondentes'
        ordering = ('id',)

    def get_matrizes(self):
        if self.segmento_id == Segmento.COORDENADOR_CURSO:
            qs = (
                Matriz.objects.filter(
                    data_inicio__year__gte=2012,
                    matrizcurso__curso_campus__modalidade__in=self.questionario.modalidades.all(),
                    matrizcurso__curso_campus__coordenador=self.vinculo,
                )
                .order_by('pk')
                .distinct()
            )
        elif self.segmento_id == Segmento.PROFESSOR:
            ids_componentes_curriculares = ProfessorDiario.objects.filter(professor__vinculo__id=self.vinculo.id).values_list(
                'diario__componente_curricular__pk', flat=True
            )
            ids_matrizes = ComponenteCurricular.objects.filter(pk__in=ids_componentes_curriculares).values_list('matriz_id', flat=True).distinct()
            qs = (
                Matriz.objects.filter(
                    data_inicio__year__gte=2012, matrizcurso__curso_campus__modalidade__in=self.questionario.modalidades.all(), pk__in=ids_matrizes
                )
                .order_by('pk')
                .distinct()
            )
        elif self.segmento_id == Segmento.ALUNO:
            aluno = self.vinculo.relacionamento
            qs = (
                Matriz.objects.filter(
                    pk__in=aluno.curso_campus.matrizes.all(), matrizcurso__curso_campus__modalidade__in=self.questionario.modalidades.all()
                )
                .order_by('pk')
                .distinct()
            )
        else:
            qs = Matriz.objects.none()
        return qs.filter(pk__in=self.questionario.matrizes.values_list('pk', flat=True))

    def reabrir(self):
        if self.finalizado and (self.questionario.data_termino > date.today()):
            self.finalizado = False
            self.save()


class Resposta(models.ModelPlus):
    respondente = models.ForeignKeyPlus(Respondente, verbose_name='Respondente', on_delete=models.CASCADE)
    pergunta = models.ForeignKeyPlus(Pergunta, verbose_name='Questionário', on_delete=models.CASCADE)
    resposta = models.TextField('Resposta', null=True)
    aprovada = models.BooleanField('Validada', null=True)

    class Meta:
        verbose_name = 'Resposta'
        verbose_name_plural = 'Respostas'
        ordering = ('id',)


class AvaliacaoComponenteCurricular(models.ModelPlus):
    componente_curricular = models.ForeignKeyPlus(ComponenteCurricular, verbose_name='Componente Curricular', on_delete=models.CASCADE)
    respondente = models.ForeignKeyPlus(Respondente, verbose_name='Respondente', on_delete=models.CASCADE)
    carga_horaria = models.CharFieldPlus('Carga-horária total da disciplina', null=True)
    sequencia_didatica = models.CharFieldPlus('Sequência Didática ', null=True)
    ementa_programa = models.CharFieldPlus('Ementa e Programa', null=True)
    regime_misto = models.CharFieldPlus('Regime Misto', null=True)
    justificativa = models.TextField('Resposta', null=True)
    aprovada = models.BooleanField('Validada', null=True)

    class Meta:
        verbose_name = 'Avaliação de Componente'
        verbose_name_plural = 'Avaliações de Componente'
        ordering = ('id',)


class JustificativaAvaliacaoComponenteCurricular(models.ModelPlus):
    CARGA_HORARIA = 1
    SEQUENCIA_DIDATICA = 2
    EMENTA_PROGRAMA = 3
    CAMPOS_CHOICES = [
        [CARGA_HORARIA, 'CH'],
        [SEQUENCIA_DIDATICA, 'Sequência Didática'],
        [EMENTA_PROGRAMA, 'Ementa'],
    ]
    respondente = models.ForeignKeyPlus(Respondente, verbose_name='Respondente', on_delete=models.CASCADE)
    componente_curricular = models.ForeignKeyPlus(ComponenteCurricular, verbose_name='Componente Curricular', on_delete=models.CASCADE)
    campo = models.IntegerField(verbose_name='Campo', choices=CAMPOS_CHOICES)
    justificativa = models.TextField('Resposta', null=True)

    class Meta:
        verbose_name = 'Justificativa de Avaliação de Componente'
        verbose_name_plural = 'Justificativas de Avaliação de Componente'
        ordering = ('id',)
