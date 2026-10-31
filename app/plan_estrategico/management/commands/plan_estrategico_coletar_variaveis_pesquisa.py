"""
Comando que coleta valores atualizados das variaveis de pesquisa.
"""

import datetime

from django.db import transaction
from django.db.models import Q

from djtools.management.commands import BaseCommandPlus
from edu.models.alunos import Aluno
from edu.models import Diario
from edu.models.cadastros_gerais import Modalidade
from edu.models.historico import MatriculaPeriodo
from edu.models.projeto_final import ProjetoFinal
from eventos.models import Evento
from pesquisa.models import Edital, Projeto, ProjetoCancelado
from plan_estrategico.models import PeriodoPreenchimentoVariavel, VariavelCampus, VariavelTrimestralCampus
from rh.models import UnidadeOrganizacional


class Command(BaseCommandPlus):
    @transaction.atomic
    def handle(self, *args, **options):
        if PeriodoPreenchimentoVariavel.objects.filter(data_inicio__date=datetime.date.today()).exists():
            ano = PeriodoPreenchimentoVariavel.objects.filter(data_inicio__date=datetime.date.today()).first().ano.ano
            hoje = datetime.datetime.now()
            for uo in UnidadeOrganizacional.objects.uo().all():
                total = 0
                variaveis = ('ETC', 'PPI', 'DTs', 'Ds')
                for var in variaveis:
                    if var == 'ETC':
                        eventos = Evento.objects.filter(
                            deferido=True, tipo__isnull=False, campus=uo, tipo__descricao__in=['Científico/tecnológico', 'Artístico/cultural']
                        )
                        total = eventos.filter(
                            Q(data_inicio__year__lte=int(ano), data_fim__year__gte=int(ano)) | Q(data_fim__isnull=True, data_inicio__year=int(ano))
                        ).count()
                    if var == 'PPI':
                        enviados = Projeto.objects.filter(
                            Q(data_conclusao_planejamento__isnull=False)
                            | Q(data_conclusao_planejamento__isnull=True, data_pre_avaliacao__isnull=False),
                            uo=uo,
                        )
                        projetos_cancelados = ProjetoCancelado.objects.filter(cancelado=True, data_avaliacao__isnull=False).values_list(
                            'projeto', flat=True
                        )
                        aprovados = enviados.filter(aprovado=True, edital__divulgacao_selecao__lt=hoje) | enviados.filter(
                            aprovado=True, edital__formato=Edital.FORMATO_SIMPLIFICADO
                        )
                        execucao = (
                            aprovados.filter(
                                pre_aprovado=True,
                                aprovado=True,
                                registroconclusaoprojeto__dt_avaliacao__isnull=True,
                                edital__divulgacao_selecao__lt=hoje,
                                inativado=False,
                            )
                            .exclude(id__in=projetos_cancelados)
                            .count()
                        )
                        concluidos = aprovados.filter(
                            registroconclusaoprojeto__dt_avaliacao__isnull=False, edital__inicio_inscricoes__year=ano
                        ).count()
                        total = execucao + concluidos
                    if var == 'DTs':
                        qs = MatriculaPeriodo.objects.exclude(aluno__participanteturmaminicurso__turma__gerar_matricula=False)
                        qs = qs.filter(
                            aluno__curso_campus__diretoria__setor__uo=uo,
                            aluno__curso_campus__modalidade__in=[Modalidade.MESTRADO, Modalidade.DOUTORADO],
                            aluno__situacao__id=6,
                            ano_letivo__ano=ano,
                        )
                        alunos = Aluno.objects.filter(id__in=qs.order_by('aluno__id').values_list('aluno__id', flat=True).distinct())
                        total = ProjetoFinal.objects.filter(
                            matricula_periodo__aluno__in=alunos, situacao=ProjetoFinal.SITUACAO_APROVADO, resultado_data__year=ano
                        ).count()
                    if var == 'Ds':
                        diarios = (
                            Diario.objects.filter(turma__curso_campus__modalidade__in=(9, 16), ano_letivo__ano=ano)
                            .order_by('professordiario__professor')
                            .values_list('professordiario__professor')
                        )
                        qs = diarios.filter(turma__curso_campus__diretoria__setor__uo=uo)
                        total = qs.filter(professordiario__professor__titulacao__in=('Doutor', 'Doutora')).distinct().count()

                    if VariavelCampus.objects.filter(variavel__sigla=var, uo=uo, ano=ano).exists():
                        variavel = VariavelCampus.objects.get(variavel__sigla=var, uo=uo, ano=ano)
                        variavel.valor_real = total
                        variavel.data_atualizacao = datetime.datetime.now()
                        variavel.save()
                        trimestre = PeriodoPreenchimentoVariavel.objects.filter(data_inicio__date=datetime.date.today()).first().trimestre
                        variavel_trimestral = VariavelTrimestralCampus.objects.get_or_create(
                            variavel=variavel, ano=variavel.ano, trimestre=trimestre
                        )[0]
                        variavel_trimestral.valor = variavel.valor_real
                        variavel_trimestral.save()

            print('Váriáveis de Pesquisa Importadas')
