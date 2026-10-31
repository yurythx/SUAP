from math import ceil

from django.core.exceptions import ValidationError

from comum.models import Ano
from djtools.db import models
from edu.managers import FiltroDiretoriaManager
from edu.models.afastamento import AfastamentoSalaAula
from edu.models.cadastros_gerais import PERIODO_LETIVO_CHOICES, GrupoAtuacao, Turno
from edu.models.cursos import ComponenteCurricular, CursoCampus, Matriz
from edu.models.professores import Professor
from rh.models import UnidadeOrganizacional

RELACAO_DOCENTE_CH_SEMANAL = 20


class CenarioOferta(models.ModelPlus):
    descricao = models.CharFieldPlus(verbose_name='Descrição', null=True)
    uo = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name='Campus', on_delete=models.CASCADE)
    ano_letivo = models.ForeignKeyPlus(Ano, verbose_name='Ano Letivo', on_delete=models.CASCADE)
    periodo_letivo = models.IntegerField('Período Letivo', choices=PERIODO_LETIVO_CHOICES)
    qtd_anos = models.IntegerField('Quantidade de Anos', default=3)

    ignorar_afastamentos = models.ManyToManyFieldPlus('edu.AfastamentoSalaAula')

    class Meta:
        verbose_name = 'Cenário'
        verbose_name_plural = 'Cenários'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.professores = None
        self.itens = None
        self.periodos = []
        self.ch_disponivel_professor = {}
        self.ch_disponivel_grupo_atuacao = {}
        self.ch_necessaria_grupo_atuacao = {}
        self.ch_semanal_professor = {}

    def __str__(self):
        return f'{self.uo} {self.ano_letivo}.{self.periodo_letivo}'

    def get_itens(self):
        if self.itens is not None:
            return self.itens
        self.itens = self.previsaoquantidadealunos_set.order_by('id')
        return self.itens

    def get_matrizes(self):
        return Matriz.objects.filter(pk__in=self.get_itens().values_list('matriz', flat=True).distinct()).order_by('id')

    def ids_grupos_atuacao(self):
        return (
            GrupoAtuacao.objects.filter(componente__componentecurricular__matriz__previsaoquantidadealunos__cenario=self)
            .values_list('id', flat=True)
            .order_by('id')
            .distinct()
        )

    def get_grupos_atuacao(self):
        grupos_atuacao = []
        for obj in GrupoAtuacao.objects.filter(id__in=self.ids_grupos_atuacao()):
            ids = obj.participacaogrupoatuacao_set.filter(professor__vinculo__setor__uo=self.uo).values_list('professor_id', flat=True).distinct()
            obj.professores = Professor.objects.filter(pk__in=ids)
            grupos_atuacao.append(obj)
        return grupos_atuacao

    def get_professores(self):
        if self.professores is None:
            ids = (
                Professor.objects.filter(vinculo__setor__uo=self.uo, participacaogrupoatuacao__grupo_atuacao__in=self.ids_grupos_atuacao())
                .values_list('id', flat=True)
                .order_by('id')
                .distinct()
            )
            self.professores = Professor.objects.filter(id__in=ids).order_by('id')
        return self.professores

    def get_afastamentos(self):
        ids = self.get_professores().values_list('id', flat=True)
        return AfastamentoSalaAula.objects.filter(professor__in=ids)

    def get_periodos(self):
        if self.periodos:
            return self.periodos
        for ano in range(self.ano_letivo.ano, self.ano_letivo.ano + self.qtd_anos):
            for periodo in (1, 2):
                self.periodos.append(f'{ano}/{periodo}')
        return self.periodos

    def is_professor_afastado(self, professor, ano, periodo, simulacao=False):
        if simulacao:
            qs = self.simulacaoafastamento_set.filter(professor=professor)
        else:
            qs = professor.afastamentosalaaula_set
        qs1 = qs.filter(tipo_substituicao=AfastamentoSalaAula.SEM_SUBSTITUICAO)
        qs1 = qs1.filter(ano_inicio__ano__lte=ano)
        if qs1.filter(ano_termino__ano__isnull=True).exists():
            qs1 = qs1.filter(ano_termino__ano__isnull=True)
        else:
            if int(periodo) == 1:
                qs1 = qs1.filter(ano_termino__ano__gte=ano)
            else:
                qs1 = qs1.filter(ano_termino__ano=ano, periodo_termino=2) | qs1.filter(ano_termino__ano__gte=ano + 1)
        return qs1.values_list('percentual', flat=True).first()

    def get_ch_semanal_professor(self, id):
        self.calcular_ch_disponivel_professor()
        return self.ch_semanal_professor[id]

    def calcular_ch_disponivel_professor(self):
        if self.ch_disponivel_professor:
            return
        for professor in self.get_professores():
            ch_sala_aula_semanal = (
                self.simulacaocargahorariaprofessor_set.filter(professor=professor).values_list('ch_sala_aula_semanal', flat=True).first()
                or professor.ch_sala_aula_semanal
            )
            self.ch_semanal_professor[professor.id] = ch_sala_aula_semanal
            pgas = professor.participacaogrupoatuacao_set.all()
            for periodo_letivo in self.get_periodos():
                self.ch_disponivel_professor[periodo_letivo] = {}
                ano, periodo = periodo_letivo.split('/')
                ano = int(ano)
                periodo = int(periodo)
                percentual_afastamento = self.is_professor_afastado(professor, ano, periodo) or self.is_professor_afastado(
                    professor, ano, periodo, simulacao=True
                )
                for pga in pgas:
                    key = f'{pga.id}/{periodo_letivo}'
                    ch = pga.percentual / 100.0 * ch_sala_aula_semanal if ch_sala_aula_semanal else 0
                    if ch and percentual_afastamento:
                        ch = ch - (percentual_afastamento / 100.0 * ch)
                    self.ch_disponivel_professor[key] = ch
                    key = f'{pga.grupo_atuacao_id}/{periodo_letivo}'
                    self.ch_disponivel_grupo_atuacao[key] = self.ch_disponivel_grupo_atuacao.get(key, 0) + ch
        for periodo_letivo in self.get_periodos():
            ano, periodo = periodo_letivo.split('/')
            ano = int(ano)
            periodo = int(periodo)
            qs = self.simulacaocontratacao_set
            if periodo == 1:
                qs_inicial = qs.filter(ano_inicio__ano=ano, periodo_inicio=periodo) | qs.filter(ano_inicio__ano__lte=ano)
            else:
                qs_inicial = qs.filter(ano_inicio__ano__lte=ano)
            qs_nao_finalizados = qs_inicial.filter(ano_termino__isnull=True)
            if periodo == 1:
                qs_finalizados_depois = qs_inicial.filter(ano_termino__ano__gte=ano)
            else:
                qs_finalizados_depois = qs_inicial.filter(ano_termino__ano=ano, periodo_termino=2) | qs_inicial.filter(ano_termino__ano__gte=ano + 1)
            for contratacao in qs_nao_finalizados | qs_finalizados_depois:
                key = f'{contratacao.grupo_atuacao_id}/{periodo_letivo}'
                self.ch_disponivel_grupo_atuacao[key] = self.ch_disponivel_grupo_atuacao.get(key, 0) + RELACAO_DOCENTE_CH_SEMANAL

    def get_ch_disponivel_professor(self, dados):
        self.calcular_ch_disponivel_professor()
        return round(self.ch_disponivel_professor[dados])

    def calcular_ch_necessaria_grupo_atuacao(self):
        if self.ch_necessaria_grupo_atuacao:
            return
        for item in self.previsaoquantidadealunos_set.all():
            qs = ComponenteCurricular.objects.filter(matriz=item.matriz, periodo_letivo__isnull=False).values_list(
                'periodo_letivo', 'componente__grupo_atuacao', 'componente__ch_qtd_creditos'
            )
            for serie, grupo_atuacao_id, ch in qs:
                key = f'{item.matriz_id}/{serie}/{grupo_atuacao_id}'
                self.ch_necessaria_grupo_atuacao[key] = self.ch_necessaria_grupo_atuacao.get(key, 0) + ch

    def get_ch_necessaria_grupo_atuacao_matriz(self, dados):
        self.calcular_ch_necessaria_grupo_atuacao()
        return self.ch_necessaria_grupo_atuacao.get(dados, 0)

    def get_ch_disponivel_grupo_atuacao_periodo(self, dados):
        self.calcular_ch_disponivel_professor()
        return round(self.ch_disponivel_grupo_atuacao.get(dados, 0))

    def get_ch_necessaria_grupo_atuacao_periodo(self, dados):
        self.calcular_ch_necessaria_grupo_atuacao()
        ch_necessaria_grupo_atuacao = 0
        grupo_atuacao_id, ano, periodo = dados.split('/')
        periodo_letivo = f'{ano}/{periodo}'
        for item in self.previsaoquantidadealunos_set.all():
            for serie in self.get_series():
                key = f'{serie}/{periodo_letivo}'
                qtd_turmas = item.get_qtd_turmas(key)
                key = f'{item.matriz_id}/{serie}/{grupo_atuacao_id}'
                ch_necessaria_grupo_atuacao += self.ch_necessaria_grupo_atuacao.get(key, 0) * qtd_turmas
        # print(grupo_atuacao_id, ano, periodo, ch_necessaria_grupo_atuacao)
        return round(ch_necessaria_grupo_atuacao)

    def get_ch_saldo_grupo_atuacao_periodo(self, dados):
        return self.get_ch_disponivel_grupo_atuacao_periodo(dados) - self.get_ch_necessaria_grupo_atuacao_periodo(dados)

    def get_docente_disponivel_grupo_atuacao_periodo(self, dados):
        self.calcular_ch_disponivel_professor()
        return round(1.0 * self.ch_disponivel_grupo_atuacao.get(dados, 0) / RELACAO_DOCENTE_CH_SEMANAL, 1)

    def get_docente_necessario_grupo_atuacao_periodo(self, dados):
        self.calcular_ch_disponivel_professor()
        return round(1.0 * self.get_ch_necessaria_grupo_atuacao_periodo(dados) / RELACAO_DOCENTE_CH_SEMANAL, 1)

    def get_docente_saldo_grupo_atuacao_periodo(self, dados):
        return self.get_docente_disponivel_grupo_atuacao_periodo(dados) - self.get_docente_necessario_grupo_atuacao_periodo(dados)

    def get_series(self):
        return range(1, 11)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return f'/edu/cenariooferta/{self.id}/'


class PrevisaoQuantidadeAlunos(models.ModelPlus):
    cenario = models.ForeignKeyPlus(CenarioOferta, verbose_name='Cenário', on_delete=models.CASCADE, null=True)
    matriz = models.ForeignKeyPlus(Matriz, verbose_name='Matriz', on_delete=models.CASCADE, null=True)
    turno = models.ForeignKeyPlus(Turno, verbose_name='Turno', on_delete=models.CASCADE, null=True)
    qtd_ingressantes = models.IntegerField(verbose_name='Qtd. Ingressantes', default=0)
    qtd_turmas = models.IntegerField(verbose_name='Qtd. Turmas', default=0)

    qtd_alunos_1 = models.IntegerField(verbose_name='Qtd. Alunos 1º Ano', default=0)
    qtd_alunos_2 = models.IntegerField(verbose_name='Qtd. Alunos 2º Ano', default=0)
    qtd_alunos_3 = models.IntegerField(verbose_name='Qtd. Alunos 3º Ano', default=0)
    qtd_alunos_4 = models.IntegerField(verbose_name='Qtd. Alunos 4º Ano', default=0)
    qtd_alunos_5 = models.IntegerField(verbose_name='Qtd. Alunos 5º Ano', default=0)
    qtd_alunos_6 = models.IntegerField(verbose_name='Qtd. Alunos 6º Ano', default=0)
    qtd_alunos_7 = models.IntegerField(verbose_name='Qtd. Alunos 7º Ano', default=0)
    qtd_alunos_8 = models.IntegerField(verbose_name='Qtd. Alunos 8º Ano', default=0)
    qtd_alunos_9 = models.IntegerField(verbose_name='Qtd. Alunos 9º Ano', default=0)
    qtd_alunos_10 = models.IntegerField(verbose_name='Qtd. Alunos 10º Ano', default=0)

    taxa_evasao_1 = models.IntegerField(verbose_name='(%) Evasão 1º Ano', default=0)
    taxa_evasao_2 = models.IntegerField(verbose_name='(%) Evasão 2º Ano', default=0)
    taxa_evasao_3 = models.IntegerField(verbose_name='(%) Evasão 3º Ano', default=0)
    taxa_evasao_4 = models.IntegerField(verbose_name='(%) Evasão 4º Ano', default=0)
    taxa_evasao_5 = models.IntegerField(verbose_name='(%) Evasão 5º Ano', default=0)
    taxa_evasao_6 = models.IntegerField(verbose_name='(%) Evasão 6º Ano', default=0)
    taxa_evasao_7 = models.IntegerField(verbose_name='(%) Evasão 7º Ano', default=0)
    taxa_evasao_8 = models.IntegerField(verbose_name='(%) Evasão 8º Ano', default=0)
    taxa_evasao_9 = models.IntegerField(verbose_name='(%) Evasão 9º Ano', default=0)
    taxa_evasao_10 = models.IntegerField(verbose_name='(%) Evasão 10º Ano', default=0)

    objects = models.Manager()
    locals = FiltroDiretoriaManager('matriz__curso_campus__diretoria')

    class Meta:
        verbose_name = 'Previsão de Quantidade de Alunos'
        verbose_name_plural = 'Previsões de Quantidade de Alunos'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.qtd_alunos = {}

    def __str__(self):
        return f'Previsão da Quantidade de Aluno para {self.matriz} em {self.cenario}'

    def get_grupos_atuacao(self):
        ids = self.matriz.componentecurricular_set.values_list('componente__grupo_atuacao', flat=True).distinct()
        return GrupoAtuacao.objects.filter(id__in=ids).order_by('id')

    def get_qtd_alunos_por_turma(self):
        return ceil(1.0 * self.qtd_ingressantes / self.qtd_turmas) if self.qtd_turmas else 0

    def calcular_qtd_alunos(self):
        if self.qtd_alunos:
            return
        periodos = self.cenario.get_periodos()
        series = self.cenario.get_series()
        is_anual = self.matriz.matrizcurso_set.filter(curso_campus__periodicidade=CursoCampus.PERIODICIDADE_ANUAL).exists()
        for i, periodo in enumerate(periodos):
            for j, serie in enumerate(series):
                key = f'{serie}/{periodo}'
                if i == 0:
                    if j == 0 and self.qtd_ingressantes:
                        self.qtd_alunos[key] = self.qtd_alunos_1 or self.qtd_ingressantes
                    else:
                        self.qtd_alunos[key] = getattr(self, f'qtd_alunos_{serie}')
                else:
                    if j == 0:
                        self.qtd_alunos[key] = self.qtd_ingressantes or self.qtd_alunos_1
                    else:
                        taxa_evasao = getattr(self, f'taxa_evasao_{serie - 1}')
                        if is_anual and periodo.endswith('2'):
                            previous_key = f'{serie}/{periodos[i - 1]}'
                            subtrair = 0
                        else:
                            previous_key = f'{serie - 1}/{periodos[i - 1]}'
                            subtrair = self.qtd_alunos[previous_key] * (taxa_evasao / 100)
                        self.qtd_alunos[key] = self.qtd_alunos[previous_key] - subtrair
                self.qtd_alunos[key] = round(self.qtd_alunos[key])

    def get_qtd_alunos(self, dados):
        self.calcular_qtd_alunos()
        return self.qtd_alunos[dados]

    def get_qtd_turmas(self, dados):
        self.calcular_qtd_alunos()
        qtd_alunos_por_turma = self.get_qtd_alunos_por_turma()
        return ceil(1.0 * self.qtd_alunos[dados] / qtd_alunos_por_turma) if qtd_alunos_por_turma else 0

    def clean(self):
        if self.taxa_evasao_1 < 0 or self.taxa_evasao_1 > 100:
            raise ValidationError('Taxa de evasão inválida.')

    def save(self, *args, **kwargs):
        if self.pk is None:
            valor = self.taxa_evasao_1
            for periodo in range(1, 11):
                setattr(self, f'taxa_evasao_{periodo}', valor)
        super().save(*args, **kwargs)


class SimulacaoAfastamento(models.ModelPlus):
    SEM_SUBSTITUICAO = 1
    PROFESSOR_SUBSTITUTO = 2
    PROFESSOR_VISITANTE = 3
    PROFESSOR_TEMPORARIO = 4

    TIPO_SUBSTITUICAO_CHOICES = [
        [SEM_SUBSTITUICAO, 'Sem substituição'],
        [PROFESSOR_SUBSTITUTO, 'Professor Substituto'],
        [PROFESSOR_VISITANTE, 'Professor Visitante'],
        [PROFESSOR_TEMPORARIO, 'Professor Temporário'],
    ]

    cenario = models.ForeignKeyPlus(CenarioOferta, verbose_name='Cenário', on_delete=models.CASCADE, null=True)
    professor = models.ForeignKeyPlus('edu.professor', verbose_name='Professor', on_delete=models.CASCADE)
    ano_inicio = models.ForeignKeyPlus('comum.ano', verbose_name='Ano do Início', on_delete=models.CASCADE, related_name='sa1')
    periodo_inicio = models.IntegerField('Período do Início', choices=PERIODO_LETIVO_CHOICES)
    ano_termino = models.ForeignKeyPlus(
        'comum.ano', verbose_name='Ano do Término', on_delete=models.CASCADE, related_name='sa2', null=True, blank=True
    )
    periodo_termino = models.IntegerField('Período do Término', null=True, blank=True, choices=[['', ''], *PERIODO_LETIVO_CHOICES])
    tipo_substituicao = models.IntegerField('Tipo de Substituição', choices=TIPO_SUBSTITUICAO_CHOICES)
    percentual = models.IntegerField('Percentual (%)', default=100)
    observacao = models.TextField('Observação', null=True, blank=True)

    class Meta:
        verbose_name = 'Simulação de Afastamento'
        verbose_name_plural = 'Simulações de Afastamento'

    def __str__(self):
        return f'{self.professor} [{self.ano_inicio}/{self.periodo_inicio}]'


class SimulacaoContratacao(models.ModelPlus):
    PROFESSOR_EFETIO = 1
    PROFESSOR_SUBSTITUTO = 2
    PROFESSOR_VISITANTE = 3
    PROFESSOR_TEMPORARIO = 4

    TIPO_CONTRATACAO_CHOICES = [
        [PROFESSOR_EFETIO, 'Professor Efetivo'],
        [PROFESSOR_SUBSTITUTO, 'Professor Substituto'],
        [PROFESSOR_VISITANTE, 'Professor Visitante'],
        [PROFESSOR_TEMPORARIO, 'Professor Temporário'],
    ]

    cenario = models.ForeignKeyPlus(CenarioOferta, verbose_name='Cenário', on_delete=models.CASCADE, null=True)
    grupo_atuacao = models.ForeignKeyPlus(GrupoAtuacao, verbose_name='Grupo de Atuação', on_delete=models.CASCADE, null=True)
    ano_inicio = models.ForeignKeyPlus('comum.ano', verbose_name='Ano do Início', on_delete=models.CASCADE, related_name='sc1')
    periodo_inicio = models.IntegerField('Período do Início', choices=PERIODO_LETIVO_CHOICES)
    ano_termino = models.ForeignKeyPlus(
        'comum.ano', verbose_name='Ano do Término', on_delete=models.CASCADE, related_name='sc2', null=True, blank=True
    )
    periodo_termino = models.IntegerField('Período do Término', null=True, blank=True, choices=[['', ''], *PERIODO_LETIVO_CHOICES])
    tipo_contratacao = models.IntegerField('Tipo de Contratação', choices=TIPO_CONTRATACAO_CHOICES)
    observacao = models.TextField('Observação', null=True, blank=True)

    class Meta:
        verbose_name = 'Simulação de Contratação'
        verbose_name_plural = 'Simulações de Contratação'

    def __str__(self):
        return f'{self.professor} [{self.ano_inicio}/{self.periodo_inicio}]'


class SimulacaoCargaHorariaProfessor(models.ModelPlus):
    cenario = models.ForeignKeyPlus(CenarioOferta, verbose_name='Cenário', on_delete=models.CASCADE, null=True)
    professor = models.ForeignKeyPlus(Professor, verbose_name='Professor', on_delete=models.CASCADE, null=True)
    ch_sala_aula_semanal = models.IntegerField(verbose_name='Carga Horária Semanal')

    class Meta:
        verbose_name = 'Simulação de CH de Professor'
        verbose_name_plural = 'Simulações de CH de Professor'

    def __str__(self):
        return f'{self.professor} [{self.ch}hs]'
