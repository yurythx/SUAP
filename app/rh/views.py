import json
import logging
import os
from collections import OrderedDict
from datetime import date, datetime
from decimal import Decimal

from django.apps import apps
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist, PermissionDenied
from django.core.files.storage import default_storage
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Case, Count, F, IntegerField, OuterRef, Q, Subquery, Value, When
from django.db.models.aggregates import Sum
from django.db.models.functions import Coalesce
from django.dispatch import Signal
from django.forms import ValidationError
from django.forms.widgets import Select
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404
from django.template.defaultfilters import pluralize
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_POST
from django_tables2.columns.base import Column
from django_tables2.columns.datecolumn import DateColumn
from django_tables2.columns.linkcolumn import LinkColumn
from django_tables2.utils import Accessor
from sentry_sdk import capture_exception

from comum.models import (
    APIExterna,
    Configuracao,
    ConfiguracaoImpressaoDocumento,
    DocumentoControle,
    DocumentoControleTipo,
    Log,
    Municipio,
    PessoaEndereco,
    PrestadorServico,
    TipoCarteiraFuncional,
    Vinculo,
)
from comum.utils import get_sigla_reitoria, get_uo, get_uo_siape
from djtools import layout, tasks
from djtools.choices import Meses, campos, campos_nao_agrupaveis, filtrar_campos_validos
from djtools.html.graficos import ColumnChart, GroupedColumnChart, PieChart
from djtools.lps import lps
from djtools.storages import AWSUploadBackend, LocalUploadBackend, is_remote_storage
from djtools.tables import get_table
from djtools.templatetags.filters.utils import format_
from djtools.utils import (
    JsonResponse,
    XlsResponse,
    documento,
    get_qtd_dias_por_ano,
    get_tabs,
    group_required,
    httprr,
    mask_cnpj,
    mask_cpf,
    mask_numbers,
    permission_required,
    render,
    retira_acentos,
    rtr,
    upload_em_pdf,
)
from djtools.utils.ldap import get_ldap_conf
from rh import tasks as rh_tasks
from rh.forms import (
    UnificarPessoasForm,
    AdicionarHorarioAcaoSaudeForm,
    AdicionarHorarioAfastamentoForm,
    AfastamentosServidoresForm,
    AgendarAtendimentoForm,
    AniversarianteForm,
    AtualizarDadosAvaliadorForm,
    BasesLegaisSetorForm,
    BuscarPessoaJuridicaApiRFBForm,
    DefinirAreasVinculacaoWizard,
    DocentesPorDisciplinaFiltroForm,
    DocumentacaoExigidaUploadForm,
    EditarHorarioAfastamentoForm,
    EditarServidorCargoEmpregoAreaForm,
    EquivalenciaSetorForm,
    GetBuscarServidorForm,
    ImportacaoPJForm,
    ImportarArquivoSCDPForm,
    ImportarServidorWSForm,
    IndeferirProcessoAfastamentoParcialRHForm,
    ObterDadosCompletaresPessoaForm,
    PessoaFisicaAlterarSenhaPontoForm,
    PessoaFisicaInformacoesDigitaisFracasForm,
    RejeitarSolicitacaoAlteracaoFotoForm,
    RelatorioAfastamentosCriticosForm,
    SalvarProcessoAfastamentoForm,
    ServidoresParaCapacitacaoPorSetorForm,
    ServidoresPorAreaFiltroForm,
    ServidorFuncaoFormFactory,
    ServidorInformacoesPessoaisForm,
    SetorJornadaHistoricoFormFactory,
    SetorRaizFormFactory,
    ViagensPorCampusForm,
    WebserviceSIAPEForm,
)
from rh.importador_ws import ImportadorWs
from rh.models import (
    PCA,
    PRIVATE_ROOT_DIR,
    AcaoSaude,
    AfastamentoSiape,
    AgendaAtendimentoHorario,
    AlertaGestaoPessoa,
    AlertaGestaoPessoaVisualizacao,
    ArquivoUnico,
    Avaliador,
    CargaHorariaReduzida,
    DocumentacaoExigida,
    Funcao,
    HorarioAgendado,
    HorarioSemanal,
    IndicadoresPublicos,
    PessoaFisica,
    PessoaInfoComplementar,
    PessoaJuridica,
    PessoaJuridicaContato,
    QuantitativoCargoClassePorCampus,
    Servidor,
    ServidorAfastamento,
    ServidorFuncaoHistorico,
    ServidorOcorrencia,
    ServidorReativacaoPermanente,
    ServidorReativacaoTemporaria,
    ServidorSetorHistorico,
    ServidorSetorLotacaoHistorico,
    Setor,
    SetorJornadaHistorico,
    Situacao,
    SolicitacaoAlteracaoFoto,
    Titulacao,
    UnidadeOrganizacional,
    Viagem,
)
from rh.pdf import imprime_carteira_funcional, imprime_cracha
from rh.utils import agrupar_por_matricula, estah_no_pgd_hoje_pgd1_pgd2, estah_no_pgd_hoje_pgd2

# Sinais utilizados na composição de views complexas, com isso, podemos criar um vínculo fraco entre RH e outras apps
from suap import nomenclatura

logger = logging.getLogger(__name__)

rh_servidor_view_tab = Signal()  # providing_args=["request", "servidor", "verificacao_propria", "eh_chefe"]


@layout.atribuidos_a_meus_grupos()
def index_atribuidos_a_meus_grupos(request):
    pendencias = []
    eh_rh_sistemico = request.user.has_group_cached('Coordenador de Gestão de Pessoas Sistêmico', ignore_groups_if_superuser=False)
    eh_rh_campus = request.user.has_group_cached('Coordenador de Gestão de Pessoas', ignore_groups_if_superuser=False)
    if eh_rh_sistemico or eh_rh_campus:
        qtd_processos_afastamento_parcial_a_validar_rh = CargaHorariaReduzida.get_processos_rh_a_validar(request.user).count()
        if qtd_processos_afastamento_parcial_a_validar_rh:
            pendencias.append(
                {
                    'titulo': f'Processo{pluralize(qtd_processos_afastamento_parcial_a_validar_rh)} de Alteração de Carga Horária',
                    'subtitulo': 'a validar',
                    'qtd': qtd_processos_afastamento_parcial_a_validar_rh,
                    'url': '/admin/rh/cargahorariareduzida/?tab=tab_processos_pendentes_de_validacao_rh',
                }
            )

        if eh_rh_sistemico:
            solicitacoes_pendentes = SolicitacaoAlteracaoFoto.objects.filter(situacao=SolicitacaoAlteracaoFoto.AGUARDANDO_VALIDACAO).count()
        else:
            servidor = request.user.get_relacionamento()
            solicitacoes_pendentes = SolicitacaoAlteracaoFoto.objects.filter(
                solicitante__setor__uo=servidor.setor.uo, situacao=SolicitacaoAlteracaoFoto.AGUARDANDO_VALIDACAO
            ).count()

        if solicitacoes_pendentes:
            pendencias.append(
                {
                    'titulo': f'Solicitaç{pluralize(solicitacoes_pendentes, "ão,ões")} de Alteração de Foto',
                    'subtitulo': 'a validar',
                    'qtd': solicitacoes_pendentes,
                    'url': '/admin/rh/solicitacaoalteracaofoto/?tab=tab_aguardando_validacao',
                }
            )

        if eh_rh_sistemico:
            qtd_solicitacoes_reativacao_temporaria = ServidorReativacaoTemporaria.objects.filter(
                situacao=ServidorReativacaoTemporaria.STATUS_SOLICITADA
            ).count()
            if qtd_solicitacoes_reativacao_temporaria:
                pendencias.append(
                    {
                        'titulo': f'Solicitaç{pluralize(qtd_solicitacoes_reativacao_temporaria, "ão,ões")} de Reativação Temporária',
                        'subtitulo': 'aguardando avaliação',
                        'qtd': qtd_solicitacoes_reativacao_temporaria,
                        'url': f'/admin/rh/servidorreativacaotemporaria/?situacao__exact={ServidorReativacaoTemporaria.STATUS_SOLICITADA}',
                    }
                )

            qtd_solicitacoes_reativacao_permanente = ServidorReativacaoPermanente.objects.filter(
                situacao=ServidorReativacaoPermanente.STATUS_SOLICITADA
            ).count()
            if qtd_solicitacoes_reativacao_permanente:
                pendencias.append(
                    {
                        'titulo': f'Solicitaç{pluralize(qtd_solicitacoes_reativacao_permanente, "ão,ões")} de Reativação Permanente',
                        'subtitulo': 'aguardando avaliação',
                        'qtd': qtd_solicitacoes_reativacao_permanente,
                        'url': f'/admin/rh/servidorreativacaopermanente/?situacao__exact={ServidorReativacaoPermanente.STATUS_SOLICITADA}',
                    }
                )
    return pendencias


@layout.quadro('Gestão de Pessoas', icone='users', pode_esconder=True)
def index_quadros(quadro, request):
    eh_rh_sistemico = request.user.has_group_cached('Coordenador de Gestão de Pessoas Sistêmico', ignore_groups_if_superuser=False)
    eh_rh_campus = request.user.has_group_cached('Coordenador de Gestão de Pessoas', ignore_groups_if_superuser=False)
    if eh_rh_sistemico or eh_rh_campus:
        qtd_servidores_sem_setor_suap = Servidor.get_sem_setor_suap().count()
        if qtd_servidores_sem_setor_suap:
            quadro.add_item(
                layout.ItemContador(
                    titulo='Servidor{}'.format(pluralize(qtd_servidores_sem_setor_suap, 'es')),
                    subtitulo='Sem setor SUAP',
                    qtd=qtd_servidores_sem_setor_suap,
                    url='/rh/servidores_sem_setor_suap/',
                )
            )

        qtd_servidores_sem_cargo = Servidor.get_sem_cargo().count()
        if qtd_servidores_sem_cargo:
            quadro.add_item(
                layout.ItemContador(
                    titulo='Servidor{}'.format(pluralize(qtd_servidores_sem_cargo, 'es')),
                    subtitulo='Sem cargo',
                    qtd=qtd_servidores_sem_cargo,
                    url='/rh/servidores_sem_cargo/',
                )
            )

        hoje = datetime.now()
        uo = get_uo(request.user)
        if eh_rh_sistemico and uo and 'edu' in settings.INSTALLED_APPS:
            qtd_docentes_sem_disciplina_ingresso = (
                Servidor.objects.docentes()
                .filter(situacao__codigo=Situacao.ATIVO_PERMANENTE, vinculos__professor__disciplina__isnull=True, setor__uo=uo)
                .count()
            )
            if qtd_docentes_sem_disciplina_ingresso:
                quadro.add_item(
                    layout.ItemContador(
                        titulo=f'Docente{pluralize(qtd_docentes_sem_disciplina_ingresso)} sem disciplina de ingresso',
                        subtitulo=f'{nomenclatura.campus} {uo}',
                        qtd=qtd_docentes_sem_disciplina_ingresso,
                        url=f'/edu/disciplina_ingresso_docentes/?campus={uo.pk}&disciplinas={1}',
                    )
                )

        if eh_rh_sistemico and uo:
            qtd_servidores_sem_area = (
                Servidor.objects.ativos().filter(cargo_emprego__cargoempregoarea__isnull=False, cargo_emprego_area__isnull=True).distinct().count()
            )
            if qtd_servidores_sem_area:
                quadro.add_item(
                    layout.ItemContador(
                        titulo='Servidor{}'.format(pluralize(qtd_servidores_sem_area, 'es')),
                        subtitulo='Sem área',
                        qtd=qtd_servidores_sem_area,
                        url='/rh/servidores_por_area/?com_area_cadastrada=2',
                    )
                )

        if uo:
            servidor_funcao_historico = ServidorFuncaoHistorico.objects.filter(
                setor__uo__equivalente=uo, data_fim_funcao__gte=hoje, setor_suap__isnull=True
            ).exclude(funcao__codigo=Funcao.CODIGO_ESTAGIARIO) | ServidorFuncaoHistorico.objects.filter(
                setor__uo__equivalente=uo, data_fim_funcao__isnull=True, setor_suap__isnull=True
            ).exclude(funcao__codigo=Funcao.CODIGO_ESTAGIARIO)
            qtd_servidor_funcao_historico = servidor_funcao_historico.count()
            if qtd_servidor_funcao_historico:
                uo_siape = UnidadeOrganizacional.objects.siape().filter(equivalente=uo, setor__excluido=False).latest('pk')
                quadro.add_item(
                    layout.ItemContador(
                        titulo='Funções de Servidores sem Setor SUAP',
                        subtitulo=f'{nomenclatura.campus} {uo_siape}',
                        qtd=qtd_servidor_funcao_historico,
                        url=f'/admin/rh/servidorfuncaohistorico/?setoruo={uo_siape.pk}&com_data_fim=False',
                    )
                )

    if request.user.has_perm('rh.view_servidor'):
        quadro.add_item(layout.ItemAcessoRapido(titulo='Servidores', icone='users', url='/admin/rh/servidor/?excluido__exact=0'))
        quadro.add_item(layout.BuscaRapida(titulo='Servidor', url='/admin/rh/servidor/'))

    if request.user.eh_servidor:
        quadro.add_item(layout.ItemAcessoRapido(titulo='SIGEPE', url='https://servidor.sigepe.planejamento.gov.br/SIGEPE-PortalServidor'))

    return quadro


@layout.atribuidos_a_mim()
def index_atribuidos_a_mim(request):
    pendencias = []
    hoje = datetime.date(datetime.now())

    if request.user.eh_servidor or request.user.eh_prestador:
        qs_horarioagendado = HorarioAgendado.objects.filter(solicitante=request.user.get_vinculo(), data_consulta__gte=hoje, cancelado=False)
        if qs_horarioagendado.exists():
            for horario in qs_horarioagendado:
                delta = horario.data_consulta - hoje
                pendencias.append(
                    {
                        'url': '/admin/rh/acaosaude/?acao_saude_ativa=1',
                        'titulo': f'Consulta agendada em {delta.days} dia(s).',
                    }
                )

    return pendencias


@layout.servicos_anonimos()
def servicos_anonimos(request):
    servicos_anonimos = []
    servicos_anonimos.append({'categoria': 'Gestão de Pessoas', 'titulo': 'Indicadores', 'icone': 'chart-line', 'url': '/rh/indicadores_publicos/'})
    return servicos_anonimos


@rtr()
@permission_required('rh.eh_rh_sistemico, comum.is_reitor, comum.is_pro_reitor, comum.is_diretor_geral')
def index(request):
    """
    gráficos:
        1-servidores com vínculo institucional por situação funcional
            1.1-servidores ativos permanentes (docentes e téc) e pensionistas
        2-titulação de ativos permanentes, cedidos e temporários
        3-campus de lotação de ativos permanentes e cedidos
        4-campus de exercício de ativos permanentes e cedidos
        5-servidores por campus de lotação
        6-servidores por campus de exercício

    +
    quadros de referências:
        docentes
        técnicos administrativos
    """
    title = 'Indicadores'

    # verifica se foi repassado algum filtro
    categoria = request.GET.get('categoria', '')

    # obtendo gráficos
    graficos = _get_graficos(categoria)
    if not categoria:
        if 'contracheques' in settings.INSTALLED_APPS:
            mostra_grafico_1_1 = True

    if categoria == 'tecnico_administrativo':
        quadro_referencia_administrativos = Servidor.quadro_referencia_administrativos()

    elif categoria == 'docente':
        texto_explicativo_situacoes_efetivos = 'Efetivos (ativo permanente e cedido)'
        texto_explicativo_situacoes_temporarios = (
            'Temporários (contrato de professor substituto, contrato de professor temporário e contrato temporário)'
        )
        (quadro_referencia_docentes, quadro_referencia_docentes_total) = Servidor.quadro_referencia_docentes()

    inconsistencias = {}
    campus_siape = UnidadeOrganizacional.objects.siape().all()
    efetivos_nao_importados = Servidor.objects.efetivos().filter(vinculos__sistema_origem='')
    efetivos_sem_campus_lotacao = Servidor.objects.efetivos().filter(vinculos__sistema_origem='SIAPE', setor_lotacao__uo=None)
    efetivos_sem_campus_exercicio = Servidor.objects.efetivos().filter(vinculos__sistema_origem='SIAPE', setor_exercicio__uo=None)
    if not campus_siape:
        inconsistencias['campus_siape'] = 1
    if efetivos_nao_importados:
        inconsistencias['efetivos_nao_importados'] = efetivos_nao_importados
    if efetivos_sem_campus_lotacao:
        inconsistencias['efetivos_sem_campus_lotacao'] = efetivos_sem_campus_lotacao
    if efetivos_sem_campus_exercicio:
        inconsistencias['efetivos_sem_campus_exercicio'] = efetivos_sem_campus_exercicio

    try:
        data_ultima_importacao_siape = Log.objects.filter(app='rh').order_by('-horario')[0].horario
    except Exception:
        pass

    return locals()


@rtr()
@permission_required('rh.eh_rh_sistemico, comum.is_reitor, comum.is_pro_reitor, comum.is_diretor_geral')
def quadro_referencia(request):
    title = 'Quadro de referência'
    quadro_referencia_administrativos = Servidor.quadro_referencia_administrativos_novo()
    quantitativo_por_classe = QuantitativoCargoClassePorCampus.objects.values('uo__id', 'uo__sigla', 'cargo_classe__codigo', 'quantidade')
    totais_por_campus = (
        QuantitativoCargoClassePorCampus.objects.filter(uo_id=OuterRef('uo_id'))
        .values('uo_id')
        .annotate(total_cargo_classe=Sum('quantidade'))
        .values('total_cargo_classe')
    )
    quantitativo_por_uo = QuantitativoCargoClassePorCampus.objects.values(
        'uo_id',
        'uo__sigla',
    ).annotate(quantidade=Sum('quantidade'))

    quadro_referencia = {}
    quadro_referencia['total_A'] = 0
    quadro_referencia['total_B'] = 0
    quadro_referencia['total_C'] = 0
    quadro_referencia['total_D'] = 0
    quadro_referencia['total_E'] = 0
    quadro_referencia['total'] = 0
    quadro_referencia['total_q'] = 0
    quadro_referencia['total_q_A'] = 0
    quadro_referencia['total_q_B'] = 0
    quadro_referencia['total_q_C'] = 0
    quadro_referencia['total_q_D'] = 0
    quadro_referencia['total_q_E'] = 0
    quadro_referencia['total_diff'] = 0
    uos = []
    for quadro in quadro_referencia_administrativos:
        id_uo = quadro['setor_lotacao__uo__id']
        uos.append(id_uo)

        quadro_referencia_uo = quantitativo_por_uo.filter(uo_id=id_uo).order_by('uo__sigla').first()
        quadro['total_por_uo'] = quadro_referencia_uo.get('quantidade') if quadro_referencia_uo else 0
        quadro['total_diff'] = quadro.get('total', 0) - quadro['total_por_uo']
        for qtd_por_class in quantitativo_por_classe.filter(uo__id=id_uo):
            quadro[f'total_{qtd_por_class.get("cargo_classe__codigo")}'] = qtd_por_class.get('quantidade')

        quadro_referencia[id_uo] = quadro
        quadro_referencia['total_q_A'] += quadro.get('total_A', 0)
        quadro_referencia['total_q_B'] += quadro.get('total_B', 0)
        quadro_referencia['total_q_C'] += quadro.get('total_C', 0)
        quadro_referencia['total_q_D'] += quadro.get('total_D', 0)
        quadro_referencia['total_q_E'] += quadro.get('total_E', 0)
        quadro_referencia['total_q'] += quadro.get('total_por_uo', 0)
        quadro_referencia['total_A'] += quadro.get('A', 0)
        quadro_referencia['total_B'] += quadro.get('B', 0)
        quadro_referencia['total_C'] += quadro.get('C', 0)
        quadro_referencia['total_D'] += quadro.get('D', 0)
        quadro_referencia['total_E'] += quadro.get('E', 0)
        quadro_referencia['total'] += quadro.get('total', 0)
        quadro_referencia['total_diff'] += quadro['total_diff']

    try:
        data_ultima_importacao_siape = Log.objects.filter(app='rh').order_by('-horario')[0].horario
    except Exception:
        pass

    return locals()


# gráfico 1 - servidores com vínculo institucional por situação funcional
def _grafico1(categoria):
    series1 = []
    for situacao in Situacao.objects.all():
        lista_servidores = Servidor.objects.filter(ativo=True, situacao__codigo=situacao.codigo)
        if categoria:
            lista_servidores = lista_servidores.filter(cargo_emprego__grupo_cargo_emprego__categoria__exact=categoria)
        if lista_servidores.count():
            series1.append([situacao.nome, lista_servidores.count()])

    grafico1 = ColumnChart(
        'grafico1',
        title='Servidores por Situação Funcional',
        subtitle='Contabilizando servidores com vínculo institucional',
        minPointLength=10,
        data=series1,
    )
    grafico1.series[0]['dataLabels'] = {'enabled': True, 'rotation': -90, 'color': '#FFF', 'align': 'right', 'x': 4, 'y': 10}
    grafico1.xAxis['labels'] = {'rotation': -45, 'align': 'right'}
    return grafico1


# gráfico 1.1 - servidores ativo permanente docentes, tecnicos adm e pensionistas


def _grafico1_1():
    if 'contracheques' in settings.INSTALLED_APPS:
        ContraCheque = apps.get_model('contracheques', 'ContraCheque')

        ativos_permanentes_docentes = Servidor.objects.filter(ativo=True, situacao__codigo=Situacao.ATIVO_PERMANENTE, eh_docente=True)
        ativos_permanentes_tecnicos = Servidor.objects.filter(ativo=True, situacao__codigo=Situacao.ATIVO_PERMANENTE, eh_tecnico_administrativo=True)
        series1_1 = []
        series1_1.append(['Técnicos Adm. Ativos Permanentes', ativos_permanentes_tecnicos.count()])
        series1_1.append(['Docentes Ativos Permanentes', ativos_permanentes_docentes.count()])

        # PENSIONISTAS
        contra_cheques = ContraCheque.objects.ativos().fita_espelho().order_by('-ano__ano', '-mes')  # ordem decrescente
        if contra_cheques.exists():
            ultimo_contra_cheque = contra_cheques[0]  # pega o primeiro registro
            num_pensionistas = (
                ContraCheque.objects.ativos()
                .fita_espelho()
                .filter(ano__ano=ultimo_contra_cheque.ano.ano, mes=ultimo_contra_cheque.mes, pensionista__isnull=False)
                .count()
            )
        else:
            num_pensionistas = 0

        series1_1.append(['Pensionistas', num_pensionistas])

        grafico1_1 = ColumnChart(
            'grafico11',
            title='Ativos Permanentes e Pensionistas',
            subtitle='Contabilizando ativos permanentes e pensionistas',
            minPointLength=10,
            data=series1_1,
        )
        grafico1_1.series[0]['dataLabels'] = {'enabled': True, 'rotation': -90, 'color': '#FFF', 'align': 'right', 'x': 4, 'y': 10}
        grafico1_1.xAxis['labels'] = {'rotation': -45, 'align': 'right'}

        return grafico1_1


# gráfico 2 - titulação de ativos permanentes, cedidos e temporários


def _grafico2(categoria):
    series2 = []

    # com titulacao
    for titulacao in Titulacao.objects.all():
        lista_servidores = Servidor.objects.filter(
            ativo=True, situacao__codigo__in=Situacao.SITUACOES_EFETIVOS_E_TEMPORARIOS, titulacao__codigo=titulacao.codigo
        )
        if categoria:
            lista_servidores = lista_servidores.filter(cargo_emprego__grupo_cargo_emprego__categoria__exact=categoria)
        if lista_servidores.count():
            series2.append([titulacao.nome, lista_servidores.count()])

    # sem titulacao
    lista_servidores_sem_titulacao = Servidor.objects.filter(
        ativo=True, situacao__codigo__in=Situacao.SITUACOES_EFETIVOS_E_TEMPORARIOS, titulacao__isnull=True
    )
    if categoria:
        lista_servidores_sem_titulacao = lista_servidores_sem_titulacao.filter(cargo_emprego__grupo_cargo_emprego__categoria__exact=categoria)

    series2.append(['Nenhuma titulação', lista_servidores_sem_titulacao.count()])

    grafico2 = PieChart(
        'grafico2', title='Titulação de Servidores', subtitle='Contabilizando ativos permanentes, cedidos e temporários', data=series2
    )

    return grafico2


# gráfico 3 - campus de lotação de ativos permanentes e cedidos (efetivos)


def _grafico3(categoria):
    series3 = []
    campus = UnidadeOrganizacional.objects.siape().all().order_by('sigla')
    for c in campus:
        lista_servidores = Servidor.objects.filter(ativo=True, situacao__codigo__in=Situacao.SITUACOES_EFETIVOS, setor_lotacao__uo__id__exact=c.id)
        if categoria:
            lista_servidores = lista_servidores.filter(cargo_emprego__grupo_cargo_emprego__categoria__exact=categoria)
        if lista_servidores.count():
            series3.append((c.sigla, lista_servidores.count()))

    grafico3 = PieChart(
        'grafico3',
        title=f'{nomenclatura.campus} de Lotação de Servidores Efetivos',
        subtitle='Contabilizando ativos permanentes e cedidos',
        data=series3,
    )
    return grafico3


# gráfico 4 - campus de exercício de ativos permanentes e cedidos (efetivos)


def _grafico4(categoria):
    series4 = []
    campus = UnidadeOrganizacional.objects.siape().all().order_by('sigla')
    for c in campus:
        lista_servidores = Servidor.objects.filter(ativo=True, situacao__codigo__in=Situacao.SITUACOES_EFETIVOS, setor_exercicio__uo__id__exact=c.id)
        if categoria:
            lista_servidores = lista_servidores.filter(cargo_emprego__grupo_cargo_emprego__categoria__exact=categoria)
        if lista_servidores.count():
            series4.append((c.sigla, lista_servidores.count()))

    grafico4 = PieChart(
        'grafico4',
        title=f'{nomenclatura.campus} de Exercício de Servidores Efetivos',
        subtitle='Contabilizando ativos permanentes e cedidos',
        data=series4,
    )
    return grafico4


# gráfico 5 - servidores por campus de lotação


def _grafico5():
    series5 = []
    campus = UnidadeOrganizacional.objects.siape().all().order_by('sigla')
    for c in campus:
        series5.append(
            [
                c.sigla,
                # efetivos docentes
                Servidor.objects.filter(
                    ativo=True, situacao__codigo__in=Situacao.SITUACOES_EFETIVOS, eh_docente=True, setor_lotacao__uo__id__exact=c.id
                ).count(),
                # efetivos téc admin
                Servidor.objects.filter(
                    ativo=True,
                    situacao__codigo__in=Situacao.SITUACOES_EFETIVOS,
                    eh_tecnico_administrativo=True,
                    setor_lotacao__uo__id__exact=c.id,
                ).count(),
                # temporários
                Servidor.objects.filter(ativo=True, situacao__codigo__in=Situacao.SITUACOES_TEMPORARIOS, setor_lotacao__uo__id__exact=c.id).count(),
                # estagiários
                Servidor.objects.filter(
                    ativo=True, situacao__codigo__in=Situacao.situacoes_siape_estagiarios(), setor_lotacao__uo__id__exact=c.id
                ).count(),
            ]
        )

    grafico5 = GroupedColumnChart(
        'grafico5',
        title=f'Servidores por {nomenclatura.campus} de Lotação',
        data=series5,
        groups=['Docentes', 'Téc. Administrativos', 'Temporários', 'Estagiários'],
    )

    return grafico5


# gráfico 6 - servidores por campus de exercício


def _grafico6():
    series6 = []
    campus = UnidadeOrganizacional.objects.siape().all().order_by('sigla')
    for c in campus:
        series6.append(
            [
                c.sigla,
                # efetivos docentes
                Servidor.objects.filter(
                    ativo=True,
                    situacao__codigo__in=Situacao.SITUACOES_EFETIVOS,
                    eh_docente=True,
                    setor_exercicio__uo__id__exact=c.id,
                ).count(),
                # efetivos téc admin
                Servidor.objects.filter(
                    ativo=True,
                    situacao__codigo__in=Situacao.SITUACOES_EFETIVOS,
                    eh_tecnico_administrativo=True,
                    setor_exercicio__uo__id__exact=c.id,
                ).count(),
                # temporários
                Servidor.objects.filter(ativo=True, situacao__codigo__in=Situacao.SITUACOES_TEMPORARIOS, setor_exercicio__uo__id__exact=c.id).count(),
                # estagiários
                Servidor.objects.filter(
                    ativo=True, situacao__codigo__in=Situacao.situacoes_siape_estagiarios(), setor_exercicio__uo__id__exact=c.id
                ).count(),
            ]
        )
    grafico6 = GroupedColumnChart(
        'grafico6',
        title=f'Servidores por {nomenclatura.campus} de Exercício',
        data=series6,
        groups=['Docentes', 'Téc. Administrativos', 'Temporários', 'Estagiários'],
    )

    return grafico6


def _get_graficos(categoria):
    graficos = [_grafico1(categoria), _grafico2(categoria), _grafico3(categoria), _grafico4(categoria)]
    if not categoria:
        if 'contracheques' in settings.INSTALLED_APPS:
            grafico1_1 = _grafico1_1()
            graficos.append(grafico1_1)
        graficos.append(_grafico5())
        graficos.append(_grafico6())
    return graficos


@rtr()
def indicadores_publicos(request):
    title = 'Indicadores'
    graficos = []
    graficos_liberados = IndicadoresPublicos.objects.filter(liberar_area_publica=True).values_list('render_to', flat=True)
    for g in _get_graficos(None):
        if g.chart.get('renderTo') in graficos_liberados:
            graficos.append(g)
    return locals()


@rtr()
@permission_required('rh.pode_ver_relatorios_rh')
def servidores_sem_setor_suap(request):
    title = 'Servidores sem Setor SUAP'
    if request.method == 'POST':
        mensagens = ''
        for servidor_post, setor_post in list(request.POST.items()):
            # Só interessa iterar os `names` que começam com "setor_".
            if not servidor_post.startswith('setor_') or not setor_post:
                continue

            try:
                setor = Setor.objects.suap_ativos().get(id=int(setor_post))
            except Setor.DoesNotExist:
                continue
            else:
                matricula = servidor_post.strip('setor_')
                servidor = Servidor.objects.get(matricula=matricula)
                servidor.setor = setor
                servidor.save()
                if servidor.is_historico_setor_com_pendencias:
                    mensagens += f'Verifique o histórico de setores do servidor {servidor}. '
        return httprr('.', f'Modificação de servidores efetuada com sucesso. {mensagens}')
    else:
        meu_campus_siape = get_uo_siape()
        apenas_do_meu_campus_siape = 'meu_campus_siape' in request.GET
        servidores_sem_suap = {}
        # prefetch dos vínculos: o grid renderiza servidor.get_foto_* (property -> get_vinculo), evita N+1.
        servidores = Servidor.get_sem_setor_suap(do_meu_campus=apenas_do_meu_campus_siape).prefetch_related('vinculos')
        situacoes = (Situacao.ATIVO_EM_OUTRO_ORGAO, *Situacao.situacoes_siape_estagiarios())
        servidores_situacoes = servidores.exclude(situacao__codigo__in=situacoes)
        for servidor in servidores_situacoes:
            setor_exercicio = servidor.setor_exercicio
            if setor_exercicio is not None:
                uo = setor_exercicio.uo
                if uo is not None:
                    campus_equivalente = uo.equivalente
                    if campus_equivalente is not None:
                        setores_suap = Setor.objects.suap_ativos().filter(uo=campus_equivalente)
                        servidores_sem_suap[servidor.id] = setores_suap

    return locals()


@rtr()
@permission_required('rh.pode_ver_relatorios_rh')
def servidores_sem_cargo(request):
    title = 'Servidores sem Cargo'
    if request.method == 'POST':
        for servidor_post, setor_post in list(request.POST.items()):
            # Só interessa iterar os `names` que começam com "setor_".
            if not servidor_post.startswith('setor_') or not setor_post:
                continue

            id_setor = int(setor_post)
            try:
                setor = Setor.objects.suap_ativos().get(id=id_setor)
            except Setor.DoesNotExist:
                continue
            else:
                matricula = servidor_post.strip('setor_')
                servidor = get_object_or_404(Servidor, matricula=matricula)
                servidor.setor = setor
                servidor.save()
        return httprr('.', 'Modificação de servidores efetuada com sucesso.')
    else:
        meu_campus = get_uo()
        apenas_do_meu_campus = 'meu_campus' in request.GET
        servidores_sem_suap = {}
        # prefetch dos vínculos: o grid renderiza servidor.get_foto_* (property -> get_vinculo), evita N+1.
        servidores = Servidor.get_sem_cargo(do_meu_campus=apenas_do_meu_campus).prefetch_related('vinculos')
        return locals()


@rtr()
@permission_required('rh.pode_ver_relatorios_rh')
def servidor_buscar(request):
    title = 'Buscar servidores'
    FormClass = GetBuscarServidorForm()
    form = FormClass(request.GET or None)
    if form.is_valid():
        return tela_relatorio(request, form.cleaned_data)
    else:
        campos_servidor = campos
        campos_servidor_nao_agrupaveis = campos_nao_agrupaveis
    return locals()


@rtr()
@permission_required('rh.pode_ver_relatorios_rh')
def tela_relatorio(request, cleaned_data=None):
    # Whitelist obrigatória: `campos` é resolvido por getattr encadeado e o resultado é
    # chamado quando callable, então aceitar a querystring crua tornaria qualquer método sem
    # argumentos do Servidor (p.ex. `delete`) executável por quem só pode ver o relatório.
    campos_selecionados = filtrar_campos_validos(request.GET.getlist('campos'))
    servidores_qs, filtrado = buscar_servidores(cleaned_data)
    if campos_selecionados and not filtrado:
        return httprr('.', 'Selecione algum filtro.', 'error')
    encoded_url = request.GET.urlencode()
    return rh_tasks.gerar_busca_servidor(request, cleaned_data, servidores_qs, campos_selecionados, encoded_url)


def buscar_servidores(dados):
    """
    Retorna um queryset de Servidor filtrado conforme os parâmetros em `dados`
    e um flag (booleano) indicando se algum filtro foi aplicado.
    """
    # Filtros diretos por matrícula ou CPF(caso estes estejam preenchidos),
    # retornamos imediatamente o queryset filtrado.
    matricula = dados.get('matricula')
    if matricula:
        return Servidor.objects.filter(matricula=matricula), True

    cpf = dados.get('cpf')
    if cpf:
        return Servidor.objects.filter(pessoa_fisica__cpf=mask_cpf(cpf)), True

    # Base: servidores sem data de exclusão (instituidor)
    qs = Servidor.objects.filter(data_exclusao_instituidor__isnull=True)
    filtrado = False

    # Filtro por nome: cada palavra é filtrada com icontains

    nome = dados.get('nome')
    if nome:
        filtrado = True
        for parte in nome.split():
            qs = qs.filter(pessoa_fisica__nome__icontains=parte)

    # Filtro ativo
    ativo = dados.get('ativo')
    if ativo == '1':
        qs = qs.filter(ativo=True)
    elif ativo == '0':
        qs = qs.filter(ativo=False)

    # Filtro por setor: se recursivo, utiliza setor.ids_descendentes; senão, somente o id.
    setor = dados.get('setor')
    if setor:
        filtrado = True
        if dados.get('recursivo'):
            qs = qs.filter(setor__id__in=setor.ids_descendentes)
        else:
            qs = qs.filter(setor__id=setor.id)

    # Filtro por "setor_contem": busca em sigla ou nome (usando unaccent no nome)
    setor_contem = dados.get('setor_contem')
    if setor_contem:
        filtrado = True
        qs = qs.filter(Q(setor__sigla__icontains=setor_contem) | Q(setor__nome__unaccent__icontains=setor_contem))

    # Filtro por categoria (diferente de "todos")
    categoria = dados.get('categoria')
    if categoria and categoria != 'todos':
        filtrado = True
        qs = qs.filter(cargo_emprego__grupo_cargo_emprego__categoria__isnull=False, cargo_emprego__grupo_cargo_emprego__categoria=categoria)

    # Filtro por cargo_emprego
    cargo_emprego = dados.get('cargo_emprego')
    if cargo_emprego:
        if cargo_emprego == 'vazio':
            filtrado = True
            qs = qs.filter(cargo_emprego__isnull=True)
        elif cargo_emprego == 'nao_vazio':
            filtrado = True
            qs = qs.filter(cargo_emprego__isnull=False)
        elif cargo_emprego not in ('', 'qualquer'):
            filtrado = True
            qs = qs.filter(cargo_emprego=cargo_emprego)

    # Filtro por cargo_emprego_area
    area = dados.get('cargo_emprego_area')
    if area:
        if area == 'vazio':
            filtrado = True
            qs = qs.filter(cargo_emprego_area__isnull=True)
        elif area == 'nao_vazio':
            filtrado = True
            qs = qs.filter(cargo_emprego_area__isnull=False)
        elif area not in ('', 'qualquer'):
            filtrado = True
            qs = qs.filter(cargo_emprego_area=area)

    # Filtro por classe
    classe = dados.get('classe')
    if classe:
        if classe == 'vazio':
            filtrado = True
            qs = qs.filter(cargo_classe__isnull=True)
        elif classe == 'nao_vazio':
            filtrado = True
            qs = qs.filter(cargo_classe__isnull=False)
        elif classe not in ('', 'qualquer'):
            filtrado = True
            qs = qs.filter(cargo_classe=classe)

    # Filtro por funcao
    funcao = dados.get('funcao')
    if funcao:
        if funcao == 'vazio':
            filtrado = True
            qs = qs.filter(funcao__isnull=True)
        elif funcao == 'nao_vazio':
            filtrado = True
            qs = qs.filter(funcao__isnull=False)
        elif funcao not in ('', 'qualquer'):
            filtrado = True
            qs = qs.filter(servidorfuncaohistorico__funcao=funcao, servidorfuncaohistorico__data_fim_funcao__isnull=True).distinct()

    # Filtro por funcao_atividade
    funcao_atividade = dados.get('funcao_atividade')
    if funcao_atividade:
        if funcao_atividade == 'vazio':
            filtrado = True
            qs = qs.filter(funcao_atividade__isnull=True)
        elif funcao_atividade == 'nao_vazio':
            filtrado = True
            qs = qs.filter(funcao_atividade__isnull=False)
        elif funcao_atividade not in ('', 'qualquer'):
            filtrado = True
            qs = qs.filter(funcao_atividade=funcao_atividade)

    # Filtro por jornada_trabalho
    jornada = dados.get('jornada_trabalho')
    if jornada:
        if jornada == 'vazio':
            filtrado = True
            qs = qs.filter(jornada_trabalho__isnull=True)
        elif jornada == 'nao_vazio':
            filtrado = True
            qs = qs.filter(jornada_trabalho__isnull=False)
        elif jornada not in ('', 'qualquer'):
            filtrado = True
            qs = qs.filter(jornada_trabalho=jornada)

    # Se o app 'pgd2' estiver instalado, filtra por modalidade_regime_trabalho
    if 'pgd2' in settings.INSTALLED_APPS:
        hoje = date.today()
        SolicitacaoAdesaoServidor = apps.get_model('pgd2', 'solicitacaoadesaoservidor')
        modalidade = dados.get('modalidade_regime_trabalho')
        if modalidade and modalidade not in ('', 'qualquer'):
            if modalidade == 'pgd':
                filtrado = True
                qs = qs.filter(
                    Q(solicitacaoadesaoservidor__situacao=SolicitacaoAdesaoServidor.DEFERIDO)
                    & (
                        Q(solicitacaoadesaoservidor__data_desligamento_efeitos_a_partir_de__isnull=True)
                        | Q(solicitacaoadesaoservidor__data_desligamento_efeitos_a_partir_de__gte=hoje)
                    )
                )
            elif modalidade == 'presencial':
                filtrado = True
                qs = qs.exclude(
                    Q(solicitacaoadesaoservidor__situacao=SolicitacaoAdesaoServidor.DEFERIDO)
                    & (
                        Q(solicitacaoadesaoservidor__data_desligamento_efeitos_a_partir_de__isnull=True)
                        | Q(solicitacaoadesaoservidor__data_desligamento_efeitos_a_partir_de__gte=hoje)
                    )
                )

    # Filtro por jornada_setor_trabalho
    jornada_setor = dados.get('jornada_setor_trabalho')
    if jornada_setor:
        if jornada_setor == 'vazio':
            filtrado = True
            qs = qs.filter(
                setor__setorjornadahistorico__jornada_trabalho__isnull=True, setor__setorjornadahistorico__data_fim_da_jornada__isnull=True
            )
        elif jornada_setor == 'nao_vazio':
            filtrado = True
            qs = qs.filter(
                setor__setorjornadahistorico__jornada_trabalho__isnull=False, setor__setorjornadahistorico__data_fim_da_jornada__isnull=True
            )
        elif jornada_setor not in ('', 'qualquer'):
            filtrado = True
            qs = qs.filter(
                setor__setorjornadahistorico__jornada_trabalho=jornada_setor, setor__setorjornadahistorico__data_fim_da_jornada__isnull=True
            )

    # Filtro por regime_juridico
    regime = dados.get('regime_juridico')
    if regime:
        if regime == 'vazio':
            filtrado = True
            qs = qs.filter(regime_juridico__isnull=True)
        elif regime == 'nao_vazio':
            filtrado = True
            qs = qs.filter(regime_juridico__isnull=False)
        elif regime not in ('', 'qualquer'):
            filtrado = True
            qs = qs.filter(regime_juridico=regime)

    # Filtro por situacao
    situacao = dados.get('situacao')
    if situacao:
        if situacao == 'vazio':
            filtrado = True
            qs = qs.filter(situacao__isnull=True)
        elif situacao == 'nao_vazio':
            filtrado = True
            qs = qs.filter(situacao__isnull=False)
        elif situacao not in ('', 'qualquer'):
            filtrado = True
            qs = qs.filter(situacao=situacao)

    # Filtro por titulacao
    titulacao = dados.get('titulacao')
    if titulacao:
        if titulacao == 'vazio':
            filtrado = True
            qs = qs.filter(titulacao__isnull=True)
        elif titulacao == 'nao_vazio':
            filtrado = True
            qs = qs.filter(titulacao__isnull=False)
        elif titulacao not in ('', 'qualquer'):
            filtrado = True
            qs = qs.filter(titulacao=titulacao)

    # Filtro por titulacao
    afastamento = dados.get('afastamento')
    if afastamento:
        qs = qs.filter(servidorafastamento__afastamento=afastamento)

    # Filtro por setor_lotacao_siape
    setor_lotacao = dados.get('setor_lotacao_siape')
    if setor_lotacao:
        if setor_lotacao == 'vazio':
            filtrado = True
            qs = qs.filter(setor_lotacao__isnull=True)
        elif setor_lotacao == 'nao_vazio':
            filtrado = True
            qs = qs.filter(setor_lotacao__isnull=False)
        elif setor_lotacao not in ('', 'qualquer'):
            filtrado = True
            qs = qs.filter(setor_lotacao=setor_lotacao)

    # Filtro por campus_lotacao_siape
    campus_lotacao = dados.get('campus_lotacao_siape')
    if campus_lotacao:
        if campus_lotacao == 'vazio':
            filtrado = True
            qs = qs.filter(setor_lotacao__uo__isnull=True)
        elif campus_lotacao == 'nao_vazio':
            filtrado = True
            qs = qs.filter(setor_lotacao__uo__isnull=False)
        elif campus_lotacao not in ('', 'qualquer'):
            filtrado = True
            qs = qs.filter(setor_lotacao__uo=campus_lotacao)

    # Filtro por setor_exercicio_siape
    setor_exercicio = dados.get('setor_exercicio_siape')
    if setor_exercicio:
        if setor_exercicio == 'vazio':
            filtrado = True
            qs = qs.filter(setor_exercicio__isnull=True)
        elif setor_exercicio == 'nao_vazio':
            filtrado = True
            qs = qs.filter(setor_exercicio__isnull=False)
        elif setor_exercicio not in ('', 'qualquer'):
            filtrado = True
            qs = qs.filter(setor_exercicio=setor_exercicio)

    # Filtro por campus_exercicio_siape
    campus_exercicio = dados.get('campus_exercicio_siape')
    if campus_exercicio:
        if campus_exercicio == 'vazio':
            filtrado = True
            qs = qs.filter(setor_exercicio__uo__isnull=True)
        elif campus_exercicio == 'nao_vazio':
            filtrado = True
            qs = qs.filter(setor_exercicio__uo__isnull=False)
        elif campus_exercicio not in ('', 'qualquer'):
            filtrado = True
            qs = qs.filter(setor_exercicio__uo=campus_exercicio)

    # Filtro por tem_digital
    tem_digital = dados.get('tem_digital')
    if tem_digital == 'sim':
        filtrado = True
        qs = qs.filter(pessoa_fisica__template__isnull=False)
    elif tem_digital == 'nao':
        filtrado = True
        qs = qs.filter(pessoa_fisica__template__isnull=True)

    # Filtro por aniversariantes (mês)
    aniversariantes = dados.get('aniversariantes')
    if aniversariantes:
        filtrado = True
        qs = (
            qs.filter(pessoa_fisica__nascimento_data__month=aniversariantes, vinculos__sistema_origem='SIAPE')
            .extra(select={'nascimento_data_day': "EXTRACT('day' FROM pessoa_fisica.nascimento_data)"})
            .order_by('nascimento_data_day', 'pessoa_fisica__nome')
        )

    # Filtro por disciplina_ingresso, se o app 'edu' estiver instalado
    disciplina_ingresso = dados.get('disciplina_ingresso')
    if disciplina_ingresso and disciplina_ingresso != 'vazio' and 'edu' in settings.INSTALLED_APPS:
        filtrado = True
        if disciplina_ingresso == 'nulo':
            qs = qs.filter(vinculos__professor__disciplina__isnull=True)
        else:
            qs = qs.filter(vinculos__professor__disciplina=disciplina_ingresso)

    # Filtro por nível
    nivel = dados.get('nivel')
    if nivel:
        if nivel == 'vazio':
            filtrado = True
            qs = qs.filter(nivel_padrao__isnull=True)
        elif nivel == 'nao_vazio':
            filtrado = True
            qs = qs.filter(nivel_padrao__isnull=False)
        elif nivel not in ('', 'qualquer'):
            filtrado = True
            qs = qs.filter(nivel_padrao=nivel)

    # Filtro por deficiencia
    deficiencia = dados.get('deficiencia')
    if deficiencia:
        if deficiencia == 'vazio':
            filtrado = True
            qs = qs.filter(vinculos__deficiencia__isnull=True)
        elif deficiencia == 'nao_vazio':
            filtrado = True
            qs = qs.filter(vinculos__deficiencia__isnull=False)
        elif deficiencia not in ('', 'qualquer'):
            filtrado = True
            qs = qs.filter(vinculos__deficiencia=deficiencia)

    return qs.order_by('pessoa_fisica__nome'), filtrado


@rtr()
@permission_required('rh.view_servidor')
@lps
def servidor(request, servidor_matricula):
    servidor = get_object_or_404(Servidor, matricula=servidor_matricula)
    vinculo = servidor.get_vinculo()
    title = str(servidor)
    verificacao_propria = request.user == servidor.get_user()
    is_chefe = False
    eh_servidor = request.user.eh_servidor
    estah_afastado_ou_de_ferias = servidor.estah_afastado_ou_de_ferias_ateh(date.today())

    if eh_servidor:
        is_chefe = request.user.get_relacionamento().eh_chefe_de(servidor)

    pode_ver_cpf_servidor = request.user.has_perm('rh.pode_ver_cpf_servidor') or verificacao_propria
    pode_ver_dados_pessoais_servidor = request.user.has_perm('rh.pode_ver_dados_pessoais_servidor') or verificacao_propria
    pode_ver_endereco_servidor = request.user.has_perm('rh.pode_ver_endereco_servidor') or verificacao_propria
    pode_ver_telefones_pessoais_servidor = request.user.has_perm('rh.pode_ver_telefones_pessoais_servidor') or verificacao_propria
    pode_ver_dados_bancarios_servidor = request.user.has_perm('rh.pode_ver_dados_bancarios_servidor') or verificacao_propria
    pode_ver_historico_funcional_servidor = request.user.has_perm('rh.pode_ver_historico_funcional_servidor') or verificacao_propria
    pode_ver_ocorrencias_afastamentos_servidor = (
        request.user.has_perm('rh.pode_ver_ocorrencias_afastamentos_servidor') or verificacao_propria or is_chefe
    )
    pode_ver_historico_setores_servidor = request.user.has_perm('rh.pode_ver_historico_setores_servidor') or verificacao_propria
    pode_ver_historico_funcao_servidor = request.user.has_perm('rh.pode_ver_historico_funcao_servidor') or verificacao_propria
    pode_ver_viagens_servidor = request.user.has_perm('rh.pode_ver_viagens_servidor') or verificacao_propria or is_chefe
    pode_ver_dados_funcionais_servidor = request.user.has_perm('rh.pode_ver_dados_funcionais_servidor') or verificacao_propria
    pode_ver__identificacao_unica_siape = request.user.has_perm('rh.pode_ver_identificacao_unica_siape') or verificacao_propria

    eh_rh_sistemico = request.user.has_perm('rh.eh_rh_sistemico')

    hoje = date.today()
    endereco_irregular = not (
        servidor.pessoa_fisica.pessoaendereco
        and servidor.pessoa_fisica.pessoaendereco.municipio
        and (servidor.pessoa_fisica.pessoaendereco.municipio.uf == Configuracao.get_valor_por_chave('comum', 'instituicao_estado'))
    )

    # if verificacao_propria or is_rh or pode_ver_dados_extras:
    totais_qtd_dias_ocorrencias = 0
    totais_qtd_dias_afastamentos = 0
    if pode_ver_ocorrencias_afastamentos_servidor:
        servidor_ocorrencias = (
            ServidorOcorrencia.objects.filter(servidor=servidor).exclude(ocorrencia__grupo_ocorrencia__nome='AFASTAMENTO').order_by('-data')
        )
        servidor_afastamentos = ServidorAfastamento.objects.filter(servidor=servidor, cancelado=False).order_by('-data_inicio')
        servidor_afastamentos_suap = []
        if 'ponto' in settings.INSTALLED_APPS:
            Afastamento = apps.get_model('ponto', 'Afastamento')
            servidor_afastamentos_suap = Afastamento.objects.filter(vinculo=vinculo).order_by('-data_ini')

        totais_qtd_dias_por_ano = OrderedDict()
        for ocorrencia in servidor_ocorrencias:
            if ocorrencia.data_termino:
                for ano, qtd_dias in list(get_qtd_dias_por_ano(ocorrencia.data, ocorrencia.data_termino).items()):
                    if ano not in totais_qtd_dias_por_ano:
                        totais_qtd_dias_por_ano[ano] = [0, 0]
                    totais_qtd_dias_por_ano[ano][0] += qtd_dias  # 0 = ocorrências
                    totais_qtd_dias_ocorrencias += qtd_dias
        for afastamento in servidor_afastamentos:
            if afastamento.data_termino:
                for ano, qtd_dias in list(get_qtd_dias_por_ano(afastamento.data_inicio, afastamento.data_termino).items()):
                    if ano not in totais_qtd_dias_por_ano:
                        totais_qtd_dias_por_ano[ano] = [0, 0]
                    totais_qtd_dias_por_ano[ano][1] += qtd_dias  # 1 = afastamentos
                    totais_qtd_dias_afastamentos += qtd_dias
        for afastamento in servidor_afastamentos_suap:
            if afastamento.data_fim:
                for ano, qtd_dias in list(get_qtd_dias_por_ano(afastamento.data_ini, afastamento.data_fim).items()):
                    if ano not in totais_qtd_dias_por_ano:
                        totais_qtd_dias_por_ano[ano] = [0, 0]
                    totais_qtd_dias_por_ano[ano][1] += qtd_dias  # 1 = afastamentos
                    totais_qtd_dias_afastamentos += qtd_dias

        totais = {k: totais_qtd_dias_por_ano[k] for k in sorted(totais_qtd_dias_por_ano.keys(), reverse=True)}

    if pode_ver_historico_setores_servidor:
        historico_setor = ServidorSetorHistorico.objects.filter(servidor=servidor).order_by('-data_inicio_no_setor')
        historico_setor_siape = ServidorSetorLotacaoHistorico.objects.filter(servidor=servidor).order_by('-data_inicio_setor_lotacao')

    funcoes_ativas = ServidorFuncaoHistorico.objects.atuais().filter(servidor=servidor).order_by('data_inicio_funcao')
    if pode_ver_historico_funcao_servidor:
        servidor_historico_funcao = ServidorFuncaoHistorico.objects.filter(servidor=servidor).order_by('data_inicio_funcao')

    # Historico de Carga Horaria
    alteracao_carga_horaria = CargaHorariaReduzida.objects.filter(servidor=servidor)

    pode_gerar_cracha = servidor.pode_gerar_cracha()
    pode_gerar_carteira_funcional = servidor.pode_gerar_carteira_funcional()

    # provimentos
    if pode_ver_historico_funcional_servidor:
        pcas = PCA.montar_timeline(servidor.pca_set.all().order_by('data_entrada_pca'))
        outros_vinculos = (
            Servidor.objects.filter(pessoa_fisica__cpf=servidor.pessoa_fisica.cpf)
            .exclude(situacao__codigo__in=Situacao.situacoes_siape_estagiarios())
            .exclude(pk=servidor.pk)
        )

        servidor_tempo_servico_na_instituicao_via_pca = servidor.tempo_servico_na_instituicao_via_pca()
        servidor_tempo_servico_na_instituicao_via_pca_ficto = servidor.tempo_servico_na_instituicao_via_pca(ficto=True)
        afastamentos_interrompe_tempo_servico = servidor.tempo_servico_interrompido()

    viagens_servidor = Viagem.consolidadas.filter(servidor=servidor).order_by('-data_inicio_viagem')

    #
    # rederizando as tabs
    tab_dados_gerais = get_tabs(request, 'tab_dados_gerais.html', modulo='rh', dict_context=locals())
    tab_historico_funcional = get_tabs(request, 'tab_historico_funcional.html', modulo='rh', dict_context=locals())
    tab_ocorrencia_afastamento = get_tabs(request, 'tab_ocorrencia_afastamento.html', modulo='rh', dict_context=locals())
    tab_historico_setor = get_tabs(request, 'tab_historico_setor.html', modulo='rh', dict_context=locals())
    tab_servidor_historico_funcao = get_tabs(request, 'tab_historico_funcao.html', modulo='rh', dict_context=locals())
    tab_alteracao_carga_horaria = get_tabs(request, 'tab_historico_carga_horaria.html', modulo='rh', dict_context=locals())
    tab_viagens_servidor = get_tabs(request, 'tab_diarias_passagens.html', modulo='rh', dict_context=locals())
    dependentes_list = servidor.dependentes.select_related(
        'usuario_externo__pessoa_fisica', 'grau_parentesco', 'representante_legal__usuario_externo__pessoa_fisica'
    ).prefetch_related('beneficiodependente_set__beneficio')
    tab_dependentes = get_tabs(request, 'tab_dependentes.html', modulo='rh', dict_context=locals())

    extra_tabs = []
    for _, data in rh_servidor_view_tab.send(
        sender=index, request=request, servidor=servidor, verificacao_propria=verificacao_propria, eh_chefe=is_chefe
    ):
        if data:
            extra_tabs.append(data)

    esta_em_pgd, adesao_pgd = estah_no_pgd_hoje_pgd1_pgd2(servidor)
    esta_em_pgd2 = estah_no_pgd_hoje_pgd2(servidor)

    return locals()


@rtr()
@permission_required('rh.view_servidor')
def editar_informacoes_pessoais_servidor(request):
    if request.user.eh_servidor:
        servidor = request.user.get_relacionamento()
        title = str(servidor)
        verificacao_propria = request.user == servidor.get_user()
        if verificacao_propria:
            form = ServidorInformacoesPessoaisForm(request.POST or None, instance=servidor)
            if form.is_valid():
                form.save()
                return httprr('..', 'Informações pessoais salvas com sucesso.')

        return locals()
    raise PermissionDenied('Tela apenas para servidores.')


@rtr()
@login_required()
def editar_informacoes_digitais_fracas(request, pessoa_fisica_id):
    pessoa_fisica = get_object_or_404(PessoaFisica, id=pessoa_fisica_id)
    pode_cadastrar_digital = request.user.has_perm('rh.pode_cadastrar_digital')
    verificacao_propria = request.user.get_profile() == pessoa_fisica and pessoa_fisica.tem_digital_fraca
    if not pode_cadastrar_digital and not verificacao_propria:
        raise PermissionDenied('Você não tem permissão para acessar essa tela.')
    if pode_cadastrar_digital:
        title = f'Editar Informações de Digitais Fracas de {pessoa_fisica!s}'
        form = PessoaFisicaInformacoesDigitaisFracasForm(request.POST or None, instance=pessoa_fisica, request=request)
    elif verificacao_propria:
        title = 'Editar Minha Senha do Ponto'
        form = PessoaFisicaAlterarSenhaPontoForm(request.POST or None, instance=pessoa_fisica, request=request)

    if form.is_valid():
        form.save()
        return httprr('..', 'Informações salvas com sucesso.')

    return locals()


@rtr()
@permission_required('rh.pode_ver_relatorios_rh, rh.eh_rh_sistemico, comum.is_reitor, comum.is_pro_reitor, comum.is_diretor_geral')
def tela_recursos_humanos(request):
    class Tabela:
        def __init__(self, titulo):
            self.titulo = titulo
            self.tabela = []
            self.soma = OrderedDict()

        def adicionar(self, label, valores):
            self.tabela.append(valores)
            for vlabel, valor in list(valores.items()):
                if not isinstance(valor, str):
                    if vlabel in list(self.soma.keys()):
                        self.soma[vlabel] += valor
                    else:
                        self.soma[vlabel] = valor
                else:
                    self.soma[vlabel] = 'Total'

        def cabecalho(self):
            return list(self.soma.keys())

        def total(self):
            return self.soma

        def linhas(self):
            return self.tabela

        def titulo(self):
            return self.titulo

    # Servidores vinculados retorna exluido=False
    servidores_all = Servidor.objects.vinculados()
    # Recupera só as situacoes usadas atualmente
    situacoes_usadas = Situacao.objects.filter(
        id__in=servidores_all.values('situacao')
        .annotate(Count('situacao'))
        .order_by()
        .filter(situacao__count__gt=0)
        .values_list('situacao', flat=True)
    )

    # ------------------------------------------------------------------------------------------
    relatorios = []

    tabela_geral_1 = Tabela('Docentes, técnicos admistrativos e estagiários - Composição por sexo')
    tabela_geral_2 = Tabela('Docentes, técnicos admistrativos e estagiários - Composição por regime de trabalho')

    tabela_docente_1 = Tabela('Docentes - Composição por sexo')
    tabela_docente_2 = Tabela('Docentes - Composição por regime de trabalho')

    tabela_tecnico_1 = Tabela('Técnicos administrativos - Composição por sexo')
    tabela_tecnico_2 = Tabela('Técnicos administrativos - Composição por regime de trabalho')

    tabela_estagiarios_1 = Tabela('Estagiários - Composição por sexo')
    tabela_estagiarios_2 = Tabela('Estagiários - Composição por regime de trabalho')

    for situacao in situacoes_usadas:
        servidores_situacao = servidores_all.filter(situacao=situacao)
        #       Tabela Por Sexo
        servidores_masculino = servidores_situacao.filter(pessoa_fisica__sexo='M')
        servidores_feminino = servidores_situacao.filter(pessoa_fisica__sexo='F')
        servidores_sexo_nao_definido = servidores_situacao.exclude(pessoa_fisica__sexo__in=['F', 'M'])

        #       Geral
        linha = OrderedDict()
        linha['Situação'] = situacao.nome
        linha['Masculino'] = servidores_masculino.count()
        linha['Feminino'] = servidores_feminino.count()
        linha['Não definido'] = servidores_sexo_nao_definido.count()
        linha['Total'] = servidores_masculino.count() + servidores_feminino.count() + servidores_sexo_nao_definido.count()

        tabela_geral_1.adicionar(str(situacao), linha)
        #       Tabela Por regime de Trabalho
        servidores_vinte_horas = servidores_situacao.filter(jornada_trabalho__nome__unaccent__icontains='20 HORAS')
        servidores_vinte_e_cinco_horas = servidores_situacao.filter(jornada_trabalho__nome__unaccent__icontains='25 HORAS')
        servidores_trinta_horas = servidores_situacao.filter(jornada_trabalho__nome__unaccent__icontains='30 HORAS')
        servidores_quarenta_horas = servidores_situacao.filter(jornada_trabalho__nome__unaccent__icontains='40 HORAS')
        servidores_dedicacao_exclusiva = servidores_situacao.filter(jornada_trabalho__nome__unaccent__icontains='DEDICACAO EXCLUSIVA')
        servidor_regime_trabalho_nao_definido = servidores_situacao.filter(jornada_trabalho__isnull=True)

        linha = OrderedDict()
        linha['Situação'] = situacao.nome
        linha['20h Semanais'] = servidores_vinte_horas.count()
        linha['25h Semanais'] = servidores_vinte_e_cinco_horas.count()
        linha['30h Semanais'] = servidores_trinta_horas.count()
        linha['40h Semanais'] = servidores_quarenta_horas.count()
        linha['Dedicação Exclusiva'] = servidores_dedicacao_exclusiva.count()
        linha['Não Definido'] = servidor_regime_trabalho_nao_definido.count()
        linha['Total'] = (
            servidores_vinte_horas.count()
            + servidores_vinte_e_cinco_horas.count()
            + servidores_trinta_horas.count()
            + servidores_quarenta_horas.count()
            + servidores_dedicacao_exclusiva.count()
            + servidor_regime_trabalho_nao_definido.count()
        )

        tabela_geral_2.adicionar(str(situacao), linha)

        #       Tecnicos Administrativos

        linha = OrderedDict()
        linha['Situação'] = situacao.nome
        linha['Masculino'] = servidores_masculino.filter(eh_tecnico_administrativo=True).count()
        linha['Feminino'] = servidores_feminino.filter(eh_tecnico_administrativo=True).count()
        linha['Não definido'] = servidores_sexo_nao_definido.filter(eh_tecnico_administrativo=True).count()
        linha['Total'] = (
            servidores_masculino.filter(eh_tecnico_administrativo=True).count()
            + servidores_feminino.filter(eh_tecnico_administrativo=True).count()
            + servidores_sexo_nao_definido.filter(eh_tecnico_administrativo=True).count()
        )

        tabela_tecnico_1.adicionar(str(situacao), linha)

        linha = OrderedDict()
        linha['Situação'] = situacao.nome
        linha['20h Semanais'] = servidores_vinte_horas.filter(eh_tecnico_administrativo=True).count()
        linha['25h Semanais'] = servidores_vinte_e_cinco_horas.filter(eh_tecnico_administrativo=True).count()
        linha['30h Semanais'] = servidores_trinta_horas.filter(eh_tecnico_administrativo=True).count()
        linha['40h Semanais'] = servidores_quarenta_horas.filter(eh_tecnico_administrativo=True).count()
        linha['Dedicação Exclusiva'] = servidores_dedicacao_exclusiva.filter(eh_tecnico_administrativo=True).count()
        linha['Não definido'] = servidor_regime_trabalho_nao_definido.filter(eh_tecnico_administrativo=True).count()
        linha['Total'] = (
            servidores_vinte_horas.filter(eh_tecnico_administrativo=True).count()
            + servidores_vinte_e_cinco_horas.filter(eh_tecnico_administrativo=True).count()
            + servidores_trinta_horas.filter(eh_tecnico_administrativo=True).count()
            + servidores_quarenta_horas.filter(eh_tecnico_administrativo=True).count()
            + servidores_dedicacao_exclusiva.filter(eh_tecnico_administrativo=True).count()
            + servidor_regime_trabalho_nao_definido.filter(eh_tecnico_administrativo=True).count()
        )

        tabela_tecnico_2.adicionar(str(situacao), linha)

        #       Docentes
        linha = OrderedDict()
        linha['Situação'] = situacao.nome
        linha['Masculino'] = servidores_masculino.filter(eh_docente=True).count()
        linha['Feminino'] = servidores_feminino.filter(eh_docente=True).count()
        linha['Não definido'] = servidores_sexo_nao_definido.filter(eh_docente=True).count()
        linha['Total'] = (
            servidores_masculino.filter(eh_docente=True).count()
            + servidores_feminino.filter(eh_docente=True).count()
            + servidores_sexo_nao_definido.filter(eh_docente=True).count()
        )

        tabela_docente_1.adicionar(str(situacao), linha)

        linha = OrderedDict()
        linha['Situação'] = situacao.nome
        linha['20h Semanais'] = servidores_vinte_horas.filter(eh_docente=True).count()
        linha['25h Semanais'] = servidores_vinte_e_cinco_horas.filter(eh_docente=True).count()
        linha['30h Semanais'] = servidores_trinta_horas.filter(eh_docente=True).count()
        linha['40h Semanais'] = servidores_quarenta_horas.filter(eh_docente=True).count()
        linha['Dedicação Exclusiva'] = servidores_dedicacao_exclusiva.filter(eh_docente=True).count()
        linha['Não definido'] = servidor_regime_trabalho_nao_definido.filter(eh_docente=True).count()
        linha['Total'] = (
            servidores_vinte_horas.filter(eh_docente=True).count()
            + servidores_vinte_e_cinco_horas.filter(eh_docente=True).count()
            + servidores_trinta_horas.filter(eh_docente=True).count()
            + servidores_quarenta_horas.filter(eh_docente=True).count()
            + servidores_dedicacao_exclusiva.filter(eh_docente=True).count()
        )

        tabela_docente_2.adicionar(str(situacao), linha)

        if situacao.codigo in Situacao.situacoes_siape_estagiarios():
            estagiarios_etg1 = servidores_situacao.filter(funcao_codigo__in=['1', '0001'])
            estagiarios_masculino_etg1 = estagiarios_etg1.filter(pessoa_fisica__sexo='M')
            estagiarios_feminino_etg1 = estagiarios_etg1.filter(pessoa_fisica__sexo='F')
            estagiarios_sexo_nao_definido_etg1 = estagiarios_etg1.exclude(pessoa_fisica__sexo__in=['F', 'M'])

            estagiarios_etg2 = servidores_situacao.filter(funcao_codigo__in=['2', '0002'])
            estagiarios_masculino_etg2 = estagiarios_etg2.filter(pessoa_fisica__sexo='M')
            estagiarios_feminino_etg2 = estagiarios_etg2.filter(pessoa_fisica__sexo='F')
            estagiarios_sexo_nao_definido_etg2 = estagiarios_etg2.exclude(pessoa_fisica__sexo__in=['F', 'M'])

            linha = OrderedDict()
            linha['Situação'] = 'ETG1'
            linha['Masculino'] = estagiarios_masculino_etg1.count()
            linha['Feminino'] = estagiarios_feminino_etg1.count()
            linha['Não definido'] = estagiarios_sexo_nao_definido_etg1.count()
            linha['Total'] = estagiarios_etg1.count()
            tabela_estagiarios_1.adicionar(str(situacao), linha)

            linha = OrderedDict()
            linha['Situação'] = 'ETG2'
            linha['Masculino'] = estagiarios_masculino_etg2.count()
            linha['Feminino'] = estagiarios_feminino_etg2.count()
            linha['Não definido'] = estagiarios_sexo_nao_definido_etg2.count()
            linha['Total'] = estagiarios_etg2.count()
            tabela_estagiarios_1.adicionar(str(situacao), linha)

            estagiarios_vinte_horas_etg1 = estagiarios_etg1.filter(jornada_trabalho__nome__unaccent__icontains='20 HORAS')
            estagiarios_vinte_e_cinco_horas_etg1 = estagiarios_etg1.filter(jornada_trabalho__nome__unaccent__icontains='25 HORAS')
            estagiarios_trinta_horas_etg1 = estagiarios_etg1.filter(jornada_trabalho__nome__unaccent__icontains='30 HORAS')
            estagiarios_quarenta_horas_etg1 = estagiarios_etg1.filter(jornada_trabalho__nome__unaccent__icontains='40 HORAS')
            estagiarios_dedicacao_exclusiva_etg1 = estagiarios_etg1.filter(jornada_trabalho__nome__unaccent__icontains='DEDICACAO EXCLUSIVA')

            estagiarios_vinte_horas_etg2 = estagiarios_etg2.filter(jornada_trabalho__nome__unaccent__icontains='20 HORAS')
            estagiarios_vinte_e_cinco_horas_etg2 = estagiarios_etg2.filter(jornada_trabalho__nome__unaccent__icontains='25 HORAS')
            estagiarios_trinta_horas_etg2 = estagiarios_etg2.filter(jornada_trabalho__nome__unaccent__icontains='30 HORAS')
            estagiarios_quarenta_horas_etg2 = estagiarios_etg2.filter(jornada_trabalho__nome__unaccent__icontains='40 HORAS')
            estagiarios_dedicacao_exclusiva_etg2 = estagiarios_etg2.filter(jornada_trabalho__nome__unaccent__icontains='DEDICACAO EXCLUSIVA')

            linha = OrderedDict()
            linha['Situação'] = 'ETG1'
            linha['20h Semanais'] = estagiarios_vinte_horas_etg1.count()
            linha['25h Semanais'] = estagiarios_vinte_e_cinco_horas_etg1.count()
            linha['30h Semanais'] = estagiarios_trinta_horas_etg1.count()
            linha['40h Semanais'] = estagiarios_quarenta_horas_etg1.count()
            linha['Dedicação Exclusiva'] = estagiarios_dedicacao_exclusiva_etg1.count()
            linha['Total'] = estagiarios_etg1.count()

            tabela_estagiarios_2.adicionar(str(situacao), linha)

            linha = OrderedDict()
            linha['Situação'] = 'ETG2'
            linha['20h Semanais'] = estagiarios_vinte_horas_etg2.count()
            linha['25h Semanais'] = estagiarios_vinte_e_cinco_horas_etg2.count()
            linha['30h Semanais'] = estagiarios_trinta_horas_etg2.count()
            linha['40h Semanais'] = estagiarios_quarenta_horas_etg2.count()
            linha['Dedicação Exclusiva'] = estagiarios_dedicacao_exclusiva_etg2.count()
            linha['Total'] = estagiarios_etg2.count()

            tabela_estagiarios_2.adicionar(str(situacao), linha)

    relatorios.append(tabela_geral_1)
    relatorios.append(tabela_geral_2)
    relatorios.append(tabela_docente_1)
    relatorios.append(tabela_docente_2)
    relatorios.append(tabela_tecnico_1)
    relatorios.append(tabela_tecnico_2)
    relatorios.append(tabela_estagiarios_1)
    relatorios.append(tabela_estagiarios_2)

    return locals()


def servidores_dados_exportacao(servidores_ids):
    """
    Monta tabela de dados retornados da busca de servidores com funcao para
    exportação via XLS.
    """
    rows = []
    header = [
        '#',
        'MATRICULA',
        'NOME',
        'FUNÇÃO',
        'ATIVIDADE',
        'DATA OCUPAÇÃO',
        'UORG',
        'QUANTIDADE DE SERVIDORES NO SETOR',
        'QUANTIDADE DE SERVIDORES SETORES DESCENDENTES',
    ]
    rows.append(header)
    count = 0
    servidores_qs = Servidor.objects.filter(id__in=servidores_ids)
    # Recupera funções atuais em lote para evitar N+1
    funcoes_historico = ServidorFuncaoHistorico.objects.atuais().filter(servidor_id__in=servidores_ids).select_related('funcao', 'atividade')
    funcoes_map = {f.servidor_id: f for f in funcoes_historico}

    for s in servidores_qs:
        count += 1
        fh = funcoes_map.get(s.id)
        funcao_nome = fh.funcao.nome if fh else (s.funcao.nome if getattr(s, 'funcao', None) else '')
        atividade = fh.atividade if fh and fh.atividade else (s.atividade if getattr(s, 'atividade', None) else '')
        data_ocupacao = fh.data_inicio_funcao if fh else getattr(s, 'funcao_data_ocupacao', None)

        row = [
            count,
            s.matricula,
            s.nome,
            funcao_nome,
            atividade,
            data_ocupacao,
            s.setor,
            s.setor.qtd_servidores(recursivo=False),
            s.setor.qtd_servidores(recursivo=True),
        ]
        rows.append(row)

    return rows


def get_cabecalho_xls_servidores_com_funcao() -> list[str]:
    return [
        'Nº',
        'Matrícula',
        'Nome',
        'UO',
        'Cargo efetivo',
        'Função',
        'Atividade',
        'Função Código',
        'Data Ocupação',
        'Lattes',
        'ORCID',
        'UORG',
        'UORG Nome',
        'E-mail',
        'Telefones',
        'Quantidade de Servidores no Setor',
    ]


def get_linha_xls_servidor_com_funcao(servidor: Servidor, contador: int, dict_setores: dict) -> list:
    uo_setor = servidor.setor.uo if servidor.setor and servidor.setor.uo else None
    funcao_obj = getattr(servidor, 'funcao_atual', None)
    atividade_obj = getattr(servidor, 'funcao_atividade_atual', None) or getattr(servidor, 'atividade', None)
    funcao_codigo = getattr(servidor, 'funcao_codigo_atual', '') or getattr(servidor, 'funcao_codigo', '')
    return [
        contador,
        format_(servidor.matricula),
        format_(servidor.nome),
        format_(uo_setor),
        format_(servidor.cargo_emprego),
        format_(getattr(funcao_obj, 'nome', '')),
        format_(atividade_obj),
        format_(f'{funcao_codigo}'),
        format_(getattr(servidor, 'funcao_data_ocupacao', None)),
        format_(servidor.pessoa_fisica.lattes),
        format_(servidor.pessoa_fisica.orcid),
        format_(servidor.setor),
        format_(servidor.setor.nome),
        format_(servidor.email_institucional),
        format_(dict_setores[servidor.setor]['telefones']),
        format_(dict_setores[servidor.setor]['quantidade_servidores_setor']),
    ]


@rtr()
@permission_required('rh.pode_ver_relatorios_rh')
def tela_servidores_com_funcao(request):
    title = 'Lista de Servidores com Função'
    # Anotar servidores com a função atual (proveniente de ServidorFuncaoHistorico.atuais())
    servidores_base = Servidor.objects.ativos().select_related(
        'setor', 'setor__uo', 'cargo_emprego', 'cargo_emprego__grupo_cargo_emprego', 'pessoa_fisica'
    )

    # Subquery para pegar a função atual (pk) e data de início
    funcao_subq = ServidorFuncaoHistorico.objects.atuais().filter(servidor=OuterRef('pk'))
    funcao_pk_sq = funcao_subq.values('funcao')[:1]
    data_inicio_sq = funcao_subq.values('data_inicio_funcao')[:1]

    servidores = (
        servidores_base.annotate(funcao_historico_pk=Subquery(funcao_pk_sq))
        .annotate(funcao_data_inicio_historico=Subquery(data_inicio_sq))
        .filter(funcao_historico_pk__isnull=False)
        .order_by('setor__uo', 'pessoa_fisica__nome')
    )
    FormClass = ServidorFuncaoFormFactory()
    servidores_no_setor = Servidor.objects.ativos_permanentes().filter(setor=OuterRef('pk')).values('setor').annotate(qt=Count('id')).values('qt')
    # Anotamos a queryset de Setor.
    # Utilizamos Coalesce para que, quando a subquery não retorne nenhum valor (ou seja, nenhum servidor encontrado),
    # seja retornado 0.
    setores = (
        Setor.objects.suap()
        .all()
        .annotate(
            quantidade_servidores_setor=Coalesce(Subquery(servidores_no_setor, output_field=IntegerField()), Value(0)),
        )
        .prefetch_related('setortelefone_set')
    )
    dict_setores = {}
    if request.POST:
        form = FormClass(request.POST)
        if form.is_valid():
            campus = request.POST['campus']
            funcao = request.POST['funcao']

            if campus:
                campus = int(campus)
                servidores = servidores.filter(setor__uo=campus)
                setores = setores.filter(uo=campus)

            if funcao:
                funcao = int(funcao)
                servidores = servidores.filter(funcao_historico_pk=funcao)
    else:
        form = FormClass()

    for setor in setores:
        if setor not in list(dict_setores.keys()):
            dict_setores[setor] = {}
            dict_setores[setor]['quantidade_servidores_setor'] = setor.quantidade_servidores_setor
            dict_setores[setor]['telefones'] = setor.telefones()

    # Precarrega as funções atuais para os servidores filtrados (usado pela tela e export)
    servidores_ids_display = list(servidores.values_list('id', flat=True))
    funcoes_historico_display = (
        ServidorFuncaoHistorico.objects.atuais().filter(servidor_id__in=servidores_ids_display).select_related('funcao', 'atividade')
    )
    funcoes_map_display = {f.servidor_id: f for f in funcoes_historico_display}

    # Convert to list so we can attach helper attributes used by templates
    servidores = list(servidores)
    for s in servidores:
        fh = funcoes_map_display.get(s.id)
        funcao_obj = fh.funcao if fh else None
        atividade_obj = fh.atividade if fh and fh.atividade else None
        data_inicio = fh.data_inicio_funcao if fh else getattr(s, 'funcao_data_ocupacao', None)
        funcao_codigo = getattr(fh.funcao, 'codigo', '') if fh and fh.funcao else getattr(s, 'funcao_codigo', '')

        # atributos auxiliares
        s.funcao_atual = funcao_obj
        s.funcao_atividade_atual = atividade_obj
        s.funcao_data_ocupacao = data_inicio
        s.funcao_codigo_atual = funcao_codigo

        # manter compatibilidade com templates/exports que acessam s.funcao / s.atividade
        # Algumas classes definem `atividade` ou `funcao` como propriedades sem setter;
        # tentar atribuir nesses casos levanta AttributeError. Evitamos quebrar a view
        # pegando via try/except e, se não for possível atribuir, mantemos apenas os
        # novos atributos `funcao_atual`/`funcao_atividade_atual` que os templates
        # já passam a suportar.
        if funcao_obj is not None:
            try:
                s.funcao = funcao_obj
            except AttributeError:
                # não podemos sobrescrever a propriedade; seguir sem alteração
                pass
        if atividade_obj is not None:
            try:
                s.atividade = atividade_obj
            except AttributeError:
                # propriedade somente leitura — continuar sem sobrescrever
                pass

    if 'to_xls' in request.GET:
        rows = [get_cabecalho_xls_servidores_com_funcao()]
        for count, servidor in enumerate(servidores, start=1):
            rows.append(get_linha_xls_servidor_com_funcao(servidor, count, dict_setores))
        return XlsResponse(rows)

    return locals()


@permission_required('rh.pode_gerar_cracha')
def cracha_pessoa(request, pessoa_id):
    servidor = get_object_or_404(Servidor, pessoa_fisica_id=pessoa_id)
    try:
        if servidor.pode_gerar_cracha():
            documentos = DocumentoControle.objects.filter(
                solicitante_vinculo=servidor.get_vinculo(), documento_tipo__identificador=DocumentoControleTipo.CRACHA
            )
            if documentos.exists():
                solicitacao = documentos.latest('data_solicitacao')
                servidor.pessoa_fisica.nome_sugerido_cracha = solicitacao.nome_sugerido or ''
                servidor.pessoa_fisica.nome_social_cracha = solicitacao.nome_social or ''
            return imprime_cracha(servidor)
    except OSError as osEx:
        return httprr('/admin/comum/documentocontrole/', str(osEx), tag='error')
    return httprr('/admin/comum/documentocontrole/', 'A pessoa não tem dados suficientes para a impressão do crachá.', tag='error')


@permission_required('rh.pode_gerar_cracha')
def cracha_setor(request, setor_id):
    lista = []
    setor = Setor.objects.suap_ativos().get(pk=setor_id)
    for servidor in setor.get_servidores().filter(ativo=True):
        if servidor.pode_gerar_cracha():
            lista.append(servidor)
    return imprime_cracha(lista)


@login_required()
@permission_required('rh.pode_gerar_carteira')
def carteira_funcional(request, servidor_id=None):
    servidor_ids = []
    if servidor_id:
        request.session['_servidores_ids'] = [servidor_id]
        servidor_ids = [servidor_id]
    else:
        servidor_ids = request.session.get('_servidores_ids')

    versao = None
    qs_tipo_carteira_funcional = TipoCarteiraFuncional.objects.filter(ativo=True)
    if qs_tipo_carteira_funcional.exists():
        tipo_carteira_funcional = qs_tipo_carteira_funcional[0]
        versao = tipo_carteira_funcional.template

    if versao == TipoCarteiraFuncional.MODELO_2016:
        return httprr('/rh/imprimir_carteira_funcional_pdf')
    else:
        qs_servidores = Servidor.objects.filter(id__in=servidor_ids)
        servidores = list(qs_servidores)
        return imprime_carteira_funcional(servidores)


def carteira_funcional_setor(request: HttpRequest, setor_id: int, abrangencia: str) -> HttpResponse:
    """
    Gera carteira funcionais para um servidores de um setor.

    Apenas os servidores ativos permanentes podem ter a carteira gerada por
    esta função.

    """
    # Bloqueio de acesso com base na permissão
    if not request.user.has_perm('rh.pode_gerar_carteira'):
        raise PermissionDenied

    # verificando a versão da carteira funcional que está ativo
    versao = None
    qs_tipo_carteira_funcional = TipoCarteiraFuncional.objects.filter(ativo=True)
    if qs_tipo_carteira_funcional.exists():
        tipo_carteira_funcional = qs_tipo_carteira_funcional[0]
        versao = tipo_carteira_funcional.template

    # selecionando servidores do setor selecionado
    servidores_setor = Servidor.objects.filter(setor=setor_id)

    lista = [servidor for servidor in servidores_setor if servidor.pode_gerar_carteira_funcional()]
    if abrangencia != 'all':
        nova_lista = []
        servidor_ids = []
        for servidor in lista:
            dc = DocumentoControle.objects.filter(
                solicitante_vinculo=servidor.get_vinculo(), documento_tipo__identificador=DocumentoControleTipo.CARTEIRA_FUNCIONAL, ativo=True
            )
            if not dc:
                nova_lista.append(servidor)
                servidor_ids.append(servidor.id)
        if nova_lista:
            if versao == TipoCarteiraFuncional.MODELO_2016:
                request.session['_servidores_ids'] = servidor_ids
                return httprr('/rh/imprimir_carteira_funcional_pdf')
            else:
                return imprime_carteira_funcional(nova_lista)
        else:
            return httprr('/admin/rh/setor/', 'Operação não pôde ser realizada')

    if versao == TipoCarteiraFuncional.MODELO_2016:
        request.session['_servidores_ids'] = [servidor.id for servidor in lista]
        return httprr('/rh/imprimir_carteira_funcional_pdf')
    else:
        return imprime_carteira_funcional(lista)


@documento(enumerar_paginas=False)
@rtr()
@login_required()
@permission_required('rh.pode_gerar_carteira')
def imprimir_carteira_funcional_pdf(request):
    usuario_logado = request.user.get_relacionamento()
    local_data_expedicao = None
    qs_cid = ConfiguracaoImpressaoDocumento.objects.filter(
        uo=usuario_logado.campus, tipos_documento__identificador=DocumentoControleTipo.CARTEIRA_FUNCIONAL
    )
    if qs_cid:
        local_impressao = qs_cid[0].local_impressao
        data_expedicao = datetime.today().strftime('%d/%m/%Y')
        local_data_expedicao = f'{local_impressao}, {data_expedicao}'

    servidor_ids = request.session.get('_servidores_ids', [])
    servidores = Servidor.objects.filter(id__in=servidor_ids)
    situacao_estagiario = Situacao.objects.filter(codigo__in=Situacao.situacoes_siape_estagiarios())

    carteiras = []
    for servidor in servidores:
        nome = servidor.pessoa_fisica.nome.upper()
        matricula = servidor.matricula
        grupo_sanguineo = servidor.grupo_sanguineo
        fator_rh = servidor.fator_rh
        nome_mae = servidor.pessoa_fisica.nome_mae.upper()
        rg = servidor.pessoa_fisica.rg
        rg_orgao = servidor.pessoa_fisica.rg_orgao
        rg_uf = servidor.pessoa_fisica.rg_uf
        cpf = servidor.pessoa_fisica.cpf
        nascimento_data = servidor.pessoa_fisica.nascimento_data.strftime('%d/%m/%Y')

        aposentado = ''
        if servidor.situacao not in situacao_estagiario:
            cargo_emprego = servidor.cargo_emprego.nome
            if servidor.cargo_emprego.nome_amigavel:
                cargo_emprego = servidor.cargo_emprego.nome_amigavel
            if servidor.situacao.nome_siape == 'APOSENTADO':
                aposentado = '(APOSENTADO)'
        else:
            cargo_emprego = 'ESTAGIÁRIO(A)'
        imagemfoto = servidor.get_foto_150x200_url()

        identidade = f'{rg}   {rg_orgao}/{rg_uf}'
        sangue = f'{grupo_sanguineo}{fator_rh}'
        naturalidade = str(servidor.pessoa_fisica.nascimento_municipio)

        carteiras.append(
            {
                'nome': nome,
                'matricula': matricula,
                'nome_mae': nome_mae,
                'cpf': cpf,
                'foto': imagemfoto,
                'cargo': cargo_emprego,
                'data_nascimento': nascimento_data,
                'identidade': identidade,
                'sangue': sangue,
                'naturalidade': naturalidade,
                'local_data_expedicao': local_data_expedicao,
            }
        )

    return locals()


@rtr()
@permission_required('rh.pode_ver_relatorios_rh', 'rh.eh_rh_sistemico, comum.is_reitor, comum.is_pro_reitor, comum.is_diretor_geral')
def aniversariantes(request):
    title = 'Aniversariantes do Mês'
    mes_escolhido = int(request.GET.get('mes', datetime.today().month))
    meses = (
        {'numero': 1, 'nome': 'Janeiro'},
        {'numero': 2, 'nome': 'Fevereiro'},
        {'numero': 3, 'nome': 'Março'},
        {'numero': 4, 'nome': 'Abril'},
        {'numero': 5, 'nome': 'Maio'},
        {'numero': 6, 'nome': 'Junho'},
        {'numero': 7, 'nome': 'Julho'},
        {'numero': 8, 'nome': 'Agosto'},
        {'numero': 9, 'nome': 'Setembro'},
        {'numero': 10, 'nome': 'Outubro'},
        {'numero': 11, 'nome': 'Novembro'},
        {'numero': 12, 'nome': 'Dezembro'},
    )

    servidores = (
        Servidor.objects.vinculados()
        .filter(pessoa_fisica__nascimento_data__month=mes_escolhido, vinculos__sistema_origem='SIAPE')
        .order_by('pessoa_fisica__nascimento_data__day', 'pessoa_fisica__nome')
    )

    form = AniversarianteForm(request.GET or None, mes=mes_escolhido)
    if form.is_valid():
        campus = form.cleaned_data.get('uo')
        setor = form.cleaned_data.get('setor')
        servidores = servidores.filter(
            Q(setor__uo=campus) if campus else Q(),
            Q(setor=setor) if setor else Q(),
        )
    return locals()


@rtr()
@permission_required('rh.pode_ver_relatorios_rh')
def enderecos(request):
    def abreviar(endereco):
        return (
            endereco.upper()
            .replace('AVENIDA', 'AV')
            .replace('BLOCO', 'BL')
            .replace('NOVA', 'N')
            .replace('RUA', 'R')
            .replace('ESPERANCA', 'ESPER')
            .replace('PARQUE', 'PQ')
            .replace('SENADOR', 'SEN')
            .replace('RESIDENCIAL', 'RESID')
            .replace('APARTAMENTO', 'AP')
            .replace('APTO', 'AP')
            .replace('APT', 'AP')
            .replace('LACERDA MONTENEGRO', 'LACERDA')
        )

    def dividir_endereco(endereco):
        se = abreviar(s.endereco).split(',')
        if len(se) == 5:  # se nao tem complemento
            se.insert(2, '')
        return se

    lista = {f'Servidores Ativos por {nomenclatura.campus}': {}, 'Servidores por Situação': {}}
    lista['Servidores por Situação']['Substitutos'] = []
    for s in Servidor.objects.substitutos().filter(vinculos__sistema_origem='SIAPE'):
        lista['Servidores por Situação']['Substitutos'].append([s.nome, s.telefones, *dividir_endereco(s.endereco)])
    lista['Servidores por Situação']['Inativos'] = []
    for s in Servidor.objects.aposentados().filter(vinculos__sistema_origem='SIAPE'):
        lista['Servidores por Situação']['Inativos'].append([s.nome, s.telefones, *dividir_endereco(s.endereco)])
    lista['Servidores por Situação']['Cedidos'] = []
    for s in Servidor.objects.cedidos().filter(vinculos__sistema_origem='SIAPE'):
        lista['Servidores por Situação']['Cedidos'].append([s.nome, s.telefones, *dividir_endereco(s.endereco)])
    campus = list(UnidadeOrganizacional.objects.siape().all().order_by('setor__sigla').values_list('setor__sigla', flat=True))
    for c in campus:
        lista[f'Servidores Ativos por {nomenclatura.campus}'][c] = []
        for s in Servidor.objects.ativos_permanentes().filter(vinculos__sistema_origem='SIAPE').filter(setor__uo__setor__sigla=c):
            lista[f'Servidores Ativos por {nomenclatura.campus}'][c].append([s.nome, s.telefones, *dividir_endereco(s.endereco)])

    return locals()


@rtr('comum/templates/html_generico_para_listas.html')
@permission_required('rh.pode_ver_relatorios_rh')
def enderecos_fora_do_estado(request: HttpRequest) -> dict[str, object]:
    lista = [['Matrícula', 'Nome', 'Situação', 'Município / UF', 'E-mail']]
    uf = Configuracao.get_valor_por_chave('comum', 'instituicao_estado')
    pes = PessoaEndereco.objects.exclude(municipio__uf=uf).values_list('pessoa', flat=True)
    servidores = Servidor.objects.ativos().filter(pessoa_fisica__in=pes)
    for s in servidores:
        lista.append(
            [
                f'<a href="../servidor/{s.matricula}/">{s.matricula}</a>',
                s.nome,
                s.situacao.nome,
                f'{s.pessoaendereco.municipio.nome} / {s.pessoaendereco.municipio.uf}',
                s.email_notificacao,
            ]
        )
    servidores = pes = None
    mensagem = ''
    titulo = f'Servidores com endereço fora do {uf}'
    return locals()


@permission_required('rh.pode_gerenciar_extracao_siape')
def upload_arquivos_extrator(request: HttpRequest) -> HttpResponse:
    """Tela antiga aposentada: só o zip do extrator ganhou upload/agendamento na tela nova."""
    return httprr('/rh/importacao_siape/')


@rtr()
@permission_required('rh.view_pessoajuridica')
def pessoajuridica(request, pessoajuridica_id):
    pj = get_object_or_404(PessoaJuridica, pk=pessoajuridica_id)
    title = f'Pessoa Jurídica: {pj}'
    return locals()


@rtr()
@permission_required('rh.view_pessoajuridica')
def importar_pj(request):
    title = 'Importador de Pessoa Jurídica'
    form = ImportacaoPJForm(request.POST or None, files=request.FILES or None)
    if form.is_valid():
        errors = form.processar()
        if errors:
            return httprr('.', f'Ocorreram alguns erros na importação: {errors}', tag='error')
        else:
            return httprr('.', 'Dados importados com sucesso sem erros.')

    return locals()


@rtr()
@permission_required('rh.pode_gerenciar_setor_jornada_historico')
def setor_jornada_historico(request, setor_pk):
    setor = get_object_or_404(Setor, pk=setor_pk)
    title = f'Histórico de Jornadas de Trabalho do Setor {setor.sigla} - {setor.nome}'

    form_class = SetorJornadaHistoricoFormFactory(request)
    if request.POST:
        form = form_class(request.POST)
        if form.is_valid():
            form.save()

            return httprr('.', 'Histórico de Jornada adicionado com sucesso.')
    else:
        nova_jornada = SetorJornadaHistorico()
        nova_jornada.setor = setor
        form = form_class(instance=nova_jornada)

    #
    # restringe a lista de setores no formulário de adição
    #
    form.fields['setor'].widget = Select()
    form.fields['setor'].queryset = Setor.objects.suap_ativos().filter(id=setor.id)
    form.fields['setor'].initial = setor

    mensagens_periodos = setor.jornada_trabalho_pendencias()

    return locals()


@permission_required('rh.pode_gerenciar_setor_jornada_historico')
def setor_jornada_historico_remover(request, jornada_historico_pk):
    jornada_historico = SetorJornadaHistorico.objects.get(pk=jornada_historico_pk)
    setor_pk = jornada_historico.setor.pk
    jornada_historico.delete()
    return httprr(f'/rh/setor_jornada_historico/{setor_pk:d}/', 'Histórico removido com sucesso.')


@rtr()
@permission_required('rh.pode_gerenciar_setor_jornada_historico')
def setor_jornada_historico_pendencias(request):
    title = 'Setores com pendências em Histórico de Jornadas de Trabalho'

    if request.user.has_perm('rh.eh_rh_sistemico'):
        setores = Setor.objects.suap_ativos().all()
    else:
        #
        # exibe apenas os setores pertencentes ao mesmo campus do usuário logado
        #
        vinculo = request.user.get_vinculo()
        if vinculo.eh_funcionario():
            setores = Setor.objects.suap_ativos().filter(uo__sigla=vinculo.setor.uo.sigla)
        else:
            setores = []  # usuário logado tem permissão para gerenciar jornadas de trabalho de setores mas não é funcionário!!!!!

    setores_com_pendencias = []
    for setor in setores:
        if setor.jornada_trabalho_pendencias():
            setores_com_pendencias.append(setor)

    return locals()


@rtr()
@login_required
def atualizar_dados_avaliador(request):
    title = 'Atualizar Dados Pessoais'
    pessoa_fisica = request.user.get_profile()
    if not Avaliador.objects.filter(vinculo__pessoa=pessoa_fisica.pessoa_ptr).exists():
        raise PermissionDenied

    form = AtualizarDadosAvaliadorForm(request.POST or None, request=request)
    if form.is_valid():
        form.save()
        return httprr('..', 'Dados atualizados com sucesso.')

    return locals()


@rtr()
@login_required
def visualizar_avaliador(request: HttpRequest, avaliador_id: int) -> dict:
    avaliador = get_object_or_404(Avaliador, pk=avaliador_id)
    # A tela mostra CPF, nascimento e telefones: só quem gere avaliadores ou o próprio avaliador.
    if not request.user.has_perm('rh.view_avaliador') and avaliador.vinculo.user_id != request.user.id:
        raise PermissionDenied
    title = f'Avaliador {avaliador.vinculo.user.get_profile().nome}'

    return locals()


@rtr()
@permission_required('rh.pode_ver_relatorios_rh')
def afastamentos_servidores(request):
    title = 'Afastamentos dos Servidores'
    if request.method != 'POST':
        if 'filtros-afastamentos-post' in request.session:
            request.POST = request.session['filtros-afastamentos-post']
            request.method = 'POST'

    form = AfastamentosServidoresForm(request.POST or None)
    if request.method == 'POST':
        request.session['filtros-afastamentos-post'] = request.POST
        if form.is_valid():
            afastamentos_servidor = ServidorAfastamento.objects
            if form.cleaned_data.get('tipo_afastamento') != 'Todos':
                afastamentos_servidor = afastamentos_servidor.filter(afastamento__tipo=form.cleaned_data.get('tipo_afastamento'))

            if form.cleaned_data.get('categoria') != 'Todos':
                afastamentos_servidor = afastamentos_servidor.filter(
                    servidor__cargo_emprego__grupo_cargo_emprego__categoria__exact=form.cleaned_data.get('categoria')
                )

            if form.cleaned_data.get('situacao') != 'Todos':
                afastamentos_servidor = afastamentos_servidor.filter(cancelado=form.cleaned_data.get('situacao'))

            if form.cleaned_data.get('afastamento'):
                afastamentos_servidor = afastamentos_servidor.filter(afastamento=form.cleaned_data.get('afastamento'))

            if form.cleaned_data.get('uo'):
                afastamentos_servidor = afastamentos_servidor.filter(servidor__setor__uo=form.cleaned_data.get('uo'))

            afastamentos_servidor = afastamentos_servidor.filter(
                (Q(data_termino__gte=form.cleaned_data.get('data_inicio')) | Q(data_termino__isnull=True))
                & Q(data_inicio__lte=form.cleaned_data.get('data_termino'))
            )

            fields = ('servidor',)
            custom_fields = {
                'matricula': Column('Matricula', accessor='servidor.matricula', order_by='servidor__matricula'),
                'servidor': Column('Servidor', accessor='servidor', order_by='servidor__pessoa_fisica__nome'),
                'data_inicio': DateColumn(format='d/m/Y', verbose_name='Data de Início'),
                'data_termino': DateColumn(format='d/m/Y', verbose_name='Data de Término'),
                'afastamento': Column('Afastamento', accessor='afastamento', order_by='afastamento'),
                'tipo': Column('Tipo de Afastamento', accessor='afastamento.tipo', order_by='afastamento__tipo'),
                'cancelado': Column('Cancelado', accessor='cancelado', order_by='cancelado'),
            }
            sequence = ['servidor', 'matricula', 'data_inicio', 'data_termino', 'afastamento']
            table = get_table(
                request=request,
                queryset=afastamentos_servidor,
                fields=fields,
                custom_fields=custom_fields,
                sequence=sequence,
                per_page_field=50,
            )
            if request.GET.get('relatorio', None):
                return tasks.table_export(request.GET.get('relatorio', None), *table.get_params())

    return locals()


@rtr()
@login_required
@permission_required('rh.pode_ver_relatorios_viagens')
def viagens_consolidadas(request):
    title = 'Relatório de Viagens Consolidadas'

    form = ViagensPorCampusForm(request.POST or None, request=request)
    if form.is_valid():
        viagens = OrderedDict()
        ano = int(form.cleaned_data['ano'].ano)
        mes = int(form.cleaned_data['mes'])
        viagens_qs = Viagem.consolidadas.filter(data_inicio_viagem__year=ano).order_by('codigo_siorg')
        if mes:
            viagens_qs = viagens_qs.filter(data_inicio_viagem__month=mes)

        total_valor_desconto_auxilio_alimentacao = Decimal('0.0')
        total_valor_desconto_auxilio_transporte = Decimal('0.0')
        total_valor_passagem = Decimal('0.0')
        total_valor_diaria = Decimal('0.0')
        total_valor_viagem = Decimal('0.0')
        total_quantidade_viagens = 0

        for viagem in viagens_qs:
            if viagens.get(viagem.codigo_siorg):
                dicionario_por_siorg = viagens[viagem.codigo_siorg]
                dicionario_por_siorg['nome_siorg'] = viagem.nome_siorg
                dicionario_por_siorg['codigo_siorg'] = viagem.codigo_siorg
                dicionario_por_siorg['valor_desconto_auxilio_alimentacao'] = (
                    dicionario_por_siorg['valor_desconto_auxilio_alimentacao'] + viagem.valor_desconto_auxilio_alimentacao
                )
                dicionario_por_siorg['valor_desconto_auxilio_transporte'] = (
                    dicionario_por_siorg['valor_desconto_auxilio_transporte'] + viagem.valor_desconto_auxilio_transporte
                )
                dicionario_por_siorg['valor_passagem'] = dicionario_por_siorg['valor_passagem'] + viagem.valor_passagem
                dicionario_por_siorg['valor_diaria'] = dicionario_por_siorg['valor_diaria'] + viagem.valor_diaria
                dicionario_por_siorg['valor_viagem'] = dicionario_por_siorg['valor_viagem'] + viagem.valor_viagem
                dicionario_por_siorg['quantidade_viagens'] = dicionario_por_siorg['quantidade_viagens'] + 1
                viagens[viagem.codigo_siorg] = dicionario_por_siorg

            else:
                dicionario_por_siorg = {}
                dicionario_por_siorg['nome_siorg'] = viagem.nome_siorg
                dicionario_por_siorg['codigo_siorg'] = viagem.codigo_siorg
                dicionario_por_siorg['valor_desconto_auxilio_alimentacao'] = viagem.valor_desconto_auxilio_alimentacao
                dicionario_por_siorg['valor_desconto_auxilio_transporte'] = viagem.valor_desconto_auxilio_transporte
                dicionario_por_siorg['valor_passagem'] = viagem.valor_passagem
                dicionario_por_siorg['valor_diaria'] = viagem.valor_diaria
                dicionario_por_siorg['valor_viagem'] = viagem.valor_viagem
                dicionario_por_siorg['quantidade_viagens'] = 1
                viagens[viagem.codigo_siorg] = dicionario_por_siorg

            total_valor_desconto_auxilio_alimentacao += viagem.valor_desconto_auxilio_alimentacao
            total_valor_desconto_auxilio_transporte += viagem.valor_desconto_auxilio_transporte
            total_valor_passagem += viagem.valor_passagem
            total_valor_diaria += viagem.valor_diaria
            total_valor_viagem += viagem.valor_viagem
            total_quantidade_viagens += 1

    return locals()


@rtr()
@login_required
@permission_required('rh.pode_ver_relatorios_viagens_detalhados')
def viagens_consolidadas_detalhamento(request: HttpRequest, ano: int, mes: int, siorg: str) -> dict | HttpResponse:
    viagens = Viagem.consolidadas.filter(data_inicio_viagem__year=ano).order_by('codigo_siorg')
    mes_referencia = ''
    if int(mes):
        viagens = viagens.filter(data_inicio_viagem__month=int(mes))
        mes_referencia = Meses.get_mes(int(mes))

    campus = 'Todos'
    if siorg != 'todos':
        viagens = viagens.filter(codigo_siorg=siorg)
        primeira_viagem = viagens.first()
        campus = primeira_viagem.nome_siorg if primeira_viagem else siorg

    if viagens.exists():
        total_valor_desconto_auxilio_alimentacao = viagens.aggregate(Sum('valor_desconto_auxilio_alimentacao'))
        total_valor_desconto_auxilio_transporte = viagens.aggregate(Sum('valor_desconto_auxilio_transporte'))
        total_valor_passagem = viagens.aggregate(Sum('valor_passagem'))
        total_valor_diaria = viagens.aggregate(Sum('valor_diaria'))
        total_valor_viagem = viagens.aggregate(Sum('valor_viagem'))

        fields = (
            'numero_pcdp',
            'nome_siorg',
            'vinculo',
            'tipo_proposto',
            'objetivo_viagem',
            'valor_desconto_auxilio_alimentacao',
            'valor_desconto_auxilio_transporte',
            'valor_passagem',
            'valor_diaria',
            'valor_viagem',
            'situacao',
        )

        custom_fields = {
            'numero_pcdp': LinkColumn('tela_pcdp', kwargs={'pcdp_pk': Accessor('pk')}, verbose_name='Número PCDP', accessor=Accessor('numero_pcdp')),
            'data_inicio_viagem': DateColumn(format='d/m/Y'),
            'data_fim_viagem': DateColumn(format='d/m/Y'),
            'data_emissao_bilhete': DateColumn(
                format='d/m/Y',
                order_by='bilheteviagem.data_emissao',
                verbose_name='Data da Emissão dos Bilhetes',
                accessor='get_data_emissao_bilhetes',
            ),
        }

        sequence = ['numero_pcdp', 'nome_siorg', 'vinculo', 'tipo_proposto', 'objetivo_viagem']
        if 'relatorio' in request.GET:
            custom_fields['motivo_viagem'] = Column(verbose_name='Motivo da Viagem', accessor=Accessor('get_motivo_viagem_truncate'))
            sequence.append('motivo_viagem')

        sequence.append('data_inicio_viagem')
        sequence.append('data_fim_viagem')
        sequence.append('data_emissao_bilhete')

        table = get_table(request=request, queryset=viagens, fields=fields, custom_fields=custom_fields, sequence=sequence, per_page_field=50)
        table.add_sum_table_foot('valor_desconto_auxilio_alimentacao')
        table.add_sum_table_foot('valor_desconto_auxilio_transporte')
        table.add_sum_table_foot('valor_passagem')
        table.add_sum_table_foot('valor_diaria')
        table.add_sum_table_foot('valor_viagem')
        if request.GET.get('relatorio', None):
            return tasks.table_export(request.GET.get('relatorio', None), *table.get_params())

    title = 'Detalhamento do Relatório de Viagens Consolidadas do ano {} - {}'.format(ano, 'Todos')
    return locals()


@rtr()
@login_required
def tela_pcdp(request: HttpRequest, pcdp_pk: int) -> dict:
    viagem = get_object_or_404(Viagem, pk=pcdp_pk)
    # O importador do SCDP grava viagem sem servidor (proposto não servidor) e até sem vínculo (sem CPF).
    verificacao_propria = viagem.vinculo is not None and viagem.vinculo.user_id == request.user.id
    if not request.user.has_perm('rh.pode_ver_relatorios_rh') and not verificacao_propria:
        raise PermissionDenied('Você não tem permissão de acesso a essa página.')
    nome = viagem.vinculo.pessoa.nome if viagem.vinculo else viagem.nome_proposto
    title = 'Viagem de {} de {} à {}'.format(nome, viagem.data_inicio_viagem.strftime('%d/%m/%Y'), viagem.data_fim_viagem.strftime('%d/%m/%Y'))
    return locals()


def handle_uploaded_file_scdp(tipo, arquivo):
    if tipo == 0:
        destination = os.path.join(settings.BASE_DIR, 'rh/arquivos_scdp/viagens/', arquivo.name)
    elif tipo == 1:
        destination = os.path.join(settings.BASE_DIR, 'rh/arquivos_scdp/bilhetes/', arquivo.name)
    with open(os.path.join(destination), 'w') as f:
        f.writelines(arquivo.chunks())


@rtr()
@permission_required('rh.pode_gerenciar_extracao_scdp')
def scdp_importar_do_arquivo(request):
    title = 'Importar Arquivo do SCDP'
    form = ImportarArquivoSCDPForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        if request.POST.get('tipo'):
            handle_uploaded_file_scdp(int(request.POST.get('tipo')), form.files['arquivo'])
            return httprr(request.path, 'Upload de Arquivo SCDP feito com sucesso!')
        else:
            messages.error(request, 'Você não escolheu um tipo de arquivo.')
    return locals()


@rtr()
def scdp_importar_bilhetes_do_arquivo(request):
    if not request.user.is_superuser:
        raise PermissionDenied
    title = 'Importar Arquivo dos Bilhetes do DW-SCDP'
    form = ImportarArquivoSCDPForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        handle_uploaded_file_scdp(form.files['arquivo'])
        return httprr(request.path, 'Upload de Arquivo SCDP feito com sucesso!')
    return locals()


@rtr()
@permission_required('avaliacao_integrada.change_eixo')
def definir_areas_vinculacao(request):
    title = 'Definir Áreas dos Setores'
    form = DefinirAreasVinculacaoWizard(request.POST or None)
    if form.is_valid():
        form.processar()
        return httprr(request.path, 'Áreas vinculadas com sucesso.')
    return locals()


@rtr()
@permission_required('avaliacao_integrada.change_eixo')
def areas_vinculacao_setor(request):
    title = 'Áreas de Vinculação dos Setores'
    setor = Setor.objects.suap_ativos().get(sigla=get_sigla_reitoria())
    return locals()


@rtr()
@login_required()
def servidores_para_capacitacao_por_setor(request):
    title = 'Dados dos Servidores para concessão de capacitação Strictu Sensu'
    form = ServidoresParaCapacitacaoPorSetorForm(request.POST or None, request=request)
    if form.is_valid():
        setor = form.cleaned_data['setor']
        setores_filhos = form.cleaned_data['setores_filhos']
        servidor = request.user.get_relacionamento()
        jornada_maxima = 40
        if servidor.eh_chefe_do_setor_hoje(setor) or request.user.has_perm('rh.pode_ver_relatorios_rh'):
            servidores_do_setor = setor.get_servidores(recursivo=setores_filhos).annotate(titulacao_isnull=Count('titulacao'))
            servidores = servidores_do_setor.all().order_by('titulacao_isnull', 'titulacao__codigo')
            total_jornada_trabalho = 0
            total_jornada_trabalho_pca = 0
            total_jornada_maxima = 0
            for servidor in servidores:
                if not servidor.afastamentos_para_capacitacao_strictu_sensu_hoje.exists():
                    total_jornada_trabalho += servidor.jornada_trabalho.get_jornada_trabalho_semanal()
                if servidor.jornada_trabalho_servidor_pca and not servidor.afastamentos_para_capacitacao_strictu_sensu_hoje.exists():
                    total_jornada_trabalho_pca += int(servidor.jornada_trabalho_servidor_pca)
                total_jornada_maxima += 40
            porcentagens = []
            if total_jornada_maxima:
                porcentagem_total_jornada_trabalho = f'{(float(total_jornada_trabalho) / float(total_jornada_maxima)) * 100:.2f}'
                porcentagem_total_jornada_trabalho_pca = f'{(float(total_jornada_trabalho_pca) / float(total_jornada_maxima)) * 100:.2f}'
                porcentagem_total_jornada_trabalho_maxima = f'{(float(total_jornada_maxima) / float(total_jornada_maxima)) * 100:.2f}'
            else:
                porcentagem_total_jornada_trabalho_maxima = porcentagem_total_jornada_trabalho_pca = porcentagem_total_jornada_trabalho = f'{0:.2f}'

        else:
            messages.error(request, 'Você não pode acessar os dados desse setor.')
    return locals()


##########################
# Carga horária reduzida #
##########################


def _indeferir_ch_excepcional(request: HttpRequest, processo: CargaHorariaReduzida) -> HttpResponse:
    """Botão "Indeferir" da carga horária excepcional (POST ``indeferir_ch_excepcional`` da tela do processo)."""
    if not processo.pode_indeferir_ch_excepcional():
        raise PermissionDenied('Este processo não pode ser indeferido.')
    form = IndeferirProcessoAfastamentoParcialRHForm(request.POST, request=request)
    if not form.is_valid():
        return httprr(f'/rh/abrir_processo_afastamento_parcial/{processo.id}/', 'Informe o motivo do indeferimento.', tag='error')
    processo.indeferir_pelo_rh(request.user, form.cleaned_data['motivo_indeferimento_rh'])
    return httprr('/admin/rh/cargahorariareduzida/', 'Carga horária excepcional indeferida com sucesso.')


@rtr()
@login_required()
@group_required('Coordenador de Gestão de Pessoas Sistêmico, Coordenador de Gestão de Pessoas')
def abrir_processo_afastamento_parcial(request: HttpRequest, processo_id: int) -> dict | HttpResponse:
    processo = get_object_or_404(CargaHorariaReduzida, pk=processo_id)
    if not processo.no_escopo_do_rh(request.user):
        raise PermissionDenied
    title = 'Processo de Alteração de Carga Horária'
    eh_dono_processo = processo.servidor.get_vinculo() == request.user.get_vinculo()
    if request.POST:
        form_afastamento = SalvarProcessoAfastamentoForm(request.POST or None, request=request, processo=processo)

        if request.POST.get('acao', None) == 'salvar_ch_excepcional':
            if not processo.pode_deferir_ch_excepcional():
                raise PermissionDenied('Este processo não pode ser deferido.')
            try:
                if processo.horariosemanal_set.all().exists():
                    periodos_validos, periodos_mensagem = processo.validar_periodos_horarios()
                    if periodos_validos:
                        processo.deferir_pelo_rh(request.user)
                        return httprr('/admin/rh/cargahorariareduzida/', 'Carga horária excepcional cadastrada com sucesso.')
                    else:
                        return httprr(f'/rh/abrir_processo_afastamento_parcial/{processo.id}/', message=periodos_mensagem, tag='warning')
                else:
                    raise Exception('Adicione o horário padrão')
            except Exception as erro:
                return httprr(f'/rh/abrir_processo_afastamento_parcial/{processo.id}/', str(erro), tag='error')
        elif request.POST.get('acao', None) == 'indeferir_ch_excepcional':
            return _indeferir_ch_excepcional(request, processo)

    else:
        form_afastamento = SalvarProcessoAfastamentoForm(processo=processo)
        arquivos_pendentes_identificar_servidor = processo.documentos.all()
    # sem o required do HTML: o motivo divide o formulário com o "Deferir", que não o exige
    form_indeferimento = IndeferirProcessoAfastamentoParcialRHForm(request=request, use_required_attribute=False)

    usuario_logado_eh_rh_sistemico = request.user.has_group_cached('Coordenador de Gestão de Pessoas Sistêmico', ignore_groups_if_superuser=False)
    grupo_coordenador_rh_campus = request.user.has_group_cached('Coordenador de Gestão de Pessoas', ignore_groups_if_superuser=False)

    pode_adicionar_horario = processo.pode_alterar_horario(request.user, 'adicionar')
    pode_editar_horario = processo.pode_alterar_horario(request.user, 'editar')
    pode_remover_horario = processo.pode_alterar_horario(request.user, 'remover')
    pode_excluir_documento = processo.pode_anexar_documento(request.user)
    form = DocumentacaoExigidaUploadForm(request=request, processo=processo)

    return locals()


@login_required()
def excluir_processo_afastamento_parcial(request: HttpRequest, processo_id: int) -> HttpResponse:
    processo = get_object_or_404(CargaHorariaReduzida, pk=processo_id)
    if not processo.pode_ser_excluido_por(request.user):
        raise PermissionDenied

    processo.delete()  # o post_delete de DocumentacaoExigida (rh/signals.py) apaga os arquivos do storage

    return httprr('/admin/rh/cargahorariareduzida/', 'Processo excluído com sucesso.')


def get_upload_directory(instance):
    object_id = instance.id
    path = f'{PRIVATE_ROOT_DIR}/{object_id}'
    return path


class FileUploader:
    def __init__(self, backend=None, **kwargs):
        if is_remote_storage():
            self.get_backend = lambda: AWSUploadBackend(**kwargs)
        else:
            self.get_backend = lambda: LocalUploadBackend(**kwargs)

    def __call__(self, request, *args, **kwargs):
        return self._upload(request, *args, **kwargs)

    def _upload(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if request.method == 'POST':
            if 'processo' in request.GET:
                processo_id = request.GET['processo']
                processo = get_object_or_404(CargaHorariaReduzida, pk=processo_id)
            else:
                return HttpResponse(json.dumps({'success': False, 'status': 400}), content_type='application/json')
            if not processo.pode_anexar_documento(request.user):
                raise PermissionDenied
            content_type = str(request.META.get('CONTENT_TYPE', ''))
            content_length = int(request.META.get('CONTENT_LENGTH', 0))
            if content_type == '' or content_length == 0:
                return HttpResponse(json.dumps({'success': False, 'status': 400}), content_type='application/json')
            resolvido = upload_em_pdf(request)
            if resolvido is None:
                return HttpResponse(json.dumps({'success': False}), content_type='application/json')
            upload, is_raw, filename = resolvido

            # Here, we have the filename and file size
            backend = self.get_backend()

            # creating the destination upload directory
            upload_to = get_upload_directory(processo.servidor)
            # configuring the
            new_filename = backend.setup(upload_to, filename)
            # save the file
            success = backend.upload(upload, content_length, is_raw, *args, **kwargs)
            # callback
            uploaded_path = backend.upload_complete(*args, **kwargs) if success else None
            if success:
                arquivo_pk = create_on_upload(processo, uploaded_path, filename, content_length)
            else:
                arquivo_pk = None
            # let Ajax Upload know whether we saved it or not
            ret_json = {'success': success, 'filename': new_filename, 'chave': arquivo_pk, 'tamanho': content_length}
            return HttpResponse(json.dumps(ret_json, cls=DjangoJSONEncoder), content_type='text/html; charset=utf-8')

        else:
            response = HttpResponseNotAllowed(['POST'])
            response.write('ERROR: Only POST allowed')
            return response


def create_on_upload(processo, diretorio, nome_do_arquivo, tamanho_arquivo):
    novo_arquivo = DocumentacaoExigida()
    novo_arquivo.processo = processo
    novo_arquivo.diretorio = diretorio
    novo_arquivo.nome = nome_do_arquivo
    novo_arquivo.tamanho = tamanho_arquivo
    novo_arquivo.save()
    return novo_arquivo.encrypted_pk


file_uploaded = Signal()  # providing_args=['backend', 'request']
afastamento_pacial_upload = login_required()(FileUploader())


@login_required()
def visualizar_documentacao_pdf(request: HttpRequest, arquivo_id: str) -> HttpResponse:
    # o manager traduz ``encrypted_pk`` (chave inválida vira pk 0); o ``get_object_or_404(DocumentacaoExigida, ...)`` não passaria por ele
    arquivo = get_object_or_404(DocumentacaoExigida.objects.filter(encrypted_pk=arquivo_id))
    if not arquivo.processo.pode_ver_documentos(request.user):
        raise PermissionDenied
    pdf_data = mark_safe(default_storage.url(arquivo.diretorio))
    return render('viewer.html', locals())


@login_required()
@require_POST
def excluir_documentacao_pdf(request: HttpRequest, arquivo_id: str) -> JsonResponse:
    # POST com token CSRF: um GET (ex.: ``<img src>`` de outro site) não passa pela checagem de CSRF do Django
    arquivo = get_object_or_404(DocumentacaoExigida.objects.filter(encrypted_pk=arquivo_id))
    if not arquivo.processo.pode_anexar_documento(request.user):
        return JsonResponse({'ok': False, 'msg': 'Você não tem permissão para excluir o arquivo.'})
    arquivo.delete()  # o post_delete de DocumentacaoExigida (rh/signals.py) apaga o arquivo do storage
    return JsonResponse({'ok': True, 'msg': ''})


@rtr()
@permission_required(['rh.change_cargahorariareduzida'])
def alterar_situacao_afastamento_parcial_rh(request: HttpRequest, processo_id: int, situacao: str) -> dict | HttpResponse:
    processo = get_object_or_404(CargaHorariaReduzida, pk=processo_id)
    if not processo.no_escopo_do_rh(request.user) or not processo.pode_atualizar_situacao_pelo_rh():
        raise PermissionDenied('Você não pode validar este processo.')

    if situacao == 'deferir':
        try:
            if processo.horariosemanal_set.all().exists():
                periodos_validos, periodos_mensagem = processo.validar_periodos_horarios()
                if periodos_validos:
                    processo.deferir_pelo_rh(request.user)
                    return httprr(
                        '/admin/rh/cargahorariareduzida/?tab=tab_processos_validados_rh',
                        'Processo de alteração de carga horária deferido com sucesso.',
                    )
                else:
                    return httprr(f'/rh/abrir_processo_afastamento_parcial/{processo.id}/', message=periodos_mensagem, tag='warning')
            else:
                raise Exception('Adicione seu horário padrão')
        except Exception as erro:
            return httprr(f'/rh/abrir_processo_afastamento_parcial/{processo.id}/', str(erro), tag='error')

    elif situacao == 'indeferir':
        title = 'Indeferir Processo de Alteração de Carga Horária'
        form = IndeferirProcessoAfastamentoParcialRHForm(request.POST or None, request=request, instance=processo)
        if form.is_valid():
            processo.indeferir_pelo_rh(request.user, form.cleaned_data['motivo_indeferimento_rh'])
            return httprr('..', 'Processo de alteração de carga horária indeferido com sucesso.')

    return locals()


@rtr()
@permission_required('rh.change_cargahorariareduzida')
def adicionar_horario_afastamento_parcial(request: HttpRequest, processo_id: int) -> dict | HttpResponse:
    title = 'Adicionar Horário do Afastamento'
    processo = get_object_or_404(CargaHorariaReduzida, pk=processo_id)
    if not processo.pode_alterar_horario(request.user, 'adicionar'):
        raise PermissionDenied('Você não tem permissão para acessar essa tela.')

    horario_novo = HorarioSemanal()
    horario_novo.processo_afastamento = processo
    form = AdicionarHorarioAfastamentoForm(request.POST or None, request=request, processo=processo)
    if form.is_valid():
        form.save()
        return httprr('..', message='Horário salvo com sucesso.')

    return locals()


@rtr()
@permission_required('rh.change_cargahorariareduzida')
def editar_horario_afastamento(request: HttpRequest, horario_id: int) -> dict | HttpResponse:
    title = 'Editar Horário'
    horario = get_object_or_404(HorarioSemanal, pk=horario_id)
    if not horario.processo_reducao_ch.pode_alterar_horario(request.user, 'editar'):
        raise PermissionDenied('Você não tem permissão de acesso a esta tela.')

    form = EditarHorarioAfastamentoForm(request.POST or None, horario=horario)
    if form.is_valid():
        form.save()
        return httprr('..', message='Horário atualizado com sucesso.')
    return locals()


@permission_required('rh.change_cargahorariareduzida')
def remover_horario_afastamento(request: HttpRequest, horario_id: int) -> HttpResponse:
    horario = get_object_or_404(HorarioSemanal, pk=horario_id)
    if horario.processo_reducao_ch.pode_alterar_horario(request.user, 'remover'):
        horario.processo_reducao_ch.status = CargaHorariaReduzida.STATUS_ALTERANDO_HORARIO
        horario.processo_reducao_ch.save()
        horario.delete()
        return httprr(f'/rh/abrir_processo_afastamento_parcial/{horario.processo_reducao_ch.id}/', 'Horário removido com sucesso.')
    else:
        raise PermissionDenied


# -------------------------------------------------------------------------------------------------------------------


@rtr()
@login_required
@permission_required('rh.add_agendaatendimentohorario')
def adicionar_horario(request, acaosaude_id):
    acao_saude = get_object_or_404(AcaoSaude, pk=acaosaude_id)
    title = f'Adicionar Horário de Agendamento - {acao_saude.descricao}'

    form = AdicionarHorarioAcaoSaudeForm(request.POST or None, acao_saude=acao_saude)
    if form.is_valid():
        form.save()
        return httprr('.', 'Horário cadastrado com sucesso.')

    horarios = AgendaAtendimentoHorario.objects.filter(acao_saude=acao_saude)
    return locals()


@rtr()
@login_required
@permission_required('rh.delete_agendaatendimentohorario')
def remover_horario(request, horario_id):
    horario = get_object_or_404(AgendaAtendimentoHorario, pk=horario_id)
    acao_id = horario.acao_saude.id
    horario.delete()
    return httprr(f'/rh/adicionar_horario/{acao_id}/', 'Horário removido com sucesso.')


@rtr()
@login_required
@permission_required('rh.view_acaosaude')
def acao_saude(request, acao_id):
    acao_saude = get_object_or_404(AcaoSaude, pk=acao_id)
    title = f'Visualizar Ação de Saúde - {acao_saude.descricao}'
    hoje = datetime.now()
    vinculo = request.user.get_vinculo()
    servidor_logado = vinculo.relacionamento

    pode_cancelar_agendamento = request.user.has_perm('rh.pode_cancelar_agendamento')

    qs_horarioagendado = HorarioAgendado.objects.filter(horario__acao_saude=acao_saude, cancelado=False).order_by('horario__hora_inicio')
    agendamentos_cancelados = HorarioAgendado.objects.filter(horario__acao_saude=acao_saude, cancelado=True)

    # verificando usuários
    pode_ver_agenda_completa = acao_saude.pode_ver_toda_agenda(request.user)
    if not pode_ver_agenda_completa and not acao_saude.eh_profissional_da_acao(servidor_logado):
        qs_horarioagendado = qs_horarioagendado.filter(solicitante=vinculo)
        agendamentos_cancelados = agendamentos_cancelados.filter(solicitante=vinculo)
        pode_cancelar_agendamento = True  # se só vai ver os próprios agendamentos, também pode cancelá-los

    agenda_dia = qs_horarioagendado.filter(data_consulta=hoje)
    agendados = qs_horarioagendado.filter(data_consulta__gt=hoje)
    agendamentos_passados = qs_horarioagendado.filter(data_consulta__lt=hoje)

    if request.user.has_perm('rh.view_agendaatendimentohorario') and pode_ver_agenda_completa:
        form = AgendarAtendimentoForm(request.POST or None, request=request, acao_saude=acao_saude)
        if form.is_valid():
            horario = form.cleaned_data.get('horario')
            form.save()
            return httprr(f'/rh/acao_saude/{acao_saude.id}/?v={horario.id}', 'Agendamento cadastrado com sucesso.')

    return locals()


@rtr()
@login_required
@permission_required('rh.view_agendaatendimentohorario')
def agendar_horario(request, horario_id):
    title = 'Agendar Atendimento'
    horario = get_object_or_404(AgendaAtendimentoHorario, pk=horario_id)
    form = AgendarAtendimentoForm(request.POST or None, request=request, horario=horario)
    if form.is_valid():
        form.save()
        return httprr('..', 'Agendamento cadastrado com sucesso.')
    return locals()


@login_required
def cancelar_agendamento(request, horarioagendado_id):
    url_retorno = request.META.get('HTTP_REFERER')
    try:
        vinculo = request.user.get_vinculo()
        agendamento = HorarioAgendado.objects.filter(pk=horarioagendado_id, solicitante=vinculo).first()
        if request.user.has_perm('rh.pode_cancelar_agendamento') and agendamento:
            agendamento.cancelar_horario()
    except ObjectDoesNotExist:
        return httprr(url_retorno, 'Você não tem agendamento nesta ação de saúde para cancelar.', 'error')
    except MultipleObjectsReturned:
        return httprr(url_retorno, 'Erro. Mais de um objeto foi encontrado.', 'error')
    except Exception as e:
        return httprr(url_retorno, str(e), 'error')

    return httprr(url_retorno, 'Agendamento cancelado com sucesso.')


@rtr()
@permission_required('rh.delete_user')
def sincronizar_ws_siape(request):
    #
    # Sincroniza dados de um serviço específico
    #
    title = 'Consulta WebService SIAPE'
    form = WebserviceSIAPEForm(request.POST or None)
    if form.is_valid():
        ws = ImportadorWs()
        result = ws._call_service_siape(form.cleaned_data)
    return locals()


@rtr()
@login_required()
def test_importador_ws(request, cpf):
    importador = ImportadorWs()
    # test = importador.importacao_servidor(mask_numbers(cpf))
    importador.importacao_completa()

    return locals()


@rtr()
@group_required('Servidor')
def atualizar_meus_dados_servidor(request):
    servidor = request.user.get_relacionamento()
    cpf = mask_numbers(request.user.get_profile().cpf)
    try:
        importador = ImportadorWs()
        dados_atualizar = importador.importacao_servidor(mask_numbers(cpf), False, False)
        importador.atualizar_ferias_afastamentos(mask_numbers(cpf), ano_inicio=1990)
        msg = []
        for dados, criado in dados_atualizar:
            msg.append(f'Servidor <a href="{dados.get_absolute_url()}">{dados}</a> {"cadastrado" if criado else "atualizado"} com sucesso.')
        return httprr(servidor.get_absolute_url(), mark_safe(', '.join(msg)))

    except Exception as e:
        if settings.DEBUG:
            raise e
        return httprr(servidor.get_absolute_url(), str(e), 'error')


def _dependente_para_exibicao(importador: ImportadorWs, dependente: dict) -> dict:
    """Achata um dependente do SIAPE, com seus benefícios, nos campos que a aba exibe."""
    beneficios_brutos = (dependente.get('arrayBeneficios') or {}).get('Beneficio', [])
    if isinstance(beneficios_brutos, dict):
        beneficios_brutos = [beneficios_brutos]
    beneficios = []
    for beneficio in beneficios_brutos:
        data_fim = beneficio.get('dataFim', '00000000')
        beneficios.append(
            {
                'codigo': beneficio.get('codBeneficio'),
                'nome': beneficio.get('nomeBeneficio'),
                'data_inicio': importador._str_to_date(beneficio.get('dataInicio')),
                'data_fim': importador._str_to_date(data_fim) if data_fim != '00000000' else None,
            }
        )
    return {
        'nome': dependente.get('nome', ''),
        'cpf': mask_cpf(dependente.get('cpf', '')),
        'grau_parentesco': dependente.get('nomeGrauParentesco'),
        'condicao': dependente.get('nomeCondicao'),
        'beneficios': beneficios,
    }


def _dependentes_do_siape(importador: ImportadorWs, cpf: str) -> list[dict]:
    """Dependentes do CPF prontos para exibição, ou lista vazia se algo falhar.

    Extraído de `importar_servidor` para manter a view dentro do limite de
    complexidade. Mantém a tolerância original: dependente é dado complementar e não
    pode derrubar a tela. O SIAPE devolve a estrutura ora como lista, ora como
    dicionário único.
    """
    try:
        bruto = importador.get_dependentes(cpf)
        if not bruto:
            return []
        lista = (bruto[0].get('dadosDependentes') or {}).get('DadosDependentes', [])
        if isinstance(lista, dict):
            lista = [lista]
        return [_dependente_para_exibicao(importador, dependente) for dependente in lista]
    except Exception:
        return []


def _historico_pca_do_siape(importador: ImportadorWs, cpf: str, apenas_em_exercicio: bool) -> dict:
    """Histórico de provimentos de cargo do CPF, para a aba correspondente.

    Como as demais consultas complementares desta tela, uma falha aqui não derruba a
    importação: devolve o resultado vazio e a aba informa que nada foi encontrado.

    Recebe o mesmo filtro de vínculos do formulário para não exibir provimentos de
    vínculos que o resto da tela omitiu. As consultas ao SIAPE feitas aqui reaproveitam
    as que a importação acabou de fazer para o mesmo CPF (ver `ImportadorWs`).
    """
    try:
        return importador.get_historico_pca(cpf, ver_apenas_servidores_em_exercicio=apenas_em_exercicio)
    except Exception:
        logger.warning('Não foi possível recuperar o histórico de PCA do CPF %s.', mask_cpf(cpf), exc_info=True)
        return {'consultas': [], 'provimentos': []}


@rtr()
@login_required()
@group_required('Coordenador de Gestão de Pessoas Sistêmico, Coordenador de Gestão de Pessoas')
def importar_servidor(request, cpf=None, apenas_servidores_em_exercicio=False):
    title = 'Importar/Atualizar dados do servidor'
    try:
        form = ImportarServidorWSForm(request.POST or None)
        # verificando se o usuário pode acessar esta área (apenas RH e superuser)
        if form.is_valid():
            apenas_servidores_em_exercicio = form.cleaned_data.get('apenas_servidores_em_exercicio')
            cpf_form = form.cleaned_data.get('cpf')
            cpf_formatado = mask_cpf(cpf_form)
            #
            # verificando se o servidor existe para encontrar o ano de início das pesquisas

            ano_inicio = date.today().year
            _qs_servidor = Servidor.objects.filter(pessoa_fisica__cpf=cpf_formatado)
            if _qs_servidor.exists():
                _servidor = _qs_servidor.first()
                if _servidor.data_inicio_exercicio_na_instituicao:
                    ano_inicio = _servidor.data_inicio_exercicio_na_instituicao.year
            #
            cpf_limpo = mask_numbers(cpf_form)
            try:
                importador = ImportadorWs()
            except ValidationError as e:
                if settings.DEBUG:
                    raise e
                return httprr('/rh/importar_servidor/', f'Erro ao iniciar importador: {e}', 'error')

            dados_atualizar = importador.importacao_servidor(cpf_limpo, True, apenas_servidores_em_exercicio)  # retornar apenas os dados
            dados_ferias_afastamentos = importador.get_afastamento_historico(cpf_limpo, ano_inicio=ano_inicio)  # retornar apenas os dados
            # o SIAPE devolve um bloco por matrícula: servidores com mais de um
            # vínculo ativo têm férias e afastamentos distintos em cada um deles
            vinculos = [(dados['matricula'], dados.get('nome_apresentacao', '')) for dados in dados_atualizar]
            dados_ferias_por_servidor = agrupar_por_matricula(
                vinculos, ((parcela['ferias'].servidor.matricula, parcela) for parcela in dados_ferias_afastamentos['ferias'])
            )
            dados_afastamentos_por_servidor = agrupar_por_matricula(
                vinculos,
                ((afastamento['servidor'].matricula, afastamento) for afastamento in dados_ferias_afastamentos['afastamentos']),
            )

            dados_dependentes = _dependentes_do_siape(importador, cpf_limpo)
            dados_pca = _historico_pca_do_siape(importador, cpf_limpo, apenas_servidores_em_exercicio)

            # dados, criado = importador.importacao_servidor(mask_numbers(cpf))

        # cadastrando ou atualizando o servidor
        if cpf is not None:
            return rh_tasks.importar_servidor_ws(mask_numbers(cpf), apenas_servidores_em_exercicio)

    except Exception as e:
        if settings.DEBUG:
            raise e
        return httprr('/rh/importar_servidor/', str(e), 'error')

    return locals()


@rtr()
@permission_required('rh.eh_rh_sistemico')
def relatorio_afastamentos_saude(request):
    title = 'Relatório de afastamentos por motivo de saúde'
    form = RelatorioAfastamentosCriticosForm(request.GET or None, request=request)
    if form.is_valid():
        uo = form.cleaned_data.get('uo')
        categoria = form.cleaned_data.get('categoria')
        servidores = (
            Servidor.objects.filter(ativo=True)
            .annotate(
                quantidade_dias=Sum(
                    Case(
                        When(
                            servidorafastamento__afastamento__codigo__in=AfastamentoSiape.LICENCAS_TRATAMENTO_SAUDE,
                            then=F('servidorafastamento__quantidade_dias_afastamento'),
                        ),
                        default=Value(0),
                        output_field=IntegerField(),
                    )
                )
            )
            .filter(quantidade_dias__gte=400)
        )
        if uo:
            servidores = servidores.filter(setor__uo_id=uo)
        if categoria == 'tecnico_adminitrativo':
            servidores = servidores.filter(eh_tecnico_adminitrativo=True)
        elif categoria == 'docente':
            servidores = servidores.filter(eh_docente=True)
        fields = ('pessoa_fisica', 'matricula', 'setor', 'setor.uo', 'quantidade_dias')
        sequence = ['pessoa_fisica', 'matricula', 'setor', 'setor.uo', 'quantidade_dias']
        table = get_table(request=request, queryset=servidores, fields=fields, sequence=sequence, per_page_field=50)
        if request.GET.get('relatorio', None):
            return tasks.table_export(request.GET.get('relatorio', None), *table.get_params())

    return locals()


@rtr()
@permission_required('rh.eh_rh_sistemico, comum.is_reitor, comum.is_pro_reitor, comum.is_diretor_geral')
def disciplina_ingresso_docentes(request):
    form = DocentesPorDisciplinaFiltroForm(request.GET or None)
    title = 'Docentes por Disciplina de Ingresso'
    if 'edu' not in settings.INSTALLED_APPS_SUAP:
        return HttpResponse('O módulo de ensino não está instalado no SUAP.')
    docentes_por_disciplina = Servidor.objects.docentes().filter(situacao__codigo=Situacao.ATIVO_PERMANENTE)
    if form.is_valid():
        campus = form.cleaned_data.get('campus')
        disciplinas = form.cleaned_data.get('disciplinas')
        if disciplinas:
            if disciplinas == '1':
                docentes_por_disciplina = docentes_por_disciplina.filter(vinculos__professor__disciplina__isnull=True)
            elif disciplinas == '2':
                docentes_por_disciplina = docentes_por_disciplina.filter(vinculos__professor__disciplina__isnull=False)
        if campus:
            docentes_por_disciplina = docentes_por_disciplina.filter(setor__uo=campus)

    custom_fields = {
        'link_column': LinkColumn(
            'editar_disciplina_docente',
            kwargs={'docente_pk': Accessor('pk')},
            verbose_name='#',
            accessor=Accessor('pk'),
            attrs={'a': {'class': 'popup'}},
        ),
        'disciplina_ingresso': Column('Disciplina de Ingresso', accessor='disciplina_ingresso', order_by='vinculo__professor__disciplina'),
        'campus': Column(nomenclatura.campus, accessor='campus', order_by='setor__uo'),
    }
    fields = ('matricula', 'nome', 'setor', 'cargo_emprego')
    sequence = ['link_column', 'matricula', 'nome', 'campus', 'setor', 'cargo_emprego', 'disciplina_ingresso']
    table_docentes_por_disciplina = get_table(
        request=request, queryset=docentes_por_disciplina, fields=fields, sequence=sequence, per_page_field=100, custom_fields=custom_fields
    )
    if request.GET.get('relatorio', None):
        return tasks.table_export(request.GET.get('relatorio', None), *table_docentes_por_disciplina.get_params())
    return locals()


@rtr()
@permission_required('rh.view_setor')
def editar_bases_legais_setor(request, pk):
    setor = get_object_or_404(Setor, pk=pk)
    vinculo = request.user.get_relacionamento()
    eh_chefe_do_setor_hoje = hasattr(vinculo, 'eh_chefe_do_setor_hoje') and vinculo.eh_chefe_do_setor_hoje(setor)
    if not eh_chefe_do_setor_hoje:
        raise PermissionDenied

    title = f'Editar Bases Legais do Setor {setor}'
    form = BasesLegaisSetorForm(request.POST or None, instance=setor)
    if form.is_valid():
        form.save()
        return httprr('..', message=f'Bases Legais do Setor {setor} foi atualizada com sucesso.', tag='success', close_popup=True)
    return locals()


@rtr()
@permission_required('rh.view_setor')
def setor(request, pk):
    """Exibe a página de detalhes de um setor com servidores, chefias e permissões.

    Args:
        request: Requisição HTTP.
        pk: Chave primária do setor.

    Returns:
        dict: Variáveis de contexto para renderização do template.
    """
    setor = get_object_or_404(Setor, pk=pk)
    vinculo = request.user.get_relacionamento()
    eh_chefe_do_setor_hoje = hasattr(vinculo, 'eh_chefe_do_setor_hoje') and vinculo.eh_chefe_do_setor_hoje(setor)
    title = f'Setor: {setor.sigla} - {setor.nome}'
    servidores = Servidor.objects.ativos().filter(setor=setor, cargo_emprego__isnull=False).exclude(
        situacao__codigo__in=Situacao.situacoes_siape_estagiarios()
    ) | Servidor.objects.em_exercicio().filter(setor=setor, cargo_emprego__isnull=False).exclude(
        situacao__codigo__in=Situacao.situacoes_siape_estagiarios()
    ).order_by('pessoa_fisica__nome')
    estagiarios = Servidor.objects.estagiarios().filter(setor=setor).order_by('pessoa_fisica__nome')
    prestadores = PrestadorServico.objects.filter(setor=setor, ativo=True).order_by('pessoa_fisica__nome')
    if 'ae' in settings.INSTALLED_APPS:
        from ae.models import ParticipacaoTrabalho

        bolsistas = ParticipacaoTrabalho.objects.filter(
            (Q(participacao__data_termino__gte=datetime.today()) | Q(participacao__data_termino__isnull=True)) & Q(bolsa_concedida__setor=setor)
        ).order_by('participacao__aluno__pessoa_fisica__nome')
    filhos = Setor.objects.suap_ativos().filter(pk__in=[s.pk for s in setor.filhos])
    chefes_atuais = Servidor.objects.filter(
        pk__in=ServidorFuncaoHistorico.objects.atuais()
        .filter(setor_suap=setor, funcao__codigo__in=Funcao.get_codigos_funcao_chefia())
        .values_list('servidor', flat=True)
        .distinct()
    ).order_by('pessoa_fisica__nome')
    funcoes_chefes_atuais = []
    for chefe in chefes_atuais:
        funcoes_chefes_atuais.append(
            {'servidor': chefe, 'funcoes': ServidorFuncaoHistorico.objects.atuais().filter(setor_suap=setor, servidor=chefe)}
        )
    servidores_com_acesso = Servidor.objects.ativos().filter(vinculos__setores_adicionais=setor).order_by('pessoa_fisica__nome')
    estagiarios_com_acesso = Servidor.objects.estagiarios().filter(vinculos__setores_adicionais=setor).order_by('pessoa_fisica__nome')
    prestadores_com_acesso = PrestadorServico.objects.filter(vinculos__setores_adicionais=setor, ativo=True).order_by('pessoa_fisica__nome')

    servidores_inativos = ServidorSetorHistorico.objects.filter(setor=setor, data_fim_no_setor__isnull=False).order_by('-data_inicio_no_setor')

    ldap_conf = get_ldap_conf()
    tem_permissao_acessar_ldap = request.user.has_perm('ldap_backend.view_ldap_user')
    if not tem_permissao_acessar_ldap or not ldap_conf or not ldap_conf.has_connectivity() or not ldap_conf.has_write_permission():
        tem_permissao_acessar_ldap = False
    else:
        tem_ldap_obj = ldap_conf.get_ou_by_admin_description(pk)
        tem_permissao_acessar_ldap = True

    return locals()


@rtr()
@permission_required('rh.view_setor')
def setor_detalhes(request, setor_pk):
    """Exibe os detalhes de um setor para o modal de visualização.

    Args:
        request: Requisição HTTP.
        setor_pk: Chave primária do setor.

    Returns:
        dict: Variáveis de contexto para renderização do modal.
    """
    setor = get_object_or_404(Setor, pk=setor_pk)
    vinculo = request.user.get_relacionamento()
    eh_chefe_do_setor_hoje = hasattr(vinculo, 'eh_chefe_do_setor_hoje') and vinculo.eh_chefe_do_setor_hoje(setor)
    servidores = Servidor.objects.ativos().filter(setor=setor, cargo_emprego__isnull=False).exclude(
        situacao__codigo__in=Situacao.situacoes_siape_estagiarios()
    ) | Servidor.objects.em_exercicio().filter(setor=setor, cargo_emprego__isnull=False).exclude(
        situacao__codigo__in=Situacao.situacoes_siape_estagiarios()
    )
    estagiarios = Servidor.objects.estagiarios().filter(setor=setor)
    prestadores = PrestadorServico.objects.filter(setor=setor, ativo=True)
    if 'ae' in settings.INSTALLED_APPS:
        from ae.models import ParticipacaoTrabalho

        bolsistas = ParticipacaoTrabalho.objects.filter(
            (Q(participacao__data_termino__gte=datetime.today()) | Q(participacao__data_termino__isnull=True)) & Q(bolsa_concedida__setor=setor)
        )
    filhos = Setor.objects.suap_ativos().filter(pk__in=[s.pk for s in setor.filhos])
    chefes_atuais = Servidor.objects.filter(
        pk__in=ServidorFuncaoHistorico.objects.atuais()
        .filter(setor_suap=setor, funcao__codigo__in=Funcao.get_codigos_funcao_chefia())
        .values_list('servidor', flat=True)
        .distinct()
    )
    funcoes_chefes_atuais = []
    for chefe in chefes_atuais:
        funcoes_chefes_atuais.append(
            {'servidor': chefe, 'funcoes': ServidorFuncaoHistorico.objects.atuais().filter(setor_suap=setor, servidor=chefe)}
        )
    servidores_com_acesso = Servidor.objects.ativos().filter(vinculos__setores_adicionais=setor)
    estagiarios_com_acesso = Servidor.objects.estagiarios().filter(vinculos__setores_adicionais=setor)
    prestadores_com_acesso = PrestadorServico.objects.filter(vinculos__setores_adicionais=setor, ativo=True)
    return locals()


@rtr()
@permission_required('rh.view_setor')
def organograma(request):
    title = 'Organograma'
    FormClass = SetorRaizFormFactory(request)
    form = FormClass(request.POST or None)
    if form.is_valid():
        setor_raiz = form.cleaned_data['raiz'].pk
    return locals()


@permission_required('rh.view_setor')
def organograma_data(request):
    """Retorna os dados do organograma hierárquico em formato JSON.

    Args:
        request: Requisição HTTP com parâmetro opcional ``setor_raiz``.

    Returns:
        JsonResponse: Dados formatados para o gráfico de organograma do Highcharts.
    """
    servidor_logado = request.user.get_relacionamento()
    setor_raiz = servidor_logado.setor
    setor_raiz_form = request.GET.get('setor_raiz')
    if setor_raiz_form:
        setor_raiz = Setor.objects.suap_ativos().filter(pk=int(setor_raiz_form)).first()

    if not setor_raiz:
        return JsonResponse({'error': 'Setor raiz não encontrado.'}, status=404)

    dataset = []
    nodes = []
    filhos_pks = [s.pk for s in setor_raiz.filhos]
    width_calc = Setor.objects.suap_ativos().filter(pk__in=filhos_pks).count() * 100
    width = max(width_calc, 1000)
    for setor in Setor.objects.suap_ativos().filter(pk__in=[*filhos_pks, setor_raiz.pk]):
        nodes.append(
            {
                'id': setor.sigla,
                'name': f'<span onclick="preencher_setor(\'/rh/setor_detalhes/{setor.pk}/\')">{setor.sigla}</span>',
                'image': setor.chefes.all().first().get_foto_75x100_url() if setor.chefes.all().first() else '',
            }
        )
        if setor.superior and not setor.excluido:
            dataset.append([setor.superior.sigla, setor.sigla])

    levels = [
        {'level': 0, 'color': '#3498db', 'colorText': 'white'},
        {'level': 1, 'color': '#95a5a6'},
        {'level': 2, 'color': '#7f8c8d'},
        {'level': 3, 'color': '#bdc3c7'},
        {'level': 4, 'layout': 'hanging', 'color': 'silver'},
    ]
    chart = {
        'chart': {'type': 'organization', 'inverted': True, 'width': width, 'height': 400},
        'title': {'useHTML': True, 'text': f'Organograma {setor_raiz}'},
        'tooltip': False,
        'series': [
            {
                'name': Configuracao.get_valor_por_chave('comum', 'instituicao_sigla'),
                'keys': ['from', 'to'],
                'data': dataset,
                'levels': levels,
                'nodes': nodes,
                'colorByPoint': False,
            }
        ],
        'xAxis': {'scrollbar': {'enabled': True}},
    }
    return JsonResponse(chart)


@rtr()
@permission_required('rh.eh_rh_sistemico')
def editar_servidor_cargo_emprego_area(request, servidor_pk):
    servidor = get_object_or_404(Servidor, pk=servidor_pk)
    title = f'Editar Área do Cargo Emprego do servidor: {servidor}'
    form = EditarServidorCargoEmpregoAreaForm(request.POST or None, instance=servidor)
    if form.is_valid():
        form.save()
        return httprr('..', message=f'Área do Cargo Emprego de {servidor} foi atualizada com sucesso.', tag='success', close_popup=True)
    return locals()


@rtr()
@permission_required('rh.eh_rh_sistemico, comum.is_reitor, comum.is_pro_reitor, comum.is_diretor_geral')
def servidores_por_area(request):
    form = ServidoresPorAreaFiltroForm(request.GET or None)
    title = 'Servidores por Área'
    servidores_por_area = Servidor.objects.ativos().filter(cargo_emprego__cargoempregoarea__isnull=False).distinct()
    if form.is_valid():
        campus = form.cleaned_data.get('campus')
        cargo_emprego = form.cleaned_data.get('cargo_emprego')
        cargo_emprego_area = form.cleaned_data.get('cargo_emprego_area')
        com_area_cadastrada = form.cleaned_data.get('com_area_cadastrada')
        if com_area_cadastrada:
            if com_area_cadastrada == '1':
                servidores_por_area = servidores_por_area.filter(cargo_emprego_area__isnull=False)
            elif com_area_cadastrada == '2':
                servidores_por_area = servidores_por_area.filter(cargo_emprego_area__isnull=True)
        if cargo_emprego:
            servidores_por_area = servidores_por_area.filter(cargo_emprego=cargo_emprego)
        if cargo_emprego_area:
            servidores_por_area = servidores_por_area.filter(cargo_emprego_area=cargo_emprego_area)
        if campus:
            servidores_por_area = servidores_por_area.filter(setor__uo=campus)

    custom_fields = {
        'link_column': LinkColumn(
            'editar_servidor_cargo_emprego_area',
            kwargs={'servidor_pk': Accessor('pk')},
            verbose_name='#',
            accessor=Accessor('pk'),
            attrs={'a': {'class': 'popup'}},
        ),
        'campus': Column(nomenclatura.campus, accessor='campus', order_by='setor__uo'),
    }
    fields = ('matricula', 'nome', 'setor', 'cargo_emprego', 'cargo_emprego_area')
    sequence = ['link_column', 'matricula', 'nome', 'campus', 'setor', 'cargo_emprego', 'cargo_emprego_area']
    table_servidores_por_area = get_table(
        request=request, queryset=servidores_por_area, fields=fields, sequence=sequence, per_page_field=100, custom_fields=custom_fields
    )
    if request.GET.get('relatorio', None):
        return tasks.table_export(request.GET.get('relatorio', None), *table_servidores_por_area.get_params())
    return locals()


@login_required()
def arquivo_unico(request, hash_sha512_link_id):
    try:
        try:
            arquivo_unico = ArquivoUnico.objects.get(hash_sha512_link_id=hash_sha512_link_id)
            response = HttpResponse(content=arquivo_unico.get_conteudo_as_bytes(), content_type=arquivo_unico.tipo_conteudo)

            filename = request.GET.get('filename')
            if filename:
                filename = retira_acentos(filename.replace(' ', ''))
                response['Content-Disposition'] = f'inline; filename={filename};'
            else:
                response['Content-Disposition'] = 'inline;'

            return response
        except ArquivoUnico.DoesNotExist:
            raise Http404('O arquivo solicitado não existe.')
    except Exception as e:
        msg_error = 'Erro ao tentar obter o arquivo.'
        if settings.DEBUG:
            msg_error += f' Detalhes: {e}'
        raise Http404(msg_error)


@rtr()
@permission_required('rh.eh_rh_sistemico, rh.eh_rh_campus')
def validaralteracaofoto(request: HttpRequest, solicitacao_id: int) -> HttpResponse:
    solicitacao = get_object_or_404(SolicitacaoAlteracaoFoto.visiveis(request.user), pk=solicitacao_id)
    try:
        solicitacao.validar(request.user)
        return httprr('/admin/rh/solicitacaoalteracaofoto/', 'Solicitação validada com sucesso.')
    except Exception as ex:
        return httprr('/admin/rh/solicitacaoalteracaofoto/', ex, tag='error')


@rtr()
@permission_required('rh.eh_rh_sistemico, rh.eh_rh_campus')
def rejeitaralteracaofoto(request: HttpRequest, solicitacao_id: int) -> HttpResponse | dict:
    solicitacao = get_object_or_404(SolicitacaoAlteracaoFoto.visiveis(request.user), pk=solicitacao_id)
    try:
        form = RejeitarSolicitacaoAlteracaoFotoForm(request.POST or None, instance=solicitacao)
        if form.is_valid():
            form.processar(request)
            return httprr('/admin/rh/solicitacaoalteracaofoto/', 'Solicitação rejeitada.', close_popup=True)
        return locals()
    except Exception as ex:
        return httprr('/admin/rh/solicitacaoalteracaofoto/', ex, close_popup=True)


@rtr()
@login_required()
def detalhe_solicitacao_alteracao_foto(request: HttpRequest, solicitacao_id: int) -> dict:
    solicitacao = get_object_or_404(SolicitacaoAlteracaoFoto.visiveis(request.user), pk=solicitacao_id)
    pode_analisar = SolicitacaoAlteracaoFoto.pode_analisar(request.user)

    title = f'Solicitação de Alteração de Foto: {solicitacao.solicitante}'
    solicitacao_aguardando_validacao = solicitacao.situacao == SolicitacaoAlteracaoFoto.AGUARDANDO_VALIDACAO

    return locals()


@rtr()
@login_required()
def pessoa_info_complementar(request, vinculo_id):
    vinculo = get_object_or_404(Vinculo, id=vinculo_id)
    verificacao_propria = request.user == vinculo.user
    pode_ver_dados_pessoais_servidor = request.user.has_perm('rh.pode_ver_dados_pessoais_servidor', ignore_superuser=True)
    pode_ver_dados_pessoais_aluno = request.user.has_perm('edu.view_dados_pessoais', ignore_superuser=True)
    if not (verificacao_propria or pode_ver_dados_pessoais_servidor or pode_ver_dados_pessoais_aluno):
        raise PermissionDenied

    if request.GET.get('id_api_atualizar', False):
        api_origem = APIExterna.objects.filter(pk=int(request.GET.get('id_api_atualizar'))).first()
        if api_origem.ativo:
            PessoaInfoComplementar.get_instance(pessoa=vinculo.pessoa, api_origem=api_origem, usuario_consulta=request.user, force=True)
            messages.success(request, 'Informações Atualizadas')
        else:
            messages.error(request, 'A API selecionada está inativa.')
    qs_pessoa_info_complementar = PessoaInfoComplementar.objects.filter(pessoa=vinculo.pessoa)
    title = f'Informações Complementares de {vinculo.pessoa.nome}'
    return locals()


@rtr()
@login_required()
def importar_dados_completares_pessoa(request, vinculo_id):
    vinculo = get_object_or_404(Vinculo, id=vinculo_id)
    verificacao_propria = request.user == vinculo.user
    pode_ver_dados_pessoais_servidor = request.user.has_perm('rh.pode_ver_dados_pessoais_servidor', ignore_superuser=True)
    pode_ver_dados_pessoais_aluno = request.user.has_perm('edu.view_dados_pessoais', ignore_superuser=True)
    if not (verificacao_propria or pode_ver_dados_pessoais_servidor or pode_ver_dados_pessoais_aluno):
        raise PermissionDenied

    title = 'Obter Informações Complementares'

    form = ObterDadosCompletaresPessoaForm(request.POST or None, files=request.FILES or None)
    if form.is_valid():
        mensagem = form.processar(vinculo.pessoa, request.user)
        if mensagem:
            return httprr('..', mensagem)

    return locals()


@rtr()
@login_required()
def ver_alerta_rh(request, id):
    alerta = get_object_or_404(AlertaGestaoPessoa, id=id)
    vinculo_usuario = request.user.get_vinculo()
    setor_rh_pk = Configuracao.get_valor_por_chave('rh', 'setor_rh')
    setor = Setor.objects.suap_ativos().filter(pk=setor_rh_pk or 0).first()
    if not setor or request.user.get_relacionamento() not in setor.chefes:
        raise PermissionDenied('Você não pode acessar essa funcionalidade.')
    # registrar todas as visualizações dos usuários com permissão
    obj = AlertaGestaoPessoaVisualizacao()
    obj.alerta_visualizado = alerta
    obj.vinculo = vinculo_usuario
    obj.data_visualizacao = datetime.now()
    obj.save()
    return locals()


@rtr()
@transaction.atomic()
@permission_required('rh.add_pessoajuridica')
def importar_pessoajuridica_api_rfb(request):
    """
    Importação de Pessoa Jurídica com base nas informações da API https://www.gov.br/conecta/catalogo/apis/consulta-cnpj
    """
    title = 'Importar Pessoa Jurídica da base do CNPJ/RFB'
    try:
        form = BuscarPessoaJuridicaApiRFBForm(request.GET or None)
        dict_info_cnpj = None
        if dict_info_cnpj or form.is_valid():
            sucesso, dict_info_cnpj = form.buscar()
            if dict_info_cnpj:
                request.session['dict_info_cnpj'] = dict_info_cnpj
            if request.GET.get('acao') and not dict_info_cnpj:
                dict_info_cnpj = request.session.pop('dict_info_cnpj', None)

            if dict_info_cnpj:
                # Verifica se existe PessoaJuridica com o CNPJ informado
                cnpj_com_digitos = mask_cnpj(dict_info_cnpj['ni'])
                possui_cadastro = PessoaJuridica.objects.filter(cnpj=cnpj_com_digitos).exists()
                operacao = 'atualizar' if possui_cadastro else 'cadastrar'

                if not request.GET.get('acao'):
                    messages.success(
                        request,
                        f'Verifique informações obtidas da Receita Federal do Brasil (RFB) e  clique em Salvar para {operacao} as informações da empresa CNPJ: {cnpj_com_digitos}.',
                    )

                if request.GET.get('acao') == 'salvar':
                    with transaction.atomic():
                        dict_pessoajuridica = {
                            'nome': dict_info_cnpj.get('nomeEmpresarial', ''),
                            'nome_fantasia': dict_info_cnpj.get('nomeFantasia', ''),
                            'nome_representante_legal': dict_info_cnpj.get('socios')
                            and len(dict_info_cnpj['socios']) > 0
                            and dict_info_cnpj['socios'][0].get('representanteLegal', {}).get('nome', ''),
                            'optante_simples': dict_info_cnpj.get('informacoesAdicionais', {}).get('optanteSimples') == 'SIM',
                            'optante_mei': dict_info_cnpj.get('informacoesAdicionais', {}).get('optanteMei', '') == 'NÃO',
                            'situacao_cadastral_codigo': dict_info_cnpj.get('situacaoCadastral', {}).get('codigo', ''),
                            'situacao_cadastral_motivo': dict_info_cnpj.get('situacaoCadastral', {}).get('motivo', ''),
                            'situacao_cadastral_data': dict_info_cnpj.get('situacaoCadastral', {}).get('data')
                            and datetime.strptime(dict_info_cnpj['situacaoCadastral']['data'], '%Y-%m-%d').date(),
                            'natureza_juridica_codigo': dict_info_cnpj.get('naturezaJuridica', {}).get('codigo', ''),
                            'natureza_juridica_descricao': dict_info_cnpj.get('naturezaJuridica', {}).get('descricao', ''),
                            'data_abertura': dict_info_cnpj.get('dataAbertura')
                            and datetime.strptime(dict_info_cnpj['dataAbertura'], '%Y-%m-%d').date(),
                            'cnae_principal_codigo': dict_info_cnpj.get('cnaePrincipal', {}).get('codigo', ''),
                            'cnae_principal_descricao': dict_info_cnpj.get('cnaePrincipal', {}).get('descricao', ''),
                        }
                        pessoajuridica, criou = PessoaJuridica.objects.update_or_create(cnpj=cnpj_com_digitos, defaults=dict_pessoajuridica)
                        if pessoajuridica:
                            telefones = dict_info_cnpj.get('telefone', [])
                            for telefone in telefones:
                                dict_pessoa_telefone = {'descricao': 'Telefone cadastro RFB', 'telefone': f'({telefone["ddd"]}) {telefone["numero"]}'}
                                pessoatelefone, criou = PessoaJuridicaContato.objects.update_or_create(
                                    pessoa_juridica=pessoajuridica, defaults=dict_pessoa_telefone
                                )

                            if dict_info_cnpj.get('endereco', False):
                                dict_info_cnpj_endereco = dict_info_cnpj.get('endereco')
                                municipio = Municipio.objects.filter(codigo=dict_info_cnpj_endereco['municipio']['codigo']).first()
                                dict_pessoa_endereco = {
                                    'municipio': municipio,
                                    'logradouro': dict_info_cnpj_endereco['logradouro'],
                                    'numero': dict_info_cnpj_endereco['numero'],
                                    'complemento': dict_info_cnpj_endereco['complemento'],
                                    'bairro': dict_info_cnpj_endereco['bairro'],
                                    'cep': dict_info_cnpj_endereco['cep'],
                                }
                                pessoaendereco, criou = PessoaEndereco.objects.update_or_create(pessoa=pessoajuridica, defaults=dict_pessoa_endereco)

                                # Atualiza informações na classe PessoaInfoComplementar
                                api_externa = APIExterna.CNPJ
                                if api_externa.ativo:
                                    PessoaInfoComplementar.get_instance(pessoa=pessoajuridica, api_origem=api_externa, force=True)

                            return httprr(
                                pessoajuridica.get_absolute_url(), f'Pessoa Juridíca {"atualizada" if possui_cadastro else "cadastrada"} com sucesso.'
                            )
            elif not dict_info_cnpj:
                messages.warning(request, 'Não foi possível localizar a Pessoa Jurídica na base da RFB.')
        return locals()

    except Exception as e:
        if settings.DEBUG:
            raise e
        mensagem = f'Ocorreu um erro ao importar a Pessoa Jurídica e o mesmo já foi reportado para equipe de desenvolvimento realizar a correção: Detalhes {e!s}'
        capture_exception(e)
        return httprr('.', str(e), 'error')


@rtr()
@permission_required('rh.eh_rh_sistemico')
def equivalencia_setor(request, id):
    setor = get_object_or_404(Setor, pk=id)  # sempre será um setor SUAP
    #
    if not request.user.has_perm('rh.eh_rh_sistemico'):
        raise PermissionDenied('Você não tem permissão para acessar esta página.')
    if setor.codigo is not None:
        raise PermissionDenied('Este setor não pode receber o código de equivalência por se tratar de um setor SIAPE.')
    #
    title = f'Equivalência de Setor ({setor})'
    form = EquivalenciaSetorForm(request.POST or None, instance=setor)
    if form.is_valid():
        form.save()
        return httprr('..', message=f'Equivalência do setor {setor} foi atualizada com sucesso.', tag='success', close_popup=True)
    return locals()


@rtr()
@login_required()
def unificar_pessoas(request):
    from rh.deduplicacao.aplicacao import ERROS_DO_GRUPO
    from rh.deduplicacao.manual import previa, unificar

    if not request.user.is_superuser:
        raise PermissionDenied
    title = 'Unificar Pessoas Físicas'
    form = UnificarPessoasForm(request.POST or None)
    if form.is_valid():
        fica, sai = form.cleaned_data['pessoas']
        if form.cleaned_data['confirmar']:
            try:
                unificar(fica.pk, sai.pk, request.user.username)
            except ERROS_DO_GRUPO as erro:
                return httprr('.', f'Nada foi alterado: {erro}', tag='error')
            return httprr('.', f'Pessoa física {sai.pk} unificada em {fica.pk} ({fica}).')
        preenchimentos, descartes = previa(fica.pk, sai.pk)
        preenchidos = [_campo_da_previa(sai, campo, valor) for campo, valor in preenchimentos.items()]
        descartados = [_campo_da_previa(sai, campo, valor) for _, campo, valor in descartes]
        pessoas = [
            (rotulo, pessoa, Vinculo.objects.filter(pessoa_id=pessoa.pk).select_related('user')) for rotulo, pessoa in (('Fica', fica), ('Sai', sai))
        ]
    return locals()


def _campo_da_previa(perdedora: PessoaFisica, attname: str, valor: object) -> tuple[str, object]:
    """Rótulo e valor (da pessoa que sai) para a prévia: FK pelo objeto, biometria e senha omitidas como na auditoria."""
    from rh.deduplicacao.campos import SEM_VALOR_NA_AUDITORIA

    campo = next(campo for campo in PessoaFisica._meta.concrete_fields if campo.attname == attname)
    if attname in SEM_VALOR_NA_AUDITORIA:
        return campo.verbose_name, '(valor omitido)'
    return campo.verbose_name, getattr(perdedora, campo.name) if campo.is_relation else valor
