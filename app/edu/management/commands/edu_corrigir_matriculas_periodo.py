""" """

import logging
from comum.models import Configuracao
from django.conf import settings
from djtools.management.commands import BaseCommandPlus
from edu.models import Aluno, Ano, MatriculaPeriodo, Modalidade, RegistroEmissaoDiploma, SituacaoMatricula, SituacaoMatriculaPeriodo

MODALIDADES = (
    Modalidade.INTEGRADO,
    Modalidade.INTEGRADO_EJA,
    Modalidade.FIC_INTEGRADO_EJA,
    Modalidade.SUBSEQUENTE,
    Modalidade.CONCOMITANTE,
    Modalidade.LICENCIATURA,
    Modalidade.LICENCIATURA_DUPLA_HABILITACAO,
    Modalidade.TECNOLOGIA,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)


class Command(BaseCommandPlus):
    def get_periodos(self, ano_atual, ultimo_ano, ultimo_periodo=None):
        lista = []
        if ultimo_periodo:
            if ultimo_periodo == 1:
                lista.append((ultimo_ano, 2))
            for ano in range(ultimo_ano + 1, ano_atual + 1):
                lista.append((ano, 1))
                lista.append((ano, 2))
        else:
            for ano in range(ultimo_ano + 1, ano_atual + 1):
                lista.append((ano, 1))
        return lista

    def criar_matriculas_periodo_concluidos(self):
        """
        Esta função tem por objeto criar matrículas-período com situação "Vínculo Institucional" para os alunos
        que concluíram o curso em um determinado ano e que não possuem registros de matrículas-período em algum
        dos períodos letivos anteriores à conclusão.
        Exemplo:
            Matrículas Período
            2011.1
            2012.1
            2013.1
            Data de Conclusão
            01/01/2015

            O sistema deve gerar uma matrícula-período para 2014.1 e 2015.1

        """
        situacoes = (SituacaoMatricula.CONCLUIDO, SituacaoMatricula.FORMADO, SituacaoMatricula.EGRESSO)

        ano_atual = int(Configuracao.objects.filter(chave='ano_letivo_atual')[0].valor)

        alunos = (
            Aluno.objects.filter(
                ano_letivo__ano__gte=2000, situacao__in=situacoes, curso_campus__modalidade_id__in=MODALIDADES, dt_conclusao_curso__isnull=False
            )
            .exclude(matriculaperiodo__ano_letivo__ano=ano_atual)
            .distinct()
        )

        for aluno in alunos:
            matricula_periodo = aluno.get_ultima_matricula_periodo()
            ultimo_ano = matricula_periodo.ano_letivo.ano
            ultimo_periodo = aluno.curso_campus.modalidade.id != Modalidade.INTEGRADO and matricula_periodo.periodo_letivo or None
            for ano, periodo_letivo in self.get_periodos(aluno.dt_conclusao_curso.year, ultimo_ano, ultimo_periodo):
                ano_letivo = Ano.objects.get(ano=ano)
                situacao = SituacaoMatriculaPeriodo.objects.get(pk=SituacaoMatriculaPeriodo.MATRICULA_VINCULO_INSTITUCIONAL)
                MatriculaPeriodo.objects.get_or_create(
                    aluno=aluno, ano_letivo=ano_letivo, periodo_letivo=periodo_letivo, situacao=situacao, turma=None, gerada_suap=True
                )

    def criar_matriculas_periodo(self):
        """
        Esta função tem por objeto criar matrículas-período com situação "Vínculo Institucional" para os alunos
        que ainda não concluíram o curso e que não possuem registros de matrículas-período em algum
        dos períodos letivos anteriores ao período atual.
        Exemplo:
            Matrículas Período
            2011.1
            2012.1
            2013.1
            Período Letivo Atual
            2015.1

            O sistema deve gerar uma matrícula-período para 2014.1 e 2015.1.
        A situação da última matrícula-período deve ser "Em Aberto" ao invés de "Vínculo Institucional"

        """
        situacoes = (
            SituacaoMatricula.MATRICULADO,
            SituacaoMatricula.CONCLUDENTE,
            SituacaoMatricula.AGUARDANDO_COLACAO_DE_GRAU,
            SituacaoMatricula.AGUARDANDO_ENADE,
            SituacaoMatricula.MATRICULA_VINCULO_INSTITUCIONAL,
            SituacaoMatricula.ESTAGIARIO_CONCLUDENTE,
        )

        ano_atual = int(Configuracao.objects.filter(chave='ano_letivo_atual')[0].valor)

        alunos = (
            Aluno.objects.filter(
                ano_letivo__ano__gte=2000,
                situacao__in=situacoes,
                curso_campus__modalidade_id__in=MODALIDADES,
                data_expedicao_diploma__isnull=True,
                dt_conclusao_curso__isnull=True,
                matriz__isnull=True,
            )
            .exclude(matriculaperiodo__ano_letivo__ano=ano_atual)
            .distinct()
        )

        for aluno in alunos:
            matricula_periodo = aluno.get_ultima_matricula_periodo()
            if matricula_periodo:
                ultimo_ano = matricula_periodo.ano_letivo.ano
                ultimo_periodo = aluno.curso_campus.modalidade.id != Modalidade.INTEGRADO and matricula_periodo.periodo_letivo or None
                for ano, periodo_letivo in self.get_periodos(ano_atual, ultimo_ano, ultimo_periodo):
                    ano_letivo = Ano.objects.get(ano=ano)
                    situacao = SituacaoMatriculaPeriodo.objects.get(pk=SituacaoMatriculaPeriodo.MATRICULA_VINCULO_INSTITUCIONAL)
                    if ano == ano_atual:
                        if not ultimo_periodo or periodo_letivo == 2:
                            situacao = SituacaoMatriculaPeriodo.objects.get(pk=SituacaoMatriculaPeriodo.EM_ABERTO)
                    MatriculaPeriodo.objects.get_or_create(
                        aluno=aluno, ano_letivo=ano_letivo, periodo_letivo=periodo_letivo, situacao=situacao, turma=None, gerada_suap=True
                    )

    def corrigir_ano_letivo_previsao_conclusao(self):
        """
        Esta função força a atualização do ano previsto para a conclusão do curso dos alunos
        """
        alunos = Aluno.objects.filter(
            ano_letivo__ano__gte=2000, curso_campus__modalidade_id__in=MODALIDADES, ano_let_prev_conclusao__isnull=True
        ).distinct()
        for aluno in alunos:
            aluno.save()

    def corrigir_data_expedicao_diploma(self):
        """
        Esta função força a atualiação da data de emissão de diploma do alunos.
        """
        registros = RegistroEmissaoDiploma.objects.filter(cancelado=False, aluno__data_expedicao_diploma__isnull=True)
        for registro in registros:
            registro.save()

    def handle(self, *args, **options):
        logger.debug('>>> Executando as correções de dados dos alunos')
        logger.debug('Corrigindo os anos letivos de previsão de conclusão...')
        self.corrigir_ano_letivo_previsao_conclusao()
        logger.debug('Criando as matriculas períodos dos alunos importados...')
        self.criar_matriculas_periodo()
        logger.debug('Criando as datas de expedição de diploma do aluno com registro de emissão de diploma...')
        self.corrigir_data_expedicao_diploma()
        logger.debug('Criando as matrículas período dos alunos concluídos')
        self.criar_matriculas_periodo_concluidos()
