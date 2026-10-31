"""
Comando que coleta valores atualizados das variaveis de extensão da rede.
"""

import datetime

from django.db import transaction
from django.db.models import Q, Sum

from comum.utils import get_sigla_reitoria
from djtools.management.commands import BaseCommandPlus
from edu.models import HistoricoSituacaoMatriculaPeriodo
from edu.models.cursos import CursoCampus
from eventos.models import Dimensao, Evento, Participante
from plan_estrategico.models import PeriodoPreenchimentoVariavel, VariavelCampus, VariavelTrimestralCampus
from projetos.models import CaracterizacaoBeneficiario, Participacao, Projeto, TermoParceriaAdesao
from rh.models import PessoaFisica, Servidor, UnidadeOrganizacional


class Command(BaseCommandPlus):
    @transaction.atomic
    def handle(self, *args, **options):
        if PeriodoPreenchimentoVariavel.objects.filter(data_inicio__date=datetime.date.today()).exists():
            ano = PeriodoPreenchimentoVariavel.objects.filter(data_inicio__date=datetime.date.today()).first().ano.ano
            uo = UnidadeOrganizacional.objects.suap().get(sigla=get_sigla_reitoria())
            variaveis = ('NACCA', 'NAE', 'NAPP', 'NAVS', 'NTS', 'NTEA', 'NDE', 'NEE_SETEC', 'NACE', 'NTE')
            for var in variaveis:
                total = 0
                projetos = Projeto.objects.filter(inicio_execucao__year=ano)
                if var == 'NACCA':
                    enviados = projetos.filter(
                        Q(data_conclusao_planejamento__isnull=False) | Q(data_conclusao_planejamento__isnull=True, data_pre_avaliacao__isnull=False)
                    )
                    aprovados = enviados.filter(aprovado=True, pre_aprovado=True)
                    total = aprovados.filter(id__in=TermoParceriaAdesao.objects.values_list('projeto', flat=True)).count()
                elif var == 'NAE' and VariavelCampus.objects.filter(variavel__sigla='PEX', uo=uo, ano=ano).exists():
                    pex = VariavelCampus.objects.filter(variavel__sigla='PEX', ano=ano).aggregate(total=Sum('valor_real'))

                    dimensao = Dimensao.objects.get(descricao='Extensão')
                    eventos = Evento.objects.filter(deferido=True, dimensoes=dimensao)
                    eventos = eventos.filter(
                        Q(data_inicio__year__lte=int(ano), data_fim__year__gte=int(ano)) | Q(data_fim__isnull=True, data_inicio__year=int(ano))
                    )
                    total_cursos = CursoCampus.objects.filter(ativo=True, ano_letivo__ano=ano, modalidade=8).exclude(ch_total__gt=0).count()
                    total_eventos = eventos.count()
                    total_projetos = pex['total'] if pex['total'] is not None else 0
                    total = total_eventos + total_projetos + total_cursos
                elif var == 'NAPP':
                    registros = CaracterizacaoBeneficiario.objects.filter(projeto__aprovado=True, projeto__edital__inicio_inscricoes__year=ano)
                    total = registros.aggregate(total=Sum('quantidade_atendida'))['total']
                elif var == 'NAVS' and VariavelCampus.objects.filter(variavel__sigla='PAS', uo=uo, ano=ano).exists():
                    pas = VariavelCampus.objects.filter(variavel__sigla='PAS', ano=ano).aggregate(total=Sum('valor_real'))
                    total = pas['total'] if pas['total'] is not None else 0
                elif var == 'NTS':
                    total = Servidor.objects.filter(ativo=True).count()
                elif var == 'NACE':
                    eventos = Evento.objects.filter(deferido=True, dimensoes__descricao='Extensão')
                    eventos = eventos.filter(
                        Q(data_inicio__year__lte=int(ano), data_fim__year__gte=int(ano)) | Q(data_fim__isnull=True, data_inicio__year=int(ano))
                    )
                    total = (
                        Participante.objects.filter(evento_id__in=eventos.distinct().values_list('id', flat=True)).select_related('evento').count()
                    )
                elif var == 'NTE':
                    total = (
                        HistoricoSituacaoMatriculaPeriodo.objects.filter(situacao_id=2, matricula_periodo__ano_letivo__ano=ano)
                        .values_list('matricula_periodo__aluno__pessoa_fisica__cpf')
                        .count()
                    )
                if var == 'NTEA' or var == 'NDE' or var == 'NEE_SETEC':
                    if var == 'NTEA':
                        total_pessoas = PessoaFisica.objects.filter(servidor_set__ativo=True, servidor_set__eh_tecnico_administrativo=True).distinct()
                    if var == 'NDE':
                        total_pessoas = PessoaFisica.objects.filter(servidor_set__ativo=True, servidor_set__eh_docente=True).distinct()
                    if var == 'NEE_SETEC':
                        total_pessoas = PessoaFisica.objects.filter(eh_aluno=True).distinct()
                    projetos = Projeto.objects.filter(aprovado=True)
                    projetos = projetos.filter(inicio_execucao__year=ano)
                    participacao = Participacao.objects.filter(projeto_id__in=projetos.values_list('id')).values('vinculo_pessoa__pessoa_id')
                    pessoas = participacao.distinct()
                    total = total_pessoas.filter(id__in=pessoas.values_list('vinculo_pessoa__pessoa_id')).count()

                if VariavelCampus.objects.filter(variavel__sigla=var, uo=uo, ano=ano).exists():
                    variavel = VariavelCampus.objects.get(variavel__sigla=var, uo=uo, ano=ano)
                    variavel.valor_real = total
                    variavel.data_atualizacao = datetime.datetime.now()
                    variavel.save()
                    trimestre = PeriodoPreenchimentoVariavel.objects.filter(data_inicio__date=datetime.date.today()).first().trimestre
                    variavel_trimestral = VariavelTrimestralCampus.objects.get_or_create(variavel=variavel, ano=variavel.ano, trimestre=trimestre)[0]
                    variavel_trimestral.valor = variavel.valor_real
                    variavel_trimestral.save()

            self.stdout.write('Váriáveis de rede importadas')
