import os
from collections import OrderedDict
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage
from django.db.models import Count
from django.db.models.aggregates import Sum
from django.dispatch import receiver
from django.shortcuts import get_object_or_404
from django_tables2.columns.linkcolumn import LinkColumn
from django_tables2.utils import Accessor

from comum.models import Ano, Log
from contracheques.forms import (
    AbsenteismoForm,
    BrutoLiquidoPorCampusFactory,
    CampusAnoForm,
    ConsultaContraChequeForm,
    GetImportarArquivoContraChequeForm,
    PeriodoAnoUOContraChequeFactory,
    PeriodoMesAnoRelatorioDGPFactory,
    RubricaPorCampusAgrupadasFactory,
    RubricaPorCampusFactory,
    TipologiaCargoPorFaixaForm,
    TitulacoesServidoresPorContracheques,
)
from contracheques.models import AgrupamentoRubricas, ContraCheque, ContraChequeRubrica, Rubrica
from djtools import layout, tasks
from djtools.choices import Meses
from djtools.html.graficos import LineChart, PieChart
from djtools.tables import get_table
from djtools.utils import CsvResponse, adicionar_mes, get_age, group_required, httprr, permission_required, render, render_to_string, rtr
from rh.models import Funcao, Servidor, ServidorAfastamento, ServidorFuncaoHistorico, Situacao, UnidadeOrganizacional
from rh.views import rh_servidor_view_tab


@layout.atribuidos_a_meus_grupos()
def index_atribuidos_a_meus_grupos(request):
    pendencias = []

    if not request.user.is_superuser and (request.user.has_perm('rh.eh_rh_sistemico') or request.user.has_perm('rh.eh_rh_campus')):
        if ContraCheque.find_servidor_com_titulacao_dispar():
            pendencias.append({'url': '/contracheques/servidores_com_titulacao_dispar/', 'titulo': 'Há titulações <strong>inconsistentes</strong>.'})

    return pendencias


@rtr()
@permission_required('rh.pode_ver_relatorios_rh')
def relatorio_absenteismo(request):
    title = 'Relatório de Absenteísmo'

    form = AbsenteismoForm(request.POST or None)
    if form.is_valid():
        ano = int(form.cleaned_data['ano'])
        campus = form.cleaned_data['campus']

        servidor_afastamentos = (
            ServidorAfastamento.objects.exclude_afastamentos_pgd().filter(data_inicio__year=ano, cancelado=False)
            | ServidorAfastamento.objects.exclude_afastamentos_pgd().filter(data_termino__year=ano, cancelado=False)
            | ServidorAfastamento.objects.exclude_afastamentos_pgd().filter(
                data_inicio__lt=date(ano, 1, 1), data_termino__gt=date(ano, 12, 31), cancelado=False
            )
        )
        #       Filtrar por grupos ocorrencias
        #        servidor_ocorrencias = servidor_ocorrencias.filter(ocorrencia__grupo_ocorrencia__nome__unaccent__icontains="AFASTAMENTO")

        #       Inicializando dicts()
        servidores_situacao_mes = {}
        servidores_situacao = {}
        indice = {}
        quantidade_faltas = {}
        quantidade_servidores = {}
        contracheques_todos = (
            ContraCheque.objects.ativos()
            .fita_espelho()
            .filter(ano__ano=ano, servidor_situacao__codigo__in=Situacao.situacoes_servidores_de_carreira())
        )
        if campus:
            campus = UnidadeOrganizacional.objects.suap().get(pk=form.cleaned_data['campus'])
            servidor_afastamentos = servidor_afastamentos.filter(servidor__setor__uo=campus)
            contracheques_todos = contracheques_todos.filter(servidor_setor_lotacao__uo__sigla=campus.sigla)
        for situacao_codigo in Situacao.situacoes_servidores_de_carreira():
            situacao = Situacao.objects.get(codigo=situacao_codigo).nome
            servidores_situacao[situacao] = (
                contracheques_todos.filter(servidor_situacao__codigo=situacao_codigo).values_list('servidor').distinct().count()
            )

        for mes in range(1, 13):
            primeiro_dia_mes = date(ano, mes, 1)
            ultimo_dia_mes = adicionar_mes(date(ano, mes, 1), 1) - timedelta(days=1)

            contracheques_mes = contracheques_todos.filter(mes=mes)

            servidor_afastamentos_mes = servidor_afastamentos.filter(
                servidor__pk__in=contracheques_mes.values_list('servidor__pk', flat=True),
                data_inicio__lte=ultimo_dia_mes,
                data_termino__gte=primeiro_dia_mes,
            )

            for situacao_codigo in Situacao.situacoes_servidores_de_carreira():
                situacao = Situacao.objects.get(codigo=situacao_codigo).nome
                contracheque_situacao = contracheques_mes.filter(servidor_situacao__codigo=situacao_codigo)

                if mes not in servidores_situacao_mes:
                    servidores_situacao_mes[mes] = {}
                servidores_situacao_mes[mes][situacao] = contracheque_situacao.values_list('servidor').distinct().count()

            # servidor_ocorrencias_mes_situacao = servidor_ocorrencias_mes.filter(servidor__situacao__codigo = situacao_codigo).count()
            total_mes = contracheques_mes.values_list('servidor').distinct().count()
            quantidade_faltas_mes = 0
            for servidor_afast in servidor_afastamentos_mes:
                if not servidor_afast.data_termino:
                    quantidade_faltas_mes += 1

                elif servidor_afast.data_inicio < primeiro_dia_mes and servidor_afast.data_termino > ultimo_dia_mes:
                    quantidade_faltas_mes += (ultimo_dia_mes - primeiro_dia_mes).days + 1

                elif servidor_afast.data_inicio < primeiro_dia_mes:
                    quantidade_faltas_mes += (servidor_afast.data_termino - primeiro_dia_mes).days + 1

                elif servidor_afast.data_termino > ultimo_dia_mes:
                    quantidade_faltas_mes += (ultimo_dia_mes - servidor_afast.data_inicio).days + 1

                else:
                    quantidade_faltas_mes += (servidor_afast.data_termino - servidor_afast.data_inicio).days + 1
            quantidade_servidores[mes] = total_mes
            quantidade_faltas[mes] = quantidade_faltas_mes
            indice[mes] = round((quantidade_faltas_mes * 100.0) / ((total_mes or 1) * (ultimo_dia_mes - primeiro_dia_mes).days), 2)

        # Total
        total = contracheques_todos.values_list('servidor').distinct().count()

        data_inicial_ano = date(ano, 1, 1)
        data_final_ano = date(ano, 12, 31)

        qtd_faltas = 0
        for servidor_afast in servidor_afastamentos:
            if not servidor_afast.data_termino:
                qtd_faltas += 1

            elif servidor_afast.data_inicio < data_inicial_ano and servidor_afast.data_termino > data_final_ano:
                qtd_faltas += (data_final_ano - data_inicial_ano).days

            elif servidor_afast.data_inicio < data_inicial_ano:
                qtd_faltas += (servidor_afast.data_termino - data_inicial_ano).days

            elif servidor_afast.data_termino > data_final_ano:
                qtd_faltas += (data_final_ano - servidor_afast.data_inicio).days

            else:
                qtd_faltas += (servidor_afast.data_termino - servidor_afast.data_inicio).days

        quantidade_servidores['total'] = total
        quantidade_faltas['total'] = qtd_faltas
        indice['total'] = round((qtd_faltas * 100.0) / ((total or 1) * 365), 2)

    return locals()


@rtr()
@permission_required('rh.pode_ver_relatorios_rh, rh.eh_rh_sistemico, comum.is_reitor, comum.is_pro_reitor, comum.is_diretor_geral')
def ingressos_egressos_por_cargos_uj(request):
    form = CampusAnoForm(request.POST or None)
    title = 'Força de Trabalho da Unidade Jurisdicionada'
    if form.is_valid():
        ano = int(form.cleaned_data['ano'])
        campus = form.cleaned_data['campus']

        #       Todos os servidores ocorrencias do ano escolhido

        contracheques_todos = ContraCheque.objects.ativos().fita_espelho().filter(ano__ano=ano, pensionista__isnull=True)
        if campus:
            campus = UnidadeOrganizacional.objects.suap().get(pk=form.cleaned_data['campus'])
            contracheques_todos = contracheques_todos.filter(servidor_setor_lotacao__uo__sigla=campus.sigla)
        if not contracheques_todos:
            return locals()
        mes = contracheques_todos.latest('mes')
        contracheques_mes = contracheques_todos.filter(mes=mes.mes)

        servidores_carreira_vinculada_ao_orgao = (
            contracheques_todos.filter(servidor_situacao__codigo__in=Situacao.situacoes_servidores_de_carreira_vinculada_ao_orgao())
            .values_list('servidor__pk', flat=True)
            .distinct()
        )
        quantidade_servidores_carreira_vinculada_ao_orgao = (
            contracheques_mes.filter(servidor_situacao__codigo__in=Situacao.situacoes_servidores_de_carreira_vinculada_ao_orgao())
            .values_list('servidor__pk', flat=True)
            .distinct()
            .count()
        )
        quantidade_servidores_carreira_vinculada_ao_orgao_ingressos = Servidor.objects.filter(
            pk__in=servidores_carreira_vinculada_ao_orgao,
            data_inicio_exercicio_no_cargo__gte=date(ano, 1, 1),
            data_inicio_exercicio_no_cargo__lte=date(ano, 12, 31),
        ).count()
        quantidade_servidores_carreira_vinculada_ao_orgao_egressos = Servidor.objects.filter(
            pk__in=servidores_carreira_vinculada_ao_orgao,
            data_fim_servico_na_instituicao__gte=date(ano, 1, 1),
            data_fim_servico_na_instituicao__lte=date(ano, 12, 31),
        ).count()

        servidores_descentralizados_ano = contracheques_todos.filter(servidor_situacao__codigo=Situacao.EXERC_DESCENT_CARREI).values_list(
            'servidor__pk', flat=True
        )
        quantidade_servidores_descentralizados = (
            contracheques_mes.filter(servidor_situacao__codigo=Situacao.EXERC_DESCENT_CARREI)
            .values_list('servidor__pk', flat=True)
            .distinct()
            .count()
        )
        quantidade_servidores_descentralizados_ingressos = Servidor.objects.filter(
            pk__in=servidores_descentralizados_ano,
            data_inicio_exercicio_no_cargo__gte=date(ano, 1, 1),
            data_inicio_exercicio_no_cargo__lte=date(ano, 12, 31),
        ).count()
        quantidade_servidores_descentralizados_egressos = Servidor.objects.filter(
            pk__in=servidores_descentralizados_ano,
            data_fim_servico_na_instituicao__gte=date(ano, 1, 1),
            data_fim_servico_na_instituicao__lte=date(ano, 12, 31),
        ).count()

        servidores_exercicio_provisorio_ano = contracheques_todos.filter(
            servidor_situacao__codigo__in=Situacao.situacoes_carreira_em_exercicio_provisorio()
        ).values_list('servidor__pk', flat=True)
        quantidade_servidores_exercicio_provisorio = (
            contracheques_mes.filter(servidor_situacao__codigo__in=Situacao.situacoes_carreira_em_exercicio_provisorio())
            .values_list('servidor__pk', flat=True)
            .distinct()
            .count()
        )
        quantidade_servidores_exercicio_provisorio_ingressos = Servidor.objects.filter(
            pk__in=servidores_exercicio_provisorio_ano,
            data_inicio_exercicio_no_cargo__gte=date(ano, 1, 1),
            data_inicio_exercicio_no_cargo__lte=date(ano, 12, 31),
        ).count()
        quantidade_servidores_exercicio_provisorio_egressos = Servidor.objects.filter(
            pk__in=servidores_exercicio_provisorio_ano,
            data_fim_servico_na_instituicao__gte=date(ano, 1, 1),
            data_fim_servico_na_instituicao__lte=date(ano, 12, 31),
        ).count()

        servidores_requisitados_ano = contracheques_todos.filter(servidor_situacao__codigo=Situacao.REQ_DE_OUTROS_ORGAOS).values_list(
            'servidor__pk', flat=True
        )
        quantidade_servidores_requisitados = (
            contracheques_mes.filter(servidor_situacao__codigo=Situacao.REQ_DE_OUTROS_ORGAOS)
            .values_list('servidor__pk', flat=True)
            .distinct()
            .count()
        )
        quantidade_servidores_requisitados_ingressos = Servidor.objects.filter(
            pk__in=servidores_requisitados_ano,
            data_inicio_exercicio_no_cargo__gte=date(ano, 1, 1),
            data_inicio_exercicio_no_cargo__lte=date(ano, 12, 31),
        ).count()
        quantidade_servidores_requisitados_egressos = Servidor.objects.filter(
            pk__in=servidores_requisitados_ano,
            data_fim_servico_na_instituicao__gte=date(ano, 1, 1),
            data_fim_servico_na_instituicao__lte=date(ano, 12, 31),
        ).count()

        servidores_temporarios_ano = contracheques_todos.filter(servidor_situacao__codigo__in=Situacao.SITUACOES_TEMPORARIOS).values_list(
            'servidor__pk', flat=True
        )
        quantidade_servidores_temporarios = (
            contracheques_mes.filter(servidor_situacao__codigo__in=Situacao.SITUACOES_TEMPORARIOS)
            .values_list('servidor__pk', flat=True)
            .distinct()
            .count()
        )
        quantidade_servidores_temporarios_ingressos = Servidor.objects.filter(
            pk__in=servidores_temporarios_ano,
            data_inicio_exercicio_no_cargo__gte=date(ano, 1, 1),
            data_inicio_exercicio_no_cargo__lte=date(ano, 12, 31),
        ).count()
        quantidade_servidores_temporarios_egressos = Servidor.objects.filter(
            pk__in=servidores_temporarios_ano,
            data_fim_servico_na_instituicao__gte=date(ano, 1, 1),
            data_fim_servico_na_instituicao__lte=date(ano, 12, 31),
        ).count()

        servidores_sem_vinculo_ano = contracheques_todos.filter(
            servidor_situacao__codigo__in=Situacao.situacoes_sem_vinculo_com_administracao_publica()
        ).values_list('servidor__pk', flat=True)
        quantidade_servidores_sem_vinculo = (
            contracheques_mes.filter(servidor_situacao__codigo__in=Situacao.situacoes_sem_vinculo_com_administracao_publica())
            .values_list('servidor__pk', flat=True)
            .distinct()
            .count()
        )
        quantidade_servidores_sem_vinculo_ingressos = Servidor.objects.filter(
            pk__in=servidores_sem_vinculo_ano,
            data_inicio_exercicio_no_cargo__gte=date(ano, 1, 1),
            data_inicio_exercicio_no_cargo__lte=date(ano, 12, 31),
        ).count()
        quantidade_servidores_sem_vinculo_egressos = Servidor.objects.filter(
            pk__in=servidores_sem_vinculo_ano,
            data_fim_servico_na_instituicao__gte=date(ano, 1, 1),
            data_fim_servico_na_instituicao__lte=date(ano, 12, 31),
        ).count()

        quantidade_cargos_efetivos = (
            quantidade_servidores_carreira_vinculada_ao_orgao
            + quantidade_servidores_descentralizados
            + quantidade_servidores_exercicio_provisorio
            + quantidade_servidores_requisitados
        )
        quantidade_ingressos_cargos_efetivos = (
            quantidade_servidores_carreira_vinculada_ao_orgao_ingressos
            + quantidade_servidores_descentralizados_ingressos
            + quantidade_servidores_exercicio_provisorio_ingressos
            + quantidade_servidores_requisitados_ingressos
        )
        quantidade_egressos_cargos_efetivos = (
            quantidade_servidores_carreira_vinculada_ao_orgao_egressos
            + quantidade_servidores_descentralizados_egressos
            + quantidade_servidores_exercicio_provisorio_egressos
            + quantidade_servidores_requisitados_egressos
        )

        resultados = []
        resultados.append(
            [
                '1. Servidores em Cargos Efetivos (1.1 + 1.2)',
                '',
                quantidade_cargos_efetivos,
                quantidade_ingressos_cargos_efetivos,
                quantidade_egressos_cargos_efetivos,
            ]
        )
        resultados.append(['1.1 Membros de poder e agentes políticos ', '-', '-', '-', '-'])
        resultados.append(
            [
                '1.2 Servidores de Carreira (1.2.1 + 1.2.2 +1.2.3 + 1.2.4)',
                '-',
                quantidade_cargos_efetivos,
                quantidade_ingressos_cargos_efetivos,
                quantidade_servidores_carreira_vinculada_ao_orgao_egressos,
            ]
        )
        resultados.append(
            [
                '1.2.1 Servidores de carreira vinculada ao órgão',
                '-',
                quantidade_servidores_carreira_vinculada_ao_orgao,
                quantidade_servidores_carreira_vinculada_ao_orgao_ingressos,
                quantidade_servidores_carreira_vinculada_ao_orgao_egressos,
            ]
        )
        resultados.append(
            [
                '1.2.2 Servidores de carreira em exercício descentralizado ',
                '-',
                quantidade_servidores_descentralizados,
                quantidade_servidores_descentralizados_ingressos,
                quantidade_servidores_descentralizados_egressos,
            ]
        )
        resultados.append(
            [
                '1.2.3 Servidores de carreira em exercício provisório ',
                '-',
                quantidade_servidores_exercicio_provisorio,
                quantidade_servidores_exercicio_provisorio_ingressos,
                quantidade_servidores_exercicio_provisorio_egressos,
            ]
        )
        resultados.append(
            [
                '1.2.4 Servidores requisitados de outros órgãos ',
                '-',
                quantidade_servidores_requisitados,
                quantidade_servidores_requisitados_ingressos,
                quantidade_servidores_requisitados_egressos,
            ]
        )
        resultados.append(
            [
                '2. Servidores com Contratos Temporários ',
                '-',
                quantidade_servidores_temporarios,
                quantidade_servidores_temporarios_ingressos,
                quantidade_servidores_temporarios_egressos,
            ]
        )
        resultados.append(
            [
                '3. Servidores sem Vínculo com a Administração Pública ',
                '-',
                quantidade_servidores_sem_vinculo,
                quantidade_servidores_sem_vinculo_ingressos,
                quantidade_servidores_sem_vinculo_egressos,
            ]
        )
        resultados.append(
            [
                '4. Total de Servidores (1+2+3) ',
                '-',
                quantidade_cargos_efetivos + quantidade_servidores_temporarios + quantidade_servidores_sem_vinculo,
                quantidade_ingressos_cargos_efetivos + quantidade_servidores_temporarios_ingressos + quantidade_servidores_sem_vinculo_ingressos,
                quantidade_egressos_cargos_efetivos + quantidade_servidores_temporarios_egressos + quantidade_servidores_sem_vinculo_egressos,
            ]
        )
    return locals()


@rtr()
@permission_required('rh.pode_ver_relatorios_rh', 'rh.eh_rh_sistemico, comum.is_reitor, comum.is_pro_reitor, comum.is_diretor_geral')
def distribuicao_lotacao_por_area(request):
    form = CampusAnoForm(request.POST or None)
    title = 'Distribuição de  Lotação Efetiva por Área'
    if form.is_valid():
        ano = int(form.cleaned_data['ano'])
        campus = form.cleaned_data['campus']
        #       Todos os servidores ocorrencias do ano escolhido

        contracheques_todos = ContraCheque.objects.ativos().fita_espelho().filter(ano__ano=ano, pensionista__isnull=True)
        if campus:
            campus = UnidadeOrganizacional.objects.suap().get(pk=form.cleaned_data['campus'])
            contracheques_todos = contracheques_todos.filter(servidor_setor_lotacao__uo__equivalente=campus)

        if not contracheques_todos:
            return locals()
        mes = contracheques_todos.latest('mes')
        contracheques_mes = contracheques_todos.filter(mes=mes.mes)

        servidores_carreira_vinculada_ao_orgao = (
            contracheques_mes.filter(servidor_situacao__codigo__in=Situacao.situacoes_servidores_de_carreira_vinculada_ao_orgao())
            .values_list('servidor__pk', flat=True)
            .distinct()
        )
        quantidade_servidores_carreira_vinculada_ao_orgao_area_meio = (
            Servidor.objects.filter(pk__in=servidores_carreira_vinculada_ao_orgao).exclude(eh_docente=True).count()
        )
        quantidade_servidores_carreira_vinculada_ao_orgao_area_fim = Servidor.objects.filter(
            pk__in=servidores_carreira_vinculada_ao_orgao, eh_docente=True
        ).count()

        servidores_descentralizados_ano = contracheques_mes.filter(servidor_situacao__codigo=Situacao.EXERC_DESCENT_CARREI).values_list(
            'servidor__pk', flat=True
        )
        quantidade_servidores_descentralizados_area_meio = (
            Servidor.objects.filter(pk__in=servidores_descentralizados_ano).exclude(eh_docente=True).count()
        )
        quantidade_servidores_descentralizados_area_fim = Servidor.objects.filter(pk__in=servidores_descentralizados_ano, eh_docente=True).count()

        servidores_exercicio_provisorio_ano = contracheques_mes.filter(
            servidor_situacao__codigo__in=Situacao.situacoes_carreira_em_exercicio_provisorio()
        ).values_list('servidor__pk', flat=True)
        quantidade_servidores_exercicio_provisorio_area_meio = (
            Servidor.objects.filter(pk__in=servidores_exercicio_provisorio_ano).exclude(eh_docente=True).count()
        )
        quantidade_servidores_exercicio_provisorio_area_fim = Servidor.objects.filter(
            pk__in=servidores_exercicio_provisorio_ano, eh_docente=True
        ).count()

        servidores_requisitados_ano = contracheques_mes.filter(servidor_situacao__codigo=Situacao.REQ_DE_OUTROS_ORGAOS).values_list(
            'servidor__pk', flat=True
        )
        quantidade_servidores_requisitados_area_meio = Servidor.objects.filter(pk__in=servidores_requisitados_ano).exclude(eh_docente=True).count()
        quantidade_servidores_requisitados_area_fim = Servidor.objects.filter(pk__in=servidores_requisitados_ano, eh_docente=True).count()

        servidores_temporarios_ano = contracheques_mes.filter(servidor_situacao__codigo__in=Situacao.SITUACOES_TEMPORARIOS).values_list(
            'servidor__pk', flat=True
        )
        quantidade_servidores_temporarios_area_meio = Servidor.objects.filter(pk__in=servidores_temporarios_ano).exclude(eh_docente=True).count()
        quantidade_servidores_temporarios_area_fim = Servidor.objects.filter(pk__in=servidores_temporarios_ano, eh_docente=True).count()

        servidores_sem_vinculo_ano = contracheques_mes.filter(
            servidor_situacao__codigo__in=Situacao.situacoes_sem_vinculo_com_administracao_publica()
        ).values_list('servidor__pk', flat=True)
        quantidade_servidores_sem_vinculo_area_meio = Servidor.objects.filter(pk__in=servidores_sem_vinculo_ano).exclude(eh_docente=True).count()
        quantidade_servidores_sem_vinculo_area_fim = Servidor.objects.filter(pk__in=servidores_sem_vinculo_ano, eh_docente=True).count()

        quantidade_cargos_efetivos_area_meio = (
            quantidade_servidores_carreira_vinculada_ao_orgao_area_meio
            + quantidade_servidores_descentralizados_area_meio
            + quantidade_servidores_exercicio_provisorio_area_meio
            + quantidade_servidores_requisitados_area_meio
        )
        quantidade_cargos_efetivos_area_fim = (
            quantidade_servidores_carreira_vinculada_ao_orgao_area_fim
            + quantidade_servidores_descentralizados_area_fim
            + quantidade_servidores_exercicio_provisorio_area_fim
            + quantidade_servidores_requisitados_area_fim
        )

        resultados = []
        resultados.append(['1. Servidores de Carreira (1.1)', quantidade_cargos_efetivos_area_meio, quantidade_cargos_efetivos_area_fim])
        resultados.append(
            [
                '1.1 Servidores de Carreira (1.1.1 + 1.1.2 +1.1.3 + 1.1.4)',
                quantidade_cargos_efetivos_area_meio,
                quantidade_cargos_efetivos_area_fim,
            ]
        )
        resultados.append(
            [
                '1.1.1 Servidores de carreira vinculada ao órgão',
                quantidade_servidores_carreira_vinculada_ao_orgao_area_meio,
                quantidade_servidores_carreira_vinculada_ao_orgao_area_fim,
            ]
        )
        resultados.append(
            [
                '1.1.2 Servidores de carreira em exercício descentralizado ',
                quantidade_servidores_descentralizados_area_meio,
                quantidade_servidores_descentralizados_area_fim,
            ]
        )
        resultados.append(
            [
                '1.1.3 Servidores de carreira em exercício provisório ',
                quantidade_servidores_exercicio_provisorio_area_meio,
                quantidade_servidores_exercicio_provisorio_area_fim,
            ]
        )
        resultados.append(
            [
                '1.1.4 Servidores requisitados de outros órgãos ',
                quantidade_servidores_requisitados_area_meio,
                quantidade_servidores_requisitados_area_fim,
            ]
        )
        resultados.append(
            [
                '2. Servidores com Contratos Temporários ',
                quantidade_servidores_temporarios_area_meio,
                quantidade_servidores_temporarios_area_fim,
            ]
        )
        resultados.append(
            [
                '3. Servidores sem Vínculo com a Administração Pública ',
                quantidade_servidores_sem_vinculo_area_meio,
                quantidade_servidores_sem_vinculo_area_fim,
            ]
        )
        resultados.append(
            [
                '4. Total de Servidores (1+2+3) ',
                quantidade_cargos_efetivos_area_meio + quantidade_servidores_temporarios_area_meio + quantidade_servidores_sem_vinculo_area_meio,
                quantidade_cargos_efetivos_area_fim + quantidade_servidores_temporarios_area_fim + quantidade_servidores_sem_vinculo_area_fim,
            ]
        )
    return locals()


@rtr()
@permission_required('rh.pode_ver_relatorios_rh', 'rh.eh_rh_sistemico, comum.is_reitor, comum.is_pro_reitor, comum.is_diretor_geral')
def ingressos_egressos_por_cargos_funcoes_uj(request):
    form = CampusAnoForm(request.POST or None)
    title = 'Detalhamento da estrutura de cargos em comissão e funções gratificadas da UJ'
    if form.is_valid():
        ano = int(form.cleaned_data['ano'])
        campus = form.cleaned_data['campus']

        contracheques_todos = ContraCheque.objects.ativos().fita_espelho().filter(ano__ano=ano, pensionista__isnull=True)
        if campus:
            campus = UnidadeOrganizacional.objects.suap().get(pk=form.cleaned_data['campus'])
            contracheques_todos = contracheques_todos.filter(servidor_setor_lotacao__uo__equivalente=campus)
        if not contracheques_todos:
            return locals()
        mes = contracheques_todos.latest('mes')
        contracheques_mes = contracheques_todos.filter(mes=mes.mes)
        primeiro_dia_mes = date(ano, mes.mes, 1)
        ultimo_dia_mes = adicionar_mes(date(ano, mes.mes, 1), 1) - timedelta(days=1)

        servidores_ultimo_mes = Servidor.objects.filter(pk__in=contracheques_mes.values_list('servidor', flat=True))
        #       Servidores de Carreira Vínculada = Ativos Permanentes e Cedidos
        contracheques_servidores_carreira_vinculada_ao_orgao = contracheques_todos.filter(
            servidor_situacao__codigo__in=Situacao.situacoes_servidores_de_carreira_vinculada_ao_orgao()
        )
        contracheques_servidores_carreira_vinculada_ao_orgao_mes = contracheques_mes.filter(
            servidor_situacao__codigo__in=Situacao.situacoes_servidores_de_carreira_vinculada_ao_orgao()
        )

        servidores_cd_carreira_vinculada_ao_orgao = Servidor.objects.filter(
            pk__in=contracheques_servidores_carreira_vinculada_ao_orgao_mes.values_list('servidor__pk')
        ).filter(
            servidorfuncaohistorico__funcao__codigo=Funcao.CODIGO_CD,
            servidorfuncaohistorico__data_inicio_funcao__lte=date(ano, 12, 31),
            servidorfuncaohistorico__data_fim_funcao__gte=date(ano, 12, 31),
        ) | Servidor.objects.filter(pk__in=contracheques_servidores_carreira_vinculada_ao_orgao_mes.values_list('servidor__pk')).filter(
            servidorfuncaohistorico__funcao__codigo=Funcao.CODIGO_CD,
            servidorfuncaohistorico__data_inicio_funcao__lte=date(ano, 12, 31),
            servidorfuncaohistorico__data_fim_funcao__isnull=True,
        )

        servidores_fg_carreira_vinculada_ao_orgao = Servidor.objects.filter(
            pk__in=contracheques_servidores_carreira_vinculada_ao_orgao_mes.values_list('servidor__pk')
        ).filter(
            servidorfuncaohistorico__funcao__codigo=Funcao.CODIGO_FG,
            servidorfuncaohistorico__data_inicio_funcao__lte=date(ano, 12, 31),
            servidorfuncaohistorico__data_fim_funcao__gte=date(ano, 12, 31),
        ) | Servidor.objects.filter(pk__in=contracheques_servidores_carreira_vinculada_ao_orgao_mes.values_list('servidor__pk')).filter(
            servidorfuncaohistorico__funcao__codigo=Funcao.CODIGO_FG,
            servidorfuncaohistorico__data_inicio_funcao__lte=date(ano, 12, 31),
            servidorfuncaohistorico__data_fim_funcao__isnull=True,
        )
        #       Servidores Exercício Descentralizado
        contracheques_servidores_exercicio_descentralizado = contracheques_todos.filter(servidor_situacao__codigo=Situacao.EXERC_DESCENT_CARREI)
        contracheques_servidores_exercicio_descentralizado_mes = contracheques_mes.filter(servidor_situacao__codigo=Situacao.EXERC_DESCENT_CARREI)

        servidores_cd_exercicio_descentralizado = Servidor.objects.filter(
            pk__in=contracheques_servidores_exercicio_descentralizado_mes.values_list('servidor__pk')
        ).filter(
            servidorfuncaohistorico__funcao__codigo=Funcao.CODIGO_CD,
            servidorfuncaohistorico__data_inicio_funcao__lte=date(ano, 12, 31),
            servidorfuncaohistorico__data_fim_funcao__gte=date(ano, 12, 31),
        ) | Servidor.objects.filter(pk__in=contracheques_servidores_exercicio_descentralizado_mes.values_list('servidor__pk')).filter(
            servidorfuncaohistorico__funcao__codigo=Funcao.CODIGO_CD,
            servidorfuncaohistorico__data_inicio_funcao__lte=date(ano, 12, 31),
            servidorfuncaohistorico__data_fim_funcao__isnull=True,
        )

        servidores_fg_exercicio_descentralizado = Servidor.objects.filter(
            pk__in=contracheques_servidores_exercicio_descentralizado_mes.values_list('servidor__pk')
        ).filter(
            servidorfuncaohistorico__funcao__codigo=Funcao.CODIGO_FG,
            servidorfuncaohistorico__data_inicio_funcao__lte=date(ano, 12, 31),
            servidorfuncaohistorico__data_fim_funcao__gte=date(ano, 12, 31),
        ) | Servidor.objects.filter(pk__in=contracheques_servidores_exercicio_descentralizado_mes.values_list('servidor__pk')).filter(
            servidorfuncaohistorico__funcao__codigo=Funcao.CODIGO_FG,
            servidorfuncaohistorico__data_inicio_funcao__lte=date(ano, 12, 31),
            servidorfuncaohistorico__data_fim_funcao__isnull=True,
        )

        #       Servidores de Outros Órgãos e Esferas
        contracheques_servidores_outros_orgaos_esferas = contracheques_todos.filter(servidor_situacao__codigo=Situacao.REQ_DE_OUTROS_ORGAOS)
        contracheques_servidores_outros_orgaos_esferas_mes = contracheques_mes.filter(servidor_situacao__codigo=Situacao.REQ_DE_OUTROS_ORGAOS)

        servidores_cd_outros_orgaos_esferas = Servidor.objects.filter(
            pk__in=contracheques_servidores_outros_orgaos_esferas_mes.values_list('servidor__pk')
        ).filter(
            servidorfuncaohistorico__funcao__codigo=Funcao.CODIGO_CD,
            servidorfuncaohistorico__data_inicio_funcao__lte=date(ano, 12, 31),
            servidorfuncaohistorico__data_fim_funcao__gte=date(ano, 12, 31),
        ) | Servidor.objects.filter(pk__in=contracheques_servidores_outros_orgaos_esferas_mes.values_list('servidor__pk')).filter(
            servidorfuncaohistorico__funcao__codigo=Funcao.CODIGO_CD,
            servidorfuncaohistorico__data_inicio_funcao__lte=date(ano, 12, 31),
            servidorfuncaohistorico__data_fim_funcao__isnull=True,
        )

        servidores_fg_outros_orgaos_esferas = Servidor.objects.filter(
            pk__in=contracheques_servidores_outros_orgaos_esferas_mes.values_list('servidor__pk')
        ).filter(
            servidorfuncaohistorico__funcao__codigo=Funcao.CODIGO_FG,
            servidorfuncaohistorico__data_inicio_funcao__lte=date(ano, 12, 31),
            servidorfuncaohistorico__data_fim_funcao__gte=date(ano, 12, 31),
        ) | Servidor.objects.filter(pk__in=contracheques_servidores_outros_orgaos_esferas_mes.values_list('servidor__pk')).filter(
            servidorfuncaohistorico__funcao__codigo=Funcao.CODIGO_FG,
            servidorfuncaohistorico__data_inicio_funcao__lte=date(ano, 12, 31),
            servidorfuncaohistorico__data_fim_funcao__isnull=True,
        )
        #       Servidores Sem Vínculo
        contracheques_servidores_sem_vinculo = contracheques_todos.filter(
            servidor_situacao__codigo__in=Situacao.situacoes_sem_vinculo_com_administracao_publica()
        )
        contracheques_servidores_sem_vinculo_mes = contracheques_mes.filter(
            servidor_situacao__codigo__in=Situacao.situacoes_sem_vinculo_com_administracao_publica()
        )

        servidores_cd_sem_vinculo = Servidor.objects.filter(pk__in=contracheques_servidores_sem_vinculo_mes.values_list('servidor__pk')).filter(
            servidorfuncaohistorico__funcao__codigo=Funcao.CODIGO_CD,
            servidorfuncaohistorico__data_inicio_funcao__lte=date(ano, 12, 31),
            servidorfuncaohistorico__data_fim_funcao__gte=date(ano, 12, 31),
        ) | Servidor.objects.filter(pk__in=contracheques_servidores_sem_vinculo_mes.values_list('servidor__pk')).filter(
            servidorfuncaohistorico__funcao__codigo=Funcao.CODIGO_CD,
            servidorfuncaohistorico__data_inicio_funcao__lte=date(ano, 12, 31),
            servidorfuncaohistorico__data_fim_funcao__isnull=True,
        )
        #       Servidores Aposentados
        contracheques_servidores_aposentados = contracheques_todos.filter(servidor_situacao__codigo=Situacao.APOSENTADOS)
        contracheques_servidores_aposentados_mes = contracheques_mes.filter(servidor_situacao__codigo=Situacao.APOSENTADOS)

        servidores_cd_aposentados = Servidor.objects.filter(pk__in=contracheques_servidores_aposentados_mes.values_list('servidor__pk')).filter(
            servidorfuncaohistorico__funcao__codigo=Funcao.CODIGO_CD,
            servidorfuncaohistorico__data_inicio_funcao__lte=date(ano, 12, 31),
            servidorfuncaohistorico__data_fim_funcao__gte=date(ano, 12, 31),
        ) | Servidor.objects.filter(pk__in=contracheques_servidores_aposentados_mes.values_list('servidor__pk')).filter(
            servidorfuncaohistorico__funcao__codigo=Funcao.CODIGO_CD,
            servidorfuncaohistorico__data_inicio_funcao__lte=date(ano, 12, 31),
            servidorfuncaohistorico__data_fim_funcao__isnull=True,
        )

        ############################################################################################################
        servidores_no_ano_carreira_vinculada_ao_orgao = Servidor.objects.filter(
            pk__in=contracheques_servidores_carreira_vinculada_ao_orgao.values_list('servidor__pk')
        )
        servidores_no_ano_exercicio_descentralizado = Servidor.objects.filter(
            pk__in=contracheques_servidores_exercicio_descentralizado.values_list('servidor__pk')
        )
        servidores_no_ano_outros_orgaos_esferas = Servidor.objects.filter(
            pk__in=contracheques_servidores_outros_orgaos_esferas.values_list('servidor__pk')
        )
        servidores_no_ano_sem_vinculo = Servidor.objects.filter(pk__in=contracheques_servidores_sem_vinculo.values_list('servidor__pk'))
        servidores_no_ano_aposentados = Servidor.objects.filter(pk__in=contracheques_servidores_aposentados.values_list('servidor__pk'))
        #        Servidores de Carreira
        qtd_cd_servidores_carreira = servidores_cd_carreira_vinculada_ao_orgao.count()
        qtd_fg_servidores_carreira = servidores_fg_carreira_vinculada_ao_orgao.count()

        qtd_ingressos_cd_servidores_carreira_vinculada_ao_orgao = (
            servidores_no_ano_carreira_vinculada_ao_orgao.filter(
                servidorfuncaohistorico__funcao__codigo=Funcao.CODIGO_CD,
                servidorfuncaohistorico__data_inicio_funcao__gte=date(ano, 1, 1),
                servidorfuncaohistorico__data_inicio_funcao__lte=date(ano, 12, 31),
            )
            .distinct()
            .count()
        )
        qtd_ingressos_fg_servidores_carreira_vinculada_ao_orgao = (
            servidores_no_ano_carreira_vinculada_ao_orgao.filter(
                servidorfuncaohistorico__funcao__codigo=Funcao.CODIGO_FG,
                servidorfuncaohistorico__data_inicio_funcao__gte=date(ano, 1, 1),
                servidorfuncaohistorico__data_inicio_funcao__lte=date(ano, 12, 31),
            )
            .distinct()
            .count()
        )
        qtd_egressos_cd_servidores_carreira_vinculada_ao_orgao = (
            servidores_no_ano_carreira_vinculada_ao_orgao.filter(
                servidorfuncaohistorico__funcao__codigo=Funcao.CODIGO_CD,
                servidorfuncaohistorico__data_fim_funcao__gte=date(ano, 1, 1),
                servidorfuncaohistorico__data_fim_funcao__lte=date(ano, 12, 31),
            )
            .distinct()
            .count()
        )
        qtd_egressos_fg_servidores_carreira_vinculada_ao_orgao = (
            servidores_no_ano_carreira_vinculada_ao_orgao.filter(
                servidorfuncaohistorico__funcao__codigo=Funcao.CODIGO_FG,
                servidorfuncaohistorico__data_fim_funcao__gte=date(ano, 1, 1),
                servidorfuncaohistorico__data_fim_funcao__lte=date(ano, 12, 31),
            )
            .distinct()
            .count()
        )
        #        Exercicio Descentralizado
        qtd_cd_servidores_exercicio_descentralizado = servidores_cd_exercicio_descentralizado.count()
        qtd_fg_servidores_exercicio_descentralizado = servidores_fg_exercicio_descentralizado.count()

        qtd_ingressos_cd_servidores_exercicio_descentralizado = (
            servidores_no_ano_exercicio_descentralizado.filter(
                servidorfuncaohistorico__funcao__codigo=Funcao.CODIGO_CD,
                servidorfuncaohistorico__data_inicio_funcao__gte=date(ano, 1, 1),
                servidorfuncaohistorico__data_inicio_funcao__lte=date(ano, 12, 31),
            )
            .distinct()
            .count()
        )
        qtd_ingressos_fg_servidores_exercicio_descentralizado = (
            servidores_no_ano_exercicio_descentralizado.filter(
                servidorfuncaohistorico__funcao__codigo=Funcao.CODIGO_FG,
                servidorfuncaohistorico__data_inicio_funcao__gte=date(ano, 1, 1),
                servidorfuncaohistorico__data_inicio_funcao__lte=date(ano, 12, 31),
            )
            .distinct()
            .count()
        )

        qtd_egressos_cd_servidores_exercicio_descentralizado = (
            servidores_no_ano_exercicio_descentralizado.filter(
                servidorfuncaohistorico__funcao__codigo=Funcao.CODIGO_CD,
                servidorfuncaohistorico__data_fim_funcao__gte=date(ano, 1, 1),
                servidorfuncaohistorico__data_fim_funcao__lte=date(ano, 12, 31),
            )
            .distinct()
            .count()
        )
        qtd_egressos_fg_servidores_exercicio_descentralizado = (
            servidores_no_ano_exercicio_descentralizado.filter(
                servidorfuncaohistorico__funcao__codigo=Funcao.CODIGO_FG,
                servidorfuncaohistorico__data_fim_funcao__gte=date(ano, 1, 1),
                servidorfuncaohistorico__data_fim_funcao__lte=date(ano, 12, 31),
            )
            .distinct()
            .count()
        )
        #        Outras Esferas e Órgãos
        qtd_cd_servidores_outros_orgaos_esferas = servidores_cd_outros_orgaos_esferas.count()
        qtd_fg_servidores_outros_orgaos_esferas = servidores_fg_outros_orgaos_esferas.count()

        qtd_ingressos_cd_servidores_outros_orgaos_esferas = (
            servidores_no_ano_outros_orgaos_esferas.filter(
                servidorfuncaohistorico__funcao__codigo=Funcao.CODIGO_CD,
                servidorfuncaohistorico__data_inicio_funcao__gte=date(ano, 1, 1),
                servidorfuncaohistorico__data_inicio_funcao__lte=date(ano, 12, 31),
            )
            .distinct()
            .count()
        )
        qtd_ingressos_fg_servidores_outros_orgaos_esferas = (
            servidores_no_ano_outros_orgaos_esferas.filter(
                servidorfuncaohistorico__funcao__codigo=Funcao.CODIGO_FG,
                servidorfuncaohistorico__data_inicio_funcao__gte=date(ano, 1, 1),
                servidorfuncaohistorico__data_inicio_funcao__lte=date(ano, 12, 31),
            )
            .distinct()
            .count()
        )

        qtd_egressos_cd_servidores_outros_orgaos_esferas = (
            servidores_no_ano_outros_orgaos_esferas.filter(
                servidorfuncaohistorico__funcao__codigo=Funcao.CODIGO_CD,
                servidorfuncaohistorico__data_fim_funcao__gte=date(ano, 1, 1),
                servidorfuncaohistorico__data_fim_funcao__lte=date(ano, 12, 31),
            )
            .distinct()
            .count()
        )
        qtd_egressos_fg_servidores_outros_orgaos_esferas = (
            servidores_no_ano_outros_orgaos_esferas.filter(
                servidorfuncaohistorico__funcao__codigo=Funcao.CODIGO_FG,
                servidorfuncaohistorico__data_fim_funcao__gte=date(ano, 1, 1),
                servidorfuncaohistorico__data_fim_funcao__lte=date(ano, 12, 31),
            )
            .distinct()
            .count()
        )
        #        Sem Vínculo
        qtd_cd_servidores_sem_vinculo = servidores_cd_sem_vinculo.count()
        qtd_ingressos_cd_servidores_sem_vinculo = (
            servidores_no_ano_sem_vinculo.filter(
                servidorfuncaohistorico__funcao__codigo=Funcao.CODIGO_CD,
                servidorfuncaohistorico__data_inicio_funcao__gte=date(ano, 1, 1),
                servidorfuncaohistorico__data_inicio_funcao__lte=date(ano, 12, 31),
            )
            .distinct()
            .count()
        )
        qtd_egressos_cd_servidores_sem_vinculo = (
            servidores_no_ano_sem_vinculo.filter(
                servidorfuncaohistorico__funcao__codigo=Funcao.CODIGO_CD,
                servidorfuncaohistorico__data_fim_funcao__gte=date(ano, 1, 1),
                servidorfuncaohistorico__data_fim_funcao__lte=date(ano, 12, 31),
            )
            .distinct()
            .count()
        )
        #        Aposentados
        qtd_cd_servidores_aposentados = servidores_cd_aposentados.count()
        qtd_ingressos_cd_servidores_aposentados = (
            servidores_no_ano_aposentados.filter(
                servidorfuncaohistorico__funcao__codigo=Funcao.CODIGO_CD,
                servidorfuncaohistorico__data_inicio_funcao__gte=date(ano, 1, 1),
                servidorfuncaohistorico__data_inicio_funcao__lte=date(ano, 12, 31),
            )
            .distinct()
            .count()
        )
        qtd_egressos_cd_servidores_aposentados = (
            servidores_no_ano_aposentados.filter(
                servidorfuncaohistorico__funcao__codigo=Funcao.CODIGO_CD,
                servidorfuncaohistorico__data_fim_funcao__gte=date(ano, 1, 1),
                servidorfuncaohistorico__data_fim_funcao__lte=date(ano, 12, 31),
            )
            .distinct()
            .count()
        )

        total_cds = (
            qtd_cd_servidores_carreira
            + qtd_cd_servidores_exercicio_descentralizado
            + qtd_cd_servidores_outros_orgaos_esferas
            + qtd_cd_servidores_sem_vinculo
            + qtd_cd_servidores_aposentados
        )

        total_fgs = qtd_fg_servidores_carreira + qtd_fg_servidores_exercicio_descentralizado + qtd_fg_servidores_outros_orgaos_esferas

        total_ingressos_fgs = (
            qtd_ingressos_fg_servidores_carreira_vinculada_ao_orgao
            + qtd_ingressos_fg_servidores_exercicio_descentralizado
            + qtd_ingressos_fg_servidores_outros_orgaos_esferas
        )
        total_ingressos_cds = (
            qtd_ingressos_cd_servidores_carreira_vinculada_ao_orgao
            + qtd_ingressos_cd_servidores_exercicio_descentralizado
            + qtd_ingressos_cd_servidores_outros_orgaos_esferas
            + qtd_ingressos_cd_servidores_sem_vinculo
            + qtd_ingressos_cd_servidores_aposentados
        )
        total_ingressos = total_ingressos_fgs + total_ingressos_cds

        total_egressos_fgs = (
            qtd_egressos_fg_servidores_carreira_vinculada_ao_orgao
            + qtd_egressos_fg_servidores_exercicio_descentralizado
            + qtd_egressos_fg_servidores_outros_orgaos_esferas
        )
        total_egressos_cds = (
            qtd_egressos_cd_servidores_carreira_vinculada_ao_orgao
            + qtd_egressos_cd_servidores_exercicio_descentralizado
            + qtd_egressos_cd_servidores_outros_orgaos_esferas
            + qtd_egressos_cd_servidores_sem_vinculo
            + qtd_egressos_cd_servidores_aposentados
        )
        total_egressos = total_egressos_cds + total_egressos_fgs

        total_funcoes = total_fgs + total_cds

        resultados = []
        resultados.append(['1. Cargos em Comissão', '', total_cds, total_ingressos_cds, total_egressos_cds])
        resultados.append(['1.1 Cargos Natureza Especial ', '-', '-', '-', '-'])
        resultados.append(['1.2 Grupo Direção e Assessoramento Superior', '-', total_cds, total_ingressos_cds, total_egressos_cds])
        resultados.append(
            [
                '1.2.1 Servidores de carreira vinculada ao órgão',
                '-',
                qtd_cd_servidores_carreira,
                qtd_ingressos_cd_servidores_carreira_vinculada_ao_orgao,
                qtd_egressos_cd_servidores_carreira_vinculada_ao_orgao,
            ]
        )
        resultados.append(
            [
                '1.2.2 Servidores de carreira em exercício descentralizado ',
                '-',
                qtd_cd_servidores_exercicio_descentralizado,
                qtd_ingressos_cd_servidores_exercicio_descentralizado,
                qtd_egressos_cd_servidores_exercicio_descentralizado,
            ]
        )
        resultados.append(
            [
                '1.2.3 Servidores de Outros Órgãos e Esferas',
                '-',
                qtd_cd_servidores_outros_orgaos_esferas,
                qtd_ingressos_cd_servidores_outros_orgaos_esferas,
                qtd_egressos_cd_servidores_outros_orgaos_esferas,
            ]
        )
        resultados.append(
            [
                '1.2.4 Sem Vínculo ',
                '-',
                qtd_cd_servidores_sem_vinculo,
                qtd_ingressos_cd_servidores_sem_vinculo,
                qtd_egressos_cd_servidores_sem_vinculo,
            ]
        )
        resultados.append(
            [
                '1.2.4 Aposentados ',
                '-',
                qtd_cd_servidores_aposentados,
                qtd_ingressos_cd_servidores_aposentados,
                qtd_egressos_cd_servidores_aposentados,
            ]
        )
        resultados.append(['2. Funções Gratificadas ', '-', total_fgs, total_ingressos_fgs, total_egressos_fgs])
        resultados.append(
            [
                '2.1 Servidores de carreira vinculada ao órgão ',
                '-',
                qtd_fg_servidores_carreira,
                qtd_ingressos_fg_servidores_carreira_vinculada_ao_orgao,
                qtd_egressos_fg_servidores_carreira_vinculada_ao_orgao,
            ]
        )
        resultados.append(
            [
                '2.2 Servidores de carreira em exercício descentralizado ',
                '-',
                qtd_fg_servidores_exercicio_descentralizado,
                qtd_ingressos_fg_servidores_exercicio_descentralizado,
                qtd_egressos_fg_servidores_exercicio_descentralizado,
            ]
        )
        resultados.append(
            [
                '2.3 Servidores de Outros Órgãos e Esferas ',
                '-',
                qtd_fg_servidores_outros_orgaos_esferas,
                qtd_ingressos_fg_servidores_outros_orgaos_esferas,
                qtd_egressos_fg_servidores_outros_orgaos_esferas,
            ]
        )
        resultados.append(['3. Total de Servidores em Cargo e em Função(1+2) ', '-', total_funcoes, total_ingressos, total_egressos])
    return locals()


@rtr()
@permission_required('rh.pode_ver_relatorios_rh', 'rh.eh_rh_sistemico, comum.is_reitor, comum.is_pro_reitor, comum.is_diretor_geral')
def relatorio_cargos_por_faixa_etaria(request):
    form = TipologiaCargoPorFaixaForm(request.POST or None)
    title = 'Cargos por Faixa Etária'
    if form.is_valid():
        campus = form.cleaned_data['campus']
        ano = int(form.cleaned_data['ano'])
        mes = int(form.cleaned_data['mes'])
        ultimo_dia_mes = adicionar_mes(date(ano, mes, 1), 1) - timedelta(days=1)

        # obtem os contra-cheques do mes/ano escolhido e campus (se informado)
        contra_cheques = ContraCheque.objects.ativos().fita_espelho().filter(ano__ano=ano, mes=mes)
        if campus:
            campus = UnidadeOrganizacional.objects.suap().get(pk=form.cleaned_data['campus'])
            contra_cheques = contra_cheques.filter(servidor_setor_lotacao__uo__equivalente=campus)
            title = f'Cargos por Faixa Etária - {campus.nome} ({campus}) - {Meses.get_mes(mes)}/{ano}'
        else:
            title = f'Cargos por Faixa Etária - Todos os Campus - {Meses.get_mes(mes)}/{ano}'

        """
            situacoes_totais =

            { codigo_situacao: {
                                nome_situacao: xxx,
                                faixas: {30: 0, 40: 0, 50: 0, 60: 0, 99: 0, total: 0},
                                funcoes: {
                                    codigo_funcao: {
                                        nome_funcao: xxxx,
                                        faixas: {30: 0, 40: 0, 50: 0, 60: 0, 99: 0, total: 0}
                                    },
                                    ...
                                }
                              },
             ... }

        """

        totais_por_faixa_geral = {'30': 0, '40': 0, '50': 0, '60': 0, '99': 0, 'total': 0}

        # analisa cada situacao siape
        situacoes_totais = {}
        for situacao in Situacao.objects.all().order_by('nome'):
            # obtem os contra-cheques cujos servidores estavam na situacao corrente
            contra_cheques_da_situacao = contra_cheques.filter(servidor_situacao__codigo=situacao.codigo)

            if contra_cheques_da_situacao.exists():
                # prepara totais da situacao
                if situacao.codigo not in situacoes_totais:
                    situacoes_totais[situacao.codigo] = {}
                    situacoes_totais[situacao.codigo]['nome_situacao'] = situacao.nome
                    situacoes_totais[situacao.codigo]['faixas'] = {'30': 0, '40': 0, '50': 0, '60': 0, '99': 0, 'total': 0}
                    situacoes_totais[situacao.codigo]['funcoes'] = {}

                # o contracheque não contém, diretamente, a informação da função do servidor

                # obtem as funcoes no historico dos servidores
                funcoes_historico = ServidorFuncaoHistorico.objects.filter(
                    servidor__id__in=contra_cheques_da_situacao.values_list('servidor', flat=True),
                    data_inicio_funcao__lte=ultimo_dia_mes,
                    data_fim_funcao__gte=ultimo_dia_mes,
                )

                # obtem as funcoes atuais dos servidores
                # obs: é possível que a função atual esteja no histórico de função e AINDA continue no registro do servidor
                servidores_funcoes_atuais = Servidor.objects.filter(
                    id__in=contra_cheques_da_situacao.values_list('servidor', flat=True),
                    funcao_data_ocupacao__lte=ultimo_dia_mes,
                    funcao_data_saida__isnull=True,
                ).exclude(id__in=funcoes_historico.values_list('servidor', flat=True))

                # contabiliza as funcoes via historico de funcoes
                for funcao_historico in funcoes_historico:
                    funcao_codigo = funcao_historico.funcao.codigo
                    funcao_nome = funcao_historico.funcao.nome
                    if funcao_codigo not in situacoes_totais[situacao.codigo]['funcoes']:
                        situacoes_totais[situacao.codigo]['funcoes'][funcao_codigo] = {}
                        situacoes_totais[situacao.codigo]['funcoes'][funcao_codigo]['nome_funcao'] = funcao_nome
                        situacoes_totais[situacao.codigo]['funcoes'][funcao_codigo]['faixas'] = {
                            '30': 0,
                            '40': 0,
                            '50': 0,
                            '60': 0,
                            '99': 0,
                            'total': 0,
                        }

                    idade_servidor = get_age(
                        funcao_historico.servidor.pessoa_fisica.nascimento_data, ultimo_dia_mes
                    )  # idade na época do contra-cheque
                    if idade_servidor <= 30:
                        faixa = '30'
                    elif idade_servidor <= 40:
                        faixa = '40'
                    elif idade_servidor <= 50:
                        faixa = '50'
                    elif idade_servidor <= 60:
                        faixa = '60'
                    else:
                        faixa = '99'  # acima de 60 anos

                    situacoes_totais[situacao.codigo]['funcoes'][funcao_codigo]['faixas'][faixa] += 1
                    situacoes_totais[situacao.codigo]['funcoes'][funcao_codigo]['faixas']['total'] += 1
                    situacoes_totais[situacao.codigo]['faixas'][faixa] += 1
                    situacoes_totais[situacao.codigo]['faixas']['total'] += 1
                    totais_por_faixa_geral[faixa] += 1
                    totais_por_faixa_geral['total'] += 1

                # contabiliza as funcoes via funcao atual
                for servidor_funcao_atual in servidores_funcoes_atuais:
                    funcao_codigo = servidor_funcao_atual.funcao and servidor_funcao_atual.funcao.codigo
                    funcao_nome = servidor_funcao_atual.funcao and servidor_funcao_atual.funcao.nome
                    if funcao_codigo is None:
                        continue
                    if funcao_codigo not in situacoes_totais[situacao.codigo]['funcoes']:
                        situacoes_totais[situacao.codigo]['funcoes'][funcao_codigo] = {}
                        situacoes_totais[situacao.codigo]['funcoes'][funcao_codigo]['nome_funcao'] = funcao_nome
                        situacoes_totais[situacao.codigo]['funcoes'][funcao_codigo]['faixas'] = {
                            '30': 0,
                            '40': 0,
                            '50': 0,
                            '60': 0,
                            '99': 0,
                            'total': 0,
                        }

                    idade_servidor = get_age(servidor_funcao_atual.nascimento_data, ultimo_dia_mes)  # idade na época do contra-cheque
                    if idade_servidor <= 30:
                        faixa = '30'
                    elif idade_servidor <= 40:
                        faixa = '40'
                    elif idade_servidor <= 50:
                        faixa = '50'
                    elif idade_servidor <= 60:
                        faixa = '60'
                    else:
                        faixa = '99'  # acima de 60 anos

                    situacoes_totais[situacao.codigo]['funcoes'][funcao_codigo]['faixas'][faixa] += 1
                    situacoes_totais[situacao.codigo]['funcoes'][funcao_codigo]['faixas']['total'] += 1
                    situacoes_totais[situacao.codigo]['faixas'][faixa] += 1
                    situacoes_totais[situacao.codigo]['faixas']['total'] += 1
                    totais_por_faixa_geral[faixa] += 1
                    totais_por_faixa_geral['total'] += 1

                # servidores sem funcao
                sem_funcao_total = None
                servidores_com_funcao = list(funcoes_historico.values_list('servidor', flat=True)) + list(
                    servidores_funcoes_atuais.values_list('id', flat=True)
                )
                for contra_cheque in contra_cheques_da_situacao:
                    servidor = contra_cheque.servidor
                    if servidor.id not in servidores_com_funcao:
                        idade_servidor = get_age(servidor.pessoa_fisica.nascimento_data, ultimo_dia_mes)  # idade na época do contra-cheque
                        if idade_servidor <= 30:
                            faixa = '30'
                        elif idade_servidor <= 40:
                            faixa = '40'
                        elif idade_servidor <= 50:
                            faixa = '50'
                        elif idade_servidor <= 60:
                            faixa = '60'
                        else:
                            faixa = '99'  # acima de 60 anos
                        situacoes_totais[situacao.codigo]['faixas'][faixa] += 1
                        situacoes_totais[situacao.codigo]['faixas']['total'] += 1
                        totais_por_faixa_geral[faixa] += 1
                        totais_por_faixa_geral['total'] += 1

    return locals()


@rtr()
@permission_required('contracheques.pode_ver_contracheques_agrupados')
def relatorio_dgp(request):
    def sum_vector(m1, m2):
        m3 = [0 if str(item).isdigit() else m2[0] for item in m1]
        for index, value in enumerate(m1):
            if str(value).isdigit():
                m3[index] = m1[index] + m2[index]
        return m3

    def count_and_distribute_query(descricao, query):
        basico = query.filter(servidor_titulacao__isnull=True, servidor_cargo_emprego__sigla_escolaridade='NA').count()
        medio = query.filter(servidor_titulacao__isnull=True, servidor_cargo_emprego__sigla_escolaridade='NI').count()
        tecnico = query.filter(
            servidor_titulacao__nome='TECNICO (NIVEL MEDIO COMPLETO)', servidor_cargo_emprego__sigla_escolaridade__in=['NA', 'NI']
        ).count()
        superior = (
            query.filter(servidor_titulacao__isnull=True, servidor_cargo_emprego__sigla_escolaridade__in=['NS']).count()
            + query.filter(servidor_titulacao__nome='GRADUACAO (NIVEL SUPERIOR COMPLETO)').count()
        )
        aperfeicoado = query.filter(servidor_titulacao__nome='APERFEICOAMENTO NIVEL SUPERIOR').count()
        especialista = query.filter(servidor_titulacao__nome='ESPECIALIZACAO NIVEL SUPERIOR').count()
        mestre = query.filter(servidor_titulacao__nome='MESTRADO').count()
        doutor = query.filter(servidor_titulacao__nome='DOUTORADO').count()
        total = basico + medio + tecnico + superior + aperfeicoado + especialista + mestre + doutor
        return [descricao, basico, medio, tecnico, superior, aperfeicoado, especialista, mestre, doutor, total]

    FormClass = PeriodoMesAnoRelatorioDGPFactory()
    if request.method == 'POST':
        form = FormClass(request.POST)
        if form.is_valid():
            setor = form.cleaned_data['setor']
            tabela = [
                [
                    'Servidores/Categorias Funcionais',
                    'Básico',
                    'Ensino Médio',
                    'Técnico',
                    'Graduado',
                    'Aperfeiçoado',
                    'Especialista',
                    'Mestre',
                    'Doutor',
                    'Total',
                ]
            ]
            d = datetime(int(form.cleaned_data['periodo'][2:6]), int(form.cleaned_data['periodo'][0:2]), 1)
            ccs = ContraCheque.objects.ativos().fita_espelho().filter(mes=d.month, ano__ano=d.year)
            servidores_afastados = ServidorAfastamento.objects.exclude_afastamentos_pgd().filter(
                data_inicio__lte=d, data_termino__gte=d, cancelado=False
            )
            ids_servidores_afastados = servidores_afastados.values_list('servidor', flat=True)
            servidores_capacitando = servidores_afastados.filter(afastamento__nome__unaccent__icontains='Capacitação')
            ids_servidores_capacitando = servidores_capacitando.values_list('servidor', flat=True)
            total_docentes = [0 for item in tabela[0]]
            total_tecnicos = [0 for item in tabela[0]]
            total_docentes[0] = 'Total Docentes'
            total_tecnicos[0] = 'Total Técnicos'

            # Nota: Estamos usando contra_cheque.servidor_setor_lotacao como referência pois
            # servidor_setor_localizacao nao vem devidamente preenchido na fita.

            # Docentes em Capacitação
            query = ccs.filter(
                servidor__id__in=ids_servidores_capacitando,
                servidor_situacao__nome_siape='ATIVO PERMANENTE',
                servidor__eh_docente=True,
                servidor_setor_lotacao__id__in=setor.ids_descendentes,
            )
            linha = count_and_distribute_query(descricao='Docentes em Capacitação', query=query)
            tabela.append(linha)

            # Docentes Afastados (férias, capacitação, licença médica, etc)
            query = ccs.filter(
                servidor__id__in=ids_servidores_afastados,
                servidor_situacao__nome_siape='ATIVO PERMANENTE',
                servidor__eh_docente=True,
                servidor_setor_lotacao__id__in=setor.ids_descendentes,
            )
            linha = count_and_distribute_query(descricao='Docentes Afastados (férias, capacitação, licença médica, etc)', query=query)
            tabela.append(linha)
            total_docentes = sum_vector(linha, total_docentes)

            # Docentes em Exercício (sem afastamento)
            query = ccs.exclude(servidor__id__in=ids_servidores_afastados).filter(
                servidor_situacao__nome_siape='ATIVO PERMANENTE',
                servidor__eh_docente=True,
                servidor_setor_lotacao__id__in=setor.ids_descendentes,
            )
            linha = count_and_distribute_query(descricao='Docentes em Exercício (sem afastamento)', query=query)
            tabela.append(linha)
            total_docentes = sum_vector(linha, total_docentes)

            # Docentes 20HS (inclusive os afastados)
            query = ccs.filter(
                servidor_situacao__nome_siape='ATIVO PERMANENTE',
                servidor__eh_docente=True,
                servidor_jornada_trabalho__nome='20 HORAS SEMANAIS',
                servidor_setor_lotacao__id__in=setor.ids_descendentes,
            )
            linha = count_and_distribute_query(descricao='Docentes 20HS (inclusive os afastados)', query=query)
            tabela.append(linha)

            # Docentes 40HS (inclusive os afastados)
            query = ccs.filter(
                servidor_situacao__nome_siape='ATIVO PERMANENTE',
                servidor__eh_docente=True,
                servidor_jornada_trabalho__nome='40 HORAS SEMANAIS',
                servidor_setor_lotacao__id__in=setor.ids_descendentes,
            )
            linha = count_and_distribute_query(descricao='Docentes 40HS (inclusive os afastados)', query=query)
            tabela.append(linha)

            # Docentes DE (inclusive os afastados)
            query = ccs.filter(
                servidor_situacao__nome_siape='ATIVO PERMANENTE',
                servidor__eh_docente=True,
                servidor_jornada_trabalho__nome='DEDICACAO EXCLUSIVA',
                servidor_setor_lotacao__id__in=setor.ids_descendentes,
            )
            linha = count_and_distribute_query(descricao='Docentes DE (inclusive os afastados)', query=query)
            tabela.append(linha)
            tabela.append(total_docentes)

            # Técnicos Administrativos em Capacitação
            query = ccs.filter(
                servidor__id__in=ids_servidores_capacitando,
                servidor_situacao__nome_siape='ATIVO PERMANENTE',
                servidor__eh_tecnico_administrativo=True,
                servidor_setor_lotacao__id__in=setor.ids_descendentes,
            )
            linha = count_and_distribute_query(descricao='Técnicos Administrativos em Capacitação', query=query)
            tabela.append(linha)

            # Técnicos Afastados (férias, capacitação, licença médica, etc)
            query = ccs.filter(
                servidor__id__in=ids_servidores_afastados,
                servidor_situacao__nome_siape='ATIVO PERMANENTE',
                servidor__eh_tecnico_administrativo=True,
                servidor_setor_lotacao__id__in=setor.ids_descendentes,
            )
            linha = count_and_distribute_query(descricao='Técnicos Afastados (férias, capacitação, licença médica, etc)', query=query)
            tabela.append(linha)
            total_tecnicos = sum_vector(linha, total_tecnicos)

            # Técnicos Administrativos em Exercício (sem afastamento)
            query = ccs.exclude(servidor__id__in=ids_servidores_afastados).filter(
                servidor_situacao__nome_siape='ATIVO PERMANENTE',
                servidor__eh_tecnico_administrativo=True,
                servidor_setor_lotacao__id__in=setor.ids_descendentes,
            )
            linha = count_and_distribute_query(descricao='Técnicos Administrativos em Exercício (sem afastamento)', query=query)
            tabela.append(linha)
            total_tecnicos = sum_vector(linha, total_tecnicos)
            tabela.append(total_tecnicos)

            mensagem = f'Contagem de Servidores por Titulação ({setor.sigla}) em {Meses.get_mes(d.month)}/{d.year}.'
            return render('contracheques/templates/tabela_relatorio_dgp.html', {'mensagem': mensagem, 'tabela': tabela})
    else:
        form = FormClass()
    return locals()


@rtr('tela_rubrica_por_campus.html')
@permission_required('contracheques.pode_ver_contracheques_agrupados')
def rubrica_por_campus(request):
    user = request.user
    FormClass = RubricaPorCampusFactory()
    form = FormClass(request.POST or None)
    title = 'Relatório de Gastos por Rubrica'
    if form.is_valid():
        if int(request.POST['periodo'][:2]):
            periodo = '/'.join([request.POST['periodo'][:2], request.POST['periodo'][2:]])
            meses = [int(request.POST['periodo'][:2])]
            meses_list = [((int(request.POST['periodo'][:2]), Meses.get_mes(int(request.POST['periodo'][:2]))))]
        else:
            periodo = request.POST['periodo'][2:]
            meses = (
                ContraCheque.objects.ativos()
                .fita_espelho()
                .filter(ano__ano=int(request.POST['periodo'][2:]))
                .order_by('mes')
                .values_list('mes', flat=True)
                .distinct()
            )
            set_meses = []
            for mes in meses:
                if mes not in set_meses:
                    set_meses.append(mes)
            meses_list = [(mes, Meses.get_mes(mes)) for mes in set_meses]

        pode_detalhar = request.user.has_perm('contracheques.pode_ver_contracheques_detalhados')

        rubrica = form.cleaned_data['rubrica']
        contabilidade = {'total_valor': Decimal('0.0'), 'total_quantidade': 0}

        totais = {}
        for numero_mes, _nome_mes in meses_list:
            totais.update({numero_mes: {'total_valor': Decimal('0.0'), 'total_quantidade': 0}})

        campus_siape = UnidadeOrganizacional.objects.siape().filter(
            pk__in=ContraChequeRubrica.objects.filter(
                contra_cheque__excluido=False,
                contra_cheque__tipo_importacao=ContraCheque.IMPORTACAO_FITA_ESPELHO,
                contra_cheque__mes__in=meses,
                contra_cheque__ano__ano=int(request.POST['periodo'][2:]),
                rubrica=rubrica,
                contra_cheque__servidor_setor_lotacao__uo__isnull=False,
            ).values_list('contra_cheque__servidor_setor_lotacao__uo', flat=True)
        )
        for c in campus_siape:
            contabilidade[c] = {}
            for numero_mes, _nome_mes in meses_list:
                contabilidade[c].update({numero_mes: {}})
                ccrs_por_campus = ContraChequeRubrica.objects.filter(
                    contra_cheque__excluido=False,
                    contra_cheque__tipo_importacao=ContraCheque.IMPORTACAO_FITA_ESPELHO,
                    contra_cheque__mes=numero_mes,
                    contra_cheque__ano__ano=int(request.POST['periodo'][2:]),
                    contra_cheque__servidor_setor_lotacao__uo=c,
                    rubrica=rubrica,
                )
                if request.POST['situacao']:
                    ccrs_por_campus = ccrs_por_campus.filter(contra_cheque__servidor_situacao=request.POST['situacao'])
                if request.POST['tipo']:
                    ccrs_por_campus = ccrs_por_campus.filter(tipo__nome=form.cleaned_data['tipo'])
                if request.POST.getlist('sequencia'):
                    ccrs_por_campus = ccrs_por_campus.filter(sequencia__in=form.cleaned_data['sequencia'])
                if request.POST['prazo']:
                    ccrs_por_campus = ccrs_por_campus.filter(prazo=form.cleaned_data['prazo'])
                if request.POST['categoria']:
                    if request.POST['categoria'] == 'docente':
                        ccrs_por_campus = ccrs_por_campus.filter(contra_cheque__servidor__eh_docente=True)
                    elif request.POST['categoria'] == 'tecnico_administrativo':
                        ccrs_por_campus = ccrs_por_campus.filter(contra_cheque__servidor__eh_tecnico_administrativo=True)

                contabilidade[c][numero_mes]['valor'] = Decimal('0.0')
                contabilidade[c][numero_mes]['valor'] += ccrs_por_campus.filter(tipo__codigo='1').aggregate(Sum('valor'))['valor__sum'] or Decimal(
                    '0.0'
                )
                contabilidade[c][numero_mes]['valor'] -= ccrs_por_campus.filter(tipo__codigo='2').aggregate(Sum('valor'))['valor__sum'] or Decimal(
                    '0.0'
                )
                contabilidade[c][numero_mes]['quantidade'] = ccrs_por_campus.count()
                totais[numero_mes]['total_valor'] += ccrs_por_campus.filter(tipo__codigo='1').aggregate(Sum('valor'))['valor__sum'] or Decimal('0.0')
                totais[numero_mes]['total_valor'] -= ccrs_por_campus.filter(tipo__codigo='2').aggregate(Sum('valor'))['valor__sum'] or Decimal('0.0')
                totais[numero_mes]['total_quantidade'] += ccrs_por_campus.count()
                contabilidade[c][numero_mes]['url'] = (
                    '/contracheques/rubrica_por_campus_detalhado/?campus={}&rubrica={}&periodo={}{}&tipo={}&situacao={}&sequencia={}&prazo={}'.format(
                        str(c.id),
                        form.cleaned_data['rubrica'].id,
                        f'{numero_mes:2d}',
                        request.POST['periodo'][2:],
                        request.POST['tipo'],
                        request.POST['situacao'],
                        ','.join(request.POST.getlist('sequencia')),
                        request.POST['prazo'],
                    )
                )

        c = 'Sem Campus'
        contabilidade[c] = {}

        for numero_mes, _nome_mes in meses_list:
            contabilidade[c].update({numero_mes: {}})
            ccrs_sem_campus = ContraChequeRubrica.objects.filter(
                contra_cheque__excluido=False,
                contra_cheque__tipo_importacao=ContraCheque.IMPORTACAO_FITA_ESPELHO,
                contra_cheque__mes=numero_mes,
                contra_cheque__ano__ano=int(request.POST['periodo'][2:]),
                contra_cheque__servidor_setor_lotacao__isnull=True,
                rubrica=rubrica,
            )
            if request.POST['situacao']:
                ccrs_sem_campus = ccrs_sem_campus.filter(contra_cheque__servidor_situacao=request.POST['situacao'])
            if request.POST['tipo']:
                ccrs_sem_campus = ccrs_sem_campus.filter(tipo__nome=form.cleaned_data['tipo'])
            if request.POST.getlist('sequencia'):
                ccrs_sem_campus = ccrs_sem_campus.filter(sequencia__in=form.cleaned_data['sequencia'])
            if request.POST['prazo']:
                ccrs_sem_campus = ccrs_sem_campus.filter(prazo=form.cleaned_data['prazo'])
            if request.POST['categoria']:
                if request.POST['categoria'] == 'docente':
                    ccrs_sem_campus = ccrs_sem_campus.filter(contra_cheque__servidor__eh_docente=True)
                elif request.POST['categoria'] == 'tecnico_administrativo':
                    ccrs_sem_campus = ccrs_sem_campus.filter(contra_cheque__servidor__eh_tecnico_administrativo=True)

            contabilidade[c][numero_mes]['valor'] = Decimal('0.0')
            contabilidade[c][numero_mes]['valor'] += ccrs_sem_campus.filter(tipo__codigo='1').aggregate(Sum('valor'))['valor__sum'] or Decimal('0.0')
            contabilidade[c][numero_mes]['valor'] -= ccrs_sem_campus.filter(tipo__codigo='2').aggregate(Sum('valor'))['valor__sum'] or Decimal('0.0')
            contabilidade[c][numero_mes]['quantidade'] = ccrs_sem_campus.count()
            totais[numero_mes]['total_valor'] += ccrs_sem_campus.filter(tipo__codigo='1').aggregate(Sum('valor'))['valor__sum'] or Decimal('0.0')
            totais[numero_mes]['total_valor'] -= ccrs_sem_campus.filter(tipo__codigo='2').aggregate(Sum('valor'))['valor__sum'] or Decimal('0.0')
            totais[numero_mes]['total_quantidade'] += ccrs_sem_campus.count()
            contabilidade[c][numero_mes]['url'] = (
                '/contracheques/rubrica_por_campus_detalhado/?campus={}&rubrica={}&periodo={}{}&tipo={}&situacao={}&sequencia={}&prazo={}&categoria={}'.format(
                    0,
                    form.cleaned_data['rubrica'].id,
                    f'{numero_mes:2d}',
                    request.POST['periodo'][2:],
                    request.POST['tipo'],
                    request.POST['situacao'],
                    ','.join(request.POST.getlist('sequencia')),
                    request.POST['prazo'],
                    request.POST['categoria'],
                )
            )

            totais[numero_mes]['url'] = (
                '/contracheques/rubrica_por_campus_detalhado/?campus={}&rubrica={}&periodo={}{}&tipo={}&situacao={}&sequencia={}&prazo={}&categoria={}'.format(
                    'todos',
                    form.cleaned_data['rubrica'].id,
                    f'{numero_mes:2d}',
                    request.POST['periodo'][2:],
                    request.POST['tipo'],
                    request.POST['situacao'],
                    ','.join(request.POST.getlist('sequencia')),
                    request.POST['prazo'],
                    request.POST['categoria'],
                )
            )

    return locals()


@rtr('contracheques/templates/tela_rubrica_por_campus_detalhado.html')
@permission_required('contracheques.pode_ver_contracheques_detalhados')
def rubrica_por_campus_detalhado(request):
    title = 'Relatório de Gastos Rubrica Detalhado por Campus'
    user = request.user
    id_campus = request.GET.get('campus')
    rubrica = Rubrica.objects.usadas_no_if().filter(id=int(request.GET.get('rubrica', 0))).first()
    if not rubrica:
        return httprr('/', 'Rubrica não encontrada.', 'error')
    periodo = '{}/{}'.format(request.GET.get('periodo', '')[:2], request.GET.get('periodo', '')[2:])

    if id_campus == 'todos':
        campus = 'Todos'
        queryset = ContraChequeRubrica.objects.filter(
            contra_cheque__excluido=False,
            contra_cheque__tipo_importacao=ContraCheque.IMPORTACAO_FITA_ESPELHO,
            contra_cheque__mes=int(periodo[:2]),
            contra_cheque__ano__ano=int(request.GET.get('periodo')[2:]),
            rubrica=rubrica,
        )

    elif id_campus == '0' or id_campus is None:
        campus = 'Sem Campus'
        queryset = ContraChequeRubrica.objects.filter(
            contra_cheque__excluido=False,
            contra_cheque__tipo_importacao=ContraCheque.IMPORTACAO_FITA_ESPELHO,
            contra_cheque__mes=int(periodo[:2]),
            contra_cheque__ano__ano=int(request.GET.get('periodo')[2:]),
            rubrica=rubrica,
            contra_cheque__servidor_setor_lotacao__isnull=True,
        )

    else:
        campus = UnidadeOrganizacional.objects.siape().get(id=int(id_campus))
        queryset = ContraChequeRubrica.objects.filter(
            contra_cheque__excluido=False,
            contra_cheque__tipo_importacao=ContraCheque.IMPORTACAO_FITA_ESPELHO,
            contra_cheque__mes=int(request.GET.get('periodo')[:2]),
            contra_cheque__ano__ano=int(request.GET.get('periodo')[2:]),
            rubrica=rubrica,
            contra_cheque__servidor_setor_lotacao__uo=campus,
        )

    situacao = request.GET.get('situacao', None)
    if situacao:
        queryset = queryset.filter(contra_cheque__servidor_situacao=situacao)

    tipo = request.GET.get('tipo', None)
    if tipo:
        queryset = queryset.filter(tipo__nome=tipo)

    sequencia = request.GET.get('sequencia', None)
    if sequencia and len(sequencia.split(',')) < 10:
        queryset = queryset.filter(sequencia__in=sequencia.split(','))

    prazo = request.GET.get('prazo', None)
    if prazo:
        queryset = queryset.filter(prazo=prazo)

    categoria = request.GET.get('categoria', None)
    if categoria:
        if categoria == 'docente':
            queryset = queryset.filter(contra_cheque__servidor__eh_docente=True)
        elif categoria == 'tecnico_administrativo':
            queryset = queryset.filter(contra_cheque__servidor__eh_tecnico_administrativo=True)

    # Django_Table2 Report
    # Primeiro define-se os fields que irão compor a table
    fields = (
        'contra_cheque.servidor.pessoa_fisica.nome',
        'contra_cheque.servidor_situacao',
        'contra_cheque.servidor_setor_lotacao',
        'contra_cheque.servidor.cargo_emprego',
        'rubrica',
        'tipo',
        'sequencia',
        'prazo',
        'valor',
    )
    # Adiciona Fields customizados se existirem
    custom_fields = {
        'matricula': LinkColumn(
            'servidor',
            kwargs={'servidor_matricula': Accessor('contra_cheque.servidor.matricula')},
            verbose_name='Matrícula',
            accessor=Accessor('contra_cheque.servidor.matricula'),
        )
    }
    # A sequencia em que os campos serão exibidos, lembrando que sem essa sequence os campos customizados serão criados no fim
    sequence = ['matricula']
    # cria a tabela a partir do dicionario com as informacoes
    queryset = queryset.select_related(
        'rubrica',
        'tipo',
        'contra_cheque',
        'contra_cheque__servidor',
        'contra_cheque__servidor_situacao',
        'contra_cheque__servidor_setor_lotacao',
        'contra_cheque__servidor__cargo_emprego',
        'contra_cheque__servidor__cargo_emprego__grupo_cargo_emprego',
    )
    table = get_table(queryset=queryset, fields=fields, sequence=sequence, custom_fields=custom_fields)
    # metodo para criar totalizadores no fim da pagina. Defini-se qual
    table.add_sum_table_foot('valor', conditions={'+': {'tipo__codigo': '1'}, '-': {'tipo__codigo': '2'}})
    if request.GET.get('relatorio', None):
        return tasks.table_export(request.GET.get('relatorio', None), *table.get_params())

    return locals()


@rtr()
@permission_required('contracheques.pode_ver_contracheques_agrupados')
def bruto_liquido_por_campus(request):
    user = request.user

    FormClass = BrutoLiquidoPorCampusFactory()
    title = 'Relatório de Gastos - Bruto/Líquido'
    if request.method == 'POST':
        form = FormClass(request.POST)

        if form.is_valid():
            if int(request.POST['periodo'][:2]):
                periodo = '/'.join([request.POST['periodo'][:2], request.POST['periodo'][2:]])
                meses = [int(request.POST['periodo'][:2])]
                meses_list = [((int(request.POST['periodo'][:2]), Meses.get_mes(int(request.POST['periodo'][:2]))))]
            else:
                periodo = request.POST['periodo'][2:]
                meses = (
                    ContraCheque.objects.ativos()
                    .fita_espelho()
                    .filter(ano__ano=int(request.POST['periodo'][2:]))
                    .order_by('mes')
                    .values_list('mes', flat=True)
                    .distinct()
                )
                set_meses = []
                for mes in meses:
                    if mes not in set_meses:
                        set_meses.append(mes)
                meses_list = [(mes, Meses.get_mes(mes)) for mes in set_meses]

            pode_detalhar = request.user.has_perm('contracheques.pode_ver_contracheques_detalhados')
            contabilidade = {'total_bruto': Decimal('0.0'), 'total_liquido': Decimal('0.0'), 'total_quantidade': 0}

            totais = {}
            for numero_mes, _nome_mes in meses_list:
                totais.update({numero_mes: {'total_bruto': Decimal('0.0'), 'total_liquido': Decimal('0.0'), 'total_quantidade': 0}})

            campus_siape = UnidadeOrganizacional.objects.siape().filter(
                pk__in=ContraCheque.objects.ativos()
                .fita_espelho()
                .filter(mes__in=meses, ano__ano=int(request.POST['periodo'][2:]), servidor_setor_lotacao__uo__isnull=False)
                .values_list('servidor_setor_lotacao__uo', flat=True)
            )
            for c in campus_siape:
                contabilidade[c] = {}
                for numero_mes, _nome_mes in meses_list:
                    contabilidade[c].update({numero_mes: {}})
                    ccrs_por_campus = (
                        ContraCheque.objects.ativos()
                        .fita_espelho()
                        .filter(
                            mes=numero_mes,
                            ano__ano=int(request.POST['periodo'][2:]),
                            servidor_setor_lotacao__uo=c,
                        )
                    )

                    if request.POST['situacao']:
                        ccrs_por_campus = ccrs_por_campus.filter(servidor_situacao=request.POST['situacao'])

                    contabilidade[c][numero_mes]['bruto'] = Decimal('0.0')
                    bruto = ccrs_por_campus.aggregate(Sum('bruto'))['bruto__sum'] or Decimal('0.0')
                    contabilidade[c][numero_mes]['bruto'] += bruto
                    totais[numero_mes]['total_bruto'] += bruto

                    contabilidade[c][numero_mes]['liquido'] = Decimal('0.0')
                    liquido = ccrs_por_campus.aggregate(Sum('liquido'))['liquido__sum'] or Decimal('0.0')
                    contabilidade[c][numero_mes]['liquido'] += liquido

                    totais[numero_mes]['total_liquido'] += liquido

                    contabilidade[c][numero_mes]['quantidade'] = ccrs_por_campus.count()

                    if not totais[numero_mes].get('total_quantidade'):
                        totais[numero_mes]['total_quantidade'] = Decimal('0.0')
                    totais[numero_mes]['total_quantidade'] += ccrs_por_campus.count()

                    contabilidade[c][numero_mes]['url'] = (
                        '/contracheques/bruto_liquido_por_campus_detalhado/?campus={}&periodo={}{}&situacao={}'.format(
                            str(c.id), f'{numero_mes:2d}', request.POST['periodo'][2:], request.POST['situacao']
                        )
                    )
                    totais[numero_mes]['url'] = '/contracheques/bruto_liquido_por_campus_detalhado/?campus={}&periodo={}{}&situacao={}'.format(
                        str(c.id), f'{numero_mes:2d}', request.POST['periodo'][2:], request.POST['situacao']
                    )

            c = 'Sem Campus'
            contabilidade[c] = {}
            for numero_mes, _nome_mes in meses_list:
                contabilidade[c].update({numero_mes: {}})
                ccrs_sem_campus = (
                    ContraCheque.objects.ativos()
                    .fita_espelho()
                    .filter(
                        mes=numero_mes,
                        ano__ano=int(request.POST['periodo'][2:]),
                        servidor_setor_lotacao__isnull=True,
                    )
                )

                if request.POST['situacao']:
                    ccrs_sem_campus = ccrs_sem_campus.filter(servidor_situacao=request.POST['situacao'])

                contabilidade[c][numero_mes]['bruto'] = Decimal('0.0')
                bruto = ccrs_sem_campus.aggregate(Sum('bruto'))['bruto__sum'] or Decimal('0.0')
                contabilidade[c][numero_mes]['bruto'] += bruto
                totais[numero_mes]['total_bruto'] += bruto

                contabilidade[c][numero_mes]['liquido'] = Decimal('0.0')
                liquido = ccrs_sem_campus.aggregate(Sum('liquido'))['liquido__sum'] or Decimal('0.0')
                contabilidade[c][numero_mes]['liquido'] += liquido
                totais[numero_mes]['total_liquido'] += liquido

                contabilidade[c][numero_mes]['quantidade'] = ccrs_sem_campus.count()
                totais[numero_mes]['total_quantidade'] += ccrs_sem_campus.count()
                contabilidade[c][numero_mes]['url'] = '/contracheques/bruto_liquido_por_campus_detalhado/?campus={}&periodo={}{}&situacao={}'.format(
                    'todos', f'{numero_mes:2d}', request.POST['periodo'][2:], request.POST['situacao']
                )

                totais[numero_mes]['url'] = '/contracheques/bruto_liquido_por_campus_detalhado/?campus={}&periodo={}{}&situacao={}'.format(
                    'todos', f'{numero_mes:2d}', request.POST['periodo'][2:], request.POST['situacao']
                )

            return render('contracheques/templates/bruto_liquido_por_campus.html', locals())
    else:
        form = FormClass()
    return locals()


@rtr('contracheques/templates/bruto_liquido_por_campus_detalhado.html')
@permission_required('contracheques.pode_ver_contracheques_detalhados')
def bruto_liquido_por_campus_detalhado(request):
    title = 'Relatório de Gastos Bruto/Líquido Detalhado por Campus'
    user = request.user
    id_campus = request.GET.get('campus')
    periodo = request.GET.get('periodo')
    if not id_campus:
        return httprr('..', 'Campus não informado.', 'error')
    if not periodo:
        return httprr('..', 'Período não informado.', 'error')
    periodo = '{}/{}'.format(request.GET['periodo'][:2], request.GET['periodo'][2:])

    if id_campus == 'todos':
        campus = 'Todos'
        queryset = ContraCheque.objects.ativos().fita_espelho().filter(mes=int(periodo[:2]), ano__ano=int(request.GET['periodo'][2:]))

    elif id_campus == '0':
        campus = 'Sem Campus'
        queryset = (
            ContraCheque.objects.ativos()
            .fita_espelho()
            .filter(
                mes=int(periodo[:2]),
                ano__ano=int(request.GET['periodo'][2:]),
                servidor_setor_lotacao__isnull=True,
            )
        )

    else:
        campus = UnidadeOrganizacional.objects.siape().get(id=int(id_campus))
        queryset = (
            ContraCheque.objects.ativos()
            .fita_espelho()
            .filter(
                mes=int(periodo[:2]),
                ano__ano=int(request.GET['periodo'][2:]),
                servidor_setor_lotacao__uo=campus,
            )
        )

    if request.GET.get('situacao'):
        queryset = queryset.filter(servidor_situacao=request.GET['situacao'])

    # Django_Table2 Report
    # Primeiro define-se os fields que irão compor a table
    fields = ('servidor.pessoa_fisica.nome', 'servidor_situacao', 'servidor_setor_lotacao', 'servidor.cargo_emprego', 'bruto', 'liquido')
    # Adiciona Fields customizados se existirem
    custom_fields = {
        'matricula': LinkColumn(
            'servidor',
            kwargs={'servidor_matricula': Accessor('servidor.matricula')},
            verbose_name='Matrícula',
            accessor=Accessor('servidor.matricula'),
        )
    }
    # A sequencia em que os campos serão exibidos, lembrando que sem essa sequence os campos customizados serão criados no fim
    sequence = ['matricula']
    # cria a tabela a partir do dicionario com as informacoes
    table = get_table(queryset=queryset, fields=fields, sequence=sequence, custom_fields=custom_fields)
    # metodo para criar totalizadores no fim da pagina. Defini-se qual
    table.add_sum_table_foot('bruto')
    table.add_sum_table_foot('liquido')
    if request.GET.get('relatorio', None):
        return tasks.table_export(request.GET.get('relatorio', None), *table.get_params())

    return locals()


@rtr()
@permission_required('contracheques.pode_ver_contracheques_agrupados')
def titulacao_por_contra_cheque(request):
    title = 'Titulação dos Servidores com Base nos Contracheques'
    form = TitulacoesServidoresPorContracheques(request.GET or None)
    if form.is_valid():
        mes = int(request.GET['periodo'][:2])
        ano = int(request.GET['periodo'][2:])
        contracheques = (
            ContraCheque.objects.ativos()
            .fita_espelho()
            .filter(
                mes=mes,
                ano__ano=ano,
                servidor_situacao__codigo__in=Situacao.situacoes_servidores_de_carreira(),
            )
            .order_by('servidor_situacao', 'servidor_titulacao', 'servidor__pessoa_fisica__nome')
        )
        subtitulo_grafico = 'Todos os Servidores'
        if 'categoria' in request.GET and request.GET['categoria'] != 'todos':
            if request.GET['categoria'] == 'docente':
                contracheques = contracheques.filter(servidor__eh_docente=True)
                subtitulo_grafico = 'Todos os Docentes'
            elif request.GET['categoria'] == 'tecnico_administrativo':
                contracheques = contracheques.filter(servidor__eh_tecnico_administrativo=True)
                subtitulo_grafico = 'Todos os Técnicos Administrativos'

        if request.GET.get('situacao'):
            situacao = Situacao.servidores_de_carreira.get(pk=int(request.GET['situacao']))
            contracheques = contracheques.filter(servidor_situacao=situacao)
            subtitulo_grafico += f' - {situacao.nome.capitalize()}'
        fields = (
            'servidor',
            'servidor_titulacao',
            'servidor_cargo_emprego',
            'servidor_nivel_padrao',
            'servidor_setor_lotacao',
            'servidor_situacao',
        )
        table_servidores_por_titulacao = get_table(queryset=contracheques, fields=fields, per_page_field=100)
        if request.GET.get('relatorio', None):
            return tasks.table_export(request.GET.get('relatorio', None), *table_servidores_por_titulacao.get_params())

        dados_grafico_por_tipo = list(
            contracheques.filter(servidor_titulacao__isnull=False)
            .order_by('servidor_titulacao__nome')
            .values_list('servidor_titulacao__nome')
            .annotate(titulacoes_contagem=Count('servidor_titulacao__nome'))
        )
        dados_grafico_por_tipo.append(('Sem Titulação', contracheques.filter(servidor_titulacao__isnull=True).count()))

        grafico1 = PieChart(
            'grafico1',
            title='Quantidade de servidores por titulação',
            subtitle=subtitulo_grafico,
            minPointLength=0,
            data=dados_grafico_por_tipo,
        )
    return locals()


@rtr('contracheques/templates/titulacoes_divergentes.html')
@group_required(['Coordenador de Gestão de Pessoas', 'Coordenador de Gestão de Pessoas Sistêmico'])
def servidores_com_titulacao_dispar(request):
    contracheques = ContraCheque.get_servidores_com_titulacao_dispar()
    return locals()


@rtr()
@login_required
def verificar_contra_cheque(request, servidor_pk):
    servidor = get_object_or_404(Servidor, pk=servidor_pk)
    title = f'Contracheques do servidor {servidor}'
    if not ContraCheque.objects.ativos().fita_espelho().filter(servidor=servidor).exists() or not ContraCheque.objects.ativos().fita_espelho().filter(
        servidor=servidor
    ).first().pode_ver(request):
        raise PermissionDenied('Acesso negado!')

    form = ConsultaContraChequeForm()

    if request.method == 'POST':
        form = ConsultaContraChequeForm(request.POST)
        if form.is_valid():
            # verifica se o usuário escolheu um mês específico
            if int(request.POST['mes']) != 0:
                mes = int(request.POST['mes'])
                ano = Ano.objects.get(ano=request.POST['ano'])

                cc = ContraCheque.objects.ativos().fita_espelho().filter(mes=mes, ano=ano, servidor=servidor)

                if not cc.exists():
                    # caso não exista cc padrao (fita espelho), verifica se existe via ws
                    cc = ContraCheque.objects.ativos().fita_espelho().filter(mes=mes, ano=ano, servidor=servidor)

                if cc.exists() and cc[0].pode_ver(request):
                    cc = cc[0]
                    possui_beneficiarios = ContraChequeRubrica.objects.filter(
                        contra_cheque__excluido=False,
                        contra_cheque__tipo_importacao=ContraCheque.IMPORTACAO_FITA_ESPELHO,
                        contra_cheque=cc,
                        beneficiario__isnull=False,
                    ).count()
                    rendimentos = ContraChequeRubrica.objects.filter(
                        contra_cheque__excluido=False,
                        contra_cheque__tipo_importacao=ContraCheque.IMPORTACAO_FITA_ESPELHO,
                        contra_cheque=cc,
                        tipo__nome='Rendimento',
                    )
                    rendimentos_rows = rendimentos.count() + 1
                    descontos = ContraChequeRubrica.objects.filter(
                        contra_cheque__excluido=False,
                        contra_cheque__tipo_importacao=ContraCheque.IMPORTACAO_FITA_ESPELHO,
                        contra_cheque=cc,
                        tipo__nome='Desconto',
                    )
                    descontos_rows = descontos.count() + 1
                else:
                    cc = rendimentos = descontos = []
            else:
                series = []
                values_list = (
                    ContraCheque.objects.ativos()
                    .fita_espelho()
                    .filter(ano__ano=request.POST['ano'])
                    .order_by('-ano', 'mes')
                    .values_list('mes', 'ano__ano')
                )
                tupla_mes_ano = []

                for vl in values_list:
                    if vl not in tupla_mes_ano:
                        tupla_mes_ano.append(vl)

                contracheques = OrderedDict()
                mes_ano = [f'{Meses.get_mes(t[0])}/{t[1]}' for t in tupla_mes_ano]
                for ma in mes_ano:
                    cc = (
                        ContraCheque.objects.ativos()
                        .fita_espelho()
                        .filter(
                            mes=Meses.get_numero(ma.split('/')[0]),
                            ano__ano=ma.split('/')[1],
                            servidor=servidor,
                        )
                    )

                    # O form detecta que existem contracheques, mas não necessariamente serão os contracheques para o servidor logado
                    if cc.exists() and cc[0].pode_ver(request):
                        cc = cc[0]
                        series.append([ma, float(cc.liquido or 0), float(cc.desconto or 0), float(cc.bruto or 0)])
                        contracheques[ma] = {'queryset': cc.contrachequerubrica_set.all(), 'total': cc.liquido}

                grafico = LineChart(
                    'grafico',
                    title='Demonstrativo Anual de Ganhos e Gastos',
                    data=series,
                    groups=['Líquido', 'Desconto', 'Bruto'],
                    yAxis_title_text='R$',
                    plotOptions_line_dataLabels_enable=True,
                    plotOptions_line_enableMouseTracking=True,
                )

                cc = rendimentos = descontos = []

    return locals()


@rtr('contracheques/templates/verificar_contra_cheque.html')
@permission_required('contracheques.pode_ver_contracheques_detalhados')
def detalhar_contra_cheque(request, id):
    user = request.user
    if user.is_superuser or user.has_perm('contracheques.pode_ver_contracheques_agrupados'):
        # aqui não precisamos restringir a contracheques ativos, pois necessitamos mostrar detalhamento de contracheque inativos também
        cc = ContraCheque.objects.get(id=int(id))
        possui_beneficiarios = ContraChequeRubrica.objects.filter(
            contra_cheque__excluido=False,
            contra_cheque__tipo_importacao=ContraCheque.IMPORTACAO_FITA_ESPELHO,
            contra_cheque=cc,
            beneficiario__isnull=False,
        ).count()
        rendimentos = ContraChequeRubrica.objects.filter(contra_cheque__excluido=False, contra_cheque=cc, tipo__nome='Rendimento')
        rendimentos_rows = rendimentos.count() + 1
        descontos = ContraChequeRubrica.objects.filter(contra_cheque__excluido=False, contra_cheque=cc, tipo__nome='Desconto')
        descontos_rows = descontos.count() + 1
        return locals()
    raise PermissionDenied('Acesso negado!')


@rtr()
@permission_required('contracheques.pode_ver_contracheques_agrupados')
def verificar_bruto(request):
    FormClass = PeriodoAnoUOContraChequeFactory()
    form = FormClass(request.POST or None)
    title = 'Bruto Anual por Situação'
    if form.is_valid():
        situacoes = Situacao.situacoes_usadas_no_instituto()
        ccs = ContraCheque.objects.ativos().fita_espelho().filter(ano__ano=request.POST['periodo'])

        if request.POST['uo'] != 'TODAS_UOS':
            ccs = ccs.filter(servidor_setor_lotacao__uo__equivalente__pk=int(request.POST['uo']))

        if request.POST.get('categoria') == 'docente':
            ccs = ccs.filter(servidor__eh_docente=True)
        elif request.POST.get('categoria') == 'tecnico_administrativo':
            ccs = ccs.filter(servidor__eh_tecnico_administrativo=True)

        """
            meses = numero dos meses em ordem crescente

            dados_contracheques = {
                'ativo permanente': {
                    'janeiro': (qtd, valor),
                    'fevereiro': (qtd, valor),
                    ...
                    'dezembro': (qtd, valor),
                    'total': (qtd, valor) --> sempre a última chave
                },
                'cedido': {
                    'janeiro': (qtd, valor),
                    'fevereiro': (qtd, valor),
                    ...
                    'dezembro': (qtd, valor),
                    'total': (qtd, valor) --> sempre a última chave
                },
                ...
            }
        """

        meses = ccs.order_by('mes').values_list('mes', flat=True).distinct()
        dados_contracheques = OrderedDict()
        #
        table_head = ['Situação']
        #
        for situacao in situacoes:
            dados_contracheques[situacao.nome] = OrderedDict()  # manter ordem de insercao (meses e depois 'total')
            total_qtd = 0
            total_bruto = Decimal('0.0')
            for mes in meses:  # precisa estah em ordem crescente (1, ..., 12)
                #
                mes_extenso = Meses.get_mes(mes)
                #
                situacao_mes_qtd = ccs.filter(mes=mes, servidor_situacao=situacao).count()
                situacao_mes_bruto = ccs.filter(mes=mes, servidor_situacao=situacao).aggregate(Sum('bruto'))['bruto__sum'] or Decimal('0.0')
                #
                dados_contracheques[situacao.nome][mes] = (situacao_mes_qtd, situacao_mes_bruto)
                #
                total_qtd += situacao_mes_qtd
                total_bruto += situacao_mes_bruto
                #
                if mes_extenso not in table_head:
                    table_head.append(mes_extenso)
                    #
            dados_contracheques[situacao.nome]['total'] = (total_qtd, total_bruto)
        #
        table_head.append('Total')
        #
        for situacao, dados in list(dados_contracheques.items()):
            excluir = True
            for valor in list(dados.values()):
                if valor[1] > 0.0:
                    excluir = False
                    break
            if excluir:
                dados_contracheques.pop(situacao)

    return locals()


def consignataria_csv(request):
    if not request.user.is_superuser:
        raise PermissionDenied

    ano = int(request.GET['ano'])
    mes = int(request.GET['mes'])
    out = [
        [
            'ano',
            'mes',
            'matricula',
            'ativo',
            'situacao',
            'nome',
            'email',
            'telefone',
            'endereco',
            'categoria',
            'campus',
            'banco',
            'agencia',
            'conta_corrente',
            'foto_url',
            'rendimento_bruto',
            'valor_auxilio_alimentacao',
            'valor_saude_suplementar',
            'valor_desconto_natalino',
        ]
    ]

    def _get_valor_auxilio_alimentacao(cc):
        ccr = cc.contrachequerubrica_set.filter(rubrica__nome='AUXILIO-ALIMENTACAO')
        return ccr and ccr[0].valor or 0

    def _get_valor_saude_suplementar(cc):
        ccr = cc.contrachequerubrica_set.filter(rubrica__nome='PER CAPITA - SAUDE SUPLEMENTAR')
        return ccr and ccr[0].valor or 0

    def _get_desconto_natalino(cc):
        ccr = cc.contrachequerubrica_set.filter(rubrica__nome='ADIANT.GRATIF.NATALINA/ATIVO', tipo__nome='Desconto')
        return ccr and ccr[0].valor or 0

    for cc in (
        ContraCheque.objects.ativos()
        .fita_espelho()
        .filter(ano__ano=ano, mes=mes)
        .select_related('contrachequerubrica', 'servidor', 'servidor__situacao', 'servidor__pagto_banco', 'cargo_emprego__grupo_cargo_emprego')
    ):
        out.append(
            [
                ano,
                mes,
                cc.servidor.matricula,
                cc.servidor.ativo and 1 or 0,
                cc.servidor.situacao.nome_siape,
                cc.servidor.pessoa_fisica.nome,
                cc.servidor.email_institucional or cc.servidor.email_pessoal,
                cc.servidor.pessoa_fisica.telefones_pessoais,
                cc.servidor.pessoa_fisica.endereco,
                cc.servidor.categoria,
                cc.servidor.campus_exercicio_siape,
                cc.servidor.pessoa_fisica.pagto_banco.nome,
                cc.servidor.pessoa_fisica.pagto_agencia,
                cc.servidor.pessoa_fisica.pagto_ccor,
                cc.servidor.get_foto_75x100_url(),
                cc.bruto or 0,
                _get_valor_auxilio_alimentacao(cc),
                _get_valor_saude_suplementar(cc),
                _get_desconto_natalino(cc),
            ]
        )
    return CsvResponse(out, name=f'suap_{ano - 2000}{str(mes).zfill(2)}')


#########
# admin #
#########


def handle_uploaded_file(arquivo, tipo):
    mes_ano = ''
    for linha in arquivo.chunks():
        if tipo == 'servidores':
            mes_ano = int(linha[45:51])
        else:
            mes_ano = int(linha[52:58])
        break

    nome_arquivo = tipo + str(mes_ano) + '.txt'
    if arquivo.name.split('_')[0] == 'test':
        nome_arquivo = 'test_' + tipo + str(mes_ano) + '.txt'

    destination_dir = 'tmp/contracheques/arquivos_contracheque/'
    destination = os.path.join(destination_dir, nome_arquivo)
    default_storage.save(destination, arquivo)


@rtr()
@permission_required('rh.pode_gerenciar_extracao_siape')
def contracheque_importar_do_arquivo(request):
    title = 'Importar Contracheques do Arquivo'
    FormClass = GetImportarArquivoContraChequeForm()
    historico = Log.objects.filter(
        app='CC', titulo__in=['Importação de Fita Espelho servidores', 'Importação de Fita Espelho pensionistas']
    ).order_by('-horario', 'titulo')[:10]
    if request.method == 'POST':
        form = FormClass(request.POST, request.FILES)
        if form.is_valid():
            handle_uploaded_file(form.files['arquivo'], request.POST['tipo'])
            return httprr(request.path, 'Upload de Arquivo {} feito com sucesso.'.format(request.POST['tipo']))
    else:
        form = FormClass()
    return locals()


@rtr()
@permission_required('contracheques.pode_ver_contracheques_agrupados')
def rubrica_por_campus_agrupados(request):
    user = request.user

    FormClass = RubricaPorCampusAgrupadasFactory()
    title = 'Relatório de Gastos por Rubrica Agrupados'

    if request.method == 'POST':
        form = FormClass(request.POST)

        if form.is_valid():
            tipo = ''
            categoria = ''
            tipo_filtro = form.cleaned_data.get('tipo')
            situacao_filtro = form.cleaned_data.get('situacao')
            categoria_filtro = form.cleaned_data.get('categoria')
            agrupamentos_rubricas_filtro = form.cleaned_data.get('agrupamentos_rubricas')
            periodo_filtro = form.cleaned_data.get('periodo')
            mes = int(periodo_filtro[:2])
            ano = int(periodo_filtro[2:])
            if mes:
                periodo = f'{mes}/{ano}'
                meses = [mes]
                meses_list = [((mes, Meses.get_mes(mes)))]
            else:
                periodo = f'{ano}'
                meses = ContraCheque.objects.ativos().fita_espelho().filter(ano__ano=ano).order_by('mes').values_list('mes', flat=True).distinct()
                set_meses = []
                for mes in meses:
                    if mes not in set_meses:
                        set_meses.append(mes)
                meses_list = [(mes, Meses.get_mes(mes)) for mes in set_meses]

            pode_detalhar = request.user.has_perm('contracheques.pode_ver_contracheques_detalhados')

            agrupamentos_rubricas = form.cleaned_data['agrupamentos_rubricas']

            totais = {}
            for numero_mes, _nome_mes in meses_list:
                totais.update({numero_mes: {'total_valor': Decimal('0.0')}})

            campus_siape = UnidadeOrganizacional.objects.siape().filter(
                pk__in=ContraChequeRubrica.objects.filter(
                    contra_cheque__excluido=False,
                    contra_cheque__tipo_importacao=ContraCheque.IMPORTACAO_FITA_ESPELHO,
                    contra_cheque__mes__in=meses,
                    contra_cheque__ano__ano=ano,
                    rubrica__in=agrupamentos_rubricas.rubricas.all(),
                    contra_cheque__servidor_setor_lotacao__uo__isnull=False,
                ).values_list('contra_cheque__servidor_setor_lotacao__uo', flat=True)
            )

            ccrs = ContraChequeRubrica.objects.filter(
                contra_cheque__excluido=False,
                contra_cheque__tipo_importacao=ContraCheque.IMPORTACAO_FITA_ESPELHO,
                contra_cheque__mes__in=meses,
                contra_cheque__ano__ano=ano,
                rubrica__in=agrupamentos_rubricas.rubricas.all(),
            )
            if situacao_filtro:
                ccrs = ccrs.filter(contra_cheque__servidor_situacao=situacao_filtro)

            if tipo_filtro:
                tipo = f'({tipo_filtro.upper()})'
                ccrs = ccrs.filter(tipo__nome=tipo_filtro)

            if categoria_filtro == 'docente':
                categoria = categoria_filtro.title()
                ccrs = ccrs.filter(contra_cheque__servidor__eh_docente=True)
            elif categoria_filtro == 'tecnico_administrativo':
                categoria = categoria_filtro.title()
                ccrs = ccrs.filter(contra_cheque__servidor__eh_tecnico_administrativo=True)

            ccrs_dados = (
                ccrs.values_list(
                    'contra_cheque__servidor_setor_lotacao__uo__setor__sigla',
                    'contra_cheque__servidor_setor_lotacao__uo',
                    'tipo__codigo',
                    'contra_cheque__mes',
                )
                .annotate(soma=Sum('valor'), qtd=Count('id'))
                .order_by(
                    'contra_cheque__servidor_setor_lotacao__uo__setor__sigla',
                    'contra_cheque__servidor_setor_lotacao__uo',
                    'contra_cheque__mes',
                    'tipo__codigo',
                )
            )

            contabilidade = {'Sem Campus': {}}
            for numero_mes, _nome_mes in meses_list:
                contabilidade['Sem Campus'][numero_mes] = {'valor': Decimal('0.0'), 'quantidade': 0}
            for uo_sigla, uo_id, tipo_cc, mes, valor, qtd in ccrs_dados:
                if uo_sigla is None:
                    uo_sigla = 'Sem Campus'
                    uo_id = 0

                if uo_sigla not in contabilidade:
                    contabilidade[uo_sigla] = {}

                if mes not in contabilidade[uo_sigla]:
                    contabilidade[uo_sigla][mes] = {'valor': Decimal('0.0'), 'quantidade': 0}

                if tipo_cc == '1':
                    contabilidade[uo_sigla][mes]['valor'] += valor
                elif tipo_cc == '2':
                    contabilidade[uo_sigla][mes]['valor'] -= valor

                contabilidade[uo_sigla][mes]['quantidade'] += qtd

                contabilidade[uo_sigla][mes]['url'] = (
                    '/contracheques/rubrica_por_campus_agrupados_detalhado/?campus={}&agrupamentos_rubricas={}&periodo={}{}&tipo={}&situacao={}'.format(
                        uo_id,
                        agrupamentos_rubricas_filtro.id,
                        f'{mes:2d}',
                        ano,
                        tipo_filtro,
                        situacao_filtro,
                    )
                )

            total_campus = {}
            for campus in campus_siape:
                total_campus[campus.setor.sigla] = Decimal('0.0')
                for numero_mes, _nome_mes in meses_list:
                    if contabilidade.get(campus.setor.sigla):
                        total_campus[campus.setor.sigla] += contabilidade[campus.setor.sigla][numero_mes]['valor']
                        totais[numero_mes]['total_valor'] += contabilidade[campus.setor.sigla][numero_mes]['valor']

            total_campus['Sem Campus'] = Decimal('0.0')
            for numero_mes, _nome_mes in meses_list:
                total_campus['Sem Campus'] += contabilidade['Sem Campus'][numero_mes]['valor']

                totais[numero_mes]['total_valor'] += contabilidade['Sem Campus'][numero_mes]['valor']
                totais[numero_mes]['url'] = (
                    '/contracheques/rubrica_por_campus_agrupados_detalhado/?campus={}&agrupamentos_rubricas={}&periodo={}{}&tipo={}&situacao={}'.format(
                        'todos',
                        form.cleaned_data['agrupamentos_rubricas'].id,
                        f'{numero_mes:2d}',
                        ano,
                        tipo_filtro,
                        situacao_filtro,
                    )
                )

            total = Decimal('0.0')
            for valor in list(total_campus.values()):
                total += valor

            return render('contracheques/templates/tela_rubrica_por_campus_agrupados.html', locals())
    else:
        form = FormClass()
    return locals()


@rtr('contracheques/templates/tela_rubrica_por_campus_detalhado.html')
@permission_required('contracheques.pode_ver_contracheques_detalhados')
def rubrica_por_campus_agrupados_detalhado(request):
    title = 'Relatório de Gastos Rubrica Detalhado por Campus'
    user = request.user
    if request.GET.get('campus'):
        id_campus = request.GET['campus']
        agrupamentos_rubricas = AgrupamentoRubricas.objects.get(id=request.GET['agrupamentos_rubricas'])
        periodo = '{}/{}'.format(request.GET['periodo'][:2], request.GET['periodo'][2:])

        if id_campus == 'todos':
            campus = 'Todos'
            queryset = ContraChequeRubrica.objects.filter(
                contra_cheque__excluido=False,
                contra_cheque__tipo_importacao=ContraCheque.IMPORTACAO_FITA_ESPELHO,
                contra_cheque__mes=int(periodo[:2]),
                contra_cheque__ano__ano=int(request.GET['periodo'][2:]),
                rubrica__in=agrupamentos_rubricas.rubricas.all(),
            )

        elif id_campus == '0':
            campus = 'Sem Campus'
            queryset = ContraChequeRubrica.objects.filter(
                contra_cheque__excluido=False,
                contra_cheque__tipo_importacao=ContraCheque.IMPORTACAO_FITA_ESPELHO,
                contra_cheque__mes=int(periodo[:2]),
                contra_cheque__ano__ano=int(request.GET['periodo'][2:]),
                rubrica__in=agrupamentos_rubricas.rubricas.all(),
                contra_cheque__servidor_setor_lotacao__isnull=True,
            )

        else:
            campus = UnidadeOrganizacional.objects.siape().get(id=int(id_campus))
            queryset = ContraChequeRubrica.objects.filter(
                contra_cheque__excluido=False,
                contra_cheque__tipo_importacao=ContraCheque.IMPORTACAO_FITA_ESPELHO,
                contra_cheque__mes=int(request.GET['periodo'][:2]),
                contra_cheque__ano__ano=int(request.GET['periodo'][2:]),
                rubrica__in=agrupamentos_rubricas.rubricas.all(),
                contra_cheque__servidor_setor_lotacao__uo=campus,
            )

        if request.GET['situacao']:
            try:
                queryset = queryset.filter(contra_cheque__servidor_situacao=request.GET['situacao'])
            except Exception:
                pass

        if request.GET['tipo']:
            queryset = queryset.filter(tipo__nome=request.GET['tipo'])

        # Django_Table2 Report
        # Primeiro define-se os fields que irão compor a table
        fields = (
            'contra_cheque.servidor.pessoa_fisica.nome',
            'contra_cheque.servidor_situacao',
            'contra_cheque.servidor_setor_lotacao',
            'contra_cheque.servidor.cargo_emprego',
            'rubrica',
            'tipo',
            'sequencia',
            'prazo',
            'valor',
        )
        # Adiciona Fields customizados se existirem
        custom_fields = {
            'matricula': LinkColumn(
                'servidor',
                kwargs={'servidor_matricula': Accessor('contra_cheque.servidor.matricula')},
                verbose_name='Matrícula',
                accessor=Accessor('contra_cheque.servidor.matricula'),
            )
        }
        # A sequencia em que os campos serão exibidos, lembrando que sem essa sequence os campos customizados serão criados no fim
        sequence = ['matricula']
        queryset = queryset.select_related(
            'rubrica',
            'tipo',
            'contra_cheque',
            'contra_cheque__servidor',
            'contra_cheque__servidor_situacao',
            'contra_cheque__servidor_setor_lotacao',
            'contra_cheque__servidor__cargo_emprego',
            'contra_cheque__servidor__cargo_emprego__grupo_cargo_emprego',
        )

        # cria a tabela a partir do dicionario com as informacoes
        table = get_table(queryset=queryset, fields=fields, sequence=sequence, custom_fields=custom_fields)
        # metodo para criar totalizadores no fim da pagina. Defini-se qual
        table.add_sum_table_foot('valor', conditions={'+': {'tipo__codigo': '1'}, '-': {'tipo__codigo': '2'}})
        if request.GET.get('relatorio', None):
            return tasks.table_export(request.GET.get('relatorio', None), *table.get_params())

        return locals()
    else:
        raise PermissionDenied


# View que se conecta a view rh.views.servidor
@receiver(rh_servidor_view_tab)
def servidor_view_tab_signal(sender, request, servidor, verificacao_propria, eh_chefe, **kwargs):
    pode_ver_contracheques_servidor = request.user.has_perm('rh.pode_ver_contracheques_servidor') or verificacao_propria

    if pode_ver_contracheques_servidor:
        contracheque = ContraCheque.objects.ativos().fita_espelho().filter(servidor=servidor).order_by('-ano__ano', '-mes')
        if not contracheque.exists():
            # se não existir cc via fita espelho, verifica se existe via ws
            contracheque = ContraCheque.objects.ativos().webservice().filter(servidor=servidor).order_by('-ano__ano', '-mes')

        possui_beneficiarios = 0
        rendimentos = descontos = []

        if contracheque.exists() and contracheque[0].pode_ver(request):
            contracheque = contracheque[0]
            possui_beneficiarios = ContraChequeRubrica.objects.filter(
                contra_cheque__excluido=False,
                contra_cheque__tipo_importacao=ContraCheque.IMPORTACAO_FITA_ESPELHO,
                contra_cheque=contracheque,
                beneficiario__isnull=False,
            ).count()
            rendimentos = ContraChequeRubrica.objects.filter(
                contra_cheque__excluido=False,
                contra_cheque__tipo_importacao=ContraCheque.IMPORTACAO_FITA_ESPELHO,
                contra_cheque=contracheque,
                tipo__nome='Rendimento',
            )
            descontos = ContraChequeRubrica.objects.filter(
                contra_cheque__excluido=False,
                contra_cheque__tipo_importacao=ContraCheque.IMPORTACAO_FITA_ESPELHO,
                contra_cheque=contracheque,
                tipo__nome='Desconto',
            )

        return render_to_string(
            template_name='contracheques/templates/servidor_view_tab.html',
            context={
                'lps_context': {'nome_modulo': 'contracheques'},
                'servidor': servidor,
                'contracheque': contracheque,
                'possui_beneficiarios': possui_beneficiarios,
                'rendimentos': rendimentos,
                'descontos': descontos,
            },
            request=request,
        )
    return False
