from collections import OrderedDict
from datetime import date, datetime, timedelta

import gitlab
from django.apps import apps
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.db.models import BooleanField, Case, Count, F, IntegerField, OuterRef, Q, Subquery, Value, When
from django.db.models.expressions import RawSQL
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.template.defaultfilters import pluralize, slugify
from django.urls import reverse, reverse_lazy
from django.views.decorators.csrf import csrf_exempt
from gitlab import GitlabError
from requests.exceptions import ConnectionError

from centralservicos.models import AtendimentoAtribuicao, GrupoAtendimento
from comum.models import Comentario, Configuracao, User, UsuarioGrupo
from demandas import tasks
from demandas.exceptions import DemandasException
from demandas.forms import (
    AcompanhamentoForm,
    AlterarUsuarioDemandaForm,
    AnexosForm,
    AprovarEntregaForm,
    AreaAtuacaoGerenciarDemandantesForm,
    ConfirmarComSenhaForm,
    DashboardForm,
    DataPrevisaoAlterarForm,
    DoDForm,
    EntregaForm,
    EspecificacaoForm,
    EspecificacaoTecnicaForm,
    ExecutarComandoForm,
    GerarDemandaSugestaoMelhoriaForm,
    NotaInternaForm,
    NovaPrioridadeDemandaForm,
    BuscarModuloSugestaoMelhoriaFormFactory,
    RelatorioForm,
    ReprovarEntregaForm,
    RevisaoEspecificacaoForm,
    SituacaoAlterarFormFactory,
    SubdemandaAddForm,
    SubstituirDemandanteForm,
    SugestaoAnexoForm,
    SugestaoMelhoriaAddForm,
    SugestaoMelhoriaEdicaoAreaAtuacaoForm,
    SugestaoMelhoriaEdicaoBasicaForm,
    SugestaoMelhoriaEdicaoCompletaForm,
    VincularIssueGitlabForm,
)
from demandas.models import (
    AmbienteHomologacao,
    AnalistaDesenvolvedor,
    Anexos,
    AreaAtuacaoDemanda,
    Atualizacao,
    Demanda,
    DemandaPriorizacao,
    DemandaVoto,
    DoD,
    Especificacao,
    HistoricoRevisao,
    HistoricoSituacao,
    HistoricoSituacaoSugestaoMelhoria,
    NotaInterna,
    ProjetoGitlab,
    RevisaoEspecificacao,
    Situacao,
    SugestaoMelhoria,
    SugestaoVoto,
    Tag,
    TipoDemanda,
)
from demandas.models.entrega import Entrega
from demandas.services import DemandaMarkdownExportService, EntregaService, SubdemandaService
from demandas.utils import Notificar
from djtools import layout
from djtools.html.graficos import GroupedColumnChart, PieChart
from djtools.lps import lps
from djtools.signals import minhas_acoes
from djtools.utils import JsonResponse, documento, httprr, permission_required, render_to_string, rtr
from djtools.utils.gitlab import GitlabJobError


@layout.servicos_anonimos()
def servicos_anonimos(request):
    servicos_anonimos = []

    servicos_anonimos.append(
        {'categoria': 'Sobre o Suap', 'titulo': 'Atualizações do sistema', 'icone': 'file-contract', 'url': '/demandas/atualizacoes/'}
    )

    return servicos_anonimos


@layout.atribuidos_a_mim()
def index_atribuidos_a_mim(request):
    pendencias = []
    usuario = request.user

    if usuario.has_group_cached('Analista'):
        demandas_como_analista = Demanda.objects.filter(analistas=usuario)

        qtd_demandas_a_atualizar = demandas_como_analista.a_atualizar().count()
        if qtd_demandas_a_atualizar:
            pendencias.append(
                {
                    'titulo': f'Demanda{pluralize(qtd_demandas_a_atualizar)}',
                    'subtitulo': 'a atualizar',
                    'qtd': qtd_demandas_a_atualizar,
                    'url': f'/admin/demandas/demanda/?tab=tab_a_atualizar&analistas={usuario.pk}',
                }
            )

    if usuario.has_group_cached('Demandante'):
        qtd_total = Demanda.objects.aguardando_feedback().filter(demandantes=usuario).count()
        if qtd_total:
            pendencias.append(
                {
                    'titulo': f'Demanda{pluralize(qtd_total)}',
                    'subtitulo': 'aguardando feedback',
                    'qtd': qtd_total,
                    'url': f'/admin/demandas/demanda/?tab=tab_aguardando_feedback&demandantes={usuario.pk}',
                }
            )

    return pendencias


@layout.atribuidos_a_meus_grupos()
def index_atribuidos_a_meus_grupos(request):
    pendencias = []

    if request.user.has_group_cached('Recebedor de Demandas', ignore_groups_if_superuser=False):
        qtd_demandas_prioritarias_por_area = DemandaPriorizacao.get_qtd_demandas_prioritarias_por_area()
        demandas_sem_analista = (
            Demanda.objects.filter(analistas__isnull=True, prioridade__lte=qtd_demandas_prioritarias_por_area)
            .exclude(situacao=Situacao.ESTADO_SUSPENSO)
            .count()
        )
        if demandas_sem_analista:
            pendencias.append(
                {
                    'titulo': f'Demanda{pluralize(demandas_sem_analista)}',
                    'subtitulo': 'a indicar analista',
                    'qtd': demandas_sem_analista,
                    'url': '/admin/demandas/demanda/?eh_prioritaria=Sim&analistas__isnull=True&tab=tab_ativas',
                }
            )

        qtd_a_acompanhar = Demanda.objects.a_acompanhar().count()
        if qtd_a_acompanhar:
            pendencias.append(
                {
                    'titulo': f'Demanda{pluralize(qtd_a_acompanhar)}',
                    'subtitulo': 'a acompanhar',
                    'qtd': qtd_a_acompanhar,
                    'url': '/admin/demandas/demanda/?tab=tab_a_acompanhar',
                }
            )

    # Sugestões de melhoria
    minhas_sugestoes_ativas_como_demandante = SugestaoMelhoria.sugestoes_ativas(
        SugestaoMelhoria.sugestoes_por_papel_usuario(user_demandante=request.user)
    ).count()
    if minhas_sugestoes_ativas_como_demandante:
        pendencias.append(
            {
                'titulo': f'Sugest{pluralize(minhas_sugestoes_ativas_como_demandante, "ão,ões")} de melhorias',
                'subtitulo': 'a avaliar',
                'qtd': minhas_sugestoes_ativas_como_demandante,
                'url': '/admin/demandas/sugestaomelhoria/?tab=tab_como_demandante',
            }
        )

    return pendencias


@layout.quadro('Atualizações do Sistema', icone='info-circle', pode_esconder=True, session_cache=8 * 3600)
def index_quadros_atualizacoes(quadro, request):
    user_groups = request.user.get_groups_cached()
    atualizacoes = (
        Atualizacao.objects.filter(
            id__in=Atualizacao.objects.filter(grupos__name__in=user_groups, data__gte=datetime.now() - timedelta(days=7), data__lte=datetime.now())
            .order_by('data')
            .values_list('id', flat=True)
        )
        .prefetch_related('tags')
        .only('id', 'data', 'descricao')
        .order_by('-data')
    )

    if atualizacoes.exists():
        quadro.add_item(layout.ItemTitulo(titulo='Últimos 7 dias'))
        for atualizacao in atualizacoes:
            quadro.add_item(
                layout.ItemNoticia(
                    titulo=f'<strong>{", ".join(atualizacao.get_tags())}</strong>: {atualizacao.descricao}',
                    chapeu=atualizacao.data.strftime('%d/%m/%Y'),
                    url=f'/demandas/atualizacao/{atualizacao.pk}/',
                )
            )

    return quadro


@layout.quadro('Demandas', icone='info-circle', pode_esconder=True)
def index_quadros_andamento(quadro, request):
    demandas_andamento = Demanda.objects.em_andamento().filter(analistas=request.user)
    if demandas_andamento.exists():
        quadro.add_item(
            layout.ItemContador(
                titulo='Demandas',
                subtitulo='Em andamento',
                qtd=demandas_andamento.count(),
                url=f'/admin/demandas/demanda/?analistas={request.user.id}&tab=tab_em_andamento',
            )
        )
    return quadro


@rtr('demandas/templates/alterar_usuario.html')
@permission_required(['demandas.add_demanda', 'demandas.change_demanda', 'demandas.view_demanda'])
def alterar_usuario(request, tipo, demanda_id):
    title = f'Alterar {tipo.capitalize()} da Demanda'
    demanda = get_object_or_404(Demanda, pk=demanda_id)
    user = request.user
    if request.method == 'POST':
        form = AlterarUsuarioDemandaForm(request.POST or None, instance=demanda, tipo=tipo, user=user)
        if form.is_valid():
            form.save()
            return httprr(demanda.get_absolute_url(), 'Usuários alterados com sucesso.')
    else:
        form = AlterarUsuarioDemandaForm(request.GET or None, instance=demanda, tipo=tipo, user=user)
    return locals()


def __adiciona_afastamento_ou_ferias(usuarios):
    retorno = []
    dia = datetime.today()
    for usuario in usuarios:
        recesso = False
        afastamento_ou_ferias = None
        vinculo = usuario.get_vinculo()
        if vinculo.eh_servidor():
            afastamento_ou_ferias = vinculo.relacionamento.estah_afastado_ou_de_ferias_ateh(dia)
            if 'ponto' in settings.INSTALLED_APPS:
                RecessoDiaEscolhido = apps.get_model('ponto', 'RecessoDiaEscolhido')
                RecessoOpcaoEscolhida = apps.get_model('ponto', 'RecessoOpcaoEscolhida')
                recesso = RecessoDiaEscolhido.objects.filter(
                    recesso_opcao_escolhida__funcionario=vinculo.relacionamento,
                    recesso_opcao_escolhida__validacao=RecessoOpcaoEscolhida.VALIDACAO_AUTORIZADO,
                    dia__data=dia,
                ).exists()
        retorno.append({'usuario': usuario, 'afastamento_ou_ferias': afastamento_ou_ferias, 'recesso': recesso})
    return retorno


def _montar_steps(demanda: Demanda) -> str | None:
    """Régua de etapas da demanda (sem régua para demanda cancelada ou suspensa)."""
    if demanda.situacao in (Situacao.ESTADO_CANCELADO, Situacao.ESTADO_SUSPENSO):
        return None
    steps = '<ul class="steps">'
    for estado, help in list(Situacao.ESTADO_FLUXO.items()):
        if not demanda.pode_desenvolver and estado not in Demanda.situacoes_pre_desenvolvimento():
            continue
        ativa = ' active' if estado == demanda.situacao else ''
        steps += f'<li aria-label="{help}" class="hint hint-bottom"><span class="step-{slugify(estado)}{ativa}">{estado}</span></li>'
    return steps + '</ul>'


def _montar_lista_historico(demanda: Demanda) -> list[dict]:
    """Histórico unificado da demanda: etapas, prioridades, vínculos e revisões, do mais recente ao mais antigo."""
    lista_historico = [
        {
            'data': item.data_hora,
            'usuario': item.usuario,
            'acao': item.situacao,
            'observacoes': item.get_observacoes_historico(),
            'class': item.get_class_situacao,
        }
        for item in demanda.historicosituacao_set.all()
    ]
    lista_historico += [
        {'data': item.data_hora, 'usuario': item.usuario, 'acao': f'Prioridade alterada para {item.prioridade}', 'observacoes': [], 'class': ''}
        for item in demanda.historicoprioridade_set.all()
    ]
    lista_historico += [
        {'data': item.data_hora, 'usuario': item.usuario, 'acao': item.acao, 'observacoes': [], 'class': ''}
        for item in demanda.historicovinculo_set.all()
    ]
    lista_historico += [
        {
            'data': item.data_hora,
            'usuario': item.usuario,
            'acao': item.acao,
            'observacoes': [],
            'class': item.acao == HistoricoRevisao.AVALIACAO_CONCLUIDA and 'success' or 'warning',
        }
        for item in demanda.historicorevisao_set.all()
    ]
    return sorted(lista_historico, key=lambda x: x['data'], reverse=True)


@rtr('demandas/templates/demanda.html')
@permission_required(['demandas.add_demanda', 'demandas.change_demanda', 'demandas.view_demanda'])
@lps
def visualizar(request, demanda_id):
    demanda = get_object_or_404(Demanda, pk=demanda_id)
    user = request.user

    dod = demanda.get_dod()
    if dod is None:
        dod = DoD()
        dod.demanda = demanda
        dod.modulo = ''
        dod.descricao = ''
        dod.envolvidos = ''
        dod.save()

    if not demanda.permite_visualizar(user):
        raise PermissionDenied('Você não tem permissão para visualizar esta demanda.')

    eh_demandante = demanda.eh_demandante(request.user)
    if eh_demandante and demanda.tem_dod and dod.validacao_revisao_solicitada and 'pular_validacao' not in request.GET:
        return httprr(reverse_lazy('validar_modificacoes_dod', kwargs={'pk': dod.id}))

    title = demanda

    voto = DemandaVoto.objects.filter(demanda=demanda, usuario=user)
    if voto.exists():
        voto = voto[0]
    else:
        voto = None

    steps = _montar_steps(demanda)

    hoje = date.today()

    eh_analista = request.user.has_group_cached('Analista')
    eh_desenvolvedor = request.user.has_group_cached('Desenvolvedor')
    eh_demandante_responsavel = demanda.eh_demandante_responsavel(request.user)
    eh_interessado = demanda.eh_interessado(request.user)
    eh_observador_pendente = demanda.eh_observador_pendente(request.user)
    eh_observador = demanda.eh_observador(request.user)

    aprovada = (demanda.em_analise or demanda.ja_foi_aprovada()) and 'collapsed' or ''
    qtd_comentarios = Comentario.objects.filter(
        content_type=ContentType.objects.get(app_label=demanda._meta.app_label, model=demanda._meta.model_name), object_id=demanda.pk, resposta=None
    ).count()
    data_previsao = (
        demanda.get_ultimo_historico_situacao().data_previsao
        and datetime.combine(demanda.get_ultimo_historico_situacao().data_previsao, datetime.max.time())
        or None
    )

    pode_anexar = demanda.pode_anexar(request.user)

    # Monta a lista com as quantidades de demandas que tenha a mesma área de atuação da Demanda Atual
    demandas = Demanda.objects.filter(area=demanda.area)
    lista = []
    em_andamento = demandas.filter(
        situacao__in=[
            Situacao.ESTADO_EM_NEGOCIACAO,
            Situacao.ESTADO_APROVADO,
            Situacao.ESTADO_EM_DESENVOLVIMENTO,
            Situacao.ESTADO_HOMOLOGADA,
            Situacao.ESTADO_EM_IMPLANTACAO,
        ],
    ).count()
    aguardando_feedback = demandas.filter(
        situacao__in=[
            Situacao.ESTADO_EM_ANALISE,
            Situacao.ESTADO_EM_HOMOLOGACAO,
            Situacao.ESTADO_SUSPENSO,
        ],
    ).count()
    nao_iniciadas = demandas.filter(situacao=Situacao.ESTADO_ABERTO).count()
    concluidas = demandas.filter(situacao=Situacao.ESTADO_CONCLUIDO).count()
    lista.append([em_andamento, aguardando_feedback, nao_iniciadas, concluidas])

    exibir_consolidacao = demanda.pode_visualizar_consolidacao(request.user)
    dod_visibilidade = exibir_consolidacao
    pode_exportar_contexto = demanda.eh_analista(request.user)

    pode_add_or_change_especificacao = (
        eh_analista
        or eh_desenvolvedor
        or request.user.has_perm('demandas.add_especificacao')
        or request.user.has_perm('demandas.change_especificacao')
    )

    pode_editar = demanda.pode_editar(request.user)

    demandantes = __adiciona_afastamento_ou_ferias(demanda.demandantes.all())
    analistas = __adiciona_afastamento_ou_ferias(demanda.analistas.all())

    demanda_etapas = demanda.get_etapas(usuario=request.user)

    tem_consolidacao_modificada = dod.revisaoespecificacao_set.exists()

    lista_historico = _montar_lista_historico(demanda)

    qtd_demandas_prioritarias_por_area = DemandaPriorizacao.get_qtd_demandas_prioritarias_por_area()
    # ── Entregas ──────────────────────────────────────────────────────────────
    entregas = demanda.entregas.all().order_by('-enviada_em')
    entrega_pendente = demanda.entrega_pendente
    pode_criar_entrega = request.user.has_perm('demandas.atende_demanda') and demanda.recebe_entregas and not entrega_pendente
    pode_validar_entrega = entrega_pendente and demanda.pode_validar_entrega(request.user, entrega_pendente)
    # Credenciais e acesso ao ambiente: o mesmo público da antiga aba Homologação.
    pode_ver_ambiente = request.user.has_perm('demandas.atende_demanda') or eh_demandante or eh_interessado
    ambiente_homologacao = demanda.ambiente_homologacao_atual
    especificacoes_sem_entrega_aprovada = demanda.get_especificacoes_sem_entrega_aprovada() if demanda.recebe_entregas else None
    pode_criar_subdemanda = True
    # ── Sub-demandas ──────────────────────────────────────────────────────────
    subdemandas = demanda.get_subdemandas() if demanda.eh_raiz else None
    return locals()


@permission_required(['demandas.add_demanda', 'demandas.change_demanda', 'demandas.view_demanda'])
@lps
def exportar_markdown(request: HttpRequest, demanda_id: int) -> HttpResponse:
    demanda = get_object_or_404(Demanda, pk=demanda_id)
    if not demanda.permite_visualizar(request.user):
        raise PermissionDenied('Você não tem permissão para visualizar esta demanda.')

    eh_analista = request.user.has_group_cached('Analista')
    incluir_consolidacao = demanda.pode_visualizar_consolidacao(request.user)
    incluir_especificacao_tecnica = request.user.has_perm('demandas.atende_demanda')

    markdown = DemandaMarkdownExportService.gerar(
        demanda,
        incluir_consolidacao=incluir_consolidacao,
        exibir_revisoes_de_especificacoes=eh_analista,
        exibir_revisoes_sem_especificacao=demanda.pode_revisar_consolidacao(request.user),
        incluir_especificacao_tecnica=incluir_especificacao_tecnica,
    )
    response = HttpResponse(markdown, content_type='text/markdown; charset=utf-8')
    if request.GET.get('download') == '1':
        response['Content-Disposition'] = f'attachment; filename=demanda-{demanda.pk}-{slugify(demanda.titulo)[:80]}.md'
    return response


@rtr()
@login_required()
def concordar_demanda(request, demanda_id):
    demanda = get_object_or_404(Demanda, pk=demanda_id)

    if demanda.pode_votar():
        demanda_voto = DemandaVoto.objects.filter(demanda=demanda, usuario=request.user)
        if demanda_voto.exists():
            voto = demanda_voto[0]
        else:
            voto = DemandaVoto()
            voto.demanda = demanda

        voto.concorda = True
        voto.save()

        return httprr(demanda.get_absolute_url(), 'Voto cadastrado com sucesso.', 'success')
    else:
        return httprr(demanda.get_absolute_url(), 'Não foi possível votar nesta demanda', 'error')


@rtr()
@login_required()
def discordar_demanda(request, demanda_id):
    demanda = get_object_or_404(Demanda, pk=demanda_id)

    if demanda.pode_votar():
        demanda_voto = DemandaVoto.objects.filter(demanda=demanda, usuario=request.user)
        if demanda_voto.exists():
            voto = demanda_voto[0]
        else:
            voto = DemandaVoto()
            voto.demanda = demanda

        voto.concorda = False
        voto.save()

        return httprr(demanda.get_absolute_url(), 'Voto cadastrado com sucesso.', 'success')
    else:
        return httprr(demanda.get_absolute_url(), 'Não foi possível votar nesta demanda', 'error')


@rtr('demandas/templates/formulario.html')
@permission_required(['demandas.atende_demanda', 'demandas.change_demanda'])
def adicionar_anexo(request, demanda_id):
    demanda = get_object_or_404(Demanda, pk=demanda_id)

    if not demanda.pode_anexar(request.user):
        raise PermissionDenied('Você não tem permissão para adicionar anexos.')

    title = demanda
    sub_title = 'Adicionar anexo à demanda'

    form = AnexosForm(request.POST or None, request.FILES or None, demanda=demanda, usuario=request.user)

    if form.is_valid():
        form.save()
        return httprr('{}?tab=anexos'.format(reverse_lazy('demanda_visualizar', kwargs={'demanda_id': demanda.pk})), 'Anexo adicionado com sucesso.')

    return locals()


@rtr()
@permission_required(['demandas.atende_demanda', 'demandas.change_demanda'])
def remover_anexo(request, anexo_id):
    anexo = get_object_or_404(Anexos, pk=anexo_id)
    demanda = anexo.demanda

    if demanda.pode_remover_anexo and (demanda.eh_demandante(request.user) or anexo.demanda.analistas.filter(pk=request.user.pk).exists()):
        anexo.delete()
        return httprr('{}?tab=anexos'.format(reverse_lazy('demanda_visualizar', kwargs={'demanda_id': demanda.pk})), 'Anexo removido com sucesso.')

    raise PermissionDenied('Você não tem permissão para remover anexos neta demanda. Apenas os demandantes e os analistas podem remover anexos.')


@rtr('demandas/templates/formulario.html')
@permission_required('demandas.change_dod')
def dod_alterar(request, demanda_id, dod_id):
    demanda = get_object_or_404(Demanda, pk=demanda_id)
    dod = get_object_or_404(DoD, pk=dod_id)

    title = demanda
    sub_title = 'Editar Consolidação da Demanda'
    url_ret = '{}?tab=dod'.format(reverse_lazy('demanda_visualizar', kwargs={'demanda_id': demanda.pk}))

    if demanda.em_analise:
        return httprr(url_ret, 'Não é possível atualizar uma demanda em análise.', tag='error')

    if demanda.aprovada:
        return httprr(url_ret, 'Não é possível atualizar uma demanda já aprovada.', tag='error')

    if demanda != dod.demanda:
        raise PermissionDenied('Esta consolidação não corresponde à demanda atual.')

    form = DoDForm(request.POST or None, instance=dod)

    if form.is_valid():
        form.save()
        return httprr(url_ret, 'A demanda foi {}.'.format(dod_id and 'atualizada' or 'adicionada'), close_popup=True)

    return locals()


@rtr()
@permission_required('demandas.fechar_dod')
def dod_fechar(request, demanda_id, dod_id):
    title = 'Enviar para Aprovação'

    demanda = get_object_or_404(Demanda, pk=demanda_id)
    dod = get_object_or_404(DoD, pk=dod_id)

    url_ret = '{}?tab=dod'.format(reverse_lazy('demanda_visualizar', kwargs={'demanda_id': demanda.pk}))

    if demanda.em_analise:
        return httprr(url_ret, 'Não é possível enviar uma demanda não consolidada para aprovação.', tag='error')

    if demanda.aprovada:
        return httprr(url_ret, 'Esta demanda já foi aprovada.', tag='error')

    if demanda != dod.demanda:
        raise PermissionDenied('Esta consolidação não corresponde à demanda atual.')

    form = ConfirmarComSenhaForm(request.POST or None, request=request)

    if form.is_valid():
        if not dod.especificacao_set.exists():
            return httprr(url_ret, 'A Consolidação da Demanda deve ter pelo menos uma especificação.', tag='error')

        for especificacao in dod.especificacao_set.all():
            if not especificacao.atividades:
                return httprr(url_ret, 'Existem especificações sem atividades cadastradas.', tag='error')

        if form.cleaned_data['confirmar'] is True:
            demanda.alterar_situacao(
                usuario=request.user,
                situacao=Situacao.ESTADO_EM_ANALISE,
                comentario='Consolidação liberada para análise dos interessados.',
                data_conclusao=date.today(),
            )

        return httprr(url_ret, 'A demanda foi enviada para análise.')

    return locals()


@rtr()
@permission_required('demandas.aprovar_dod')
def dod_aprovar(request, demanda_id, dod_id):
    title = 'Aprovar Demanda'

    demanda = get_object_or_404(Demanda, pk=demanda_id)
    dod = get_object_or_404(DoD, pk=dod_id)

    url_ret = '{}?tab=dod'.format(reverse_lazy('demanda_visualizar', kwargs={'demanda_id': demanda.pk}))

    if not demanda.eh_demandante(request.user):
        return httprr(url_ret, 'Apenas demandantes podem aprovar a consolidação.', tag='error')

    if not demanda.em_analise:
        return httprr(url_ret, 'Não é possível aprovar uma demanda não consolidada.', tag='error')

    if demanda.aprovada:
        return httprr(url_ret, 'Esta demanda já foi aprovada.', tag='error')

    if demanda != dod.demanda:
        raise PermissionDenied('Esta consolidação não corresponde à demanda atual.')

    form = ConfirmarComSenhaForm(request.POST or None, request=request)

    if form.is_valid():
        if form.cleaned_data['confirmar'] is True:
            demanda.alterar_situacao(usuario=request.user, situacao=Situacao.ESTADO_APROVADO, data_conclusao=date.today())

        return httprr(url_ret, 'A consolidação da demanda foi aprovada.')

    return locals()


@rtr()
@permission_required('demandas.aprovar_dod')
def dod_reprovar(request, demanda_id, dod_id):
    title = 'Reprovar Demanda'

    demanda = get_object_or_404(Demanda, pk=demanda_id)
    dod = get_object_or_404(DoD, pk=dod_id)

    url_ret = '{}?tab=dod'.format(reverse_lazy('demanda_visualizar', kwargs={'demanda_id': demanda.pk}))

    if not demanda.eh_demandante(request.user):
        return httprr(url_ret, 'Apenas demandantes podem reprovar a consolidação.', tag='error')

    if not demanda.em_analise:
        return httprr(url_ret, 'Não é possível reprovar uma demanda não consolidada.', tag='error')

    if demanda.aprovada:
        return httprr(url_ret, 'Não é possível reprovar uma demanda já aprovada.', tag='error')

    if demanda != dod.demanda:
        raise PermissionDenied('Esta consolidação não corresponde à demanda atual.')

    form = ConfirmarComSenhaForm(request.POST or None, request=request)

    if form.is_valid():
        if form.cleaned_data['confirmar'] is True:
            demanda.alterar_situacao(
                usuario=request.user,
                situacao=Situacao.ESTADO_EM_NEGOCIACAO,
                comentario='A consolidação da demanda foi reprovada.',
                data_conclusao=date.today(),
            )

        return httprr(url_ret, 'A consolidação da demanda foi reprovada.')

    return locals()


@rtr()
@permission_required('demandas.add_especificacao, demandas.change_especificacao')
def especificacao_add_change(request, demanda_id, dod_id, especificacao_id=None):
    demanda = get_object_or_404(Demanda, pk=demanda_id)
    dod = get_object_or_404(DoD, pk=dod_id)
    especificacao = None

    title = 'Adicionar especificação'

    url_ret = '{}?tab=dod'.format(reverse_lazy('demanda_visualizar', kwargs={'demanda_id': demanda.pk}))

    if demanda.em_analise:
        return httprr(url_ret, 'Não é possível adicionar/alterar uma especificação para uma Consolidação em análise.', tag='error')

    if demanda.aprovada:
        return httprr(url_ret, 'Não é possível adicionar/alterar uma especificação para uma Consolidação aprovada.', tag='error')

    if demanda != dod.demanda:
        raise PermissionDenied('Esta consolidação não corresponde à demanda atual.')

    if especificacao_id:
        title = 'Editar especificação'
        especificacao = get_object_or_404(Especificacao, pk=especificacao_id)

    form = EspecificacaoForm(request.POST or None, instance=especificacao, dod=dod)

    if form.is_valid():
        form.save()
        return httprr(url_ret, f'A especificação foi {especificacao_id and "atualizada" or "adicionada"}.')

    return locals()


@rtr()
@permission_required('demandas.add_especificacao')
def adicionar_revisaoespecificacao(request, dod_id):
    dod = get_object_or_404(DoD, pk=dod_id)
    demanda = dod.demanda
    title = 'Adicionar especificação'
    url_ret = '{}?tab=dod'.format(reverse_lazy('demanda_visualizar', kwargs={'demanda_id': demanda.pk}))
    if not dod.aceita_revisao:
        return httprr(url_ret, 'Não é possível adicionar uma revisão de especificação nesta fase.', tag='error')
    form = RevisaoEspecificacaoForm(request.POST or None, dod=dod)
    if form.is_valid():
        form.save()
        return httprr(url_ret, 'Especificação adicionada com sucesso.')
    return locals()


@rtr()
@permission_required('demandas.add_especificacao')
def editar_revisaoespecificacao(request, pk):
    title = 'Editar revisão da especificação'
    revisao = get_object_or_404(RevisaoEspecificacao, pk=pk)
    demanda = revisao.dod.demanda
    url_ret = '{}?tab=dod'.format(reverse_lazy('demanda_visualizar', kwargs={'demanda_id': demanda.pk}))
    if not revisao.dod.aceita_revisao:
        return httprr(url_ret, 'Não é possível adicionar uma revisão de especificação nesta fase.', tag='error')
    form = RevisaoEspecificacaoForm(request.POST or None, instance=revisao)
    if form.is_valid():
        form.save()
        return httprr(url_ret, 'Especificação adicionada com sucesso.')
    return locals()


@rtr()
@permission_required('demandas.add_especificacao')
def revisar_especificacao(request, pk):
    title = 'Revisar especificação'
    especificacao = get_object_or_404(Especificacao, pk=pk)
    demanda = especificacao.dod.demanda
    url_ret = '{}?tab=dod'.format(reverse_lazy('demanda_visualizar', kwargs={'demanda_id': demanda.pk}))
    if not especificacao.dod.aceita_revisao:
        return httprr(url_ret, 'Não é possível solicitar a remoção de uma especificação nesta fase.', tag='error')
    form = RevisaoEspecificacaoForm(request.POST or None, especificacao=especificacao)
    if form.is_valid():
        form.save()
        return httprr(url_ret, 'Especificação revisada com sucesso.')
    return locals()


@rtr()
@permission_required('demandas.add_especificacao, demandas.aprovar_dod')
def visualizar_especificacao(request, pk):
    especificacao = get_object_or_404(Especificacao, pk=pk)
    title = f'Especificação aprovada {especificacao.ordem}: {especificacao.nome}'
    return locals()


@rtr()
@permission_required('demandas.aprovar_dod')
def aprovar_revisaoespecificacao(request, pk):
    revisao = get_object_or_404(RevisaoEspecificacao, pk=pk)
    url_ret = '{}?tab=dod'.format(reverse_lazy('demanda_visualizar', kwargs={'demanda_id': revisao.dod.demanda_id}))
    if not revisao.dod.demanda.eh_demandante(request.user):
        return httprr(url_ret, 'Você não tem permissão para isso.', 'error')
    revisao.aprovar(request.user)
    return httprr(url_ret, 'Modificação aprovada com sucesso.')


@rtr()
@permission_required('demandas.aprovar_dod')
def reprovar_revisaoespecificacao(request, pk):
    revisao = get_object_or_404(RevisaoEspecificacao, pk=pk)
    url_ret = '{}?tab=dod'.format(reverse_lazy('demanda_visualizar', kwargs={'demanda_id': revisao.dod.demanda_id}))
    if not revisao.dod.demanda.eh_demandante(request.user):
        return httprr(url_ret, 'Você não tem permissão para isso.', 'error')
    revisao.reprovar(request.user)
    return httprr(url_ret, 'Modificação rejeitada com sucesso.')


@rtr()
@permission_required('demandas.add_especificacao')
def solicitar_remocao_especificacao(request, pk):
    especificacao = get_object_or_404(Especificacao, pk=pk)
    demanda = especificacao.dod.demanda
    url_ret = '{}?tab=dod'.format(reverse_lazy('demanda_visualizar', kwargs={'demanda_id': demanda.pk}))
    if not especificacao.dod.aceita_revisao:
        return httprr(url_ret, 'Não é possível remover uma especificação nesta fase.', tag='error')

    revisao = RevisaoEspecificacao()
    revisao.dod = especificacao.dod
    revisao.especificacao = especificacao
    revisao.nome = especificacao.nome
    revisao.atividades = '-'
    revisao.remocao_solicitada = True
    revisao.save()
    return httprr(url_ret, 'Remoção da especificação solicitada com sucesso.')


@permission_required('demandas.add_especificacao')
def solicitar_aprovacao_modificacoes_dod(request, pk):
    dod = get_object_or_404(DoD, pk=pk)
    dod.solicitar_aprovacao_modificacoes(request.user)
    return httprr(f'/demandas/visualizar/{dod.demanda.pk}/?tab=dod', 'Foi solicitada validação das alterações na consolidação.')


@rtr()
@permission_required('demandas.aprovar_dod')
def validar_modificacoes_dod(request, pk):
    demanda = get_object_or_404(Demanda, dod=pk)
    title = f'{demanda}'
    if not demanda.tem_dod or not demanda.get_dod().validacao_revisao_solicitada:
        return httprr(reverse_lazy('demanda_visualizar', kwargs={'demanda_id': pk}))
    eh_demandante = demanda.eh_demandante(request.user)
    modificacoes = RevisaoEspecificacao.objects.filter(dod_id=pk)
    return locals()


@rtr()
@permission_required('demandas.atende_demanda')
def especificacao_tecnica(request, demanda_id):
    demanda = get_object_or_404(Demanda, pk=demanda_id)
    title = 'Especificação Técnica'

    if not demanda.eh_situacao_terminal:
        raise PermissionDenied('Não é possível atualizar a Especificação Técnica para uma Demanda concluída ou cancelada.')

    form = EspecificacaoTecnicaForm(request.POST or None, instance=demanda)

    if form.is_valid():
        form.save()
        return httprr('..', 'A Especificação Técnica foi atualizada.')

    return locals()


@rtr()
@permission_required('demandas.delete_especificacao')
def especificacao_delete(request, demanda_id, dod_id, especificacao_id):
    demanda = get_object_or_404(Demanda, pk=demanda_id)
    dod = get_object_or_404(DoD, pk=dod_id)
    especificacao = get_object_or_404(Especificacao, pk=especificacao_id)

    url_ret = '{}?tab=dod'.format(reverse_lazy('demanda_visualizar', kwargs={'demanda_id': demanda.pk}))

    if demanda.em_analise:
        return httprr(url_ret, 'Não é possível excluir uma especificação para uma Consolidação em análise.', tag='error')

    if demanda.aprovada:
        return httprr(url_ret, 'Não é possível excluir uma especificação para uma Consolidação aprovada.', tag='error')

    if demanda != dod.demanda:
        raise PermissionDenied('Esta consolidação não corresponde à demanda atual.')

    if especificacao.dod != dod:
        raise PermissionDenied('Esta especificação não pertence à esta consolidação da demanda.')

    especificacao.delete()
    dod.atualizar_ordens()

    return httprr(url_ret, 'A especificação foi removida com sucesso.')


def _checar_permissao_alteracao_situacao(user: User, demanda: Demanda, estado: str | None) -> None:
    """Analistas podem alterar qualquer etapa possível; demandantes só podem cancelar."""
    eh_demandante = demanda.eh_demandante(user)
    tem_permissao_atende = user.has_perm('demandas.atende_demanda')

    if not tem_permissao_atende and not eh_demandante:
        raise PermissionDenied('Você não tem permissão para alterar a etapa desta demanda.')

    if eh_demandante and not tem_permissao_atende and estado != Situacao.ESTADO_CANCELADO:
        raise PermissionDenied('Demandantes podem apenas cancelar suas demandas.')

    if estado is None:
        raise PermissionDenied('Etapa escolhida não é válida.')

    if Situacao.eh_estado_terminal(demanda.situacao):
        raise PermissionDenied('Não é possível mudar a etapa atual da demanda.')

    if not Situacao.eh_estado_possivel(demanda, estado, user):
        raise PermissionDenied('Não é possível alterar para a etapa escolhida para esta demanda.')

    if estado not in [Situacao.ESTADO_SUSPENSO, Situacao.ESTADO_CANCELADO] and estado not in Demanda.situacoes_pre_desenvolvimento():
        if not demanda.pode_desenvolver:
            raise PermissionDenied('Etapa escolhida não é válida.')


def _bloqueio_alteracao_situacao(demanda: Demanda, estado: str) -> str | None:
    """Mensagem de erro quando a etapa escolhida é possível, mas a demanda ainda não pode ir para ela."""
    if estado == Situacao.ESTADO_CONCLUIDO and not demanda.pode_concluir_pai:
        subdemandas_ativas = demanda.get_subdemandas_ativas()
        nomes = ', '.join(f'#{s.pk} {s.titulo}' for s in subdemandas_ativas[:3])
        return f'Existem sub-demandas ainda ativas que impedem a conclusão: {nomes}.'

    if estado in [Situacao.ESTADO_EM_ANALISE, Situacao.ESTADO_EM_DESENVOLVIMENTO] and not demanda.tem_dod:
        return 'Não é possível alterar uma demanda para Em Análise caso ela não tenha Consolidação.'
    return None


def _homologar_pela_entrega(usuario: User, demanda: Demanda) -> HttpResponseRedirect:
    """O "Homologar" do menu de etapas é atalho para o cadastro da entrega, já preenchido para entregar tudo."""
    if not demanda.pode_enviar_para_homologacao(usuario):
        raise PermissionDenied('A demanda vai para homologação ao cadastrar uma entrega: só em desenvolvimento e sem entrega pendente.')
    return HttpResponseRedirect(f'{reverse("criar_enrega", kwargs={"demanda_id": demanda.pk})}?homologar=1')


@rtr('demandas/templates/formulario.html')
@permission_required(['demandas.add_demanda'])
def alterar_situacao(request, demanda_id, situacao):
    demanda = get_object_or_404(Demanda, pk=demanda_id)

    estado_atual = demanda.situacao
    estado = Situacao.get_situacao_em_amigavel(situacao)

    title = demanda
    sub_title = f'Alterar etapa de {estado_atual} para {estado}'
    if estado == Situacao.ESTADO_CANCELADO:
        alerta = 'O cancelamento de uma demanda é irreversível.'

    if estado == Situacao.ESTADO_EM_HOMOLOGACAO:
        return _homologar_pela_entrega(request.user, demanda)

    _checar_permissao_alteracao_situacao(request.user, demanda, estado)
    bloqueio = _bloqueio_alteracao_situacao(demanda, estado)
    if bloqueio:
        return httprr(reverse_lazy('demanda_visualizar', kwargs={'demanda_id': demanda.pk}), bloqueio, tag='error')

    FormKlass = SituacaoAlterarFormFactory(
        situacao=estado,
        analistas_demanda=demanda.analistas.all(),
        branch=demanda.branch or '',
    )
    form = FormKlass(request.POST or None)

    if form.is_valid():
        demanda.alterar_situacao(
            usuario=request.user,
            situacao=estado,
            comentario=form.cleaned_data.get('comentario'),
            desenvolvedores=form.cleaned_data.get('desenvolvedores'),
            analistas=form.cleaned_data.get('analistas'),
            data_previsao=form.cleaned_data.get('data_previsao'),
            data_conclusao=form.cleaned_data.get('data_conclusao'),
            id_merge_request=form.cleaned_data.get('id_merge_request'),
            branch=form.cleaned_data.get('branch'),
        )

        return httprr(f'/demandas/visualizar/{demanda.pk}/', 'A etapa da demanda foi alterada.')

    return locals()


@rtr('demandas/templates/formulario.html')
@permission_required(['demandas.add_demanda'])
def editar_data_previsao_etapa(request, demanda_id):
    demanda = get_object_or_404(Demanda, pk=demanda_id)

    title = demanda
    sub_title = f'Alterar Previsão de Conclusão da Etapa {demanda.situacao}'

    if not request.user.has_perm('demandas.atende_demanda'):
        raise PermissionDenied('Você não tem permissão para alterar a etapa desta demanda.')

    if not Situacao.eh_estado_com_data_previsao(demanda.situacao):
        raise PermissionDenied('Não é possível mudar a data de previsão da etapa atual da demanda.')

    form = DataPrevisaoAlterarForm(request.POST or None)

    if form.is_valid():
        demanda.alterar_situacao(
            usuario=request.user,
            situacao=demanda.situacao,
            editou_data_previsao=True,
            comentario=form.cleaned_data.get('comentario'),
            data_previsao=form.cleaned_data.get('data_previsao'),
        )

        return httprr(f'/demandas/visualizar/{demanda.pk}/', f'A data da previsão da etapa {demanda.situacao} foi alterada.', close_popup=True)

    return locals()


@rtr()
@login_required()
def acompanhar(request, demanda_id):
    demanda = get_object_or_404(Demanda, pk=demanda_id)
    if demanda.privada:
        return httprr(f'/demandas/visualizar/{demanda.pk}/', 'Você não pode acompanhar essa demanda por se tratar de uma demanda privada.')

    demanda.observadores_pendentes.add(request.user)
    demanda.save()

    Notificar.solicitacao_observador(demanda)

    return httprr(
        f'/demandas/visualizar/{demanda.pk}/', 'Você solicitou sua inclusão como Observador desta demanda. Aguarde validação pelos demandantes.'
    )


@rtr()
@permission_required('demandas.aprovar_dod')
def adicionar_observador(request, demanda_id, user_id):
    demanda = get_object_or_404(Demanda, pk=demanda_id)
    user = get_object_or_404(User, pk=user_id)
    if demanda.privada:
        return httprr(
            f'/demandas/visualizar/{demanda.pk}/', 'Não é possível adicionar observador nesta demanda por se tratar de uma demanda privada.'
        )
    demanda.observadores_pendentes.remove(user_id)
    demanda.observadores.add(user_id)
    demanda.save()

    Notificar.adicao_como_observador(demanda, user)

    return httprr(f'/demandas/visualizar/{demanda.pk}/', f'O usuário {user.get_profile().nome_usual} foi adicionado como Observador desta demanda.')


@rtr()
@permission_required('demandas.aprovar_dod')
def remover_observador(request, demanda_id, user_id):
    demanda = get_object_or_404(Demanda, pk=demanda_id)
    user = get_object_or_404(User, pk=user_id)

    demanda.observadores_pendentes.remove(user_id)
    demanda.save()

    Notificar.remocao_como_observador_pendente(demanda, user)

    return httprr(
        f'/demandas/visualizar/{demanda.pk}/',
        f'O usuário {user.get_profile().nome_usual} foi removido com sucesso da lista de Observadores Pendentes desta demanda.',
    )


@rtr('demandas/templates/formulario.html')
@permission_required('demandas.add_notainterna')
def nota_interna_add_change(request, demanda_id, notainterna_id=None):
    demanda = get_object_or_404(Demanda, pk=demanda_id)
    nota_interna = None

    title = demanda
    sub_title = 'Adicionar Nota Interna'

    url_ret = '{}?tab=nota_interna'.format(reverse_lazy('demanda_visualizar', kwargs={'demanda_id': demanda.pk}))

    if not (request.user.has_group_cached('Analista') or request.user.has_group_cached('Desenvolvedor')):
        return httprr(url_ret, 'A nota interna é somente para analistas e desenvolvedores.', tag='error')

    if demanda.eh_situacao_terminal():
        return httprr(url_ret, 'Não é possível adicionar/alterar uma nota interna a uma demanda em etapa final.', tag='error')

    if notainterna_id is not None:
        sub_title = 'Alterar Nota Interna'
        nota_interna = get_object_or_404(NotaInterna, pk=notainterna_id)

        if nota_interna.demanda != demanda:
            raise PermissionDenied('Esta nota interna não é da demanda relacionada.')

    form = NotaInternaForm(request.POST or None, instance=nota_interna, demanda=demanda)

    if form.is_valid():
        form.save()
        return httprr('..', 'A nota interna foi {}'.format(nota_interna and 'atualizada.' or 'adicionada.'))

    return locals()


@rtr()
@permission_required('demandas.delete_notainterna')
def nota_interna_delete(request, demanda_id, notainterna_id):
    demanda = get_object_or_404(Demanda, pk=demanda_id)
    nota_interna = get_object_or_404(NotaInterna, pk=notainterna_id)

    url_ret = '{}?tab=nota_interna'.format(reverse_lazy('demanda_visualizar', kwargs={'demanda_id': demanda.pk}))

    if demanda.eh_situacao_terminal():
        return httprr(url_ret, 'Não é possível excluir uma atividade para uma DoD produzida', tag='error')

    if demanda != nota_interna.demanda:
        raise PermissionDenied('Esta nota interna não é da demanda atual.')

    nota_interna.delete()

    return httprr(url_ret, 'A nota interna foi removida com sucesso.')


@rtr()
@permission_required('demandas.view_demanda')
def glossario(request):
    title = 'Glossário'
    return locals()


@rtr()
@permission_required('demandas.visualiza_forca_trabalho')
def painel_forca_trabalho(request):
    title = 'Painel de Força-trabalho'
    ano_atual = date.today().year
    analistas_desenvolvedores = AnalistaDesenvolvedor.objects.filter(ativo=True).order_by('usuario__vinculo__pessoa__pessoafisica__nome_usual')

    # Desenvolvedores por Atualizações
    atualizacoes = Atualizacao.objects.all()
    atualizadores = []
    for atualizador in analistas_desenvolvedores:
        atualizacoes_desenvolvedores = atualizacoes.filter(responsaveis=atualizador.usuario)
        tags = Tag.objects.filter(atualizacao__in=atualizacoes_desenvolvedores).annotate(qtd=Count('atualizacao')).order_by('-qtd')
        if tags.exists():
            atualizadores_tags = []
            for tag in tags:
                atualizadores_tags.append([tag.pk, tag.nome, tag.qtd])
            atualizadores.append(
                [
                    atualizador.usuario_id,
                    atualizador.usuario.get_profile().nome_usual,
                    atualizadores_tags,
                    atualizador.usuario.get_vinculo().get_foto_75x100_url,
                    atualizacoes_desenvolvedores.count(),
                ]
            )

    return locals()


@permission_required('demandas.visualiza_forca_trabalho')
def painel_forca_trabalho_desenvolvedor(request, desenvolvedor_id):
    desenvolvedor = get_object_or_404(AnalistaDesenvolvedor, pk=desenvolvedor_id)

    title = 'Painel de força-trabalho'
    hoje = date.today()
    ano_atual = hoje.year
    demandas_ativas = Demanda.objects.ativas()
    demandas_concluidas = Demanda.objects.filter(situacao=Situacao.ESTADO_CONCLUIDO)
    qtd_demandas_prioritarias_por_area = DemandaPriorizacao.get_qtd_demandas_prioritarias_por_area()

    # Analista
    demandas_prioritarias_a_iniciar = demandas_ativas.filter(
        prioridade__lte=qtd_demandas_prioritarias_por_area,
        situacao__in=[Situacao.ESTADO_ABERTO, Situacao.ESTADO_APROVADO, Situacao.ESTADO_HOMOLOGADA],
    )
    demandas_nao_prioritarias_a_iniciar = demandas_ativas.filter(
        prioridade__gt=qtd_demandas_prioritarias_por_area, situacao__in=[Situacao.ESTADO_ABERTO, Situacao.ESTADO_APROVADO, Situacao.ESTADO_HOMOLOGADA]
    )
    demandas_prioritarias_em_andamento = demandas_ativas.filter(
        prioridade__lte=qtd_demandas_prioritarias_por_area,
        situacao__in=[Situacao.ESTADO_EM_NEGOCIACAO, Situacao.ESTADO_EM_DESENVOLVIMENTO, Situacao.ESTADO_EM_IMPLANTACAO],
    )
    demandas_nao_prioritarias_em_andamento = demandas_ativas.filter(
        prioridade__gt=qtd_demandas_prioritarias_por_area,
        situacao__in=[Situacao.ESTADO_EM_NEGOCIACAO, Situacao.ESTADO_EM_DESENVOLVIMENTO, Situacao.ESTADO_EM_IMPLANTACAO],
    )
    demandas_prioritarias_aguardando_feedback = demandas_ativas.filter(
        prioridade__lte=qtd_demandas_prioritarias_por_area,
        situacao__in=[Situacao.ESTADO_EM_ANALISE, Situacao.ESTADO_SUSPENSO, Situacao.ESTADO_EM_HOMOLOGACAO],
    )
    demandas_nao_prioritarias_aguardando_feedback = demandas_ativas.filter(
        prioridade__gt=qtd_demandas_prioritarias_por_area,
        situacao__in=[Situacao.ESTADO_EM_ANALISE, Situacao.ESTADO_SUSPENSO, Situacao.ESTADO_EM_HOMOLOGACAO],
    )

    # Afastamento ou Ferias
    vinculo = desenvolvedor.usuario.get_vinculo()
    if vinculo.eh_servidor():
        dia = datetime.today()
        afastamento_ou_ferias = vinculo.relacionamento.estah_afastado_ou_de_ferias_ateh(dia)
        recesso = vinculo.relacionamento.estah_em_recesso(dia)

    # Atraso
    demandas_em_andamento_desenvolvedor = demandas_prioritarias_em_andamento.filter(analistas=desenvolvedor.usuario)
    em_atraso = False
    tags = set()
    for atrasada in demandas_em_andamento_desenvolvedor:
        for tag in atrasada.tags.all():
            tags.add(tag.nome)
        if atrasada.em_atraso():
            em_atraso = True

    # Demandas
    qtd_prioritarias_a_iniciar = demandas_prioritarias_a_iniciar.filter(analistas=desenvolvedor.usuario).count()
    qtd_nao_prioritarias_a_iniciar = demandas_nao_prioritarias_a_iniciar.filter(analistas=desenvolvedor.usuario).count()
    qtd_prioritarias_em_andamento = demandas_prioritarias_em_andamento.filter(analistas=desenvolvedor.usuario).count()
    qtd_nao_prioritarias_em_andamento = demandas_nao_prioritarias_em_andamento.filter(analistas=desenvolvedor.usuario).count()
    qtd_prioritarias_aguardando_feedback = demandas_prioritarias_aguardando_feedback.filter(analistas=desenvolvedor.usuario).count()
    qtd_nao_prioritarias_aguardando_feedback = demandas_nao_prioritarias_aguardando_feedback.filter(analistas=desenvolvedor.usuario).count()
    qtd_concluidas = demandas_concluidas.filter(analistas=desenvolvedor.usuario, data_atualizacao__year=ano_atual).count()
    qtd_demandas_prioritarias = qtd_prioritarias_a_iniciar + qtd_prioritarias_em_andamento + qtd_prioritarias_aguardando_feedback
    qtd_demandas_nao_prioritarias = qtd_nao_prioritarias_a_iniciar + qtd_nao_prioritarias_em_andamento + qtd_nao_prioritarias_aguardando_feedback
    qtd_demandas = qtd_demandas_prioritarias + qtd_demandas_nao_prioritarias

    # Gitlab
    projetos_issues = []
    qtd_tarefas = 0
    git = gitlab.Gitlab(
        Configuracao.get_valor_por_chave('demandas', 'gitlab_url'),
        private_token=Configuracao.get_valor_por_chave('demandas', 'gitlab_token'),
        timeout=60,
    )
    qtd_issues_concluidas_ano = 0
    qtd_issues_atualizadas_7dias = 0
    qtd_issues_atualizadas_14dias = 0
    for projeto in ProjetoGitlab.objects.filter(ativo=True):
        qtd_issues = 0
        try:
            project = git.projects.get(projeto.id_projeto_gitlab)
            extra_params = {'not[labels]': 'Waiting Feedback'}
            for milestone in project.milestones.list(get_all=True, iterator=False, state='active'):
                qtd_issues = len(
                    git.projects.get(projeto.id_projeto_gitlab).issues.list(
                        milestone=milestone.title,
                        assignee_username=desenvolvedor.username_gitlab,
                        state='opened',
                        iterator=False,
                        get_all=True,
                        **extra_params,
                    )
                )
                qtd_tarefas += qtd_issues
                projetos_issues.append(
                    (
                        f'{projeto.nome_projeto} - {milestone.title}',
                        qtd_issues,
                        desenvolvedor.get_url_issues_em_andamento_projeto(projeto, milestone.title),
                    )
                )

            qtd_issues = len(
                git.projects.get(projeto.id_projeto_gitlab).issues.list(
                    milestone='None', assignee_username=desenvolvedor.username_gitlab, state='opened', iterator=False, get_all=True, **extra_params
                )
            )
            qtd_tarefas += qtd_issues
            projetos_issues.append(
                (f'{projeto.nome_projeto} - Sem milestone', qtd_issues, desenvolvedor.get_url_issues_em_andamento_projeto(projeto, 'None'))
            )

            qtd_issues_concluidas_ano += len(
                git.projects.get(projeto.id_projeto_gitlab).issues.list(
                    assignee_username=desenvolvedor.username_gitlab, state='closed', updated_after=date(hoje.year, 1, 1), iterator=False, get_all=True
                )
            )
            qtd_issues_atualizadas_7dias += len(
                git.projects.get(projeto.id_projeto_gitlab).issues.list(
                    assignee_username=desenvolvedor.username_gitlab, updated_after=hoje - timedelta(7), iterator=False, get_all=True
                )
            )
            qtd_issues_atualizadas_14dias += len(
                git.projects.get(projeto.id_projeto_gitlab).issues.list(
                    assignee_username=desenvolvedor.username_gitlab, updated_after=hoje - timedelta(14), iterator=False, get_all=True
                )
            )
        except GitlabError, ConnectionError:
            continue

    issues_desenvolvedor_em_andamento = projetos_issues

    # Chamados
    qtd_chamados = 0
    if 'centralservicos' in settings.INSTALLED_APPS:
        from centralservicos.models import Chamado

        chamados = Chamado.get_chamados_do_suporte(user=request.user, atribuicoes=Chamado.ATRIBUIDOS_A_OUTROS, atendente=desenvolvedor.usuario)
        qtd_chamados = chamados.count()

    # Erros
    qtd_erros = 0
    if 'erros' in settings.INSTALLED_APPS:
        from erros.models import Erro

        qtd_erros = Erro.objects.filter(atendente_atual_id=vinculo.pk, situacao=Erro.SITUACAO_EM_ANALISE).count()

    # Total
    total = qtd_prioritarias_a_iniciar + qtd_prioritarias_em_andamento + qtd_nao_prioritarias_em_andamento + qtd_tarefas + qtd_chamados + qtd_erros

    # Situação
    situacao = 'Ocupado'
    if total == 0:
        situacao = 'Disponível'
    elif qtd_prioritarias_em_andamento == 0 and qtd_tarefas == 0 and qtd_chamados == 0:
        situacao = 'Ocioso'
    elif em_atraso:
        situacao = 'Atrasado'

    ordem = f'{total:d}.{qtd_prioritarias_em_andamento:02d}'

    html = render_to_string('demandas/templates/painel_forca_trabalho_desenvolvedor.html', locals())
    return JsonResponse({'html': html, 'ordem': ordem, 'total': total})


def _acompanhamento_demandas_e_erros(data_inicio: date, data_fim: date, area: AreaAtuacaoDemanda = None) -> dict:
    # Demandas.
    demandas_criadas = Demanda.get_demandas_criadas(data_inicio, data_fim, area).order_by('aberto_em')
    demandas_atualizadas = Demanda.get_demandas_atualizadas(data_inicio, data_fim, area).order_by('data_atualizacao')
    demandas_abertas = demandas_atualizadas.filter(situacao=Situacao.ESTADO_ABERTO)
    demandas_suspensas = demandas_atualizadas.filter(situacao=Situacao.ESTADO_SUSPENSO)
    demandas_canceladas = demandas_atualizadas.filter(situacao=Situacao.ESTADO_CANCELADO)
    demandas_concluidas = demandas_atualizadas.filter(situacao=Situacao.ESTADO_CONCLUIDO)
    if area:
        demandas_prioritarias = DemandaPriorizacao.get_prioritarias_da_area(area).order_by('area', 'prioridade', 'data_atualizacao')
    else:
        demandas_prioritarias = Demanda.objects.none()
    demandas_envolvidas = (demandas_criadas | demandas_atualizadas | demandas_prioritarias).distinct().order_by('id')
    qtd_demandas_criadas = demandas_criadas.count()
    qtd_demandas_abertas = demandas_abertas.count()
    qtd_demandas_suspensas = demandas_suspensas.count()
    qtd_demandas_canceladas = demandas_canceladas.count()
    qtd_demandas_concluidas = demandas_concluidas.count()
    qtd_demandas_prioritarias = demandas_prioritarias.count()
    qtd_demandas_envolvidas = demandas_envolvidas.count()

    # Erros.
    if 'erros' in settings.INSTALLED_APPS:
        from erros.models import Erro

        modulos_afetados = [app for tag in area.tags_relacionadas.all() for app in tag.apps_relacionadas_as_list] if area else None
        erros_criados = Erro.get_erros_criados(data_inicio, data_fim, modulos_afetados).order_by('data_criacao')
        erros_atualizados = Erro.get_erros_atualizados(data_inicio, data_fim, modulos_afetados).order_by('data_ultima_alteracao')
        erros_abertos = erros_atualizados.filter(situacao__in=[Erro.SITUACAO_ABERTO, Erro.SITUACAO_REABERTO])
        erros_cancelados = erros_atualizados.filter(situacao=Erro.SITUACAO_CANCELADO)
        erros_resolvidos = erros_atualizados.filter(situacao=Erro.SITUACAO_RESOLVIDO)
        erros_envolvidos = (erros_criados | erros_atualizados).distinct().order_by('id')
        qtd_erros_criados = erros_criados.count()
        qtd_erros_abertos = erros_abertos.count()
        qtd_erros_cancelados = erros_cancelados.count()
        qtd_erros_resolvidos = erros_resolvidos.count()
        qtd_erros_envolvidos = erros_envolvidos.count()

    return locals()


@rtr()
@permission_required('demandas.pode_relatorio')
def acompanhamento_demandas(request):
    title = 'Relatório de Acompanhamento de Demandas e Erros'
    form = AcompanhamentoForm(request.GET or None)
    ctx = {}
    if form.is_valid():
        inicio = form.cleaned_data.get('inicio')
        fim = form.cleaned_data.get('fim')
        area = form.cleaned_data.get('area')
        ctx = _acompanhamento_demandas_e_erros(inicio, fim, area)
    ctx.update(locals())
    return ctx


@documento()
@rtr()
@permission_required('demandas.pode_relatorio')
def acompanhamento_demandas_pdf(request):
    title = 'Relatório de Acompanhamento de Demandas e Erros'

    try:
        inicio = datetime.strptime(request.GET.get('inicio'), '%Y%m%d').date()
        fim = datetime.strptime(request.GET.get('fim'), '%Y%m%d').date()
    except Exception:
        return httprr(
            '/demandas/acompanhamento_demandas',
            'Parâmetros inválidos para o relatório.',
            'alert',
        )

    area_pk = request.GET.get('area')

    area = None
    if area_pk:
        area = AreaAtuacaoDemanda.objects.filter(pk=area_pk).first()

    ctx = _acompanhamento_demandas_e_erros(inicio, fim, area)

    if area:
        qtd_demandas_nao_prioritarias = DemandaPriorizacao.get_ativas_da_area(area).difference(ctx['demandas_prioritarias']).count()

    ctx.update(locals())

    return ctx


def _get_demandas_por_area(demandas_ativas, demandas_concluidas_ano, areas, prefetch_relateds):
    qtd_demandas_prioritarias_por_area = DemandaPriorizacao.get_qtd_demandas_prioritarias_por_area()
    prioritarias = []
    for area in areas:
        total_demandas_area = demandas_ativas.filter(area=area, prioridade__gte=0).prefetch_related(*prefetch_relateds).order_by('prioridade')
        demandas_prioritarias = total_demandas_area[:qtd_demandas_prioritarias_por_area]
        quantidade_demandas_prioritarias = demandas_prioritarias.count()
        if quantidade_demandas_prioritarias:
            qtd_demandas_concluidas_area = demandas_concluidas_ano.filter(area=area).count()
            prioritarias.append(
                [
                    area,
                    demandas_prioritarias,
                    qtd_demandas_prioritarias_por_area - quantidade_demandas_prioritarias,
                    qtd_demandas_concluidas_area,
                    total_demandas_area.count(),
                    area.demandante_responsavel,
                ]
            )
    return prioritarias


@rtr()
@permission_required('demandas.view_demanda')
def demandas(request):
    title = 'Dashboard: Demandas'
    ano_atual = date.today().year
    ano_passado = ano_atual - 1
    eh_demandante = request.user.has_group_cached('Demandante') and AreaAtuacaoDemanda.objects.filter(
        Q(demandantes=request.user) | Q(demandante_responsavel=request.user)
    )
    eh_analista = request.user.has_group_cached('Analista')
    eh_desenvolvedor = request.user.has_group_cached('Desenvolvedor')

    # Pendências
    pode_ver_pendencias = request.user.has_group_cached('Recebedor de Demandas') or request.user.has_group_cached('Coordenador de Sistemas')
    group = Group.objects.get(name='Demandante')
    demandantes = User.objects.filter(is_active=True, groups=group)
    demandantes_sem_areas = []
    for demandante in demandantes:
        if not AreaAtuacaoDemanda.objects.filter(Q(demandantes=demandante) | Q(demandante_responsavel=demandante)).exists():
            demandantes_sem_areas.append(demandante)

    qtd_demandas_prioritarias_por_area = DemandaPriorizacao.get_qtd_demandas_prioritarias_por_area()

    prefetch_relateds = ['historicosituacao_set', 'dod_set', 'dod_set__especificacao_set', 'analistas', 'demandantes']
    # Estatísticas
    demandas_ativas = Demanda.objects.ativas().prefetch_related(*prefetch_relateds)
    demandas_nao_prioritarias = demandas_ativas.filter(prioridade__gt=qtd_demandas_prioritarias_por_area)
    demandas_concluidas = Demanda.objects.filter(situacao=Situacao.ESTADO_CONCLUIDO).prefetch_related(*prefetch_relateds)
    demandas_concluidas_ano = demandas_concluidas.filter(data_atualizacao__year=ano_atual)
    demandas_concluidas_ano_passado = demandas_concluidas.filter(data_atualizacao__year=ano_passado)
    qtd_demandas_concluidas_ano_passado = demandas_concluidas.filter(data_atualizacao__year=ano_passado).count()
    qtd_demandas_concluidas_ano = demandas_concluidas_ano.count()
    if qtd_demandas_concluidas_ano_passado > 0:
        percent_demandas_concluidas_ano = qtd_demandas_concluidas_ano * 100 / qtd_demandas_concluidas_ano_passado
    else:
        percent_demandas_concluidas_ano = 0
    melhorias = demandas_ativas.filter(tipo=TipoDemanda.MELHORIA).count()
    funcionalidades = demandas_ativas.filter(tipo=TipoDemanda.FUNCIONALIDADE).count()
    demandas_solicitadas = demandas_nao_prioritarias.filter(situacao=Situacao.ESTADO_ABERTO).count()
    demandas_em_negociacao = demandas_nao_prioritarias.filter(situacao=Situacao.ESTADO_EM_NEGOCIACAO).count()
    demandas_em_analise = demandas_nao_prioritarias.filter(situacao=Situacao.ESTADO_EM_ANALISE).count()
    demandas_aprovadas = demandas_nao_prioritarias.filter(situacao=Situacao.ESTADO_APROVADO).count()
    demandas_homologadas = demandas_nao_prioritarias.filter(situacao=Situacao.ESTADO_HOMOLOGADA).count()
    demandas_em_homologacao = demandas_nao_prioritarias.filter(situacao=Situacao.ESTADO_EM_HOMOLOGACAO).count()
    demandas_em_implantacao = demandas_nao_prioritarias.filter(situacao=Situacao.ESTADO_EM_IMPLANTACAO).count()
    demandas_suspensas = demandas_ativas.filter(situacao=Situacao.ESTADO_SUSPENSO).count()
    qtd_demandas_ativas = demandas_ativas.count()
    if qtd_demandas_ativas:
        percent_demandas_suspensas = demandas_suspensas * 100 / qtd_demandas_ativas
    else:
        percent_demandas_suspenas = 0
    total_demandas = Demanda.objects.exclude(situacao=Situacao.ESTADO_CANCELADO).count()
    demandas_atrasadas_demandantes = 0
    demandas_atrasadas_desenvolvimento = 0
    for atrasada in demandas_ativas:
        historico_situacao = atrasada.get_ultimo_historico_situacao()
        if historico_situacao and historico_situacao.data_previsao:
            hoje = date.today()
            historico_situacao = atrasada.get_ultimo_historico_situacao()
            if historico_situacao.data_previsao < hoje and not historico_situacao.data_conclusao:
                if atrasada.situacao in [Situacao.ESTADO_EM_ANALISE, Situacao.ESTADO_EM_HOMOLOGACAO]:
                    demandas_atrasadas_demandantes += 1
                elif atrasada.situacao in [Situacao.ESTADO_EM_DESENVOLVIMENTO, Situacao.ESTADO_EM_IMPLANTACAO]:
                    demandas_atrasadas_desenvolvimento += 1

    # Demandas Prioritárias
    total_demandas_prioritarias = demandas_ativas.filter(prioridade__lte=qtd_demandas_prioritarias_por_area).count()
    prioritarias = []
    todas_areas = AreaAtuacaoDemanda.objects.all().order_by('area__nome').select_related('area', 'demandante_responsavel')
    prioritarias = _get_demandas_por_area(demandas_ativas, demandas_concluidas_ano, todas_areas, prefetch_relateds)
    if eh_demandante:
        minhas_areas = todas_areas.filter(demandantes__in=[request.user])
        minhas_prioritarias = []
        [minhas_prioritarias.append(prioritaria) for prioritaria in prioritarias if prioritaria[0] in minhas_areas]
        # minhas_areas = todas_areas.filter(demandantes__in=[request.user])
        # minhas_prioritarias = _get_demandas_por_area(demandas_ativas, demandas_concluidas_ano, minhas_areas, prefetch_relateds)

    qtd_demandas_prioritarias_por_area_range = range(1, qtd_demandas_prioritarias_por_area + 1)
    areas_pode_alterar_prioridade = []
    for area in request.user.demandanteresponsavelarea.all().select_related('area'):
        areas_pode_alterar_prioridade.append({'url': reverse('demandas_prioritarias_por_area', args=(area.pk,)), 'label': f'{area.area}'})

    entregas_pendentes = (
        Entrega.objects.filter(status='ENVIADA').select_related('demanda', 'demanda__area', 'cadastrada_por').order_by('prazo_feedback')
    )

    entregas_vencidas = entregas_pendentes.filter(prazo_feedback__lt=date.today())

    qtd_entregas_pendentes = entregas_pendentes.count()
    qtd_entregas_vencidas = entregas_vencidas.count()
    return locals()


@rtr()
@permission_required('demandas.pode_relatorio')
def indicadores(request):
    title = 'Indicadores'
    form = DashboardForm(request.POST or None)
    demandas = Demanda.objects.all()
    demandas_ativas = Demanda.objects.ativas()
    demandas_em_andamento = Demanda.objects.em_andamento()
    demandas_aguardando_feedback = Demanda.objects.aguardando_feedback()
    atualizacoes = Atualizacao.objects.all()
    lista_desenvolvedores = UsuarioGrupo.objects.filter(group__name='Desenvolvedor')
    form_tag = None

    if form.is_valid():
        inicio = None
        if form.cleaned_data.get('inicio'):
            inicio = form.cleaned_data['inicio']

        final = None
        if form.cleaned_data.get('final'):
            final = form.cleaned_data['final']

        if inicio or final:
            if inicio and not final:
                demandas = demandas.filter(data_atualizacao__gte=inicio)
                demandas_ativas = demandas_ativas.filter(data_atualizacao__gte=inicio)
                demandas_em_andamento = demandas_em_andamento.filter(data_atualizacao__gte=inicio)
                demandas_aguardando_feedback = demandas_aguardando_feedback.filter(data_atualizacao__gte=inicio)
                atualizacoes = atualizacoes.filter(data__gte=inicio)
            elif final and not inicio:
                demandas = demandas.filter(data_atualizacao__lte=final)
                demandas_ativas = demandas_ativas.filter(data_atualizacao__lte=final)
                demandas_em_andamento = demandas_em_andamento.filter(data_atualizacao__lte=final)
                demandas_aguardando_feedback = demandas_aguardando_feedback.filter(data_atualizacao__lte=final)
                atualizacoes = atualizacoes.filter(data__lte=final)
            else:
                demandas = demandas.filter(data_atualizacao__range=(inicio, final))
                demandas_ativas = demandas_ativas.filter(data_atualizacao__range=(inicio, final))
                demandas_em_andamento = demandas_em_andamento.filter(data_atualizacao__range=(inicio, final))
                demandas_aguardando_feedback = demandas_aguardando_feedback.filter(data_atualizacao__range=(inicio, final))
                atualizacoes = atualizacoes.filter(data__range=(inicio, final))

        if form.cleaned_data.get('tag'):
            form_tag = form.cleaned_data['tag']
            demandas = demandas.filter(tags=form_tag)
            demandas_ativas = demandas_ativas.filter(tags=form_tag)
            demandas_em_andamento = demandas_em_andamento.filter(tags=form_tag)
            demandas_aguardando_feedback = demandas_aguardando_feedback.filter(tags=form_tag)
            atualizacoes = atualizacoes.filter(tags=form_tag)

    # Gráfico com as situações das demandas
    dados_grafico_demandas_por_situacao = []
    for demanda in demandas.order_by('situacao').values('situacao').annotate(Count('situacao')):
        dados_grafico_demandas_por_situacao.append([demanda['situacao'], demanda['situacao__count']])
    grafico_demandas_por_situacao = PieChart(
        'grafico_demandas_por_situacao',
        title='Demandas por Etapa',
        subtitle='Quantitativo de Demandas',
        minPointLength=0,
        data=dados_grafico_demandas_por_situacao,
    )

    # Gráfico com demandas por tags
    dados_grafico_demandas_por_tags = []
    tags = Tag.objects.filter(demanda_tags_set__in=demandas).annotate(qtd=Count('demanda_tags_set'))
    for tag in tags:
        dados_grafico_demandas_por_tags.append([tag.nome, tag.qtd])
    grafico_demandas_por_tags = PieChart(
        'grafico_demandas_por_tags',
        title='Demandas por Tags',
        subtitle='Quantitativo de Demandas',
        minPointLength=0,
        data=dados_grafico_demandas_por_tags,
    )

    # Gráfico com as situações por área de atuação de demandas
    grupos_situacoes = [
        Situacao.ESTADO_ABERTO,
        Situacao.ESTADO_EM_NEGOCIACAO,
        Situacao.ESTADO_EM_ANALISE,
        Situacao.ESTADO_APROVADO,
        Situacao.ESTADO_EM_DESENVOLVIMENTO,
        Situacao.ESTADO_EM_HOMOLOGACAO,
        Situacao.ESTADO_HOMOLOGADA,
        Situacao.ESTADO_EM_IMPLANTACAO,
        Situacao.ESTADO_CONCLUIDO,
        Situacao.ESTADO_SUSPENSO,
        Situacao.ESTADO_CANCELADO,
    ]
    dict_situacao_por_area = {}
    for demanda in demandas.order_by('area__area__nome'):
        if demanda.area:
            if demanda.area.area.nome not in dict_situacao_por_area:
                order = OrderedDict()
                order['nome'] = demanda.area.area.nome
                order[Situacao.ESTADO_ABERTO] = 0
                order[Situacao.ESTADO_EM_NEGOCIACAO] = 0
                order[Situacao.ESTADO_EM_ANALISE] = 0
                order[Situacao.ESTADO_APROVADO] = 0
                order[Situacao.ESTADO_EM_DESENVOLVIMENTO] = 0
                order[Situacao.ESTADO_EM_HOMOLOGACAO] = 0
                order[Situacao.ESTADO_HOMOLOGADA] = 0
                order[Situacao.ESTADO_EM_IMPLANTACAO] = 0
                order[Situacao.ESTADO_CONCLUIDO] = 0
                order[Situacao.ESTADO_SUSPENSO] = 0
                order[Situacao.ESTADO_CANCELADO] = 0
                dict_situacao_por_area[demanda.area.area.nome] = order

            dict_situacao_por_area[demanda.area.area.nome][demanda.situacao] += 1

    grafico_situacoes_por_tags = GroupedColumnChart(
        'grafico_situacoes_por_tags',
        title='Etapas por Áreas de Atuação',
        subtitle='Quantitativo de Demandas',
        data=[list(lista.values()) for lista in list(dict_situacao_por_area.values())],
        groups=grupos_situacoes,
        plotOptions_line_dataLabels_enable=True,
        plotOptions_line_enableMouseTracking=True,
    )

    # Gráfico com as força de trabalho dos analistas
    dados_grafico_analista = []
    grupos_situacoes = [
        Situacao.ESTADO_ABERTO,
        Situacao.ESTADO_EM_NEGOCIACAO,
        Situacao.ESTADO_EM_ANALISE,
        Situacao.ESTADO_APROVADO,
        Situacao.ESTADO_EM_DESENVOLVIMENTO,
        Situacao.ESTADO_EM_HOMOLOGACAO,
        Situacao.ESTADO_HOMOLOGADA,
        Situacao.ESTADO_EM_IMPLANTACAO,
        Situacao.ESTADO_CONCLUIDO,
        Situacao.ESTADO_SUSPENSO,
        Situacao.ESTADO_CANCELADO,
    ]
    dict_analistas = {}
    for demanda in demandas.order_by('analistas__username'):
        for analista in demanda.analistas.all():
            if analista.username not in dict_analistas:
                order = OrderedDict()
                order['nome'] = analista.get_profile().nome_usual
                order[Situacao.ESTADO_ABERTO] = 0
                order[Situacao.ESTADO_EM_NEGOCIACAO] = 0
                order[Situacao.ESTADO_EM_ANALISE] = 0
                order[Situacao.ESTADO_APROVADO] = 0
                order[Situacao.ESTADO_EM_DESENVOLVIMENTO] = 0
                order[Situacao.ESTADO_EM_HOMOLOGACAO] = 0
                order[Situacao.ESTADO_HOMOLOGADA] = 0
                order[Situacao.ESTADO_EM_IMPLANTACAO] = 0
                order[Situacao.ESTADO_CONCLUIDO] = 0
                order[Situacao.ESTADO_SUSPENSO] = 0
                order[Situacao.ESTADO_CANCELADO] = 0
                dict_analistas[analista.username] = order

            dict_analistas[analista.username][demanda.situacao] += 1

    dados_grafico_analistas = GroupedColumnChart(
        'div_grafico_analistas',
        title='Etapas por Analistas',
        subtitle='Quantitativo de Demandas',
        data=[list(lista.values()) for lista in list(dict_analistas.values())],
        groups=grupos_situacoes,
        plotOptions_line_dataLabels_enable=True,
        plotOptions_line_enableMouseTracking=True,
    )

    # Monta força tarefa - Desenvolvedores
    grafico_desenvolvedores = {}
    dict_desenvolvedores = {}

    for demanda in demandas.order_by('desenvolvedores__username'):
        for desenvolvedor in demanda.desenvolvedores.all():
            if desenvolvedor.username not in dict_desenvolvedores:
                order = OrderedDict()
                order['nome'] = desenvolvedor.get_profile().nome_usual
                order[Situacao.ESTADO_ABERTO] = 0
                order[Situacao.ESTADO_EM_NEGOCIACAO] = 0
                order[Situacao.ESTADO_EM_ANALISE] = 0
                order[Situacao.ESTADO_APROVADO] = 0
                order[Situacao.ESTADO_EM_DESENVOLVIMENTO] = 0
                order[Situacao.ESTADO_EM_HOMOLOGACAO] = 0
                order[Situacao.ESTADO_HOMOLOGADA] = 0
                order[Situacao.ESTADO_EM_IMPLANTACAO] = 0
                order[Situacao.ESTADO_CONCLUIDO] = 0
                order[Situacao.ESTADO_SUSPENSO] = 0
                order[Situacao.ESTADO_CANCELADO] = 0
                dict_desenvolvedores[desenvolvedor.username] = order

            dict_desenvolvedores[desenvolvedor.username][demanda.situacao] += 1

    dados_grafico_desenvolvedores = GroupedColumnChart(
        'div_grafico_desenvolvedores',
        title='Etapas por Desenvolvedores',
        subtitle='Quantitativo de Demandas',
        data=[list(lista.values()) for lista in list(dict_desenvolvedores.values())],
        groups=grupos_situacoes,
        plotOptions_line_dataLabels_enable=True,
        plotOptions_line_enableMouseTracking=True,
    )

    # Gráficos de Atualizações
    dados_grafico_tags = []
    tags = Tag.objects.filter(atualizacao__in=atualizacoes).annotate(qtd=Count('atualizacao'))
    for tag in tags:
        dados_grafico_tags.append([tag.nome, tag.qtd])
    grafico_tags = PieChart('grafico_tags', title='Quantitativo de Atualizações por Tags', minPointLength=0, data=dados_grafico_tags)

    dados_grafico_tipos = []
    tags = Tag.objects.filter(id__in=atualizacoes.values_list('tags', flat=True))
    for tag in tags:
        serie = [
            tag.nome,
            atualizacoes.filter(tags=tag, tipo=Atualizacao.FUNCIONALIDADE).count(),
            atualizacoes.filter(tags=tag, tipo=Atualizacao.MANUTENCAO).count(),
            atualizacoes.filter(tags=tag, tipo=Atualizacao.BUG).count(),
        ]
        dados_grafico_tipos.append(serie)

    grafico_tipos = GroupedColumnChart(
        'grafico_tipos',
        title='Tipo por Tags',
        subtitle='Quantitativo de Atualizações',
        data=dados_grafico_tipos,
        groups=[Atualizacao.FUNCIONALIDADE, Atualizacao.MANUTENCAO, Atualizacao.BUG],
        plotOptions_line_dataLabels_enable=True,
        plotOptions_line_enableMouseTracking=True,
    )

    if not form_tag:
        dados_grafico_tipo_funcionalidade = []
        qs = atualizacoes.filter(tipo=Atualizacao.FUNCIONALIDADE)
        tags = Tag.objects.filter(atualizacao__in=qs).annotate(qtd=Count('atualizacao'))
        for tag in tags:
            dados_grafico_tipo_funcionalidade.append([tag.nome, tag.qtd])
        grafico_tipo_funcionalidade = PieChart(
            'grafico_tipo_funcionalidade',
            title='Quantitativo de Atualizações de Funcionalidades',
            minPointLength=0,
            data=dados_grafico_tipo_funcionalidade,
        )

        dados_grafico_tipo_manutencao = []
        qs = atualizacoes.filter(tipo=Atualizacao.MANUTENCAO)
        tags = Tag.objects.filter(atualizacao__in=qs).annotate(qtd=Count('atualizacao'))
        for tag in tags:
            dados_grafico_tipo_manutencao.append([tag.nome, tag.qtd])
        grafico_tipo_manutencao = PieChart(
            'grafico_tipo_manutencao', title='Quantitativo de Atualizações de Manutenção', minPointLength=0, data=dados_grafico_tipo_manutencao
        )

        dados_grafico_tipo_bug = []
        qs = atualizacoes.filter(tipo=Atualizacao.BUG)
        tags = Tag.objects.filter(atualizacao__in=qs).annotate(qtd=Count('atualizacao'))
        for tag in tags:
            dados_grafico_tipo_bug.append([tag.nome, tag.qtd])
        grafico_tipo_bug = PieChart('grafico_tipo_bug', title='Quantitativo de Atualizações de Bugs', minPointLength=0, data=dados_grafico_tipo_bug)

    return locals()


@rtr()
@permission_required('demandas.pode_relatorio')
def relatorio_geral(request):
    title = 'Relatório de Demandas por Tags (XLS)'

    form = RelatorioForm(request.POST or None)

    if form.is_valid():
        dt_inicio = form.cleaned_data['inicio']
        dt_final = form.cleaned_data['final']

        demandas = Demanda.objects.filter(data_atualizacao__gte=dt_inicio).filter(data_atualizacao__lte=dt_final)

        tags_dict = {}
        situacao_dict = {}

        for demanda in demandas:
            for tag in demanda.tags.all():
                if tag.nome not in tags_dict:
                    sit_dict = OrderedDict()
                    sit_dict[Situacao.ESTADO_ABERTO] = 0
                    sit_dict[Situacao.ESTADO_EM_NEGOCIACAO] = 0
                    sit_dict[Situacao.ESTADO_EM_ANALISE] = 0
                    sit_dict[Situacao.ESTADO_APROVADO] = 0
                    sit_dict[Situacao.ESTADO_EM_DESENVOLVIMENTO] = 0
                    sit_dict[Situacao.ESTADO_EM_HOMOLOGACAO] = 0
                    sit_dict[Situacao.ESTADO_EM_IMPLANTACAO] = 0
                    sit_dict[Situacao.ESTADO_CONCLUIDO] = 0
                    sit_dict[Situacao.ESTADO_SUSPENSO] = 0
                    sit_dict[Situacao.ESTADO_CANCELADO] = 0
                    tags_dict[tag.nome] = {'qtd': 0, 'situacao': sit_dict}
                tags_dict[tag.nome]['qtd'] += 1

                if demanda.situacao not in tags_dict[tag.nome]['situacao']:
                    tags_dict[tag.nome]['situacao'][demanda.situacao] = 0

                tags_dict[tag.nome]['situacao'][demanda.situacao] += 1

        import pandas as pd

        # Prepare data for DataFrame
        data = []
        for tag, dados in list(tags_dict.items()):
            row = {'Tag': tag, 'Total': dados['qtd']}
            # Add situations
            col_idx = 0
            for situacao in list(dados['situacao'].values()):
                # We need to map values to column names based on the order
                # The original code iterated over values, assuming order matches the header writing order.
                # The header writing order was:
                # Situacao.ESTADO_ABERTO, ..., Situacao.ESTADO_CANCELADO
                # And sit_dict was created with OrderedDict in that same order.
                # So we can just use the keys from sit_dict or the hardcoded list.

                # Let's reconstruct the keys to be safe
                keys = [
                    Situacao.ESTADO_ABERTO,
                    Situacao.ESTADO_EM_NEGOCIACAO,
                    Situacao.ESTADO_EM_ANALISE,
                    Situacao.ESTADO_APROVADO,
                    Situacao.ESTADO_EM_DESENVOLVIMENTO,
                    Situacao.ESTADO_EM_HOMOLOGACAO,
                    Situacao.ESTADO_EM_IMPLANTACAO,
                    Situacao.ESTADO_CONCLUIDO,
                    Situacao.ESTADO_SUSPENSO,
                    Situacao.ESTADO_CANCELADO,
                ]
                row[keys[col_idx]] = situacao
                col_idx += 1
            data.append(row)

        # Define columns order
        columns = [
            'Tag',
            'Total',
            Situacao.ESTADO_ABERTO,
            Situacao.ESTADO_EM_NEGOCIACAO,
            Situacao.ESTADO_EM_ANALISE,
            Situacao.ESTADO_APROVADO,
            Situacao.ESTADO_EM_DESENVOLVIMENTO,
            Situacao.ESTADO_EM_HOMOLOGACAO,
            Situacao.ESTADO_EM_IMPLANTACAO,
            Situacao.ESTADO_CONCLUIDO,
            Situacao.ESTADO_SUSPENSO,
            Situacao.ESTADO_CANCELADO,
        ]

        df = pd.DataFrame(data, columns=columns)

        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename=DisponibilidadeGeral.xlsx'

        with pd.ExcelWriter(response) as writer:
            df.to_excel(writer, sheet_name='Demandas por Tags', startrow=4, index=False)

            # Add header info
            workbook = writer.book
            worksheet = writer.sheets['Demandas por Tags']

            worksheet.cell(row=1, column=1, value='Relatório de Demandas por Tags')
            worksheet.cell(row=2, column=1, value='A demanda porde ter mais de uma tag')
            worksheet.cell(row=3, column=1, value=f'Número de demandas no período de {dt_inicio} a {dt_final}:')
            worksheet.cell(row=3, column=2, value=demandas.count())

        return response

    return locals()


@rtr()
@login_required()
def atualizacao(request, atualizacao_id):
    atualizacao = get_object_or_404(Atualizacao, pk=atualizacao_id)
    title = f'Atualização #{atualizacao.pk}'

    eh_analista = request.user.has_group_cached('Analista')
    eh_desenvolvedor = request.user.has_group_cached('Desenvolvedor')

    # Monta a lista de Atualizacoes Relacionadas aos mesmos grupos da Atualizacao Atual
    grupos = atualizacao.grupos.all().values_list('id', flat=True)
    relacionadas = Atualizacao.objects.filter(grupos__in=grupos).exclude(pk=atualizacao.pk)[:5]

    # Monta a lista com as quantidades de bugs, manutencoes e funcionalidades de atualizacoes que tenham as mesmas tags da Atualizacao Atual
    tags = atualizacao.tags.all().values_list('id', flat=True)
    lista_tags = Tag.objects.filter(pk__in=tags)
    lista = []
    for tag in lista_tags:
        bugs = Atualizacao.objects.filter(tags=tag, tipo=Atualizacao.BUG).count()
        manutencoes = Atualizacao.objects.filter(tags=tag, tipo=Atualizacao.MANUTENCAO).count()
        funcionalidades = Atualizacao.objects.filter(tags=tag, tipo=Atualizacao.FUNCIONALIDADE).count()
        lista.append([tag, tag.pk, bugs, manutencoes, funcionalidades])

    return locals()


@rtr()
def atualizacoes(request):
    title = 'Atualizações do Sistema'
    category = 'Consultas'
    icon = 'file-contract'
    servicos_anonimos = layout.gerar_servicos_anonimos(request)

    atualizacoes = Atualizacao.objects.all().order_by('-data')

    return locals()


@rtr()
@login_required()
def demandas_prioritarias_por_area(request, pk_area):
    qtd_demandas_prioritarias_por_area = DemandaPriorizacao.get_qtd_demandas_prioritarias_por_area()
    area = get_object_or_404(AreaAtuacaoDemanda, pk=pk_area)
    title = f'Demandas Prioritárias pela Área: {area}'
    if not request.user.demandanteresponsavelarea.filter(area=area.area).exists() and not request.user.is_superuser:
        raise PermissionDenied('Você não tem permissão para visualizar esta página.')
    demandas = Demanda.objects.ativas().filter(area=area).order_by('prioridade')
    return locals()


@csrf_exempt
@login_required()
def atualizar_prioridade(request, area_id):
    area = get_object_or_404(AreaAtuacaoDemanda, pk=area_id)

    if not request.user.demandanteresponsavelarea.filter(area=area.area).exists() and not request.user.is_superuser:
        raise PermissionDenied('Você não tem permissão para visualizar esta página.')

    demandas_pks = []

    for pk in request.GET.get('demandas', '').split(','):
        if not pk.isdigit():
            return JsonResponse({'ok': False, 'mensagem': f'PK "{pk}" inválida.'})
        demandas_pks.append(int(pk))

    if not demandas_pks:
        return JsonResponse({'ok': False, 'mensagem': 'Nenhuma demanda foi selecionada.'})

    demandas = {demanda.pk: demanda for demanda in Demanda.objects.filter(area=area, pk__in=demandas_pks)}
    if not demandas_pks:
        return JsonResponse({'ok': False, 'mensagem': 'Nenhuma demanda foi encontrada.'})

    demandas_em_ordem = []
    for demanda_pk in demandas_pks:
        if demanda_pk not in demandas:
            return JsonResponse({'ok': False, 'mensagem': f'Demanda "{demanda_pk}" não encontrada na área "{area}".'})
        demandas_em_ordem.append(demandas[demanda_pk])

    try:
        DemandaPriorizacao.alterar_prioridade_em_lote(demandas_em_ordem, usuario=request.user, commit=True)
    except DemandasException as error:
        return JsonResponse({'ok': False, 'mensagem': f'{error}'})
    except Exception:
        return JsonResponse({'ok': False, 'mensagem': 'Ocorreu um erro. Tente novamente.'})

    return JsonResponse({'ok': True})


@rtr()
@login_required()
def atualizar_prioridade_manualmente(request, demanda_id):
    demanda_nova_prioridade = get_object_or_404(Demanda, pk=demanda_id)

    title = f'Alterar prioridade de {demanda_nova_prioridade}'

    if not request.user.demandanteresponsavelarea.filter(area=demanda_nova_prioridade.area.area).exists() and not request.user.is_superuser:
        raise PermissionDenied('Você não tem permissão para visualizar esta página.')

    form = NovaPrioridadeDemandaForm(request.POST or None, initial={'nova_prioridade': demanda_nova_prioridade.prioridade})

    if form.is_valid():
        nova_prioridade = form.cleaned_data.get('nova_prioridade')

        try:
            DemandaPriorizacao.alterar_prioridade(demanda_nova_prioridade, nova_prioridade, usuario=request.user, commit=True)
        except DemandasException as error:
            form.add_error(None, f'{error}')
        except Exception:
            form.add_error(None, 'Ocorreu um erro. Tente novamente.')
        else:
            return httprr('..', 'Gerenciamento salvo com sucesso.')

    return locals()


@rtr()
@permission_required('demandas.add_sugestaomelhoria')
def listar_areas_atuacao_sugestao_melhoria(request: HttpRequest) -> dict[str, object]:
    title = 'Módulos para abertura de Sugestões de melhorias para o SUAP'
    areas_atuacao = AreaAtuacaoDemanda.areas_pode_abrir_sugestoes(request.user).select_related('area').prefetch_related('tags_relacionadas')
    modulos = Tag.objects.filter(pk__in=areas_atuacao.values_list('tags_relacionadas', flat=True)).distinct()
    FormClass = BuscarModuloSugestaoMelhoriaFormFactory(modulos)
    form = FormClass(request.POST or None)
    if form.is_valid():
        modulo = form.cleaned_data.get('modulo')
        if modulo:
            area_atuacao = get_object_or_404(areas_atuacao, tags_relacionadas=modulo)
            return redirect(f'/demandas/sugestoes_modulo/{area_atuacao.pk}/{modulo.pk}/')
        return httprr('.', 'Selecione um módulo da lista.', tag='error')
    return locals()


@rtr()
@permission_required('demandas.add_sugestaomelhoria')
def sugestoes_modulo(request, area_atuacao_id, modulo_id):
    area_atuacao = get_object_or_404(AreaAtuacaoDemanda, pk=area_atuacao_id)
    modulo = get_object_or_404(Tag, pk=modulo_id)

    title = f'Sugestões de melhorias para {modulo} ({area_atuacao})'

    sugestoes = SugestaoMelhoria.objects.filter(area_atuacao=area_atuacao, tags=modulo)
    sugestoes_ativas = sugestoes.exclude(
        situacao__in=[
            SugestaoMelhoria.SITUACAO_DEFERIDA,
            SugestaoMelhoria.SITUACAO_CANCELADA,
            SugestaoMelhoria.SITUACAO_INDEFERIDA,
            SugestaoMelhoria.SITUACAO_IMPLEMENTADA,
        ]
    ).order_by('situacao', '-votos')

    # Deferidas com Demanda Solicitada ou não gerada
    sugestoes_deferidas = (
        sugestoes.filter(situacao=SugestaoMelhoria.SITUACAO_DEFERIDA)
        .filter(Q(demanda_gerada__situacao=Situacao.ESTADO_ABERTO) | Q(demanda_gerada__isnull=True))
        .count()
    )

    # Deferidas com Demanda Em andamento
    sugestoes_em_implementacao = (
        sugestoes.filter(situacao=SugestaoMelhoria.SITUACAO_DEFERIDA)
        .exclude(
            Q(demanda_gerada__situacao__in=[Situacao.ESTADO_ABERTO, Situacao.ESTADO_CONCLUIDO, Situacao.ESTADO_CANCELADO])
            | Q(demanda_gerada__isnull=True)
        )
        .count()
    )

    # Implementadas ou com Demanda Concluída
    sugestoes_implementadas = sugestoes.filter(
        Q(situacao=SugestaoMelhoria.SITUACAO_IMPLEMENTADA) | Q(demanda_gerada__situacao=Situacao.ESTADO_CONCLUIDO)
    ).count()

    # Indeferidas
    sugestoes_indeferidas = sugestoes.filter(situacao=SugestaoMelhoria.SITUACAO_INDEFERIDA).count()

    # Canceladas ou com Demanda Cancelada
    sugestoes_canceladas = sugestoes.filter(
        Q(situacao=SugestaoMelhoria.SITUACAO_CANCELADA) | Q(demanda_gerada__situacao=Situacao.ESTADO_CANCELADO)
    ).count()

    return locals()


@rtr()
@permission_required('demandas.add_sugestaomelhoria')
def adicionar_sugestao_melhoria(request, area_atuacao_id):
    area_atuacao = get_object_or_404(AreaAtuacaoDemanda, pk=area_atuacao_id)

    if not area_atuacao.pode_abrir_sugestoes(request.user):
        raise PermissionDenied(f'Você não tem permissão para abrir sugestões de melhoria para a área {area_atuacao}.')

    tags_ids = request.GET.get('tags_ids', '')
    tags = [get_object_or_404(Tag, pk=tag_id) for tag_id in tags_ids.split(',') if tag_id]

    if tags:
        area_atuacao_tags_relacionadas = area_atuacao.tags_relacionadas.all()
        for tag in tags:
            if tag not in area_atuacao_tags_relacionadas:
                raise PermissionDenied(f'A Tag "{tag}" não está relacionada à Área de Atuação "{area_atuacao}".')
    else:
        raise PermissionDenied('Nenhuma Tag foi selecionada.')

    title = 'Adicionar Sugestão de Melhoria'

    form = SugestaoMelhoriaAddForm(request.POST or None, area_atuacao=area_atuacao, tags=tags, user_requisitante=request.user)

    if form.is_valid():
        sugestao_salva = form.save()
        if sugestao_salva:
            Notificar.nova_sugestao_melhoria(sugestao_salva)
            return httprr(sugestao_salva.get_absolute_url(), 'Sugestão de Melhoria salva com sucesso.')

    return locals()


@rtr()
@login_required()
def sugestao_melhoria(request, sugestao_melhoria_id):
    sugestao_melhoria = get_object_or_404(SugestaoMelhoria, pk=sugestao_melhoria_id)
    usuario = request.user
    title = f'Sugestão de Melhoria #{sugestao_melhoria.pk}: {sugestao_melhoria.titulo}'

    voto = SugestaoVoto.objects.filter(sugestao=sugestao_melhoria, usuario=usuario)
    if voto.exists():
        voto = voto[0]
    else:
        voto = None

    pode_editar_dados_basicos = sugestao_melhoria.pode_editar_dados_basicos(usuario)
    pode_editar_todos_dados = sugestao_melhoria.pode_editar_todos_dados(usuario)
    pode_gerar_demanda = sugestao_melhoria.pode_gerar_demanda(usuario)
    pode_visualizar_demanda_gerada = sugestao_melhoria.pode_visualizar_demanda_gerada(usuario)
    pode_excluir_demanda_gerada = sugestao_melhoria.pode_excluir_demanda_gerada(usuario)
    eh_usuario_ti = SugestaoMelhoria.eh_usuario_ti(usuario)
    eh_interessado = sugestao_melhoria.eh_interessado(usuario)
    eh_requisitante = sugestao_melhoria.eh_requisitante(usuario)
    is_responsavel_ou_demandante = sugestao_melhoria.is_responsavel_ou_demandante(usuario)
    pode_visualizar_comentario = sugestao_melhoria.pode_visualizar_comentario(usuario)
    pode_registrar_comentario = sugestao_melhoria.pode_registrar_comentario(usuario)
    pode_anexar = sugestao_melhoria.pode_anexar(usuario)

    etapas_sugestao = [
        (SugestaoMelhoria.SITUACAO_PENDENTE, 'Pendente', 'Sugestão aguardando análise.', 'step-warning'),
        (SugestaoMelhoria.SITUACAO_EM_ANALISE, 'Em análise', 'Sugestão em análise pelo responsável.', 'step-warning'),
    ]
    if sugestao_melhoria.is_suspensa:
        etapas_sugestao.append((SugestaoMelhoria.SITUACAO_SUSPENSA, 'Suspensa', 'Análise pausada; pode ser retomada.', 'step-warning'))
    elif sugestao_melhoria.is_indeferida:
        etapas_sugestao.append((SugestaoMelhoria.SITUACAO_INDEFERIDA, 'Indeferida', 'Sugestão não aprovada.', 'step-error'))
    elif sugestao_melhoria.is_cancelada:
        etapas_sugestao.append((SugestaoMelhoria.SITUACAO_CANCELADA, 'Cancelada', 'Sugestão cancelada.', 'step-error'))
    else:
        etapas_sugestao.append((SugestaoMelhoria.SITUACAO_DEFERIDA, 'Deferida', 'Sugestão aprovada.', 'step-success'))
        etapas_sugestao.append((SugestaoMelhoria.SITUACAO_IMPLEMENTADA, 'Implementada', 'Sugestão implementada.', 'step-success'))

    steps = '<ul class="steps">'
    for situacao, etapa, descricao, classe in etapas_sugestao:
        ativa = ' active' if sugestao_melhoria.situacao == situacao else ''
        steps += f'<li aria-label="{descricao}" class="hint hint-bottom"><span class="{classe}{ativa}">{etapa}</span></li>'
    steps += '</ul>'

    qtd_comentarios = Comentario.objects.filter(
        content_type=ContentType.objects.get(app_label=sugestao_melhoria._meta.app_label, model=sugestao_melhoria._meta.model_name),
        object_id=sugestao_melhoria.pk,
        resposta=None,
    ).count()

    return locals()


@rtr()
@login_required
def adicionar_anexo_sugestao(request, sugestao_id):
    title = 'Adicionar anexo'
    sugestao = get_object_or_404(SugestaoMelhoria, pk=sugestao_id)

    if not sugestao.pode_anexar(request.user):
        raise PermissionDenied('Você não tem permissão para adicionar anexo nesta sugestão de melhoria.')

    form = SugestaoAnexoForm(request.POST or None, request.FILES or None)
    form.instance.sugestao = sugestao
    form.instance.anexado_por = request.user
    if form.is_valid():
        form.save()
        return httprr(sugestao.get_absolute_url(), 'Anexo adicionado com sucesso.')

    return locals()


@rtr()
@login_required()
def concordar_sugestao(request, sugestao_melhoria_id):
    sugestao = get_object_or_404(SugestaoMelhoria, pk=sugestao_melhoria_id)

    if sugestao.pode_votar():
        sugestao_voto = SugestaoVoto.objects.filter(sugestao=sugestao, usuario=request.user)
        if sugestao_voto.exists():
            voto = sugestao_voto[0]
        else:
            voto = SugestaoVoto()
            voto.sugestao = sugestao

        voto.concorda = True
        voto.save()

        return httprr(sugestao.get_absolute_url(), 'Voto cadastrado com sucesso.', 'success')
    else:
        return httprr(sugestao.get_absolute_url(), 'Não foi possível votar nesta sugestão', 'error')


@rtr()
@login_required()
def discordar_sugestao(request, sugestao_melhoria_id):
    sugestao = get_object_or_404(SugestaoMelhoria, pk=sugestao_melhoria_id)

    if sugestao.pode_votar():
        sugestao_voto = SugestaoVoto.objects.filter(sugestao=sugestao, usuario=request.user)
        if sugestao_voto.exists():
            voto = sugestao_voto[0]
        else:
            voto = SugestaoVoto()
            voto.sugestao = sugestao

        voto.concorda = False
        voto.save()

        return httprr(sugestao.get_absolute_url(), 'Voto cadastrado com sucesso.', 'success')
    else:
        return httprr(sugestao.get_absolute_url(), 'Não foi possível votar nesta sugestão', 'error')


@rtr()
@login_required()
def tornar_se_interessado(request, sugestao_melhoria_id):
    sugestao = get_object_or_404(SugestaoMelhoria, pk=sugestao_melhoria_id)
    usuario = request.user

    if usuario in sugestao.interessados.all():
        raise PermissionDenied('Você já é Interessado desta sugestão de melhoria.')

    if sugestao.eh_requisitante(usuario):
        raise PermissionDenied('Você já é o Requisitante desta sugestão de melhoria.')

    sugestao.interessados.add(usuario)
    sugestao.save()

    return httprr(sugestao.get_absolute_url(), 'Você foi incluído como Interessado desta sugestão.')


@rtr()
@login_required()
def alterar_situacao_sugestao(request, sugestao_melhoria_id, situacao):
    obj = SugestaoMelhoria.objects.get(pk=sugestao_melhoria_id)
    if obj.is_responsavel(request.user):
        obj.situacao = situacao
        obj.save()
        return httprr(obj.get_absolute_url(), 'Etapa alterada com sucesso.')
    return httprr(obj.get_absolute_url(), 'Somente o responsável pela sugestão pode alterar a etapa.', 'error')


def _editar_dados_sugestao_melhoria_processar_form(user, sugestao_melhoria, form):
    sugestao_melhoria_situacao_anterior = sugestao_melhoria.situacao
    if form.is_valid():
        sugestao_salva = form.save()
        if sugestao_salva:
            if form.cleaned_data.get('modulo'):
                sugestao_salva.tags.clear()
                sugestao_salva.tags.add(form.cleaned_data.get('modulo'))
            situacao_alterada = sugestao_salva.situacao != sugestao_melhoria_situacao_anterior
            if situacao_alterada:
                Notificar.nova_situacao_em_sugestao_melhoria(sugestao_salva, user)
            return httprr(sugestao_melhoria.get_absolute_url(), 'Sugestão de Melhoria salva com sucesso.')
    return None


@rtr()
@login_required()
def editar_dados_basicos_sugestao_melhoria(request, sugestao_melhoria_id):
    sugestao_melhoria = get_object_or_404(SugestaoMelhoria, pk=sugestao_melhoria_id)

    title = f'Editar Sugestão de Melhoria (Área de Atuação: {sugestao_melhoria.area_atuacao.area.nome})'

    if not sugestao_melhoria.pode_editar_dados_basicos(request.user):
        raise PermissionDenied('Você não tem permissão para editar a sugestão de melhoria.')

    form = SugestaoMelhoriaEdicaoBasicaForm(request.POST or None, instance=sugestao_melhoria, request=request)

    return _editar_dados_sugestao_melhoria_processar_form(request.user, sugestao_melhoria, form) or locals()


@rtr()
@login_required()
def editar_todos_dados_sugestao_melhoria(request, sugestao_melhoria_id):
    sugestao_melhoria = get_object_or_404(SugestaoMelhoria, pk=sugestao_melhoria_id)

    title = f'Editar Sugestão de Melhoria (Área de Atuação: {sugestao_melhoria.area_atuacao.area.nome})'

    if not sugestao_melhoria.pode_editar_todos_dados(request.user):
        raise PermissionDenied('Você não tem permissão para editar a sugestão de melhoria.')

    form = SugestaoMelhoriaEdicaoCompletaForm(request.POST or None, instance=sugestao_melhoria, request=request)

    return _editar_dados_sugestao_melhoria_processar_form(request.user, sugestao_melhoria, form) or locals()


@rtr()
@permission_required('comum.is_coordenador_de_sistemas')
def editar_area_atuacao(request, sugestao_melhoria_id):
    sugestao_melhoria = get_object_or_404(SugestaoMelhoria, pk=sugestao_melhoria_id)

    title = f'Editar Área de Atuação da Sugestão de Melhoria #{sugestao_melhoria_id}'

    form = SugestaoMelhoriaEdicaoAreaAtuacaoForm(request.POST or None, instance=sugestao_melhoria)

    if form.is_valid():
        form.save()
        return httprr(sugestao_melhoria.get_absolute_url(), 'Sugestão de Melhoria salva com sucesso.')

    return locals()


@rtr()
@login_required()
def atribuir_se_como_responsavel_sugestao_melhoria(request, sugestao_melhoria_id):
    sugestao_melhoria = get_object_or_404(SugestaoMelhoria, pk=sugestao_melhoria_id)

    url_visualizar = sugestao_melhoria.get_absolute_url()
    if sugestao_melhoria.atribuir_responsavel(request.user):
        return httprr(url_visualizar, 'Responsável definido com sucesso.')

    return httprr(url_visualizar, 'Ocorreu um erro ao definir o responsável.', 'error')


@rtr()
@login_required()
def gerar_demanda_sugestao_melhoria(request, sugestao_melhoria_id):
    sugestao_melhoria = get_object_or_404(SugestaoMelhoria, pk=sugestao_melhoria_id)

    if not sugestao_melhoria.pode_gerar_demanda(request.user):
        raise PermissionDenied('Você não tem permissão para gerar a demanda para esta sugestão de melhoria.')

    form = GerarDemandaSugestaoMelhoriaForm(
        request.POST or None,
        area=sugestao_melhoria.area_atuacao,
        titulo=sugestao_melhoria.titulo,
        descricao=sugestao_melhoria.descricao,
        demandantes=[sugestao_melhoria.responsavel],
        interessados=[sugestao_melhoria.requisitante, *list(sugestao_melhoria.interessados.all())],
        tags=list(sugestao_melhoria.tags.all()),
    )

    if form.is_valid():
        form.save()
        sugestao_melhoria.gerar_demanda(request.user, form.instance)
        return httprr(form.instance.get_absolute_url(), 'Demanda gerada com sucesso.')

    return locals()


def _remover_ambiente(obj: AmbienteHomologacao | AnalistaDesenvolvedor, action: str, url: str) -> HttpResponse:
    """Remove provisória (undeploy) ou definitivamente (destroy) o container ou a IDE.

    Só anuncia sucesso se o GitLab aceitou disparar o job; uma recusa vira mensagem de erro.
    """
    eh_ide = isinstance(obj, AnalistaDesenvolvedor)
    remover = {
        'undeploy': obj.excluir_ide if eh_ide else obj.excluir_container,
        'destroy': obj.destruir_ide if eh_ide else obj.destruir,
    }[action]
    try:
        remover()
    except GitlabJobError as e:
        return httprr(url, str(e), 'error')
    if action == 'undeploy':
        return httprr(url, 'Ambiente excluído provisoriamente com sucesso')
    return httprr(url, 'Ambiente e base de dados excluídos com sucesso')


@rtr()
@permission_required('demandas.add_ambientehomologacao')
def analistadesenvolvedor(request, pk):
    obj = get_object_or_404(AnalistaDesenvolvedor, pk=pk)
    title = str(obj)
    action = request.GET.get('action')
    if action:
        url = f'/demandas/analistadesenvolvedor/{pk}/'
        if action == 'deploy':
            return tasks.criar_atualizar_ide(obj, url)
        elif action == 'log':
            return HttpResponse(obj.get_log_ide_cricao_atualizacao_ide())
        elif action in ('undeploy', 'destroy'):
            return _remover_ambiente(obj, action, url)
    return locals()


@rtr()
@permission_required('demandas.add_ambientehomologacao')
def ambientehomologacao(request, pk):
    obj = get_object_or_404(AmbienteHomologacao, pk=pk)
    title = str(obj)
    action = request.GET.get('action')
    if action:
        url = f'/demandas/ambientehomologacao/{pk}/'
        if action == 'deploy':
            tasks.criar_atualizar_container(obj, url)
            return redirect(obj.get_deploy_job_url())
        elif action in ('undeploy', 'destroy'):
            return _remover_ambiente(obj, action, url)
        elif action == 'pipeline':
            try:
                obj.atualizar_pipeline()
                return httprr(url, 'Pipeline do ambiente atualizado com sucesso')
            except Exception as e:
                if settings.DEBUG:
                    raise e
                return httprr(url, str(e), 'error')
    return locals()


@permission_required('demandas.view_demanda')
def acessar_ambiente_via_demanda(request, pk, demanda_pk):
    obj = get_object_or_404(AmbienteHomologacao, pk=pk)
    if not obj.ativo:
        url = obj.get_url_homologacao()
        return tasks.criar_atualizar_container(obj, url)
    return HttpResponseRedirect(f'/demandas/visualizar/{demanda_pk}/?tab=entregas')


@rtr()
@permission_required('demandas.add_ambientehomologacao')
def executar_comando_ambiente_homologacao(request, pk):
    title = 'Executar Comando'
    obj = get_object_or_404(AmbienteHomologacao, pk=pk)
    form = ExecutarComandoForm(data=request.POST or None)
    if form.is_valid():
        log = obj.executar_comando(form.cleaned_data['comando'])
        return HttpResponse(log)
    return locals()


@rtr()
@permission_required('demandas.change_areaatuacaodemanda')
def gerenciar_demandantes(request, area_atuacao_id):
    area_atuacao = get_object_or_404(AreaAtuacaoDemanda, pk=area_atuacao_id)
    title = f'Gerenciar demandantes (Área {area_atuacao})'
    return locals()


@rtr()
@permission_required('demandas.change_areaatuacaodemanda')
def gerenciar_demandantes_editar(request, area_atuacao_id, tag_id):
    area_atuacao = get_object_or_404(AreaAtuacaoDemanda, pk=area_atuacao_id)
    tag = get_object_or_404(Tag, pk=tag_id)

    title = f'Editar demandantes do módulo: {tag}'

    form = AreaAtuacaoGerenciarDemandantesForm(request.POST or None, area_atuacao=area_atuacao, tag=tag)

    if form.is_valid():
        if form.save():
            return httprr('..', 'Demandantes salvos com sucesso.')
        return httprr('.', 'Erro ao salvar os demandantes.', tag='error')

    return locals()


@rtr()
@permission_required('demandas.change_areaatuacaodemanda')
def substituir_demandante(request, area_atuacao_id, demandante_id):
    area_atuacao = get_object_or_404(AreaAtuacaoDemanda, pk=area_atuacao_id)
    demandante = User.objects.get(pk=demandante_id)
    title = f'Atualizar/substituir demandante: {demandante}'
    form = SubstituirDemandanteForm(request.POST or None, demandante=demandante, area_atuacao=area_atuacao)
    if form.is_valid():
        form.processar()
        return httprr('..', 'Demandante atualizado/substituído com sucesso.', close_popup=True)

    return locals()


@minhas_acoes.registrar_acao()
def minhas_acoes_demandas(request, data, datahora_inicio, datahora_fim):
    user_id = request.user.id
    filters = {}

    if datahora_inicio:
        filters['data_hora__gte'] = datahora_inicio
    if datahora_fim:
        filters['data_hora__lte'] = datahora_fim

    qs_historico_situacao_demandas_concluidas = (
        HistoricoSituacao.objects.filter(situacao=Situacao.ESTADO_CONCLUIDO, **filters)
        .select_related('demanda')
        .prefetch_related('demanda__dod_set', 'demanda__dod_set__especificacao_set')
        .order_by('data_hora')
    )
    for hs_demanda_concluida_analista in qs_historico_situacao_demandas_concluidas.filter(demanda__analistas__id=user_id):
        data.append(
            (
                'Demandas',
                'Concluídas como Analista',
                hs_demanda_concluida_analista.demanda,
                f'em {hs_demanda_concluida_analista.data_hora.strftime("%d/%m/%Y %H:%M")}',
                f'{hs_demanda_concluida_analista.demanda.get_absolute_url()}',
            )
        )

    for hs_demanda in qs_historico_situacao_demandas_concluidas.filter(demanda__desenvolvedores__id=user_id):
        data.append(
            (
                'Demandas',
                'Concluídas como Desenvolvedor',
                hs_demanda.demanda,
                f'em {hs_demanda.data_hora.strftime("%d/%m/%Y %H:%M")}',
                f'{hs_demanda.demanda.get_absolute_url()}',
            )
        )

    qs_historico_situacao_demandas_homologadas = HistoricoSituacao.objects.filter(
        usuario_id=user_id, situacao=Situacao.ESTADO_HOMOLOGADA, **filters
    ).select_related('demanda')
    for hs_demanda in qs_historico_situacao_demandas_homologadas.values('demanda_id').annotate(count=Count('demanda_id')):
        hs_demanda = qs_historico_situacao_demandas_homologadas.filter(demanda_id=hs_demanda['demanda_id']).order_by('data_hora').last()
        data.append(
            (
                'Demandas',
                'Homologadas como Demandante',
                hs_demanda.demanda,
                f'em {hs_demanda.data_hora.strftime("%d/%m/%Y %H:%M")}',
                f'{hs_demanda.demanda.get_absolute_url()}',
            )
        )

    qs_historico_situacao_demandas_aprovadas = HistoricoSituacao.objects.filter(
        usuario_id=user_id, situacao=Situacao.ESTADO_APROVADO, **filters
    ).select_related('demanda')
    for hs_demanda in qs_historico_situacao_demandas_aprovadas.values('demanda_id').annotate(count=Count('demanda_id')):
        hs_demanda = qs_historico_situacao_demandas_aprovadas.filter(demanda_id=hs_demanda['demanda_id']).order_by('data_hora').last()
        data.append(
            (
                'Demandas',
                'Aprovadas como Demandante',
                hs_demanda.demanda,
                f'em {hs_demanda.data_hora.strftime("%d/%m/%Y %H:%M")}',
                f'{hs_demanda.demanda.get_absolute_url()}',
            )
        )

    qs_historico_sugestao = HistoricoSituacaoSugestaoMelhoria.objects.filter(
        usuario_id=user_id, situacao__in=[SugestaoMelhoria.SITUACAO_PENDENTE, SugestaoMelhoria.SITUACAO_DEFERIDA], **filters
    )

    # Subquery para obter o pk do primeiro histórico por sugestão (ordenado por data_hora)
    first_pk_subq = (
        HistoricoSituacaoSugestaoMelhoria.objects.filter(sugestao_melhoria=OuterRef('sugestao_melhoria')).order_by('data_hora').values('pk')[:1]
    )

    qs_historico_sugestao = qs_historico_sugestao.annotate(first_pk=Subquery(first_pk_subq))
    qs_historico_sugestao = qs_historico_sugestao.annotate(
        is_first=Case(When(pk=F('first_pk'), then=Value(True)), default=Value(False), output_field=BooleanField())
    )

    for historico_sugestao_melhoria in qs_historico_sugestao:
        display = 'Deferidas'
        if historico_sugestao_melhoria.situacao == SugestaoMelhoria.SITUACAO_PENDENTE:
            display = 'Enviadas' if getattr(historico_sugestao_melhoria, 'is_first', False) else 'Editadas'
        data.append(
            (
                'Sugestões de melhorias',
                display,
                historico_sugestao_melhoria.sugestao_melhoria,
                f'em {historico_sugestao_melhoria.data_hora.strftime("%d/%m/%Y %H:%M")}',
                f'{historico_sugestao_melhoria.sugestao_melhoria.get_absolute_url()}',
            )
        )


@rtr()
@login_required
def criar_issue_gitlab(request, especificao_id):
    obj = get_object_or_404(Especificacao, pk=especificao_id)
    obj.criar_issue_gitlab(request)
    return httprr(f'/demandas/visualizar/{obj.dod.demanda.id}/', 'Issue criada com sucesso.')


@rtr()
@login_required
def vincular_issue_gitlab(request, especificao_id):
    title = 'Vincular Issue'
    obj = get_object_or_404(Especificacao, pk=especificao_id)

    form = VincularIssueGitlabForm(request.POST or None, request=request, instance=obj, url=obj.gitlab_issue_url)
    if form.is_valid():
        form.processar()
        return httprr(f'/demandas/visualizar/{obj.dod.demanda.id}/', 'URL vinculada com sucesso.', close_popup=True)
    return locals()


@rtr()
@permission_required(['demandas.add_demanda', 'demandas.change_demanda', 'demandas.view_demanda'])
def anexos_atualizar_informacoes(request, demanda_id):
    demanda = get_object_or_404(Demanda, pk=demanda_id)
    demanda.anexos_atualizar_informacoes()
    return httprr(f'/demandas/visualizar/{demanda.id}/?tab=anexos', 'Anexos atualizados com sucesso.', close_popup=True)


# --- Funções de Subquery (CORRIGIDAS para aceitar referências externas) ---


# Função para pegar o ID do registro de histórico mais relevante (última mudança para a situação atual)
# Aceita a referência da PK da Demanda e o valor da situação como argumentos.
def get_historico_id_subquery(demanda_id_ref, situacao_ref):
    return HistoricoSituacao.objects.filter(demanda_id=demanda_id_ref, situacao=situacao_ref).order_by('-data_hora').values('pk')[:1]


# Função para buscar a Data de Entrada na Etapa (data_hora)
def get_data_entrada_subquery(historico_pk_ref):
    # Usamos o F() na filter abaixo, mas ela se resolve em SQL Subquery acima
    return HistoricoSituacao.objects.filter(pk=Subquery(historico_pk_ref)).values('data_hora')[:1]


# Função para buscar a Data de Previsão na Etapa (data_previsao)
def get_data_previsao_subquery(historico_pk_ref):
    return HistoricoSituacao.objects.filter(pk=Subquery(historico_pk_ref)).values('data_previsao')[:1]


@rtr()
@permission_required('demandas.visualiza_forca_trabalho')
def relatorio_atividades_reprimidas(request):
    title = 'Relatório de atividades reprimidas'
    hoje = date.today()

    erro = None
    if 'erros' in settings.INSTALLED_APPS:
        from erros.models import Erro

        erro = (
            Erro.objects.filter(data_criacao__lt=hoje - timedelta(5))
            .exclude(situacao__in=Erro.SITUACOES_FINAIS)
            .annotate(dias_atraso=RawSQL('CURRENT_DATE - data_criacao::date', params=[], output_field=IntegerField()))
            .order_by('-dias_atraso')
            .first()
        )

    chamado = None
    if 'centralservicos' in settings.INSTALLED_APPS:
        from centralservicos.models import Chamado, StatusChamado

        grupos_atendimento_ids = Configuracao.get_valor_por_chave('demandas', 'grupos_atendimento')
        if grupos_atendimento_ids:
            grupos_atendimento_ids = grupos_atendimento_ids.split(',')
        else:
            grupos_atendimento_ids = []
        grupos_atendimento = GrupoAtendimento.objects.filter(id__in=grupos_atendimento_ids)
        atendimentos = AtendimentoAtribuicao.objects.filter(grupo_atendimento__in=grupos_atendimento)
        chamados_atendimentos = (
            Chamado.objects.filter(pk__in=atendimentos.values('chamado'))
            .exclude(status__in=[StatusChamado.RESOLVIDO, StatusChamado.FECHADO, StatusChamado.CANCELADO])
            .annotate(dias_atraso_sla=RawSQL('CURRENT_DATE - data_limite_atendimento::date', params=[], output_field=IntegerField()))
            .filter(dias_atraso_sla__gt=0)
            .order_by('-dias_atraso_sla')
        )
        for chamado_atendimento in chamados_atendimentos:
            if chamado_atendimento.get_atendimento_atribuicao_atual().grupo_atendimento in grupos_atendimento:
                chamado = chamado_atendimento
                break

    # --- 1. Definição das Referências SQL para a Correlação ---
    # Usamos RawSQL para forçar o nome da coluna da tabela principal que será correlacionada
    # (Nome da Tabela: "demandas_demanda").
    id_ref_sql = RawSQL('"demandas_demanda"."id"', params=[])
    situacao_ref_sql = RawSQL('"demandas_demanda"."situacao"', params=[])

    # --- 2. Criação das Queries com as Referências Corretas ---
    historico_id_subquery = get_historico_id_subquery(id_ref_sql, situacao_ref_sql)
    data_entrada_subquery = get_data_entrada_subquery(historico_id_subquery)
    data_previsao_subquery = get_data_previsao_subquery(historico_id_subquery)

    # Converte as subqueries para string SQL e adiciona parênteses para injeção segura.
    sql_data_entrada = str(data_entrada_subquery.query)
    sql_data_previsao = str(data_previsao_subquery.query)

    # --- 3. QuerySet Base ---
    demandas_base = Demanda.objects.filter(
        situacao__in=[
            Situacao.ESTADO_EM_NEGOCIACAO,
            Situacao.ESTADO_EM_ANALISE,
            Situacao.ESTADO_EM_DESENVOLVIMENTO,
            Situacao.ESTADO_EM_HOMOLOGACAO,
            Situacao.ESTADO_EM_IMPLANTACAO,
        ]
    )

    # --- 4. CÁLCULO DO ATRASO (RawSQL Autocontido com Injeção Direta) ---
    # A Subquery inteira, o CASE e o COALESCE são injetados aqui.
    atraso_em_dias_sql = RawSQL(  # noqa: S611
        f"""
        COALESCE(
            (CURRENT_DATE - (
                CASE
                    -- Referencia a coluna da tabela principal
                    WHEN "demandas_demanda"."situacao" = %s THEN
                        -- Injeta Subquery e força CAST para DATE
                        CAST(({sql_data_entrada}) AS DATE)
                    ELSE
                        -- Injeta Subquery (já é um DateField no banco, mas forçamos os parênteses)
                        (({sql_data_previsao}))
                END
            )),
            0
        )
        """,
        params=[Situacao.ESTADO_EM_NEGOCIACAO],
        output_field=IntegerField(),
    )

    # --- 5. Anotação, Filtro e Ordenação ---
    demanda = demandas_base.annotate(dias_atraso=atraso_em_dias_sql).filter(dias_atraso__gt=0).order_by('-dias_atraso').first()

    return locals()


@login_required
def get_tags_area_ajax(request):
    """View AJAX para retornar as tags (módulos) de uma área de atuação"""
    from django.http import JsonResponse

    area_id = request.GET.get('area_id')
    if not area_id:
        return JsonResponse({'tags': []})

    try:
        area = AreaAtuacaoDemanda.objects.get(id=area_id)
        tags = area.tags_relacionadas.filter(ativa=True).values('id', 'nome')
        return JsonResponse({'tags': list(tags)})
    except AreaAtuacaoDemanda.DoesNotExist:
        return JsonResponse({'tags': []})


# ─────────────────────────────────────────────────────────────────────────────
# Views de Entrega
# ─────────────────────────────────────────────────────────────────────────────


@rtr('demandas/templates/formulario.html')
@permission_required('demandas.atende_demanda')
def criar_enrega(request, demanda_id):
    demanda = get_object_or_404(Demanda, pk=demanda_id)
    homologar = request.GET.get('homologar') == '1'
    title = f'{"Homologar" if homologar else "Nova Entrega"} — {demanda}'

    form = EntregaForm(request.POST or None, demanda=demanda, request=request, homologar=homologar)
    if form.is_valid():
        try:
            EntregaService.criar(
                demanda=demanda,
                titulo=form.cleaned_data['titulo'],
                usuario=request.user,
                descricao=form.cleaned_data.get('descricao', ''),
                notas=form.cleaned_data.get('notas', ''),
                ambiente_homologacao=form.cleaned_data.get('ambiente_homologacao'),
                url_validacao=form.cleaned_data.get('url_validacao', ''),
                senha_homologacao=form.cleaned_data.get('senha_homologacao', ''),
                prazo_feedback=form.cleaned_data['prazo_feedback'],
                branch=form.cleaned_data.get('branch', ''),
                id_merge_request=form.cleaned_data.get('id_merge_request'),
                pipeline_id=form.cleaned_data.get('pipeline_id'),
                versionamento=form.cleaned_data.get('versionamento', ''),
                conclui_demanda=form.cleaned_data.get('conclui_demanda', False),
                especificacoes=form.cleaned_data.get('especificacoes'),
            )
            return httprr(demanda.get_absolute_url(), 'Entrega registrada. A demanda está em homologação.', close_popup=True)
        except Exception as e:
            return httprr(demanda.get_absolute_url(), f'Erro ao registrar entrega: {e}', tag='error', close_popup=True)
    return locals()


def _entrega_para_validar(request: HttpRequest, entrega_id: int) -> Entrega:
    entrega = get_object_or_404(Entrega, pk=entrega_id)
    if not entrega.demanda.pode_validar_entrega(request.user, entrega):
        raise PermissionDenied('Só os demandantes validam a entrega, e nunca quem a cadastrou.')
    return entrega


@rtr('demandas/templates/formulario.html')
@login_required()
def entrega_aprovar(request, entrega_id):
    entrega = _entrega_para_validar(request, entrega_id)
    demanda = entrega.demanda
    title = f'Aprovar Entrega — {entrega.titulo}'

    if entrega.esta_encerrada:
        return httprr(demanda.get_absolute_url(), 'Esta entrega já está encerrada.', tag='error', close_popup=True)

    if request.method == 'POST':
        form = AprovarEntregaForm(request.POST)
        if form.is_valid():
            try:
                EntregaService.aprovar(
                    entrega=entrega,
                    usuario=request.user,
                    observacao=form.cleaned_data.get('observacao', ''),
                )
                demanda.refresh_from_db()
                return httprr(demanda.get_absolute_url(), f'Entrega aprovada. A demanda está "{demanda.situacao}".', close_popup=True)
            except Exception as e:
                return httprr(demanda.get_absolute_url(), f'Erro ao aprovar entrega: {e}', tag='error', close_popup=True)
    else:
        form = AprovarEntregaForm()

    return locals()


@rtr('demandas/templates/formulario.html')
@login_required()
def entrega_reprovar(request, entrega_id):
    entrega = _entrega_para_validar(request, entrega_id)
    demanda = entrega.demanda
    title = f'Reprovar Entrega — {entrega.titulo}'

    if entrega.esta_encerrada:
        return httprr(demanda.get_absolute_url(), 'Esta entrega já está encerrada.', tag='error', close_popup=True)

    if request.method == 'POST':
        form = ReprovarEntregaForm(request.POST)
        if form.is_valid():
            try:
                EntregaService.reprovar(
                    entrega=entrega,
                    usuario=request.user,
                    motivo=form.cleaned_data['motivo'],
                )
                return httprr(demanda.get_absolute_url(), 'Entrega reprovada. Demanda retornou para desenvolvimento.', close_popup=True)
            except Exception as e:
                return httprr(demanda.get_absolute_url(), f'Erro ao reprovar entrega: {e}', tag='error', close_popup=True)
    else:
        form = ReprovarEntregaForm()

    return locals()


@rtr()
@permission_required('demandas.atende_demanda')
def entrega_cancelar(request, entrega_id):
    entrega = get_object_or_404(Entrega, pk=entrega_id)
    demanda = entrega.demanda

    if entrega.esta_encerrada:
        return httprr(demanda.get_absolute_url(), 'Esta entrega já está encerrada.', tag='error')

    try:
        EntregaService.cancelar(entrega=entrega, usuario=request.user)
        return httprr(demanda.get_absolute_url(), 'Entrega cancelada. Demanda retornou para desenvolvimento.')
    except Exception as e:
        return httprr(demanda.get_absolute_url(), f'Erro ao cancelar entrega: {e}', tag='error')


# ─────────────────────────────────────────────────────────────────────────────
# Views de Sub-demanda
# ─────────────────────────────────────────────────────────────────────────────


@rtr('demandas/templates/formulario.html')
@permission_required('demandas.atende_demanda')
def subdemanda_criar(request, demanda_id):
    pai = get_object_or_404(Demanda, pk=demanda_id)
    title = f'Nova Sub-demanda — {pai}'

    if pai.eh_subdemanda:
        return httprr(pai.get_absolute_url(), 'Não é possível criar sub-demanda de uma sub-demanda.', tag='error', close_popup=True)

    form = SubdemandaAddForm(request.POST or None, request=request, pai=pai)
    if form.is_valid():
        try:
            form.instance.parent = pai
            form.instance.prioridade_interna = pai.proxima_prioridade_interna
            form.instance.consolidacao_sempre_visivel = pai.consolidacao_sempre_visivel
            subdemanda = form.save()
            return httprr(pai.get_absolute_url(), f'Sub-demanda "{subdemanda.titulo}" criada com sucesso.', close_popup=True)
        except Exception as e:
            return httprr(pai.get_absolute_url(), f'Erro ao criar sub-demanda: {e}', tag='error', close_popup=True)
    return locals()


@csrf_exempt
@login_required()
def subdemanda_reordenar(request, demanda_id):
    pai = get_object_or_404(Demanda, pk=demanda_id)

    if not request.user.has_perm('demandas.atende_demanda'):
        return JsonResponse({'ok': False, 'mensagem': 'Sem permissão para reordenar sub-demandas.'})

    pks = []
    for pk in request.GET.get('subdemandas', '').split(','):
        if not pk.isdigit():
            return JsonResponse({'ok': False, 'mensagem': f'ID "{pk}" inválido.'})
        pks.append(int(pk))

    if not pks:
        return JsonResponse({'ok': False, 'mensagem': 'Nenhuma sub-demanda informada.'})

    subdemandas_map = {d.pk: d for d in Demanda.objects.filter(parent=pai, pk__in=pks)}
    subdemandas_em_nova_ordem = []
    for pk in pks:
        if pk not in subdemandas_map:
            return JsonResponse({'ok': False, 'mensagem': f'Sub-demanda #{pk} não pertence a esta demanda.'})
        subdemandas_em_nova_ordem.append(subdemandas_map[pk])

    try:
        SubdemandaService.reordenar(pai, subdemandas_em_nova_ordem, usuario=request.user)
    except Exception as error:
        return JsonResponse({'ok': False, 'mensagem': str(error)})

    return JsonResponse({'ok': True})


@rtr()
@permission_required(['demandas.add_demanda', 'demandas.change_demanda', 'demandas.view_demanda'])
def demandas_listagem(request):
    title = 'Listagem de Demandas'

    eh_analista = request.user.has_group_cached('Analista')
    eh_desenvolvedor = request.user.has_group_cached('Desenvolvedor')
    eh_demandante = request.user.has_group_cached('Demandante')

    # ── Queryset base: apenas demandas raiz (sem parent) ─────────────────────
    # Sub-demandas são exibidas aninhadas dentro de cada pai.
    qs = (
        Demanda.objects.filter(parent__isnull=True)
        .select_related('area', 'area__area')
        .prefetch_related(
            'demandantes',
            'tags',
            'analistas',
            'subdemandas',
            'entregas',
        )
    )

    # ── Filtros ───────────────────────────────────────────────────────────────
    area_id = request.GET.get('area')
    situacao = request.GET.get('situacao')
    tipo = request.GET.get('tipo')
    tag_id = request.GET.get('tag')
    com_sub = request.GET.get('com_subdemandas')
    entrega_f = request.GET.get('entrega')  # pendente | vencida
    busca = request.GET.get('q', '').strip()

    if area_id:
        qs = qs.filter(area__id=area_id)

    if situacao:
        qs = qs.filter(situacao=situacao)

    if tipo:
        qs = qs.filter(tipo=tipo)

    if tag_id:
        qs = qs.filter(tags__id=tag_id)

    if com_sub == '1':
        qs = qs.filter(subdemandas__isnull=False).distinct()
    elif com_sub == '0':
        qs = qs.filter(subdemandas__isnull=True)

    if entrega_f == 'pendente':
        qs = qs.filter(entregas__status='ENVIADA').distinct()
    elif entrega_f == 'vencida':
        qs = qs.filter(
            entregas__status='ENVIADA',
            entregas__prazo_feedback__lt=date.today(),
        ).distinct()

    if busca:
        qs = qs.filter(Q(id__icontains=busca) | Q(titulo__icontains=busca) | Q(descricao__icontains=busca))

    qs = qs.order_by('area__area__nome', 'prioridade', 'pk')

    # ── Dados para filtros ────────────────────────────────────────────────────
    areas = AreaAtuacaoDemanda.objects.select_related('area').order_by('area__nome')
    tags = Tag.objects.filter(ativa=True).order_by('nome')
    situacoes = Situacao.ESTADO_CHOICES
    tipos = TipoDemanda.TIPODEMANDA_CHOICES

    # ── Anotação de indicadores por demanda ───────────────────────────────────
    # Para evitar N+1 no template, monta dicionários indexados por demanda.pk
    ids = list(qs.values_list('pk', flat=True))

    # entregas pendentes por demanda
    pendentes_map = {}
    vencidas_map = {}
    for e in Entrega.objects.filter(demanda_id__in=ids, status='ENVIADA').select_related('demanda'):
        pendentes_map[e.demanda_id] = e
        if e.prazo_feedback and e.prazo_feedback < date.today():
            vencidas_map[e.demanda_id] = e

    # sub-demandas por pai
    subdemandas_map = {}
    for sub in Demanda.objects.filter(parent_id__in=ids).select_related('area'):
        subdemandas_map.setdefault(sub.parent_id, []).append(sub)

    # ── Monta lista enriquecida ───────────────────────────────────────────────
    demandas_lista = []
    for d in qs:
        demandas_lista.append(
            {
                'demanda': d,
                'entrega_pendente': pendentes_map.get(d.pk),
                'entrega_vencida': vencidas_map.get(d.pk),
                'subdemandas': subdemandas_map.get(d.pk, []),
                'tem_subdemandas': d.pk in subdemandas_map,
            }
        )

    total = len(demandas_lista)

    return locals()
