import datetime
import tempfile
from collections import OrderedDict
from datetime import date

import sentry_sdk
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Avg, Count, F, Max, Min, Q, Sum
from django.db.models.functions import TruncMonth
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.defaultfilters import pluralize
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django_fsm import TransitionNotAllowed, has_transition_perm
from reversion import revisions as reversion
from reversion.views import create_revision

from centralservicos import tasks
from centralservicos.forms import (
    AdicionarGrupoInteressadosFormFactory,
    AdicionarOutrosInteressadosFormFactory,
    AdicionarTagsAoChamadoFormFactory,
    AlterarStatusChamadoFormFactory,
    AtendentesFormFactory,
    AtendimentoAtribuicaoFormFactory,
    AtendimentosPorAnoForm,
    BuscarArtigoForm,
    BuscarChamadoSuporteFormFactory,
    BuscarChamadoUsuarioFormFactory,
    BuscarServicoFormFactory,
    ChamadoAnexoForm,
    ChamadoAnexoFormset,
    ChamadoFormFactory,
    ComunicacaoFormFactory,
    EditarPatrimonioRelacionadoChamadoForm,
    GraficosFormFactory,
    MarcarParaCorrecaoForm,
    ReclassificarChamadoFormFactory,
    ResolverChamadoFormFactory,
    TarefaChamadoAddFormFactory,
    TarefaChamadoChangeFormFactory,
    EditarAreaBaseConhecimentoFormFactory,
    ConfirmarAcaoFormFactory,
)
from centralservicos.models import (
    AtendimentoAtribuicao,
    AvaliaBaseConhecimento,
    BaseConhecimento,
    BaseConhecimentoAnexo,
    CategoriaServico,
    CentroAtendimento,
    Chamado,
    ChamadoAnexo,
    Comunicacao,
    GrupoAtendimento,
    GrupoInteressado,
    GrupoServico,
    HistoricoStatus,
    Monitoramento,
    PerguntaAvaliacaoBaseConhecimento,
    RespostaPadrao,
    Servico,
    StatusChamado,
    Tag,
    Tarefa,
    TarefaChamado,
)
from centralservicos.utils import Notificar
from comum.models import AreaAtuacao, Configuracao, User
from comum.utils import get_uo
from djtools import db, layout
from djtools.choices import Meses
from djtools.html.graficos import ColumnChart, LineChart, PieChart
from djtools.signals import minhas_acoes
from djtools.storages import upload_temporary_file
from djtools.templatetags.filters.utils import in_group
from djtools.utils import JsonResponse, Relatorio, generate_pdf, group_required, httprr, permission_required, rtr
from rh.models import UnidadeOrganizacional


@layout.atribuidos_a_mim()
def index_atribuidos_a_mim(request):
    pendencias = []

    # chamados resolvidos e que podem ser fechados pelo usuário atual
    qtd_posso_fechar = Chamado.chamados_a_fechar(usuario=request.user, como_requisitante=True).count()
    if qtd_posso_fechar:
        pendencias.append(
            {
                'titulo': f'Chamado{pluralize(qtd_posso_fechar)} resolvido{pluralize(qtd_posso_fechar)}',
                'subtitulo': 'a fechar',
                'qtd': qtd_posso_fechar,
                'url': '/centralservicos/meus_chamados/?tab=a_fechar',
            }
        )

    # Alerta "serviços sem grupo de atendimento ativo" para os usuários do grupo "Gestor da Central de Serviços"
    eh_gestor_central = request.user.has_group_cached('Gestor da Central de Serviços', ignore_groups_if_superuser=False)
    if eh_gestor_central:
        qtd = Servico.get_servicos_ativos_sem_grupo_atendimento_ativo().count()
        if qtd:
            pendencias.append(
                {
                    'titulo': f'Serviço{pluralize(qtd)}',
                    'subtitulo': 'sem grupo de atendimento ativo',
                    'qtd': qtd,
                    'url': '/admin/centralservicos/servico/?grupo_atendimento=sem_grupo_ativo',
                }
            )

    return pendencias


@layout.atribuidos_a_meus_grupos()
def index_atribuidos_a_meus_grupos(request):
    pendencias = []
    usuario = request.user
    eh_atendente_central = usuario.has_group_cached('Atendente da Central de Serviços', ignore_groups_if_superuser=False)
    eh_supervidor_central = usuario.has_group_cached('Supervisor da Base de Conhecimento', ignore_groups_if_superuser=False)
    if eh_atendente_central:
        chamados_sem_atribuicao = Chamado.SEM_ATRIBUICAO
        qtd = Chamado.get_chamados_do_suporte(user=usuario, atribuicoes=Chamado.SEM_ATRIBUICAO).count()
        if qtd:
            pendencias.append(
                {
                    'titulo': f'Chamado{pluralize(qtd)}',
                    'subtitulo': 'a atribuir',
                    'qtd': qtd,
                    'url': f'/centralservicos/listar_chamados_suporte/?atribuicoes={chamados_sem_atribuicao}',
                }
            )
    if (eh_atendente_central or eh_supervidor_central) and (request.user.has_perm('centralservicos.change_baseconhecimento')):
        areas = GrupoAtendimento.areas_vinculadas_ao_meu_centro_atendimento(request.user)
        meus_grupos = GrupoAtendimento.meus_grupos(request.user)
        basesconhecimento = (
            BaseConhecimento.objects.filter(area__in=areas)
            .filter(Q(grupos_atendimento__isnull=True) | Q(grupos_atendimento__in=meus_grupos))
            .distinct()
        )

        basesconhecimento_supervisao_pendente = basesconhecimento.filter(supervisao_pendente=True)
        qtd = basesconhecimento_supervisao_pendente.count()
        if qtd > 0:
            pendencias.append(
                {
                    'titulo': f'Artigo{pluralize(qtd)} da base de conhecimentos',
                    'subtitulo': 'a revisar',
                    'qtd': qtd,
                    'url': '/admin/centralservicos/baseconhecimento/?tab=tab_supervisao_pendente',
                }
            )

        basesconhecimento_supervisao_pendente = basesconhecimento.filter(necessita_correcao=True)
        qtd = basesconhecimento_supervisao_pendente.count()
        if qtd > 0:
            pendencias.append(
                {
                    'titulo': f'Artigo{pluralize(qtd)} da base de conhecimentos',
                    'subtitulo': 'a corrigir',
                    'qtd': qtd,
                    'url': '/admin/centralservicos/baseconhecimento/?tab=tab_necessita_correcao',
                }
            )

    return pendencias


@layout.quadro('Central de Serviços', icone='list', pode_esconder=True)
def index_quadros(quadro, request):
    usuario = request.user

    # chamados em atendimento nos quais o usuário atual é interessado
    qtd_tenho_algum_interesse = Chamado.get_chamados_do_usuario(
        usuario, status=StatusChamado.EM_ATENDIMENTO, tipo_usuario=Chamado.TIPO_USUARIO_ALGUM_INTERESSE
    ).count()
    if qtd_tenho_algum_interesse:
        quadro.add_item(
            layout.ItemContador(
                titulo=f'Chamado{pluralize(qtd_tenho_algum_interesse)} como interessado',
                subtitulo='Em andamento',
                qtd=qtd_tenho_algum_interesse,
                url=f'/centralservicos/meus_chamados/?tab=em_atendimento&tipo_usuario={Chamado.TIPO_USUARIO_ALGUM_INTERESSE}',
            )
        )

    if usuario.has_group_cached('Atendente da Central de Serviços', ignore_groups_if_superuser=False):
        qtd_chamados_atribuidos_a_mim = Chamado.get_chamados_do_suporte(user=usuario, atribuicoes=Chamado.ATRIBUIDOS_A_MIM).count()
        if qtd_chamados_atribuidos_a_mim:
            quadro.add_item(
                layout.ItemContador(
                    titulo=f'Chamado{pluralize(qtd_chamados_atribuidos_a_mim)}',
                    subtitulo='Em atendimento',
                    qtd=qtd_chamados_atribuidos_a_mim,
                    url='/centralservicos/listar_chamados_suporte/?atribuicoes=1',
                )
            )

        chamados_atribuidos_a_mim = Chamado.get_chamados_do_suporte(user=usuario, atribuicoes=Chamado.ATRIBUIDOS_A_MIM)
        prazo_24_horas = datetime.date.today() + relativedelta(days=+1)
        vencendo_amanha = chamados_atribuidos_a_mim.filter(
            data_limite_atendimento__gt=datetime.datetime.now(), data_limite_atendimento__date__lte=prazo_24_horas
        ).count()
        if vencendo_amanha:
            quadro.add_item(
                layout.ItemContador(
                    titulo=f'Chamado{pluralize(vencendo_amanha)}',
                    subtitulo=f'Atribuído{pluralize(vencendo_amanha)} a mim com data limite em 24 horas',
                    qtd=vencendo_amanha,
                    url='/centralservicos/listar_chamados_suporte/?atribuicoes=1',
                )
            )

        vencidos = chamados_atribuidos_a_mim.filter(data_limite_atendimento__lt=datetime.datetime.now()).count()
        if vencidos:
            quadro.add_item(
                layout.ItemContador(
                    titulo=f'Chamado{pluralize(vencidos)}',
                    subtitulo='Atrasado{0} atribuído{0} a mim'.format(pluralize(vencidos)),
                    qtd=vencidos,
                    url='/centralservicos/listar_chamados_suporte/?atribuicoes=1',
                )
            )

        qtd_tarefas_vinculadas_ativas = TarefaChamado.get_tarefas_vinculadas_ativas(usuario).count()
        if qtd_tarefas_vinculadas_ativas:
            quadro.add_item(
                layout.ItemContador(
                    titulo=f'Tarefa{pluralize(qtd_tarefas_vinculadas_ativas)} em chamado{pluralize(qtd_tarefas_vinculadas_ativas)} atribuída{pluralize(qtd_tarefas_vinculadas_ativas)} a você',
                    subtitulo='ativas',
                    qtd=qtd_tarefas_vinculadas_ativas,
                    url=f'/admin/centralservicos/tarefachamado/?responsavel={usuario.id}&tab=tab_ativas',
                )
            )

    if usuario.has_perm('centralservicos.view_chamado'):
        quadro.add_item(layout.ItemAcessoRapido(titulo='Meus chamados', url='/centralservicos/meus_chamados/?tab=ativos', icone='bars'))
        quadro.add_item(layout.ItemAcessoRapido(titulo='Abrir chamado', url='/centralservicos/listar_area_servico/', icone='plus', classe='success'))
        quadro.add_item(layout.ItemAcessoRapido(titulo='Base de Conhecimentos', icone='question', url='/centralservicos/baseconhecimento/'))

    tarefas_vinculadas_ativas_por_situacao = TarefaChamado.get_tarefas_vinculadas_ativas_por_situacao(usuario)
    if tarefas_vinculadas_ativas_por_situacao:
        for situacao, info in tarefas_vinculadas_ativas_por_situacao.items():
            situacao_qtd = info[1].count()
            if situacao_qtd:
                situacao_descricao = info[0]
                quadro.add_item(
                    layout.ItemContador(
                        titulo=f'Tarefa{pluralize(situacao_qtd)} em chamado{pluralize(situacao_qtd)}',
                        subtitulo=f'{situacao_descricao} atribuída{pluralize(situacao_qtd)} a você',
                        qtd=situacao_qtd,
                        url=f'/admin/centralservicos/tarefachamado/?situacao__exact={situacao}&responsavel={usuario.id}&tab=tab_ativas',
                    )
                )

    return quadro


@rtr('centralservicos/templates/listar_area_servico.html')
@permission_required(['centralservicos.view_chamado', 'centralservicos.change_chamado'])
def listar_area_servico(request):
    title = 'Listar Áreas de serviço'
    title_box = 'Ou selecione a Área de Serviço para a qual deseja abrir o chamado:'
    link_prefix = '/centralservicos/selecionar_servico_abertura/'

    servicos_ao_usuario = Servico.get_servicos_ao_usuario(request.user)

    # Lista de áreas restrita aos serviços ao usuário.
    lista_areas = AreaAtuacao.objects.filter(
        ativo=True,
        servico__id__in=servicos_ao_usuario.values_list('id', flat=True),
    ).distinct()

    FormClass = BuscarServicoFormFactory(servicos_ao_usuario)
    form = FormClass(request.POST or None)
    if form.is_valid():
        servico = form.cleaned_data.get('servico')
        if servico:
            return redirect(reverse('centralservicos_visualizar_solucoes', args=(servico.pk,)))
        else:
            return httprr('.', 'Selecione um serviço da lista.', tag='error')

    return locals()


@rtr('centralservicos/templates/selecionar_servico_abertura_chamado.html')
@permission_required(['centralservicos.view_chamado', 'centralservicos.change_chamado'])
def selecionar_servico_abertura_chamado(request, slug):
    area = get_object_or_404(AreaAtuacao, slug=slug)
    if not area.ativo:
        raise PermissionDenied('Não é possível abrir um chamado para este serviço, pois a Área de Serviço não está ativa.')

    title = f'Abrir chamado para {area.nome}'

    servicos_ao_usuario = Servico.get_servicos_ao_usuario(request.user, area)
    lista_categorias = (
        CategoriaServico.objects.select_related(
            'area',
        )
        .filter(area=area)
        .distinct()
    )
    FormClass = BuscarServicoFormFactory(servicos_ao_usuario)

    form = FormClass(request.POST or None)
    if form.is_valid():
        servico = form.cleaned_data.get('servico')
        if servico:
            return redirect(reverse('centralservicos_visualizar_solucoes', args=(servico.pk,)))
        else:
            return httprr('.', 'Selecione um serviço da lista.', tag='error')

    return locals()


@rtr('centralservicos/templates/listar_area_servico.html')
@permission_required(['centralservicos.view_baseconhecimento', 'centralservicos.add_chamado'])
def baseconhecimento_listar_area_servico(request):
    title = 'Listar Áreas de serviço'
    title_box = 'Ou Selecione a Área do Serviço para a qual deseja consultar bases de conhecimento:'
    link_prefix = '/centralservicos/baseconhecimento/dashboard/'

    form = BuscarArtigoForm(request.POST or None)
    if form.is_valid():
        baseconhecimento = form.cleaned_data.get('baseconhecimento')
        if baseconhecimento:
            return httprr(f'/centralservicos/baseconhecimento/{baseconhecimento.pk}/')
        else:
            return httprr('.', 'Selecione uma base da lista.', tag='error')

    if request.user.has_perm('centralservicos.view_baseconhecimento'):
        # Lista de áreas restrita aos serviços ao usuário.
        servicos_ao_usuario = Servico.get_servicos_ao_usuario(request.user)
        lista_areas = AreaAtuacao.objects.filter(
            ativo=True,
            servico__id__in=servicos_ao_usuario.values_list('id', flat=True),
        ).distinct()
    else:
        # Lista de áreas restrita ao usuario comum.
        lista_areas = AreaAtuacao.objects.filter(
            ativo=True,
            servico__interno=False,
            servico__base_conhecimento_servicos_set__visibilidade=BaseConhecimento.VISIBILIDADE_PUBLICA,
        ).distinct()

    return locals()


@rtr('centralservicos/templates/baseconhecimento.html')
@permission_required(['centralservicos.view_baseconhecimento', 'centralservicos.add_chamado'])
def baseconhecimento(request, slug):
    area = get_object_or_404(AreaAtuacao, slug=slug)
    if not area.ativo:
        raise PermissionDenied('Não é possível consultar Base de Conhecimento nesta área, pois a mesma não está ativa.')

    title = f'Base de Conhecimentos: {area.nome}'
    eh_atendente_desta_area = (
        request.user.has_perm('centralservicos.view_baseconhecimento') and GrupoAtendimento.meus_grupos(request.user, area).exists()
    )

    form = BuscarArtigoForm(request.POST or None, eh_atendente_desta_area=eh_atendente_desta_area, area=area)
    if form.is_valid():
        baseconhecimento = form.cleaned_data.get('baseconhecimento')
        if baseconhecimento:
            return httprr(f'/centralservicos/baseconhecimento/{baseconhecimento.pk}/')
        else:
            return httprr('.', 'Selecione uma base da lista.', tag='error')

    if eh_atendente_desta_area:
        lista_categorias = CategoriaServico.objects.filter(
            pk__in=BaseConhecimento.objects.filter(ativo=True, servicos__grupo_servico__categorias__area=area).values(
                'servicos__grupo_servico__categorias'
            )
        ).distinct()
        qs = (
            HistoricoStatus.objects.filter(status=StatusChamado.get_status_resolvido(), bases_conhecimento__area=area, bases_conhecimento__ativo=True)
            .values('bases_conhecimento__id')
            .annotate(total=Count('bases_conhecimento__id'))
            .order_by('-total')[:5]
            .values('bases_conhecimento__id')
        )

        mais_populares = BaseConhecimento.objects.filter(id__in=qs)
        mais_populares = sorted(mais_populares, key=lambda t: t.get_quantidade_utilizacoes, reverse=True)
        ultimos_cadastrados = BaseConhecimento.objects.filter(area=area, ativo=True).order_by('-atualizado_em').distinct()[:5]
    else:
        lista_categorias = CategoriaServico.objects.filter(
            pk__in=BaseConhecimento.objects.filter(
                ativo=True,
                visibilidade=BaseConhecimento.VISIBILIDADE_PUBLICA,
                servicos__grupo_servico__categorias__area=area,
                servicos__interno=False,
            ).values('servicos__grupo_servico__categorias')
        ).distinct()
        qs = (
            HistoricoStatus.objects.filter(
                status=StatusChamado.get_status_resolvido(),
                bases_conhecimento__ativo=True,
                bases_conhecimento__visibilidade=BaseConhecimento.VISIBILIDADE_PUBLICA,
                bases_conhecimento__area=area,
            )
            .values('bases_conhecimento__id')
            .annotate(total=Count('bases_conhecimento__id'))
            .order_by('-total')[:5]
            .values('bases_conhecimento__id')
        )

        mais_populares = BaseConhecimento.objects.filter(id__in=qs)
        mais_populares = sorted(mais_populares, key=lambda t: t.get_quantidade_utilizacoes, reverse=True)
        ultimos_cadastrados = (
            BaseConhecimento.objects.filter(ativo=True, visibilidade=BaseConhecimento.VISIBILIDADE_PUBLICA, area=area)
            .order_by('-atualizado_em')
            .distinct()[:5]
        )

    return locals()


@rtr('centralservicos/templates/visualizar_solucoes.html')
@permission_required('centralservicos.add_chamado')
def visualizar_solucoes(request, servico_id):
    servico = get_object_or_404(Servico, pk=servico_id)
    title = servico
    if (not servico.tem_bases_conhecimento_publicas()) or (servico.nao_exibir_artigos is True):
        url = f'/centralservicos/abrir_chamado/{servico.id}/'
        return httprr(url)
    else:
        bases = list(servico.get_bases_conhecimento_faq())
        bases.sort(key=lambda x: x.get_quantidade_utilizacoes, reverse=True)
    return locals()


def _validar_abertura_de_chamado(request, servico):
    """Valida as pré-condições para abrir um chamado; levanta PermissionDenied quando alguma falha."""
    pode_abrir_chamado_interno = (
        request.user.has_perm('centralservicos.change_chamado')
        and GrupoAtendimento.meus_grupos(request.user, servico.area).filter(ativo=True).exists()
    )
    if servico.interno and not pode_abrir_chamado_interno:
        raise PermissionDenied('Você não tem permissão para abrir um chamado interno.')
    if not servico.ativo:
        raise PermissionDenied('Não é possível abrir um chamado para este serviço, pois o mesmo está inativo.')
    if not servico.pode_acessar_servico(request.user):
        raise PermissionDenied('Você não tem permissão para abrir um chamado desse serviço pois não faz parte do seu público.')
    campus_default = get_uo(request.user)
    if campus_default is None:
        raise PermissionDenied("""
                               Você não pode abrir um chamado, pois não possui uma Ocupação ativa na instituição.
                               Por favor, entrar em contato com o setor responsável pelo seu cadastro.
                               """)
    return campus_default


def _preencher_atores_padrao_do_chamado(form, request):
    if not hasattr(form.instance, 'interessado') or not form.cleaned_data.get('interessado'):
        form.instance.interessado = request.user
    if not hasattr(form.instance, 'requisitante') or not form.cleaned_data.get('requisitante'):
        form.instance.requisitante = form.instance.interessado


def _salvar_anexos_do_chamado(formset, chamado, request):
    for frm in formset.forms:  # Para cada Anexo
        if frm.cleaned_data.get('anexo'):
            frm.instance.chamado = chamado
            frm.instance.anexado_em = datetime.datetime.today()
            frm.instance.anexado_por = request.user
            frm.instance.anexo = frm.cleaned_data.get('anexo')
            frm.save()


def _redirecionar_apos_abertura_de_chamado(request, servico, chamado):
    if chamado.pode_visualizar(request.user):
        return httprr(Chamado.get_absolute_url(chamado), 'Chamado aberto com sucesso.')
    url = f'/centralservicos/selecionar_servico_abertura/{servico.area.slug}/'
    return httprr(url, f'Chamado aberto com sucesso. Número do chamado:{chamado.pk}')


@rtr('centralservicos/templates/form_abrir_chamado.html')
@permission_required(['centralservicos.add_chamado'])
def abrir_chamado(request, servico_id):
    servico = get_object_or_404(Servico, pk=servico_id)

    campus_default = _validar_abertura_de_chamado(request, servico)

    if not servico.tem_grupo_atendimento_ativo():
        return httprr(
            '/centralservicos/listar_area_servico/',
            tag='error',
            message=f"O serviço '{servico.nome}' não possui grupo de atendimento ativo.",
        )

    title = servico.nome
    interno = '(Interno)' if servico.interno else ''
    title = f'{servico.nome} {interno}'

    # Os atores de um chamado são instâncias de User. Mas os choices fields correspondentes, no
    # formulário a seguir, trabalham com instâncias de Vinculo. Então os consumidores dessa view
    # devem parametrizar, se for o caso, os fields dos atores com IDs de Vinculo.

    FormClass = ChamadoFormFactory(request, servico=servico)
    form = FormClass(request.POST or None)

    formset = ChamadoAnexoFormset(request.POST or None, request.FILES or None)
    form.instance.servico = servico
    _preencher_atores_padrao_do_chamado(form, request)

    if form.is_valid() and formset.is_valid():
        try:
            form.instance.aberto_em = datetime.datetime.today()
            form.instance.aberto_por = request.user

            if not servico.requer_numero_patrimonio:
                FormClass.base_fields['patrimonio'].value = None

            if not hasattr(form.instance, 'meio_abertura') or not form.cleaned_data.get('meio_abertura'):
                form.instance.meio_abertura = Chamado.MEIO_ABERTURA_WEB

            """ É necessário fazer essa consulta pois esse atributo no form não é um objeto do tipo CentroAtendimento """
            form.instance.centro_atendimento = form.cleaned_data.get('centro_atendimento')
            form.instance.campus = UnidadeOrganizacional.objects.suap().get(pk=form.cleaned_data.get('uo'))

            form.save()

            if servico.permite_anexos:
                _salvar_anexos_do_chamado(formset, form.instance, request)

            Notificar.chamado_aberto(form.instance, form.cleaned_data.get('enviar_copia_email'))
            return _redirecionar_apos_abertura_de_chamado(request, servico, form.instance)

        except ValidationError as e:
            messages.error(request, ''.join(e.messages))

    return locals()


@rtr('centralservicos/templates/chamado.html')
@permission_required(['centralservicos.view_chamado', 'centralservicos.change_chamado'])
def visualizar_chamado(request, chamado_id):
    chamado = Chamado.annotate_ultima_interacao(Chamado.objects.filter(pk=chamado_id)).select_related('aberto_por', 'requisitante').first()
    if not chamado:
        raise Http404(f'Não existe o chamado {chamado_id}')

    eh_atendente = chamado.eh_atendente(request.user)
    eh_pessoa_envolvida = chamado.pessoa_envolvida(request.user)

    permissoes = chamado.get_permissoes(request.user)
    pode_visualizar = permissoes['pode_visualizar']

    if not pode_visualizar:
        raise PermissionDenied('Você não tem permissão para visualizar este chamado.')

    pode_adicionar_comentario = permissoes['pode_adicionar_comentario']
    pode_adicionar_nota_interna = permissoes['pode_adicionar_nota_interna']
    pode_adicionar_anexo = permissoes['pode_adicionar_anexo']

    hoje = datetime.datetime.today()
    interno = 'Interno' if chamado.servico.interno else ''
    title = f'Chamado {interno} {chamado_id}'
    pode_alterar_status = eh_atendente and not (chamado.estah_resolvido() or chamado.estah_cancelado() or chamado.estah_fechado())
    pode_fechar = chamado.pode_fechar(request.user)
    pode_reabrir = chamado.pode_reabrir(request.user)
    pode_assumir = chamado.pode_assumir(request.user)
    pode_suspender = chamado.pode_suspender(request.user)
    pode_reclassificar = chamado.pode_reclassificar(request.user)
    pode_cancelar = chamado.pode_cancelar(request.user)
    pode_adicionar_outros_interessados = (
        eh_pessoa_envolvida or eh_atendente or request.user.is_superuser or request.user in chamado.get_responsaveis_equipe_atendimento()
    ) and chamado.status not in (StatusChamado.get_status_fechado(), StatusChamado.get_status_resolvido(), StatusChamado.get_status_cancelado())

    initial_tab = None

    if chamado.estah_em_atendimento() and eh_atendente:
        bases_de_conhecimento = list(
            chamado.servico.get_bases_de_conhecimento_disponiveis(chamado.get_atendimento_atribuicao_atual().grupo_atendimento)
        )
        bases_de_conhecimento.sort(
            key=lambda x: (x.estah_disponivel_para_uso(), x.get_media_avaliacoes(), x.get_quantidade_utilizacoes), reverse=True
        )
        perguntas_avaliacao = PerguntaAvaliacaoBaseConhecimento.objects.filter(area=chamado.servico.area, ativo=True)
        respostas_padrao = RespostaPadrao.objects.filter(atendente=request.user)

    FormClass = ComunicacaoFormFactory(request, chamado)
    form = FormClass()

    acoes = []
    if not chamado.estah_cancelado():
        if not chamado.estah_fechado() and not chamado.estah_resolvido():
            if request.user in chamado.get_responsaveis_equipe_atendimento():
                acoes.append(f'<li><a class="popup" href="/centralservicos/atribuir_chamado/{chamado.pk:d}/">Atribuir</a></li>')
        if eh_atendente or request.user in chamado.get_responsaveis_equipe_atendimento():
            if chamado.pode_escalar():
                acoes.append(f'<li><a href="/centralservicos/escalar_atendimento_chamado/{chamado.pk:d}/">Escalar</a></li>')
            if chamado.pode_retornar():
                acoes.append(f'<li><a href="/centralservicos/retornar_atendimento_chamado/{chamado.pk:d}/">Retornar</a></li>')
            if chamado.pode_criar_processo(request.user):
                acoes.append(f'<li><a href="/centralservicos/criar_processo_de_chamado/{chamado.pk:d}/">Criar processo eletrônico</a></li>')
            areas = GrupoAtendimento.areas_vinculadas_ao_meu_centro_atendimento(request.user)
            if chamado.tem_tags_disponiveis(areas):
                acoes.append(f'<li><a class="popup" href="/centralservicos/adicionar_tags_ao_chamado/{chamado.pk:d}/">Adicionar tags</a></li>')
        if pode_reclassificar:
            acoes.append(f'<li><a href="/centralservicos/reclassificar_chamado/{chamado.pk:d}/">Reclassificar</a></li>')
            if 'erros' in settings.INSTALLED_APPS:
                acoes.append(f'<li><a class="popup" href="/erros/reportar_erro_por_chamado/{chamado.pk:d}/">Reportar erro do sistema</a></li>')
        if pode_adicionar_outros_interessados:
            acoes.append(
                f'<li><a class="popup" href="/centralservicos/adicionar_outros_interessados/{chamado.pk:d}/">Adicionar outros interessados</a></li>'
            )
            if GrupoInteressado.objects.filter(grupo_atendimento=chamado.get_atendimento_atribuicao_atual().grupo_atendimento).exists():
                acoes.append(
                    f'<li><a class="popup" href="/centralservicos/adicionar_grupo_de_interessados/{chamado.pk:d}/">Adicionar grupo de interessados</a></li>'
                )
        if pode_alterar_status and chamado.estah_em_atendimento():
            acoes.append(
                f'<li><a class="popup" href="/centralservicos/visualizar_chamados_semelhantes/{chamado.pk:d}/">Visualizar chamados semelhantes</a></li>'
            )
        if request.user.has_perm('centralservicos.solve_chamado'):
            acoes.append(
                f'<li><a class="popup" href="/centralservicos/visualizar_outros_chamados_do_interessado/{chamado.pk:d}/">Outros chamados do interessado</a></li>'
            )
        if request.user.has_perm('centralservicos.change_servico'):
            acoes.append(f'<li><a href="/admin/centralservicos/servico/{chamado.servico.pk}/change/">Editar serviço</a></li>')
        if chamado.servico and Servico.get_servicos_ao_atendente(request.user).filter(id=chamado.servico.id).exists():
            acoes.append(f'<li><a href="/centralservicos/estatisticas_servico/{chamado.servico.pk}/">Estatísticas do serviço</a></li>')
        if not chamado.interessado.eh_aluno and request.user.has_perms(
            ['comum.is_coordenador_de_ti_de_campus', 'comum.is_coordenador_de_ti_sistemico']
        ):
            acoes.append(f'<li><a class="popup" href="/comum/grupos_usuario/{chamado.interessado.pk}/">Grupos do interessado</a></li>')

    ResolverChamadoFormClass = ResolverChamadoFormFactory(request, chamado)
    if 'resolverchamado_form' in request.POST or {}:
        resolver_chamado_form = ResolverChamadoFormClass(request.POST)
        if resolver_chamado_form.is_valid():
            try:
                chamados_ids = resolver_chamado_form.resolver_chamado()
                return httprr(
                    chamado.get_absolute_url(),
                    f'Alteração de situação realizada com sucesso. Os seguintes chamados foram resolvidos: {", ".join(chamados_ids)}.',
                )
            except TransitionNotAllowed:
                raise PermissionDenied('Você não tem permissão para alterar a situação deste chamado.')
        else:
            initial_tab = 'bases'
    else:
        resolver_chamado_form = ResolverChamadoFormClass()

    if chamado.pode_editar_patrimonio_relacionado(request.user):
        acoes.append(
            f'<li><a class="popup" href="/centralservicos/editar_patrimonio_relacionado/{chamado.pk:d}/">Editar patrimônio relacionado</a></li>'
        )

    if chamado.servico_requer_numero_patrimonio():
        if chamado.patrimonio:
            chamado_patrimonio_display_html = f'<a class="popup" href="/patrimonio/inventario/{chamado.patrimonio.numero}/">{chamado.patrimonio}</a>'
        else:
            chamado_patrimonio_display_html = '<span>-</span>'

    tarefas_cadastradas_servico = chamado.servico.get_tarefas_cadastradas() if chamado.servico else Servico.objects.none()
    tarefas_cadastradas_servico_qtd = tarefas_cadastradas_servico.count()
    tarefas_vinculadas_chamado_info = chamado.get_tarefas_vinculadas_info(request.user)
    tarefas_vinculadas_chamado_qtd = len(tarefas_vinculadas_chamado_info)
    eh_atendente_central_servicos = in_group(request.user, 'Atendente da Central de Serviços', ignore_groups_if_superuser=False)
    exibir_tab_tarefas = (tarefas_cadastradas_servico_qtd and eh_atendente_central_servicos) or (
        tarefas_vinculadas_chamado_qtd and chamado.eh_ou_foi_responsavel_por_tarefa_vinculada(request.user)
    )
    pode_vincular_tarefas = chamado.pode_vincular_tarefas(request.user)

    return locals()


def finalizar_chamado(numero_processo_criado=None, url_processo=None, erros=None, on_finish_extra_params=None):
    chamado, request = on_finish_extra_params

    observacao_fechamento = None
    if numero_processo_criado:
        if url_processo:
            processo_referenciado = f'Processo <a href="{url_processo}">{numero_processo_criado}</a>'
        else:
            processo_referenciado = f'Processo {numero_processo_criado}'
        observacao_fechamento = (
            f'Chamado fechado automaticamente, gerando abertura do {processo_referenciado}.<br>'
            f'Você pode acompanhá-lo pelo seu SUAP, na área "Documentos/Processos".'
        )
    if chamado.estah_em_atendimento():
        if erros:
            observacao_fechamento += (
                '<p><b>OBSERVAÇÃO:</b> O processo já foi encaminhado, mas os seguintes arquivos não puderam ser '
                'anexados automaticamente. <b>Anexe-os manualmente</b>:</p>'
                '<ul>'
            )
            for arquivo, mensagem in erros.items():
                observacao_fechamento += f'<li><b>{arquivo}:</b> {mensagem}.</li>'
            observacao_fechamento += '</ul>'

        chamado.resolver_chamado(request.user, [])
        chamado.fechar_chamado(request.user, fechado_automaticamente=True, observacao=observacao_fechamento)


@rtr()
@login_required()
@group_required('Atendente da Central de Serviços')
@transaction.atomic
def criar_processo_de_chamado(request, chamado_id):
    title = 'Criar processo a partir de chamado'

    chamado = get_object_or_404(Chamado, pk=chamado_id)
    try:
        if 'processo_eletronico' not in settings.INSTALLED_APPS:
            return httprr(chamado.get_absolute_url(), message='O módulo de Processo Eletrônico não está disponível.', tag='error')

        if not chamado.pode_criar_processo(request.user):
            return httprr(
                chamado.get_absolute_url(),
                message=(
                    f'Não é permitido criar processo a partir do chamado #{chamado.id}. '
                    f'Verifique se o serviço permite essa operação e se você possui as permissões necessárias.'
                ),
                tag='error',
            )

        # Iniciando coleta de dados...
        # Coletando dados do chamado...
        contexto_extrato_do_chamado = {
            'chamado': chamado,
            'nome_instituicao': Configuracao.get_valor_por_chave('comum', 'instituicao'),
            'data_emissao': datetime.datetime.now(),
            # Seção 1 - Dados gerais
            'dados_gerais': {
                # TODO: utilizar um meio mais confiável de obter matrícula, ao invés de user.username
                'interessado': f'{chamado.interessado.get_profile().nome} ({chamado.interessado.username})',
                'data_abertura': chamado.aberto_em,
                # TODO: utilizar um meio mais confiável de obter matrícula, ao invés de user.username
                'aberto_por': f'{chamado.aberto_por.get_profile().nome} ({chamado.aberto_por.username})',
                'url_chamado': chamado.get_visualizar_chamado_url(),
            },
            # Seção 2 - Decrição
            'descricao': chamado.descricao,
            # Seção 3 - Linha do Tempo
            'linha_do_tempo': chamado.get_linha_do_tempo(ordem_decrescente=False, somente_tipos=['comentario', 'historicostatus', 'anexo']),
        }

        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as pdf_extrato:
            pdf_extrato.write(generate_pdf(template_name='extrato_chamado_pdf.html', context=contexto_extrato_do_chamado).getvalue())
        extrato_path = upload_temporary_file(pdf_extrato.name)

        extrato_do_chamado = {
            'name': f'extrato_chamado_{chamado_id}.pdf',
            'descricao': f'Extrato do Chamado {chamado_id}',
            'path': extrato_path,
            'url_publica': chamado.get_absolute_url(),
            'temporario': True,
        }

        # Coletando pre-definições do processo...
        anexos_do_chamado = [extrato_do_chamado] + [
            {
                'name': chamado_anexo.anexo.name.split('/')[-1],
                'descricao': chamado_anexo.descricao,
                'path': chamado_anexo.anexo.name,
                'url_publica': f'{settings.SITE_URL}{chamado_anexo.anexo.get_url_publica()}',
                'temporario': False,
            }
            for chamado_anexo in ChamadoAnexo.objects.filter(chamado__id=chamado_id).all()
        ]

        dados_do_processo = {
            'assunto': chamado.descricao,
            'anexos_do_chamado': anexos_do_chamado,
            'ids_interessados': [vinculo.id for vinculo in chamado.get_vinculos_interessados()],
        }

        from processo_eletronico.forms import CriarProcessoComTramiteForm

        form = CriarProcessoComTramiteForm(request.POST or None, dados_iniciais=dados_do_processo, request=request)

        if form.is_valid():
            form.processar(notificar=True, on_finish=finalizar_chamado, on_finish_extra_params=[chamado, request])
            return httprr(chamado.get_absolute_url(), 'Criando processo em segundo plano. Você será notificado(a) quando a operação terminar.')

    except Exception as e:
        if settings.DEBUG:
            raise e
        messages.error(request, 'Ocorreu um erro ao criar o processo.')
        sentry_sdk.capture_exception(e)

    return locals()


@csrf_exempt
@permission_required('centralservicos.change_chamado')
def avaliar_baseconhecimento(request, baseconhecimento_id, pergunta_id, nota):
    base_conhecimento = get_object_or_404(BaseConhecimento, pk=baseconhecimento_id)
    pergunta = get_object_or_404(PerguntaAvaliacaoBaseConhecimento, pk=pergunta_id)
    AvaliaBaseConhecimento.objects.update_or_create(
        base_conhecimento=base_conhecimento, pergunta=pergunta, avaliado_por=request.user, defaults={'nota': nota}
    )

    qtd_perguntas = PerguntaAvaliacaoBaseConhecimento.objects.filter(area=base_conhecimento.area, ativo=True).count()
    qtd_avaliacoes_usuario = AvaliaBaseConhecimento.objects.filter(
        base_conhecimento=base_conhecimento, avaliado_por=request.user, data__gte=base_conhecimento.atualizado_em
    ).count()
    avaliou_todas_perguntas = qtd_perguntas == qtd_avaliacoes_usuario
    media_avaliacoes = f'{base_conhecimento.get_media_avaliacoes():,.1f}'.replace('.', ',')
    qtd_avaliacoes = base_conhecimento.get_quantidade_avaliacoes

    return JsonResponse(
        {'ok': True, 'avaliou_todas_perguntas': avaliou_todas_perguntas, 'media_avaliacoes': media_avaliacoes, 'qtd_avaliacoes': qtd_avaliacoes}
    )


@rtr('centralservicos/templates/visualizar_baseconhecimento.html')
@permission_required(['centralservicos.change_baseconhecimento', 'centralservicos.add_chamado'])
def visualizar_baseconhecimento(request, baseconhecimento_id):
    base_conhecimento = get_object_or_404(BaseConhecimento, pk=baseconhecimento_id)
    perguntas_avaliacao = PerguntaAvaliacaoBaseConhecimento.objects.filter(area=base_conhecimento.area, ativo=True)
    title = base_conhecimento.titulo
    tags = []
    if base_conhecimento.tags:
        tags = base_conhecimento.tags.split(', ')
    eh_atendente_desta_area = (
        request.user.has_perm('centralservicos.change_baseconhecimento')
        and GrupoAtendimento.meus_grupos(request.user, base_conhecimento.area).exists()
    )
    pode_editar_area = base_conhecimento.pode_editar_area(request.user)
    eh_admin_central_servicos = request.user.groups.filter(name='centralservicos Administrador').exists()
    return locals()


@rtr()
@permission_required('centralservicos.review_baseconhecimento')
@create_revision()
def aprovar_baseconhecimento(request, baseconhecimento_id):
    get_object_or_404(BaseConhecimento, pk=baseconhecimento_id)
    if request.method == 'POST':
        with transaction.atomic():
            BaseConhecimento.objects.filter(pk=baseconhecimento_id).update(necessita_correcao=False, supervisao_pendente=False)
            reversion.set_comment('Base de conhecimento aprovada.')
            messages.success(request, 'Base de conhecimento revisada com sucesso.')
    return redirect(reverse('centralservicos_visualizar_baseconhecimento', args=(baseconhecimento_id,)))


@rtr('centralservicos/templates/visualizar_baseconhecimento_publica.html')
@permission_required('centralservicos.add_chamado')
def visualizar_baseconhecimento_publica(request, baseconhecimento_id):
    base_conhecimento = get_object_or_404(BaseConhecimento, pk=baseconhecimento_id)
    if not base_conhecimento.visibilidade == BaseConhecimento.VISIBILIDADE_PUBLICA and not request.user.has_perm('centralservicos.change_chamado'):
        raise PermissionDenied('Esta base de conhecimento não é publica e por isso não pode ser visualizada neste endereço.')
    title = base_conhecimento.titulo
    return locals()


@rtr()
@login_required
def adicionar_anexo(request, chamado_id):
    title = 'Adicionar Anexo'
    chamado = get_object_or_404(Chamado, pk=chamado_id)
    # if not chamado.permite_visualizar(request.user):
    if not chamado.pode_adicionar_anexo(request.user):
        raise PermissionDenied('Você não tem permissão para adicionar anexo neste chamado.')
    form = ChamadoAnexoForm(request.POST or None, request.FILES or None)
    form.instance.chamado = chamado
    form.instance.anexado_por = request.user
    if form.is_valid():
        form.save()
        Notificar.adicao_anexo(form.instance)
        return httprr(chamado.get_absolute_url(), 'Anexo adicionado com sucesso.')
    return locals()


def __adicionar_comentario_ou_nota_interna(request, tipo, chamado_id):
    """Método privado, pois está sendo usado apenas internamente
    Responsável por adicionar um comentário ou nota interna no chamado
    """
    chamado = get_object_or_404(Chamado, pk=chamado_id)

    # if not chamado.permite_visualizar(request.user):
    #     raise PermissionDenied('Você não tem permissão para adicionar comentário ou nota interna neste chamado.')
    # elif chamado.status not in (
    #     StatusChamado.get_status_aberto(),
    #     StatusChamado.get_status_reaberto(),
    #     StatusChamado.get_status_em_atendimento(),
    #     StatusChamado.get_status_suspenso(),
    # ):
    #     raise PermissionDenied(
    #         f'Não é possível adicionar um comentário ou nota interna em um chamado com a situação atual ({chamado.get_status_display()}).'
    #     )

    # if tipo == Comunicacao.TIPO_NOTA_INTERNA and not (
    #     chamado.eh_atendente(request.user)
    #     or request.user in chamado.get_atendentes_equipe_atendimento()
    #     or request.user in chamado.get_responsaveis_equipe_atendimento()
    # ):
    #     raise PermissionDenied('Você não tem permissão para adicionar uma Nota Interna neste chamado.')

    permissoes = chamado.get_permissoes(request.user)

    if tipo == Comunicacao.TIPO_COMENTARIO:
        if not permissoes['pode_adicionar_comentario']:
            raise PermissionDenied('Você não tem permissão para adicionar um comentário neste chamado.')
    else:
        if not permissoes['pode_adicionar_nota_interna']:
            raise PermissionDenied('Você não tem permissão para adicionar uma nota interna neste chamado.')

    FormClass = ComunicacaoFormFactory(request, chamado)
    form = FormClass(request.POST or None)
    form.instance.chamado = chamado
    form.instance.remetente = request.user
    form.instance.tipo = tipo
    if form.is_valid():
        form.save()
        if tipo == Comunicacao.TIPO_COMENTARIO:
            mensagem = 'Comentário adicionado com sucesso.'
            url = f'{chamado.get_absolute_url()}?tab=linha_tempo'
        else:
            mensagem = 'Nota Interna adicionada com sucesso.'
            url = f'{chamado.get_absolute_url()}?tab=notas_internas'
        return httprr(url, mensagem)
    else:
        mensagem = 'Não foi possível enviar a sua mensagem.'
        if tipo == Comunicacao.TIPO_COMENTARIO:
            url = f'{chamado.get_absolute_url()}?tab=linha_tempo'
        else:
            url = f'{chamado.get_absolute_url()}?tab=notas_internas'
        return httprr(url, mensagem, 'error')


@rtr()
@permission_required(['centralservicos.add_comment', 'centralservicos.change_chamado'])
@require_POST
def arquivar_comentario(request: HttpRequest, comentario_id: int) -> HttpResponse:
    comentario = get_object_or_404(Comunicacao, pk=comentario_id, tipo=Comunicacao.TIPO_COMENTARIO)
    if comentario.remetente != request.user or not comentario.chamado.pode_adicionar_comentario(request.user):
        raise PermissionDenied('Você não tem permissão para arquivar este comentário.')
    if comentario.escondida_em is None:
        comentario.escondida_em = datetime.datetime.now()
        comentario.save(update_fields=['escondida_em'])
    return httprr(f'{comentario.chamado.get_absolute_url()}?tab=linha_tempo', 'Comentário arquivado com sucesso.')


@rtr()
@permission_required(['centralservicos.add_comment', 'centralservicos.change_chamado'])
@require_POST
def desarquivar_comentario(request: HttpRequest, comentario_id: int) -> HttpResponse:
    comentario = get_object_or_404(Comunicacao, pk=comentario_id, tipo=Comunicacao.TIPO_COMENTARIO)
    if comentario.remetente != request.user or not comentario.chamado.pode_adicionar_comentario(request.user):
        raise PermissionDenied('Você não tem permissão para desarquivar este comentário.')
    if comentario.escondida_em is not None:
        comentario.escondida_em = None
        comentario.save(update_fields=['escondida_em'])
    return httprr(f'{comentario.chamado.get_absolute_url()}?tab=linha_tempo', 'Comentário desarquivado com sucesso.')


@rtr()
@permission_required(['centralservicos.add_comment', 'centralservicos.change_chamado'])
def adicionar_comentario(request, chamado_id):
    return __adicionar_comentario_ou_nota_interna(request, Comunicacao.TIPO_COMENTARIO, chamado_id)


@rtr()
@permission_required('centralservicos.add_internal_note', 'centralservicos.change_chamado')
def adicionar_nota_interna(request, chamado_id):
    return __adicionar_comentario_ou_nota_interna(request, Comunicacao.TIPO_NOTA_INTERNA, chamado_id)


@rtr('centralservicos/templates/form_resolver_chamado.html')
@permission_required('centralservicos.solve_chamado')
def resolver_chamado(request, chamado_id):
    chamado = get_object_or_404(Chamado, pk=chamado_id)
    if not chamado.pode_resolver_info(request.user)['pode_resolver']:
        raise PermissionDenied('Você não tem permissão para resolver este chamado.')
    title = 'Alterar para Resolvido'
    ResolverChamadoFormClass = ResolverChamadoFormFactory(request, chamado)
    form = ResolverChamadoFormClass(request.POST or None)
    if form.is_valid():
        try:
            chamados_ids = form.resolver_chamado()
            return httprr(
                chamado.get_absolute_url(),
                f'Alteração de situação realizada com sucesso. Os seguintes chamados foram resolvidos: {", ".join(chamados_ids)}.',
            )
        except TransitionNotAllowed:
            raise PermissionDenied('Você não tem permissão para alterar a situação deste chamado.')
    return locals()


@rtr('centralservicos/templates/form_fechar_chamado.html')
@permission_required(['centralservicos.close_chamado'])
def fechar_chamado(request, chamado_id):
    chamado = get_object_or_404(Chamado, pk=chamado_id)
    if chamado.pode_fechar(request.user):
        if chamado.interessado == request.user:
            title = 'Fechar Chamado'
            if request.method == 'POST':
                try:
                    chamado.fechar_chamado(
                        request.user, nota_avaliacao=request.POST.get('nota_avaliacao', None), comentario_avaliacao=request.POST.get('comentario', '')
                    )
                    return httprr(chamado.get_absolute_url(), 'Alteração de situação realizada com sucesso.')
                except TransitionNotAllowed:
                    raise PermissionDenied('Você não tem permissão para alterar a situação deste chamado.')
        elif request.method == 'POST':
            chamado.fechar_chamado(request.user)
            return httprr(chamado.get_absolute_url(), 'Chamado fechado com sucesso.')

    else:
        raise PermissionDenied('Você não tem permissão para fechar este chamado.')
    return locals()


@permission_required(['centralservicos.view_chamado', 'centralservicos.change_chamado'])
def colocar_em_atendimento(request, chamado_id):
    chamado = get_object_or_404(Chamado, pk=chamado_id)
    if not has_transition_perm(chamado.colocar_em_atendimento_transition, request.user):
        raise PermissionDenied('Você não tem permissão para alterar a situação deste chamado.')
    try:
        chamado.colocar_em_atendimento(request.user)
    except TransitionNotAllowed:
        raise PermissionDenied('Você não tem permissão para alterar a situação deste chamado.')

    return httprr(chamado.get_absolute_url(), 'Alteração de situação realizada com sucesso.')


@rtr()
@permission_required(['centralservicos.reopen_chamado'])
def reabrir_chamado(request, chamado_id):
    title = 'Alterar Situação para Reaberto'
    chamado = get_object_or_404(Chamado, pk=chamado_id)
    if chamado.pode_reabrir(request.user):
        atendimento_atribuicao = chamado.get_atendimento_atribuicao_atual()
        FormClass = AlterarStatusChamadoFormFactory(request, servico=chamado.servico, grupo_atendimento=None)
        form = FormClass(request.POST or None, instance=chamado)
        if form.is_valid():
            try:
                chamado.reabrir_chamado(request.user, observacao=form.cleaned_data.get('observacao'))
                chamado.atribuir_atendente(atendimento_atribuicao.grupo_atendimento, request.user, atendimento_atribuicao.atribuido_para)
                return httprr(chamado.get_absolute_url(), 'Situação alterada com sucesso.')
            except TransitionNotAllowed:
                return httprr(chamado.get_absolute_url(), 'Você não tem permissão para alterar esta situação.', tag='error')
    else:
        raise PermissionDenied('Você não tem permissão para alterar esta situação.')
    return locals()


@rtr()
@permission_required(['centralservicos.suspend_chamado'])
def suspender_chamado(request, chamado_id):
    title = 'Alterar Situação para Suspenso'
    chamado = get_object_or_404(Chamado, pk=chamado_id)
    if chamado.pode_suspender(request.user):
        atendimento_atribuicao = chamado.get_atendimento_atribuicao_atual()
        FormClass = AlterarStatusChamadoFormFactory(request, servico=chamado.servico, grupo_atendimento=None)
        form = FormClass(request.POST or None, instance=chamado)
        if form.is_valid():
            try:
                chamado.suspender_chamado(request.user, observacao=form.cleaned_data.get('observacao'))
                return httprr(chamado.get_absolute_url(), 'Situação alterada com sucesso.')
            except TransitionNotAllowed:
                return httprr(chamado.get_absolute_url(), 'Você não tem permissão para alterar esta situação.', tag='error')
    else:
        raise PermissionDenied('Você não tem permissão para alterar esta situação.')
    return locals()


@rtr('centralservicos/templates/cancelar_chamado.html')
@permission_required(['centralservicos.cancel_chamado'])
def cancelar_chamado(request, chamado_id):
    chamado = get_object_or_404(Chamado, pk=chamado_id)
    title = f'Cancelar {chamado}'
    if chamado.pode_cancelar(request.user):
        FormClass = AlterarStatusChamadoFormFactory(request, servico=chamado.servico, grupo_atendimento=None)
        form = FormClass(request.POST or None, instance=chamado)
        if form.is_valid():
            try:
                chamado.cancelar_chamado(request.user, observacao=form.cleaned_data.get('observacao'))
                return httprr(chamado.get_absolute_url(), 'Situação alterada com sucesso.')
            except TransitionNotAllowed:
                return httprr(chamado.get_absolute_url(), 'Este atendimento não pode ser fechado.', tag='error')
    else:
        raise PermissionDenied('Você não tem permissão para alterar esta situação.')
    return locals()


@rtr('centralservicos/templates/meus_chamados.html')
@permission_required(['centralservicos.view_chamado', 'centralservicos.change_chamado'])
def meus_chamados(request):
    title = 'Meus chamados'
    FormClass = BuscarChamadoUsuarioFormFactory(request)
    form = FormClass(request.GET or {})
    if form.is_valid():
        chamados_select_related = ('servico__area', 'interessado')
        chamados_prefetch_related = (
            'historicostatus_set',
            'atendimentoatribuicao_set__atribuido_para',
            'atendimentoatribuicao_set__grupo_atendimento',
        )
        todos_chamados = (
            Chamado.get_chamados_do_usuario(
                request.user,
                chamado_id=form.cleaned_data.get('chamado_id'),
                area=form.cleaned_data.get('area'),
                data_inicial=form.cleaned_data.get('data_inicial'),
                data_final=form.cleaned_data.get('data_final'),
                tipo_usuario=form.cleaned_data.get('tipo_usuario'),
            )
            .select_related(*chamados_select_related)
            .prefetch_related(*chamados_prefetch_related)
        )
        # single aggregate to compute all counters in one query
        status_aberto = StatusChamado.get_status_aberto()
        status_em_atendimento = StatusChamado.get_status_em_atendimento()
        status_reaberto = StatusChamado.get_status_reaberto()
        status_suspenso = StatusChamado.get_status_suspenso()
        status_resolvido = StatusChamado.get_status_resolvido()
        status_fechado = StatusChamado.get_status_fechado()
        status_cancelado = StatusChamado.get_status_cancelado()
        counts = todos_chamados.aggregate(
            total=Count('pk'),
            ativos=Count('pk', filter=~Q(status__in=(status_fechado, status_resolvido, status_cancelado))),
            abertos=Count('pk', filter=Q(status=status_aberto)),
            em_atendimento=Count('pk', filter=Q(status=status_em_atendimento)),
            reabertos=Count('pk', filter=Q(status=status_reaberto)),
            suspensos=Count('pk', filter=Q(status=status_suspenso)),
            resolvidos=Count('pk', filter=Q(status=status_resolvido)),
            fechados=Count('pk', filter=Q(status=status_fechado)),
            cancelados=Count('pk', filter=Q(status=status_cancelado)),
        )

        todos_chamados_contador = counts.get('total') or 0
        chamados_ativos_contador = counts.get('ativos') or 0
        chamados_abertos_contador = counts.get('abertos') or 0
        chamados_em_atendimento_contador = counts.get('em_atendimento') or 0
        chamados_reabertos_contador = counts.get('reabertos') or 0
        chamados_suspensos_contador = counts.get('suspensos') or 0
        chamados_resolvidos_contador = counts.get('resolvidos') or 0
        chamados_fechados_contador = counts.get('fechados') or 0
        chamados_cancelados_contador = counts.get('cancelados') or 0

        # keep full queryset objects but avoid extra .count() calls above
        chamados_ativos = todos_chamados.exclude(status__in=(status_fechado, status_resolvido, status_cancelado))
        chamados_abertos = todos_chamados.filter(status=status_aberto)
        chamados_em_atendimento = todos_chamados.filter(status=status_em_atendimento)
        chamados_reabertos = todos_chamados.filter(status=status_reaberto)
        chamados_suspensos = todos_chamados.filter(status=status_suspenso)
        chamados_resolvidos = todos_chamados.filter(status=status_resolvido)
        chamados_fechados = todos_chamados.filter(status=status_fechado)
        chamados_cancelados = todos_chamados.filter(status=status_cancelado)

        # Chamados a fechar é outra regra; ainda precisa de sua própria query.
        chamados_a_fechar = Chamado.chamados_a_fechar(usuario=request.user, como_requisitante=True)
        chamados_a_fechar_contador = chamados_a_fechar.count()

    return locals()


@rtr('centralservicos/templates/listar_chamados_suporte.html')
@permission_required('centralservicos.list_chamados_suporte')
def listar_chamados_suporte(request):
    title = 'Chamados'

    # Os atores de um chamado são instâncias de User. Mas os choices fields correspondentes, no
    # formulário a seguir, trabalham com instâncias de Vinculo. Então os consumidores dessa view
    # devem parametrizar, se for o caso, os fields dos atores com IDs de Vinculo.

    FormClass = BuscarChamadoSuporteFormFactory(request, request.GET.get('area', None) and request.GET.getlist('area', []) or [])
    form = FormClass(request.GET or {})

    if form.is_valid():
        lista_chamados = Chamado.get_chamados_do_suporte(
            request.user,
            chamado_id=form.cleaned_data.get('chamado_id'),
            status=form.cleaned_data.get('status'),
            todos_status=form.cleaned_data.get('todos_status'),
            tipo=form.cleaned_data.get('tipo'),
            servico=form.cleaned_data.get('servico'),
            grupo_servico=form.cleaned_data.get('grupo_servico'),
            data_inicial=form.cleaned_data.get('data_inicial'),
            data_final=form.cleaned_data.get('data_final'),
            aberto_por=form.aberto_por_as_user(),
            interessado=form.interessado_as_user(),
            texto_livre=form.cleaned_data.get('texto'),
            nota_avaliacao=form.cleaned_data.get('nota_avaliacao'),
            tags=form.cleaned_data.get('tags'),
            sla_estourado=form.cleaned_data.get('sla_estourado'),
            grupo_atendimento=form.cleaned_data.get('grupo_atendimento'),
            area=form.cleaned_data.get('area'),
            considerar_escalados=form.cleaned_data.get('considerar_escalados'),
            uo=form.cleaned_data.get('uo'),
            atribuicoes=form.cleaned_data.get('atribuicoes'),
            atendente=form.atendente_as_user(),
            ordenar_por=form.cleaned_data.get('ordenar_por'),
            tipo_ordenacao=form.cleaned_data.get('tipo_ordenacao'),
            numero_patrimonio=form.cleaned_data.get('numero_patrimonio'),
        )
    else:
        lista_chamados = Chamado.get_chamados_do_suporte(request.user)

    return locals()


@rtr('centralservicos/templates/listar_chamados_a_fechar.html')
@permission_required('centralservicos.view_chamado')
def listar_chamados_a_fechar(request):
    """
    Página exclusiva para mostrar TODOS os chamados que podem ser fechados
    pelo usuário logado.

    Para efeitos de notificação, o usuário pode fechar os chamados como requisitante.
    Mas, conforme o método 'Chamado.pode_fechar', um usuário poderá fechar chamados
    como requisitante, interessado ou atendente atual. Se o usuário for um superuser,
    então pdoerá fechar qualquer chamado. Logo, isso justifica a existência desta view.
    """
    title = 'Todos os Chamados que podem ser fechados por você'

    user = request.user
    restringe_superuser = request.GET.get('restringe_superuser') != '0'
    chamados_a_fechar = Chamado.chamados_a_fechar(
        usuario=user, como_requisitante=True, como_interessado=True, como_responsavel_atendimento_atual=True, restringe_superuser=restringe_superuser
    )
    user_is_superuser = user.is_superuser

    return locals()


@rtr('centralservicos/templates/dashboard.html')
@permission_required('centralservicos.change_chamado')
def dashboard(request):
    title = 'Dashboard'
    """
        Chamados que estejam nos grupos de atendimento do usuário,
        que não estejam com o status igual a fechado ou resolvido
        e agrupado por incidente ou requisição
        #DashBoard se refere aos chamados que o Atendente possui permissão
    """

    area = None
    areas = GrupoAtendimento.areas_vinculadas_ao_meu_centro_atendimento(request.user)
    filtro_area = ''.join([f'&area={id_area}' for id_area in areas.values_list('id', flat=True)])
    filtros_qs_chamados = {}
    if request.GET.get('area'):
        area = get_object_or_404(AreaAtuacao, pk=request.GET.get('area'))
        filtro_area = f'&area={area.id}'
        title = f'Dashboard - {area.nome}'
        filtros_qs_chamados['area'] = area

    """ grupos_atendimento = Variavel utilizada no template para listar todos os grupos do usuário """
    grupos_atendimento = GrupoAtendimento.meus_grupos_com_servicos_ou_chamados_ativos(request.user, area)
    filtro_grupo_atendimento = ''.join(
        [f'&grupo_atendimento={grupo_atendimento_uo_id}' for grupo_atendimento_uo_id in grupos_atendimento.values_list('id', flat=True)]
    )
    uos = UnidadeOrganizacional.objects.suap().filter(pk__in=grupos_atendimento.values_list('campus', flat=True))
    filtro_uo = ''.join([f'&uo={id_uo}' for id_uo in uos.values_list('id', flat=True)])

    """ filtra_por_grupo = filtro com base no parametro informado na URL ou nos grupos do usuario """
    filtra_por_grupo = grupos_atendimento
    if request.GET.get('grupo_atendimento'):
        grupo_atendimento = get_object_or_404(GrupoAtendimento, pk=request.GET.get('grupo_atendimento'))
        filtro_grupo_atendimento = f'&grupo_atendimento={grupo_atendimento.id}'
        filtra_por_grupo = [grupo_atendimento.id]
        filtros_qs_chamados['grupo_atendimento'] = grupo_atendimento

    if request.GET.get('uo'):
        uo = get_object_or_404(UnidadeOrganizacional, pk=request.GET.get('uo'))
        filtro_uo = f'&uo={uo.id}'
        atendimentos = AtendimentoAtribuicao.objects.filter(
            grupo_atendimento__campus_id=uo.id, grupo_atendimento__in=filtra_por_grupo, cancelado_em__isnull=True
        )
        filtros_qs_chamados['uo'] = uo
    else:
        atendimentos = AtendimentoAtribuicao.objects.filter(grupo_atendimento__in=filtra_por_grupo, cancelado_em__isnull=True)

    qs_atribuidos_a_mim = Chamado.get_chamados_do_suporte(request.user, atribuicoes=Chamado.ATRIBUIDOS_A_MIM, **filtros_qs_chamados)
    qs = Chamado.objects.filter(pk__in=atendimentos.values('chamado')).exclude(
        status__in=(StatusChamado.get_status_fechado(), StatusChamado.get_status_resolvido(), StatusChamado.get_status_cancelado())
    )

    # qs_atribuidos_a_mim = Chamado.objects.filter(pk__in=atendimentos.filter(atribuido_para=request.user).values('chamado')).exclude(
    #     status__in=(StatusChamado.get_status_fechado(), StatusChamado.get_status_resolvido(), StatusChamado.get_status_cancelado())
    # )
    qs_atribuidos_a_outros = Chamado.objects.filter(
        pk__in=atendimentos.filter(atribuido_para__isnull=False).exclude(atribuido_para=request.user).values('chamado')
    ).exclude(status__in=(StatusChamado.get_status_fechado(), StatusChamado.get_status_resolvido(), StatusChamado.get_status_cancelado()))
    qs_nao_atribuidos = Chamado.objects.filter(pk__in=atendimentos.filter(atribuido_para__isnull=True).values('chamado')).exclude(
        status__in=(StatusChamado.get_status_fechado(), StatusChamado.get_status_resolvido(), StatusChamado.get_status_cancelado())
    )

    qtd_incidentes_atribuidos_a_mim = qs_atribuidos_a_mim.filter(servico__tipo=Servico.TIPO_INCIDENTE).count()
    qtd_incidentes_atribuidos_a_outros = qs_atribuidos_a_outros.filter(servico__tipo=Servico.TIPO_INCIDENTE).count()
    qtd_incidentes_nao_atribuidos = qs_nao_atribuidos.filter(servico__tipo=Servico.TIPO_INCIDENTE).count()

    qtd_requisicoes_atribuidas_a_mim = qs_atribuidos_a_mim.filter(servico__tipo=Servico.TIPO_REQUISICAO).count()
    qtd_requisicoes_atribuidas_a_outros = qs_atribuidos_a_outros.filter(servico__tipo=Servico.TIPO_REQUISICAO).count()
    qtd_requisicoes_nao_atribuidas = qs_nao_atribuidos.filter(servico__tipo=Servico.TIPO_REQUISICAO).count()

    qtd_favicon = qtd_incidentes_nao_atribuidos + qtd_requisicoes_nao_atribuidas

    grafico_categorias = []
    [
        grafico_categorias.append([categoria.nome, categoria.qtd_chamados])
        for categoria in CategoriaServico.objects.filter(gruposervico__servico__chamado__in=qs)
        .annotate(qtd_chamados=Count('gruposervico__servico__chamado'))
        .filter(qtd_chamados__gt=0)
        .only('nome')
    ]

    dados_grafico = PieChart(
        'div_grafico', title='Chamados por Categoria', subtitle='Nos seus Grupos de Atendimento', minPointLength=0, data=grafico_categorias
    )
    return locals()


def _motivo_para_nao_assumir(chamado: Chamado, user: User) -> str:
    """Explica por que ``Chamado.pode_assumir`` recusou o usuário."""
    if not chamado.pode_atribuir():
        return f'Este chamado não pode ser assumido, pois sua situação atual é {chamado.get_status_display()}.'
    atendimento_atribuicao = chamado.get_atendimento_atribuicao_atual()
    if atendimento_atribuicao and atendimento_atribuicao.atribuido_para == user:
        return 'Este chamado já está atribuído a você.'
    return 'Você não pode assumir este chamado, pois não faz parte do grupo de atendimento ao qual ele está atribuído.'


@permission_required('centralservicos.add_auto_atribuicao')
def auto_atribuir_chamado(request: HttpRequest, chamado_id: int) -> HttpResponse:
    chamado = get_object_or_404(Chamado, pk=chamado_id)
    url = request.META.get('HTTP_REFERER', chamado.get_absolute_url())

    # Mesma regra do botão "Assumir": a permissão da URL vem do grupo "Atendente da Central de
    # Serviços", que o atendente de qualquer grupo de atendimento tem.
    if not chamado.pode_assumir(request.user):
        return httprr(url, _motivo_para_nao_assumir(chamado, request.user), tag='error')

    atendimento_atribuicao = chamado.get_atendimento_atribuicao_atual()

    try:
        chamado.atribuir_atendente(atendimento_atribuicao.grupo_atendimento, request.user, request.user)
        return httprr(chamado.get_absolute_url(), 'Atribuição realizada com sucesso.')
    except TransitionNotAllowed:
        return httprr(url, f'Este atendimento não pode ser atribuído a {request.user}.', tag='error')


def __escalar_ou_retornar_atendimento_chamado(request, operacao, chamado_id):
    if request.user.has_perm('centralservicos.change_chamado'):
        chamado = get_object_or_404(Chamado, pk=chamado_id)

        title = f'{operacao.capitalize()} Atendimento'
        if operacao == 'escalar':
            if not chamado.pode_escalar():
                return httprr(
                    '..',
                    'Este atendimento não pode ser escalado. Verifique se existe grupo de atendimento superior ou se o chamado não está resolvido/fechado.',
                    tag='error',
                )
        else:
            if not chamado.pode_retornar():
                return httprr(
                    '..',
                    'Este atendimento não pode ser retornado. Verifique se existe grupo de atendimento inferior ou se o chamado não está resolvido/fechado.',
                    tag='error',
                )

        FormClass = ComunicacaoFormFactory(request, chamado, operacao)
        form = FormClass(request.POST or None)
        form.fields['texto'].help_text = f'Para {operacao} o atendimento, adicione um texto que será exibido como Nota Interna.'
        form.instance.chamado = chamado
        form.instance.remetente = request.user
        form.instance.tipo = Comunicacao.TIPO_NOTA_INTERNA
        if form.is_valid():
            atribuido_para = form.cleaned_data.get('atribuido_para', None)
            chamado.escalar_ou_retornar_atendimento(operacao, request.user, atribuido_para)

            # if atribuido_para:
            #     chamado.atribuir_atendente(grupo, request.user, atribuido_para)
            form.save()
            """
                Quando o atendente escala/retorna um chamado, normalmente ele nao possui acesso ao chamado.
                Por isso, por padrão redireciona para o dashboard.
            """
            if chamado.pode_visualizar(request.user):
                return httprr(chamado.get_absolute_url(), 'Operação realizada com sucesso.')
            else:
                return httprr('/centralservicos/dashboard/')

    else:
        raise PermissionDenied('Você não tem permissão para realizar esta operação.')

    return locals()


@rtr()
@permission_required('centralservicos.change_atendimentoatribuicao')
def escalar_atendimento_chamado(request, chamado_id):
    return __escalar_ou_retornar_atendimento_chamado(request, 'escalar', chamado_id)


@rtr()
@permission_required('centralservicos.change_atendimentoatribuicao')
def retornar_atendimento_chamado(request, chamado_id):
    return __escalar_ou_retornar_atendimento_chamado(request, 'retornar', chamado_id)


@rtr('centralservicos/templates/form_atribuir_chamado.html')
@permission_required('centralservicos.change_chamado')
def atribuir_chamado(request, chamado_id):
    title = 'Atribuição de Chamado'
    chamado = get_object_or_404(Chamado, pk=chamado_id)
    grupo = chamado.get_atendimento_atribuicao_atual().grupo_atendimento
    if not chamado.estah_fechado() and not chamado.estah_resolvido():
        if request.user.is_superuser or chamado.get_responsaveis_equipe_atendimento().filter(pk=request.user.pk).exists():
            FormClass = AtendimentoAtribuicaoFormFactory(request, grupo)
            form = FormClass(request.POST or None)
            if form.is_valid():
                try:
                    atribuido_para = form.cleaned_data.get('atribuido_para', None)
                    chamado.atribuir_atendente(grupo, request.user, atribuido_para)
                    return httprr('..', f'Atribuição realizada com sucesso para {atribuido_para}.')
                except TransitionNotAllowed:
                    return httprr(chamado.get_absolute_url(), 'Chamados com Situação Resolvido ou Fechado não podem ser atribuídos.', tag='error')
        else:
            raise PermissionDenied('..', 'Você não tem permissão para atribuir um chamado.')
    else:
        raise PermissionDenied('..', 'Chamados com Situação Resolvido ou Fechado não podem ser atribuídos.')

    return locals()


"""
Método responsavel por retornar uma lista de centros de atendimento, em formato json, com base no serviço e campus informado
Centros de atendimento do com eh_local = False, retornarão todos da área do serviço.
"""


@csrf_exempt
@login_required()
def get_centros_atendimento_por_servico_e_campus(request, servico_id, campus_id):
    servico = get_object_or_404(Servico, pk=servico_id)
    choice = []
    for centro in servico.get_centros_atendimento(campus_id):
        choice.append([centro.id, centro.nome, centro.eh_local])
    return JsonResponse({'centros': choice})


@csrf_exempt
@login_required()
def get_centros_atendimento_por_area(request, area_id):
    area = get_object_or_404(AreaAtuacao, pk=area_id)
    choice = []
    for centro in CentroAtendimento.objects.filter(area=area):
        choice.append([centro.id, centro.nome, centro.eh_local])
    return JsonResponse({'centros': choice})


"""
Método responsavel por retornar uma lista de campus, em formato json, com base no serviço informado
"""


@csrf_exempt
@login_required()
def get_campus_com_centros_atendimento(request: HttpRequest, servico_id: int, chamado_id: int) -> JsonResponse:
    """Campus com centros de atendimento do serviço.

    ``chamado_id`` é sempre informado pela única URL da rota; o JS manda ``0`` quando não há
    chamado (`static/centralservicos/js/get_centros_atendimento_por_campus.js:34-37`), e é o
    ``DoesNotExist`` do ``get`` que cai no campus padrão do usuário.
    """
    try:
        campus_default = Chamado.objects.get(pk=chamado_id).campus
    except Chamado.DoesNotExist:
        campus_default = get_uo(request.user)
    servico = get_object_or_404(Servico, pk=servico_id)
    choice = []
    if campus_default:
        for campus in servico.get_campus_disponiveis_para_atendimento():
            selected = campus.id == campus_default.id
            choice.append([campus.id, campus.sigla, selected])
    return JsonResponse({'campus': choice})


@rtr()
@csrf_exempt
@permission_required('centralservicos.reclassify_chamado')
def reclassificar_chamado(request, chamado_id):
    chamado = get_object_or_404(Chamado, pk=chamado_id)

    interno = ' Interno' if chamado.servico.interno else ''
    title = f'Reclassificar Chamado{interno}: {chamado_id} - {chamado.servico.nome}'
    usuario = request.user
    if usuario.is_superuser or chamado.get_responsaveis_equipe_atendimento().filter(pk=usuario.pk).exists() or chamado.eh_atendente(usuario):
        troca_area = False
        if usuario.is_superuser or chamado.get_responsaveis_equipe_atendimento().filter(pk=usuario.pk).exists():
            troca_area = True
        if 'centro_atendimento' in request.POST and 'servico' in request.POST and request.POST.get('servico'):
            servico = Servico.objects.get(pk=request.POST.get('servico'))
            centros_validos = servico.centros_atendimento.filter(ativo=True)
        else:
            centros_validos = chamado.servico.centros_atendimento.filter(ativo=True)

        FormClass = ReclassificarChamadoFormFactory(request, chamado, troca_area, centros_validos)
        form = FormClass(request.POST or None)
        if request.POST and form.is_valid():
            try:
                centro_atendimento_novo = form.cleaned_data.get('centro_atendimento')
                campus = UnidadeOrganizacional.objects.suap().get(pk=form.cleaned_data.get('uo'))
                servico_novo = form.cleaned_data.get('servico')
                chamado.reclassificar(servico_novo, campus, centro_atendimento_novo, form.cleaned_data.get('justificativa'), request.user)
                if chamado.pode_visualizar(usuario):
                    return httprr(chamado.get_absolute_url(), 'Reclassificação de chamado realizada com sucesso.')
                else:
                    return httprr('/centralservicos/dashboard/', 'Reclassificação de chamado realizada com sucesso.')
            except ValidationError as e:
                messages.error(request, ''.join(e.messages))
    else:
        raise PermissionDenied('Você não tem permissão para reclassificar um chamado.')

    return locals()


@rtr()
@permission_required('centralservicos.pode_ver_indicadores')
def indicadores(request):
    def obtem_media_tempo_chamados_agrupado_por_ano(campo, tipo_tempo, inicio, termino, area=None, tipo_retorno='list'):
        """
        :param campo: String: campo utilizado no group by. Exemplo: 'tipo' ou 'o_interessado_id'
        :param tipo_tempo: Strings: 'tempo_atendimento', 'tempo_resposta' ou 'tempo_suspensao
        :param ano: inteiro: Ano. Ex: 2015
        :param area: objeto tipo AreaAtuacao:
        :return: Lista
        """
        area_id = area.id if area else -1

        sql = f"""
                select {campo}, round(  CAST(float8 (avg(tempo) / 3600) as numeric), 0) as total, CAST(ano as integer) as ano from (
                select chamado_id, {campo}, to_char(data_hora, 'YYYY') as ano, sum({tipo_tempo}) as tempo
                from centralservicos_historicostatus hs
                inner join centralservicos_chamado c on c.id = hs.chamado_id
                inner join centralservicos_servico s on s.id = c.servico_id
                where {tipo_tempo} is not null
                and to_char(data_hora, 'YYYY-MM-DD') >= '{inicio}' and to_char(data_hora, 'YYYY-MM-DD') <= '{termino}'
                and exists (select gs.id from centralservicos_gruposervico gs
                    inner join centralservicos_gruposervico_categorias gsc ON gs.id = gsc.gruposervico_id
                    inner join centralservicos_categoriaservico cs ON gsc.categoriaservico_id = cs.id
                    where s.grupo_servico_id = gs.id
                    and (cs.area_id = {area_id} or {area_id} = '-1')
                )
                group by chamado_id, {campo}, to_char(data_hora, 'YYYY')
                ) as tab
                group by {campo}, ano
                order by ano, {campo} asc
                """

        if tipo_retorno == 'list':
            return db.get_list(sql)

        return db.get_dict(sql)

    def obtem_media_tempo_chamados_agrupado_por_mes(campo, tipo_tempo, inicio, termino, uo=None, area=None, tipo_retorno='list'):
        """
        :param campo: String: campo utilizado no group by. Exemplo: 'tipo' ou 'o_interessado_id'
        :param tipo_tempo: String: 'tempo_atendimento', 'tempo_resposta' ou 'tempo_suspensao
        :param ano: inteiro: Ano. Ex: 2015
        :param uo_id: inteiro. id da UO
        :param area: objeto tipo AreaAtuacao:
        :param tipo_retorno: String: 'list' ou 'dict'
        :return: Lista
        """
        uo_id = uo.id if uo else -1
        area_id = area.id if area else -1

        sql = f"""
                select {campo}, round(  CAST(float8 (avg(tempo) / 3600) as numeric), 0) as total, CAST(mes as integer) as mes from (
                select chamado_id, {campo}, to_char(data_hora, 'MM') as mes, sum({tipo_tempo}) as tempo
                from centralservicos_historicostatus hs
                inner join centralservicos_chamado c on c.id = hs.chamado_id
                inner join centralservicos_servico s on s.id = c.servico_id
                where {tipo_tempo} is not null
                and (c.campus_id = {uo_id} or {uo_id} = '-1')
                and to_char(data_hora, 'YYYY-MM-DD') >= '{inicio}' and to_char(data_hora, 'YYYY-MM-DD') <= '{termino}'
                and exists (select gs.id from centralservicos_gruposervico gs
                    inner join centralservicos_gruposervico_categorias gsc ON gs.id = gsc.gruposervico_id
                    inner join centralservicos_categoriaservico cs ON gsc.categoriaservico_id = cs.id
                    where s.grupo_servico_id = gs.id
                    and (cs.area_id = {area_id} or {area_id} = '-1')
                )
                group by chamado_id, {campo}, to_char(data_hora, 'MM')
                ) as tab
                group by {campo}, mes
                order by mes, {campo} asc
                """
        if tipo_retorno == 'list':
            return db.get_list(sql)

        return db.get_dict(sql)

    def dados_grafico_tempo(lista, verifica_tipo):
        series = []
        mes_corrente = 0
        if lista:
            inc = 0
            rec = 0
            for tipo, total, mes in lista:
                if mes_corrente != 0 and mes_corrente != mes:
                    series.append([Meses.get_mes(mes_corrente), float(inc), float(rec)])
                    inc = 0
                    rec = 0
                mes_corrente = mes
                if tipo == verifica_tipo[0]:
                    inc = total
                elif tipo == verifica_tipo[1]:
                    rec = total
            series.append([Meses.get_mes(mes_corrente), float(inc), float(rec)])
        return series

    def dados_grafico_nota_avaliacao(queryset):
        def percentual(nota, total):
            percent = float(nota) * 100 / float(total)
            return {'y': float(f'{percent:.2f}'), 'total': nota}

        series = []
        mes_corrente = 0
        if queryset.exists():
            nota_1, nota_2, nota_3, nota_4, nota_5 = 0, 0, 0, 0, 0
            for nota, total, mes in queryset:
                if mes_corrente != 0 and mes_corrente != mes.month:
                    total_geral = nota_1 + nota_2 + nota_3 + nota_4 + nota_5
                    series.append(
                        [
                            Meses.get_mes(mes_corrente),
                            percentual(nota_1, total_geral),
                            percentual(nota_2, total_geral),
                            percentual(nota_3, total_geral),
                            percentual(nota_4, total_geral),
                            percentual(nota_5, total_geral),
                        ]
                    )
                    nota_1, nota_2, nota_3, nota_4, nota_5 = 0, 0, 0, 0, 0
                mes_corrente = mes.month
                if nota == 1:
                    nota_1 = total
                elif nota == 2:
                    nota_2 = total
                elif nota == 3:
                    nota_3 = total
                elif nota == 4:
                    nota_4 = total
                elif nota == 5:
                    nota_5 = total
            total_geral = nota_1 + nota_2 + nota_3 + nota_4 + nota_5
            series.append(
                [
                    Meses.get_mes(mes_corrente),
                    percentual(nota_1, total_geral),
                    percentual(nota_2, total_geral),
                    percentual(nota_3, total_geral),
                    percentual(nota_4, total_geral),
                    percentual(nota_5, total_geral),
                ]
            )
        return series

    # Tem que fazer isso, porque o retorno da consulta é datetime.datetime
    def configura_mes(data):
        for i in data:
            i[0] = Meses.get_mes(i[0].month)

    title = 'Indicadores'
    dic = Chamado.objects.all().aggregate(Max('aberto_em'), Min('aberto_em'))
    eh_administrador = request.user.has_perm('centralservicos Administrador')
    data_inicio = date(date.today().year, 1, 1)
    data_termino = date(date.today().year, 12, 31)

    FormClass = GraficosFormFactory(request, data_inicio, data_termino)
    form = FormClass(request.GET or None)
    if form.is_valid():
        inicio = form.cleaned_data.get('inicio')
        termino = form.cleaned_data.get('termino') + relativedelta(hours=23, minutes=59)
        uo = form.cleaned_data.get('uo')
        grupo_atendimento = form.cleaned_data.get('grupo_atendimento')
        area = form.cleaned_data.get('area')

        chamados_abertos = Chamado.objects.annotate(mes=TruncMonth('aberto_em')).filter(aberto_em__gte=inicio, aberto_em__lte=termino)
        historico_status = HistoricoStatus.objects.annotate(mes=TruncMonth('data_hora')).filter(data_hora__gte=inicio, data_hora__lte=termino)
        atendimento_atribuicao = AtendimentoAtribuicao.objects.annotate(mes=TruncMonth('cancelado_em')).filter(
            cancelado_em__gte=inicio, cancelado_em__lte=termino
        )
        comunicacao = Comunicacao.objects.annotate(mes=TruncMonth('data_hora')).filter(data_hora__gte=inicio, data_hora__lte=termino)

        if uo:
            chamados_abertos = chamados_abertos.filter(campus=uo)
            historico_status = historico_status.filter(chamado__campus=uo)
            atendimento_atribuicao = atendimento_atribuicao.filter(chamado__campus=uo)
            comunicacao = comunicacao.filter(chamado__campus=uo)

        if area:
            chamados_abertos = chamados_abertos.filter(servico__grupo_servico__categorias__area=area)
            historico_status = historico_status.filter(chamado__servico__grupo_servico__categorias__area=area)
            atendimento_atribuicao = atendimento_atribuicao.filter(chamado__servico__grupo_servico__categorias__area=area)
            comunicacao = comunicacao.filter(chamado__servico__grupo_servico__categorias__area=area)

        meus_grupos = GrupoAtendimento.meus_grupos(request.user)
        if grupo_atendimento:
            atendimentos = AtendimentoAtribuicao.objects.filter(grupo_atendimento=grupo_atendimento, cancelado_em__isnull=True)
        else:
            atendimentos = AtendimentoAtribuicao.objects.filter(grupo_atendimento__in=meus_grupos, cancelado_em__isnull=True)

        chamados_abertos = chamados_abertos.filter(pk__in=atendimentos.values('chamado'))
        historico_status = historico_status.filter(chamado__in=atendimentos.values('chamado'))
        atendimento_atribuicao = atendimento_atribuicao.filter(chamado__in=atendimentos.values('chamado'))
        comunicacao = comunicacao.filter(chamado__in=atendimentos.values('chamado'))

        chamados_abertos_por_tipo = chamados_abertos.values_list('mes', 'servico__tipo').annotate(total=Count('servico__tipo')).order_by('mes')

        chamados_fechados_por_tipo = (
            historico_status.filter(status=StatusChamado.get_status_fechado())
            .values('mes', 'chamado__servico__tipo')
            .annotate(total=Count('chamado__servico__tipo'))
            .order_by('mes')
        )

        chamados_reabertos_por_tipo = (
            historico_status.filter(status=StatusChamado.get_status_reaberto())
            .values('mes', 'chamado__servico__tipo')
            .annotate(total=Count('chamado__servico__tipo'))
            .order_by('mes')
        )
        chamados_nota_avaliacao = (
            historico_status.filter(status=StatusChamado.get_status_fechado(), chamado__nota_avaliacao__gte=0)
            .values('mes', 'chamado__nota_avaliacao')
            .annotate(total=Count('chamado__nota_avaliacao'))
            .order_by('mes', 'chamado__nota_avaliacao')
        )

        chamados_escalados_retornados = (
            atendimento_atribuicao.filter(
                tipo_justificativa__in=[AtendimentoAtribuicao.TIPO_CHAMADO_ESCALADO, AtendimentoAtribuicao.TIPO_CHAMADO_RETORNADO]
            )
            .values('mes', 'tipo_justificativa')
            .annotate(total=Count('tipo_justificativa'))
            .order_by('mes', 'tipo_justificativa')
        )
        chamados_reclassificados = (
            comunicacao.filter(chamado__reclassificado__gte=1)
            .values('mes', 'chamado__servico__tipo')
            .annotate(total=Count('chamado__id', distinct=True))
            .order_by('mes')
        )

        groups = []
        data1 = Relatorio.get_dados_em_coluna_linha(
            chamados_abertos_por_tipo.values('servico__tipo', 'total', 'mes'), groups, 'servico__tipo', 'mes', 'total', True
        )
        configura_mes(data1)
        grafico_chamados_abertos = LineChart(
            'grafico_chamados_abertos',
            title='Número de Chamados Abertos',
            data=data1,
            groups=groups,
            yAxis_title_text='Quantidade',
            plotOptions_line_dataLabels_enable=True,
            plotOptions_line_enableMouseTracking=True,
            yAxis_min=0,
        )

        groups = []
        data1 = Relatorio.get_dados_em_coluna_linha(
            chamados_fechados_por_tipo.values('chamado__servico__tipo', 'total', 'mes'), groups, 'chamado__servico__tipo', 'mes', 'total', True
        )
        configura_mes(data1)
        grafico_chamados_fechados = LineChart(
            'grafico_chamados_fechados',
            title='Número de Chamados Fechados',
            data=data1,
            groups=groups,
            yAxis_title_text='Quantidade',
            plotOptions_line_dataLabels_enable=True,
            plotOptions_line_enableMouseTracking=True,
            yAxis_min=0,
        )

        groups = []
        data1 = Relatorio.get_dados_em_coluna_linha(
            chamados_reabertos_por_tipo.values('chamado__servico__tipo', 'total', 'mes'), groups, 'chamado__servico__tipo', 'mes', 'total', True
        )
        configura_mes(data1)
        grafico_chamados_reabertos = LineChart(
            'grafico_chamados_reabertos',
            title='Número de Chamados Reabertos',
            data=data1,
            groups=groups,
            yAxis_title_text='Quantidade',
            plotOptions_line_dataLabels_enable=True,
            plotOptions_line_enableMouseTracking=True,
            yAxis_min=0,
        )

        groups = []
        data1 = Relatorio.get_dados_em_coluna_linha(
            chamados_escalados_retornados.values('tipo_justificativa', 'total', 'mes'), groups, 'tipo_justificativa', 'mes', 'total', True
        )
        configura_mes(data1)
        groups = [w.replace('CHAMADO_', '').capitalize() for w in groups]
        grafico_escalados_retornados = LineChart(
            'grafico_escalados_retornados',
            title='Número de Chamados Escalados/Retornados',
            data=data1,
            groups=groups,
            yAxis_title_text='Quantidade',
            plotOptions_line_dataLabels_enable=True,
            plotOptions_line_enableMouseTracking=True,
            yAxis_min=0,
        )

        groups = []
        data1 = Relatorio.get_dados_em_coluna_linha(
            chamados_reclassificados.values('chamado__servico__tipo', 'total', 'mes'), groups, 'chamado__servico__tipo', 'mes', 'total', True
        )
        configura_mes(data1)
        grafico_chamados_reclassificados = LineChart(
            'grafico_chamados_reclassificados',
            title='Número de Chamados Reclassificados',
            data=data1,
            groups=groups,
            yAxis_title_text='Quantidade',
            plotOptions_line_dataLabels_enable=True,
            plotOptions_line_enableMouseTracking=True,
            yAxis_min=0,
        )

        grafico_nota_avaliacao = LineChart(
            'grafico_nota_avaliacao',
            title='Avaliação dos Chamados Fechados',
            subtitle='Valores em percentuais',
            data=dados_grafico_nota_avaliacao(chamados_nota_avaliacao.values_list('chamado__nota_avaliacao', 'total', 'mes')),
            tooltip={'pointFormat': '<strong>{point.y}%</strong> ({point.total})'},
            groups=['Ruim', 'Regular', 'Bom', 'Ótimo', 'Excelente'],
            yAxis_title_text='Quantidade',
            plotOptions_line_dataLabels_enable=True,
            plotOptions_line_enableMouseTracking=True,
            yAxis_min=0,
        )

        grafico_chamados_tempo_atendimento = LineChart(
            'grafico_chamados_tempo_atendimento',
            title='Média do Tempo de Atendimento dos Chamados',
            subtitle='(em horas)',
            data=dados_grafico_tempo(
                obtem_media_tempo_chamados_agrupado_por_mes('tipo', 'tempo_atendimento', inicio, termino, uo, area), ['INC', 'REQ']
            ),
            tooltip={'pointFormat': '<strong>{point.y} horas</strong>'},
            groups=['REQ', 'INC'],
            yAxis_title_text='Média do Tempo',
            plotOptions_line_dataLabels_enable=True,
            plotOptions_line_enableMouseTracking=True,
            yAxis_min=0,
        )

        grafico_chamados_tempo_resposta = LineChart(
            'grafico_chamados_tempo_resposta',
            title='Média do Tempo de Resposta dos Chamados',
            subtitle='(em horas)',
            data=dados_grafico_tempo(
                obtem_media_tempo_chamados_agrupado_por_mes('tipo', 'tempo_resposta', inicio, termino, uo, area), ['INC', 'REQ']
            ),
            tooltip={'pointFormat': '<strong>{point.y} horas</strong>'},
            groups=['REQ', 'INC'],
            yAxis_title_text='Média do Tempo',
            plotOptions_line_dataLabels_enable=True,
            plotOptions_line_enableMouseTracking=True,
            yAxis_min=0,
        )

        top_10_atendentes = (
            historico_status.filter(status=StatusChamado.get_status_resolvido())
            .values('usuario')
            .annotate(total_chamados=Count('chamado', distinct=True))
            .order_by('-total_chamados')[:10]
        )
        top_10_demandantes = (
            chamados_abertos.values('aberto_por').annotate(total_chamados=Count('pk', distinct=True)).order_by('-total_chamados')[:10]
        )
        top_10_chamados_maior_tempo_atendimento = (
            historico_status.filter(tempo_atendimento__isnull=False)
            .values('chamado')
            .annotate(tempo=Sum('tempo_atendimento'))
            .order_by('-tempo')[:10]
        )

        lista_top_10_chamados_maior_tempo_atendimento = []
        for i in top_10_chamados_maior_tempo_atendimento:
            chamado = Chamado.objects.get(pk=i['chamado'])
            lista_top_10_chamados_maior_tempo_atendimento.append(chamado)

        top_10_chamados_maior_tempo_resposta = (
            historico_status.filter(tempo_resposta__isnull=False)
            .filter(chamado__status=StatusChamado.get_status_em_atendimento())
            .values('chamado')
            .annotate(tempo=Sum('tempo_resposta'))
            .order_by('-tempo')[:10]
        )

        lista_top_10_chamados_maior_tempo_resposta = []
        for i in top_10_chamados_maior_tempo_resposta:
            chamado = Chamado.objects.get(pk=i['chamado'])
            lista_top_10_chamados_maior_tempo_resposta.append(chamado)

        grafico_pizza = []
        for i in top_10_atendentes:
            i['usuario'] = User.objects.get(pk=i['usuario'])
            if not i['usuario'].get_profile():
                grafico_pizza.append([i['usuario'].username, i['total_chamados']])
            else:
                grafico_pizza.append([i['usuario'].get_profile().nome_usual, i['total_chamados']])

        grafico_atendentes = PieChart(
            'grafico_atendentes', title='Top 10 Atendentes', subtitle='que mais resolveram chamados', minPointLength=0, data=grafico_pizza
        )

        grafico_pizza = []
        for i in top_10_demandantes:
            i['aberto_por'] = User.objects.get(pk=i['aberto_por'])
            if not i['aberto_por'].get_profile():
                grafico_pizza.append([i['aberto_por'].username, i['total_chamados']])
            else:
                grafico_pizza.append([i['aberto_por'].get_profile().nome_usual, i['total_chamados']])

        grafico_demandantes = PieChart(
            'grafico_demandantes', title='Top 10 Demandantes', subtitle='que mais abriram chamados', minPointLength=0, data=grafico_pizza
        )

        # Gráfico: Top 10 Serviços mais demandados
        top_10_servicos = chamados_abertos.values('servico').annotate(total_chamados=Count('id')).order_by('-total_chamados')[:10]
        grafico_pizza_servicos = []
        for i in top_10_servicos:
            i['servico'] = Servico.objects.get(pk=i['servico'])
            grafico_pizza_servicos.append([i['servico'].nome, i['total_chamados']])

        grafico_servicos = PieChart(
            'grafico_servicos', title='Top 10 Serviços', subtitle='mais demandados', minPointLength=0, data=grafico_pizza_servicos
        )

        # Tabela com Serviços mais demandados
        servicos_mais_demandados = chamados_abertos.values('servico__nome').annotate(total_chamados=Count('id')).order_by('-total_chamados')

        # Gráfico: Grupos de Serviços mais demandados
        top_chamados_por_grupo_servicos = (
            chamados_abertos.values('servico__grupo_servico').annotate(total_chamados=Count('id')).order_by('-total_chamados')
        )
        grafico_chamados_por_grupo_servicos = []
        for i in top_chamados_por_grupo_servicos:
            i['servico__grupo_servico'] = GrupoServico.objects.get(pk=i['servico__grupo_servico'])
            grafico_chamados_por_grupo_servicos.append([i['servico__grupo_servico'].nome, i['total_chamados']])

        grafico_grupos_servicos = PieChart(
            'grafico_grupos_servicos',
            title='Grupos de Serviços',
            subtitle='mais demandados',
            minPointLength=0,
            data=grafico_chamados_por_grupo_servicos,
        )

        # Gráfico: Categorias de Serviços mais demandadas
        top_chamados_por_categoria_servicos = (
            chamados_abertos.values('servico__grupo_servico__categorias').annotate(total_chamados=Count('id')).order_by('-total_chamados')
        )
        grafico_chamados_por_categoria_servicos = []
        for i in top_chamados_por_categoria_servicos:
            i['servico__grupo_servico__categorias'] = CategoriaServico.objects.get(pk=i['servico__grupo_servico__categorias'])
            grafico_chamados_por_categoria_servicos.append([i['servico__grupo_servico__categorias'].nome, i['total_chamados']])

        grafico_categorias_servicos = PieChart(
            'grafico_categorias_servicos',
            title='Categorias de Serviços',
            subtitle='mais demandadas',
            minPointLength=0,
            data=grafico_chamados_por_categoria_servicos,
        )

        if request.user.has_group_cached('centralservicos Administrador'):
            data1 = obtem_media_tempo_chamados_agrupado_por_ano('campus_id', 'tempo_atendimento', inicio, termino, area)
            for i in data1:
                if i[0]:
                    uo = UnidadeOrganizacional.objects.suap().get(pk=i[0])
                    i[0] = uo.sigla
                else:
                    i[0] = 'Não definido'
                i[1] = float(i[1])
            grafico_media_tempo_atendimento_agrupado_por_ano = ColumnChart(
                'grafico_media_tempo_atendimento_agrupado_por_ano',
                title='Média do Tempo de Atendimento por UO',
                subtitle='em horas / agrupado por ano',
                minPointLength=10,
                data=data1,
            )
            grafico_media_tempo_atendimento_agrupado_por_ano.series[0]['dataLabels'] = {
                'enabled': True,
                'rotation': -90,
                'color': '#FFF',
                'align': 'right',
                'x': 4,
                'y': 10,
            }
            grafico_media_tempo_atendimento_agrupado_por_ano.xAxis['labels'] = {'rotation': -45, 'align': 'right'}
            data1 = obtem_media_tempo_chamados_agrupado_por_ano('campus_id', 'tempo_resposta', inicio, termino, area)
            for i in data1:
                if i[0]:
                    uo = UnidadeOrganizacional.objects.suap().get(pk=i[0])
                    i[0] = uo.sigla
                else:
                    i[0] = 'Não definido'
                i[1] = float(i[1])
            grafico_media_tempo_resposta_agrupado_por_ano = ColumnChart(
                'grafico_media_tempo_resposta_agrupado_por_ano',
                title='Média do Tempo de Resposta por UO',
                subtitle='em horas / agrupado por ano',
                minPointLength=10,
                data=data1,
            )
            grafico_media_tempo_resposta_agrupado_por_ano.series[0]['dataLabels'] = {
                'enabled': True,
                'rotation': -90,
                'color': '#FFF',
                'align': 'right',
                'x': 4,
                'y': 10,
            }
            grafico_media_tempo_resposta_agrupado_por_ano.xAxis['labels'] = {'rotation': -45, 'align': 'right'}

    return locals()


@rtr()
@permission_required('centralservicos.pode_ver_indicadores')
def atendimentos_por_ano(request):
    title = 'Relatório de Atendimentos por Ano'
    form = AtendimentosPorAnoForm(request.POST or None, request=request)
    if form.is_valid():
        inicio = form.cleaned_data.get('inicio')
        termino = form.cleaned_data.get('termino')
        area = form.cleaned_data.get('area')
        pks_chamados_resolvidos = HistoricoStatus.objects.filter(
            data_hora__year__gte=inicio, data_hora__year__lte=termino, status=StatusChamado.get_status_resolvido()
        ).values_list('chamado__id', flat=True)
        chamados = (
            Chamado.objects.filter(pk__in=pks_chamados_resolvidos)
            .annotate(tempo_atendimento=Sum('historicostatus__tempo_atendimento'), tempo_resposta=Sum('historicostatus__tempo_resposta'))
            .annotate(total_atendimento=F('tempo_atendimento') + F('tempo_resposta'))
        )
        if area:
            chamados = chamados.filter(servico__grupo_servico__categorias__area=area)
        chamados_por_uo = OrderedDict()
        for uo in UnidadeOrganizacional.objects.suap():
            chamados_uo = chamados.filter(campus=uo)
            if chamados_uo.exists():
                chamados_uo = chamados_uo.aggregate(total_chamados=Count(F('id')), media_tempo_atendimento=Avg('total_atendimento'))
                chamados_por_uo[uo] = chamados_uo

    return locals()


@rtr()
@permission_required('centralservicos.pode_ver_indicadores')
def relatorio_atendentes(request):
    title = 'Relatório de Situação dos Atendentes'

    FormClass = AtendentesFormFactory(request)
    form = FormClass(request.GET or None)
    if form.is_valid():
        uo = form.cleaned_data.get('uo')
        setor = form.cleaned_data.get('setor')
        grupo_atendimento = form.cleaned_data.get('grupo_atendimento')
        area = form.cleaned_data.get('area')

        lista_atendentes = GrupoAtendimento.objects.all()

        if uo:
            lista_atendentes = lista_atendentes.filter(campus=uo)

        if setor:
            lista_atendentes = lista_atendentes.filter(atendentes__vinculo__setor=setor)

        if area:
            lista_atendentes = lista_atendentes.filter(centro_atendimento__area=area)

        meus_grupos = GrupoAtendimento.meus_grupos(request.user)
        if grupo_atendimento:
            lista_atendentes = lista_atendentes.filter(id=grupo_atendimento.id)
        else:
            lista_atendentes = lista_atendentes.filter(id__in=meus_grupos)

        atendentes = []
        for usuario in User.objects.filter(id__in=lista_atendentes.values('atendentes')):
            total_chamados = Chamado.get_chamados_do_suporte(
                user=usuario, area=area, grupo_atendimento=grupo_atendimento, uo=uo, atribuicoes=Chamado.ATRIBUIDOS_A_MIM
            ).count()

            vinculo_usuario = usuario.get_vinculo()
            atendentes.append([usuario.pk, usuario.get_profile().nome, vinculo_usuario.foto, total_chamados, vinculo_usuario.pk])
        atendentes = sorted(atendentes, key=lambda atend: atend[3])

    return locals()


@rtr()
@permission_required(['centralservicos.add_interested'])
def adicionar_outros_interessados(request, chamado_id):
    chamado = get_object_or_404(Chamado, pk=chamado_id)
    title = 'Adicionar Outros Interessados'
    if chamado.pode_visualizar(request.user):
        # Os atores de um chamado são instâncias de User. Mas os choices fields correspondentes, no
        # formulário a seguir, trabalham com instâncias de Vinculo. Então os consumidores dessa view
        # devem parametrizar, se for o caso, os fields dos atores com IDs de Vinculo.

        FormClass = AdicionarOutrosInteressadosFormFactory(request, chamado)
        form = FormClass(request.POST or None)

        if form.is_valid():
            try:
                chamado.adicionar_outros_interessados(form.outros_interessados_as_users())
                return httprr('..', 'Adição de outros interessados realizada com sucesso.')
            except ValidationError as e:
                messages.error(request, ''.join(e.messages))
    else:
        raise PermissionDenied('Você não tem permissão para adicionar outros interessados neste chamado.')

    return locals()


@rtr()
@permission_required(['centralservicos.add_interested'])
def adicionar_grupo_de_interessados(request, chamado_id):
    chamado = get_object_or_404(Chamado, pk=chamado_id)
    title = 'Adicionar Grupo de Interessados'
    if chamado.pode_visualizar(request.user):
        FormClass = AdicionarGrupoInteressadosFormFactory(request, chamado)
        form = FormClass(request.POST or None)
        if form.is_valid():
            try:
                chamado.adicionar_grupos_interessados(form.cleaned_data.get('grupos_interessados'))
                return httprr('..', 'Adição de grupo de interessados realizada com sucesso.')
            except ValidationError as e:
                messages.error(request, ''.join(e.messages))
    else:
        raise PermissionDenied('Você não tem permissão para adicionar um grupo de interessados neste chamado.')

    return locals()


@rtr()
@permission_required(['centralservicos.remove_interested'])
def remover_outros_interessados(request, chamado_id, usuario_id):
    chamado = get_object_or_404(Chamado, pk=chamado_id)
    usuario = get_object_or_404(User, pk=usuario_id)
    title = 'Remover Interessado'
    if chamado.pode_visualizar(request.user):
        if request.method == 'POST':
            chamado.outros_interessados.remove(usuario)
            if request.user != usuario:
                return httprr(chamado.get_absolute_url(), 'Interessado removido com sucesso.')
            else:
                return httprr('/', 'Interessado removido com sucesso.')

    else:
        raise PermissionDenied('Você não tem permissão para remover interessados neste chamado.')

    return locals()


@rtr()
@permission_required(['centralservicos.pode_unificar_baseconhecimento'])
def unificar_basesconhecimento(request):
    title = 'Unificar Bases de Conhecimento'
    if not request.GET.get('bases'):
        raise PermissionDenied('Nenhuma base de conhecimento selecionada.')

    ids = request.GET.getlist('bases')[0].split(',')
    bases = BaseConhecimento.objects.filter(id__in=ids)
    if request.method == 'POST':
        base_principal = BaseConhecimento.objects.get(pk=request.POST.get('base_id'))
        removeu = False
        for base in bases:
            if base != base_principal:
                for historico in HistoricoStatus.objects.filter(bases_conhecimento=base):
                    historico.bases_conhecimento.add(base_principal)
                    historico.bases_conhecimento.remove(base)
                base.delete()
                removeu = True
        bases = BaseConhecimento.objects.filter(id__in=ids)
        if removeu:
            messages.success(request, 'Bases de conhecimento unificadas com sucesso.')
    return locals()


@rtr()
@permission_required(['centralservicos.review_baseconhecimento'])
def revisar_basesconhecimento(request):
    title = 'Revisar Bases de Conhecimento'

    if request.GET.get('bases'):
        ids = request.GET.getlist('bases')[0].split(',')
        bases = BaseConhecimento.objects.filter(id__in=ids)
    if request.method == 'POST':
        ids = request.POST.getlist('base_id')
        if len(ids) == 0:
            messages.error(request, 'Nenhuma base de conhecimento foi selecionada.')
        else:
            BaseConhecimento.objects.filter(id__in=ids).update(necessita_correcao=False, supervisao_pendente=False)
            messages.success(request, 'Bases de conhecimento revisadas com sucesso.')

    return locals()


@rtr()
def marcar_baseconhecimento_para_correcao(request, baseconhecimento_id):
    title = 'Solicitar correção de artigo da Base de Conhecimentos'
    base_conhecimento = get_object_or_404(BaseConhecimento, pk=baseconhecimento_id)
    if request.method == 'POST':
        form = MarcarParaCorrecaoForm(request.POST)
        if form.is_valid():
            comentario = form.cleaned_data.get('comentario')
            base_conhecimento.marcar_para_correcao(comentario, request.user)
            return httprr(base_conhecimento.get_absolute_url(), 'Base de conhecimento marcada para correção.')
    else:
        form = MarcarParaCorrecaoForm()

    return locals()


@rtr('centralservicos/templates/visualizar_chamados_semelhantes.html')
@permission_required('centralservicos.solve_chamado')
def visualizar_chamados_semelhantes(request, chamado_id):
    title = 'Visualizar Chamados Semelhantes'
    chamado = get_object_or_404(Chamado, pk=chamado_id)
    if chamado.eh_atendente(request.user):
        chamados = Chamado.objects.filter(status=StatusChamado.RESOLVIDO, servico_id=chamado.servico_id)[:20]
    else:
        raise PermissionDenied('Você não tem permissão para visualizar chamados semelhantes.')
    return locals()


@rtr('centralservicos/templates/visualizar_outros_chamados_do_interessado.html')
@permission_required('centralservicos.solve_chamado')
def visualizar_outros_chamados_do_interessado(request, chamado_id):
    title = 'Outros Chamados do Interessado'
    chamado = get_object_or_404(Chamado, pk=chamado_id)
    chamados = (
        Chamado.objects.exclude(pk=chamado.pk)
        .filter(
            interessado_id=chamado.interessado_id,
            servico__centros_atendimento__area__in=chamado.servico.centros_atendimento.all().values_list('area', flat=True),
        )
        .distinct()[:20]
    )
    return locals()


@rtr()
@permission_required('centralservicos.change_chamado')
def adicionar_tags_ao_chamado(request, chamado_id):
    chamado = get_object_or_404(Chamado, pk=chamado_id)
    title = 'Adicionar tags a este chamado'
    FormClass = AdicionarTagsAoChamadoFormFactory(request, chamado)
    form = FormClass(request.POST or None)
    if form.is_valid():
        try:
            chamado.adicionar_tags(form.cleaned_data.get('tags'))
            return httprr('..', 'Adição de tags realizada com sucesso.')
        except ValidationError as e:
            messages.error(request, ''.join(e.messages))

    return locals()


@rtr()
@permission_required('centralservicos.change_chamado')
def remover_tag_do_chamado(request, chamado_id, tag_id):
    chamado = get_object_or_404(Chamado, pk=chamado_id)
    tag = get_object_or_404(Tag, pk=tag_id)
    if request.method == 'POST':
        chamado.tags.remove(tag)
        return httprr(chamado.get_absolute_url(), 'Tag removida com sucesso.')
    return locals()


@rtr()
@permission_required('centralservicos.delete_baseconhecimentoanexo')
def remover_anexo_baseconhecimento(request, baseconhecimento_id, baseconhecimento_anexo_id):
    baseconhecimento = get_object_or_404(BaseConhecimento, pk=baseconhecimento_id)
    baseconhecimento_anexo = get_object_or_404(BaseConhecimentoAnexo, pk=baseconhecimento_anexo_id)
    if request.method == 'POST':
        baseconhecimento_anexo.delete()
        return httprr(baseconhecimento.get_absolute_url(), 'Anexo removido com sucesso.')
    return locals()


@rtr('centralservicos/templates/visualizar_chamados_resolvidos.html')
def baseconhecimento_chamados_resolvidos(request, baseconhecimento_id):
    title = 'Chamados Resolvidos com Este Artigo'
    base_conhecimento = get_object_or_404(BaseConhecimento, pk=baseconhecimento_id)
    chamados = Chamado.objects.filter(
        pk__in=HistoricoStatus.objects.filter(
            status=StatusChamado.get_status_resolvido(), bases_conhecimento__id__in=[baseconhecimento_id]
        ).values_list('chamado_id', flat=True)
    )
    return locals()


@rtr()
def monitoramento(request, token):
    obj = get_object_or_404(Monitoramento, token=token)
    title = f'Monitoramento de Chamados: {obj.titulo} '

    ha_pendencias = False
    resultado = []
    organizar_por_tipo = obj.organizar_por_tipo

    for grupo in obj.grupos.all():
        atendimentos = AtendimentoAtribuicao.objects.filter(grupo_atendimento=grupo, cancelado_em__isnull=True)

        qs_atribuidos = Chamado.ativos.filter(pk__in=atendimentos.filter(atribuido_para__isnull=False).values('chamado'))
        qs_nao_atribuidos = Chamado.ativos.filter(pk__in=atendimentos.filter(atribuido_para__isnull=True).values('chamado'))

        qtd_com_sla_estourado = Chamado.com_sla_estourado.filter(pk__in=atendimentos.filter(atribuido_para__isnull=False).values('chamado')).count()

        qtd_incidentes_atribuidos = qs_atribuidos.filter(servico__tipo=Servico.TIPO_INCIDENTE).count()
        qtd_incidentes_nao_atribuidos = qs_nao_atribuidos.filter(servico__tipo=Servico.TIPO_INCIDENTE).count()

        qtd_requisicoes_atribuidas = qs_atribuidos.filter(servico__tipo=Servico.TIPO_REQUISICAO).count()
        qtd_requisicoes_nao_atribuidas = qs_nao_atribuidos.filter(servico__tipo=Servico.TIPO_REQUISICAO).count()
        item = {
            'grupo': grupo,
            'qtd_incidentes_atribuidos': qtd_incidentes_atribuidos,
            'qtd_requisicoes_atribuidas': qtd_requisicoes_atribuidas,
            'qtd_atribuidos': qs_atribuidos.count(),
            'qtd_incidentes_nao_atribuidos': qtd_incidentes_nao_atribuidos,
            'qtd_requisicoes_nao_atribuidas': qtd_requisicoes_nao_atribuidas,
            'qtd_nao_atribuidos': qs_nao_atribuidos.count(),
            'qtd_com_sla_estourado': qtd_com_sla_estourado,
        }
        if qtd_incidentes_nao_atribuidos > 0 or qtd_requisicoes_nao_atribuidas > 0:
            ha_pendencias = True
        resultado.append(item)

    return locals()


@minhas_acoes.registrar_acao()
def minhas_acoes_central_servicos(request, data, datahora_inicio, datahora_fim):
    if in_group(request.user, 'Atendente da Central de Serviços', ignore_groups_if_superuser=False):
        usuario_id = request.user.id

        filters_chamados_abertos = {}
        if datahora_inicio:
            filters_chamados_abertos['aberto_em__gte'] = datahora_inicio
        if datahora_fim:
            filters_chamados_abertos['aberto_em__lte'] = datahora_fim

        qs_chamados_abertos = (
            Chamado.objects.filter(aberto_por__id=usuario_id, **filters_chamados_abertos).select_related('servico').order_by('aberto_em')
        )
        for chamado_aberto in qs_chamados_abertos:
            data.append(
                (
                    'Central de Serviços',
                    'Abertura de Chamados',
                    chamado_aberto,
                    f'em {chamado_aberto.aberto_em.strftime("%d/%m/%Y %H:%M")}',
                    f'{chamado_aberto.get_absolute_url()}',
                )
            )

        filters_historico_chamados = {}
        if datahora_inicio:
            filters_historico_chamados['data_hora__gte'] = datahora_inicio
        if datahora_fim:
            filters_historico_chamados['data_hora__lte'] = datahora_fim

        qs_historicostatus = (
            HistoricoStatus.objects.filter(usuario_id=usuario_id, status=StatusChamado.get_status_resolvido(), **filters_historico_chamados)
            .select_related('chamado', 'chamado__servico')
            .only('chamado__servico__nome', 'chamado_id', 'data_hora')
            .order_by('data_hora')
        )
        for chamados_resolvidos in qs_historicostatus:
            data.append(
                (
                    'Central de Serviços',
                    'Resolução de Chamados',
                    chamados_resolvidos.chamado,
                    f'em {chamados_resolvidos.data_hora.strftime("%d/%m/%Y %H:%M")}',
                    f'{chamados_resolvidos.chamado.get_absolute_url()}',
                )
            )

        qs_chamados_cancelados = (
            HistoricoStatus.objects.filter(usuario_id=usuario_id, status=StatusChamado.get_status_cancelado(), **filters_historico_chamados)
            .select_related('chamado', 'chamado__servico')
            .only('chamado__servico__nome', 'chamado_id', 'data_hora')
            .order_by('data_hora')
        )
        for chamados_cancelados in qs_chamados_cancelados:
            data.append(
                (
                    'Central de Serviços',
                    'Cancelamento de Chamados',
                    chamados_cancelados.chamado,
                    f'em {chamados_cancelados.data_hora.strftime("%d/%m/%Y %H:%M")}',
                    f'{chamados_cancelados.chamado.get_absolute_url()}',
                )
            )

        filters_chamados_atribuidos = {}
        if datahora_inicio:
            filters_chamados_atribuidos['atribuido_em__gte'] = datahora_inicio
        if datahora_fim:
            filters_chamados_atribuidos['atribuido_em__lte'] = datahora_fim

        qs_atendimento_atribuicao = (
            AtendimentoAtribuicao.objects.filter(atribuido_por__id=usuario_id, **filters_chamados_atribuidos)
            .exclude(atribuido_para__id=usuario_id)
            .select_related('chamado', 'chamado__servico', 'atribuido_para__vinculo__pessoa')
            .only('chamado_id', 'atribuido_para__vinculo__pessoa__nome', 'atribuido_em', 'chamado__servico__nome')
            .order_by('atribuido_em')
        )
        for atendimento_atribuicao in qs_atendimento_atribuicao:
            atribuido_para = atendimento_atribuicao.atribuido_para.get_profile().nome if atendimento_atribuicao.atribuido_para else 'Nínguem'
            data.append(
                (
                    'Central de Serviços',
                    'Atribuição de Chamados',
                    atendimento_atribuicao.chamado,
                    f'para {atribuido_para} em {atendimento_atribuicao.atribuido_em.strftime("%d/%m/%Y %H:%M")}',
                    f'{atendimento_atribuicao.chamado.get_absolute_url()}',
                )
            )


@rtr()
@login_required()
def editar_patrimonio_relacionado(request, chamado_id):
    chamado = get_object_or_404(Chamado, pk=chamado_id)

    if not chamado.pode_editar_patrimonio_relacionado(request.user):
        raise PermissionDenied('Você não tem permissão para editar o patrimônio relacionado a este chamado.')

    form = EditarPatrimonioRelacionadoChamadoForm(request.POST or None, instance=chamado)

    if form.is_valid():
        form.save()
        return httprr('..', 'Alteração realizada com sucesso.')

    title = 'Editar patrimônio relacionado'

    return locals()


@rtr()
@login_required()
def visualizar_tarefa(request, tarefa_id):
    tarefa = get_object_or_404(Tarefa, pk=tarefa_id)
    if not Tarefa.pode_visualizar_cadastro_tarefas(request.user):
        raise PermissionDenied('Você não tem permissão para visualizar esta tarefa.')
    title = f'Tarefa: {tarefa}'
    pode_editar = tarefa.pode_editar(request.user)
    historico_vinculacoes_a_chamados = tarefa.get_historico_vinculacoes_a_chamados()
    return locals()


@rtr()
@login_required()
def vincular_tarefa_chamado(request, chamado_id):
    title = 'Adicionar Tarefa ao Chamado'
    chamado = get_object_or_404(Chamado, pk=chamado_id)
    if not chamado.pode_vincular_tarefas(request.user):
        raise PermissionDenied('Você não tem permissão para adicionar tarefas ao chamado.')
    formClass = TarefaChamadoAddFormFactory(chamado)
    form = formClass(request.POST or None)
    if form.is_valid():
        try:
            TarefaChamado.vincular_tarefa(
                request.user,
                form.cleaned_data.get('tarefa'),
                chamado,
                form.cleaned_data.get('responsavel'),
                form.cleaned_data.get('situacao'),
            )
            return httprr('..')
        except Exception:
            form.add_error(None, 'Ocorreu um erro. Tente novamente.')
    return locals()


@rtr()
@login_required()
def visualizar_tarefa_chamado(request, tarefa_chamado_id):
    tarefa_chamado = get_object_or_404(TarefaChamado, pk=tarefa_chamado_id)
    if not tarefa_chamado.pode_visualizar(request.user):
        raise PermissionDenied('Você não tem permissão para visualizar esta tarefa.')
    title = f'Tarefa: {tarefa_chamado}'
    pode_atualizar_situacao = tarefa_chamado.pode_atualizar_situacao(request.user)
    historico_alteracoes = tarefa_chamado.get_historico_alteracoes()
    return locals()


@rtr()
@login_required()
def editar_tarefa_chamado(request, tarefa_chamado_id):
    tarefa_chamado = get_object_or_404(TarefaChamado, pk=tarefa_chamado_id)
    if not tarefa_chamado.pode_atualizar_situacao(request.user):
        raise PermissionDenied('Você não tem permissão para editar esta tarefa.')
    title = f'Alterar Tarefa: {tarefa_chamado}'
    formClass = TarefaChamadoChangeFormFactory(
        tarefa_chamado,
        somente_situacao=(request.GET or {}).get('somente_situacao') == '1',
        somente_responsavel=(request.GET or {}).get('somente_responsavel') == '1',
    )
    form = formClass(request.POST or None, instance=tarefa_chamado)
    if form.is_valid():
        try:
            tarefa_chamado.alterar_tarefa(
                request.user,
                form.cleaned_data.get('responsavel'),
                form.cleaned_data.get('situacao'),
            )
            return httprr('..')
        except Exception:
            form.add_error(None, 'Ocorreu um erro. Tente novamente.')
    return locals()


@rtr()
@login_required()
def visualizar_historico_tarefa_chamado(request, tarefa_chamado_id):
    tarefa_chamado = get_object_or_404(TarefaChamado, pk=tarefa_chamado_id)
    if not tarefa_chamado.pode_visualizar(request.user):
        raise PermissionDenied('Você não tem permissão para visualizar o histórico de alterações desta tarefa.')
    title = f'Histórico de alterações da Tarefa: {tarefa_chamado}'
    historico_alteracoes = tarefa_chamado.get_historico_alteracoes()
    return locals()


@rtr()
@permission_required(['centralservicos.change_baseconhecimento'])
def editar_area_baseconhecimento(request, baseconhecimento_id):
    base_conhecimento = get_object_or_404(BaseConhecimento, pk=baseconhecimento_id)
    if not base_conhecimento.pode_editar_area(request.user):
        raise PermissionDenied('Você não tem permissão para editar a área desta base de conhecimento.')
    title = f'Editar Área da Base de Conhecimento "{base_conhecimento}"'
    formClass = EditarAreaBaseConhecimentoFormFactory(request.user)
    form = formClass(request.POST or None, instance=base_conhecimento)
    if form.is_valid():
        form.save()
        return httprr('..')
    return locals()


@rtr()
@permission_required(['centralservicos.view_chamado'])
def estatisticas_servico(request, servico_id):
    servico = get_object_or_404(Servico, pk=servico_id)
    if servico not in Servico.get_servicos_ao_atendente(request.user):
        raise PermissionDenied
    title = f'Estatísticas do serviço "{servico.nome}"'
    pode_editar_servico = servico.pode_editar_servico(request.user)
    return locals()


@rtr()
@permission_required(['centralservicos.view_chamado'])
def atualizar_estatisticas_servico(request: HttpRequest, servico_id: int) -> HttpResponse | dict:
    servico = get_object_or_404(Servico, pk=servico_id)
    if not servico.pode_editar_servico(request.user):
        raise PermissionDenied
    title = f'Atualizar estatísticas do serviço "{servico.nome}"'
    form = ConfirmarAcaoFormFactory('A atualização das estatísticas do serviço pode demorar.')(request.POST or None)
    if form.is_valid():
        # O recálculo percorre todos os chamados do serviço: roda em background (tela de progresso da tarefa).
        return tasks.atualizar_estatisticas(servico)
    return locals()
