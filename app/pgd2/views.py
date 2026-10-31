import base64
import io
import operator
from collections import defaultdict
from datetime import date, timedelta
from functools import reduce

import qrcode
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import CharField, F, Q, Sum, Value
from django.shortcuts import get_object_or_404
from django.template.defaultfilters import pluralize
from django.urls import reverse
from django.utils.safestring import mark_safe

from comum.utils import get_acoes_por_periodo
from demandas.models import AnalistaDesenvolvedor
from djtools import layout
from djtools.templatetags.filters import format_datetime
from djtools.utils import get_client_ip, httprr, permission_required, rtr
from pgd2 import tasks
from pgd2.api_pgd2_v2 import get_api_pgd2_v2
from pgd2.forms import (
    AjustarHorasSemestreRitForm,
    AnaliseCompletaExecucaoPesForm,
    AnaliseDetalhadaExecucaoPesForm,
    AnaliseSimplificadaExecucaoPesForm,
    AvaliacaoPesForm,
    AvaliacaoPitLoteForm,
    AvaliacaoRitForm,
    AvaliacaoRitLoteForm,
    BuscarAcompanhamentoPesExecucaoForm,
    BuscarAcompanhamentoPesPlanejamentoForm,
    BuscarPitsChefeForm,
    BuscarPitsChefeFormSimples2,
    BuscarPitsPgdForm,
    BuscarRelatorioDesligamentoForm,
    BuscarRelatorioQuestionarioRitForm,
    BuscarRitsChefeForm,
    BuscarRitsChefeFormSimples2,
    BuscarServidoresApiPgdForm,
    BuscarServidoresPendenciaPgdForm,
    BuscarServidoresPgdForm,
    BuscarServidoresPgdGestaoForm,
    BuscarServidoresPublicoPgdForm,
    BuscarSetoresPgdForm,
    CadastrarDesligamentoGestaoPgdForm,
    CadastrarDesligamentoPgdForm,
    ComfirmacaoComSenhaIrreversivelForm,
    ConfirmacaoComSenhaForm,
    ConsultaDesligamento,
    ConsultaMonitoramentoPes,
    ConsultaMonitoramentoPit,
    ConsultaMonitoramentoServidorSimples,
    CopiarPesForm,
    CopiarPitForm,
    CopiarPitRelacionarEntregasForm,
    CriarPitForm,
    DesfazerDistribuirHorasAutoRitForm,
    DesfazerDistribuirHorasCompensacaoEspecificaRitForm,
    DesfazerDistribuirHorasSemestreRitForm,
    DistribuirHorasAutoRitForm,
    EditarDadosBasicosPitCopiaForm,
    EditarDadosBasicosPitForm,
    EditarTelefonePgdForm,
    HomologarPitForm,
    JustificativaComSenhaForm,
    JustificativaComSenhaIrreversivelForm,
    JustificativaObrigatoriaComSenhaForm,
    PlanoEntregasSetorialEditarAuxiliaresForm,
    PlanoEntregasSetorialEditarDocumentacaoForm,
    PlanoEntregasSetorialEntregaCadastrarForm,
    PlanoEntregasSetorialHorarioFuncionamentoSetorCadastrarForm,
    PlanoEntregasSetorialHorarioFuncionamentoSetorEditarForm,
    PlanoEntregasSetorialHorarioPlanejamentoSetorCadastrarForm,
    PlanoEntregasSetorialHorarioPlanejamentoSetorEditarForm,
    PlanoIndividualTrabalhoAtendimentoTeletrabalhoCadastrarForm,
    PlanoIndividualTrabalhoAtendimentoTeletrabalhoEditarForm,
    PlanoIndividualTrabalhoEntregasCadastrarForm,
    PlanoIndividualTrabalhoEntregasEditarForm,
    PlanoIndividualTrabalhoPresencialCadastrarForm,
    PlanoIndividualTrabalhoPresencialEditarForm,
    QuestionarioRitChefeForm,
    QuestionarioRitServidorForm,
    RelatorioIndividualTrabalhoCadastrarForm,
    RelatorioIndividualTrabalhoEditarForm,
    RemoverDesligamentoGestaoPgdForm,
    SelecionarSetorForm,
    SolicitarAdesaoPesForm,
    SolicitarAdesaoPgdForm,
)
from pgd2.models import (
    ComissaoPGD,
    DesligamentoPgdServidor,
    DocumentoAdesaoPesServidor,
    JustificativaDesligamentoPgd,
    LogApi,
    ParticipantePgd,
    PeriodoPes,
    PeriodoPitRit,
    PitSetores,
    PitSolicitacaoAnalise,
    PitSolicitacaoAnaliseSetor,
    PlanoEntregasSetorial,
    PlanoEntregasSetorialEntregas,
    PlanoEntregasSetorialHorarioFuncionamentoSetor,
    PlanoEntregasSetorialHorarioPlanejamentoSetor,
    PlanoIndividualTrabalho,
    PlanoIndividualTrabalhoAtendimento,
    PlanoIndividualTrabalhoCopia,
    PlanoIndividualTrabalhoEntregas,
    PlanoIndividualTrabalhoPresencial,
    RegistroAcaoPES,
    RegistroAcaoPlanoIndividualTrabalho,
    RegistroAcaoSolicitacaoAdesaoPesServidor,
    RegistroAcaoSolicitacaoAdesaoServidor,
    RelatorioIndividualTrabalho,
    RelatorioIndividualTrabalhoDistribuicaoHoras,
    RelatorioIndividualTrabalhoQuestionario,
    SetorHabilitacao,
    SetorPgdApi,
    SolicitacaoAdesaoPesServidor,
    SolicitacaoAdesaoServidor,
)
from pgd2.monitoramento import (
    get_pess_aprovados_de_setores_nao_habilitados,
    get_pess_aptos_para_analise_execucao,
    get_pess_aptos_para_avaliacao_execucao,
    get_pess_de_setores_habilitados,
    get_pess_de_setores_nao_habilitados,
    get_pess_inconsistentes_aprovacao,
    get_pess_relacionados_a_pit,
    get_servidores_adesao_vigente_sem_pit_relacionado,
    get_servidores_desligados,
    get_servidores_deveriam_mas_nao_tem_pit_homologado,
    get_servidores_deveriam_mas_nao_tem_pit_homologado_ultimos_3_periodos,
    get_servidores_deveriam_mas_nao_tem_rit_homologado_nos_2_periodos_anteriores,
    get_servidores_em_pgd,
    get_servidores_em_pgd_com_dados_diferentes_entre_sougov_suap,
    get_servidores_em_pgd_em_estagio_probratorio,
    get_servidores_em_pgd_no_sou_gov,
    get_servidores_em_pgd_no_sou_gov_mas_nao_no_suap,
    get_servidores_em_pgd_no_suap_mas_nao_no_sou_gov,
    get_servidores_inativos_em_pgd,
    get_servidores_inconsistentes_regra_de_perfil_geral_servidor,
    get_servidores_inconsistentes_regra_habilitacao_setor,
    get_servidores_movimentados_com_menos_de_6_meses_de_instituto,
    get_setores_habilitados_sem_pes_criado,
)
from pgd2.notificacoes import (
    notificar_homologacao_pit,
    notificar_homologacao_rit,
    notificar_nao_homologacao_pit,
    notificar_nao_homologacao_rit,
    notificar_reabrir_rit,
)
from pgd2.pendencias_alertas import get_pendencia_geral_servidor_pgd, get_pendencias_chefe, get_pendencias_servidor
from pgd2.pgd_gitlab_novo import ContribuicoesGitlab
from pgd2.utils import (
    get_datetime_now,
    get_msg_plural_nenhum_setor_habilitado,
    get_msg_singular_nenhum_setor_habilitado,
    get_pendencias_ponto_servidor,
    get_pgd_sou_gov,
    get_setores_pgd,
    get_vbn_field,
    gv,
    obter_compensacoes_especificas_compesaveis_rit,
    permite_habilitacao_dos_setores,
    pode_consultar_dados_api,
    setores_e_servidores_que_sou_relacionado_como_chefe_no_periodo,
    setores_que_sou_chefe_direto_hoje,
    setores_que_sou_chefe_hoje,
    setores_que_sou_fui_chefe,
    utilizar_integracao_com_plan_estrategico,
    utilizar_integracao_com_ponto,
)
from ponto.models import RecessoOpcaoEscolhida, SaldoExterno
from rh.models import Servidor, ServidorSetorLotacaoHistorico, Setor, UnidadeOrganizacional
from suap import nomenclatura


@layout.servicos_anonimos()
def servicos_anonimos(request):
    servicos_anonimos = []

    servicos_anonimos.append(
        {'categoria': 'Consultas gerais', 'url': '/pgd2/listar_servidores_publico_pgd2/', 'icone': 'file', 'titulo': 'Servidores PGD'}
    )

    return servicos_anonimos


@layout.atribuidos_a_mim()
def index_atribuidos_a_mim(request):
    """Integração com o painel "Atribuídos a mim" da raiz do SUAP.

    Retorna uma lista de cartões resumo apontando para `pendencias_avisos_pgd`
    quando há pendências como servidor (adesões/PIT/RIT) ou como chefe.
    """
    pendencias = []

    if request.user.eh_servidor:
        url = reverse('pendencias_avisos_pgd_pgd2')
        pendencias_chefe = get_pendencias_chefe(request.user, verifica_sou_gov=False)
        pendencias_servidor = get_pendencias_servidor(request.user, apenas_lista_separada=False, verifica_sou_gov=False)
        total_pendencias = len(pendencias_chefe) + len(pendencias_servidor)
        if total_pendencias > 0:
            pendencias.append(
                {
                    'titulo': f'Pendência{pluralize(total_pendencias)} no PGD',
                    'subtitulo': 'a resolver',
                    'qtd': total_pendencias,
                    'url': url,
                }
            )

    return pendencias


@rtr()
@permission_required('rh.eh_servidor')
def pendencias_avisos_pgd(request):
    """Painel das pendências do usuário no PGD (servidor + chefe direto).

    Reúne pendências do usuário enquanto servidor (qualquer adesão registrada)
    e enquanto chefe direto de setor. Para gestão (`pgd2.gestao_pgd2`), aceita
    `?matricula=` para inspecionar pendências de outro servidor.
    """
    # Chefe (apenas chefe direto) ou servidor com adesao alguma adesao

    title = 'Minhas Pendências no PGD'

    user = request.user
    servidor = request.user.get_relacionamento()

    if request.GET.get('matricula') and request.user.has_perm('pgd2.gestao_pgd2'):
        servidor = Servidor.objects.vinculados().filter(matricula=request.GET.get('matricula')).first()
        user = servidor.get_user()
        title = f'Pendências no PGD - {servidor}'

    eh_servidor_pgd = SolicitacaoAdesaoServidor.objects.filter(servidor=servidor).exists()
    eh_chefe = setores_que_sou_chefe_direto_hoje(servidor).exists()

    if not (eh_servidor_pgd or eh_chefe):
        raise PermissionDenied

    pendencias_chefe = get_pendencias_chefe(user, verifica_sou_gov=False)
    pendencias_servidor = get_pendencias_servidor(user, apenas_lista_separada=False, verifica_sou_gov=False)

    return locals()


@rtr()
@permission_required('rh.chefe')
def listar_pendencias_setor_servidor(request):
    """Lista as pendências dos servidores sob a chefia do usuário.

    Por padrão restringe a chefes diretos; reitor/diretor geral devem informar
    `campus` obrigatoriamente. Suporta filtros por setor, campus e busca por
    nome/matrícula; resultados são limitados a `max_qtd_listado` quando o
    setor não está informado.
    """
    title = 'Pendências dos Servidores'

    setores_chefe = setores_que_sou_chefe_hoje(request.user.get_relacionamento())
    setores_chefe_direto = setores_que_sou_chefe_direto_hoje(request.user.get_relacionamento())

    sem_filtro = True
    querys = []
    querys.append(Q(servidor__setor__in=setores_chefe_direto))

    servidor = request.user.get_relacionamento()
    eh_reitor = servidor.eh_reitor()
    eh_dg = request.user.groups.filter(name='Diretor Geral').exists()
    campis = UnidadeOrganizacional.objects.uo()
    obrigatorio_campus = eh_reitor or eh_dg

    campus_filtro = None
    setor_filtro = None
    max_qtd_listado = 25

    form = BuscarServidoresPendenciaPgdForm(
        request.GET or None, request=request, setores_chefe=setores_chefe, campis=campis, obrigatorio_campus=obrigatorio_campus
    )
    if form.is_valid():
        buscar_str = form.cleaned_data.get('buscar_str')
        setor = form.cleaned_data.get('setor')
        campus = form.cleaned_data.get('campus')

        campus_filtro = campus
        setor_filtro = setor

        if buscar_str or setor:
            sem_filtro = False
            querys = []
            if setor:
                querys.append(Q(servidor__setor=setor))
            if buscar_str:
                querys.append(Q(servidor__pessoa_fisica__nome__icontains=buscar_str) | Q(servidor__matricula__icontains=buscar_str))
            if not setor and buscar_str:
                querys.append(Q(servidor__setor__in=setores_chefe))
            if campus:
                querys.append(Q(servidor__setor__uo=campus))

    if (not obrigatorio_campus) or (obrigatorio_campus and campus_filtro):
        servidores_vinculados = Servidor.objects.vinculados()
        lista_servidores = (
            SolicitacaoAdesaoServidor.get_adesoes_vigentes()
            .filter(reduce(operator.and_, querys), servidor__in=servidores_vinculados)
            .order_by('servidor__pessoa_fisica__nome')
        )
        if not setor_filtro and (len(lista_servidores) > max_qtd_listado):
            lista_servidores = lista_servidores[:max_qtd_listado]

        lista_servidores_pendencias = []
        for ls in lista_servidores:
            lista_pendencias_pit, lista_pendencias_rit, pendencia_geral = get_pendencias_servidor(ls.servidor.get_user(), apenas_lista_separada=True)
            lista_servidores_pendencias.append(
                {
                    'servidor': ls.servidor,
                    'pendencias_pit': lista_pendencias_pit,
                    'pendencias_rit': lista_pendencias_rit,
                    'pendencia_geral': pendencia_geral,
                }
            )

    return locals()


# ====================================================
# CADASTROS BÁSICOS
# ====================================================


@rtr()
@transaction.atomic
@permission_required('pgd2.gestao_pgd2')
def ativar_desativar_preencher_questionario_pesquisa(request, periodo_pit_rit_id):
    if not (PeriodoPitRit.pode_cadastrar_alterar(request.user)):
        raise PermissionDenied

    periodo = get_object_or_404(PeriodoPitRit, pk=periodo_pit_rit_id)
    periodo.preencher_questionario_pesquisa = not periodo.preencher_questionario_pesquisa
    periodo.save()
    url = '/admin/pgd2/periodopitrit/'
    return httprr(url, 'Alteração realizada com sucesso.')


# ====================================================
# PES - Plano de Entregas Setorial
# ====================================================


@rtr()
@permission_required('rh.eh_servidor')
def visualizar_pes(request, pes_id):
    """Tela principal do Plano de Entregas Setorial (PES).

    Recalcula o PES e expõe todos os flags `pode_*` consultados pelo template
    para habilitar ações conforme o estado e o papel do usuário: edição de
    dados básicos/horários/auxiliares, cadastro/remoção de entrega, solicitação
    de aprovação, aprovação, solicitação/realização de avaliação e reabertura.
    Também carrega orientações e o registro de ações do PES.
    """
    pes = get_object_or_404(PlanoEntregasSetorial, pk=pes_id)
    if not (pes.pode_visualizar(request.user)):
        raise PermissionDenied
    pes.calcular_pes()

    title = pes

    pode_receber_copia = pes.pode_receber_copia(request.user)
    pode_editar_dados_basicos = pes.pode_editar_dados_basicos(request.user)
    pode_cadastrar_horario_funcionamento_setor = pes.pode_cadastrar_horario_funcionamento_setor(request.user)
    pode_cadastrar_horario_planejamento_setor = pes.pode_cadastrar_horario_planejamento_setor(request.user)
    pode_cadastrar_entrega = pes.pode_cadastrar_entrega(request.user)
    pode_excluir = pes.pode_excluir(request.user)
    existe_entrega_que_pode_ser_removida_no_pes = pes.existe_entrega_que_pode_ser_removida_no_pes(request.user)

    registros_acoes = RegistroAcaoPES.objects.filter(pes=pes)
    pes_horarios_funcionamento_setor_agrupado_por_semana = (
        PlanoEntregasSetorialHorarioFuncionamentoSetor.get_horarios_funcionamento_setor_agrupado_por_semana(pes)
    )
    pes_horarios_planejamento_setor_agrupado_por_semana = (
        PlanoEntregasSetorialHorarioPlanejamentoSetor.get_horarios_planejamento_setor_agrupado_por_semana(pes)
    )
    pes_entregas = pes.get_entregas()
    pes_auxiliares = pes.auxiliares.all()

    orientacoes = pes.get_orientacoes_relacionadas_ao_periodo()
    orientacoes_sistemico = orientacoes.filter(eh_sistemica=True)
    orientacoes_nao_sistemico = orientacoes.filter(eh_sistemica=False)
    utilizar_plan_estrat = utilizar_integracao_com_plan_estrategico()

    usuario_pode_solicitar_aprovacao = pes.usuario_pode_solicitar_aprovacao(user=request.user)
    pode_solicitar_aprovacao, erros = pes.pode_solicitar_aprovacao(user=request.user, retornar_lista_erros=True)
    if pes.situacao != pes.EM_CADASTRO:
        erros = None
    pode_aprovar, _ = pes.pode_aprovar(user=request.user, retornar_lista_erros=False)

    pode_visualizar_execucao = pes.pode_visualizar_execucao(request.user)

    pode_solicitar_avaliacao, _ = pes.pode_solicitar_avaliacao(user=request.user, retornar_lista_erros=False)
    pode_avaliar = pes.pode_avaliar(request.user)[0]
    pode_reabrir = pes.pode_reabrir(request.user)[0]
    estah_solicitado_aprovacao_avaliacao = (
        pes.situacao == PlanoEntregasSetorial.SOLICITADO_APROVACAO or pes.situacao_avaliacao == PlanoEntregasSetorial.SOLICITADO_AVALIACAO
    )

    eh_super_usuario = request.user.is_superuser

    erro_habilitacao_setor = None
    if not SetorHabilitacao.setor_estah_habilitado(pes.setor):
        erro_habilitacao_setor = get_msg_singular_nenhum_setor_habilitado(sigla_setor=pes.setor.sigla)

    return locals()


@rtr()
@permission_required('rh.chefe')
def visualizar_pes_execucao_geral(request, pes_id):
    """Acompanhamento agregado da execução do PES por período PIT/RIT.

    Para cada período não cancelado do `PeriodoPitRit` listado no PES, separa
    os PITs cujo setor de homologação coincide com o setor do PES daqueles que
    vêm de outros setores — útil para diagnóstico de aderência ao plano.
    """
    pes = get_object_or_404(PlanoEntregasSetorial, pk=pes_id)
    pes.calcular_pes()
    if not (pes.pode_visualizar_execucao(request.user)):
        raise PermissionDenied

    pode_visualizar_execucao = pes.pode_visualizar_execucao(request.user)

    pes_em_execucao = pes.em_execucao

    title = f'Acompanhamento do {pes} - Geral'

    # Lista os períodos de PIT/RIT do PES
    lista_pes_execucao = []
    periodos_pit_rit = PeriodoPitRit.objects.filter(periodo_pes=pes.periodo_pes, cancelado=False).order_by('data_inicio')
    for p in periodos_pit_rit:
        pes_execucao = {}
        pes_execucao['periodo'] = p

        pits = PlanoIndividualTrabalho.get_pits_por_pes(pes).filter(periodo_pit_rit=p).order_by('adesao__servidor__pessoa_fisica__nome')
        pes_execucao['pits_do_setor'] = pits.filter(setor_pode_homologar_pit_rit=pes.setor)
        pes_execucao['pits_outros_setores'] = pits.exclude(setor_pode_homologar_pit_rit=pes.setor)

        lista_pes_execucao.append(pes_execucao)

    return locals()


@rtr()
@permission_required('rh.chefe')
def visualizar_pes_execucao_planejamento(request, pes_id):
    pes = get_object_or_404(PlanoEntregasSetorial, pk=pes_id)
    pes.calcular_pes()
    if not (pes.pode_visualizar_execucao(request.user)):
        raise PermissionDenied

    pode_visualizar_execucao = pes.pode_visualizar_execucao(request.user)

    pes_em_execucao = pes.em_execucao

    title = f'Acompanhamento do {pes} - Planejamento'

    utilizar_plan_estrat = utilizar_integracao_com_plan_estrategico()

    # Estrutura
    # - Periodos
    #   - Entregas do PES
    #     - Entregas de PIT

    # Lista os períodos de PIT/RIT do PES
    periodos_pit_rit = PeriodoPitRit.objects.filter(periodo_pes=pes.periodo_pes, cancelado=False).order_by('data_inicio')

    # Lista entregas do PES
    entregas_pes = pes.get_entregas()

    # Lista PITs do PES
    pits = PlanoIndividualTrabalho.get_pits_por_pes(pes)

    # Lista de servidores relacionados
    servidores_relacionados = Servidor.objects.vinculados().filter(id__in=pits.values('adesao__servidor_id'))

    formato_filter = 'agrupado_por_periodo_pit'
    servidores_filter = None
    lista_dados = []

    tem_apenas_parametro_tab = 'tab' in request.GET and len(request.GET.keys()) == 1
    form = BuscarAcompanhamentoPesPlanejamentoForm(request.GET or None, servidores_relacionados=servidores_relacionados)
    if form.is_valid() and not tem_apenas_parametro_tab:
        formato_filter = form.cleaned_data.get('formato')
        servidores_filter = form.cleaned_data.get('servidores')

    if formato_filter == 'agrupado_por_periodo_pit':
        for periodo_pit_rit in periodos_pit_rit:
            dados = {}
            dados['periodo'] = periodo_pit_rit
            pits = PlanoIndividualTrabalho.get_pits_por_pes(pes).filter(periodo_pit_rit=periodo_pit_rit).order_by('adesao__servidor')
            if servidores_filter:
                pits = pits.filter(adesao__servidor_id__in=servidores_filter.values('id'))
            lista_dados_entrega_pes = []

            for entrega_pes in entregas_pes:
                entregas_pit = (
                    PlanoIndividualTrabalho.get_entregas_pit_com_canceladas_utilizadas(pits.values_list('id', flat=True))
                    .filter(entrega_pes=entrega_pes)
                    .order_by('pit__periodo_pit_rit__data_inicio', 'pit__adesao__servidor__pessoa_fisica__nome')
                )
                dados_entrega_pes = {'entrega_pes': entrega_pes, 'entregas_pit': entregas_pit}
                lista_dados_entrega_pes.append(dados_entrega_pes)

            dados['entregas_pes'] = lista_dados_entrega_pes
            lista_dados.append(dados)
    else:
        pits = PlanoIndividualTrabalho.get_pits_por_pes(pes).order_by('adesao__servidor__pessoa_fisica__nome__pessoa_fisica__nome')
        if servidores_filter:
            pits = pits.filter(adesao__servidor_id__in=servidores_filter.values('id'))
        for entrega_pes in entregas_pes:
            entregas_pit = (
                PlanoIndividualTrabalho.get_entregas_pit_com_canceladas_utilizadas(pits.values_list('id', flat=True))
                .filter(entrega_pes=entrega_pes)
                .order_by('pit__periodo_pit_rit__data_inicio', 'pit__adesao__servidor__pessoa_fisica__nome')
            )
            dados = {'entrega_pes': entrega_pes, 'entregas_pit': entregas_pit}
            lista_dados.append(dados)

    return locals()


@rtr()
@permission_required('rh.chefe')
def visualizar_pes_execucao(request, pes_id):
    """Acompanhamento detalhado da execução do PES — entrega a entrega.

    Quando `?entrega_pes=` é informado, restringe aos RITs cujas entregas de
    PIT apontam para a entrega do PES selecionada, com filtro opcional de
    servidores via `BuscarAcompanhamentoPesExecucaoForm`.
    """
    pes = get_object_or_404(PlanoEntregasSetorial, pk=pes_id)

    if not (pes.pode_visualizar_execucao(request.user)):
        raise PermissionDenied

    pes.calcular_pes()

    pode_visualizar_execucao = pes.pode_visualizar_execucao(request.user)
    utilizar_plan_estrat = utilizar_integracao_com_plan_estrategico()

    title = f'Acompanhamento do {pes} - Execução'

    entregas_pes = pes.get_entregas().select_related('pes')
    entregas_rit = []

    filtro_entrega_pes = request.GET.get('entrega_pes')
    if filtro_entrega_pes:
        pits = PlanoIndividualTrabalho.get_pits_por_pes(pes)
        servidores_relacionados = Servidor.objects.vinculados().filter(id__in=pits.values('adesao__servidor_id'))

        form = BuscarAcompanhamentoPesExecucaoForm(
            request.GET or None, servidores_relacionados=servidores_relacionados, entrega_pes=filtro_entrega_pes
        )
        if form.is_valid():
            servidores_filter = form.cleaned_data.get('servidores')

        entregas_pes = entregas_pes.filter(id=filtro_entrega_pes)

        if servidores_filter:
            pits = pits.filter(adesao__servidor_id__in=servidores_filter.values('id'))
        entregas_rit = (
            RelatorioIndividualTrabalho.objects.filter(entrega_pit__pit__in=pits, entrega_pit__entrega_pes_id__in=entregas_pes.values_list('id'))
            .order_by('entrega_pit__pit__adesao__servidor__pessoa_fisica__nome')
            .select_related('entrega_pit__pit__adesao__servidor', 'entrega_pit__pit__periodo_pit_rit')
        )

    return locals()


@rtr()
@permission_required('rh.chefe')
def visualizar_pes_servidores_relacionados(request, pes_id):
    pes = get_object_or_404(PlanoEntregasSetorial, pk=pes_id)
    if not (pes.pode_visualizar_execucao(request.user)):
        raise PermissionDenied

    pes.calcular_pes()
    title = f'Acompanhamento do {pes} - Servidores relacionados'

    pode_visualizar_execucao = pes.pode_visualizar_execucao(request.user)

    lista_servidores_adesao_por_periodo = pes.get_servidores_relacionados_periodo()

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def editar_dados_basicos_pes(request, pes_id):
    """Edita documentação do PES (percentual de teletrabalho, infra, técnica).

    Registra automaticamente um `RegistroAcaoPES` do tipo
    `TIPO_EDITOU_DOCUMENTACAO` com o diff DE→PARA dos campos alterados.
    """
    pes = get_object_or_404(PlanoEntregasSetorial, pk=pes_id)
    if not pes.pode_editar_dados_basicos(request.user):
        raise PermissionDenied

    title = f'Editar Dados Básicos do {pes}'
    url = f'{reverse("visualizar_pes_pgd2", args=[pes_id])}?tab=tab2'

    # Dados para comparação DE
    pes_doc_percentual_maximo_teletrabalho = pes.doc_percentual_maximo_teletrabalho
    pes_doc_insfraestrutura = pes.doc_insfraestrutura
    pes_doc_tecnica = pes.doc_tecnica

    form = PlanoEntregasSetorialEditarDocumentacaoForm(request.POST or None, instance=pes)
    if form.is_valid():
        obj = form.save()

        # Montando DE -> PARA
        dados_de_para = None
        try:
            dados_de = {}
            dados_para = {}
            if pes_doc_percentual_maximo_teletrabalho != obj.doc_percentual_maximo_teletrabalho:
                dados_de[get_vbn_field(PlanoEntregasSetorial, 'doc_percentual_maximo_teletrabalho')] = str(pes_doc_percentual_maximo_teletrabalho)
                dados_para[get_vbn_field(PlanoEntregasSetorial, 'doc_percentual_maximo_teletrabalho')] = str(obj.doc_percentual_maximo_teletrabalho)
            if pes_doc_insfraestrutura != obj.doc_insfraestrutura:
                dados_de[get_vbn_field(PlanoEntregasSetorial, 'doc_insfraestrutura')] = pes_doc_insfraestrutura
                dados_para[get_vbn_field(PlanoEntregasSetorial, 'doc_insfraestrutura')] = obj.doc_insfraestrutura
            if pes_doc_tecnica != obj.doc_tecnica:
                dados_de[get_vbn_field(PlanoEntregasSetorial, 'doc_tecnica')] = pes_doc_tecnica
                dados_para[get_vbn_field(PlanoEntregasSetorial, 'doc_tecnica')] = obj.doc_tecnica
            dados_de_para = {'de': dados_de, 'para': dados_para}
        except Exception:
            pass

        ra_obs = ''
        RegistroAcaoPES.registrar(request=request, tipo=RegistroAcaoPES.TIPO_EDITOU_DOCUMENTACAO, pes=pes, obs=ra_obs, dados_de_para=dados_de_para)

        return httprr(url, 'Dados alterados com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def cadastrar_horario_funcionamento_setor_pes(request, pes_id):
    pes = get_object_or_404(PlanoEntregasSetorial, pk=pes_id)
    if not pes.pode_cadastrar_horario_funcionamento_setor(request.user):
        raise PermissionDenied

    title = f'Cadastrar Horário de Funcionamento do Setor - {pes}'
    url = f'{reverse("visualizar_pes_pgd2", args=[pes_id])}?tab=tab3'

    form = PlanoEntregasSetorialHorarioFuncionamentoSetorCadastrarForm(request.POST or None, pes=pes)
    if form.is_valid():
        form.save()
        ra_obs = ''

        RegistroAcaoPES.registrar(request=request, tipo=RegistroAcaoPES.TIPO_CADASTROU_HORARIO_FUNCIONAMENTO_DO_SETOR, pes=pes, obs=ra_obs)

        return httprr(url, 'O horário de funcionamento do setor foi cadastrado com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def editar_horario_funcionamento_setor_pes(request, pes_hfs_id):
    pes_hfs = get_object_or_404(PlanoEntregasSetorialHorarioFuncionamentoSetor, pk=pes_hfs_id)
    pes = pes_hfs.pes
    if not pes.pode_editar_horario_funcionamento_setor(request.user):
        raise PermissionDenied

    title = f'Editar Horário de Funcionamento do Setor - {pes}'
    url = f'{reverse("visualizar_pes_pgd2", args=[pes.id])}?tab=tab3'

    if pes_hfs.recorrencia:
        pes_horarios_funcionamento_setor_agrupado_por_semana = (
            PlanoEntregasSetorialHorarioFuncionamentoSetor.get_horarios_funcionamento_setor_agrupado_por_semana(pes, pes_hfs.recorrencia)
        )

    # Historico: DE
    # ----------------------
    de_hora_inicio = pes_hfs.hora_inicio
    de_hora_final = pes_hfs.hora_inicio

    form = PlanoEntregasSetorialHorarioFuncionamentoSetorEditarForm(request.POST or None, pes=pes, instance=pes_hfs)
    if form.is_valid():
        form.save()

        editou_recorrencias = form.cleaned_data.get('tipo_edicao') != 'este'

        # Historico: PARA
        # ----------------------
        para_hora_inicio = form.cleaned_data.get('hora_inicio')
        para_hora_final = form.cleaned_data.get('hora_final')

        # --------------------------------------
        # Histórico: montando DE -> PARA
        # --------------------------------------
        dados_de_para = None
        try:
            dados_de = {}
            dados_para = {}
            if de_hora_inicio != para_hora_inicio:
                dados_de[get_vbn_field(PlanoEntregasSetorialHorarioFuncionamentoSetor, 'hora_inicio')] = str(de_hora_inicio)
                dados_para[get_vbn_field(PlanoEntregasSetorialHorarioFuncionamentoSetor, 'hora_inicio')] = str(para_hora_inicio)
            if de_hora_final != para_hora_final:
                dados_de[get_vbn_field(PlanoEntregasSetorialHorarioFuncionamentoSetor, 'hora_final')] = str(de_hora_final)
                dados_para[get_vbn_field(PlanoEntregasSetorialHorarioFuncionamentoSetor, 'hora_final')] = str(para_hora_final)
            dados_de_para = {'de': dados_de, 'para': dados_para}
        except Exception:
            pass
        # --------------------------------------

        ra_obs = f'Editou "{pes_hfs}"'
        if editou_recorrencias:
            ra_obs = f'Editou "{pes_hfs}" e suas recorrências'
        RegistroAcaoPES.registrar(
            request=request, tipo=RegistroAcaoPES.TIPO_EDITOU_HORARIO_FUNCIONAMENTO_DO_SETOR, pes=pes, obs=ra_obs, dados_de_para=dados_de_para
        )

        return httprr(url, 'O horário de funcionamento do setor foi atualizado com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def remover_horario_funcionamento_setor_pes(request, pes_id):
    pes = get_object_or_404(PlanoEntregasSetorial, pk=pes_id)
    if not pes.pode_remover_horario_funcionamento_setor(request.user):
        raise PermissionDenied

    title = f'Remover Horário de Funcionamento do Setor - {pes}'
    url = f'{reverse("visualizar_pes_pgd2", args=[pes_id])}?tab=tab3'

    hfs_selecionados = request.GET.getlist('checks[]')
    if 'remover_hfs' in request.GET and hfs_selecionados:
        form = ConfirmacaoComSenhaForm(request.POST or None, request=request)
        if form.is_valid():
            PlanoEntregasSetorialHorarioFuncionamentoSetor.objects.filter(pes=pes, id__in=hfs_selecionados).delete()
            ra_obs = ''
            RegistroAcaoPES.registrar(request=request, tipo=RegistroAcaoPES.TIPO_CADASTROU_HORARIO_FUNCIONAMENTO_DO_SETOR, pes=pes, obs=ra_obs)
            return httprr(url, 'Os horários de funcionamento selecionados foram removidos com sucesso.')
    else:
        return httprr(url, 'Selecione ao menos um horário para remover.', tag='error')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def cadastrar_horario_planejamento_setor_pes(request, pes_id):
    pes = get_object_or_404(PlanoEntregasSetorial, pk=pes_id)
    if not pes.pode_cadastrar_horario_planejamento_setor(request.user):
        raise PermissionDenied

    title = f'Cadastrar Horário de Planejamento do Setor - {pes}'
    url = f'{reverse("visualizar_pes_pgd2", args=[pes_id])}?tab=tab4'

    form = PlanoEntregasSetorialHorarioPlanejamentoSetorCadastrarForm(request.POST or None, pes=pes)
    if form.is_valid():
        form.save()
        ra_obs = ''
        RegistroAcaoPES.registrar(request=request, tipo=RegistroAcaoPES.TIPO_CADASTROU_HORARIO_PLANEJAMENTO_DO_SETOR, pes=pes, obs=ra_obs)

        return httprr(url, 'O horário de planejamento do setor foi cadastrado com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def editar_horario_planejamento_setor_pes(request, pes_hfs_id):
    pes_hfs = get_object_or_404(PlanoEntregasSetorialHorarioPlanejamentoSetor, pk=pes_hfs_id)
    pes = pes_hfs.pes
    if not pes.pode_editar_horario_planejamento_setor(request.user):
        raise PermissionDenied

    title = f'Editar Horário de Planejamento do Setor - {pes}'
    url = f'{reverse("visualizar_pes_pgd2", args=[pes.id])}?tab=tab4'

    if pes_hfs.recorrencia:
        pes_horarios_planejamento_setor_agrupado_por_semana = (
            PlanoEntregasSetorialHorarioPlanejamentoSetor.get_horarios_planejamento_setor_agrupado_por_semana(pes, pes_hfs.recorrencia)
        )

    # Historico: DE
    # ----------------------
    de_data = pes_hfs.data
    de_hora_inicio = pes_hfs.hora_inicio
    de_hora_final = pes_hfs.hora_inicio
    de_reuniao = pes_hfs.reuniao

    form = PlanoEntregasSetorialHorarioPlanejamentoSetorEditarForm(request.POST or None, pes=pes, instance=pes_hfs)
    if form.is_valid():
        form.save()

        editou_recorrencias = form.cleaned_data.get('tipo_edicao') != 'este'

        # Historico: PARA
        # ----------------------
        para_hora_inicio = form.cleaned_data.get('hora_inicio')
        para_hora_final = form.cleaned_data.get('hora_final')

        # --------------------------------------
        # Histórico: montando DE -> PARA
        # --------------------------------------
        dados_de_para = None
        try:
            dados_de = {}
            dados_para = {}
            if de_hora_inicio != para_hora_inicio:
                dados_de[get_vbn_field(PlanoEntregasSetorialHorarioPlanejamentoSetor, 'hora_inicio')] = str(de_hora_inicio)
                dados_para[get_vbn_field(PlanoEntregasSetorialHorarioPlanejamentoSetor, 'hora_inicio')] = str(para_hora_inicio)
            if de_hora_final != para_hora_final:
                dados_de[get_vbn_field(PlanoEntregasSetorialHorarioPlanejamentoSetor, 'hora_final')] = str(de_hora_final)
                dados_para[get_vbn_field(PlanoEntregasSetorialHorarioPlanejamentoSetor, 'hora_final')] = str(para_hora_final)
            dados_de_para = {'de': dados_de, 'para': dados_para}
        except Exception:
            pass
        # --------------------------------------

        ra_obs = f'Editou "{pes_hfs}"'
        if editou_recorrencias:
            ra_obs = f'Editou "{pes_hfs}" e suas recorrências'
        RegistroAcaoPES.registrar(
            request=request, tipo=RegistroAcaoPES.TIPO_EDITOU_HORARIO_PLANEJAMENTO_DO_SETOR, pes=pes, obs=ra_obs, dados_de_para=dados_de_para
        )

        return httprr(url, 'O horário de planejamento do setor foi atualizado com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def remover_horario_planejamento_setor_pes(request, pes_id):
    pes = get_object_or_404(PlanoEntregasSetorial, pk=pes_id)
    if not pes.pode_remover_horario_planejamento_setor(request.user):
        raise PermissionDenied

    title = f'Remover Horário de Planejamento do Setor - {pes}'
    url = f'{reverse("visualizar_pes_pgd2", args=[pes.id])}?tab=tab4'

    hfs_selecionados = request.GET.getlist('checks[]')
    if 'remover_hps' in request.GET and hfs_selecionados:
        form = ConfirmacaoComSenhaForm(request.POST or None, request=request)
        if form.is_valid():
            ra_obs = ''
            RegistroAcaoPES.registrar(request=request, tipo=RegistroAcaoPES.TIPO_REMOVEU_HORARIO_PLANEJAMENTO_DO_SETOR, pes=pes, obs=ra_obs)
            PlanoEntregasSetorialHorarioPlanejamentoSetor.objects.filter(pes=pes, id__in=hfs_selecionados).delete()
            return httprr(url, 'Os horários de planejamento selecionados foram removidos com sucesso.')
    else:
        return httprr(url, 'Selecione ao menos um horário para remover.', tag='error')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def cadastrar_entrega_pes(request, pes_id):
    """Cadastra uma nova entrega no PES (permitido apenas em cadastro).

    Cria `PlanoEntregasSetorialEntregas` vinculada ao PES e registra um
    `TIPO_CADASTROU_ENTREGA` no log de ações.
    """
    pes = get_object_or_404(PlanoEntregasSetorial, pk=pes_id)
    if not pes.pode_cadastrar_entrega(request.user):
        raise PermissionDenied

    title = f'Cadastrar Entrega - {pes}'
    url = f'{reverse("visualizar_pes_pgd2", args=[pes_id])}?tab=tab5'

    form = PlanoEntregasSetorialEntregaCadastrarForm(request.POST or None, pes=pes)
    if form.is_valid():
        entrega = form.save(False)
        entrega.save()
        form.save_m2m()
        ra_obs = f'Cadastrou a entrega {entrega}'
        RegistroAcaoPES.registrar(request=request, tipo=RegistroAcaoPES.TIPO_CADASTROU_ENTREGA, pes=pes, obs=ra_obs)

        return httprr(url, 'A entrega foi cadastrada no PES com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def editar_entrega_pes(request, pes_ent_id):
    """Edita uma entrega do PES capturando histórico DE→PARA.

    Compara título, descrição, prazo, métrica, meta, critérios e os vínculos
    de setores/pessoas demandantes/destinatárias antes e depois do save;
    registra `TIPO_EDITOU_ENTREGA` apenas se algum campo realmente mudou.
    """
    pes_ent = get_object_or_404(PlanoEntregasSetorialEntregas, pk=pes_ent_id)
    pes = pes_ent.pes
    if not pes.pode_cadastrar_entrega(request.user):
        raise PermissionDenied

    title = f'Editar Entrega - {pes}'
    url = f'{reverse("visualizar_pes_pgd2", args=[pes.id])}?tab=tab5'

    # Historico: DE
    # ----------------------
    de_titulo = pes_ent.titulo
    de_descricao = pes_ent.descricao
    de_data_prazo = pes_ent.data_prazo
    de_criterios_avaliacao = pes_ent.criterios_avaliacao
    #
    de_metrica = pes_ent.get_metrica_display()
    de_meta = pes_ent.meta
    #
    de_setores_demandantes = pes_ent.setores_demandantes
    de_vinculos_demandantes = pes_ent.vinculos_demandantes
    de_setores_destinatarios = pes_ent.setores_destinatarios
    de_vinculos_destinatarios = pes_ent.vinculos_destinatarios

    form = PlanoEntregasSetorialEntregaCadastrarForm(request.POST or None, pes=pes, instance=pes_ent)
    if form.is_valid():
        entrega = form.save(False)
        entrega.save()
        form.save_m2m()

        alterou = False

        # Historico: PARA
        # ----------------------
        para_titulo = form.cleaned_data.get('titulo')
        para_descricao = form.cleaned_data.get('descricao')
        para_data_prazo = form.cleaned_data.get('data_prazo')
        para_criterios_avaliacao = form.cleaned_data.get('criterios_avaliacao')
        #
        para_metrica = form.cleaned_data.get('metrica')
        if para_metrica == PlanoEntregasSetorialEntregas.PERCENTUAL:
            para_metrica = 'Percentual'
        else:
            para_metrica = 'Quantidade'
        para_meta = form.cleaned_data.get('meta')
        #
        para_setores_demandantes = form.cleaned_data.get('setores_demandantes')
        para_vinculos_demandantes = form.cleaned_data.get('vinculos_demandantes')
        para_setores_destinatarios = form.cleaned_data.get('setores_destinatarios')
        para_vinculos_destinatarios = form.cleaned_data.get('vinculos_destinatarios')

        # --------------------------------------
        # Histórico: montando DE -> PARA
        # --------------------------------------
        dados_de_para = None
        try:
            dados_de = {}
            dados_para = {}
            if de_titulo != para_titulo:
                dados_de[get_vbn_field(PlanoEntregasSetorialEntregas, 'titulo')] = str(de_titulo)
                dados_para[get_vbn_field(PlanoEntregasSetorialEntregas, 'titulo')] = str(para_titulo)
            if de_descricao != para_descricao:
                dados_de[get_vbn_field(PlanoEntregasSetorialEntregas, 'descricao')] = str(de_descricao)
                dados_para[get_vbn_field(PlanoEntregasSetorialEntregas, 'descricao')] = str(para_descricao)
            if de_data_prazo != para_data_prazo:
                dados_de[get_vbn_field(PlanoEntregasSetorialEntregas, 'data_prazo')] = str(de_data_prazo)
                dados_para[get_vbn_field(PlanoEntregasSetorialEntregas, 'data_prazo')] = str(para_data_prazo)
            #
            if de_metrica != para_metrica:
                dados_de[get_vbn_field(PlanoEntregasSetorialEntregas, 'metrica')] = str(de_metrica)
                dados_para[get_vbn_field(PlanoEntregasSetorialEntregas, 'metrica')] = str(para_metrica)
            if de_meta != para_meta:
                dados_de[get_vbn_field(PlanoEntregasSetorialEntregas, 'meta')] = str(de_meta)
                dados_para[get_vbn_field(PlanoEntregasSetorialEntregas, 'meta')] = str(para_meta)
            #
            if de_criterios_avaliacao != para_criterios_avaliacao:
                dados_de[get_vbn_field(PlanoEntregasSetorialEntregas, 'criterios_avaliacao')] = str(de_criterios_avaliacao)
                dados_para[get_vbn_field(PlanoEntregasSetorialEntregas, 'criterios_avaliacao')] = str(para_criterios_avaliacao)

            if dados_de and dados_para:
                dados_de_para = {'de': dados_de, 'para': dados_para}
                alterou = True
        except Exception:
            pass
        # --------------------------------------

        ra_obs = f'Editou "{pes_ent}"'
        dif_para_setores_demandantes = de_setores_demandantes != para_setores_demandantes
        dif_vinculos_demandantes = de_vinculos_demandantes != para_vinculos_demandantes
        dif_setores_destinatarios = de_setores_destinatarios != para_setores_destinatarios
        dif_vinculos_destinatarios = de_vinculos_destinatarios != para_vinculos_destinatarios
        if dif_para_setores_demandantes or dif_vinculos_demandantes or dif_setores_destinatarios or dif_vinculos_destinatarios:
            ra_obs = f'Editou "{pes_ent}" e seus vínculos/setores'

        if alterou:
            RegistroAcaoPES.registrar(request=request, tipo=RegistroAcaoPES.TIPO_EDITOU_ENTREGA, pes=pes, obs=ra_obs, dados_de_para=dados_de_para)

        return httprr(url, 'A entrega do PES foi atualizada com sucesso.')

    return locals()


@rtr()
@permission_required('rh.eh_servidor')
def visualizar_entrega_pes(request, pes_ent_id):
    """Tela de detalhe de uma entrega do PES (somente leitura)."""
    pes_ent = get_object_or_404(PlanoEntregasSetorialEntregas, pk=pes_ent_id)
    pes = pes_ent.pes
    if not (pes.pode_visualizar(request.user)):
        raise PermissionDenied

    title = f'Visualizar Entrega do {pes}'

    utilizar_plan_estrat = utilizar_integracao_com_plan_estrategico()

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def remover_entrega_pes(request, pes_id):
    """Remove em lote as entregas marcadas em `?checks[]=` no PES.

    Cada entrega é removida apenas se `pode_remover_entrega()` permitir (não
    há PIT/RIT a ela vinculado). As bloqueadas viram mensagem ao usuário e o
    restante segue a remoção; o log recebe `TIPO_REMOVEU_ENTREGA`.
    """
    pes = get_object_or_404(PlanoEntregasSetorial, pk=pes_id)
    if not pes.pode_cadastrar_entrega(request.user):
        raise PermissionDenied

    title = f'Remover Entrega - {pes}'
    url = f'{reverse("visualizar_pes_pgd2", args=[pes.id])}?tab=tab5'

    hfs_selecionados = request.GET.getlist('checks[]')
    if 'remover_entregas_setor' in request.GET and hfs_selecionados:
        form = ConfirmacaoComSenhaForm(request.POST or None, request=request)
        if form.is_valid():
            entregas = PlanoEntregasSetorialEntregas.objects.filter(pes=pes, id__in=hfs_selecionados)
            nao_removidas = []
            teve_remocao = False
            for entrega in entregas:
                if entrega.pode_remover_entrega():
                    entrega.delete()
                    teve_remocao = True
                else:
                    nao_removidas.append(f'"{entrega.titulo!s}"')
            if nao_removidas:
                messages.error(
                    request,
                    f'As seguintes entregas não foram removidas pois existem entregas de {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} relacionadas: {mark_safe("</br>".join(nao_removidas))}',
                )

            if teve_remocao:
                ra_obs = ''
                RegistroAcaoPES.registrar(request=request, tipo=RegistroAcaoPES.TIPO_REMOVEU_ENTREGA, pes=pes, obs=ra_obs)
                if nao_removidas:
                    return httprr(url, 'As outras entregas foram removidas com sucesso.')
                else:
                    return httprr(url, 'Removida(s) com sucesso.')
            return httprr(url)
    else:
        return httprr(url, 'Nenhuma entrega selecionada.', tag='error')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def cancelar_entrega_pes(request, pes_ent_id):
    """Marca a entrega do PES como cancelada (`cancelado=True`).

    Não exclui o registro — preserva o histórico — e grava
    `TIPO_EDITOU_ENTREGA` com observação "Cancelou entrega".
    """
    pes_ent = get_object_or_404(PlanoEntregasSetorialEntregas, pk=pes_ent_id)

    if not pes_ent.pode_cancelar_entrega(request.user):
        raise PermissionDenied

    pes = pes_ent.pes

    url = f'{reverse("visualizar_pes_pgd2", args=[pes.id])}?tab=tab5'

    pes_ent.cancelado = True
    pes_ent.save()

    RegistroAcaoPES.registrar(request=request, tipo=RegistroAcaoPES.TIPO_EDITOU_ENTREGA, pes=pes, obs='Cancelou entrega')

    return httprr(url, 'Entrega cancelada com sucesso.')


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def descancelar_entrega_pes(request, pes_ent_id):
    """Reativa uma entrega previamente cancelada do PES."""
    pes_ent = get_object_or_404(PlanoEntregasSetorialEntregas, pk=pes_ent_id)

    if not pes_ent.pode_descancelar_entrega(request.user):
        raise PermissionDenied

    pes = pes_ent.pes

    url = f'{reverse("visualizar_pes_pgd2", args=[pes.id])}?tab=tab5'

    pes_ent.cancelado = False
    pes_ent.save()

    RegistroAcaoPES.registrar(request=request, tipo=RegistroAcaoPES.TIPO_EDITOU_ENTREGA, pes=pes, obs='Descancelou entrega')

    return httprr(url, 'Entrega descancelada com sucesso.')


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def editar_auxiliares_pes(request, pes_id):
    """Edita os vínculos auxiliares do PES (servidores com acesso editorial).

    Auxiliares ganham permissão para operar o PES sem serem o chefe titular.
    """
    pes = get_object_or_404(PlanoEntregasSetorial, pk=pes_id)
    if not pes.pode_editar_auxiliares(request.user):
        raise PermissionDenied

    title = f'Editar Auxiliares do {pes}'
    url = f'{reverse("visualizar_pes_pgd2", args=[pes_id])}?tab=tab6'

    form = PlanoEntregasSetorialEditarAuxiliaresForm(request.POST or None, instance=pes)
    if form.is_valid():
        obj = form.save(False)
        obj.save()
        form.save_m2m()
        ra_obs = ''
        RegistroAcaoPES.registrar(request=request, tipo=RegistroAcaoPES.TIPO_EDITOU_AUXILIARES, pes=pes, obs=ra_obs)
        return httprr(url, 'Os auxiliares do PES foram atualizados com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.chefe')
def excluir_pes(request, pes_id):
    """Exclui definitivamente o PES (irreversível, exige confirmação por senha).

    O método `pode_excluir` já garante que não há dependências bloqueantes
    (entregas vinculadas a PIT, por exemplo).
    """
    pes = get_object_or_404(PlanoEntregasSetorial, pk=pes_id)
    if not pes.pode_excluir(request.user):
        raise PermissionDenied

    title = f'Excluir - {pes}'
    url = reverse('visualizar_pes_pgd2', args=[pes.id])

    form = ComfirmacaoComSenhaIrreversivelForm(request.POST or None)
    if form.is_valid():
        pes.delete()
        return httprr('/', 'O PES foi excluído com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def solicitar_aprovacao_pes(request, pes_id):
    """Envia o PES para aprovação do setor superior.

    Muda a situação para `SOLICITADO_APROVACAO` e define
    `setor_para_aprovacao` via `get_setor_superior_aprovar_pes()`.
    """
    pes = get_object_or_404(PlanoEntregasSetorial, pk=pes_id)
    if not pes.pode_solicitar_aprovacao(request.user):
        raise PermissionDenied

    title = f'Solicitar Aprovação - {pes}'
    url = reverse('visualizar_pes_pgd2', args=[pes.id])

    form = ConfirmacaoComSenhaForm(request.POST or None)
    if form.is_valid():
        pes.situacao = PlanoEntregasSetorial.SOLICITADO_APROVACAO
        pes.setor_para_aprovacao = pes.get_setor_superior_aprovar_pes()
        pes.save()
        ra_obs = ''
        RegistroAcaoPES.registrar(request=request, tipo=RegistroAcaoPES.TIPO_SOLICITOU_APROVACAO, pes=pes, obs=ra_obs)
        return httprr(url, 'O PES foi enviado para aprovação.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.chefe')
def aprovar_pes(request, pes_id):
    """Aprova o PES (chefe do setor superior), passando-o à situação `APROVADO`."""
    pes = get_object_or_404(PlanoEntregasSetorial, pk=pes_id)
    if not pes.pode_aprovar(request.user)[0]:
        raise PermissionDenied

    title = f'Aprovar - {pes}'
    url = reverse('visualizar_pes_pgd2', args=[pes.id])

    form = ConfirmacaoComSenhaForm(request.POST or None)
    if form.is_valid():
        pes.situacao = PlanoEntregasSetorial.APROVADO
        pes.save()
        ra_obs = ''
        RegistroAcaoPES.registrar(request=request, tipo=RegistroAcaoPES.TIPO_APROVACAO, pes=pes, obs=ra_obs)
        return httprr(url, 'O PES foi aprovado com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.chefe')
def reprovar_pes(request, pes_id):
    """Devolve o PES para edição (situação volta a `EM_CADASTRO`).

    Exige justificativa, que fica gravada no `RegistroAcaoPES` do tipo
    `TIPO_REPROVACAO`.
    """
    pes = get_object_or_404(PlanoEntregasSetorial, pk=pes_id)
    if not pes.pode_aprovar(request.user)[0]:
        raise PermissionDenied

    title = f'Reprovar - {pes}'
    url = reverse('visualizar_pes_pgd2', args=[pes.id])

    form = JustificativaObrigatoriaComSenhaForm(request.POST or None)
    if form.is_valid():
        pes.situacao = PlanoEntregasSetorial.EM_CADASTRO
        pes.save()
        ra_obs = form.cleaned_data.get('justificativa')
        RegistroAcaoPES.registrar(request=request, tipo=RegistroAcaoPES.TIPO_REPROVACAO, pes=pes, obs=ra_obs)
        return httprr(url, 'O PES foi devolvido para ajustes.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.chefe')
def analisar_pes(request, pes_id):
    """Tela de seleção do modo de análise da execução do PES.

    Bifurca entre análise simplificada (todas as entregas executadas
    totalmente) e detalhada (entrega a entrega). Expõe flags sobre o estado
    da análise para o template oferecer os próximos passos.
    """
    pes = get_object_or_404(PlanoEntregasSetorial, pk=pes_id)
    pode_solicitar_avaliacao = pes.pode_solicitar_avaliacao(request.user)[0]
    if not pode_solicitar_avaliacao:
        raise PermissionDenied

    title = f'Analisar Execução do {pes} - Selecione o tipo de análise'
    url_retorno = f'/pgd2/analisar_pes/{pes_id}/?a={request.GET.get("a")}'

    analise_foi_iniciada_mas_nao_finalizada = pes.analise_foi_iniciada_mas_nao_finalizada()
    analise_foi_finalizada = pes.analise_foi_finalizada()
    pode_enviar_avaliacao = pes.pode_solicitar_avaliacao(request.user, validar_analise_entregas_pes=True)[0]

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.chefe')
def analisar_pes_detalhado(request, pes_id):
    """Painel da análise detalhada: lista entregas aptas com indicadores de progresso.

    Mostra o quanto já foi analisado vs. pendente, alerta sobre servidores
    relacionados sem RIT homologado e habilita o botão de enviar para
    avaliação somente quando todas as entregas estiverem analisadas.
    """
    pes = get_object_or_404(PlanoEntregasSetorial, pk=pes_id)
    pode_solicitar_avaliacao = pes.pode_solicitar_avaliacao(request.user)[0]
    if not pode_solicitar_avaliacao:
        raise PermissionDenied

    title = f'Analisar Execução do {pes} - Análise Detalhada'

    entregas_pes = pes.get_entregas_aptas().select_related('pes')
    qtd_entregas_pes = entregas_pes.count()
    entregas_pes_nao_analisadas = entregas_pes.filter(entrega_analise__isnull=True)
    qtd_entregas_pes_nao_analisadas = entregas_pes_nao_analisadas.count()
    entregas_pes_analisadas = entregas_pes.filter(entrega_analise__isnull=False)
    qtd_entregas_pes_analisadas = entregas_pes_analisadas.count()

    analise_foi_iniciada_mas_nao_finalizada = pes.analise_foi_iniciada_mas_nao_finalizada()
    analise_foi_finalizada = pes.analise_foi_finalizada()
    pode_enviar_avaliacao = pes.pode_solicitar_avaliacao(request.user, validar_analise_entregas_pes=True)[0]

    lista_servidores_adesao_por_periodo = pes.get_servidores_relacionados_com_pendencia()
    if lista_servidores_adesao_por_periodo:
        tem_servidor_sem_rit_homologado = True

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.chefe')
def analisar_pes_detalhado_entrega(request, entrega_pes_id):
    """Registra a análise de uma entrega específica do PES.

    Agrega a quantidade efetivamente executada via RITs vinculados à entrega
    (quando a métrica é quantitativa) e pré-popula `meta_analise` para o
    chefe ajustar antes de gravar via `AnaliseCompletaExecucaoPesForm`.
    """
    entrega_pes = get_object_or_404(PlanoEntregasSetorialEntregas, pk=entrega_pes_id)
    pes = entrega_pes.pes
    pode_solicitar_avaliacao = pes.pode_solicitar_avaliacao(request.user)[0]
    if not pode_solicitar_avaliacao:
        raise PermissionDenied

    title = f'Analisar execução da {entrega_pes}'
    url_retorno = f'/pgd2/analisar_pes_detalhado/{pes.id}/'

    utilizar_plan_estrat = utilizar_integracao_com_plan_estrategico()

    pits = PlanoIndividualTrabalho.get_pits_por_pes(pes).order_by('adesao__servidor')
    entregas_rit = (
        RelatorioIndividualTrabalho.objects.filter(entrega_pit__pit__in=pits, entrega_pit__entrega_pes=entrega_pes)
        .order_by('entrega_pit__pit__periodo_pit_rit__data_inicio', 'entrega_pit__pit__adesao__servidor__pessoa_fisica__nome')
        .select_related('entrega_pit__pit__adesao__servidor', 'entrega_pit__pit__periodo_pit_rit')
    )
    qtd_entregas_executadas = entregas_rit.count()

    qtd_executada = 0
    if entrega_pes.tem_metrica_de_quantidade():
        qtd_executada = int(gv(entregas_rit.aggregate(v=Sum('quantidade_progresso'))))
        if not entrega_pes.meta_analise:
            entrega_pes.meta_analise = qtd_executada

    form = AnaliseCompletaExecucaoPesForm(request.POST or None, instance=entrega_pes)
    if form.is_valid():
        form.save()
        return httprr(url_retorno, 'A análise da execução do PES foi salva com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def solicitar_avaliacao_pes(request, pes_id):
    """Finaliza a análise e solicita avaliação do PES.

    Diferenciado pelo `?a=s` (simplificada) ou `?a=d` (detalhada). Em ambos
    os modos pede uma observação e — quando houver servidores sem RIT
    homologado — uma confirmação explícita do chefe; ao confirmar, chama
    `analisar_pes_modo_simplificado`/`_detalhado` e registra
    `TIPO_SOLICITOU_AVALIACAO` no log.
    """
    pes = get_object_or_404(PlanoEntregasSetorial, pk=pes_id)
    if not pes.pode_solicitar_avaliacao(request.user)[0]:
        raise PermissionDenied

    eh_analise_simplicada = request.GET.get('a') and request.GET.get('a') == 's'
    eh_analise_detalhada = request.GET.get('a') and request.GET.get('a') == 'd'

    title = f'Solicitar Avaliação da Execução do {pes}'
    if eh_analise_simplicada:
        title = f'Análise Simplificada e Solicitação da Avaliação da Execução do {pes}'

    url_retorno = reverse('visualizar_pes_pgd2', args=[pes.id])

    if eh_analise_simplicada:
        analise_foi_iniciada_mas_nao_finalizada = pes.analise_foi_iniciada_mas_nao_finalizada()

        tem_servidor_sem_rit_homologado = False
        if not request.POST:
            lista_servidores_adesao_por_periodo = pes.get_servidores_relacionados_com_pendencia()
            if lista_servidores_adesao_por_periodo:
                tem_servidor_sem_rit_homologado = True

        form = AnaliseSimplificadaExecucaoPesForm(request.POST or None, tem_servidor_sem_rit_homologado=tem_servidor_sem_rit_homologado)
        if form.is_valid():
            observacao = form.cleaned_data.get('observacao')

            pes.analisar_pes_modo_simplificado(avaliacao_solicitacao_observacao_pes=observacao)

            confirmacao_servidor_sem_rit_homologado = form.cleaned_data.get('confirmacao_servidor_sem_rit_homologado')
            confirmacoes = 'Realizou Análise Simplificada da execução do PES. Confirmou que todas as entregas do PES foram Executadas Totalmente.'
            if confirmacao_servidor_sem_rit_homologado:
                confirmacoes = f'Realizou Análise Simplificada da execução do PES. Confirmou que todas as entregas do PES foram Executadas Totalmente. Confirmou que no momento desta solicitação existiam alguns servidores com {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2} não homologado para o período do PES.'

            ra_obs = f'Solicitou Avaliação da Execução do "{pes}". {confirmacoes}'
            if observacao:
                ra_obs = f'Solicitou Avaliação da Execução do "{pes}" considerando a observação "{observacao}". {confirmacoes}'

            RegistroAcaoPES.registrar(request=request, tipo=RegistroAcaoPES.TIPO_SOLICITOU_AVALIACAO, pes=pes, obs=ra_obs)
            return httprr(url_retorno, 'A solicitação de avaliação da execução do PES foi enviada com sucesso.')

    if eh_analise_detalhada:
        pode_enviar_avaliacao = pes.pode_solicitar_avaliacao(request.user, validar_analise_entregas_pes=True)[0]
        if not pode_enviar_avaliacao:
            raise PermissionDenied
        tem_servidor_sem_rit_homologado = False
        if not request.POST:
            lista_servidores_adesao_por_periodo = pes.get_servidores_relacionados_com_pendencia()
            if lista_servidores_adesao_por_periodo:
                tem_servidor_sem_rit_homologado = True

        form = AnaliseDetalhadaExecucaoPesForm(request.POST or None, tem_servidor_sem_rit_homologado=tem_servidor_sem_rit_homologado)
        if form.is_valid():
            observacao = form.cleaned_data.get('observacao')

            pes.analisar_pes_modo_detalhado(avaliacao_solicitacao_observacao_pes=observacao)

            confirmacao_servidor_sem_rit_homologado = form.cleaned_data.get('confirmacao_servidor_sem_rit_homologado')
            confirmacoes = 'Realizou Análise Detalhada da execução do PES.'
            if confirmacao_servidor_sem_rit_homologado:
                confirmacoes = f'Realizou Análise Detalhada da execução do PES. Confirmou que no momento desta solicitação existiam alguns servidores com {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2} não homologado para o período do PES.'

            ra_obs = f'Solicitou Avaliação da Execução do "{pes}". {confirmacoes}'
            if observacao:
                ra_obs = f'Solicitou Avaliação da Execução do "{pes}" considerando a observação "{observacao}". {confirmacoes}'

            RegistroAcaoPES.registrar(request=request, tipo=RegistroAcaoPES.TIPO_SOLICITOU_AVALIACAO, pes=pes, obs=ra_obs)
            return httprr(url_retorno, 'A solicitação de avaliação da execução do PES foi enviada com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.chefe')
def avaliar_pes(request, pes_id):
    """Grava a avaliação final do PES (chefe do setor superior).

    Define `situacao_avaliacao=AVALIADO`, `avaliacao_pes` (conceito) e
    `avaliacao_observacao_pes` (justificativa). O log de ação cita também a
    observação registrada pelo solicitante.
    """
    pes = get_object_or_404(PlanoEntregasSetorial, pk=pes_id)
    if not pes.pode_avaliar(request.user)[0]:
        raise PermissionDenied

    title = f'Avaliar execução do {pes}'
    url = reverse('visualizar_pes_pgd2', args=[pes.id])

    justificativa_observacao_solicitacao = None
    r = RegistroAcaoPES.objects.filter(pes=pes, tipo=RegistroAcaoPES.TIPO_SOLICITOU_AVALIACAO).first()
    if r.observacao:
        justificativa_observacao_solicitacao = r.observacao

    form = AvaliacaoPesForm(request.POST or None, request=request)
    if form.is_valid():
        avaliacao_pes = form.cleaned_data.get('avaliacao_pes')
        justificativa = form.cleaned_data.get('justificativa')

        pes.situacao_avaliacao = PlanoEntregasSetorial.AVALIADO
        pes.avaliacao_pes = avaliacao_pes
        pes.avaliacao_observacao_pes = justificativa
        pes.save()

        avaliacao_pes_str = PlanoEntregasSetorial.AVALIACAO_PES_CHOICES[int(avaliacao_pes) - 1][1]

        ra_obs = f'Avaliação do "{pes}" mediante a avaliação "{avaliacao_pes_str}" e confirmação da execução do PES'
        if justificativa:
            ra_obs = (
                f'Avaliação do "{pes}" mediante a avaliação "{avaliacao_pes_str}", justificativa "{justificativa}" e confirmação da execução do PES'
            )

        RegistroAcaoPES.registrar(request=request, tipo=RegistroAcaoPES.TIPO_AVALIOU, pes=pes, obs=ra_obs)

        return httprr(url, 'A avaliação da execução do PES foi registrada com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.chefe')
def reabrir_pes(request, pes_id):
    """Reabre o PES já avaliado (zera situacao/avaliacao/observações).

    Permite uma nova rodada de análise/avaliação; exige justificativa, que
    fica no `TIPO_REABRIU`.
    """
    pes = get_object_or_404(PlanoEntregasSetorial, pk=pes_id)
    if not pes.pode_reabrir(request.user)[0]:
        raise PermissionDenied

    title = f'Reabrir/Devolver {pes}'
    url = reverse('visualizar_pes_pgd2', args=[pes.id])

    form = JustificativaComSenhaForm(request.POST or None, request=request)
    if form.is_valid():
        justificativa = form.cleaned_data.get('justificativa')

        # Atualiza PES
        pes.situacao_avaliacao = None
        pes.avaliacao_pes = None
        pes.avaliacao_solicitacao_observacao_pes = None
        pes.avaliacao_observacao_pes = None
        pes.save()

        ra_obs = f'Reabriu o "{pes}"'
        if justificativa:
            ra_obs = f'Reabriu o "{pes}" mediante a justificativa "{justificativa}"'

        RegistroAcaoPES.registrar(request=request, tipo=RegistroAcaoPES.TIPO_REABRIU, pes=pes, obs=ra_obs)

        return httprr(url, 'O PES foi reaberto para uma nova análise.')

    return locals()


@rtr()
@permission_required('rh.chefe')
def qrcode_setor(request):
    visualizar_qrcode = request.GET.get('setorqc')

    ids_setores_com_pes = PlanoEntregasSetorial.get_pess_aprovados().values('setor_id')
    title = 'QR Code do Setor'

    if visualizar_qrcode:
        setor_qrcode = get_setores_pgd().filter(id__in=ids_setores_com_pes).filter(id=visualizar_qrcode).first()
        if setor_qrcode:
            title = f'QR Code do Setor - {setor_qrcode}'
            url = f'{settings.SITE_URL}/pgd2/visualizar_setor_pgd/{visualizar_qrcode}'
            img = qrcode.make(url)
            buffer_img = io.BytesIO()
            img.save(buffer_img, 'png')
            qrcode_setor = base64.encodebytes(buffer_img.getvalue()).decode()
    else:
        lista_setores = setores_que_sou_chefe_hoje(request.user.get_relacionamento()).filter(id__in=ids_setores_com_pes)
        form = BuscarSetoresPgdForm(request.GET or None, request=request, setores_chefe=lista_setores)
        if form.is_valid():
            setor = form.cleaned_data.get('setor')
            if setor:
                lista_setores = lista_setores.filter(id=setor.id)

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def copiar_pes(request, pes_id):
    pes = get_object_or_404(PlanoEntregasSetorial, pk=pes_id)
    if not pes.pode_receber_copia(request.user):
        raise PermissionDenied

    title = f'Copiar dados para o {pes}'
    url = reverse('visualizar_pes_pgd2', args=[pes.id])

    form = CopiarPesForm(request.POST or None, request=request, pess_podem_ser_copiados=pes.get_pess_podem_ser_copiados_para_este())
    if form.is_valid():
        pes_origem = form.cleaned_data.get('pes_origem')
        substituir_entregas_atuais = form.cleaned_data.get('confirmacao1')
        substituir_auxiliares_atuais = form.cleaned_data.get('confirmacao2')
        pes.copiar_outro_pes_para_este(pes_origem, substituir_entregas_atuais, substituir_auxiliares_atuais)
        return httprr(url, 'Os dados selecionados do PES de origem foram copiados para este PES.')

    return locals()


# ====================================================
# Servidor PGD
# ====================================================


@rtr()
@permission_required('rh.eh_servidor')
def meu_pgd(request, matricula=None):
    """Painel "Meu PGD" do servidor (ou de outro, via `matricula=`).

    Modo `meupgd` (padrão): adesões + PITs/RITs recalculados + registros de
    PGD em outro órgão. Modo `pessauxiliar`: PESs em que o servidor é
    auxiliar. Quando consultando outro servidor, exibe ainda horários
    presenciais/atendimento dentro de ±15 dias e pendências (se quem
    consulta é gestão/comissão).
    """
    servidor = None
    if matricula:
        servidor = get_object_or_404(Servidor, matricula=matricula)
    else:
        servidor = request.user.get_relacionamento()
    if not matricula or matricula == request.user.get_relacionamento().matricula:
        eh_meu_pgd = True
        title = f'Meu PGD - {servidor}'
    else:
        eh_meu_pgd = False
        title = f'PGD - {servidor}'

    adesoes_pgd = SolicitacaoAdesaoServidor.objects.filter(servidor=servidor).order_by('id')

    # meupgd ou pessauxiliar
    modo = request.GET.get('modo') or 'meupgd'

    if eh_meu_pgd and modo == 'pessauxiliar':
        pess_que_sou_auxiliar = PlanoEntregasSetorial.objects.filter(auxiliares__in=[request.user.get_vinculo()])
    else:
        if eh_meu_pgd:
            # calcula os PITs e RITs
            pits_relacionados = PlanoIndividualTrabalho.objects.filter(adesao__in=adesoes_pgd).order_by('-data_inicio')
            for pit in pits_relacionados:
                pit.calcular_pit()

            # PGD exterior
            registros_pgd_exterior = SolicitacaoAdesaoServidor.get_dados_servidores_em_pgd_exterior(servidor)

        if not eh_meu_pgd:
            # busca horarios em PITs que foram homologados alguma vez
            adesoes_vigentes = SolicitacaoAdesaoServidor.get_vigentes(servidor.get_user())
            if adesoes_vigentes:
                adesoes_vigentes = adesoes_vigentes.order_by('id')
                ultima_adesao_vigente = adesoes_vigentes.last()
                pits_da_adesao = (
                    PlanoIndividualTrabalho.objects.filter(adesao__in=adesoes_vigentes)
                    .exclude(situacao=PlanoIndividualTrabalho.CANCELADO)
                    .order_by('data_inicio')
                )
                pits_foi_homologado_alguma_vez = RegistroAcaoPlanoIndividualTrabalho.objects.filter(
                    pit__in=pits_da_adesao, tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_HOMOLOGOU
                ).values('pit__id')
                pits_da_adesao = pits_da_adesao.filter(id__in=pits_foi_homologado_alguma_vez)
                quinze_dias_anteriores = get_datetime_now().date() - timedelta(15)
                quinze_dias_posteriores = get_datetime_now().date() + timedelta(15)

                horarios_presencial_servidor = PlanoIndividualTrabalhoPresencial.objects.filter(pit__in=pits_da_adesao, homologado=True).order_by(
                    'data', 'hora_inicio'
                )
                horarios_presencial_servidor = horarios_presencial_servidor.filter(data__range=(quinze_dias_anteriores, quinze_dias_posteriores))
                horarios_atendimento_teletrabalho_servidor = PlanoIndividualTrabalhoAtendimento.objects.filter(
                    pit__in=pits_da_adesao, homologado=True
                ).order_by('data', 'hora_inicio')
                horarios_atendimento_teletrabalho_servidor = horarios_atendimento_teletrabalho_servidor.filter(
                    data__range=(quinze_dias_anteriores, quinze_dias_posteriores)
                )

        pendencias_servidor = None
        eh_gestao = ComissaoPGD.user_estah_em_gestao_pgd(request.user) or ComissaoPGD.user_estah_em_comissao_sistemica_vigente(request.user)
        if eh_gestao and not eh_meu_pgd:
            pendencias_servidor = get_pendencias_servidor(servidor.get_user(), apenas_lista_separada=False)

    return locals()


@permission_required('rh.eh_servidor')
def atualizar_dados_pgd_suap_com_sougov(request):
    url = reverse('servidor_pgd_pgd2')
    servidor = request.user.get_relacionamento()
    erro, _ = get_pgd_sou_gov(servidor.pessoa_fisica.cpf, servidor.matricula, atualizar_suap_com_sou_gov=True)
    if erro == 'erro':
        return httprr(url, 'Erro ao tentar atualizar os dados. Tente novamente', tag='error')
    return httprr(url, 'Dados atualizados. Apenas dados relacionados ao "Regime individual de execução no PGD" são atualizados. ')


# ====================================================
# Adesão PGD
# ====================================================


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def solicitar_adesao(request):
    """Cria uma nova `SolicitacaoAdesaoServidor` no estado `SOLICITADO`.

    Vincula ao documento de adesão vigente no período, aplica `+55` como
    código de país padrão e registra `TIPO_SOLICITADO` no log da solicitação
    com o IP do requisitante.
    """
    title = 'Solicitar Adesão ao PGD'

    pode_solicitar, erros = SolicitacaoAdesaoServidor.pode_solicitar(request.user, True)

    if pode_solicitar:
        servidor = request.user.get_relacionamento()
        documento_vigente = SolicitacaoAdesaoServidor.get_regras_relacionadas_ao_periodo()

        form = SolicitarAdesaoPgdForm(request.POST or None, request=request)
        if request.method == 'POST':
            if form.is_valid():
                sol = form.save(False)
                sol.servidor = servidor
                sol.documento_adesao = documento_vigente
                sol.codigo_contato_pais = form.cleaned_data.get('codigo_contato_pais') or 55
                sol.situacao = SolicitacaoAdesaoServidor.SOLICITADO
                sol.save()

                ip = get_client_ip(request)
                RegistroAcaoSolicitacaoAdesaoServidor.objects.create(
                    tipo=RegistroAcaoSolicitacaoAdesaoServidor.TIPO_SOLICITADO, solicitacao=sol, ip=ip, observacao=''
                )

                url = reverse('visualizar_solicitacao_adesao_pgd2', args=[sol.id])
                return httprr(url, 'Solicitação de Adesão submetida com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def editar_telefone_pgd(request, sol_id):
    sol = get_object_or_404(SolicitacaoAdesaoServidor, pk=sol_id)
    if not sol.pode_editar_telefone_pgd(request.user):
        raise PermissionDenied

    title = f'Editar Telefone para contato PGD - {sol}'
    url = reverse('visualizar_solicitacao_adesao_pgd2', args=[sol_id])

    telefone = sol.telefone

    form = EditarTelefonePgdForm(request.POST or None, request=request, instance=sol)
    if form.is_valid():
        obj = form.save(False)
        obj.codigo_contato_pais = form.cleaned_data.get('codigo_contato_pais') or 55
        obj.save()
        return httprr(url, 'Telefone editado com sucesso.')

    return locals()


@rtr()
@permission_required('rh.eh_servidor')
def visualizar_solicitacao_adesao(request, sol_id):
    """Tela da solicitação de adesão de um servidor.

    Expõe flags de quais ações o usuário corrente pode disparar (cancelar,
    avaliar, editar telefone, cadastrar desligamento) e o histórico de
    desligamentos + log de ações.
    """
    sol = get_object_or_404(SolicitacaoAdesaoServidor, pk=sol_id)

    title = 'Solicitação de Adesão do Servidor ao PGD'
    if sol.estah_deferida:
        title = 'Adesão do Servidor ao PGD'

    if not sol.pode_visualizar(request.user):
        raise PermissionDenied

    servidor = sol.servidor
    pode_cancelar_servidor = sol.pode_cancelar_servidor(request.user)
    pode_cancelar_avaliador = sol.pode_cancelar_avaliador(request.user)
    pode_avaliar = sol.pode_avaliar(request.user)
    pode_editar_telefone_pgd = sol.pode_editar_telefone_pgd(request.user)
    pode_cadastrar_desligamento, _ = DesligamentoPgdServidor.pode_iniciar_cadastro(request.user, sol, retornar_lista_erros=False)

    registros_acoes = RegistroAcaoSolicitacaoAdesaoServidor.objects.filter(solicitacao=sol)
    desligamentos = DesligamentoPgdServidor.objects.filter(adesao=sol).order_by('data_cadastro')

    estah_vigente = sol.estah_vigente
    data_desligamento_efeitos_a_partir_de = sol.data_desligamento_efeitos_a_partir_de

    documento_vigente = sol.documento_adesao

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def alterar_situacao_solicitacao_adesao(request, sol_id, alteracao_id):
    sol = get_object_or_404(SolicitacaoAdesaoServidor, pk=sol_id)

    # Sabendo e verificando qual alteração será feita
    # SolicitacaoAdesaoServidor.CANCELADO_PELO_SERVIDOR = 2
    # SolicitacaoAdesaoServidor.CANCELADO_PELO_AVALIADOR = 3
    # SolicitacaoAdesaoServidor.DEFERIDO = 4
    # SolicitacaoAdesaoServidor.INDEFERIDO = 5

    if alteracao_id not in [
        SolicitacaoAdesaoServidor.CANCELADO_PELO_SERVIDOR,
        SolicitacaoAdesaoServidor.CANCELADO_PELO_AVALIADOR,
        SolicitacaoAdesaoServidor.DEFERIDO,
        SolicitacaoAdesaoServidor.INDEFERIDO,
    ]:
        raise PermissionDenied
    if (
        alteracao_id == SolicitacaoAdesaoServidor.CANCELADO_PELO_SERVIDOR
        and not sol.pode_cancelar_servidor(request.user)
        or alteracao_id == SolicitacaoAdesaoServidor.CANCELADO_PELO_AVALIADOR
        and not sol.pode_cancelar_avaliador(request.user)
        or alteracao_id == SolicitacaoAdesaoServidor.DEFERIDO
        and not sol.pode_avaliar(request.user)
        or alteracao_id == SolicitacaoAdesaoServidor.INDEFERIDO
        and not sol.pode_avaliar(request.user)
    ):
        raise PermissionDenied

    title = f'Alterar a situação da {sol.__str__()} para {SolicitacaoAdesaoServidor.SITUACAO_SOLICITACAO_ADESAO_CHOICES[alteracao_id - 1][1]}'
    url = reverse('visualizar_solicitacao_adesao_pgd2', args=[sol_id])

    form = JustificativaComSenhaForm(request.POST or None, request=request)

    if request.method == 'POST':
        if form.is_valid():
            sol.situacao = alteracao_id

            if alteracao_id == SolicitacaoAdesaoServidor.DEFERIDO:
                sol.data_inicio = get_datetime_now().date()

            sol.save()

            ip = get_client_ip(request)
            ra_obs = f'A situação da {sol.__str__()} foi alterada para "{SolicitacaoAdesaoServidor.SITUACAO_SOLICITACAO_ADESAO_CHOICES[alteracao_id - 1][1]}"'
            if form.cleaned_data.get('justificativa'):
                justificativa = form.cleaned_data.get('justificativa')
                ra_obs = f'A situação da {sol.__str__()} foi alterada para "{SolicitacaoAdesaoServidor.SITUACAO_SOLICITACAO_ADESAO_CHOICES[alteracao_id - 1][1]}" mediante a justificativa "{justificativa}"'
            RegistroAcaoSolicitacaoAdesaoServidor.objects.create(tipo=alteracao_id, solicitacao=sol, ip=ip, observacao=ra_obs)

            situacao = SolicitacaoAdesaoServidor.SITUACAO_SOLICITACAO_ADESAO_CHOICES[alteracao_id - 1][1]
            return httprr(url, f'A solicitação teve a situação atualizada para "{situacao}".')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def cadastrar_desligamento_pgd(request, sol_id):
    """Cadastra o desligamento de uma adesão PGD (servidor ou chefe).

    O conjunto de justificativas exibidas depende do perfil de quem
    cadastra (servidor x chefe; gestão/comissão atua como chefe). Após
    salvar o `DesligamentoPgdServidor`:

    - aplica a carência para nova adesão (se a justificativa tiver punição);
    - propaga `data_desligamento_efeitos_a_partir_de` e
      `data_desligamento_carencia_ate` para a adesão;
    - recalcula todos os PITs ainda em execução (não cancelados e sem RIT
      homologado);
    - grava `TIPO_DESLIGAMENTO` no log da solicitação.
    """
    # Chefe Cadastra Desligamento
    # OU Servidor Cadastra Desligamento
    # Gestor do PGD e Comissão Sistêmica PGD farão o cadastro como chefe

    title = 'Cadastrar Desligamento do PGD'

    adesao = get_object_or_404(SolicitacaoAdesaoServidor, pk=sol_id)
    servidor = adesao.servidor
    erros = []

    pode_iniciar_cadastro, erros = DesligamentoPgdServidor.pode_iniciar_cadastro(request.user, adesao, retornar_lista_erros=True)
    if not pode_iniciar_cadastro:
        return locals()

    # Se quem estah cadastrando é o chefe (ou outros com que podem cadastrar como chefe) ou o servidor da adesao
    # Lista das justificativas de acordo com o perfil de quem esta cadastrando
    perfil_user_estah_cadastrando = DesligamentoPgdServidor.perfil_user_estah_cadastrando(request.user, adesao)
    justificativas = []
    if perfil_user_estah_cadastrando == 'servidor':
        # servidor
        justificativas = JustificativaDesligamentoPgd.get_justificativas_servidor()
    else:
        # chefe
        justificativas = JustificativaDesligamentoPgd.get_justificativas_chefe()

    if not justificativas:
        raise PermissionDenied('A gestão ainda não cadastrou as Justificativas de Desligamento')

    # Cadastro
    form = CadastrarDesligamentoPgdForm(
        request.POST or None, request=request, lista_justificativas=justificativas, perfil_user_estah_cadastrando=perfil_user_estah_cadastrando
    )
    if request.method == 'POST':
        if form.is_valid():
            data_desligamento_efeitos_a_partir_de = form.cleaned_data.get('data_desligamento_efeitos_a_partir_de')
            pode, erros = DesligamentoPgdServidor.pode_cadastrar(
                request.user, adesao, retornar_lista_erros=True, data_desligamento_efeitos_a_partir_de=data_desligamento_efeitos_a_partir_de
            )
            if pode:
                d = DesligamentoPgdServidor()
                d.adesao = adesao
                d.justificativa = form.cleaned_data.get('justificativa')
                d.observacao = form.cleaned_data.get('observacao')
                d.data_desligamento_efeitos_a_partir_de = form.cleaned_data.get('data_desligamento_efeitos_a_partir_de')
                d.data_cadastro = get_datetime_now()
                d.usuario_cadastro = request.user
                d.save()

                # Se tem punicao de dias na justificativa
                if d.justificativa.qtd_dias_punicao > 0:
                    carencia_nova_adesao_ate = d.data_desligamento_efeitos_a_partir_de + relativedelta(days=d.justificativa.qtd_dias_punicao)
                    d.data_pode_solicitar_nova_adesao = carencia_nova_adesao_ate
                    d.save()
                    adesao.data_pode_solicitar_nova_adesao = d.data_pode_solicitar_nova_adesao

                # Cadastra deligamento no PIT
                adesao.data_desligamento_efeitos_a_partir_de = d.data_desligamento_efeitos_a_partir_de
                adesao.data_desligamento_carencia_ate = d.data_desligamento_efeitos_a_partir_de + relativedelta(
                    days=PlanoIndividualTrabalho.CARENCIA_PARA_EDICAO_PIT_SEM_ADESAO_VIGENTE
                )
                adesao.save()

                # Calcula os PITs/RITs da adesao
                # Calcula os PITs não cancelados e sem RIT homologado
                pits_calcular = adesao.get_pits_todos().exclude(
                    Q(situacao=PlanoIndividualTrabalho.CANCELADO) | Q(situacao_rit=PlanoIndividualTrabalho.HOMOLOGADO_RIT)
                )
                for pit in pits_calcular:
                    pit.calcular_pit()

                url = reverse('visualizar_solicitacao_adesao_pgd2', args=[adesao.id])

                ip = get_client_ip(request)
                justificativa = form.cleaned_data.get('justificativa')
                ra_obs = f'O Desligamento do PGD da {adesao.__str__()} foi cadastrado com daata de efeitos a partir de "{format_datetime(data_desligamento_efeitos_a_partir_de)}" mediante seguinte justificativa "{justificativa}". Além disso, CONFIRMOU que estava ciente de que este desligamento só poderia ser cancelado até o dia anterior da data de efeitos.'
                RegistroAcaoSolicitacaoAdesaoServidor.objects.create(
                    tipo=RegistroAcaoSolicitacaoAdesaoServidor.TIPO_DESLIGAMENTO, solicitacao=adesao, ip=ip, observacao=ra_obs
                )

                return httprr(url, 'O desligamento foi cadastrado com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def cancelar_desligamento_pgd(request, deslig_id):
    """Cancela um desligamento ainda dentro da janela permitida.

    Limpa as datas de efeito/carência na adesão, recalcula os PITs em
    execução e registra `TIPO_DESLIGAMENTO_CANCELADO` no log.
    """
    desligamento = get_object_or_404(DesligamentoPgdServidor, pk=deslig_id)
    if not desligamento.pode_cancelar(request.user):
        raise PermissionDenied

    title = f'Cancelar desligado da adesão {desligamento.adesao}'
    url = reverse('visualizar_solicitacao_adesao_pgd2', args=[desligamento.adesao.id])

    form = JustificativaComSenhaForm(request.POST or None, request=request)

    if request.method == 'POST':
        if form.is_valid():
            desligamento.data_cancelamento = get_datetime_now()
            desligamento.save()

            adesao = desligamento.adesao
            adesao.data_desligamento_efeitos_a_partir_de = None
            adesao.data_desligamento_carencia_ate = None
            adesao.data_pode_solicitar_nova_adesao = None
            adesao.save()

            # Calcula os PITs/RITs da adesao
            # Calcula os PITs não cancelados e sem RIT homologado
            pits_calcular = adesao.get_pits_todos().exclude(
                Q(situacao=PlanoIndividualTrabalho.CANCELADO) | Q(situacao_rit=PlanoIndividualTrabalho.HOMOLOGADO_RIT)
            )
            for pit in pits_calcular:
                pit.calcular_pit()

            ip = get_client_ip(request)
            justificativa = form.cleaned_data.get('justificativa')
            ra_obs = f'O Desligamento foi cancelado mediante a justificativa "{justificativa}".'
            RegistroAcaoSolicitacaoAdesaoServidor.objects.create(
                tipo=RegistroAcaoSolicitacaoAdesaoServidor.TIPO_DESLIGAMENTO_CANCELADO, solicitacao=desligamento.adesao, ip=ip, observacao=ra_obs
            )

            return httprr(url, 'O desligamento foi cancelado com sucesso.')

    return locals()


# ====================================================
# Adesão PES (Setor)
# ====================================================


@rtr()
@permission_required('rh.eh_servidor')
def selecionar_setor_solicitar_adesao_pes(request):
    title = 'Solicitação de Adesão do Servidor ao PES - Selecione o setor'

    pode_solicitar, erros = SolicitacaoAdesaoPesServidor.pode_iniciar_solicitacao(request.user, retornar_lista_erros=True)

    if pode_solicitar:
        form = SelecionarSetorForm(request.POST or None)
        if form.is_valid():
            setor = form.cleaned_data.get('setor')
            url = f'/pgd2/solicitar_adesao_pes/{setor.id}'

            return httprr(url)

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def solicitar_adesao_pes(request, setor_id):
    setor = get_object_or_404(Setor, pk=setor_id)
    title = f'Solicitar Adesão ao PES do Setor {setor} - Confirmação'

    pode_solicitar, erros = SolicitacaoAdesaoPesServidor.pode_solicitar(user=request.user, setor=setor, adesao_pgd=None, retornar_lista_erros=True)

    if pode_solicitar:
        adesoes_pgd = SolicitacaoAdesaoServidor.get_vigentes_ou_desligado_na_carencia(request.user)
        documento_vigente = DocumentoAdesaoPesServidor.get_vigente()

        servidor = request.user.get_relacionamento()
        pess_aptos = PlanoEntregasSetorial.get_pess_aprovados(setor=setor).order_by('periodo_pes__data_inicio')

        form = SolicitarAdesaoPesForm(request.POST or None, request=request, adesoes_pgd=adesoes_pgd)
        if request.method == 'POST':
            if form.is_valid():
                adesao_pgd = form.cleaned_data.get('adesao_pgd')
                pode_solicitar, erros = SolicitacaoAdesaoPesServidor.pode_solicitar(
                    user=request.user, setor=setor, adesao_pgd=adesao_pgd, retornar_lista_erros=True
                )
                if not pode_solicitar:
                    return locals()

                sol = SolicitacaoAdesaoPesServidor()
                sol.setor = setor
                sol.adesao = adesao_pgd
                sol.situacao = SolicitacaoAdesaoPesServidor.SOLICITADO
                sol.documento_adesao = documento_vigente
                sol.save()

                ip = get_client_ip(request)
                RegistroAcaoSolicitacaoAdesaoPesServidor.objects.create(
                    tipo=RegistroAcaoSolicitacaoAdesaoPesServidor.TIPO_SOLICITADO, solicitacao=sol, ip=ip, observacao=''
                )

                url = reverse('visualizar_solicitacao_adesao_pes_pgd2', args=[sol.id])
                return httprr(url, 'Solicitação de Adesão ao PES submetida com sucesso.')

    return locals()


@rtr()
@permission_required('rh.eh_servidor')
def visualizar_solicitacao_adesao_pes(request, sol_id):
    sol = get_object_or_404(SolicitacaoAdesaoPesServidor, pk=sol_id)

    title = 'Solicitação de Adesão do Servidor ao PES'

    if not sol.pode_visualizar(request.user):
        raise PermissionDenied

    servidor = sol.adesao.servidor
    pode_cancelar_servidor = sol.pode_cancelar_servidor(request.user)
    pode_cancelar_avaliador = sol.pode_cancelar_avaliador(request.user)
    pode_avaliar = sol.pode_avaliar(request.user)
    pode_cadastrar_desligamento_servidor = sol.pode_cadastrar_desligamento_servidor(request.user)

    registros_acoes = RegistroAcaoSolicitacaoAdesaoPesServidor.objects.filter(solicitacao=sol)

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def alterar_situacao_solicitacao_adesao_pes(request, sol_id, alteracao_id):
    # Acessado pelo Servidor e Chefe

    sol = get_object_or_404(SolicitacaoAdesaoPesServidor, pk=sol_id)

    # Sabendo e verificando qual alteração será feita
    # SolicitacaoAdesaoServidor.CANCELADO_PELO_SERVIDOR = 2
    # SolicitacaoAdesaoServidor.CANCELADO_PELO_AVALIADOR = 3
    # SolicitacaoAdesaoServidor.DEFERIDO = 4
    # SolicitacaoAdesaoServidor.INDEFERIDO = 5
    if alteracao_id not in [
        SolicitacaoAdesaoPesServidor.CANCELADO_PELO_SERVIDOR,
        SolicitacaoAdesaoPesServidor.CANCELADO_PELO_AVALIADOR,
        SolicitacaoAdesaoPesServidor.DEFERIDO,
        SolicitacaoAdesaoPesServidor.INDEFERIDO,
    ]:
        raise PermissionDenied
    if (
        alteracao_id == SolicitacaoAdesaoPesServidor.CANCELADO_PELO_SERVIDOR
        and not sol.pode_cancelar_servidor(request.user)
        or alteracao_id == SolicitacaoAdesaoPesServidor.CANCELADO_PELO_AVALIADOR
        and not sol.pode_cancelar_avaliador(request.user)
        or alteracao_id == SolicitacaoAdesaoPesServidor.DEFERIDO
        and not sol.pode_avaliar(request.user)
        or alteracao_id == SolicitacaoAdesaoPesServidor.INDEFERIDO
        and not sol.pode_avaliar(request.user)
    ):
        raise PermissionDenied

    title = f'Alteração a situação da {sol.__str__()} para {SolicitacaoAdesaoPesServidor.SITUACAO_SOLICITACAO_ADESAO_CHOICES[alteracao_id - 1][1]}'
    url = reverse('visualizar_solicitacao_adesao_pes_pgd2', args=[sol_id])

    form = JustificativaComSenhaForm(request.POST or None, request=request)

    if request.method == 'POST':
        if form.is_valid():
            sol.situacao = alteracao_id
            sol.save()

            ip = get_client_ip(request)
            justificativa = form.cleaned_data.get('justificativa')
            ra_obs = f'A situação da {sol.__str__()} foi alterada para "{SolicitacaoAdesaoServidor.SITUACAO_SOLICITACAO_ADESAO_CHOICES[alteracao_id - 1][1]}" mediante a justificativa "{justificativa}"'
            RegistroAcaoSolicitacaoAdesaoPesServidor.objects.create(tipo=alteracao_id, solicitacao=sol, ip=ip, observacao=ra_obs)

            return httprr(url, 'A situação da solicitação de adesão ao PES foi atualizada com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def cadastrar_desligamento_pes(request, sol_id):
    # Servidor Cadastra Desligamento

    sol = get_object_or_404(SolicitacaoAdesaoPesServidor, pk=sol_id)
    title = 'Cadastrar Desligamento de PES'
    servidor = sol.adesao.servidor

    if not sol.pode_cadastrar_desligamento_servidor(request.user):
        raise PermissionDenied

    url = reverse('visualizar_solicitacao_adesao_pes_pgd2', args=[sol_id])

    form = JustificativaComSenhaIrreversivelForm(request.POST or None, request=request)

    if request.method == 'POST':
        if form.is_valid():
            sol.data_desligamento = get_datetime_now()
            sol.save()

            ip = get_client_ip(request)
            justificativa = form.cleaned_data.get('justificativa')
            ra_obs = f'Foi cadastrado um DESLIGAMENTO para {sol.__str__()} mediante a justificativa "{justificativa}"'
            RegistroAcaoSolicitacaoAdesaoPesServidor.objects.create(
                tipo=RegistroAcaoSolicitacaoAdesaoPesServidor.TIPO_DESLIGAMENTO, solicitacao=sol, ip=ip, observacao=ra_obs
            )

            return httprr(url, 'O desligamento do servidor do PES foi registrado com sucesso.')

    return locals()


# ====================================================
# PIT
# ====================================================


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def cadastrar_pit(request):
    """Cria um novo Plano Individual de Trabalho (PIT) para o servidor.

    Resolve a janela do PIT alinhando o período PIT/RIT escolhido com o
    intervalo da adesão (início após a data da adesão; fim antes da data de
    efeito de um eventual desligamento). Inicia o PIT em `EM_CADASTRO`,
    marca-o para não enviar via API até a homologação, recalcula os setores
    envolvidos e registra `TIPO_EM_CADASTRO` no log.
    """
    # Servidor
    pode_iniciar_cadastro, erros = PlanoIndividualTrabalho.pode_iniciar_cadastro(user=request.user, retornar_lista_erros=True)

    servidor = request.user.get_relacionamento()
    title = f'Adicionar {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} - {servidor}'

    if pode_iniciar_cadastro:
        adesoes_pgd = SolicitacaoAdesaoServidor.get_vigentes_ou_desligado_na_carencia(request.user)
        form = CriarPitForm(request.POST or None, request=request, adesoes_pgd=adesoes_pgd)
        if request.method == 'POST':
            if form.is_valid():
                url = reverse('servidor_pgd_pgd2')

                # Calculando data início e final
                adesao_pgd = form.cleaned_data.get('adesao_pgd')
                periodo_pit_rit = form.cleaned_data.get('periodo_pit_rit')
                data_inicio = periodo_pit_rit.data_inicio
                if data_inicio < adesao_pgd.get_data_inicio_adesao():
                    data_inicio = adesao_pgd.get_data_inicio_adesao()

                data_fim = periodo_pit_rit.data_fim
                if adesao_pgd.data_desligamento_efeitos_a_partir_de and data_fim >= adesao_pgd.data_desligamento_efeitos_a_partir_de:
                    data_fim = adesao_pgd.data_desligamento_efeitos_a_partir_de - relativedelta(days=1)

                pode_finalizar_cadastro, erros = PlanoIndividualTrabalho.pode_finalizar_cadastro(
                    user=request.user,
                    periodo_pit_rit=periodo_pit_rit,
                    adesao_pgd=adesao_pgd,
                    data_inicio=data_inicio,
                    data_fim=data_fim,
                    retornar_lista_erros=True,
                )
                if not pode_finalizar_cadastro:
                    strs = []
                    c = 1
                    for m in erros:
                        strs.append(f'({c}) {m}')
                        c += 1
                    erro = ' / '.join(strs)
                    # return httprr(url, f'Erro(s) ao cadastrar o {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}: {erro}', tag='error')
                    return locals()

                # Salva dos dados
                pit = PlanoIndividualTrabalho()
                pit.adesao = adesao_pgd
                pit.periodo_pit_rit = periodo_pit_rit
                pit.data_inicio = data_inicio
                pit.data_fim = data_fim
                pit.situacao = PlanoIndividualTrabalho.EM_CADASTRO
                pit.save()

                pit.marcar_para_nao_enviar_pela_api()

                pit.calcular_pit_setores_envolvidos()

                ip = get_client_ip(request)
                RegistroAcaoPlanoIndividualTrabalho.objects.create(
                    tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_EM_CADASTRO, pit=pit, ip=ip, observacao=''
                )

                url = reverse('visualizar_pit_pgd2', args=[pit.id])
                return httprr(url, f'{nomenclatura.plano_individual_de_trabalho_sigla_pgd2} adicionado com sucesso.')

    return locals()


@rtr()
@permission_required('rh.eh_servidor')
def visualizar_pit(request, pit_id):
    """Tela principal do Plano Individual de Trabalho (PIT).

    Recalcula o PIT e seleciona o modo de exibição via `?m=`:
    `registro` (padrão, todos os dados), `historico` (somente histórico) ou
    o painel de solicitações de aprovação/homologação.
    """
    pit = get_object_or_404(PlanoIndividualTrabalho, pk=pit_id)
    if not pit.pode_visualizar(request.user):
        raise PermissionDenied

    pit.calcular_pit()

    # Registro: habilita todos os dados do PIT
    # Histórico: visualiza apenas o histórico
    # Solicitações de Aprovação / Homologação: visualiza apenas as solicitações de aprovação / homologação
    modo = request.GET.get('m', 'registro')

    title = pit.get_verbose_pit()

    pode_homologar_pit = pit.pode_homologar_pit(request.user)
    pode_homologar_pit2 = pit.pode_homologar_pit(request.user, considera_pendencia_geral_servidor_pgd=False)

    eu_mesmo = pit.adesao.servidor == request.user.get_relacionamento()
    pode_visualizar_nao_homologados = eu_mesmo or pit.pode_aprovar_pit(request.user) or (pode_homologar_pit or pode_homologar_pit2)
    msg_adesao_relacionada = pit.adesao

    registros_acoes = RegistroAcaoPlanoIndividualTrabalho.objects.filter(pit=pit)

    setores_envolvidos = pit.get_setores_envolvidos()
    tem_erro_nos_setores_envolvidos = False
    for setor in setores_envolvidos:
        if setor.tem_erro():
            tem_erro_nos_setores_envolvidos = True
            break

    orientacoes_vigentes_sistemico = pit.get_orientacoes_sistemicas_relacionadas_ao_periodo()
    orientacoes_vigentes_nao_sistemico = pit.get_orientacoes_nao_sistemicas_relacionadas_ao_periodo()

    pit_dados_basicos = None
    pit_copia = PlanoIndividualTrabalhoCopia.objects.filter(original=pit).first()
    if pit_copia and pode_visualizar_nao_homologados:
        pit_dados_basicos = pit_copia
    else:
        pit_dados_basicos = pit

    trabalho_presencial_horarios_agrupado_por_semana = None
    if pode_visualizar_nao_homologados:
        trabalho_presencial_horarios_agrupado_por_semana = PlanoIndividualTrabalhoPresencial.get_horarios_agrupado_por_semana(
            pit, listar_copias_se_houver=True
        )
    else:
        trabalho_presencial_horarios_agrupado_por_semana = PlanoIndividualTrabalhoPresencial.get_horarios_agrupado_por_semana(
            pit, apenas_homologados=True
        )

    atendimento_teletrabalho_horarios_agrupado_por_semana = None
    if pode_visualizar_nao_homologados:
        atendimento_teletrabalho_horarios_agrupado_por_semana = PlanoIndividualTrabalhoAtendimento.get_horarios_agrupado_por_semana(
            pit, listar_copias_se_houver=True
        )
    else:
        atendimento_teletrabalho_horarios_agrupado_por_semana = PlanoIndividualTrabalhoAtendimento.get_horarios_agrupado_por_semana(
            pit, apenas_homologados=False
        )

    entregas_pit = pit.get_entregas_pit()
    if pode_visualizar_nao_homologados:
        entregas_pit = pit.get_entregas_para_analise_aprovacao_homologacao(entregas_pit=entregas_pit)
    else:
        entregas_pit = entregas_pit.filter(homologado=True)
    existe_entrega_que_pode_ser_removida_no_pit = PlanoIndividualTrabalho.existe_entrega_que_pode_ser_removida_no_pit(request.user, entregas_pit)

    # Agrupando as entregas de PIT pela entrega do PES
    entregas_pes_pit = []
    entregas_pit_sem_pes = []
    if entregas_pit:
        pess_entregas_pit = PlanoEntregasSetorialEntregas.objects.filter(id__in=entregas_pit.values('entrega_pes_id')).order_by(
            'pes__setor', 'titulo'
        )
        for pes_entrega in pess_entregas_pit:
            dados = {}
            dados['pes_entrega'] = pes_entrega
            dados['pit_entregas'] = entregas_pit.filter(entrega_pes=pes_entrega).order_by(
                'entrega_pes__pes__setor__sigla', 'entrega_pes__titulo', 'titulo'
            )
            entregas_pes_pit.append(dados)
        entregas_pit_sem_pes = entregas_pit.filter(entrega_pes__isnull=True).order_by(
            'entrega_pes__pes__setor__sigla', 'entrega_pes__titulo', 'titulo'
        )

    solicitacoes_aprovacao_homologacao_pit = pit.get_solicitacoes_aprovacao_homologacao(pit_rit=PitSolicitacaoAnalise.PIT).order_by('-id')

    pode_editar = pit.pode_editar(request.user)
    eu_mesmo_posso_editar = True
    if eu_mesmo and not pode_editar and not pit.pit_estah_homologado():
        eu_mesmo_posso_editar = False
    pode_cancelar_edicao_dados_basicos = pit.pode_cancelar_edicao_dados_basicos(request.user)
    pode_cancelar_pit = pit.pode_cancelar(request.user)
    pode_editar_dados_basicos = pit.pode_editar_dados_basicos(request.user)
    pode_cadastrar_trabalho_presencial = pit.pode_cadastrar_trabalho_presencial(request.user)
    pode_cadastrar_atendimento_teletrabalho = pit.pode_cadastrar_atendimento_teletrabalho(request.user)
    pode_cadastrar_entrega = pit.pode_cadastrar_entrega(request.user)
    pode_cancelar_em_lote_edicao_atendimento_teletrabalho = pit.pode_cancelar_em_lote_edicao_atendimento_teletrabalho(request.user)
    pode_cancelar_em_lote_edicao_trabalho_presencial = pit.pode_cancelar_em_lote_edicao_trabalho_presencial(request.user)
    pode_solicitar_aprovacao_homologacao_pit, erros_pode_solicitar_aprovacao_homologacao_pit = pit.pode_solicitar_aprovacao_homologacao_pit(
        request.user, retornar_lista_erros=True
    )
    pode_aprovar_aprovar_pit = pit.pode_aprovar_pit(request.user)
    pode_receber_copia = pit.pode_receber_copia(request.user)

    se_pit_ja_foi_homologado_ao_menos_uma_vez = pit.se_pit_ja_foi_homologado_ao_menos_uma_vez()

    justificativa_observacao_solicitacao = None
    if pode_aprovar_aprovar_pit or pode_homologar_pit:
        r = RegistroAcaoPlanoIndividualTrabalho.objects.filter(
            pit=pit, tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_SERVIDOR_SOLICITOU_APROVACAO_HOMOLOGACAO
        ).first()
        if r.observacao:
            justificativa_observacao_solicitacao = r.observacao

    dados_na_base_api_pgd2 = False
    if modo == 'consultar_api':
        api_pgd_v2 = get_api_pgd2_v2()
        if api_pgd_v2:
            api_pgd_v2.set_token()
            api_pgd_v2.set_header()
            response = api_pgd_v2.get_manualmente_pit(pit)
            if response.ok:
                dados_na_base_api_pgd2 = True

    pendencia_geral_pgd = None
    if eu_mesmo or pode_homologar_pit2:
        pit_atual = PlanoIndividualTrabalho.get_pit_na_data(pit.adesao.servidor, get_datetime_now().date(), permite_pit_nao_homologado=True)
        if pit == pit_atual:
            pit_teste = pit
            if pit_copia:
                pit_teste.regime_execucacao = pit_copia.regime_execucacao
                pit_teste.percentual_teletrabalho = pit_copia.percentual_teletrabalho
            if pit_teste.regime_execucacao:
                pendencia_geral_pgd = get_pendencia_geral_servidor_pgd(
                    pit.adesao.servidor, pit_especifico=pit_teste, msgs_para_chefe=pode_homologar_pit2
                )

    erro_habilitacao_setor = None
    setores_envolvidos_nao_habilitado = pit.get_setores_envolvidos_nao_habilitado()
    if setores_envolvidos_nao_habilitado:
        siglas_setores = ', '.join([s.sigla for s in setores_envolvidos_nao_habilitado])
        erro_habilitacao_setor = get_msg_plural_nenhum_setor_habilitado(sigla_setores=siglas_setores)

    # APENAS para a super usuário
    # - se pes atual ou setor forem diferentes do atual avisa em tela e deixa recalcular
    msg_erro_setor_pes = None
    if request.user.is_superuser:
        msg_erro_setor_pes = pit.get_setor_e_pes_que_deveria_ser_o_atual()

    pode_calcular_pit = pit.pode_calcular_pit()
    pode_recalcular_setor_pes_pit = request.user.is_superuser or (pode_calcular_pit and eu_mesmo)

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def cancelar_pit(request, pit_id):
    """Cancela um PIT (irreversível, exige justificativa + senha).

    Marca como `CANCELADO`, zera o estado de RIT, desfaz a distribuição de
    horas e — se o PIT já foi homologado pelo menos uma vez — agenda envio
    pela API para refletir o cancelamento externamente.
    """
    pit = get_object_or_404(PlanoIndividualTrabalho, pk=pit_id)
    if not pit.pode_cancelar(request.user):
        raise PermissionDenied

    title = f'Cancelar {pit.get_verbose_pit_rit()}'
    url = reverse('servidor_pgd_pgd2')

    form = JustificativaComSenhaIrreversivelForm(request.POST or None, request=request)
    if form.is_valid():
        pit.situacao = PlanoIndividualTrabalho.CANCELADO
        pit.rit_em_execucao = False
        pit.situacao_rit = None
        pit.save()

        pit.desfazer_distribuicao_horas()

        if pit.se_pit_ja_foi_homologado_ao_menos_uma_vez():
            pit.marcar_para_enviar_pela_api()

        justificativa = form.cleaned_data.get('justificativa')
        ra_obs = f'O "{pit}" foi cancelado mediante a justificativa "{justificativa}"'
        RegistroAcaoPlanoIndividualTrabalho.registrar(request=request, tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_CANCELADO, pit=pit, obs=ra_obs)

        return httprr(url, 'O PIT foi cancelado com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def recalcular_setor_pes_pit(request, pit_id):
    # Pode ser acessada pelo servidor dono do PIT por superuser
    # Essa view só recalcula (para casos de mudanca de setor durante o ciclo do PIT, por exemplo)
    # Não resolve caso de mudança retroativa de setor, por exemplo. Observe "pgd2_arruma_pits_sem_setor_pes" para o seu caso/dados

    pit = get_object_or_404(PlanoIndividualTrabalho, pk=pit_id)
    eh_meu_pit = pit.adesao.servidor == request.user.get_relacionamento()
    pode_calcular_pit = pit.pode_calcular_pit()

    if request.user.is_superuser or (pode_calcular_pit and eh_meu_pit):
        pit.calcular_pit_setores_envolvidos()
        pit.marcar_para_enviar_pela_api()
    else:
        raise PermissionDenied

    url = f'{reverse("visualizar_pit_pgd2", args=[pit_id])}'
    return httprr(url, 'Os setores envolvidos no PIT foram atualizados com sucesso.')


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def editar_dados_basicos_pit(request, pit_id):
    """Edita os dados básicos do PIT (datas, regime, observações).

    Atualizações ficam disponíveis somente enquanto o PIT permite edição
    (vide `pit.pode_editar_dados_basicos`).
    """
    pit = get_object_or_404(PlanoIndividualTrabalho, pk=pit_id)
    if not pit.pode_editar_dados_basicos(request.user):
        raise PermissionDenied

    title = f'Editar Dados Básicos - {pit}'
    url = f'{reverse("visualizar_pit_pgd2", args=[pit_id])}?tab=dadosbasicostab'

    form = None
    pit_copia = PlanoIndividualTrabalhoCopia.objects.filter(original=pit).first()
    if pit.se_pit_ja_foi_homologado_ao_menos_uma_vez() and pit_copia:
        form = EditarDadosBasicosPitCopiaForm(request.POST or None, instance=pit_copia, pit=pit)
    else:
        form = EditarDadosBasicosPitForm(request.POST or None, instance=pit)

    if form.is_valid():
        # Se tiver homologado cria uma copia pra manter o original intacto
        if pit.se_pit_ja_foi_homologado_ao_menos_uma_vez():
            if not pit_copia:
                pit_copia = PlanoIndividualTrabalhoCopia()
                pit_copia.data_inicio = form.cleaned_data.get('data_inicio')
                pit_copia.regime_execucacao = form.cleaned_data.get('regime_execucacao')
                pit_copia.percentual_teletrabalho = form.cleaned_data.get('percentual_teletrabalho')
                pit_copia.original = pit
                pit_copia.save()
            else:
                obj = form.save()
        else:
            obj = form.save()

        RegistroAcaoPlanoIndividualTrabalho.registrar(
            request=request, tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_CADASTROU_DADOS_BASICOS, pit=pit, obs=''
        )

        return httprr(url, 'Os dados básicos do PIT foram atualizados com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def cancelar_edicao_dados_basicos_pit(request, pit_id):
    pit = get_object_or_404(PlanoIndividualTrabalho, pk=pit_id)
    if not pit.pode_cancelar_edicao_dados_basicos(request.user):
        raise PermissionDenied

    PlanoIndividualTrabalhoCopia.objects.filter(original=pit).delete()

    url = f'{reverse("visualizar_pit_pgd2", args=[pit_id])}?tab=dadosbasicostab'
    return httprr(url, 'Edição cancelada com sucesso.')


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def cadastrar_trabalho_presencial_pit(request, pit_id):
    pes = get_object_or_404(PlanoIndividualTrabalho, pk=pit_id)
    if not pes.pode_cadastrar_trabalho_presencial(request.user):
        raise PermissionDenied

    title = f'Cadastrar Cronograma de Trabalho Presencial - {pes}'
    url = f'{reverse("visualizar_pit_pgd2", args=[pit_id])}?tab=trabalhopresencial'

    form = PlanoIndividualTrabalhoPresencialCadastrarForm(request.POST or None, pes=pes)
    if form.is_valid():
        form.save()

        RegistroAcaoPlanoIndividualTrabalho.registrar(
            request=request, tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_CADASTROU_CRONOGRAMA_TRABALHO_PRESENCIAL, pit=pes, obs=''
        )

        return httprr(url, 'O cronograma de trabalho presencial foi cadastrado com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def editar_trabalho_presencial_pit(request, pit_tp_id):
    pes_hfs = get_object_or_404(PlanoIndividualTrabalhoPresencial, pk=pit_tp_id)
    pes = pes_hfs.pit
    if not pes.pode_editar_trabalho_presencial(request.user):
        raise PermissionDenied

    # Se partir de um original e este original tiver uma copia, então redireciona para alterar a copia
    if pes_hfs.homologado and not pes_hfs.original:
        copia = PlanoIndividualTrabalhoPresencial.objects.filter(original__id=pes_hfs.id).first()
        if copia:
            pes_hfs = copia

    title = f'Editar Cronograma de Trabalho Presencial - {pes}'
    url = f'{reverse("visualizar_pit_pgd2", args=[pes.id])}?tab=trabalhopresencial'

    horarios_agrupado_por_semana = None
    if pes_hfs.recorrencia:
        horarios_agrupado_por_semana = PlanoIndividualTrabalhoPresencial.get_horarios_agrupado_por_semana(pes, pes_hfs.recorrencia)

    # Historico: DE
    # ----------------------
    de_data = pes_hfs.data
    de_hora_inicio = pes_hfs.hora_inicio
    de_hora_final = pes_hfs.hora_inicio

    form = PlanoIndividualTrabalhoPresencialEditarForm(request.POST or None, pes=pes, instance=pes_hfs)
    if form.is_valid():
        form.save()

        editou_recorrencias = form.cleaned_data.get('tipo_edicao') != 'este'

        # Historico: PARA
        # ----------------------
        para_hora_inicio = form.cleaned_data.get('hora_inicio')
        para_hora_final = form.cleaned_data.get('hora_final')

        # --------------------------------------
        # Histórico: montando DE -> PARA
        # --------------------------------------
        dados_de_para = None
        try:
            dados_de = {}
            dados_para = {}
            if de_hora_inicio != para_hora_inicio:
                dados_de[get_vbn_field(PlanoIndividualTrabalhoPresencial, 'hora_inicio')] = str(de_hora_inicio)
                dados_para[get_vbn_field(PlanoIndividualTrabalhoPresencial, 'hora_inicio')] = str(para_hora_inicio)
            if de_hora_final != para_hora_final:
                dados_de[get_vbn_field(PlanoIndividualTrabalhoPresencial, 'hora_final')] = str(de_hora_final)
                dados_para[get_vbn_field(PlanoIndividualTrabalhoPresencial, 'hora_final')] = str(para_hora_final)
            dados_de_para = {'de': dados_de, 'para': dados_para}
        except Exception:
            pass
        # --------------------------------------

        ra_obs = f'Editou "{pes_hfs}"'
        if editou_recorrencias:
            ra_obs = f'Editou "{pes_hfs}" e suas recorrências'
        RegistroAcaoPlanoIndividualTrabalho.registrar(
            request=request,
            tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_CADASTROU_CRONOGRAMA_TRABALHO_PRESENCIAL,
            pit=pes,
            obs=ra_obs,
            dados_de_para=dados_de_para,
        )

        return httprr(url, 'O cronograma de trabalho presencial foi atualizado com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def cancelar_edicao_trabalho_presencial_pit(request, pit_ent_id):
    ent = get_object_or_404(PlanoIndividualTrabalhoPresencial, pk=pit_ent_id)

    if not ent.pode_cancelar_edicao_atendimento(request.user):
        raise PermissionDenied

    pit = ent.pit

    url = f'{reverse("visualizar_pit_pgd2", args=[pit.id])}?tab=trabalhopresencial'

    ent_original_id = ent.original.id
    PlanoIndividualTrabalhoPresencial.objects.filter(original_id=ent.original.id).delete()

    copia = PlanoIndividualTrabalhoPresencial.objects.get(id=ent_original_id)
    copia.id = None
    copia.homologado = False
    copia.alterado = False
    copia.original = PlanoIndividualTrabalhoPresencial.objects.get(id=ent_original_id)
    copia.save()

    return httprr(url, 'Edição cancelada com sucesso.')


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def cancelar_em_lote_edicao_trabalho_presencial_pit(request, pit_id):
    pit = get_object_or_404(PlanoIndividualTrabalho, pk=pit_id)

    if not pit.pode_cancelar_em_lote_edicao_trabalho_presencial(request.user):
        raise PermissionDenied

    url = f'{reverse("visualizar_pit_pgd2", args=[pit.id])}?tab=trabalhopresencial'

    PlanoIndividualTrabalhoPresencial.objects.filter(pit=pit, original__isnull=False).delete()

    datas_criar_copia = PlanoIndividualTrabalhoPresencial.objects.filter(pit=pit, homologado=True)
    for original in datas_criar_copia:
        if not PlanoIndividualTrabalhoPresencial.objects.filter(original__id=original.id).exists():
            copia = original
            entrega_original = PlanoIndividualTrabalhoPresencial.objects.get(id=original.id)
            copia.id = None
            copia.homologado = False
            copia.original = entrega_original
            copia.save()

    return httprr(url, 'As edições dos horários de trabalho presencial foram canceladas.')


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def remover_trabalho_presencial_pit(request, pit_id):
    pes = get_object_or_404(PlanoIndividualTrabalho, pk=pit_id)
    if not pes.pode_remover_trabalho_presencial(request.user):
        raise PermissionDenied

    title = f'Remover Cronograma de Trabalho Presencial - {pes}'
    url = f'{reverse("visualizar_pit_pgd2", args=[pes.id])}?tab=trabalhopresencial'

    hfs_selecionados = request.GET.getlist('checks[]')
    if 'remover_htp' in request.GET and hfs_selecionados:
        form = ConfirmacaoComSenhaForm(request.POST or None, request=request)
        if form.is_valid():
            RegistroAcaoPlanoIndividualTrabalho.registrar(
                request=request, tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_CADASTROU_CRONOGRAMA_TRABALHO_PRESENCIAL, pit=pes, obs='Removeu'
            )

            PlanoIndividualTrabalhoPresencial.objects.filter(pit=pes, id__in=hfs_selecionados).delete()

            return httprr(url, 'Removido com sucesso.')
    else:
        return httprr(url, 'Selecione ao menos um horário para remover.', tag='error')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def cadastrar_atendimento_teletrabalho_pit(request, pit_id):
    pes = get_object_or_404(PlanoIndividualTrabalho, pk=pit_id)
    if not pes.pode_cadastrar_atendimento_teletrabalho(request.user):
        raise PermissionDenied

    title = f'Cadastrar Cronograma de Atendimento em Teletrabalho - {pes}'
    url = f'{reverse("visualizar_pit_pgd2", args=[pit_id])}?tab=horaatendimento'

    form = PlanoIndividualTrabalhoAtendimentoTeletrabalhoCadastrarForm(request.POST or None, pes=pes)
    if form.is_valid():
        form.save()

        RegistroAcaoPlanoIndividualTrabalho.registrar(
            request=request, tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_CADASTROU_CRONOGRAMA_ATENDIMENTO_TELETRABALHO, pit=pes, obs=''
        )

        return httprr(url, 'O cronograma de atendimento em teletrabalho foi cadastrado com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def editar_atendimento_teletrabalho_pit(request, pit_at_id):
    pit_hfs = get_object_or_404(PlanoIndividualTrabalhoAtendimento, pk=pit_at_id)
    pit = pit_hfs.pit
    if not pit.pode_editar_atendimento_teletrabalho(request.user):
        raise PermissionDenied

    # Se partir de um original e este original tiver uma copia, então redireciona para alterar a copia
    if pit_hfs.homologado and not pit_hfs.original:
        copia = PlanoIndividualTrabalhoAtendimento.objects.filter(original__id=pit_hfs.id).first()
        if copia:
            pit_hfs = copia

    title = f'Editar Cronograma de Atendimento em Teletrabalho - {pit}'
    url = f'{reverse("visualizar_pit_pgd2", args=[pit.id])}?tab=horaatendimento'

    horarios_agrupado_por_semana = None
    if pit_hfs.recorrencia:
        horarios_agrupado_por_semana = PlanoIndividualTrabalhoAtendimento.get_horarios_agrupado_por_semana(
            pit, recorrencia=pit_hfs.recorrencia, listar_copias_se_houver=True
        )

    # Historico: DE
    # ----------------------
    de_data = pit_hfs.data
    de_hora_inicio = pit_hfs.hora_inicio
    de_hora_final = pit_hfs.hora_inicio

    form = PlanoIndividualTrabalhoAtendimentoTeletrabalhoEditarForm(request.POST or None, pit=pit, instance=pit_hfs)
    if form.is_valid():
        form.save()

        editou_recorrencias = form.cleaned_data.get('tipo_edicao') != 'este'

        # Historico: PARA
        # ----------------------
        para_hora_inicio = form.cleaned_data.get('hora_inicio')
        para_hora_final = form.cleaned_data.get('hora_final')

        # --------------------------------------
        # Histórico: montando DE -> PARA
        # --------------------------------------
        dados_de_para = None
        try:
            dados_de = {}
            dados_para = {}
            if de_hora_inicio != para_hora_inicio:
                dados_de[get_vbn_field(PlanoIndividualTrabalhoAtendimento, 'hora_inicio')] = str(de_hora_inicio)
                dados_para[get_vbn_field(PlanoIndividualTrabalhoAtendimento, 'hora_inicio')] = str(para_hora_inicio)
            if de_hora_final != para_hora_final:
                dados_de[get_vbn_field(PlanoIndividualTrabalhoAtendimento, 'hora_final')] = str(de_hora_final)
                dados_para[get_vbn_field(PlanoIndividualTrabalhoAtendimento, 'hora_final')] = str(para_hora_final)
            dados_de_para = {'de': dados_de, 'para': dados_para}
        except Exception:
            pass
        # --------------------------------------

        ra_obs = f'Editou "{pit_hfs}"'
        if editou_recorrencias:
            ra_obs = f'Editou "{pit_hfs}" e suas recorrências'
        RegistroAcaoPlanoIndividualTrabalho.registrar(
            request=request,
            tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_CADASTROU_CRONOGRAMA_ATENDIMENTO_TELETRABALHO,
            pit=pit,
            obs=ra_obs,
            dados_de_para=dados_de_para,
        )

        return httprr(url, 'O cronograma de atendimento em teletrabalho foi atualizado com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def cancelar_edicao_atendimento_teletrabalho_pit(request, pit_ent_id):
    ent = get_object_or_404(PlanoIndividualTrabalhoAtendimento, pk=pit_ent_id)

    if not ent.pode_cancelar_edicao_atendimento(request.user):
        raise PermissionDenied

    pit = ent.pit

    url = f'{reverse("visualizar_pit_pgd2", args=[pit.id])}?tab=horaatendimento'

    ent_original_id = ent.original.id
    PlanoIndividualTrabalhoAtendimento.objects.filter(original_id=ent.original.id).delete()

    copia = PlanoIndividualTrabalhoAtendimento.objects.get(id=ent_original_id)
    copia.id = None
    copia.homologado = False
    copia.alterado = False
    copia.original = PlanoIndividualTrabalhoAtendimento.objects.get(id=ent_original_id)
    copia.save()

    return httprr(url, 'Edição cancelada com sucesso.')


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def cancelar_em_lote_edicao_atendimento_teletrabalho_pit(request, pit_id):
    pit = get_object_or_404(PlanoIndividualTrabalho, pk=pit_id)

    if not pit.pode_cancelar_em_lote_edicao_atendimento_teletrabalho(request.user):
        raise PermissionDenied

    url = f'{reverse("visualizar_pit_pgd2", args=[pit.id])}?tab=horaatendimento'

    PlanoIndividualTrabalhoAtendimento.objects.filter(pit=pit, original__isnull=False).delete()

    datas_criar_copia = PlanoIndividualTrabalhoAtendimento.objects.filter(pit=pit, homologado=True)
    for original in datas_criar_copia:
        if not PlanoIndividualTrabalhoAtendimento.objects.filter(original__id=original.id).exists():
            copia = original
            entrega_original = PlanoIndividualTrabalhoAtendimento.objects.get(id=original.id)
            copia.id = None
            copia.homologado = False
            copia.original = entrega_original
            copia.save()

    return httprr(url, 'As edições dos horários de atendimento em teletrabalho foram canceladas.')


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def remover_atendimento_teletrabalho_pit(request, pit_id):
    pes = get_object_or_404(PlanoIndividualTrabalho, pk=pit_id)
    if not pes.pode_remover_atendimento_teletrabalho(request.user):
        raise PermissionDenied

    title = f'Remover Cronograma de Atendimento em Teletrabalho - {pes}'
    url = f'{reverse("visualizar_pit_pgd2", args=[pes.id])}?tab=horaatendimento'

    hfs_selecionados = request.GET.getlist('checks[]')
    if 'remover_hat' in request.GET and hfs_selecionados:
        form = ConfirmacaoComSenhaForm(request.POST or None, request=request)
        if form.is_valid():
            RegistroAcaoPlanoIndividualTrabalho.registrar(
                request=request, tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_CADASTROU_CRONOGRAMA_ATENDIMENTO_TELETRABALHO, pit=pes, obs='Removeu'
            )

            PlanoIndividualTrabalhoAtendimento.objects.filter(pit=pes, id__in=hfs_selecionados).delete()

            return httprr(url, 'Os horários de atendimento em teletrabalho selecionados foram removidos com sucesso.')
    else:
        return httprr(url, 'Selecione ao menos um horário para remover.', tag='error')

    return locals()


@rtr()
@permission_required('rh.eh_servidor')
def selecionar_entrega_pes_cadastrar_entrega_pit(request, pit_id):
    pit = get_object_or_404(PlanoIndividualTrabalho, pk=pit_id)
    pode_cadastrar_entrega = pit.pode_cadastrar_entrega(request.user)
    if not pode_cadastrar_entrega:
        raise PermissionDenied

    title = f'Cadastrar Entrega - {pit} - Selecionar entrega do PES'
    pit.calcular_pit()

    pess_aptos = pit.get_pess_aptos_relacionados()

    setor_pode_homologar = pit.get_setor_envolvido_apto_para_homologar()

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def cadastrar_entrega_pit(request, pit_id, entrega_pes_id=None):
    pit = get_object_or_404(PlanoIndividualTrabalho, pk=pit_id)
    if not pit.pode_cadastrar_entrega(request.user):
        raise PermissionDenied

    pit.calcular_pit()

    entrega_pes = None
    if entrega_pes_id:
        entrega_pes = get_object_or_404(PlanoEntregasSetorialEntregas, pk=entrega_pes_id)

    title = f'Cadastrar Entrega - {pit} - Informar dados da entrega'

    url = f'{reverse("visualizar_pit_pgd2", args=[pit_id])}?tab=entregas'

    form = PlanoIndividualTrabalhoEntregasCadastrarForm(request.POST or None, pit=pit)
    if form.is_valid():
        form.instance.pit = pit
        form.instance.entrega_pes = entrega_pes
        form.save()

        RegistroAcaoPlanoIndividualTrabalho.registrar(
            request=request, tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_CADASTROU_ENTREGA, pit=pit, obs='Cadastrou'
        )

        pit.calcular_pit_setores_envolvidos()

        return httprr(url, 'A entrega do PIT foi cadastrada com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def editar_entrega_pit(request, pit_ent_id):
    pit_ent = get_object_or_404(PlanoIndividualTrabalhoEntregas, pk=pit_ent_id)
    pit = pit_ent.pit
    if not pit_ent.pode_editar_entrega(request.user):
        raise PermissionDenied
    entrega_pes = pit_ent.entrega_pes

    pit.calcular_pit()

    # Se partir de um original e este original tiver uma copia, então redireciona para alterar a copia
    if pit_ent.homologado and not pit_ent.original:
        copia = PlanoIndividualTrabalhoEntregas.objects.filter(original__id=pit_ent.id).first()
        if copia:
            pit_ent = copia

    title = f'Editar Entrega - {pit_ent}'
    url = f'{reverse("visualizar_pit_pgd2", args=[pit.id])}?tab=entregas'

    # Historico: DE
    # ----------------------
    de_titulo = pit_ent.titulo
    de_descricao = pit_ent.descricao
    de_data_prazo = pit_ent.data_prazo
    de_tempo_planejado = pit_ent.tempo_planejado

    form = PlanoIndividualTrabalhoEntregasEditarForm(request.POST or None, instance=pit_ent, pit=pit)
    if form.is_valid():
        form.instance.pit = pit
        entrega = form.save(False)

        # Cria o espelho para conseguir cancelar edicao depois
        # - Se a entrega já não possui mais uma cópia ajustada da original
        # - Se a entrega do PIT já foi homologada
        # ----------------------
        if entrega.homologado:
            # Situacoes
            # - Esta esta alterando uma original (com cópia ou não)
            #   - Apaga copia
            #   - Cria copia
            #   - Joga os dados para a copia
            #   - Mantem a original intacta
            # - Esta esta alterando uma copia
            #   - Altera normal
            #   - Mantem a original intacta
            if not entrega.original:
                # Esta esta alterando uma original (com cópia ou não)
                PlanoIndividualTrabalhoEntregas.objects.filter(original__id=entrega.id).delete()
                entrega_copia = entrega
                entrega_original = PlanoIndividualTrabalhoEntregas.objects.get(id=entrega.id)
                entrega_copia.id = None
                entrega_copia.homologado = False
                entrega_copia.original = entrega_original
                entrega_copia.save()
            else:
                # Esta esta alterando uma copia
                entrega.save()
        else:
            entrega.save()

        # Historico: PARA
        # ----------------------
        para_titulo = form.cleaned_data.get('titulo')
        para_descricao = form.cleaned_data.get('descricao')
        para_data_prazo = form.cleaned_data.get('data_prazo')
        para_tempo_planejado = form.cleaned_data.get('tempo_planejado')

        # --------------------------------------
        # Histórico: montando DE -> PARA
        # --------------------------------------
        dados_de_para = None
        try:
            dados_de = {}
            dados_para = {}
            if de_titulo != para_titulo:
                dados_de[get_vbn_field(PlanoIndividualTrabalhoEntregas, 'titulo')] = str(de_titulo)
                dados_para[get_vbn_field(PlanoIndividualTrabalhoEntregas, 'titulo')] = str(para_titulo)
            if de_descricao != para_descricao:
                dados_de[get_vbn_field(PlanoIndividualTrabalhoEntregas, 'descricao')] = str(de_descricao)
                dados_para[get_vbn_field(PlanoIndividualTrabalhoEntregas, 'descricao')] = str(para_descricao)
            if de_data_prazo != para_data_prazo:
                dados_de[get_vbn_field(PlanoIndividualTrabalhoEntregas, 'data_prazo')] = str(de_data_prazo)
                dados_para[get_vbn_field(PlanoIndividualTrabalhoEntregas, 'data_prazo')] = str(para_data_prazo)
            if de_tempo_planejado != para_tempo_planejado:
                dados_de[get_vbn_field(PlanoIndividualTrabalhoEntregas, 'tempo_planejado')] = str(de_tempo_planejado)
                dados_para[get_vbn_field(PlanoIndividualTrabalhoEntregas, 'tempo_planejado')] = str(para_tempo_planejado)
            dados_de_para = {'de': dados_de, 'para': dados_para}
        except Exception:
            pass
        # --------------------------------------

        ra_obs = f'Editou "{pit_ent}"'
        RegistroAcaoPlanoIndividualTrabalho.registrar(
            request=request, tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_CADASTROU_ENTREGA, pit=pit, obs=ra_obs, dados_de_para=dados_de_para
        )

        return httprr(url, 'Dados alterados com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def remover_entrega_pit(request, pit_id):
    pit = get_object_or_404(PlanoIndividualTrabalho, pk=pit_id)
    if not pit.pode_cadastrar_entrega(request.user):
        raise PermissionDenied

    title = f'Remover Entrega - {pit}'
    url = f'{reverse("visualizar_pit_pgd2", args=[pit.id])}?tab=entregas'

    selecionados = request.GET.getlist('checks[]')
    if 'remover_entregas_pit' in request.GET and selecionados:
        form = ConfirmacaoComSenhaForm(request.POST or None, request=request)
        if form.is_valid():
            entregas = PlanoIndividualTrabalhoEntregas.objects.filter(pit=pit, id__in=selecionados)

            nao_removidas = []
            teve_remocao = False
            for entrega in entregas:
                if entrega.pode_remover_entrega():
                    entrega.delete()
                    teve_remocao = True
                else:
                    nao_removidas.append(f'"{entrega.titulo!s}"')
            if nao_removidas:
                messages.error(
                    request,
                    f'As seguintes entregas não foram removidas pois existem entregas de {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2} relacionadas: {mark_safe("</br>".join(nao_removidas))}',
                )

            if teve_remocao:
                RegistroAcaoPlanoIndividualTrabalho.registrar(
                    request=request, tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_CADASTROU_ENTREGA, pit=pit, obs='Removeu entrega(s)'
                )

            pit.calcular_pit()
            pit.calcular_pit_setores_envolvidos()

            return httprr(url, 'Removida(s) com sucesso.')
    else:
        return httprr(url, 'Nenhuma entrega selecionada.', tag='error')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def cancelar_entrega_pit(request, pit_ent_id):
    ent = get_object_or_404(PlanoIndividualTrabalhoEntregas, pk=pit_ent_id)

    if not ent.pode_cancelar_entrega(request.user):
        raise PermissionDenied

    pit = ent.pit

    url = f'{reverse("visualizar_pit_pgd2", args=[pit.id])}?tab=entregas'

    # Cria o espelho para conseguir cancelar edicao depois
    # ----------------------
    PlanoIndividualTrabalhoEntregas.objects.filter(original__id=ent.id).delete()
    entrega_copia = ent
    entrega_original = PlanoIndividualTrabalhoEntregas.objects.get(id=ent.id)
    entrega_copia.id = None
    entrega_copia.homologado = False
    entrega_copia.original = entrega_original
    entrega_copia.cancelado = True
    entrega_copia.save()

    return httprr(url, 'Entrega cancelada com sucesso.')


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def descancelar_entrega_pit(request, pit_ent_id):
    ent = get_object_or_404(PlanoIndividualTrabalhoEntregas, pk=pit_ent_id)

    if not ent.pode_descancelar_entrega(request.user):
        raise PermissionDenied

    pit = ent.pit

    url = f'{reverse("visualizar_pit_pgd2", args=[pit.id])}?tab=entregas'

    if ent.eh_copia():
        ent.delete()
    else:
        # Cria o espelho
        # ----------------------
        if ent.homologado and not ent.original:
            # Esta esta alterando uma original (com cópia ou não)
            PlanoIndividualTrabalhoEntregas.objects.filter(original__id=ent.id).delete()
            entrega_copia = ent
            entrega_original = PlanoIndividualTrabalhoEntregas.objects.get(id=ent.id)
            entrega_copia.id = None
            entrega_copia.homologado = False
            entrega_copia.original = entrega_original
            entrega_copia.cancelado = False
            entrega_copia.save()

    return httprr(url, 'Entrega descancelada com sucesso.')


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def cancelar_edicao_entrega_pit(request, pit_ent_id):
    ent = get_object_or_404(PlanoIndividualTrabalhoEntregas, pk=pit_ent_id)

    if not ent.pode_cancelar_edicao_entrega(request.user):
        raise PermissionDenied

    pit = ent.pit

    url = f'{reverse("visualizar_pit_pgd2", args=[pit.id])}?tab=entregas'

    ent.delete()

    return httprr(url, 'Edição cancelada com sucesso.')


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def solicitar_aprovacao_homologacao_pit(request, pit_id):
    pit = get_object_or_404(PlanoIndividualTrabalho, pk=pit_id)
    url = reverse('visualizar_pit_pgd2', args=[pit.id])

    pode_solicitar_aprovacao_homologacao_pit, erros = pit.pode_solicitar_aprovacao_homologacao_pit(request.user, retornar_lista_erros=True)
    if not pode_solicitar_aprovacao_homologacao_pit:
        messages.error(request, mark_safe('</br>'.join(erros)))
        return httprr(url)

    title = f'Solicitar Aprovação/Homologação - {pit}'

    form = JustificativaComSenhaForm(request.POST or None, request=request)
    if form.is_valid():
        # Calcula o PIT
        pit.calcular_pit()

        def eh_adesao_migrada_do_pgd1_ifrn():
            from pgd import models as pgd1

            pgd1_adesao_pgd = pgd1.SolicitacaoAdesaoServidor.get_adesoes_vigentes().filter(servidor=pit.adesao.servidor).first()
            if pgd1_adesao_pgd:
                return pgd1_adesao_pgd.get_data_inicio_adesao().date() == pit.adesao.data_inicio
            return False

        # Regra do ponto
        if pit.deve_verificar_ponto() and not eh_adesao_migrada_do_pgd1_ifrn():
            lista_pendencias_ponto = get_pendencias_ponto_servidor(pit)
            if lista_pendencias_ponto:
                messages.error(request, mark_safe('</br>'.join(lista_pendencias_ponto)))
                return httprr(url)
            pit.data_verificacao_ponto = get_datetime_now()
            pit.save()

        # Verifica se o prazo das entregas extrapola o periodo do PIT
        data_ini = pit.data_inicio
        data_fim = pit.data_fim
        entregas = pit.get_entregas_para_analise_aprovacao_homologacao().filter(data_prazo__isnull=False)
        tem_prazo_fora_periodo = False
        for ent in entregas:
            if ent.data_prazo and not (data_ini <= ent.data_prazo <= data_fim):
                tem_prazo_fora_periodo = True
                break
        if tem_prazo_fora_periodo:
            return httprr(
                url,
                'Impossível Solicitar Aprovação/Homologação se uma das entregas estiver com prazo em desacordo com o período do PIT.',
                tag='error',
            )

        # Gera a solicitação e ajusta o PIT
        pit.gerar_solicitacao_aprovacao_homologacao_pit_rit(objeto_parecer=PitSolicitacaoAnalise.PIT)

        justificativa = form.cleaned_data.get('justificativa')
        ra_obs = f'Foi solicitado aprovação/homologação do "{pit}"'
        if justificativa:
            ra_obs = f'Foi solicitado aprovação/homologação do "{pit}" mediante a justificativa "{justificativa}"'
        RegistroAcaoPlanoIndividualTrabalho.registrar(
            request=request, tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_SERVIDOR_SOLICITOU_APROVACAO_HOMOLOGACAO, pit=pit, obs=ra_obs
        )

        return httprr(url, 'Aprovação/homologação solicitada com sucesso.')

    return locals()


@rtr()
@permission_required('rh.chefe')
def listar_pits_chefe(request):
    if not PlanoIndividualTrabalho.pode_visualizar_lista(request.user):
        raise PermissionDenied

    title = nomenclatura.planos_individuais_de_trabalho_pgd2

    # Se fui chefe no periodo ou Se sou chefe hoje
    setores = setores_que_sou_fui_chefe(request.user.get_relacionamento())

    ids_pits = PitSetores.objects.filter(setor__in=setores).values_list('pit_id', flat=True)
    lista_pits = PlanoIndividualTrabalho.objects.filter(id__in=ids_pits).order_by(
        'adesao__servidor__pessoa_fisica__nome', 'periodo_pit_rit__data_inicio'
    )

    form = BuscarPitsChefeForm(request.GET or None, request=request, setores=setores)
    buscou = False
    if form.is_valid():
        buscar_str = form.cleaned_data.get('buscar_str')
        setor_filtro = form.cleaned_data.get('setor')
        situacao = form.cleaned_data.get('situacao')
        periodo_pit_rit = form.cleaned_data.get('periodo_pit_rit')
        buscou = buscar_str or setor_filtro or situacao or periodo_pit_rit

        if buscou:
            # Periodo
            if periodo_pit_rit:
                lista_pits = lista_pits.filter(periodo_pit_rit=periodo_pit_rit)

            if setor_filtro:
                # Essa busca pode resultar em PITs com ou sem entregas.
                # - Em consequência disso podemos ter ou não setores vinculados (PitSetores).
                # - Os setores vinculados são gerados com base nas entregas
                # Então usaremos um OU para buscar no setor do servidor OU nos setores relacionados
                ids_pits = PitSetores.objects.filter(setor=setor_filtro).values_list('setor_id', flat=True)
                lista_pits = lista_pits.filter(Q(id__in=ids_pits) | Q(adesao__servidor__setor=setor_filtro))

            if situacao:
                lista_pits = lista_pits.filter(situacao=situacao)

            if buscar_str:
                lista_pits = lista_pits.filter(
                    Q(adesao__servidor__pessoa_fisica__nome__icontains=buscar_str) | Q(adesao__servidor__matricula__icontains=buscar_str)
                )

    return locals()


@rtr()
@permission_required('rh.chefe')
def listar_pits_chefe_deve_aprova_homologa(request):
    if not PlanoIndividualTrabalho.pode_visualizar_lista(request.user):
        raise PermissionDenied

    title = f'{nomenclatura.planos_individuais_de_trabalho_pgd2} para Aprovar/Homologar (chefe imediato)'

    lista_pits_aprova, lista_pits_homologacao = PlanoIndividualTrabalho.get_pits_pendendentes_avaliacao_chefe_direto(request.user)

    querys = []

    form = BuscarPitsChefeFormSimples2(request.GET or None, request=request)
    if form.is_valid():
        buscar_str = form.cleaned_data.get('buscar_str')
        periodo_pit_rit = form.cleaned_data.get('periodo_pit_rit')
        if buscar_str or periodo_pit_rit:
            if periodo_pit_rit:
                querys.append(Q(periodo_pit_rit=periodo_pit_rit))
            if buscar_str:
                querys.append(Q(adesao__servidor__pessoa_fisica__nome__icontains=buscar_str) | Q(adesao__servidor__matricula__icontains=buscar_str))
            lista_pits_aprova = lista_pits_aprova.filter(reduce(operator.and_, querys))
            lista_pits_homologacao = lista_pits_homologacao.filter(reduce(operator.and_, querys))

    return locals()


@rtr()
@permission_required('rh.chefe')
def listar_pits_chefe_pode_aprova_homologa(request):
    if not PlanoIndividualTrabalho.pode_visualizar_lista(request.user):
        raise PermissionDenied

    title = f'{nomenclatura.planos_individuais_de_trabalho_pgd2} para Aprovar/Homologar (outros)'

    lista_pits_aprova, lista_pits_homologacao = PlanoIndividualTrabalho.get_pits_pendendentes_avaliacao_chefe_outros(request.user)

    querys = []

    form = BuscarPitsChefeFormSimples2(request.GET or None, request=request)
    if form.is_valid():
        buscar_str = form.cleaned_data.get('buscar_str')
        periodo_pit_rit = form.cleaned_data.get('periodo_pit_rit')
        if buscar_str or periodo_pit_rit:
            if periodo_pit_rit:
                querys.append(Q(periodo_pit_rit=periodo_pit_rit))
            if buscar_str:
                querys.append(Q(adesao__servidor__pessoa_fisica__nome__icontains=buscar_str) | Q(adesao__servidor__matricula__icontains=buscar_str))
            lista_pits_aprova = lista_pits_aprova.filter(reduce(operator.and_, querys))
            lista_pits_homologacao = lista_pits_homologacao.filter(reduce(operator.and_, querys))

    return locals()


@rtr()
@permission_required('rh.chefe')
def listar_pits_chefe_deve_pode_aprova_homologa(request):
    if not PlanoIndividualTrabalho.pode_visualizar_lista(request.user):
        raise PermissionDenied

    title = f'{nomenclatura.planos_individuais_de_trabalho_pgd2} para Aprovar/Homologar'

    # Deve Aprovar/Homologar
    lista_pits_aprova_deve, lista_pits_homologacao_deve = PlanoIndividualTrabalho.get_pits_pendendentes_avaliacao_chefe_direto(request.user)
    lista_pits_homologacao_deve = lista_pits_homologacao_deve.annotate(parecer=Value('Homologação', output_field=CharField()))
    lista_pits_aprova_deve = lista_pits_aprova_deve.annotate(parecer=Value('Aprovação', output_field=CharField()))
    lista_pits_deve = []

    # Pode Aprovar/Homologar
    lista_pits_aprova_pode, lista_pits_homologacao_pode = PlanoIndividualTrabalho.get_pits_pendendentes_avaliacao_chefe_outros(request.user)
    lista_pits_homologacao_pode = lista_pits_homologacao_pode.annotate(parecer=Value('Homologação', output_field=CharField()))
    lista_pits_aprova_pode = lista_pits_aprova_pode.annotate(parecer=Value('Aprovação', output_field=CharField()))
    lista_pits_pode = []

    # Retira do PODE os DEVE
    ids_deve = []
    ids_deve.extend(lista_pits_aprova_deve.values_list('id', flat=True))
    ids_deve.extend(lista_pits_homologacao_deve.values_list('id', flat=True))
    lista_pits_aprova_pode = lista_pits_aprova_pode.exclude(id__in=ids_deve)
    lista_pits_homologacao_pode = lista_pits_homologacao_pode.exclude(id__in=ids_deve)

    form = BuscarPitsChefeFormSimples2(request.GET or None, request=request)
    if form.is_valid():
        buscar_str = form.cleaned_data.get('buscar_str')
        periodo_pit_rit = form.cleaned_data.get('periodo_pit_rit')
        if buscar_str or periodo_pit_rit:
            querys = []

            if periodo_pit_rit:
                querys.append(Q(periodo_pit_rit=periodo_pit_rit))
            if buscar_str:
                querys.append(Q(adesao__servidor__pessoa_fisica__nome__icontains=buscar_str) | Q(adesao__servidor__matricula__icontains=buscar_str))

            if querys:
                lista_pits_homologacao_deve = lista_pits_homologacao_deve.filter(reduce(operator.and_, querys))
                lista_pits_aprova_deve = lista_pits_aprova_deve.filter(reduce(operator.and_, querys))

                lista_pits_homologacao_pode = lista_pits_homologacao_pode.filter(reduce(operator.and_, querys))
                lista_pits_aprova_pode = lista_pits_aprova_pode.filter(reduce(operator.and_, querys))

    lista_pits_deve.extend(lista_pits_homologacao_deve)
    lista_pits_deve.extend(lista_pits_aprova_deve)
    lista_pits_deve = sorted(lista_pits_deve, key=lambda p: p.adesao.servidor.pessoa_fisica.nome)

    lista_pits_pode.extend(lista_pits_homologacao_pode)
    lista_pits_pode.extend(lista_pits_aprova_pode)
    lista_pits_pode = sorted(lista_pits_pode, key=lambda p: p.adesao.servidor.pessoa_fisica.nome)

    return locals()


@rtr('pgd2/templates/homologar_pit.html')
@transaction.atomic
@permission_required('rh.chefe')
def aprovar_pit(request, pit_id):
    pit = get_object_or_404(PlanoIndividualTrabalho, pk=pit_id)
    url = reverse('visualizar_pit_pgd2', args=[pit.id])

    # Calcula o PIT
    pit.calcular_pit()

    if not pit.pode_aprovar_pit(request.user):
        raise PermissionDenied

    title = f'Aprovar - {pit}'

    justificativa_observacao_solicitacao = None
    r = RegistroAcaoPlanoIndividualTrabalho.objects.filter(
        pit=pit, tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_SERVIDOR_SOLICITOU_APROVACAO_HOMOLOGACAO
    ).first()
    if r.observacao:
        justificativa_observacao_solicitacao = r.observacao

    form = JustificativaComSenhaForm(request.POST or None, request=request)
    if form.is_valid():
        pode_finalizar_aprovacao_homologacao_pit, erros_pode_finalizar_aprovacao_homologacao_pit = pit.pode_finalizar_aprovacao_homologacao_pit(
            retornar_lista_erros=True
        )
        if not pode_finalizar_aprovacao_homologacao_pit:
            return locals()

        # setores = setores_que_sou_chefe_no_periodo(pit.data_inicio, pit.data_fim, request.user.get_relacionamento())
        setores, _ = setores_e_servidores_que_sou_relacionado_como_chefe_no_periodo(request.user, pit.data_inicio, pit.data_fim)

        pit.aprovar_pit(setores, request.user.get_relacionamento())

        justificativa = form.cleaned_data.get('justificativa')
        ra_obs = f'Aprovação do "{pit}"'
        if justificativa:
            ra_obs = f'Aprovação do "{pit}" mediante a justificativa "{justificativa}"'
        RegistroAcaoPlanoIndividualTrabalho.registrar(request=request, tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_APROVOU, pit=pit, obs=ra_obs)

        return httprr(url, f'O {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} foi aprovado com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.chefe')
def reprovar_pit(request, pit_id):
    pit = get_object_or_404(PlanoIndividualTrabalho, pk=pit_id)
    url = reverse('visualizar_pit_pgd2', args=[pit.id])

    # Calcula o PIT
    pit.calcular_pit()

    if not pit.pode_aprovar_pit(request.user):
        raise PermissionDenied

    title = f'Reprovar - {pit}'

    form = JustificativaComSenhaForm(request.POST or None, request=request)
    if form.is_valid():
        # setores = setores_que_sou_chefe_no_periodo(pit.data_inicio, pit.data_fim, request.user.get_relacionamento())
        setores, _ = setores_e_servidores_que_sou_relacionado_como_chefe_no_periodo(request.user, pit.data_inicio, pit.data_fim)

        pit.reprovar_pit(setores, request.user.get_relacionamento())

        justificativa = form.cleaned_data.get('justificativa')
        ra_obs = f'Reprovação do "{pit}"'
        if justificativa:
            ra_obs = f'Reprovação do "{pit}" mediante a justificativa "{justificativa}"'
        RegistroAcaoPlanoIndividualTrabalho.registrar(request=request, tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_NAO_APROVOU, pit=pit, obs=ra_obs)

        return httprr(url, f'O {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} foi devolvido para ajustes.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.chefe')
def homologar_pit(request, pit_id):
    pit = get_object_or_404(PlanoIndividualTrabalho, pk=pit_id)
    url = reverse('visualizar_pit_pgd2', args=[pit.id])

    # Calcula o PIT
    pit.calcular_pit()

    if not pit.pode_homologar_pit(request.user):
        raise PermissionDenied

    title = f'Homologar - {pit}'

    justificativa_observacao_solicitacao = None
    r = RegistroAcaoPlanoIndividualTrabalho.objects.filter(
        pit=pit, tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_SERVIDOR_SOLICITOU_APROVACAO_HOMOLOGACAO
    ).first()
    if r.observacao:
        justificativa_observacao_solicitacao = r.observacao

    habilita_confirmacao_cronograma_presencial = PlanoIndividualTrabalhoPresencial.objects.filter(pit=pit).exists()

    form = HomologarPitForm(request.POST or None, request=request, habilita_confirmacao3=habilita_confirmacao_cronograma_presencial)
    if form.is_valid():
        pode_finalizar_aprovacao_homologacao_pit, erros_pode_finalizar_aprovacao_homologacao_pit = pit.pode_finalizar_aprovacao_homologacao_pit(
            retornar_lista_erros=True
        )
        if not pode_finalizar_aprovacao_homologacao_pit:
            return locals()

        setores, _ = setores_e_servidores_que_sou_relacionado_como_chefe_no_periodo(request.user, pit.data_inicio, pit.data_fim)

        pit.homologar_pit(setores, request.user.get_relacionamento())

        confirmacoes = f'Confirmou os seguintes dados informados no {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}: '
        confirmacoes += '"Regime individual de execução no PGD", '
        confirmacoes += '"% de Teletrabalho", '
        if habilita_confirmacao_cronograma_presencial:
            confirmacoes += '"Cronograma de Trabalho Presencial", '
        confirmacoes += '"Cronograma de Atendimento em Teletrabalho" e '
        confirmacoes += f'"Entregas informadas no {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}"'

        justificativa = form.cleaned_data.get('justificativa')
        if justificativa:
            ra_obs = f'Homologação do "{pit}" mediante a justificativa "{justificativa}". {confirmacoes}'
        else:
            ra_obs = f'Homologação do "{pit}". {confirmacoes}'

        RegistroAcaoPlanoIndividualTrabalho.registrar(request=request, tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_HOMOLOGOU, pit=pit, obs=ra_obs)

        notificar_homologacao_pit(pit)

        return httprr(url, f'O {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} foi homologado com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.chefe')
def nao_homologar_pit(request, pit_id):
    pit = get_object_or_404(PlanoIndividualTrabalho, pk=pit_id)
    url = reverse('visualizar_pit_pgd2', args=[pit.id])

    # Calcula o PIT
    pit.calcular_pit()

    if not pit.pode_homologar_pit(request.user):
        raise PermissionDenied

    title = f'Não Homologar - {pit}'

    form = JustificativaComSenhaForm(request.POST or None, request=request)
    if form.is_valid():
        # setores = setores_que_sou_chefe_no_periodo(pit.data_inicio, pit.data_fim, request.user.get_relacionamento())
        setores, _ = setores_e_servidores_que_sou_relacionado_como_chefe_no_periodo(request.user, pit.data_inicio, pit.data_fim)

        pit.nao_homologar_pit(setores, request.user.get_relacionamento())

        justificativa = form.cleaned_data.get('justificativa')
        ra_obs = f'Não Homologação do "{pit}"'
        if justificativa:
            ra_obs = f'Não Homologação do "{pit}" mediante a justificativa "{justificativa}"'
        RegistroAcaoPlanoIndividualTrabalho.registrar(
            request=request, tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_NAO_HOMOLOGOU, pit=pit, obs=ra_obs
        )

        notificar_nao_homologacao_pit(pit)

        return httprr(url, f'O {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} não foi homologado.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def copiar_pit(request, pit_id):
    pit = get_object_or_404(PlanoIndividualTrabalho, pk=pit_id)
    if not pit.pode_receber_copia(request.user):
        raise PermissionDenied

    title = f'Copiar entregas para o {pit}'
    url = reverse('visualizar_pit_pgd2', args=[pit.id])

    form = None
    form_relacionar = None
    form_relacionar_mapeamento = None
    pits_podem_ser_copiados_para_este = pit.get_pits_podem_ser_copiados_para_este(request.user)
    usando_fallback_outro_pes = False

    tem_pits_para_copiar = pits_podem_ser_copiados_para_este.exists()

    pit_origem = None
    if tem_pits_para_copiar:
        acao = request.POST.get('acao') if request.method == 'POST' else None
        is_post_copiar = request.method == 'POST' and (acao == 'copiar' or 'confirmacao' in request.POST)

        if is_post_copiar:
            pit_origem = pits_podem_ser_copiados_para_este.filter(id=request.POST.get('pit_origem')).first()
            form = CopiarPitForm(
                initial={'pit_origem': pit_origem.id if pit_origem else None},
                request=request,
                pits_podem_ser_copiados=pits_podem_ser_copiados_para_este,
                pit_destino=pit,
            )
            if pit_origem:
                form_relacionar = CopiarPitRelacionarEntregasForm(
                    request.POST or None,
                    request=request,
                    pit_destino=pit,
                    pit_origem=pit_origem,
                    pits_podem_ser_copiados=pits_podem_ser_copiados_para_este,
                )
                form_relacionar_mapeamento = CopiarPitRelacionarEntregasForm(
                    request.POST or None,
                    request=request,
                    pit_destino=pit,
                    pit_origem=pit_origem,
                    pits_podem_ser_copiados=pits_podem_ser_copiados_para_este,
                    somente_mapeamento=True,
                )
                if form_relacionar.is_valid():
                    acao_copia = form_relacionar.cleaned_data.get('acao_copia')
                    mapa_entregas_pes = form_relacionar.mapa_entregas_pes

                    pit.copiar_outro_pit_para_este(pit_origem, acao_copia, request.user, mapa_entregas_pes=mapa_entregas_pes)

                    return httprr(url, 'Cópia realizada com sucesso.')
        else:
            form = CopiarPitForm(
                request.POST or None,
                request=request,
                pits_podem_ser_copiados=pits_podem_ser_copiados_para_este,
                pit_destino=pit,
            )
            if request.method == 'POST' and form.is_valid():
                pit_origem = form.cleaned_data.get('pit_origem')
            elif request.method != 'POST':
                pit_origem = pits_podem_ser_copiados_para_este.first()

            if pit_origem:
                form_relacionar = CopiarPitRelacionarEntregasForm(
                    request=request,
                    pit_destino=pit,
                    pit_origem=pit_origem,
                    pits_podem_ser_copiados=pits_podem_ser_copiados_para_este,
                )
                form_relacionar_mapeamento = CopiarPitRelacionarEntregasForm(
                    request=request,
                    pit_destino=pit,
                    pit_origem=pit_origem,
                    pits_podem_ser_copiados=pits_podem_ser_copiados_para_este,
                    somente_mapeamento=True,
                )

    return locals()


# ====================================================
# RIT
# ====================================================


@rtr()
@permission_required('rh.eh_servidor')
def visualizar_rit(request, pit_id):
    pit = get_object_or_404(PlanoIndividualTrabalho, pk=pit_id)
    if not pit.pode_visualizar_rit(request.user):
        raise PermissionDenied

    # Registro: habilita todos os dados do PIT
    # Histórico: visualiza apenas o histórico
    # Solicitações de Aprovação / Homologação: visualiza apenas as solicitações de aprovação / homologação
    modo = request.GET.get('m', 'registro')

    pit.calcular_pit()

    title = pit.get_verbose_rit()

    msg_adesao_relacionada = pit.adesao

    registros_acoes = RegistroAcaoPlanoIndividualTrabalho.objects.filter(pit=pit)

    entregas_pit = pit.get_entregas_pit_para_rit_com_canceladas_utilizadas()
    entregas_rit = pit.get_entregas_rit().order_by('entrega_pit__titulo')

    # As checagens de PIT feitas por pode_cadastrar_entrega_rit() independem da entrega, então são
    # calculadas uma única vez aqui: por entrega resta apenas conferir se ela está apta para o RIT.
    pode_cadastrar_entrega_rit = pit.pode_cadastrar_entrega_rit(request.user)
    ids_entregas_pit_aptas_para_rit = set(pit.get_entregas_pit_para_rit().values_list('id', flat=True)) if pode_cadastrar_entrega_rit else set()

    # Agrupando as entregas de RIT pela entrega do PIT
    entregas_pit_rit = []
    if entregas_pit:
        rit_entregas_por_entrega_pit = defaultdict(list)
        for entrega_rit in entregas_rit.select_related('entrega_pit__entrega_pes').order_by('titulo'):
            rit_entregas_por_entrega_pit[entrega_rit.entrega_pit_id].append(entrega_rit)

        pit_entregas_rit = (
            PlanoIndividualTrabalhoEntregas.objects.filter(id__in=entregas_pit.values('id'))
            .select_related('entrega_pes__pes__setor__uo__setor')
            .order_by('titulo')
        )
        for pit_entrega in pit_entregas_rit:
            pit_entrega.pit = pit
            dados = {}
            dados['pit_entrega'] = pit_entrega
            dados['possui_pes_vinculado_e_metrica_de_quantidade'] = pit_entrega.entrega_pes_tem_metrica_de_quantidade()
            dados['pode_cadastrar_entrega'] = pode_cadastrar_entrega_rit and pit_entrega.id in ids_entregas_pit_aptas_para_rit
            dados['rit_entregas'] = rit_entregas_por_entrega_pit[pit_entrega.id]
            entregas_pit_rit.append(dados)

    solicitacoes_aprovacao_homologacao_rit = pit.get_solicitacoes_aprovacao_homologacao(pit_rit=PitSolicitacaoAnalise.RIT).order_by('-id')

    pode_cancelar_pit = pit.pode_cancelar(request.user)

    existe_entrega_que_pode_ser_removida_no_rit = pit.existe_entrega_que_pode_ser_removida_no_rit(request.user)
    pode_solicitar_aprovacao_homologacao_rit, erros_pode_solicitar_aprovacao_homologacao_rit = pit.pode_solicitar_aprovacao_homologacao_rit(
        request.user, retornar_lista_erros=True
    )

    pode_aprovar_aprovar_rit = pit.pode_aprovar_rit(request.user)
    pode_homologar_rit = pit.pode_homologar_rit(request.user)
    pode_reabrir_rit = pit.pode_reabrir_rit(request.user)

    setores_envolvidos = pit.get_setores_envolvidos()

    justificativa_observacao_solicitacao = None
    if pode_aprovar_aprovar_rit or pode_homologar_rit:
        r = RegistroAcaoPlanoIndividualTrabalho.objects.filter(
            pit=pit, tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_SERVIDOR_SOLICITOU_APROVACAO_HOMOLOGACAO_RIT
        ).first()
        if r.observacao:
            justificativa_observacao_solicitacao = r.observacao

    existem_pendencias_no_pit_para_solicitar_aprovacao_homologaca_rit, erros_existem_pendencias_no_pit = (
        pit.existem_pendencias_no_pit_para_solicitar_aprovacao_homologaca_rit(request.user, retornar_lista_erros=True)
    )
    pode_visualizar_dados = True
    if not pit.pit_estah_cancelado() and existem_pendencias_no_pit_para_solicitar_aprovacao_homologaca_rit:
        pode_visualizar_dados = False

    pode_homologar_rit2 = pit.pode_homologar_rit(request.user, considera_pendencia_geral_servidor_pgd=False)
    pendencia_geral_pgd = None
    pode_operacoes_chefe_direto = pode_reabrir_rit or pode_homologar_rit2
    if pit.adesao.servidor == request.user.get_relacionamento() or pode_operacoes_chefe_direto:
        pit_atual = PlanoIndividualTrabalho.get_pit_na_data(pit.adesao.servidor, get_datetime_now().date())
        if pit == pit_atual:
            pendencia_geral_pgd = get_pendencia_geral_servidor_pgd(pit.adesao.servidor, msgs_para_chefe=pode_operacoes_chefe_direto)

    erro_habilitacao_setor = None
    setores_envolvidos_nao_habilitado = pit.get_setores_envolvidos_nao_habilitado()
    if setores_envolvidos_nao_habilitado:
        siglas_setores = ', '.join([s.sigla for s in setores_envolvidos_nao_habilitado])
        erro_habilitacao_setor = get_msg_plural_nenhum_setor_habilitado(sigla_setores=siglas_setores)

    analista = AnalistaDesenvolvedor.objects.filter(usuario=request.user).first()

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def cadastrar_entrega_rit(request, entrega_pit_id):
    entrega_pit = get_object_or_404(PlanoIndividualTrabalhoEntregas, pk=entrega_pit_id)
    pit = entrega_pit.pit
    if not pit.pode_cadastrar_entrega_rit(request.user, entrega_pit_id):
        raise PermissionDenied
    # if not entrega_pit.pode_cadastrar_entrega(request.user):
    #    raise PermissionDenied()

    title = f'Cadastrar Entrega - {pit.get_verbose_rit()}'
    url = f'{reverse("visualizar_rit_pgd2", args=[pit.id])}?tab=entregas'

    entrega_pes = entrega_pit.entrega_pes
    percentual_maximo_teletrabalho_inicial = pit.percentual_teletrabalho

    form = RelatorioIndividualTrabalhoCadastrarForm(
        request.POST or None,
        request.FILES or None,
        pit=pit,
        entrega_pes=entrega_pes,
        percentual_maximo_teletrabalho_inicial=percentual_maximo_teletrabalho_inicial,
    )
    if form.is_valid():
        form.instance.entrega_pit = entrega_pit
        if form.instance.perc_executada_em_teletrabalho and form.instance.tempo_executado:
            form.instance.tempo_executada_em_teletrabalho = (form.instance.perc_executada_em_teletrabalho / 100) * form.instance.tempo_executado
        entrega = form.save()

        pit.calcular_pit()

        RegistroAcaoPlanoIndividualTrabalho.registrar(
            request=request, tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_CADASTROU_ENTREGA_RIT, pit=pit, obs=''
        )

        return httprr(url, 'A entrega do RIT foi cadastrada com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def remover_entrega_rit(request, pit_id):
    pit = get_object_or_404(PlanoIndividualTrabalho, pk=pit_id)
    if not pit.pode_cadastrar_entrega_rit(request.user):
        raise PermissionDenied

    title = f'Remover Entrega - {pit.get_verbose_rit()}'
    url = f'{reverse("visualizar_rit_pgd2", args=[pit.id])}?tab=entregas'

    selecionados = request.GET.getlist('checks[]')
    if 'remover_entregas_rit' in request.GET and selecionados:
        form = ConfirmacaoComSenhaForm(request.POST or None, request=request)
        if form.is_valid():
            # RegistroAcaoPlanoIndividualTrabalho.registrar(request=request, tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_CADASTROU_ENTREGA_RIT, pit=pit, obs='Removeu')

            RelatorioIndividualTrabalho.objects.filter(entrega_pit__pit=pit, id__in=selecionados).delete()
            pit.calcular_pit()

            return httprr(url, 'As entregas selecionadas do RIT foram removidas com sucesso.')
    else:
        return httprr(url, 'Selecione ao menos uma entrega para remover.', tag='error')

    return locals()


@rtr('pgd2/templates/cadastrar_entrega_rit.html')
@transaction.atomic
@permission_required('rh.eh_servidor')
def editar_entrega_rit(request, rit_ent_id):
    rit_ent = get_object_or_404(RelatorioIndividualTrabalho, pk=rit_ent_id)
    pit = rit_ent.entrega_pit.pit
    if not rit_ent.pode_editar_entrega_rit(request.user):
        raise PermissionDenied

    title = f'Editar {rit_ent}'
    url = f'{reverse("visualizar_rit_pgd2", args=[pit.id])}?tab=entregas'

    entrega_pes = rit_ent.entrega_pit.entrega_pes
    entrega_pit = rit_ent.entrega_pit

    # Historico: DE
    # ----------------------
    de_titulo = rit_ent.titulo
    de_descricao = rit_ent.descricao
    de_tempo_executado = rit_ent.tempo_executado
    de_perc_executada_em_teletrabalho = rit_ent.perc_executada_em_teletrabalho
    de_data_inicio = rit_ent.data_inicio
    de_data_fim = rit_ent.data_fim

    form = RelatorioIndividualTrabalhoEditarForm(
        request.POST or None, request.FILES or None, instance=rit_ent, pit=pit, entrega_pes=rit_ent.entrega_pit.entrega_pes
    )
    if form.is_valid():
        form.instance.pit = pit
        form.instance.tempo_executada_em_teletrabalho = (form.instance.perc_executada_em_teletrabalho / 100) * form.instance.tempo_executado

        entrega = form.save(False)
        if form.cleaned_data.get('quantidade_progresso_e'):
            entrega.quantidade_progresso = form.cleaned_data.get('quantidade_progresso_e')
        else:
            entrega.quantidade_progresso = 0
        entrega.save()

        # Historico: PARA
        # ----------------------
        para_titulo = form.cleaned_data.get('titulo')
        para_descricao = form.cleaned_data.get('descricao')
        para_tempo_executado = form.cleaned_data.get('tempo_executado')
        para_perc_executada_em_teletrabalho = form.cleaned_data.get('perc_executada_em_teletrabalho')
        para_data_inicio = form.cleaned_data.get('data_inicio')
        para_data_fim = form.cleaned_data.get('data_fim')

        # --------------------------------------
        # Histórico: montando DE -> PARA
        # --------------------------------------
        dados_de_para = None
        try:
            dados_de = {}
            dados_para = {}
            if de_titulo != para_titulo:
                dados_de[get_vbn_field(RelatorioIndividualTrabalho, 'titulo')] = str(de_titulo)
                dados_para[get_vbn_field(RelatorioIndividualTrabalho, 'titulo')] = str(para_titulo)
            if de_descricao != para_descricao:
                dados_de[get_vbn_field(RelatorioIndividualTrabalho, 'descricao')] = str(de_descricao)
                dados_para[get_vbn_field(RelatorioIndividualTrabalho, 'descricao')] = str(para_descricao)
            if de_tempo_executado != para_tempo_executado:
                dados_de[get_vbn_field(RelatorioIndividualTrabalho, 'tempo_executado')] = str(de_tempo_executado)
                dados_para[get_vbn_field(RelatorioIndividualTrabalho, 'tempo_executado')] = str(para_tempo_executado)
            if de_perc_executada_em_teletrabalho != para_perc_executada_em_teletrabalho:
                dados_de[get_vbn_field(RelatorioIndividualTrabalho, 'executada_em_teletrabalho')] = str(de_perc_executada_em_teletrabalho)
                dados_para[get_vbn_field(RelatorioIndividualTrabalho, 'executada_em_teletrabalho')] = str(para_perc_executada_em_teletrabalho)
            if de_data_inicio != para_data_inicio:
                dados_de[get_vbn_field(RelatorioIndividualTrabalho, 'data_inicio')] = str(de_data_inicio)
                dados_para[get_vbn_field(RelatorioIndividualTrabalho, 'data_inicio')] = str(para_data_inicio)
            if de_data_fim != para_data_fim:
                dados_de[get_vbn_field(RelatorioIndividualTrabalho, 'data_fim')] = str(de_data_fim)
                dados_para[get_vbn_field(RelatorioIndividualTrabalho, 'data_fim')] = str(para_data_fim)
            dados_de_para = {'de': dados_de, 'para': dados_para}
        except Exception:
            pass
        # --------------------------------------

        ra_obs = f'Editou "{rit_ent}"'
        RegistroAcaoPlanoIndividualTrabalho.registrar(
            request=request, tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_CADASTROU_ENTREGA_RIT, pit=pit, obs=ra_obs, dados_de_para=dados_de_para
        )

        return httprr(url, 'Dados alterados com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def solicitar_aprovacao_homologacao_rit(request, pit_id):
    pit = get_object_or_404(PlanoIndividualTrabalho, pk=pit_id)
    url = reverse('visualizar_rit_pgd2', args=[pit.id])

    pode_solicitar_aprovacao_homologacao_rit, erros = pit.pode_solicitar_aprovacao_homologacao_rit(request.user, retornar_lista_erros=True)
    if not pode_solicitar_aprovacao_homologacao_rit:
        messages.error(request, mark_safe('</br>'.join(erros)))
        return httprr(url)

    title = f'Solicitar Aprovação/Homologação - {pit.get_verbose_rit()}'

    # Verifica se deve ou nao preencher o questionário de pesquisa
    # ------------------------
    deve_responder_como_servidor = RelatorioIndividualTrabalhoQuestionario.deve_responder_como_servidor(
        servidor=pit.adesao.servidor, setor_pit_rit=pit.adesao.servidor.setor, periodo_pit_rit=pit.periodo_pit_rit
    )
    if deve_responder_como_servidor:
        title = f'Questionário de pesquisa referente ao {pit.get_verbose_pit_rit()}'
        mensagem_form_questionario = f'Após o preenchimento do questionário você será redirecionado para Solicitar Aprovação/Homologação do {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2}'
        form = QuestionarioRitServidorForm(request.POST or None, request=request)
        if form.is_valid():
            o = form.save(False)
            o.periodo_pit_rit = pit.periodo_pit_rit
            o.setor = pit.adesao.servidor.setor
            o.servidor_respondente = pit.adesao.servidor
            o.questionario_de_chefe = False
            o.save()

            url_entregar_rit = f'/pgd2/solicitar_aprovacao_homologacao_rit/{pit_id}/'
            return httprr(url_entregar_rit, 'Questionário preenchido com sucesso.')

    if not deve_responder_como_servidor:
        form = JustificativaComSenhaForm(request.POST or None, request=request)
        if form.is_valid():
            # Calcula o PIT
            pit.calcular_pit()

            # Verifica se o prazo das entregas extrapola o periodo do PIT
            data_ini_pit = pit.data_inicio
            data_fim_pit = pit.data_fim
            entregas = pit.get_entregas_rit().filter(data_inicio__isnull=False, data_fim__isnull=False)
            tem_data_fora_periodo = False
            for ent in entregas:
                valida_dt_inicio = data_ini_pit <= ent.data_inicio <= data_fim_pit
                valida_dt_fim = data_ini_pit <= ent.data_fim <= data_fim_pit
                if not (valida_dt_inicio and valida_dt_fim):
                    tem_data_fora_periodo = True
                    break
            if tem_data_fora_periodo:
                return httprr(
                    url,
                    'Impossível Solicitar Aprovação/Homologação se uma das entregas estiver com data início e final em desacordo com o período do PIT.',
                    tag='error',
                )

            # Gera a solicitação e ajusta o PIT
            pit.gerar_solicitacao_aprovacao_homologacao_pit_rit(objeto_parecer=PitSolicitacaoAnalise.RIT)

            justificativa = form.cleaned_data.get('justificativa')
            ra_obs = f'Foi solicitado aprovação/homologação do "{pit.get_verbose_rit()}"'
            if justificativa:
                ra_obs = f'Foi solicitado aprovação/homologação do "{pit.get_verbose_rit()}" mediante a justificativa "{justificativa}"'
            RegistroAcaoPlanoIndividualTrabalho.registrar(
                request=request, tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_SERVIDOR_SOLICITOU_APROVACAO_HOMOLOGACAO_RIT, pit=pit, obs=ra_obs
            )

            return httprr(url, 'Aprovação/homologação solicitada com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.chefe')
def aprovar_rit(request, pit_id):
    pit = get_object_or_404(PlanoIndividualTrabalho, pk=pit_id)
    url = reverse('visualizar_rit_pgd2', args=[pit.id])

    # Calcula o PIT
    pit.calcular_pit()

    if not pit.pode_aprovar_rit(request.user):
        raise PermissionDenied

    title = f'Aprovar - {pit.get_verbose_rit()}'

    form = JustificativaComSenhaForm(request.POST or None, request=request)
    if form.is_valid():
        # setores = setores_que_sou_chefe_no_periodo(pit.data_inicio, pit.data_fim, request.user.get_relacionamento())
        setores, _ = setores_e_servidores_que_sou_relacionado_como_chefe_no_periodo(request.user, pit.data_inicio, pit.data_fim)

        pit.aprovar_rit(setores, request.user.get_relacionamento())

        justificativa = form.cleaned_data.get('justificativa')
        ra_obs = f'Aprovação do "{pit.get_verbose_rit()}"'
        if justificativa:
            ra_obs = f'Aprovação do "{pit.get_verbose_rit()}" mediante a justificativa "{justificativa}"'
        RegistroAcaoPlanoIndividualTrabalho.registrar(request=request, tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_APROVOU_RIT, pit=pit, obs=ra_obs)

        return httprr(url, f'O {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2} foi aprovado com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.chefe')
def reprovar_rit(request, pit_id):
    pit = get_object_or_404(PlanoIndividualTrabalho, pk=pit_id)
    url = reverse('visualizar_rit_pgd2', args=[pit.id])

    # Calcula o PIT
    pit.calcular_pit()

    if not pit.pode_aprovar_rit(request.user):
        raise PermissionDenied

    title = f'Reprovar - {pit.get_verbose_rit()}'

    form = JustificativaComSenhaForm(request.POST or None, request=request)
    if form.is_valid():
        # setores = setores_que_sou_chefe_no_periodo(pit.data_inicio, pit.data_fim, request.user.get_relacionamento())
        setores, _ = setores_e_servidores_que_sou_relacionado_como_chefe_no_periodo(request.user, pit.data_inicio, pit.data_fim)

        pit.reprovar_rit(setores, request.user.get_relacionamento())

        justificativa = form.cleaned_data.get('justificativa')
        ra_obs = f'Reprovação do "{pit.get_verbose_rit()}"'
        if justificativa:
            ra_obs = f'Reprovação do "{pit.get_verbose_rit()}" mediante a justificativa "{justificativa}"'
        RegistroAcaoPlanoIndividualTrabalho.registrar(
            request=request, tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_NAO_APROVOU_RIT, pit=pit, obs=ra_obs
        )

        return httprr(url, f'O {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2} foi devolvido para ajustes.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.chefe')
def homologar_rit(request, pit_id):
    pit = get_object_or_404(PlanoIndividualTrabalho, pk=pit_id)
    url = reverse('visualizar_rit_pgd2', args=[pit.id])

    # Calcula o PIT
    pit.calcular_pit()

    if not pit.pode_homologar_rit(request.user):
        raise PermissionDenied

    # Homologa
    # ------------------------
    title = f'Homologar - {pit.get_verbose_rit()}'
    tempo_executado_total = pit.tempo_executado_total
    form = AvaliacaoRitForm(request.POST or None, request=request, tempo_executado_total=tempo_executado_total)
    if form.is_valid():
        # setores = setores_que_sou_chefe_no_periodo(pit.data_inicio, pit.data_fim, request.user.get_relacionamento())
        setores, _ = setores_e_servidores_que_sou_relacionado_como_chefe_no_periodo(request.user, pit.data_inicio, pit.data_fim)

        avaliacao_rit = form.cleaned_data.get('avaliacao_rit')
        justificativa = form.cleaned_data.get('justificativa')
        avaliacao_rit_str = PlanoIndividualTrabalho.AVALIACAO_RIT_CHOICES[int(avaliacao_rit) - 1][1]
        tempo_homologado = form.cleaned_data.get('tempo_homologado')

        pit.homologar_rit(setores, avaliacao_rit, tempo_homologado, request.user.get_relacionamento(), justificativa=justificativa)

        ra_obs = f'Homologação do "{pit.get_verbose_rit()}" mediante a avaliação "{avaliacao_rit_str}" e confirmação das entregas do {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2}'
        if justificativa:
            ra_obs = f'Homologação do "{pit.get_verbose_rit()}" mediante a avaliação "{avaliacao_rit_str}", justificativa "{justificativa}" e  e confirmação das entregas do {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2}'

        RegistroAcaoPlanoIndividualTrabalho.registrar(
            request=request, tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_HOMOLOGOU_RIT, pit=pit, obs=ra_obs
        )

        notificar_homologacao_rit(pit)

        return httprr(url, f'O {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2} foi homologado com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.chefe')
def reabrir_rit(request, pit_id):
    pit = get_object_or_404(PlanoIndividualTrabalho, pk=pit_id)
    url = reverse('visualizar_rit_pgd2', args=[pit.id])

    # Calcula o PIT
    pit.calcular_pit()

    if not pit.pode_reabrir_rit(request.user):
        raise PermissionDenied

    title = f'Reabrir/Devolver - {pit.get_verbose_rit()}'

    form = JustificativaComSenhaForm(request.POST or None, request=request)
    if form.is_valid():
        justificativa = form.cleaned_data.get('justificativa')

        pit.reabrir_rit()
        pit.calcular_pit()

        ra_obs = ''
        if justificativa:
            ra_obs = f'Reabriu {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2} mediante a seguinte justificativa: "{justificativa}"'
        RegistroAcaoPlanoIndividualTrabalho.registrar(request=request, tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_REABRIU_RIT, pit=pit, obs=ra_obs)

        notificar_reabrir_rit(pit)

        return httprr(url, f'Reabertura/Devolução {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2} realizada com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.chefe')
def nao_homologar_rit(request, pit_id):
    pit = get_object_or_404(PlanoIndividualTrabalho, pk=pit_id)
    url = reverse('visualizar_rit_pgd2', args=[pit.id])

    # Calcula o PIT
    pit.calcular_pit()

    if not pit.pode_homologar_rit(request.user):
        raise PermissionDenied

    title = f'Não Homologar - {pit.get_verbose_rit()}'

    form = JustificativaComSenhaForm(request.POST or None, request=request)
    if form.is_valid():
        # setores = setores_que_sou_chefe_no_periodo(pit.data_inicio, pit.data_fim, request.user.get_relacionamento())
        setores, _ = setores_e_servidores_que_sou_relacionado_como_chefe_no_periodo(request.user, pit.data_inicio, pit.data_fim)

        pit.nao_homologar_rit(setores, request.user.get_relacionamento())

        justificativa = form.cleaned_data.get('justificativa')
        ra_obs = f'Não Homologação do "{pit.get_verbose_rit()}"'
        if justificativa:
            ra_obs = f'Não Homologação do "{pit.get_verbose_rit()}" mediante a justificativa "{justificativa}"'
        RegistroAcaoPlanoIndividualTrabalho.registrar(
            request=request, tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_NAO_HOMOLOGOU_RIT, pit=pit, obs=ra_obs
        )

        notificar_nao_homologacao_rit(pit)

        return httprr(url, f'O {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2} não foi homologado.')

    return locals()


@rtr()
@permission_required('rh.chefe')
def listar_rits_chefe(request):
    if not PlanoIndividualTrabalho.pode_visualizar_lista(request.user):
        raise PermissionDenied

    title = f'{nomenclatura.relatorios_individuais_de_trabalho_pgd2}'

    lista_pits = None

    # Se fui chefe no periodo ou Se sou chefe hoje
    setores = setores_que_sou_fui_chefe(request.user.get_relacionamento())

    ids_pits = PitSetores.objects.filter(setor__in=setores).values_list('pit_id', flat=True)
    lista_pits = PlanoIndividualTrabalho.objects.filter(id__in=ids_pits).order_by(
        'adesao__servidor__pessoa_fisica__nome', 'periodo_pit_rit__data_inicio'
    )
    lista_pits = lista_pits.filter(situacao_rit__isnull=False)

    form = BuscarRitsChefeForm(request.GET or None, request=request, setores=setores)
    buscou = False
    if form.is_valid():
        buscar_str = form.cleaned_data.get('buscar_str')
        setor_filtro = form.cleaned_data.get('setor')
        situacao = form.cleaned_data.get('situacao')
        periodo_pit_rit = form.cleaned_data.get('periodo_pit_rit')
        buscou = buscar_str or setor_filtro or situacao or periodo_pit_rit

        if buscou:
            # Periodo
            if periodo_pit_rit:
                lista_pits = lista_pits.filter(periodo_pit_rit=periodo_pit_rit)

            if setor_filtro:
                # Essa busca pode resultar em PITs com ou sem entregas.
                # - Em consequência disso podemos ter ou não setores vinculados (PitSetores).
                # - Os setores vinculados são gerados com base nas entregas
                # Então usaremos um OU para buscar no setor do servidor OU nos setores relacionados
                ids_pits = PitSetores.objects.filter(setor=setor_filtro).values_list('setor_id', flat=True)
                lista_pits = lista_pits.filter(Q(id__in=ids_pits) | Q(adesao__servidor__setor=setor_filtro))

            if situacao:
                lista_pits = lista_pits.filter(situacao_rit=situacao)

            if buscar_str:
                lista_pits = lista_pits.filter(
                    Q(adesao__servidor__pessoa_fisica__nome__icontains=buscar_str) | Q(adesao__servidor__matricula__icontains=buscar_str)
                )

    return locals()


@rtr()
@permission_required('rh.chefe')
def listar_rits_chefe_deve_aprova_homologa(request):
    if not PlanoIndividualTrabalho.pode_visualizar_lista(request.user):
        raise PermissionDenied

    title = f'{nomenclatura.relatorios_individuais_de_trabalho_pgd2} para Aprovar/Homologar (chefe imediato)'

    lista_pits_aprova, lista_pits_homologacao = PlanoIndividualTrabalho.get_rits_pendendentes_avaliacao_chefe_direto(request.user)

    querys = []

    form = BuscarRitsChefeFormSimples2(request.GET or None, request=request)
    if form.is_valid():
        buscar_str = form.cleaned_data.get('buscar_str')
        periodo_pit_rit = form.cleaned_data.get('periodo_pit_rit')
        if buscar_str or periodo_pit_rit:
            if periodo_pit_rit:
                querys.append(Q(periodo_pit_rit=periodo_pit_rit))
            if buscar_str:
                querys.append(Q(adesao__servidor__pessoa_fisica__nome__icontains=buscar_str) | Q(adesao__servidor__matricula__icontains=buscar_str))
            lista_pits_aprova = lista_pits_aprova.filter(reduce(operator.and_, querys))
            lista_pits_homologacao = lista_pits_homologacao.filter(reduce(operator.and_, querys))

    return locals()


@rtr()
@permission_required('rh.chefe')
def listar_rits_chefe_pode_aprova_homologa(request):
    if not PlanoIndividualTrabalho.pode_visualizar_lista(request.user):
        raise PermissionDenied

    title = f'{nomenclatura.relatorios_individuais_de_trabalho_pgd2} (outros)'

    setores = setores_que_sou_chefe_hoje(request.user.get_relacionamento())
    setores_chefe_direto = setores_que_sou_chefe_direto_hoje(request.user.get_relacionamento())
    setores = setores.exclude(id__in=setores_chefe_direto.values('id'))

    lista_pits = (
        PlanoIndividualTrabalho.objects.exclude(situacao=PlanoIndividualTrabalho.CANCELADO)
        .exclude(adesao__servidor=request.user.get_relacionamento())
        .order_by('adesao__servidor__pessoa_fisica__nome')
    )

    form = BuscarRitsChefeFormSimples2(request.GET or None, request=request)
    if form.is_valid():
        buscar_str = form.cleaned_data.get('buscar_str')
        periodo_pit_rit = form.cleaned_data.get('periodo_pit_rit')
        if buscar_str or periodo_pit_rit:
            if periodo_pit_rit:
                lista_pits = lista_pits.filter(periodo_pit_rit=periodo_pit_rit)
            if buscar_str:
                lista_pits = lista_pits.filter(
                    Q(adesao__servidor__pessoa_fisica__nome__icontains=buscar_str) | Q(adesao__servidor__matricula__icontains=buscar_str)
                )

    solicitacoes_aprovacao = PlanoIndividualTrabalho.get_solicitacoes_setor_aprovacao_homologacao_nao_finalizadas(
        objeto_parecer=2, setores=setores, tipo_parecer=PitSolicitacaoAnaliseSetor.APROVACAO
    )
    solicitacoes_homologacao = PlanoIndividualTrabalho.get_solicitacoes_setor_aprovacao_homologacao_nao_finalizadas(
        objeto_parecer=2, setores=setores, tipo_parecer=PitSolicitacaoAnaliseSetor.HOMOLOGACAO
    )

    ids_pits_apovacao = solicitacoes_aprovacao.values_list('solicitacao__pit', flat=True)
    ids_pits_homologacao = solicitacoes_homologacao.values_list('solicitacao__pit', flat=True)

    lista_pits_aprova = lista_pits.filter(id__in=ids_pits_apovacao)
    lista_pits_homologacao = lista_pits.filter(id__in=ids_pits_homologacao)

    return locals()


@rtr()
@permission_required('rh.chefe')
def listar_rits_chefe_deve_pode_aprova_homologa(request):
    if not PlanoIndividualTrabalho.pode_visualizar_lista(request.user):
        raise PermissionDenied

    title = f'{nomenclatura.relatorios_individuais_de_trabalho_pgd2} para Aprovar/Homologar'

    # Deve Aprovar/Homologar
    lista_pits_aprova_deve, lista_pits_homologacao_deve = PlanoIndividualTrabalho.get_rits_pendendentes_avaliacao_chefe_direto(request.user)
    lista_pits_homologacao_deve = lista_pits_homologacao_deve.annotate(parecer=Value('Homologação', output_field=CharField()))
    lista_pits_aprova_deve = lista_pits_aprova_deve.annotate(parecer=Value('Aprovação', output_field=CharField()))
    lista_pits_deve = []

    # Pode Aprovar/Homologar
    lista_pits_aprova_pode, lista_pits_homologacao_pode = PlanoIndividualTrabalho.get_rits_pendendentes_avaliacao_chefe_outros(request.user)
    lista_pits_homologacao_pode = lista_pits_homologacao_pode.annotate(parecer=Value('Homologação', output_field=CharField()))
    lista_pits_aprova_pode = lista_pits_aprova_pode.annotate(parecer=Value('Aprovação', output_field=CharField()))
    lista_pits_pode = []

    # Retira do PODE os DEVE
    ids_deve = []
    ids_deve.extend(lista_pits_aprova_deve.values_list('id', flat=True))
    ids_deve.extend(lista_pits_homologacao_deve.values_list('id', flat=True))
    lista_pits_aprova_pode = lista_pits_aprova_pode.exclude(id__in=ids_deve)
    lista_pits_homologacao_pode = lista_pits_homologacao_pode.exclude(id__in=ids_deve)

    form = BuscarRitsChefeFormSimples2(request.GET or None, request=request)
    if form.is_valid():
        buscar_str = form.cleaned_data.get('buscar_str')
        periodo_pit_rit = form.cleaned_data.get('periodo_pit_rit')
        if buscar_str or periodo_pit_rit:
            querys = []
            if periodo_pit_rit:
                querys.append(Q(periodo_pit_rit=periodo_pit_rit))
            if buscar_str:
                querys.append(Q(adesao__servidor__pessoa_fisica__nome__icontains=buscar_str) | Q(adesao__servidor__matricula__icontains=buscar_str))

            if querys:
                lista_pits_homologacao_deve = lista_pits_homologacao_deve.filter(reduce(operator.and_, querys))
                lista_pits_aprova_deve = lista_pits_aprova_deve.filter(reduce(operator.and_, querys))

                lista_pits_homologacao_pode = lista_pits_homologacao_pode.filter(reduce(operator.and_, querys))
                lista_pits_aprova_pode = lista_pits_aprova_pode.filter(reduce(operator.and_, querys))

    lista_pits_deve.extend(lista_pits_homologacao_deve)
    lista_pits_deve.extend(lista_pits_aprova_deve)
    lista_pits_deve = sorted(lista_pits_deve, key=lambda p: p.adesao.servidor.pessoa_fisica.nome)

    lista_pits_pode.extend(lista_pits_homologacao_pode)
    lista_pits_pode.extend(lista_pits_aprova_pode)
    lista_pits_pode = sorted(lista_pits_pode, key=lambda p: p.adesao.servidor.pessoa_fisica.nome)

    return locals()


@rtr()
@permission_required('rh.eh_servidor')
def servidor_pgd_horas(request, sol_id):
    # Lista as horas do servidor para cada adesão

    adesao = get_object_or_404(SolicitacaoAdesaoServidor, pk=sol_id)
    servidor = adesao.servidor
    if not adesao.pode_visualizar_horas_servidor(request.user):
        raise PermissionDenied

    eu_mesmo = adesao.servidor == request.user.get_relacionamento()

    utiliza_ponto = utilizar_integracao_com_ponto()

    title = f'Horas PGD - {servidor} da {adesao.get_verbose_simples()}'

    totais_soma = ['tempo_previsto', 'tempo_planejado_total', 'tempo_executado_homologado_total', 'ch_distribuida', 'ch_a_distribuir']
    anos = set()

    rits = adesao.get_pits()
    for rit in rits:
        anos.add(rit.data_inicio.year)
    anos = list(anos)
    anos.sort()

    semestres = {}
    for ano in anos:
        i = f'{ano}-1'
        f = f'{ano}-2'
        semestres[i] = None
        semestres[f] = None
    for ano in anos:
        ids_rits_ano_s1 = []
        ids_rits_ano_s2 = []
        for rit in rits:
            ids_rits_ano = []
            if rit.data_inicio.year == ano:
                if rit.data_inicio.month <= 6:
                    ids_rits_ano_s1.append(rit.id)
                else:
                    ids_rits_ano_s2.append(rit.id)
        i = f'{ano}-1'
        f = f'{ano}-2'

        # Semestre 1
        dados_semestre = {}
        rits_1 = PlanoIndividualTrabalho.objects.filter(id__in=ids_rits_ano_s1).order_by('data_inicio')
        dados_semestre['rits'] = rits_1
        for total in totais_soma:
            dados_semestre[total] = gv(rits_1.aggregate(v=Sum(total)))
        semestres[i] = dados_semestre

        # Semestre 2
        dados_semestre = {}
        rits_2 = PlanoIndividualTrabalho.objects.filter(id__in=ids_rits_ano_s2).order_by('data_fim')
        dados_semestre['rits'] = rits_2
        for total in totais_soma:
            dados_semestre[total] = gv(rits_2.aggregate(v=Sum(total)))
        semestres[f] = dados_semestre

    return locals()


@rtr()
@permission_required('rh.eh_servidor')
def servidor_pgd_horas_detalhes(request, rit_id):
    # Lista as horas do servidor para cada adesão

    rit = get_object_or_404(PlanoIndividualTrabalho, pk=rit_id)

    servidor = rit.adesao.servidor
    adesao = rit.adesao

    utiliza_ponto = utilizar_integracao_com_ponto()
    if not utiliza_ponto and not (adesao.estah_deferida and adesao.servidor == request.user.get_relacionamento()):
        raise PermissionDenied

    pit = rit

    title = f'Distribuição de Horas do {rit.get_verbose_rit()}'

    pode_distribuir_horas = rit.pode_distribuir_horas(request.user)
    pode_ajustar_distribuicao_horas_semestre_rit = rit.pode_ajustar_distribuicao_horas_semestre_rit(request.user)
    pode_desfazer_distribuicao_horas_semestre = rit.pode_desfazer_distribuicao_horas_semestre(request.user)

    distribuicoes = RelatorioIndividualTrabalhoDistribuicaoHoras.objects.filter(rit=rit)
    distribuicoes_semestre_rit = distribuicoes.filter(tipo=RelatorioIndividualTrabalhoDistribuicaoHoras.SEMESTRE_RIT)
    distribuicoes_semestre_antes_rit = distribuicoes.filter(tipo=RelatorioIndividualTrabalhoDistribuicaoHoras.SEMESTRE_ANTES_RIT)
    distribuicoes_compensacao_especifica = distribuicoes.filter(tipo=RelatorioIndividualTrabalhoDistribuicaoHoras.COMPENSACAO_ESPECIFICA)
    distribuicoes_semestre_pos_rit = distribuicoes.filter(tipo=RelatorioIndividualTrabalhoDistribuicaoHoras.SEMESTRE_POS_RIT)

    pode_ajustar_distribuicoes_compensacao_especifica = False
    if pode_distribuir_horas:
        if distribuicoes_compensacao_especifica:
            compensacoes_compensaveis = obter_compensacoes_especificas_compesaveis_rit(rit)
            compensacoes_verificadas = []
            for dist in distribuicoes_compensacao_especifica:
                if dist.compensacao_especifica.id not in compensacoes_verificadas:
                    pode_ajustar_distribuicao_compensacao_especifica = rit.pode_ajustar_distribuicao_compensacao_especifica(
                        request.user, compensacao_especifica=dist.compensacao_especifica, compensacoes_compensaveis=compensacoes_compensaveis
                    )
                    pode_desfazer_distribuicao_compensacao_especifica = rit.pode_desfazer_distribuicao_compensacao_especifica(
                        request.user, compensacao_especifica=dist.compensacao_especifica
                    )
                    if pode_ajustar_distribuicao_compensacao_especifica or pode_desfazer_distribuicao_compensacao_especifica:
                        pode_ajustar_distribuicoes_compensacao_especifica = True
                        break
                compensacoes_verificadas.append(dist.compensacao_especifica.id)
        else:
            if not rit.bloqueado_para_distribuicao_manual:
                pode_ajustar_distribuicoes_compensacao_especifica = True

    ch_segundos_rit_ch_distribuido_periodo_rit = int(rit.ch_distribuido_periodo_rit)
    ch_segundos_saldos_externos_periodo_rit = 0

    dados_semestre_rit = list(distribuicoes_semestre_rit)
    dados_semestre_rit.extend(distribuicoes_semestre_antes_rit)
    dados_semestre_rit.extend(distribuicoes_semestre_pos_rit)
    dados_compensacao_especifica = list(distribuicoes_compensacao_especifica)

    ch_segundos_diferenca_periodo_rit = ch_segundos_rit_ch_distribuido_periodo_rit - ch_segundos_saldos_externos_periodo_rit
    if ch_segundos_diferenca_periodo_rit < 0:
        ch_segundos_diferenca_periodo_rit = 0

    # dados_saldos_externos_criados = [d.saldo_externo for d in dados_semestre_rit]
    # dados_saldos_externos_criados_totais = SaldoExterno.get_valores_totais(dados_saldos_externos_criados)
    content_type_rit = ContentType.objects.get_for_model(PlanoIndividualTrabalho)
    dados_saldos_externos_criados = SaldoExterno.objects.filter(origem_type=content_type_rit, origem_id=pit.id)
    dados_saldos_externos_criados_totais = SaldoExterno.get_valores_totais(dados_saldos_externos_criados)

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def distribuir_horas_automaticamente_rit(request, rit_id):
    rit = get_object_or_404(PlanoIndividualTrabalho, pk=rit_id)

    if not rit.pode_distribuir_horas(request.user):
        raise PermissionDenied

    title = f'Distribuir/Redistribuir horas automaticamente no {rit.get_verbose_rit()}'

    form = DistribuirHorasAutoRitForm(request.POST or None, request=request)
    if form.is_valid():
        apenas_periodo_rit = form.cleaned_data.get('confirmacao2')
        rit.desfazer_distribuicao_horas()
        rit.distribuir_horas_automaticamente(apenas_periodo_rit=apenas_periodo_rit)
        url = f'/pgd2/servidor_pgd_horas_detalhes/{rit.id}'
        return httprr(url, 'Distribuição/Redistribuição automática de horas realizada com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def desfazer_distribuicao_horas(request, rit_id):
    # Desfaz todas a distribuição de horas
    rit = get_object_or_404(PlanoIndividualTrabalho, pk=rit_id)

    if not rit.pode_distribuir_horas(request.user):
        raise PermissionDenied

    title = f'Desfazer distribuição de horas no {rit.get_verbose_rit()}'

    form = DesfazerDistribuirHorasAutoRitForm(request.POST or None, request=request)
    if form.is_valid():
        rit.desfazer_distribuicao_horas()
        url = f'/pgd2/servidor_pgd_horas_detalhes/{rit.id}'
        return httprr(url, 'A distribuição de horas do semestre foi ajustada com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def atualizar_horas_previstas_rit(request, rit_id):
    # Recalcula as horas previstas de um rit
    # - usado apenas na tela de distribuição de horas

    rit = get_object_or_404(PlanoIndividualTrabalho, pk=rit_id)

    if not rit.pode_distribuir_horas(request.user):
        raise PermissionDenied

    rit.calcular_pit_tempo_previsto(salvar_dado=True)

    url = f'/pgd2/servidor_pgd_horas_detalhes/{rit.id}'
    return httprr(url, 'As horas previstas do RIT foram atualizadas com sucesso.')


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def ajustar_distribuicao_semestre(request, rit_id):
    # Ajusta manualmente a distribuicao de horas do semestre do rit
    # - apaga a distribuicao anterio do semestre
    # - cria uma nova
    rit = get_object_or_404(PlanoIndividualTrabalho, pk=rit_id)

    if not rit.pode_ajustar_distribuicao_horas_semestre_rit(request.user):
        raise PermissionDenied

    title = f'Ajustar distribuição de horas no semestre relativo ao {rit.get_verbose_rit()}'

    form = AjustarHorasSemestreRitForm(request.POST or None, request=request, rit=rit)
    if form.is_valid():
        rit.desfazer_distribuicao_horas_semestre()

        compensar_automaticamente = form.cleaned_data.get('confirmacao2')
        distribuir_todas = form.cleaned_data.get('confirmacao4')
        ch = form.cleaned_data.get('horas')
        if ch:
            ch = ch.hour * 60 * 60 + ch.minute * 60 + ch.second
        rit.ajustar_distribuicao_horas_semestre_rit(compensar_automaticamente=compensar_automaticamente, ch=ch, distribuir_todas=distribuir_todas)

        url = f'/pgd2/servidor_pgd_horas_detalhes/{rit.id}'
        return httprr(url, 'Distribuição de horas foi desfeita com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def desfazer_distribuicao_horas_semestre(request, rit_id):
    # Desfaz a distribuicao de horas do semestre do rit
    rit = get_object_or_404(PlanoIndividualTrabalho, pk=rit_id)

    if not rit.pode_desfazer_distribuicao_horas_semestre(request.user):
        raise PermissionDenied

    title = f'Desfazer distribuição de horas no semestre relativo ao {rit.get_verbose_rit()}'

    form = DesfazerDistribuirHorasSemestreRitForm(request.POST or None, request=request)
    if form.is_valid():
        rit.desfazer_distribuicao_horas_semestre()
        url = f'/pgd2/servidor_pgd_horas_detalhes/{rit.id}'
        return httprr(url, 'Distribuição de horas foi desfeita com sucesso.')

    return locals()


@rtr()
@permission_required('rh.eh_servidor')
def visualizar_distribuicao_compensacao_especifica(request, rit_id):
    # Tela de visualizaçao das do resumo das compenacoes especificas
    # - apaga a distribuicao anterio do semestre
    # - cria uma nova
    rit = get_object_or_404(PlanoIndividualTrabalho, pk=rit_id)

    if not rit.pode_distribuir_horas(request.user):
        raise PermissionDenied

    title = f'Ajustar distribuição de horas do {rit.get_verbose_rit()} para compensações específicas compensáveis por este {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2}'

    # Lista compensações compensáveis
    compensacoes_compensaveis = obter_compensacoes_especificas_compesaveis_rit(rit)
    compensacoes_especificas_lista = []
    for comp_e in compensacoes_compensaveis:
        pode_ajustar_distribuicao_compensacao_especifica = rit.pode_ajustar_distribuicao_compensacao_especifica(
            request.user, compensacao_especifica=comp_e[0], compensacoes_compensaveis=compensacoes_compensaveis
        )
        pode_desfazer_distribuicao_compensacao_especifica = rit.pode_desfazer_distribuicao_compensacao_especifica(
            request.user, compensacao_especifica=comp_e[0]
        )
        compensacoes_especificas_lista.append(
            {
                'dados': comp_e[0],
                'pode_ajustar_distribuicao_compensacao_especifica': pode_ajustar_distribuicao_compensacao_especifica,
                'pode_desfazer_distribuicao_compensacao_especifica': pode_desfazer_distribuicao_compensacao_especifica,
            }
        )

    return locals()


@transaction.atomic
@permission_required('rh.eh_servidor')
def ajustar_distribuicao_compensacao_especifica(request, rit_id, compesacao_especifica_id):
    # Ajusta manualmente a distribuicao de horas de uma compensação específica
    # - apaga a distribuicao anterior referente a este rit
    # - cria uma nova
    rit = get_object_or_404(PlanoIndividualTrabalho, pk=rit_id)
    if not rit.pode_ajustar_distribuicao_compensacao_especifica(request.user):
        raise PermissionDenied
    compensacao_especifica = get_object_or_404(RecessoOpcaoEscolhida, pk=compesacao_especifica_id)

    rit.ajustar_distribuicao_compensacao_especifica(compensacao_especifica=compensacao_especifica)

    url = f'/pgd2/servidor_pgd_horas_detalhes/{rit.id}'
    return httprr(url, 'Distribuição de horas realizada com sucesso.')


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def desfazer_distribuicao_compensacao_especifica(request, rit_id, compesacao_especifica_id):
    # Desfaz a distribuicao de horas de uma compensação específica
    rit = get_object_or_404(PlanoIndividualTrabalho, pk=rit_id)
    compensacao_especifica = get_object_or_404(RecessoOpcaoEscolhida, pk=compesacao_especifica_id)

    if not rit.pode_desfazer_distribuicao_compensacao_especifica(request.user, compensacao_especifica=compensacao_especifica):
        raise PermissionDenied

    title = f'Desfazer distribuição de horas relativas ao {rit.get_verbose_rit_servidor()} para a compensação específica {compensacao_especifica}'

    form = DesfazerDistribuirHorasCompensacaoEspecificaRitForm(request.POST or None, request=request)
    if form.is_valid():
        rit.desfazer_distribuicao_compensacao_especifica(compensacao_especifica)
        url = f'/pgd2/servidor_pgd_horas_detalhes/{rit.id}'
        return httprr(url, 'Distribuição de horas foi desfeita com sucesso.')

    return locals()


@rtr()
@permission_required('rh.eh_servidor')
def listar_servidores(request):
    """Lista os servidores que possuem alguma solicitação de adesão no PGD.

    Suporta filtros por busca textual (nome/matrícula), setor, campus,
    cargo, jornada e situação via `BuscarServidoresPgdForm`.
    """
    title = 'Servidores'

    lista_servidores = (
        Servidor.objects.vinculados().filter(id__in=SolicitacaoAdesaoServidor.objects.all().values('servidor_id')).order_by('pessoa_fisica__nome')
    )

    form = BuscarServidoresPgdForm(request.GET or None, request=request)
    if form.is_valid():
        buscar_str = form.cleaned_data.get('buscar_str')
        setor = form.cleaned_data.get('setor')
        campus = form.cleaned_data.get('campus')
        cargo_emprego = form.cleaned_data.get('cargo_emprego')
        jornada_trabalho = form.cleaned_data.get('jornada_trabalho')
        situacao = form.cleaned_data.get('situacao')

        if campus:
            lista_servidores = lista_servidores.filter(setor__uo=campus)
        if setor:
            lista_servidores = lista_servidores.filter(setor=setor)

        if cargo_emprego:
            lista_servidores = lista_servidores.filter(cargo_emprego=cargo_emprego)
        if jornada_trabalho:
            lista_servidores = lista_servidores.filter(jornada_trabalho=jornada_trabalho)
        if situacao:
            lista_servidores = lista_servidores.filter(situacao=situacao)
        if buscar_str:
            lista_servidores = lista_servidores.filter(Q(pessoa_fisica__nome__icontains=buscar_str) | Q(matricula__icontains=buscar_str))

    return locals()


@rtr()
@permission_required('rh.eh_servidor')
def listar_setores(request):
    """Lista setores com algum PES aprovado, com filtro opcional por setor."""
    title = 'Setores'

    lista_setores = get_setores_pgd().filter(id__in=PlanoEntregasSetorial.get_pess_aprovados().values('setor_id'))

    form = BuscarSetoresPgdForm(request.GET or None, request=request, setores_chefe=lista_setores)
    if form.is_valid():
        setor = form.cleaned_data.get('setor')
        if setor:
            lista_setores = lista_setores.filter(id=setor.id)

    return locals()


@rtr()
@permission_required('rh.eh_servidor')
def visualizar_setor_pgd(request, setor_id):
    """Ficha pública do setor no PGD (acessada também via QR Code).

    Mostra horários de funcionamento e de planejamento do PES atualmente
    apto, além dos servidores cujo setor de homologação é este.
    """
    setor = get_setores_pgd().filter(id=setor_id).first()
    if not setor:
        raise PermissionDenied

    title = f'{setor} - PGD'

    # Horários atuais
    pes_atual = PlanoEntregasSetorial.get_pes_apto(setor).order_by('periodo_pes__data_inicio').first()
    pes_horarios_funcionamento_setor_agrupado_por_semana = (
        PlanoEntregasSetorialHorarioFuncionamentoSetor.get_horarios_funcionamento_setor_agrupado_por_semana(pes_atual)
    )
    pes_horarios_planejamento_setor_agrupado_por_semana = (
        PlanoEntregasSetorialHorarioPlanejamentoSetor.get_horarios_planejamento_setor_agrupado_por_semana(pes_atual)
    )

    # Servidores em pgd no setor (setor para homologar)
    #   - Link para Meu PGD do servidor)
    lista_adesoes = SolicitacaoAdesaoServidor.get_adesoes_vigentes().filter(servidor__setor=setor).order_by('servidor__pessoa_fisica__nome')

    # Lista de PESs do setor
    lista_pess = PlanoEntregasSetorial.get_pes_apto(setor).order_by('periodo_pes__data_inicio')

    return locals()


# ----------------------------------------------
# RELATORIOS e OUTROS
# ----------------------------------------------


@rtr()
@permission_required(['pgd2.gestao_pgd2', 'pgd2.gestao_pgd2_comissao_sistemica', 'pgd2.gestao_pgd2_comissao_local'])
def relatorio_participantes_percentual_quadro_geral(request):
    """
    DESCRICAO: Relatorio dos participantes. Por categoria e campus.
    Relatorio
    - Filtros
      - Data de hoje
    - Dados
      - Servidores que estao atualmente no PGD
      - Por campus
      - Variacao em relacao ao quadro de pessoal
    """

    estah_em_gestao_pgd = request.user.has_group_cached('Gestor do PGD 2')
    estah_em_comissao_sistemica_vigente = request.user.has_group_cached('Comissão Sistêmica PGD 2')
    estah_em_comissao_local_vigente = request.user.has_group_cached('Comissão Local PGD 2')

    if not (estah_em_gestao_pgd or estah_em_comissao_sistemica_vigente or estah_em_comissao_local_vigente):
        raise PermissionDenied

    title = 'Relatório de Servidores do PGD (Por categoria e campus)'

    lista_quadro_consolidado = []
    dict_dados_quadro_consolidado = {}

    lista_campis = []
    lista_quadro_campus = []
    dict_dados_quadro_por_campus = {}
    dict_dados_campus = {}

    # ---------------------------
    # Dados iniciais
    # ---------------------------
    servidores_ifrn = Servidor.objects.vinculados()
    servidores_ifrn_tae = Servidor.objects.tecnicos_administrativos()
    servidores_ifrn_docentes = Servidor.objects.docentes()
    servidores_ifrn_estagiarios = Servidor.objects.estagiarios()

    servidores_pgd = SolicitacaoAdesaoServidor.get_servidores_em_pgd()

    servidores_pgd_tae = servidores_pgd.tecnicos_administrativos()
    servidores_pgd_docente = servidores_pgd.docentes()
    servidores_pgd_estagiarios = servidores_pgd.estagiarios()

    campis = UnidadeOrganizacional.objects.uo()

    def calcula_percentual(parte, total):
        if total > 0:
            p = (parte / total) * 100
            return round(p, 2)
        return 0

    # ---------------------------
    # Dados sistêmicos
    # ---------------------------
    dict_dados_quadro_consolidado = {}
    dict_dados_quadro_consolidado['descricao'] = '1 - NÚMERO DE COLABORADORES DO IFRN'
    dict_dados_quadro_consolidado['qtd'] = servidores_ifrn.count()
    lista_quadro_consolidado.append(dict_dados_quadro_consolidado)
    #
    dict_dados_quadro_consolidado = {}
    dict_dados_quadro_consolidado['descricao'] = '1.1 - TÉCNICO ADMINISTRATIVO'
    dict_dados_quadro_consolidado['qtd'] = servidores_ifrn_tae.count()
    dict_dados_quadro_consolidado['percentual_sobre_total'] = calcula_percentual(
        servidores_ifrn_tae.count(), servidores_ifrn.count()
    )  # % EM RELAÇÃO AO TOTAL A 1
    lista_quadro_consolidado.append(dict_dados_quadro_consolidado)
    #
    dict_dados_quadro_consolidado = {}
    dict_dados_quadro_consolidado['descricao'] = '1.2 - DOCENTE'
    dict_dados_quadro_consolidado['qtd'] = servidores_ifrn_docentes.count()
    dict_dados_quadro_consolidado['percentual_sobre_total'] = calcula_percentual(
        servidores_ifrn_docentes.count(), servidores_ifrn.count()
    )  # % EM RELAÇÃO AO TOTAL A 1
    lista_quadro_consolidado.append(dict_dados_quadro_consolidado)
    #
    dict_dados_quadro_consolidado = {}
    dict_dados_quadro_consolidado['descricao'] = '1.3 - ESTAGIÁRIO'
    dict_dados_quadro_consolidado['qtd'] = servidores_ifrn_estagiarios.count()
    dict_dados_quadro_consolidado['percentual_sobre_total'] = calcula_percentual(
        servidores_ifrn_estagiarios.count(), servidores_ifrn.count()
    )  # % EM RELAÇÃO AO TOTAL A 1
    lista_quadro_consolidado.append(dict_dados_quadro_consolidado)
    #
    dict_dados_quadro_consolidado = {}
    dict_dados_quadro_consolidado['descricao'] = '2 - NÚMERO DE COLABORADORES ESTÃO EM PGD (APENAS DADOS DO SUAP)'
    dict_dados_quadro_consolidado['qtd'] = servidores_pgd.count()
    dict_dados_quadro_consolidado['percentual_sobre_total'] = calcula_percentual(
        servidores_pgd.count(), servidores_ifrn.count()
    )  # % EM RELAÇÃO AO TOTAL A 1
    lista_quadro_consolidado.append(dict_dados_quadro_consolidado)
    #
    dict_dados_quadro_consolidado = {}
    dict_dados_quadro_consolidado['descricao'] = '2.1 - TÉCNICO ADMINISTRATIVO'
    dict_dados_quadro_consolidado['qtd'] = servidores_pgd_tae.count()
    dict_dados_quadro_consolidado['percentual_sobre_total'] = calcula_percentual(
        servidores_pgd_tae.count(), servidores_pgd.count()
    )  # % EM RELAÇÃO AO TOTAL A 2
    lista_quadro_consolidado.append(dict_dados_quadro_consolidado)
    #
    dict_dados_quadro_consolidado = {}
    dict_dados_quadro_consolidado['descricao'] = '2.2 - DOCENTE'
    dict_dados_quadro_consolidado['qtd'] = servidores_pgd_docente.count()
    dict_dados_quadro_consolidado['percentual_sobre_total'] = calcula_percentual(
        servidores_pgd_docente.count(), servidores_pgd.count()
    )  # % EM RELAÇÃO AO TOTAL A 2
    lista_quadro_consolidado.append(dict_dados_quadro_consolidado)
    #
    dict_dados_quadro_consolidado = {}
    dict_dados_quadro_consolidado['descricao'] = '2.3 - ESTAGIÁRIO'
    dict_dados_quadro_consolidado['qtd'] = servidores_pgd_estagiarios.count()
    dict_dados_quadro_consolidado['percentual_sobre_total'] = calcula_percentual(
        servidores_pgd_estagiarios.count(), servidores_pgd.count()
    )  # % EM RELAÇÃO AO TOTAL A 2
    lista_quadro_consolidado.append(dict_dados_quadro_consolidado)

    # ---------------------------
    # Dados por campus
    # ---------------------------
    for campus in campis:
        dict_dados_quadro_por_campus = {}
        dict_dados_quadro_por_campus['descricao'] = '1 - NÚMERO DE COLABORADORES DO CAMPUS'
        dict_dados_quadro_por_campus['qtd'] = servidores_ifrn.filter(setor__uo=campus).count()
        lista_quadro_campus.append(dict_dados_quadro_por_campus)
        #
        dict_dados_quadro_por_campus = {}
        dict_dados_quadro_por_campus['descricao'] = '1.1 - TÉCNICO ADMINISTRATIVO'
        dict_dados_quadro_por_campus['qtd'] = servidores_ifrn_tae.filter(setor__uo=campus).count()
        dict_dados_quadro_por_campus['percentual_sobre_total'] = calcula_percentual(
            servidores_ifrn_tae.filter(setor__uo=campus).count(), servidores_ifrn.filter(setor__uo=campus).count()
        )  # % EM RELAÇÃO AO TOTAL A 1
        lista_quadro_campus.append(dict_dados_quadro_por_campus)
        #
        dict_dados_quadro_por_campus = {}
        dict_dados_quadro_por_campus['descricao'] = '1.2 - DOCENTE'
        dict_dados_quadro_por_campus['qtd'] = servidores_ifrn_docentes.filter(setor__uo=campus).count()
        dict_dados_quadro_por_campus['percentual_sobre_total'] = calcula_percentual(
            servidores_ifrn_docentes.filter(setor__uo=campus).count(), servidores_ifrn.filter(setor__uo=campus).count()
        )  # % EM RELAÇÃO AO TOTAL A 1
        lista_quadro_campus.append(dict_dados_quadro_por_campus)
        #
        dict_dados_quadro_por_campus = {}
        dict_dados_quadro_por_campus['descricao'] = '1.3 - ESTAGIÁRIO'
        dict_dados_quadro_por_campus['qtd'] = servidores_ifrn_estagiarios.filter(setor__uo=campus).count()
        dict_dados_quadro_por_campus['percentual_sobre_total'] = calcula_percentual(
            servidores_ifrn_estagiarios.filter(setor__uo=campus).count(), servidores_ifrn.filter(setor__uo=campus).count()
        )  # % EM RELAÇÃO AO TOTAL A 1
        lista_quadro_campus.append(dict_dados_quadro_por_campus)
        #
        dict_dados_quadro_por_campus = {}
        dict_dados_quadro_por_campus['descricao'] = '2 - NÚMERO DE COLABORADORES ESTÃO EM PGD (APENAS DADOS DO SUAP)'
        dict_dados_quadro_por_campus['qtd'] = servidores_pgd.filter(setor__uo=campus).count()
        dict_dados_quadro_por_campus['percentual_sobre_total'] = calcula_percentual(
            servidores_pgd.filter(setor__uo=campus).count(), servidores_ifrn.filter(setor__uo=campus).count()
        )  # % EM RELAÇÃO AO TOTAL A 1
        lista_quadro_campus.append(dict_dados_quadro_por_campus)
        #
        dict_dados_quadro_por_campus = {}
        dict_dados_quadro_por_campus['descricao'] = '2.1 - TÉCNICO ADMINISTRATIVO'
        dict_dados_quadro_por_campus['qtd'] = servidores_pgd_tae.filter(setor__uo=campus).count()
        dict_dados_quadro_por_campus['percentual_sobre_total'] = calcula_percentual(
            servidores_pgd_tae.filter(setor__uo=campus).count(), servidores_pgd.filter(setor__uo=campus).count()
        )  # % EM RELAÇÃO AO TOTAL A 2
        lista_quadro_campus.append(dict_dados_quadro_por_campus)
        #
        dict_dados_quadro_por_campus = {}
        dict_dados_quadro_por_campus['descricao'] = '2.2 - DOCENTE'
        dict_dados_quadro_por_campus['qtd'] = servidores_pgd_docente.filter(setor__uo=campus).count()
        dict_dados_quadro_por_campus['percentual_sobre_total'] = calcula_percentual(
            servidores_pgd_docente.filter(setor__uo=campus).count(), servidores_pgd.filter(setor__uo=campus).count()
        )  # % EM RELAÇÃO AO TOTAL A 2
        lista_quadro_campus.append(dict_dados_quadro_por_campus)
        #
        dict_dados_quadro_por_campus = {}
        dict_dados_quadro_por_campus['descricao'] = '2.3 - ESTAGIÁRIO'
        dict_dados_quadro_por_campus['qtd'] = servidores_pgd_estagiarios.filter(setor__uo=campus).count()
        dict_dados_quadro_por_campus['percentual_sobre_total'] = calcula_percentual(
            servidores_pgd_estagiarios.filter(setor__uo=campus).count(), servidores_pgd.filter(setor__uo=campus).count()
        )  # % EM RELAÇÃO AO TOTAL A 2
        lista_quadro_campus.append(dict_dados_quadro_por_campus)
        #
        dict_dados_campus = {}
        dict_dados_campus['campus'] = campus
        dict_dados_campus['dados'] = lista_quadro_campus
        lista_campis.append(dict_dados_campus)
        lista_quadro_campus = []

    return locals()


@rtr()
@permission_required(['pgd2.gestao_pgd2', 'pgd2.gestao_pgd2_comissao_sistemica'])
def relatorio_rits_a_menor(request):
    """
    DESCRICAO: Relatorio dos rits entregues com CH menor que a meta
    Relatorio
    - Filtros
      - Periodo de mês
    - Dados
      - Qtds
        - Por campus
        - Por categoria
      - Entregues
      - Entregues menor que a meta
    """
    estah_em_gestao_pgd = request.user.has_group_cached('Gestor do PGD 2')
    estah_em_comissao_sistemica_vigente = request.user.has_group_cached('Comissão Sistêmica PGD 2')
    estah_em_comissao_local_vigente = request.user.has_group_cached('Comissão Local PGD 2')

    if not (estah_em_gestao_pgd or estah_em_comissao_sistemica_vigente or estah_em_comissao_local_vigente):
        raise PermissionDenied

    title = f'Relatório de {nomenclatura.relatorio_individual_de_trabalho_sigla_plural_pgd2} entregues com horas menor que o planejado'

    mes_ini = None
    ano_ini = None
    mes_fim = None
    ano_fim = None
    form = BuscarRelatorioDesligamentoForm(request.GET or None)
    if form.is_valid():
        mes_ini = int(form.cleaned_data.get('mes_ini'))
        ano_ini = int(form.cleaned_data.get('ano_ini').ano)
        mes_fim = int(form.cleaned_data.get('mes_fim'))
        ano_fim = int(form.cleaned_data.get('ano_fim').ano)

        # Obtendo os periodos conforme periodo inicial e final passados como parametro
        data_inicio = date(ano_ini, mes_ini, 1)
        data_final = date(ano_fim, mes_fim, 1)
        periodos = []
        if data_inicio and data_final:
            if data_inicio == data_final:
                periodos.append(data_inicio)
            else:
                parar = False
                d = data_inicio
                periodos.append(d)
                while not parar:
                    d = d + relativedelta(months=1)
                    periodos.append(d)
                    if d.month == data_final.month and d.year == data_final.year:
                        parar = True

        lista_dados_periodo = []
        lista_dados = []
        dict_consolidado_uos = {}

        rits_homologados = PlanoIndividualTrabalho.get_rits_homologados_todos()
        taes = Servidor.objects.vinculados().tecnicos_administrativos()
        docentes = Servidor.objects.vinculados().docentes()
        estagiarios = Servidor.objects.vinculados().estagiarios()
        campis = UnidadeOrganizacional.objects.uo()

        # Estruturas de somatório
        dict_consolidado = {
            'ifrn_entregues': 0,
            'ifrn_entregues_abaixo_da_meta': 0,
            'tae_entregues': 0,
            'tae_entregues_abaixo_da_meta': 0,
            'docente_entregues': 0,
            'docente_entregues_abaixo_da_meta': 0,
            'estagiario_entregues': 0,
            'estagiario_entregues_abaixo_da_meta': 0,
        }

        for campus in campis:
            dict_consolidado_uos[campus.sigla] = {
                'ifrn_entregues': 0,
                'ifrn_entregues_abaixo_da_meta': 0,
                'tae_entregues': 0,
                'tae_entregues_abaixo_da_meta': 0,
                'docente_entregues': 0,
                'docente_entregues_abaixo_da_meta': 0,
                'estagiario_entregues': 0,
                'estagiario_entregues_abaixo_da_meta': 0,
            }

        for periodo in periodos:
            lista_dados = []

            # rits_homologados_periodo = RegistroAcaoRelatorioIndividualTrabalho.objects.filter(data__month=periodo.month, data__year=periodo.year, tipo=RegistroAcaoRelatorioIndividualTrabalho.TIPO_APROVOU_HOMOLOGOU_RIT).values_list('rit_id')
            rits_homologados_periodo = RegistroAcaoPlanoIndividualTrabalho.objects.filter(
                data__month=periodo.month, data__year=periodo.year, tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_HOMOLOGOU_RIT
            ).values_list('pit_id')

            # ---------------------------
            # Dados por periodo
            # ---------------------------
            dict_dados = {}
            dict_dados['descricao'] = '1 - COLABORADORES DO IFRN'
            dict_dados['entregues'] = rits_homologados_periodo.count()
            dict_dados['entregues_abaixo_da_meta'] = rits_homologados_periodo.filter(
                pit__tempo_planejado_total__gt=F('pit__tempo_executado_homologado_total')
            ).count()
            lista_dados.append(dict_dados)
            dict_consolidado['ifrn_entregues'] += dict_dados['entregues']
            dict_consolidado['ifrn_entregues_abaixo_da_meta'] += dict_dados['entregues_abaixo_da_meta']

            dict_dados = {}
            dict_dados['descricao'] = '1.1 - TÉCNICO ADMINISTRATIVO'
            dict_dados['entregues'] = rits_homologados_periodo.filter(pit__adesao__servidor__in=taes).count()
            dict_dados['entregues_abaixo_da_meta'] = rits_homologados_periodo.filter(
                pit__tempo_planejado_total__gt=F('pit__tempo_executado_homologado_total'), pit__adesao__servidor__in=taes
            ).count()
            lista_dados.append(dict_dados)
            dict_consolidado['tae_entregues'] += dict_dados['entregues']
            dict_consolidado['tae_entregues_abaixo_da_meta'] += dict_dados['entregues_abaixo_da_meta']

            dict_dados = {}
            dict_dados['descricao'] = '1.2 - DOCENTE'
            dict_dados['entregues'] = rits_homologados_periodo.filter(pit__adesao__servidor__in=docentes).count()
            dict_dados['entregues_abaixo_da_meta'] = rits_homologados_periodo.filter(
                pit__tempo_planejado_total__gt=F('pit__tempo_executado_homologado_total'), pit__adesao__servidor__in=docentes
            ).count()
            lista_dados.append(dict_dados)
            dict_consolidado['docente_entregues'] += dict_dados['entregues']
            dict_consolidado['docente_entregues_abaixo_da_meta'] += dict_dados['entregues_abaixo_da_meta']

            dict_dados = {}
            dict_dados['descricao'] = '1.3 - ESTAGIÁRIO'
            dict_dados['entregues'] = rits_homologados_periodo.filter(pit__adesao__servidor__in=estagiarios).count()
            dict_dados['entregues_abaixo_da_meta'] = rits_homologados_periodo.filter(
                pit__tempo_planejado_total__gt=F('pit__tempo_executado_homologado_total'), pit__adesao__servidor__in=estagiarios
            ).count()
            lista_dados.append(dict_dados)
            dict_consolidado['estagiario_entregues'] += dict_dados['entregues']
            dict_consolidado['estagiario_entregues_abaixo_da_meta'] += dict_dados['entregues_abaixo_da_meta']

            dict_dados_periodo = {}
            dict_dados_periodo['periodo'] = f'{periodo.month}/{periodo.year}'
            dict_dados_periodo['dados'] = lista_dados
            # lista_dados_periodo.append(dict_dados_periodo)

            # Por campus
            # --------------------
            for campus in campis:
                dict_dados = {}
                dict_dados['descricao'] = campus
                lista_dados.append(dict_dados)

                dict_dados = {}
                dict_dados['descricao'] = '1 - COLABORADORES DO CAMPUS'
                dict_dados['entregues'] = rits_homologados_periodo.filter(pit__adesao__servidor__setor__uo=campus).count()
                dict_dados['entregues_abaixo_da_meta'] = rits_homologados_periodo.filter(
                    pit__tempo_planejado_total__gt=F('pit__tempo_executado_homologado_total'), pit__adesao__servidor__setor__uo=campus
                ).count()
                lista_dados.append(dict_dados)
                dict_consolidado_uos[campus.sigla]['ifrn_entregues'] += dict_dados['entregues']
                dict_consolidado_uos[campus.sigla]['ifrn_entregues_abaixo_da_meta'] += dict_dados['entregues_abaixo_da_meta']

                dict_dados = {}
                dict_dados['descricao'] = '1.1 - TÉCNICO ADMINISTRATIVO'
                dict_dados['entregues'] = rits_homologados_periodo.filter(
                    pit__adesao__servidor__in=taes, pit__adesao__servidor__setor__uo=campus
                ).count()
                dict_dados['entregues_abaixo_da_meta'] = rits_homologados_periodo.filter(
                    pit__tempo_planejado_total__gt=F('pit__tempo_executado_homologado_total'),
                    pit__adesao__servidor__in=taes,
                    pit__adesao__servidor__setor__uo=campus,
                ).count()
                lista_dados.append(dict_dados)
                dict_consolidado_uos[campus.sigla]['tae_entregues'] += dict_dados['entregues']
                dict_consolidado_uos[campus.sigla]['tae_entregues_abaixo_da_meta'] += dict_dados['entregues_abaixo_da_meta']

                dict_dados = {}
                dict_dados['descricao'] = '1.2 - DOCENTE'
                dict_dados['entregues'] = rits_homologados_periodo.filter(
                    pit__adesao__servidor__in=docentes, pit__adesao__servidor__setor__uo=campus
                ).count()
                dict_dados['entregues_abaixo_da_meta'] = rits_homologados_periodo.filter(
                    pit__tempo_planejado_total__gt=F('pit__tempo_executado_homologado_total'),
                    pit__adesao__servidor__in=docentes,
                    pit__adesao__servidor__setor__uo=campus,
                ).count()
                lista_dados.append(dict_dados)
                dict_consolidado_uos[campus.sigla]['docente_entregues'] += dict_dados['entregues']
                dict_consolidado_uos[campus.sigla]['docente_entregues_abaixo_da_meta'] += dict_dados['entregues_abaixo_da_meta']

                dict_dados = {}
                dict_dados['descricao'] = '1.3 - ESTAGIÁRIO'
                dict_dados['entregues'] = rits_homologados_periodo.filter(
                    pit__adesao__servidor__in=estagiarios, pit__adesao__servidor__setor__uo=campus
                ).count()
                dict_dados['entregues_abaixo_da_meta'] = rits_homologados_periodo.filter(
                    pit__tempo_planejado_total__gt=F('pit__tempo_executado_homologado_total'),
                    pit__adesao__servidor__in=estagiarios,
                    pit__adesao__servidor__setor__uo=campus,
                ).count()
                lista_dados.append(dict_dados)
                dict_consolidado_uos[campus.sigla]['estagiario_entregues'] += dict_dados['entregues']
                dict_consolidado_uos[campus.sigla]['estagiario_entregues_abaixo_da_meta'] += dict_dados['entregues_abaixo_da_meta']

            dict_dados_periodo = {}
            dict_dados_periodo['periodo'] = f'{periodo.month}/{periodo.year}'
            dict_dados_periodo['dados'] = lista_dados
            lista_dados_periodo.append(dict_dados_periodo)

        # ---------------------------
        # Dados consolidados do periodo
        # ---------------------------
        lista_dados = []

        dict_dados = {}
        dict_dados['descricao'] = '1 - COLABORADORES DO IFRN'
        dict_dados['entregues'] = dict_consolidado['ifrn_entregues']
        dict_dados['entregues_abaixo_da_meta'] = dict_consolidado['ifrn_entregues_abaixo_da_meta']
        lista_dados.append(dict_dados)

        dict_dados = {}
        dict_dados['descricao'] = '1.1 - TÉCNICO ADMINISTRATIVO'
        dict_dados['entregues'] = dict_consolidado['tae_entregues']
        dict_dados['entregues_abaixo_da_meta'] = dict_consolidado['tae_entregues_abaixo_da_meta']
        lista_dados.append(dict_dados)

        dict_dados = {}
        dict_dados['descricao'] = '1.2 - DOCENTE'
        dict_dados['entregues'] = dict_consolidado['docente_entregues']
        dict_dados['entregues_abaixo_da_meta'] = dict_consolidado['docente_entregues_abaixo_da_meta']
        lista_dados.append(dict_dados)

        dict_dados = {}
        dict_dados['descricao'] = '1.3 - ESTAGIÁRIO'
        dict_dados['entregues'] = dict_consolidado['estagiario_entregues']
        dict_dados['entregues_abaixo_da_meta'] = dict_consolidado['estagiario_entregues_abaixo_da_meta']
        lista_dados.append(dict_dados)

        # Por campus
        # --------------------
        for campus in campis:
            dict_dados = {}
            dict_dados['descricao'] = campus
            lista_dados.append(dict_dados)

            dict_dados = {}
            dict_dados['descricao'] = '1 - COLABORADORES DO CAMPUS'
            dict_dados['entregues'] = dict_consolidado_uos[campus.sigla]['ifrn_entregues']
            dict_dados['entregues_abaixo_da_meta'] = dict_consolidado_uos[campus.sigla]['ifrn_entregues_abaixo_da_meta']
            lista_dados.append(dict_dados)

            dict_dados = {}
            dict_dados['descricao'] = '1.1 - TÉCNICO ADMINISTRATIVO'
            dict_dados['entregues'] = dict_consolidado_uos[campus.sigla]['tae_entregues']
            dict_dados['entregues_abaixo_da_meta'] = dict_consolidado_uos[campus.sigla]['tae_entregues_abaixo_da_meta']
            lista_dados.append(dict_dados)

            dict_dados = {}
            dict_dados['descricao'] = '1.2 - DOCENTE'
            dict_dados['entregues'] = dict_consolidado_uos[campus.sigla]['docente_entregues']
            dict_dados['entregues_abaixo_da_meta'] = dict_consolidado_uos[campus.sigla]['docente_entregues_abaixo_da_meta']
            lista_dados.append(dict_dados)

            dict_dados = {}
            dict_dados['descricao'] = '1.3 - ESTAGIÁRIO'
            dict_dados['entregues'] = dict_consolidado_uos[campus.sigla]['estagiario_entregues']
            dict_dados['entregues_abaixo_da_meta'] = dict_consolidado_uos[campus.sigla]['estagiario_entregues_abaixo_da_meta']
            lista_dados.append(dict_dados)

        dict_dados_periodo = {}
        dict_dados_periodo['periodo'] = 'Consolidado'
        dict_dados_periodo['dados'] = lista_dados
        lista_dados_periodo.append(dict_dados_periodo)

    return locals()


@rtr()
@permission_required(['pgd2.gestao_pgd2', 'pgd2.gestao_pgd2_comissao_sistemica'])
def relatorio_rotatividade_forca_trabalho(request):
    """
    DESCRICAO: Relatorio de rotativiade de força de trabalho
    Relatorio
    - Filtros
      - Periodo de mês
    - Dados por período e categoria
      - Qtds
        - Rotatividade Interna no campus
        - Rotatividade para outro campus
    """

    estah_em_gestao_pgd = request.user.has_group_cached('Gestor do PGD 2')
    estah_em_comissao_sistemica_vigente = request.user.has_group_cached('Comissão Sistêmica PGD 2')
    estah_em_comissao_local_vigente = request.user.has_group_cached('Comissão Local PGD 2')

    if not (estah_em_gestao_pgd or estah_em_comissao_sistemica_vigente or estah_em_comissao_local_vigente):
        raise PermissionDenied

    title = 'Relatório de rotatividade de força de trabalho'

    mes_ini = None
    ano_ini = None
    mes_fim = None
    ano_fim = None
    form = BuscarRelatorioDesligamentoForm(request.GET or None)
    if form.is_valid():
        mes_ini = int(form.cleaned_data.get('mes_ini'))
        ano_ini = int(form.cleaned_data.get('ano_ini').ano)
        mes_fim = int(form.cleaned_data.get('mes_fim'))
        ano_fim = int(form.cleaned_data.get('ano_fim').ano)

        # -----------------------------
        # Dados iniciais
        # -----------------------------
        campis = UnidadeOrganizacional.objects.uo()
        # campis = UnidadeOrganizacional.objects.all()

        # Obtendo os periodos conforme periodo inicial e final passados como parametro
        # -----------------------------
        data_inicio = date(ano_ini, mes_ini, 1)
        data_final = date(ano_fim, mes_fim, 1)
        periodos = []
        if data_inicio and data_final:
            if data_inicio == data_final:
                periodos.append(data_inicio)
            else:
                parar = False
                d = data_inicio
                periodos.append(d)
                while not parar:
                    d = d + relativedelta(months=1)
                    periodos.append(d)
                    if d.month == data_final.month and d.year == data_final.year:
                        parar = True

        # -----------------------------
        # Estruturas de somatório
        # -----------------------------
        lista_dados_periodo = []
        lista_dados = []
        dict_consolidado_uos = {}
        dict_calculo_uos = {}

        dict_consolidado = {
            'ifrn_rotatividade_interna': 0,
            'ifrn_rotatividade_externa': 0,
            'taes_rotatividade_interna': 0,
            'taes_rotatividade_externa': 0,
            'docentes_rotatividade_interna': 0,
            'docentes_rotatividade_externa': 0,
            'estagiarios_rotatividade_interna': 0,
            'estagiarios_rotatividade_externa': 0,
        }

        for campus in campis:
            dict_consolidado_uos[campus.sigla] = {
                'ifrn_rotatividade_interna': 0,
                'ifrn_rotatividade_externa': 0,
                'taes_rotatividade_interna': 0,
                'taes_rotatividade_externa': 0,
                'docentes_rotatividade_interna': 0,
                'docentes_rotatividade_externa': 0,
                'estagiarios_rotatividade_interna': 0,
                'estagiarios_rotatividade_externa': 0,
            }
            dict_calculo_uos[campus.sigla] = {
                'ifrn_rotatividade_interna': 0,
                'ifrn_rotatividade_externa': 0,
                'taes_rotatividade_interna': 0,
                'taes_rotatividade_externa': 0,
                'docentes_rotatividade_interna': 0,
                'docentes_rotatividade_externa': 0,
                'estagiarios_rotatividade_interna': 0,
                'estagiarios_rotatividade_externa': 0,
            }

        # -----------------------------
        # Obtendo dados e gerando o relatório
        # -----------------------------
        def get_rotatividade_por_categoria_periodo(mes, ano):
            ifrn_rotatividade_interna = 0
            ifrn_rotatividade_externa = 0
            taes_rotatividade_interna = 0
            taes_rotatividade_externa = 0
            docentes_rotatividade_interna = 0
            docentes_rotatividade_externa = 0
            estagiarios_rotatividade_interna = 0
            estagiarios_rotatividade_externa = 0

            # Busca as motivomentacoes do periodo
            movimentacoes_de_setor = ServidorSetorLotacaoHistorico.objects.filter(data_fim_setor_lotacao__month=mes, data_fim_setor_lotacao__year=ano)
            for movimentacao_saida in movimentacoes_de_setor:
                # Para cada movimentacao busca o par
                # - Para cada mudanca de setor precisa de uma entrada para o dia imediatamente posterior a saída
                data_inicio_chegada = movimentacao_saida.data_fim_setor_lotacao + relativedelta(days=1)
                movimentacao_chegada = ServidorSetorLotacaoHistorico.objects.filter(
                    servidor=movimentacao_saida.servidor, data_inicio_setor_lotacao=data_inicio_chegada
                ).last()
                # Se teve movimentacao de fato temos que saber
                # - Qual foi a categoria (docente, tae e estagiario)
                # - Se foi rotatividade no mesmo campus ou se foi pra outro campus
                if movimentacao_chegada:
                    if movimentacao_chegada.servidor.eh_tecnico_administrativo:
                        if movimentacao_saida.setor_lotacao.uo == movimentacao_chegada.setor_lotacao.uo:
                            taes_rotatividade_interna += 1
                            if dict_calculo_uos.get(movimentacao_saida.setor_lotacao.uo.sigla):
                                dict_calculo_uos[movimentacao_saida.setor_lotacao.uo.sigla]['taes_rotatividade_interna'] += 1
                                dict_calculo_uos[movimentacao_saida.setor_lotacao.uo.sigla]['ifrn_rotatividade_interna'] += 1
                        else:
                            taes_rotatividade_externa += 1
                            if dict_calculo_uos.get(movimentacao_saida.setor_lotacao.uo.sigla):
                                dict_calculo_uos[movimentacao_saida.setor_lotacao.uo.sigla]['taes_rotatividade_externa'] += 1
                                dict_calculo_uos[movimentacao_saida.setor_lotacao.uo.sigla]['ifrn_rotatividade_externa'] += 1
                    elif movimentacao_chegada.servidor.eh_docente:
                        if movimentacao_saida.setor_lotacao.uo == movimentacao_chegada.setor_lotacao.uo:
                            docentes_rotatividade_interna += 1
                            if dict_calculo_uos.get(movimentacao_saida.setor_lotacao.uo.sigla):
                                dict_calculo_uos[movimentacao_saida.setor_lotacao.uo.sigla]['docentes_rotatividade_interna'] += 1
                                dict_calculo_uos[movimentacao_saida.setor_lotacao.uo.sigla]['ifrn_rotatividade_interna'] += 1
                        else:
                            docentes_rotatividade_externa += 1
                            if dict_calculo_uos.get(movimentacao_saida.setor_lotacao.uo.sigla):
                                dict_calculo_uos[movimentacao_saida.setor_lotacao.uo.sigla]['docentes_rotatividade_externa'] += 1
                                dict_calculo_uos[movimentacao_saida.setor_lotacao.uo.sigla]['ifrn_rotatividade_externa'] += 1
                    elif movimentacao_chegada.servidor.eh_estagiario:
                        if movimentacao_saida.setor_lotacao.uo == movimentacao_chegada.setor_lotacao.uo:
                            estagiarios_rotatividade_interna += 1
                            if dict_calculo_uos.get(movimentacao_saida.setor_lotacao.uo.sigla):
                                dict_calculo_uos[movimentacao_saida.setor_lotacao.uo.sigla]['estagiarios_rotatividade_interna'] += 1
                                dict_calculo_uos[movimentacao_saida.setor_lotacao.uo.sigla]['ifrn_rotatividade_interna'] += 1
                        else:
                            estagiarios_rotatividade_externa += 1
                            if dict_calculo_uos.get(movimentacao_saida.setor_lotacao.uo.sigla):
                                dict_calculo_uos[movimentacao_saida.setor_lotacao.uo.sigla]['estagiarios_rotatividade_externa'] += 1
                                dict_calculo_uos[movimentacao_saida.setor_lotacao.uo.sigla]['ifrn_rotatividade_externa'] += 1

            ifrn_rotatividade_interna = taes_rotatividade_interna + docentes_rotatividade_interna + estagiarios_rotatividade_interna
            ifrn_rotatividade_externa = taes_rotatividade_externa + docentes_rotatividade_externa + estagiarios_rotatividade_externa

            return locals()

        for periodo in periodos:
            lista_dados = []
            dados_rotatividade = get_rotatividade_por_categoria_periodo(mes=periodo.month, ano=periodo.year)

            # Dados por periodo
            # ---------------------------
            dict_dados = {}
            dict_dados['descricao'] = '1 - COLABORADORES DO IFRN'
            dict_dados['interno'] = dados_rotatividade.get('ifrn_rotatividade_interna')
            dict_dados['externo'] = dados_rotatividade.get('ifrn_rotatividade_externa')
            lista_dados.append(dict_dados)
            dict_consolidado['ifrn_rotatividade_interna'] += dict_dados['interno']
            dict_consolidado['ifrn_rotatividade_externa'] += dict_dados['externo']

            dict_dados = {}
            dict_dados['descricao'] = '1.1 - TÉCNICO ADMINISTRATIVO'
            dict_dados['interno'] = dados_rotatividade.get('taes_rotatividade_interna')
            dict_dados['externo'] = dados_rotatividade.get('taes_rotatividade_externa')
            lista_dados.append(dict_dados)
            dict_consolidado['taes_rotatividade_interna'] += dict_dados['interno']
            dict_consolidado['taes_rotatividade_externa'] += dict_dados['externo']

            dict_dados = {}
            dict_dados['descricao'] = '1.2 - DOCENTE'
            dict_dados['interno'] = dados_rotatividade.get('docentes_rotatividade_interna')
            dict_dados['externo'] = dados_rotatividade.get('docentes_rotatividade_externa')
            lista_dados.append(dict_dados)
            dict_consolidado['docentes_rotatividade_interna'] += dict_dados['interno']
            dict_consolidado['docentes_rotatividade_externa'] += dict_dados['externo']

            dict_dados = {}
            dict_dados['descricao'] = '1.3 - ESTAGIÁRIO'
            dict_dados['interno'] = dados_rotatividade.get('estagiarios_rotatividade_interna')
            dict_dados['externo'] = dados_rotatividade.get('estagiarios_rotatividade_externa')
            lista_dados.append(dict_dados)
            dict_consolidado['estagiarios_rotatividade_interna'] += dict_dados['interno']
            dict_consolidado['estagiarios_rotatividade_externa'] += dict_dados['externo']

            # Por campus
            # --------------------
            for campus in campis:
                dict_dados = {}
                dict_dados['descricao'] = campus
                lista_dados.append(dict_dados)

                dict_dados = {}
                dict_dados['descricao'] = '1 - COLABORADORES DO CAMPUS'
                dict_dados['interno'] = dict_calculo_uos[campus.sigla]['ifrn_rotatividade_interna']
                dict_dados['externo'] = dict_calculo_uos[campus.sigla]['ifrn_rotatividade_externa']
                lista_dados.append(dict_dados)
                dict_consolidado_uos[campus.sigla]['ifrn_rotatividade_interna'] += dict_dados['interno']
                dict_consolidado_uos[campus.sigla]['ifrn_rotatividade_externa'] += dict_dados['externo']

                dict_dados = {}
                dict_dados['descricao'] = '1.1 - TÉCNICO ADMINISTRATIVO'
                dict_dados['interno'] = dict_calculo_uos[campus.sigla]['taes_rotatividade_interna']
                dict_dados['externo'] = dict_calculo_uos[campus.sigla]['taes_rotatividade_externa']
                lista_dados.append(dict_dados)
                dict_consolidado_uos[campus.sigla]['taes_rotatividade_interna'] += dict_dados['interno']
                dict_consolidado_uos[campus.sigla]['taes_rotatividade_externa'] += dict_dados['externo']

                dict_dados = {}
                dict_dados['descricao'] = '1.2 - DOCENTE'
                dict_dados['interno'] = dict_calculo_uos[campus.sigla]['docentes_rotatividade_interna']
                dict_dados['externo'] = dict_calculo_uos[campus.sigla]['docentes_rotatividade_externa']
                lista_dados.append(dict_dados)
                dict_consolidado_uos[campus.sigla]['docentes_rotatividade_interna'] += dict_dados['interno']
                dict_consolidado_uos[campus.sigla]['docentes_rotatividade_externa'] += dict_dados['externo']

                dict_dados = {}
                dict_dados['descricao'] = '1.3 - ESTAGIÁRIO'
                dict_dados['interno'] = dict_calculo_uos[campus.sigla]['estagiarios_rotatividade_interna']
                dict_dados['externo'] = dict_calculo_uos[campus.sigla]['estagiarios_rotatividade_externa']
                lista_dados.append(dict_dados)
                dict_consolidado_uos[campus.sigla]['estagiarios_rotatividade_interna'] += dict_dados['interno']
                dict_consolidado_uos[campus.sigla]['estagiarios_rotatividade_externa'] += dict_dados['externo']

            dict_dados_periodo = {}
            dict_dados_periodo['periodo'] = f'{periodo.month}/{periodo.year}'
            dict_dados_periodo['dados'] = lista_dados
            lista_dados_periodo.append(dict_dados_periodo)

        # ---------------------------
        # Dados consolidados do periodo
        # ---------------------------
        lista_dados = []

        dict_dados = {}
        dict_dados['descricao'] = '1 - COLABORADORES DO IFRN'
        dict_dados['interno'] = dict_consolidado['ifrn_rotatividade_interna']
        dict_dados['externo'] = dict_consolidado['ifrn_rotatividade_externa']
        lista_dados.append(dict_dados)

        dict_dados = {}
        dict_dados['descricao'] = '1.1 - TÉCNICO ADMINISTRATIVO'
        dict_dados['interno'] = dict_consolidado['taes_rotatividade_interna']
        dict_dados['externo'] = dict_consolidado['taes_rotatividade_externa']
        lista_dados.append(dict_dados)

        dict_dados = {}
        dict_dados['descricao'] = '1.2 - DOCENTE'
        dict_dados['interno'] = dict_consolidado['docentes_rotatividade_interna']
        dict_dados['externo'] = dict_consolidado['docentes_rotatividade_externa']
        lista_dados.append(dict_dados)

        dict_dados = {}
        dict_dados['descricao'] = '1.3 - ESTAGIÁRIO'
        dict_dados['interno'] = dict_consolidado['estagiarios_rotatividade_interna']
        dict_dados['externo'] = dict_consolidado['estagiarios_rotatividade_externa']
        lista_dados.append(dict_dados)

        # Por campus
        # --------------------
        for campus in campis:
            dict_dados = {}
            dict_dados['descricao'] = campus
            lista_dados.append(dict_dados)

            dict_dados = {}
            dict_dados['descricao'] = '1 - COLABORADORES DO CAMPUS'
            dict_dados['interno'] = dict_consolidado_uos[campus.sigla]['ifrn_rotatividade_interna']
            dict_dados['externo'] = dict_consolidado_uos[campus.sigla]['ifrn_rotatividade_externa']
            lista_dados.append(dict_dados)

            dict_dados = {}
            dict_dados['descricao'] = '1.1 - TÉCNICO ADMINISTRATIVO'
            dict_dados['interno'] = dict_consolidado_uos[campus.sigla]['taes_rotatividade_interna']
            dict_dados['externo'] = dict_consolidado_uos[campus.sigla]['taes_rotatividade_externa']
            lista_dados.append(dict_dados)

            dict_dados = {}
            dict_dados['descricao'] = '1.2 - DOCENTE'
            dict_dados['interno'] = dict_consolidado_uos[campus.sigla]['docentes_rotatividade_interna']
            dict_dados['externo'] = dict_consolidado_uos[campus.sigla]['docentes_rotatividade_externa']
            lista_dados.append(dict_dados)

            dict_dados = {}
            dict_dados['descricao'] = '1.3 - ESTAGIÁRIO'
            dict_dados['interno'] = dict_consolidado_uos[campus.sigla]['estagiarios_rotatividade_interna']
            dict_dados['externo'] = dict_consolidado_uos[campus.sigla]['estagiarios_rotatividade_externa']
            lista_dados.append(dict_dados)

        dict_dados_periodo = {}
        dict_dados_periodo['periodo'] = 'Consolidado'
        dict_dados_periodo['dados'] = lista_dados
        lista_dados_periodo.append(dict_dados_periodo)

    return locals()


@rtr()
@permission_required(['pgd2.gestao_pgd2', 'pgd2.gestao_pgd2_comissao_sistemica'])
def relatorio_questionario_rit(request):
    estah_em_gestao_pgd = ComissaoPGD.user_estah_em_gestao_pgd(request.user)
    estah_em_comissao_sistemica_vigente = ComissaoPGD.user_estah_em_comissao_sistemica_vigente(request.user)
    estah_em_comissao_local_vigente = ComissaoPGD.user_estah_em_comissao_local_vigente(request.user)

    if not (estah_em_gestao_pgd or estah_em_comissao_sistemica_vigente or estah_em_comissao_local_vigente):
        raise PermissionDenied

    campis = None
    if not (estah_em_gestao_pgd and estah_em_comissao_sistemica_vigente) and estah_em_comissao_local_vigente:
        campis = ComissaoPGD.get_campis_comissoes_locais_vigentes_user(request.user.get_vinculo())

    title = 'Relatório de avaliação do PGD'

    existem_questionarios = RelatorioIndividualTrabalhoQuestionario.objects.all().exists()
    lista_dados = []
    lista_dados_complemento = []
    tipo_resultado = 1

    if existem_questionarios:
        buscou = False
        form = BuscarRelatorioQuestionarioRitForm(request.GET or None, campis=campis)
        if form.is_valid():
            buscou = True
            periodo = form.cleaned_data.get('periodo')
            pergunta = form.cleaned_data.get('pergunta')
            campus = form.cleaned_data.get('campus')

            questionarios = RelatorioIndividualTrabalhoQuestionario.objects.filter(periodo_pit_rit=periodo).order_by('data')
            if campus:
                questionarios = questionarios.filter(setor__uo=campus)

            dict_filtros_basicos = {}
            dict_filtros_basicos[f'{pergunta}__isnull'] = False
            questionarios = questionarios.filter(**dict_filtros_basicos)

            # TextField
            if pergunta in ['pergunta_1', 'pergunta_2', 'pergunta_7']:
                tipo_resultado = 1
                for questionario in questionarios:
                    lista_dados.append(getattr(questionario, pergunta))

            # PositiveIntegerField - SIM, NÃO (Sem complemento ou Com complemento)
            if pergunta in ['pergunta_3', 'pergunta_4', 'pergunta_5', 'pergunta_6', 'pergunta_9', 'pergunta_10', 'pergunta_11']:
                tipo_resultado = 2

                dict_filtros = {}
                dict_filtros_basicos[f'{pergunta}'] = RelatorioIndividualTrabalhoQuestionario.SIM
                qtd_sim = questionarios.filter(**dict_filtros_basicos).count()
                dict_filtros_basicos[f'{pergunta}'] = RelatorioIndividualTrabalhoQuestionario.NAO
                qtd_nao = questionarios.filter(**dict_filtros_basicos).count()
                dict_filtros_basicos[f'{pergunta}'] = RelatorioIndividualTrabalhoQuestionario.ABSTENCAO
                qtd_abstencao = questionarios.filter(**dict_filtros_basicos).count()

                qtd_total = qtd_sim + qtd_nao + qtd_abstencao
                if qtd_total > 0:
                    perc_qtd_sim = (qtd_sim / qtd_total) * 100
                    perc_qtd_nao = (qtd_nao / qtd_total) * 100
                    perc_qtd_abstencao = (qtd_abstencao / qtd_total) * 100
                else:
                    perc_qtd_sim = 0
                    perc_qtd_nao = 0
                    perc_qtd_abstencao = 0

                lista_dados.append((qtd_total, qtd_sim, qtd_nao, qtd_abstencao, perc_qtd_sim, perc_qtd_nao, perc_qtd_abstencao))

                # Calculando complemento
                if pergunta == 'pergunta_11':
                    resultados_set = set()
                    for questionario in questionarios:
                        if questionario.pergunta_11_complemento is not None and questionario.pergunta_11_complemento > 0:
                            resultados_set.add(questionario.pergunta_11_complemento)
                    resultados_set = sorted(resultados_set)

                    qtd_total_complemento = len(resultados_set)
                    for resultado in resultados_set:
                        qtd = questionarios.filter(pergunta_11_complemento=resultado).count()
                        perc_qtd = (qtd / qtd_total_complemento) * 100
                        lista_dados_complemento.append((resultado, qtd, perc_qtd))
                if pergunta == 'pergunta_3':
                    resultados_set = set()
                    for questionario in questionarios:
                        if questionario.pergunta_3_complemento > 0:
                            resultados_set.add(questionario.pergunta_3_complemento)
                    resultados_set = sorted(resultados_set)

                    qtd_total_complemento = len(resultados_set)
                    for resultado in resultados_set:
                        qtd = questionarios.filter(pergunta_3_complemento=resultado).count()
                        perc_qtd = (qtd / qtd_total_complemento) * 100
                        lista_dados_complemento.append((resultado, qtd, perc_qtd))

            # PositiveIntegerField - ESTRELAS
            if pergunta == 'pergunta_8':
                tipo_resultado = 3

                dict_filtros = {}
                dict_filtros_basicos[f'{pergunta}'] = RelatorioIndividualTrabalhoQuestionario.ESTRELA_1
                qtd_1_estrela = questionarios.filter(**dict_filtros_basicos).count()
                dict_filtros_basicos[f'{pergunta}'] = RelatorioIndividualTrabalhoQuestionario.ESTRELA_2
                qtd_2_estrela = questionarios.filter(**dict_filtros_basicos).count()
                dict_filtros_basicos[f'{pergunta}'] = RelatorioIndividualTrabalhoQuestionario.ESTRELA_3
                qtd_3_estrela = questionarios.filter(**dict_filtros_basicos).count()
                dict_filtros_basicos[f'{pergunta}'] = RelatorioIndividualTrabalhoQuestionario.ESTRELA_4
                qtd_4_estrela = questionarios.filter(**dict_filtros_basicos).count()
                dict_filtros_basicos[f'{pergunta}'] = RelatorioIndividualTrabalhoQuestionario.ESTRELA_5
                qtd_5_estrela = questionarios.filter(**dict_filtros_basicos).count()

                qtd_total = qtd_1_estrela + qtd_2_estrela + qtd_3_estrela + qtd_4_estrela + qtd_5_estrela

                if qtd_total > 0:
                    perc_qtd_1_estrela = (qtd_1_estrela / qtd_total) * 100
                    perc_qtd_2_estrela = (qtd_2_estrela / qtd_total) * 100
                    perc_qtd_3_estrela = (qtd_3_estrela / qtd_total) * 100
                    perc_qtd_4_estrela = (qtd_4_estrela / qtd_total) * 100
                    perc_qtd_5_estrela = (qtd_5_estrela / qtd_total) * 100
                else:
                    perc_qtd_1_estrela = 0
                    perc_qtd_2_estrela = 0
                    perc_qtd_3_estrela = 0
                    perc_qtd_4_estrela = 0
                    perc_qtd_5_estrela = 0

                lista_dados.append(
                    (
                        qtd_total,
                        qtd_1_estrela,
                        qtd_2_estrela,
                        qtd_3_estrela,
                        qtd_4_estrela,
                        qtd_5_estrela,
                        perc_qtd_1_estrela,
                        perc_qtd_2_estrela,
                        perc_qtd_3_estrela,
                        perc_qtd_4_estrela,
                        perc_qtd_5_estrela,
                    )
                )

    return locals()


@rtr()
@permission_required('rh.chefe')
def listar_questionarios_chefe_deve_responder(request):
    title = 'Questionários de pesquisa de PGD que devem ser preenchidos'

    lista_setor_periodo_a_preencher, _ = RelatorioIndividualTrabalhoQuestionario.questionarios_a_responder_como_chefe(
        request.user.get_relacionamento()
    )

    return locals()


@rtr()
@permission_required('rh.chefe')
def preencher_questionario_chefe(request, setor_id, periodo_id):
    _, lista_setores_para_preencher = RelatorioIndividualTrabalhoQuestionario.questionarios_a_responder_como_chefe(request.user.get_relacionamento())
    setor = get_setores_pgd().filter(id=setor_id).first()
    if setor not in lista_setores_para_preencher:
        raise PermissionDenied

    periodo = PeriodoPitRit.objects.get(id=periodo_id)
    servidor_chefe = request.user.get_relacionamento()

    title = f'Questionário de pesquisa referente ao {periodo} | {setor}'
    form = QuestionarioRitChefeForm(request.POST or None, request=request)
    if form.is_valid():
        o = form.save(False)
        o.periodo_pit_rit = periodo
        o.setor = setor
        o.servidor_respondente = servidor_chefe
        o.questionario_de_chefe = True
        o.save()
        url = '/pgd2/listar_questionarios_chefe_deve_responder/'
        return httprr(url, 'Questionário preenchido com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.chefe')
def homologar_rit_lote(request):
    if not PlanoIndividualTrabalho.pode_visualizar_lista(request.user):
        raise PermissionDenied

    url = '/pgd2/listar_rits_chefe_deve_pode_aprova_homologa/'

    ids = request.GET.getlist('checks[]')
    if 'on' in ids:
        ids.remove('on')
    if not ids:
        raise PermissionDenied

    title = f'Aprovar/Homologar {nomenclatura.relatorio_individual_de_trabalho_sigla_plural_pgd2}'

    lista_pits_aprova_deve, lista_pits_homologacao_deve = PlanoIndividualTrabalho.get_rits_pendendentes_avaliacao_chefe_direto(request.user)
    lista_pits_aprova_deve = lista_pits_aprova_deve.filter(id__in=ids)
    lista_pits_homologacao_deve = lista_pits_homologacao_deve.filter(id__in=ids)
    if not lista_pits_aprova_deve and not lista_pits_homologacao_deve:
        raise PermissionDenied
    lista_pits_homologacao_deve = lista_pits_homologacao_deve.annotate(parecer=Value('Homologação', output_field=CharField()))
    lista_pits_aprova_deve = lista_pits_aprova_deve.annotate(parecer=Value('Aprovação', output_field=CharField()))

    lista_pits_deve = []
    lista_pits_deve.extend(lista_pits_homologacao_deve)
    lista_pits_deve.extend(lista_pits_aprova_deve)
    lista_pits_deve = sorted(lista_pits_deve, key=lambda p: p.adesao.servidor.nome)

    form = AvaliacaoRitLoteForm(request.POST or None, lista_pits_homologacao_deve=lista_pits_homologacao_deve)
    if form.is_valid():
        executado = False

        # Homologação
        # -------------------
        for hom in lista_pits_homologacao_deve:
            if not hom.pode_homologar_rit(request.user):
                return httprr(
                    url,
                    f'Não foi possível homologar "{hom.get_verbose_rit()}" em lote. Abra o RIT individualmente para consultar e resolver as pendências.',
                    tag='error',
                )
        for hom in lista_pits_homologacao_deve:
            setores, _ = setores_e_servidores_que_sou_relacionado_como_chefe_no_periodo(request.user, hom.data_inicio, hom.data_fim)

            avaliacao_rit = form.cleaned_data.get('avaliacao_rit')
            justificativa = form.cleaned_data.get('justificativa')
            avaliacao_rit_str = PlanoIndividualTrabalho.AVALIACAO_RIT_CHOICES[int(avaliacao_rit) - 1][1]
            tempo_homologado = hom.tempo_executado_total

            homologado = hom.homologar_rit(setores, avaliacao_rit, tempo_homologado, request.user.get_relacionamento(), justificativa=justificativa)
            if not homologado:
                return httprr(
                    url,
                    f'Não foi possível homologar "{hom.get_verbose_rit()}" em lote. Consulte as pendências do RIT e tente novamente.',
                    tag='error',
                )
            # Registro de Ação
            # -------------------
            ra_obs = f'Homologação do "{hom.get_verbose_rit()}" mediante a avaliação "{avaliacao_rit_str}" e confirmação das entregas do {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2}. Homologação realizada em LOTE.'
            if justificativa:
                ra_obs = f'Homologação do "{hom.get_verbose_rit()}" mediante a avaliação "{avaliacao_rit_str}", justificativa "{justificativa}" e  e confirmação das entregas do {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2}. Homologação realizada em LOTE.'

            RegistroAcaoPlanoIndividualTrabalho.registrar(
                request=request, tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_HOMOLOGOU_RIT, pit=hom, obs=ra_obs
            )

            vinculo = hom.adesao.servidor.get_vinculo()
            assunto = f'Homologação de {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2}'
            texto = f'<h1>Homologação de {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2}</h1><p>{nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2} {hom.get_verbose_periodo()} foi homologado.</p>'
            tasks.notificar_pgd_task(vinculo, assunto, texto)

            executado = True

        # Aprovação
        # -------------------
        for hom in lista_pits_aprova_deve:
            if not hom.pode_aprovar_rit(request.user):
                return httprr(
                    url,
                    f'Não foi possível aprovar "{hom.get_verbose_rit()}" em lote. Abra o RIT individualmente para consultar e resolver as pendências.',
                    tag='error',
                )

        for hom in lista_pits_aprova_deve:
            setores, _ = setores_e_servidores_que_sou_relacionado_como_chefe_no_periodo(request.user, hom.data_inicio, hom.data_fim)
            hom.aprovar_rit(setores, request.user.get_relacionamento())
            ra_obs = f'Aprovação do "{hom.get_verbose_rit()}". Aprovação realizada em LOTE.'
            RegistroAcaoPlanoIndividualTrabalho.registrar(
                request=request, tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_APROVOU_RIT, pit=hom, obs=ra_obs
            )
            executado = True

        if executado:
            return httprr(url, 'As ações de aprovação e homologação foram concluídas para os RITs selecionados.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.chefe')
def homologar_pit_lote(request):
    if not PlanoIndividualTrabalho.pode_visualizar_lista(request.user):
        raise PermissionDenied

    url = '/pgd2/listar_pits_chefe_deve_pode_aprova_homologa/'

    ids = request.GET.getlist('checks[]')
    if 'on' in ids:
        ids.remove('on')
    if not ids:
        raise PermissionDenied

    title = f'Aprovar/Homologar {nomenclatura.plano_individual_de_trabalho_sigla_plural_pgd2}'

    # Deve Aprovar/Homologar
    lista_pits_aprova_deve, lista_pits_homologacao_deve = PlanoIndividualTrabalho.get_pits_pendendentes_avaliacao_chefe_direto(request.user)
    lista_pits_aprova_deve = lista_pits_aprova_deve.filter(id__in=ids)
    lista_pits_homologacao_deve = lista_pits_homologacao_deve.filter(id__in=ids)
    lista_pits_homologacao_deve = lista_pits_homologacao_deve.annotate(parecer=Value('Homologação', output_field=CharField()))
    lista_pits_aprova_deve = lista_pits_aprova_deve.annotate(parecer=Value('Aprovação', output_field=CharField()))
    lista_pits_deve = []

    lista_pits_deve.extend(lista_pits_homologacao_deve)
    lista_pits_deve.extend(lista_pits_aprova_deve)
    lista_pits_deve = sorted(lista_pits_deve, key=lambda p: p.adesao.servidor.nome)

    form = AvaliacaoPitLoteForm(request.POST or None)
    if form.is_valid():
        executado = False

        # Homologação
        # -------------------
        pode_homologar = True
        for hom in lista_pits_homologacao_deve:
            if not hom.pode_homologar_pit(request.user):
                pode_homologar = False
            if pode_homologar:
                pode_finalizar_aprovacao_homologacao_pit = hom.pode_finalizar_aprovacao_homologacao_pit(retornar_lista_erros=False)[0]
                if not pode_finalizar_aprovacao_homologacao_pit:
                    pode_homologar = False
            if not pode_homologar:
                return httprr(
                    url,
                    f'Impossível Homologar o "{hom.get_verbose_pit_rit()}" em lote. Tente Homologar individualmente para verificar as eventuais pendências.',
                    tag='error',
                )
        for hom in lista_pits_homologacao_deve:
            setores, _ = setores_e_servidores_que_sou_relacionado_como_chefe_no_periodo(request.user, hom.data_inicio, hom.data_fim)
            hom.homologar_pit(setores, request.user.get_relacionamento())
            ra_obs = f'Homologação do "{hom}". Homologação realizada em LOTE.'
            RegistroAcaoPlanoIndividualTrabalho.registrar(
                request=request, tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_HOMOLOGOU, pit=hom, obs=ra_obs
            )

            vinculo = hom.adesao.servidor.get_vinculo()
            assunto = f'Homologação de {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}'
            texto = f'<h1>Homologação de {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}</h1><p>{nomenclatura.plano_individual_de_trabalho_sigla_pgd2} {hom.get_verbose_periodo()} foi homologado.</p>'
            tasks.notificar_pgd_task(vinculo, assunto, texto)

            executado = True

        # Aprovação
        # -------------------
        pode_aprovar = True
        for hom in lista_pits_aprova_deve:
            if not hom.pode_aprovar_pit(request.user):
                pode_aprovar = False
            if pode_homologar:
                pode_finalizar_aprovacao_homologacao_pit = hom.pode_finalizar_aprovacao_homologacao_pit(retornar_lista_erros=False)[0]
                if not pode_finalizar_aprovacao_homologacao_pit:
                    pode_aprovar = False
            if not pode_aprovar:
                return httprr(
                    url,
                    f'Impossível Aprovar o "{hom.get_verbose_pit_rit()}" em lote. Tente Aprovar individualmente para verificar as eventuais pendências.',
                    tag='error',
                )
        for hom in lista_pits_aprova_deve:
            setores, _ = setores_e_servidores_que_sou_relacionado_como_chefe_no_periodo(request.user, hom.data_inicio, hom.data_fim)
            hom.aprovar_pit(setores, request.user.get_relacionamento())
            ra_obs = f'Aprovação do "{hom}". Aprovação realizada em LOTE.'
            RegistroAcaoPlanoIndividualTrabalho.registrar(request=request, tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_APROVOU, pit=hom, obs=ra_obs)
            executado = True

        if executado:
            return httprr(url, 'Homologação/Aprovação realizada com sucesso.')

    return locals()


@rtr()
@permission_required(['pgd2.gestao_pgd2', 'pgd2.gestao_pgd2_comissao_sistemica'])
def listar_pits(request):
    title = f'{nomenclatura.planos_individuais_de_trabalho_pgd2}'

    # Todos os planos de trabalho
    # - Independente de adesão ou desligamento
    lista_pits = PlanoIndividualTrabalho.objects.all().order_by('adesao__servidor')

    form = BuscarPitsPgdForm(request.GET or None, request=request)
    if form.is_valid():
        buscar_str = form.cleaned_data.get('buscar_str')
        setor = form.cleaned_data.get('setor')
        campus = form.cleaned_data.get('campus')
        periodo = form.cleaned_data.get('periodo')

        if periodo:
            lista_pits = lista_pits.filter(periodo_pit_rit_id=periodo)
        if campus:
            lista_pits = lista_pits.filter(setor_pode_homologar_pit_rit__uo=campus)
        if setor:
            lista_pits = lista_pits.filter(setor_pode_homologar_pit_rit=setor)
        if buscar_str:
            lista_pits = lista_pits.filter(
                Q(adesao__servidor__pessoa_fisica__nome__icontains=buscar_str) | Q(adesao__servidor__matricula__icontains=buscar_str)
            )

    return locals()


@rtr()
@permission_required('rh.eh_servidor')
def listar_servidores_pgd_exterior(request):
    title = 'Servidores em PGD Exterior'

    lista_servidores = SolicitacaoAdesaoServidor.get_servidores_em_pgd_exterior().order_by('pessoa_fisica__nome')

    form = BuscarServidoresPgdForm(request.GET or None, request=request)
    if form.is_valid():
        buscar_str = form.cleaned_data.get('buscar_str')
        setor = form.cleaned_data.get('setor')
        campus = form.cleaned_data.get('campus')

        if campus:
            lista_servidores = lista_servidores.filter(setor__uo=campus)
        if setor:
            lista_servidores = lista_servidores.filter(setor=setor)
        if buscar_str:
            lista_servidores = lista_servidores.filter(Q(pessoa_fisica__nome__icontains=buscar_str) | Q(matricula__icontains=buscar_str))

    return locals()


@rtr()
def obter_pit_api_pgd2(request, pit_id):
    if not pode_consultar_dados_api(request.user):
        raise PermissionDenied

    pit = get_object_or_404(PlanoIndividualTrabalho, pk=pit_id)

    title = f'API PGD 2 - {pit}'

    from pgd2.api_pgd2_v2 import get_api_pgd2_v2

    api_pgd_v2 = get_api_pgd2_v2()
    if api_pgd_v2:
        api_pgd_v2.set_token()
        api_pgd_v2.set_header()

        dados_locais = api_pgd_v2.get_dados_api_pit(pit)

        response = api_pgd_v2.get_manualmente_pit(pit)
        if response.ok:
            dados_remotos = response.json()
        else:
            dados_remotos = f'Erro ao obter dados externos {response.status_code} - {response.text}'
    else:
        dados_remotos = 'API PGD2 não está ativa'

    return locals()


@rtr()
def listar_servidores_api_pgd2(request):
    if not pode_consultar_dados_api(request.user):
        raise PermissionDenied

    title = 'API PGD 2 - Servidores PGD'

    lista_servidores = Servidor.objects.vinculados().filter(id__in=SolicitacaoAdesaoServidor.objects.all().values('servidor_id'))
    lista_servidores = lista_servidores.order_by('pessoa_fisica__nome')

    form = BuscarServidoresApiPgdForm(request.GET or None, request=request)
    if form.is_valid():
        buscar_str = form.cleaned_data.get('buscar_str')
        setor = form.cleaned_data.get('setor')
        apenas_sem_pit_enviado = form.cleaned_data.get('apenas_sem_pit_enviado')
        if setor:
            lista_servidores = lista_servidores.filter(setor=setor)
        if buscar_str:
            lista_servidores = lista_servidores.filter(Q(pessoa_fisica__nome__icontains=buscar_str) | Q(matricula__icontains=buscar_str))

    return locals()


@rtr()
def visualizar_servidor_api_pgd2(request, matricula):
    if not pode_consultar_dados_api(request.user):
        raise PermissionDenied

    servidor = get_object_or_404(Servidor, matricula=matricula)
    title = f'API PGD 2 - {servidor}'

    from pgd2.api_pgd2_v2 import get_api_pgd2_v2

    api_pgd_v2 = get_api_pgd2_v2()

    adesoes_pgd = SolicitacaoAdesaoServidor.objects.filter(servidor=servidor).order_by('id')

    modo = request.GET.get('m', 'visualizar')
    retorno = None
    dados_remotos = None
    dados_locais = None

    if modo == 'dados_participante':
        title = f'API PGD 2 - Servidor Participante | {servidor}'

        if api_pgd_v2:
            api_pgd_v2.set_token()
            api_pgd_v2.set_header()

            participante = ParticipantePgd.objects.filter(servidor=servidor).first()
            if participante:
                dados_locais = api_pgd_v2.get_dados_parcipante(participante)

            adesoes_vigentes = SolicitacaoAdesaoServidor.get_vigentes(servidor.get_user())
            if adesoes_vigentes:
                response = api_pgd_v2.get_manualmente_participante(adesoes_vigentes.first())
                if response.ok:
                    dados_remotos = response.json()
                else:
                    dados_remotos = f'Erro ao obter dados externos {response.status_code} - {response.text}'
        else:
            dados_remotos = 'API PGD2 não está ativa'

    return locals()


@rtr()
def visualizar_pes_api_pgd2(request, pes_id):
    if not pode_consultar_dados_api(request.user):
        raise PermissionDenied

    pes = get_object_or_404(PlanoEntregasSetorial, id=pes_id)
    title = f'API PGD 2 - {pes}'

    from pgd2.api_pgd2_v2 import get_api_pgd2_v2

    api_pgd = get_api_pgd2_v2()
    if api_pgd:
        api_pgd.set_token()
        api_pgd.set_header()

        grupo_setores = []
        grupo = pes.get_grupo_pes_api()
        if grupo:
            for g in grupo:
                dados = {}
                dados['pes_id'] = pes.id
                dados['setor'] = g.setor
                dados['cod_siape_grupo'] = api_pgd.get_codigo_siape_setor(g.setor)
                dados['setor_siape_grupo'] = Setor.objects.siape().get(codigo=dados['cod_siape_grupo'])
                grupo_setores.append(dados)

        dados_locais = api_pgd.get_dados_api_grupo_pes(pes)
        response = api_pgd.get_manualmente_pes(pes)
        if response.ok:
            dados_remotos = response.json()
        else:
            dados_remotos = f'Erro ao obter dados externos {response.status_code} - {response.text}'
    else:
        dados_remotos = 'API PGD2 não está ativa'

    return locals()


@rtr()
def listar_servidores_publico_pgd2(request):
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    title = 'PGD'
    category = 'Servidores'
    icon = 'file'

    adesoes_vigentes = SolicitacaoAdesaoServidor.get_adesoes_vigentes()
    lista_servidores = Servidor.objects.vinculados().filter(id__in=adesoes_vigentes.values('servidor_id')).order_by('pessoa_fisica__nome')

    form = BuscarServidoresPublicoPgdForm(request.POST or None)
    if form.is_valid():
        buscar_str = form.cleaned_data.get('buscar_str')
        setor = form.cleaned_data.get('setor')
        campus = form.cleaned_data.get('campus')
        if setor:
            lista_servidores = lista_servidores.filter(setor=setor)
        if buscar_str:
            lista_servidores = lista_servidores.filter(Q(pessoa_fisica__nome__icontains=buscar_str) | Q(matricula__icontains=buscar_str))
        if campus:
            lista_servidores = lista_servidores.filter(setor__uo=campus)
    else:
        lista_servidores = Servidor.objects.none()

    sh = request.GET.get('sh')
    pes_horarios_funcionamento_setor_agrupado_por_semana = None
    if sh:
        setor = get_setores_pgd().filter(id=sh).first()
        title = f'PGD - Horário de funcionamento - {setor}'

        pes_atual = PlanoEntregasSetorial.get_pes_na_data(setor, get_datetime_now().date())
        pes_horarios_funcionamento_setor_agrupado_por_semana = (
            PlanoEntregasSetorialHorarioFuncionamentoSetor.get_horarios_funcionamento_setor_agrupado_por_semana(pes_atual)
        )

    return locals()


@rtr()
@permission_required(['pgd2.gestao_pgd2', 'pgd2.gestao_pgd2_comissao_sistemica'])
def listar_servidores_gestao(request):
    title = 'Servidores PGD'

    adesoes_vigentes = SolicitacaoAdesaoServidor.get_adesoes_vigentes()
    lista_servidores = Servidor.objects.vinculados().filter(id__in=adesoes_vigentes.values('servidor_id')).order_by('pessoa_fisica__nome')

    form = BuscarServidoresPgdGestaoForm(request.GET or None, request=request)
    if form.is_valid():
        buscar_str = form.cleaned_data.get('buscar_str')
        setor = form.cleaned_data.get('setor')
        campus = form.cleaned_data.get('campus')

        if campus:
            lista_servidores = lista_servidores.filter(setor__uo=campus)
        if setor:
            lista_servidores = lista_servidores.filter(setor=setor)
        if buscar_str:
            lista_servidores = lista_servidores.filter(Q(pessoa_fisica__nome__icontains=buscar_str) | Q(matricula__icontains=buscar_str))

    return locals()


# ====================================================================
# MONITORAMENTO
# ====================================================================


@rtr()
@permission_required(['pgd2.gestao_pgd2', 'pgd2.gestao_pgd2_comissao_sistemica', 'pgd2.gestao_pgd2_comissao_local'])
def visualizar_habilitacao_setor(request, habilitacao_setor_id):
    hab_setor = get_object_or_404(SetorHabilitacao, id=habilitacao_setor_id)

    title = 'Habilitação do Setor no PGD'

    return locals()


@rtr()
@permission_required(['pgd2.gestao_pgd2', 'pgd2.gestao_pgd2_comissao_sistemica', 'pgd2.gestao_pgd2_comissao_local'])
def monitoramento_pes(request):
    title = 'Monitoramento Planos de Entregas dos Setores'

    REGRA_INCONSISTENCIA_ENVIO_APROVACAO = 1
    REGRA_INCONSISTENCIA_APROVACAO = 2
    REGRA_INCONSISTENCIA_ANALISE_EXECUCAO = 3
    REGRA_INCONSISTENCIA_AVALIACAO_EXCUCAO = 4
    REGRA_INCONSISTENCIA_PES_SEM_PIT = 5
    REGRA_INCONSISTENCIA_PES_SEM_PIT_HOMOLOGADO = 6
    #
    REGRA_COM_PES_COM_HABILITACAO = 7
    REGRA_COM_PES_SEM_HABILITACAO = 8
    REGRA_COM_PES_APROVADOS_SEM_HABILITACAO = 9
    REGRA_INCONSISTENCIA_CRIACAO_PES = 10

    MONITORAMENTO_CHOICES = [
        [REGRA_INCONSISTENCIA_ENVIO_APROVACAO, '[1] PESs cadastrados, mas que ainda não foram enviados para aprovação.'],
        [REGRA_INCONSISTENCIA_APROVACAO, '[2] PESs cadastrados, enviados para aprovação, mas que ainda não foram aprovados.'],
        [REGRA_INCONSISTENCIA_ANALISE_EXECUCAO, '[3] PESs aptos para análise da execução, mas que ainda não foram analisados.'],
        [REGRA_INCONSISTENCIA_AVALIACAO_EXCUCAO, '[4] PESs aptos para avaliação da execução, mas que ainda não foram avaliados.'],
        [REGRA_INCONSISTENCIA_PES_SEM_PIT, '[5] PESs aprovados, mas sem qualquer Plano de Trabalho (exceto cancelados) relacionado.'],
        [REGRA_INCONSISTENCIA_PES_SEM_PIT_HOMOLOGADO, '[6] PESs aprovados, mas sem Plano de Trabalho homologado relacionado.'],
    ]

    if permite_habilitacao_dos_setores():
        MONITORAMENTO_CHOICES.append([REGRA_COM_PES_COM_HABILITACAO, '[7] PESs relacionados a setores que possuem cadastro de habilitação no PGD.'])
        MONITORAMENTO_CHOICES.append(
            [REGRA_COM_PES_SEM_HABILITACAO, '[8] PESs relacionados a setores que não possuem cadastro de habilitação no PGD.']
        )
        MONITORAMENTO_CHOICES.append(
            [
                REGRA_COM_PES_APROVADOS_SEM_HABILITACAO,
                '[9] PESs aprovados relacionados a setores que não possuem cadastro de habilitação no PGD.',
            ],
        )
        MONITORAMENTO_CHOICES.append([REGRA_INCONSISTENCIA_CRIACAO_PES, '[10] Setores habilitados com PES não criado.'])

    eh_retorno_pes = True
    lista = []
    regra_selecionada = None
    uos_user = None
    if request.user.has_perm('pgd2.gestao_pgd2_comissao_local'):
        uos_user = ComissaoPGD.get_lista_uos_vigentes_por_user(request.user)
        if not uos_user:
            raise PermissionDenied
    form = ConsultaMonitoramentoPes(request.GET or None, mon_coices=MONITORAMENTO_CHOICES, uos=uos_user)
    if form.is_valid():
        setores = form.cleaned_data.get('setores')
        uos = form.cleaned_data.get('uos')
        periodos_pes = form.cleaned_data.get('periodos_pes')
        regra = int(form.cleaned_data.get('regra'))

        if not uos and uos_user:
            uos = uos_user

        if regra == REGRA_INCONSISTENCIA_ENVIO_APROVACAO:
            lista = get_pess_inconsistentes_aprovacao(tipo=1, uos=uos, setores=setores, periodos_pes=periodos_pes)
            regra_selecionada = MONITORAMENTO_CHOICES[REGRA_INCONSISTENCIA_ENVIO_APROVACAO - 1][1]
        if regra == REGRA_INCONSISTENCIA_APROVACAO:
            lista = get_pess_inconsistentes_aprovacao(tipo=2, uos=uos, setores=setores, periodos_pes=periodos_pes)
            regra_selecionada = MONITORAMENTO_CHOICES[REGRA_INCONSISTENCIA_APROVACAO - 1][1]
        if regra == REGRA_INCONSISTENCIA_ANALISE_EXECUCAO:
            lista = get_pess_aptos_para_analise_execucao(uos=uos, setores=setores, periodos_pes=periodos_pes)
            regra_selecionada = MONITORAMENTO_CHOICES[REGRA_INCONSISTENCIA_ANALISE_EXECUCAO - 1][1]
        if regra == REGRA_INCONSISTENCIA_AVALIACAO_EXCUCAO:
            lista = get_pess_aptos_para_avaliacao_execucao(uos=uos, setores=setores, periodos_pes=periodos_pes)
            regra_selecionada = MONITORAMENTO_CHOICES[REGRA_INCONSISTENCIA_AVALIACAO_EXCUCAO - 1][1]
        if regra == REGRA_INCONSISTENCIA_PES_SEM_PIT:
            lista = get_pess_relacionados_a_pit(tipo=1, uos=uos, setores=setores, periodos_pes=periodos_pes)
            regra_selecionada = MONITORAMENTO_CHOICES[REGRA_INCONSISTENCIA_PES_SEM_PIT - 1][1]
        if regra == REGRA_INCONSISTENCIA_PES_SEM_PIT_HOMOLOGADO:
            lista = get_pess_relacionados_a_pit(tipo=2, uos=uos, setores=setores, periodos_pes=periodos_pes)
            regra_selecionada = MONITORAMENTO_CHOICES[REGRA_INCONSISTENCIA_PES_SEM_PIT_HOMOLOGADO - 1][1]

        #

        if regra == REGRA_COM_PES_COM_HABILITACAO:
            lista = get_pess_de_setores_habilitados(uos=uos, setores=setores, periodos_pes=periodos_pes)
            regra_selecionada = MONITORAMENTO_CHOICES[REGRA_COM_PES_COM_HABILITACAO - 1][1]
        if regra == REGRA_COM_PES_SEM_HABILITACAO:
            lista = get_pess_de_setores_nao_habilitados(uos=uos, setores=setores, periodos_pes=periodos_pes)
            regra_selecionada = MONITORAMENTO_CHOICES[REGRA_COM_PES_SEM_HABILITACAO - 1][1]
        if regra == REGRA_COM_PES_APROVADOS_SEM_HABILITACAO:
            lista = get_pess_aprovados_de_setores_nao_habilitados(uos=uos, setores=setores, periodos_pes=periodos_pes)
            regra_selecionada = MONITORAMENTO_CHOICES[REGRA_COM_PES_APROVADOS_SEM_HABILITACAO - 1][1]
        if regra == REGRA_INCONSISTENCIA_CRIACAO_PES:
            lista = get_setores_habilitados_sem_pes_criado(uos=uos, setores=setores, periodos_pes=periodos_pes)
            regra_selecionada = MONITORAMENTO_CHOICES[REGRA_INCONSISTENCIA_CRIACAO_PES - 1][1]
            eh_retorno_pes = False

    return locals()


@rtr()
@permission_required('pgd2.gestao_pgd2')
def atualizar_setores_siape(request):
    SetorPgdApi.carregar_setores()
    url = '/admin/pgd2/setorpgdapi/'
    return httprr(url, 'Setores atualizados com sucesso.')


@rtr()
def visualizar_log_api_pgd2(request, log_id):
    if not pode_consultar_dados_api(request.user):
        raise PermissionDenied

    log = get_object_or_404(LogApi, id=log_id)
    title = f'API PGD 2 - {log}'

    return locals()


@rtr()
@permission_required(['pgd2.gestao_pgd2', 'pgd2.gestao_pgd2_comissao_sistemica', 'pgd2.gestao_pgd2_comissao_local'])
def monitoramento_servidores(request):
    title = 'Monitoramento dos Servidores'

    # AGRUPAMENTO_SERVIDORES_EM_PGD_SEM_PIT_HOMOLOGADO = 10
    # AGRUPAMENTO_SERVIDORES_EM_PGD_SEM_PIT_HOMOLOGADO_PERIODO_ATUAL = 11

    AGRUPAMENTO_SERVIDORES_EM_PGD = 1
    AGRUPAMENTO_SERVIDORES_EM_PGD_SOU_GOV = 2
    AGRUPAMENTO_SERVIDORES_EM_PGD_NO_SUAP_MAS_NAO_NO_SOU_GOV = 3
    AGRUPAMENTO_SERVIDORES_EM_PGD_NO_SOUGOV_MAS_NAO_NO_SUAP = 4
    AGRUPAMENTO_SERVIDORES_EM_PGD_COM_DADOS_PGD_DIFERENTE_SOUGOV_SUAP = 5
    AGRUPAMENTO_SERVIDORES_COM_ADESAO_VIGENTE_SEM_PIT_RELACIONADO = 6
    AGRUPAMENTO_SERVIDORES_COM_ADESAO_VIGENTE_SEM_PIT_HOMOLOGADO = 7
    AGRUPAMENTO_SERVIDORES_COM_ADESAO_VIGENTE_SEM_PIT_HOMOLOGADO_PERIODO_ATUAL = 8
    REGRA_SERVIDOR_DEVERIA_TER_PIT = 9
    REGRA_SERVIDOR_DEVERIA_TER_PIT_ULTIMOS_3_PERIODOS = 10
    REGRA_SERVIDORES_NO_PRIMEIRO_ANO_ESTAGIO_PROBATORIO = 11
    REGRA_SERVIDORES_NO_PRIMEIRO_SEGUNDO_ESTAGIO_PROBATORIO = 12
    REGRA_SERVIDORES_NO_PRIMEIRO_TERCEIRO_ESTAGIO_PROBATORIO = 13
    REGRA_SERVIDORES_MOVIMENTADOS_COM_MENOS_DE_6_MESES_DE_INSTITUTO = 14
    AGRUPAMENTO_SERVIDORES_DESLIGADOS = 15
    AGRUPAMENTO_SERVIDORES_INATIVOS_EM_PGD = 16
    REGRA_PERFIL_GERAL_SERVIDOR = 17
    AGRUPAMENTO_SERVIDORES_COM_ADESAO_VIGENTE_SEM_RIT_HOMOLOGADO_2_PERIODOS_ANTERIORES = 18
    #
    REGRA_HABILITACAO_SETOR = 19

    MONITORAMENTO_CHOICES = [
        [AGRUPAMENTO_SERVIDORES_EM_PGD, '[1] Servidores em PGD no SUAP no SUAP'],
        [AGRUPAMENTO_SERVIDORES_EM_PGD_SOU_GOV, '[2] Servidores em PGD (apenas dados SOU GOV)'],
        [AGRUPAMENTO_SERVIDORES_EM_PGD_NO_SUAP_MAS_NAO_NO_SOU_GOV, '[3] Servidores em PGD no SUAP mas não no SOU GOV'],
        [AGRUPAMENTO_SERVIDORES_EM_PGD_NO_SOUGOV_MAS_NAO_NO_SUAP, '[4] Servidores em PGD no SOU GOV mas não no SUAP'],
        [
            AGRUPAMENTO_SERVIDORES_EM_PGD_COM_DADOS_PGD_DIFERENTE_SOUGOV_SUAP,
            '[5] Servidores em PGD no SUAP com dados PGD diferentes entre SUAP e SOU GOV',
        ],
        [
            AGRUPAMENTO_SERVIDORES_COM_ADESAO_VIGENTE_SEM_PIT_RELACIONADO,
            f'[6] Servidores com adesão vigente e sem qualquer {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} relacionado (exceto cancelados)',
        ],
        [
            AGRUPAMENTO_SERVIDORES_COM_ADESAO_VIGENTE_SEM_PIT_HOMOLOGADO,
            f'[7] Servidores com adesão vigente e sem {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} relacionado homologado ao menos uma vez (exceto cancelados)',
        ],
        [
            AGRUPAMENTO_SERVIDORES_COM_ADESAO_VIGENTE_SEM_PIT_HOMOLOGADO_PERIODO_ATUAL,
            f'[8] Servidores com adesão vigente e sem {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} relacionado homologado ao menos uma vez no período atual (exceto cancelados)',
        ],
        # [
        #    AGRUPAMENTO_SERVIDORES_EM_PGD_SEM_PIT_HOMOLOGADO,
        #    f'Servidores em PGD e sem {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} homologado ao menos uma vez (exceto cancelados)',
        # ],
        # [
        #    AGRUPAMENTO_SERVIDORES_EM_PGD_SEM_PIT_HOMOLOGADO_PERIODO_ATUAL,
        #    f'Servidores em PGD e sem {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} homologado no período atual (exceto cancelados)',
        # ],
        [
            REGRA_SERVIDOR_DEVERIA_TER_PIT,
            '[9] Servidores com adesão vigente que deveriam ter plano de trabalho (exceto cancelados) homologado no período atual, mas não possuem',
        ],
        [
            REGRA_SERVIDOR_DEVERIA_TER_PIT_ULTIMOS_3_PERIODOS,
            '[10] Servidores com adesão vigente que deveriam ter plano de trabalho homologado em cada um dos últimos 3 períodos (incluindo o período atual), mas não possuem',
        ],
        [REGRA_SERVIDORES_NO_PRIMEIRO_ANO_ESTAGIO_PROBATORIO, '[11] Servidores em PGD que estão cumprindo o primeiro ano de estágio probatório'],
        [REGRA_SERVIDORES_NO_PRIMEIRO_SEGUNDO_ESTAGIO_PROBATORIO, '[12] Servidores em PGD que estão cumprindo o segundo ano de estágio probatório'],
        [REGRA_SERVIDORES_NO_PRIMEIRO_TERCEIRO_ESTAGIO_PROBATORIO, '[13] Servidores em PGD que estão cumprindo o terceiro ano de estágio probatório'],
        [REGRA_SERVIDORES_MOVIMENTADOS_COM_MENOS_DE_6_MESES_DE_INSTITUTO, '[14] Servidores em PGD movimentados com menos de 6 meses de instituto'],
        [AGRUPAMENTO_SERVIDORES_DESLIGADOS, '[15] Servidores desligados do PGD (estavam em PGD)'],
        [AGRUPAMENTO_SERVIDORES_INATIVOS_EM_PGD, '[16] Servidores não ativos em PGD'],
        [REGRA_PERFIL_GERAL_SERVIDOR, '[17] Servidores inconsistentes pela regra de habilitação do servidor pelo perfil geral do servidor'],
        [
            AGRUPAMENTO_SERVIDORES_COM_ADESAO_VIGENTE_SEM_RIT_HOMOLOGADO_2_PERIODOS_ANTERIORES,
            '[18] Servidores com adesão vigente e sem Relatório homologado nos 2 períodos anteriores',
        ],
    ]

    if permite_habilitacao_dos_setores():
        MONITORAMENTO_CHOICES.append([REGRA_HABILITACAO_SETOR, '[19] Servidores inconsistentes pela regra de habilitação do setor'])

    uos_user = None
    if request.user.has_perm('pgd2.gestao_pgd2_comissao_local'):
        uos_user = ComissaoPGD.get_lista_uos_vigentes_por_user(request.user)
        if not uos_user:
            raise PermissionDenied

    lista_servidores = []
    regra_selecionada = None
    form = ConsultaMonitoramentoPit(request.GET or None, mon_coices=MONITORAMENTO_CHOICES, uos=uos_user)
    if form.is_valid():
        buscar_str = form.cleaned_data.get('buscar_str')
        setores = form.cleaned_data.get('setores')
        uos = form.cleaned_data.get('uos')
        regra = int(form.cleaned_data.get('regra'))

        if not uos and uos_user:
            uos = uos_user

        for r in MONITORAMENTO_CHOICES:
            if r[0] == regra:
                regra_selecionada = r[1]

        if regra_selecionada:
            if regra == AGRUPAMENTO_SERVIDORES_EM_PGD:
                lista_servidores = get_servidores_em_pgd(buscar_str=buscar_str, setores=setores, uos=uos)

            if regra == AGRUPAMENTO_SERVIDORES_EM_PGD_SOU_GOV:
                lista_servidores = get_servidores_em_pgd_no_sou_gov(buscar_str=buscar_str, setores=setores, uos=uos)

            if regra == AGRUPAMENTO_SERVIDORES_EM_PGD_NO_SUAP_MAS_NAO_NO_SOU_GOV:
                lista_servidores = get_servidores_em_pgd_no_suap_mas_nao_no_sou_gov(buscar_str=buscar_str, setores=setores, uos=uos)

            if regra == AGRUPAMENTO_SERVIDORES_EM_PGD_NO_SOUGOV_MAS_NAO_NO_SUAP:
                lista_servidores = get_servidores_em_pgd_no_sou_gov_mas_nao_no_suap(buscar_str=buscar_str, setores=setores, uos=uos)

            if regra == AGRUPAMENTO_SERVIDORES_EM_PGD_COM_DADOS_PGD_DIFERENTE_SOUGOV_SUAP:
                lista_servidores_diferenca_modalidade = get_servidores_em_pgd_com_dados_diferentes_entre_sougov_suap(
                    buscar_str=buscar_str, setores=setores, uos=uos
                )

            if regra == AGRUPAMENTO_SERVIDORES_INATIVOS_EM_PGD:
                lista_servidores = get_servidores_inativos_em_pgd(buscar_str=buscar_str, setores=setores, uos=uos)

            if regra == AGRUPAMENTO_SERVIDORES_COM_ADESAO_VIGENTE_SEM_PIT_RELACIONADO:
                lista_servidores = get_servidores_adesao_vigente_sem_pit_relacionado(regra=1, buscar_str=buscar_str, setores=setores, uos=uos)

            if regra == AGRUPAMENTO_SERVIDORES_COM_ADESAO_VIGENTE_SEM_PIT_HOMOLOGADO:
                lista_servidores = get_servidores_adesao_vigente_sem_pit_relacionado(regra=2, buscar_str=buscar_str, setores=setores, uos=uos)

            if regra == AGRUPAMENTO_SERVIDORES_COM_ADESAO_VIGENTE_SEM_PIT_HOMOLOGADO_PERIODO_ATUAL:
                lista_servidores = get_servidores_adesao_vigente_sem_pit_relacionado(regra=3, buscar_str=buscar_str, setores=setores, uos=uos)

            # if regra == AGRUPAMENTO_SERVIDORES_EM_PGD_SEM_PIT_HOMOLOGADO:
            #    lista_servidores = get_servidores_em_pgd_sem_pit_homologado(
            #        buscar_str=buscar_str, setores=setores, considerar_apenas_periodo_pit_atual=False
            #    )

            # if regra == AGRUPAMENTO_SERVIDORES_EM_PGD_SEM_PIT_HOMOLOGADO_PERIODO_ATUAL:
            #    lista_servidores = get_servidores_em_pgd_sem_pit_homologado(
            #        buscar_str=buscar_str, setores=setores, considerar_apenas_periodo_pit_atual=True
            #    )

            if regra == AGRUPAMENTO_SERVIDORES_DESLIGADOS:
                lista_servidores = get_servidores_desligados(buscar_str=buscar_str, setores=setores, uos=uos)

            if regra == REGRA_SERVIDOR_DEVERIA_TER_PIT:
                lista_servidores = get_servidores_deveriam_mas_nao_tem_pit_homologado(buscar_str=buscar_str, setores=setores, uos=uos)

            if regra == REGRA_SERVIDOR_DEVERIA_TER_PIT_ULTIMOS_3_PERIODOS:
                lista_servidores = get_servidores_deveriam_mas_nao_tem_pit_homologado_ultimos_3_periodos(
                    buscar_str=buscar_str, setores=setores, uos=uos
                )

            if regra == REGRA_PERFIL_GERAL_SERVIDOR:
                lista_servidores = get_servidores_inconsistentes_regra_de_perfil_geral_servidor(buscar_str=buscar_str, setores=setores, uos=uos)

            if regra == REGRA_HABILITACAO_SETOR:
                lista_servidores = get_servidores_inconsistentes_regra_habilitacao_setor(buscar_str=buscar_str, setores=setores, uos=uos)

            if regra == REGRA_SERVIDORES_NO_PRIMEIRO_ANO_ESTAGIO_PROBATORIO:
                lista_servidores = get_servidores_em_pgd_em_estagio_probratorio(
                    ano_estagio_probratorio=1, buscar_str=buscar_str, setores=setores, uos=uos
                )
            if regra == REGRA_SERVIDORES_NO_PRIMEIRO_SEGUNDO_ESTAGIO_PROBATORIO:
                lista_servidores = get_servidores_em_pgd_em_estagio_probratorio(
                    ano_estagio_probratorio=2, buscar_str=buscar_str, setores=setores, uos=uos
                )
            if regra == REGRA_SERVIDORES_NO_PRIMEIRO_TERCEIRO_ESTAGIO_PROBATORIO:
                lista_servidores = get_servidores_em_pgd_em_estagio_probratorio(
                    ano_estagio_probratorio=3, buscar_str=buscar_str, setores=setores, uos=uos
                )

            if regra == REGRA_SERVIDORES_MOVIMENTADOS_COM_MENOS_DE_6_MESES_DE_INSTITUTO:
                lista_servidores = get_servidores_movimentados_com_menos_de_6_meses_de_instituto(buscar_str=buscar_str, setores=setores, uos=uos)

            if regra == AGRUPAMENTO_SERVIDORES_COM_ADESAO_VIGENTE_SEM_RIT_HOMOLOGADO_2_PERIODOS_ANTERIORES:
                lista_servidores = get_servidores_deveriam_mas_nao_tem_rit_homologado_nos_2_periodos_anteriores(
                    buscar_str=buscar_str, setores=setores, uos=uos
                )

            tipo_lista = 1
            if regra in [REGRA_PERFIL_GERAL_SERVIDOR, REGRA_HABILITACAO_SETOR]:
                tipo_lista = 2
            if regra in [
                REGRA_SERVIDORES_NO_PRIMEIRO_ANO_ESTAGIO_PROBATORIO,
                REGRA_SERVIDORES_NO_PRIMEIRO_SEGUNDO_ESTAGIO_PROBATORIO,
                REGRA_SERVIDORES_NO_PRIMEIRO_TERCEIRO_ESTAGIO_PROBATORIO,
            ]:
                tipo_lista = 3
            if regra == REGRA_SERVIDORES_MOVIMENTADOS_COM_MENOS_DE_6_MESES_DE_INSTITUTO:
                tipo_lista = 4

    return locals()


@rtr()
@permission_required(['pgd2.gestao_pgd2', 'pgd2.gestao_pgd2_comissao_sistemica'])
def relatorio_visao_geral_participantes(request):
    title = 'Visão Geral dos Servidores'

    """
    PGD (ParticipantePgd)
    1 - Total de participantes registrados no Siape em regime presencial
    2 - Total de participantes registrados no Siape em regime teletrabalho parcial
    3 - Total de participantes registrados no Siape em regime teletrabalho integral
    4 - Total de participantes registrados no Siape em regime teletrabalho no exterior (art. 12, VIII)
    5 - Total de participantes registrados no Siape em regime teletrabalho no exterior (art. 12, §7°)

    SOU GOV
    - presencial
    - parcial
    - integral
    - no exterior
    """

    modo_consulta = bool(request.GET)
    tipo_consulta = request.GET.get('consulta')

    # 1
    servidores_em_pgd_suap = ParticipantePgd.objects.filter(situacao=1).order_by('servidor__pessoa_fisica__nome')
    qtd_servidores_em_pgd_suap = servidores_em_pgd_suap.count()
    # 2
    servidores_em_pgd_sougov = Servidor.objects.vinculados().filter(participa_pgd=True).order_by('pessoa_fisica__nome')
    qtd_servidores_em_pgd_sougov = servidores_em_pgd_sougov.count()

    # 3
    servidores_em_pgd_suap_presencial = ParticipantePgd.objects.filter(situacao=1, modalidade_execucao=1).order_by('servidor__pessoa_fisica__nome')
    qtd_servidores_em_pgd_suap_presencial = servidores_em_pgd_suap_presencial.count()
    # 4
    servidores_em_pgd_sougov_presencial = (
        Servidor.objects.vinculados().filter(participa_pgd=True, modalidade_pgd__nome='presencial').order_by('pessoa_fisica__nome')
    )
    qtd_servidores_em_pgd_sougov_presencial = servidores_em_pgd_sougov_presencial.count()

    # 5
    servidores_em_pgd_suap_teletrabalho_parcial = ParticipantePgd.objects.filter(situacao=1, modalidade_execucao=2).order_by(
        'servidor__pessoa_fisica__nome'
    )
    qtd_servidores_em_pgd_suap_teletrabalho_parcial = servidores_em_pgd_suap_teletrabalho_parcial.count()
    # 6
    servidores_em_pgd_sougov_teletrabalho_parcial = (
        Servidor.objects.vinculados().filter(participa_pgd=True, modalidade_pgd__nome='parcial').order_by('pessoa_fisica__nome')
    )
    qtd_servidores_em_pgd_sougov_teletrabalho_parcial = servidores_em_pgd_sougov_teletrabalho_parcial.count()

    # 7
    servidores_em_pgd_suap_teletrabalho_integral = ParticipantePgd.objects.filter(situacao=1, modalidade_execucao=3).order_by(
        'servidor__pessoa_fisica__nome'
    )
    qtd_servidores_em_pgd_suap_teletrabalho_integral = servidores_em_pgd_suap_teletrabalho_integral.count()
    # 8
    servidores_em_pgd_sougov_teletrabalho_integral = (
        Servidor.objects.vinculados().filter(participa_pgd=True, modalidade_pgd__nome='integral').order_by('pessoa_fisica__nome')
    )
    qtd_servidores_em_pgd_sougov_teletrabalho_integral = servidores_em_pgd_sougov_teletrabalho_integral.count()

    # 9
    servidores_em_pgd_suap_teletrabalho_exterior1 = ParticipantePgd.objects.filter(situacao=1, modalidade_execucao=4).order_by(
        'servidor__pessoa_fisica__nome'
    )
    qtd_servidores_em_pgd_suap_teletrabalho_exterior1 = servidores_em_pgd_suap_teletrabalho_exterior1.count()
    # 10
    servidores_em_pgd_suap_teletrabalho_exterior2 = ParticipantePgd.objects.filter(situacao=1, modalidade_execucao=5).order_by(
        'servidor__pessoa_fisica__nome'
    )
    qtd_servidores_em_pgd_suap_teletrabalho_exterior2 = servidores_em_pgd_suap_teletrabalho_exterior2.count()
    # 11
    servidores_em_pgd_sougov_teletrabalho__exterior = (
        Servidor.objects.vinculados().filter(participa_pgd=True, modalidade_pgd__nome='no exterior').order_by('pessoa_fisica__nome')
    )
    qtd_servidores_em_pgd_sougov_teletrabalho__exterior = servidores_em_pgd_sougov_teletrabalho__exterior.count()

    # 12
    # servidores_em_pgd_apenas_suap = SolicitacaoAdesaoServidor.get_servidores_em_pgd().order_by('pessoa_fisica__nome')
    # qtd_servidores_em_pgd_apenas_suap = servidores_em_pgd_apenas_suap.count()
    # 13
    # servidores_em_pgd_apenas_suap_presencial = PlanoIndividualTrabalho.get_servidores_pgd_por_modalidade(3).order_by('pessoa_fisica__nome')
    # qtd_servidores_em_pgd_apenas_suap_presencial = servidores_em_pgd_apenas_suap_presencial.count()

    lista_servidores = []
    regra_selecionada = None
    if modo_consulta:
        if tipo_consulta:
            # -----------
            if tipo_consulta == '1':
                lista_servidores = servidores_em_pgd_suap
                regra_selecionada = 'Dados do SUAP - Participantes em PGD'
            if tipo_consulta == '2':
                lista_servidores = servidores_em_pgd_sougov
                regra_selecionada = 'Dados do SOU GOV - Participantes em PGD'
            # -----------
            if tipo_consulta == '3':
                lista_servidores = servidores_em_pgd_suap_presencial
                regra_selecionada = 'Dados do SUAP - Participantes em PGD Presencial'
            if tipo_consulta == '4':
                lista_servidores = servidores_em_pgd_sougov_presencial
                regra_selecionada = 'Dados do SOU GOV - Participantes em PGD Presencial'
            # -----------
            if tipo_consulta == '5':
                lista_servidores = servidores_em_pgd_suap_teletrabalho_parcial
                regra_selecionada = 'Dados do SUAP - Participantes em PGD Teletrabalho Parcial'
            if tipo_consulta == '6':
                lista_servidores = servidores_em_pgd_sougov_teletrabalho_parcial
                regra_selecionada = 'Dados do SOU GOV - Participantes em PGD Teletrabalho Parcial'
            # -----------
            if tipo_consulta == '7':
                lista_servidores = servidores_em_pgd_suap_teletrabalho_integral
                regra_selecionada = 'Dados do SUAP - Participantes em PGD Teletrabalho Integral'
            if tipo_consulta == '8':
                lista_servidores = servidores_em_pgd_sougov_teletrabalho_integral
                regra_selecionada = 'Dados do SOU GOV - Participantes em PGD Teletrabalho Integral'
            # -----------
            if tipo_consulta == '9':
                lista_servidores = servidores_em_pgd_suap_teletrabalho_exterior1
                regra_selecionada = 'Dados do SOU GOV - Participantes em PGD Teletrabalho no exterior (art. 12, VIII)'
            if tipo_consulta == '10':
                lista_servidores = servidores_em_pgd_suap_teletrabalho_exterior2
                regra_selecionada = 'Dados do SOU GOV - Participantes em PGD Teletrabalho no exterior (art. 12, §7°)'
            if tipo_consulta == '11':
                lista_servidores = servidores_em_pgd_sougov_teletrabalho__exterior
                regra_selecionada = 'Dados do SOU GOV - Participantes em PGD Teletrabalho no exterior (independente da hipótese legal)'
            # -----------
            # if tipo_consulta == '12':
            #    lista_servidores = servidores_em_pgd_apenas_suap
            #    regra_selecionada = 'Dados do SUAP - Servidores em PGD'
            # if tipo_consulta == '13':
            #    lista_servidores = servidores_em_pgd_apenas_suap_presencial
            #    regra_selecionada = 'Dados do SUAP - Servidores em PGD Presencial'

            busca_participante = ['1', '3', '5', '7', '9', '10']
            busca_servidor = ['2', '4', '6', '8', '11', '12', '13']
            buscou_participante = True  # True para Participante e False para Servidor
            if tipo_consulta in busca_servidor:
                buscou_participante = False

            form = ConsultaMonitoramentoServidorSimples(request.GET or None, tipo_consulta=tipo_consulta)
            if form.is_valid():
                buscar_str = form.cleaned_data.get('buscar_str')
                setores = form.cleaned_data.get('setores')

                if tipo_consulta in busca_participante:
                    if buscar_str:
                        lista_servidores = lista_servidores.filter(
                            Q(servidor__pessoa_fisica__nome__icontains=buscar_str) | Q(servidor__matricula__icontains=buscar_str)
                        )
                    if setores:
                        lista_servidores = lista_servidores.filter(servidor__setor__in=setores)
                if tipo_consulta in busca_servidor:
                    if buscar_str:
                        lista_servidores = lista_servidores.filter(Q(pessoa_fisica__nome__icontains=buscar_str) | Q(matricula__icontains=buscar_str))
                    if setores:
                        lista_servidores = lista_servidores.filter(setor__in=setores)

    return locals()


@rtr()
@permission_required(['pgd2.gestao_pgd2', 'pgd2.gestao_pgd2_comissao_sistemica'])
def visao_geral_pes_pit(request):
    title = f'Visão Geral PESs e {nomenclatura.plano_individual_de_trabalho_sigla_plural_pgd2}'

    pits_nao_cancelados = PlanoIndividualTrabalho.objects.exclude(situacao=PlanoIndividualTrabalho.CANCELADO)

    pess_aprovados = PlanoEntregasSetorial.get_pess_aprovados()

    periodo_pes_atual = PeriodoPes.objects.filter(data_inicio__lte=get_datetime_now().date(), data_fim__gte=get_datetime_now().date())
    if periodo_pes_atual:
        periodo_pes_atual = periodo_pes_atual.first()
    else:
        periodo_pes_atual = None

    periodo_pes_anterior = None
    if periodo_pes_atual:
        try:
            periodo_pes_anterior = (
                PeriodoPes.objects.exclude(Q(id=periodo_pes_atual.id) | Q(data_inicio__gt=periodo_pes_atual.data_inicio))
                .order_by('-data_inicio')
                .first()
            )
        except Exception:
            pass

    periodo_pit_atual = PeriodoPitRit.objects.filter(
        cancelado=False, data_inicio__lte=get_datetime_now().date(), data_fim__gte=get_datetime_now().date()
    )
    if periodo_pit_atual:
        periodo_pit_atual = periodo_pit_atual.first()
    else:
        periodo_pit_atual = None

    periodo_pit_anterior = None
    if periodo_pit_atual:
        try:
            periodo_pit_anterior = (
                PeriodoPitRit.objects.exclude(Q(id=periodo_pit_atual.id) | Q(data_inicio__gt=periodo_pit_atual.data_inicio))
                .order_by('-data_inicio')
                .first()
            )
        except Exception:
            pass

    # Plano de entregas
    # -------------------

    # Qtd setores habilitados no PGD
    setores_habilitados = SetorHabilitacao.get_setores_habilitados()
    qtd_setores_habilitados = setores_habilitados.count()

    # Qtd de plano de entregas aprovado para o período atual
    qtd_pes_periodo_atual = None
    if periodo_pes_atual:
        qtd_pes_periodo_atual = pess_aprovados.filter(periodo_pes=periodo_pes_atual).count()

    # Qtd planos de entrega com análise de execução realizada -- periodo anterior
    qtd_pess_com_analise_execucao = None
    if periodo_pes_anterior:
        qtd_pess_com_analise_execucao = (
            pess_aprovados.filter(periodo_pes=periodo_pes_anterior).filter(situacao_avaliacao=PlanoEntregasSetorial.SOLICITADO_AVALIACAO).count()
        )

    # Qtd planos de entrega com avaliacao de execução realizada -- periodo anterior
    qtd_pess_com_avaliacao_execucao = None
    if periodo_pes_anterior:
        qtd_pess_com_avaliacao_execucao = (
            pess_aprovados.filter(periodo_pes=periodo_pes_anterior).filter(situacao_avaliacao=PlanoEntregasSetorial.SOLICITADO_AVALIACAO).count()
        )

    # Plano de trabalho
    # -------------------

    # Núm. participantes únicos e ativos com pelo menos 1 plano de trabalho em execução (no periodo atual)
    qtd_pits_em_execucao_no_periodo_atual = PlanoIndividualTrabalho.get_pits_foram_homologados_ao_menos_uma_vez().filter(
        periodo_pit_rit=periodo_pit_atual
    )
    qtd_pits_em_execucao_no_periodo_atual = qtd_pits_em_execucao_no_periodo_atual.filter(rit_em_execucao=True)
    qtd_pits_em_execucao_no_periodo_atual = qtd_pits_em_execucao_no_periodo_atual.order_by('adesao__servidor').distinct('adesao__servidor').count()

    # Núm. participantes únicos e ativos sem plano de trabalho concluído - sem relatório homologado (no periodo atual)
    qtd_pits_sem_execucao_no_periodo_atual = PlanoIndividualTrabalho.get_pits_foram_homologados_ao_menos_uma_vez().filter(
        periodo_pit_rit=periodo_pit_atual
    )
    qtd_pits_sem_execucao_no_periodo_atual = qtd_pits_sem_execucao_no_periodo_atual.filter(rit_em_execucao=True)
    qtd_pits_sem_execucao_no_periodo_atual = qtd_pits_sem_execucao_no_periodo_atual.exclude(situacao_rit=PlanoIndividualTrabalho.HOMOLOGADO_RIT)
    qtd_pits_sem_execucao_no_periodo_atual = qtd_pits_sem_execucao_no_periodo_atual.order_by('adesao__servidor').distinct('adesao__servidor').count()

    # Núm. planos de trabalho pendentes de avaliação (no periodo anterior) -- que deveria ter sido homologado e não foi
    qtd_pits_nao_homologados_periodo_anterior = pits_nao_cancelados.filter(periodo_pit_rit=periodo_pit_anterior)
    qtd_pits_nao_homologados_periodo_anterior = qtd_pits_nao_homologados_periodo_anterior.exclude(
        id__in=PlanoIndividualTrabalho.get_pits_foram_homologados_ao_menos_uma_vez().filter(periodo_pit_rit=periodo_pit_anterior).values_list('id')
    )
    qtd_pits_nao_homologados_periodo_anterior = qtd_pits_nao_homologados_periodo_anterior.count()

    return locals()


@rtr()
@permission_required(['pgd2.gestao_pgd2', 'pgd2.gestao_pgd2_comissao_sistemica'])
def desligamento(request):
    title = 'Desligamentos'

    AGRUPAMENTO_SERVIDORES_EM_PGD = 1
    AGRUPAMENTO_SERVIDORES_DESLIGADOS = 2

    AGRUPAMENTO_CHOICES = [
        [AGRUPAMENTO_SERVIDORES_EM_PGD, 'Servidores em PGD'],
        [AGRUPAMENTO_SERVIDORES_DESLIGADOS, 'Servidores desligados do PGD'],
    ]

    lista_servidores = []

    form = ConsultaDesligamento(request.GET or None, mon_coices=AGRUPAMENTO_CHOICES)
    if form.is_valid():
        buscar_str = form.cleaned_data.get('buscar_str')
        setores = form.cleaned_data.get('setores')
        regra = int(form.cleaned_data.get('regra'))

        if regra == AGRUPAMENTO_SERVIDORES_EM_PGD:
            lista_servidores = get_servidores_em_pgd(buscar_str=buscar_str, setores=setores)

        if regra == AGRUPAMENTO_SERVIDORES_DESLIGADOS:
            lista_servidores = get_servidores_desligados(buscar_str=buscar_str, setores=setores)
    else:
        lista_servidores = get_servidores_em_pgd(buscar_str=None, setores=None)

    return locals()


@rtr()
@permission_required(['pgd2.gestao_pgd2'])
def cadastrar_desligamento_pgd_gestao(request, matricula):
    operacao = 'cadastrar' if request.GET.get('adesao_id') else 'listar'
    adesao_id = request.GET.get('adesao_id')

    title = 'Desligamento - Adesões'

    adesao = None
    pode_cadastrar, msgs_erro = None, None
    adesoes = SolicitacaoAdesaoServidor.objects.filter(servidor__matricula=matricula).order_by('data_inicio')
    if operacao == 'cadastrar':
        adesao = adesoes.filter(id=adesao_id).first()

        # Cadastra desligamento
        if not adesao.tem_desligamento_cadastrado:
            pode_cadastrar, msgs_erro = DesligamentoPgdServidor.gestao_pode_cadastrar(
                user=request.user, adesao=adesao, retornar_lista_erros=True, data_desligamento_efeitos_a_partir_de=None
            )
            title = f'Desligamento - Cadastrar - {adesao.servidor}'

            justificativas = JustificativaDesligamentoPgd.get_justificativas_ativas()

            # Cadastro
            form = CadastrarDesligamentoGestaoPgdForm(
                request.POST or None,
                request=request,
                lista_justificativas=justificativas,
            )
            if request.method == 'POST':
                if form.is_valid():
                    data_desligamento_efeitos_a_partir_de = form.cleaned_data.get('data_desligamento_efeitos_a_partir_de')
                    pode_cadastrar, msgs_erro = DesligamentoPgdServidor.gestao_pode_cadastrar(
                        user=request.user,
                        adesao=adesao,
                        retornar_lista_erros=True,
                        data_desligamento_efeitos_a_partir_de=data_desligamento_efeitos_a_partir_de,
                    )
                    if pode_cadastrar:
                        d = DesligamentoPgdServidor()
                        d.adesao = adesao
                        d.justificativa = form.cleaned_data.get('justificativa')
                        d.observacao = form.cleaned_data.get('observacao')
                        d.data_desligamento_efeitos_a_partir_de = form.cleaned_data.get('data_desligamento_efeitos_a_partir_de')
                        d.data_cadastro = get_datetime_now()
                        d.usuario_cadastro = request.user
                        d.save()

                        # Se tem punicao de dias na justificativa
                        if d.justificativa.qtd_dias_punicao > 0:
                            carencia_nova_adesao_ate = d.data_desligamento_efeitos_a_partir_de + relativedelta(days=d.justificativa.qtd_dias_punicao)
                            d.data_pode_solicitar_nova_adesao = carencia_nova_adesao_ate
                            d.save()
                            adesao.data_pode_solicitar_nova_adesao = d.data_pode_solicitar_nova_adesao

                        # Cadastra deligamento no PIT
                        adesao.data_desligamento_efeitos_a_partir_de = d.data_desligamento_efeitos_a_partir_de
                        adesao.data_desligamento_carencia_ate = d.data_desligamento_efeitos_a_partir_de + relativedelta(
                            days=PlanoIndividualTrabalho.CARENCIA_PARA_EDICAO_PIT_SEM_ADESAO_VIGENTE
                        )
                        adesao.save()

                        # Calcula os PITs/RITs da adesao
                        # Calcula os PITs não cancelados e sem RIT homologado
                        pits_calcular = adesao.get_pits_todos().exclude(
                            Q(situacao=PlanoIndividualTrabalho.CANCELADO) | Q(situacao_rit=PlanoIndividualTrabalho.HOMOLOGADO_RIT)
                        )
                        for pit in pits_calcular:
                            pit.calcular_pit()

                        ip = get_client_ip(request)
                        justificativa = form.cleaned_data.get('justificativa')
                        ra_obs = f'O Desligamento do PGD da {adesao.__str__()} foi cadastrado PELA GESTÃO com daata de efeitos a partir de "{format_datetime(data_desligamento_efeitos_a_partir_de)}" mediante seguinte justificativa "{justificativa}".'
                        RegistroAcaoSolicitacaoAdesaoServidor.objects.create(
                            tipo=RegistroAcaoSolicitacaoAdesaoServidor.TIPO_DESLIGAMENTO, solicitacao=adesao, ip=ip, observacao=ra_obs
                        )

                        url = reverse('cadastrar_desligamento_pgd_gestao_pgd2', args=[matricula])
                        return httprr(url, 'Desligamento cadastrado sucesso.')

        # Remove desligamento
        if adesao.tem_desligamento_cadastrado:
            title = f'Desligamento - Remover - {adesao.servidor}'
            form = RemoverDesligamentoGestaoPgdForm(request.POST or None, request=request)
            if request.method == 'POST':
                if form.is_valid():
                    desligamento = DesligamentoPgdServidor.objects.filter(adesao=adesao, data_cancelamento__isnull=True).first()
                    desligamento.data_cancelamento = get_datetime_now()
                    desligamento.save()

                    adesao = desligamento.adesao
                    adesao.data_desligamento_efeitos_a_partir_de = None
                    adesao.data_desligamento_carencia_ate = None
                    adesao.data_pode_solicitar_nova_adesao = None
                    adesao.save()

                    # Calcula os PITs/RITs da adesao
                    # Calcula os PITs não cancelados e sem RIT homologado
                    pits_calcular = adesao.get_pits_todos().exclude(
                        Q(situacao=PlanoIndividualTrabalho.CANCELADO) | Q(situacao_rit=PlanoIndividualTrabalho.HOMOLOGADO_RIT)
                    )
                    for pit in pits_calcular:
                        pit.calcular_pit()

                    ip = get_client_ip(request)
                    justificativa = form.cleaned_data.get('observacao')
                    ra_obs = f'O Desligamento foi cancelado PELA GESTÃO mediante a justificativa "{justificativa}".'
                    RegistroAcaoSolicitacaoAdesaoServidor.objects.create(
                        tipo=RegistroAcaoSolicitacaoAdesaoServidor.TIPO_DESLIGAMENTO_CANCELADO,
                        solicitacao=desligamento.adesao,
                        ip=ip,
                        observacao=ra_obs,
                    )

                    url = reverse('cadastrar_desligamento_pgd_gestao_pgd2', args=[matricula])
                    return httprr(url, 'Desligamento cancelado com sucesso.')

    return locals()


@rtr()
@permission_required('rh.chefe')
def listar_pes_chefe_deve_analisar(request):
    """Lista os PESs aguardando análise da execução pelo chefe.

    Separa em dois conjuntos: `pess_deve` (chefe direto, ação obrigatória) e
    `pess_pode` (qualquer chefe na cadeia, ação opcional).
    """
    title = 'Analisar Execução de Planos de Entregas Setorial'

    pess_deve = PlanoEntregasSetorial.get_pess_pendendentes_analise_execucao(user=request.user, apenas_chefe_direto=True).order_by(
        'periodo_pes__data_inicio'
    )
    pess_pode = PlanoEntregasSetorial.get_pess_pendendentes_analise_execucao(user=request.user, apenas_chefe_direto=False).order_by(
        'periodo_pes__data_inicio'
    )

    return locals()


@rtr()
@permission_required('rh.chefe')
def listar_pes_chefe_deve_avaliar(request):
    """Lista os PESs aguardando avaliação final pelo chefe do setor superior."""
    title = 'Avaliar Execução de Planos de Entregas Setorial'

    pess = PlanoEntregasSetorial.get_pess_pendendentes_avaliacao(user=request.user).order_by('periodo_pes__data_inicio')

    return locals()


@rtr()
@permission_required('rh.eh_servidor')
def visualizar_acoes_periodo_rit(request, pit_id):
    pit = get_object_or_404(PlanoIndividualTrabalho, pk=pit_id)
    analista = AnalistaDesenvolvedor.objects.filter(usuario=request.user).first()
    if not pit.pode_visualizar_rit(request.user) or not analista:
        raise PermissionDenied

    title = f'Contribuições relacionadas ao {pit.get_verbose_rit()}'

    areas = get_acoes_por_periodo(request, pit.adesao.servidor.get_user(), pit.data_inicio, pit.data_fim)

    gitlab = ContribuicoesGitlab(gitlab_username=analista.username_gitlab)
    gitlab.obter_contribuicoes(data_inicio=pit.data_inicio, data_final=pit.data_fim)

    issues_relacionadas_a_erros = gitlab.get_issues_relacionadas_a_erros()
    merge_requests_relacionadas_a_erros = gitlab.get_merge_requests_relacionadas_a_erros()

    issues_nao_relacionadas_a_erros = gitlab.get_issues_nao_relacionadas_a_erros()
    merge_requests_nao_relacionadas_a_erros = gitlab.get_merge_requests_nao_relacionadas_a_erros()

    # outras_contribuicoes = gitlab.get_outras_contribuicoes()

    qtd_dados_gitlab = (
        len(issues_relacionadas_a_erros)
        + len(merge_requests_relacionadas_a_erros)
        + len(issues_nao_relacionadas_a_erros)
        + len(merge_requests_nao_relacionadas_a_erros)
    )

    return locals()
