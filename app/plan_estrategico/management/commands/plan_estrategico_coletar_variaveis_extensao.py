"""
Comando que coleta valores atualizados das variaveis de extensão.
"""

import datetime
from datetime import date
from django.db.models import Q
from django.db import transaction

from djtools.management.commands import BaseCommandPlus
from estagios.models import Aprendizagem, PraticaProfissional
from plan_estrategico.models import PeriodoPreenchimentoVariavel, VariavelCampus, VariavelTrimestralCampus
from projetos.models import Projeto, ProjetoCancelado, VisitaTecnica, TermoParceriaAdesao
from rh.models import UnidadeOrganizacional


class Command(BaseCommandPlus):
    def _total_especifico(self, var: str, uo: UnidadeOrganizacional, ano: int, periodo_referencia: date, projetos, total: int) -> int:
        if var == 'VIS':
            total = VisitaTecnica.objects.filter(campus=uo, data__gte=periodo_referencia).count()

        if var == 'Estg_dis':
            total = PraticaProfissional.objects.filter(data_inicio__gte=periodo_referencia, aluno__curso_campus__diretoria__setor__uo=uo).count()

        if var == 'Papr_dis':
            total = Aprendizagem.objects.filter(aprendiz__curso_campus__diretoria__setor__uo=uo, data_inicio__gt=periodo_referencia).count()

        if var == 'AM_OR_E1':
            if VariavelCampus.objects.filter(variavel__sigla='AM_OR', uo=uo, ano=ano).exists():
                total = VariavelCampus.objects.get(variavel__sigla='AM_OR', uo=uo, ano=ano).valor_real
        if var == 'Par_II_P':
            enviados = projetos.filter(
                Q(data_conclusao_planejamento__isnull=False) | Q(data_conclusao_planejamento__isnull=True, data_pre_avaliacao__isnull=False)
            )
            aprovados = enviados.filter(aprovado=True, pre_aprovado=True)
            total = aprovados.filter(id__in=TermoParceriaAdesao.objects.values_list('projeto', flat=True)).count()
        return total

    @transaction.atomic
    def handle(self, *args, **options):
        if PeriodoPreenchimentoVariavel.objects.filter(data_inicio__date=datetime.date.today()).exists():
            ano = PeriodoPreenchimentoVariavel.objects.filter(data_inicio__date=datetime.date.today()).first().ano.ano
            hoje = datetime.datetime.now()
            periodo_referencia = date(ano, 1, 1)
            for uo in UnidadeOrganizacional.objects.uo().all():
                variaveis = ('EMPCESC', 'PEX', 'PAS', 'VIS', 'Estg_dis', 'Papr_dis', 'AM_OR_E1', 'Par_II_P')
                for var in variaveis:
                    projetos = Projeto.objects.filter(inicio_execucao__year=ano, uo=uo)
                    if var == 'PAS':
                        projetos = projetos.filter(possui_cunho_social=True)
                    if var == 'EMPCESC':
                        projetos = projetos.filter(possui_acoes_empreendedorismo=True)

                    projetos_cancelados = ProjetoCancelado.objects.filter(cancelado=True, data_avaliacao__isnull=False).values_list(
                        'projeto', flat=True
                    )
                    em_execucao = (
                        projetos.filter(
                            pre_aprovado=True,
                            aprovado=True,
                            registroconclusaoprojeto__dt_avaliacao__isnull=True,
                            edital__divulgacao_selecao__lt=hoje,
                            inativado=False,
                        )
                        .exclude(id__in=projetos_cancelados)
                        .count()
                    )
                    concluidos = projetos.filter(registroconclusaoprojeto__dt_avaliacao__isnull=False).count()
                    total = em_execucao + concluidos

                    total = self._total_especifico(var, uo, ano, periodo_referencia, projetos, total)
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

            self.stdout.write('Variáveis de Extensão Importadas')
