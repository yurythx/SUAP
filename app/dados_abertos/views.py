from datetime import date

from django.core.exceptions import PermissionDenied, ValidationError
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.admin.sites import site as admin_site
from djtools.utils import rtr, httprr
from django.http import Http404, HttpRequest, HttpResponseRedirect, JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from collections import defaultdict

from djtools import layout

from .enums import EstadoCKAN, SituacaoLAI
from .models import BaseDados, PlanoDadosAbertos, Etapa, PDAAcao, PDABaseDados, PDAEtapa, RecursoDados, VersaoPDA
from .services.ckan_api_service import get_ckan_service
from .services.ckan_service import sync_dataset_with_ckan, sync_resource_with_ckan
from .services.dashboard_service import anotar_deliberacao_lai, buscar_bases_relacionadas, montar_dados_bases_pda
from .services.documento_pda_service import (
    find_pda_by_versao_arquivo,
    ler_documento_html,
    url_arquivo,
    versoes_com_arquivos,
)
from .services.lai_service import montar_detalhe, montar_fila, progresso_pda, registrar_deliberacao, registrar_reenvio
from .services.acoes_automaticas_service import sincronizar_acoes_automaticas
from .services.visualizacao import ULTIMOS_EVENTOS_LAI, visualizacao_base, visualizacao_recurso
from .services import pendencias_service
from .services.matriz_priorizacao_service import (
    build_matriz_data,
    finalizar_avaliacoes,
    iter_notas_from_post,
    salvar_notas,
)


@rtr('dadosabertos/base_dados_detalhe.html')
@login_required
def base_dados_detalhe(request: HttpRequest, pk: int) -> dict:
    """Visualização da base de dados (``BaseDados.get_absolute_url``)."""
    if not request.user.has_perm('dados_abertos.view_basedados'):
        raise PermissionDenied
    base = get_object_or_404(BaseDados.objects.select_related('organizacao', 'licenca', 'tema'), pk=pk)
    return {'title': str(base), 'base': base, 'v': visualizacao_base(base, request.user), 'ULTIMOS_EVENTOS_LAI': ULTIMOS_EVENTOS_LAI}


@rtr('dadosabertos/recurso_dados_detalhe.html')
@login_required
def recurso_dados_detalhe(request: HttpRequest, pk: int) -> dict:
    """Visualização do recurso, com a prévia dos dados (``RecursoDados.get_absolute_url``)."""
    if not request.user.has_perm('dados_abertos.view_recursodados'):
        raise PermissionDenied
    recurso = get_object_or_404(RecursoDados.objects.select_related('dataset', 'derivado_de'), pk=pk)
    return {'title': str(recurso), 'recurso': recurso, 'v': visualizacao_recurso(recurso, request.user)}


@rtr()
def pda_detalhe(request, pk: int):
    obj = get_object_or_404(PlanoDadosAbertos, pk=pk)
    if not request.user.has_perm('dados_abertos.view_planodadosabertos'):
        raise PermissionDenied

    capa = obj.capa.first() if hasattr(obj, 'capa') else None
    topicos = obj.topicos.all().order_by('ordem', 'id')

    context = {
        **admin_site.each_context(request),
        'title': obj.titulo,
        'pda': obj,
        'capa': capa,
        'topicos': topicos,
    }
    return render(request, 'dadosabertos/pda_detalhe.html', context)


def _status_etapa(etapa, pulada, pendente, pda, etapa_atual_ordem):
    """Classifica o status de exibição de uma etapa no dashboard."""
    if pulada:
        return 'pulada'
    if pda.etapa_atual_id == etapa.id:
        return 'atual'
    if not pendente and etapa.ordem < etapa_atual_ordem:
        return 'concluida'
    if etapa.ordem > (pda.etapa_atual.ordem if pda.etapa_atual else 0):
        return 'bloqueada'
    return 'pendente'


def _montar_etapas_data(pda):
    """Monta a lista de etapas (com progresso/status) e o progresso geral do PDA.

    Etapas dispensadas (puladas) recebem status ``'pulada'``, progresso 100% e não bloqueiam o
    fluxo; suas ações obrigatórias contam como resolvidas no progresso geral.
    """
    puladas_ids = pda.etapas_puladas_ids()
    etapas = list(Etapa.objects.all())
    acoes = list(getattr(pda, 'acoes', []).all())

    acoes_por_etapa: dict[int, list[PDAAcao]] = defaultdict(list)
    total_por_etapa: dict[int, int] = defaultdict(int)
    concluidas_por_etapa: dict[int, int] = defaultdict(int)
    obrigatoria_pendente_por_etapa: dict[int, bool] = defaultdict(bool)

    obrigatorias_total = 0
    obrigatorias_resolvidas = 0

    for pda_acao in acoes:
        etapa_id = pda_acao.acao.etapa_id
        pulada = etapa_id in puladas_ids
        acoes_por_etapa[etapa_id].append(pda_acao)
        total_por_etapa[etapa_id] += 1
        if pda_acao.concluida:
            concluidas_por_etapa[etapa_id] += 1

        if not pda_acao.acao.obrigatoria:
            continue

        obrigatorias_total += 1
        if pda_acao.concluida or pulada:
            # a dispensa encerra a etapa: suas obrigatórias contam como resolvidas
            obrigatorias_resolvidas += 1
        else:
            obrigatoria_pendente_por_etapa[etapa_id] = True

    progresso_geral = round(obrigatorias_resolvidas * 100 / obrigatorias_total) if obrigatorias_total else 0

    etapa_atual_ordem = pda.etapa_atual.ordem if pda.etapa_atual else 999

    etapas_data = []
    for etapa in etapas:
        etapa_id = etapa.id
        total = total_por_etapa.get(etapa_id, 0)
        if etapa_id in puladas_ids:
            progresso = 100  # etapa dispensada aparece resolvida, como em get_progresso_etapa()
        else:
            progresso = round(concluidas_por_etapa.get(etapa_id, 0) * 100 / total) if total else 0
        pendente = obrigatoria_pendente_por_etapa.get(etapa_id, False)
        etapas_data.append(
            {
                'etapa': etapa,
                'acoes_pda': acoes_por_etapa.get(etapa_id, []),
                'progresso': progresso,
                'status': _status_etapa(etapa, etapa_id in puladas_ids, pendente, pda, etapa_atual_ordem),
                'pulavel': etapa.pulavel,
                'pulada': etapa_id in puladas_ids,
            }
        )
    return etapas_data, progresso_geral


@rtr()
@login_required
def dashboard(request, pda_id=None):
    if not request.user.has_perm('dados_abertos.view_planodadosabertos'):
        raise PermissionDenied
    title = 'Dashboard do Dados Abertos'
    pdas = list(PlanoDadosAbertos.objects.only('id', 'titulo', 'vigencia_inicio', 'vigencia_fim').order_by('-vigencia_inicio', '-id'))
    if not pdas:
        return httprr('..', 'Nenhum Plano de Dados Abertos cadastrado.', tag='warning')

    # checando pda selecionado
    if pda_id is None:
        pda_id = pdas[0].id

    # Inicializa o checklist e sincroniza as ações automáticas ANTES de carregar para exibição,
    # para o dashboard refletir o estado real (bases com recurso, liberação LAI, sync CKAN, etc.).
    pda_atual = get_object_or_404(PlanoDadosAbertos, pk=pda_id)
    pda_atual.inicializar_checklist()
    sincronizar_acoes_automaticas(pda_atual)

    pda = get_object_or_404(
        PlanoDadosAbertos.objects.select_related('etapa_atual').prefetch_related(
            Prefetch(
                'acoes',
                queryset=PDAAcao.objects.select_related('acao', 'acao__etapa').order_by('acao__ordem', 'acao_id'),
            )
        ),
        pk=pda_id,
    )

    etapas_data, progresso_geral = _montar_etapas_data(pda)

    # --- Plano de Ação ---
    bases_relacionadas = buscar_bases_relacionadas(pda)
    devolvidas_lai = anotar_deliberacao_lai(bases_relacionadas)
    bases_relacionadas, plano_pendencias, ckan_resumo = montar_dados_bases_pda(bases_relacionadas, request.user)

    contexto = {
        **admin_site.each_context(request),
        'title': title,
        'pdas': pdas,
        'pda': pda,
        'etapas_data': etapas_data,
        'progresso_geral': progresso_geral,
        'bases_relacionadas': bases_relacionadas,
        'plano_pendencias': plano_pendencias,
        'devolvidas_lai': devolvidas_lai,
        'usuario_pode_reenviar_lai': request.user.has_perm('dados_abertos.change_pdabasedados'),
        'ckan_resumo': ckan_resumo,
        'ckan_configurado': ckan_resumo['configurado'],
        'usuario_pode_sincronizar_ckan': request.user.has_perm('dados_abertos.change_basedados'),
        'usuario_pode_marcar_acoes': request.user.has_perm('dados_abertos.change_planodadosabertos'),
        'usuario_pode_pular_etapa': request.user.has_perm('dados_abertos.pular_etapa_pda'),
        'hoje': date.today(),
    }

    return render(request, 'dadosabertos/dashboard.html', contexto)


@login_required
@require_POST
def sincronizar_base_ckan(request: HttpRequest, pda_id: int, rel_id: int) -> HttpResponseRedirect:
    if not request.user.has_perm('dados_abertos.change_basedados'):
        raise PermissionDenied

    rel = get_object_or_404(
        PDABaseDados.objects.select_related('pda', 'base_dados').prefetch_related('base_dados__recursos'),
        pk=rel_id,
        pda_id=pda_id,
    )

    # as abas do dashboard são indexadas a partir de zero: Etapas (tab0), Plano de Ação (tab1), CKAN (tab2)
    redirect_url = reverse('dados_abertos:dashboard', kwargs={'pda_id': rel.pda_id}) + '?tab=tab2'

    if not rel.base_dados.lai_liberada_para_sync():
        messages.error(request, rel.base_dados.motivo_bloqueio_lai())
        return redirect(redirect_url)

    service = get_ckan_service()
    if not service:
        messages.error(request, 'API CKAN não configurada ou inativa.')
        return redirect(redirect_url)

    recursos = rel.base_dados.recursos.all()
    if not recursos.exists():
        messages.warning(request, 'A base de dados não possui recursos para sincronização.')
        return redirect(redirect_url)

    ok_dataset, err_dataset = sync_dataset_with_ckan(BaseDados.objects.filter(pk=rel.base_dados_id), service.base_url, service.api_key)
    ok_recursos, err_recursos = sync_resource_with_ckan(recursos, service.base_url, service.api_key)

    if err_dataset or err_recursos:
        messages.error(
            request,
            f'Sincronização concluída com pendências. Dataset: {ok_dataset} sucesso(s), {err_dataset} erro(s). Recursos: {ok_recursos} sucesso(s), {err_recursos} erro(s).',
        )
    else:
        messages.success(
            request,
            f'Sincronização com o CKAN concluída. Dataset: {ok_dataset} sucesso(s). Recursos: {ok_recursos} sucesso(s).',
        )

    return redirect(redirect_url)


@login_required
@require_POST
def toggle_acao_pda(request, pda_id, acao_id):
    if not request.user.has_perm('dados_abertos.change_planodadosabertos'):
        return JsonResponse({'ok': False, 'erro': 'Sem permissão para alterar o checklist do PDA.'}, status=403)
    pda = get_object_or_404(PlanoDadosAbertos, pk=pda_id)

    try:
        pda_acao = PDAAcao.objects.select_related('acao', 'acao__etapa').get(
            pda=pda,
            acao_id=acao_id,
        )
    except PDAAcao.DoesNotExist:
        raise Http404('Ação não encontrada para este PDA.')

    if pda_acao.acao.condicao_automatica:
        return JsonResponse(
            {'ok': False, 'erro': 'Ação automática — marcada pelo sistema conforme o estado do PDA.'},
            status=400,
        )

    concluida_str = request.POST.get('concluida', '').lower()
    novo_status = concluida_str in ['true', '1', 'on', 'yes']

    if novo_status:
        pda_acao.marcar_concluida(user=request.user)
    else:
        pda_acao.marcar_pendente()

    etapa = pda_acao.acao.etapa
    progresso_etapa = pda.get_progresso_etapa(etapa)

    return JsonResponse(
        {
            'ok': True,
            'acao_id': pda_acao.acao_id,
            'concluida': pda_acao.concluida,
            'progresso_etapa': progresso_etapa,
            'etapa_atual_id': pda.etapa_atual_id,
            'progresso_geral': pda.get_progresso_geral(),
        }
    )


def _pda_da_matriz(request, pdas):
    """PDA sobre o qual a matriz opera: o escolhido na tela ou, por padrão, o de vigência mais recente.

    Em POST o corpo tem precedência sobre a query string: o formulário é a fonte da verdade, e uma
    URL com ``?pda=`` antiga (bookmark, edição manual) não deve redirecionar as notas para outro PDA.

    Args:
        request: Requisição atual (o PDA vem em ``pda``, por GET ou POST).
        pdas: QuerySet de PDAs já ordenado por vigência decrescente.

    Returns:
        PlanoDadosAbertos | None: PDA selecionado, ou ``None`` se não houver nenhum cadastrado.
    """
    pda_id = request.POST.get('pda') or request.GET.get('pda')
    if pda_id:
        selecionado = pdas.filter(pk=pda_id).first()
        if selecionado:
            return selecionado
    return pdas.first()


def _redirecionar_para_matriz(pda):
    """Redireciona para a matriz preservando o PDA selecionado."""
    url = reverse('dados_abertos:matriz_priorizacao')
    return redirect(f'{url}?pda={pda.pk}' if pda else url)


def _processar_matriz_post(request, pda, matriz):
    """Salva as notas enviadas e, se pedido, finaliza a matriz do PDA.

    Args:
        request: Requisição POST com os campos ``nota_{base}_{criterio}`` e ``acao``.
        pda: PDA selecionado na tela.
        matriz: Dados da matriz montados para o PDA.

    Returns:
        HttpResponseRedirect: Volta para a matriz do mesmo PDA.
    """
    if not matriz.pda:
        messages.error(request, 'Nenhum PDA cadastrado.')
        return _redirecionar_para_matriz(pda)

    acao = (request.POST.get('acao') or 'salvar').lower().strip()

    criterios_ids = set(matriz.criterios.values_list('id', flat=True))
    bases_ids = set(matriz.pda.bases_dados.values_list('id', flat=True))

    notas = iter_notas_from_post(request.POST)
    atualizados, ignorados_finalizados = salvar_notas(
        bases_ids=bases_ids,
        criterios_ids=criterios_ids,
        notas=notas,
    )

    if acao == 'finalizar':
        if matriz.pda.tem_base_sem_avaliacao():
            messages.error(request, 'Não é possível finalizar. Todas as bases devem ter uma avaliação cadastrada.')
            return _redirecionar_para_matriz(pda)

        finalizadas_agora = finalizar_avaliacoes(
            bases_ids=bases_ids,
            criterios_ids=criterios_ids,
        )
        messages.success(request, f'Avaliações finalizadas com sucesso. Finalizadas agora: {finalizadas_agora}.')
        return _redirecionar_para_matriz(pda)

    if atualizados:
        messages.success(request, f'Notas salvas com sucesso. Alterações: {atualizados}.')
    else:
        messages.info(request, 'Nenhuma alteração para salvar.')

    if ignorados_finalizados:
        messages.warning(request, f'{ignorados_finalizados} avaliação(ões) finalizada(s) não foram alteradas.')

    return _redirecionar_para_matriz(pda)


@login_required
def matriz_priorizacao(request):
    """Matriz de priorização: consultar exige ver as avaliações; salvar e finalizar, alterá-las."""
    if not request.user.has_perm('dados_abertos.view_avaliacaobasedados'):
        raise PermissionDenied
    pode_editar = request.user.has_perm('dados_abertos.change_avaliacaobasedados')

    title = 'Matriz de Priorização de PDAs'
    pdas = PlanoDadosAbertos.objects.order_by('-vigencia_inicio', '-id')
    pda = _pda_da_matriz(request, pdas)
    matriz = build_matriz_data(pda)

    if request.method == 'POST':
        if not pode_editar:
            raise PermissionDenied
        return _processar_matriz_post(request, pda, matriz)

    contexto = {
        **admin_site.each_context(request),
        'title': title,
        'pda': pda,
        'pdas': pdas,
        'consulta_publica': matriz.consulta_publica,
        'criterios': matriz.criterios,
        'bases': matriz.bases,
        'tem_base_nao_avaliada': pda.tem_base_nao_avaliada() if pda else None,
        'pode_editar': pode_editar,
    }

    return render(request, 'dadosabertos/matriz_priorizacao.html', contexto)


@login_required
@require_POST
def pular_etapa(request, pda_id, etapa_id):
    """Dispensa (pula) uma etapa pulável do PDA, com justificativa e auditoria."""
    if not request.user.has_perm('dados_abertos.pular_etapa_pda'):
        return JsonResponse({'ok': False, 'erro': 'Sem permissão para pular etapas.'}, status=403)

    pda = get_object_or_404(PlanoDadosAbertos, pk=pda_id)
    etapa = get_object_or_404(Etapa, pk=etapa_id)
    if not etapa.pulavel:
        return JsonResponse({'ok': False, 'erro': 'Esta etapa não pode ser dispensada.'}, status=400)

    justificativa = (request.POST.get('justificativa') or '').strip()
    if not justificativa:
        return JsonResponse({'ok': False, 'erro': 'Informe a justificativa da dispensa.'}, status=400)

    try:
        vinculo = request.user.get_vinculo()
    except Exception:
        vinculo = None

    PDAEtapa.objects.update_or_create(
        pda=pda,
        etapa=etapa,
        defaults={
            'justificativa': justificativa,
            'pulada_por': vinculo,
            'ip': _client_ip(request),
            'user_agent': request.META.get('HTTP_USER_AGENT', ''),
        },
    )
    pda.atualizar_etapa_atual()
    sincronizar_acoes_automaticas(pda)
    return JsonResponse({'ok': True})


@login_required
@require_POST
def reativar_etapa(request, pda_id, etapa_id):
    """Reativa uma etapa dispensada do PDA (remove a dispensa)."""
    if not request.user.has_perm('dados_abertos.pular_etapa_pda'):
        return JsonResponse({'ok': False, 'erro': 'Sem permissão para reativar etapas.'}, status=403)

    pda = get_object_or_404(PlanoDadosAbertos, pk=pda_id)
    PDAEtapa.objects.filter(pda=pda, etapa_id=etapa_id).delete()
    pda.atualizar_etapa_atual()
    sincronizar_acoes_automaticas(pda)
    return JsonResponse({'ok': True})


def _client_ip(request):
    return request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or request.META.get('REMOTE_ADDR')


def _client_vinculo(request):
    try:
        return request.user.get_vinculo()
    except Exception:
        return None


def _erros_de(exc: ValidationError) -> str:
    return '; '.join(m for msgs in exc.message_dict.values() for m in msgs)


def _pda_selecionado(request):
    """PDA da tela: o escolhido no seletor ou, sem escolha, o de vigência mais recente."""
    pda_id = request.GET.get('pda') or request.POST.get('pda')
    if pda_id:
        return PlanoDadosAbertos.objects.filter(pk=pda_id).first()
    return PlanoDadosAbertos.objects.order_by('-vigencia_inicio', '-id').first()


def _item_da_fila(fila: list, rel_id):
    """Item em foco e sua posição (1-based). Sem escolha válida na URL, o primeiro da fila."""
    if not fila:
        return None, 0
    if rel_id:
        for posicao, item in enumerate(fila, start=1):
            if str(item.pk) == str(rel_id):
                return item, posicao
    return fila[0], 1


def _proximo_da_fila(pda, relacao_decidida) -> str:
    """URL do próximo dataset a analisar após uma decisão, para deliberar em sequência."""
    base = f'{reverse("dados_abertos:deliberacao_lai")}?pda={pda.pk if pda else ""}'
    restantes = [item for item in montar_fila(pda) if item.pk != relacao_decidida.pk]
    return f'{base}&rel={restantes[0].pk}' if restantes else base


def _processar_deliberacao_post(request, pda):
    """Registra a decisão. Retorna a URL de redirect, ou ``None`` para re-renderizar com o erro.

    Re-renderizar em vez de redirecionar é o que preserva o parecer digitado quando a validação
    falha — no fluxo anterior o texto era descartado junto com o POST.
    """
    try:
        relacao = registrar_deliberacao(
            relacao_id=int(request.POST['relacao_id']),
            decisao=int(request.POST['decisao']),
            parecer=request.POST.get('parecer', ''),
            vinculo=_client_vinculo(request),
            ip=_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
        )
    except PDABaseDados.DoesNotExist:
        messages.warning(request, 'Este dataset não está mais em análise.')
        return f'{reverse("dados_abertos:deliberacao_lai")}?pda={pda.pk if pda else ""}'
    except ValidationError as e:
        messages.error(request, _erros_de(e))
        return None
    messages.success(request, 'Deliberação registrada.')
    return _proximo_da_fila(pda, relacao)


@rtr('dadosabertos/deliberacao_lai.html')
@login_required
def deliberacao_lai(request):
    if not request.user.has_perm('dados_abertos.deliberar_lai'):
        raise PermissionDenied

    title = 'Deliberação LAI'
    pda = _pda_selecionado(request)
    rel_id = request.POST.get('relacao_id') if request.method == 'POST' else request.GET.get('rel')

    if request.method == 'POST':
        destino = _processar_deliberacao_post(request, pda)
        if destino:
            return redirect(destino)

    fila = montar_fila(pda)
    em_foco, posicao = _item_da_fila(fila, rel_id)
    return {
        'title': title,
        'pda': pda,
        'pdas': PlanoDadosAbertos.objects.order_by('-vigencia_inicio', '-id'),
        'fila': fila,
        'posicao': posicao,
        'anterior': fila[posicao - 2] if posicao > 1 else None,
        'proximo': fila[posicao] if 0 < posicao < len(fila) else None,
        'detalhe': montar_detalhe(em_foco) if em_foco else None,
        'progresso': progresso_pda(pda),
        'parecer_digitado': request.POST.get('parecer', '') if request.method == 'POST' else '',
        'SituacaoLAI': SituacaoLAI,
    }


@login_required
@require_POST
def reenviar_lai(request, pda_id: int, rel_id: int):
    """Devolve ao Responsável LAI um dataset devolvido para ajustes, com a resposta do gestor."""
    if not request.user.has_perm('dados_abertos.change_pdabasedados'):
        raise PermissionDenied

    destino = f'{reverse("dados_abertos:dashboard", args=[pda_id])}#plano-de-acao'
    get_object_or_404(PDABaseDados, pk=rel_id, pda_id=pda_id)
    try:
        registrar_reenvio(
            relacao_id=rel_id,
            texto=request.POST.get('resposta', ''),
            vinculo=_client_vinculo(request),
            ip=_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
        )
    except PDABaseDados.DoesNotExist:
        return httprr(destino, 'Esta base não está devolvida para ajustes.', tag='warning')
    except ValidationError as e:
        return httprr(destino, _erros_de(e), tag='error')
    return httprr(destino, 'Base reenviada ao Responsável LAI.')


@login_required
def gerar_documento_versao_pda(request, pda_id):
    """
    Regenera os arquivos HTML e PDF da versão atual do PDA.
    Útil quando os arquivos foram perdidos ou quando o conteúdo foi alterado
    sem criação de nova versão.
    """
    pda = get_object_or_404(PlanoDadosAbertos, pk=pda_id)

    if not request.user.has_perm('dados_abertos.change_planodadosabertos'):
        raise PermissionDenied

    from .services.documento_pda_service import gerar_documento_pda

    gerar_documento_pda(pda, pda.versao_atual)

    changelist_url = reverse('admin:dados_abertos_planodadosabertos_changelist')
    messages.success(
        request,
        f'Documento do PDA "{pda.titulo}" (v{pda.versao_atual}) gerado com sucesso.',
    )
    return redirect(changelist_url)


@rtr()
@login_required
def criar_versao_pda(request, pda_id):
    title = 'Criar nova versão do PDA'
    pda = get_object_or_404(PlanoDadosAbertos, pk=pda_id)

    if not request.user.has_perm('dados_abertos.add_versaopda'):
        raise PermissionDenied

    from .forms import CriarVersaoPDAForm

    if request.method == 'POST':
        form = CriarVersaoPDAForm(request.POST)
        if form.is_valid():
            form.processar(pda=pda)
            return httprr(reverse('admin:dados_abertos_planodadosabertos_changelist'), message='Versão do PDA criada com sucesso.', close_popup=True)
    else:
        form = CriarVersaoPDAForm()

    return locals()


@layout.atribuidos_a_mim()
def index_atribuidos_a_mim(request):
    """Indicadores de *Minhas pendências* no index: o que é responsabilidade direta do usuário."""
    return pendencias_service.como_indicadores(pendencias_service.pessoais(request.user.get_vinculo()))


@layout.atribuidos_a_meus_grupos()
def index_atribuidos_a_meus_grupos(request):
    """Indicadores de *Pendências coletivas*: o estado do plano, para quem responde por ele.

    O gate vem antes de qualquer consulta — este receiver roda para todo usuário do SUAP, e quem
    não gere dados abertos não deve pagar por nenhuma query.
    """
    if not request.user.has_perm('dados_abertos.change_basedados'):
        return []
    return pendencias_service.como_indicadores(pendencias_service.coletivas())


@layout.servicos_anonimos()
def servicos_anonimos(request):
    return [
        {
            'categoria': 'Transparência',
            'titulo': 'Dados Abertos',
            'icone': 'folder-open',
            'url': '/dados_abertos/publico/',
        }
    ]


def area_publica_pda(request):
    """
    Landing page pública do Plano de Dados Abertos.
    Apresenta todos os PDAs cadastrados com todas as versões geradas.
    """
    pdas_qs = PlanoDadosAbertos.objects.prefetch_related('versoes').order_by('-vigencia_inicio')

    pdas_info = []
    for pda in pdas_qs:
        versoes = versoes_com_arquivos(pda)
        pdas_info.append(
            {
                'pda': pda,
                'versoes': versoes,
                'versao_atual': pda.versao_atual,
                'num_datasets': pda.bases_dados.filter(estado=EstadoCKAN.ACTIVE).count(),
            }
        )

    total_datasets = BaseDados.objects.filter(estado=EstadoCKAN.ACTIVE).count()
    total_recursos = RecursoDados.objects.count()

    return render(
        request,
        'dadosabertos/area_publica_pda.html',
        {
            'pdas_info': pdas_info,
            'total_datasets': total_datasets,
            'total_recursos': total_recursos,
        },
    )


def documento_publico_pda(request, pda_id=None):
    """
    View pública (sem autenticação) que exibe o documento HTML do PDA
    mais recente envolto em um layout institucional.
    """
    versao_str_param = request.GET.get('v', '').strip()

    if pda_id:
        pda = get_object_or_404(PlanoDadosAbertos, pk=pda_id)
        if versao_str_param:
            versoes = list(VersaoPDA.objects.filter(pda=pda).order_by('major', 'minor', 'patch'))
            versao_obj = None
            for i, v in enumerate(versoes):
                arquivo = versoes[i + 1].numero_formatado if i + 1 < len(versoes) else pda.versao_atual
                if arquivo == versao_str_param:
                    versao_obj = v
                    break
            versao_arquivo = versao_str_param
        else:
            versao_obj = VersaoPDA.objects.filter(pda=pda).order_by('-major', '-minor', '-patch').first()
            versao_arquivo = pda.versao_atual
    elif versao_str_param:
        pda, versao_obj = find_pda_by_versao_arquivo(versao_str_param)
        if not pda:
            raise Http404('Versão não encontrada.')
        versao_arquivo = versao_str_param
    else:
        pda = PlanoDadosAbertos.objects.order_by('-vigencia_inicio', '-id').first()
        if not pda:
            raise Http404('Nenhum Plano de Dados Abertos cadastrado.')
        versao_obj = VersaoPDA.objects.filter(pda=pda).order_by('-major', '-minor', '-patch').first()
        versao_arquivo = pda.versao_atual

    documento_style, documento_html = ler_documento_html(pda, versao_arquivo) if versao_arquivo else (None, None)

    return render(
        request,
        'dadosabertos/documento_publico_pda.html',
        {
            'pda': pda,
            'versao': versao_obj,
            'versao_str': versao_arquivo,
            'documento_style': documento_style,
            'documento_html': documento_html,
            'pdf_url': url_arquivo(pda, versao_arquivo, 'pdf'),
        },
    )
