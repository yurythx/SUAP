import datetime
import operator
from datetime import date
from functools import reduce

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import F, Q, Sum
from django.shortcuts import get_object_or_404
from django.template.defaultfilters import pluralize
from django.urls import reverse
from django.utils.safestring import mark_safe

from djtools import layout
from djtools.templatetags.filters import format_datetime
from djtools.utils import diferenca_listas, formata_segundos, get_client_ip, httprr, permission_required, rtr, send_mail
from pgd import tasks
from pgd.forms import (
    AdicionarAtividadeRitForm,
    AjustarHorasSemestreRitForm,
    BuscarAtividadeQuadroForm,
    BuscarRelatorioDesligamentoForm,
    BuscarRelatorioQuestionarioRitForm,
    BuscarSelecionarAtividadeAdicionarPitForm,
    BuscarServidoresPgdForm,
    CadastrarDesligamentoPgdForm,
    CadastrarEntregaForm,
    ConfirmacaoComSenhaForm,
    ConfirmacaoDeferirSolicitacaoAlteracaoAtividadeForm,
    CopiarPlanejamentoForm,
    CriarPitForm,
    DesfazerDistribuirHorasAutoRitForm,
    DesfazerDistribuirHorasCompensacaoEspecificaRitForm,
    DesfazerDistribuirHorasSemestreRitForm,
    DevolverRitConfirmacaoForm,
    DistribuirHorasAutoRitForm,
    EditarAtividadeRitForm,
    EditarEntregaForm,
    EditarTelefonePgdForm,
    EntregarRitForm,
    EnviarEmailComSenhaForm,
    HomologarRitForm,
    JustificativaComSenhaForm,
    JustificativaComSenhaIrreverssivelForm,
    JustificativaForm,
    PlanoIndividualTrabalhoEditarEspecificosForm,
    PlanoTrabalhoSetorialEditarAuxiliaresForm,
    PlanoTrabalhoSetorialEditarDocumentacaoForm,
    PlanoTrabalhoSetorialEditarVigenciaForm,
    QuestionarioRitChefeForm,
    QuestionarioRitServidorForm,
    RelatorioIndividualTrabalhoAtividadeEntregaAvaliarForm,
    RelatorioIndividualTrabalhoAtividadeEntregaAvaliarSimplesForm,
    SelecionarHierarquiaAtividadeForm,
    SolicitarAdesaoPgdForm,
    SolicitarAdesaoPtsForm,
)
from pgd.models import (
    Atividade,
    AtividadeEntrega,
    ComissaoPGD,
    ConfiguracaoOrientacaoPit,
    ConfiguracaoOrientacaoPlanoSetorial,
    DesligamentoPgdServidor,
    DocumentoAdesaoPtsServidor,
    DocumentoAdesaoServidor,
    JustificativaDesligamentoPgd,
    PeriodoPitRit,
    PlanoIndividualTrabalho,
    PlanoTrabalhoSetorial,
    PlanoTrabalhoSetorialAtividades,
    RegistroAcaoPlanoIndividualTrabalho,
    RegistroAcaoPTS,
    RegistroAcaoRelatorioIndividualTrabalho,
    RegistroAcaoSolicitacaoAdesaoPtsServidor,
    RegistroAcaoSolicitacaoAdesaoServidor,
    RelatorioIndividualTrabalho,
    RelatorioIndividualTrabalhoAtividade,
    RelatorioIndividualTrabalhoAtividadeEntrega,
    RelatorioIndividualTrabalhoDistribuicaoHoras,
    RelatorioIndividualTrabalhoQuestionario,
    ServicoAtividade,
    SolicitacaoAdesaoPtsServidor,
    SolicitacaoAdesaoServidor,
    SubtematicaAtividade,
    TematicaAtividade,
)
from pgd.utils import (
    get_datetime_now,
    gv,
    obter_compensacoes_especificas_compesaveis_rit,
    setores_que_sou_chefe_direto_hoje,
    setores_que_sou_chefe_hoje,
)
from ponto.models import Frequencia, RecessoOpcaoEscolhida, RecessoPeriodoCompensacao, SaldoExterno
from rh.models import Servidor, ServidorSetorLotacaoHistorico, Setor, UnidadeOrganizacional


@layout.atribuidos_a_mim()
def index_atribuidos_a_mim(request):
    pendencias = []

    user_servidor = request.user.get_relacionamento()

    if request.user.has_perm('comum.is_chefe_de_setor'):
        setores = setores_que_sou_chefe_hoje(request.user.get_relacionamento())

        solicitacoes_pgd_pendentes = (
            SolicitacaoAdesaoServidor.objects.exclude(servidor=user_servidor)
            .filter(servidor__setor__in=setores, situacao=SolicitacaoAdesaoServidor.SOLICITADO)
            .count()
        )
        if solicitacoes_pgd_pendentes:
            pendencias.append(
                {
                    'titulo': f'Ades{pluralize(solicitacoes_pgd_pendentes, "ão,ões")} ao PGD 1.0',
                    'subtitulo': 'a avaliar',
                    'qtd': solicitacoes_pgd_pendentes,
                    'url': '/admin/pgd/solicitacaoadesaoservidor/?tab=tab_solicitado',
                }
            )

        solicitacoes_pts_pendentes = (
            SolicitacaoAdesaoPtsServidor.objects.exclude(adesao__servidor=user_servidor)
            .filter(plano_trabalho_setorial__setor__in=setores, situacao=SolicitacaoAdesaoPtsServidor.SOLICITADO)
            .count()
        )
        if solicitacoes_pts_pendentes:
            pendencias.append(
                {
                    'titulo': f'Ades{pluralize(solicitacoes_pts_pendentes, "ão,ões")} ao PTS do PGD 1.0',
                    'subtitulo': 'a avaliar',
                    'qtd': solicitacoes_pts_pendentes,
                    'url': '/admin/pgd/solicitacaoadesaoptsservidor/?situacao__exact=1&tab=tab_outras',
                }
            )

        solicitacoes_pit_pendentes = (
            PlanoIndividualTrabalho.objects.exclude(adesao__servidor=user_servidor)
            .filter(adesao__servidor__setor__in=setores, situacao=PlanoIndividualTrabalho.AGUARDANDO_PARECER)
            .count()
        )
        if solicitacoes_pit_pendentes:
            pendencias.append(
                {
                    'titulo': f'PIT{pluralize(solicitacoes_pit_pendentes)} do PGD 1.0',
                    'subtitulo': 'a avaliar',
                    'qtd': solicitacoes_pit_pendentes,
                    'url': '/admin/pgd/planoindividualtrabalho/?tab=tab_aguardando_parecer',
                }
            )

        solicitacoes_rit_pendentes = (
            RelatorioIndividualTrabalho.objects.exclude(pit__adesao__servidor=user_servidor)
            .filter(pit__adesao__servidor__setor__in=setores, entregue=True)
            .exclude(pit__adesao__servidor=request.user.get_relacionamento())
        )
        qtd_solicitacoes_rit_pendentes_aprovacao = solicitacoes_rit_pendentes.filter(aprovado_definitivo__isnull=True).count()
        if qtd_solicitacoes_rit_pendentes_aprovacao:
            pendencias.append(
                {
                    'titulo': f'RIT{pluralize(qtd_solicitacoes_rit_pendentes_aprovacao)} do PGD 1.0',
                    'subtitulo': 'a aprovar',
                    'qtd': qtd_solicitacoes_rit_pendentes_aprovacao,
                    'url': '/admin/pgd/relatorioindividualtrabalho/?rit_ag=3&entregue__exact=1&avrit=1',
                }
            )
        qtd_solicitacoes_rit_pendentes_homologacao = solicitacoes_rit_pendentes.filter(
            aprovado_definitivo=True, homologado_definitivo__isnull=True
        ).count()
        if qtd_solicitacoes_rit_pendentes_homologacao:
            pendencias.append(
                {
                    'titulo': f'RIT{pluralize(qtd_solicitacoes_rit_pendentes_homologacao)} do PGD 1.0',
                    'subtitulo': 'a homologar',
                    'qtd': qtd_solicitacoes_rit_pendentes_homologacao,
                    'url': '/admin/pgd/relatorioindividualtrabalho/?rit_ag=3&entregue__exact=1&avrit=2',
                }
            )

    if request.user.eh_servidor:
        # Pendencias de servidor
        url = reverse('servidor_pgd')
        pits_pendencias = PlanoIndividualTrabalho.get_pendencias_pit_servidor(user_servidor)
        rits_pendencias = PlanoIndividualTrabalho.get_pendencias_rit_servidor(user_servidor)
        if pits_pendencias or rits_pendencias:
            qtd = len(pits_pendencias) + len(rits_pendencias)
            pendencias.append(
                {
                    'titulo': f'Pendência{pluralize(qtd)} de servidor no PGD 1.0',
                    'subtitulo': 'a resolver',
                    'qtd': qtd,
                    'url': url,
                }
            )

    return pendencias


# ====================================================
# BÁSICO E ATIVIDADES
# ====================================================
@rtr()
@login_required
def quadro_atividades(request, action=None, target=None):
    if not Atividade.pode_visualizar(request.user):
        raise PermissionDenied

    # Actions: qta, addptslote
    # -------------------------------------
    minhas_solicitacoes = None
    # Action QTA
    if action is None:
        action = 'qta'
        # Se usuario puder apenas solicitar cadastro (nao pode efetivamente cadastrar)
        pode_cadastrar = Atividade.pode_cadastrar(request.user)
        pode_solicitar_cadastro_alteracao = Atividade.pode_solicitar_cadastro_alteracao(request.user)
        if pode_solicitar_cadastro_alteracao:
            minhas_solicitacoes = Atividade.objects.solicitacoes().filter(solicitado_por=request.user)
        title = 'Quadro Temático de Atividades'
    atividades_para_adicionar = None
    # Actions addptslote
    if action == 'addptslote':
        pts_id = target
        if pts_id is None:
            raise PermissionDenied
        pts = get_object_or_404(PlanoTrabalhoSetorial, pk=pts_id)
        if not pts.pode_vincular_atividades(request.user):
            raise PermissionDenied
        atividades_para_adicionar = pts.get_atividades_para_adicionar()
        if not atividades_para_adicionar.exists():
            return httprr('..', 'Não existem atividades disponíveis para adicionar neste Plano de Trabalho Setorial.', tag='error')
        title = f'Vincular Novas Atividades ao {pts}'
        action_form = f'/pgd/vincular_atividade_em_lote_pts/{pts.id}/'

    tematicas = TematicaAtividade.objects.all().order_by('titulo')

    buscou = request.GET.get('buscaratividadequadro_form')
    form = BuscarAtividadeQuadroForm(request.GET or None)

    buscar_str = None
    buscar_str2 = None
    tematica = None
    subtematica = None
    servico = None
    atividade = None
    pode_ser_teletrabalho = None
    ativo = None
    ordenar_por = 'hierarquia'
    organizacao = 'aba_por_tematica'

    lista_dados = []

    # Obtendo os filtros
    if buscou and form.is_valid():
        buscar_str = form.cleaned_data.get('buscar_str')
        buscar_str2 = form.cleaned_data.get('buscar_str2')
        tematica = form.cleaned_data.get('tematica')
        subtematica = form.cleaned_data.get('subtematica')
        servico = form.cleaned_data.get('servico')
        atividade = form.cleaned_data.get('atividade')

        pode_ser_teletrabalho = None
        if form.cleaned_data.get('pode_ser_teletrabalho'):
            if form.cleaned_data.get('pode_ser_teletrabalho') == '1':
                pode_ser_teletrabalho = True
            else:
                pode_ser_teletrabalho = False

        ativo = form.cleaned_data.get('ativo')

        organizacao = form.cleaned_data.get('organizacao')
        ordenar_por = form.cleaned_data.get('ordenar_por')

    # Prepara queryset
    # -------------------------
    atividades = Atividade.objects.all().select_related('tematica', 'subtematica', 'servico').prefetch_related('atividadeentrega_set')
    if action == 'addptslote':
        atividades = atividades.filter(id__in=atividades_para_adicionar.values_list('id', flat=True))

    # Aplica filtros
    # -------------------------
    # Buscar no Título e Descrição da Atividade
    if buscar_str:
        atividades = atividades.filter(Q(titulo__icontains=buscar_str) | Q(descricao__icontains=buscar_str))
    # Buscar no Título da Entrega
    if buscar_str2:
        entregas = AtividadeEntrega.objects.filter(titulo__icontains=buscar_str2)
        atividades = atividades.filter(id__in=entregas.values_list('atividade__id', flat=True))
    # Buscar tematica
    if tematica:
        atividades = atividades.filter(tematica=tematica)
    # Buscar subtematica
    if subtematica:
        atividades = atividades.filter(subtematica=subtematica)
    # Buscar servico
    if servico:
        atividades = atividades.filter(servico=servico)
    # Buscar atividade
    if atividade:
        atividades = atividades.filter(atividade=atividade)
    if pode_ser_teletrabalho is not None:
        atividades = atividades.filter(pode_ser_teletrabalho=pode_ser_teletrabalho)
    if ativo:
        # choices=[(None, '-------------'), ('1', 'Sim'), ('2', 'Não'), ('3', 'Com inativação programada')]
        hoje = get_datetime_now().date()
        if ativo == '1':
            # Ativo
            atividades = Atividade.get_atividades_ativas()
        elif ativo == '2':
            # Inativo
            atividades = atividades.filter(data_inativacao_efeitos_a_partir_de__lte=hoje)
        else:
            # Com inativação programada
            atividades = atividades.filter(data_inativacao_efeitos_a_partir_de__gt=hoje)

    # Ordenacao
    if ordenar_por == 'hierarquia':
        atividades = atividades.order_by('tematica__titulo', 'subtematica__titulo', 'servico__titulo', 'titulo')
    else:
        atividades = atividades.order_by(ordenar_por)

    if organizacao == 'aba_por_tematica':
        # Gerando os dados de cada aba (organização em abas por tematica)
        # -------------------------
        for obj_tematica in tematicas:
            dados = {}
            dados['tematica'] = obj_tematica

            dados['atividades'] = atividades.filter(tematica=obj_tematica)
            lista_dados.append(dados)

    limpar_filtro = bool(request.GET)

    return locals()


@rtr()
@login_required
def selecionar_hierarquia_atividade(request, atividade_id=None):
    # Se usuario puder apenas solicitar cadastro (nao pode efetivamente cadastrar)
    pode_solicitar_cadastro_alteracao = Atividade.pode_solicitar_cadastro_alteracao(request.user)

    # Se tiver atividade_id é para alterar a hierarquia da atividade
    # Se não tiver atividade_id é para cadastrar a hierarquia da atividade
    atividade = None
    if atividade_id:
        atividade = get_object_or_404(Atividade.objects.todos(), pk=atividade_id)

    if not pode_solicitar_cadastro_alteracao:
        if atividade:
            if not atividade.pode_alterar(request.user):
                raise PermissionDenied
        else:
            if not Atividade.pode_cadastrar(request.user):
                raise PermissionDenied

    url = '/admin/pgd/atividade/add'
    if atividade:
        url = f'/pgd/alterar_hierarquia_atividade/{atividade.id}'

    if pode_solicitar_cadastro_alteracao:
        title = 'Selecione uma Hierarquia para a Solicitação de Nova Atividade'
    else:
        title = 'Selecione uma Hierarquia para a Nova Atividade'
    if atividade:
        if pode_solicitar_cadastro_alteracao:
            title = 'Selecione uma Nova Hierarquia a Solicitação de Alteração da Atividade'
        else:
            title = 'Selecione uma Nova Hierarquia para Atividade'

    buscar_por = None
    dados = None
    buscou = request.GET.get('selecionarhierarquiaatividade_form')
    form = SelecionarHierarquiaAtividadeForm(request.GET or None, request=request)
    if form.is_valid():
        dados, hierarquia, buscar_por = form.processar()

    lista_dados = []
    if dados:
        if buscar_por == 'tematica':
            lista_dados = dados
        elif buscar_por == 'subtematica':
            tematicas = dados.order_by('tematica__titulo').values_list('tematica__id', flat=True).distinct()
            for tematica in tematicas:
                obj = {}
                obj['tematica'] = TematicaAtividade.objects.get(id=tematica)
                obj['subtematicas'] = dados.filter(ativo=True, tematica=tematica).order_by('titulo')
                lista_dados.append(obj)
        elif buscar_por == 'servico':
            tematicas = dados.order_by('subtematica__tematica__titulo').values_list('subtematica__tematica__id', flat=True).distinct()
            for tematica in tematicas:
                obj = {}
                obj['tematica'] = TematicaAtividade.objects.get(id=tematica)
                obj['subtematica_servicos'] = None
                subtematicas = (
                    dados.filter(ativo=True, subtematica__tematica__id=tematica)
                    .order_by('subtematica__titulo')
                    .values_list('subtematica__id', flat=True)
                    .distinct()
                )
                lista_subtematica_servicos = []
                qtd_servicos = 0
                for subtematica in subtematicas:
                    servicos = ServicoAtividade.objects.filter(ativo=True, subtematica__id=subtematica).order_by('titulo')
                    subtematica_servicos = {}
                    if servicos:
                        subtematica_servicos['subtematica'] = SubtematicaAtividade.objects.get(id=subtematica)
                        subtematica_servicos['servicos'] = servicos
                        qtd_servicos += len(servicos)
                        lista_subtematica_servicos.append(subtematica_servicos)
                if lista_subtematica_servicos:
                    obj['subtematica_servicos'] = lista_subtematica_servicos
                    obj['qtd_servicos'] = qtd_servicos
                    lista_dados.append(obj)

    return locals()


@rtr()
@transaction.atomic
@permission_required('pgd.change_atividade')
def alterar_hierarquia_atividade(request, atividade_id):
    atividade = get_object_or_404(Atividade.objects.todos(), pk=atividade_id)
    if not atividade.pode_alterar(request.user):
        raise PermissionDenied

    hierarquia_nivel = request.GET.get('hierarquia_nivel')
    hierarquia_id = request.GET.get('hierarquia_id')
    if not hierarquia_nivel or not hierarquia_id:
        raise PermissionDenied

    tematica = None
    subtematica = None
    servico = None

    if hierarquia_nivel == 'tematica':
        tematica = TematicaAtividade.objects.get(id=hierarquia_id)
    elif hierarquia_nivel == 'subtematica':
        subtematica = SubtematicaAtividade.objects.get(id=hierarquia_id)
        tematica = subtematica.tematica
    else:
        servico = ServicoAtividade.objects.get(id=hierarquia_id)
        subtematica = servico.subtematica
        tematica = subtematica.tematica

    atividade.tematica = tematica
    atividade.subtematica = subtematica
    atividade.servico = servico
    atividade.save()

    return httprr(f'/pgd/visualizar_atividade/{atividade.id}/', 'Alterado com sucesso.')


@rtr()
@login_required
def visualizar_atividade(request, atividade_id):
    atividade = get_object_or_404(Atividade.objects.todos(), pk=atividade_id)

    if not atividade.pode_visualizar_esta_atividade(request.user):
        raise PermissionDenied

    action = request.GET.get('action', None)
    if action is None:
        action = 'qta'

    pode_alterar = (action == 'qta') and atividade.pode_alterar(request.user)

    original = atividade.original
    if atividade.situacao_cadastro == Atividade.CADASTRADO:
        title = f'Atividade: {atividade.titulo}'
    else:
        if original:
            title = f'Solicitação de Alteração da Atividade: {original.titulo}'
        else:
            title = f'Solicitação de Cadastro de Nova Atividade: {atividade.titulo}'

    pode_analisar_solicitacoes_cadastro_alteracao = (action == 'qta') and atividade.pode_analisar_solicitacoes_cadastro_alteracao(request.user)
    pode_solicitar_alteracao_desta_atividade = (action == 'qta') and atividade.pode_solicitar_alteracao_desta_atividade(request.user)
    pode_submeter_alteracao_desta_atividade = (action == 'qta') and atividade.pode_submeter_alteracao_desta_atividade(request.user)

    existe_diferenca = None
    if original and (atividade.esta_pendente_envio or atividade.estah_solicitada):
        existe_diferenca = atividade.existe_diferenca(original)

    return locals()


@rtr()
@transaction.atomic
@login_required
def remover_solicitacao_atividade(request, atividade_id):
    solicitacao_atividade = Atividade.objects.solicitacoes().filter(id=atividade_id)
    if not solicitacao_atividade:
        raise PermissionDenied
    solicitacao_atividade = solicitacao_atividade[0]
    url = reverse('quadro_atividades')
    if solicitacao_atividade.pode_remover_solicitacao_cadastro_alteracao(request.user):
        solicitacao_atividade.delete()
        return httprr(url, 'Solicitação removida com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@transaction.atomic
@login_required
def cadastrar_solicitacao_alteracao_atividade(request, atividade_id):
    # Seleciona a atividade que deseja solicitar alteracao
    atividade = Atividade.objects.filter(id=atividade_id)
    if not atividade:
        raise PermissionDenied
    atividade = atividade[0]

    # Se pode solicitar
    if not atividade.pode_solicitar_alteracao_desta_atividade(request.user):
        raise PermissionDenied

    # Clona a atividade selecionada e coloca como filha
    # Coloca a atividade sem situacao de cadastro para que o servidor possa editar
    # Servidor submete pela "view submeter_solicitacao_atividade"
    original = Atividade.objects.get(id=atividade_id)
    atividade_solicitacao = atividade
    atividade_solicitacao.id = None
    atividade_solicitacao.situacao_cadastro = Atividade.SOLICITACAO_PENDENTE_ENVIO
    atividade_solicitacao.solicitado_por = request.user
    atividade_solicitacao.ativo = False
    atividade_solicitacao.original = original
    atividade_solicitacao.save()
    # AtividadeEntrega
    for entrega in original.get_entregas():
        entrega.id = None
        entrega.atividade = atividade_solicitacao
        entrega.save()

    return httprr(f'/pgd/visualizar_atividade/{atividade.id}/', 'Solicitação cadastrada com sucesso. Ainda está PENDENTE DE ENVIO.')


@rtr()
@transaction.atomic
@login_required
def submeter_solicitacao_atividade(request, atividade_id):
    solicitacao_atividade = Atividade.objects.solicitacoes().filter(id=atividade_id)
    if not solicitacao_atividade:
        raise PermissionDenied
    solicitacao_atividade = solicitacao_atividade[0]

    if not solicitacao_atividade.pode_submeter_alteracao_desta_atividade(request.user):
        raise PermissionDenied

    title = f'Submeter alteração da atividade: {solicitacao_atividade.titulo}'

    form = JustificativaComSenhaForm(request.POST or None, request=request)
    if form.is_valid():
        solicitacao_atividade.situacao_cadastro = Atividade.SOLICITADO
        solicitacao_atividade.justificativa_solicitacao = form.cleaned_data.get('justificativa')
        solicitacao_atividade.save()
        url = f'/pgd/visualizar_atividade/{solicitacao_atividade.id}/'
        return httprr(url, 'Solicitação submetida com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@login_required
def deferir_solicitacao_atividade(request, atividade_id):
    solicitacao_atividade = Atividade.objects.solicitacoes().filter(id=atividade_id)
    if not solicitacao_atividade:
        raise PermissionDenied
    solicitacao_atividade = solicitacao_atividade[0]

    if not solicitacao_atividade.pode_analisar_solicitacoes_cadastro_alteracao(request.user):
        raise PermissionDenied

    title = 'Deferir alteração da atividade'
    if solicitacao_atividade.tipo_solicitacao == 'Cadastro':
        title = 'Deferir cadastro da atividade'

    url = '/admin/pgd/atividadesolicitacoes/'
    if solicitacao_atividade.tipo_solicitacao == 'Cadastro':
        form = ConfirmacaoComSenhaForm(request.POST or None, request=request)
        if form.is_valid():
            solicitacao_atividade.situacao_cadastro = Atividade.CADASTRADO
            solicitacao_atividade.ativo = True
            solicitacao_atividade.save()
            return httprr(url, 'Solicitação deferida com sucesso.')
    elif solicitacao_atividade.tipo_solicitacao == 'Alteração':
        permite_editar_dados_da_original = True
        if solicitacao_atividade.existe_diferenca_nas_entregas(
            solicitacao_atividade.original
        ) or solicitacao_atividade.existe_diferenca_nas_complexidades(solicitacao_atividade.original):
            permite_editar_dados_da_original = False
        form = ConfirmacaoDeferirSolicitacaoAlteracaoAtividadeForm(
            request.POST or None, request=request, permite_editar_dados_da_original=permite_editar_dados_da_original
        )
        if form.is_valid():
            if form.cleaned_data.get('operacao') == 'deferir_alterar':
                original = solicitacao_atividade.original
                original.substituir_esta_atividade_por_outra_atividade(solicitacao_atividade)
                solicitacao_atividade.situacao_cadastro = Atividade.CADASTRADO
                solicitacao_atividade.save()
            elif form.cleaned_data.get('operacao') == 'deferir':
                solicitacao_atividade.situacao_cadastro = Atividade.CADASTRADO
                solicitacao_atividade.ativo = True
                solicitacao_atividade.save()
            return httprr(url, 'Solicitação deferida com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@login_required
def indeferir_solicitacao_atividade(request, atividade_id):
    solicitacao_atividade = Atividade.objects.solicitacoes().filter(id=atividade_id)
    if not solicitacao_atividade:
        raise PermissionDenied
    solicitacao_atividade = solicitacao_atividade[0]

    if not solicitacao_atividade.pode_analisar_solicitacoes_cadastro_alteracao(request.user):
        raise PermissionDenied

    title = 'Indeferir alteração da atividade'
    if solicitacao_atividade.tipo_solicitacao == 'Cadastro':
        title = 'Indeferir cadastro da atividade'

    form = JustificativaComSenhaForm(request.POST or None, request=request)
    if form.is_valid():
        solicitacao_atividade.situacao_cadastro = Atividade.SOLICITACAO_INDEFERIDA
        solicitacao_atividade.ativo = False
        solicitacao_atividade.justificativa_indeferimento = form.cleaned_data.get('justificativa')
        solicitacao_atividade.save()

        url = '/admin/pgd/atividadesolicitacoes/'
        return httprr(url, 'Solicitação indeferida com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('pgd.change_periodopitrit')
def ativar_desativar_preencher_questionario_pesquisa(request, periodo_pit_rit_id):
    periodo = get_object_or_404(PeriodoPitRit, pk=periodo_pit_rit_id)
    periodo.preencher_questionario_pesquisa = not periodo.preencher_questionario_pesquisa
    periodo.save()
    url = '/admin/pgd/periodopitrit/'
    return httprr(url, 'Alteração realizada com sucesso.')


@rtr()
@login_required
def enviar_email_pgd(request):
    title = 'Enviar E-mail PGD'

    estah_em_comissao_sistemica_vigente = request.user.has_group_cached('Comissão Sistêmica PGD')
    estah_em_gestao_pgd = request.user.has_group_cached('Gestor do PGD')
    if not estah_em_comissao_sistemica_vigente and not estah_em_gestao_pgd:
        raise PermissionDenied

    lista_emails = []

    # Operações
    # - enviar_email_participantes_pgd_selecionados
    # - enviar_email_participantes_pgd_campi (a implementar)
    # - enviar_email_participantes_pgd_todos (a implementar)
    # - enviar_email_participantes_por_filtro (a implementar)

    # Valida a action
    # --------------------------------
    if not request.GET.get('action') or request.GET.get('action') != 'enviar_email_participantes_pgd_selecionados':
        raise PermissionDenied
    action_a_ser_executada = request.GET.get('action')

    # Pega os selecionadas
    # --------------------------------
    if action_a_ser_executada == 'enviar_email_participantes_pgd_selecionados':
        adesao_participantes = request.GET.getlist('checks')
        for ap in adesao_participantes:
            participante = SolicitacaoAdesaoServidor.objects.get(id=ap)
            if participante.servidor.email_institucional:
                lista_emails.append(participante.servidor.email_institucional)
        if not lista_emails:
            raise PermissionDenied

    # Envia o email
    # --------------------------------
    form = EnviarEmailComSenhaForm(request.POST or None, request=request)
    if form.is_valid():
        texto_mensagem = form.cleaned_data.get('mensagem')

        mensagem = f"""
                    Caro(a),

                    {texto_mensagem}
                    """

        send_mail('[SUAP] PGD', mensagem, settings.DEFAULT_FROM_EMAIL, [], bcc=lista_emails, fail_silently=True)

        return httprr('/admin/pgd/participantespgd/', 'Operação realizada com sucesso.')

    return locals()


# ====================================================
# PTS
# ====================================================


@rtr()
@permission_required('pgd.view_planotrabalhosetorial')
def visualizar_plano_trabalho_setorial(request, pts_id):
    pts = get_object_or_404(PlanoTrabalhoSetorial, pk=pts_id)
    if not pts.pode_visualizar(request.user):
        raise PermissionDenied

    pts.sincrononiza_inativacao_atividades()

    title = pts

    pode_editar = pts.pode_editar(request.user)
    pode_publicar = pts.pode_publicar(request.user)
    pode_despublicar = pts.pode_despublicar(request.user)
    pode_cancelar = pts.pode_cancelar(request.user)
    pode_editar_vigencia = pts.pode_editar_vigencia(request.user)
    pode_editar_documentacao = pts.pode_editar_documentacao(request.user)
    pode_vincular_atividades = pts.pode_vincular_atividades(request.user)
    pode_editar_auxiliares = pts.pode_editar_auxiliares(request.user)

    orientacoes_vigentes_sistemico = ConfiguracaoOrientacaoPlanoSetorial.get_vigentes_sistemico()
    orientacoes_vigentes_nao_sistemico = ConfiguracaoOrientacaoPlanoSetorial.get_vigentes_nao_sistemico(pts.setor.uo)
    atividades = pts.get_atividades()
    atividades_ativas = pts.get_atividades_ativas()
    auxiliares = pts.auxiliares.all()

    registros_acoes = RegistroAcaoPTS.objects.filter(pts=pts)

    return locals()


@rtr()
@permission_required('pgd.view_planotrabalhosetorial')
def visualizar_plano_trabalho_setorial_linha_tempo(request, pts_id):
    pts = get_object_or_404(PlanoTrabalhoSetorial, pk=pts_id)
    if not pts.pode_visualizar(request.user):
        raise PermissionDenied

    title = f'Linha do tempo do {pts}'
    url = reverse('visualizar_plano_trabalho_setorial', args=[pts_id])

    registros_acoes = RegistroAcaoPTS.objects.filter(pts=pts).order_by('data')

    return locals()


@rtr()
@transaction.atomic
@permission_required('pgd.change_planotrabalhosetorial')
def publicar_pts(request, pts_id):
    pts = get_object_or_404(PlanoTrabalhoSetorial, pk=pts_id)
    if not pts.pode_publicar(request.user):
        raise PermissionDenied

    title = f'Publicar e Aprovar eventuais ajustes do  {pts}'
    url = reverse('visualizar_plano_trabalho_setorial', args=[pts_id])

    form = JustificativaComSenhaForm(request.POST or None, request=request)
    if form.is_valid():
        pts.publicado = True
        pts.save()

        ip = get_client_ip(request)
        justificativa = form.cleaned_data.get('justificativa')
        ra_obs = f'O plano de trabalho setorial foi Publicado e Aprovado (eventuais ajustes) mediante a sguinte justificativa: {justificativa}'
        RegistroAcaoPTS.objects.create(tipo=RegistroAcaoPTS.TIPO_PUBLICADO, pts=pts, ip=ip, observacao=ra_obs)

        return httprr(url, 'Publicado com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('pgd.change_planotrabalhosetorial')
def despublicar_pts(request, pts_id):
    pts = get_object_or_404(PlanoTrabalhoSetorial, pk=pts_id)
    if not pts.pode_despublicar(request.user):
        raise PermissionDenied

    title = f'Despublicar {pts}'
    url = reverse('visualizar_plano_trabalho_setorial', args=[pts_id])

    form = JustificativaForm(request.POST or None, request=request)
    if form.is_valid():
        pts.publicado = False
        pts.save()

        ip = get_client_ip(request)
        justificativa = form.cleaned_data.get('justificativa')
        ra_obs = f'O plano de trabalho setorial foi despublicado mediante a sguinte justificativa: {justificativa}'
        RegistroAcaoPTS.objects.create(tipo=RegistroAcaoPTS.TIPO_DESPUBLICADO, pts=pts, ip=ip, observacao=ra_obs)

        return httprr(url, 'Despublicado com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@login_required
def cancelar_pts(request, pts_id):
    pts = get_object_or_404(PlanoTrabalhoSetorial, pk=pts_id)
    if not pts.pode_cancelar(request.user):
        raise PermissionDenied

    title = f'Cancelar {pts}'
    url = reverse('visualizar_plano_trabalho_setorial', args=[pts_id])

    form = JustificativaComSenhaIrreverssivelForm(request.POST or None, request=request)
    if form.is_valid():
        pts.cancelado = True
        pts.save()

        ip = get_client_ip(request)
        justificativa = form.cleaned_data.get('justificativa')
        ra_obs = f'O plano de trabalho setorial foi cancelado mediante a sguinte justificativa: {justificativa}'
        RegistroAcaoPTS.objects.create(tipo=RegistroAcaoPTS.TIPO_CANCELADO, pts=pts, ip=ip, observacao=ra_obs)

        return httprr(url, 'Cancelado com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@login_required
def editar_vigencia_pts(request, pts_id):
    pts = get_object_or_404(PlanoTrabalhoSetorial, pk=pts_id)
    if not pts.pode_editar_vigencia(request.user):
        raise PermissionDenied

    title = f'Editar Vigência do {pts}'
    url = reverse('visualizar_plano_trabalho_setorial', args=[pts_id])

    pts_data_inicio = pts.data_inicio
    pts_data_fim = pts.data_fim

    form = PlanoTrabalhoSetorialEditarVigenciaForm(request.POST or None, request=request, instance=pts)
    if form.is_valid():
        obj = form.save()

        if pts_data_inicio != obj.data_inicio or pts_data_fim != obj.data_fim:
            ip = get_client_ip(request)
            ra_obs = f'A vigência foi alterada para {format_datetime(obj.data_inicio)} a {format_datetime(obj.data_fim)}'
            RegistroAcaoPTS.objects.create(tipo=RegistroAcaoPTS.TIPO_EDITOU_VIGENCIA, pts=pts, ip=ip, observacao=ra_obs)

        return httprr(url, 'Vigência editada com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@login_required
def editar_documentacao_pts(request, pts_id):
    pts = get_object_or_404(PlanoTrabalhoSetorial, pk=pts_id)
    if not pts.pode_editar_documentacao(request.user):
        raise PermissionDenied

    title = f'Editar Documentação do Plano de Trabalho Setorial {pts}'
    url = reverse('visualizar_plano_trabalho_setorial', args=[pts_id])

    pts_doc_horario_funcionamento_setor = pts.doc_horario_funcionamento_setor
    pts_doc_escala_trabalho_setor = pts.doc_escala_trabalho_setor
    pts_doc_regras_planejamento_setor = pts.doc_regras_planejamento_setor
    pts_doc_infraestrutura_minima = pts.doc_infraestrutura_minima
    pts_doc_cohecimento_tecnico = pts.doc_cohecimento_tecnico

    form = PlanoTrabalhoSetorialEditarDocumentacaoForm(request.POST or None, request=request, instance=pts)
    if form.is_valid():
        obj = form.save()

        if (
            (pts_doc_horario_funcionamento_setor != obj.doc_horario_funcionamento_setor)
            or (pts_doc_escala_trabalho_setor != obj.doc_escala_trabalho_setor)
            or (pts_doc_regras_planejamento_setor != obj.doc_regras_planejamento_setor)
            or (pts_doc_infraestrutura_minima != obj.doc_infraestrutura_minima)
            or (pts_doc_cohecimento_tecnico != obj.doc_cohecimento_tecnico)
        ):
            ip = get_client_ip(request)
            RegistroAcaoPTS.objects.create(tipo=RegistroAcaoPTS.TIPO_DOCUMENTACAO, pts=pts, ip=ip, observacao='')

        return httprr(url, 'Documentação editada com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@login_required
def editar_auxiliares_pts(request, pts_id):
    pts = get_object_or_404(PlanoTrabalhoSetorial, pk=pts_id)
    if not pts.pode_editar_auxiliares(request.user):
        raise PermissionDenied

    title = f'Auxiliares do Chefe no Preenchimento do Plano de Trabalho Setorial {pts}'
    url = reverse('visualizar_plano_trabalho_setorial', args=[pts_id])

    pts_auxiliares = list(pts.auxiliares.values_list('id', flat=True)).copy()

    form = PlanoTrabalhoSetorialEditarAuxiliaresForm(request.POST or None, request=request, instance=pts)
    if form.is_valid():
        obj = form.save()

        if diferenca_listas(pts_auxiliares, obj.auxiliares.values_list('id', flat=True)):
            ip = get_client_ip(request)
            RegistroAcaoPTS.objects.create(tipo=RegistroAcaoPTS.TIPO_ALTEROU_AUXILIARES, pts=pts, ip=ip, observacao='')

        return httprr(url, 'Editado com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@login_required
def remover_atividade_pts(request, at_pts_id):
    at_pts = get_object_or_404(PlanoTrabalhoSetorialAtividades, pk=at_pts_id)
    url = reverse('visualizar_plano_trabalho_setorial', args=[at_pts.plano_trabalho_setorial.id])

    atr = at_pts.atividade
    pts = at_pts.plano_trabalho_setorial

    if at_pts.pode_remover_atividade(request.user):
        at_pts.delete()

        ip = get_client_ip(request)
        ra_obs = f'A atividade "{atr}" foi removida do PTS'
        RegistroAcaoPTS.objects.create(tipo=RegistroAcaoPTS.TIPO_ATIVIDADE_REMOVIDA, pts=pts, ip=ip, observacao=ra_obs)

        return httprr(url, 'Atividade removida com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@transaction.atomic
@login_required
def ativar_atividade_pts(request, at_pts_id):
    at_pts = get_object_or_404(PlanoTrabalhoSetorialAtividades, pk=at_pts_id)
    url = reverse('visualizar_plano_trabalho_setorial', args=[at_pts.plano_trabalho_setorial.id])

    atr = at_pts.atividade
    pts = at_pts.plano_trabalho_setorial

    if at_pts.pode_ativar_atividade(request.user):
        at_pts.ativo = True
        at_pts.save()

        ip = get_client_ip(request)
        ra_obs = f'A atividade "{atr}" foi ativada do PTS'
        RegistroAcaoPTS.objects.create(tipo=RegistroAcaoPTS.TIPO_ATIVIDADE_ATIVADA, pts=pts, ip=ip, observacao=ra_obs)

        return httprr(url, 'Atividade ativada com sucesso.')
    else:
        raise PermissionDenied


@rtr()
@transaction.atomic
@login_required
def desativar_atividade_pts(request, at_pts_id):
    at_pts = get_object_or_404(PlanoTrabalhoSetorialAtividades, pk=at_pts_id)
    url = reverse('visualizar_plano_trabalho_setorial', args=[at_pts.plano_trabalho_setorial.id])

    atr = at_pts.atividade
    pts = at_pts.plano_trabalho_setorial

    if at_pts.pode_desativar_atividade(request.user):
        at_pts.ativo = False
        at_pts.save()

        ip = get_client_ip(request)
        ra_obs = f'A atividade "{atr}" foi desativada do PTS'
        RegistroAcaoPTS.objects.create(tipo=RegistroAcaoPTS.TIPO_ATIVIDADE_DESATIVADA, pts=pts, ip=ip, observacao=ra_obs)

        return httprr(url, 'Atividade inativada com sucesso.')
    else:
        raise PermissionDenied


# ====================================================
# ADESÃO PGD
# ====================================================


@rtr()
@transaction.atomic
@permission_required('pgd.add_solicitacaoadesaoservidor')
def solicitar_adesao(request):
    title = 'Solicitar Adesão ao PGD'

    pode_solicitar, erros = SolicitacaoAdesaoServidor.pode_solicitar(request.user, True)

    if pode_solicitar:
        servidor = request.user.get_relacionamento()
        documento_vigente = DocumentoAdesaoServidor.get_vigente()

        form = SolicitarAdesaoPgdForm(request.POST or None, request=request)
        if request.method == 'POST':
            if form.is_valid():
                sol = SolicitacaoAdesaoServidor()
                sol.servidor = servidor
                sol.documento_adesao = documento_vigente
                sol.telefone = form.cleaned_data.get('telefone')
                sol.preferencia_contato = form.cleaned_data.get('preferencia_contato')
                sol.situacao = SolicitacaoAdesaoServidor.SOLICITADO
                sol.save()

                ip = get_client_ip(request)
                RegistroAcaoSolicitacaoAdesaoServidor.objects.create(
                    tipo=RegistroAcaoSolicitacaoAdesaoServidor.TIPO_SOLICITADO, solicitacao=sol, ip=ip, observacao=''
                )

                url = reverse('visualizar_solicitacao_adesao', args=[sol.id])
                return httprr(url, 'Solicitação de Adesão submetida com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@login_required
def editar_telefone_pgd(request, sol_id):
    sol = get_object_or_404(SolicitacaoAdesaoServidor, pk=sol_id)
    if not sol.pode_editar_telefone_pgd(request.user):
        raise PermissionDenied

    title = f'Editar Telefone para contato PGD - {sol}'
    url = reverse('visualizar_solicitacao_adesao', args=[sol_id])

    telefone = sol.telefone

    form = EditarTelefonePgdForm(request.POST or None, request=request, instance=sol)
    if form.is_valid():
        obj = form.save()
        return httprr(url, 'Telefone editado com sucesso.')

    return locals()


@rtr()
@permission_required('pgd.view_solicitacaoadesaoservidor')
def visualizar_solicitacao_adesao(request, sol_id):
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

    return locals()


@rtr()
@transaction.atomic
@permission_required('pgd.change_solicitacaoadesaoservidor')
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
    url = reverse('visualizar_solicitacao_adesao', args=[sol_id])

    form = JustificativaComSenhaForm(request.POST or None, request=request)

    if request.method == 'POST':
        if form.is_valid():
            sol.situacao = alteracao_id
            sol.save()

            ip = get_client_ip(request)
            justificativa = form.cleaned_data.get('justificativa')
            ra_obs = f'A situação da {sol.__str__()} foi alterada para "{SolicitacaoAdesaoServidor.SITUACAO_SOLICITACAO_ADESAO_CHOICES[alteracao_id - 1][1]}" mediante a justificativa "{justificativa}"'
            RegistroAcaoSolicitacaoAdesaoServidor.objects.create(tipo=alteracao_id, solicitacao=sol, ip=ip, observacao=ra_obs)

            return httprr(url, 'Realizado com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('pgd.pode_cadastrar_desligamento_pgd')
def cadastrar_desligamento_pgd(request, sol_id):
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

                adesao.data_desligamento_efeitos_a_partir_de = d.data_desligamento_efeitos_a_partir_de
                adesao.data_desligamento_carencia_ate = d.data_desligamento_efeitos_a_partir_de + relativedelta(
                    days=PlanoIndividualTrabalho.CARENCIA_PARA_EDICAO_PIT_SEM_ADESA_VIGENTE
                )
                adesao.save()

                url = reverse('visualizar_solicitacao_adesao', args=[adesao.id])

                ip = get_client_ip(request)
                justificativa = form.cleaned_data.get('justificativa')
                ra_obs = f'O Desligamento do PGD da {adesao.__str__()} foi cadastrado com daata de efeitos a partir de "{format_datetime(data_desligamento_efeitos_a_partir_de)}" mediante seguinte justificativa "{justificativa}". Além disso, CONFIRMOU que estava ciente de que este desligamento só poderia ser cancelado até o dia anterior da data de efeitos.'
                RegistroAcaoSolicitacaoAdesaoServidor.objects.create(
                    tipo=RegistroAcaoSolicitacaoAdesaoServidor.TIPO_DESLIGAMENTO, solicitacao=adesao, ip=ip, observacao=ra_obs
                )

                return httprr(url, 'Desligamento cadastrado sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('pgd.view_solicitacaoadesaoservidor')
def cancelar_desligamento_pgd(request, deslig_id):
    desligamento = get_object_or_404(DesligamentoPgdServidor, pk=deslig_id)
    if not desligamento.pode_cancelar(request.user):
        raise PermissionDenied

    title = f'Cancelar desligado da adesão {desligamento.adesao}'
    url = reverse('visualizar_solicitacao_adesao', args=[desligamento.adesao.id])

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

            ip = get_client_ip(request)
            justificativa = form.cleaned_data.get('justificativa')
            ra_obs = f'O Desligamento com efeitos a partir de "{format_datetime(desligamento.adesao.data_desligamento_efeitos_a_partir_de)}" foi cancelado mediante a justificativa "{justificativa}".'
            RegistroAcaoSolicitacaoAdesaoServidor.objects.create(
                tipo=RegistroAcaoSolicitacaoAdesaoServidor.TIPO_DESLIGAMENTO_CANCELADO, solicitacao=desligamento.adesao, ip=ip, observacao=ra_obs
            )

            return httprr(url, 'Realizado com sucesso.')

    return locals()


# ====================================================
# ADESÃO PTS
# ====================================================


@rtr()
@transaction.atomic
@permission_required('pgd.add_solicitacaoadesaoptsservidor')
def solicitar_adesao_pts(request, setor_id):
    setor = get_object_or_404(Setor, pk=setor_id)
    title = f'Solicitar Adesão ao PTS do Setor {setor}'

    pode_solicitar, erros = SolicitacaoAdesaoPtsServidor.pode_solicitar(user=request.user, setor=setor, adesao_pgd=None, retornar_lista_erros=True)

    if pode_solicitar:
        pts_apto = PlanoTrabalhoSetorial.get_pts_apto(setor)
        adesoes_pgd = SolicitacaoAdesaoServidor.get_vigentes_e_na_carencia(request.user)
        documento_vigente = DocumentoAdesaoPtsServidor.get_vigente()
        servidor = request.user.get_relacionamento()
        atividades = pts_apto.get_atividades()

        form = SolicitarAdesaoPtsForm(request.POST or None, request=request, adesoes_pgd=adesoes_pgd)
        if request.method == 'POST':
            if form.is_valid():
                adesao_pgd = form.cleaned_data.get('adesao_pgd')
                pode_solicitar, erros = SolicitacaoAdesaoPtsServidor.pode_solicitar(
                    user=request.user, setor=setor, adesao_pgd=adesao_pgd, retornar_lista_erros=True
                )
                if not pode_solicitar:
                    return locals()

                sol = SolicitacaoAdesaoPtsServidor()
                sol.plano_trabalho_setorial = pts_apto
                sol.adesao = adesao_pgd
                sol.situacao = SolicitacaoAdesaoPtsServidor.SOLICITADO
                sol.documento_adesao = documento_vigente
                sol.save()

                ip = get_client_ip(request)
                RegistroAcaoSolicitacaoAdesaoPtsServidor.objects.create(
                    tipo=RegistroAcaoSolicitacaoAdesaoPtsServidor.TIPO_SOLICITADO, solicitacao=sol, ip=ip, observacao=''
                )

                url = reverse('visualizar_solicitacao_adesao_pts', args=[sol.id])
                return httprr(url, 'Solicitação de Adesão ao PTS submetida com sucesso.')

    return locals()


@rtr()
@permission_required('pgd.view_solicitacaoadesaoptsservidor')
def visualizar_solicitacao_adesao_pts(request, sol_id):
    sol = get_object_or_404(SolicitacaoAdesaoPtsServidor, pk=sol_id)

    title = 'Solicitação de Adesão do Servidor ao PTS'

    if not sol.pode_visualizar(request.user):
        raise PermissionDenied

    servidor = sol.adesao.servidor
    pode_cancelar_servidor = sol.pode_cancelar_servidor(request.user)
    pode_cancelar_avaliador = sol.pode_cancelar_avaliador(request.user)
    pode_avaliar = sol.pode_avaliar(request.user)
    pode_cadastrar_desligamento_servidor = sol.pode_cadastrar_desligamento_servidor(request.user)

    registros_acoes = RegistroAcaoSolicitacaoAdesaoPtsServidor.objects.filter(solicitacao=sol)

    return locals()


@rtr()
@transaction.atomic
@permission_required('pgd.change_solicitacaoadesaoptsservidor')
def alterar_situacao_solicitacao_adesao_pts(request, sol_id, alteracao_id):
    # Acessado pelo Servidor e Chefe

    sol = get_object_or_404(SolicitacaoAdesaoPtsServidor, pk=sol_id)

    # Sabendo e verificando qual alteração será feita
    # SolicitacaoAdesaoServidor.CANCELADO_PELO_SERVIDOR = 2
    # SolicitacaoAdesaoServidor.CANCELADO_PELO_AVALIADOR = 3
    # SolicitacaoAdesaoServidor.DEFERIDO = 4
    # SolicitacaoAdesaoServidor.INDEFERIDO = 5
    if alteracao_id not in [
        SolicitacaoAdesaoPtsServidor.CANCELADO_PELO_SERVIDOR,
        SolicitacaoAdesaoPtsServidor.CANCELADO_PELO_AVALIADOR,
        SolicitacaoAdesaoPtsServidor.DEFERIDO,
        SolicitacaoAdesaoPtsServidor.INDEFERIDO,
    ]:
        raise PermissionDenied
    if (
        alteracao_id == SolicitacaoAdesaoPtsServidor.CANCELADO_PELO_SERVIDOR
        and not sol.pode_cancelar_servidor(request.user)
        or alteracao_id == SolicitacaoAdesaoPtsServidor.CANCELADO_PELO_AVALIADOR
        and not sol.pode_cancelar_avaliador(request.user)
        or alteracao_id == SolicitacaoAdesaoPtsServidor.DEFERIDO
        and not sol.pode_avaliar(request.user)
        or alteracao_id == SolicitacaoAdesaoPtsServidor.INDEFERIDO
        and not sol.pode_avaliar(request.user)
    ):
        raise PermissionDenied

    title = f'Alteração a situação da {sol.__str__()} para {SolicitacaoAdesaoPtsServidor.SITUACAO_SOLICITACAO_ADESAO_CHOICES[alteracao_id - 1][1]}'
    url = reverse('visualizar_solicitacao_adesao_pts', args=[sol_id])

    form = JustificativaComSenhaForm(request.POST or None, request=request)

    if request.method == 'POST':
        if form.is_valid():
            sol.situacao = alteracao_id
            sol.save()

            ip = get_client_ip(request)
            justificativa = form.cleaned_data.get('justificativa')
            ra_obs = f'A situação da {sol.__str__()} foi alterada para "{SolicitacaoAdesaoServidor.SITUACAO_SOLICITACAO_ADESAO_CHOICES[alteracao_id - 1][1]}" mediante a justificativa "{justificativa}"'
            RegistroAcaoSolicitacaoAdesaoPtsServidor.objects.create(tipo=alteracao_id, solicitacao=sol, ip=ip, observacao=ra_obs)

            return httprr(url, 'Realizado com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('pgd.pode_cadastrar_desligamento_pts')
def cadastrar_desligamento_pts(request, sol_id):
    # Servidor Cadastra Desligamento

    sol = get_object_or_404(SolicitacaoAdesaoPtsServidor, pk=sol_id)
    title = 'Cadastrar Desligamento de PTS'
    servidor = sol.adesao.servidor

    if not sol.pode_cadastrar_desligamento_servidor(request.user):
        raise PermissionDenied

    url = reverse('visualizar_solicitacao_adesao_pts', args=[sol_id])

    form = JustificativaComSenhaIrreverssivelForm(request.POST or None, request=request)

    if request.method == 'POST':
        if form.is_valid():
            sol.data_desligamento = get_datetime_now()
            sol.save()

            ip = get_client_ip(request)
            justificativa = form.cleaned_data.get('justificativa')
            ra_obs = f'Foi cadastrado um DESLIGAMENTO para {sol.__str__()} mediante a justificativa "{justificativa}"'
            RegistroAcaoSolicitacaoAdesaoPtsServidor.objects.create(
                tipo=RegistroAcaoSolicitacaoAdesaoPtsServidor.TIPO_DESLIGAMENTO, solicitacao=sol, ip=ip, observacao=ra_obs
            )

            return httprr(url, 'Realizado com sucesso.')

    return locals()


# ====================================================
# PIT
# ====================================================


@rtr()
@permission_required('rh.eh_servidor')
def servidor_pgd(request):
    servidor_pgd = request.user.get_relacionamento()
    servidor_acesso = request.user.get_relacionamento()
    # Tentando ver de outro servidor
    if request.GET.get('servidor_pgd'):
        servidor_pgd = request.GET.get('servidor_pgd')
        if servidor_pgd:
            servidor_pgd = get_object_or_404(Servidor.objects, matricula=servidor_pgd)
            servidor = servidor_pgd

    eh_proprio_servidor = servidor_pgd == servidor_acesso
    if not PlanoIndividualTrabalho.pode_gestao_visualizar_pgd_servidor(servidor_pgd, servidor_acesso.get_user()):
        raise PermissionDenied

    servidor = servidor_pgd
    title = f'Meu PGD - {servidor}'
    if not eh_proprio_servidor:
        title = servidor

    # Adesão do servidor ao PGD
    adesoes_pgd = SolicitacaoAdesaoServidor.objects.filter(servidor=servidor).order_by('id')

    # Pendencias do servidor
    pits_pendencias_lista = []
    rits_pendencias_lista = []
    if eh_proprio_servidor:
        pits_pendencias = PlanoIndividualTrabalho.get_pendencias_pit_servidor(servidor)
        rits_pendencias = PlanoIndividualTrabalho.get_pendencias_rit_servidor(servidor)
        for p in pits_pendencias:
            pits_pendencias_lista.append(p.get_verbose_periodo())
        for p in rits_pendencias:
            rits_pendencias_lista.append(p.get_verbose_planejamento_periodo())

    return locals()


@rtr()
@permission_required('rh.chefe')
def listar_pendencias_setor_servidor(request):
    title = 'Pendências dos Servidores'

    setores_chefe = setores_que_sou_chefe_hoje(request.user.get_relacionamento())
    setores_chefe_direto = setores_que_sou_chefe_direto_hoje(request.user.get_relacionamento())

    sem_filtro = True
    querys = []
    querys.append(Q(servidor__setor__in=setores_chefe_direto))

    form = BuscarServidoresPgdForm(request.GET or None, request=request, setores_chefe=setores_chefe)
    if form.is_valid():
        buscar_str = form.cleaned_data.get('buscar_str')
        setor = form.cleaned_data.get('setor')
        if buscar_str or setor:
            sem_filtro = False
            querys = []
            if setor:
                querys.append(Q(servidor__setor=setor))
            if buscar_str:
                querys.append(Q(servidor__pessoa_fisica__nome__icontains=buscar_str) | Q(servidor__matricula__icontains=buscar_str))
            if not setor and buscar_str:
                querys.append(Q(servidor__setor__in=setores_chefe))

    servidores_vinculados = Servidor.objects.vinculados()
    lista_servidores = (
        SolicitacaoAdesaoServidor.get_adesoes_vigentes()
        .filter(reduce(operator.and_, querys), servidor__in=servidores_vinculados)
        .order_by('servidor__pessoa_fisica__nome')
    )

    lista_servidores_pendencias = []
    for ls in lista_servidores:
        pits_pendencias_lista = []
        rits_pendencias_lista = []
        pits_pendencias = PlanoIndividualTrabalho.get_pendencias_pit_servidor(ls.servidor)
        rits_pendencias = PlanoIndividualTrabalho.get_pendencias_rit_servidor(ls.servidor)
        for p in pits_pendencias:
            pits_pendencias_lista.append(p.get_verbose_periodo())
        for p in rits_pendencias:
            rits_pendencias_lista.append(p.get_verbose_planejamento_periodo())
        lista_servidores_pendencias.append(
            {'servidor': ls.servidor, 'pendencias_pit': pits_pendencias_lista, 'pendencias_rit': rits_pendencias_lista}
        )

    return locals()


@rtr()
@permission_required('rh.eh_servidor')
def servidor_pgd_horas(request, sol_id):
    # Lista as horas do servidor para cada adesão

    adesao = get_object_or_404(SolicitacaoAdesaoServidor, pk=sol_id)
    servidor = adesao.servidor
    if not adesao.estah_deferida or not PlanoIndividualTrabalho.pode_gestao_visualizar_pgd_servidor(servidor, request.user):
        raise PermissionDenied

    title = f'Horas PGD - {servidor} da {adesao.get_verbose_simples()}'

    totais_soma = [
        'tempo_previsto',
        'tempo_planejado',
        'tempo_executado',
        'tempo_executado_entregue',
        'tempo_executado_nao_entregue',
        'tempo_executado_homologado',
        'ch_distribuida',
        'ch_distribuido_periodo_rit',
        'ch_distribuido_semestre_rit',
        'ch_a_distribuir',
    ]
    anos = set()

    rits = adesao.get_rits().order_by('-pit__data_inicial')
    for rit in rits:
        anos.add(rit.get_data_inicial().year)
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
            if rit.get_data_inicial().year == ano:
                if rit.get_data_inicial().month <= 6:
                    ids_rits_ano_s1.append(rit.id)
                else:
                    ids_rits_ano_s2.append(rit.id)
        i = f'{ano}-1'
        f = f'{ano}-2'

        # Semestre 1
        dados_semestre = {}
        rits_1 = RelatorioIndividualTrabalho.objects.filter(id__in=ids_rits_ano_s1).order_by('pit__data_inicial')
        dados_semestre['rits'] = rits_1
        for total in totais_soma:
            dados_semestre[total] = gv(rits_1.aggregate(v=Sum(total)))
        semestres[i] = dados_semestre

        # Semestre 2
        dados_semestre = {}
        rits_2 = RelatorioIndividualTrabalho.objects.filter(id__in=ids_rits_ano_s2).order_by('pit__data_inicial')
        dados_semestre['rits'] = rits_2
        for total in totais_soma:
            dados_semestre[total] = gv(rits_2.aggregate(v=Sum(total)))
        semestres[f] = dados_semestre

    return locals()


@rtr()
@permission_required('rh.eh_servidor')
def servidor_pgd_horas_detalhes(request, rit_id):
    # Lista as horas do servidor para cada adesão

    rit = get_object_or_404(RelatorioIndividualTrabalho, pk=rit_id)

    servidor = rit.pit.adesao.servidor
    adesao = rit.pit.adesao

    if not PlanoIndividualTrabalho.pode_gestao_visualizar_pgd_servidor(servidor, request.user):
        raise PermissionDenied

    pit = rit.pit

    title = f'Distribuição de Horas do {rit.get_verbose_rit_servidor()}'

    pode_distribuir_horas = rit.pode_distribuir_horas(request.user)
    pode_ajustar_distribuicao_horas_semestre_rit = rit.pode_ajustar_distribuicao_horas_semestre_rit(request.user)
    pode_desfazer_distribuicao_horas_semestre = rit.pode_desfazer_distribuicao_horas_semestre(request.user)

    distribuicoes = RelatorioIndividualTrabalhoDistribuicaoHoras.objects.filter(rit=rit)
    distribuicoes_semestre_rit = distribuicoes.filter(
        tipo__in=[RelatorioIndividualTrabalhoDistribuicaoHoras.PERIODO_RIT, RelatorioIndividualTrabalhoDistribuicaoHoras.SEMESTRE_RIT]
    )
    distribuicoes_semestre_antes_rit = distribuicoes.filter(tipo=RelatorioIndividualTrabalhoDistribuicaoHoras.SEMESTRE_ANTES_RIT)
    distribuicoes_compensacao_especifica = distribuicoes.filter(tipo=RelatorioIndividualTrabalhoDistribuicaoHoras.COMPENSACAO_ESPECIFICA)
    distribuicoes_semestre_pos_rit = distribuicoes.filter(tipo=RelatorioIndividualTrabalhoDistribuicaoHoras.SEMESTRE_POS_RIT)

    pode_ajustar_distribuicoes_compensacao_especifica = False
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
    for d in dados_semestre_rit:
        ch_segundos_saldos_externos_periodo_rit += d.saldo_externo.valor_saldo
    dados_semestre_rit.extend(distribuicoes_semestre_antes_rit)
    dados_semestre_rit.extend(distribuicoes_semestre_pos_rit)
    dados_compensacao_especifica = list(distribuicoes_compensacao_especifica)

    ch_segundos_diferenca_periodo_rit = ch_segundos_rit_ch_distribuido_periodo_rit - ch_segundos_saldos_externos_periodo_rit
    if ch_segundos_diferenca_periodo_rit < 0:
        ch_segundos_diferenca_periodo_rit = 0

    dados_saldos_externos_criados = [d.saldo_externo for d in dados_semestre_rit]
    dados_saldos_externos_criados_totais = SaldoExterno.get_valores_totais(dados_saldos_externos_criados)

    return locals()


@rtr()
@transaction.atomic
@permission_required('pgd.add_planoindividualtrabalho')
def cadastrar_pit(request):
    # Servidor
    pode_iniciar_cadastro, erros = PlanoIndividualTrabalho.pode_iniciar_cadastro(user=request.user, retornar_lista_erros=True)

    servidor = request.user.get_relacionamento()
    title = f'Adicionar PIT - {servidor}'

    if pode_iniciar_cadastro:
        adesoes_pgd = SolicitacaoAdesaoServidor.get_vigentes_e_na_carencia(request.user)
        form = CriarPitForm(request.POST or None, request=request, adesoes_pgd=adesoes_pgd)
        if request.method == 'POST':
            if form.is_valid():
                adesao_pgd = form.cleaned_data.get('adesao_pgd')
                periodo_pit_rit = form.cleaned_data.get('periodo_pit_rit')

                # Gera o PIT
                pit = PlanoIndividualTrabalho()
                pit.adesao = adesao_pgd
                pit.periodo_pit_rit = periodo_pit_rit
                pit.situacao = PlanoIndividualTrabalho.CADASTRADO
                pit.data_inicial = periodo_pit_rit.data_inicio
                pit.save()

                # Gera os RITs conforme o calendario
                periodos_rit = periodo_pit_rit.get_periodos_calendario_rit()
                periodo = 1
                for _periodo_rit in periodos_rit:
                    rit = RelatorioIndividualTrabalho()
                    rit.pit = pit
                    rit.periodo = periodo
                    rit.save()
                    periodo += 1

                ip = get_client_ip(request)
                RegistroAcaoPlanoIndividualTrabalho.objects.create(
                    tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_CADASTRADO, pit=pit, ip=ip, observacao=''
                )

                url = reverse('servidor_pgd')
                return httprr(url, 'PIT adicionado com sucesso.')

    return locals()


@rtr()
@permission_required('pgd.view_planoindividualtrabalho')
def visualizar_plano_individual_trabalho(request, pit_id):
    # Servidor

    pit = get_object_or_404(PlanoIndividualTrabalho, pk=pit_id)
    if not pit.pode_visualizar(request.user):
        url = reverse('visualizar_pit_completo', args=[pit_id])
        return httprr(url)

    title = pit.get_verbose_pit_rit()

    servidor = request.user.get_relacionamento()

    pode_editar_dado_especifico = pit.pode_servidor_editar(request.user)
    pode_servidor_cancelar_pit = pit.pode_servidor_cancelar_pit(request.user)

    orientacoes_vigentes_sistemico = ConfiguracaoOrientacaoPit.get_vigentes_sistemico()
    orientacoes_vigentes_nao_sistemico = ConfiguracaoOrientacaoPit.get_vigentes_nao_sistemico(servidor.setor.uo)

    planejamentos = RelatorioIndividualTrabalho.objects.filter(pit=pit).order_by('periodo')
    registros_acoes = RegistroAcaoPlanoIndividualTrabalho.objects.filter(pit=pit)

    msg_adesao_relacionada = pit.adesao

    return locals()


@rtr()
@permission_required('pgd.view_planoindividualtrabalho')
def visualizar_chefe_plano_individual_trabalho(request, pit_id):
    # Chefe

    pit = get_object_or_404(PlanoIndividualTrabalho, pk=pit_id)
    if not pit.pode_visualizar(request.user):
        url = reverse('visualizar_pit_completo', args=[pit_id])
        return httprr(url)

    title = pit.get_verbose_pit_rit()

    servidor = pit.adesao.servidor

    planejamentos = RelatorioIndividualTrabalho.objects.filter(pit=pit).order_by('periodo')

    setores_sou_chefe_hoje = setores_que_sou_chefe_hoje(request.user.get_relacionamento())
    # Se pode APENAS HOMOLOGAR O PLANEJAMENTO
    pode_chefe_autorizar_pit_planejamento = pit.pode_chefe_autorizar_pit_planejamento(request.user, setores_chefe_hoje=setores_sou_chefe_hoje)
    depois_pode_chefe_autorizar_pit_planejamento = pit.pode_chefe_autorizar_pit_planejamento(
        request.user, setores_chefe_hoje=setores_sou_chefe_hoje, depois=True
    )
    # Se pode APENAS AUTORIZAR ALGUMA ATIVIDADE
    pode_chefe_autorizar_alguma_atividade, ids_atividades_pode = pit.pode_chefe_autorizar_atividades(
        request.user, setores_chefe_hoje=setores_sou_chefe_hoje
    )

    pode_aprovar_homologar_pit_rit = pit.pode_aprovar_homologar_pit_rit(request.user) and (
        pode_chefe_autorizar_pit_planejamento or pode_chefe_autorizar_alguma_atividade
    )

    tem_atividades_nao_autorizadas = pit.get_atividades_a_aprovar_do_pit().exists()

    quem_deve_aprovar_atividades = pit.get_ptss_das_atividades_a_aprovar_do_pit()
    quem_deve_autorizar_pit = pit.get_setor_a_autorizar_pit()

    return locals()


@rtr()
@transaction.atomic
@login_required
def editar_dados_especificos_pit(request, pit_id):
    # Servidor

    pit = get_object_or_404(PlanoIndividualTrabalho, pk=pit_id)
    if not pit.pode_servidor_editar(request.user):
        raise PermissionDenied

    title = f'Editar Dados Específicos do {pit}'
    url = reverse('visualizar_plano_individual_trabalho', args=[pit_id])

    data_inicial = pit.data_inicial
    percentual_presencial = pit.percentual_presencial
    percentual_teletrabalho = pit.percentual_teletrabalho

    form = PlanoIndividualTrabalhoEditarEspecificosForm(request.POST or None, request=request, instance=pit)
    if form.is_valid():
        obj = form.save()

        # if data_inicial != obj.data_inicial or percentual_presencial != obj.percentual_presencial or percentual_teletrabalho != obj.percentual_teletrabalho:
        # if percentual_presencial != obj.percentual_presencial or percentual_teletrabalho != obj.percentual_teletrabalho:
        if (
            data_inicial != obj.data_inicial
            or percentual_presencial != obj.percentual_presencial
            or percentual_teletrabalho != obj.percentual_teletrabalho
        ):
            ip = get_client_ip(request)
            ra_obs = 'Os dados específicos do PIT foram alterados'
            RegistroAcaoPlanoIndividualTrabalho.objects.create(
                tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_ALTEROU_DADOS_ESPECIFICOS, pit=pit, ip=ip, observacao=ra_obs
            )

        return httprr(url, 'Dados alterados com sucesso.')

    return locals()


@rtr()
@login_required()
def visualizar_pit_completo(request, pit_id):
    pit = get_object_or_404(PlanoIndividualTrabalho, pk=pit_id)

    if not pit.pode_visualizar_pit_completo(request.user):
        raise PermissionDenied

    pit = PlanoIndividualTrabalho.objects.get(pk=pit_id)

    title = f'{pit!s}'

    servidor = pit.adesao.servidor

    # Acoes
    registros_acoes = RegistroAcaoPlanoIndividualTrabalho.objects.filter(pit=pit)
    registros_acoes_rits = RegistroAcaoRelatorioIndividualTrabalho.objects.filter(rit__pit=pit)

    # PTSs relacionados
    ptss_relacionados = pit.get_pts_relacionados()

    # RITs relacionados
    rits_relacionados = pit.get_rits_relacionados()

    pode_servidor_cancelar_pit = pit.pode_servidor_cancelar_pit(request.user)

    return locals()


@rtr()
@transaction.atomic
@permission_required('pgd.change_planoindividualtrabalho')
def cancelar_pit(request, pit_id):
    pit = get_object_or_404(PlanoIndividualTrabalho, pk=pit_id)
    if not pit.pode_servidor_cancelar_pit(request.user):
        raise PermissionDenied

    url = reverse('servidor_pgd')
    title = f'Cancelar {pit.get_verbose_pit_rit()}'

    form = JustificativaComSenhaIrreverssivelForm(request.POST or None, request=request)
    if form.is_valid():
        # Cancelando PIT
        pit.situacao = PlanoIndividualTrabalho.CANCELADO_PELO_SERVIDOR
        pit.homologado_definitivo = False
        pit.save()

        # Desfazendo distribuição de horas dos RITs relacionados
        rits = pit.get_rits_relacionados()
        for rit in rits:
            rit.desfazer_distribuicao_horas()
            rit.ch_a_distribuir = 0
            rit.save()

        ip = get_client_ip(request)
        justificativa = form.cleaned_data.get('justificativa')
        ra_obs = f'O "{pit}" foi CANCELADO PELO SERVIDOR mediante a justificativa "{justificativa}"'
        RegistroAcaoPlanoIndividualTrabalho.objects.create(
            tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_CANCELADO_PELO_SERVIDOR, pit=pit, ip=ip, observacao=ra_obs
        )
        return httprr(url, 'PIT cancelado com sucesso.')

    return locals()


# ====================================================
# PIT - RIT - Planejamento de atividades
# ====================================================


@rtr()
@permission_required('pgd.view_planoindividualtrabalho')
def visualizar_planejamento(request, rit_id):
    rit = get_object_or_404(RelatorioIndividualTrabalho, pk=rit_id)
    servidor = request.user.get_relacionamento()
    if not rit.pit.pode_visualizar(request.user):
        raise PermissionDenied
    pit = rit.pit

    ptss_relacionados = pit.get_pts_relacionados()
    if ptss_relacionados:
        for pts_relacionados in ptss_relacionados:
            pts_relacionados.sincrononiza_inativacao_atividades()

    pode_recalcular_pit_rit = rit.pit.pode_recalcular_pit_rit(request.user)
    rit.pit.calcular_pit(forcar_recalcular_tempo_previsto=True)

    rit = RelatorioIndividualTrabalho.objects.get(id=rit_id)

    title = f'{rit.get_verbose_planejamento()} | {rit.pit.adesao.servidor}'

    pode_editar = rit.pode_servidor_editar(request.user)
    pode_servidor_solicitar_aprovacao_pit_rit = rit.pit.pode_servidor_solicitar_aprovacao_pit_rit(request.user)

    atividades_rit = rit.get_atividades().order_by('atividade_pts__plano_trabalho_setorial__setor', 'atividade_pts__atividade__titulo')

    registros_acoes = RegistroAcaoPlanoIndividualTrabalho.objects.filter(pit=rit.pit)

    quem_deve_aprovar_atividades = pit.get_ptss_das_atividades_a_aprovar_do_pit()
    quem_deve_autorizar_pit = pit.get_setor_a_autorizar_pit()

    msg_adesao_relacionada = pit.adesao

    return locals()


@rtr()
@login_required
@permission_required('pgd.change_planoindividualtrabalho')
def adicionar_selecionar_atividade_rit(request, rit_id):
    # Servidor

    # Tela para selecionar uma atividade que será adicionada a um PIT
    # Seleciona a atividade com base nos seguintes criterios
    # - Atividades relacionadas a adesao vigente e aos PTSs do servidor

    rit = get_object_or_404(RelatorioIndividualTrabalho, pk=rit_id)
    if not rit.pode_servidor_editar(request.user):
        raise PermissionDenied

    title = f'Vincular atividades ao {rit.get_verbose_planejamento()} - Selecionar'

    ptss_relacionados = rit.pit.get_pts_relacionados()
    if ptss_relacionados:
        for pts_relacionados in ptss_relacionados:
            pts_relacionados.sincrononiza_inativacao_atividades()

    # Atividades que podem ser adicionadas
    atividades_para_adicionar = rit.get_atividades_para_adicionar()

    # PTSs do servidor
    pts_aptos = PlanoTrabalhoSetorial.get_pts_ativo_do_servidor(rit.pit.adesao)

    # Preparando Filtros
    # -------------------------
    tematicas = TematicaAtividade.objects.all().order_by('titulo')

    buscou = request.GET.get('buscarselecionaratividadeadicionarpit_form')
    form = BuscarSelecionarAtividadeAdicionarPitForm(request.GET or None, pts_aptos=pts_aptos)

    buscar_str = None
    buscar_str2 = None
    pts = None
    tematica = None
    subtematica = None
    servico = None
    atividade = None
    pode_ser_teletrabalho = None
    ativo = None
    ordenar_por = 'hierarquia'
    organizacao = 'aba_por_tematica'

    lista_dados = []

    # Obtendo os filtros
    if buscou and form.is_valid():
        buscar_str = form.cleaned_data.get('buscar_str')
        buscar_str2 = form.cleaned_data.get('buscar_str2')
        pts = form.cleaned_data.get('pts')
        tematica = form.cleaned_data.get('tematica')
        subtematica = form.cleaned_data.get('subtematica')
        servico = form.cleaned_data.get('servico')
        atividade = form.cleaned_data.get('atividade')

        pode_ser_teletrabalho = None
        if form.cleaned_data.get('pode_ser_teletrabalho'):
            if form.cleaned_data.get('pode_ser_teletrabalho') == '1':
                pode_ser_teletrabalho = True
            else:
                pode_ser_teletrabalho = False

        ativo = None
        if form.cleaned_data.get('ativo'):
            if form.cleaned_data.get('ativo') == '1':
                ativo = True
            else:
                ativo = False

        ativo = None
        if form.cleaned_data.get('ativo'):
            if form.cleaned_data.get('ativo') == '1':
                ativo = True
            else:
                ativo = False

        organizacao = form.cleaned_data.get('organizacao')

        ordenar_por = form.cleaned_data.get('ordenar_por')

    # Prepara queryset
    # -------------------------
    atividades = (
        PlanoTrabalhoSetorialAtividades.objects.all()
        .select_related('atividade__tematica', 'atividade__subtematica', 'atividade__servico')
        .prefetch_related('atividade__atividadeentrega_set')
    )
    atividades = atividades.filter(id__in=atividades_para_adicionar.values_list('id', flat=True))

    # Aplica filtros
    # -------------------------
    # Buscar no Título e Descrição da Atividade
    if buscar_str:
        atividades = atividades.filter(Q(atividade__titulo__icontains=buscar_str) | Q(atividade__descricao__icontains=buscar_str))
    # Buscar no Título da Entrega
    if buscar_str2:
        entregas = AtividadeEntrega.objects.filter(titulo__icontains=buscar_str2)
        atividades = atividades.filter(atividade__id__in=entregas.values_list('atividade__id', flat=True))
    # Buscar pts
    if pts:
        atividades = atividades.filter(plano_trabalho_setorial=pts)
    # Buscar tematica
    if tematica:
        atividades = atividades.filter(atividade__tematica=tematica)
    # Buscar subtematica
    if subtematica:
        atividades = atividades.filter(atividade__subtematica=subtematica)
    # Buscar servico
    if servico:
        atividades = atividades.filter(atividade__servico=servico)
    # Buscar atividade
    if atividade:
        atividades = atividades.filter(atividade__atividade=atividade)
    if pode_ser_teletrabalho is not None:
        atividades = atividades.filter(atividade__pode_ser_teletrabalho=pode_ser_teletrabalho)
    if ativo is not None:
        atividades = atividades.filter(atividade__ativo=ativo)
    # Ordenacao
    if ordenar_por == 'hierarquia':
        atividades = atividades.order_by(
            'atividade__tematica__titulo', 'atividade__subtematica__titulo', 'atividade__servico__titulo', 'atividade__titulo'
        )
    else:
        atividades = atividades.order_by(ordenar_por)

    tem_atividade_aba_por_tematica = False
    if organizacao == 'aba_por_tematica':
        # Gerando os dados de cada aba (organização em abas por tematica)
        # -------------------------
        for obj_tematica in tematicas:
            dados = {}
            dados['tematica'] = obj_tematica

            dados['atividades'] = atividades.filter(atividade__tematica=obj_tematica)
            if not tem_atividade_aba_por_tematica and dados['atividades']:
                tem_atividade_aba_por_tematica = True
            lista_dados.append(dados)

    limpar_filtro = bool(request.GET)

    return locals()


@rtr()
@transaction.atomic
@permission_required('pgd.change_planoindividualtrabalho')
def adicionar_atividade_rit(request, rit_id, pts_atividade_id):
    # Servidor

    rit = get_object_or_404(RelatorioIndividualTrabalho, pk=rit_id)
    if not rit.pode_servidor_editar(request.user):
        raise PermissionDenied

    pts_atividade = get_object_or_404(PlanoTrabalhoSetorialAtividades, pk=pts_atividade_id)

    # Atividades que podem ser adiconadas ao PIT/RIT (Planejamento)
    atividades_para_adicionar = rit.get_atividades_para_adicionar()
    if not atividades_para_adicionar.filter(id=pts_atividade_id).exists():
        raise PermissionDenied

    title = f'Vincular atividades ao {rit.get_verbose_planejamento()} - Dados'

    form = AdicionarAtividadeRitForm(request.POST or None, pts_atividade=pts_atividade, rit=rit)
    if form.is_valid():
        atividade_rit = RelatorioIndividualTrabalhoAtividade()
        atividade_rit.rit = rit
        atividade_rit.situacao = RelatorioIndividualTrabalhoAtividade.CADASTRADO
        atividade_rit.atividade_pts = form.cleaned_data.get('atividade')
        atividade_rit.data_prazo = form.cleaned_data.get('data_prazo')
        atividade_rit.tempo_planejado = form.cleaned_data.get('tempo_planejado')
        atividade_rit.descricao = form.cleaned_data.get('descricao')
        atividade_rit.save()

        ip = get_client_ip(request)
        ra_obs = f'A atividade "{atividade_rit.atividade_pts.atividade}" foi adicionada ao planejamento "{rit.get_verbose_planejamento()}"'
        RegistroAcaoRelatorioIndividualTrabalho.objects.create(
            tipo=RegistroAcaoRelatorioIndividualTrabalho.TIPO_ADICIONOU_ATIVIDADE, rit=rit, rit_atividade=atividade_rit, ip=ip, observacao=ra_obs
        )

        # Pelo amor de deus deixe a URL mesmo e não o '..'
        return httprr(f'/pgd/visualizar_planejamento/{rit.id}/', 'Atividade adicionada com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('pgd.change_planoindividualtrabalho')
def editar_atividade_rit(request, atividade_rit_id):
    atividade_rit = get_object_or_404(RelatorioIndividualTrabalhoAtividade, pk=atividade_rit_id)

    # if atividade_rit.eh_espelho():
    #    atividade_rit = atividade_rit.original

    if not atividade_rit.pode_editar(request.user):
        raise PermissionDenied

    title = f'Editar Atividade {atividade_rit} do planejamento {atividade_rit.rit.get_verbose_planejamento()}'
    url = reverse('visualizar_planejamento', args=[atividade_rit.rit.id])

    atividade_rit_data_prazo = atividade_rit.data_prazo
    atividade_rit_tempo_planejado = atividade_rit.tempo_planejado
    atividade_rit_descricao = atividade_rit.descricao

    form = EditarAtividadeRitForm(request.POST or None, request=request, instance=atividade_rit)
    if form.is_valid():
        obj = form.save(False)

        # Se esta AUTORIZADO cria o espelho para conseguir cancelar edicao depois
        if obj.situacao == RelatorioIndividualTrabalhoAtividade.AUTORIZADO:
            RelatorioIndividualTrabalhoAtividade.objects.filter(original__id=obj.id).delete()
            espelho_obj = obj
            original = RelatorioIndividualTrabalhoAtividade.objects.get(id=obj.id)
            espelho_obj.id = None
            espelho_obj.situacao = RelatorioIndividualTrabalhoAtividade.CADASTRADO
            espelho_obj.aprovado = False
            espelho_obj.homologado = False
            espelho_obj.save()
            espelho_obj.original = original
            espelho_obj.save()
        else:
            obj.save()

        if (
            atividade_rit_data_prazo != atividade_rit.data_prazo
            or atividade_rit_tempo_planejado != atividade_rit.tempo_planejado
            or atividade_rit_descricao != atividade_rit.descricao
        ):
            ip = get_client_ip(request)
            ra_obs = (
                f'A atividade "{atividade_rit.atividade_pts.atividade}" foi editada no planejamento "{atividade_rit.rit.get_verbose_planejamento()}"'
            )
            RegistroAcaoRelatorioIndividualTrabalho.objects.create(
                tipo=RegistroAcaoRelatorioIndividualTrabalho.TIPO_EDITOU_ATIVIDADE,
                rit=atividade_rit.rit,
                ip=ip,
                rit_atividade=atividade_rit,
                observacao=ra_obs,
            )

        return httprr(url, 'Atividade editada com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('pgd.change_planoindividualtrabalho')
def remover_atividade_rit(request, atividade_rit_id):
    atividade_rit = get_object_or_404(RelatorioIndividualTrabalhoAtividade, pk=atividade_rit_id)
    if not atividade_rit.pode_remover(request.user):
        raise PermissionDenied

    url = reverse('visualizar_planejamento', args=[atividade_rit.rit.id])
    title = f'Remover Atividade {atividade_rit} do planejamento {atividade_rit.rit.get_verbose_planejamento()}'

    if atividade_rit.original:
        atividade_rit.delete()
        return httprr(url, 'Atividade removida com sucesso.')

    atividade_rit_str = str(atividade_rit.atividade_pts.atividade)

    form = JustificativaComSenhaForm(request.POST or None, request=request)
    if form.is_valid():
        atividade_rit.delete()

        ip = get_client_ip(request)
        justificativa = form.cleaned_data.get('justificativa')
        ra_obs = f'A atividade "{atividade_rit_str}" foi removida no planejamento "{atividade_rit.rit.get_verbose_planejamento()}" mediante a justificativa "{justificativa}"'
        RegistroAcaoRelatorioIndividualTrabalho.objects.create(
            tipo=RegistroAcaoRelatorioIndividualTrabalho.TIPO_REMOVEU_ATIVIDADE, rit=atividade_rit.rit, ip=ip, observacao=ra_obs
        )

        return httprr(url, 'Atividade removida com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('pgd.change_planoindividualtrabalho')
def cancelar_atividade_rit(request, atividade_rit_id):
    atividade_rit = get_object_or_404(RelatorioIndividualTrabalhoAtividade, pk=atividade_rit_id)
    if not atividade_rit.pode_cancelar(request.user):
        raise PermissionDenied

    title = f'Cancelar Atividade {atividade_rit} do {atividade_rit.rit.get_verbose_planejamento()}'
    url = reverse('visualizar_planejamento', args=[atividade_rit.rit.id])

    if atividade_rit.original:
        atividade_rit.delete()
        return httprr(url, 'Atividade cancelada com sucesso.')

    form = JustificativaComSenhaIrreverssivelForm(request.POST or None, request=request)
    if form.is_valid():
        atividade_rit.situacao = RelatorioIndividualTrabalhoAtividade.CANCELADO
        atividade_rit.save()

        # Se tiver entregas vinculadas vai cancelar também
        entregas_vinculadas = RelatorioIndividualTrabalhoAtividadeEntrega.objects.filter(rit_atividade=atividade_rit)
        for entrega_vinculada in entregas_vinculadas:
            entrega_vinculada.situacao = RelatorioIndividualTrabalhoAtividadeEntrega.CANCELADO
            entrega_vinculada.nota = None
            entrega_vinculada.tempo_executado_homologado = None
            entrega_vinculada.justificativa_observacao_avaliacao = None
            entrega_vinculada.aprovado = None
            entrega_vinculada.homologado = None
            entrega_vinculada.save()

        ip = get_client_ip(request)
        justificativa = form.cleaned_data.get('justificativa')
        ra_obs = f'A atividade "{atividade_rit.atividade_pts.atividade}" e suas entregas foram canceladas no planejamento "{atividade_rit.rit.get_verbose_planejamento()}" mediante a justificativa "{justificativa}"'
        RegistroAcaoRelatorioIndividualTrabalho.objects.create(
            tipo=RegistroAcaoRelatorioIndividualTrabalho.TIPO_CANCELOU_ATIVIDADE,
            rit=atividade_rit.rit,
            rit_atividade=atividade_rit,
            ip=ip,
            observacao=ra_obs,
        )

        return httprr(url, 'Atividade cancelada com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('pgd.change_planoindividualtrabalho')
def cancelar_espelho_atividade_rit(request, atividade_rit_id):
    # Cancelar edicao de uma atividade

    atividade_rit = get_object_or_404(RelatorioIndividualTrabalhoAtividade, pk=atividade_rit_id)
    if not atividade_rit.pode_cancelar(request.user):
        raise PermissionDenied

    url = reverse('visualizar_planejamento', args=[atividade_rit.rit.id])

    if atividade_rit.original:
        atividade_rit.delete()
    return httprr(url, 'Atividade cancelada com sucesso.')


@rtr()
@transaction.atomic
@permission_required('pgd.change_planoindividualtrabalho')
def copiar_planejamento(request, rit_id):
    # Apenas Servidor

    rit = get_object_or_404(RelatorioIndividualTrabalho, pk=rit_id)
    if not rit.pode_servidor_editar(request.user):
        raise PermissionDenied

    title = f'Copiar atividades de um Planejamento para o {rit.get_verbose_planejamento()}'

    adesao_vigente = rit.pit.adesao
    planejamentos_para_copiar = None
    if adesao_vigente:
        planejamentos_para_copiar = RelatorioIndividualTrabalho.get_rits_podem_ser_copiados(adesao_vigente, rit_alvo=rit).order_by('-id')
    else:
        raise PermissionDenied

    form = CopiarPlanejamentoForm(request.POST or None, planejamentos_para_copiar=planejamentos_para_copiar, request=request)
    if form.is_valid():
        planejamento_alvo = rit
        planejamento_copia = form.cleaned_data.get('planejamento_copia')
        atividades = planejamento_copia.get_atividades_podem_ser_copiadas_de_um_rit()
        atividades = atividades.exclude(atividade_pts__id__in=planejamento_alvo.get_atividades().values_list('atividade_pts__id', flat=True))

        # Copia as atividades
        for atividade in atividades:
            atividade_planejamento = RelatorioIndividualTrabalhoAtividade()
            atividade_planejamento.situacao = RelatorioIndividualTrabalhoAtividade.CADASTRADO
            atividade_planejamento.atividade_pts = atividade.atividade_pts
            atividade_planejamento.tempo_planejado = atividade.tempo_planejado
            atividade_planejamento.descricao = atividade.descricao
            atividade_planejamento.rit = planejamento_alvo
            atividade_planejamento.save()

        # Pelo amor de deus deixe a URL mesmo e não o '..'
        return httprr(f'/pgd/visualizar_planejamento/{rit.id}/', 'Atividade adicionada com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('pgd.change_planoindividualtrabalho')
def servidor_solicitar_aprovacao_pit_rit(request, rit_id):
    rit = get_object_or_404(RelatorioIndividualTrabalho, pk=rit_id)
    pit = rit.pit
    pit_id = rit.pit.id
    if not pit.pode_servidor_solicitar_aprovacao_pit_rit(request.user):
        raise PermissionDenied

    url = reverse('visualizar_planejamento', args=[rit.id])

    # Pode solicitar
    # ------------------------
    #   Se tem atividade que deve ser aprovada
    #   E se ao menos uma dessas atividades esta vinculada a um PTS ativo do servidor
    # - Essa regra iniciamente estava em "pode_servidor_solicitar_aprovacao_pit_rit"
    # - Essa regra foi colocada aqui para que esse motivo seja mostrado em tela para o usuario
    atividades_pendente_analise = RelatorioIndividualTrabalhoAtividade.objects.filter(
        rit__pit=pit, situacao__in=[RelatorioIndividualTrabalhoAtividade.CADASTRADO]
    )
    atividades_autorizadas = pit.get_atividades_autorizadas()
    existe_atividade_com_pts_inativo = False
    for apa in atividades_pendente_analise:
        if not apa.atividade_estah_vinculada_a_adesao_pts_vigente_do_servidor():
            existe_atividade_com_pts_inativo = True
            break
    if not existe_atividade_com_pts_inativo:
        for at in atividades_autorizadas:
            if not at.atividade_estah_vinculada_a_adesao_pts_vigente_do_servidor():
                existe_atividade_com_pts_inativo = True
                break
    if existe_atividade_com_pts_inativo:
        return httprr(
            url,
            'Impossível solicitar Aprovação se uma das atividades estiver relacionada um PTS em que o Servidor não estiver com adesão válida.',
            tag='error',
        )

    # Não pode haver nenhuma atividade que tenha prazo desalinhado com o periodo do PIT
    # ------------------------
    existe_atividade_prazo_desalinhado_com_periodo_pit = False
    for apa in atividades_pendente_analise:
        if not apa.atividade_estah_com_prazo_alinhado_com_periodo_pit():
            existe_atividade_prazo_desalinhado_com_periodo_pit = True
            break
    if not existe_atividade_prazo_desalinhado_com_periodo_pit:
        for at in atividades_autorizadas:
            if not at.atividade_estah_com_prazo_alinhado_com_periodo_pit():
                existe_atividade_prazo_desalinhado_com_periodo_pit = True
                break
    if existe_atividade_prazo_desalinhado_com_periodo_pit:
        return httprr(url, 'Impossível solicitar Aprovação se uma das atividades estiver com prazo em desacordo com o período do PIT.', tag='error')

    title = f'Solicitar Aprovação do {pit}'

    form = JustificativaComSenhaForm(request.POST or None, request=request)
    if form.is_valid():
        # ======================================
        # REGRAS DO PONTO
        # ======================================
        lista_pendencias_ponto = []
        if pit.deve_verificar_ponto():
            servidor = pit.adesao.servidor
            ontem = get_datetime_now().date() - relativedelta(days=1)
            # Compensacoes especificas
            # -------------------
            q_rpc = RecessoPeriodoCompensacao.objects.filter(data_inicial__lte=ontem, data_final__gte=ontem).distinct('recesso_opcao')
            recesso_servidor = RecessoOpcaoEscolhida.objects.filter(
                funcionario=servidor,
                recesso_opcao__id__in=q_rpc.values_list('recesso_opcao_id', flat=True),
                validacao=RecessoOpcaoEscolhida.VALIDACAO_AUTORIZADO,
            )
            for es in recesso_servidor:
                dias = es.dias_efetivos_a_compensar()
                if dias and ontem > dias[-1]:
                    total = es.totais_ch(carga_horaria_pendente=True)['total_carga_horaria_pendente']
                    if total:
                        total_formatado = formata_segundos(total, '{h:02.0f}h ', '{m:02.0f}min ', '{s:02.0f}seg ', True)
                        lista_pendencias_ponto.append(
                            f'Não é possível solicitar aprovação pois o recesso "{es.recesso_opcao!s}" está com débito de: {total_formatado}. Acesse "https://suap.ifrn.edu.br/admin/ponto/recessoopcaoescolhida/" para mais informações.'
                        )
            # Se o ponto anterior está ok
            # -------------------
            # Ontem
            ontem = get_datetime_now().date() - relativedelta(days=1)
            data_inicial_pit = pit.data_inicial - relativedelta(days=1)
            data_fim = min(ontem, data_inicial_pit)
            # Primeiro dia do mês passado
            mes_passado = get_datetime_now().date() - relativedelta(months=1)
            data_ini = datetime.date(mes_passado.year, mes_passado.month, 1)

            ponto = Frequencia.relatorio_ponto_pessoa_novo(
                vinculo=servidor.get_vinculo(), servidor_logado=servidor, data_ini=data_ini, data_fim=data_fim, escopo='todos'
            )

            total_debito = ponto.get('totais_compensacao').get('total_debito_pendente')
            if total_debito != '0h 0min 0seg':
                link_ponto = f'<a href="/ponto/frequencia_funcionario/?funcionario={servidor.id}&faixa_0={data_ini!s}&faixa_1={data_fim!s}">relatório de ponto aqui</a>'
                lista_pendencias_ponto.append(
                    mark_safe(
                        f'O Servidor não pode ter débitos no ponto. <strong>Para conferir seu débito de "{total_debito}" acesse o {link_ponto}.</strong>'
                    )
                )

            # Se tiver erro mostra os erros
            # -------------------
            if lista_pendencias_ponto:
                messages.error(request, mark_safe('</br>'.join(lista_pendencias_ponto)))
                return httprr(url)

            # Marca quando o ponto foi verificado
            # -------------------
            pit.data_verificacao_ponto = get_datetime_now()
            pit.save()

        # ======================================

        pit.situacao = PlanoIndividualTrabalho.AGUARDANDO_PARECER
        pit.save()

        ip = get_client_ip(request)
        justificativa = form.cleaned_data.get('justificativa')
        ra_obs = f'Foi solicitado aprovação/homologação do "{pit}" mediante a justificativa "{justificativa}"'
        RegistroAcaoPlanoIndividualTrabalho.objects.create(
            tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_SERVIDOR_SOLICITOU_APROVACAO_HOMOLOGACAO, pit=pit, ip=ip, observacao=ra_obs
        )
        return httprr(url, 'Aprovação/homologação solicitada com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@login_required
def chefe_aprova_homologa_pit_rit(request, pit_id):
    pit = get_object_or_404(PlanoIndividualTrabalho, pk=pit_id)
    if not pit.pode_aprovar_homologar_pit_rit(request.user):
        raise PermissionDenied

    url = '/admin/pgd/planoindividualtrabalho/'
    url_erro = f'/pgd/visualizar_chefe_plano_individual_trabalho/{pit_id}'

    setores_sou_chefe_hoje = setores_que_sou_chefe_hoje(request.user.get_relacionamento())

    # Se pode APENAS HOMOLOGAR O PLANEJAMENTO
    pode_chefe_autorizar_pit_planejamento = pit.pode_chefe_autorizar_pit_planejamento(request.user, setores_chefe_hoje=setores_sou_chefe_hoje)
    depois_pode_chefe_autorizar_pit_planejamento = pit.pode_chefe_autorizar_pit_planejamento(
        request.user, setores_chefe_hoje=setores_sou_chefe_hoje, depois=True
    )
    # Se pode APENAS AUTORIZAR ALGUMA ATIVIDADE
    pode_chefe_autorizar_alguma_atividade, ids_atividades_pode = pit.pode_chefe_autorizar_atividades(
        request.user, setores_chefe_hoje=setores_sou_chefe_hoje
    )

    pode_aprovar_homologar_pit_rit = pit.pode_aprovar_homologar_pit_rit(request.user) and (
        pode_chefe_autorizar_pit_planejamento or pode_chefe_autorizar_alguma_atividade
    )
    if not pode_aprovar_homologar_pit_rit:
        raise PermissionDenied

    # Pode homologar
    #   Se nao tiver uma atividade relacionada a um PTS sem adesao valida
    # - Essa regra iniciamente estava em "pode_aprovar_homologar_pit_rit"
    # - Essa regra foi colocada aqui para que esse motivo seja mostrado em tela para o usuario
    atividades_a_aprovar_do_pit = pit.get_atividades_a_aprovar_do_pit()
    atividades_autorizadas = pit.get_atividades_autorizadas()
    existe_atividade_com_pts_inativo = False
    for at in atividades_a_aprovar_do_pit:
        if not at.atividade_estah_vinculada_a_adesao_pts_vigente_do_servidor():
            existe_atividade_com_pts_inativo = True
            break
    for at in atividades_autorizadas:
        if not at.atividade_estah_vinculada_a_adesao_pts_vigente_do_servidor():
            existe_atividade_com_pts_inativo = True
            break
    if existe_atividade_com_pts_inativo:
        return httprr(
            url_erro,
            'Impossível Aprovar/Homologar se uma das atividades estiver relacionada um PTS em que o Servidor não estiver com adesão válida.',
            tag='error',
        )

    title = f'Aprovar/Homologar {pit}'

    form = JustificativaComSenhaForm(request.POST or None, request=request)
    if form.is_valid():
        setores_sou_chefe_hoje = setores_que_sou_chefe_hoje(request.user.get_relacionamento())
        ip = get_client_ip(request)

        # Se pode APENAS AUTORIZAR ALGUMA ATIVIDADE
        pode_chefe_autorizar_alguma_atividade, ids_atividades_pode = pit.pode_chefe_autorizar_atividades(
            request.user, setores_chefe_hoje=setores_sou_chefe_hoje
        )
        if pode_chefe_autorizar_alguma_atividade:
            for at in atividades_a_aprovar_do_pit:
                if at.id in ids_atividades_pode:
                    if at.eh_espelho():
                        # Se ela for um espelho
                        # - A original recebe seus dados
                        # - A original fica como aprov/homol
                        # - Salva a original
                        # - Delete o espelho
                        original = at.original
                        original.data_prazo = at.data_prazo
                        original.tempo_planejado = at.tempo_planejado
                        original.descricao = at.descricao
                        original.save()
                        at.delete()

                        ra_obs = f'A atividade "{original}" foi Aprovado/Homologado'
                        RegistroAcaoRelatorioIndividualTrabalho.objects.create(
                            tipo=RegistroAcaoRelatorioIndividualTrabalho.TIPO_APROVOU_HOMOLOGOU_ATIVIDADE,
                            rit=original.rit,
                            rit_atividade=original,
                            ip=ip,
                            observacao=ra_obs,
                        )
                    else:
                        at.situacao = RelatorioIndividualTrabalhoAtividade.AUTORIZADO
                        at.save()

                        ra_obs = f'A atividade "{at}" foi Aprovado/Homologado'
                        RegistroAcaoRelatorioIndividualTrabalho.objects.create(
                            tipo=RegistroAcaoRelatorioIndividualTrabalho.TIPO_APROVOU_HOMOLOGOU_ATIVIDADE,
                            rit=at.rit,
                            rit_atividade=at,
                            ip=ip,
                            observacao=ra_obs,
                        )

        # Autorizando o planejamento
        # Se pode APENAS HOMOLOGAR O PLANEJAMENTO
        pode_chefe_autorizar_pit_planejamento = pit.pode_chefe_autorizar_pit_planejamento(request.user, setores_chefe_hoje=setores_sou_chefe_hoje)
        if pode_chefe_autorizar_pit_planejamento:
            pit.situacao = PlanoIndividualTrabalho.AUTORIZADO
            pit.save()

            justificativa = form.cleaned_data.get('justificativa')
            ra_obs = f'O "{pit}" foi Aprovado/Homologado mediante a justificativa "{justificativa}"'
            RegistroAcaoPlanoIndividualTrabalho.objects.create(
                tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_CHEFE_APROVOU_HOMOLOGOU, pit=pit, ip=ip, observacao=ra_obs
            )

        return httprr(url, 'Aprovação/homologação cadastrada com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@login_required
def chefe_nao_aprova_homologa_pit_rit(request, pit_id):
    pit = get_object_or_404(PlanoIndividualTrabalho, pk=pit_id)
    if not pit.pode_aprovar_homologar_pit_rit(request.user):
        raise PermissionDenied

    url = '/admin/pgd/planoindividualtrabalho/'
    url_erro = f'/pgd/visualizar_chefe_plano_individual_trabalho/{pit_id}'

    setores_sou_chefe_hoje = setores_que_sou_chefe_hoje(request.user.get_relacionamento())
    # Se pode APENAS HOMOLOGAR O PLANEJAMENTO
    pode_chefe_autorizar_pit_planejamento = pit.pode_chefe_autorizar_pit_planejamento(request.user, setores_chefe_hoje=setores_sou_chefe_hoje)
    depois_pode_chefe_autorizar_pit_planejamento = pit.pode_chefe_autorizar_pit_planejamento(
        request.user, setores_chefe_hoje=setores_sou_chefe_hoje, depois=True
    )
    # Se pode APENAS AUTORIZAR ALGUMA ATIVIDADE
    pode_chefe_autorizar_alguma_atividade, ids_atividades_pode = pit.pode_chefe_autorizar_atividades(
        request.user, setores_chefe_hoje=setores_sou_chefe_hoje
    )

    pode_aprovar_homologar_pit_rit = pit.pode_aprovar_homologar_pit_rit(request.user) and (
        pode_chefe_autorizar_pit_planejamento or pode_chefe_autorizar_alguma_atividade
    )
    if not pode_aprovar_homologar_pit_rit:
        raise PermissionDenied

    title = f'Não Aprovar/Homologar {pit}'

    form = JustificativaComSenhaForm(request.POST or None, request=request)
    if form.is_valid():
        pit.situacao = PlanoIndividualTrabalho.CADASTRADO
        pit.save()

        RelatorioIndividualTrabalhoAtividade.objects.filter(rit__pit=pit, original__isnull=False).delete()

        ip = get_client_ip(request)
        justificativa = form.cleaned_data.get('justificativa')
        ra_obs = f'O "{pit}" não foi Aprovado/Homologado mediante a justificativa "{justificativa}"'
        RegistroAcaoPlanoIndividualTrabalho.objects.create(
            tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_CHEFE_NAO_APROVOU_HOMOLOGOU, pit=pit, ip=ip, observacao=ra_obs
        )
        return httprr(url, 'Não Aprovação/homologação cadastrada com sucesso.')

    return locals()


# ====================================================
# PIT - RIT - Execucao - Entregas
# ====================================================


@rtr()
@transaction.atomic
@login_required()
def cadastrar_entrega_rit(request, rit_id, rit_atividade_id):
    rit = get_object_or_404(RelatorioIndividualTrabalho, pk=rit_id)
    rit_atividade = get_object_or_404(RelatorioIndividualTrabalhoAtividade, pk=rit_atividade_id)

    if not RelatorioIndividualTrabalhoAtividadeEntrega.pode_cadastrar(request.user, rit_atividade):
        raise PermissionDenied('Você não pode cadastrar entrega para essa atividade no RIT.')

    if rit_atividade_id not in rit.get_atividades_pode_receber_entregas().values_list('id', flat=True):
        raise PermissionDenied('Esta atividade não pode receber entregas em seu RIT.')

    title = f'Cadastrar entrega para o {rit.get_verbose_rit()} - Atividade {rit_atividade.atividade_pts!s}'
    perfil = request.GET.get('p')
    tipo_url = (
        'relatorioindividualtrabalhoatividadeentregacheferegistrar'
        if perfil == 'chefe'
        else 'relatorioindividualtrabalhoatividadeentregaservidorregistrar'
    )
    url = f'/admin/pgd/{tipo_url}/?rit_atividade__rit={rit.id}'
    form = CadastrarEntregaForm(request.POST or None, request.FILES or None, request=request, rit_atividade=rit_atividade)
    if form.is_valid():
        entrega = form.save()

        ip = get_client_ip(request)
        ra_obs = f'A entrega "{entrega}" foi adicionada ao RIT "{rit.get_verbose_rit()}"'
        RegistroAcaoRelatorioIndividualTrabalho.objects.create(
            tipo=RegistroAcaoRelatorioIndividualTrabalho.TIPO_CADASTROU_ENTREGA,
            rit=rit,
            rit_atividade=rit_atividade,
            rit_atividade_entrega=entrega,
            ip=ip,
            observacao=ra_obs,
        )

        rit.pit.calcular_pit(forcar_recalcular_tempo_previsto=True)
        return httprr('..', 'Entrega adicionada com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@login_required()
def alterar_entrega_rit(request, rit_atividade_entrega_id):
    rit_atividade_entrega = get_object_or_404(RelatorioIndividualTrabalhoAtividadeEntrega, pk=rit_atividade_entrega_id)
    rit = rit_atividade_entrega.rit_atividade.rit

    if not rit_atividade_entrega.pode_editar(request.user):
        raise PermissionDenied

    if rit_atividade_entrega.rit_atividade.id not in rit.get_atividades_pode_receber_entregas().values_list('id', flat=True):
        raise PermissionDenied

    title = f'Editar entrega para o {rit.get_verbose_rit()} - Atividade {rit_atividade_entrega!s}'

    perfil = request.GET.get('p')
    url = f'/admin/pgd/relatorioindividualtrabalhoatividadeentregaservidorregistrar/?rit_atividade__rit={rit.id}'
    if perfil == 'chefe':
        url = f'/admin/pgd/relatorioindividualtrabalhoatividadeentregacheferegistrar/?rit_atividade__rit={rit.id}'

    form = EditarEntregaForm(request.POST or None, request.FILES or None, request=request, instance=rit_atividade_entrega)
    if form.is_valid():
        form.save()

        ip = get_client_ip(request)
        ra_obs = f'A entrega "{rit_atividade_entrega}" foi alterada no rit "{rit.get_verbose_rit()}"'
        RegistroAcaoRelatorioIndividualTrabalho.objects.create(
            tipo=RegistroAcaoRelatorioIndividualTrabalho.TIPO_ALTEROU_ENTREGA,
            rit=rit,
            rit_atividade=rit_atividade_entrega.rit_atividade,
            rit_atividade_entrega=rit_atividade_entrega,
            ip=ip,
            observacao=ra_obs,
        )

        rit.pit.calcular_pit(forcar_recalcular_tempo_previsto=True)
        return httprr(url, 'Entrega atualizada com sucesso.')

    return locals()


@rtr()
@login_required()
def visualizar_entrega_rit(request, rit_atividade_entrega_id):
    rit_entrega = get_object_or_404(RelatorioIndividualTrabalhoAtividadeEntrega, pk=rit_atividade_entrega_id)

    if not rit_entrega.pode_visualizar(request.user):
        raise PermissionDenied

    rit_entrega.calcular_entrega()
    rit_entrega.save()
    rit_entrega = RelatorioIndividualTrabalhoAtividadeEntrega.objects.get(pk=rit_atividade_entrega_id)

    title = f'Visualizar Entrega {rit_entrega!s}'

    rit = rit_entrega.rit_atividade.rit

    return locals()


@rtr()
@transaction.atomic
@login_required
def remover_entrega_rit(request, rit_atividade_entrega_id):
    rit_atividade_entrega = get_object_or_404(RelatorioIndividualTrabalhoAtividadeEntrega, pk=rit_atividade_entrega_id)
    rit = rit_atividade_entrega.rit_atividade.rit
    rit_atividade = rit_atividade_entrega.rit_atividade

    if not rit_atividade_entrega.pode_remover(request.user):
        raise PermissionDenied

    perfil = request.GET.get('p')
    url = f'/admin/pgd/relatorioindividualtrabalhoatividadeentregaservidorregistrar/?rit_atividade__rit={rit.id}'
    if perfil == 'chefe':
        url = f'/admin/pgd/relatorioindividualtrabalhoatividadeentregacheferegistrar/?rit_atividade__rit={rit.id}'

    str_entrega = str(rit_atividade_entrega)

    rit_atividade_entrega.delete()

    ip = get_client_ip(request)
    ra_obs = f'A entrega "{str_entrega}" foi removida do rit "{rit.get_verbose_rit()}"'
    RegistroAcaoRelatorioIndividualTrabalho.objects.create(
        tipo=RegistroAcaoRelatorioIndividualTrabalho.TIPO_REMOVEU_ENTREGA,
        rit=rit,
        rit_atividade=rit_atividade,
        rit_atividade_entrega=None,
        ip=ip,
        observacao=ra_obs,
    )

    return httprr(url, 'Entrega removida com sucesso.')


"""
@rtr()
@transaction.atomic
@permission_required('pgd.change_relatorioindividualtrabalhoatividadeentrega')
def servidor_operacoes_entrega_rit(request):

    rit = get_object_or_404(RelatorioIndividualTrabalho, pk=request.GET.get('rit_id'))
    url = reverse('visualizar_rit', args=[rit.id])

    user = request.user

    # Valida a action
    # --------------------------------
    if not request.GET.get('servidor_entregar_entrega') and not request.GET.get('servidor_reverter_entrega_entregue'):
        raise PermissionDenied()
    action_executada = False
    action_a_ser_executada = None
    if request.GET.get('servidor_entregar_entrega'):
        action_a_ser_executada = 'servidor_entregar_entrega'
        title = f'Registrar entregas para o {rit.get_verbose_rit()}'
    elif request.GET.get('servidor_reverter_entrega_entregue'):
        action_a_ser_executada = 'servidor_reverter_entrega_entregue'
        title = f'Reverter entregas para o {rit.get_verbose_rit()}'

    # Pega as entregas selecionadas
    # --------------------------------
    entregas_ids = request.GET.getlist('checks[]')
    if not entregas_ids:
        return httprr(url, 'Deve selecionar alguma entrega.', tag='error')
    if entregas_ids[0] == 'on':
        entregas_ids = entregas_ids[1:]
    if not entregas_ids:
        return httprr(url, 'Deve selecionar alguma entrega.', tag='error')
    entregas = RelatorioIndividualTrabalhoAtividadeEntrega.objects.filter(id__in=entregas_ids)
    if len(entregas) != len(entregas_ids):
        raise PermissionDenied()

    # Valida se todas as entregas sao da mesma adesao
    # --------------------------------
    if len(entregas.distinct('rit_atividade__rit__pit__adesao')) > 1:
        return httprr(url, 'As entregas selecionadas devem ser mesma adesão ao PGD.', tag='error')

    # ---------------------------------------------------
    # Se for "servidor_entregar_entrega"
    # ---------------------------------------------------
    if action_a_ser_executada == 'servidor_entregar_entrega':

        form = JustificativaComSenhaForm(request.POST or None, request=request)
        if form.is_valid():

            # Verifica se cada uma pode ser entregue
            # Pega as entregas que podem ser entregues
            # Pega as entregas que nao podem ser entregues
            # --------------------------------
            entregas_podem_ser_entregue = list()
            entregas_nao_podem_ser_entregue = list()
            for entrega in entregas:
                if entrega.pode_entregar(user):
                    entregas_podem_ser_entregue.append(entrega)
                else:
                    entregas_nao_podem_ser_entregue.append(entrega)

            # Critica se nenhuma das selecionadas pode ser entregue
            # --------------------------------
            if not entregas_podem_ser_entregue:
                return httprr(url, 'Nenhuma entrega pode ser entregue.', tag='error')

            # Realiza a operacao
            # ---------------------------------------------------
            for entrega in entregas_podem_ser_entregue:
                entrega.situacao = RelatorioIndividualTrabalhoAtividadeEntrega.ENTREGUE
                entrega.save()

                ip = get_client_ip(request)
                justificativa = form.cleaned_data.get('justificativa')
                ra_obs = f'A entrega "{str(entrega)}" do rit "{rit.get_verbose_rit()}" foi entregue mediante seguinte justificativa/observação "{justificativa}"'
                RegistroAcaoRelatorioIndividualTrabalho.objects.create(tipo=RegistroAcaoRelatorioIndividualTrabalho.TIPO_ENTREGOU_ENTREGA,
                                                                       rit=rit,
                                                                       rit_atividade=entrega.rit_atividade,
                                                                       rit_atividade_entrega=entrega,
                                                                       ip=ip, observacao=ra_obs)
            if entregas_nao_podem_ser_entregue:
                messages.success(request, 'Algumas entregas foram realizadas com sucesso.')
                messages.error(request, 'Algumas entregas não puderam ser relizadas')
            else:
                messages.success(request, 'Entregas realizadas com sucesso.')

            action_executada = True

    # ---------------------------------------------------
    # Se for "servidor_reverter_entrega_entregue"
    # ---------------------------------------------------
    if action_a_ser_executada == 'servidor_reverter_entrega_entregue':

        form = JustificativaComSenhaForm(request.POST or None, request=request)
        if form.is_valid():

            # Verifica se cada uma pode ser revertida
            # Pega as entregas que podem ser revertidas
            # Pega as entregas que nao podem ser revertidas
            # --------------------------------
            entregas_podem_ser_revertida = list()
            entregas_nao_podem_ser_revertida = list()
            for entrega in entregas:
                if entrega.pode_reverter_entrega(user):
                    entregas_podem_ser_revertida.append(entrega)
                else:
                    entregas_nao_podem_ser_revertida.append(entrega)

            # Critica se nenhuma das selecionadas pode ser revertida
            # --------------------------------
            if not entregas_podem_ser_revertida:
                return httprr(url, 'Nenhuma entrega pode ser revertida.', tag='error')

            # Realiza a operacao
            # ---------------------------------------------------
            for entrega in entregas_podem_ser_revertida:
                entrega.situacao = RelatorioIndividualTrabalhoAtividadeEntrega.CADASTRADO
                entrega.nota = None
                entrega.tempo_executado_homologado = None
                entrega.justificativa_observacao_avaliacao = None
                entrega.aprovado = None
                entrega.homologado = None
                entrega.save()

                ip = get_client_ip(request)
                justificativa = form.cleaned_data.get('justificativa')
                ra_obs = f'A entrega "{str(entrega)}" do rit "{rit.get_verbose_rit()}" foi revertida mediante seguinte justificativa/observação "{justificativa}"'
                RegistroAcaoRelatorioIndividualTrabalho.objects.create(tipo=RegistroAcaoRelatorioIndividualTrabalho.TIPO_REVERTEU_ENTREGA,
                                                                       rit=rit,
                                                                       rit_atividade=entrega.rit_atividade,
                                                                       rit_atividade_entrega=entrega,
                                                                       ip=ip, observacao=ra_obs)
            if entregas_nao_podem_ser_revertida:
                messages.success(request, 'Algumas entregas foram revertidas com sucesso.')
                messages.error(request, 'Algumas entregas não puderam ser revertidas')
            else:
                messages.success(request, 'Entregas revertidas com sucesso.')

            action_executada = True




    return locals()

"""


@rtr()
@transaction.atomic
@permission_required('pgd.change_relatorioindividualtrabalhoatividadeentrega')
def servidor_chefe_operacoes_entrega_rit(request):
    # Operações
    # - Entregar Entrega
    # - Reverter Entrega
    # - Remover Entrega
    # - Avaliar Entrega

    rit = get_object_or_404(RelatorioIndividualTrabalho, pk=request.GET.get('rit_id'))
    user = request.user
    perfil = request.GET.get('p')
    form = None

    # Valida a action
    # --------------------------------
    if not request.GET.get('action') or request.GET.get('action') not in [
        'entregar_entrega',
        'reverter_entrega_entregue',
        'remover_entrega',
        'avaliar_entrega',
    ]:
        raise PermissionDenied
    action_executada = False
    action_a_ser_executada = request.GET.get('action')
    title_box_selecionadas = 'Selecionadas'
    if action_a_ser_executada == 'entregar_entrega':
        title = f'Registrar entregas para o {rit.get_verbose_rit()}'
        title_box_foram_operadas = 'Entregues'
        title_box_nao_foram_operadas = 'Não entregues'
    elif action_a_ser_executada == 'reverter_entrega_entregue':
        title = f'Reverter entregas para o {rit.get_verbose_rit()}'
        title_box_foram_operadas = 'Revertidas'
        title_box_nao_foram_operadas = 'Não revertidas'
    elif action_a_ser_executada == 'remover_entrega':
        title = f'Remover entregas para o {rit.get_verbose_rit()}'
        title_box_foram_operadas = 'Removidas'
        title_box_nao_foram_operadas = 'Não removidas'
    elif action_a_ser_executada == 'avaliar_entrega':
        title = f'Avaliar entregas para o {rit.get_verbose_rit()}'
        title_box_foram_operadas = 'Avaliadas'
        title_box_nao_foram_operadas = 'Não avaliadas'

    # URL de retorno
    # --------------------------------
    url = f'/admin/pgd/relatorioindividualtrabalhoatividadeentregaservidorregistrar/?rit_atividade__rit={rit.id}'
    if perfil == 'chefe':
        url = f'/admin/pgd/relatorioindividualtrabalhoatividadeentregacheferegistrar/?rit_atividade__rit={rit.id}'
        if action_a_ser_executada == 'avaliar_entrega':
            url = f'/admin/pgd/relatorioindividualtrabalhoatividadeentregaavaliar/?rit_atividade__rit={rit.id}'

    # Pega as entregas selecionadas
    # --------------------------------
    entregas_ids = request.GET.getlist('checks')
    if not entregas_ids or '' in entregas_ids:
        return httprr(url, 'Deve selecionar alguma entrega.', tag='error')
    entregas = RelatorioIndividualTrabalhoAtividadeEntrega.objects.filter(id__in=entregas_ids)
    if len(entregas) != len(entregas_ids):
        raise PermissionDenied

    # Valida se todas as entregas sao da mesma adesao
    # --------------------------------
    if len(entregas.distinct('rit_atividade__rit__pit__adesao')) > 1:
        return httprr(url, 'As entregas selecionadas devem ser mesma adesão ao PGD.', tag='error')

    # ---------------------------------------------------
    # Se for "entregar_entrega"
    # ---------------------------------------------------
    if action_a_ser_executada == 'entregar_entrega':
        form = JustificativaComSenhaForm(request.POST or None, request=request)
        if form.is_valid():
            # Verifica se cada uma pode ser entregue
            # Pega as entregas que podem ser entregues
            # Pega as entregas que nao podem ser entregues
            # --------------------------------
            entregas_podem_ser_operadas = []
            entregas_nao_podem_ser_operadas = []
            for entrega in entregas:
                if entrega.pode_entregar(user):
                    entregas_podem_ser_operadas.append(entrega)
                else:
                    entregas_nao_podem_ser_operadas.append(entrega)

            # Critica se nenhuma das selecionadas pode ser entregue
            # --------------------------------
            if not entregas_podem_ser_operadas:
                return httprr(url, 'Nenhuma entrega pode ser entregue.', tag='error')

            # Realiza a operacao
            # ---------------------------------------------------
            for entrega in entregas_podem_ser_operadas:
                entrega.situacao = RelatorioIndividualTrabalhoAtividadeEntrega.ENTREGUE
                entrega.save()

                ip = get_client_ip(request)
                justificativa = form.cleaned_data.get('justificativa')
                ra_obs = f'A entrega "{entrega!s}" do rit "{rit.get_verbose_rit()}" foi entregue mediante seguinte justificativa/observação "{justificativa}"'
                RegistroAcaoRelatorioIndividualTrabalho.objects.create(
                    tipo=RegistroAcaoRelatorioIndividualTrabalho.TIPO_ENTREGOU_ENTREGA,
                    rit=rit,
                    rit_atividade=entrega.rit_atividade,
                    rit_atividade_entrega=entrega,
                    ip=ip,
                    observacao=ra_obs,
                )
            if entregas_nao_podem_ser_operadas:
                messages.success(request, 'Algumas entregas foram realizadas com sucesso.')
                messages.error(request, 'Algumas entregas não puderam ser relizadas')
            else:
                messages.success(request, 'Entregas realizadas com sucesso.')

            action_executada = True

    # ---------------------------------------------------
    # Se for "reverter_entrega_entregue"
    # ---------------------------------------------------
    if action_a_ser_executada == 'reverter_entrega_entregue':
        form = JustificativaComSenhaForm(request.POST or None, request=request)
        if form.is_valid():
            # Verifica se cada uma pode ser revertida
            # Pega as entregas que podem ser revertidas
            # Pega as entregas que nao podem ser revertidas
            # --------------------------------
            entregas_podem_ser_operadas = []
            entregas_nao_podem_ser_operadas = []
            for entrega in entregas:
                if entrega.pode_reverter_entrega(user):
                    entregas_podem_ser_operadas.append(entrega)
                else:
                    entregas_nao_podem_ser_operadas.append(entrega)

            # Critica se nenhuma das selecionadas pode ser revertida
            # --------------------------------
            if not entregas_podem_ser_operadas:
                return httprr(url, 'Nenhuma entrega pode ser revertida.', tag='error')

            # Realiza a operacao
            # ---------------------------------------------------
            for entrega in entregas_podem_ser_operadas:
                entrega.situacao = RelatorioIndividualTrabalhoAtividadeEntrega.CADASTRADO
                entrega.nota = None
                entrega.tempo_executado_homologado = None
                entrega.justificativa_observacao_avaliacao = None
                entrega.aprovado = None
                entrega.homologado = None
                entrega.save()

                ip = get_client_ip(request)
                justificativa = form.cleaned_data.get('justificativa')
                ra_obs = f'A entrega "{entrega!s}" do rit "{rit.get_verbose_rit()}" foi revertida mediante seguinte justificativa/observação "{justificativa}"'
                RegistroAcaoRelatorioIndividualTrabalho.objects.create(
                    tipo=RegistroAcaoRelatorioIndividualTrabalho.TIPO_REVERTEU_ENTREGA,
                    rit=rit,
                    rit_atividade=entrega.rit_atividade,
                    rit_atividade_entrega=entrega,
                    ip=ip,
                    observacao=ra_obs,
                )
            if entregas_nao_podem_ser_operadas:
                messages.success(request, 'Algumas entregas foram revertidas com sucesso.')
                messages.error(request, 'Algumas entregas não puderam ser revertidas')
            else:
                messages.success(request, 'Entregas revertidas com sucesso.')

            action_executada = True

    # ---------------------------------------------------
    # Se for "remover_entrega"
    # ---------------------------------------------------
    if action_a_ser_executada == 'remover_entrega':
        form = JustificativaComSenhaForm(request.POST or None, request=request)
        if form.is_valid():
            # Verifica se cada uma pode ser removida
            # Pega as entregas que podem ser removidas
            # Pega as entregas que nao podem ser removidas
            # --------------------------------
            entregas_podem_ser_operadas = []
            entregas_nao_podem_ser_operadas = []
            for entrega in entregas:
                if entrega.pode_remover(user):
                    entregas_podem_ser_operadas.append(entrega)
                else:
                    entregas_nao_podem_ser_operadas.append(entrega)

            # Critica se nenhuma das selecionadas pode ser removida
            # --------------------------------
            if not entregas_podem_ser_operadas:
                return httprr(url, 'Nenhuma entrega pode ser removida.', tag='error')

            # Realiza a operacao
            # ---------------------------------------------------
            for entrega in entregas_podem_ser_operadas:
                str_entrega = str(entrega)
                rit_atividade = entrega.rit_atividade
                entrega.delete()
                ip = get_client_ip(request)
                ra_obs = f'A entrega "{str_entrega}" foi removida do rit "{rit.get_verbose_rit()}"'
                RegistroAcaoRelatorioIndividualTrabalho.objects.create(
                    tipo=RegistroAcaoRelatorioIndividualTrabalho.TIPO_REMOVEU_ENTREGA,
                    rit=rit,
                    rit_atividade=rit_atividade,
                    rit_atividade_entrega=None,
                    ip=ip,
                    observacao=ra_obs,
                )

            if entregas_nao_podem_ser_operadas:
                messages.success(request, 'Algumas entregas foram removidas com sucesso.')
                messages.error(request, 'Algumas entregas não puderam ser removidas')
            else:
                messages.success(request, 'Entregas removidas com sucesso.')

            action_executada = True

    # ---------------------------------------------------
    # Se for "avaliar_entrega"
    # ---------------------------------------------------
    if action_a_ser_executada == 'avaliar_entrega':
        lista_setores_user_eh_chefe_hoje = setores_que_sou_chefe_hoje(request.user.get_relacionamento())
        pode_avaliar_entregas_rit = rit.pode_avaliar_entregas_rit(request.user, lista_setores_user_eh_chefe_hoje=lista_setores_user_eh_chefe_hoje)
        if not pode_avaliar_entregas_rit:
            messages.error(request, 'Algumas entregas não puderam ser avaliadas')
            action_executada = False

        if pode_avaliar_entregas_rit:
            form = RelatorioIndividualTrabalhoAtividadeEntregaAvaliarSimplesForm(request.POST or None, request=request)
            if form.is_valid():
                # Verifica se cada uma pode ser avaliada
                # Pega as entregas que podem ser avaliada
                # Pega as entregas que nao podem ser avaliada
                # --------------------------------
                entregas_podem_ser_operadas = []
                entregas_nao_podem_ser_operadas = []
                for entrega in entregas:
                    if entrega.pode_avaliar(
                        user,
                        lista_setores_user_eh_chefe_hoje=lista_setores_user_eh_chefe_hoje,
                        user_pode_avaliar_entregas_rit=pode_avaliar_entregas_rit,
                    ):
                        entregas_podem_ser_operadas.append(entrega)
                    else:
                        entregas_nao_podem_ser_operadas.append(entrega)

                # Critica se nenhuma das selecionadas pode ser avaliada
                # --------------------------------
                if not entregas_podem_ser_operadas:
                    return httprr(url, 'Nenhuma entrega pode ser avaliada.', tag='error')

                # Realiza a operacao
                # ---------------------------------------------------
                for entrega in entregas_podem_ser_operadas:
                    str_entrega = str(entrega)
                    rit_atividade = entrega.rit_atividade

                    # Avalia a entrega
                    # --------------------------------------
                    entrega.tempo_executado_homologado = entrega.tempo_executado
                    entrega.nota = form.cleaned_data.get('nota')
                    entrega.justificativa_observacao_avaliacao = form.cleaned_data.get('justificativa')
                    entrega.aprovado = form.cleaned_data.get('homologa')
                    entrega.homologado = form.cleaned_data.get('homologa')
                    entrega.save()

                    ip = get_client_ip(request)
                    ra_obs = f'A entrega "{str_entrega}" foi avaliada no rit "{rit.get_verbose_rit()}"'
                    RegistroAcaoRelatorioIndividualTrabalho.objects.create(
                        tipo=RegistroAcaoRelatorioIndividualTrabalho.TIPO_AVALIOU_ENTREGA,
                        rit=rit,
                        rit_atividade=rit_atividade,
                        rit_atividade_entrega=entrega,
                        ip=ip,
                        observacao=ra_obs,
                    )

                if entregas_nao_podem_ser_operadas:
                    messages.success(request, 'Algumas entregas foram avaliadas com sucesso.')
                    messages.error(request, 'Algumas entregas não puderam ser avaliadas')
                else:
                    messages.success(request, 'Entregas avaliadas com sucesso.')

                action_executada = True

    if action_executada:
        rit.pit.calcular_pit(forcar_recalcular_tempo_previsto=True)

    pode_homologar_rit = rit.pode_homologar_rit(request.user)

    return locals()


@rtr()
@transaction.atomic
@permission_required('pgd.change_relatorioindividualtrabalhoatividadeentrega')
def avaliar_entrega_rit(request, rit_atividade_entrega_id):
    # Entrega (de um determinado RIT) que sera avalido pelo chefe

    rit_entrega = get_object_or_404(RelatorioIndividualTrabalhoAtividadeEntrega, pk=rit_atividade_entrega_id)
    rit = rit_entrega.rit_atividade.rit
    title = f'Avaliar Entrega {rit_entrega!s}'

    url = f'/admin/pgd/relatorioindividualtrabalhoatividadeentregaavaliar/?rit_atividade__rit={rit.id}'

    if not rit_entrega.pode_avaliar(request.user):
        raise PermissionDenied

    form = RelatorioIndividualTrabalhoAtividadeEntregaAvaliarForm(request.POST or None, request=request, rit_entrega=rit_entrega)
    if form.is_valid():
        # Avalia a entrega
        # --------------------------------------
        rit_entrega.nota = form.cleaned_data.get('nota')
        rit_entrega.tempo_executado_homologado = form.cleaned_data.get('tempo_homologado')
        rit_entrega.justificativa_observacao_avaliacao = form.cleaned_data.get('justificativa')
        rit_entrega.aprovado = form.cleaned_data.get('homologa')
        rit_entrega.homologado = form.cleaned_data.get('homologa')
        rit_entrega.save()

        ip = get_client_ip(request)
        justificativa = form.cleaned_data.get('justificativa')
        rit_atividade = rit_entrega.rit_atividade
        ra_obs = f'A entrega "{rit_entrega!s}" do rit "{rit.get_verbose_rit()}" foi avaliada"'
        if justificativa:
            ra_obs = f'A entrega "{rit_entrega!s}" do rit "{rit.get_verbose_rit()}" foi avaliada mediante seguinte justificativa/observação "{justificativa}"'
        RegistroAcaoRelatorioIndividualTrabalho.objects.create(
            tipo=RegistroAcaoRelatorioIndividualTrabalho.TIPO_AVALIOU_ENTREGA,
            rit=rit,
            rit_atividade=rit_atividade,
            rit_atividade_entrega=rit_entrega,
            ip=ip,
            observacao=ra_obs,
        )

        return httprr(url, 'Entrega avaliada com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('pgd.change_relatorioindividualtrabalhoatividadeentrega')
def avaliar_entregas_nao_avaliadas_rit(request, rit_id):
    # Chefe pode avaliar TODAS AS ENTREGAS NAO AVALIDAS de um RIT

    rit = get_object_or_404(RelatorioIndividualTrabalho, pk=rit_id)

    title = 'Avaliar todas as entregas ainda não avaliadas'

    url = f'/admin/pgd/relatorioindividualtrabalhoatividadeentregaavaliar/?rit_atividade__rit={rit.id}'

    lista_setores_user_eh_chefe_hoje = setores_que_sou_chefe_hoje(request.user.get_relacionamento())
    pode_avaliar_entregas_rit = rit.pode_avaliar_entregas_rit(request.user, lista_setores_user_eh_chefe_hoje=lista_setores_user_eh_chefe_hoje)
    if not pode_avaliar_entregas_rit:
        raise PermissionDenied

    form = RelatorioIndividualTrabalhoAtividadeEntregaAvaliarSimplesForm(request.POST or None, request=request)
    if form.is_valid():
        entregas = rit.get_entregas()
        entregas_podem_ser_avaliadas = []
        for entrega in entregas:
            if not entrega.foi_avaliado() and entrega.pode_avaliar(
                request.user,
                lista_setores_user_eh_chefe_hoje=lista_setores_user_eh_chefe_hoje,
                user_pode_avaliar_entregas_rit=pode_avaliar_entregas_rit,
            ):
                entregas_podem_ser_avaliadas.append(entrega)

        if entregas_podem_ser_avaliadas:
            for entrega in entregas_podem_ser_avaliadas:
                # Avalia a entrega
                # --------------------------------------
                entrega.tempo_executado_homologado = entrega.tempo_executado
                entrega.nota = form.cleaned_data.get('nota')
                entrega.justificativa_observacao_avaliacao = form.cleaned_data.get('justificativa')
                entrega.aprovado = form.cleaned_data.get('homologa')
                entrega.homologado = form.cleaned_data.get('homologa')
                entrega.save()

                ip = get_client_ip(request)
                justificativa = form.cleaned_data.get('justificativa')
                rit_atividade = entrega.rit_atividade
                ra_obs = f'A entrega "{entrega!s}" do rit "{rit.get_verbose_rit()}" foi avaliada"'
                if justificativa:
                    ra_obs = f'A entrega "{entrega!s}" do rit "{rit.get_verbose_rit()}" foi avaliada mediante seguinte justificativa/observação "{justificativa}"'
                RegistroAcaoRelatorioIndividualTrabalho.objects.create(
                    tipo=RegistroAcaoRelatorioIndividualTrabalho.TIPO_AVALIOU_ENTREGA,
                    rit=rit,
                    rit_atividade=rit_atividade,
                    rit_atividade_entrega=entrega,
                    ip=ip,
                    observacao=ra_obs,
                )
        else:
            return httprr(url, 'Nenhuma entrega a avaliar.', tag='error')

        return httprr(url, 'Entregas avaliadas com sucesso.')

    return locals()


@rtr('pgd/templates/base_form_message.html')
@transaction.atomic
@login_required()
def entregar_rit(request, rit_id):
    rit = get_object_or_404(RelatorioIndividualTrabalho, pk=rit_id)

    if not rit.pode_entregar_rit(request.user):
        raise PermissionDenied

    title = f'Entregar o {rit.get_verbose_rit_servidor()}'

    pit = rit.pit
    url = f'/pgd/visualizar_plano_individual_trabalho/{pit.id}/'

    entregas_pedentes = RelatorioIndividualTrabalhoAtividadeEntrega.objects.filter(rit_atividade__rit=rit).filter(
        situacao=RelatorioIndividualTrabalhoAtividadeEntrega.CADASTRADO
    )
    entregas_validas = RelatorioIndividualTrabalhoAtividadeEntrega.objects.filter(rit_atividade__rit=rit).filter(
        situacao=RelatorioIndividualTrabalhoAtividadeEntrega.ENTREGUE
    )

    # Só entrega se existe alguma entrega vinculada ao PTS do setor do Servidor (Apenas nas válidas)
    # - Essa regra foi colocada aqui para que esse motivo para não entregar o
    #   rit seja mostrado em tela para o usuario
    existe_pedentes_do_pts_setor_servidor = entregas_pedentes.filter(
        rit_atividade__atividade_pts__plano_trabalho_setorial__setor=rit.pit.adesao.servidor.setor
    ).exists()
    existe_validas_do_pts_setor_servidor = entregas_validas.filter(
        rit_atividade__atividade_pts__plano_trabalho_setorial__setor=rit.pit.adesao.servidor.setor
    ).exists()
    if not existe_pedentes_do_pts_setor_servidor and not existe_validas_do_pts_setor_servidor:
        return httprr(
            url, 'Impossível entregar um RIT que não tenha ao menos uma entrega vinculada ao PTS relacionado ao setor do Servidor.', tag='error'
        )

    # Se todas as entregas foram entregues (exceto as que foram canceladas) - Se existem válidas e nao existe nenhuma pendente
    # - Essa regra foi colocada aqui para que esse motivo para não entregar o
    #   rit seja mostrado em tela para o usuario
    existe_entregas_pedentes = entregas_pedentes.exists()
    existe_entregas_validas = entregas_validas.exists()
    if not (existe_entregas_validas and not existe_entregas_pedentes):
        return httprr(url, 'Impossível entregar um RIT tenha entregas pendentes de serem Entregues.', tag='error')

    # Só entrega se existir ao menos uma entrega vinculada a uma atividade relacionada a um PTS ativo do servidor
    # ------------------------
    # - Essa regra foi colocada aqui para que esse motivo para não entregar o
    #   rit seja mostrado em tela para o usuario
    # PTSs de cada um dos setores que o user é chefe
    existe_atividade_com_pts_inativo = False
    for entrega in entregas_validas:
        if not entrega.rit_atividade.atividade_estah_vinculada_a_adesao_pts_vigente_do_servidor():
            existe_atividade_com_pts_inativo = True
            break
    if existe_atividade_com_pts_inativo:
        return httprr(
            url,
            'Impossível entregar um RIT tenha entregas vinculadas a atividade relacionadas a PTS em que o Servidor não estiver com adesão válida.',
            tag='error',
        )

    # Não pode haver nenhuma entrega que tenha data final desalinhado com o periodo do PIT
    # ------------------------
    existe_entrega_prazo_desalinhado_com_periodo_pit = False
    for entrega in entregas_validas:
        if not entrega.entrega_estah_com_prazo_alinhado_com_periodo_rit():
            existe_entrega_prazo_desalinhado_com_periodo_pit = True
            break
    if existe_entrega_prazo_desalinhado_com_periodo_pit:
        return httprr(
            url, 'Impossível entregar o RIT se uma das entregas estiver estiver com data final em desacordo com o período do PIT.', tag='error'
        )

    # Verifica se deve ou nao preencher o questionário de pesquisa
    # ------------------------
    deve_responder_como_servidor = RelatorioIndividualTrabalhoQuestionario.deve_responder_como_servidor(
        servidor=rit.pit.adesao.servidor, setor_pit_rit=rit.pit.adesao.servidor.setor, periodo_pit_rit=rit.pit.periodo_pit_rit
    )
    if deve_responder_como_servidor:
        title = f'Questionário de pesquisa referente ao {rit.get_verbose_rit_servidor()}'
        mensagem_form_questionario = 'Após o preenchimento do questionário você será redirecionado para a Entrega do RIT'
        form = QuestionarioRitServidorForm(request.POST or None, request=request)
        if form.is_valid():
            o = form.save(False)
            o.periodo_pit_rit = rit.pit.periodo_pit_rit
            o.setor = rit.pit.adesao.servidor.setor
            o.servidor_respondente = rit.pit.adesao.servidor
            o.questionario_de_chefe = False
            o.save()

            url_entregar_rit = f'/pgd/entregar_rit/{rit_id}/'
            return httprr(url_entregar_rit, 'Questionário preenchido com sucesso.')

    if not deve_responder_como_servidor:
        form = EntregarRitForm(request.POST or None, request=request)
        if form.is_valid():
            rit.entregue = True
            rit.save()

            ip = get_client_ip(request)
            justificativa = form.cleaned_data.get('justificativa_entrega')
            ra_obs = f'O rit "{rit.get_verbose_rit()}" foi entregue"'
            if rit.justificativa_entrega:
                ra_obs = f'O rit "{rit.get_verbose_rit()}" foi entregue mediante seguinte justificativa/observação "{justificativa}"'
            RegistroAcaoRelatorioIndividualTrabalho.objects.create(
                tipo=RegistroAcaoRelatorioIndividualTrabalho.TIPO_ENTREGOU_RIT, rit=rit, ip=ip, observacao=ra_obs
            )

            return httprr(url, 'RIT entregue com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@login_required()
def recalcular_pit_rit(request, pit_id):
    pit = get_object_or_404(PlanoIndividualTrabalho, pk=pit_id)
    if not pit.pode_recalcular_pit_rit(request.user):
        raise PermissionDenied

    pit.calcular_pit(forcar_recalcular_tempo_previsto=True)
    return httprr(
        request.META.get(
            'HTTP_REFERER',
        )
        or '..',
        'PIT/RIT recalculado com sucesso.',
    )


@rtr('pgd/templates/base_form_message.html')
@transaction.atomic
@login_required()
def homologar_rit(request, rit_id):
    rit = get_object_or_404(RelatorioIndividualTrabalho, pk=rit_id)

    if not rit.pode_homologar_rit(request.user):
        raise PermissionDenied

    title = f'Aprovar/Homologar o {rit.get_verbose_rit_servidor()}'

    pit = rit.pit
    url = f'/admin/pgd/relatorioindividualtrabalhoatividadeentregaavaliar/?rit_atividade__rit={rit.id}'
    url_sucesso = f'/pgd/visualizar_opcoes_rit/{rit.id}'

    servidor_chefe = request.user.get_relacionamento()

    # Só entrega se existir ao menos uma entrega vinculada a uma atividade relacionada a um PTS ativo do servidor
    # --------------------------------------------------------------------------
    # - Essa regra foi colocada aqui para que esse motivo para não entregar o
    #   rit seja mostrado em tela para o usuario
    # PTSs de cada um dos setores que o user é chefe
    entregas_validas = RelatorioIndividualTrabalhoAtividadeEntrega.objects.filter(rit_atividade__rit=rit).filter(
        situacao=RelatorioIndividualTrabalhoAtividadeEntrega.ENTREGUE
    )
    existe_atividade_com_pts_inativo = False
    for entrega in entregas_validas:
        if not entrega.rit_atividade.atividade_estah_vinculada_a_adesao_pts_vigente_do_servidor():
            existe_atividade_com_pts_inativo = True
            break
    if existe_atividade_com_pts_inativo:
        return httprr(
            url,
            'Impossível homologar um RIT tenha entregas vinculadas a atividade relacionadas a PTS em que o Servidor não estiver com adesão válida.',
            tag='error',
        )

    # Se o servidor estiver desligado da adesao relacionada nao pode homologar
    # --------------------------------------------------------------------------
    # - Qualquer RIT que inicie após a data de efeito nao pode estar homologado
    if rit.pit.adesao.tem_desligamento_cadastrado:
        if rit.get_data_inicial() >= rit.pit.adesao.data_desligamento_efeitos_a_partir_de:
            return httprr(
                url, 'Impossível homologar um RIT que inicie após a data de efeitos do desligamento da adesão PGD relacionada.', tag='error'
            )

    # Não pode haver nenhuma entrega que tenha data final desalinhado com o periodo do PIT
    # ------------------------
    existe_entrega_prazo_desalinhado_com_periodo_pit = False
    for entrega in entregas_validas:
        if not entrega.entrega_estah_com_prazo_alinhado_com_periodo_rit():
            existe_entrega_prazo_desalinhado_com_periodo_pit = True
            break
    if existe_entrega_prazo_desalinhado_com_periodo_pit:
        return httprr(
            url, 'Impossível homologar o RIT se uma das entregas estiver estiver com data final em desacordo com o período do PIT.', tag='error'
        )

    # Verifica se deve ou nao preencher o questionário de pesquisa
    # ------------------------
    deve_responder_como_chefe = RelatorioIndividualTrabalhoQuestionario.deve_responder_como_chefe(
        servidor=servidor_chefe, setor_pit_rit=rit.pit.adesao.servidor.setor, periodo_pit_rit=rit.pit.periodo_pit_rit
    )
    if deve_responder_como_chefe:
        title = f'Questionário de pesquisa referente ao {rit.pit.periodo_pit_rit} | {rit.pit.adesao.servidor.setor}'
        mensagem = 'Após o preenchimento do questionário você será redirecionado para a Homologação'
        tipo_mensagem = 'info'
        form = QuestionarioRitChefeForm(request.POST or None, request=request)
        if form.is_valid():
            o = form.save(False)
            o.periodo_pit_rit = rit.pit.periodo_pit_rit
            o.setor = rit.pit.adesao.servidor.setor
            o.servidor_respondente = servidor_chefe
            o.questionario_de_chefe = True
            o.save()
            url_entregar_rit = f'/pgd/homologar_rit/{rit_id}/'
            return httprr(url_entregar_rit, 'Questionário preenchido com sucesso.')

    if not deve_responder_como_chefe:
        form = HomologarRitForm(request.POST or None, request=request)
        if form.is_valid():
            # Recalcula
            pit.calcular_pit(forcar_recalcular_tempo_previsto=True)
            rit = get_object_or_404(RelatorioIndividualTrabalho, pk=rit_id)
            pit = rit.pit

            # Homologa RIT e salva outros dados do form
            rit.aprovado_definitivo = True
            rit.homologado_definitivo = True
            rit.save()

            # Homologa em definitivo o PIT se não houver mais nada a ser feito nos RITs deste PIT
            # Joga o saldo externo para o ponto
            if pit.pode_homologar_pit():
                pit.homologado_definitivo = True
                pit.save()
                rit.distribuir_horas_automaticamente()

            # Registro de acao
            ip = get_client_ip(request)
            justificativa = form.cleaned_data.get('justificativa_homologacao')
            ra_obs = f'O rit "{rit.get_verbose_rit()}" foi Aprovado/Homologado"'
            if justificativa:
                ra_obs = f'O rit "{rit.get_verbose_rit()}" foi Aprovado/Homologado mediante seguinte justificativa/observação "{justificativa}"'
            RegistroAcaoRelatorioIndividualTrabalho.objects.create(
                tipo=RegistroAcaoRelatorioIndividualTrabalho.TIPO_APROVOU_HOMOLOGOU_RIT, rit=rit, ip=ip, observacao=ra_obs
            )

            return httprr(url_sucesso, 'RIT Aprovado/Homologado com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@login_required()
def distribuir_horas_automaticamente_rit(request, rit_id):
    rit = get_object_or_404(RelatorioIndividualTrabalho, pk=rit_id)

    if not rit.pode_distribuir_horas(request.user):
        raise PermissionDenied

    title = f'Distribuir/Redistribuir horas automaticamente no {rit.get_verbose_rit_servidor()}'

    form = DistribuirHorasAutoRitForm(request.POST or None, request=request)
    if form.is_valid():
        apenas_periodo_rit = form.cleaned_data.get('confirmacao2')
        rit.desfazer_distribuicao_horas()
        rit.distribuir_horas_automaticamente(apenas_periodo_rit=apenas_periodo_rit)
        url = f'/pgd/servidor_pgd_horas_detalhes/{rit.id}'
        return httprr(url, 'Distribuição/Redistribuição automática de horas realizada com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@login_required()
def desfazer_distribuicao_horas(request, rit_id):
    # Desfaz todas a distribuição de horas
    rit = get_object_or_404(RelatorioIndividualTrabalho, pk=rit_id)

    if not rit.pode_distribuir_horas(request.user):
        raise PermissionDenied

    title = f'Desfazer distribuição de horas no {rit.get_verbose_rit_servidor()}'

    form = DesfazerDistribuirHorasAutoRitForm(request.POST or None, request=request)
    if form.is_valid():
        rit.desfazer_distribuicao_horas()
        url = f'/pgd/servidor_pgd_horas_detalhes/{rit.id}'
        return httprr(url, 'Distribuição de horas foi desfeita com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@login_required()
def atualizar_horas_previstas_rit(request, rit_id):
    # Recalcula as horas previstas de um rit
    # - usado apenas na tela de distribuição de horas

    rit = get_object_or_404(RelatorioIndividualTrabalho, pk=rit_id)

    if not rit.pode_distribuir_horas(request.user):
        raise PermissionDenied

    rit.atualizar_horas_previstas_rit()

    url = f'/pgd/servidor_pgd_horas_detalhes/{rit.id}'
    return httprr(url, 'Atualização realizada com sucesso.')


@rtr()
@transaction.atomic
@login_required()
def ajustar_distribuicao_semestre(request, rit_id):
    # Ajusta manualmente a distribuicao de horas do semestre do rit
    # - apaga a distribuicao anterio do semestre
    # - cria uma nova
    rit = get_object_or_404(RelatorioIndividualTrabalho, pk=rit_id)

    if not rit.pode_ajustar_distribuicao_horas_semestre_rit(request.user):
        raise PermissionDenied

    title = f'Ajustar distribuição de horas no semestre relativo ao {rit.get_verbose_rit_servidor()}'

    form = AjustarHorasSemestreRitForm(request.POST or None, request=request, rit=rit)
    if form.is_valid():
        rit.desfazer_distribuicao_horas_semestre()

        compensar_automaticamente = form.cleaned_data.get('confirmacao2')
        distribuir_todas = form.cleaned_data.get('confirmacao4')
        ch = form.cleaned_data.get('horas')
        if ch:
            ch = ch.hour * 60 * 60 + ch.minute * 60 + ch.second
        rit.ajustar_distribuicao_horas_semestre_rit(compensar_automaticamente=compensar_automaticamente, ch=ch, distribuir_todas=distribuir_todas)

        url = f'/pgd/servidor_pgd_horas_detalhes/{rit.id}'
        return httprr(url, 'Distribuição de horas foi desfeita com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@login_required()
def desfazer_distribuicao_horas_semestre(request, rit_id):
    # Desfaz a distribuicao de horas do semestre do rit
    rit = get_object_or_404(RelatorioIndividualTrabalho, pk=rit_id)

    if not rit.pode_desfazer_distribuicao_horas_semestre(request.user):
        raise PermissionDenied

    title = f'Desfazer distribuição de horas no semestre relativo ao {rit.get_verbose_rit_servidor()}'

    form = DesfazerDistribuirHorasSemestreRitForm(request.POST or None, request=request)
    if form.is_valid():
        rit.desfazer_distribuicao_horas_semestre()
        url = f'/pgd/servidor_pgd_horas_detalhes/{rit.id}'
        return httprr(url, 'Distribuição de horas foi desfeita com sucesso.')

    return locals()


@rtr()
@login_required()
def visualizar_distribuicao_compensacao_especifica(request, rit_id):
    # Tela de visualizaçao das do resumo das compenacoes especificas
    # - apaga a distribuicao anterio do semestre
    # - cria uma nova
    rit = get_object_or_404(RelatorioIndividualTrabalho, pk=rit_id)

    if not rit.pode_distribuir_horas(request.user):
        raise PermissionDenied

    title = f'Ajustar distribuição de horas do {rit.get_verbose_rit_servidor()} para compensações específicas compensáveis por este RIT'

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
@login_required()
def ajustar_distribuicao_compensacao_especifica(request, rit_id, compesacao_especifica_id):
    # Ajusta manualmente a distribuicao de horas de uma compensação específica
    # - apaga a distribuicao anterior referente a este rit
    # - cria uma nova
    rit = get_object_or_404(RelatorioIndividualTrabalho, pk=rit_id)
    if not rit.pode_ajustar_distribuicao_compensacao_especifica(request.user):
        raise PermissionDenied
    compensacao_especifica = get_object_or_404(RecessoOpcaoEscolhida, pk=compesacao_especifica_id)

    rit.ajustar_distribuicao_compensacao_especifica(compensacao_especifica=compensacao_especifica)

    url = f'/pgd/servidor_pgd_horas_detalhes/{rit.id}'
    return httprr(url, 'Distribuição de horas realizada com sucesso.')


@rtr()
@transaction.atomic
@login_required()
def desfazer_distribuicao_compensacao_especifica(request, rit_id, compesacao_especifica_id):
    # Desfaz a distribuicao de horas de uma compensação específica
    rit = get_object_or_404(RelatorioIndividualTrabalho, pk=rit_id)
    compensacao_especifica = get_object_or_404(RecessoOpcaoEscolhida, pk=compesacao_especifica_id)

    if not rit.pode_desfazer_distribuicao_compensacao_especifica(request.user, compensacao_especifica=compensacao_especifica):
        raise PermissionDenied

    title = f'Desfazer distribuição de horas relativas ao {rit.get_verbose_rit_servidor()} para a compensação específica {compensacao_especifica}'

    form = DesfazerDistribuirHorasCompensacaoEspecificaRitForm(request.POST or None, request=request)
    if form.is_valid():
        rit.desfazer_distribuicao_compensacao_especifica(compensacao_especifica)
        url = f'/pgd/servidor_pgd_horas_detalhes/{rit.id}'
        return httprr(url, 'Distribuição de horas foi desfeita com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@login_required()
def devolver_rit_servidor(request, rit_id):
    # Desentrega o RIT para qiue o servidor possa fazer algom a mais neste RIT

    rit = get_object_or_404(RelatorioIndividualTrabalho, pk=rit_id)

    lista_setores_user_eh_chefe_hoje = setores_que_sou_chefe_hoje(request.user.get_relacionamento())
    if not rit.pode_reabrir_rit(request.user, lista_setores_user_eh_chefe_hoje=lista_setores_user_eh_chefe_hoje):
        raise PermissionDenied

    title = f'Devolver o {rit.get_verbose_rit()}'

    pit = rit.pit
    url = '/admin/pgd/relatorioindividualtrabalho/'

    form = DevolverRitConfirmacaoForm(request.POST or None, request=request)
    if form.is_valid():
        # Rabrindo RIT
        rit.homologado_definitivo = None
        rit.aprovado_definitivo = None
        rit.entregue = False
        rit.save()

        # Reabrindo PIT
        pit = rit.pit
        pit.homologado_definitivo = False
        pit.save()

        # Desfazendo distribuição de horas
        rit.desfazer_distribuicao_horas()
        rit.ch_a_distribuir = 0
        rit.save()

        ip = get_client_ip(request)
        justificativa = form.cleaned_data.get('justificativa')
        ra_obs = f'O rit "{rit.get_verbose_rit()}" foi Reaberto'
        if justificativa:
            ra_obs = f'O rit "{rit.get_verbose_rit()}" foi Reaberto mediante seguinte justificativa/observação "{justificativa}"'
        RegistroAcaoRelatorioIndividualTrabalho.objects.create(
            tipo=RegistroAcaoRelatorioIndividualTrabalho.TIPO_REABRIU_RIT, rit=rit, ip=ip, observacao=ra_obs
        )

        return httprr(url, 'RIT reaberto com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@login_required
def vincular_atividade_em_lote_pts(request, pts_id):
    pts = get_object_or_404(PlanoTrabalhoSetorial, pk=pts_id)
    if not pts.pode_vincular_atividades(request.user):
        raise PermissionDenied

    pts.sincrononiza_inativacao_atividades()
    atividades_para_adicionar = pts.get_atividades_para_adicionar()
    if not atividades_para_adicionar.exists():
        return httprr('..', 'Não existem atividades disponíveis para adicionar neste Plano de Trabalho Setorial.', tag='error')

    if not request.GET.get('submeter_atividades_selecionadas'):
        raise PermissionDenied

    atividades_ids = request.GET.getlist('checks[]')
    for atividades_id in atividades_ids:
        if not atividades_para_adicionar.filter(id=atividades_id):
            raise PermissionDenied

    atividades_para_adicionar = atividades_para_adicionar.filter(id__in=atividades_ids)
    atividades_adicionadas = False

    for atividade in atividades_para_adicionar:
        nova_atividade = PlanoTrabalhoSetorialAtividades()
        nova_atividade.plano_trabalho_setorial = pts
        nova_atividade.atividade = atividade
        nova_atividade.save()

        ip = get_client_ip(request)
        ra_obs = f'A atividade "{nova_atividade.atividade}" foi vinculada ao PTS'
        RegistroAcaoPTS.objects.create(tipo=RegistroAcaoPTS.TIPO_ATIVIDADE_VINCULADA, pts=pts, ip=ip, observacao=ra_obs)

        atividades_adicionadas = True

    if atividades_adicionadas:
        return httprr(f'/pgd/visualizar_plano_trabalho_setorial/{pts_id}/', 'Atividades vinculadas com sucesso.')

    return locals()


# ====================================================
# Relatorios e Consultas
# ====================================================


@rtr()
@permission_required('pgd.gestao_pgd')
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

    estah_em_gestao_pgd = request.user.has_group_cached('Gestor do PGD')
    estah_em_comissao_sistemica_vigente = request.user.has_group_cached('Comissão Sistêmica PGD')
    estah_em_comissao_local_vigente = request.user.has_group_cached('Comissão Local PGD')

    if not (estah_em_gestao_pgd or estah_em_comissao_sistemica_vigente or estah_em_comissao_local_vigente):
        raise PermissionDenied

    title = 'Relatório de Participantes do PGD (Por categoria e campus)'

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

    servidores_pgd = SolicitacaoAdesaoServidor.get_servidores_com_adesao_vigente()
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
    dict_dados_quadro_consolidado['descricao'] = '2 - NÚMERO DE COLABORADORES QUE ADERIRAM AO PGD'
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
        dict_dados_quadro_por_campus['descricao'] = '2 - NÚMERO DE COLABORADORES QUE ADERIRAM AO PGD'
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
        #
        dict_dados_campus = {}
        dict_dados_campus['campus'] = campus
        dict_dados_campus['dados'] = lista_quadro_campus
        lista_campis.append(dict_dados_campus)
        lista_quadro_campus = []

    return locals()


@rtr()
@permission_required('pgd.gestao_pgd')
def relatorio_participantes_desligamento(request):
    """
    DESCRICAO: Relatorio dos participantes com desligamento. Por categoria e campus.
    Relatorio
    - Filtros
      - Periodo de mês
    - Dados
      - Qtds
        - Por campus
        - Por categoria
      - Adesões
      - Servidores que se desligaram
        - Desligaram por desligamento voluntario
        - Desligaram por desligamento como punicao
    """

    estah_em_gestao_pgd = request.user.has_group_cached('Gestor do PGD')
    estah_em_comissao_sistemica_vigente = request.user.has_group_cached('Comissão Sistêmica PGD')
    estah_em_comissao_local_vigente = request.user.has_group_cached('Comissão Local PGD')

    if not (estah_em_gestao_pgd or estah_em_comissao_sistemica_vigente or estah_em_comissao_local_vigente):
        raise PermissionDenied

    title = 'Relatório de Participantes do PGD com desligamento (Por período, categoria e campus)'

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
        return tasks.gerar_relatorio_participantes_desligamento(mes_ini, ano_ini, mes_fim, ano_fim, request)

    return locals()


@rtr()
@permission_required('pgd.gestao_pgd')
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
    estah_em_gestao_pgd = request.user.has_group_cached('Gestor do PGD')
    estah_em_comissao_sistemica_vigente = request.user.has_group_cached('Comissão Sistêmica PGD')
    estah_em_comissao_local_vigente = request.user.has_group_cached('Comissão Local PGD')

    if not (estah_em_gestao_pgd or estah_em_comissao_sistemica_vigente or estah_em_comissao_local_vigente):
        raise PermissionDenied

    title = 'Relatório de RITs entregues com horas menor que o planejado'

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

        rits_homologados = RelatorioIndividualTrabalho.objects.filter(aprovado_definitivo=True, homologado_definitivo=True)
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

            rits_homologados_periodo = RegistroAcaoRelatorioIndividualTrabalho.objects.filter(
                data__month=periodo.month, data__year=periodo.year, tipo=RegistroAcaoRelatorioIndividualTrabalho.TIPO_APROVOU_HOMOLOGOU_RIT
            ).values_list('rit_id')

            # ---------------------------
            # Dados por periodo
            # ---------------------------
            dict_dados = {}
            dict_dados['descricao'] = '1 - COLABORADORES DO IFRN'
            dict_dados['entregues'] = rits_homologados_periodo.count()
            dict_dados['entregues_abaixo_da_meta'] = rits_homologados_periodo.filter(
                rit__tempo_planejado__gt=F('rit__tempo_executado_homologado_ajustado_pela_faixa_complexidade')
            ).count()
            lista_dados.append(dict_dados)
            dict_consolidado['ifrn_entregues'] += dict_dados['entregues']
            dict_consolidado['ifrn_entregues_abaixo_da_meta'] += dict_dados['entregues_abaixo_da_meta']

            dict_dados = {}
            dict_dados['descricao'] = '1.1 - TÉCNICO ADMINISTRATIVO'
            dict_dados['entregues'] = rits_homologados_periodo.filter(rit__pit__adesao__servidor__in=taes).count()
            dict_dados['entregues_abaixo_da_meta'] = rits_homologados_periodo.filter(
                rit__tempo_planejado__gt=F('rit__tempo_executado_homologado_ajustado_pela_faixa_complexidade'), rit__pit__adesao__servidor__in=taes
            ).count()
            lista_dados.append(dict_dados)
            dict_consolidado['tae_entregues'] += dict_dados['entregues']
            dict_consolidado['tae_entregues_abaixo_da_meta'] += dict_dados['entregues_abaixo_da_meta']

            dict_dados = {}
            dict_dados['descricao'] = '1.2 - DOCENTE'
            dict_dados['entregues'] = rits_homologados_periodo.filter(rit__pit__adesao__servidor__in=docentes).count()
            dict_dados['entregues_abaixo_da_meta'] = rits_homologados_periodo.filter(
                rit__tempo_planejado__gt=F('rit__tempo_executado_homologado_ajustado_pela_faixa_complexidade'),
                rit__pit__adesao__servidor__in=docentes,
            ).count()
            lista_dados.append(dict_dados)
            dict_consolidado['docente_entregues'] += dict_dados['entregues']
            dict_consolidado['docente_entregues_abaixo_da_meta'] += dict_dados['entregues_abaixo_da_meta']

            dict_dados = {}
            dict_dados['descricao'] = '1.3 - ESTAGIÁRIO'
            dict_dados['entregues'] = rits_homologados_periodo.filter(rit__pit__adesao__servidor__in=estagiarios).count()
            dict_dados['entregues_abaixo_da_meta'] = rits_homologados_periodo.filter(
                rit__tempo_planejado__gt=F('rit__tempo_executado_homologado_ajustado_pela_faixa_complexidade'),
                rit__pit__adesao__servidor__in=estagiarios,
            ).count()
            lista_dados.append(dict_dados)
            dict_consolidado['estagiario_entregues'] += dict_dados['entregues']
            dict_consolidado['estagiario_entregues_abaixo_da_meta'] += dict_dados['entregues_abaixo_da_meta']

            dict_dados_periodo = {}
            dict_dados_periodo['periodo'] = f'{periodo.month}/{periodo.year}'
            dict_dados_periodo['dados'] = lista_dados
            lista_dados_periodo.append(dict_dados_periodo)

            # Por campus
            # --------------------
            for campus in campis:
                dict_dados = {}
                dict_dados['descricao'] = campus
                lista_dados.append(dict_dados)

                dict_dados = {}
                dict_dados['descricao'] = '1 - COLABORADORES DO CAMPUS'
                dict_dados['entregues'] = rits_homologados_periodo.filter(rit__pit__adesao__servidor__setor__uo=campus).count()
                dict_dados['entregues_abaixo_da_meta'] = rits_homologados_periodo.filter(
                    rit__tempo_planejado__gt=F('rit__tempo_executado_homologado_ajustado_pela_faixa_complexidade'),
                    rit__pit__adesao__servidor__setor__uo=campus,
                ).count()
                lista_dados.append(dict_dados)
                dict_consolidado_uos[campus.sigla]['ifrn_entregues'] += dict_dados['entregues']
                dict_consolidado_uos[campus.sigla]['ifrn_entregues_abaixo_da_meta'] += dict_dados['entregues_abaixo_da_meta']

                dict_dados = {}
                dict_dados['descricao'] = '1.1 - TÉCNICO ADMINISTRATIVO'
                dict_dados['entregues'] = rits_homologados_periodo.filter(
                    rit__pit__adesao__servidor__in=taes, rit__pit__adesao__servidor__setor__uo=campus
                ).count()
                dict_dados['entregues_abaixo_da_meta'] = rits_homologados_periodo.filter(
                    rit__tempo_planejado__gt=F('rit__tempo_executado_homologado_ajustado_pela_faixa_complexidade'),
                    rit__pit__adesao__servidor__in=taes,
                    rit__pit__adesao__servidor__setor__uo=campus,
                ).count()
                lista_dados.append(dict_dados)
                dict_consolidado_uos[campus.sigla]['tae_entregues'] += dict_dados['entregues']
                dict_consolidado_uos[campus.sigla]['tae_entregues_abaixo_da_meta'] += dict_dados['entregues_abaixo_da_meta']

                dict_dados = {}
                dict_dados['descricao'] = '1.2 - DOCENTE'
                dict_dados['entregues'] = rits_homologados_periodo.filter(
                    rit__pit__adesao__servidor__in=docentes, rit__pit__adesao__servidor__setor__uo=campus
                ).count()
                dict_dados['entregues_abaixo_da_meta'] = rits_homologados_periodo.filter(
                    rit__tempo_planejado__gt=F('rit__tempo_executado_homologado_ajustado_pela_faixa_complexidade'),
                    rit__pit__adesao__servidor__in=docentes,
                    rit__pit__adesao__servidor__setor__uo=campus,
                ).count()
                lista_dados.append(dict_dados)
                dict_consolidado_uos[campus.sigla]['docente_entregues'] += dict_dados['entregues']
                dict_consolidado_uos[campus.sigla]['docente_entregues_abaixo_da_meta'] += dict_dados['entregues_abaixo_da_meta']

                dict_dados = {}
                dict_dados['descricao'] = '1.3 - ESTAGIÁRIO'
                dict_dados['entregues'] = rits_homologados_periodo.filter(
                    rit__pit__adesao__servidor__in=estagiarios, rit__pit__adesao__servidor__setor__uo=campus
                ).count()
                dict_dados['entregues_abaixo_da_meta'] = rits_homologados_periodo.filter(
                    rit__tempo_planejado__gt=F('rit__tempo_executado_homologado_ajustado_pela_faixa_complexidade'),
                    rit__pit__adesao__servidor__in=estagiarios,
                    rit__pit__adesao__servidor__setor__uo=campus,
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
@permission_required('pgd.gestao_pgd')
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

    estah_em_gestao_pgd = request.user.has_group_cached('Gestor do PGD')
    estah_em_comissao_sistemica_vigente = request.user.has_group_cached('Comissão Sistêmica PGD')
    estah_em_comissao_local_vigente = request.user.has_group_cached('Comissão Local PGD')

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
@login_required()
def visualizar_opcoes_rit(request, rit_id):
    rit = get_object_or_404(RelatorioIndividualTrabalho, pk=rit_id)

    opcoes = None
    pode_visualizar = False
    texto = '<ul class="action-bar">'
    lista_setores_user_eh_chefe_hoje = setores_que_sou_chefe_hoje(request.user.get_relacionamento())

    if rit.pit.pode_visualizar_pit_completo(request.user):
        # Chefe pode visualizar o PIT e RIT completo
        texto += f'<li><a href="/pgd/visualizar_pit_completo/{rit.pit.id}/" class="btn primary">Visualizar PIT/RITs Completo</a></li>'
        pode_visualizar = True

    if rit.pode_receber_entregas(request.user):
        # Chefe pode visualizar a execução (entregas), editar e adicionar entregas
        texto += f'<li><a href="/admin/pgd/relatorioindividualtrabalhoatividadeentregacheferegistrar/?rit_atividade__rit={rit.id}" class="btn primary">Cadastrar/Editar Execução (RIT- Entregas)</a></li>'
        pode_visualizar = True

    if rit.pode_avaliar_entregas_rit(request.user, lista_setores_user_eh_chefe_hoje=lista_setores_user_eh_chefe_hoje):
        # Chefe pode avaliar as entregas e o RIT
        texto += f'<li><a href="/admin/pgd/relatorioindividualtrabalhoatividadeentregaavaliar/?rit_atividade__rit={rit.id}" class="btn primary">Avaliar e Homologar (RIT)</a></li>'
        pode_visualizar = True

    if rit.pode_reabrir_rit(request.user, lista_setores_user_eh_chefe_hoje=lista_setores_user_eh_chefe_hoje):
        # Chefe pode reabrir RIT
        texto += f'<li><a href="/pgd/devolver_rit_servidor/{rit.id}/" class="btn primary">Devolver RIT</a></li>'
        pode_visualizar = True

    texto += '</ul>'
    opcoes = mark_safe(texto)

    if not pode_visualizar:
        raise PermissionDenied

    servidor = rit.pit.adesao.servidor

    rit = RelatorioIndividualTrabalho.objects.get(pk=rit_id)

    title = f'{rit.get_verbose_rit()}'

    return locals()


@rtr()
@permission_required('pgd.gestao_pgd')
def relatorio_questionario_rit(request):
    estah_em_gestao_pgd = request.user.has_group_cached('Gestor do PGD')
    estah_em_comissao_sistemica_vigente = request.user.has_group_cached('Comissão Sistêmica PGD')
    estah_em_comissao_local_vigente = request.user.has_group_cached('Comissão Local PGD')

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
