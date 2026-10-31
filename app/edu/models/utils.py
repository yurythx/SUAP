from datetime import datetime
from itertools import chain

from django.conf import settings

from comum.models import Ano, Configuracao
from comum.utils import tl
from djtools.db import models
from edu.models.diarios import ProfessorDiario
from edu.models.diarios_especiais import DiarioEspecial
from edu.models.diretorias import CalendarioAcademico
from edu.models.historico import MatriculaPeriodo
from edu.models.logs import LogModel


class PeriodoLetivoAtual(models.ModelPlus):
    user = models.CurrentUserField()
    ano = models.IntegerField()
    periodo = models.IntegerField()

    def get_periodos(self):
        if self.user:
            lista = []
            hoje = datetime.now()
            qs_matriculas_periodo = MatriculaPeriodo.objects.none()
            qs = MatriculaPeriodo.objects.filter(aluno__vinculos__user=self.user)
            if qs.exists():
                qs_matriculas_periodo = qs.values_list('ano_letivo__ano', 'periodo_letivo').distinct()

            qs_diarios = ProfessorDiario.objects.none()
            diarios_segundo_semestre = []
            qs = ProfessorDiario.objects.filter(professor__vinculo__user=self.user)
            if qs.exists():
                for ano in qs.order_by('diario__ano_letivo__ano').values_list('diario__ano_letivo__ano', flat=True).distinct():
                    diarios_segundo_semestre.append((ano, 1))
                    diarios_segundo_semestre.append((ano, 2))

            qs_diarios_especiais = DiarioEspecial.objects.none()
            qs = DiarioEspecial.objects.filter(professores__vinculo__user=self.user)
            if qs.exists():
                qs_diarios_especiais = qs.values_list('ano_letivo__ano', 'periodo_letivo').distinct()

            qs_extra = ProfessorDiario.objects.none()
            if 'pit_rit' in settings.INSTALLED_APPS:
                from pit_rit.models import PlanoIndividualTrabalho

                qs_extra = PlanoIndividualTrabalho.objects.filter(professor__vinculo__user=self.user)
                qs_extra = qs_extra.values_list('ano_letivo__ano', 'periodo_letivo')

            if 'pit_rit_v2' in settings.INSTALLED_APPS:
                from pit_rit_v2.models import PlanoIndividualTrabalhoV2

                qs_extra = PlanoIndividualTrabalhoV2.objects.filter(professor__vinculo__user=self.user)
                qs_extra = qs_extra.values_list('ano_letivo__ano', 'periodo_letivo')

            if diarios_segundo_semestre or qs_matriculas_periodo.exists() or qs_diarios.exists() or qs_diarios_especiais.exists() or qs_extra:
                for a, b in list(chain(diarios_segundo_semestre, qs_matriculas_periodo, qs_diarios, qs_diarios_especiais, qs_extra)):
                    if (a, b) not in lista:
                        lista.append((a, b))

            if self.user.has_group_cached('Professor'):
                periodo_corrente = (hoje.year, 1 if hoje.month < 7 else 2)
                periodo_anterior = (periodo_corrente[0], 1) if periodo_corrente[1] == 2 else (periodo_corrente[0] - 1, 2)
                if periodo_corrente not in lista:
                    lista.append(periodo_corrente)
                if periodo_anterior not in lista:
                    lista.append(periodo_anterior)

        ano_letivo_atual = int(Configuracao.get_valor_por_chave('edu', 'ano_letivo_atual') or hoje.year)
        periodo_letivo_atual = int(Configuracao.get_valor_por_chave('edu', 'periodo_letivo_atual') or 1)
        if (ano_letivo_atual, periodo_letivo_atual) not in lista:
            lista.append((ano_letivo_atual, periodo_letivo_atual))
        return sorted(lista, reverse=True)

    def as_widget(self):
        lista = ['<div class="search-and-filters">']
        lista.append('<form id="form_periodo_letivo"><div class="filter"><label>Período:</label>')
        lista.append(
            """<select id="select_ano_periodo" name="ano-periodo"
                             onchange="
                             if( window.location.search.indexOf(\'ano-periodo\') !=-1){
                                 window.location.search = window.location.search.substring(0,window.location.search.indexOf(\'ano-periodo\'))+\'ano-periodo=\'+document.getElementById(\'select_ano_periodo\').value +  window.location.search.substring(window.location.search.indexOf(\'ano-periodo\')+18)
                             }
                             else {
                                 window.location.search = window.location.search + \'&ano-periodo=\' + document.getElementById(\'select_ano_periodo\').value
                             }"
                     >"""
        )
        for tupla in self.get_periodos():
            ano, periodo = tupla
            selected = ''
            if int(ano) == int(self.ano) and int(periodo) == int(self.periodo):
                selected = 'selected'
            lista.append(f'<option {selected}>{ano}.{periodo}</option>')
        lista.append('</select></div></form></div>')
        return ''.join(lista)

    @classmethod
    def get_instance(cls, request, usuario=None):
        if not usuario:
            user = request.user
        else:
            user = usuario.get_vinculo() and usuario.get_vinculo().user or usuario

        qs = cls.objects.filter(user=user, user__isnull=False)
        if qs.exists():
            periodo_letivo_atual = qs[0]
            if 'ano-periodo' in request.GET:
                try:
                    ano, periodo = request.GET['ano-periodo'].split('.')
                    periodo_letivo_atual.ano = int(ano)
                    periodo_letivo_atual.periodo = int(periodo)
                except Exception:
                    return qs[0]
                if request.user == user:
                    periodo_letivo_atual.save()
            for ano, periodo in periodo_letivo_atual.get_periodos():
                if periodo_letivo_atual.ano == ano and periodo_letivo_atual.periodo == periodo:
                    return periodo_letivo_atual

        periodo_letivo_atual = cls()
        periodo_letivo_atual.user = user
        periodos = periodo_letivo_atual.get_periodos()
        if periodos:
            periodo_letivo_atual.ano = periodos[0][0]
            periodo_letivo_atual.periodo = periodos[0][1]
        else:
            periodo_letivo_atual.ano = datetime.today().year
            periodo_letivo_atual.periodo = 1

        if periodo_letivo_atual.user:
            periodo_letivo_atual.save()

        return periodo_letivo_atual


class PeriodoLetivoAtualSecretario(PeriodoLetivoAtual):
    def get_periodos(self):
        return (
            CalendarioAcademico.objects.order_by('-ano_letivo__ano', '-periodo_letivo')
            .values_list('ano_letivo__ano', 'periodo_letivo')
            .distinct()[0:5]
        )


class PeriodoLetivoAtualPolo(PeriodoLetivoAtual):
    polo = models.ForeignKeyPlus('edu.Polo', verbose_name='Polo')

    @classmethod
    def get_instance(cls, request, polo, usuario=None):
        if not usuario:
            user = request.user
        else:
            user = usuario.get_vinculo().user
        qs = cls.objects.filter(user=user, polo=polo)
        if qs.exists():
            periodo_letivo_atual = qs[0]
            if 'ano-periodo' in request.GET:
                ano, periodo = request.GET['ano-periodo'].split('.')
                periodo_letivo_atual.ano = int(ano)
                periodo_letivo_atual.periodo = int(periodo)
                if request.user == user:
                    periodo_letivo_atual.save()
            for ano, periodo in periodo_letivo_atual.get_periodos():
                if periodo_letivo_atual.ano == ano and periodo_letivo_atual.periodo == periodo:
                    return periodo_letivo_atual

        periodo_letivo_atual = cls()
        periodo_letivo_atual.user = user
        periodo_letivo_atual.polo = polo
        periodos = periodo_letivo_atual.get_periodos()
        if periodos:
            periodo_letivo_atual.ano = periodos[0][0]
            periodo_letivo_atual.periodo = periodos[0][1]
        else:
            periodo_letivo_atual.ano = Ano.objects.latest('ano').ano
            periodo_letivo_atual.periodo = 1
        periodo_letivo_atual.save()
        return periodo_letivo_atual

    def get_periodos(self):
        return self.polo.turma_set.order_by('-ano_letivo__ano', '-periodo_letivo').values_list('ano_letivo__ano', 'periodo_letivo').distinct()[0:2]


class HistoricoRelatorio(LogModel):
    TIPO_ALUNO = 1
    TIPO_DIARIO = 2
    TIPO_PROFESSOR = 3
    TIPO_TRABALHO_CONCLUSAO_CURSO = 4
    TIPO_CHOICES = [[TIPO_ALUNO, 'Aluno'], [TIPO_DIARIO, 'Diário'], [TIPO_PROFESSOR, 'Professor']]

    URL_CHOICES = [[TIPO_ALUNO, '/edu/relatorio/'], [TIPO_DIARIO, '/edu/relatorio_diario/'], [TIPO_PROFESSOR, '/edu/relatorio_professor/']]

    user = models.CurrentUserField()
    descricao = models.CharFieldPlus()
    query_string = models.TextField()
    tipo = models.PositiveIntegerField(choices=TIPO_CHOICES)

    class Meta:
        verbose_name = 'Histórico de Relatório'
        verbose_name_plural = 'Histórico de Relatórios'

    def get_url_sem_parametro(self):
        return self.URL_CHOICES[self.tipo - 1][1]

    def get_url(self):
        url = '{}?{}'.format(self.get_url_sem_parametro(), bytes.fromhex(self.query_string).decode('utf-8'))
        return url

    def delete(self, *args, **kwargs):
        if self.user == tl.get_user():
            super().delete(*args, **kwargs)
        else:
            raise Exception('Usuário não tem permissão para excluir')


class HistoricoSituacaoMatricula(models.ModelPlus):
    aluno = models.ForeignKeyPlus('edu.Aluno', on_delete=models.CASCADE)
    situacao = models.ForeignKeyPlus('edu.SituacaoMatricula', verbose_name='Situação da Matrícula', on_delete=models.CASCADE)
    data = models.DateField()

    class Meta:
        verbose_name = 'Histórico de Situação do Aluno'
        verbose_name_plural = 'Históricos do Aluno'

        ordering = ('data',)

    def __str__(self):
        return str(self.situacao)


class HistoricoSituacaoMatriculaPeriodo(models.ModelPlus):
    matricula_periodo = models.ForeignKeyPlus('edu.MatriculaPeriodo', on_delete=models.CASCADE)
    situacao = models.ForeignKeyPlus('edu.SituacaoMatriculaPeriodo', verbose_name='Situação da Matrícula', on_delete=models.CASCADE)
    data = models.DateTimeField()
    usuario = models.CurrentUserField(verbose_name='Usuário')

    class Meta:
        verbose_name = 'Histórico de Situação no Período'
        verbose_name_plural = 'Históricos de Situação no Período'

        ordering = ('data',)

    def __str__(self):
        return str(self.situacao)


class HistoricoImportacao(models.ModelPlus):
    data = models.DateTimeFieldPlus('Data da Importação')
    total_alunos_criados = models.IntegerField('Total de Alunos Criados')
    total_alunos_atualizados = models.IntegerField('Total de Alunos Atualizados')
    total_matriculas_periodo_criadas = models.IntegerField('Total de Matrículas Período Criadas')
    total_matriculas_periodo_atualizadas = models.IntegerField('Total de Matrículas Período Atualizadas')

    class Meta:
        verbose_name = 'Importação Q-Acadêmico'
        verbose_name_plural = 'Importações Q-Acadêmico'
