import datetime

from django.conf import settings

from djtools.db import models
from djtools.html.graficos import PieChart
from djtools.utils import send_notification
from edu.models import Aluno, SituacaoMatricula


class PeriodoResposta(models.ModelPlus):
    ano = models.ForeignKeyPlus('comum.Ano', on_delete=models.CASCADE)
    data_inicio = models.DateField(verbose_name='Data de Início')
    data_fim = models.DateField(verbose_name='Data de Término')

    class Meta:
        verbose_name = 'Período de Resposta'
        verbose_name_plural = 'Períodos de Resposta'

    def __str__(self):
        return f'Período de Resposta para {self.ano.ano}'


class AvaliacaoProcessualCurso(models.ModelPlus):
    OPNIAO_CHOICES = [['Ótimo', 'Ótimo'], ['Bom', 'Bom'], ['Regular', 'Regular'], ['Insuficiente', 'Insuficiente'], ['Desconheço', 'Desconheço']]
    aluno = models.ForeignKeyPlus('edu.Aluno', null=True, blank=True)
    questionario_matriz = models.ForeignKeyPlus('pedagogia.QuestionarioMatriz', verbose_name='Questionário da Matriz', on_delete=models.CASCADE)

    # avaliação da matriz
    avaliacao_regime_credito = models.CharFieldPlus(choices=OPNIAO_CHOICES, null=True, blank=True)

    # identificacao
    # 5. Programas de Assistência Estudantil a que tem acesso:
    # 6. ( ) Não utilizo ( ) Bolsa trabalho ( ) Alimentação ( ) Transporte ( ) Outro ________________

    identificacao_5_bolsa_trabalho = models.BooleanField('Bolsa trabalho', help_text='Utiliza bolsa trabalho', default=False)
    identificacao_5_alimentacao = models.BooleanField('Alimentação', help_text='Utiliza bolsa alimentação', default=False)
    identificacao_5_transporte = models.BooleanField('Transporte', help_text='Utiliza bolsa transporte', default=False)
    identificacao_5_outroi = models.BooleanField(
        'Outro', help_text='Utiliza aluma bolsa sem ser de trabalho, alimentação e transporte.', default=False
    )
    identificacao_5_outroii = models.CharFieldPlus('Outro', null=True, blank=True)

    # 7. Participa de algum de projetos de ensino, pesquisa ou extensão com bolsa?
    # ( ) Não participo ( ) Bolsa de iniciação científica do IFRN ( ) Bolsa de iniciação científica externa ( )
    # Bolsa de extensão do IFRN ( ) Bolsa de extensão externa ( ) PIBID ( ) PIBIC ( ) PIBIT
    identificacao_7_bolsa_de_IC_ifrn = models.BooleanField('Bolsa de iniciação científica do IFRN', default=False)
    identificacao_7_bolsa_de_IC_externa = models.BooleanField('Bolsa de iniciação científica externa', default=False)
    identificacao_7_bolsa_de_extensao_ifrn = models.BooleanField('Bolsa de extensão do IFRN', default=False)
    identificacao_7_bolsa_de_extensao_externa = models.BooleanField('Bolsa de extensão externa', default=False)
    identificacao_7_pibid = models.BooleanField('PIBID', default=False)
    identificacao_7_pibic = models.BooleanField('PIBIC', default=False)
    identificacao_7_pibit = models.BooleanField('PIBIT', default=False)

    # 8. Trabalha ou faz estágio? ( ) Sim, trabalho em empresa pública  ( ) Sim, trabalho em empresa privada
    # ( ) Sim, trabalho como autônomo ( ) Sim, faço estágio em empresa pública  ( ) Sim, faço estágio em empresa privada
    # ( ) Não
    TRABALHO_ESTAGIO = [
        ['Sim, trabalho em empresa pública', 'Sim, trabalho em empresa pública'],
        ['Sim, trabalho em empresa privada', 'Sim, trabalho em empresa privada'],
        ['Sim, trabalho como autônomo', 'Sim, trabalho como autônomo'],
        ['Sim, faço estágio em empresa pública', 'Sim, faço estágio em empresa pública'],
        ['Sim, faço estágio em empresa privada', 'Sim, faço estágio em empresa privada'],
        ['Não', 'Não'],
    ]
    identificacao_8 = models.CharFieldPlus('Trabalha ou faz estágio?', choices=TRABALHO_ESTAGIO, null=True, blank=True)

    # 9. Trabalha ou faz estágio conseguido por intermédio do curso? ( ) Sim ( ) Não
    # ( ) Não estou trabalhando/estagiando
    TRABALHO_ESTAGIO_INTERMEDIADO = [['Sim', 'Sim'], ['Não', 'Não'], ['Não estou trabalhando/estagiando', 'Não estou trabalhando/estagiando']]
    identificacao_9 = models.CharFieldPlus(
        'O Trabalho/Estágio foi conseguido por intermédio do curso?', choices=TRABALHO_ESTAGIO_INTERMEDIADO, null=True, blank=True
    )

    # PARTE II
    # Agora explicite seus pontos de vista para avaliar os itens listados a seguir.

    # I. Das dimensões avaliadas na PARTE I, justifique aquelas indicadas como INSUFICIENTE.

    parte_2_I_4 = models.CharFieldPlus('Organização do curso em Regime de Crédito', null=True, blank=True)
    parte_2_I_5 = models.TextField('Sugestões', null=True, blank=True)

    # a) Avalie as condições de ensino quanto à: (no questionário online, colocar a escala ao lado
    # de cada opção)

    parte_2_II_a_1 = models.CharFieldPlus('Infraestrutura das salas de aulas', choices=OPNIAO_CHOICES, null=True, blank=True)
    parte_2_II_a_2 = models.CharFieldPlus('Qualidade dos equipamentos nos laboratórios', choices=OPNIAO_CHOICES, null=True, blank=True)
    parte_2_II_a_3 = models.CharFieldPlus('Quantidade de alunos por aula laboratório', choices=OPNIAO_CHOICES, null=True, blank=True)
    parte_2_II_a_4 = models.CharFieldPlus('Qualidade dos equipamentos nas sala de aula', choices=OPNIAO_CHOICES, null=True, blank=True)
    parte_2_II_a_5 = models.CharFieldPlus('Material didático', choices=OPNIAO_CHOICES, null=True, blank=True)
    parte_2_II_a_6 = models.CharFieldPlus('Qualidade dos livros da biblioteca', choices=OPNIAO_CHOICES, null=True, blank=True)
    parte_2_II_a_7 = models.CharFieldPlus('Funcionamento da biblioteca', choices=OPNIAO_CHOICES, null=True, blank=True)
    parte_2_II_a_8 = models.CharFieldPlus(
        'Acessibilidade à salas de aula, laboratórios e demais espaços', choices=OPNIAO_CHOICES, null=True, blank=True
    )

    # b) Avalie o desenvolvimento de atividades didático-pedagógicas para a organização da
    # aprendizagem:
    parte_2_II_b_1 = models.CharFieldPlus('aulas expositivas', choices=OPNIAO_CHOICES, null=True, blank=True)
    parte_2_II_b_2 = models.CharFieldPlus('seminários e oficinas', choices=OPNIAO_CHOICES, null=True, blank=True)
    parte_2_II_b_3 = models.CharFieldPlus('eventos científico-artístico-culturais', choices=OPNIAO_CHOICES, null=True, blank=True)
    parte_2_II_b_4 = models.CharFieldPlus('aulas de campo', choices=OPNIAO_CHOICES, null=True, blank=True)
    parte_2_II_b_5 = models.CharFieldPlus('aulas práticas em laboratórios', choices=OPNIAO_CHOICES, null=True, blank=True)
    parte_2_II_b_6 = models.CharFieldPlus('aulas de recuperação e centros de aprendizagens', choices=OPNIAO_CHOICES, null=True, blank=True)
    parte_2_II_b_7 = models.CharFieldPlus('desenvolvimento do projeto integrador', choices=OPNIAO_CHOICES, null=True, blank=True)
    parte_2_II_b_8i = models.CharFieldPlus('outros', choices=OPNIAO_CHOICES, null=True, blank=True)
    parte_2_II_b_8ii = models.TextField('outros', null=True, blank=True)

    # c) Avalie a realização de projetos de pesquisa e de extensão:
    parte_2_II_c_1 = models.CharFieldPlus('a sua participação em projetos de pesquisa', choices=OPNIAO_CHOICES, null=True, blank=True)
    parte_2_II_c_2 = models.CharFieldPlus('a sua participação em projetos de extensão', choices=OPNIAO_CHOICES, null=True, blank=True)
    parte_2_II_c_3 = models.CharFieldPlus(
        'o desenvolvimento de projetos de pesquisas na formação dos estudantes durante o curso', choices=OPNIAO_CHOICES, null=True, blank=True
    )
    parte_2_II_c_4 = models.CharFieldPlus(
        'o desenvolvimento de projetos de extensão na formação dos estudantes durante o curso', choices=OPNIAO_CHOICES, null=True, blank=True
    )
    parte_2_II_c_5 = models.CharFieldPlus(
        'qualidade dos projetos de pesquisas desenvolvidos durante o curso', choices=OPNIAO_CHOICES, null=True, blank=True
    )
    parte_2_II_c_6 = models.CharFieldPlus(
        'qualidade dos projetos de extensão desenvolvidos durante o curso', choices=OPNIAO_CHOICES, null=True, blank=True
    )

    # d) Avalie o desenvolvimento da prática profissional e elaboração de TCC:
    parte_2_II_d_1 = models.CharFieldPlus(
        'Orientações recebidas para a realização da prática profissional', choices=OPNIAO_CHOICES, null=True, blank=True
    )
    parte_2_II_d_2 = models.CharFieldPlus('Orientações recebidas para a elaboração de TCC', choices=OPNIAO_CHOICES, null=True, blank=True)
    parte_2_II_d_3 = models.CharFieldPlus(
        'Organização interna para o desenvolvimento da prática profissional', choices=OPNIAO_CHOICES, null=True, blank=True
    )
    parte_2_II_d_4 = models.CharFieldPlus('Qualidade do acompanhamento da prática profissional', choices=OPNIAO_CHOICES, null=True, blank=True)

    # e) Faça    uma    avaliação    sobre    a    organização    administrativo-pedagógica    do    curso:
    parte_2_II_e_1 = models.CharFieldPlus('Acompanhamento pedagógico', choices=OPNIAO_CHOICES, null=True, blank=True)
    parte_2_II_e_2 = models.CharFieldPlus(
        'Organização e funcionamento do trabalho coletivo entre os educadores', choices=OPNIAO_CHOICES, null=True, blank=True
    )
    parte_2_II_e_3 = models.CharFieldPlus('Atendimento na Diretoria Acadêmica', choices=OPNIAO_CHOICES, null=True, blank=True)
    parte_2_II_e_4 = models.TextField('Sugestões', null=True, blank=True)

    # f) Avalie a proposta pedagógica do curso:
    parte_2_II_f_1 = models.CharFieldPlus('Acompanhamento pedagógico', choices=OPNIAO_CHOICES, null=True, blank=True)
    parte_2_II_f_2 = models.CharFieldPlus('Estrutura do curso', choices=OPNIAO_CHOICES, null=True, blank=True)
    parte_2_II_f_3 = models.CharFieldPlus('Procedimentos metodológicos utilizados', choices=OPNIAO_CHOICES, null=True, blank=True)
    parte_2_II_f_4 = models.CharFieldPlus('Práticas de avaliação da aprendizagem', choices=OPNIAO_CHOICES, null=True, blank=True)
    parte_2_II_f_5 = models.CharFieldPlus('Articulação entre teoria e prática', choices=OPNIAO_CHOICES, null=True, blank=True)
    parte_2_II_f_6 = models.CharFieldPlus('Indissociabilidade entre ensino, pesquisa e extensão', choices=OPNIAO_CHOICES, null=True, blank=True)
    parte_2_II_f_7 = models.CharFieldPlus('Práticas interdisciplinares', choices=OPNIAO_CHOICES, null=True, blank=True)
    parte_2_II_f_8 = models.TextField('Sugestões', null=True, blank=True)

    # g) Avalie sua postura acadêmica, quanto à:
    parte_2_II_g_1 = models.CharFieldPlus(
        'Participação, envolvimento/motivação nas atividades do curso', choices=OPNIAO_CHOICES, null=True, blank=True
    )
    parte_2_II_g_2 = models.CharFieldPlus('Desempenho nas disciplinas', choices=OPNIAO_CHOICES, null=True, blank=True)
    parte_2_II_g_3 = models.CharFieldPlus('Identidade com o curso', choices=OPNIAO_CHOICES, null=True, blank=True)
    parte_2_II_g_4 = models.CharFieldPlus('Responsabilidade com as atividades estudantis', choices=OPNIAO_CHOICES, null=True, blank=True)

    ENUMERACAO_1A7_CHOICES = [(i, i) for i in range(1, 8)]
    ENUMERACAO_1A8_CHOICES = [(i, i) for i in range(1, 9)]
    # h) Dos itens abaixo, indique quais os que contribuem para a sua permanência e êxito no curso.
    # (Enumere de 1 a 7, considerando o número 1 para o que mais contribui)
    parte_2_II_h_1 = models.PositiveIntegerField(
        'Participação em projetos de pesquisa e/ou extensão', choices=ENUMERACAO_1A7_CHOICES, null=True, blank=True
    )
    parte_2_II_h_2 = models.PositiveIntegerField('Acompanhamento pedagógico', choices=ENUMERACAO_1A7_CHOICES, null=True, blank=True)
    parte_2_II_h_3 = models.PositiveIntegerField('Programas de Assistência Estudantil', choices=ENUMERACAO_1A7_CHOICES, null=True, blank=True)
    parte_2_II_h_4 = models.PositiveIntegerField('Condições de infraestrutura do curso', choices=ENUMERACAO_1A7_CHOICES, null=True, blank=True)
    parte_2_II_h_5 = models.PositiveIntegerField('Articulação teoria-prática', choices=ENUMERACAO_1A7_CHOICES, null=True, blank=True)
    parte_2_II_h_6 = models.PositiveIntegerField('Acompanhamento do estágio', choices=ENUMERACAO_1A7_CHOICES, null=True, blank=True)
    parte_2_II_h_7i = models.PositiveIntegerField('Outros (descrever)', choices=ENUMERACAO_1A7_CHOICES, null=True, blank=True)
    parte_2_II_h_7ii = models.TextField(null=True, blank=True)

    # i) Considerando a realidade do IFRN, avalie os fatores que contribuem para a
    # reprovação no curso. (Enumere de 1 a 8, atribuindo em uma ordem de prioridade, considerando o
    # número 1 para o que mais contribui)
    parte_2_II_i_1 = models.PositiveIntegerField('Metodologia de ensino adotada', choices=ENUMERACAO_1A8_CHOICES, null=True, blank=True)
    parte_2_II_i_2 = models.PositiveIntegerField(
        'Dificuldade de conciliar o trabalho com o estudo', choices=ENUMERACAO_1A8_CHOICES, null=True, blank=True
    )
    parte_2_II_i_3 = models.PositiveIntegerField('Dificuldade de aprendizagem', choices=ENUMERACAO_1A8_CHOICES, null=True, blank=True)
    parte_2_II_i_4 = models.PositiveIntegerField('Nível de complexidade dos conteúdos', choices=ENUMERACAO_1A8_CHOICES, null=True, blank=True)
    parte_2_II_i_5 = models.PositiveIntegerField(
        'Critérios e instrumentos de avaliação utilizados', choices=ENUMERACAO_1A8_CHOICES, null=True, blank=True
    )
    parte_2_II_i_6 = models.PositiveIntegerField('Estrutura curricular do curso', choices=ENUMERACAO_1A8_CHOICES, null=True, blank=True)
    parte_2_II_i_7 = models.PositiveIntegerField(
        'Infraestrutura e recursos materiais do curso/instituição', choices=ENUMERACAO_1A8_CHOICES, null=True, blank=True
    )
    parte_2_II_i_8i = models.PositiveIntegerField('Outro (descrever)', choices=ENUMERACAO_1A8_CHOICES, null=True, blank=True)
    parte_2_II_i_8ii = models.TextField(null=True, blank=True)

    # j) Dentre os itens abaixo, quais os fatores que contribuem para a evasão dos
    # estudantes? (Enumere de 1 a 7, considerando o número 1 para o que mais contribui)
    parte_2_II_j_1 = models.PositiveIntegerField('Metodologia de ensino adotada ', choices=ENUMERACAO_1A7_CHOICES, null=True, blank=True)
    parte_2_II_j_2 = models.PositiveIntegerField(
        'Dificuldade de conciliar o trabalho com o estudo', choices=ENUMERACAO_1A7_CHOICES, null=True, blank=True
    )
    parte_2_II_j_3 = models.PositiveIntegerField('Mudança de cidade', choices=ENUMERACAO_1A7_CHOICES, null=True, blank=True)
    parte_2_II_j_4 = models.PositiveIntegerField('Dificuldade de aprendizagem', choices=ENUMERACAO_1A7_CHOICES, null=True, blank=True)
    parte_2_II_j_5 = models.PositiveIntegerField('Reprovação', choices=ENUMERACAO_1A7_CHOICES, null=True, blank=True)
    parte_2_II_j_6 = models.PositiveIntegerField('Dificuldades com transporte', choices=ENUMERACAO_1A7_CHOICES, null=True, blank=True)
    parte_2_II_j_7i = models.PositiveIntegerField('Outro (descrever)', choices=ENUMERACAO_1A7_CHOICES, null=True, blank=True)
    parte_2_II_j_7ii = models.TextField(null=True, blank=True)

    # Caso considere necessário, apresente suas observações ou sugestões de
    # melhorias
    parte_2_observacoes_sugestoes = models.TextField('Sugestões de melhorias', null=True, blank=True)


class QuestionarioMatriz(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição')
    cursos = models.ManyToManyFieldPlus('edu.CursoCampus', verbose_name='Curso')
    periodo = models.IntegerField('Período', help_text='Período a partir do qual os alunos deverão realizar a avaliação. Ex: 3')

    class Meta:
        verbose_name = 'Questionário de Matriz'
        verbose_name_plural = 'Questionários de Matrizes'

    @staticmethod
    def get_grafico(questionarios_matriz, campo, uo=None):
        dados = (
            AvaliacaoProcessualCurso.objects.filter(questionario_matriz__in=questionarios_matriz)
            .values_list(campo)
            .annotate(count=models.Count(campo))
            .order_by('count')
        )

        if uo:
            dados = dados.filter(aluno__curso_campus__diretoria__setor__uo=uo)

        dados_grafico = []
        for dado in dados:
            if dado[0] is not None:
                dado_grafico = []

                if type(dado[0]) is bool:
                    rotulo = dado[0] is False and 'Não' or 'Sim'
                else:
                    rotulo = str(dado[0])
                dado_grafico.append(rotulo)
                dado_grafico.append(dado[1])
                dados_grafico.append(dado_grafico)

        grafico = PieChart(
            campo,
            title=AvaliacaoProcessualCurso._meta.get_field(campo).verbose_name,
            subtitle=AvaliacaoProcessualCurso._meta.get_field(campo).help_text,
            minPointLength=0,
            data=dados_grafico,
        )
        grafico.id = campo
        return grafico

    @staticmethod
    def get_total_alunos_aptos(questionarios_matriz, uo=None):
        total = 0
        for questionario_matriz in questionarios_matriz:
            ids = questionario_matriz.cursos.all().values_list('id', flat=True).distinct()
            qs = Aluno.objects.filter(
                curso_campus__id__in=ids, matriculaperiodo__periodo_matriz__gte=questionario_matriz.periodo, situacao__ativo=True
            ).distinct()

            if uo:
                qs = qs.filter(curso_campus__diretoria__setor__uo=uo)

            total += qs.count()

        return total

    @staticmethod
    def get_total_questionarios_repondidos(questionarios_matriz, uo=None):
        qs = AvaliacaoProcessualCurso.objects.filter(questionario_matriz__in=questionarios_matriz).distinct()

        if uo:
            qs = qs.filter(aluno__curso_campus__diretoria__setor__uo=uo)

        return qs.count()

    def replicar(self):
        itens = self.itemquestionariomatriz_set.all()
        self.pk = None
        self.descricao = f'{self.descricao} [REPLICADO]'
        self.save()
        for item in itens:
            item.pk = None
            item.questionario_matriz = self
            item.save()
        return self

    def __str__(self):
        return f'{self.descricao}'

    def get_periodos(self):
        try:
            return self.periodos
        except Exception:
            d = {}
            for periodos in self.itemquestionariomatriz_set.all().values_list('periodo', flat=True).distinct():
                for periodo in periodos.split(';'):
                    d[periodo] = None
            self.periodos = list(d.keys())
            self.periodos.sort()
        return self.periodos

    def get_numero_periodos(self):
        return len(self.get_periodos()) * 2

    def get_numero_colunas(self):
        return self.get_numero_periodos() + 4

    def get_absolute_url(self):
        return f'/pedagogia/questionariomatriz/{self.pk}/'

    @staticmethod
    def pode_responder(aluno):
        qs = QuestionarioMatriz.objects.filter(cursos=aluno.curso_campus)
        if qs.exists():
            questionario = qs[0]
            is_do_periodo_esperado = aluno.matriculaperiodo_set.filter(periodo_matriz__gte=questionario.periodo).exists()
            periodo_aberto = PeriodoResposta.objects.filter(data_inicio__lte=datetime.datetime.now(), data_fim__gte=datetime.datetime.now())
            return is_do_periodo_esperado and periodo_aberto
        return False

    def enviar_email(self):
        titulo = '[SUAP] Responda ao questionário do seu curso'
        qs = PeriodoResposta.objects.filter(data_inicio__lte=datetime.datetime.now(), data_fim__gte=datetime.datetime.now())
        if qs.exists():
            periodo = qs[0]
            texto = """
                <h1>Pedagogia</h1>
                <h2>Questionário</h2>
                <p>Car@ estudante!</p>
                <br />
                <p>A Pró-Reitoria de Ensino está avaliando todos os cursos iniciados a partir de 2012. Convidamos você a avaliar o seu curso, respondendo a um QUESTIONÁRIO de avaliação "on line". Esse instrumento ficará disponível no SUAP até o dia 30 de Junho.</p>
                <p>As informações para ter acesso ao sistema são as seguintes:</p>
                <br />
                <dl>
                    <dt>Link de acesso ao SUAP:</dt><dd>{}</dd>
                    <dt>Usuário:</dt><dd>Matrícula do(a) aluno (a)</dd>
                </dl>
                <p>No link acima, você tem acesso à sua página inicial no SUAP. Em seguida deverão clicar no link "Responda ao questionário de Avaliação do Curso".</p>
                <p>Dessa forma, o questionário será inicializado para ser respondido.</p>
                <br />
                <p>O questionário deve ser preenchido entre {} até {}.</p>
                <br />
                <p>Lembramos que a sua participação é muito importante para avaliar o seu curso e melhorar a qualidade das ofertas desenvolvidas por essa Instituição.</p>
                <br />
                <p>Agradecemos a sua colaboração!</p>""".format(
                settings.SITE_URL,
                periodo.data_inicio.strftime('%d/%m/%Y'),
                periodo.data_fim.strftime('%d/%m/%Y'),
            )
            emails_enviados = 0
            for curso in self.cursos.all():
                for aluno in curso.aluno_set.all():
                    respondeu = AvaliacaoProcessualCurso.objects.filter(aluno=aluno).exists()
                    if not respondeu and self.pode_responder(aluno) and aluno.get_situacao_id() == SituacaoMatricula.MATRICULADO:
                        emails_enviados += send_notification(
                            titulo + '"' + curso.descricao_historico + '"',
                            texto,
                            settings.DEFAULT_FROM_EMAIL,
                            [aluno.get_vinculo()],
                            categoria='Responda ao questionário do seu curso',
                        )
            return emails_enviados
        return 0


class ItemQuestionarioMatriz(models.ModelPlus):
    questionario_matriz = models.ForeignKeyPlus('pedagogia.QuestionarioMatriz', verbose_name='Questionário da Matriz', on_delete=models.CASCADE)
    disciplina = models.CharFieldPlus(verbose_name='Disciplina')
    nucleo = models.CharFieldPlus(verbose_name='Núcleo')
    periodo = models.CharFieldPlus(
        verbose_name='Período', help_text='Caso a discplina seja ofertada em mais de um período, informe os períodos separados por ";"'
    )
    aulas_por_semana = models.CharFieldPlus(
        verbose_name='Aulas por semana',
        help_text='Caso tenha informado mais de um período no campo anterior, separa a quantidade de aulas por semana com ";" ',
    )

    class Meta:
        verbose_name = 'Disciplina'
        verbose_name_plural = 'Disciplinas'

    def __str__(self):
        return self.disciplina

    def get_grafico(self, campo, uo=None, questionario_matriz=None):
        dados = self.avaliacaodisciplina_set.all().values_list(campo).annotate(count=models.Count(campo)).order_by('count')

        if uo:
            dados = dados.filter(avaliacao_processual_curso__aluno__curso_campus__diretoria__setor__uo=uo)

        dados_grafico = []
        for dado in dados:
            if dado[0] is not None:
                dado_grafico = []
                if dado[0] is False or dado[0] is True:
                    rotulo = dado[0] is False and 'Não' or 'Sim'
                else:
                    rotulo = str(dado[0])
                if rotulo:
                    dado_grafico.append(rotulo)
                    dado_grafico.append(dado[1])
                    dados_grafico.append(dado_grafico)

        div_id = f'{campo}_{self.pk}'
        grafico = PieChart(
            div_id,
            title=AvaliacaoDisciplina._meta.get_field(campo).verbose_name,
            subtitle=AvaliacaoDisciplina._meta.get_field(campo).help_text,
            minPointLength=0,
            data=dados_grafico,
        )
        grafico.id = div_id
        d = dict(dados)
        grafico.insuficiente = 'Insuficiente' in d and d['Insuficiente'] or 0
        grafico.pk = self.pk
        grafico.campo = campo
        return grafico

    def get_dicionario_aulas_por_semana(self):
        try:
            return self.aulas_por_semana_dict
        except Exception:
            periodos = self.periodo.split(';')
            qtd_aulas = self.aulas_por_semana.split(';')
            self.aulas_por_semana_dict = {}
            for i in range(len(periodos)):
                self.aulas_por_semana_dict[periodos[i]] = qtd_aulas[i].split('/')
            return self.aulas_por_semana_dict

    def get_aulas_semana(self, periodo):
        aulas_por_semana = self.get_dicionario_aulas_por_semana().get(periodo)
        if aulas_por_semana == '0':
            return '-'
        else:
            return aulas_por_semana or ''

    def get_aulas_semana_1(self):
        return self.get_aulas_semana('1')

    def get_aulas_semana_2(self):
        return self.get_aulas_semana('2')

    def get_aulas_semana_3(self):
        return self.get_aulas_semana('3')

    def get_aulas_semana_4(self):
        return self.get_aulas_semana('4')

    def get_aulas_semana_5(self):
        return self.get_aulas_semana('5')

    def get_aulas_semana_6(self):
        return self.get_aulas_semana('6')

    def get_aulas_semana_7(self):
        return self.get_aulas_semana('7')

    def get_aulas_semana_8(self):
        return self.get_aulas_semana('8')


class AvaliacaoDisciplina(models.ModelPlus):
    avaliacao_processual_curso = models.ForeignKeyPlus(
        'pedagogia.AvaliacaoProcessualCurso', verbose_name='Avaliação Processual do Curso', on_delete=models.CASCADE
    )
    item_questionario_matriz = models.ForeignKeyPlus('pedagogia.ItemQuestionarioMatriz', verbose_name='Disciplina', on_delete=models.CASCADE)
    avaliacao_carga_horaria = models.CharFieldPlus(choices=AvaliacaoProcessualCurso.OPNIAO_CHOICES, verbose_name='Avaliação da Carga Horária')
    avaliacao_sequencia_didatica = models.CharFieldPlus(
        choices=AvaliacaoProcessualCurso.OPNIAO_CHOICES, verbose_name='Avaliação da Sequência Didática'
    )
    avaliacao_ementa_disciplina = models.CharFieldPlus(
        choices=AvaliacaoProcessualCurso.OPNIAO_CHOICES, verbose_name='Avaliação da Ementa da Disciplina'
    )

    avaliacao_carga_horaria_justificativa = models.TextField(null=True, blank=True)
    avaliacao_sequencia_didatica_justificativa = models.TextField(null=True, blank=True)
    avaliacao_ementa_disciplina_justificativa = models.TextField(null=True, blank=True)
