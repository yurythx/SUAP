from collections import OrderedDict
from datetime import date

import pandas as pd
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Prefetch, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views.decorators.csrf import csrf_exempt

from djtools.templatetags.filters import format_
from djtools.utils import httprr, rtr
from plan_v2.forms import (
    AcaoPAForm,
    AcaoSistemicoForm,
    AlterarIndicadorPlanoAcaoForm,
    AssociarAcaoPDIForm,
    AssociarAcaoPlanoAcaoForm,
    AssociarMacroProcessoPDIForm,
    AtividadeForm,
    ImportarObjetivosPlanoAcaoForm,
    IndicadorForm,
    MetaForm,
    NaturezaDespesaPAForm,
    ObjetivoEstrategicoPDIForm,
    OrigemRecursoForm,
    PlanoAcaoFiltroForm,
    RelatorioDetalhamentoForm,
    SolicitacaoForm,
    SolicitacaoParecerForm,
    UnidadeAdministrativaForm,
    alterar_indicador_ua_form_factory,
    alterar_origem_recurso_ua_form_factory,
)
from plan_v2.models import (
    PDI,
    Acao,
    AcaoPA,
    Atividade,
    Dimensao,
    Indicador,
    IndicadorPA,
    IndicadorPAUnidadeAdministrativa,
    Macroprocesso,
    Meta,
    MetaPA,
    NaturezaDespesaPA,
    ObjetivoEstrategico,
    OrigemRecurso,
    OrigemRecursoUA,
    PDIAcao,
    PDIMacroprocesso,
    PlanoAcao,
    Solicitacao,
    UnidadeAdministrativa,
)
from plan_v2.templatetags.plan_v2_filters import status_validacao
from plan_v2.utils import get_setor_unidade_administrativa, get_setor_unidade_administrativa_equivalente, get_setores_participantes

# Views PDI ------------------------------------------------------------------------------------------------------------


@rtr()
@login_required()
def pdi_view(request, pdi_pk):
    pdi = get_object_or_404(PDI, pk=pdi_pk)

    title = f'PDI - {pdi.ano_inicial} a {pdi.ano_final}'

    ano_atual = date.today().year

    pode_adicionar_objetivo_estrategico = request.user.has_group_cached('Administrador de Planejamento Institucional')
    pode_editar_meta = request.user.has_group_cached(
        'Coordenador de Planejamento Institucional Sistêmico, Administrador de Planejamento Institucional'
    )
    pode_acessar_indicadores = request.user.has_group_cached(
        'Coordenador de Planejamento Institucional Sistêmico, Administrador de Planejamento Institucional'
    )

    # Montagem das unidades administrativas
    uas = UnidadeAdministrativa.objects.select_related().filter(pdi=pdi).order_by('tipo', 'setor_equivalente__sigla')

    # Montagem dos macroprocessos
    macroprocessos_pdi = PDIMacroprocesso.objects.select_related().filter(pdi=pdi)
    ids_dim = set(macroprocessos_pdi.values_list('macroprocesso__dimensao', flat=True))

    query_dados = (
        Dimensao.objects.filter(id__in=ids_dim)
        .prefetch_related(
            Prefetch(
                'macroprocesso_set',
                queryset=Macroprocesso.objects.all().prefetch_related(
                    Prefetch(
                        'pdimacroprocesso_set',
                        queryset=PDIMacroprocesso.objects.filter(pdi=pdi)
                        .prefetch_related(
                            Prefetch(
                                'objetivoestrategico_set',
                                queryset=ObjetivoEstrategico.objects.all()
                                .prefetch_related(
                                    Prefetch(
                                        'meta_set', queryset=Meta.objects.all().select_related('responsavel').order_by('codigo', 'responsavel__sigla')
                                    )
                                )
                                .order_by('codigo'),
                            )
                        )
                        .order_by('codigo'),
                    )
                ),
            )
        )
        .order_by('codigo')
    )

    # Montagem das ações
    acoes = PDIAcao.objects.select_related().filter(pdi=pdi).order_by('acao__macroprocesso__nome', 'acao__detalhamento')

    solicitacoes = Solicitacao.objects.all().order_by('tipo', 'parecer')

    pdi_atual = PDI.objects.latest('id')
    if pdi_atual == pdi:
        pode_associar_acoes = True

    return locals()


@rtr()
@login_required()
def pdi_unidadeadministrativa_add_change(request, pdi_pk, ua_pk=None):
    pdi = get_object_or_404(PDI, pk=pdi_pk)
    ua = None

    title = '{} Unidade Administrativa'.format(ua_pk and 'Editar' or 'Adicionar')

    if ua_pk:
        ua = get_object_or_404(UnidadeAdministrativa, pk=ua_pk)

    form = UnidadeAdministrativaForm(request.POST or None, instance=ua, pdi=pdi)

    if form.is_valid():
        form.save()
        return httprr('..', 'Unidade administrativa salva.')

    return locals()


@rtr()
@login_required()
def pdi_unidadeadministrativa_delete(request, pdi_pk, ua_pk):
    get_object_or_404(PDI, pk=pdi_pk)
    ua = get_object_or_404(UnidadeAdministrativa, pk=ua_pk)

    if not request.user.has_perm('plan_v2.delete_unidadeadministrativa'):
        return httprr('..', 'Operação não permitida.', tag='error')

    indicadores = IndicadorPAUnidadeAdministrativa.objects.filter(unidade_administrativa=ua).exists()
    origens = OrigemRecursoUA.objects.filter(unidade_administrativa=ua).exists()
    acoes = AcaoPA.objects.filter(unidade_administrativa=ua).exists()

    if indicadores or origens or acoes:
        return httprr('..', 'Operação não permitida.', tag='error')

    ua.delete()

    return httprr('..', 'Unidade administrativa foi excluída.')


@rtr()
@login_required()
def pdi_macroprocessos_associar(request, pdi_pk):
    pdi = get_object_or_404(PDI, pk=pdi_pk)

    title = f'PDI - {pdi.ano_inicial} a {pdi.ano_final}'

    form = AssociarMacroProcessoPDIForm(request.POST or None, pdi=pdi)
    if form.is_valid():
        form.save()
        return httprr('..', 'Operação realizada.')

    return locals()


@rtr()
@login_required()
def pdi_objetivo_add_change(request, pdi_pk, objetivo_pk=None):
    title = '{} objetivo estratégico'.format(objetivo_pk and 'Editar' or 'Adicionar')

    pdi = get_object_or_404(PDI, pk=pdi_pk)
    objetivo = None

    if objetivo_pk:
        objetivo = get_object_or_404(ObjetivoEstrategico, pk=objetivo_pk)

    form = ObjetivoEstrategicoPDIForm(request.POST or None, instance=objetivo, pdi=pdi)

    if form.is_valid():
        form.save()
        return httprr('..', 'Objetivo estratégico salvo.')

    return locals()


@rtr()
@login_required()
def pdi_meta_add_change(request, pdi_pk, objetivo_pk, meta_pk=None):
    title = '{} meta'.format(meta_pk and 'Editar' or 'Adicionar')

    pdi = get_object_or_404(PDI, pk=pdi_pk)
    objetivo = get_object_or_404(ObjetivoEstrategico, pk=objetivo_pk)
    meta = None

    if meta_pk:
        meta = get_object_or_404(Meta, pk=meta_pk)

    form = MetaForm(request.POST or None, instance=meta, objetivo_estrategico=objetivo)

    if form.is_valid():
        form.save()
        return httprr('..', 'Meta salva.')

    return locals()


@rtr(template='pdi_indicadores.html')
@login_required()
def pdi_meta_indicadores(request, pdi_pk, meta_pk):
    pdi = get_object_or_404(PDI, pk=pdi_pk)
    meta = get_object_or_404(Meta, pk=meta_pk)
    objetivo = meta.objetivo_estrategico
    macroprocesso = objetivo.pdi_macroprocesso

    title = f'PDI - {pdi.ano_inicial} a {pdi.ano_final}'

    indicadores = Indicador.objects.filter(meta=meta)

    return locals()


@rtr()
@login_required()
def pdi_meta_indicador_add_change(request, pdi_pk, meta_pk, indicador_pk=None):
    pdi = get_object_or_404(PDI, pk=pdi_pk)
    meta = get_object_or_404(Meta, pk=meta_pk)
    indicador = None

    title = '{} Indicador'.format(indicador_pk and 'Editar' or 'Adicionar')

    if indicador_pk:
        indicador = get_object_or_404(Indicador, pk=indicador_pk)

    form = IndicadorForm(request.POST or None, instance=indicador, meta=meta)

    if form.is_valid():
        form.save()
        return httprr('..', 'Indicador salvo.')

    return locals()


@rtr()
@login_required()
def planoacao_acao_associar(request, pdi_pk):
    pdi = get_object_or_404(PDI, pk=pdi_pk)
    planoacao = PlanoAcao.objects.latest('id')

    title = f'Plano Ação - {planoacao}'

    form = AssociarAcaoPlanoAcaoForm(request.POST or None, pdi=pdi)

    if form.is_valid():
        form.save()
        return httprr('..', 'Ações associadas com sucesso.')

    return locals()


@rtr()
@login_required()
def pdi_acao_associar(request, pdi_pk):
    pdi = get_object_or_404(PDI, pk=pdi_pk)

    title = f'PDI - {pdi.ano_inicial} a {pdi.ano_final}'

    form = AssociarAcaoPDIForm(request.POST or None, pdi=pdi)

    if form.is_valid():
        form.save()
        return httprr('..', 'Ações associados com sucesso.')

    return locals()


@rtr()
@login_required()
def pdi_solicitacao_parecer(request, pdi_pk, solicitacao_pk):
    pdi = get_object_or_404(PDI, pk=pdi_pk)
    solicitacao = get_object_or_404(Solicitacao, pk=solicitacao_pk)

    if solicitacao.parecer != Solicitacao.PARECER_ESPERA:
        return httprr('..', f'Só é possível essa operação para solicitações "{Solicitacao.PARECER_ESPERA}".')

    title = 'PDI - Parecer'

    form = SolicitacaoParecerForm(request.POST or None, instance=solicitacao)

    if form.is_valid():
        form.save()
        return httprr('..', 'O parecer foi salvo.')

    return locals()


# Views Plano Ação - Sistêmico -----------------------------------------------------------------------------------------
@rtr()
@login_required()
def planoacao_sistemico_view(request, plano_acao_pk):
    plano_acao = get_object_or_404(PlanoAcao, pk=plano_acao_pk)
    unidade_adm_usuario = get_setor_unidade_administrativa(request.user)

    if not request.user.has_group_cached('Administrador de Planejamento Institucional', 'Auditor'):
        setores_usuario = get_setores_participantes(unidade_adm_usuario)
    if not request.user.has_group_cached('Administrador de Planejamento Institucional, Coordenador de Planejamento Institucional Sistêmico, Auditor'):
        return httprr('/admin/plan_v2/planoacao/', 'Você não tem permissão', tag='error')

    if not request.user.has_perm('plan_v2.pode_detalhar_planoacao'):
        return httprr('/admin/plan_v2/planoacao/', 'Você não tem permissão de detalhar o plano de ação', tag='error')

    title = f'Plano Ação {plano_acao.ano_base} Sistêmico'

    # Busca a dimensão do usuário para filtrar os dados
    if request.user.has_group_cached('Administrador de Planejamento Institucional', 'Auditor'):
        dimensoes_usuario = Dimensao.objects.all()
    else:
        dimensoes_usuario = Dimensao.objects.filter(setor_sistemico__in=setores_usuario)

    # Monta aba do objetivo estratégico
    query_filter = MetaPA.objects.select_related().filter(plano_acao=plano_acao)
    if not request.user.has_perm('plan_v2.pode_ver_todo_planoacao'):
        query_filter = query_filter.filter(meta__objetivo_estrategico__pdi_macroprocesso__macroprocesso__dimensao__in=dimensoes_usuario)
    query_filter = query_filter.distinct().order_by('meta__codigo_dimensao', 'meta__codigo_macroprocesso', 'meta__codigo_objetivo', 'meta__codigo')

    dimensoes = OrderedDict()

    dimensao = None
    macroprocesso = None
    objetivo_estrategico = None
    meta = None

    objetivos_lst = []
    metas_lst = []
    macroprocessos_lst = []

    adicionar_ultimo = False
    for meta_pa in query_filter:
        if not adicionar_ultimo:
            adicionar_ultimo = True
            dimensao = meta_pa.meta.objetivo_estrategico.pdi_macroprocesso.macroprocesso.dimensao
            macroprocesso = meta_pa.meta.objetivo_estrategico.pdi_macroprocesso
            objetivo_estrategico = meta_pa.meta.objetivo_estrategico

        if meta_pa.meta.objetivo_estrategico != objetivo_estrategico:
            objetivos_lst.append({'id': objetivo_estrategico.id, 'objetivo': objetivo_estrategico, 'metas': metas_lst})
            metas_lst = []
            objetivo_estrategico = meta_pa.meta.objetivo_estrategico

        if meta_pa.meta.objetivo_estrategico.pdi_macroprocesso != macroprocesso:
            macroprocessos_lst.append({'id': macroprocesso.id, 'nome': macroprocesso, 'objetivos': objetivos_lst})
            objetivos_lst = []
            metas_lst = []
            # Atualiza os dados das listas de objetivos de metas
            objetivo_estrategico = meta_pa.meta.objetivo_estrategico
            macroprocesso = meta_pa.meta.objetivo_estrategico.pdi_macroprocesso

        if meta_pa.meta.objetivo_estrategico.pdi_macroprocesso.macroprocesso.dimensao != dimensao:
            dimensoes[dimensao] = {'id': dimensao.id, 'macroprocessos': macroprocessos_lst}

            macroprocessos_lst = []
            objetivos_lst = []
            metas_lst = []
            # Atualiza os dados das listas de objetivos de metas
            dimensao = meta_pa.meta.objetivo_estrategico.pdi_macroprocesso.macroprocesso.dimensao
            macroprocesso = meta_pa.meta.objetivo_estrategico.pdi_macroprocesso

        metas_lst.append({'id': meta_pa.id, 'titulo': meta_pa.meta})

    if adicionar_ultimo:
        objetivos_lst.append({'id': objetivo_estrategico.id, 'objetivo': objetivo_estrategico, 'metas': metas_lst})
        macroprocessos_lst.append({'id': macroprocesso.id, 'nome': macroprocesso, 'objetivos': objetivos_lst})
        dimensoes[dimensao] = {'id': dimensao.id, 'macroprocessos': macroprocessos_lst}

    # Origem de recursos
    origens_recurso = OrigemRecurso.objects.select_related().filter(plano_acao=plano_acao)
    if not request.user.has_group_cached('Administrador de Planejamento Institucional'):
        origens_recurso = origens_recurso.filter(visivel_campus=True)

    if not request.user.has_perm('plan_v2.pode_ver_todo_planoacao'):
        origens_recurso = origens_recurso.filter(dimensao__in=dimensoes_usuario)

    origens_recurso = origens_recurso.order_by('dimensao__nome')

    # Natureza de Despesa
    naturezas_despesa = NaturezaDespesaPA.objects.filter(plano_acao=plano_acao)

    # Permissões para montagem das telas
    origem_pode_incluir = OrigemRecurso.pode_incluir(usuario=request.user, plano_acao=plano_acao)
    origem_pode_alterar = OrigemRecurso.pode_alterar(usuario=request.user, plano_acao=plano_acao)
    origem_pode_excluir = OrigemRecurso.pode_excluir(usuario=request.user, plano_acao=plano_acao)

    # Montar queryset para tab validação
    unidades_adm = (
        UnidadeAdministrativa.objects.filter(acaopa__meta_pa__plano_acao=plano_acao).distinct().order_by('tipo', 'setor_equivalente__sigla')
    )

    validacoes = []
    for unidade in unidades_adm:
        validacoes.append(
            {
                'id': unidade.id,
                'nome': unidade.setor_equivalente.sigla,
                'total': AcaoPA.objects.filter(
                    unidade_administrativa=unidade,
                    meta_pa__plano_acao=plano_acao,
                    meta_pa__meta__objetivo_estrategico__pdi_macroprocesso__macroprocesso__dimensao__in=dimensoes_usuario,
                ).count(),
                'validadas': AcaoPA.objects.filter(
                    unidade_administrativa=unidade,
                    meta_pa__plano_acao=plano_acao,
                    validacao=Acao.SITUACAO_DEFERIDA,
                    meta_pa__meta__objetivo_estrategico__pdi_macroprocesso__macroprocesso__dimensao__in=dimensoes_usuario,
                ).count(),
                'invalidadas': AcaoPA.objects.filter(
                    unidade_administrativa=unidade,
                    meta_pa__plano_acao=plano_acao,
                    validacao=Acao.SITUACAO_INDEFERIDA,
                    meta_pa__meta__objetivo_estrategico__pdi_macroprocesso__macroprocesso__dimensao__in=dimensoes_usuario,
                ).count(),
                'pendentes': AcaoPA.objects.filter(
                    unidade_administrativa=unidade,
                    meta_pa__plano_acao=plano_acao,
                    validacao__in=(Acao.SITUACAO_ANALISADA, Acao.SITUACAO_NAO_ANALISADA),
                    meta_pa__meta__objetivo_estrategico__pdi_macroprocesso__macroprocesso__dimensao__in=dimensoes_usuario,
                ).count(),
            }
        )

    solicitacoes = Solicitacao.objects.filter(unidade_administrativa__in=unidade_adm_usuario).order_by('tipo', 'parecer')

    return locals()


@rtr()
@login_required()
def pas_origemrecurso_add_change(request, plano_acao_pk, origem_pk=None):
    plano_acao = get_object_or_404(PlanoAcao, pk=plano_acao_pk)
    origem_recurso = None

    title = '{} Origem de Recurso'.format(origem_pk and 'Editar' or 'Adicionar')

    if origem_pk:
        origem_recurso = get_object_or_404(OrigemRecurso, pk=origem_pk)

        if not OrigemRecurso.pode_alterar(usuario=request.user, plano_acao=plano_acao):
            return httprr('..', 'Operação não permitida.', tag='error')
    else:
        if not OrigemRecurso.pode_incluir(usuario=request.user, plano_acao=plano_acao):
            return httprr('..', 'Operação não permitida.', tag='error')

    form = OrigemRecursoForm(request.POST or None, instance=origem_recurso, plano_acao=plano_acao)

    if form.is_valid():
        form.save()
        return httprr('..', 'Origem de recurso salva.')

    return locals()


@rtr()
@login_required()
@transaction.atomic
def pas_origemrecurso_delete(request, plano_acao_pk, origem_pk=None):
    plano_acao = get_object_or_404(PlanoAcao, pk=plano_acao_pk)
    origem_recurso = get_object_or_404(OrigemRecurso, pk=origem_pk)

    if not OrigemRecurso.pode_excluir(usuario=request.user, plano_acao=plano_acao, origem_recurso_pk=origem_pk):
        return httprr('..', 'Operação não permitida.', tag='error')

    OrigemRecursoUA.objects.filter(origem_recurso=origem_recurso).delete()
    origem_recurso.delete()

    return httprr('..', 'Origem de recurso foi excluída.')


@rtr()
@login_required()
def pas_alterar_origem_recurso_ua(request, plano_acao_pk, origem_recurso_pk):
    plano_acao = get_object_or_404(PlanoAcao, pk=plano_acao_pk)
    origem_recurso = get_object_or_404(OrigemRecurso, pk=origem_recurso_pk)

    if not request.user.has_perm('plan_v2.pode_detalhar_origemrecursoua'):
        return httprr('..', 'Você não tem acesso a esse procedimento', 'error')

    if not OrigemRecursoUA.pode_alterar(usuario=request.user, plano_acao=plano_acao):
        return httprr('..', 'Operação não permitida.', tag='error')

    title = 'Origens de Recurso das Unidades Administrativas'

    Klass = alterar_origem_recurso_ua_form_factory(origem_recurso)

    form = Klass(request.POST or None)

    if form.is_valid():
        form.save()
        return httprr('..', 'Alterações foram realizadas.')

    return locals()


@rtr()
@login_required()
def pas_natureza_despesa_add_delete(request, plano_acao_pk, natureza_despesa_pk=None):
    plano_acao = get_object_or_404(PlanoAcao, pk=plano_acao_pk)
    natureza_despeza = None

    url_retorno = '{}?tab=natureza_despesa'.format(reverse_lazy('planoacao_sistemico_view', kwargs={'plano_acao_pk': plano_acao_pk}))

    if not request.user.has_perm('plan_v2.pode_vincular_naturezadespesapa'):
        return httprr(url_retorno, 'Você não tem acesso a esse procedimento.', 'error')

    title = '{} Natureza de Despesa'.format(natureza_despesa_pk and 'Desvincular' or 'Vincular')

    form = None

    # Se tiver id é uma exclusão, caso contrário é uma vinculação
    if natureza_despesa_pk:
        natureza_despeza = NaturezaDespesaPA.objects.filter(id=natureza_despesa_pk)

        if Atividade.objects.filter(natureza_despesa=natureza_despeza).exists():
            return httprr(url_retorno, 'A Natureza de Despesa está vinculada a atividade(s).')

        natureza_despeza.delete()
        return httprr(url_retorno, 'A Natureza de Despesa foi desvinculada.')
    else:
        form = NaturezaDespesaPAForm(request.POST or None, plano_acao=plano_acao)

        if form.is_valid():
            form.save()
            return httprr('..', 'A Natureza de Despesa foi vinculada.')

    return locals()


@rtr()
@login_required()
def pas_importar_objetivos(request, plano_acao_pk):
    plano_acao = get_object_or_404(PlanoAcao, pk=plano_acao_pk)

    title = f'Plano de Ação - {plano_acao.ano_base}'

    form = ImportarObjetivosPlanoAcaoForm(request.POST or None, plano_acao=plano_acao)

    if form.is_valid():
        form.save()
        return httprr('..', 'Ações associadas com sucesso.')

    return locals()


@rtr(template='planoacao_sistemico_indicadores.html')
@login_required()
def pas_indicadores_detalhar(request, plano_acao_pk, meta_pk):
    plano_acao = get_object_or_404(PlanoAcao, pk=plano_acao_pk)
    meta_pa = get_object_or_404(MetaPA, pk=meta_pk)
    eh_auditor = request.user.has_perm('rh.auditor')
    objetivo = meta_pa.meta.objetivo_estrategico
    indicadores_pa = IndicadorPA.objects.filter(meta_pa=meta_pa)

    acoes_pk = AcaoPA.objects.filter(meta_pa__plano_acao=plano_acao, meta_pa=meta_pa).values_list('acao__acao__id', flat=True)
    acoes_indicadas = []

    pode_vincular_acao = Acao.pode_vincular(usuario=request.user, plano_acao=plano_acao)

    pk = None
    for acao in Acao.objects.filter(pk__in=acoes_pk).order_by('detalhamento'):
        unidades = []
        # acao__acao__acao => acao (pdiacao) __acao (acao)
        acoes = AcaoPA.objects.filter(meta_pa__plano_acao=plano_acao, meta_pa=meta_pa, acao__acao=acao)
        acoes = acoes.order_by('unidade_administrativa__tipo', 'unidade_administrativa__setor_equivalente__sigla')
        for pa in acoes:
            unidades.append(pa.unidade_administrativa.setor_equivalente.sigla)
        acoes_indicadas.append({'id': acao.pk, 'detalhamento': pa.acao, 'campi': ', '.join(unidades)})

    title = f'Plano de Ação - {plano_acao.ano_base}'

    return locals()


@rtr()
@login_required()
def pas_indicadores_alterar(request, plano_acao_pk, indicador_pa_pk):
    plano_acao = get_object_or_404(PlanoAcao, pk=plano_acao_pk)
    indicador_pa = get_object_or_404(IndicadorPA, pk=indicador_pa_pk)

    title = f'Editar Indicador do Plano de Ação - {plano_acao.ano_base}'

    form = AlterarIndicadorPlanoAcaoForm(request.POST or None, instance=indicador_pa)

    if form.is_valid():
        form.save()
        return httprr('..', 'Ações associadas com sucesso.')

    return locals()


@rtr()
@login_required()
def pas_indicadores_ua__alterar(request, plano_acao_pk, indicador_pa_pk):
    plano_acao = get_object_or_404(PlanoAcao, pk=plano_acao_pk)
    indicador_pa = get_object_or_404(IndicadorPA, pk=indicador_pa_pk)

    title = 'Indicadores das Unidades Administrativas'

    if not IndicadorPAUnidadeAdministrativa.pode_alterar(usuario=request.user, plano_acao=plano_acao):
        return httprr('..', 'Operação não permitida.', tag='error')

    Klass = alterar_indicador_ua_form_factory(indicador_pa)

    form = Klass(request.POST or None)

    if form.is_valid():
        form.save()
        return httprr('..', 'Alterações foram realizadas.')

    return locals()


@rtr()
@login_required()
@transaction.atomic
def pas_indicadores_acao_vincular_desvincular(request, plano_acao_pk, meta_pk, acao_pk=None):
    plano_acao = get_object_or_404(PlanoAcao, pk=plano_acao_pk)
    meta_pa = get_object_or_404(MetaPA, pk=meta_pk)
    acao = None

    title = '{} Ação'.format(acao_pk and 'Vincular/Desvincular' or 'Vincular')

    if not AcaoPA.pode_incluir(usuario=request.user, plano_acao=plano_acao):
        return httprr('..', 'Operação não permitida.', tag='error')
    if acao_pk:
        acao = get_object_or_404(PDIAcao, acao__pk=acao_pk)

    form = AcaoSistemicoForm(request.POST or None, plano_acao=plano_acao, meta_pa=meta_pa, acao=acao)

    if form.is_valid():
        for unidade in form.cleaned_data['unidades_administrativa']:
            pdiacao = PDIAcao.objects.get(pdi=plano_acao.pdi, acao=form.cleaned_data['acao'].acao, ativa_planoacao=True)
            if not AcaoPA.objects.filter(meta_pa=meta_pa, acao__acao=pdiacao.acao, unidade_administrativa=unidade).exists():
                AcaoPA.objects.create(
                    meta_pa=meta_pa,
                    unidade_administrativa=unidade,
                    acao=PDIAcao.objects.get(pdi=plano_acao.pdi, acao=form.cleaned_data['acao'].acao),
                    cadastro_sistemico=True,
                )

        for acao_excluir in AcaoPA.objects.filter(meta_pa=meta_pa, acao=acao).exclude(
            unidade_administrativa__in=form.cleaned_data['unidades_administrativa']
        ):
            if not Atividade.objects.filter(acao_pa=acao_excluir).exists():
                acao_excluir.delete()

        return httprr('..', 'Operação realizada.')

    return locals()


@rtr()
@login_required()
def pas_unidade_validacao(request, plano_acao_pk, unidade_pk):
    plano_acao = get_object_or_404(PlanoAcao, pk=plano_acao_pk)
    unidade_adm = get_object_or_404(UnidadeAdministrativa, pk=unidade_pk)
    unidade_adm_usuario = get_setor_unidade_administrativa(request.user)

    setores_usuario = get_setores_participantes(unidade_adm_usuario)

    # Busca a dimensão do usuário para filtrar os dados
    if request.user.has_group_cached('Administrador de Planejamento Institucional'):
        dimensoes_usuario = Dimensao.objects.all()
    else:
        dimensoes_usuario = Dimensao.objects.filter(setor_sistemico__in=setores_usuario)

    title = 'Validação do plano de ação'

    # Monta tabela com as ações da dimensão
    acoes_pa = (
        AcaoPA.objects.select_related()
        .filter(
            meta_pa__meta__objetivo_estrategico__pdi_macroprocesso__macroprocesso__dimensao__in=dimensoes_usuario,
            meta_pa__plano_acao=plano_acao,
            unidade_administrativa=unidade_adm,
        )
        .annotate(num_atividades=Count('atividade'))
        .distinct()
        .order_by('acao__codigo_dimensao', 'acao__codigo_macroprocesso', 'acao__codigo')
    )

    metas_pa = []
    meta_pa = None
    acoes_lst = None

    for acao_pa in acoes_pa:
        if meta_pa is None:
            meta_pa = acao_pa.meta_pa
            acoes_lst = []

        if meta_pa != acao_pa.meta_pa:
            metas_pa.append({'id': meta_pa.id, 'titulo': meta_pa.meta, 'acoes': acoes_lst})
            meta_pa = acao_pa.meta_pa

            acoes_lst = []
        acoes_lst.append(
            {
                'id': acao_pa.id,
                'titulo': acao_pa.acao,
                'validacao': acao_pa.validacao,
                'unidade': unidade_adm.pk,
                'num_atividades': acao_pa.num_atividades,
            }
        )
    if acoes_lst:
        metas_pa.append({'id': meta_pa.id, 'titulo': meta_pa.meta, 'acoes': acoes_lst})

    # Monta tabela com as ações vinculadas
    atividades_vinculadas = Atividade.objects.filter(
        acao_pa__meta_pa__plano_acao=plano_acao,
        acao_pa__unidade_administrativa=unidade_adm,
        acao_pa_vinculadora__meta_pa__meta__objetivo_estrategico__pdi_macroprocesso__macroprocesso__dimensao__in=dimensoes_usuario,
    ).values_list('acao_pa_vinculadora__id', flat=True)
    acoes_pa = (
        AcaoPA.objects.select_related()
        .filter(pk__in=atividades_vinculadas)
        .distinct()
        .order_by('acao__codigo_dimensao', 'acao__codigo_macroprocesso', 'acao__codigo')
    )

    metas_pa_vinculadas = []
    meta_pa = None
    acoes_lst = None

    for acao_pa in acoes_pa:
        if meta_pa is None:
            meta_pa = acao_pa.meta_pa
            acoes_lst = []

        if meta_pa != acao_pa.meta_pa:
            metas_pa_vinculadas.append({'id': meta_pa.id, 'titulo': meta_pa.meta, 'acoes': acoes_lst})
            meta_pa = acao_pa.meta_pa

            acoes_lst = []
        acoes_lst.append(
            {
                'id': acao_pa.id,
                'titulo': acao_pa.acao,
                'validacao': acao_pa.validacao,
                'unidade': unidade_adm.pk,
                'num_atividades': acao_pa.get_atividades_vincudadas().count(),
            }
        )
    if acoes_lst:
        metas_pa_vinculadas.append({'id': meta_pa.id, 'titulo': meta_pa.meta, 'acoes': acoes_lst})

    # Monta tabela com as ações por origem de recursos
    atividades_vinculadas = (
        Atividade.objects.filter(
            acao_pa__meta_pa__plano_acao=plano_acao, acao_pa__unidade_administrativa=unidade_adm, origem_recurso__dimensao__in=dimensoes_usuario
        )
        .exclude(
            Q(acao_pa__meta_pa__meta__objetivo_estrategico__pdi_macroprocesso__macroprocesso__dimensao__in=dimensoes_usuario)
            | Q(acao_pa_vinculadora__meta_pa__meta__objetivo_estrategico__pdi_macroprocesso__macroprocesso__dimensao__in=dimensoes_usuario)
        )
        .values_list('acao_pa__id', flat=True)
    )

    acoes_pa = (
        AcaoPA.objects.select_related()
        .filter(pk__in=atividades_vinculadas)
        .annotate(num_atividades=Count('atividade'))
        .distinct()
        .order_by('acao__codigo_dimensao', 'acao__codigo_macroprocesso', 'acao__codigo')
    )

    metas_pa_origem = []
    meta_pa = None
    acoes_lst = None

    for acao_pa in acoes_pa:
        if meta_pa is None:
            meta_pa = acao_pa.meta_pa
            acoes_lst = []

        if meta_pa != acao_pa.meta_pa:
            metas_pa_origem.append({'id': meta_pa.id, 'titulo': meta_pa.meta, 'acoes': acoes_lst})
            meta_pa = acao_pa.meta_pa

            acoes_lst = []
        acoes_lst.append(
            {
                'id': acao_pa.id,
                'titulo': acao_pa.acao,
                'validacao': acao_pa.validacao,
                'unidade': unidade_adm.pk,
                'num_atividades': acao_pa.num_atividades,
            }
        )
    if meta_pa:
        metas_pa_origem.append({'id': meta_pa.id, 'titulo': meta_pa.meta, 'acoes': acoes_lst})

    return locals()


@login_required()
@rtr(template='planoacao_unidade_acao_validar.html')
def pas_acao_validacao(request, plano_acao_pk, unidade_pk, acao_pk, tipo):
    plano_acao = get_object_or_404(PlanoAcao, pk=plano_acao_pk)
    unidade_adm = get_object_or_404(UnidadeAdministrativa, pk=unidade_pk)
    unidade_adm_usuario = get_setor_unidade_administrativa(request.user)
    acao_pa = get_object_or_404(AcaoPA, pk=acao_pk)
    dimensoes_usuario = None

    atividades = None
    origem_vinculadora = False
    outras_acoes = False

    setores_usuario = get_setores_participantes(unidade_adm_usuario)

    tab = '?tab=acoes'

    # Busca a dimensão do usuário para filtrar os dados
    if request.user.has_group_cached('Administrador de Planejamento Institucional'):
        dimensoes_usuario = Dimensao.objects.all()
    else:
        dimensoes_usuario = Dimensao.objects.filter(setor_sistemico__in=setores_usuario)

    title = 'Avaliação da Ação'

    # Verifica se a acao_pa é da dimensão do usuário
    if tipo == 'propria' and acao_pa.dimensao in dimensoes_usuario:
        atividades = acao_pa.atividade_set.all()
    elif tipo == 'vinculada' and acao_pa.acao.acao.eh_vinculadora:
        title = 'Avaliação da Ação vinculadora'
        tab = '?tab=acoes_vinculadas'
        atividades = acao_pa.get_atividades_vincudadas()
        origem_vinculadora = True
    else:
        title = 'Avaliação de Outras Ações'
        tab = '?tab=outras_acoes'
        atividades = acao_pa.get_atividades_origem_recurso()
        outras_acoes = True

    SITUACAO_DEFERIDA = Acao.SITUACAO_DEFERIDA
    SITUACAO_INDEFERIDA = Acao.SITUACAO_INDEFERIDA
    SITUACAO_ANALISADA = Acao.SITUACAO_ANALISADA

    pode_validar = plano_acao.em_periodo_validacao

    return locals()


@csrf_exempt
@login_required()
def pas_atividade_validar(request):
    atividade = Atividade.objects.filter(pk=request.POST['id'])

    if not atividade.exists() or not atividade[0].acao_pa.meta_pa.plano_acao.em_periodo_validacao:
        raise PermissionDenied('Operação inválida.')

    unidade_adm = get_setor_unidade_administrativa(request.user)
    dimensoes_usuario = None

    setores_usuario = get_setores_participantes(unidade_adm)

    # Busca a dimensão do usuário para filtrar os dados
    if request.user.has_group_cached('Administrador de Planejamento Institucional'):
        dimensoes_usuario = Dimensao.objects.all()
    else:
        dimensoes_usuario = Dimensao.objects.filter(setor_sistemico__in=setores_usuario)

    eh_vinculadora = False
    atividade = atividade[0]
    validacao = ''

    if atividade.acao_pa.id == int(request.POST['acao']) and atividade.acao_pa.dimensao in dimensoes_usuario:
        # Não é uma atividade com ação vinculada
        if request.POST['status'] == 'deferida':
            atividade.validacao = Acao.SITUACAO_DEFERIDA
        elif request.POST['status'] == 'indeferida':
            atividade.validacao = Acao.SITUACAO_INDEFERIDA
        elif request.POST['status'] == 'analise':
            atividade.validacao = Acao.SITUACAO_ANALISADA
        validacao = atividade.validacao
    else:
        eh_vinculadora = True
        # É uma atividade com ação vinculada
        if request.POST['status'] == 'deferida':
            atividade.validacao_vinculadora = Acao.SITUACAO_DEFERIDA
        elif request.POST['status'] == 'indeferida':
            atividade.validacao_vinculadora = Acao.SITUACAO_INDEFERIDA
        elif request.POST['status'] == 'analise':
            atividade.validacao_vinculadora = Acao.SITUACAO_ANALISADA
        validacao = atividade.validacao_vinculadora
    atividade.save()

    acao_pa = atividade.acao_pa
    span = ''

    span = f'#status_{atividade.id}'

    atividade_nao_validada = 0
    atividade_validada = 0
    atividade_invalidada = 0
    atividades_em_analise = 0

    for atividade in Atividade.objects.filter(acao_pa=acao_pa):
        if eh_vinculadora:
            if atividade.validacao == atividade.validacao_vinculadora:
                if atividade.validacao == Acao.SITUACAO_DEFERIDA:
                    atividade_validada += 1
                elif atividade.validacao == Acao.SITUACAO_INDEFERIDA:
                    atividade_invalidada += 1
                elif atividade.validacao == Acao.SITUACAO_ANALISADA:
                    atividades_em_analise += 1
                else:
                    atividade_nao_validada += 1
            elif atividade.validacao == Acao.SITUACAO_ANALISADA or atividade.validacao_vinculadora == Acao.SITUACAO_ANALISADA:
                atividades_em_analise += 1
            elif atividade.validacao == Acao.SITUACAO_DEFERIDA and atividade.validacao_vinculadora == Acao.SITUACAO_DEFERIDA:
                atividade_validada += 1
            elif (
                atividade.validacao == Acao.SITUACAO_DEFERIDA
                and (atividade.validacao_vinculadora == Acao.SITUACAO_ANALISADA or atividade.validacao_vinculadora == Acao.SITUACAO_NAO_ANALISADA)
                or atividade.validacao_vinculadora == Acao.SITUACAO_DEFERIDA
                and (atividade.validacao == Acao.SITUACAO_ANALISADA or atividade.validacao == Acao.SITUACAO_NAO_ANALISADA)
            ):
                atividades_em_analise += 1
            elif atividade.validacao == Acao.SITUACAO_NAO_ANALISADA or atividade.validacao_vinculadora == Acao.SITUACAO_NAO_ANALISADA:
                atividade_nao_validada += 1
            else:
                atividade_invalidada += 1
        else:
            if atividade.validacao == Acao.SITUACAO_DEFERIDA:
                atividade_validada += 1
            elif atividade.validacao == Acao.SITUACAO_INDEFERIDA:
                atividade_invalidada += 1
            elif atividade.validacao == Acao.SITUACAO_ANALISADA:
                atividades_em_analise += 1
            else:
                atividade_nao_validada += 1

    if atividades_em_analise > 0:
        acao_pa.validacao = Acao.SITUACAO_ANALISADA
    elif atividade_nao_validada == 0:
        if atividade_validada > 0:
            acao_pa.validacao = Acao.SITUACAO_DEFERIDA
        else:
            acao_pa.validacao = Acao.SITUACAO_INDEFERIDA
    acao_pa.save()

    return HttpResponse(f'{span}&{status_validacao(validacao)}&{validacao}')


@login_required()
@rtr(template='planoacao_sistemico_disponibilidade.html')
def pas_disponibilidade_financeira(request, plano_acao_pk):
    plano_acao = get_object_or_404(PlanoAcao, pk=plano_acao_pk)

    title = 'Disponibilidade Financeira'

    query_origem = OrigemRecursoUA.objects.select_related().filter(origem_recurso__plano_acao=plano_acao)

    if not request.user.has_group_cached('Administrador de Planejamento Institucional, Auditor'):
        unidade_adm_usuario = get_setor_unidade_administrativa(request.user)
        setores_usuario = get_setores_participantes(unidade_adm_usuario)
        dimensoes = Dimensao.objects.filter(setor_sistemico__in=setores_usuario)
        query_origem = query_origem.filter(origem_recurso__dimensao__in=dimensoes, origem_recurso__visivel_campus=True)

    query_origem = query_origem.filter(Q(valor_custeio__gt=0) | Q(valor_capital__gt=0))
    query_origem = query_origem.order_by(
        'unidade_administrativa__tipo',
        'unidade_administrativa__setor_equivalente__sigla',
        'origem_recurso__codigo',
        'origem_recurso__acao_financeira__acao__codigo_acao',
        'origem_recurso__acao_financeira__ptres',
    )

    origens_recurso = OrderedDict()

    origens_lst = None
    ua = None

    for origem in query_origem:
        if ua is None:
            ua = origem.unidade_administrativa
            origens_lst = []

        if ua != origem.unidade_administrativa:
            origens_recurso[ua.setor_equivalente.sigla] = {'id': ua.id, 'origens': origens_lst}
            ua = origem.unidade_administrativa
            origens_lst = []

        capital_comprometido = origem.valor_capital_comprometido
        custeio_comprometido = origem.valor_custeio_comprometido

        origens_lst.append(
            {
                'nome': str(origem.origem_recurso),
                'valor_capital': origem.valor_capital,
                'capital_comprometido': capital_comprometido,
                'capital_saldo': origem.valor_capital - capital_comprometido,
                'valor_custeio': origem.valor_custeio,
                'custeio_comprometido': custeio_comprometido,
                'custeio_saldo': origem.valor_custeio - custeio_comprometido,
            }
        )

    if ua:
        origens_recurso[ua.setor_equivalente.sigla] = {'id': ua.id, 'origens': origens_lst}

    return locals()


@login_required()
def pas_disponibilidade_geral_financeira(request, plano_acao_pk):
    plano_acao = get_object_or_404(PlanoAcao, pk=plano_acao_pk)

    unidades = UnidadeAdministrativa.objects.filter(pdi=plano_acao.pdi).values('id', 'setor_equivalente__sigla')
    unidades = unidades.order_by('tipo', 'setor_equivalente__sigla')

    # Build MultiIndex columns
    columns = []
    for unidade in unidades:
        sigla = unidade['setor_equivalente__sigla']
        columns.append((sigla, 'Custeio', 'Rateado'))
        columns.append((sigla, 'Custeio', 'Comprometido'))
        columns.append((sigla, 'Capital', 'Rateado'))
        columns.append((sigla, 'Capital', 'Comprometido'))

    multi_index = pd.MultiIndex.from_tuples(columns)

    origens = OrigemRecurso.objects.filter(plano_acao=plano_acao)

    if not request.user.has_group_cached('Administrador de Planejamento Institucional'):
        origens = origens.filter(visivel_campus=True)

    origens = origens.order_by('codigo', 'acao_financeira__acao__codigo_acao', 'acao_financeira__ptres')

    data = []
    index = []
    for origem in origens:
        index.append(str(origem))
        row = []
        for unidade in unidades:
            origem_ua = OrigemRecursoUA.objects.filter(origem_recurso=origem, unidade_administrativa=unidade['id'])
            if origem_ua.exists():
                origem_ua = origem_ua[0]
                row.append(format_(origem_ua.valor_custeio))
                row.append(format_(origem_ua.valor_custeio_comprometido))
                row.append(format_(origem_ua.valor_capital))
                row.append(format_(origem_ua.valor_capital_comprometido))
            else:
                row.extend(['', '', '', ''])
        data.append(row)

    df = pd.DataFrame(data, index=index, columns=multi_index)
    df.index.name = 'Origem de Recurso'

    # Create Excel file
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=DisponibilidadeGeral.xlsx'

    with pd.ExcelWriter(response, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Disponibilidade')

        # Add title and subtitle manually using openpyxl
        worksheet = writer.sheets['Disponibilidade']
        worksheet.insert_rows(1, 2)
        worksheet['A1'] = 'Relatório de Disponibilidade Financeira - Origens de Recurso'
        worksheet['A2'] = f'Plano de Ação: {plano_acao}'

    return response


@login_required()
@rtr(template='planoacao_sistemico_relatorio_pa.html')
def pas_relatorio_plano_acao(request):
    planos_acoes = PlanoAcao.objects.all().order_by('-ano_base__ano')

    if not len(planos_acoes):
        mensagem = 'Não existe plano de ação cadastrado.'
        return locals()
    if 'planoacao' in request.POST:
        planoacao = PlanoAcao.objects.get(pk=request.POST['planoacao'])
    else:
        planoacao = PlanoAcao.objects.all().order_by('-ano_base__ano')[0]

    title = f'Plano Ação {planoacao.ano_base}'
    form = PlanoAcaoFiltroForm(id_planoacao=planoacao.id)
    acoes_pa = (
        AcaoPA.objects.filter(meta_pa__plano_acao=planoacao)
        .annotate(valor=Sum('atividade__valor'))
        .order_by(
            'meta_pa__meta__codigo_dimensao',
            'meta_pa__meta__codigo_macroprocesso',
            'meta_pa__meta__codigo_objetivo',
            'meta_pa__meta__codigo',
            'acao__codigo',
        )
        .select_related()
        .distinct()
    )

    dimensao_dict = OrderedDict()
    dimensao = None
    macroprocesso = None
    objetivo = None
    meta = None
    acao = None

    macroprocesso_lst = []
    objetivo_lst = []
    meta_lst = []
    acao_lst = []
    for acao_pa in acoes_pa:
        if dimensao is None:
            dimensao = acao_pa.meta_pa.meta.objetivo_estrategico.pdi_macroprocesso.macroprocesso.dimensao
            macroprocesso = acao_pa.meta_pa.meta.objetivo_estrategico.pdi_macroprocesso
            objetivo = acao_pa.meta_pa.meta.objetivo_estrategico
            meta = acao_pa.meta_pa.meta
            acao = {'acao': acao_pa.acao, 'valor': acao_pa.valor or 0, 'atividades': []}

        if acao['acao'] != acao_pa.acao:
            acao_lst.append(acao)
            acao = {'acao': acao_pa.acao, 'valor': acao_pa.valor or 0, 'atividades': []}

        else:
            acao['valor'] += acao_pa.valor or 0

        for ativ in acao_pa.atividade_set.all():
            acao['atividades'].append(ativ)

        if meta != acao_pa.meta_pa.meta:
            meta_lst.append({'titulo': meta, 'acoes': acao_lst})
            meta = acao_pa.meta_pa.meta
            acao_lst = []

        if objetivo != acao_pa.meta_pa.meta.objetivo_estrategico:
            objetivo_lst.append({'titulo': objetivo, 'metas': meta_lst})
            objetivo = acao_pa.meta_pa.meta.objetivo_estrategico
            meta_lst = []

        if macroprocesso != acao_pa.meta_pa.meta.objetivo_estrategico.pdi_macroprocesso:
            macroprocesso_lst.append({'macroprocesso': macroprocesso, 'objetivos': objetivo_lst})
            macroprocesso = acao_pa.meta_pa.meta.objetivo_estrategico.pdi_macroprocesso
            objetivo_lst = []

        if dimensao != acao_pa.meta_pa.meta.objetivo_estrategico.pdi_macroprocesso.macroprocesso.dimensao:
            dimensao_dict[dimensao] = macroprocesso_lst
            dimensao = acao_pa.meta_pa.meta.objetivo_estrategico.pdi_macroprocesso.macroprocesso.dimensao
            macroprocesso_lst = []

    if dimensao:
        acao_lst.append(acao)
        meta_lst.append({'meta': meta, 'acoes': acao_lst})
        objetivo_lst.append({'titulo': objetivo, 'metas': meta_lst})
        macroprocesso_lst.append({'macroprocesso': macroprocesso, 'objetivos': objetivo_lst})
        dimensao_dict[dimensao] = macroprocesso_lst

    return locals()


# Views Plano Acão - Unid. Adm -----------------------------------------------------------------------------------------
@rtr()
@login_required()
def planoacao_unidade_view(request, plano_acao_pk):
    plano_acao = get_object_or_404(PlanoAcao, pk=plano_acao_pk)

    if not request.user.has_perm('plan_v2.pode_detalhar_planoacao'):
        return httprr('/admin/plan_v2/planoacao/', 'Você não tem permissão de detalhar o plano de ação', tag='error')

    title = f'Plano Ação {plano_acao.ano_base} da Unidade Administrativa'
    unidade_adm = UnidadeAdministrativa.objects.all()
    if not request.user.has_group_cached('Auditor'):
        unidade_adm = get_setor_unidade_administrativa(request.user)

    # Monta aba do objetivo estratégico
    query_filter = (
        AcaoPA.objects.filter(meta_pa__plano_acao=plano_acao, unidade_administrativa__in=unidade_adm)
        .annotate(valor=Sum('atividade__valor'))
        .order_by(
            'meta_pa__meta__objetivo_estrategico__pdi_macroprocesso__macroprocesso__dimensao__nome',
            'meta_pa__meta__objetivo_estrategico__pdi_macroprocesso__macroprocesso__nome',
            'meta_pa__meta__objetivo_estrategico__descricao',
            'meta_pa__meta__titulo',
            'acao__acao__detalhamento',
        )
        .select_related()
    )

    dimensoes = OrderedDict()
    dimensao = None

    macroprocesso = None
    meta = None
    acao = None

    macroprocesso_lst = []
    metas_lst = []
    acoes_lst = []

    adicionar_ultimo = False
    for acao_pa in query_filter:
        if not adicionar_ultimo:
            adicionar_ultimo = True
            dimensao = acao_pa.meta_pa.meta.objetivo_estrategico.pdi_macroprocesso.macroprocesso.dimensao
            macroprocesso = acao_pa.meta_pa.meta.objetivo_estrategico.pdi_macroprocesso
            meta = acao_pa.meta_pa.meta

        if acao_pa.meta_pa.meta != meta:
            metas_lst.append({'id': meta.id, 'nome': meta, 'acoes': acoes_lst})
            acoes_lst = []
            meta = acao_pa.meta_pa.meta

        if acao_pa.meta_pa.meta.objetivo_estrategico.pdi_macroprocesso != macroprocesso:
            macroprocesso_lst.append({'id': macroprocesso.id, 'nome': macroprocesso, 'metas': metas_lst})
            metas_lst = []
            acoes_lst = []
            # Atualiza os dados das listas de objetivos de metas
            macroprocesso = acao_pa.meta_pa.meta.objetivo_estrategico.pdi_macroprocesso
            meta = acao_pa.meta_pa.meta

        if acao_pa.meta_pa.meta.objetivo_estrategico.pdi_macroprocesso.macroprocesso.dimensao != dimensao:
            dimensoes[dimensao] = {'id': dimensao.id, 'macroprocessos': macroprocesso_lst}
            macroprocesso_lst = []
            metas_lst = []
            acoes_lst = []
            # Atualiza os dados das listas de objetivos de metas
            dimensao = acao_pa.meta_pa.meta.objetivo_estrategico.pdi_macroprocesso.macroprocesso.dimensao
            macroprocesso = acao_pa.meta_pa.meta.objetivo_estrategico.pdi_macroprocesso
            meta = acao_pa.meta_pa.meta

        acoes_lst.append(
            {
                'id': acao_pa.pk,
                'unidade': acao_pa.unidade_administrativa.setor_equivalente,
                'titulo': acao_pa.acao,
                'setores_responsaveis': acao_pa.setores_responsaveis.all(),
                'validacao': acao_pa.validacao,
                'data_inicial': acao_pa.data_inicial,
                'data_final': acao_pa.data_final,
            }
        )

    if adicionar_ultimo:
        metas_lst.append({'id': meta.id, 'nome': meta, 'acoes': acoes_lst})
        macroprocesso_lst.append({'id': macroprocesso.id, 'nome': macroprocesso, 'metas': metas_lst})
        dimensoes[dimensao] = {'id': dimensao.id, 'macroprocessos': macroprocesso_lst}

    # Permissões para geração das telas
    acao_pa_pode_incluir = AcaoPA.pode_incluir(request.user, plano_acao)
    acao_pa_pode_alterar = AcaoPA.pode_alterar(request.user, plano_acao)
    acao_pa_pode_incluir_atividade = AcaoPA.pode_incluir_atividade(request.user, plano_acao)
    acao_pa_pode_excluir = AcaoPA.pode_excluir(request.user, plano_acao)

    # Montagem das solicitações
    solicitacoes = Solicitacao.objects.filter(unidade_administrativa__in=unidade_adm).order_by('tipo', 'parecer')

    return locals()


@rtr()
@login_required()
def paua_acao_add_change(request, plano_acao_pk, meta_pk, acao_pa_pk=None):
    plano_acao = get_object_or_404(PlanoAcao, pk=plano_acao_pk)
    meta = get_object_or_404(Meta, pk=meta_pk)
    meta_pa = MetaPA.objects.get(plano_acao=plano_acao, meta=meta)
    unidade_adm = get_setor_unidade_administrativa_equivalente(request.user)

    acao_pa = None
    acao_add = True

    title = '{} Ação'.format(acao_pa_pk and 'Editar' or 'Adicionar')

    if acao_pa_pk:
        acao_pa = get_object_or_404(AcaoPA, pk=acao_pa_pk)
        acao_add = False
        if not AcaoPA.pode_incluir_atividade(usuario=request.user, plano_acao=plano_acao):
            return httprr('..', 'Operação não permitida.', tag='error')
    else:
        if not AcaoPA.pode_incluir(usuario=request.user, plano_acao=plano_acao):
            return httprr('..', 'Operação não permitida.', tag='error')

    form = AcaoPAForm(request.POST or None, instance=acao_pa, acao_add=acao_add, meta_pa=meta_pa, unidade_administrativa=unidade_adm)

    if form.is_valid():
        form.save()
        return httprr('..', 'A ação foi salva.')

    return locals()


def paua_acao_delete(request, plano_acao_pk, meta_pk, acao_pa_pk):
    plano_acao = get_object_or_404(PlanoAcao, pk=plano_acao_pk)
    acao_pa = get_object_or_404(AcaoPA, pk=acao_pa_pk)

    url = '{}?tab=acoes#macro_{}'.format(reverse_lazy('planoacao_unidade_view', kwargs={'plano_acao_pk': plano_acao_pk}), acao_pa.meta_pa.id)

    if not AcaoPA.pode_excluir(usuario=request.user, plano_acao=plano_acao, acao_pa_pk=acao_pa_pk):
        return httprr(url, 'Operação não permitida.', tag='error')

    acao_pa.delete()

    return httprr(url, 'A ação foi excluída.')


@rtr(template='planoacao_unidade_atividades.html')
@login_required()
def paua_acao_atividades(request, plano_acao_pk, acao_pa_pk):
    plano_acao = get_object_or_404(PlanoAcao, pk=plano_acao_pk)
    acao_pa = get_object_or_404(AcaoPA, pk=acao_pa_pk)
    if not acao_pa.setores_responsaveis:
        url_retorno = '{}?tab=acao#macro_{}'.format(
            reverse_lazy('planoacao_unidade_view', kwargs={'plano_acao_pk': plano_acao_pk}), acao_pa.meta_pa.id
        )
        return httprr(url_retorno, 'Você deve informar responsável.', 'error')

    title = f'Plano de Ação - {plano_acao.ano_base}'

    pode_incluir = Atividade.pode_incluir(request.user, plano_acao)
    pode_alterar = Atividade.pode_alterar(request.user, plano_acao)
    pode_excluir = Atividade.pode_excluir(request.user, plano_acao)

    atividades = Atividade.objects.filter(acao_pa__meta_pa__plano_acao=plano_acao)
    atividades = atividades.filter(acao_pa=acao_pa)
    ativ = atividades.filter(Q(validacao=Acao.SITUACAO_ANALISADA) | Q(validacao_vinculadora=Acao.SITUACAO_ANALISADA))

    pode_incluir_validacao = ativ.exists() and Atividade.pode_incluir_validacao(request.user, plano_acao)
    return locals()


@rtr()
@login_required()
def paua_atividade_add_change(request, plano_acao_pk, acao_pa_pk, atividade_pk=None):
    plano_acao = get_object_or_404(PlanoAcao, pk=plano_acao_pk)
    acao_pa = get_object_or_404(AcaoPA, pk=acao_pa_pk)
    atividade = None

    title = '{} Atividade'.format(atividade_pk and 'Editar' or 'Adicionar')

    if atividade_pk:
        atividade = get_object_or_404(Atividade, pk=atividade_pk)

        if not atividade.pode_alterar_validacao():
            if not Atividade.pode_alterar(usuario=request.user, plano_acao=plano_acao) and not atividade.pode_alterar_validacao():
                return httprr('..', 'Operação não permitida.', tag='error')
    else:
        if not Atividade.pode_incluir(usuario=request.user, plano_acao=plano_acao) and not Atividade.pode_incluir_validacao(
            usuario=request.user, plano_acao=plano_acao
        ):
            return httprr('..', 'Operação não permitida.', tag='error')

    form = AtividadeForm(request.POST or None, instance=atividade, acao_pa=acao_pa)

    if form.is_valid():
        form.save()
        return httprr('..', 'A atividade foi salva.')

    return locals()


@login_required()
def paua_atividade_delete(request, plano_acao_pk, acao_pa_pk, atividade_pk=None):
    plano_acao = get_object_or_404(PlanoAcao, pk=plano_acao_pk)
    get_object_or_404(AcaoPA, pk=acao_pa_pk)
    atividade = get_object_or_404(Atividade, pk=atividade_pk)

    url = reverse_lazy('paua_acao_atividades', kwargs={'plano_acao_pk': plano_acao_pk, 'acao_pa_pk': acao_pa_pk})

    if not Atividade.pode_excluir(usuario=request.user, plano_acao=plano_acao):
        return httprr(url, 'Operação não permitida.', tag='error')

    atividade.delete()

    return httprr(url, 'A atividade foi excluída.')


@rtr(template='planoacao_unidade_disponibilidade.html')
@login_required()
def paua_disponibilidade_financeira(request, plano_acao_pk):
    plano_acao = get_object_or_404(PlanoAcao, pk=plano_acao_pk)
    unidade_administrativa = get_setor_unidade_administrativa(request.user)
    title = 'Disponibilidade Financeira'

    origens_recurso = []

    query_origem = OrigemRecursoUA.objects.filter(origem_recurso__plano_acao=plano_acao)
    query_origem = query_origem.filter(unidade_administrativa__in=unidade_administrativa, origem_recurso__visivel_campus=True)
    query_origem = query_origem.filter(Q(valor_custeio__gt=0) | Q(valor_capital__gt=0))
    query_origem = query_origem.order_by('unidade_administrativa__tipo', 'unidade_administrativa__setor_equivalente__sigla')

    origens_recurso = OrderedDict()

    origens_lst = None
    ua = None

    for origem in query_origem:
        if ua is None:
            ua = origem.unidade_administrativa
            origens_lst = []

        if ua != origem.unidade_administrativa:
            origens_recurso[ua.setor_equivalente.sigla] = {'id': ua.id, 'origens': origens_lst}
            ua = origem.unidade_administrativa
            origens_lst = []

        capital_comprometido = origem.valor_capital_comprometido
        custeio_comprometido = origem.valor_custeio_comprometido

        origens_lst.append(
            {
                'nome': str(origem.origem_recurso),
                'valor_capital': origem.valor_capital,
                'capital_comprometido': capital_comprometido,
                'capital_saldo': origem.valor_capital - capital_comprometido,
                'valor_custeio': origem.valor_custeio,
                'custeio_comprometido': custeio_comprometido,
                'custeio_saldo': origem.valor_custeio - custeio_comprometido,
            }
        )

    if ua:
        origens_recurso[ua.setor_equivalente.sigla] = {'id': ua.id, 'origens': origens_lst}

    return locals()


@login_required()
@rtr(template='planoacao_unidade_relatorio_pa.html')
def paua_relatorio_plano_acao(request, plano_acao_pk):
    plano_acao = get_object_or_404(PlanoAcao, pk=plano_acao_pk)
    unidade_administrativa = get_setor_unidade_administrativa(request.user)

    title = f'Plano Ação {plano_acao.ano_base}'

    acoes_pa = (
        AcaoPA.objects.filter(meta_pa__plano_acao=plano_acao, unidade_administrativa__in=unidade_administrativa)
        .annotate(valor=Sum('atividade__valor'))
        .order_by(
            'meta_pa__meta__objetivo_estrategico__pdi_macroprocesso__macroprocesso__dimensao__nome',
            'meta_pa__meta__objetivo_estrategico__pdi_macroprocesso__macroprocesso__nome',
            'meta_pa__meta__objetivo_estrategico__descricao',
            'meta_pa__meta__titulo',
            'acao__acao__detalhamento',
        )
        .select_related()
        .distinct()
    )

    dimensao_dict = OrderedDict()

    dimensao = None
    macroprocesso = None
    objetivo = None
    meta = None
    acao = None

    macroprocesso_lst = []
    objetivo_lst = []
    meta_lst = []
    acao_lst = []

    for acao_pa in acoes_pa:
        if dimensao is None:
            dimensao = acao_pa.meta_pa.meta.objetivo_estrategico.pdi_macroprocesso.macroprocesso.dimensao
            macroprocesso = acao_pa.meta_pa.meta.objetivo_estrategico.pdi_macroprocesso.macroprocesso
            objetivo = acao_pa.meta_pa.meta.objetivo_estrategico
            meta = acao_pa.meta_pa.meta
            acao = {'acao': acao_pa.acao, 'codigo': acao_pa.acao.acao.id, 'titulo': acao_pa.acao.acao.detalhamento, 'valor': acao_pa.valor or 0}

        if acao['acao'] != acao_pa.acao:
            acao_lst.append(acao)

            acao = {
                'acao': acao_pa.acao,
                'codigo': acao_pa.acao.acao.id,
                'titulo': acao_pa.acao.acao.detalhamento,
                'valor': acao_pa.valor or 0,
                'atividades': acao_pa.atividade_set.filter(validacao=Acao.SITUACAO_DEFERIDA),
            }

        if meta != acao_pa.meta_pa.meta:
            meta_lst.append({'titulo': meta.titulo, 'acoes': acao_lst})
            meta = acao_pa.meta_pa.meta
            acao_lst = []

        if objetivo != acao_pa.meta_pa.meta.objetivo_estrategico:
            objetivo_lst.append({'titulo': objetivo.descricao, 'metas': meta_lst})
            objetivo = acao_pa.meta_pa.meta.objetivo_estrategico
            meta_lst = []

        if macroprocesso != acao_pa.meta_pa.meta.objetivo_estrategico.pdi_macroprocesso.macroprocesso:
            macroprocesso_lst.append({'titulo': macroprocesso.nome, 'objetivos': objetivo_lst})
            macroprocesso = acao_pa.meta_pa.meta.objetivo_estrategico.pdi_macroprocesso.macroprocesso
            objetivo_lst = []

        if dimensao != acao_pa.meta_pa.meta.objetivo_estrategico.pdi_macroprocesso.macroprocesso.dimensao:
            dimensao_dict[dimensao.nome] = macroprocesso_lst
            dimensao = acao_pa.meta_pa.meta.objetivo_estrategico.pdi_macroprocesso.macroprocesso.dimensao
            macroprocesso_lst = []

    if dimensao:
        acao_lst.append(acao)
        meta_lst.append({'meta': meta.titulo, 'acoes': acao_lst})
        objetivo_lst.append({'titulo': objetivo.descricao, 'metas': meta_lst})
        macroprocesso_lst.append({'macroprocesso': macroprocesso.nome, 'metas': meta_lst})
        dimensao_dict[dimensao.nome] = macroprocesso_lst

    return locals()


@rtr()
@login_required()
def geral_acao_solicitacao_add_change(request, plano_acao_pk, solicitacao_pk=None):
    plano_acao = get_object_or_404(PlanoAcao, pk=plano_acao_pk)
    unidade_administrativa = get_setor_unidade_administrativa(request.user)
    solicitacao = None

    title = '{} Solicitação'.format(solicitacao_pk and 'Editar' or 'Adicionar')

    if solicitacao_pk:
        solicitacao = get_object_or_404(Solicitacao, pk=solicitacao_pk)

        if not request.user.has_perm('plan_v2.change_solicitacao'):
            return httprr('..', 'Operação não permitida.', tag='error')

        if not solicitacao.em_espera:
            return httprr('..', 'Não é possível editar essa solicitação.')
    else:
        if not request.user.has_perm('plan_v2.add_solicitacao'):
            return httprr('..', 'Operação não permitida.', tag='error')

    form = SolicitacaoForm(request.POST or None, instance=solicitacao, unidade_administrativa=unidade_administrativa)

    if form.is_valid():
        form.save()
        return httprr('..', 'A solicitação foi salva.')

    return locals()


@login_required()
def geral_acao_solicitacao_delete(request, plano_acao_pk, solicitacao_pk):
    get_object_or_404(PlanoAcao, pk=plano_acao_pk)
    solicitacao = get_object_or_404(Solicitacao, pk=solicitacao_pk)

    if not request.user.has_perm('plan_v2.delete_solicitacao'):
        return httprr('..', 'Operação não permitida.', tag='error')

    if solicitacao.parecer != Solicitacao.PARECER_ESPERA:
        return httprr('..', f'A exclusão só é permitida para solicitações "{Solicitacao.PARECER_ESPERA}".', tag='error')

    solicitacao.delete()

    return httprr('..', 'A solicitação foi excluída.')


@login_required()
@rtr(template='relatorio_detalhamento.html')
def relatorio_detalhamento(request, plano_acao_pk):
    plano_acao = get_object_or_404(PlanoAcao, pk=plano_acao_pk)
    unidade_administrativa = None

    title = f'Detalhamento Planejamento {plano_acao.ano_base}'

    campus_form = RelatorioDetalhamentoForm(request.POST)

    try:
        unidade_administrativa = UnidadeAdministrativa.objects.get(pk=int(request.POST['campus']))
    except Exception:
        mensagem = 'Selecione um Campus para gerar o relatório.'

    acoes_pa = (
        AcaoPA.objects.filter(meta_pa__plano_acao=plano_acao, unidade_administrativa=unidade_administrativa)
        .annotate(valor=Sum('atividade__valor'))
        .order_by(
            'meta_pa__meta__objetivo_estrategico__pdi_macroprocesso__macroprocesso__dimensao__nome',
            'meta_pa__meta__objetivo_estrategico__pdi_macroprocesso__macroprocesso__nome',
            'meta_pa__meta__objetivo_estrategico__descricao',
            'meta_pa__meta__titulo',
            'acao__acao__detalhamento',
        )
        .select_related()
    )

    dimensao_dict = OrderedDict()

    dimensao = None
    macroprocesso = None
    objetivo = None
    meta = None
    acao = None
    atividade = None

    dimensao_lst = []
    macroprocesso_lst = []
    objetivo_lst = []
    meta_lst = []
    acao_lst = []
    atividade_lst = []
    for acao_pa in acoes_pa:
        if dimensao is None:
            dimensao = acao_pa.meta_pa.meta.objetivo_estrategico.pdi_macroprocesso.macroprocesso.dimensao
            macroprocesso = acao_pa.meta_pa.meta.objetivo_estrategico.pdi_macroprocesso.macroprocesso
            objetivo = acao_pa.meta_pa.meta.objetivo_estrategico
            meta = acao_pa.meta_pa.meta

            acao = {
                'acao': acao_pa.acao,
                'codigo': acao_pa.acao.acao.id,
                'titulo': acao_pa.acao.acao,
                'setores_responsaveis': acao_pa.setores_responsaveis.all(),
                'valor': acao_pa.valor or 0,
            }

        if acao['acao'] != acao_pa.acao:
            acao_lst.append(acao)

            acao = {
                'acao': acao_pa.acao,
                'codigo': acao_pa.acao.acao.id,
                'titulo': acao_pa.acao.acao,
                'setores_responsaveis': acao_pa.setores_responsaveis.all(),
                'valor': acao_pa.valor or 0,
                'atividades': acao_pa.atividade_set.filter(validacao=Acao.SITUACAO_DEFERIDA),
            }

        if meta != acao_pa.meta_pa.meta:
            valor_meta = 0
            for a in acao_lst:
                valor_meta += a['valor']
            meta_lst.append({'titulo': meta.titulo, 'acoes': acao_lst, 'valor': valor_meta})
            meta = acao_pa.meta_pa.meta
            acao_lst = []

        if objetivo != acao_pa.meta_pa.meta.objetivo_estrategico:
            valor_objetivo = 0
            for m in meta_lst:
                valor_objetivo += m['valor']
            objetivo_lst.append({'titulo': objetivo.descricao, 'metas': meta_lst, 'valor': valor_objetivo})
            objetivo = acao_pa.meta_pa.meta.objetivo_estrategico
            meta_lst = []

        if macroprocesso != acao_pa.meta_pa.meta.objetivo_estrategico.pdi_macroprocesso.macroprocesso:
            valor_macro = 0
            for o in objetivo_lst:
                valor_macro += o['valor']
            macroprocesso_lst.append({'titulo': macroprocesso.nome, 'objetivos': objetivo_lst, 'valor': valor_macro})
            macroprocesso = acao_pa.meta_pa.meta.objetivo_estrategico.pdi_macroprocesso.macroprocesso
            objetivo_lst = []

        if dimensao != acao_pa.meta_pa.meta.objetivo_estrategico.pdi_macroprocesso.macroprocesso.dimensao:
            valor_dimensao = 0
            for o in macroprocesso_lst:
                valor_dimensao += o['valor']
            dimensao_dict[dimensao.nome] = [macroprocesso_lst, valor_dimensao]
            dimensao = acao_pa.meta_pa.meta.objetivo_estrategico.pdi_macroprocesso.macroprocesso.dimensao
            macroprocesso_lst = []

        acao['valor'] = acao_pa.valor or 0

    if dimensao:
        acao_lst.append(acao)
        valor_meta = 0
        for a in acao_lst:
            valor_meta += a['valor']

        meta_lst.append({'titulo': meta.titulo, 'acoes': acao_lst, 'valor': valor_meta})
        valor_objetivo = 0
        for m in meta_lst:
            valor_objetivo += m['valor']
        objetivo_lst.append({'titulo': objetivo.descricao, 'metas': meta_lst, 'valor': valor_objetivo})
        valor_macro = 0
        for o in objetivo_lst:
            valor_macro += o['valor']
        macroprocesso_lst.append({'titulo': macroprocesso.nome, 'objetivos': objetivo_lst, 'valor': valor_macro})
        valor_dimensao = 0
        for o in macroprocesso_lst:
            valor_dimensao += o['valor']
        dimensao_dict[dimensao.nome] = [macroprocesso_lst, valor_dimensao]

    return locals()


@login_required()
@rtr(template='relatorio_origemrecurso.html')
def relatorio_origemrecurso(request, plano_acao_pk):
    plano_acao = get_object_or_404(PlanoAcao, pk=plano_acao_pk)
    unidade_administrativa = None

    title = f'Relatório de Origem de Recurso por Campus {plano_acao.ano_base}'

    campus_form = RelatorioDetalhamentoForm(request.POST)

    try:
        unidade_administrativa = UnidadeAdministrativa.objects.get(pk=int(request.POST['campus']))
    except Exception:
        mensagem = 'Selecione um Campus para gerar o relatório.'

    dados = OrigemRecursoUA.objects.filter(origem_recurso__plano_acao=plano_acao, unidade_administrativa=unidade_administrativa)

    dados = dados.filter(Q(valor_capital__gt=0) | Q(valor_custeio__gt=0))
    return locals()


@login_required()
@rtr(template='relatorio_naturezadespesa.html')
def relatorio_naturezadespesa(request, plano_acao_pk):
    plano_acao = get_object_or_404(PlanoAcao, pk=plano_acao_pk)
    unidade_administrativa = None

    title = f'Relatório de Natureza de Despesa por Campus {plano_acao.ano_base}'

    campus_form = RelatorioDetalhamentoForm(request.POST)

    try:
        unidade_administrativa = UnidadeAdministrativa.objects.get(pk=int(request.POST['campus']))
    except Exception:
        mensagem = 'Selecione um Campus para gerar o relatório.'

    dados = NaturezaDespesaPA.objects.filter(
        atividade__acao_pa__meta_pa__plano_acao=plano_acao, atividade__acao_pa__unidade_administrativa=unidade_administrativa
    ).annotate(total=Sum('atividade__valor'))

    return locals()
