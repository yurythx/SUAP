"""
Comando que coleta valores atualizados das variaveis de pesquisa da rede.
"""

import datetime

from django.db import transaction
from django.db.models import Q, Sum

from cnpq.models import ProducaoBibliografica
from comum.utils import get_sigla_reitoria
from djtools.management.commands import BaseCommandPlus
from edu.models import Aluno, FormaIngresso
from edu.models import Modalidade as M
from pesquisa.models import (
    EmpreendimentoIncubadora,
    LaboratorioPesquisa,
    Participacao,
    Projeto,
    RegistroPropriedadeIntelectual,
    SolicitacaoServicoLaboratorio,
    TransferenciaTecnologica,
)
from plan_estrategico.models import PeriodoPreenchimentoVariavel, VariavelCampus, VariavelTrimestralCampus
from rh.models import Servidor, UnidadeOrganizacional


class Command(BaseCommandPlus):
    @transaction.atomic
    def handle(self, *args, **options):
        if PeriodoPreenchimentoVariavel.objects.filter(data_inicio__date=datetime.date.today()).exists():
            ano = PeriodoPreenchimentoVariavel.objects.filter(data_inicio__date=datetime.date.today()).first().ano.ano
            uo = UnidadeOrganizacional.objects.suap().get(sigla=get_sigla_reitoria())
            projetos = Projeto.objects.all()
            FORMA_INGRESSO_CHOICES = [
                'L10 - Renda <= 1,5 / Autodeclarados PPI / Deficiente',
                'L10 - Renda <= 1,5 / Autodeclarados PPI / Deficiente (SISU)',
                'L13 - Qualquer Renda / Qualquer Etnia / Deficiente',
                'L13 - Qualquer Renda / Qualquer Etnia / Deficiente (SISU)',
                'L14 - Qualquer Renda / Autodeclarado PPI / Deficiente',
                'L14 - Qualquer Renda / Autodeclarado PPI / Deficiente (SISU)',
                'L15 - Deficiente / Qualquer Escola de Origem',
                'L15 - Deficiente / Qualquer Escola de Origem (SISU)',
                'L1 - Renda <= 1,5 / Qualquer Etnia',
                'L1 - Renda <= 1,5 / Qualquer Etnia (SISU)',
                'L2 - Renda <= 1,5 / Autodeclarados PPI',
                'L2 - Renda <= 1,5 / Autodeclarados PPI (SISU)',
                'L5 - Qualquer Renda / Qualquer Etnia',
                'L5 - Qualquer Renda / Qualquer Etnia (SISU)',
                'L6 - Qualquer Renda / Autodeclarado PPI',
                'L6 - Qualquer Renda / Autodeclarado PPI (SISU)',
                'L9 - Renda <= 1,5 / Qualquer Etnia / Deficiente',
                'L9 - Renda <= 1,5 / Qualquer Etnia / Deficiente (SISU)',
                'Pessoas com Deficiência',
            ]
            variaveis = (
                'C',
                'DI',
                'M_SETEC',
                'NA_SETEC',
                'NAPI',
                'NEGAPI',
                'NEAAPI',
                'NAPPP',
                'NPPB',
                'NAr',
                'NC',
                'NCL',
                'NEAHI',
                'NEGHI',
                'NHI',
                'NL_SETEC',
                'NPPA',
                'NS',
                'NSPP',
                'NTAFPP',
                'NTATT',
                'NTCTT',
                'OGM',
                'PA',
                'PC',
                'PTLT',
                'TC',
                'TPTI',
                'NTAAA',
            )
            for var in variaveis:
                total = 0
                if var == 'C':
                    total = RegistroPropriedadeIntelectual.objects.filter(tipo__descricao='Cultivares', data__year=ano).count()
                if var == 'DI':
                    total = RegistroPropriedadeIntelectual.objects.filter(tipo__descricao='Desenho Industrial', data__year=ano).count()
                if var == 'M_SETEC':
                    total = RegistroPropriedadeIntelectual.objects.filter(tipo__descricao='Marca', data__year=ano).count()
                if var == 'NAPI':
                    total = LaboratorioPesquisa.objects.all().count()
                if var == 'NA_SETEC':
                    na = VariavelCampus.objects.filter(variavel__sigla='ATENDIDOS', ano=ano).aggregate(total=Sum('valor_real'))
                    total = na['total'] if na['total'] is not None else 0
                if var == 'NAPPP':
                    projetos_nappp = projetos.filter(edital__inicio_inscricoes__year=ano)
                    queryset_nappp = projetos_nappp.filter(
                        Q(data_conclusao_planejamento__isnull=False) | Q(data_conclusao_planejamento__isnull=True, data_pre_avaliacao__isnull=False)
                    )
                    participacoes = Participacao.objects.filter(projeto__in=queryset_nappp.values_list('id')).distinct()
                    alunos = Aluno.objects.filter(vinculos__in=participacoes.values_list('vinculo_pessoa_id')).distinct().count()
                    total = alunos
                if var == 'NSPP':
                    projetos_nappp = projetos.filter(edital__inicio_inscricoes__year=ano)
                    queryset_nappp = projetos_nappp.filter(
                        Q(data_conclusao_planejamento__isnull=False) | Q(data_conclusao_planejamento__isnull=True, data_pre_avaliacao__isnull=False)
                    )
                    participacoes = Participacao.objects.filter(projeto__in=queryset_nappp.values_list('id')).distinct()
                    docentes = (
                        Servidor.objects.filter(ativo=True, vinculos__in=participacoes.values_list('vinculo_pessoa_id'), eh_docente=True)
                        .distinct()
                        .count()
                    )
                    tecnicos_adm = (
                        Servidor.objects.filter(ativo=True, id__in=participacoes.values_list('vinculo_pessoa_id'), eh_tecnico_administrativo=True)
                        .distinct()
                        .count()
                    )
                    total = docentes + tecnicos_adm
                if var == 'NAr':
                    total = ProducaoBibliografica.filtrar(tipo='ARTIGO-PUBLICADO', ano_ini=ano, ano_fim=ano, apenas_no_exercicio=True).count()
                if var == 'NC':
                    total = ProducaoBibliografica.filtrar(tipo='TRABALHO-EM-EVENTOS', ano_ini=ano, ano_fim=ano, apenas_no_exercicio=True).count()
                if var == 'NCL':
                    total = ProducaoBibliografica.filtrar(
                        tipo='CAPITULO-DE-LIVRO-PUBLICADO', ano_ini=ano, ano_fim=ano, apenas_no_exercicio=True
                    ).count()
                if var == 'NEAHI':
                    incubadoras = EmpreendimentoIncubadora.objects.filter(situacao=EmpreendimentoIncubadora.ATIVO).count()
                    servicos = (
                        SolicitacaoServicoLaboratorio.objects.exclude(laboratorio__tipo='Polo de inovação').distinct('cnpj_instituicao').count()
                    )
                    total = incubadoras + servicos
                if var == 'NEAAPI':
                    total = SolicitacaoServicoLaboratorio.objects.filter(laboratorio__tipo='Polo de inovação').distinct('cnpj_instituicao').count()
                if var == 'NEGHI':
                    total = EmpreendimentoIncubadora.objects.filter(data_incubacao__year=ano).count()
                if var == 'NEGAPI':
                    total = 0
                if var == 'NHI':
                    incubadoras = EmpreendimentoIncubadora.objects.filter(situacao=EmpreendimentoIncubadora.ATIVO, data_incubacao__year=ano).count()
                    labs = LaboratorioPesquisa.objects.all().count()
                    total = incubadoras + labs
                if var == 'NL_SETEC':
                    total = ProducaoBibliografica.filtrar(
                        tipo='LIVRO-PUBLICADO-OU-ORGANIZADO', ano_ini=ano, ano_fim=ano, apenas_no_exercicio=True
                    ).count()
                if var == 'NPPA':
                    projetos_nppa = projetos.filter(edital__inicio_inscricoes__year=ano)
                    queryset_nppa = projetos_nppa.filter(
                        Q(data_conclusao_planejamento__isnull=False) | Q(data_conclusao_planejamento__isnull=True, data_pre_avaliacao__isnull=False)
                    )
                    projeto_nppa = Projeto.objects.filter(id__in=queryset_nppa.values_list('id'))

                    total_ppa = projeto_nppa.exclude(classificacao_trl='TRL 1').count()
                    total = total_ppa
                if var == 'NPPB':
                    projetos_nppb = projetos.filter(edital__inicio_inscricoes__year=ano)
                    queryset_nppb = projetos_nppb.filter(
                        Q(data_conclusao_planejamento__isnull=False) | Q(data_conclusao_planejamento__isnull=True, data_pre_avaliacao__isnull=False)
                    )
                    projeto_nppb = Projeto.objects.filter(id__in=queryset_nppb.values_list('id'))
                    total = projeto_nppb.filter(classificacao_trl='TRL 1').count()
                if var == 'NS':
                    total = Servidor.objects.filter(ativo=True).count()
                if var == 'NTAFPP':
                    projetos_ntafpp = projetos.filter(edital__inicio_inscricoes__year=ano)
                    queryset_ntafpp = projetos_ntafpp.filter(
                        Q(data_conclusao_planejamento__isnull=False) | Q(data_conclusao_planejamento__isnull=True, data_pre_avaliacao__isnull=False)
                    )
                    participacoes = Participacao.objects.filter(projeto__in=queryset_ntafpp.values_list('id'))
                    participacoes_aplicada = Participacao.objects.filter(
                        projeto__classificacao_trl=Projeto.TRL_2, projeto__in=queryset_ntafpp.values_list('id')
                    )
                    alunos = Aluno.objects.filter(forma_ingresso__descricao__in=FORMA_INGRESSO_CHOICES)

                    total_participantes = alunos.filter(vinculos__in=participacoes_aplicada.values_list('vinculo_pessoa_id')).distinct().count()
                    demais_participantes = alunos.filter(vinculos__in=participacoes.values_list('vinculo_pessoa_id')).distinct().count()
                    total = total_participantes + demais_participantes
                if var == 'NTATT' or var == 'NTCTT':
                    total = TransferenciaTecnologica.objects.filter(data_dou__year=ano).count()
                if var == 'NTAAA':
                    cotas = {
                        'L9 - Renda <= 1,5 / Qualquer Etnia / Deficiente',
                        'L10 - Renda <= 1,5 / Autodeclarados PPI / Deficiente',
                        'L15 - Deficiente / Qualquer Escola de Origem',
                        'L10 - Renda <= 1,5 / Autodeclarados PPI / Deficiente (SISU)',
                        'L9 - Renda <= 1,5 / Qualquer Etnia / Deficiente (SISU)',
                        'L6 - Qualquer Renda / Autodeclarado PPI (SISU)',
                        'L15 - Deficiente / Qualquer Escola de Origem (SISU)',
                        'L14 - Qualquer Renda / Autodeclarado PPI / Deficiente',
                        'L1 - Renda <= 1,5 / Qualquer Etnia (SISU)',
                        'L1 - Renda <= 1,5 / Qualquer Etnia',
                        'Pessoas com Deficiência',
                        'L5 - Qualquer Renda / Qualquer Etnia (SISU)',
                        'L6 - Qualquer Renda / Autodeclarado PPI',
                        'L14 - Qualquer Renda / Autodeclarado PPI / Deficiente (SISU)',
                        'L13 - Qualquer Renda / Qualquer Etnia / Deficiente (SISU)',
                        'L2 - Renda <= 1,5 / Autodeclarados PPI (SISU)',
                        'L5 - Qualquer Renda / Qualquer Etnia',
                        'L2 - Renda <= 1,5 / Autodeclarados PPI',
                        'L13 - Qualquer Renda / Qualquer Etnia / Deficiente',
                    }
                    ids = FormaIngresso.objects.filter(descricao__in=cotas).values_list('id')
                    qs = Aluno.objects.filter(forma_ingresso__in=ids).filter(
                        curso_campus__modalidade__in=[
                            M.INTEGRADO,
                            M.SUBSEQUENTE,
                            M.CONCOMITANTE,
                            M.ENGENHARIA,
                            M.TECNOLOGIA,
                            M.ESPECIALIZACAO,
                            M.MESTRADO,
                            M.DOUTORADO,
                        ]
                    )
                    total = qs.filter(matriculaperiodo__ano_letivo__ano=ano).count()
                if var == 'TC':
                    total = RegistroPropriedadeIntelectual.objects.filter(tipo__descricao='Topografia de Circuito Integrado', data__year=ano).count()
                if var == 'OGM':
                    total = RegistroPropriedadeIntelectual.objects.filter(
                        tipo__descricao='Organismos geneticamente modificados', data__year=ano
                    ).count()
                if var == 'PC':
                    total = RegistroPropriedadeIntelectual.objects.filter(tipo__descricao='Software', data__year=ano).count()
                if var == 'PA':
                    total = RegistroPropriedadeIntelectual.objects.filter(tipo__descricao='Patente', data__year=ano).count()
                if var == 'PTLT':
                    transferencias = TransferenciaTecnologica.objects.filter(data_dou__year=ano).count()
                    total = transferencias
                if var == 'TPTI':
                    total = RegistroPropriedadeIntelectual.objects.filter(data__year=ano).count()
                if VariavelCampus.objects.filter(variavel__sigla=var, uo=uo, ano=ano).exists():
                    variavel = VariavelCampus.objects.get(variavel__sigla=var, uo=uo, ano=ano)
                    variavel.valor_real = total
                    variavel.data_atualizacao = datetime.datetime.now()
                    variavel.save()
                    trimestre = PeriodoPreenchimentoVariavel.objects.filter(data_inicio__date=datetime.date.today()).first().trimestre
                    variavel_trimestral = VariavelTrimestralCampus.objects.get_or_create(variavel=variavel, ano=variavel.ano, trimestre=trimestre)[0]
                    variavel_trimestral.valor = variavel.valor_real
                    variavel_trimestral.save()

            print('Váriáveis de pesquisa da rede importadas')
