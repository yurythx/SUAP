import datetime
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.db.models.aggregates import Sum
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from redis.exceptions import LockError

from comum.models import Ano
from djtools import layout
from djtools.templatetags.filters import format_datetime
from djtools.utils import XlsResponse, atomic, httprr, permission_required, render_pdf_from_template_with_wkhtmltopdf, rtr
from licenca_capacitacao import tasks
from licenca_capacitacao.forms import (
    BuscarServidoresForm,
    CancelarPedidoGestaoForm,
    CriarProcessamentoForm,
    EditarDataIniExercicioForm,
    EditarOrdemClassificacaoGestaoForm,
    FiltroQuadroLicencaCapacitacaoForm,
    ImportarResultadoFinalForm,
    ServidorComplementarForm,
    SolicitarDesistenciaForm,
)
from licenca_capacitacao.models import (
    AnexosEdital,
    AnexosPedidoLicCapacitacaoSubmissao,
    CalculoAquisitivoUsofrutoServidorEdital,
    CalculosGeraisServidorEdital,
    CodigoAfastamentoCapacitacao,
    CodigoAfastamentoNaoContabilizaExercicio,
    CodigoLicencaCapacitacao,
    DadosProcessamentoEdital,
    EditalLicCapacitacao,
    LicCapacitacaoPorDia,
    PedidoLicCapacitacao,
    PeriodoPedidoLicCapacitacao,
    ProcessamentoEdital,
    ServidorComplementar,
    ServidorDataInicioExercicioAjustada,
    SituacaoContabilizaExercicio,
    SolicitacaoAlteracaoDados,
    SolicitacaoAlteracaoDadosAdicionar,
    SolicitacaoAlteracaoDataInicioExercicio,
    SolicitacaoAlteracaoDataInicioExercicioAdicionar,
)
from licenca_capacitacao.regras_calculos import calcular, checklist
from licenca_capacitacao.utils import get_e
from rh.models import Servidor, ServidorAfastamento


@layout.inscricao()
def index_inscricoes(request):
    inscricoes = []

    if request.user.eh_servidor:
        hoje = datetime.datetime.now()
        editais_abertos = EditalLicCapacitacao.objects.filter(
            ativo=True, periodo_submissao_inscricao_inicio__lte=hoje, periodo_submissao_inscricao_final__gte=hoje
        )
        for edital in editais_abertos:
            inscricoes.append(
                {
                    'url': '/admin/licenca_capacitacao/editalliccapacitacao/',
                    'titulo': f'Submeter pedido de <strong>Licença Capacitação</strong> para {edital.titulo}.',
                    'prazo': edital.periodo_submissao_inscricao_final,
                }
            )

    return inscricoes


@rtr()
@login_required
def quadro(request):
    title = 'Quadro Geral de Servidores - Licença Capacitação'

    ano_atual = Ano.objects.get(ano=datetime.date.today().year)
    afastamentos_servidor = LicCapacitacaoPorDia.objects.filter(ano=ano_atual).order_by('ano__ano', 'mes', 'dia')

    form = FiltroQuadroLicencaCapacitacaoForm(request.POST or None)
    if form.is_valid():
        if form.cleaned_data.get('ano'):
            afastamentos_servidor = LicCapacitacaoPorDia.objects.filter(ano_id=form.cleaned_data.get('ano')).order_by('ano__ano', 'mes', 'dia')

    # ---------------------------------
    # CADASTRADOS NO SIAPE
    # ---------------------------------
    if afastamentos_servidor:
        ano_atual = afastamentos_servidor[0].ano.ano
        mes_atual = afastamentos_servidor[0].mes
        lista_ano_mes = []
        lista_dias_qtd = []
        dict_ano_mes_dia = {}
        dict_ano_mes_dia['ano'] = ano_atual
        dict_ano_mes_dia['mes'] = f'{mes_atual:02d}'

        for afs in afastamentos_servidor:
            if ano_atual != afs.ano.ano:
                ano_atual = afs.ano.ano

            if ano_atual == afs.ano.ano and mes_atual != afs.mes:
                mes_atual = afs.mes
                # Novo Ano Mes
                dict_ano_mes_dia['dias'] = lista_dias_qtd
                dict_ano_mes_dia['faltam_para_31dias'] = 31 - len(lista_dias_qtd)
                lista_ano_mes.append(dict_ano_mes_dia)
                lista_dias_qtd = []
                dict_ano_mes_dia = {}
                dict_ano_mes_dia['ano'] = ano_atual
                dict_ano_mes_dia['mes'] = f'{mes_atual:02d}'

            dict_ano_mes_dia['data'] = date(ano_atual, mes_atual, 1)
            dict_dia_qtd = {}
            dict_dia_qtd['dia'] = f'{afs.dia:02d}'
            dict_dia_qtd['qtd_taes'] = afs.qtd_taes_geral
            dict_dia_qtd['qtd_docentes'] = afs.qtd_docentes_geral
            dict_dia_qtd['qtd_total'] = afs.qtd_total_geral
            lista_dias_qtd.append(dict_dia_qtd)

        dict_ano_mes_dia['dias'] = lista_dias_qtd
        lista_ano_mes.append(dict_ano_mes_dia)

    return locals()


@rtr()
@login_required
def visualizar_servidores_por_dia(request, data):
    # -------------------------------------------------------------------
    # O calculo da lista servidores deve ser o mesmo considerado para a criacao do quadro
    # - Observar
    #   - comando processar_quantitativo_lic_capacitacao
    # -------------------------------------------------------------------

    data = date(int(data[4:8]), int(data[2:4]), int(data[0:2]))
    # Busca os dados do SIAPE de acordo com a data solicitada
    # Formato: 31032020

    title = f'Servidores em Licença Capacitação ({data.day}/{data.month}/{data.year})'

    # licenciados que ja estao no siape
    codigos_lc = EditalLicCapacitacao.get_todos_os_codigos_licenca_capacitacao()
    # afastamentos_servidor = ServidorAfastamento.objects.filter(
    #    afastamento__codigo=AfastamentoSiape.LICENCA_CAPACITACAO_3_MESES, cancelado=False).order_by('data_inicio')
    afastamentos_servidor = ServidorAfastamento.objects.filter(afastamento__codigo__in=codigos_lc, cancelado=False).order_by('data_inicio')
    lista = afastamentos_servidor.filter(data_inicio__lte=data, data_termino__gte=data)

    # licenciados que nao estao no siape
    licenciados_suap = PedidoLicCapacitacao.get_pedidos_aprovado_em_definitivo_nao_cadastrados_no_siape_por_data(data, None)

    return locals()


@rtr()
@login_required
def visualizar_edital_gestao(request, edital_id):
    # -------------------------------------------------------------------
    # Visualizar edital como Gestor/Equipe
    # -------------------------------------------------------------------
    edital = get_object_or_404(EditalLicCapacitacao, pk=edital_id)
    title = f'{edital}'

    if not EditalLicCapacitacao.eh_perfil_gestao(request.user):
        raise PermissionDenied

    eh_gestao = True

    estah_em_aberto_antes_submissao = edital.estah_em_aberto_antes_submissao()

    # Permissoes
    # --------------
    pode_editar = edital.can_change(user=request.user)
    pode_ativar_edital = edital.pode_ativar(user=request.user)
    pode_inativar_edital = edital.pode_inativar(user=request.user)
    pode_criar_processamento_parcial = ProcessamentoEdital.pode_criar_processamento(
        request.user, edital, ProcessamentoEdital.PROCESSAMENTO_PARCIAL, False
    )
    pode_criar_processamento_final = ProcessamentoEdital.pode_criar_processamento(
        request.user, edital, ProcessamentoEdital.PROCESSAMENTO_FINAL, False
    )
    # TODO rever essa regra quando for homologar a parte de Processamento
    # pode_calcular_parametros_edital = ProcessamentoEdital.pode_recalcular_parametros_edital(request.user, edital, False)
    pode_calcular_parametros_edital = pode_editar
    # TODO rever essa regra quando for homologar a parte de Processamento
    pode_visualizar_servidores_aptos = ServidorComplementar.pode_visualizar(request.user, edital)
    pode_cadastrar_servidores_aptos = ServidorComplementar.pode_cadastrar(request.user, edital)

    pode_editar_calculos_submissao_servidor = CalculoAquisitivoUsofrutoServidorEdital.pode_editar(
        request.user, edital, False
    ) and CalculosGeraisServidorEdital.pode_editar(request.user, edital, False)
    pode_exportar_dados_dos_pedidos = EditalLicCapacitacao.pode_exportar_dados_dos_pedidos(request.user, edital, False)
    pode_importar_resultado_final = EditalLicCapacitacao.pode_importar_resultado_final(request.user, edital, False)

    # Dados
    # --------------
    processamentos_do_edital = ProcessamentoEdital.get_processamentos_do_edital(edital)
    arquivos_do_edital = AnexosEdital.objects.filter(edital=edital).order_by('-data_cadastro')

    qtd_sol_alt_dt_ini_exercicio_a_analisar = SolicitacaoAlteracaoDataInicioExercicio.objects.filter(
        edital=edital, pode_analisar=True, data_hora_parecer__isnull=True
    ).count()
    qtd_sol_alt_dados_exercicio_a_analisar = SolicitacaoAlteracaoDados.objects.filter(
        edital=edital, pode_analisar=True, data_hora_parecer__isnull=True
    ).count()

    return locals()


@rtr()
@login_required
def visualizar_edital_servidor(request, edital_id):
    # -------------------------------------------------------------------
    # Visualizar edital como Servidor
    # -------------------------------------------------------------------
    edital = get_object_or_404(EditalLicCapacitacao, pk=edital_id)
    title = f'{edital}'
    if not edital.pode_visualizar_como_servidor(user=request.user):
        raise PermissionDenied

    pode_cadastrar_pedido = edital.pode_cadastrar_pedido(user=request.user)
    meus_pedidos = PedidoLicCapacitacao.objects.filter(servidor=request.user.get_relacionamento(), edital=edital)
    try:
        with atomic(f'edital_lic_capacitacao_lock:{edital.id}_{request.user.get_relacionamento().id}', timeout=10):
            calcular(edital, request.user.get_relacionamento())
    except LockError:
        return httprr('/', 'Erro ao tentar calcular os dados do edital.', tag='error')

    pode_mostrar_todas_abas = pode_cadastrar_pedido or meus_pedidos

    eh_gestao = False

    estah_em_aberto_antes_submissao = edital.estah_em_aberto_antes_submissao()
    estah_em_aberto = edital.estah_em_aberto()
    estah_finalizado = edital.estah_finalizado()

    if estah_em_aberto:
        servidor_estah_apto_no_edital = EditalLicCapacitacao.servidor_estah_apto_no_edital(edital, request.user.get_relacionamento())

    if pode_mostrar_todas_abas:
        # Permissoes
        # --------------
        pode_solicitar_alteracao_dt_ini_exercicio = SolicitacaoAlteracaoDataInicioExercicioAdicionar.pode_solicitar(request.user, edital, False)
        pode_excluir_solicitacao_alteracao_dt_ini_exercicio = SolicitacaoAlteracaoDataInicioExercicioAdicionar.pode_excluir(
            request.user, edital, False
        )
        pode_solicitar_alteracao_dados = SolicitacaoAlteracaoDadosAdicionar.pode_solicitar(request.user, edital, False)
        pode_excluir_alteracao_dados = SolicitacaoAlteracaoDadosAdicionar.pode_excluir(request.user, edital, False)

        # Dados
        # --------------
        arquivos_do_edital = AnexosEdital.objects.filter(edital=edital).order_by('-data_cadastro')
        processamentos_do_edital = ProcessamentoEdital.get_processamentos_finalizado_e_definitivos_do_edital(edital)
        # apos ter sido shmetido e nao poder mais cadastrar pedido -- apenas a gestao pode calcular
        if pode_cadastrar_pedido:
            try:
                with atomic(f'edital_lic_capacitacao_lock:{edital.id}_{request.user.get_relacionamento().id}', timeout=10):
                    calcular(edital, request.user.get_relacionamento())
            except LockError:
                return httprr('/', 'Erro ao tentar calcular os dados do edital.', tag='error')
        calculos_exercicio, calculos_quinquenios, licencas_capacitacao_servidor, afastamentos_nao_conta_como_efet_exerc = (
            EditalLicCapacitacao.get_dados_calculos_servidor_no_edital(edital, request.user.get_relacionamento())
        )
        solicitacoes_alteracao_dt_ini_efet_execicio_servidor_no_edital = (
            SolicitacaoAlteracaoDataInicioExercicioAdicionar.get_solicitacoes_servidor_no_edital(edital, request.user.get_relacionamento())
        )
        solicitacoes_alteracao_dados_servidor_no_edital = SolicitacaoAlteracaoDadosAdicionar.get_solicitacoes_servidor_no_edital(
            edital, request.user.get_relacionamento()
        )

        # Avisos
        # --------------
        lista_msgs_solicitacoes_alteracao_de_dados = []
        lista_msgs_solicitacoes_alteracao_de_dados.append(
            'Só é possível "Adicionar Solicitação de Alteração de Data de início de exercício" se a Data de Início do exercício estiver como "AJUSTADA PELA GESTÃO" (isso pode ser checado nos "Parâmetros utilizados pelo checklist de submissão").'
        )
        lista_msgs_solicitacoes_alteracao_de_dados.append(
            'As solicitações de alteração só poderão ser cadastradas se o edital estiver em ABERTO, se existirem pedidos e se não houver algum pedido SUBMETIDO neste edital.'
        )
        lista_msgs_solicitacoes_alteracao_de_dados.append(
            'As solicitações de alteração ficarão como PENDENTES DE ENVIO se pelo o menos um dos seus pedidos não for submetido neste edital.'
        )
        lista_msgs_solicitacoes_alteracao_de_dados.append(
            'As solicitações de alteração ficarão como PENDENTES DE ANÁLISE se ao menos um dos seus pedidos for submetido neste edital.'
        )
        lista_msgs_solicitacoes_alteracao_de_dados.append(
            'As solicitações de alteração ficarão como ENVIO CANCELADO se todos os seus pedidos deste edital forem cancelados.'
        )
        lista_msgs_solicitacoes_alteracao_de_dados.append(
            'É permitido cadastrar apenas uma solicitação de alteração de data de início de exercício .'
        )

        lista_msgs_parametros_checklist = []
        lista_msgs_parametros_checklist.append(
            'Se você discorda do "Início do exercício" deve cadastrar uma "Solicitação de Alteração de Data de início de exercício".'
        )
        lista_msgs_parametros_checklist.append('Se você discorda de qualquer outro dado deve cadastrar uma "Solicitações de Alteração de Dados".')

        lista_msgs_geral = []
        # Se ainda existem pedidos pendentes de envio
        if pode_cadastrar_pedido and EditalLicCapacitacao.existe_algum_pedido_pendente_de_submissao_do_servidor_no_edital(
            edital, request.user.get_relacionamento()
        ):
            lista_msgs_geral.append('Ao menos um dos seus pedidos está como "PENDENTE DE SUBMISSÃO" neste edital.')
        # Se ainda não cadastrou algum pedido
        if pode_cadastrar_pedido and not EditalLicCapacitacao.existe_algum_pedido_do_servidor_no_edital(edital, request.user.get_relacionamento()):
            lista_msgs_geral.append('Você ainda não cadastrou pedidos neste edital.')
        if pode_cadastrar_pedido and edital.qtd_max_periodos_por_pedido == 1:
            lista_msgs_geral.append('Cada pedido corresponde a uma parcela. Portanto, para cada parcela deve ser cadastrado um pedido.')

        # Resultado pessoal
        meus_resultados = ProcessamentoEdital.get_processamentos_finalizado_e_definitivos_do_edital_por_servidor(
            edital, request.user.get_relacionamento()
        )

    else:
        arquivos_do_edital = AnexosEdital.objects.filter(edital=edital).order_by('-data_cadastro')

    return locals()


@rtr()
@transaction.atomic
@login_required
def excluir_solicitacao_alteracao_dt_inicio_exercicicio_servidor(request, solicitacao_id):
    sol = get_object_or_404(SolicitacaoAlteracaoDataInicioExercicioAdicionar, pk=solicitacao_id)
    url = reverse('visualizar_edital_servidor', args=[sol.edital.id])

    try:
        SolicitacaoAlteracaoDataInicioExercicioAdicionar.pode_excluir(request.user, sol.edital, True)
        sol.delete()
        return httprr(url, 'Solicitação excluída com sucesso.')
    except Exception as e:
        return httprr(url, f'Erro ao tentar excluir uma Solicitação de Alteração de Data de início de exercício: {e}', tag='error')


@rtr()
@transaction.atomic
@login_required
def excluir_solicitacao_alteracao_dados_servidor(request, solicitacao_id):
    sol = get_object_or_404(SolicitacaoAlteracaoDadosAdicionar, pk=solicitacao_id)
    url = reverse('visualizar_edital_servidor', args=[sol.edital.id])

    try:
        SolicitacaoAlteracaoDadosAdicionar.pode_excluir(request.user, sol.edital, True)
        sol.delete()
        return httprr(url, 'Solicitação excluída com sucesso.')
    except Exception as e:
        return httprr(url, f'Erro ao tentar excluir uma Solicitação de Alteração de Dados: {e}', tag='error')


@login_required
def operacao_pedido_licenca_capacitacao(request, pedido_id, operacao):
    pedido = get_object_or_404(PedidoLicCapacitacao, pk=pedido_id)
    if operacao not in ['submeter_pedido', 'desfazer_pedido', 'cancelar_pedido', 'descancelar_pedido']:
        raise PermissionDenied

    url = f'/licenca_capacitacao/visualizar_pedido_servidor/{pedido.id}/'
    try:
        if operacao == 'submeter_pedido':
            tem_erro, _lista_verificacao = checklist(pedido)
            if tem_erro:
                raise Exception('Impossível submeter pedido de licença capacitação. Verifique o checklist de submissão.')
            PedidoLicCapacitacao.submeter_pedido(pedido, request.user)
        elif operacao == 'desfazer_pedido':
            PedidoLicCapacitacao.desfazer_sumbmissao_pedido(pedido, request.user)
        elif operacao == 'cancelar_pedido':
            PedidoLicCapacitacao.cancelar_pedido(pedido, request.user)
        else:
            PedidoLicCapacitacao.descancelar_pedido(pedido, request.user)
        EditalLicCapacitacao.habilitar_analise_das_solicitacoes_do_servidor_no_edital(pedido.edital, pedido.servidor)

    except Exception as e:
        return httprr(url, f'Erro: {e}', tag='error')

    return httprr(url, 'Operação executada com sucesso.')


@rtr('licenca_capacitacao/templates/visualizar_pedido_servidor_gestao.html')
@login_required
def visualizar_pedido_servidor(request, pedido_id):
    pedido = get_object_or_404(PedidoLicCapacitacao, pk=pedido_id)
    servidor = pedido.servidor

    if not pedido.pode_visualizar(user=request.user):
        raise PermissionDenied

    if not pedido.edital.pode_visualizar_como_servidor(user=request.user):
        raise PermissionDenied

    title = f'Pedido de Licença Capacitação - {pedido.edital} - {servidor}'

    visualizar_como_servidor = True
    try:
        with atomic(f'edital_lic_capacitacao_lock:{pedido.edital.id}_{servidor.id}', timeout=10):
            calcular(pedido.edital, servidor)
    except LockError:
        return httprr('/', 'Erro ao tentar calcular os dados do edital.', tag='error')

    # Permissoes
    # -----------------
    pode_editar = pedido.pode_editar(request.user)
    pode_submeter = pedido.pode_submeter(request.user)
    pode_desfazer_submissao = pedido.pode_desfazer_submissao(request.user)
    pode_cancelar = pedido.pode_cancelar(request.user)
    pode_descancelar = pedido.pode_descancelar(request.user)
    pode_imprimir_pedido = pedido.pode_imprimir_pedido(request.user)
    # Essa funcionalidade não será utilizada neste primeiro edital
    # - Estamos colocando False para desabilitar/ocultar especificamente para este edital
    # - Este fluxo será revisado durante a segunda fase de homologação conforme demanda 1027
    # pode_solicitar_desistencia_pedido = pedido.pode_solicitar_desistencia_pedido(request.user)
    pode_solicitar_desistencia_pedido = False
    pode_visualizar_desistencia = pedido.desistencia and pedido.situacao == PedidoLicCapacitacao.SUBMETIDO
    pode_recalcular_pedido = pedido.pode_recalcular_pedido(request.user)

    pode_solicitar_alteracao_dt_ini_exercicio = SolicitacaoAlteracaoDataInicioExercicioAdicionar.pode_solicitar(request.user, pedido.edital, False)
    pode_solicitar_alteracao_dados = SolicitacaoAlteracaoDadosAdicionar.pode_solicitar(request.user, pedido.edital, False)

    # Dados e calculos
    # -----------------
    # Atualiza categoria do servidor
    if pode_recalcular_pedido:
        pedido.save()

    # So recalcula se puder submeter OU se for super user
    tem_erro, lista_verificacao = checklist(pedido, calcula_pedido=pode_recalcular_pedido)
    if request.user.is_superuser:
        tem_erro, lista_verificacao = checklist(pedido, calcula_pedido=True)

    calculos_exercicio, calculos_quinquenios, licencas_capacitacao_servidor, afastamentos_nao_conta_como_efet_exerc = (
        EditalLicCapacitacao.get_dados_calculos_servidor_no_edital(pedido.edital, request.user.get_relacionamento())
    )

    periodos_solicitados = PeriodoPedidoLicCapacitacao.objects.filter(pedido=pedido).order_by('data_inicio')
    anexos = AnexosPedidoLicCapacitacaoSubmissao.objects.filter(pedido=pedido).order_by('descricao')

    # Mensagens
    # -----------------
    lista_msgs_geral_pedido_servidor = []
    if pedido.servidor_pedido_estah_sem_categoria():
        lista_msgs_geral_pedido_servidor.append(
            'Servidor não pode submeter por não ser possível verificar a qual categoria (Técnico-administrativo ou Docente) o servidor está vinculado.'
        )
    if pedido.situacao == PedidoLicCapacitacao.PENDENTE_SUBMISSAO and not (
        datetime.datetime.now() <= pedido.edital.periodo_submissao_inscricao_final
    ):
        lista_msgs_geral_pedido_servidor.append('Este pedido não pode mais ser submetido por já ter passado o período de submissão do Edital.')
    if pedido.situacao == PedidoLicCapacitacao.PENDENTE_SUBMISSAO and pode_submeter and tem_erro:
        lista_msgs_geral_pedido_servidor.append('Este pedido não pode ser submetido por conter erros no Checklist de submissão.')
    if pode_submeter and not tem_erro:
        lista_msgs_geral_pedido_servidor.append('Este pedido já está apto para ser submetido.')
    if pode_submeter and pedido.edital.qtd_max_periodos_por_pedido == 1:
        lista_msgs_geral_pedido_servidor.append('Cada pedido corresponde a uma parcela. Portanto, para cada parcela deve ser cadastrado um pedido.')
    if pedido.data_solicitacao_desistencia and not pedido.desistencia:
        lista_msgs_geral_pedido_servidor.append(
            'Você solicitou desistência para este pedido. Para maiores detalhes verique na aba Desistência no final dessa tela.'
        )
    if pedido.data_parecer_desistencia and pedido.desistencia:
        lista_msgs_geral_pedido_servidor.append(
            'Foi cadastrada uma desistência para este pedido. Para maiores detalhes verique na aba Desistência no final dessa tela.'
        )

    lista_msgs_parametros_checklist = []
    lista_msgs_parametros_checklist.append(
        'Se você discorda do "Início do exercício" deve cadastrar uma "Solicitação de Alteração de Data de início de exercício".'
    )
    lista_msgs_parametros_checklist.append('Se você discorda de qualquer outro dado deve cadastrar uma "Solicitações de Alteração de Dados".')

    return locals()


@rtr()
@transaction.atomic
@login_required
def ativar_edital(request, edital_id):
    edital = get_object_or_404(EditalLicCapacitacao, pk=edital_id)
    url = reverse('visualizar_edital_gestao', args=[edital_id])

    try:
        if edital.pode_ativar(request.user, True):
            if not CodigoLicencaCapacitacao.objects.all().exists():
                raise Exception('Impossível ativar o edital sem cadastrar os Códigos de Licença Capacitação.')
            if not CodigoAfastamentoCapacitacao.objects.all().exists():
                raise Exception('Impossível ativar o edital sem cadastrar os Códigos de Afastamento Capacitação.')
            if not CodigoAfastamentoNaoContabilizaExercicio.objects.all().exists():
                raise Exception('Impossível ativar o edital sem cadastrar os Códigos de afastamentos que não contabilizam como efetivo exercício.')
            if not SituacaoContabilizaExercicio.objects.all().exists():
                raise Exception('Impossível ativar o edital sem cadastrar as Situações que contabilizam como efetivo exercício.')

            edital.ativo = True
            edital.save()
        return httprr(url, 'Edital ativado com sucesso.')
    except Exception as e:
        return httprr(url, f'Erro ao tentar ativar edital: {e}', tag='error')


@rtr()
@transaction.atomic
@login_required
def inativar_edital(request, edital_id):
    edital = get_object_or_404(EditalLicCapacitacao, pk=edital_id)
    url = reverse('visualizar_edital_gestao', args=[edital_id])

    try:
        if edital.pode_inativar(request.user, True):
            edital.ativo = False
            edital.save()
        return httprr(url, 'Edital inativado com sucesso.')
    except Exception as e:
        return httprr(url, f'Erro ao tentar inativado edital: {e}', tag='error')


@rtr()
@login_required
def visualizar_processamento(request, processamento_id):
    # -------------------------------------------------------------------
    # Visualizar edital como Gestor/Equipe ou como Servidor
    # -------------------------------------------------------------------
    processamento = get_object_or_404(ProcessamentoEdital, pk=processamento_id)
    eh_gestao = EditalLicCapacitacao.eh_perfil_gestao(request.user)
    if not processamento.edital.pode_visualizar_como_servidor(user=request.user) and not eh_gestao:
        raise PermissionDenied

    eh_processamento_parcial = processamento.tipo_processamento == ProcessamentoEdital.PROCESSAMENTO_PARCIAL

    title = f'{processamento}'

    edital = processamento.edital

    dados_processamento_taes = ProcessamentoEdital.get_dados_processamento(processamento, 'tae')
    dados_processamento_docentes = ProcessamentoEdital.get_dados_processamento(processamento, 'docente')

    existe_empate_taes = ProcessamentoEdital.existe_empate(processamento, tae_docente='tae')
    existe_empate_docentes = ProcessamentoEdital.existe_empate(processamento, tae_docente='docente')

    pode_regerar_dados_processamento = ProcessamentoEdital.pode_editar(request.user, processamento, False)
    pode_calcular_processamento = ProcessamentoEdital.pode_editar(request.user, processamento, False)
    pode_finalizar_processamento = ProcessamentoEdital.pode_finalizar_processamento(request.user, processamento, False)
    pode_desfinalizar_processamento = ProcessamentoEdital.pode_desfinalizar_processamento(request.user, processamento, False)
    pode_cancelar_processamento = ProcessamentoEdital.pode_editar(request.user, processamento, False)
    pode_descancelar_processamento = ProcessamentoEdital.pode_descancelar_processamento(request.user, processamento, False)

    pode_definir_processamento_definitivo = ProcessamentoEdital.pode_definir_processamento_definitivo(request.user, processamento, False)
    pode_desfazer_definir_processamento_definitivo = ProcessamentoEdital.pode_desfazer_definir_processamento_definitivo(
        request.user, processamento, False
    )
    dados_completos = bool(request.GET.get('dados_completos'))
    return locals()


@rtr()
@login_required
def gerar_processamento(request, edital_id, tipo=None):
    # -------------------------------------------------------------------
    # Gerar processamento, parcial ou final
    # -------------------------------------------------------------------
    edital = get_object_or_404(EditalLicCapacitacao, pk=edital_id)
    url = reverse('visualizar_edital_gestao', args=[edital_id])

    if tipo == 1:
        title = f'Criar processamento parcial do edital {edital}'
    elif tipo == 2:
        title = f'Criar processamento final do edital {edital}'

    try:
        pode_criar_processamento = ProcessamentoEdital.pode_criar_processamento(request.user, edital, tipo, True)
        form = CriarProcessamentoForm(request.POST or None, request=request)
        if request.method == 'POST':
            if form.is_valid():
                ProcessamentoEdital.criar_processamento(request.user, edital, tipo, form.cleaned_data.get('titulo'))
                return httprr(url, 'Processamento criado com sucesso.')
    except Exception as e:
        return httprr(url, f'Erro ao tentar criar o processamento do edital: {get_e(e)}', tag='error')

    return locals()


@rtr()
@login_required
def exportar_submissoes(request, edital_id):
    if not EditalLicCapacitacao.eh_perfil_gestao(request.user):
        raise PermissionDenied
    edital = get_object_or_404(EditalLicCapacitacao, pk=edital_id)
    url = reverse('visualizar_edital_gestao', args=[edital_id])

    try:
        EditalLicCapacitacao.pode_exportar_dados_dos_pedidos(request.user, edital, True)

        dados = ProcessamentoEdital.criar_processamento(request.user, edital, ProcessamentoEdital.PROCESSAMENTO_PARCIAL, gravar_dados=False)
        rows_1 = [
            [
                'Identificador do pedido',
                'Matrícula',
                'Servidor',
                'Categoria',
                'Campus SUAP',
                'Setor',
                'Data de início de exercício',
                'Modalidade',
                'Carga horária total (horas)',
                'Ação',
                'Outros Detalhes',
                'Parcelas',
                'Quantidade de dias do pedido',
                'Quantidade de dias de licença capacitação já concedidas',
                'Período aquisitivo mais próximo do fim (data final)',
                'Quantidade de dias de efetivo exercício',
                'Quantidade de dias de afastamento capacitação',
                'Quantidade de dias que não contabilizam como efetivo exercício',
                'Idade do servidor (no início da abrangência do edital)',
            ]
        ]

        rows_2 = [
            [
                'Identificador do pedido',
                'Matrícula',
                'Servidor',
                'Categoria',
                'Campus SUAP',
                'Setor',
                'Data de início de exercício',
                'Modalidade',
                'Carga horária total (horas)',
                'Ação',
                'Outros Detalhes',
                'Data início parcela',
                'Data final parcela',
                'Quantidade de dias do pedido',
                'Quantidade de dias de licença capacitação já concedidas',
                'Período aquisitivo mais próximo do fim (data final)',
                'Quantidade de dias de efetivo exercício',
                'Quantidade de dias de afastamento capacitação',
                'Quantidade de dias que não contabilizam como efetivo exercício',
                'Idade do servidor (no início da abrangência do edital)',
                'Erro no Checklist de Submissão',
            ]
        ]

        for d in dados:
            parcelas = d.pedido.get_lista_periodos_pedido()
            parcelas_str = ''
            parcela_ini = None
            parcela_fim = None

            rows_add = rows_1
            if edital.qtd_max_periodos_por_pedido == 1:
                rows_add = rows_2
                parcela_ini = format_datetime(parcelas[0].data_inicio)
                parcela_fim = format_datetime(parcelas[0].data_termino)
            else:
                for p in parcelas:
                    parcelas_str += f'{format_datetime(p.data_inicio)} a {format_datetime(p.data_termino)} '

            qtd_dias_pedido = d.pedido.periodopedidoliccapacitacao_set.aggregate(qtd=Sum('qtd_dias_total'))['qtd']

            if edital.qtd_max_periodos_por_pedido == 1:
                rows_add.append(
                    [
                        d.pedido.id,
                        d.pedido.servidor.matricula,
                        d.pedido.servidor.pessoa_fisica.nome.upper(),
                        d.pedido.categoria_display,
                        d.pedido.servidor.setor.uo,
                        d.pedido.servidor.setor,
                        d.inicio_exercicio,
                        d.pedido.get_modalidade_display(),
                        d.pedido.carga_horaria,
                        d.pedido.acao,
                        d.pedido.outros_detalhes,
                        parcela_ini,
                        parcela_fim,
                        qtd_dias_pedido,
                        d.qtd_dias_total_licenca_capacitacao_utilizada,
                        d.periodo_aquisitivo_proximo_do_fim,
                        d.qtd_dias_efetivo_exercicio,
                        d.qtd_dias_afastamento_capacitacao,
                        d.qtd_dias_afast_nao_conta_como_efet_exerc,
                        d.idade_servidor_inicio_abrangencia_edital,
                        d.tem_erro_checklist,
                    ]
                )
            else:
                rows_add.append(
                    [
                        d.pedido.id,
                        d.pedido.servidor.matricula,
                        d.pedido.servidor.pessoa_fisica.nome.upper(),
                        d.pedido.categoria_display,
                        d.pedido.servidor.setor.uo,
                        d.pedido.servidor.setor,
                        d.inicio_exercicio,
                        d.pedido.get_modalidade_display(),
                        d.pedido.carga_horaria,
                        d.pedido.acao,
                        d.pedido.outros_detalhes,
                        parcelas_str,
                        qtd_dias_pedido,
                        d.qtd_dias_total_licenca_capacitacao_utilizada,
                        d.periodo_aquisitivo_proximo_do_fim,
                        d.qtd_dias_efetivo_exercicio,
                        d.qtd_dias_afastamento_capacitacao,
                        d.qtd_dias_afast_nao_conta_como_efet_exerc,
                        d.idade_servidor_inicio_abrangencia_edital,
                        d.tem_erro_checklist,
                    ]
                )

        return XlsResponse(rows_add, name='pedidos_submetidos')

    except Exception as e:
        return httprr(url, f'Erro ao tentar exportar dados da submissão: {get_e(e)}', tag='error')


@rtr()
@login_required
def regerar_dados_processamento(request, processamento_id):
    # -------------------------------------------------------------------
    # Regerar processamento, parcial ou final
    # -------------------------------------------------------------------
    processamento = get_object_or_404(ProcessamentoEdital, pk=processamento_id)
    url = reverse('visualizar_processamento', args=[processamento_id])

    try:
        ProcessamentoEdital.regerar_dados_processamento(request.user, processamento)
        return httprr(url, 'Dados do processamento regerados com sucesso.')
    except Exception as e:
        return httprr(url, f'Erro ao tentar regerar dados do processamento do edital: {e}', tag='error')


@rtr()
@login_required
def calcular_processamento(request, processamento_id):
    # -------------------------------------------------------------------
    # Regerar processamento, parcial ou final
    # -------------------------------------------------------------------
    get_object_or_404(ProcessamentoEdital, pk=processamento_id)
    return tasks.calcular_processamento(processamento_id, request.user)


@rtr()
@login_required
def calcular_parametros_edital(request, edital_id):
    # -------------------------------------------------------------------
    # Calcula/recalcula parametros do edital
    # -------------------------------------------------------------------
    edital = get_object_or_404(EditalLicCapacitacao, pk=edital_id)
    url = reverse('visualizar_edital_gestao', args=[edital_id])

    try:
        ProcessamentoEdital.pode_recalcular_parametros_edital(request.user, edital, True)
        EditalLicCapacitacao.calcular_parametros(edital)
        return httprr(url, 'Parâmetros do edital calculados com sucesso.')
    except Exception as e:
        return httprr(url, f'Erro ao tentar calcular os parâmetros do edital: {e}', tag='error')


@rtr('licenca_capacitacao/templates/visualizar_pedido_servidor_gestao.html')
@login_required
def visualizar_pedido_gestao(request, pedido_id):
    pedido = get_object_or_404(PedidoLicCapacitacao, pk=pedido_id)
    servidor = pedido.servidor

    if not (EditalLicCapacitacao.eh_perfil_gestao(request.user) or request.user.is_superuser):
        raise PermissionDenied

    title = f'Pedido de Licença Capacitação - {pedido.edital} - {servidor}'

    visualizar_como_gestao = True

    # tem_erro, lista_verificacao = checklist(pedido, calcula_pedido=True)
    # if not (pedido.situacao == pedido.PENDENTE_SUBMISSAO or request.user.is_superuser):
    #    tem_erro, lista_verificacao = None, None
    try:
        with atomic(f'edital_lic_capacitacao_lock:{pedido.edital.id}_{servidor.id}', timeout=10):
            calcular(pedido.edital, servidor)
    except LockError:
        return httprr('/', 'Erro ao tentar calcular os dados do edital.', tag='error')

    # Dados dos calculos
    calculos_exercicio, calculos_quinquenios, licencas_capacitacao_servidor, afastamentos_nao_conta_como_efet_exerc = (
        EditalLicCapacitacao.get_dados_calculos_servidor_no_edital(pedido.edital, servidor)
    )

    # Outrs dados
    periodos_solicitados = PeriodoPedidoLicCapacitacao.objects.filter(pedido=pedido).order_by('data_inicio')
    # anexos = AnexosPedidoLicCapacitacaoSubmissao.objects.filter(pedido=pedido).order_by('descricao')

    pode_gestao_cancelar = pedido.pode_gestao_cancelar(request.user)

    return locals()


@rtr()
@login_required
def finalizar_processamento(request, processamento_id):
    processamento = get_object_or_404(ProcessamentoEdital, pk=processamento_id)
    url = reverse('visualizar_processamento', args=[processamento_id])

    try:
        ProcessamentoEdital.finalizar_processamento(request.user, processamento)
        return httprr(url, 'Processamento finalizado com sucesso.')
    except Exception as e:
        return httprr(url, f'Erro ao finalizar processamento: {e}', tag='error')


@rtr()
@login_required
def desfinalizar_processamento(request, processamento_id):
    processamento = get_object_or_404(ProcessamentoEdital, pk=processamento_id)
    url = reverse('visualizar_processamento', args=[processamento_id])

    try:
        ProcessamentoEdital.desfinalizar_processamento(request.user, processamento)
        return httprr(url, 'Processamento desfinalizado com sucesso.')
    except Exception as e:
        return httprr(url, f'Erro ao desfinalizar processamento: {e}', tag='error')


@rtr()
@login_required
def cancelar_processamento(request, processamento_id):
    processamento = get_object_or_404(ProcessamentoEdital, pk=processamento_id)
    url = reverse('visualizar_processamento', args=[processamento_id])

    try:
        ProcessamentoEdital.cancelar_processamento(request.user, processamento)
        return httprr(url, 'Processamento cancelado com sucesso.')
    except Exception as e:
        return httprr(url, f'Erro ao cancelar processamento: {e}', tag='error')


@rtr()
@login_required
def descancelar_processamento(request, processamento_id):
    processamento = get_object_or_404(ProcessamentoEdital, pk=processamento_id)
    url = reverse('visualizar_processamento', args=[processamento_id])

    try:
        ProcessamentoEdital.descancelar_processamento(request.user, processamento)
        return httprr(url, 'Processamento descancelar com sucesso.')
    except Exception as e:
        return httprr(url, f'Erro ao descancelar processamento: {e}', tag='error')


@rtr()
@login_required
def definir_processamento_definitivo(request, processamento_id):
    processamento = get_object_or_404(ProcessamentoEdital, pk=processamento_id)
    url = reverse('visualizar_processamento', args=[processamento_id])

    try:
        ProcessamentoEdital.definir_processamento_definitivo(request.user, processamento)
        return httprr(url, 'Processamento definido como definitivo com sucesso.')
    except Exception as e:
        return httprr(url, f'Erro ao tentar definir um processamento como definitivo: {e}', tag='error')


@rtr()
@login_required
def desfazer_definir_processamento_definitivo(request, processamento_id):
    processamento = get_object_or_404(ProcessamentoEdital, pk=processamento_id)
    url = reverse('visualizar_processamento', args=[processamento_id])

    try:
        ProcessamentoEdital.definir_processamento_definitivo(request.user, processamento, desfazer=True)
        return httprr(url, 'Processamento não está mais como definitivo.')
    except Exception as e:
        return httprr(url, f'Erro ao tentar desfazer um processamento como definitivo: {e}', tag='error')


@rtr()
@login_required
def editar_ordem_classificacao_gestao(request, dado_processamento_edital_id):
    # -------------------------------------------------------------------
    # Gerar processamento, parcial ou final
    # -------------------------------------------------------------------
    dado_processamento_edital = get_object_or_404(DadosProcessamentoEdital, pk=dado_processamento_edital_id)
    url = reverse('visualizar_processamento', args=[dado_processamento_edital.processamento.id])

    title = 'Editar Ordem de Classificação definida pela gestão'

    processamento = dado_processamento_edital.processamento

    if processamento.tipo_processamento == ProcessamentoEdital.PROCESSAMENTO_PARCIAL:
        ordem_colocacao_inicial = dado_processamento_edital.ordem_classificacao_resultado_parcial_gestao
    elif processamento.tipo_processamento == ProcessamentoEdital.PROCESSAMENTO_FINAL:
        ordem_colocacao_inicial = dado_processamento_edital.ordem_classificacao_resultado_final_gestao

    try:
        form = EditarOrdemClassificacaoGestaoForm(request.POST or None, ordem_colocacao_inicial=ordem_colocacao_inicial)
        if request.method == 'POST':
            if form.is_valid():
                DadosProcessamentoEdital.editar_ordem_classificacao_gestao(
                    request.user, dado_processamento_edital, form.cleaned_data.get('ordem_colocacao')
                )
                return httprr(url, 'Ordem/classificação editada com sucesso.')
    except Exception as e:
        return httprr(url, f'Erro ao tentar editar ordem/classificação: {e}', tag='error')

    return locals()


@rtr()
@login_required
def cancelar_pedido_gestao(request, pedido_id):
    # -------------------------------------------------------------------
    # A gestão pode cancelar um pedido
    # - Para casos de pedidos que foram aprovados em definitivo mas que não foram gozados pelo servidor
    # -------------------------------------------------------------------
    pedido = get_object_or_404(PedidoLicCapacitacao, pk=pedido_id)
    if not pedido.pode_gestao_cancelar(request.user):
        raise PermissionDenied

    url = f'/licenca_capacitacao/visualizar_pedido_gestao/{pedido.id}'

    title = f'Gestão - Cancelar {pedido}'

    form = CancelarPedidoGestaoForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            pedido.justificativa_cancelado_pela_gestao = form.cleaned_data.get('justificativa')
            pedido.cancelado_pela_gestao = True
            pedido.save()
            return httprr('..', 'Pedido cancelado com sucesso.')

    return locals()


@rtr()
@login_required
def imprimir_pedido_servidor(request, pedido_id):
    pedido = get_object_or_404(PedidoLicCapacitacao, pk=pedido_id)

    if not pedido.pode_imprimir_pedido(request.user):
        raise PermissionDenied

    servidor = pedido.servidor
    periodos_solicitados = PeriodoPedidoLicCapacitacao.objects.filter(pedido=pedido).order_by('data_inicio')
    calculos_exercicio, calculos_quinquenios, licencas_capacitacao_servidor, afastamentos_nao_conta_como_efet_exerc = (
        EditalLicCapacitacao.get_dados_calculos_servidor_no_edital(pedido.edital, request.user.get_relacionamento())
    )

    pdf_pedido = render_pdf_from_template_with_wkhtmltopdf(
        'imprimir_pedido_servidor.html',
        context=locals(),
        cmd_options={'header-spacing': 3, 'footer-spacing': 3, 'orientation': 'portrait', 'enable-local-file-access': ''},
    )
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename=Pedido.pdf'
    response.write(pdf_pedido)
    return response


@rtr()
@login_required()
def importar_resultado_final(request, edital_id):
    if not EditalLicCapacitacao.eh_perfil_gestao(request.user):
        raise PermissionDenied
    edital = get_object_or_404(EditalLicCapacitacao, pk=edital_id)
    title = f'Importar Resultado Final do {edital}'
    url = reverse('visualizar_edital_gestao', args=[edital_id])

    try:
        EditalLicCapacitacao.pode_importar_resultado_final(request.user, edital, True)

        form = ImportarResultadoFinalForm(edital, data=request.POST or None, files=request.POST and request.FILES or None)
        if form.is_valid():
            form.processar()

            return httprr(url, 'Sucesso ao importar resultado final.')
    except Exception as e:
        return httprr(url, f'Erro ao importar resultado final: {e}', tag='error')

    return locals()


@rtr()
@login_required
def solicitar_desistencia(request, pedido_id):
    # -------------------------------------------------------------------
    # Servidor solicita desistência
    # -------------------------------------------------------------------
    pedido = get_object_or_404(PedidoLicCapacitacao, pk=pedido_id)
    servidor = pedido.servidor

    if not pedido.pode_solicitar_desistencia_pedido(request.user):
        raise PermissionDenied

    url = f'/licenca_capacitacao/visualizar_pedido_servidor/{pedido.id}/'

    title = f'Solicitar desistência do pedido {pedido}'

    try:
        form = SolicitarDesistenciaForm(request.POST or None, request=request, instance=pedido)
        if form.is_valid():
            form.save()
            return httprr(url, 'Solicitação de desistência criada com sucesso.')
    except Exception as e:
        return httprr(url, f'Erro ao tentar criar solicitar desistência: {get_e(e)}', tag='error')

    return locals()


@rtr()
@login_required()
def cadastrar_servidor_complementar(request, edital_id):
    edital = get_object_or_404(EditalLicCapacitacao, pk=edital_id)
    if not ServidorComplementar.pode_cadastrar(request.user, edital):
        raise PermissionDenied

    title = f'Cadastrar servidor complementar no edital {edital}'

    url = reverse('listar_servidores_aptos_no_edital', args=[edital_id])

    form = ServidorComplementarForm(request.POST or None, request=request)
    if form.is_valid():
        form.save()
        return httprr(url, 'Servidor complementar cadastrado com sucesso.')

    return locals()


@rtr()
@login_required
def listar_servidores_aptos_no_edital(request, edital_id):
    edital = get_object_or_404(EditalLicCapacitacao, pk=edital_id)

    if not ServidorComplementar.pode_visualizar(request.user, edital):
        raise PermissionDenied

    title = f'Servidores aptos a submeter pedido ao edital {edital}'

    pode_cadastrar = ServidorComplementar.pode_cadastrar(request.user, edital)

    servidores = EditalLicCapacitacao.get_servidores_efetivo_exercicio().order_by('pessoa_fisica__nome')
    servidores_complementares = ServidorComplementar.objects.filter(edital=edital).order_by('servidor__pessoa_fisica__nome')

    return locals()


@login_required()
def excluir_servidor_complementar(request, edital_id, servidor_complementar_id):
    edital = get_object_or_404(EditalLicCapacitacao, pk=edital_id)
    if not ServidorComplementar.pode_cadastrar(request.user, edital):
        raise PermissionDenied

    url = reverse('listar_servidores_aptos_no_edital', args=[edital_id])

    sc = get_object_or_404(ServidorComplementar, pk=servidor_complementar_id)

    if EditalLicCapacitacao.existe_algum_pedido_submetido_do_servidor_no_edital(edital, sc.servidor):
        return httprr(url, 'Servidor possui pedido submetido neste edital')

    sc.delete()
    return httprr(url, 'Servidor complementar excluído com sucesso.')


@login_required
def excluir_processamento(request, processamento_id):
    if not request.user.is_superuser:
        raise PermissionDenied
    processamento = get_object_or_404(ProcessamentoEdital, pk=processamento_id)
    processamento.delete()
    return httprr('/admin/licenca_capacitacao/editalliccapacitacao/', 'Processamento excluído com sucesso.')


@rtr()
@permission_required('licenca_capacitacao.change_solicitacaoalteracaodatainicioexercicio')
def listar_inscritos_para_ajuste_dt_exercicio(request, edital_id):
    edital = get_object_or_404(EditalLicCapacitacao, pk=edital_id)

    pode_ajustar = False
    try:
        SolicitacaoAlteracaoDataInicioExercicio.pode_analisar_solicitacao_alteracao_dt_inicio_exercicio(request.user, edital, True)
        pode_ajustar = True
    except Exception as e:
        messages.error(request, get_e(e))

    title = f'Ajustar data de início de exercício dos inscritos no {edital}'

    servidores_inscritos = PedidoLicCapacitacao.get_pedidos_submetidos(edital=edital).values('servidor_id')
    lista_servidores = Servidor.objects.vinculados().filter(id__in=servidores_inscritos)
    lista_servidores = lista_servidores.order_by('pessoa_fisica__nome')

    # Coluna: se data já foi ajustada
    data_ajustada = ServidorDataInicioExercicioAjustada.objects.filter(servidor_id=OuterRef('pk'))
    lista_servidores = lista_servidores.annotate(tem_data_ajustada=Exists(data_ajustada))

    # Coluna: se foi solicitado ajuste
    solicitacao_valida = SolicitacaoAlteracaoDataInicioExercicio.objects.filter(servidor_id=OuterRef('pk'), edital=edital, situacao__isnull=True)
    lista_servidores = lista_servidores.annotate(tem_solicitacao=Exists(solicitacao_valida))

    form = BuscarServidoresForm(request.GET or None, request=request)
    if form.is_valid():
        buscar_str = form.cleaned_data.get('buscar_str')
        setor = form.cleaned_data.get('setor')
        agrupamento = form.cleaned_data.get('agrupamento')
        if setor:
            lista_servidores = lista_servidores.filter(setor=setor)
        if buscar_str:
            lista_servidores = lista_servidores.filter(Q(pessoa_fisica__nome__icontains=buscar_str) | Q(matricula__icontains=buscar_str))
        if agrupamento == 'da':
            lista_servidores = lista_servidores.filter(tem_data_ajustada=True)
        if agrupamento == 'dna':
            lista_servidores = lista_servidores.filter(tem_data_ajustada=False)

    return locals()


@rtr()
@permission_required('licenca_capacitacao.change_solicitacaoalteracaodatainicioexercicio')
def ajustar_dt_exercicio(request, edital_id, matricula):
    edital = get_object_or_404(EditalLicCapacitacao, pk=edital_id)

    pode_ajustar = False
    try:
        SolicitacaoAlteracaoDataInicioExercicio.pode_analisar_solicitacao_alteracao_dt_inicio_exercicio(request.user, edital, True)
        pode_ajustar = True
    except Exception as e:
        messages.error(request, get_e(e))

    servidor = Servidor.objects.get(matricula=matricula)
    existe_no_edital = PedidoLicCapacitacao.get_pedidos_submetidos(edital=edital).filter(servidor=servidor)
    if not existe_no_edital:
        raise PermissionDenied

    acao = None
    title = None
    if (request.GET.get('a') is None or request.GET.get('a') == 'ajustar') and pode_ajustar:
        acao = 'ajustar'
        title = f'Ajustar data de início de exercício do {servidor}'
    if request.GET.get('a') == 'visualizar':
        acao = 'visualizar'
        title = f'Visualizar data de início de exercício do {servidor}'

    calculos = CalculosGeraisServidorEdital.objects.filter(edital=edital, servidor=servidor).first()
    data_ajustada_servidor = ServidorDataInicioExercicioAjustada.objects.filter(servidor=servidor).first()

    if acao == 'ajustar':
        url_retorno = request.GET.get('url')
        solicitacao_valida = SolicitacaoAlteracaoDataInicioExercicio.objects.filter(servidor=servidor, edital=edital, situacao__isnull=True).first()
        if solicitacao_valida:
            return HttpResponseRedirect(
                f'/admin/licenca_capacitacao/solicitacaoalteracaodatainicioexercicio/{solicitacao_valida.id}/change/?url={url_retorno}'
            )

        form = EditarDataIniExercicioForm(request.POST or None)
        if form.is_valid():
            ServidorDataInicioExercicioAjustada.ajustar(servidor, form.cleaned_data.get('data'), request.user, None)
            return httprr(url_retorno, 'Data alterada com sucesso.')

    return locals()
