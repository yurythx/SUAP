import datetime
import tempfile
from collections import OrderedDict
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.apps import apps
from django.core.cache import cache
from django.db import transaction
from django.db.models import FloatField, Q
from django.db.models.aggregates import Count, Sum, Max
from django.db.models.functions import Cast, Length
from django.http import HttpRequest
from django.shortcuts import get_object_or_404

from ae.models import (
    AgendamentoRefeicao,
    AnaliseInscricao,
    CriterioSelecaoPrograma,
    DatasRecessoFerias,
    DemandaAluno,
    DemandaAlunoAtendida,
    DocumentoInscricaoAluno,
    HistoricoFaltasAlimentacao,
    Inscricao,
    InscricaoCaracterizacao,
    IntegranteFamiliarCaracterizacao,
    OfertaValorBolsa,
    ParametroSelecaoPrograma,
    Participacao,
    ParticipacaoPasseEstudantil,
    PassesChoices,
    PerguntaParticipacao,
    Programa,
    RelatorioGrafico,
    RespostaParticipacao,
    SolicitacaoAuxilioAluno,
    TipoRefeicao,
    Caracterizacao,
)
from ae.relatorio_gestao import (
    preencher_relatorio_atendimentos,
    preencher_relatorio_auxilios,
    preencher_relatorio_bolsas,
    preencher_relatorio_grafico,
    preencher_relatorio_programas,
    preencher_relatorio_resumo,
    preencher_relatorio_saude,
)
from comum.models import Configuracao, User
from comum.utils import get_uo
from djtools import relatorios
from djtools.assincrono import task
from djtools.db import models
from djtools.relatorios.reportlabplus import get_topo_pdf
from djtools.templatetags.filters import format_
from djtools.utils import XlsResponse, somar_dias
from edu.models import Aluno, MatriculaDiario, MatriculaPeriodo, Modalidade
from rh.models import UnidadeOrganizacional
from saude.models import TipoAtendimento


@task('Relatório de Atendimento de Gestão')
def relatorio_atendimento(get, querystring, username, task=None):
    from ae.forms import RelatorioAtendimentoForm

    user = User.objects.get(username=username)
    request = HttpRequest()
    request.META = {'QUERY_STRING': querystring}
    request.GET = get
    request.user = user
    with transaction.atomic():
        form = RelatorioAtendimentoForm(get or None, request=request)
        ano, campus, _somente_ead, _renda = form._get_dados()
        demandas_atendidas, auxilios_atendidos, bolsas_atendidas, participacoes_atendidas, atendimentos_saude = form.processar_queries()

        if (
            demandas_atendidas.exists()
            or auxilios_atendidos.exists()
            or bolsas_atendidas.exists()
            or participacoes_atendidas.exists()
            or atendimentos_saude.exists()
        ):
            relatorio_sistemico = False
            if form.request.user.has_perm('ae.pode_ver_relatorio_atendimento_todos') and not campus:
                relatorio_sistemico = True

            relatorio = form.obter_relatorio()
            if relatorio:
                relatorio.delete()

            relatorio = form.criar_relatorio()

            ################
            # ATENDIMENTOS #
            ################
            # Controla o somatório das refeições
            atendimento_refeicao = 'Refeição (Café da manhã + Almoço + Jantar)'
            demanda_id_refeicao = [DemandaAluno.ALMOCO, DemandaAluno.JANTAR, DemandaAluno.CAFE]
            # Cria um anotate para melhorar performance do cálculo
            total_demandas = demandas_atendidas.filter(demanda__ativa=True).extra(select={'mes': "date_part('month', data)"})
            total_demandas = total_demandas.values('demanda__custeio', 'aluno_id', 'demanda__id', 'demanda__nome', 'mes')
            total_demandas = total_demandas.annotate(qtd=models.Sum('quantidade'))
            total_demandas = total_demandas.annotate(valor_total=models.Sum('valor'))
            total_demandas = total_demandas.annotate(qtd_aluno=models.Count('aluno__id'))
            total_demandas = total_demandas.order_by('demanda__custeio', 'mes', 'demanda__nome')
            # Calcula as demandas do ano escolhido
            atendimentos, total_geral_atendimentos = form.obter_dados_para_exibicao(
                total_demandas,
                nome='demanda__nome',
                custeio='demanda__custeio',
                aluno_id='aluno_id',
                nome_agrupamento=atendimento_refeicao,
                nome_agrupador='demanda__id',
                valores_agrupados=demanda_id_refeicao,
            )

            total_demandas_valor = (
                demandas_atendidas.filter(demanda__ativa=True)
                .exclude(demanda__in=demanda_id_refeicao)
                .extra(select={'mes': "date_part('month', data)"})
            )
            total_demandas_valor = total_demandas_valor.values('demanda__custeio', 'aluno_id', 'demanda__id', 'demanda__nome', 'mes')
            total_demandas_valor = total_demandas_valor.annotate(qtd=models.Sum('quantidade'))
            total_demandas_valor = total_demandas_valor.annotate(valor_total=models.Sum('valor'))
            total_demandas_valor = total_demandas_valor.annotate(qtd_aluno=models.Count('aluno__id'))
            total_demandas_valor = total_demandas_valor.order_by('demanda__custeio', 'mes', 'demanda__nome')
            # Calcula as demandas do ano escolhido
            atendimentos_valor, _total_geral_atendimentos_valor = form.obter_dados_para_exibicao(
                total_demandas_valor, nome='demanda__nome', custeio='demanda__custeio', aluno_id='aluno_id', nome_agrupador='demanda__id'
            )
            atendimentos = OrderedDict(sorted(atendimentos.items(), key=lambda t: t[1]['custeio']))
            preencher_relatorio_atendimentos(relatorio, atendimentos, atendimentos_valor)
            contador = range(25)
            task.iterate(contador)  # 20%

            # Monta o gráfico das demandas no ano e cálcula o número de alunos atendidos
            atendimentos_grafico = []
            alunos_assistidos = []
            for nome, dados in list(atendimentos.items()):
                if nome != atendimento_refeicao:
                    atendimentos_grafico.append([nome, dados['total']])
                    alunos_assistidos.append([nome, len(dados['total_alunos'])])

            preencher_relatorio_grafico(relatorio, 'grafico_atendimentos', RelatorioGrafico.PIE, RelatorioGrafico.ATENDIMENTOS, atendimentos_grafico)
            task.iterate(contador)  # 24%
            preencher_relatorio_grafico(relatorio, 'alunos_unicos', RelatorioGrafico.PIE, RelatorioGrafico.ATENDIMENTOS, alunos_assistidos)
            task.iterate(contador)  # 28%

            if relatorio_sistemico:
                refeicoes_total = demandas_atendidas.filter(demanda__in=demanda_id_refeicao)
                campi_ids = refeicoes_total.values_list('campus', flat=True).distinct()
                series_refeicoes_por_campus = []
                series_refeicoes_por_campus_unicos = []
                dict_tipos = dict(DemandaAluno.REFEICOES_CHOICES)
                tipos = list(dict_tipos.keys())
                tipos.sort()
                groups = []
                for tipo in tipos:
                    groups.append(dict_tipos.get(tipo))

                campi_ids = list(campi_ids)
                nomes_uos = dict(UnidadeOrganizacional.objects.uo().filter(id__in=campi_ids).values_list('id', 'nome'))
                refeicoes_total = (
                    refeicoes_total.filter(campus_id__in=campi_ids).values_list('campus', 'demanda').annotate(qtd=models.Count('demanda'))
                )
                refeicoes_total_dict = {}
                for campus, demanda, qtd in refeicoes_total:
                    if campus not in refeicoes_total_dict:
                        refeicoes_total_dict[campus] = {}
                    refeicoes_total_dict[campus][demanda] = qtd

                for campus_id in campi_ids:
                    serie = [nomes_uos[campus_id]]
                    for tipo in tipos:
                        serie.append(refeicoes_total_dict[campus_id].get(tipo))

                    series_refeicoes_por_campus.append(serie)

                    total_demandas = demandas_atendidas.filter(demanda__in=demanda_id_refeicao, campus=campus_id).extra(
                        select={'mes': "date_part('month', data)"}
                    )
                    total_demandas = total_demandas.values('demanda__custeio', 'aluno_id', 'demanda__id', 'demanda__nome', 'mes')
                    total_demandas = total_demandas.annotate(qtd=models.Sum('quantidade'))
                    total_demandas = total_demandas.annotate(valor_total=models.Sum('valor'))
                    total_demandas = total_demandas.annotate(qtd_aluno=models.Count('aluno__id'))
                    total_demandas = total_demandas.order_by('demanda__custeio', 'mes', 'demanda__nome')

                    refeicoes, _total_geral_refeicoes = form.obter_dados_para_exibicao(
                        total_demandas,
                        nome='demanda__nome',
                        custeio='demanda__custeio',
                        aluno_id='aluno_id',
                        nome_agrupador='demanda__id',
                        valores_agrupados=demanda_id_refeicao,
                    )

                    serie = [nomes_uos[campus_id]]
                    cafe = almoco = jantar = None
                    for item, dados in list(refeicoes.items()):
                        if item:
                            if item.lower() == next(iter(dict_tipos.values())).lower():
                                almoco = len(dados['total_alunos'])
                            elif item.lower() == list(dict_tipos.values())[1].lower():
                                jantar = len(dados['total_alunos'])
                            elif item.lower() == list(dict_tipos.values())[2].lower():
                                cafe = len(dados['total_alunos'])

                    serie.append(jantar)
                    serie.append(cafe)
                    serie.append(almoco)
                    series_refeicoes_por_campus_unicos.append(serie)

                preencher_relatorio_grafico(
                    relatorio,
                    'total_refeicoes_por_campus',
                    RelatorioGrafico.GROUPEDCOLUMN,
                    RelatorioGrafico.ATENDIMENTOS,
                    series_refeicoes_por_campus,
                    groups,
                )
                task.iterate(contador)  # 32%
                preencher_relatorio_grafico(
                    relatorio,
                    'total_refeicoes_por_campus_unicos',
                    RelatorioGrafico.GROUPEDCOLUMN,
                    RelatorioGrafico.ATENDIMENTOS,
                    series_refeicoes_por_campus_unicos,
                    groups,
                )
                task.iterate(contador)  # 36%

            ############
            # AUXÍLIOS #
            ############
            auxilios_atendidos.order_by('tipoatendimentosetor__nome')
            # Cria um anotate para melhorar performance do cálculo
            total_auxilios = auxilios_atendidos.extra(select={'mes': "date_part('month', data)"})
            total_auxilios = total_auxilios.values('id', 'alunos__id', 'tipoatendimentosetor__id', 'tipoatendimentosetor__nome', 'mes')
            total_auxilios = total_auxilios.annotate(qtd=models.Count('tipoatendimentosetor'))
            total_auxilios = total_auxilios.annotate(valor_total=models.Sum('valor'))
            total_auxilios = total_auxilios.annotate(qtd_aluno=models.Count('alunos__id'))
            total_auxilios = total_auxilios.order_by('mes', 'tipoatendimentosetor__nome')
            # Calcula os auxílios do ano escolhido
            auxilios, total_geral_auxilios = form.obter_dados_para_exibicao(
                total_auxilios, nome='tipoatendimentosetor__nome', aluno_id='alunos__id', agrupamento_aluno='id'
            )
            preencher_relatorio_auxilios(relatorio, auxilios)
            task.iterate(contador)  # 40%

            # Monta o gráfico das demandas no ano e cálcula o número de alunos atendidos
            auxilios_grafico = []
            for nome, dados in list(auxilios.items()):
                auxilios_grafico.append([nome, int(dados['total'])])

            preencher_relatorio_grafico(relatorio, 'grafico_auxilios', RelatorioGrafico.PIE, RelatorioGrafico.AUXILIOS, auxilios_grafico)
            task.iterate(contador)  # 44%

            ##########
            # BOLSAS #
            ##########
            bolsas_atendidas.order_by('categoria__nome')
            total_bolsas = bolsas_atendidas.values('aluno_id', 'categoria__id', 'categoria__nome', 'data_inicio', 'data_termino', 'id')
            total_bolsas = total_bolsas.annotate(qtd_aluno=models.Count('aluno__id'))
            total_bolsas = total_bolsas.order_by('categoria__nome')
            # Calcula as bolsas do ano escolhido
            bolsas, total_geral_bolsas = form.obter_dados_para_exibicao_ano(
                total_bolsas, nome='categoria__nome', aluno_id='aluno_id', ano=ano, agrupamento_aluno='id'
            )
            preencher_relatorio_bolsas(relatorio, bolsas)
            task.iterate(contador)  # 48%
            if relatorio_sistemico:
                campi_ids = bolsas_atendidas.values_list('aluno__curso_campus__diretoria__setor__uo', flat=True).distinct()
                series_bolsas_por_campus = []
                series_bolsas_por_campus_unicos = []
                tipos = bolsas_atendidas.values_list('categoria__nome', flat=True).distinct()
                groups = []
                for tipo in tipos:
                    groups.append(tipo)

                nomes_uos = dict(UnidadeOrganizacional.objects.uo().filter(id__in=campi_ids).values_list('id', 'nome'))
                for campus_id in campi_ids:
                    serie = [nomes_uos[campus_id]]
                    dados = dict(
                        bolsas_atendidas.filter(aluno__curso_campus__diretoria__setor__uo=campus_id)
                        .values_list('categoria__nome')
                        .annotate(qtd=models.Count('categoria__nome'))
                    )
                    for tipo in tipos:
                        serie.append(dados.get(tipo))
                    series_bolsas_por_campus.append(serie)

                    ids = []
                    ids_repetidos = []
                    for item in bolsas_atendidas.filter(aluno__curso_campus__diretoria__setor__uo=campus_id):
                        if item.aluno_id not in ids:
                            ids.append(item.aluno_id)
                        else:
                            ids_repetidos.append(item.id)

                    serie = [nomes_uos[campus_id]]
                    dados_unicos = dict(
                        bolsas_atendidas.filter(aluno__curso_campus__diretoria__setor__uo=campus_id)
                        .exclude(id__in=ids_repetidos)
                        .values_list('categoria__nome')
                        .annotate(qtd=models.Count('categoria__nome'))
                    )
                    for tipo in tipos:
                        serie.append(dados_unicos.get(tipo))

                    series_bolsas_por_campus_unicos.append(serie)

                preencher_relatorio_grafico(
                    relatorio, 'total_bolsas_campus', RelatorioGrafico.GROUPEDCOLUMN, RelatorioGrafico.BOLSAS, series_bolsas_por_campus, groups
                )
                task.iterate(contador)  # 52%
                preencher_relatorio_grafico(
                    relatorio,
                    'total_bolsas_campus_unicos',
                    RelatorioGrafico.GROUPEDCOLUMN,
                    RelatorioGrafico.BOLSAS,
                    series_bolsas_por_campus_unicos,
                    groups,
                )
                task.iterate(contador)  # 56%

            else:
                bolsas_profissional_total = bolsas_atendidas.filter(aluno__curso_campus__diretoria__setor__uo=campus)
                bolsa_profissional_campus = (
                    bolsas_profissional_total.values('categoria__nome').annotate(qtd=Count('categoria__nome')).order_by('categoria__nome')
                )
                bolsas_todas = []
                bolsas_unicas = []
                if bolsa_profissional_campus:
                    for item in bolsa_profissional_campus:
                        bolsas_todas.append([item['categoria__nome'], item['qtd']])

                    if bolsas_todas[-1][1] == 0:
                        bolsas_todas.pop()

                    ids = []
                    ids_repetidos = []
                    for item in bolsas_profissional_total:
                        if item.aluno_id not in ids:
                            ids.append(item.aluno_id)
                        else:
                            ids_repetidos.append(item.id)

                    for item in (
                        bolsas_profissional_total.exclude(id__in=ids_repetidos)
                        .values('categoria__nome')
                        .annotate(qtd=Count('categoria__nome'))
                        .order_by('categoria__nome')
                    ):
                        bolsas_unicas.append([item['categoria__nome'], item['qtd']])

                preencher_relatorio_grafico(relatorio, 'bolsas_campus', RelatorioGrafico.PIE, RelatorioGrafico.BOLSAS, bolsas_todas)
                task.iterate(contador)  # 60%
                preencher_relatorio_grafico(relatorio, 'bolsas_campus_unicos', RelatorioGrafico.PIE, RelatorioGrafico.BOLSAS, bolsas_unicas)
                task.iterate(contador)  # 64%

            #############
            # PROGRAMAS #
            #############
            participacoes_atendidas.order_by('programa__tipo')
            # Cria um anotate para melhorar performance do cálculo
            total_programas = participacoes_atendidas.values(
                'id', 'aluno_id', 'programa__id', 'programa__titulo', 'programa__tipo_programa__titulo', 'data_inicio', 'data_termino'
            )
            total_programas = total_programas.annotate(qtd_aluno=models.Count('aluno__id'))
            total_programas = total_programas.order_by('programa__tipo_programa__titulo')
            # Cálcula os programas do ano escolhido
            programas, total_geral_programas = form.obter_dados_para_exibicao_ano(
                total_programas, nome='programa__titulo', aluno_id='aluno_id', ano=ano, agrupamento_aluno='id', programa=True
            )
            preencher_relatorio_programas(relatorio, programas)
            task.iterate(contador)  # 68%

            transporte_total = ParticipacaoPasseEstudantil.objects.filter(participacao__in=participacoes_atendidas.values_list('id', flat=True))
            if relatorio_sistemico:
                campi_ids = transporte_total.values_list('participacao__programa__instituicao', flat=True).distinct()
                series_transportes_por_campus = []
                series_transportes_por_campus_unicos = []
                dict_tipos = dict(PassesChoices.PASSES_CHOICES)
                tipos = list(dict_tipos.keys())
                tipos.sort()
                groups = []
                for tipo in tipos:
                    groups.append(dict_tipos.get(tipo))

                nomes_uos = dict(UnidadeOrganizacional.objects.uo().filter(id__in=campi_ids).values_list('id', 'nome'))
                for campus_id in campi_ids:
                    serie = [nomes_uos[campus_id]]
                    dados = dict(
                        transporte_total.filter(participacao__programa__instituicao=campus_id)
                        .values_list('tipo_passe_concedido')
                        .annotate(qtd=models.Count('tipo_passe_concedido'))
                    )
                    for tipo in tipos:
                        serie.append(dados.get(tipo))

                    series_transportes_por_campus.append(serie)

                    ids = []
                    ids_repetidos = []
                    participacoes_passe_estudantil = OrderedDict(
                        (item.id, item.participacao_id)
                        for item in transporte_total.filter(participacao__programa__instituicao=campus_id).order_by('-participacao_id')
                    )
                    participacoes = {
                        participacao.id: participacao.aluno_id
                        for participacao in Participacao.objects.filter(id__in=list(participacoes_passe_estudantil.values()))
                    }
                    for participacao_passe_estudantil_id, participacao_id in list(participacoes_passe_estudantil.items()):
                        aluno_id = participacoes[participacao_id]
                        if aluno_id not in ids:
                            ids.append(aluno_id)
                        else:
                            ids_repetidos.append(participacao_passe_estudantil_id)

                    serie = [nomes_uos[campus_id]]
                    dados_unicos = dict(
                        transporte_total.filter(participacao__programa__instituicao=campus_id)
                        .exclude(id__in=ids_repetidos)
                        .values_list('tipo_passe_concedido')
                        .annotate(qtd=models.Count('tipo_passe_concedido'))
                    )
                    for tipo in tipos:
                        serie.append(dados_unicos.get(tipo))

                    series_transportes_por_campus_unicos.append(serie)

                preencher_relatorio_grafico(
                    relatorio,
                    'total_transportes_por_campus',
                    RelatorioGrafico.GROUPEDCOLUMN,
                    RelatorioGrafico.PROGRAMAS,
                    series_transportes_por_campus,
                    groups,
                )
                task.iterate(contador)  # 72%
                preencher_relatorio_grafico(
                    relatorio,
                    'total_transportes_por_campus_unicos',
                    RelatorioGrafico.GROUPEDCOLUMN,
                    RelatorioGrafico.PROGRAMAS,
                    series_transportes_por_campus_unicos,
                    groups,
                )
                task.iterate(contador)  # 76%

            else:
                transporte_por_tipo = (
                    transporte_total.filter(participacao__programa__instituicao=campus)
                    .values('tipo_passe_concedido')
                    .annotate(qtd=Count('tipo_passe_concedido'))
                    .order_by('tipo_passe_concedido')
                )
                dados = []
                dados_unicos = []
                if transporte_por_tipo:
                    for item in transporte_por_tipo:
                        if item['tipo_passe_concedido'] == PassesChoices.INTERMUNICIPAL:
                            dados.append(['Intermunicipal', item['qtd']])
                        else:
                            dados.append(['Municipal', item['qtd']])

                    if dados[-1][1] == 0:
                        dados.pop()

                    ids = []
                    ids_repetidos = []
                    participacoes_passe_estudantil = OrderedDict(
                        (item.id, item.participacao_id)
                        for item in transporte_total.filter(participacao__programa__instituicao=campus).order_by('-participacao_id')
                    )
                    participacoes = {
                        participacao.id: participacao.aluno_id
                        for participacao in Participacao.objects.filter(id__in=list(participacoes_passe_estudantil.values()))
                    }
                    for participacao_passe_estudantil_id, participacao_id in list(participacoes_passe_estudantil.items()):
                        aluno_id = participacoes[participacao_id]
                        if aluno_id not in ids:
                            ids.append(aluno_id)
                        else:
                            ids_repetidos.append(participacao_passe_estudantil_id)

                    for item in (
                        transporte_total.filter(participacao__programa__instituicao=campus)
                        .exclude(id__in=ids_repetidos)
                        .values('tipo_passe_concedido')
                        .annotate(qtd=Count('tipo_passe_concedido'))
                        .order_by('tipo_passe_concedido')
                    ):
                        if item['tipo_passe_concedido'] == PassesChoices.INTERMUNICIPAL:
                            dados_unicos.append(['Intermunicipal', item['qtd']])
                        else:
                            dados_unicos.append(['Municipal', item['qtd']])

                    if dados_unicos[-1][1] == 0:
                        dados_unicos.pop()

                preencher_relatorio_grafico(relatorio, 'transporte_campus', RelatorioGrafico.PIE, RelatorioGrafico.PROGRAMAS, dados)
                task.iterate(contador)  # 80%
                preencher_relatorio_grafico(relatorio, 'transporte_campus_unicos', RelatorioGrafico.PIE, RelatorioGrafico.PROGRAMAS, dados_unicos)
                task.iterate(contador)  # 84%

            #########
            # SAÚDE #
            #########
            # Cria um anotate para melhorar performance do cálculo
            total_saude = atendimentos_saude.values(
                'id', 'aluno_id', 'tipo', 'data_aberto', 'data_fechado', 'atendimentopsicologia__data_atendimento'
            )
            total_saude = total_saude.annotate(qtd_aluno=models.Count('aluno__id'))
            # Cálcula os atendimentos de saúde do ano escolhido
            saude, total_geral_saude = form.obter_dados_para_exibicao_ano_saude(
                total_saude, nome='tipo', aluno_id='aluno_id', ano=ano, agrupamento_aluno='id'
            )
            preencher_relatorio_saude(relatorio, saude)
            task.iterate(contador)  # 88%

            atendimentos_saude = atendimentos_saude.filter(data_aberto__year=ano)
            if campus:
                atendimentos_saude = atendimentos_saude.filter(usuario_aberto__vinculo__setor__uo=campus)

            atendimentos_saude_count = (
                atendimentos_saude.extra(select={'datafechadoisnull': 'data_fechado is null'})
                .values('tipo', 'datafechadoisnull')
                .annotate(qtd=Count('tipo'))
                .values('tipo', 'qtd', 'datafechadoisnull')
            )
            dados_atendimentos = {}
            for atendimento in atendimentos_saude_count:
                tipo = atendimento['tipo']
                datafechadoisnull = atendimento['datafechadoisnull']
                qtd = atendimento['qtd']
                if tipo not in dados_atendimentos:
                    dados_atendimentos[tipo] = {}

                if datafechadoisnull not in dados_atendimentos[tipo]:
                    dados_atendimentos[tipo][datafechadoisnull] = 0

                dados_atendimentos[tipo][datafechadoisnull] = qtd

            def get_dados_atendimentos(dados_atendimentos, tipo, data_fechado):
                return dados_atendimentos[tipo][data_fechado] if tipo in dados_atendimentos and data_fechado in dados_atendimentos[tipo] else 0

            avaliacao_biomedica_aberta = get_dados_atendimentos(dados_atendimentos, TipoAtendimento.AVALIACAO_BIOMEDICA, True)
            avaliacao_biomedica_fechada = get_dados_atendimentos(dados_atendimentos, TipoAtendimento.AVALIACAO_BIOMEDICA, False)
            atendimentos_medicos = atendimentos_saude.filter(
                tipo=TipoAtendimento.ENFERMAGEM_MEDICO, condutamedica__isnull=False, data_fechado__isnull=False
            ).count()
            atendimentos_enfermagem = atendimentos_saude.filter(
                tipo=TipoAtendimento.ENFERMAGEM_MEDICO, intervencaoenfermagem__isnull=False, data_fechado__isnull=False
            ).count()
            atendimentos_odontologicos = get_dados_atendimentos(dados_atendimentos, TipoAtendimento.ODONTOLOGICO, False)
            atendimentos_psicologicos = get_dados_atendimentos(dados_atendimentos, TipoAtendimento.PSICOLOGICO, False)
            atendimentos_multidisciplinares = get_dados_atendimentos(dados_atendimentos, TipoAtendimento.MULTIDISCIPLINAR, False)

            dados = []
            dados.append(['Avaliação Biomédica Aberta', avaliacao_biomedica_aberta])
            dados.append(['Avaliação Biomédica Fechada', avaliacao_biomedica_fechada])
            dados.append(['Médico', atendimentos_medicos])
            dados.append(['Enfermagem', atendimentos_enfermagem])
            dados.append(['Odontológico', atendimentos_odontologicos])
            dados.append(['Psicológico', atendimentos_psicologicos])
            dados.append(['Multidisciplinar', atendimentos_multidisciplinares])

            preencher_relatorio_grafico(relatorio, 'saude_atendimentos', RelatorioGrafico.PIE, RelatorioGrafico.SAUDE, dados)
            task.iterate(contador)  # 92%

            ###############
            # TOTALIZADOR #
            ###############
            total_geral = preencher_relatorio_resumo(
                relatorio, total_geral_atendimentos, total_geral_auxilios, total_geral_bolsas, total_geral_programas, total_geral_saude
            )
            dados_grafico_resumo = []
            alunos_ativos = Aluno.objects.filter(id__in=MatriculaPeriodo.objects.filter(ano_letivo__ano=ano).values_list('aluno', flat=True))
            if campus:
                alunos_ativos = alunos_ativos.filter(curso_campus__diretoria__setor__uo=campus)

            dados_grafico_resumo.append(['Alunos com Vunerabilidade Socioeconômica Assistidos', len(total_geral)])
            dados_grafico_resumo.append(['Alunos com matrícula ativa no ano', alunos_ativos.count()])

            preencher_relatorio_grafico(
                relatorio, 'alunos_vulnerabilidade_assistidos', RelatorioGrafico.BAR, RelatorioGrafico.RESUMO, dados_grafico_resumo
            )
            task.iterate(contador)  # 96%

            task.finalize('Relatório processado com sucesso.', '/ae/relatorio_gestao/?{}&finalize=1'.format(request.META.get('QUERY_STRING', '')))
        else:
            task.finalize('Nenhum registro encontrado.', '/ae/relatorio_gestao/', error=True)


@task('Exportar Folha de Pagamento para XLS')
def exportar_folha_pagamento_xls(
    tipo_programa,
    oferta_do_mes,
    lista,
    ver_nome,
    ver_matricula,
    ver_cpf,
    ver_banco,
    ver_agencia,
    ver_operacao,
    ver_conta,
    ver_tipo_passe,
    ver_valor_padrao,
    ver_valor_pagar,
    total,
    task=None,
):
    colunas = []
    rows = []
    conta_atributos = 0
    colunas.append('#')
    if ver_nome:
        colunas.append('Nome')
        conta_atributos += 1
    if ver_matricula:
        colunas.append('Matrícula')
        conta_atributos += 1
    if ver_cpf:
        colunas.append('CPF')
        conta_atributos += 1
    if ver_banco:
        colunas.append('Banco')
        conta_atributos += 1
    if ver_agencia:
        colunas.append('Agência')
        conta_atributos += 1
    if ver_operacao:
        colunas.append('Operação')
        conta_atributos += 1
    if ver_conta:
        colunas.append('Conta')
        conta_atributos += 1
    if ver_tipo_passe:
        colunas.append('Tipo de Passe')
        conta_atributos += 1
    if ver_valor_padrao:
        colunas.append('Valor Padrão')
        conta_atributos += 1
    if ver_valor_pagar:
        colunas.append('Valor a Pagar')
        conta_atributos += 1
    rows.append(colunas)
    contador = 1

    for obj in task.iterate(lista):
        row = [contador]
        if ver_nome:
            row.append(format_(obj['nome']))
        if ver_matricula:
            row.append(format_(obj['matricula']))
        if ver_cpf:
            row.append(format_(obj['cpf'].replace('.', '').replace('-', '')))
        if ver_banco:
            texto = format_(obj['banco'] or '-')
            row.append(texto)
        if ver_agencia:
            texto = format_(obj['agencia'] or '-')
            row.append(texto)
        if ver_operacao:
            texto = format_(obj['operacao'] or '-')
            row.append(texto)
        if ver_conta:
            texto = format_(obj['conta'] or '-')
            row.append(texto)
        if tipo_programa == Programa.TIPO_TRANSPORTE:
            if ver_tipo_passe:
                row.append(format_(obj['tipo_passe']))
            if ver_valor_padrao:
                row.append(format_(obj['valor_concedido']))
        else:
            if ver_valor_padrao:
                resultado = oferta_do_mes or 'não informado'
                row.append(format_(resultado))

        if ver_valor_pagar:
            row.append(format_(obj['valor_a_pagar']))

        rows.append(row)
        contador += 1
    if ver_valor_pagar:
        row = ['Total']
        item = 1
        while item < conta_atributos:
            row.append('')
            item += 1
        row.append(format_(total))
        rows.append(row)

    XlsResponse(rows, processo=task)


@task('Exportar Relatório de Atendimento PNAES para XLS')
def exportar_relatorio_atendimento_pnaes_xls(
    alunos, ids_lista_alunos_alimentacao, ids_lista_alunos_transporte, lista_alunos_transporte_valores, task=None
):
    rows = [
        [
            '#',
            'Nome do(a) aluno(a) PNAES',
            'CPF do(a)  aluno(a)',
            'Renda familiar per capita (Salário(s) Mínimo(s)) ',
            'Curso',
            'Código e­Mec do curso',
            'Data de ingresso no curso',
            'Modalidade(s) de benefício(s) recebido(s)',
            'Valor recebido / ano (R$)',
        ]
    ]
    contador = 0
    for aluno in task.iterate(alunos):
        contador += 1
        renda = 0
        valor = 0
        curso = 'Não informado'
        codigo_emec = 'Não informado'
        if aluno.curso_campus:
            curso = aluno.curso_campus
            if curso:
                codigo_emec = curso.codigo_emec
        if hasattr(aluno, 'caracterizacao'):
            renda = aluno.caracterizacao.renda_per_capita
        beneficio = ''
        if aluno.id in ids_lista_alunos_alimentacao:
            beneficio += 'auxílio-alimentação; '
        if aluno.id in ids_lista_alunos_transporte:
            beneficio += 'auxílio-transporte; '
        nome_aluno = aluno.pessoa_fisica.nome
        if nome_aluno in list(lista_alunos_transporte_valores.keys()):
            valor = lista_alunos_transporte_valores[nome_aluno]
        row = [
            contador,
            format_(aluno.pessoa_fisica.nome),
            format_(aluno.pessoa_fisica.cpf),
            format_(renda),
            format_(curso),
            format_(codigo_emec),
            format_(aluno.data_matricula),
            format_(beneficio),
            format_(valor),
        ]
        rows.append(row)
    return XlsResponse(rows, processo=task)


@task('Exportar Relatório: Alunos Participantes x Índices Acadêmicos para XLS')
def relatorio_aluno_rendimento_frequencia_xls(matriculas, data_inicio, data_fim, task=None):
    rows = [
        [
            '#',
            'Nome do Aluno',
            'Nível de Ensino',
            'Curso',
            'Programas que participa',
            'Rendimento Acadêmico',
            'Frequência Escolar',
            'IRA por Curso',
            'Medidas Disciplinares / Premiações',
            'Atividades Complementares',
        ]
    ]

    contador = 0
    for matricula in task.iterate(matriculas):
        contador += 1
        texto = ''
        for registro in Participacao.abertas.filter(aluno=matricula.aluno):
            texto = texto + '{} (Entrada em: {}), '.format(registro.programa.tipo_programa, registro.data_inicio.strftime('%d/%m/%Y'))
        texto = texto[:-2]
        row = [
            contador,
            format_(matricula.aluno.pessoa_fisica.nome),
            format_(matricula.aluno.curso_campus.modalidade.nivel_ensino.descricao),
            format_(matricula.aluno.curso_campus),
            format_(texto),
            format_(matricula.aluno.get_ira()),
            format_(f'{matricula.get_percentual_carga_horaria_frequentada()}%'),
            format_(matricula.aluno.get_ira_curso_aluno()),
            format_(matricula.aluno.get_total_medidas_disciplinares_premiacoes(data_inicio, data_fim)),
            format_(matricula.aluno.get_total_atividades_complementares(data_inicio, data_fim)),
        ]
        rows.append(row)
    return XlsResponse(rows, processo=task)


@task('Processar folha de Pagamento')
def processar_folha_pagamento(programa, participantes, ano, mes, data_inicio, data_termino, url_retorno, task=None):
    def gerar_dados_participante(participante, valor):
        dados_folha = participante.aluno.get_dados_bancarios_folha_pagamento()
        sub_instance = participante.sub_instance()
        tipo_passe_fn = getattr(sub_instance, 'get_tipo_passe_concedido_display', None)
        return {
            'nome': participante.aluno.pessoa_fisica.nome,
            'matricula': participante.aluno.matricula,
            'cpf': participante.aluno.pessoa_fisica.cpf,
            'banco': participante.aluno.get_dados_bancarios_banco(),
            'agencia': participante.aluno.get_dados_bancarios_numero_agencia(),
            'operacao': dados_folha and dados_folha.operacao or '-',
            'conta': participante.aluno.get_dados_bancarios_numero_conta(),
            'tipo_passe': tipo_passe_fn and tipo_passe_fn() or '-',
            'valor_concedido': getattr(sub_instance, 'valor_concedido', '-'),
            'data_inicio': participante.data_inicio,
            'data_termino': participante.data_termino,
            'valor_a_pagar': valor,
        }

    lista = []
    total = 0
    decricao_dias_abonados = None
    oferta_do_mes = None
    if programa.get_tipo() == Programa.TIPO_TRANSPORTE:
        dias_do_mes = 22
        dias_abonados_geral = DatasRecessoFerias.objects.filter(data__gte=data_inicio, data__lt=data_termino, campus=programa.instituicao).exclude(
            data__week_day__in=[1, 7]
        )
        decricao_dias_abonados = [dia.data.day for dia in dias_abonados_geral.order_by('data')]
        for item in task.iterate(participantes):
            dias_abonados = dias_abonados_geral.filter(data__gte=item.data_inicio)
            diferenca = None
            if item.data_termino:
                dias_abonados = dias_abonados.filter(data__lt=item.data_termino)
            qtd_dias_abonados = dias_abonados.count()
            valor = item.sub_instance().valor_concedido
            if valor:
                if item.data_inicio > data_inicio and item.data_inicio.month == int(mes):
                    fromdate = item.data_inicio
                    todate = data_termino
                    daygenerator = (fromdate + datetime.timedelta(x + 1) for x in range((todate - fromdate).days))
                    diferenca = sum(1 for day in daygenerator if day.weekday() < 5)

                    if diferenca > dias_do_mes:
                        diferenca_em_dias = dias_do_mes - qtd_dias_abonados
                    else:
                        diferenca_em_dias = diferenca - qtd_dias_abonados
                    if diferenca_em_dias < 0:
                        diferenca_em_dias = 0
                    valor = Decimal((valor / dias_do_mes) * diferenca_em_dias).quantize(Decimal(10) ** -2)
                if item.data_termino and item.data_termino < data_termino and item.data_termino.month == int(mes):
                    fromdate = data_inicio
                    todate = item.data_termino
                    daygenerator = (fromdate + datetime.timedelta(x + 1) for x in range((todate - fromdate).days))
                    diferenca = sum(1 for day in daygenerator if day.weekday() < 5)
                    if diferenca > dias_do_mes:
                        diferenca_em_dias = dias_do_mes - qtd_dias_abonados
                    else:
                        diferenca_em_dias = diferenca - qtd_dias_abonados
                    if diferenca_em_dias < 0:
                        diferenca_em_dias = 0
                    valor = Decimal((valor / dias_do_mes) * diferenca_em_dias).quantize(Decimal(10) ** -2)
                if not diferenca:
                    if qtd_dias_abonados > dias_do_mes:
                        qtd_dias_abonados = dias_do_mes
                    valor = ((dias_do_mes - qtd_dias_abonados) * valor) / dias_do_mes
                total += valor
                lista.append(gerar_dados_participante(item, valor))

    elif programa.get_tipo() == Programa.TIPO_TRABALHO:
        dias_do_mes = 30
        ofertas = OfertaValorBolsa.objects.filter(data_inicio__lte=data_termino, data_termino__gte=data_inicio, campus=programa.instituicao)
        oferta_do_mes = ofertas[0].valor
        for item in task.iterate(participantes):
            valor = ofertas[0].valor
            if item.data_inicio > data_inicio and item.data_inicio.month == int(mes):
                diferenca = data_termino - item.data_inicio
                valor = Decimal((valor / dias_do_mes) * diferenca.days).quantize(Decimal(10) ** -2)
            if item.data_termino and item.data_termino < data_termino and item.data_termino.month == int(mes):
                diferenca = item.data_termino - data_inicio
                valor = Decimal((valor / dias_do_mes) * diferenca.days).quantize(Decimal(10) ** -2)
            total += valor
            lista.append(gerar_dados_participante(item, valor))
    else:
        dias_do_mes = 30
        for item in task.iterate(participantes):
            if RespostaParticipacao.objects.filter(
                pergunta__eh_info_financeira=True, pergunta__ativo=True, pergunta__tipo_resposta=PerguntaParticipacao.NUMERO, participacao=item
            ).exists():
                valor = (
                    RespostaParticipacao.objects.filter(
                        pergunta__eh_info_financeira=True,
                        pergunta__ativo=True,
                        pergunta__tipo_resposta=PerguntaParticipacao.NUMERO,
                        participacao=item,
                    )
                    .annotate(soma=Cast('valor_informado', FloatField()))
                    .aggregate(Sum('soma'))['soma__sum']
                )
                if item.data_inicio > data_inicio and item.data_inicio.month == int(mes):
                    diferenca = data_termino - item.data_inicio
                    valor = Decimal((valor / dias_do_mes) * diferenca.days).quantize(Decimal(10) ** -2)
                if item.data_termino and item.data_termino < data_termino and item.data_termino.month == int(mes):
                    diferenca = item.data_termino - data_inicio
                    valor = Decimal((valor / dias_do_mes) * diferenca.days).quantize(Decimal(10) ** -2)
                total += Decimal(valor)
                lista.append(gerar_dados_participante(item, valor))

    CACHE_NAME = f'_AE_FOLHA_PAGAMENTO_{programa.id}_{ano}_{mes}'

    cache.set(CACHE_NAME, [oferta_do_mes, dias_do_mes, decricao_dias_abonados, lista, total])
    task.finalize('Folha de pagamento processada com sucesso.', url_retorno)


@task('Imprimir Lista Diária de Alimentação')
def imprimir_lista_diaria(tipo_refeicao, data, programa, categoria_busca, agendados, somente_participantes, dia_semana, request, task=None):
    if tipo_refeicao == DemandaAluno.CAFE:
        tipo_refeicao_label = 'CAFÉ DA MANHÃ'
        tipo_refeicao_agendada = AgendamentoRefeicao.TIPO_CAFE
        falta_tipo_refeicao = TipoRefeicao.TIPO_CAFE
    elif tipo_refeicao == DemandaAluno.ALMOCO:
        tipo_refeicao_label = 'ALMOÇO'
        tipo_refeicao_agendada = AgendamentoRefeicao.TIPO_ALMOCO
        falta_tipo_refeicao = TipoRefeicao.TIPO_ALMOCO
    else:
        tipo_refeicao_label = 'JANTAR'
        tipo_refeicao_agendada = AgendamentoRefeicao.TIPO_JANTAR
        falta_tipo_refeicao = TipoRefeicao.TIPO_JANTAR

    data_fim = somar_dias(data, 1)
    registros_participacoes = Participacao.objects.filter(
        Q(programa=programa),
        Q(participacaoalimentacao__suspensa=False),
        Q(data_termino__isnull=True) | Q(data_termino__gte=data_fim),
        Q(data_inicio__lte=data),
    )

    faltas = HistoricoFaltasAlimentacao.objects.filter(participacao__programa=programa, data=data, justificativa__isnull=False)
    registros_participacoes = registros_participacoes.exclude(
        id__in=faltas.filter(tipo_refeicao=falta_tipo_refeicao).values_list('participacao', flat=True)
    )

    if categoria_busca:
        registros_participacoes = registros_participacoes.filter(participacaoalimentacao__categoria=categoria_busca)

    registros_participacoes = registros_participacoes.values_list('aluno_id', flat=True)
    registros_agendados = AgendamentoRefeicao.objects.filter(
        cancelado=False, tipo_refeicao=tipo_refeicao_agendada, programa=programa, data__date__gte=data, data__date__lte=data_fim
    ).values_list('aluno_id', flat=True)
    registros_atendidos = DemandaAlunoAtendida.objects.filter(
        campus=programa.instituicao, demanda=tipo_refeicao, data__gte=data, data__lte=data_fim
    ).values_list('aluno_id', flat=True)

    ids = set()
    if not somente_participantes:
        ids.update(registros_agendados)

    if not agendados:
        ids.update(registros_participacoes)
        ids.update(registros_atendidos)
    alunos = Aluno.objects.filter(id__in=ids).only('pessoa_fisica', 'matricula')

    count = 1
    atendimentos = []
    categoria_label = 'Atendimento Avulso'
    solicitacao_atendida = None
    task.count(alunos, alunos)
    for aluno in task.iterate(alunos):
        categoria = ''
        motivo_atendimento = ''
        try:
            inscricao = aluno.inscricao_set.get(programa=programa).sub_instance()
        except Inscricao.DoesNotExist:
            inscricao = None

        except Exception:
            # Ainda existem alunos com inscrições duplicadas (ver https://projetos.ifrn.edu.br/issues/3889)
            # Existem alunos com participações que não tem os dados dos atendimentos
            inscricoes = aluno.inscricao_set.filter(programa=programa, participacao__isnull=False, participacao__data_termino__isnull=True).distinct()
            if inscricoes.exists():
                inscricao = inscricoes[0].sub_instance()
            else:
                inscricao = None

        participacao_aberta = None
        participacao = None
        if inscricao:
            try:
                participacao = inscricao.get_ultima_participacao()
                participacao_aberta = inscricao.get_participacao_aberta()
            except Exception:
                pass
            if categoria_busca and participacao and participacao.sub_instance().categoria != categoria_busca:
                continue
            if participacao:
                if tipo_refeicao == DemandaAluno.ALMOCO:
                    solicitacao_atendida = participacao.sub_instance().solicitacao_atendida_almoco
                elif tipo_refeicao == DemandaAluno.JANTAR:
                    solicitacao_atendida = participacao.sub_instance().solicitacao_atendida_janta
                elif tipo_refeicao == DemandaAluno.CAFE:
                    solicitacao_atendida = participacao.sub_instance().solicitacao_atendida_cafe
            else:
                solicitacao_atendida = None

        adiciona_aluno = False

        if programa.get_atendimento(aluno, tipo_refeicao, data):
            if AgendamentoRefeicao.objects.filter(cancelado=False, aluno=aluno, data__date=data, tipo_refeicao=tipo_refeicao_agendada).exists():
                adiciona_aluno = True
                registro_do_agendamento = AgendamentoRefeicao.objects.filter(
                    cancelado=False, aluno=aluno, data__date=data, tipo_refeicao=tipo_refeicao_agendada
                ).first()
                if hasattr(registro_do_agendamento, 'solicitacaorefeicaoaluno'):
                    motivo_atendimento = registro_do_agendamento.solicitacaorefeicaoaluno.motivo_solicitacao

            elif not agendados:
                if (
                    solicitacao_atendida
                    and solicitacao_atendida.valida()
                    and (
                        (dia_semana == '0' and solicitacao_atendida.seg)
                        or (dia_semana == '1' and solicitacao_atendida.ter)
                        or (dia_semana == '2' and solicitacao_atendida.qua)
                        or (dia_semana == '3' and solicitacao_atendida.qui)
                        or (dia_semana == '4' and solicitacao_atendida.sex)
                    )
                ):
                    if participacao and ((not participacao.data_termino) or (participacao.data_termino and participacao.data_termino >= data)):
                        adiciona_aluno = True
                    else:
                        adiciona_aluno = True
                        categoria = categoria_label
                else:
                    adiciona_aluno = True
                    categoria = categoria_label

        else:
            if AgendamentoRefeicao.objects.filter(cancelado=False, aluno=aluno, data__date=data, tipo_refeicao=tipo_refeicao_agendada).exists():
                adiciona_aluno = True
                registro_do_agendamento = AgendamentoRefeicao.objects.filter(
                    cancelado=False, aluno=aluno, data__date=data, tipo_refeicao=tipo_refeicao_agendada
                ).first()
                if hasattr(registro_do_agendamento, 'solicitacaorefeicaoaluno'):
                    motivo_atendimento = registro_do_agendamento.solicitacaorefeicaoaluno.motivo_solicitacao

            elif (
                not agendados
                and solicitacao_atendida
                and solicitacao_atendida.valida()
                and (
                    (dia_semana == '0' and solicitacao_atendida.seg)
                    or (dia_semana == '1' and solicitacao_atendida.ter)
                    or (dia_semana == '2' and solicitacao_atendida.qua)
                    or (dia_semana == '3' and solicitacao_atendida.qui)
                    or (dia_semana == '4' and solicitacao_atendida.sex)
                )
            ):
                if participacao and ((not participacao.data_termino) or (participacao.data_termino and participacao.data_termino >= data)):
                    if not HistoricoFaltasAlimentacao.objects.filter(
                        justificativa__isnull=False, aluno=aluno, data=data, tipo_refeicao=falta_tipo_refeicao, cancelada=False
                    ).exists():
                        adiciona_aluno = True

        if inscricao and participacao_aberta:
            categoria = participacao.participacaoalimentacao.categoria or 'Não informada'

        if not categoria:
            categoria = 'Refeição Agendada'
        if adiciona_aluno:
            dicionario = {
                'count': count,
                'matricula': aluno.matricula,
                'pessoa_fisica': aluno.pessoa_fisica.nome,
                'categoria': categoria,
                'motivo_atendimento': motivo_atendimento,
            }

            atendimentos.append(dicionario)
            count += 1

    uo = get_uo(request.user)
    topo = get_topo_pdf(f'Relatório Diário - Programa de Alimentação ({tipo_refeicao_label})')
    servidor = request.user.get_relacionamento()
    info = [['UO', uo], ['Servidor', servidor], ['Data', data.strftime('%d/%m/%Y')], ['Emitido em', datetime.datetime.now().strftime('%d/%m/%Y')]]
    dados = [['Matrícula', 'Aluno', 'Categoria', 'Restrição Alimentar', 'Assinatura']]
    for registro in task.iterate(atendimentos):
        ProcessoSaudeDoenca = apps.get_model('saude', 'ProcessoSaudeDoenca')
        AtendimentoNutricao = apps.get_model('saude', 'AtendimentoNutricao')
        lista_restricoes = []
        if ProcessoSaudeDoenca:
            processos_saude_doenca = ProcessoSaudeDoenca.objects.filter(atendimento__aluno__matricula=registro['matricula'])
            if processos_saude_doenca.exists():
                mais_recente = processos_saude_doenca.latest('id')
                tem_alergia_alimentos = mais_recente.alergia_alimentos
                if tem_alergia_alimentos:
                    lista_restricoes.append(mais_recente.que_alimentos)
        if AtendimentoNutricao:
            atendimentos_nutricao = AtendimentoNutricao.objects.filter(atendimento__aluno__matricula=registro['matricula'])
            if atendimentos_nutricao.exists():
                atendimento = atendimentos_nutricao.latest('id')
                for restricao in atendimento.restricao_alimentar.all():
                    lista_restricoes.append(restricao.descricao)

        dados.append([registro['matricula'], registro['pessoa_fisica'], registro['categoria'], ', '.join(lista_restricoes), ' '])
    tabela_info = relatorios.table(info, grid=0, w=[30, 160])
    tabela_dados = relatorios.table(dados, head=1, zebra=1, w=[27, 35, 26, 18, 45], count=1)
    body = [*topo, tabela_info, relatorios.space(8), tabela_dados, relatorios.space(8)]
    temp = tempfile.NamedTemporaryFile(suffix='.pdf', mode='w+b', delete=False)
    temp.close()
    relatorios.PdfReport(body=body, filename=temp.name).generate()
    task.finalize('Lista gerada com sucesso', '..', file_path=temp.name)


def _criterios_form():
    """Import tardio de ``CriterioSelecaoProgramaForm`` (``ae.forms`` importa ``ae.tasks``)."""
    from ae.forms import CriterioSelecaoProgramaForm

    return CriterioSelecaoProgramaForm


def _semestre_atual(aluno: Aluno) -> str:
    """Semestre/ano do período letivo corrente; vazio quando o aluno não tem matrícula corrente.

    O acesso direto a ``get_matriculas_periodo()[0]`` estourava ``IndexError`` — e a task
    inteira com 500 — para um aluno com caracterização e sem matrícula no período corrente.
    """
    matriculas = aluno.get_matriculas_periodo()
    if not matriculas:
        return ''
    return f'{matriculas[0].periodo_letivo}/{matriculas[0].ano_letivo}'


def _valor_renda_per_capita(caracterizacao) -> float:
    """Renda bruta dividida pelas pessoas do domicílio (0 quando o domicílio está vazio)."""
    if caracterizacao.qtd_pessoas_domicilio > 0:
        return caracterizacao.renda_bruta_familiar / caracterizacao.qtd_pessoas_domicilio
    return 0


def _sim_nao(existe: bool) -> str:
    """Converte presença/ausência no vocabulário da análise ('Sim'/'Não')."""
    return 'Sim' if existe else 'Não'


def _ultima_caracterizacao(aluno: Aluno):
    """Última caracterização do formulário de inscrição do aluno (pode não existir)."""
    return InscricaoCaracterizacao.objects.filter(aluno=aluno).order_by('-id').first()


def _preencher_refeicoes(nova_analise: AnaliseInscricao, inscricao: Inscricao) -> None:
    """Preenche refeições por dia, total e motivo (só o programa de alimentação tem o dado)."""
    if inscricao.programa.tipo_programa.sigla != Programa.TIPO_ALIMENTACAO:
        return
    inscricao_alimentacao = inscricao.sub_instance()
    dias_de_refeicoes = inscricao_alimentacao.get_total_refeicoes_por_dia()
    for campo, quantidade in zip(('refeicao_seg', 'refeicao_ter', 'refeicao_qua', 'refeicao_qui', 'refeicao_sex'), dias_de_refeicoes, strict=False):
        setattr(nova_analise, campo, quantidade)
    nova_analise.total_refeicoes = sum(dias_de_refeicoes)
    nova_analise.motivo_atendimento = inscricao_alimentacao.motivo_atendimento or inscricao.motivo


def _acumular_pontuacao(criterio, descricao: str, pontuacao_total: float, total_integrantes: int, nova_analise: AnaliseInscricao):
    """Soma a pontuação do critério quando a descrição casa; marca o critério restritivo."""
    if criterio.opcao != descricao or criterio.pontuacao <= 0:
        return pontuacao_total, total_integrantes
    if criterio.restritivo:
        nova_analise.possui_criterio_restritivo = True
    return pontuacao_total + criterio.pontuacao, total_integrantes + 1


def _pontuacao_trabalho(nova_analise: AnaliseInscricao, criterios_programa, caracterizacao, ultima_caracterizacao) -> float:
    """Média da pontuação de situação de trabalho (aluno e integrantes do núcleo familiar)."""
    criterios = list(criterios_programa.filter(criterio=_criterios_form().SITUACAO_TRABALHO).order_by('pontuacao'))
    if not criterios:
        return 0
    integrantes = IntegranteFamiliarCaracterizacao.objects.none()
    if ultima_caracterizacao is not None:
        integrantes = IntegranteFamiliarCaracterizacao.objects.filter(inscricao_caracterizacao=ultima_caracterizacao)
    pontuacao_total = 0
    total_integrantes = 0
    for criterio in criterios:
        for integrante in integrantes:
            pontuacao_total, total_integrantes = _acumular_pontuacao(
                criterio, integrante.situacao_trabalho.descricao, pontuacao_total, total_integrantes, nova_analise
            )
        pontuacao_total, total_integrantes = _acumular_pontuacao(
            criterio, caracterizacao.trabalho_situacao.descricao, pontuacao_total, total_integrantes, nova_analise
        )
    if not total_integrantes:
        return 0
    return pontuacao_total / total_integrantes


def _origem_escolar(aluno: Aluno) -> str:
    """Escola de origem: fundamental para Técnico Integrado, médio para os demais cursos."""
    if aluno.curso_campus.modalidade.descricao == 'Técnico Integrado':
        escola = aluno.caracterizacao.escola_ensino_fundamental
    else:
        escola = aluno.caracterizacao.escola_ensino_medio
    return escola.descricao if escola else 'Não informado'


def _preencher_composicao_familiar(nova_analise: AnaliseInscricao, aluno: Aluno) -> None:
    """Composição familiar: 60+, menores de 14, deficiência, doença crônica e medicamentos."""
    hoje = datetime.date.today()
    criterios = (
        ('composicao_maior_60', {'data_nascimento__lte': hoje + relativedelta(years=-60)}),
        ('composicao_menor_14', {'data_nascimento__gt': hoje + relativedelta(years=-14)}),
        ('composicao_deficiencia', {'possui_deficiencia': True}),
        ('doenca_cronica', {'possui_doenca_cronica': True}),
        ('despesa_medicamentos', {'possui_despesa_medicamento': True}),
    )
    for campo, filtro in criterios:
        setattr(nova_analise, campo, _sim_nao(IntegranteFamiliarCaracterizacao.objects.filter(aluno=aluno, **filtro).exists()))


def _gasto_transporte(inscricao: Inscricao, ultima_caracterizacao) -> float:
    """Gasto mensal com transporte (valor informado vezes 22) ou 0 fora do programa de transporte."""
    if inscricao.programa.tipo_programa.sigla != Programa.TIPO_TRANSPORTE:
        return 0
    sub = inscricao.sub_instance()
    valor_informado = sub.valor_transporte or (ultima_caracterizacao.valor_transporte if ultima_caracterizacao else None)
    if not valor_informado:
        return 0
    return valor_informado * 22


def _recebe_bolsa(inscricao: Inscricao) -> str:
    """'Sim' quando o aluno já tem bolsa vinculada à inscrição do programa de trabalho."""
    return _sim_nao(inscricao.programa.tipo_programa.sigla == Programa.TIPO_TRABALHO and inscricao.sub_instance().bolsas.exists())


def _cumpriu_toda_ch(aluno: Aluno) -> str:
    """'Sim' quando o aluno não tem componentes pendentes."""
    return _sim_nao(not aluno.get_componentes_pendentes())


def _existe_reprovacao(aluno: Aluno) -> str:
    """'Sim' quando há reprovação (por falta, extensão ou nota) em qualquer diário do aluno."""
    situacoes = (
        MatriculaDiario.SITUACAO_REPROVADO,
        MatriculaDiario.SITUACAO_REPROVADO_POR_FALTA,
        MatriculaDiario.SITUACAO_REPROVADO_EXTENSAO,
    )
    return _sim_nao(MatriculaDiario.objects.filter(matricula_periodo__aluno=aluno, situacao__in=situacoes).exists())


def _despesas_basicas_volumosas(caracterizacao) -> str:
    """Moradia alugada/financiada pontua como despesa básica volumosa; o resto é 'Outro'."""
    tipo_imovel = caracterizacao.tipo_imovel_residencial
    return 'Alugado ou financiado' if tipo_imovel and tipo_imovel.descricao in ('Alugado', 'Financiado') else 'Outro'


def _habilitado_bolsa_integral(aluno: Aluno) -> bool:
    """O critério só pontua com o comprovante de bolsa integral validado."""
    return DocumentoInscricaoAluno.objects.filter(
        aluno=aluno, validado=True, tipo_arquivo='Comprovante de estudo em escola particular com bolsa integral'
    ).exists()


def _habilitado_napne(aluno: Aluno) -> bool:
    """O critério só pontua quando a caracterização registra acompanhamento pelo NAPNE."""
    return InscricaoCaracterizacao.objects.filter(aluno=aluno, recebe_acompanhamento_napne=True).exists()


def _habilitado_orfanato(aluno: Aluno, ultima_caracterizacao) -> bool:
    """O critério só pontua com a declaração de orfanato na caracterização e o comprovante validado."""
    if ultima_caracterizacao is None or not ultima_caracterizacao.morou_em_orfanato:
        return False
    return DocumentoInscricaoAluno.objects.filter(
        aluno=aluno, validado=True, tipo_arquivo='Comprovante de que mora ou morou em abrigo institucional (orfanato)'
    ).exists()


def _habilitado_estrangeiro(aluno: Aluno, caracterizacao) -> bool:
    """O critério de estrangeiro/refugiado só pontua para renda até 1 SM ou com o comprovante."""
    if aluno.nacionalidade != 'Estrangeira':
        return False
    salario_minimo = Decimal(Configuracao.get_valor_por_chave('comum', 'salario_minimo'))
    if caracterizacao.renda_bruta_familiar < salario_minimo:
        return True
    return DocumentoInscricaoAluno.objects.filter(aluno=aluno, validado=True, tipo_arquivo='Comprovante de vinda para o país como refugiado').exists()


def _habilitado_ingresso_cota(aluno: Aluno) -> bool:
    """O critério de cota só pontua quando a forma de ingresso é ação afirmativa/programa de vagas."""
    return bool(aluno.forma_ingresso and aluno.forma_ingresso.is_acao_afirmativa_ou_programa_vagas())


def _aplicar_criterio(criterios_programa, tipo: str, opcao) -> tuple:
    """Pontuação/restritividade do critério que casa com a opção; (0, False) quando não há."""
    criterio = criterios_programa.filter(criterio=tipo, opcao=opcao).first()
    if criterio is None:
        return 0, False
    return criterio.pontuacao, criterio.restritivo


def _montar_pontuacoes(pontuacoes: dict) -> dict:
    """``tipo -> pontuação`` na ordem em que a tela de análise exibe os critérios.

    A ordem importa: o ``pontuacoes`` é um JSON consumido na ordem de inserção e o
    dicionário de trabalho do cálculo não preserva a ordem de exibição.
    """
    campos = _criterios_form()
    ordem = (
        campos.RENDA_PER_CAPITA,
        campos.SITUACAO_TRABALHO,
        campos.ORIGEM_ESCOLAR,
        campos.TIPO_ZONA,
        campos.MAIOR_60,
        campos.MENOR_14,
        campos.COM_DEFICIENCIA,
        campos.DOENCA_CRONICA,
        campos.GASTOS_MEDICAMENTOS,
        campos.RECEBE_BOLSA,
        campos.BENEFICIARIO_PROGRAMA_SOCIAL,
        campos.DESPESAS_BASICAS_VOLUMOSAS,
        campos.BOLSA_INTEGRAL_ESCOLA_PART,
        campos.RECEBE_ACOMPANHAMENTO_NAPNE,
        campos.MOROU_ORFANATO,
        campos.ESTRANGEIRO_REFUGIADO,
        campos.INGRESSO_COTA,
    )
    data = {}
    for tipo in ordem:
        if tipo in pontuacoes:
            data[tipo] = pontuacoes[tipo]
    return data


def _pontuacao_zona_quilombola(nova_analise: AnaliseInscricao, criterios_programa, ultima_caracterizacao) -> tuple:
    """Zona quilombola/indígena/rural não declarada na caracterização, mas informada na inscrição."""
    zonas = ('Comunidade Quilombola', 'Rural', 'Comunidade Indígena')
    if nova_analise.zona_domiciliar in zonas or not (ultima_caracterizacao and ultima_caracterizacao.eh_quilombola):
        return 0, False
    criterio = criterios_programa.filter(criterio=_criterios_form().TIPO_ZONA, opcao__in=zonas).first()
    if criterio is None:
        return 0, False
    return criterio.pontuacao, criterio.restritivo


def _casos_de_pontuacao(nova_analise: AnaliseInscricao, caracterizacao, aluno: Aluno, ultima_caracterizacao) -> tuple:
    """(tipo do critério, opção, habilitado) de todos os critérios que o programa pontua."""
    campos = _criterios_form()
    return (
        (campos.RENDA_PER_CAPITA, caracterizacao.get_faixa_renda_per_capita(), True),
        (campos.ORIGEM_ESCOLAR, nova_analise.origem_escolar, True),
        (campos.TIPO_ZONA, nova_analise.zona_domiciliar, True),
        (campos.MAIOR_60, nova_analise.composicao_maior_60, True),
        (campos.MENOR_14, nova_analise.composicao_menor_14, True),
        (campos.COM_DEFICIENCIA, nova_analise.composicao_deficiencia, True),
        (campos.DOENCA_CRONICA, nova_analise.doenca_cronica, True),
        (campos.GASTOS_MEDICAMENTOS, nova_analise.despesa_medicamentos, True),
        (campos.RECEBE_BOLSA, nova_analise.recebe_bolsa, True),
        (campos.BENEFICIARIO_PROGRAMA_SOCIAL, nova_analise.beneficiario_programa_social, True),
        (campos.DESPESAS_BASICAS_VOLUMOSAS, nova_analise.despesas_basicas_volumosas, True),
        (campos.BOLSA_INTEGRAL_ESCOLA_PART, 'Sim', _habilitado_bolsa_integral(aluno)),
        (campos.RECEBE_ACOMPANHAMENTO_NAPNE, 'Sim', _habilitado_napne(aluno)),
        (
            campos.MOROU_ORFANATO,
            ultima_caracterizacao.morou_em_orfanato if ultima_caracterizacao else '',
            _habilitado_orfanato(aluno, ultima_caracterizacao),
        ),
        (campos.ESTRANGEIRO_REFUGIADO, 'Sim', _habilitado_estrangeiro(aluno, caracterizacao)),
        (campos.INGRESSO_COTA, 'Sim', _habilitado_ingresso_cota(aluno)),
    )


def _pontuar_criterios(
    nova_analise: AnaliseInscricao, criterios_programa, caracterizacao, aluno: Aluno, ultima_caracterizacao, pontuacao_trabalho: float
) -> None:
    """Aplica os critérios do programa e grava ``pontuacoes``, ``pontuacao_total`` e ``pontuacao_criterios``."""
    import json

    campos = _criterios_form()
    pontuacoes = {}
    pontuacao_total = 0
    for tipo, opcao, habilitado in _casos_de_pontuacao(nova_analise, caracterizacao, aluno, ultima_caracterizacao):
        if not habilitado:
            continue
        pontuacao, restritivo = _aplicar_criterio(criterios_programa, tipo, opcao)
        pontuacoes[tipo] = pontuacao
        pontuacao_total += pontuacao
        if restritivo:
            nova_analise.possui_criterio_restritivo = True

    pontuacoes[campos.SITUACAO_TRABALHO] = pontuacao_trabalho
    pontuacao_total += pontuacao_trabalho

    pontuacao_zona, restritivo_zona = _pontuacao_zona_quilombola(nova_analise, criterios_programa, ultima_caracterizacao)
    if pontuacao_zona:
        pontuacoes[campos.TIPO_ZONA] = pontuacao_zona
        pontuacao_total += pontuacao_zona
        if restritivo_zona:
            nova_analise.possui_criterio_restritivo = True

    nova_analise.pontuacoes = json.dumps(_montar_pontuacoes(pontuacoes), ensure_ascii=False)
    nova_analise.pontuacao_total = pontuacao_total
    nova_analise.pontuacao_criterios = pontuacao_total


def _simulacao_transporte(nova_analise: AnaliseInscricao, parametro, aluno: Aluno) -> None:
    """Sugestão do programa de transporte: percentual do parâmetro e dados bancários do aluno."""
    if parametro.exists():
        porcentagem = parametro[0].porcentagem_sugerida
        nova_analise.qtd_refeicoes_sugeridas = porcentagem
        nova_analise.simulacao_resultado = porcentagem
        nova_analise.gasto_transporte_sugerido = (nova_analise.gasto_transporte * int(porcentagem)) / 100
        nova_analise.valor_simulacao_resultado = (nova_analise.gasto_transporte * int(porcentagem)) / 100
    nova_analise.banco = aluno.get_dados_bancarios_banco()
    nova_analise.agencia = aluno.get_dados_bancarios_numero_agencia()
    nova_analise.operacao = aluno.get_dados_bancarios_operacao()
    nova_analise.conta = aluno.get_dados_bancarios_numero_conta()


def _simulacao_resultado(nova_analise: AnaliseInscricao, programa: Programa, parametro, inscricao: Inscricao) -> None:
    """Sugestões de simulação conforme o tipo do programa (transporte, trabalho, alimentação)."""
    sigla = programa.tipo_programa.sigla
    if sigla == Programa.TIPO_TRANSPORTE:
        _simulacao_transporte(nova_analise, parametro, inscricao.aluno)
    elif sigla == Programa.TIPO_TRABALHO:
        nova_analise.turno_escolhido = inscricao.sub_instance().get_turno_display()
    elif sigla == Programa.TIPO_ALIMENTACAO and parametro.exists():
        nova_analise.qtd_refeicoes_sugeridas = parametro[0].dias_sugeridos
        nova_analise.simulacao_resultado = parametro[0].dias_sugeridos


def _preencher_identificacao(nova_analise: AnaliseInscricao, inscricao: Inscricao, programa: Programa, edital_id: int, request):
    """Dados de identificação/renda da inscrição; devolve a caracterização do aluno."""
    aluno = inscricao.aluno
    caracterizacao = aluno.caracterizacao
    participacao_aberta = inscricao.get_participacao_aberta()
    nova_analise.edital_id = edital_id
    nova_analise.programa_id = programa.id
    nova_analise.tipo_programa = programa.tipo_programa
    nova_analise.tipo_programa_sigla = programa.tipo_programa.sigla
    nova_analise.inscricao = inscricao
    nova_analise.aluno = aluno
    nova_analise.id_do_aluno = aluno.id
    nova_analise.identificacao = aluno.__str__().split(' (')[0]
    nova_analise.matricula = aluno.matricula
    nova_analise.semestre_atual = _semestre_atual(aluno)
    nova_analise.cidade = aluno.cidade and aluno.cidade.__str__() or ''
    nova_analise.turno = aluno.turno.descricao
    nova_analise.situacao_documentacao = aluno.get_situacao_documentacao()
    nova_analise.documentacao_entregue = (aluno.documentada or aluno.data_documentacao) and True or False
    nova_analise.curso = aluno.curso_campus.__str__()
    nova_analise.situacao = aluno.situacao.__str__()
    nova_analise.participacoes = aluno.get_participacoes_abertas()
    nova_analise.id_da_participacao_atual = participacao_aberta.id if participacao_aberta else ''
    nova_analise.uo = programa.instituicao
    nova_analise.renda_bruta = caracterizacao.renda_bruta_familiar
    nova_analise.renda_per_capita = caracterizacao.get_faixa_renda_per_capita()
    nova_analise.valor_renda_per_capita = _valor_renda_per_capita(caracterizacao)
    nova_analise.qtd_pessoas = caracterizacao.qtd_pessoas_domicilio
    nova_analise.faixa_etaria = caracterizacao.get_faixa_etaria()
    nova_analise.gerada_por = request.user.get_vinculo()
    return caracterizacao


def _preencher_analise(nova_analise: AnaliseInscricao, inscricao: Inscricao, programa: Programa, edital_id: int, request) -> None:
    """Preenche e salva uma ``AnaliseInscricao`` a partir da inscrição/caracterização do aluno."""
    aluno = inscricao.aluno
    caracterizacao = _preencher_identificacao(nova_analise, inscricao, programa, edital_id, request)
    ultima_caracterizacao = _ultima_caracterizacao(aluno)
    _preencher_refeicoes(nova_analise, inscricao)
    nova_analise.situacao_trabalho = caracterizacao.responsavel_financeir_trabalho_situacao.descricao
    criterios_programa = CriterioSelecaoPrograma.objects.filter(gera_pontuacao=True, tipo_programa=programa.tipo_programa)
    pontuacao_trabalho = _pontuacao_trabalho(nova_analise, criterios_programa, caracterizacao, ultima_caracterizacao)
    nova_analise.zona_domiciliar = caracterizacao.tipo_area_residencial.descricao
    nova_analise.origem_escolar = _origem_escolar(aluno)
    _preencher_composicao_familiar(nova_analise, aluno)
    nova_analise.gasto_transporte = _gasto_transporte(inscricao, ultima_caracterizacao)
    nova_analise.recebe_bolsa = _recebe_bolsa(inscricao)
    nova_analise.cumpriu_toda_ch = _cumpriu_toda_ch(aluno)
    nova_analise.existe_reprovacao = _existe_reprovacao(aluno)
    nova_analise.beneficiario_programa_social = _sim_nao(caracterizacao.beneficiario_programa_social.exists())
    nova_analise.despesas_basicas_volumosas = _despesas_basicas_volumosas(caracterizacao)
    _pontuar_criterios(nova_analise, criterios_programa, caracterizacao, aluno, ultima_caracterizacao, pontuacao_trabalho)
    parametro = ParametroSelecaoPrograma.objects.filter(
        uo_id=programa.instituicao.id, tipo_programa_id=programa.tipo_programa.id, pontuacao_minima__lte=nova_analise.pontuacao_total
    ).order_by('-pontuacao_minima')
    _simulacao_resultado(nova_analise, programa, parametro, inscricao)
    nova_analise.save()


@task('Gerar Análise das Inscrições')
def gerar_analise_inscricoes(edital_id, programa_id, ordenacao, request, task=None):
    """Gera as análises das inscrições de um edital/programa para a tela de análise social."""
    inscricoes = Inscricao.objects.filter(periodo_inscricao__edital_id=edital_id, programa_id=programa_id).select_related(
        'aluno', 'aluno__curso_campus', 'aluno__caracterizacao'
    )
    programa = get_object_or_404(Programa, pk=programa_id)

    for inscricao in task.iterate(inscricoes.exclude(aluno__caracterizacao=None)):
        if AnaliseInscricao.objects.filter(aluno=inscricao.aluno, programa_id=programa_id, inscricao=inscricao).exists():
            continue
        _preencher_analise(AnaliseInscricao(), inscricao, programa, edital_id, request)

    task.finalize(
        'Análises geradas com sucesso.',
        f'/ae/analise_inscricoes/?edital={edital_id}&programa={programa_id}&ordenar={ordenacao}&analiseinscricoes_form=Aguarde...',
    )


@task('Recalcular Pontuação das Análises')
def recalcular_pontuacao(edital_id, programa_id, url, inscricao_id=None, task=None):
    inscricoes = Inscricao.objects.filter(periodo_inscricao__edital_id=edital_id, programa_id=programa_id).select_related(
        'aluno', 'aluno__curso_campus', 'aluno__caracterizacao'
    )
    if inscricao_id:
        inscricoes = inscricoes.filter(id=inscricao_id)
    programa = get_object_or_404(Programa, pk=programa_id)
    for nova_analise in task.iterate(
        AnaliseInscricao.objects.filter(inscricao__in=inscricoes.exclude(aluno__caracterizacao=None).values_list('id', flat=True))
    ):
        parametro = ParametroSelecaoPrograma.objects.filter(
            uo_id=programa.instituicao.id, tipo_programa_id=programa.tipo_programa.id, pontuacao_minima__lte=nova_analise.pontuacao_total
        ).order_by('-pontuacao_minima')
        if programa.tipo_programa.sigla == Programa.TIPO_TRANSPORTE:
            if parametro.exists():
                pct = parametro[0].porcentagem_sugerida
                nova_analise.qtd_refeicoes_sugeridas = pct
                nova_analise.simulacao_resultado = pct
                nova_analise.gasto_transporte_sugerido = (nova_analise.gasto_transporte * int(pct)) / 100
                nova_analise.valor_simulacao_resultado = (nova_analise.gasto_transporte * int(pct)) / 100
        elif programa.tipo_programa.sigla == Programa.TIPO_ALIMENTACAO:
            if parametro.exists():
                nova_analise.qtd_refeicoes_sugeridas = parametro[0].dias_sugeridos
                nova_analise.simulacao_resultado = parametro[0].dias_sugeridos
        nova_analise.save()

    task.finalize('Análises recalculadas com sucesso.', url)


@task('Imprimir Relatório de Refeições')
def imprimir_relatorio_refeicoes(demandas, data_inicial, data_final, request, task=None):
    task.count(demandas, demandas)
    uo = get_uo(request.user)
    topo = get_topo_pdf('Relatório de Refeições')
    servidor = request.user.get_relacionamento()
    info = [
        ['UO', uo],
        ['Servidor', servidor],
        ['Período', f'{data_inicial.strftime("%d/%m/%Y")} - {data_final.strftime("%d/%m/%Y")}'],
        ['Emitido em', datetime.datetime.now().strftime('%d/%m/%Y')],
    ]
    dados = [['Campus', 'Nome', 'Matrícula', 'Tipo de refeição', 'Data da refeição', 'Motivo do atendimento', 'Tipo de solicitação']]
    for registro in task.iterate(demandas):
        situacao = 'Agendado' if registro.agendamento else 'Participante'
        dados.append(
            [
                str(registro.campus),
                registro.aluno.pessoa_fisica.nome,
                registro.aluno.matricula,
                str(registro.demanda),
                registro.data.strftime('%d/%m/%Y'),
                registro.motivo_atendimento or registro.motivo or registro.motivo_inscricao or '',
                situacao,
            ]
        )
    tabela_info = relatorios.table(info, grid=0, w=[30, 160])
    tabela_dados = relatorios.table(dados, head=1, zebra=1, w=[18, 35, 28, 22, 20, 30, 25], count=1)
    body = [*topo, tabela_info, relatorios.space(8), tabela_dados, relatorios.space(8)]
    temp = tempfile.NamedTemporaryFile(suffix='.pdf', mode='w+b', delete=False)
    temp.close()
    relatorios.PdfReport(body=body, filename=temp.name).generate()
    task.finalize('Lista gerada com sucesso', '..', file_path=temp.name)


@task('Exportar Análises de Inscrições Deferidas/Indeferidas')
def exportar_analises_deferidas_pdf(edital_id, programa_id, tipo_id, request, task=None):
    queryset = AnaliseInscricao.objects.filter(programa_id=programa_id, edital_id=edital_id)
    if tipo_id == 1:
        descricao = 'Deferidas'
        analises = queryset.filter(inscricao__situacao_parecer=Inscricao.DEFERIDO).order_by('identificacao', 'id')
    else:
        descricao = 'Indeferidas'
        analises = queryset.filter(inscricao__situacao_parecer=Inscricao.INDEFERIDO).order_by('identificacao', 'id')
    task.count(analises, analises)
    uo = get_uo(request.user)
    topo = get_topo_pdf(f'Análises de Inscrições {descricao}')
    servidor = request.user.get_relacionamento()
    info = [
        ['UO', uo],
        ['Servidor', servidor],
        ['Edital', str(analises[0].edital)],
        ['Programa', str(analises[0].programa)],
        ['Servidor', servidor],
        ['Emitido em', datetime.datetime.now().strftime('%d/%m/%Y')],
    ]
    dados = [['Nome', 'Matrícula']]
    for inscricao in task.iterate(analises):
        dados.append(
            [
                inscricao.aluno.pessoa_fisica.nome,
                inscricao.aluno.matricula,
            ]
        )
    tabela_info = relatorios.table(info, grid=0, w=[30, 160])
    tabela_dados = relatorios.table(dados, head=1, zebra=1, w=[80, 50], count=1)
    body = [*topo, tabela_info, relatorios.space(8), tabela_dados, relatorios.space(8)]
    temp = tempfile.NamedTemporaryFile(suffix='.pdf', mode='w+b', delete=False)
    temp.close()
    relatorios.PdfReport(body=body, filename=temp.name).generate()
    task.finalize('Lista gerada com sucesso', '..', file_path=temp.name)


@task('Exportar Análises de Inscrições')
def exportar_analises_inscricoes_pdf(inscricoes, titulo, request, task=None):
    analises = AnaliseInscricao.objects.filter(inscricao__in=inscricoes.values_list('inscricao__id', flat=True)).order_by('identificacao', 'id')
    task.count(analises, analises)
    uo = get_uo(request.user)
    topo = get_topo_pdf(f'Análises de Inscrições {titulo}')
    servidor = request.user.get_relacionamento()
    info = [
        ['UO', uo],
        ['Servidor', servidor],
        ['Edital', str(analises[0].edital)],
        ['Programa', str(analises[0].programa)],
        ['Servidor', servidor],
        ['Emitido em', datetime.datetime.now().strftime('%d/%m/%Y')],
    ]
    dados = [['Nome', 'Matrícula']]
    for inscricao in task.iterate(analises):
        dados.append(
            [
                inscricao.aluno.pessoa_fisica.nome,
                inscricao.aluno.matricula,
            ]
        )
    tabela_info = relatorios.table(info, grid=0, w=[30, 160])
    tabela_dados = relatorios.table(dados, head=1, zebra=1, w=[80, 50], count=1)
    body = [*topo, tabela_info, relatorios.space(8), tabela_dados, relatorios.space(8)]
    temp = tempfile.NamedTemporaryFile(suffix='.pdf', mode='w+b', delete=False)
    temp.close()
    relatorios.PdfReport(body=body, filename=temp.name).generate()
    task.finalize('Lista gerada com sucesso', '..', file_path=temp.name)


@task('Exportar Relatório de Beneficiários SISPNAES para XLS')
def exportar_relatorio_sispnaes(ano, lista_cpfs, task=None):
    rows = [
        [
            'CPF',
            'Nome',
            'Data de nascimento',
            'E-mail',
            'Sexo',
            'Raça/Cor',
            'Etnia',
            'Nacionalidade',
            'Deficiência',
            'Transtornos Globais',
            'Superdotação',
            'Quantidade de membros da unidade familiar',
            'Faixa de renda familiar per capita',
            'Nível de ensino',
            'Curso',
        ]
    ]
    inicio = datetime.date(int(ano), 1, 1)
    fim = datetime.date(int(ano), 12, 31)
    if lista_cpfs:
        from django.db.models import F, CharField, Func

        last_occurrence_ids = Aluno.objects.values('pessoa_fisica__cpf').annotate(max_id=Max('id')).values_list('max_id', flat=True)
        alunos = (
            Aluno.objects.filter(id__in=last_occurrence_ids)
            .select_related('pessoa_fisica')
            .order_by('pessoa_fisica__cpf')
            .annotate(
                cleaned_cpf=Func(
                    F('pessoa_fisica__cpf'),
                    function='REGEXP_REPLACE',
                    template="REGEXP_REPLACE(%(expressions)s, '[^0-9]', '', 'g')",
                    output_field=CharField(),
                ),
                cpf_len=Length('pessoa_fisica__cpf'),
            )
            .exclude(cpf_len__lt=14)
            .filter(cleaned_cpf__in=lista_cpfs)
            .distinct('pessoa_fisica__cpf')
        )
    else:
        alunos_participacoes = Aluno.objects.filter(
            id__in=Participacao.objects.filter(
                Q(programa__tipo_programa__sigla__in=['PAS', 'TRB']) | Q(programa__tipo_programa__titulo='Auxílio Moradia')
            )
            .filter(
                Q(data_termino__gte=inicio, data_inicio__lt=fim) | Q(data_termino__isnull=True, data_inicio__lte=fim),
            )
            .values_list('aluno', flat=True)
        ).order_by('pessoa_fisica__nome')

        alunos_auxilios = Aluno.objects.filter(
            id__in=SolicitacaoAuxilioAluno.objects.filter(deferida=True, data_solicitacao__year=int(ano)).values_list('aluno', flat=True)
        )

        alunos = alunos_participacoes | alunos_auxilios

    for aluno in task.iterate(alunos):
        pessoa_fisica = aluno.pessoa_fisica
        dt_nasc = aluno.pessoa_fisica.nascimento_data
        email = aluno.email_notificacao
        if not dt_nasc:
            outra_dt = (
                Aluno.objects.filter(pessoa_fisica__cpf=aluno.pessoa_fisica.cpf)
                .exclude(pessoa_fisica__nascimento_data=None)
                .only('pessoa_fisica__nascimento_data')
                .last()
            )
            dt_nasc = outra_dt and outra_dt.pessoa_fisica.nascimento_data
        caracterizacao = Caracterizacao.objects.filter(aluno=aluno).last()
        sexo = 3
        if pessoa_fisica.sexo:
            if pessoa_fisica.sexo == 'M':
                sexo = 1
            elif pessoa_fisica.sexo == 'F':
                sexo = 2
        raca = 6
        if aluno.raca:
            if aluno.raca.descricao == 'Branca':
                raca = 1
            elif aluno.raca.descricao == 'Preta':
                raca = 2
            elif aluno.raca.descricao == 'Parda':
                raca = 3
            elif aluno.raca.descricao == 'Amarela':
                raca = 4
            elif aluno.raca.descricao == 'Indígena':
                raca = 5
        etnia = 4
        if caracterizacao:
            if caracterizacao.tipo_area_residencial:
                if caracterizacao.tipo_area_residencial.descricao == 'Comunidade Indígena':
                    etnia = 1
                elif caracterizacao.tipo_area_residencial.descricao == 'Comunidade Quilombola':
                    etnia = 2
                elif caracterizacao.tipo_area_residencial.descricao == 'Comunidade Tradicional':
                    etnia = 3
        nacionalidade = 1
        if pessoa_fisica.nacionalidade:
            from rh.enums import Nacionalidade

            if int(pessoa_fisica.nacionalidade) == Nacionalidade.BRASILEIRO_NATO:
                nacionalidade = 1
            elif int(pessoa_fisica.nacionalidade) == Nacionalidade.BRASILEIRO_NATZ or int(pessoa_fisica.nacionalidade) == Nacionalidade.EQUIPARADO:
                nacionalidade = 2
            elif int(pessoa_fisica.nacionalidade) == Nacionalidade.ESTRANGEIRO:
                nacionalidade = 3

        deficiencia = 2
        superdotacao = 2
        if caracterizacao and caracterizacao.necessidade_especial.exists():
            for item in caracterizacao.necessidade_especial.all():
                if item.descricao in ['Auditiva', 'Física', 'Mental', 'Visual', 'Múltipla', 'Condutas Típicas']:
                    deficiencia = 1
                elif item.descricao == 'Superdotado/Altas habilidades':
                    superdotacao = 1

        # valores que não temos no SUAP
        transtornos_globais = 2
        # -----------

        qtd_pessoas_familia = caracterizacao and caracterizacao.qtd_pessoas_domicilio or ''
        # renda_bruta_familiar = caracterizacao.renda_bruta_familiar
        # renda_per_capita = caracterizacao.renda_per_capita

        sm = 4
        if caracterizacao and caracterizacao.qtd_pessoas_domicilio > 0:
            sm = Decimal(Configuracao.get_valor_por_chave('comum', 'salario_minimo'))
            renda = caracterizacao.renda_bruta_familiar / caracterizacao.qtd_pessoas_domicilio
            if renda <= sm / 2:
                sm = 1
            elif renda <= sm:
                sm = 2
            elif renda <= Decimal('1.5') * sm:
                sm = 3
            elif renda <= Decimal('2.5') * sm:
                sm = 5
            elif renda <= Decimal('3.5') * sm:
                sm = 6
            elif renda > Decimal('3.5') * sm:
                sm = 7

        nivel = ''
        # O campo Etapa da formação deve ser preenchido com um dos seguintes valores:
        # 16( Qualificação Profissional (FIC) - PROEJA - Concomitante ),
        # 19( Técnico - PROEJA - Concomitante ),
        # 23( Qualificação Profissional (FIC) - PROEJA - Integrado )
        modalidade_propria = aluno.curso_campus.modalidade_id if aluno.curso_campus else None
        codigo_emec = aluno.curso_campus.codigo_emec if aluno.curso_campus else None

        todas_matriculas = (
            Aluno.objects.filter(pessoa_fisica__cpf=pessoa_fisica.cpf, situacao__ativo=True)
            .exclude(curso_campus=None)
            .exclude(curso_campus__modalidade=None)
        )
        modalidades_ativas = set(todas_matriculas.values_list('curso_campus__modalidade_id', flat=True))

        # a ordem de verificação foi previamente definida como um requisito para definir o nível com mais prioridade
        NIVEIS_POR_MODALIDADE = (
            (Modalidade.INTEGRADO, 18),
            (Modalidade.ENSINO_MEDIO, 1),
            (Modalidade.SUBSEQUENTE, 21),
            (Modalidade.CONCOMITANTE, 17),
            (Modalidade.INTEGRADO_EJA, 20),
            (Modalidade.FIC_INTEGRADO_EJA, 20),
            (Modalidade.LICENCIATURA, 13),
            (Modalidade.LICENCIATURA_DUPLA_HABILITACAO, 13),
            (Modalidade.BACHARELADO, 7),
            (Modalidade.ENGENHARIA, 7),
            (Modalidade.TECNOLOGIA, 22),
            (Modalidade.DOUTORADO, 5),
            (Modalidade.MESTRADO, 4),
            (Modalidade.ESPECIALIZACAO, 3),
            (Modalidade.FIC, 15),
            (Modalidade.FIC_MENOS, 15),
        )
        for modalidade, nivel_ensino in NIVEIS_POR_MODALIDADE:
            if modalidade_propria == modalidade:
                nivel = nivel_ensino
                break
            elif modalidade in modalidades_ativas:
                nivel = nivel_ensino
                codigo_emec = todas_matriculas.filter(curso_campus__modalidade_id=modalidade).latest('id').curso_campus.codigo_emec
                break

        row = [
            format_(pessoa_fisica.cpf),
            format_(pessoa_fisica.nome),
            format_(dt_nasc),
            format_(email),
            format_(sexo),
            format_(raca),
            format_(etnia),
            format_(nacionalidade),
            format_(deficiencia),
            format_(transtornos_globais),
            format_(superdotacao),
            format_(qtd_pessoas_familia),
            format_(sm),
            format_(nivel),
            format_(codigo_emec),
        ]
        rows.append(row)
    return XlsResponse(rows, processo=task)
