import os
from collections import OrderedDict
from datetime import date, datetime
from decimal import Decimal
from operator import itemgetter

from django.apps import apps
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.db import transaction
from django.http import HttpResponse

from comum.models import Comentario, Log, User
from djtools import db
from djtools.templatetags.filters import in_group
from djtools.utils import eval_attr, group_required, httprr, rtr
from financeiro.forms import AcaoFiltroForm
from financeiro.models import Acao as AcaoOrcamento
from financeiro.models import FonteRecurso, NaturezaDespesa
from planejamento.enums import Situacao, TipoUnidade
from planejamento.forms import (
    AcaoAvaliacaoForm,
    AcaoBuscaForm,
    AcaoExecucaoForm,
    AcaoForm,
    AcaoPropostaForm,
    AcaoValidarFiltro,
    AtividadeExecucaoForm,
    AtividadeForm,
    CampusFiltroForm,
    ConfiguracaoFiltroForm,
    ConfirmacaoForm,
    DimensaoFiltroForm,
    MetaForm,
    MetaUnidadeAcaoPropostaForm,
    MetaUnidadeAcaoPropostaTodosCampiForm,
    MetaUnidadeForm,
    MetaUnidadeTodosCampiForm,
    OrigemRecursoFiltroForm,
    PlanoAcaoForm,
    RelatorioCampusForm,
    RelatorioDetalhamentoForm,
    RelatorioOrigemRecursoForm,
    RelatorioOrigemRecursosForm,
)
from planejamento.models import (
    Acao,
    AcaoExecucao,
    AcaoExtraTeto,
    AcaoProposta,
    AcaoValidacao,
    Atividade,
    AtividadeExecucao,
    Configuracao,
    Dimensao,
    Meta,
    MetaUnidade,
    MetaUnidadeAcaoProposta,
    ObjetivoEstrategico,
    OrigemRecurso,
    OrigemRecursoUA,
    UnidadeAdministrativa,
)
from planejamento.utils import get_setor_unidade_administrativa
from rh.models import Setor


def http_query_string_para_ultimo_ano(GET, Modelo, filtro):
    params = []
    objeto = Modelo.objects.latest(filtro)

    if objeto:
        params.append('{}__exact={}'.format(filtro, eval_attr(objeto, filtro.replace('__', '.'))))

    for p in GET:
        params.append(f'{p}={GET[p]}')

    return '&'.join(params)


@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico, Auditor')
def origemrecurso_anobase_atual(request):
    params = http_query_string_para_ultimo_ano(request.GET, OrigemRecurso, 'configuracao__ano_base__id')
    return httprr(f'/admin/planejamento/origemrecurso/?{params}')


@group_required('Administrador de Planejamento, Auditor')
def unidadeadministrativa_anobase_atual(request):
    params = http_query_string_para_ultimo_ano(request.GET, UnidadeAdministrativa, 'configuracao__ano_base__id')
    return httprr(f'/admin/planejamento/unidadeadministrativa/?{params}')


@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico, Auditor')
def objetivoestrategico_anobase_atual(request):
    params = http_query_string_para_ultimo_ano(request.GET, ObjetivoEstrategico, 'configuracao__ano_base__id')
    return httprr(f'/admin/planejamento/objetivoestrategico/?{params}')


@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico, Auditor')
def meta_anobase_atual(request):
    params = http_query_string_para_ultimo_ano(request.GET, Meta, 'objetivo_estrategico__configuracao__ano_base__id')
    return httprr(f'/admin/planejamento/meta/?{params}')


@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico,Coordenador de Planejamento, Auditor')
def metaunidade_anobase_atual(request):
    params = http_query_string_para_ultimo_ano(request.GET, MetaUnidade, 'meta__objetivo_estrategico__configuracao__ano_base__id')
    return httprr(f'/admin/planejamento/metaunidade/?{params}')


@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico, Auditor')
def acaoproposta_anobase_atual(request):
    params = http_query_string_para_ultimo_ano(request.GET, AcaoProposta, 'meta__objetivo_estrategico__configuracao__ano_base__id')
    return httprr(f'/admin/planejamento/acaoproposta/?{params}')


@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico,Coordenador de Planejamento')
def acaoextrateto_anobase_atual(request):
    params = http_query_string_para_ultimo_ano(request.GET, AcaoExtraTeto, 'unidade__configuracao__ano_base__id')
    return httprr(f'/admin/planejamento/acaoextrateto/?{params}')


@group_required('Administrador de Planejamento, Auditor')
def origemrecursoua_anobase_atual(request):
    params = http_query_string_para_ultimo_ano(request.GET, OrigemRecursoUA, 'configuracao__ano_base__id')
    return httprr(f'/admin/planejamento/origemrecursoua/?{params}')


@rtr()
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico, Auditor')
def origemrecurso(request, id):
    origem_recurso = OrigemRecurso.objects.get(id=id)
    orcamento = origem_recurso.valor_custeio + origem_recurso.valor_capital
    origem_recursoua = OrigemRecursoUA.objects.filter(origem_recurso=id)
    title = f'Origem Recurso {origem_recurso.nome}'

    return locals()


@rtr()
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico, Auditor')
def objetivoestrategico(request, id):
    objetivo_estrategico = ObjetivoEstrategico.objects.get(id=id)
    configuracao = objetivo_estrategico.configuracao
    title = f'Macro Projeto Institucional {objetivo_estrategico.get_codigo_completo()}'

    return locals()


@rtr()
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico, Auditor')
def meta(request, id):
    meta = Meta.objects.get(id=id)
    title = f'Meta {meta.get_codigo_completo()}'

    return locals()


@rtr()
@group_required('Administrador de Planejamento, Coordenador de Planejamento, Auditor')
def metaunidade(request, id):
    metaunidade = MetaUnidade.objects.get(id=id)
    title = f'Meta {metaunidade.get_codigo_completo()}'

    saldo = metaunidade.unidade.get_saldo_proprio()
    # indica quais as ações propostas e quais destas já foram importadas
    acoespropostas = MetaUnidadeAcaoProposta.objects.filter(meta_unidade=metaunidade).extra(
        select={
            'importada': f'select 1 from planejamento_acao \
                            where meta_unidade_id = {metaunidade.id} and \
                                acao_indutora_id = planejamento_metaunidadeacaoproposta.id'
        }
    )

    # Auxiliar ao template
    eh_administrador = in_group(request.user, 'Administrador de Planejamento')
    eh_gerente_campus = in_group(request.user, 'Coordenador de Planejamento')
    eh_periodo_campus = metaunidade.meta.objetivo_estrategico.configuracao.periodo_campus()
    eh_periodo_validacao = metaunidade.meta.objetivo_estrategico.configuracao.periodo_validacao()

    return locals()


@rtr()
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico, Auditor')
def acaoproposta(request, id):
    acaoproposta = AcaoProposta.objects.get(id=id)
    title = f'Ação Proposta {acaoproposta.get_codigo_completo()}'

    return locals()


@rtr()
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico,Coordenador de Planejamento, Auditor')
def acao(request, id):
    acao = Acao.objects.get(id=id)
    title = f'Ação {acao.get_codigo_completo()}'

    eh_administrador = in_group(request.user, 'Administrador de Planejamento')
    eh_gerente_campus = in_group(request.user, 'Coordenador de Planejamento')
    eh_periodo_campus = acao.meta_unidade.meta.objetivo_estrategico.configuracao.periodo_campus()
    eh_periodo_validacao = acao.meta_unidade.meta.objetivo_estrategico.configuracao.periodo_validacao()
    eh_acao_pendente = acao.is_pendente() or acao.is_parcialmente_deferida()

    return locals()


@rtr()
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico,Coordenador de Planejamento, Auditor')
def atividade(request, id):
    title = 'Atividade'

    atividade = Atividade.objects.get(id=id)

    return locals()


@rtr()
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico')
def meta_remover(request, id):
    meta = Meta.objects.get(id=id)
    objetivo_estrategico = meta.objetivo_estrategico
    configuracao = objetivo_estrategico.configuracao

    if configuracao.periodo_sistemico():
        msg = ''
        if meta.metaunidade_set.exists():
            msg = msg + ' Existe(m) unidades administrativas'
        if meta.acaoproposta_set.exists():
            if len(msg) > 0:
                msg = msg + ' e ações propostas para essa meta.'
            else:
                msg = msg + ' Existe(m) ações propostas para essa meta.'
        elif len(msg) > 0:
            msg = msg + ' para essa meta.'

        if len(msg) > 0:
            msg = 'Não é possível efetuar a operação. ' + msg
            return httprr(f'/planejamento/meta/{meta.id}/', msg)
        if not request.user.has_perm('planejamento.delete_meta'):
            return httprr(f'/planejamento/meta/{meta.id}/', 'Você não tem permissão para remover metas.')
        meta.delete()
    else:
        return httprr(f'/planejamento/meta/{objetivo_estrategico.id}/', 'O período para remoção de metas expirou.')
    return httprr(
        f'/planejamento/objetivoestrategico/{objetivo_estrategico.id}/',
        f'A meta {meta.get_codigo_completo()} foi removida com sucesso.',
    )


@rtr()
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico')
def metaunidade_remover(request, id):
    metaunidade = MetaUnidade.objects.get(id=id)
    meta = metaunidade.meta
    configuracao = meta.objetivo_estrategico.configuracao

    if configuracao.periodo_sistemico():
        if metaunidade.acao_set.exists():
            return httprr(
                f'/planejamento/meta/{meta.id}/',
                'Não é possível efetuar a operação. Existe(m) ações cadastradas para essa unidade administrativa.',
            )
        if not request.user.has_perm('planejamento.delete_metaunidade'):
            return httprr(f'/planejamento/meta/{meta.id}/', 'Você não tem permissão para remover unidades administrativas.')
        metaunidade.delete()
    else:
        return httprr(f'/planejamento/meta/{meta.id}/', 'O período para remoção de unidades administrativas expirou.')

    return httprr(f'/planejamento/meta/{meta.id}/', f'A unidade administrativa {metaunidade.unidade} não está mais associada.')


@rtr()
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico')
def acaoproposta_remover(request, id):
    acaoproposta = AcaoProposta.objects.get(id=id)
    meta = acaoproposta.meta
    configuracao = meta.objetivo_estrategico.configuracao

    if configuracao.periodo_sistemico():
        if acaoproposta.metaunidadeacaoproposta_set.exists():
            return httprr(
                f'/planejamento/acaoproposta/{acaoproposta.id}/',
                'Não é possível efetuar a operação. Existe(m) unidade(s) administrativa(s) associadas a essa ação proposta.',
            )
        if not request.user.has_perm('planejamento.delete_acaoproposta'):
            return httprr(f'/planejamento/acaoproposta/{acaoproposta.id}/', 'Você não tem permissão para remover ações propostas.')
        acaoproposta.delete()
    else:
        return httprr(f'/planejamento/acaoproposta/{acaoproposta.id}/', 'O período para remoção de ações propostas expirou.')
    return httprr(f'/planejamento/meta/{meta.id}/', f'A ação proposta {acaoproposta.get_codigo_completo()} foi removida com sucesso.')


@rtr()
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico')
def metaunidadeacaoproposta_remover(request, id):
    metaunidade_ap = MetaUnidadeAcaoProposta.objects.get(id=id)
    acaoproposta = metaunidade_ap.acao_proposta
    configuracao = acaoproposta.meta.objetivo_estrategico.configuracao

    if configuracao.periodo_sistemico():
        if metaunidade_ap.acao_set.exists():
            return httprr(
                f'/planejamento/acaoproposta/{acaoproposta.id}/',
                'Não é possível efetuar a operação. Existe(m) ação(ões) associada(s) a essa proposta.',
            )
        if not request.user.has_perm('planejamento.delete_metaunidadeacaoproposta'):
            return httprr(f'/planejamento/acaoproposta/{acaoproposta.id}/', 'Você não tem permissão para remover ações propostas.')
        metaunidade_ap.delete()
    else:
        return httprr(f'/planejamento/acaoproposta/{acaoproposta.id}/', 'O período para remoção de unidades administrativas expirou.')
    return httprr(f'/planejamento/acaoproposta/{acaoproposta.id}/', 'A unidade administrativa foi removida com sucesso.')


@rtr()
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico,Coordenador de Planejamento')
def acao_remover(request, id):
    acao = Acao.objects.get(id=id)
    configuracao = acao.meta_unidade.meta.objetivo_estrategico.configuracao

    if configuracao.periodo_campus():
        if acao.atividade_set.exists():
            return httprr(f'/planejamento/acao/{acao.id}/', 'Não é possível efetuar a operação. Existe(m) atividade(s) cadastrada(s) para essa ação.')
        if not request.user.has_perm('planejamento.delete_acao'):
            return httprr(f'/planejamento/acao/{acao.id}/', 'Você não tem permissão para remover ações.')
        acao.delete()
    else:
        return httprr(f'/planejamento/acao/{acao.id}/', 'O período para remoção de ações expirou.')
    return httprr(f'/planejamento/metaunidade/{acao.meta_unidade.id}/', f'A ação {acao.get_codigo_completo()} foi removida com sucesso.')


@rtr()
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico,Coordenador de Planejamento')
def atividade_remover(request, id):
    atividade = Atividade.objects.get(pk=id)
    configuracao = atividade.acao.meta_unidade.meta.objetivo_estrategico.configuracao

    if configuracao.periodo_campus():
        if not request.user.has_perm('planejamento.delete_atividade'):
            return httprr(f'/planejamento/atividade/{atividade.id}/', 'Você não tem permissão para remover atividades.')
        atividade.delete()
    else:
        if atividade.acao.status not in [Situacao.PENDENTE, Situacao.PARCIALMENTE_DEFERIDA] and not request.user.has_perm(
            'planejamento.delete_atividade'
        ):
            return httprr(f'/planejamento/atividade/{atividade.id}/', 'O período para remoção de atividades expirou.')
        else:
            # se a acao estiver pendente as suas atividades podem ser removidas
            if in_group(request.user, ['Coordenador de Planejamento']):
                atividade.acao.status = Situacao.PENDENTE
                atividade.acao.save()
            atividade.delete()
    return httprr(f'/planejamento/acao/{atividade.acao.id}/', f'A atividade "{atividade.descricao}" foi removida com sucesso.')


@rtr('planejamento/templates/objetivoestrategico_metas.html')
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico')
def objetivoestrategico_metas(request, id):
    objetivo_estrategico = ObjetivoEstrategico.objects.get(id=id)
    configuracao = objetivo_estrategico.configuracao
    if request.method == 'POST':
        form = MetaForm(request.POST, id_objetivo_estrategico=id, request=request)
        if form.is_valid():
            form.save()
            return httprr(f'/planejamento/objetivoestrategico/{id}/metas/', 'Meta cadastrada com sucesso.')
    else:
        form = MetaForm(id_objetivo_estrategico=id, request=request)
    return locals()


@rtr('planejamento/templates/objetivoestrategico_metas.html')
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico')
def meta_old(request, id_objetivo_estrategico, id_meta):
    objetivo_estrategico = ObjetivoEstrategico.objects.get(id=id_objetivo_estrategico)
    meta = Meta.objects.get(id=id_meta)

    if request.method == 'POST':
        form = MetaForm(request.POST, instance=meta, request=request)
        if form.is_valid():
            form.save()
            return httprr(f'/planejamento/objetivoestrategico/{id_objetivo_estrategico}/metas/', 'Meta editada com sucesso.')
    else:
        form = MetaForm(instance=meta, request=request)
    return locals()


@rtr('planejamento/templates/objetivoestrategico_metas.html')
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico')
def meta_remover_old(request, id_objetivo_estrategico, id_meta):
    objetivo_estrategico = ObjetivoEstrategico.objects.get(id=id_objetivo_estrategico)
    meta = Meta.objects.get(id=id_meta)
    configuracao = objetivo_estrategico.configuracao

    if configuracao.periodo_sistemico():
        msg = ''
        if meta.metaunidade_set.exists():
            msg = msg + ' Existe(m) unidades administrativas'
        if meta.acaoproposta_set.exists():
            if len(msg) > 0:
                msg = msg + ' e ações propostas para essa meta.'
            else:
                msg = msg + ' Existe(m) ações propostas para essa meta.'
        elif len(msg) > 0:
            msg = msg + ' para essa meta.'

        if len(msg) > 0:
            msg = 'Não é possível efetuar a operação. ' + msg
            return httprr(f'/planejamento/objetivoestrategico/{id_objetivo_estrategico}/metas/', msg)
        if not request.user.has_perm('planejamento.delete_meta'):
            return httprr(f'/planejamento/objetivoestrategico/{id_objetivo_estrategico}/metas/', 'Você não tem permissão para remover metas.')
        meta.delete()
    else:
        return httprr(f'/planejamento/objetivoestrategico/{id_objetivo_estrategico}/metas/', 'O período para remoção de metas expirou.')
    return httprr(f'/planejamento/objetivoestrategico/{id_objetivo_estrategico}/metas/', 'A meta foi removida.')


# Esta view trabalha com dois forms:
# 1 Form associado a apenas um model
# 2 Form associado a mais de um model
@rtr('planejamento/templates/meta_metaunidades.html')
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico')
def meta_metaunidades(request, id):
    meta = Meta.objects.get(id=id)
    unidades_adm = UnidadeAdministrativa.objects.filter(configuracao=meta.objetivo_estrategico.configuracao)
    unidades_administrativas = unidades_adm.filter(tipo=TipoUnidade.CAMPUS)

    if request.method == 'POST':
        if 'campi' in request.POST:
            form_todos_campi = MetaUnidadeTodosCampiForm(request.POST, id_meta=id)
            if form_todos_campi.is_valid():
                quantidade = form_todos_campi.cleaned_data['quantidade']
                valor_total = form_todos_campi.cleaned_data['valor_total']
                if len(unidades_administrativas):
                    for unidade_administrativa in unidades_administrativas:
                        MetaUnidade.objects.create(meta=meta, unidade=unidade_administrativa, quantidade=quantidade, valor_total=valor_total)
                    return httprr(f'/planejamento/meta/{id}/metaunidades/', 'Todos os campi foram associados.')
                else:
                    return httprr(f'/planejamento/meta/{id}/metaunidades/', 'Não existem unidades administrativas do tipo "Campus".')
        else:
            form = MetaUnidadeForm(request.POST, id_meta=id, request=request)
            if form.is_valid():
                form.save()
                return httprr(f'/planejamento/meta/{id}/metaunidades/', 'A Unidade Administrativa foi associada com sucesso.')
    else:
        form_todos_campi = MetaUnidadeTodosCampiForm(id_meta=id)
        form = MetaUnidadeForm(id_meta=id, request=request)
    return locals()


@rtr('planejamento/templates/meta_metaunidades.html')
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico')
def metaunidade_old(request, id_meta, id_meta_unidade):
    meta = Meta.objects.get(id=id_meta)
    meta_unidade = MetaUnidade.objects.get(id=id_meta_unidade)
    # Esta variável é passada para renderização correta de botões no template
    unidades_administrativas = UnidadeAdministrativa.objects.filter(tipo=TipoUnidade.CAMPUS)
    if request.method == 'POST':
        form = MetaUnidadeForm(request.POST, instance=meta_unidade, request=request)
        if form.is_valid():
            form.save()
            return httprr(f'/planejamento/meta/{id_meta}/metaunidades/', 'Meta para uma unidade editada com sucesso.')
    else:
        form = MetaUnidadeForm(instance=meta_unidade, request=request)
    return locals()


@rtr('planejamento/templates/meta_metaunidades.html')
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico')
def metaunidade_remover_old(request, id_meta, id_meta_unidade):
    meta = Meta.objects.get(id=id_meta)
    meta_unidade = MetaUnidade.objects.get(id=id_meta_unidade)
    configuracao = meta.objetivo_estrategico.configuracao

    if configuracao.periodo_sistemico():
        if meta_unidade.acao_set.exists():
            return httprr(
                f'/planejamento/meta/{id_meta}/metaunidades/',
                'Não é possível efetuar a operação. Existe(m) ações para essa unidade administrativa.',
            )
        if not request.user.has_perm('planejamento.delete_metaunidade'):
            return httprr(f'/planejamento/meta/{id_meta}/metaunidades/', 'Você não tem permissão para remover unidades administrativas.')
        meta_unidade.delete()
    else:
        return httprr(f'/planejamento/meta/{id_meta}/metaunidades/', 'O período para remoção de unidades administrativas expirou.')
    return httprr(f'/planejamento/meta/{id_meta}/metaunidades/', 'A unidade administrativa da meta foi removida.')


@rtr('planejamento/templates/meta_acoespropostas.html')
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico')
def meta_acoespropostas(request, id_meta):
    meta = Meta.objects.get(id=id_meta)

    if request.method == 'POST':
        form = AcaoPropostaForm(request.POST, id_meta=id_meta, request=request)
        if form.is_valid():
            form.save()
            return httprr(f'/planejamento/meta/{id_meta}/acoespropostas/', 'Ação proposta cadastrada com sucesso.')
    else:
        form = AcaoPropostaForm(id_meta=id_meta, request=request)
    return locals()


@rtr('planejamento/templates/meta_acoespropostas.html')
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico')
def acaoproposta_old(request, id_meta, id_acao_proposta):
    meta = Meta.objects.get(id=id_meta)
    acao_proposta = AcaoProposta.objects.get(id=id_acao_proposta)
    acoes_importadas = Acao.objects.filter(acao_indutora__acao_proposta=acao_proposta)
    tem_acoes_importadas = acoes_importadas.exists()
    if request.method == 'POST':
        form = AcaoPropostaForm(request.POST, instance=acao_proposta, request=request)
        if form.is_valid():
            form.save()
            return httprr(f'/planejamento/meta/{id_meta}/acoespropostas/', 'Ação Proposta editada com sucesso.')
    else:
        form = AcaoPropostaForm(instance=acao_proposta, request=request)
    return locals()


# Esta view trabalha com dois forms:
# 1 Form associado a apenas um model: form
# 2 Form associado a mais de um model: form_todos_campi
@rtr('planejamento/templates/acaoproposta_unidades.html')
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico')
def acaoproposta_metaunidades(request, id):
    acao_proposta = AcaoProposta.objects.get(id=id)
    metaunidades = MetaUnidade.objects.filter(meta=acao_proposta.meta)
    meta_unidades = metaunidades.filter(unidade__tipo=TipoUnidade.CAMPUS)

    if request.method == 'POST':
        if 'campi' in request.POST:
            form_todos_campi = MetaUnidadeAcaoPropostaTodosCampiForm(request.POST, id_acao_proposta=id)
            if form_todos_campi.is_valid():
                quantidade = form_todos_campi.cleaned_data['quantidade']
                valor_unitario = form_todos_campi.cleaned_data['valor_unitario']
                if len(meta_unidades):
                    for meta_unidade in meta_unidades:
                        MetaUnidadeAcaoProposta.objects.create(
                            acao_proposta=acao_proposta, meta_unidade=meta_unidade, quantidade=quantidade, valor_unitario=valor_unitario
                        )
                    return httprr(f'/planejamento/acaoproposta/{id}/unidades/', 'Todos os campi foram associados.')
                else:
                    return httprr(f'/planejamento/acaoproposta/{id}/unidades/', 'Não existem unidades administrativas do tipo "Campus".')
        else:
            form = MetaUnidadeAcaoPropostaForm(request.POST, id_acao_proposta=id, request=request)
            if form.is_valid():
                form.save()
                return httprr(f'/planejamento/acaoproposta/{id}/unidades/', 'A Unidade Administrativa foi associada com sucesso.')
    else:
        form_todos_campi = MetaUnidadeAcaoPropostaTodosCampiForm(id_acao_proposta=id)
        form = MetaUnidadeAcaoPropostaForm(id_acao_proposta=id, request=request)

    return locals()


@rtr('planejamento/templates/acaoproposta_unidades.html')
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico')
def metaunidadeacaoproposta(request, id_acao_proposta, id_meta_unidade_acao_proposta):
    acao_proposta = AcaoProposta.objects.get(id=id_acao_proposta)
    meta_unidade_acao_proposta = MetaUnidadeAcaoProposta.objects.get(id=id_meta_unidade_acao_proposta)
    # Esta variável é passada para renderização correta de botões no template
    metaunidades = MetaUnidade.objects.filter(unidade__tipo=TipoUnidade.CAMPUS, meta=acao_proposta.meta)
    if request.method == 'POST':
        form = MetaUnidadeAcaoPropostaForm(request.POST, instance=meta_unidade_acao_proposta, request=request)
        if form.is_valid():
            form.save()
            return httprr(f'/planejamento/acaoproposta/{id_acao_proposta}/unidades/', 'Unidade de uma ação proposta editada com sucesso.')
    else:
        form = MetaUnidadeAcaoPropostaForm(instance=meta_unidade_acao_proposta, request=request)
    return locals()


@rtr('planejamento/templates/acaoproposta_unidades.html')
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico')
def metaunidadeacaoproposta_remover_old(request, id_acao_proposta, id_meta_unidade_acao_proposta):
    acao_proposta = AcaoProposta.objects.get(id=id_acao_proposta)
    meta_unidade_acao_proposta = MetaUnidadeAcaoProposta.objects.get(id=id_meta_unidade_acao_proposta)
    configuracao = acao_proposta.meta.objetivo_estrategico.configuracao

    if configuracao.periodo_sistemico():
        if meta_unidade_acao_proposta.acao_set.exists():
            return httprr(
                f'/planejamento/acaoproposta/{id_acao_proposta}/unidades/',
                'Não é possível efetuar a operação. Existe(m) ação(ões) associada(s) a essa proposta.',
            )
        if not request.user.has_perm('planejamento.delete_metaunidadeacaoproposta'):
            return httprr(f'/planejamento/acaoproposta/{id_acao_proposta}/unidades/', 'Você não tem permissão para remover ações propostas.')
        meta_unidade_acao_proposta.delete()
    else:
        return httprr(f'/planejamento/acaoproposta/{id_acao_proposta}/unidades/', 'O período para remoção de unidades administrativas expirou.')
    return httprr(f'/planejamento/acaoproposta/{id_acao_proposta}/unidades/', 'A unidade administrativa foi removida.')


@rtr('planejamento/templates/meta_acoespropostas.html')
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico')
def acaoproposta_remover_old(request, id_meta, id_acao_proposta):
    meta = Meta.objects.get(id=id_meta)
    acao_proposta = AcaoProposta.objects.get(id=id_acao_proposta)
    configuracao = meta.objetivo_estrategico.configuracao

    if configuracao.periodo_sistemico():
        if acao_proposta.metaunidadeacaoproposta_set.exists():
            return httprr(
                f'/planejamento/meta/{id_meta}/acoespropostas/',
                'Não é possível efetuar a operação. Existe(m) unidade(s) administrativa(s) associadas a essa proposta.',
            )
        if not request.user.has_perm('planejamento.delete_acaoproposta'):
            return httprr(f'/planejamento/meta/{id_meta}/acoespropostas/', 'Você não tem permissão para remover ações propostas.')
        acao_proposta.delete()
    else:
        return httprr(f'/planejamento/meta/{id_meta}/acoespropostas/', 'O período para remoção de ações propostas expirou.')
    return httprr(f'/planejamento/meta/{id_meta}/acoespropostas/', 'A ação proposta foi removida.')


@rtr('planejamento/templates/metaunidade_acoes.html')
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico,Coordenador de Planejamento')
def metaunidade_acoespropostas(request, id_meta_unidade, id_meta_unidade_acao_proposta):
    meta_unidade = MetaUnidade.objects.get(id=id_meta_unidade)

    # indica quais as ações propostas e quais destas já foram importadas
    acoes_propostas = MetaUnidadeAcaoProposta.objects.filter(meta_unidade=meta_unidade).extra(
        select={
            'importada': f'select 1 from planejamento_acao \
                            where meta_unidade_id={meta_unidade.id} and \
                            acao_indutora_id=planejamento_metaunidadeacaoproposta.id'
        }
    )

    if request.method == 'POST':
        form = AcaoForm(request.POST, id_meta_unidade=id_meta_unidade, id_meta_unidade_acao_proposta=id_meta_unidade_acao_proposta, request=request)
        if form.is_valid():
            form.save()
            return httprr(f'/planejamento/metaunidade/{id_meta_unidade}/acoes/', 'Ação proposta importada com sucesso.')
    else:
        form = AcaoForm(id_meta_unidade=id_meta_unidade, id_meta_unidade_acao_proposta=id_meta_unidade_acao_proposta, request=request)

    return locals()


@rtr('planejamento/templates/metaunidade_acoes.html')
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico,Coordenador de Planejamento')
def metaunidade_acoes(request, id):
    meta_unidade = MetaUnidade.objects.get(id=id)
    saldo = meta_unidade.unidade.get_saldo_proprio()
    # indica quais as ações propostas e quais destas já foram importadas
    acoes_propostas = MetaUnidadeAcaoProposta.objects.filter(meta_unidade=meta_unidade).extra(
        select={
            'importada': f'select 1 from planejamento_acao \
                            where meta_unidade_id={meta_unidade.id} and \
                            acao_indutora_id=planejamento_metaunidadeacaoproposta.id'
        }
    )

    if request.method == 'POST':
        form = AcaoForm(request.POST, id_meta_unidade=id, request=request)
        if form.is_valid():
            form.save()
            return httprr(f'/planejamento/metaunidade/{id}/acoes/', 'Ação cadastrada com sucesso.')
    else:
        form = AcaoForm(id_meta_unidade=id, request=request)

    return locals()


@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico,Coordenador de Planejamento, Auditor')
def acao_anobase_atual(request):
    sql = """select max(a.id)
                    from planejamento_objetivoestrategico o,
                         planejamento_meta m,
                         planejamento_metaunidade mu,
                         planejamento_acao ac,
                         planejamento_configuracao c,
                         comum_ano a
                    where o.id = m.objetivo_estrategico_id and
                          m.id = mu.meta_id and
                          mu.id = ac.meta_unidade_id and
                          c.id = o.configuracao_id and
                          a.id = c.ano_base_id;"""
    resultado = db.get_list(sql)[0]
    return httprr(f'/admin/planejamento/acao/?meta_unidade__meta__objetivo_estrategico__configuracao__ano_base__id__exact={resultado}')


@rtr()
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico,Coordenador de Planejamento, Auditor')
def acao_busca(request):
    form = AcaoBuscaForm(request.POST or None)

    title = 'Consulta de Ações'
    if form.is_valid():
        titulo = request.POST['titulo']
        ano_base = request.POST['ano_base']
        if ano_base:
            if in_group(request.user, ['Coordenador de Planejamento Sistêmico']):
                acoes = Acao.objects.select_related('meta_unidade__unidade', 'unidade_medida').filter(
                    titulo__icontains=titulo,
                    meta_unidade__meta__objetivo_estrategico__configuracao__id=ano_base,
                    meta_unidade__meta__objetivo_estrategico__dimensao__setor_sistemico=get_setor_unidade_administrativa(request.user),
                )
            else:
                acoes = Acao.objects.select_related('meta_unidade__unidade', 'unidade_medida').filter(
                    titulo__icontains=titulo, meta_unidade__meta__objetivo_estrategico__configuracao__id=ano_base
                )
            acoes = acoes.order_by('meta_unidade__unidade__setor_equivalente__sigla', 'titulo')
        else:
            if in_group(request.user, ['Coordenador de Planejamento Sistêmico']):
                acoes = Acao.objects.select_related('meta_unidade__unidade', 'unidade_medida').filter(
                    titulo__icontains=titulo,
                    meta_unidade__meta__objetivo_estrategico__dimensao__setor_sistemico=get_setor_unidade_administrativa(request.user),
                )
            else:
                acoes = Acao.objects.select_related('meta_unidade__unidade', 'unidade_medida').filter(titulo__icontains=titulo)
            acoes = acoes.order_by('meta_unidade__unidade__configuracao', 'titulo')

    gerente_campus = in_group(request.user, ['Coordenador de Planejamento'])
    administrador = in_group(request.user, ['Administrador de Planejamento'])
    return locals()


@rtr('planejamento/templates/metaunidade_acoes.html')
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico,Coordenador de Planejamento')
def acao_old(request, id_meta_unidade, id_acao):
    meta_unidade = MetaUnidade.objects.get(id=id_meta_unidade)
    acao = Acao.objects.get(id=id_acao)

    # indica quais as ações propostas e quais destas já foram importadas
    acoes_propostas = MetaUnidadeAcaoProposta.objects.filter(meta_unidade=meta_unidade).extra(
        select={
            'importada': f'select 1 from planejamento_acao \
                            where meta_unidade_id={meta_unidade.id} and \
                            acao_indutora_id=planejamento_metaunidadeacaoproposta.id'
        }
    )

    if request.method == 'POST':
        form = AcaoForm(request.POST, instance=acao, request=request)
        if form.is_valid():
            form.save()
            return httprr(f'/planejamento/metaunidade/{id_meta_unidade}/acoes/', 'Ação editada com sucesso.')
    else:
        form = AcaoForm(instance=acao, request=request)

    return locals()


@rtr('planejamento/templates/acao_view.html')
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico,Coordenador de Planejamento, Auditor, Servidor')
def acao_view(request, id):
    try:
        acao = Acao.objects.get(pk=id)
        setor_usuario = get_setor_unidade_administrativa(request.user)

        # verifica se o usuário tem permissão para visualizar a atividade
        if (acao.meta_unidade.unidade.setor_equivalente != setor_usuario and in_group(request.user, ['Coordenador de Planejamento', 'Servidor'])) or (
            acao.meta_unidade.meta.objetivo_estrategico.dimensao.setor_sistemico != setor_usuario
            and in_group(request.user, ['Coordenador de Planejamento Sistêmico'])
        ):
            erro = 'O usuário não possui permissão para visualizar a ação.'
    except Exception:
        erro = 'Não foi encontrada ação para o código informado.'

    return locals()


@rtr('planejamento/templates/acao_detalhes_validacao.html')
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico')
def acaovalidacao_view(request, id):
    try:
        acao = Acao.objects.get(pk=id)
        setor_usuario = get_setor_unidade_administrativa(request.user)
    except Exception:
        erro = 'Não foi encontrada ação para o código informado.'

    return locals()


@rtr('planejamento/templates/acao_atividades.html')
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico,Coordenador de Planejamento')
def acao_remover_old(request, id_meta_unidade, id_acao):
    meta_unidade = MetaUnidade.objects.get(id=id_meta_unidade)
    acao = Acao.objects.get(id=id_acao)
    configuracao = meta_unidade.meta.objetivo_estrategico.configuracao

    if configuracao.periodo_campus():
        if acao.atividade_set.exists():
            return httprr(
                f'/planejamento/metaunidade/{id_meta_unidade}/acoes/',
                'Não é possível efetuar a operação. Existe(m) atividade(s) cadastrada(s) para essa ação.',
            )
        if not request.user.has_perm('planejamento.delete_acao'):
            return httprr(f'/planejamento/metaunidade/{id_meta_unidade}/acoes/', 'Você não tem permissão para remover ações.')
        acao.delete()
    else:
        return httprr(f'/planejamento/metaunidade/{id_meta_unidade}/acoes/', 'O período para remoção de ações expirou.')
    return httprr(f'/planejamento/metaunidade/{id_meta_unidade}/acoes/', 'A ação foi removida.')


@rtr('planejamento/templates/acao_atividades.html')
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico,Coordenador de Planejamento')
def acao_atividades(request, id):
    acao = Acao.objects.get(pk=id)
    meta_unidade = acao.meta_unidade
    saldo = meta_unidade.unidade.get_saldo_proprio()
    unidade = meta_unidade.unidade
    ids_atividades = ''
    for i, id_atividade in enumerate(Atividade.objects.filter(acao__meta_unidade__unidade=unidade).values_list('id', flat=True)):
        if i == 0:
            ids_atividades += str(id_atividade)
        else:
            ids_atividades += ',' + str(id_atividade)

    if request.method == 'POST':
        form = AtividadeForm(request.POST, id_acao=id, request=request)
        if form.is_valid():
            form.save()
            return httprr(f'/planejamento/acao/{id}/atividades/', 'Atividade cadastrada com sucesso.')
    else:
        form = AtividadeForm(id_acao=id, request=request)

    return locals()


@rtr('planejamento/templates/acao_atividades.html')
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico,Coordenador de Planejamento')
def atividade_old(request, id_acao, id_atividade):
    acao = Acao.objects.get(pk=id_acao)
    meta_unidade = acao.meta_unidade

    # verifica se o usuário está tentando editar uma atividade diretamente pela url
    try:
        atividade = Atividade.objects.get(pk=id_atividade, acao=acao)
    except Exception:
        return httprr(f'/planejamento/acao/{id_acao}/atividades/', 'Atividade não encontrada.')

    ids_atividades = ''
    for i, id_atividade_unidade in enumerate(
        Atividade.objects.filter(acao__meta_unidade__unidade=acao.meta_unidade.unidade).values_list('id', flat=True)
    ):
        if i == 0:
            ids_atividades += str(id_atividade_unidade)
        else:
            ids_atividades += ',' + str(id_atividade_unidade)

    if ids_atividades != '':
        # verifica os totais gastos para cadas tipo de fonte de recurso
        strConsulta = f"""select a.tipo_recurso_id as id_recurso, o.nome as recurso, sum(quantidade*valor_unitario) as total
                                from planejamento_atividade a, planejamento_origemrecurso o
                                where o.id = a.tipo_recurso_id and
                                      a.id in ({ids_atividades}) and
                                      a.tipo_recurso_id is not null
                                group by a.tipo_recurso_id, o.nome
                                order by o.nome;"""
        despesas = db.get_dict(strConsulta)
        total_despesas = sum([recurso['total'] for recurso in despesas])

    if request.method == 'POST':
        form = AtividadeForm(request.POST, instance=atividade, request=request)
        if form.is_valid():
            form.save()
            return httprr(f'/planejamento/acao/{id_acao}/atividades/', 'Atividade editada com sucesso.')
    else:
        form = AtividadeForm(instance=atividade, request=request)
    return locals()


@rtr('planejamento/templates/atividade_view.html')
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico,Coordenador de Planejamento,Servidor, Auditor')
def atividade_view(request, id):
    try:
        atividade = Atividade.objects.get(pk=id)
        setor_usuario = get_setor_unidade_administrativa(request.user)

        # verifica se o usuário tem permissão para visualizar a atividade
        if (
            atividade.acao.meta_unidade.unidade.setor_equivalente != setor_usuario
            and in_group(request.user, ['Coordenador de Planejamento', 'Servidor'])
        ) or (
            atividade.acao.meta_unidade.meta.objetivo_estrategico.dimensao.setor_sistemico != setor_usuario
            and in_group(request.user, ['Coordenador de Planejamento Sistêmico'])
        ):
            erro = 'O usuário não possui permissão para visualizar a atividade.'
    except Exception:
        erro = 'Não foi encontrada atividade para o código informado.'

    return locals()


@rtr('planejamento/templates/acao_atividades.html')
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico,Coordenador de Planejamento')
def atividade_remover_old(request, id_acao, id_atividade):
    atividade = Atividade.objects.get(pk=id_atividade)
    configuracao = atividade.acao.meta_unidade.meta.objetivo_estrategico.configuracao

    descricao = atividade.descricao

    if configuracao.periodo_campus():
        if not request.user.has_perm('planejamento.delete_atividade'):
            return httprr(f'/planejamento/acao/{id_acao}/atividades/', 'Você não tem permissão para remover atividades.')
        atividade.delete()
    else:
        if atividade.acao.status != Situacao.PARCIALMENTE_DEFERIDA:
            return httprr(f'/planejamento/acao/{id_acao}/atividades/', 'O período para remoção de atividades expirou.')
        else:
            # se a acao estiver pendente as suas atividades podem ser removidas
            atividade.delete()

    return httprr(f'/planejamento/acao/{id_acao}/atividades/', f'Atividade "{descricao}" removida com sucesso.')


@rtr('planejamento/templates/planilhas.html')
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico, Auditor')
def planilhas(request):
    title = 'Planilhas de Materiais'

    configuracoes = Configuracao.objects.all().order_by('-ano_base__ano')
    if not len(configuracoes):
        mensagem = 'Não existe período de vigência de planejamento cadastrado.'
        return locals()

    # verifica se foi repassado alguma configuracao ou pega o id do ultimo ano base cadastrado
    if 'configuracao' in request.GET and request.GET['configuracao'] != '':
        configuracao = Configuracao.objects.get(pk=int(request.GET['configuracao']))
    else:
        configuracao = configuracoes[0]

    configuracao_form = ConfiguracaoFiltroForm(id_config=configuracao.id)

    DIR_ARQ = settings.BASE_DIR + '/planejamento/arquivos/planilhas/'
    EXTENSOES_PERMITIDAS = ('.xls', '.xlsx', '.ods')

    # verifica se existe um arquivo para este campus
    planilhas = []
    for arquivo in os.listdir(DIR_ARQ):
        # consulta os arquivos pelas extensões e com o ano base informado
        if (
            any(str.find(arquivo.lower(), ext) != -1 for ext in EXTENSOES_PERMITIDAS)
            and str.find(arquivo.lower(), f'.{configuracao.ano_base.ano}.') != -1
        ):
            params = arquivo.split('.')
            data_cadastro = params[3].split('-')

            campus = Setor.objects.suap_ativos().get(pk=int(params[0]))
            usuario = User.objects.get(username=params[1])
            data = datetime(
                int(data_cadastro[2]),
                int(data_cadastro[1]),
                int(data_cadastro[0]),
                int(data_cadastro[3]),
                int(data_cadastro[4]),
                int(data_cadastro[5]),
            )

            planilha = {}
            planilha['campus'] = campus
            planilha['responsavel'] = usuario
            planilha['data'] = data
            planilha['nome_arquivo'] = '.'.join(params[4:-1]).replace('_', ' ')
            planilha['arquivo'] = arquivo

            planilhas.append({'chave': campus.nome, 'dados_envio': planilha})

    planilhas.sort()
    return locals()


@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico,Coordenador de Planejamento, Auditor')
def baixar_planilha(request):
    try:
        arquivo = request.GET['a']

        DIR_ARQ = settings.BASE_DIR + '/planejamento/arquivos/planilhas/'
        get_setor_unidade_administrativa(request.user)

        # encontra a extensão do arquivo que foi enviado
        nome_arq = arquivo.split('.')
        extensao = nome_arq[len(nome_arq) - 1]

        with open(DIR_ARQ + arquivo) as f:
            content = f.read()
        response = HttpResponse(content, content_type='application/force-download')
        response['Content-Disposition'] = 'attachment; filename=%s' % ('.'.join(nome_arq[4:-1]).encode('ASCII', 'replace') + '.' + extensao)
    except Exception as e:
        raise e
    return response


@group_required('Coordenador de Planejamento')
def remover_planilha(request):
    try:
        arquivo = request.GET['a']

        DIR_ARQ = settings.BASE_DIR + '/planejamento/arquivos/planilhas/'
        get_setor_unidade_administrativa(request.user)

        os.remove(DIR_ARQ + arquivo)
        log = Log(
            titulo='Planejamento: planilha removida',
            texto='o usuário {} removeu a planilha: "{}" [{}]'.format(request.user, '.'.join(arquivo.split('.')[4:]).replace('_', ' '), arquivo),
        )
        log.save()
    except Exception as e:
        raise e

    return httprr('/planejamento/planilhas/carregar/', 'Planilha removida com sucesso')


@rtr('planejamento/templates/campi_validar.html')
@group_required('Coordenador de Planejamento Sistêmico,Administrador de Planejamento')
def campi_validar(request):
    configuracoes = Configuracao.objects.all().order_by('-ano_base__ano')
    if not len(configuracoes):
        erro = 'Não existe período de vigência de planejamento cadastrado.'
        return locals()

    # verifica se foi repassado alguma configuracao ou pega o id do ultimo ano base cadastrado
    if 'configuracao' in request.POST and request.POST['configuracao'] != '':
        configuracao = Configuracao.objects.get(pk=int(request.POST['configuracao']))
    else:
        configuracao = configuracoes[0]

    configuracao_form = ConfiguracaoFiltroForm(id_config=configuracao.id)

    sistemico = ''
    if in_group(request.user, ['Coordenador de Planejamento Sistêmico']):
        sistemico = f'and d.setor_sistemico_id = {get_setor_unidade_administrativa(request.user).id}'
    strConsulta = f"""select mu.unidade_id as id, s.nome as nome,
                           sum(CASE WHEN a.status = 'Deferida' THEN 1 END) as deferidas,
                           sum(CASE WHEN a.status = 'Indeferida' THEN 1 END) as indeferidas,
                           sum(CASE WHEN a.status = 'Pendente' or a.status = 'Parcialmente Deferida' THEN 1 END) as pendentes,
                           count(a.status) as total
                        from planejamento_metaunidade mu left join planejamento_acao a on mu.id = a.meta_unidade_id,
                             planejamento_unidadeadministrativa u, setor s, planejamento_meta m,
                             planejamento_objetivoestrategico o, planejamento_dimensao d,
                             planejamento_configuracao c
                        where u.id = mu.unidade_id and
                              s.id = u.setor_equivalente_id and
                              m.id = mu.meta_id and
                              o.id = m.objetivo_estrategico_id and
                              c.id = o.configuracao_id and
                              c.id = {configuracao.id} and
                              d.id = o.dimensao_id
                              {sistemico}
                        group by mu.unidade_id, s.nome
                        order by upper(s.nome);"""

    campi = db.get_dict(strConsulta)
    return locals()


@rtr('planejamento/templates/metas_validar.html')
@group_required('Coordenador de Planejamento Sistêmico,Administrador de Planejamento')
def metas_unidade_validar(request, id_campus):
    campus = UnidadeAdministrativa.objects.get(id=id_campus)
    sistemico = ''
    if in_group(request.user, ['Coordenador de Planejamento Sistêmico']):
        sistemico = f'and d.setor_sistemico_id = {get_setor_unidade_administrativa(request.user).id}'
    strConsulta = f"""select u.id as unidade_administrativa, mu.id as id, m.titulo as titulo,
                           sum(CASE WHEN a.status = 'Deferida' THEN 1 END) as deferidas,
                           sum(CASE WHEN a.status = 'Indeferida' THEN 1 END) as indeferidas,
                           sum(CASE WHEN a.status = 'Pendente' or a.status = 'Parcialmente Deferida' THEN 1 END) as pendentes,
                           count(a.status) as total
                        from planejamento_metaunidade mu left join planejamento_acao a on mu.id = a.meta_unidade_id,
                             planejamento_unidadeadministrativa u, setor s, planejamento_meta m,
                             planejamento_objetivoestrategico o, planejamento_dimensao d
                        where u.id = mu.unidade_id and
                              s.id = u.setor_equivalente_id and
                              m.id = mu.meta_id and
                              o.id = m.objetivo_estrategico_id and
                              d.id = o.dimensao_id
                              {sistemico} and
                              u.id = {id_campus}
                        group by u.id, mu.id, m.titulo
                        order by upper(m.titulo);"""

    metas = db.get_dict(strConsulta)
    return locals()


@rtr()
@group_required('Coordenador de Planejamento Sistêmico,Administrador de Planejamento')
@transaction.atomic
def validacao_confirmar(request, id_acao, id_meta_unidade):
    acao = Acao.objects.get(id=id_acao)
    meta_unidade = MetaUnidade.objects.get(id=id_meta_unidade)
    if acao.status == 'Deferida' and not in_group(request.user, 'Administrador de Planejamento'):
        mensagem = 'Ação Deferida. Não é possível avaliar novamente!'
        return locals()

    if request.method == 'POST':
        form = ConfirmacaoForm(request.POST, id_acao=id_acao)
        params = request.POST
        if form.is_valid():
            status_acao = form.cleaned_data['status_acao']
            acao.status = status_acao
            acao.save()

            if status_acao != Situacao.DEFERIDA:
                comentario_acao = form.cleaned_data['comentario_acao']
                AcaoValidacao.objects.create(acao=acao, status=status_acao)
                content_type = ContentType.objects.get(app_label=acao._meta.app_label, model=acao._meta.model_name)
                Comentario.objects.create(texto=comentario_acao, content_type=content_type, object_id=acao.id, resposta=None)
            msg = 'Ação validada com sucesso.'
            return httprr('..', msg)
    else:
        form = ConfirmacaoForm(id_acao=id_acao)
    return locals()


@rtr('planejamento/templates/acoes_validar.html')
@group_required('Coordenador de Planejamento Sistêmico,Administrador de Planejamento')
def acoes_validar(request, id_meta_unidade):
    meta_unidade = MetaUnidade.objects.get(id=id_meta_unidade)

    # indica se ainda é possível cadastrar acões por parte dos campi
    # caso seja possível, o sistêmico não poderá importar uma ação em nome do campus
    periodo_cadastro_campus = False
    configuracao = meta_unidade.meta.objetivo_estrategico.configuracao
    if date.today() >= configuracao.data_acoes_inicial and date.today() <= configuracao.data_acoes_final:
        periodo_cadastro_campus = True

    periodo_validacao_sistemico = False
    if date.today() >= configuracao.data_validacao_inicial and date.today() <= configuracao.data_validacao_final:
        periodo_validacao_sistemico = True

    if request.method == 'POST':
        params = request.POST
        cont_validacao = 0
        # identifica as acoes e associa os comentarios de cada uma, caso existam
        for param in params:
            # indica que o parametro representa o status da acao
            if param.find('comentario_') == -1:
                try:
                    acao = Acao.objects.get(id=param)
                    status_acao = request.POST[str(acao.id)]
                    comentario_acao = request.POST['comentario_' + str(acao.id)]

                    validacoes = AcaoValidacao.objects.filter(acao=acao)

                    if acao.status != status_acao or (len(validacoes) and validacoes.latest().texto != comentario_acao):
                        AcaoValidacao.objects.create(acao=acao, texto=comentario_acao, status=status_acao)
                        acao.status = status_acao
                        acao.save()
                        cont_validacao += 1
                # evita que o parâmetro expasible presente devido a template tag box seja lida e interpretada como um codigo de acao
                except ValueError:
                    pass

        if cont_validacao == 1:
            msg = 'Ação validada com sucesso.'
        else:
            msg = f'{cont_validacao} ações foram validadas com sucesso.'

        return httprr(f'/planejamento/metaunidade/{meta_unidade.id}/validar/', msg)
    sistemico = ''
    if in_group(request.user, ['Coordenador de Planejamento Sistêmico']):
        sistemico = f'and d.setor_sistemico_id = {get_setor_unidade_administrativa(request.user).id}'
    strNaoImportadas = f"""select ap.id, ap.titulo, muap.id as id_acaoproposta_metaunidade, muap.quantidade, muap.valor_unitario*muap.quantidade as valor_total
                                from planejamento_metaunidade mu, planejamento_acaoproposta ap,
                                     planejamento_metaunidadeacaoproposta muap left join planejamento_acao a on muap.id = a.acao_indutora_id,
                                     planejamento_meta m, planejamento_objetivoestrategico o, planejamento_dimensao d
                                where mu.id = muap.meta_unidade_id and
                                      ap.id = muap.acao_proposta_id and
                                      m.id = mu.meta_id and
                                      m.id = ap.meta_id and
                                      o.id = m.objetivo_estrategico_id and
                                      d.id = o.dimensao_id and
                                      a.acao_indutora_id is null {sistemico} and
                                      mu.id = {id_meta_unidade}
                                order by upper(ap.titulo);"""

    acoes_nao_importadas = db.get_dict(strNaoImportadas)

    strConsulta = f"""select a.id as id, a.titulo as titulo, a.status as status, a.quantidade as quantidade, um.nome as unidade_medida
                        from planejamento_metaunidade mu, planejamento_acao a left join planejamento_acaovalidacao v on a.id = v.acao_id,
                             planejamento_meta m, planejamento_objetivoestrategico o, planejamento_dimensao d, planejamento_unidademedida um
                        where m.id = mu.meta_id and
                              mu.id = a.meta_unidade_id and
                              um.id = a.unidade_medida_id and
                              o.id = m.objetivo_estrategico_id and
                              d.id = o.dimensao_id
                              {sistemico} and
                              mu.id = {id_meta_unidade}
                        group by a.id, a.titulo, a.status, a.quantidade, um.nome
                        order by upper(a.titulo);"""

    acoes = db.get_dict(strConsulta)
    valor_total_acoes = 0
    for acao in acoes:
        strConsAtividades = """select at.descricao, u.nome as unidade_medida, n.codigo as cod_natureza_despesa,
                                     n.nome as desc_natureza_despesa, at.tipo_recurso_id as id_recurso, og.nome as tipo_recurso,
                                     at.quantidade as quantidade, at.valor_unitario as valor_unitario,
                                     sum(at.quantidade * at.valor_unitario) as valor_total
                                    from planejamento_acao a, planejamento_atividade at left join financeiro_naturezadespesa n
                                         on at.elemento_despesa_id = n.id left join planejamento_origemrecurso og
                                         on at.tipo_recurso_id = og.id,
                                         planejamento_unidademedida u
                                    where at.acao_id = a.id and
                                          at.unidade_medida_id = u.id and
                                          a.id = {}
                                    group by at.descricao, u.nome, n.codigo, n.nome, at.tipo_recurso_id, og.nome, at.quantidade, at.valor_unitario
                                    order by at.descricao;""".format(acao['id'])
        atividades = db.get_dict(strConsAtividades)

        acao_ = Acao.objects.get(id=acao['id'])

        acao['valor_informado'] = acao_.get_valor_total()
        acao['quantidade_proposta'] = acao_.get_quantidade_proposta()
        acao['valor_referencia'] = acao_.get_valor_referencia()
        acao['atividades'] = atividades

        if acao['status'] == Situacao.DEFERIDA:
            valor_total_acoes = valor_total_acoes + acao['valor_informado']

    return locals()


@rtr('planejamento/templates/acoes_validacao.html')
@group_required('Coordenador de Planejamento Sistêmico,Coordenador de Planejamento')
def acoes_validacao(request):
    configuracoes = Configuracao.objects.all().order_by('-ano_base__ano')
    if not len(configuracoes):
        erro = 'Não existe período de vigência de planejamento cadastrado.'
        return locals()

    # verifica se foi repassado alguma configuracao ou pega o id do ultimo ano base cadastrado
    if 'configuracao' in request.GET and request.GET['configuracao'] != '':
        configuracao = Configuracao.objects.get(pk=int(request.GET['configuracao']))
    else:
        configuracao = configuracoes[0]

    configuracao_form = ConfiguracaoFiltroForm(id_config=configuracao.id)

    try:
        unidade_administrativa = UnidadeAdministrativa.objects.get(
            setor_equivalente=get_setor_unidade_administrativa(request.user), configuracao=configuracao
        )

        strDimensao = f"""select distinct d.id, d.descricao
                                from planejamento_dimensao d, planejamento_objetivoestrategico o, planejamento_meta m,
                                     planejamento_metaunidade mu, planejamento_acao a, planejamento_unidadeadministrativa u,
                                     planejamento_configuracao c
                                where d.id = o.dimensao_id and
                                      o.id = m.objetivo_estrategico_id and
                                      m.id = mu.meta_id and
                                      mu.id = a.meta_unidade_id and
                                      u.id = mu.unidade_id and
                                      u.id = {unidade_administrativa.id}
                                order by d.descricao;"""

        dimensoes = db.get_dict(strDimensao)

        for dimensao in dimensoes:
            strConsulta = """select mu.id as meta_unidade, a.id as id, a.titulo as titulo, a.quantidade as quantidade, um.nome as unidade_medida, a.status as status
                                from planejamento_metaunidade mu, planejamento_acao a left join planejamento_acaovalidacao v on a.id = v.acao_id,
                                     planejamento_unidadeadministrativa u, planejamento_unidademedida um, planejamento_meta m, planejamento_objetivoestrategico o,
                                     planejamento_dimensao d
                                where mu.id = a.meta_unidade_id and
                                      um.id = a.unidade_medida_id and
                                      u.id = mu.unidade_id and
                                      m.id = mu.meta_id and
                                      o.id = m.objetivo_estrategico_id and
                                      d.id = o.dimensao_id and
                                      d.id = {} and
                                      u.id = {}
                                group by mu.id, a.id, a.titulo, a.status, a.quantidade, um.nome
                                order by upper(a.titulo);""".format(
                dimensao['id'],
                unidade_administrativa.id,
            )

            acoes = db.get_dict(strConsulta)

            dimensao['acoes'] = acoes

        if not len(dimensoes):
            mensagem = 'Não existem ações cadastradas até o momento.'
    except ObjectDoesNotExist:
        mensagem = 'A unidade administrativa do usuário não está cadastrada para este ano base.'

    return locals()


@rtr('planejamento/templates/acompanhamento_sistemico.html')
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico, Auditor')
def acompanhamento_sistemico(request):
    title = 'Acompanhamento da Execução do Planejamento'
    setor_usuario = get_setor_unidade_administrativa(request.user)

    configuracoes = Configuracao.objects.all().order_by('-ano_base__ano')
    if not len(configuracoes):
        mensagem = 'Não existe período de vigência de planejamento cadastrado.'
        return locals()

    # verifica se foi repassado alguma configuracao ou pega o id do ultimo ano base cadastrado
    if 'configuracao' in request.GET and request.GET['configuracao'] != '':
        configuracao = Configuracao.objects.get(pk=int(request.GET['configuracao']))
    else:
        configuracao = configuracoes[0]

    configuracao_form = ConfiguracaoFiltroForm(id_config=configuracao.id)

    if in_group(request.user, ['Administrador de Planejamento', 'Auditor']):
        sql = f"""select u.id as id, s.nome as nome,
                        a.id as id_acao,
                        case when a.execucao = 100
                            then 'true'
                            else 'false'
                        end as acao_executada
                        from planejamento_objetivoestrategico o,
                            planejamento_meta m,
                            planejamento_metaunidade mu,
                            planejamento_unidadeadministrativa u,
                            planejamento_configuracao c,
                            setor s,
                            planejamento_acao a
                        where s.id = u.setor_equivalente_id
                            and o.id = m.objetivo_estrategico_id
                            and m.id = mu.meta_id
                            and u.id = mu.unidade_id
                            and c.id = u.configuracao_id
                            and mu.id = a.meta_unidade_id
                            and a.status = 'Deferida'
                            and c.id = {configuracao.id}
                        order by s.nome;"""
        unidades_administrativas = db.get_dict(sql)
        dimensao = None
    else:
        sql = f"""select u.id as id, s.nome as nome,
                        a.id as id_acao,
                        case when a.execucao = 100
                            then 'true'
                            else 'false'
                        end as acao_executada
                            from planejamento_dimensao d,
                            planejamento_objetivoestrategico o,
                            planejamento_meta m,
                            planejamento_metaunidade mu,
                            planejamento_unidadeadministrativa u,
                            planejamento_configuracao c,
                            setor s,
                            planejamento_acao a
                        where s.id = u.setor_equivalente_id
                            and d.id = o.dimensao_id
                            and o.id = m.objetivo_estrategico_id
                            and m.id = mu.meta_id
                            and u.id = mu.unidade_id
                            and c.id = u.configuracao_id
                            and mu.id = a.meta_unidade_id
                            and a.status = 'Deferida'
                            and d.setor_sistemico_id = {setor_usuario.id}
                            and c.id = {configuracao.id}
                        order by s.nome;"""
        unidades_administrativas = db.get_dict(sql)
        dimensoes = Dimensao.objects.filter(setor_sistemico=get_setor_unidade_administrativa(request.user))
        if len(dimensoes):
            dimensao = dimensoes[0]
        else:
            mensagem = 'Não existe dimensão associada a unidade administrativa do usuário.'

    return locals()


@rtr('planejamento/templates/acompanhamento_execucao.html')
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico,Coordenador de Planejamento, Auditor')
def acompanhamento_execucao(request):
    title = 'Acompanhamento de Execução'
    setor_usuario = get_setor_unidade_administrativa(request.user)
    unidade_administrativa = None

    if in_group(request.user, ['Coordenador de Planejamento']):
        configuracoes = Configuracao.objects.all().order_by('-ano_base__ano')
        if not len(configuracoes):
            mensagem = 'Não existe período de vigência de planejamento cadastrado.'
            return locals()

        # verifica se foi repassado alguma configuracao ou pega o id do ultimo ano base cadastrado
        if 'configuracao' in request.GET and request.GET['configuracao'] != '':
            configuracao = Configuracao.objects.get(pk=int(request.GET['configuracao']))
        else:
            configuracao = configuracoes[0]

        configuracao_form = ConfiguracaoFiltroForm(id_config=configuracao.id)
        try:
            # verifica se a unidade admin. foi cadastrada para o ano base atual
            unidade_administrativa = UnidadeAdministrativa.objects.get(setor_equivalente=setor_usuario, configuracao=configuracao)
        except Exception:
            pass
    else:
        if request.method == 'GET' and 'und' in request.GET:
            unidades = UnidadeAdministrativa.objects.filter(id=request.GET['und'])
            if not len(unidades):
                return httprr('/planejamento/acompanhamento/sistemico/')
            unidade_administrativa = unidades[0]
        else:
            return httprr('/planejamento/acompanhamento/sistemico/')

    if unidade_administrativa:
        # filtra a consulta de obj estrategicos, caso o usuário esteja logado como sistemico para apresentar a execucao apenas de sua dimensao
        if in_group(request.user, ['Coordenador de Planejamento Sistêmico']):
            sql = f"""select o.id as id, o.descricao as descricao,
                            a.id as id_acao,
                            case when a.execucao = 100
                                then 'true'
                                else 'false'
                            end as acao_executada,
                            coalesce(d.codigo::text,'x') || '.' || coalesce(o.codigo::text,'x') as codigo
                            from planejamento_dimensao d,
                                planejamento_objetivoestrategico o,
                                planejamento_meta m,
                                planejamento_metaunidade mu,
                                planejamento_unidadeadministrativa u,
                                planejamento_acao a
                            where d.id = o.dimensao_id
                                and o.id = m.objetivo_estrategico_id
                                and m.id = mu.meta_id
                                and u.id = mu.unidade_id
                                and mu.id = a.meta_unidade_id
                                and a.status = 'Deferida'
                                and d.setor_sistemico_id = {setor_usuario.id}
                                and u.id = {unidade_administrativa.id}
                            group by o.id, o.descricao,
                                    a.id, a.execucao,
                                    d.codigo, o.codigo;"""
        else:
            sql = f"""select o.id as id, o.descricao as descricao,
                            a.id as id_acao,
                            case when a.execucao = 100
                                then 'true'
                                else 'false'
                            end as acao_executada,
                            coalesce(d.codigo::text,'x') || '.' || coalesce(o.codigo::text,'x') as codigo
                            from planejamento_dimensao d,
                                planejamento_objetivoestrategico o,
                                planejamento_meta m,
                                planejamento_metaunidade mu,
                                planejamento_unidadeadministrativa u,
                                planejamento_acao a
                            where d.id = o.dimensao_id
                                and o.id = m.objetivo_estrategico_id
                                and m.id = mu.meta_id
                                and u.id = mu.unidade_id
                                and mu.id = a.meta_unidade_id
                                and a.status = 'Deferida'
                                and u.id = {unidade_administrativa.id}
                            group by o.id, o.descricao,
                                    a.id, a.execucao,
                                    d.codigo, o.codigo;"""
        objs_estrategicos = db.get_dict(sql)
    return locals()


@rtr('planejamento/templates/acompanhamento_objetivoestrategico.html')
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico,Coordenador de Planejamento, Auditor')
def acompanhamento_objetivoestrategico(request, id_obj_estrategico):
    title = 'Acompanhamento de Objetivo Estratégico'
    obj_estrategico = ObjetivoEstrategico.objects.get(id=id_obj_estrategico)

    if in_group(request.user, ['Coordenador de Planejamento']):
        unidade_administrativa = UnidadeAdministrativa.objects.get(
            setor_equivalente=get_setor_unidade_administrativa(request.user), configuracao=obj_estrategico.configuracao
        )
    else:
        if request.method == 'GET' and 'und' in request.GET:
            unidades = UnidadeAdministrativa.objects.filter(id=request.GET['und'])
            if not len(unidades):
                return httprr('/planejamento/acompanhamento/sistemico/')
            unidade_administrativa = unidades[0]
        else:
            return httprr('/planejamento/acompanhamento/sistemico/')

    sql = f"""select distinct(mu.id)
                    from planejamento_objetivoestrategico o,
                        planejamento_meta m,
                        planejamento_metaunidade mu,
                        planejamento_unidadeadministrativa u,
                        planejamento_acao a
                    where o.id = m.objetivo_estrategico_id
                        and m.id = mu.meta_id
                        and u.id = mu.unidade_id
                        and mu.id = a.meta_unidade_id
                        and a.status = 'Deferida'
                        and o.id = {obj_estrategico.id}
                        and u.id = {unidade_administrativa.id};"""
    ids_meta_unidades = db.get_list(sql)
    meta_unidades = MetaUnidade.objects.filter(id__in=ids_meta_unidades)
    return locals()


@rtr('planejamento/templates/acompanhamento_metaunidade.html')
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico,Coordenador de Planejamento, Auditor')
def acompanhamento_metaunidade(request, id_metaunidade):
    title = 'Acompanhamento de Meta Unidade'
    meta_unidade = MetaUnidade.objects.get(id=id_metaunidade)
    acoes = Acao.objects.filter(meta_unidade=meta_unidade, status='Deferida').order_by(
        'meta_unidade__meta__objetivo_estrategico__dimensao__codigo',
        'meta_unidade__meta__objetivo_estrategico__codigo',
        'meta_unidade__meta__codigo',
        'codigo',
        'titulo',
    )
    setor_usuario = get_setor_unidade_administrativa(request.user)
    if in_group(request.user, ['Coordenador de Planejamento']):
        unidade_administrativa = UnidadeAdministrativa.objects.get(
            setor_equivalente=setor_usuario, configuracao=meta_unidade.meta.objetivo_estrategico.configuracao
        )
        registrar_execucao = True
    else:
        unidade_administrativa = UnidadeAdministrativa.objects.get(id=meta_unidade.unidade.id)

        # permite que o sistemico possa registrar as execuções de sua unidade administrativa
        if unidade_administrativa.setor_equivalente == setor_usuario:
            registrar_execucao = True

    return locals()


@rtr('planejamento/templates/acompanhamento_acao_atividades.html')
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico,Coordenador de Planejamento')
def acompanhamento_acao_atividades(request, id_acao):
    acao = Acao.objects.get(pk=id_acao)
    setor_usuario = get_setor_unidade_administrativa(request.user)
    if in_group(request.user, ['Coordenador de Planejamento']):
        unidade_administrativa = UnidadeAdministrativa.objects.get(
            setor_equivalente=setor_usuario, configuracao=acao.meta_unidade.meta.objetivo_estrategico.configuracao
        )
        registrar_execucao = True
    else:
        unidade_administrativa = UnidadeAdministrativa.objects.get(id=acao.meta_unidade.unidade.id)

        # permite que o sistemico possa registrar as execuções de sua unidade administrativa
        if unidade_administrativa.setor_equivalente == setor_usuario:
            registrar_execucao = True

    return locals()


@rtr('planejamento/templates/acompanhamento_acao.html')
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico,Coordenador de Planejamento')
def acompanhamento_acao(request, id_acao):
    title = 'Acompanhamento da Execução da Ação'
    acao = Acao.objects.get(id=id_acao)
    configuracao = acao.meta_unidade.meta.objetivo_estrategico.configuracao
    acompanhamentos = AcaoExecucao.objects.filter(acao=acao)
    unidade_administrativa = UnidadeAdministrativa.objects.get(
        setor_equivalente=get_setor_unidade_administrativa(request.user), configuracao=configuracao
    )

    if request.method == 'POST':
        form = AcaoExecucaoForm(request.POST, id_acao=id_acao)
        if form.is_valid():
            form.save()
            if in_group(request.user, ['Coordenador de Planejamento']):
                return httprr(f'/planejamento/acompanhamento/metaunidade/{acao.meta_unidade.id}/', 'Registro de execução realizado com sucesso.')
            else:
                return httprr(
                    f'/planejamento/acompanhamento/metaunidade/{acao.meta_unidade.id}/?und={unidade_administrativa.id}',
                    'Registro de execução realizado com sucesso.',
                )
    else:
        form = AcaoExecucaoForm(id_acao=id_acao)
    return locals()


@rtr('planejamento/templates/acompanhamento_acao_detalhes.html')
@group_required('Administrador de Planejamento, Coordenador de Planejamento Sistêmico')
def acompanhamento_acao_detalhar(request, id_acao):
    acao = Acao.objects.get(id=id_acao)
    detalhes = AcaoExecucao.objects.filter(acao=id_acao)

    return locals()


@rtr('planejamento/templates/acompanhamento_atividade.html')
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico,Coordenador de Planejamento')
def acompanhamento_atividade(request, id_atividade):
    atividade = Atividade.objects.get(id=id_atividade)
    configuracao = atividade.acao.meta_unidade.meta.objetivo_estrategico.configuracao
    acompanhamentos = AtividadeExecucao.objects.filter(atividade=atividade)
    unidade_administrativa = UnidadeAdministrativa.objects.get(
        setor_equivalente=get_setor_unidade_administrativa(request.user), configuracao=configuracao
    )
    title = 'Acompanhamento da Execução da Atividade'
    if request.method == 'POST':
        form = AtividadeExecucaoForm(request.POST, id_atividade=id_atividade)
        if form.is_valid():
            form.save()
            if in_group(request.user, ['Coordenador de Planejamento']):
                return httprr(
                    f'/planejamento/acompanhamento/metaunidade/{atividade.acao.meta_unidade.id}/',
                    'Registro de execução realizado com sucesso.',
                )
            else:
                return httprr(
                    f'/planejamento/acompanhamento/metaunidade/{atividade.acao.meta_unidade.id}/?und={unidade_administrativa.id}',
                    'Registro de execução realizado com sucesso.',
                )
    else:
        form = AtividadeExecucaoForm(id_atividade=id_atividade)
    return locals()


@rtr('planejamento/templates/acompanhamento_atividade_detalhes.html')
@group_required('Administrador de Planejamento, Coordenador de Planejamento Sistêmico')
def acompanhamento_atividade_detalhar(request, id_atividade):
    atividade = Atividade.objects.get(id=id_atividade)
    detalhes = AtividadeExecucao.objects.filter(atividade=atividade)

    return locals()


# relatorios -----------------------------------------------------------------------------------------------------------------------


@rtr('planejamento/templates/relatorio/geral.html')
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico, Auditor')
def relatorio_geral(request):
    title = 'Metas e Ações'
    configuracoes = Configuracao.objects.all().order_by('-ano_base__ano')
    if not len(configuracoes):
        erro = 'Não existe período de vigência de planejamento cadastrado.'
        return locals()
    if 'configuracao' in request.POST:
        configuracao = Configuracao.objects.get(pk=request.POST['configuracao'])
    else:
        configuracao = Configuracao.objects.all().order_by('-ano_base__ano')[0]
    form = ConfiguracaoFiltroForm(id_config=configuracao.id)

    strDimensao = """select d.id, d.descricao, s.nome as nome_setor, coalesce(d.codigo,0) as codigo, s.sigla as sigla_setor
                            from planejamento_dimensao d, setor s
                            where d.setor_sistemico_id = s.id
                            order by d.codigo, upper(descricao);"""
    dimensoes = db.get_dict(strDimensao)

    for ed, dimensao in enumerate(dimensoes):
        dimensao['indice'] = ed + 1

        strConsulta = """select o.id, o.descricao, coalesce(o.codigo,0) as codigo
                                from planejamento_objetivoestrategico o, planejamento_configuracao c
                                where c.id = o.configuracao_id and
                                      c.id = {} and
                                      o.dimensao_id = {}
                                order by o.codigo, upper(o.descricao);""".format(
            configuracao.id,
            dimensao['id'],
        )
        objetivos_estrategicos = db.get_dict(strConsulta)

        for eo, objetivo_estrategico in enumerate(objetivos_estrategicos):
            objetivo_estrategico['indice'] = eo + 1

            strConsMetas = """select m.id, coalesce(m.codigo,0) as codigo, m.titulo, m.justificativa, m.data_inicial, m.data_final, u.nome as unidade_medida
                                from planejamento_meta m, planejamento_unidademedida u
                                where m.unidade_medida_id = u.id and
                                      m.objetivo_estrategico_id = {}
                                order by m.codigo, m.titulo;""".format(objetivo_estrategico['id'])
            metas = db.get_dict(strConsMetas)

            for em, meta in enumerate(metas):
                meta['indice'] = em + 1

                strAcoes = """select t.* from
                                    (select count(titulo) as num_unidades,
                                           codigo, titulo, unidade_medida, sum(quantidade) as quantidade,
                                           data_inicial, data_final, sum(valor) as valor
                                           from (select coalesce(ap.codigo,0) as codigo, ap.titulo, um.nome as unidade_medida, a.quantidade as quantidade,
                                                           coalesce(ap.data_inicial, m.data_inicial) as data_inicial, coalesce(ap.data_final, m.data_final) as data_final,
                                                           (select coalesce(sum(at.quantidade*at.valor_unitario), 0.00)
                                                                    from planejamento_atividade at
                                                                    where a.id = at.acao_id) as valor
                                                        from planejamento_meta m, planejamento_acaoproposta ap, planejamento_unidademedida um,
                                                             planejamento_metaunidadeacaoproposta muap, planejamento_acao a
                                                        where m.id = ap.meta_id and
                                                              ap.id = muap.acao_proposta_id and
                                                              um.id = ap.unidade_medida_id and
                                                              muap.id = a.acao_indutora_id and
                                                              a.status = 'Deferida' and
                                                              a.acao_indutora_id is not null and
                                                              m.id = {}) t
                                        group by codigo, titulo, unidade_medida,
                                                 data_inicial, data_final
                                    union
                                    select 1 as num_unidades,
                                             coalesce(a.codigo,0) as codigo, a.titulo, um.nome as unidade_medida, a.quantidade as quantidade,
                                             coalesce(a.data_inicial, m.data_inicial) as data_inicial, coalesce(a.data_final, m.data_final) as data_final,
                                             coalesce(sum(at.quantidade*at.valor_unitario), 0.00) as valor
                                          from planejamento_meta m, planejamento_metaunidade mu, planejamento_unidademedida um,
                                               planejamento_acao a left join planejamento_atividade at
                                               on a.id = at.acao_id
                                          where m.id = mu.meta_id and
                                                mu.id = a.meta_unidade_id and
                                                 um.id = a.unidade_medida_id and
                                                a.status = 'Deferida' and
                                                a.acao_indutora_id is null and
                                                m.id = {}
                                          group by a.codigo, a.titulo, um.nome, a.quantidade,
                                                   a.data_inicial, a.data_final,
                                                   m.data_inicial, m.data_final) t
                                    order by t.codigo, upper(t.titulo);""".format(
                    meta['id'],
                    meta['id'],
                )

                acoes = db.get_dict(strAcoes)

                for ea, acao in enumerate(acoes):
                    acao['indice'] = ea + 1
                meta['acoes'] = acoes

            objetivo_estrategico['metas'] = metas

        dimensao['objetivos_estrategicos'] = objetivos_estrategicos

    return locals()


@rtr('planejamento/templates/relatorio/geral_acao_orcamento.html')
@group_required('Administrador de Planejamento, Auditor')
def relatorio_geral_acao_orcamento(request):
    """este relatório depende de informações cadastradas no módulo de orçamento. informações sobre o qdd"""

    title = 'Relatório Geral por Ações do Orçamento'
    if 'orcamento' not in settings.INSTALLED_APPS:
        erro = 'Este relatório não pode ser apresentado sem informações do módulo de orçamento.'
        return locals()

    configuracoes = Configuracao.objects.all().order_by('-ano_base__ano')
    if not len(configuracoes):
        erro = 'Não existe período de vigência de planejamento cadastrado.'
        return locals()
    if 'configuracao' in request.POST:
        configuracao = Configuracao.objects.get(pk=request.POST['configuracao'])
    else:
        configuracao = Configuracao.objects.all().order_by('-ano_base__ano')[0]
    form = ConfiguracaoFiltroForm(id_config=configuracao.id)

    str = f"""select acao_orcamento_id, acao_orcamento_codigo,
                    acao_orcamento_nome, acao_orcamento_unidademedida,
                    acao_orcamento_quantidade, acao_titulo,
                    sum(acao_valor) as valor
                    from (select pro.codigo || '.' || fac.codigo_acao as acao_orcamento_codigo, fac.id as acao_orcamento_id,
                        fac.nome as acao_orcamento_nome, oum.nome as acao_orcamento_unidademedida,
                        epf.quantidade as acao_orcamento_quantidade, aca.titulo as acao_titulo,
                        coalesce(sum(ati.quantidade * ati.valor_unitario), 0.00) as acao_valor
                        from planejamento_atividade ati, planejamento_acao aca, planejamento_metaunidade mun,
                            planejamento_meta met, planejamento_objetivoestrategico obj, planejamento_configuracao con, comum_ano an1,
                            financeiro_acao fac, financeiro_programatrabalho ptr,
                            orcamento_estruturaprogramaticafinanceira epf left outer join orcamento_unidademedida oum
                            on oum.id = epf.unidade_medida_id,
                            comum_ano an2, financeiro_programa pro
                        where aca.id = ati.acao_id
                            and mun.id = aca.meta_unidade_id
                            and met.id = mun.meta_id
                            and obj.id = met.objetivo_estrategico_id
                            and con.id = obj.configuracao_id
                            and an1.id = con.ano_base_id
                            and fac.id = aca.acao_orcamento_id
                            and fac.id = ptr.acao_id
                            and ptr.id = epf.programa_trabalho_id
                            and an2.id = epf.ano_base_id
                            and an1.id = an2.id
                            and pro.id = fac.programa_id
                            and aca.status != 'Indeferida'
                            and con.id = {configuracao.id}
                        group by fac.id, fac.codigo_acao, oum.nome, epf.quantidade, pro.codigo, fac.nome, aca.id, aca.titulo) t
                        group by acao_orcamento_id, acao_orcamento_codigo, acao_orcamento_unidademedida,
                                 acao_orcamento_quantidade, acao_orcamento_nome, acao_titulo
                        order by acao_orcamento_nome;"""
    acoes = db.get_dict(str)
    return locals()


@rtr('planejamento/templates/resumo_campus.html')
@group_required('Servidor')
def resumo_campus(request):
    configuracoes = Configuracao.objects.all().order_by('-ano_base__ano')
    if not len(configuracoes):
        erro = 'Não existe período de vigência de planejamento cadastrado.'
        return locals()
    else:
        configuracao = configuracoes[0]

    # verifica se foi repassado alguma configuracao ou pega o id do ultimo ano base cadastrado
    if 'configuracao' in request.POST and request.POST['configuracao'] != '':
        configuracao = Configuracao.objects.get(pk=int(request.POST['configuracao']))

    configuracao_form = ConfiguracaoFiltroForm(id_config=configuracao.id)

    acoes = (
        Acao.objects.filter(
            meta_unidade__unidade__setor_equivalente=get_setor_unidade_administrativa(request.user),
            meta_unidade__meta__objetivo_estrategico__configuracao=configuracao,
        )
        .exclude(status='Indeferida')
        .order_by('meta_unidade__meta__objetivo_estrategico__dimensao')
    )
    return locals()


@rtr('planejamento/templates/relatorio/resumo_executivo.html')
@group_required('Coordenador de Planejamento Sistêmico')
def resumo_executivo(request):
    title = 'Resumo Executivo'
    configuracoes = Configuracao.objects.all().order_by('-ano_base__ano')
    if not len(configuracoes):
        mensagem = 'Não existe período de vigência de planejamento cadastrado.'
        return locals()

    configuracao = configuracoes[0]
    str_configuracao = f'AND pco.id = {configuracao.id}'

    id_configuracao = configuracao.id if configuracao else None
    data_hora = datetime.now()

    # verifica se foi repassado alguma configuracao ou pega o id do ultimo ano base cadastrado
    if 'configuracao' in request.POST and request.POST['configuracao'] != '':
        configuracao = Configuracao.objects.get(pk=int(request.POST['configuracao']))
        id_configuracao = configuracao.id
        str_configuracao = f'AND pco.id = {id_configuracao}'

    form = ConfiguracaoFiltroForm(id_config=id_configuracao)
    # filtra para evitar que um setor não esteja cadastrado como dimensão e acabe gerando um erro na apresentação
    dimensoes = Dimensao.objects.filter(setor_sistemico=get_setor_unidade_administrativa(request.user))

    if len(dimensoes):
        dimensao = dimensoes[0]

        strConsulta = f"""select id, descricao
                                from planejamento_objetivoestrategico
                                where dimensao_id = {dimensao.id} and configuracao_id = {id_configuracao}
                                order by descricao;"""
        objetivos_estrategicos = db.get_dict(strConsulta)

        for objetivo_estrategico in objetivos_estrategicos:
            strConsMetas = """select m.id, m.titulo, m.justificativa, m.data_inicial, m.data_final, u.nome as unidade_medida
                                from planejamento_meta m, planejamento_unidademedida u
                                where m.unidade_medida_id = u.id and
                                      m.objetivo_estrategico_id = {}
                                order by titulo;""".format(objetivo_estrategico['id'])
            metas = db.get_dict(strConsMetas)

            for meta in metas:
                strConsMeta = """select mu.quantidade as quantidade, mu.valor_total as valor, s.nome as unidade
                                       from planejamento_meta m, planejamento_metaunidade mu, planejamento_unidadeadministrativa u, setor s
                                       where mu.meta_id = m.id and
                                             mu.unidade_id = u.id and
                                             u.setor_equivalente_id = s.id and
                                             mu.meta_id = {};""".format(meta['id'])
                metaunidades = db.get_dict(strConsMeta)

                strConsAcoesMeta = """select a.id as id, a.titulo as titulo, u.nome as unidade_medida,
                                            a.data_inicial, a.data_final, f.nome as fonte_recurso
                                            from planejamento_acaoproposta a, planejamento_meta m,
                                                 financeiro_fonterecurso f, planejamento_unidademedida u
                                            where a.meta_id = m.id and
                                                  a.fonte_financiamento_id = f.id and
                                                  a.unidade_medida_id = u.id and
                                                  m.id = {}
                                            order by upper(a.titulo);""".format(meta['id'])
                acoes = db.get_dict(strConsAcoesMeta)

                for acao in acoes:
                    strConsAcoes = """select s.nome as unidade_administrativa, u.quantidade, u.valor_unitario,
                                                    (u.quantidade * u.valor_unitario) as valor_total,
                                                    (CASE c.status
                                                        WHEN 'Indeferida' THEN 0
                                                        ELSE coalesce(c.quantidade, 0)
                                                    END) as quantidade_informada,
                                                    (CASE c.status
                                                        WHEN 'Indeferida' THEN 0.00
                                                        ELSE coalesce(sum(t.quantidade * t.valor_unitario), 0.00)
                                                    END) as valor_informado
                                                    from planejamento_acaoproposta a, planejamento_metaunidadeacaoproposta u
                                                        left join planejamento_acao c on c.acao_indutora_id = u.id
                                                        left join planejamento_atividade t on t.acao_id = c.id,
                                                        planejamento_metaunidade m, planejamento_unidadeadministrativa ua,
                                                        setor s
                                                    where a.id = u.acao_proposta_id and
                                                        m.id = u.meta_unidade_id and
                                                        ua.id = m.unidade_id and
                                                        s.id = ua.setor_equivalente_id and
                                                        a.id = {}
                                                    group by s.nome, u.quantidade, u.valor_unitario,
                                                            c.quantidade, c.status
                                                    order by upper(s.nome);""".format(acao['id'])
                    acaounidades = db.get_dict(strConsAcoes)

                    acao['unidades'] = acaounidades
                    acao['quantidade_acao'] = sum([ac['quantidade'] for ac in acaounidades])
                    acao['valor_total_acao'] = sum([ac['valor_total'] for ac in acaounidades])
                    acao['quantidade_informada_acao'] = sum([ac['quantidade_informada'] for ac in acaounidades])
                    acao['valor_total_informado_acao'] = sum([ac['valor_informado'] for ac in acaounidades])

                meta['unidades'] = metaunidades
                meta['acoespropostas'] = acoes
                meta['quantidade_total'] = sum([metaunidade['quantidade'] for metaunidade in metaunidades])
                meta['valor_total'] = sum([metaunidade['valor'] for metaunidade in metaunidades])

            objetivo_estrategico['metas'] = metas

    return locals()


@rtr('planejamento/templates/relatorio/detalhamento.html')
@group_required('Administrador de Planejamento, Coordenador de Planejamento Sistêmico, Coordenador de Planejamento, Auditor ,Servidor')
def detalhamento(request):
    title = 'Detalhamento dos Campi'
    configuracoes = Configuracao.objects.all().order_by('-ano_base__ano')
    if not len(configuracoes):
        mensagem = 'Não existe período de vigência de planejamento cadastrado.'
        return locals()

    configuracao = configuracoes[0]

    # verifica se foi repassado alguma configuracao ou pega o id do ultimo ano base cadastrado
    if 'configuracao' in request.POST and request.POST['configuracao'] != '':
        configuracao = Configuracao.objects.get(pk=int(request.POST['configuracao']))

    # indica o id do campus que será utilizado para gerar o relatório de detalhamento
    campus = None
    dimensao = None

    try:
        unidade_administrativa = UnidadeAdministrativa.objects.get(pk=int(request.POST['campus']), configuracao=configuracao)
        campus = unidade_administrativa.setor_equivalente
    except Exception:
        mensagem = 'Selecione um Campus para gerar o relatório.'

    campus_form = RelatorioDetalhamentoForm(request.POST, id_configuracao=configuracao.id)

    if 'dimensao' in request.POST and request.POST['dimensao'] != '':
        dimensao = Dimensao.objects.get(pk=int(request.POST['dimensao']))

    dimensao_form = DimensaoFiltroForm(id_dimensao=dimensao.id if dimensao else None, empty_label='Todas')

    str_dimensao = ''
    if dimensao:
        str_dimensao = f'AND d.id = {dimensao.id}'
    if campus:
        strConsDim = f"""select d.id, d.codigo, d.descricao, sd.nome as orgao_sistemico
                            from planejamento_dimensao d, setor sd, planejamento_objetivoestrategico o,
                                 planejamento_meta m, planejamento_metaunidade mu,
                                 planejamento_unidadeadministrativa u, setor s
                            where d.id = o.dimensao_id and
                                  sd.id = d.setor_sistemico_id and
                                  o.id = m.objetivo_estrategico_id and
                                  m.id = mu.meta_id and
                                  u.id = mu.unidade_id and
                                  s.id = u.setor_equivalente_id and
                                  s.id = {campus.id}
                                  {str_dimensao}
                            group by d.id, d.codigo, d.descricao, sd.nome
                            order by d.codigo, d.descricao;"""
        _dimensoes = db.get_dict(strConsDim)
        dimensoes = []

        for dimensao in _dimensoes:
            strConsulta = """select o.id, o.codigo, o.descricao, o.macro_projeto_institucional
                                    from planejamento_objetivoestrategico o, planejamento_meta m, planejamento_metaunidade mu,
                                         planejamento_unidadeadministrativa u, planejamento_configuracao c
                                    where o.id = m.objetivo_estrategico_id and
                                          m.id = mu.meta_id and
                                          u.id = mu.unidade_id and
                                          o.dimensao_id = {} and
                                          u.setor_equivalente_id = {} and
                                          c.id = o.configuracao_id and
                                          c.id = {}
                                    group by o.id, o.codigo, o.descricao, o.macro_projeto_institucional
                                    order by o.codigo, o.descricao, o.macro_projeto_institucional;""".format(
                dimensao['id'],
                campus.id,
                configuracao.id,
            )
            objetivos_estrategicos = db.get_dict(strConsulta)

            for objetivo_estrategico in objetivos_estrategicos:
                objetivo_estrategico['valor'] = Decimal(0)
                consMetas = """select m.id, mu.id as mu, m.codigo, m.titulo, mu.quantidade, m.data_inicial, m.data_final, mu.valor_total as valor_total
                                    from planejamento_meta m, planejamento_metaunidade mu,
                                         planejamento_unidadeadministrativa ua
                                    where m.id = mu.meta_id and
                                          ua.id = mu.unidade_id and
                                          m.objetivo_estrategico_id = '{}' and
                                          ua.setor_equivalente_id = '{}'
                                    group by m.id, mu.quantidade, valor_total, mu
                                    order by m.id, codigo, titulo;""".format(
                    objetivo_estrategico['id'],
                    campus.id,
                )
                metas = db.get_dict(consMetas)

                for meta in metas:
                    strconsAcoes = """ SELECT a.id, a.codigo, a.titulo, sum(at.quantidade * at.valor_unitario) AS valor, a.status, a.quantidade
                                            FROM planejamento_metaunidade mu
                                            LEFT JOIN planejamento_acao a ON mu.id = a.meta_unidade_id
                                            LEFT JOIN planejamento_atividade AT ON a.id = AT.acao_id
                                            LEFT JOIN planejamento_origemrecurso og ON og.id = AT.tipo_recurso_id,
                                            planejamento_meta m, planejamento_objetivoestrategico oe, planejamento_naturezadespesa n,
                                            financeiro_naturezadespesa fn, planejamento_dimensao d, planejamento_unidadeadministrativa u,
                                            planejamento_configuracao pco
                                            WHERE m.id = mu.meta_id
                                              AND oe.id = m.objetivo_estrategico_id
                                              AND d.id = oe.dimensao_id
                                              AND u.id = mu.unidade_id
                                              AND AT.acao_id = a.id
                                              AND AT.elemento_despesa_id = n.id
                                              AND a.meta_unidade_id = mu.id
                                              AND n.naturezadespesa_id = fn.id
                                              AND u.configuracao_id = pco.id
                                              AND mu.id = {}
                                            GROUP BY a.id, a.codigo,
                                                 a.titulo
                                            ORDER BY upper(a.titulo);""".format(meta['mu'])

                    acoes = db.get_dict(strconsAcoes)

                    for acao in acoes:
                        strConsAtividades = """SELECT at.descricao, u.nome as unidade_medida, COALESCE(fn.nome, '-') as natureza_despesa, at.tipo_recurso_id,
                                                       at.quantidade as quantidade, at.valor_unitario as valor_unitario, o.nome as tipo_recurso,
                                                       SUM( CASE a.status
                                                                 WHEN 'Indeferida' THEN at.quantidade * at.valor_unitario
                                                                 ELSE 0.00
                                                            END ) AS valor_indeferido,
                                                       SUM( CASE a.status
                                                                 WHEN 'Indeferida' THEN 0.00
                                                                 ELSE at.quantidade * at.valor_unitario
                                                            END ) AS valor_total, a.status, SUM(at.quantidade * at.valor_unitario)
                                                  FROM planejamento_acao a,
                                                       financeiro_naturezadespesa fn,
                                                       planejamento_atividade AT LEFT JOIN planejamento_naturezadespesa pn
                                                                ON at.elemento_despesa_id = pn.id LEFT JOIN planejamento_origemrecurso o
                                                                       ON at.tipo_recurso_id = o.id, planejamento_unidademedida u
                                                 WHERE at.acao_id = a.id
                                                   AND at.unidade_medida_id = u.id
                                                   AND fn.id = pn.naturezadespesa_id
                                                   AND a.id = {}
                                                 GROUP BY at.descricao, u.nome, fn.nome,
                                                          at.tipo_recurso_id, o.nome, at.quantidade, at.valor_unitario, a.status;""".format(
                            acao['id']
                        )
                        atividades = db.get_dict(strConsAtividades)

                        acao['atividades'] = atividades
                        acao['valor_total'] = sum([atividade['valor_total'] for atividade in atividades])
                        acao['valor_indeferido'] = sum([atividade['valor_indeferido'] for atividade in atividades])

                    meta['acoes'] = acoes
                    meta['valor'] = sum([acao['valor_total'] for acao in acoes])

                objetivo_estrategico['metas'] = metas

            if objetivos_estrategicos:
                dimensao['objetivos_estrategicos'] = objetivos_estrategicos
                dimensoes.append(dimensao)

        # verifica se alguma das dimensões encontradas possuem informações para apresentar
        if not dimensoes:
            mensagem = 'Até o momento não existem informações para os filtros informados.'

    return locals()


@rtr('planejamento/templates/relatorio/acoes.html')
@group_required('Administrador de Planejamento,Coordenador de Planejamento')
def relatorio_acoes(request):
    # indica o id do campus que será utilizado para gerar o relatório de acoes
    campus = None
    title = 'Ações da Unidade Administrativa'
    if 'campus' in request.POST:
        if request.POST['campus'] == '':
            mensagem = 'Selecione um Campus para gerar o relatório.'
        else:
            unidade_administrativa = UnidadeAdministrativa.objects.get(pk=int(request.POST['campus']))
            campus = unidade_administrativa.setor_equivalente.id
    else:
        # verifica se a unidade administrativa associada ao usuário é do tipo tipo campus
        unidades_administrativas = UnidadeAdministrativa.objects.filter(
            tipo=TipoUnidade.CAMPUS, setor_equivalente=get_setor_unidade_administrativa(request.user)
        )
        if len(unidades_administrativas):
            unidade_administrativa = unidades_administrativas[0]
            campus = unidade_administrativa.setor_equivalente.id

    if 'configuracao' in request.POST:
        configuracao = Configuracao.objects.get(pk=request.POST['configuracao'])
    else:
        configuracao = Configuracao.objects.all().order_by('-ano_base__ano')[0]

    if not in_group(request.user, ['Coordenador de Planejamento']):
        form = CampusFiltroForm(id_campus=campus, id_config=configuracao.id)
        # apresenta uma mensagem indicando que é necessário escolher um campus antes de solicitar o relatório
        if campus is None:
            mensagem = 'Selecione um Campus para gerar o relatório.'

    if campus:
        # verifica se o usuário tem permissão de sistêmico, pois se tiver deve visualizar apenas as ações de sua competência
        str_pesquisa_sistemico = ''
        str_pesquisa_configuracao = ''
        if in_group(request.user, ['Coordenador de Planejamento Sistêmico']):
            setor_sistemico = get_setor_unidade_administrativa(request.user)
            str_pesquisa_sistemico = f'd.setor_sistemico_id = {setor_sistemico.id} and '
        str_pesquisa_configuracao = f'o.configuracao_id = {configuracao.id} and '

        consAcoesPropostas = f"""select ap.titulo,
                                        CASE WHEN a.status = 'Pendente' THEN 'Não Validada'
                                             WHEN a.status = 'Parcialmente Deferida' THEN 'Pendente'
                                             ELSE a.status
                                        END as status,
                                        muap.quantidade as quantidade_proposta,
                                        muap.quantidade * muap.valor_unitario as valor_proposto,
                                        coalesce(a.quantidade, null) as quantidade, coalesce(sum(at.quantidade * at.valor_unitario), 0.00) as valor
                                    from planejamento_acaoproposta ap,
                                        planejamento_metaunidadeacaoproposta muap left join planejamento_acao a
                                        on muap.id = a.acao_indutora_id left join planejamento_atividade at on a.id = at.acao_id,
                                        planejamento_metaunidade mu, planejamento_unidadeadministrativa u,
                                        planejamento_meta m, planejamento_objetivoestrategico o, planejamento_dimensao d
                                    where ap.id = muap.acao_proposta_id and
                                        mu.id = muap.meta_unidade_id and
                                        u.id = mu.unidade_id and
                                        m.id = mu.meta_id and
                                        o.id = m.objetivo_estrategico_id and
                                        d.id = o.dimensao_id and
                                        {str_pesquisa_sistemico}
                                        {str_pesquisa_configuracao}
                                        u.setor_equivalente_id = {campus}
                                    group by ap.titulo, a.status, muap.quantidade, muap.valor_unitario, a.quantidade
                                    order by ap.titulo;"""
        acoes_propostas = db.get_dict(consAcoesPropostas)

        valor_total_acoes_propostas = sum([acao['valor'] for acao in acoes_propostas])

        consAcoesInformadas = f"""select a.titulo,
                                        CASE WHEN a.status = 'Pendente' THEN 'Não Validada'
                                             WHEN a.status = 'Parcialmente Deferida' THEN 'Pendente'
                                             ELSE a.status
                                        END as status,
                                        a.quantidade, coalesce(sum(t.quantidade * t.valor_unitario), 0.00) as valor_unitario
                                        from planejamento_acao a left join planejamento_atividade t on a.id = t.acao_id,
                                             planejamento_metaunidade mu, planejamento_unidadeadministrativa u,
                                             planejamento_meta m, planejamento_objetivoestrategico o, planejamento_dimensao d
                                        where mu.id = a.meta_unidade_id and
                                              u.id = mu.unidade_id and
                                              a.acao_indutora_id is null and
                                              m.id = mu.meta_id and
                                              o.id = m.objetivo_estrategico_id and
                                              d.id = o.dimensao_id and
                                              {str_pesquisa_sistemico}
                                              {str_pesquisa_configuracao}
                                              u.setor_equivalente_id = {campus}
                                        group by a.titulo, a.status, a.quantidade
                                        order by a.titulo;"""
        acoes_informadas = db.get_dict(consAcoesInformadas)

        valor_total_acoes_informadas = sum([acao['valor_unitario'] for acao in acoes_informadas])

    return locals()


@rtr('planejamento/templates/relatorio/acoes_recurso_dimensao_unidade.html')
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico, Coordenador de Planejamento, Auditor')
def relatorio_acoes_recurso_dimensao_unidade(request, id_origem_recurso, id_dimensao, id_unidade_administrativa):
    title = 'Ações da Unidade Administrativa'
    dimensao = Dimensao.objects.get(id=id_dimensao)
    origem_recurso = OrigemRecurso.objects.get(id=id_origem_recurso)
    unidade_administrativa = UnidadeAdministrativa.objects.get(id=id_unidade_administrativa)

    consObjEstrategicos = f"""select o.id, o.descricao, o.codigo
                                    from planejamento_dimensao d, planejamento_objetivoestrategico o, planejamento_meta m,
                                         planejamento_metaunidade mu, planejamento_unidadeadministrativa u,
                                         planejamento_acao a, planejamento_atividade at, planejamento_origemrecurso r
                                    where d.id = o.dimensao_id and
                                          o.id = m.objetivo_estrategico_id and
                                          m.id = mu.meta_id and
                                          u.id = mu.unidade_id and
                                          mu.id = a.meta_unidade_id and
                                          a.id = at.acao_id and
                                          r.id = at.tipo_recurso_id and
                                          r.id = {id_origem_recurso} and
                                          d.id = {id_dimensao} and
                                          u.id = {id_unidade_administrativa}
                                    group by o.id, o.codigo, o.descricao
                                    order by upper(o.descricao);"""
    objetivos_estrategicos = db.get_dict(consObjEstrategicos)

    for obj_estrategico in objetivos_estrategicos:
        obj_estrategico['valor'] = Decimal(0)
        consMetas = """select m.id, m.codigo, m.titulo, mu.id as meta_unidade
                            from planejamento_objetivoestrategico o, planejamento_meta m,
                                 planejamento_metaunidade mu, planejamento_unidadeadministrativa u,
                                 planejamento_acao a, planejamento_atividade at, planejamento_origemrecurso r
                            where o.id = m.objetivo_estrategico_id and
                                  m.id = mu.meta_id and
                                  u.id = mu.unidade_id and
                                  mu.id = a.meta_unidade_id and
                                  a.id = at.acao_id and
                                  r.id = at.tipo_recurso_id and
                                  r.id = {} and
                                  u.id = {} and
                                  o.id = {}
                            group by m.id, m.codigo, m.titulo, mu.id
                            order by upper(m.titulo);""".format(
            id_origem_recurso,
            id_unidade_administrativa,
            obj_estrategico['id'],
        )
        metas = db.get_dict(consMetas)

        for meta in metas:
            consAcoes = """SELECT a.id, a.codigo, a.titulo, sum(at.quantidade * at.valor_unitario) AS valor
                            FROM planejamento_metaunidade mu
                                LEFT JOIN planejamento_acao a ON mu.id = a.meta_unidade_id
                                LEFT JOIN planejamento_atividade AT ON a.id = AT.acao_id
                                LEFT JOIN planejamento_origemrecurso og ON og.id = AT.tipo_recurso_id,
                                planejamento_meta m, planejamento_objetivoestrategico oe, planejamento_naturezadespesa n,
                                financeiro_naturezadespesa fn, planejamento_dimensao d, planejamento_unidadeadministrativa u,
                                planejamento_configuracao pco
                            WHERE m.id = mu.meta_id
                              AND oe.id = m.objetivo_estrategico_id
                              AND d.id = oe.dimensao_id
                              AND u.id = mu.unidade_id
                              AND AT.acao_id = a.id
                              AND AT.elemento_despesa_id = n.id
                              AND a.meta_unidade_id = mu.id
                              AND a.status != 'Indeferida'
                              AND n.naturezadespesa_id = fn.id
                              AND u.configuracao_id = pco.id
                              AND og.id = {}
                              AND mu.id = {}
                            GROUP BY a.id,
                                     a.codigo,
                                     a.titulo
                            ORDER BY upper(a.titulo);""".format(
                id_origem_recurso,
                meta['meta_unidade'],
            )
            acoes = db.get_dict(consAcoes)
            meta['acoes'] = acoes
            meta['valor'] = sum([a['valor'] for a in acoes])
            obj_estrategico['valor'] += meta['valor']

        obj_estrategico['metas'] = metas

    return locals()


@rtr('planejamento/templates/relatorio/despesas_acoes_elementos_despesa.html')
@group_required('Administrador de Planejamento, Coordenador de Planejamento Sistêmico, Coordenador de Planejamento, Auditor')
def relatorio_despesas_acoes_elementos_despesa(request):
    title = 'Detalhamento de Despesas por Ações'
    try:
        # filtros
        str_nat_despesa = ''
        str_configuracao = ''
        str_dimensao = ''
        str_campus = ''
        str_acao_orcamento = ''
        str_origem_recurso = ''

        data_hora = datetime.now()

        if not request.GET['n'] or not request.GET['u'] or not request.GET['c']:
            raise ValueError

        nat_despesa = NaturezaDespesa.objects.get(codigo=request.GET['n'])
        str_nat_despesa = f"AND fnd.codigo = '{nat_despesa.codigo}'"

        configuracao = Configuracao.objects.get(pk=int(request.GET['c']))
        str_configuracao = f'AND pco.id = {configuracao.id}'

        unidade_administrativa = UnidadeAdministrativa.objects.get(setor_equivalente__sigla=request.GET['u'], configuracao=configuracao)
        str_campus = f'AND pua.id = {unidade_administrativa.id}'

        if request.GET['d']:
            dimensao = Dimensao.objects.get(pk=int(request.GET['d']))
            str_dimensao = f'AND pdi.id = {dimensao.id}'

        if request.GET['o']:
            acao_orcamento = apps.get_model('financeiro', 'Acao').objects.get(id=request.GET['o'])
            str_acao_orcamento = f"AND fac.id = '{acao_orcamento.id}'"

        if request.GET['r']:
            origem_recurso = OrigemRecurso.objects.get(id=request.GET['r'])
            str_origem_recurso = f'AND por.id = {origem_recurso.id}'

        # Devido à mudanças no planejamento a partir de 2014, foi necessária a alteração da consulta
        if configuracao.ano_base.ano < 2014:
            str_tabela = ''
            str_complemento = 'AND fac.id = pac.acao_orcamento_id'
        else:
            str_tabela = ', financeiro_acaoano faa'
            str_complemento = 'AND por.acao_ano_id = faa.acao_id AND fac.id = faa.acao_id'

        sql = f"""SELECT fac.codigo_acao,
                        coalesce(pdi.codigo::text,'x') || '.' ||
                            coalesce(poe.codigo::text,'x') || '.' ||
                            coalesce(pme.codigo::text,'x') || '.' ||
                            coalesce(pac.codigo::text,'x') as acao_codigo,
                        pac.titulo as acao,
                        coalesce(pdi.codigo::text,'x') || '.' ||
                            coalesce(poe.codigo::text,'x') || '.' ||
                            coalesce(pme.codigo::text,'x') as meta_codigo,
                        pme.titulo as meta,
                        pat.descricao as atividade,
                        SUM(pat.quantidade * pat.valor_unitario) as valor
                    FROM planejamento_atividade pat, planejamento_acao pac, planejamento_metaunidade pmu,
                        planejamento_unidadeadministrativa pua, planejamento_meta pme,
                        planejamento_objetivoestrategico poe, planejamento_dimensao pdi,
                        planejamento_configuracao pco, planejamento_naturezadespesa pnd,
                        planejamento_origemrecurso por,
                        setor str, financeiro_naturezadespesa fnd, financeiro_acao fac {str_tabela}
                    WHERE fnd.id = pnd.naturezadespesa_id
                        AND pnd.id = pat.elemento_despesa_id
                        AND pac.id = pat.acao_id
                        AND pmu.id = pac.meta_unidade_id
                        AND pua.id = pmu.unidade_id
                        AND str.id = pua.setor_equivalente_id
                        AND pme.id = pmu.meta_id
                        AND poe.id = pme.objetivo_estrategico_id
                        AND pdi.id = poe.dimensao_id
                        AND pco.id = poe.configuracao_id
                        {str_complemento}
                        AND por.id = pat.tipo_recurso_id
                        AND pco.id = por.configuracao_id
                        AND pac.status != 'Indeferida'
                        AND pat.valor_unitario != 0.00
                        {str_nat_despesa}
                        {str_configuracao}
                        {str_dimensao}
                        {str_campus}
                        {str_acao_orcamento}
                        {str_origem_recurso}
                    GROUP BY pdi.codigo, poe.codigo, pme.codigo, pac.codigo, pme.titulo, pac.titulo, pat.descricao, fac.codigo_acao
                    ORDER BY pme.titulo, pac.titulo, pat.descricao, fac.codigo_acao;"""
        relatorio = db.get_dict(sql)
    except Exception:
        mensagem = 'Não é possível gerar o relatório solicitado.'

    return locals()


@rtr('planejamento/templates/relatorio/acao_orcamento.html')
@group_required('Administrador de Planejamento, Auditor')
def relatorio_acoes_orcamento(request):
    title = 'Detalhamento de Ações do Orçamento'

    if 'configuracao' in request.POST:
        configuracao = Configuracao.objects.get(pk=request.POST['configuracao'])
    else:
        configuracao = Configuracao.objects.all().order_by('-ano_base__ano')[0]

    form = ConfiguracaoFiltroForm(id_config=configuracao.id)

    str_configuracao = f' {configuracao.id}'

    sql = f"""SELECT ofr.id, ofr.grupo_id, ofr.especificacao_id, ofr.nome, SUM(pat.quantidade * pat.valor_unitario) AS valor_total
               FROM orcamento_programa op, financeiro_acao oa, financeiro_fonterecurso ofr, planejamento_acao pa, planejamento_metaunidade pmu,
                    planejamento_unidadeadministrativa pua, setor s, planejamento_atividade pat,
                    planejamento_meta m, planejamento_objetivoestrategico o, planejamento_dimensao d, planejamento_configuracao pco
              WHERE op.id = oa.programa_id
                AND oa.id = pa.acao_orcamento_id
                AND ofr.id = pa.fonte_financiamento_id
                AND pa.meta_unidade_id = pmu.id
                AND pua.id = pmu.unidade_id
                AND s.id = pua.setor_equivalente_id
                AND pa.id = pat.acao_id
                AND pa.status NOT LIKE 'Indeferida'
                AND pa.id = pat.acao_id
                AND pmu.id = pa.meta_unidade_id
                AND pua.id = pmu.unidade_id
                AND m.id = pmu.meta_id
                AND o.id = m.objetivo_estrategico_id
                AND d.id = o.dimensao_id
                AND pco.id = o.configuracao_id
                AND pco.id = {str_configuracao}
              GROUP BY ofr.id, ofr.grupo_id, ofr.especificacao_id, ofr.nome
              ORDER BY ofr.grupo_id, ofr.especificacao_id;"""
    fontes_recurso = db.get_dict(sql)

    relatorio = []

    for fonte in fontes_recurso:
        sql = """SELECT oa.codigo_acao, oa.nome, SUM(pat.quantidade * pat.valor_unitario) AS valor_total
                   FROM financeiro_acao oa, financeiro_fonterecurso ofr, planejamento_acao pa, planejamento_metaunidade pmu,
                         planejamento_unidadeadministrativa pua, setor s, planejamento_atividade pat
                  WHERE oa.id = pa.acao_orcamento_id
                    AND ofr.id = pa.fonte_financiamento_id
                    AND pa.meta_unidade_id = pmu.id
                    AND pua.id = pmu.unidade_id
                    AND s.id = pua.setor_equivalente_id
                    AND pa.id = pat.acao_id
                    AND pa.status NOT LIKE 'Indeferida'
                    AND ofr.id = {}
                  GROUP BY oa.codigo_acao, oa.nome
                  ORDER BY oa.nome""".format(fonte['id'])
        acoes_orcamento = db.get_dict(sql)

        fonte_rel = {
            'id': fonte['grupo_id'],
            'codigo': fonte['grupo_id'] + fonte['especificacao_id'],
            'fonte_financiamento': fonte['nome'],
            'valor_total': fonte['valor_total'],
            'acoes': [],
        }

        for acao in acoes_orcamento:
            sql = """SELECT pua.id, pua.codigo_simec, pua.codigo_simec_digito, s.nome AS setor, SUBSTRING(ond.codigo, 1, 2) AS tipo,
                            pat.quantidade * pat.valor_unitario AS valor_total
                       FROM financeiro_acao oa, financeiro_fonterecurso ofr, financeiro_naturezadespesa ond, planejamento_acao pa, planejamento_metaunidade pmu,
                            planejamento_unidadeadministrativa pua, setor s, planejamento_atividade pat
                      WHERE oa.id = pa.acao_orcamento_id
                        AND ofr.id = pa.fonte_financiamento_id
                        AND pa.meta_unidade_id = pmu.id
                        AND pua.id = pmu.unidade_id
                        AND s.id = pua.setor_equivalente_id
                        AND pa.id = pat.acao_id
                        AND ond.id = pat.elemento_despesa_id
                        AND pa.status NOT LIKE 'Indeferida'
                        AND ofr.id = %s
                        AND oa.codigo_acao LIKE %s
                      ORDER BY s.nome"""
            args = [fonte['id'], acao['codigo_acao']]

            setores = {}

            st = ''

            for s in db.get_dict(sql, args):
                if s['id'] != st:
                    setores[s['id']] = {
                        'id': s['id'],
                        'codigo_simec': s['codigo_simec'],
                        'codigo_simec_digito': s['codigo_simec_digito'],
                        'setor': s['setor'],
                        'valor_capital': 0,
                        'valor_custeio': 0,
                        'valor_pessoal': 0,
                        'valor_outros': 0,
                        'valor_total': 0,
                    }
                    st = s['id']

                if s['tipo'] == '44':
                    setores[s['id']]['valor_capital'] += s['valor_total']
                elif s['tipo'] == '33':
                    setores[s['id']]['valor_custeio'] += s['valor_total']
                elif s['tipo'] == '31':
                    setores[s['id']]['valor_pessoal'] += s['valor_total']
                else:
                    setores[s['id']]['valor_outros'] += s['valor_total']
                setores[s['id']]['valor_total'] += s['valor_total']

            acao_rel = {
                'codigo': acao['codigo_acao'],
                'acao': acao['nome'],
                'valor_total': acao['valor_total'],
                'setores': sorted(setores.values(), key=itemgetter('setor')),
            }
            fonte_rel['acoes'].append(acao_rel)
        relatorio.append(fonte_rel)

    return locals()


@rtr('planejamento/templates/relatorio/detalhamento_despesas_orcamento.html')
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico, Auditor')
def detalhamento_despesas_orcamento(request):
    campus = None
    if 'configuracao' in request.POST:
        configuracao = Configuracao.objects.get(pk=request.POST['configuracao'])
    else:
        configuracao = Configuracao.objects.all().order_by('-ano_base__ano')[0]

    if 'campus' in request.POST:
        if request.POST['campus'] != '':
            campus = UnidadeAdministrativa.objects.get(pk=int(request.POST['campus']))
    else:
        # verifica se a unidade administrativa associada ao usuário é do tipo tipo campus
        unidade_administrativa = UnidadeAdministrativa.objects.filter(
            tipo=TipoUnidade.CAMPUS, setor_equivalente=get_setor_unidade_administrativa(request.user)
        )
        if len(unidade_administrativa):
            campus = unidade_administrativa[0]

    cons_unidade = ''

    if campus:
        campus_form = CampusFiltroForm(id_campus=campus.setor_equivalente.id, id_config=configuracao.id, empty_label='Todas')

        cons_unidade = f'   and mu.unidade_id = {campus.id}'
    else:
        campus_form = CampusFiltroForm(id_campus=None, id_config=configuracao.id, empty_label='Todas')

    str_configuracao = f'and pco.id = {configuracao.id} '

    sql = f"""select op.codigo as programa_codigo, op.nome as programa_nome,
                   oa.codigo_acao as acao_codigo, oa.nome as acao_nome,
                   oz.codigo as natureza_despesa_codigo, oz.nome as natureza_despesa_nome,
                   of.codigo as fonte_recurso_codigo, of.nome as fonte_recurso_nome,
                   sum(pt.quantidade * pt.valor_unitario) as valor
                from planejamento_metaunidade mu left join planejamento_acao pa on mu.id = pa.meta_unidade_id
                     left join planejamento_atividade pt on pt.acao_id = pa.id
                     left join financeiro_naturezadespesa oz on oz.id = pt.elemento_despesa_id,
                      financeiro_fonterecurso of, financeiro_acao oa, orcamento_programa op, planejamento_configuracao pco
                where of.id = pa.fonte_financiamento_id
                  and oa.id = pa.acao_orcamento_id
                  and op.id = oa.programa_id
                  and pa.status = 'Deferida'
                  and pt.elemento_despesa_id is not null
                  {str_configuracao}
                  {cons_unidade}
                group by op.codigo, op.nome, oa.codigo_acao, oa.nome,
                         oz.codigo, oz.nome, of.codigo,
                         of.nome
                order by op.codigo, op.nome, oa.codigo_acao, oa.nome,
                         oz.nome, oz.codigo, of.codigo,
                         of.nome;"""
    despesas = db.get_dict(sql)

    show_relatorio = True
    mensagem = ''

    if not despesas:
        show_relatorio = False
        mensagem = 'Não existem informações cadastradas.'

    return locals()


@rtr('planejamento/templates/relatorio/comparativo_despesas_orcamento.html')
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico, Auditor')
def comparativo_despesas_orcamento(request):
    sql = """
            SELECT op.codigo AS programa_codigo, op.nome AS programa_nome, oa.codigo_acao AS acao_codigo, oa.nome AS acao_nome,
                   ond.codigo AS despesa_codigo, ond.nome AS despesa_nome, oe.valor AS despesa_valor,
                   ofr.grupo_id || ofr.especificacao_id AS fonte_recurso,
                   COALESCE((
                   SELECT SUM(pat.quantidade * pat.valor_unitario)
                     FROM planejamento_acao pa, planejamento_atividade pat
                    WHERE pat.acao_id = pa.id
                      AND pa.acao_orcamento_id = oa.id
                      AND pa.status = 'Deferida'
                      AND pat.elemento_despesa_id = ond.id
                   ), 0.0) AS planejamento_valor
              FROM orcamento_programa op, financeiro_acao oa, orcamento_estruturaprogramaticafinanceira oe, financeiro_naturezadespesa ond,
                   orcamento_fonterecurso ofr
             WHERE oa.programa_id         = op.id
               AND oe.acao_id             = oa.codigo_acao
               AND oe.natureza_despesa_id = ond.id
               AND oe.fonte_recurso_id    = ofr.id
             ORDER BY op.codigo, op.nome, oa.codigo_acao, oa.nome, ond.codigo, ofr.grupo_id, ofr.especificacao_id
         """
    comparativo = db.get_dict(sql)

    return locals()


@rtr('planejamento/templates/relatorio/acao_orcamento_total.html')
@group_required('Administrador de Planejamento, Auditor')
def relatorio_acoes_orcamento_total(request, id_fonte, id_acao):
    fonte = FonteRecurso.objects.get(pk=id_fonte)
    acao = AcaoOrcamento.objects.get(codigo_acao=id_acao)

    sql = f"""SELECT pa.titulo, SUM(pat.quantidade * pat.valor_unitario) AS valor_total
                FROM financeiro_acao oa, financeiro_fonterecurso ofr, planejamento_acao pa, planejamento_atividade pat
              WHERE oa.id = pa.acao_orcamento_id
                AND ofr.id = pa.fonte_financiamento_id
                AND pa.id = pat.acao_id
                AND pa.status NOT LIKE 'Indeferida'
                AND ofr.id = {fonte.id}
                AND oa.codigo_acao LIKE '{acao.codigo_acao}'
              GROUP BY pa.titulo
              ORDER BY pa.titulo"""
    acoes_planejamento = db.get_dict(sql)

    valor_total = sum([a['valor_total'] for a in acoes_planejamento])

    return locals()


@rtr('planejamento/templates/relatorio/acao_orcamento_campus.html')
@group_required('Administrador de Planejamento, Auditor')
def relatorio_acoes_orcamento_campus(request, id_fonte, id_acao, id_campus):
    title = 'Ações do Campus da Ação do Orçamento'
    fonte = FonteRecurso.objects.get(pk=id_fonte)
    acao = AcaoOrcamento.objects.get(codigo_acao=id_acao)
    campus = UnidadeAdministrativa.objects.get(pk=id_campus)

    sql = f"""SELECT pa.titulo, SUM(pat.quantidade * pat.valor_unitario) AS valor_total
                       FROM financeiro_acao oa, financeiro_fonterecurso ofr, planejamento_acao pa, planejamento_metaunidade pmu,
                            planejamento_unidadeadministrativa pua, planejamento_atividade pat
                      WHERE oa.id = pa.acao_orcamento_id
                        AND ofr.id = pa.fonte_financiamento_id
                        AND pa.meta_unidade_id = pmu.id
                        AND pua.id = pmu.unidade_id
                        AND pa.id = pat.acao_id
                        AND pa.status NOT LIKE 'Indeferida'
                        AND ofr.id = {fonte.id}
                        AND oa.codigo_acao LIKE '{acao.codigo_acao}'
                        AND pua.id = {campus.id}
                      GROUP BY pa.titulo
                      ORDER BY pa.titulo"""
    acoes_planejamento = db.get_dict(sql)

    valor_total = sum([a['valor_total'] for a in acoes_planejamento])

    return locals()


@rtr('planejamento/templates/relatorio/acoes_recurso_dimensao_unidade_acao.html')
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico, Coordenador de Planejamento, Auditor')
def relatorio_acoes_recurso_dimensao_unidade_acao(request, id_origem_recurso, id_acao):
    title = 'Atividades da Ação da Unidade Administrativa'
    # a dimensão e unidade administrativa são obtidas a partir da ação
    acao = Acao.objects.get(id=id_acao)
    meta_unidade = acao.meta_unidade
    meta = meta_unidade.meta
    objetivo_estrategico = meta.objetivo_estrategico
    dimensao = objetivo_estrategico.dimensao
    unidade_administrativa = meta_unidade.unidade
    origem_recurso = OrigemRecurso.objects.get(id=id_origem_recurso)
    atividades = acao.atividade_set.filter(tipo_recurso=origem_recurso)
    atividades_valor_total = 0

    for atividade in atividades:
        atividades_valor_total += atividade.get_valor_total()

    return locals()


@rtr('planejamento/templates/relatorio/natureza_despesa.html')
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico,Coordenador de Planejamento, Auditor')
def relatorio_natureza_despesa(request):
    title = 'Detalhamento de Despesas por Natureza de Despesas'

    configuracao = Configuracao.objects.latest('ano_base__ano')
    if not configuracao:
        mensagem = 'Não existe período de vigência de planejamento cadastrado.'
        return locals()

    # indica o id do campus que será utilizado para gerar o relatório
    campus = None
    origem = None
    dimensao = None

    # verifica se foi repassado alguma configuracao ou pega o id do ultimo ano base cadastrado
    if 'configuracao' in request.POST and request.POST['configuracao'] != '':
        configuracao = Configuracao.objects.get(pk=int(request.POST['configuracao']))

    if in_group(request.user, ['Coordenador de Planejamento Sistêmico', 'Administrador de Planejamento', 'Auditor']):
        if 'campus' in request.POST:
            if request.POST['campus'] == '':
                mensagem = 'Selecione um Campus para gerar o relatório.'
            else:
                unidade_administrativa = UnidadeAdministrativa.objects.get(pk=int(request.POST['campus']))
                campus = unidade_administrativa.setor_equivalente

        else:
            # verifica se a unidade administrativa associada ao usuário é do tipo tipo campus
            unidades_administrativas = UnidadeAdministrativa.objects.filter(
                tipo=TipoUnidade.CAMPUS, setor_equivalente=get_setor_unidade_administrativa(request.user), configuracao=configuracao
            )
            if len(unidades_administrativas):
                unidade_administrativa = unidades_administrativas[0]
                campus = unidade_administrativa.setor_equivalente

        # apresenta uma mensagem indicando que é necessário escolher um campus antes de solicitar o relatório
        if campus is None:
            mensagem = 'Selecione uma Unidade Administrativa para gerar o relatório.'

    else:
        unidades_administrativas = UnidadeAdministrativa.objects.filter(
            tipo=TipoUnidade.CAMPUS, setor_equivalente=get_setor_unidade_administrativa(request.user)
        )
        if not len(unidades_administrativas):
            mensagem = 'Não existem despesas cadastradas nesta unidade administrativa com os filtros informados.'
        else:
            campus = unidades_administrativas[0].setor_equivalente

    if 'origem' in request.GET or 'origem' in request.POST:
        origem_pk = request.GET.get('origem') or request.POST.get('origem')
        if origem_pk:
            origem = OrigemRecurso.objects.get(pk=int(origem_pk))

    if 'dimensao' in request.POST and request.POST['dimensao'] != '':
        dimensao = Dimensao.objects.get(pk=int(request.POST['dimensao']))

    campus_form = RelatorioCampusForm(id_campus=campus.id if campus else None, id_config=configuracao.id)
    origem_form = OrigemRecursoFiltroForm(id_origem=origem.id if origem else None, id_config=configuracao.id, empty_label='Todas')
    dimensao_form = DimensaoFiltroForm(id_dimensao=dimensao.id if dimensao else None, empty_label='Todas')

    if campus:
        str_pesquisa_origem = ''
        str_pesquisa_dimensao = ''

        if origem:
            str_pesquisa_origem = f'AND origem.id = {origem.id}'

        if dimensao:
            str_pesquisa_dimensao = f'AND dimensao.id = {dimensao.id}'

        consNaturezaDespesa = f"""
                            SELECT dimensao.descricao as dimensao, acao.status, atividade.elemento_despesa_id, nat.nome as elemento_despesa,
                                   nat.codigo as codigo_elemento_despesa, SUM(atividade.quantidade * atividade.valor_unitario) as valor
                              FROM planejamento_atividade atividade, financeiro_naturezadespesa nat, planejamento_acao acao,
                                   planejamento_metaunidade metau, planejamento_meta meta, planejamento_naturezadespesa pnat,
                                   planejamento_objetivoestrategico objetivo, planejamento_dimensao dimensao,
                                   planejamento_unidadeadministrativa ua, planejamento_origemrecurso origem,
                                   planejamento_configuracao configuracao
                             WHERE atividade.elemento_despesa_id = pnat.id
                               AND nat.id = pnat.naturezadespesa_id
                               AND atividade.acao_id = acao.id
                               AND acao.meta_unidade_id = metau.id
                               AND metau.meta_id = meta.id
                               AND meta.objetivo_estrategico_id = objetivo.id
                               AND objetivo.dimensao_id = dimensao.id
                               AND metau.unidade_id = ua.id
                               AND origem.id = atividade.tipo_recurso_id
                               AND acao.status NOT IN ('Indeferida')
                               AND configuracao.id = ua.configuracao_id
                               AND configuracao.id = origem.configuracao_id
                               AND configuracao.id = {configuracao.id}
                               AND ua.setor_equivalente_id = {campus.id}
                               {str_pesquisa_origem}
                               {str_pesquisa_dimensao}
                             GROUP BY dimensao.descricao, acao.status, atividade.elemento_despesa_id, nat.nome, nat.codigo
                             ORDER BY dimensao.descricao, nat.codigo, nat.nome, acao.status"""
        natureza_despesas = db.get_dict(consNaturezaDespesa)

        valor_total_natureza_despesa = {}

        for nd in natureza_despesas:
            if nd['dimensao'] in valor_total_natureza_despesa:
                valor_total_natureza_despesa[nd['dimensao']] += nd['valor']
            else:
                valor_total_natureza_despesa[nd['dimensao']] = nd['valor']

        if not len(natureza_despesas):
            mensagem = 'Não existem despesas cadastradas nesta unidade administrativa com os filtros informados.'

    return locals()


@rtr('planejamento/templates/relatorio/acoes_dimensao.html')
@group_required('Coordenador de Planejamento Sistêmico')
def relatorio_acoes_dimensao(request):
    form = ConfiguracaoFiltroForm(request.POST or None)

    str_configuracao = ''

    if 'configuracao' in request.POST:
        str_configuracao = str('and o.configuracao_id = {}'.format(request.POST['configuracao']))
    else:
        configuracao = Configuracao.objects.all().order_by('-ano_base__ano')[0]
        str_configuracao = str(f'and o.configuracao_id = {configuracao.id}')

    setor_sistemico = get_setor_unidade_administrativa(request.user)

    strUnidadesAdm = f"""select u.setor_equivalente_id as id, s.nome
                            from planejamento_dimensao d, planejamento_objetivoestrategico o, planejamento_meta m,
                                 planejamento_metaunidade mu, planejamento_unidadeadministrativa u, setor s
                            where d.id = o.dimensao_id and
                                  o.id = m.objetivo_estrategico_id and
                                  m.id = mu.meta_id and
                                  u.id = mu.unidade_id and
                                  s.id = u.setor_equivalente_id and
                                  d.setor_sistemico_id = {setor_sistemico.id}
                                  {str_configuracao}
                            group by u.setor_equivalente_id, s.nome
                            order by upper(s.nome);"""
    unidades_admin = db.get_dict(strUnidadesAdm)

    for unidade in unidades_admin:
        consAcoesPropostas = """select ap.titulo,
                                        CASE WHEN a.status = 'Pendente' THEN 'Não Validada'
                                             WHEN a.status = 'Parcialmente Deferida' THEN 'Pendente'
                                             ELSE a.status
                                        END as status,
                                        muap.quantidade as quantidade_proposta,
                                        muap.quantidade * muap.valor_unitario as valor_proposto,
                                        coalesce(a.quantidade, null) as quantidade, coalesce(sum(at.quantidade * at.valor_unitario), 0.00) as valor
                                    from planejamento_acaoproposta ap,
                                        planejamento_metaunidadeacaoproposta muap left join planejamento_acao a
                                        on muap.id = a.acao_indutora_id left join planejamento_atividade at on a.id = at.acao_id,
                                        planejamento_metaunidade mu, planejamento_unidadeadministrativa u,
                                        planejamento_meta m, planejamento_objetivoestrategico o, planejamento_dimensao d
                                    where ap.id = muap.acao_proposta_id and
                                        mu.id = muap.meta_unidade_id and
                                        u.id = mu.unidade_id and
                                        m.id = mu.meta_id and
                                        o.id = m.objetivo_estrategico_id and
                                        d.id = o.dimensao_id and
                                        d.setor_sistemico_id = {} and
                                        u.setor_equivalente_id = {}
                                        {}
                                    group by ap.titulo, a.status, muap.quantidade, muap.valor_unitario, a.quantidade
                                    order by ap.titulo;""".format(
            setor_sistemico.id,
            unidade['id'],
            str_configuracao,
        )
        acoes_propostas = db.get_dict(consAcoesPropostas)

        unidade['valor_total_acoes_propostas'] = sum([acao['valor'] for acao in acoes_propostas])

        consAcoesInformadas = """select a.titulo,
                                        CASE WHEN a.status = 'Pendente' THEN 'Não Validada'
                                             WHEN a.status = 'Parcialmente Deferida' THEN 'Pendente'
                                             ELSE a.status
                                        END as status,
                                        a.quantidade, coalesce(sum(t.quantidade * t.valor_unitario), 0.00) as valor_unitario
                                        from planejamento_acao a left join planejamento_atividade t on a.id = t.acao_id,
                                             planejamento_metaunidade mu, planejamento_unidadeadministrativa u,
                                             planejamento_meta m, planejamento_objetivoestrategico o, planejamento_dimensao d
                                        where mu.id = a.meta_unidade_id and
                                              u.id = mu.unidade_id and
                                              a.acao_indutora_id is null and
                                              m.id = mu.meta_id and
                                              o.id = m.objetivo_estrategico_id and
                                              d.id = o.dimensao_id and
                                              d.setor_sistemico_id = {} and
                                              u.setor_equivalente_id = {}
                                              {}
                                        group by a.titulo, a.status, a.quantidade
                                        order by a.titulo;""".format(
            setor_sistemico.id,
            unidade['id'],
            str_configuracao,
        )
        acoes_informadas = db.get_dict(consAcoesInformadas)

        unidade['valor_total_acoes_informadas'] = sum([acao['valor_unitario'] for acao in acoes_informadas])

        unidade['acoes_propostas'] = acoes_propostas
        unidade['acoes_informadas'] = acoes_informadas

    return locals()


@rtr('planejamento/templates/relatorio/despesas_recurso.html')
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico,Coordenador de Planejamento, Auditor')
def despesas_recurso(request):
    title = 'Distribuição das Despesas das Dimensões por Origem de Recurso'
    configuracoes = Configuracao.objects.all().order_by('-ano_base__ano')

    if not len(configuracoes):
        mensagem = 'Não existe período de vigência de planejamento cadastrado.'
        return locals()
    if 'configuracao' in request.POST:
        configuracao = Configuracao.objects.get(pk=request.POST['configuracao'])
    else:
        configuracao = Configuracao.objects.all().order_by('-ano_base__ano')[0]
    form = ConfiguracaoFiltroForm(id_config=configuracao.id)
    origem_recurso = OrigemRecurso.objects.filter(configuracao=configuracao)
    if not len(origem_recurso):
        mensagem = 'Não existe origem de recurso associada ao ano base.'
        return locals()

    configuracao = configuracoes[0]
    str_configuracao = f'AND pco.id = {configuracao.id}'

    id_configuracao = configuracao.id if configuracao else None
    data_hora = datetime.now()

    # verifica se foi repassado alguma configuracao ou pega o id do ultimo ano base cadastrado
    if 'configuracao' in request.POST and request.POST['configuracao'] != '':
        configuracao = Configuracao.objects.get(pk=int(request.POST['configuracao']))
        id_configuracao = configuracao.id
        str_configuracao = f'AND pco.id = {id_configuracao}'

    configuracao_form = ConfiguracaoFiltroForm(id_config=id_configuracao)
    # consulta todas origens de recurso
    # quando a origem for do tipo proprio (orcamento proprio) a consulta reflete o valor destinado à unidade administrativa
    origens_proprias = list(OrigemRecurso.propria.filter(configuracao=configuracao).values_list('id', flat=True))
    origens_nao_proprias = list(OrigemRecurso.objects.filter(configuracao=configuracao).exclude(id__in=origens_proprias).values_list('id', flat=True))

    # Devido à mudanças no planejamento a partir de 2014, foi necessária a alteração da consulta
    if configuracao.ano_base.ano < 2014:
        if origens_proprias:
            strOrigensRecursos = f"""SELECT t.*
                                    FROM
                                      (SELECT o.id,
                                              o.nome,
                                              coalesce(o.valor_disponivel, 0.00) AS orcamento,
                                              'recurso' AS tipo
                                       FROM planejamento_origemrecurso o,
                                            planejamento_configuracao pco
                                       WHERE o.id IN ({str(origens_nao_proprias)[1:-1]})
                                         AND o.configuracao_id = pco.id {str_configuracao}
                                       UNION SELECT r.setor_equivalente_id AS id,
                                                    'Unid. ' || s.sigla AS nome,
                                                    coalesce(r.orcamento, 0.00) AS orcamento,
                                                    'unidade' AS tipo
                                       FROM planejamento_unidadeadministrativa r,
                                            setor s,
                                            planejamento_configuracao pco
                                       WHERE r.setor_equivalente_id = s.id
                                         AND r.configuracao_id = pco.id {str_configuracao} ) t
                                    ORDER BY upper(t.nome);"""
        else:
            strOrigensRecursos = f"""SELECT o.id,
                                           o.nome,
                                           coalesce(o.valor_disponivel, 0.00) AS orcamento,
                                           'recurso' AS tipo
                                    FROM planejamento_origemrecurso o,
                                         planejamento_configuracao pco
                                    WHERE o.id IN ({str(origens_nao_proprias)[1:-1]})
                                      AND o.configuracao_id = pco.id {str_configuracao};"""
    else:
        if origens_proprias:
            strOrigensRecursos = f"""SELECT t.*
                                    FROM
                                      (SELECT o.id,
                                              o.nome,
                                              COALESCE(o.valor_custeio + o.valor_capital, 0.00) AS orcamento,
                                              'recurso' AS tipo
                                       FROM planejamento_origemrecurso o,
                                            planejamento_configuracao pco
                                       WHERE o.id IN ({str(origens_nao_proprias)[1:-1]})
                                         AND o.configuracao_id = pco.id {str_configuracao}
                                       UNION SELECT r.setor_equivalente_id AS id,
                                                    'Unid. ' || s.sigla AS nome,
                                                    COALESCE(oua.valor_custeio + oua.valor_capital, 0.00) AS orcamento,
                                                    'unidade' AS tipo
                                       FROM planejamento_unidadeadministrativa r,
                                            setor s,
                                            planejamento_configuracao pco,
                                            planejamento_origemrecurso o,
                                            planejamento_origemrecursoua oua
                                       WHERE r.setor_equivalente_id = s.id
                                         AND r.configuracao_id = pco.id
                                         AND o.id = oua.origem_recurso_id
                                         AND r.id = oua.unidade_id
                                         AND o.funcionamento_campus = TRUE {str_configuracao} ) t
                                    ORDER BY upper(t.nome);"""
        else:
            strOrigensRecursos = f"""SELECT o.id,
                                           o.nome,
                                           COALESCE(o.valor_custeio + o.valor_capital, 0.00) AS orcamento,
                                           'recurso' AS tipo
                                    FROM planejamento_origemrecurso o,
                                         planejamento_configuracao pco
                                    WHERE o.id IN ({str(origens_nao_proprias)[1:-1]})
                                      AND o.configuracao_id = pco.id {str_configuracao};"""
    origens_recursos = db.get_dict(strOrigensRecursos)

    # consulta todas as dimensoes
    lista_dimensoes = Dimensao.objects.all().order_by('descricao')

    for origem in origens_recursos:
        # verifica se o recurso é do tipo campus e caso seja pesquisa pela unidade administrativa associada
        if origem['tipo'] == 'recurso':
            str_recurso = 'og.id = {} {}'.format(origem['id'], str_configuracao)
        else:
            str_recurso = 'og.id in ({}) and u.setor_equivalente_id = {} {}'.format(str(origens_proprias)[1:-1], origem['id'], str_configuracao)
            origem['unidade_administrativa'] = UnidadeAdministrativa.objects.get(setor_equivalente=origem['id'], configuracao=id_configuracao)
            # atualiza o valor do id, que inicialmente apontava para o setor da unidade adm. para o id com origem de recurso propria
            origens = OrigemRecurso.propria.filter(configuracao=configuracao)
            if len(origens):
                origem['id'] = origens[0].id

        dimensoes = []
        if configuracao != configuracoes[0]:
            for dimensao in lista_dimensoes:
                strDespesaDimensao = f"""select coalesce(sum(at.quantidade*at.valor_unitario), 0.00) as valor
                                                from planejamento_metaunidade mu left join planejamento_acao a on mu.id = a.meta_unidade_id
                                                     left join planejamento_atividade at on a.id = at.acao_id
                                                     left join planejamento_origemrecurso og on og.id = at.tipo_recurso_id,
                                                     planejamento_meta m, planejamento_objetivoestrategico oe,
                                                     planejamento_dimensao d, planejamento_unidadeadministrativa u, planejamento_configuracao pco
                                                where m.id = mu.meta_id and
                                                      a.status != 'Indeferida' and
                                                      oe.id = m.objetivo_estrategico_id and
                                                      d.id = oe.dimensao_id and
                                                      u.id = mu.unidade_id and
                                                      d.id = {dimensao.id} and
                                                      u.configuracao_id = pco.id and
                                                      {str_recurso};"""
                despesa = db.get_dict(strDespesaDimensao)
                dimensoes.append({'id': dimensao.id, 'sigla': dimensao.sigla, 'valor': despesa[0]['valor']})
        else:
            for dimensao in lista_dimensoes:
                strDespesaDimensao = f"""SELECT COALESCE(SUM(at.quantidade*at.valor_unitario), 0.00) AS valor
                                                FROM planejamento_metaunidade mu LEFT JOIN planejamento_acao a ON mu.id = a.meta_unidade_id
                                                     LEFT JOIN planejamento_atividade at ON a.id = at.acao_id
                                                     LEFT JOIN planejamento_origemrecurso og ON og.id = at.tipo_recurso_id,
                                                     planejamento_meta m, planejamento_objetivoestrategico oe,planejamento_naturezadespesa n,
                                                     financeiro_naturezadespesa fn, planejamento_dimensao d, planejamento_unidadeadministrativa u, planejamento_configuracao pco
                                                WHERE m.id = mu.meta_id
                                                     AND oe.id = m.objetivo_estrategico_id
                                                     AND d.id = oe.dimensao_id
                                                     AND u.id = mu.unidade_id
                                                     AND at.acao_id = a.id
                                                     AND at.elemento_despesa_id = n.id
                                                     AND a.meta_unidade_id = mu.id
                                                     AND a.status != 'Indeferida'
                                                     AND n.naturezadespesa_id = fn.id
                                                     AND d.id = {dimensao.id}
                                                     AND u.configuracao_id = pco.id
                                                     AND {str_recurso};"""
                despesa = db.get_dict(strDespesaDimensao)
                dimensoes.append({'id': dimensao.id, 'sigla': dimensao.sigla, 'valor': despesa[0]['valor']})

        origem['dimensoes'] = dimensoes
        if origem['orcamento'] < sum([d['valor'] for d in dimensoes]):
            origem['debito'] = True
            origem['saldo'] = sum([d['valor'] for d in dimensoes]) - origem['orcamento']
        else:
            origem['credito'] = True
            origem['saldo'] = origem['orcamento'] - sum([d['valor'] for d in dimensoes])

    total_previsao = 0
    total_orcamento = 0
    total_orcamento_negativo = False
    for o in origens_recursos:
        total_previsao += o['orcamento']
        if 'debito' in o:
            total_orcamento -= o['saldo']
        else:
            total_orcamento += o['saldo']
    if total_orcamento < 0:
        total_orcamento = abs(total_orcamento)
        total_orcamento_negativo = True

    return locals()


@rtr('planejamento/templates/relatorio/despesas_recurso_unidadeadministrativa.html')
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico,Coordenador de Planejamento, Auditor')
def despesas_recurso_unidadeadministrativa(request):
    title = 'Distribuição das Despesas da Unidade Administrativa por Origem do Recurso'
    configuracoes = Configuracao.objects.all().order_by('-ano_base__ano')
    if not len(configuracoes):
        mensagem = 'Não existe período de vigência de planejamento cadastrado.'
        return locals()

    configuracao = configuracoes[0]

    # verifica se foi repassado alguma configuracao ou pega o id do ultimo ano base cadastrado
    if 'configuracao' in request.POST and request.POST['configuracao'] != '':
        configuracao = Configuracao.objects.get(pk=int(request.POST['configuracao']))

    # indica o id do campus que será utilizado para gerar o relatório de detalhamento
    campus = None

    if in_group(request.user, ['Coordenador de Planejamento']):
        unidade_administrativa = UnidadeAdministrativa.objects.get(
            setor_equivalente=get_setor_unidade_administrativa(request.user), configuracao=configuracao
        )
        if unidade_administrativa:
            campus = unidade_administrativa.setor_equivalente
        else:
            mensagem = 'Não existe unidade administrativa cadastrada para o setor de lotação do usuário.'
            return locals()
    else:
        try:
            unidade_administrativa = UnidadeAdministrativa.objects.get(pk=int(request.POST['campus']), configuracao=configuracao)
            campus = unidade_administrativa.setor_equivalente
        except Exception:
            mensagem = 'Selecione um Campus para gerar o relatório.'

    configuracao_form = ConfiguracaoFiltroForm(id_config=configuracao.id)
    campus_form = CampusFiltroForm(id_campus=campus.id if campus else None, id_configuracao=configuracao.id)

    if campus:
        ids_atividades = ''
        for i, id_atividade in enumerate(Atividade.objects.filter(acao__meta_unidade__unidade=unidade_administrativa).values_list('id', flat=True)):
            if i == 0:
                ids_atividades += str(id_atividade)
            else:
                ids_atividades += ',' + str(id_atividade)

        if ids_atividades != '':
            # verifica os totais gastos para cadas tipo de fonte de recurso
            strConsulta = f"""select a.tipo_recurso_id as id_recurso, o.nome as recurso, sum(a.quantidade*a.valor_unitario) as total
                                    from planejamento_atividade a, planejamento_origemrecurso o, planejamento_acao ac,
                                         planejamento_configuracao pco
                                    where o.id = a.tipo_recurso_id
                                          and a.acao_id = ac.id
                                          and a.id in ({ids_atividades})
                                          and a.tipo_recurso_id is not null
                                          and ac.status != 'Indeferida'
                                          and o.configuracao_id = pco.id
                                          AND pco.id = {configuracao.id}
                                    group by tipo_recurso_id, o.nome
                                    order by upper(o.nome);"""
            despesas = db.get_dict(strConsulta)
            total_despesas = sum([recurso['total'] for recurso in despesas])

    return locals()


@rtr('planejamento/templates/relatorio/despesas_recurso_dimensao.html')
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico, Coordenador de Planejamento, Auditor')
def despesas_recurso_dimensao(request):
    origem = None
    dimensao = None
    title = 'Distribuição das Despesas da Cada Dimensão por Origem de Recurso'
    # verifica se existem cadastros de configuracao

    configuracao = Configuracao.objects.latest('ano_base__ano')

    if 'configuracao' in request.GET or 'configuracao' in request.POST:
        configuracao_pk = request.GET.get('configuracao') or request.POST.get('configuracao')
        if configuracao_pk:
            configuracao = Configuracao.objects.get(pk=int(configuracao_pk))

    if 'origemrecurso' in request.GET or 'origemrecurso' in request.POST:
        origemrecurso_pk = request.GET.get('origemrecurso') or request.POST.get('origemrecurso')
        if origemrecurso_pk:
            origem = OrigemRecurso.objects.get(pk=int(origemrecurso_pk))

    if 'dimensao' in request.GET or 'dimensao' in request.POST:
        dimensao_pk = request.GET.get('dimensao') or request.POST.get('dimensao')
        if dimensao_pk:
            dimensao = Dimensao.objects.get(pk=int(dimensao_pk))

    origem_form = RelatorioOrigemRecursoForm(origemrecurso=origem.id if origem else None, id_configuracao=configuracao.id)
    dimensao_form = DimensaoFiltroForm(id_dimensao=dimensao.id if dimensao else None, empty_label='Todas')

    str_campus = ''
    if not in_group(request.user, ['Coordenador de Planejamento Sistêmico', 'Administrador de Planejamento']):
        unid_admin = UnidadeAdministrativa.objects.get(
            setor_equivalente__id=get_setor_unidade_administrativa(request.user).id, configuracao=configuracao
        )
        str_campus = f'AND u.id = {unid_admin.id}'
        configuracao_form = ConfiguracaoFiltroForm(id_config=configuracao.id)

    strConsulta = """select u.id, s.nome, coalesce(sum(at.quantidade*at.valor_unitario), 0.00) as valor
                            from planejamento_metaunidade mu left join planejamento_acao a on mu.id = a.meta_unidade_id
                                 left join planejamento_atividade at on a.id = at.acao_id,
                                 planejamento_meta m, planejamento_objetivoestrategico oe,
                                 planejamento_dimensao d, planejamento_unidadeadministrativa u,
                                 planejamento_configuracao c, setor s
                            where m.id = mu.meta_id and
                                  oe.id = m.objetivo_estrategico_id and
                                  d.id = oe.dimensao_id and
                                  u.id = mu.unidade_id and
                                  s.id = u.setor_equivalente_id and
                                  c.id = oe.configuracao_id and
                                  c.id = u.configuracao_id and
                                  a.status != 'Indeferida' and
                                  c.id = {}
                                  {}
                                  {}
                                  {}
                            group by u.id, s.nome
                            order by upper(s.nome);""".format(
        configuracao.id,
        f'and at.tipo_recurso_id = {origem.id}' if origem else '',
        f'and d.id = {dimensao.id}' if dimensao else '',
        str_campus,
    )
    campi = db.get_dict(strConsulta)
    return locals()


@rtr('planejamento/templates/relatorio/metas.html')
@group_required('Administrador de Planejamento,Coordenador de Planejamento Sistêmico,Coordenador de Planejamento')
def relatorio_metas(request):
    # indica o id do campus que será utilizado para gerar o relatório de metas

    title = 'Metas'
    campus = None

    if 'campus' in request.POST:
        if request.POST['campus'] == '':
            mensagem = 'Selecione um Campus para gerar o relatório.'
        else:
            unidade_administrativa = UnidadeAdministrativa.objects.get(pk=int(request.POST['campus']))
            campus = unidade_administrativa.setor_equivalente.id
    else:
        # verifica se a unidade administrativa associada ao usuário é do tipo tipo campus
        unidades_administrativas = UnidadeAdministrativa.objects.filter(
            tipo=TipoUnidade.CAMPUS, setor_equivalente=get_setor_unidade_administrativa(request.user)
        )
        if len(unidades_administrativas):
            unidade_administrativa = unidades_administrativas[0]
            campus = unidade_administrativa.setor_equivalente.id

    if 'configuracao' in request.POST:
        configuracao = Configuracao.objects.get(pk=request.POST['configuracao'])
    else:
        configuracao = Configuracao.objects.all().order_by('-ano_base__ano')[0]

    if not in_group(request.user, ['Coordenador de Planejamento']):
        form = CampusFiltroForm(id_campus=campus, id_config=configuracao.id)
        # apresenta uma mensagem indicando que é necessário escolher um campus antes de solicitar o relatório
        if campus is None:
            mensagem = 'Selecione um Campus para gerar o relatório.'

    if campus:
        # verifica se o usuário tem permissão de sistêmico, pois se tiver deve visualizar apenas as ações de sua competência
        str_pesquisa_sistemico = ''
        str_configuracao = f'o.configuracao_id = {configuracao.id} and '
        if in_group(request.user, ['Coordenador de Planejamento Sistêmico']):
            setor_sistemico = get_setor_unidade_administrativa(request.user)
            str_pesquisa_sistemico = f'd.setor_sistemico_id = {setor_sistemico.id} and '

        consMetas = f"""select d.descricao as dimensao, m.titulo, mu.quantidade, mu.valor_total as valor_proposto,
                            coalesce(sum(t.quantidade * t.valor_unitario), 0.00) as valor
                            from planejamento_unidadeadministrativa u,
                                 planejamento_meta m, planejamento_objetivoestrategico o, planejamento_dimensao d,
                                 planejamento_metaunidade mu left join planejamento_acao a on mu.id = a.meta_unidade_id
                                 left join planejamento_atividade t on a.id = t.acao_id
                            where d.id = o.dimensao_id and
                                  o.id = m.objetivo_estrategico_id and
                                  m.id = mu.meta_id and
                                  u.id = mu.unidade_id and
                                  a.status != 'Indeferida' and
                                  {str_pesquisa_sistemico}
                                  {str_configuracao}
                                  u.setor_equivalente_id = {campus}
                            group by d.descricao, m.titulo, mu.quantidade, mu.valor_total
                            order by m.titulo;"""

        metas = db.get_dict(consMetas)

    return locals()


@rtr('planejamento/templates/relatorio/detalhamento_gastos.html')
def relatorio_detalhamento_gastos(request):
    # filtros
    title = 'Detalhamento de Gastos por Natureza de Despesa'
    configuracoes = Configuracao.objects.all().order_by('-ano_base__ano')
    if not len(configuracoes):
        mensagem = 'Não existe período de vigência de planejamento cadastrado.'
        return locals()

    configuracao = configuracoes[0]

    origem = None
    unid_admin = None
    dimensao = None
    acao_orcam = None

    str_origem_recurso = ''
    str_dimensao = ''
    str_campus = ''
    str_acao_orcamento = ''

    data_hora = datetime.now()

    if 'configuracao' in request.POST and request.POST['configuracao'] != '':
        configuracao = Configuracao.objects.get(pk=int(request.POST['configuracao']))

    if 'origem' in request.POST and request.POST['origem'] != '':
        origens = OrigemRecurso.objects.filter(pk=int(request.POST['origem']), configuracao=configuracao)
        if len(origens):
            origem = origens[0]
            str_origem_recurso = f'AND por.id = {origem.id}'

    if 'dimensao' in request.POST and request.POST['dimensao'] != '':
        dimensao = Dimensao.objects.get(pk=int(request.POST['dimensao']))
        str_dimensao = f'AND pdi.id = {dimensao.id}'

    if 'acao_orcamento' in request.POST and request.POST['acao_orcamento'] != '':
        acao_orcam = apps.get_model('financeiro', 'Acao').objects.get(id=request.POST['acao_orcamento'])
        str_acao_orcamento = f"AND fac.id = '{acao_orcam.pk}'"

    if not in_group(request.user, ['Coordenador de Planejamento Sistêmico', 'Administrador de Planejamento', 'Auditor']):
        unid_admin = UnidadeAdministrativa.objects.get(
            setor_equivalente__id=get_setor_unidade_administrativa(request.user).id, configuracao=configuracao
        )
        str_campus = f'AND pua.id = {unid_admin.id}'
        configuracao_form = ConfiguracaoFiltroForm(id_config=configuracao.id)

    else:
        if 'campus' in request.POST and request.POST['campus'] != '':
            unidades = UnidadeAdministrativa.objects.filter(pk=int(request.POST['campus']), configuracao=configuracao)
            if len(unidades):
                unid_admin = unidades[0]
                str_campus = f'AND pua.id = {unid_admin.id}'
        campus_form = RelatorioCampusForm(
            id_campus=unid_admin.setor_equivalente.id if unid_admin else None, id_config=configuracao.id, empty_label='Todas'
        )

    origem_form = OrigemRecursoFiltroForm(id_origem=origem.id if origem else None, id_config=configuracao.id, empty_label='Todas')
    dimensao_form = DimensaoFiltroForm(id_dimensao=dimensao.id if dimensao else None, empty_label='Todas')
    acao_orcamento_form = AcaoFiltroForm(id_acao=acao_orcam.pk if acao_orcam else None, empty_label='Todas')

    # Devido à mudanças no planejamento a partir de 2014, foi necessária a alteração da consulta
    if 'configuracao' in request.POST and Configuracao.objects.get(pk=request.POST['configuracao']).ano_base.ano < 2014:
        str_tabela = ''
        str_complemento = 'AND fac.id = pac.acao_orcamento_id'
    else:
        str_tabela = ', financeiro_acaoano faa'
        str_complemento = 'AND por.acao_ano_id = faa.acao_id AND fac.id = faa.acao_id'

    sql = f"""SELECT fac.codigo_acao || fac.nome as acao_orcamento,
                    fnd.codigo as codigo_natureza_despesa,
                    fnd.nome as natureza_despesa,
                    pdi.descricao as dimensao,
                    str.sigla as unidade_administrativa,
                    SUM(pat.quantidade * pat.valor_unitario) as valor
                FROM planejamento_atividade pat, planejamento_acao pac, planejamento_metaunidade pmu,
                    planejamento_unidadeadministrativa pua, planejamento_meta pme, planejamento_origemrecurso por,
                    planejamento_objetivoestrategico poe, planejamento_dimensao pdi,
                    planejamento_configuracao pco, planejamento_naturezadespesa pnd,
                    setor str, financeiro_naturezadespesa fnd, financeiro_acao fac {str_tabela}
                WHERE fnd.id = pnd.naturezadespesa_id
                    AND pnd.id = pat.elemento_despesa_id
                    AND pac.id = pat.acao_id
                    AND pmu.id = pac.meta_unidade_id
                    AND pua.id = pmu.unidade_id
                    AND str.id = pua.setor_equivalente_id
                    AND pme.id = pmu.meta_id
                    AND poe.id = pme.objetivo_estrategico_id
                    AND pdi.id = poe.dimensao_id
                    AND pco.id = poe.configuracao_id
                    {str_complemento}
                    AND pac.status != 'Indeferida'
                    AND pat.valor_unitario != 0.00
                    AND por.id = pat.tipo_recurso_id
                    AND pco.id = por.configuracao_id
                    AND pco.id = {configuracao.id}
                    {str_dimensao}
                    {str_campus}
                    {str_acao_orcamento}
                    {str_origem_recurso}
                GROUP BY fac.codigo_acao, fac.nome, fnd.codigo, fnd.nome, pdi.descricao,
                        str.sigla
                ORDER BY fnd.codigo, pdi.descricao,
                        str.sigla;"""
    consulta = db.get_dict(sql)

    # verifica se existem dados retornados
    if not consulta:
        mensagem = 'Não existem informações cadastradas para os filtros utilizados.'
    else:
        # pesquisa quais as naturezas de despesa e unidades administrativas presentes na consulta
        relatorio = {}
        naturezas = []
        despesas = []

        for r in consulta:
            if r['codigo_natureza_despesa'] not in naturezas:
                naturezas.append(r['codigo_natureza_despesa'])
                despesas.append({'codigo': r['codigo_natureza_despesa'], 'descricao': r['natureza_despesa']})

        # ordena as listas de naturezas e unidades
        naturezas.sort()

        for registro in consulta:
            if registro['unidade_administrativa'] not in relatorio:
                relatorio[registro['unidade_administrativa']] = {}

                for nat in naturezas:
                    relatorio[registro['unidade_administrativa']][nat] = Decimal(0)

            relatorio[registro['unidade_administrativa']][registro['codigo_natureza_despesa']] += registro['valor']

        for unid_adm, nats in list(relatorio.items()):
            relatorio[unid_adm] = OrderedDict(sorted(iter(list(nats.items())), key=lambda k_v: (k_v[0], k_v[1])))

        relatorio = OrderedDict(sorted(iter(list(relatorio.items())), key=lambda k_v1: (k_v1[0], k_v1[1])))

    return locals()


@rtr('planejamento/templates/comentario_detalhes.html')
@group_required('Administrador de Planejamento, Coordenador de Planejamento Sistêmico, Coordenador de Planejamento')
def comentario_detalhar(request, id_acao):
    acao = AcaoValidacao.objects.filter(acao=id_acao)
    lista = acao.order_by('-id')
    acao = lista[0]
    return locals()


@rtr('planejamento/templates/nova_metas_validar.html')
@group_required('Coordenador de Planejamento Sistêmico,Administrador de Planejamento')
def metaunidade_validacao(request):
    title = 'Avaliar Ações'

    metas = MetaUnidade.objects.all()
    filtro_form = AcaoValidarFiltro(request.GET)

    if filtro_form.is_valid():
        metas = metas.filter(unidade__configuracao=filtro_form.cleaned_data['ano'])

        if filtro_form.cleaned_data['unidade'] is not None:
            metas = metas.filter(unidade=filtro_form.cleaned_data['unidade'])

        if filtro_form.cleaned_data['situacao'] != 'todas':
            metas_nao_concluidas = metas.filter(acao__status__in=[Situacao.PENDENTE, Situacao.PARCIALMENTE_DEFERIDA])
            metas_nao_concluidas = metas_nao_concluidas | metas.filter(acao__isnull=True)
            if filtro_form.cleaned_data['situacao'] == 'validadas':
                metas = metas.exclude(pk__in=metas_nao_concluidas)
            else:
                metas = metas.filter(pk__in=metas_nao_concluidas)
    else:
        configuracao = Configuracao.objects.all().order_by('-ano_base__ano')[0]
        metas = metas.filter(unidade__configuracao=configuracao)

    if not in_group(request.user, ['Administrador de Planejamento']) and in_group(request.user, ['Coordenador de Planejamento Sistêmico']):
        dimensoes = Dimensao.objects.filter(setor_sistemico=get_setor_unidade_administrativa(request.user))
        metas = metas.filter(meta__objetivo_estrategico__dimensao__in=dimensoes)

    metas = metas.select_related().order_by('unidade', 'meta')
    prepend_get = request.META.get('QUERY_STRING', '')
    if 'id_meta' in request.GET:
        prepend_get = '&'.join(prepend_get.split('&')[:-1])

    # Verifica se foi clicado
    id_meta = request.GET.get('id_meta')
    meta_validar = None
    if id_meta:
        id_meta = int(id_meta)
        meta_validar = nova_acoes_validar(request, id_meta)
        meta_validar = meta_validar.content

    return locals()


@rtr('planejamento/templates/nova_acoes_validar.html')
@group_required('Coordenador de Planejamento Sistêmico,Administrador de Planejamento')
def nova_acoes_validar(request, id_meta_unidade):
    meta_unidade = MetaUnidade.objects.get(id=id_meta_unidade)

    # indica se ainda é possível cadastrar acões por parte dos campi
    # caso seja possível, o sistêmico não poderá importar uma ação em nome do campus
    periodo_cadastro_campus = False
    configuracao = meta_unidade.meta.objetivo_estrategico.configuracao
    if date.today() >= configuracao.data_acoes_inicial and date.today() <= configuracao.data_acoes_final:
        periodo_cadastro_campus = True

    periodo_validacao_sistemico = False
    if date.today() >= configuracao.data_validacao_inicial and date.today() <= configuracao.data_validacao_final:
        periodo_validacao_sistemico = True

    # Pega as ações propostas para uma meta
    acoes = Acao.objects.filter(meta_unidade=meta_unidade)
    acoes_nao_importadas = MetaUnidadeAcaoProposta.objects.filter(meta_unidade=meta_unidade, acao__acao_indutora__isnull=True)

    if not in_group(request.user, ['Administrador de Planejamento']) and in_group(request.user, ['Coordenador de Planejamento Sistêmico']):
        dimensoes = Dimensao.objects.filter(setor_sistemico=get_setor_unidade_administrativa(request.user))
        acoes = acoes.filter(meta_unidade__meta__objetivo_estrategico__dimensao__in=dimensoes)
        acoes_nao_importadas = acoes_nao_importadas.filter(meta_unidade__meta__objetivo_estrategico__dimensao__in=dimensoes)

    valor_total_acoes = 0

    for acao in acoes:
        if acao.status == Situacao.DEFERIDA:
            valor_total_acoes = valor_total_acoes + acao.get_valor_total()

    return locals()


@rtr('planejamento/templates/relatorio/avaliar_acoes.html')
@group_required('Coordenador de Planejamento,Coordenador de Planejamento Sistêmico,Administrador de Planejamento')
def relatorio_avaliar_acoes(request):
    title = 'Relatório de Avaliação de Ações'

    acoes = Acao.objects.all()
    filtro_form = AcaoAvaliacaoForm(request.GET)

    if filtro_form.is_valid():
        # Filtro por ano
        acoes = acoes.filter(meta_unidade__unidade__configuracao=filtro_form.cleaned_data['ano'])

        # Filtro por unidade administrativa
        if filtro_form.cleaned_data['unidade'] is not None:
            acoes = acoes.filter(meta_unidade__unidade=filtro_form.cleaned_data['unidade'])

        # Filtro por Situacao
        acoes = acoes.filter(status=filtro_form.cleaned_data['situacao'])
    else:
        configuracao = Configuracao.objects.all().order_by('-ano_base__ano')[0]
        acoes = acoes.filter(meta_unidade__unidade__configuracao=configuracao)
        acoes = acoes.filter(status=filtro_form.fields['situacao'].choices[0][0])

    if not in_group(request.user, ['Administrador de Planejamento']) and in_group(request.user, ['Coordenador de Planejamento Sistêmico']):
        dimensoes = Dimensao.objects.filter(setor_sistemico=get_setor_unidade_administrativa(request.user))
        acoes = acoes.filter(meta_unidade__meta__objetivo_estrategico__dimensao__in=dimensoes)

    if not in_group(request.user, ['Coordenador de Planejamento Sistêmico', 'Administrador de Planejamento']) and in_group(
        request.user, ['Coordenador de Planejamento']
    ):
        unidade = get_setor_unidade_administrativa(request.user)
        acoes = acoes.filter(meta_unidade__unidade__setor_equivalente=unidade)

    acoes = acoes.select_related().order_by('-meta_unidade__unidade__configuracao__ano_base', 'meta_unidade__unidade')

    return locals()


@rtr('planejamento/templates/relatorio/tabela_origem_recurso.html')
@group_required('Coordenador de Planejamento,Coordenador de Planejamento Sistêmico,Administrador de Planejamento')
def relatorio_tabela_origem_recurso(request, id_unidade):
    title = 'Resumo das Origens de Recursos'
    origem_recursoua = OrigemRecursoUA.objects.filter(unidade__pk=id_unidade).order_by('origem_recurso__nome')
    return locals()


@rtr('planejamento/templates/relatorio/relatorio_origem_recurso.html')
@group_required('Coordenador de Planejamento,Coordenador de Planejamento Sistêmico,Administrador de Planejamento, Auditor')
def relatorio_origem_recurso(request):
    title = 'Relatório de Origem de Recursos'
    form = RelatorioOrigemRecursosForm(data=request.GET or None)
    if form.is_valid():
        origens = OrigemRecurso.objects.filter(id__in=form.cleaned_data['origem']).distinct('nome').order_by('nome')
        if form.cleaned_data['unidade']:
            unidades = OrigemRecursoUA.objects.filter(
                origem_recurso__in=form.cleaned_data['origem'], unidade__in=form.cleaned_data['unidade']
            ).order_by('unidade')
        else:
            unidades = OrigemRecursoUA.objects.filter(origem_recurso__in=form.cleaned_data['origem']).order_by('unidade')
    return locals()


@rtr('planejamento/templates/relatorio/planoacao.html')
@group_required('Administrador de Planejamento, Coordenador de Planejamento Sistêmico, Auditor')
def planoacao(request):
    title = 'Plano de Ações'

    form = PlanoAcaoForm(request.GET or None)
    if form.is_valid():
        configuracao = Configuracao.objects.get(id=form.cleaned_data['ano_base'].id)
        strConsDim = """select d.id, d.codigo, d.descricao, sd.nome as orgao_sistemico
                            from planejamento_dimensao d, setor sd, planejamento_objetivoestrategico o,
                                 planejamento_meta m, planejamento_metaunidade mu,
                                 planejamento_unidadeadministrativa u, setor s
                            where d.id = o.dimensao_id and
                                  sd.id = d.setor_sistemico_id and
                                  o.id = m.objetivo_estrategico_id and
                                  m.id = mu.meta_id and
                                  u.id = mu.unidade_id and
                                  s.id = u.setor_equivalente_id
                            group by d.id, d.codigo, d.descricao, sd.nome
                            order by d.codigo, d.descricao;"""

        consultadimensoes = db.get_dict(strConsDim)
        dimensoes = []
        for dimensao in consultadimensoes:
            strConsulta = """select o.id, o.codigo, o.descricao, o.macro_projeto_institucional
                                        from planejamento_objetivoestrategico o, planejamento_meta m, planejamento_metaunidade mu,
                                             planejamento_unidadeadministrativa u, planejamento_configuracao c
                                        where o.id = m.objetivo_estrategico_id and
                                              m.id = mu.meta_id and
                                              u.id = mu.unidade_id and
                                              o.dimensao_id = {} and
                                              c.id = o.configuracao_id and
                                              c.id = {}
                                        group by o.id, o.codigo, o.descricao, o.macro_projeto_institucional
                                        order by o.codigo, o.descricao, o.macro_projeto_institucional;""".format(
                dimensao['id'],
                configuracao.id,
            )
            objetivos_estrategicos = db.get_dict(strConsulta)

            for objetivo_estrategico in objetivos_estrategicos:
                objetivo_estrategico['valor'] = Decimal(0)
                consMetas = """select m.id, m.codigo, m.titulo, m.data_inicial, m.data_final
                                    from planejamento_meta m, planejamento_metaunidade mu
                                    where m.id = mu.meta_id and
                                          m.objetivo_estrategico_id = {}
                                    group by m.id
                                    order by m.id, codigo, titulo;""".format(objetivo_estrategico['id'])
                metas = db.get_dict(consMetas)

                for meta in metas:
                    consAcoes = """SELECT a.codigo, a.titulo, sum(at.quantidade * at.valor_unitario) AS valor
                                    FROM planejamento_metaunidade mu
                                        LEFT JOIN planejamento_acao a ON mu.id = a.meta_unidade_id
                                        LEFT JOIN planejamento_atividade AT ON a.id = AT.acao_id
                                        LEFT JOIN planejamento_origemrecurso og ON og.id = AT.tipo_recurso_id,
                                        planejamento_meta m, planejamento_objetivoestrategico oe, planejamento_naturezadespesa n,
                                        financeiro_naturezadespesa fn, planejamento_dimensao d, planejamento_unidadeadministrativa u,
                                        planejamento_configuracao pco
                                    WHERE m.id = mu.meta_id
                                      AND oe.id = m.objetivo_estrategico_id
                                      AND d.id = oe.dimensao_id
                                      AND u.id = mu.unidade_id
                                      AND AT.acao_id = a.id
                                      AND AT.elemento_despesa_id = n.id
                                      AND a.meta_unidade_id = mu.id
                                      AND n.naturezadespesa_id = fn.id
                                      AND u.configuracao_id = pco.id
                                      AND a.acao_indutora_id IS NOT NULL
                                      AND a.status = 'Deferida'
                                      AND m.id = {}
                                    GROUP BY a.codigo,
                                             a.titulo
                                    ORDER BY upper(a.titulo);""".format(meta['id'])
                    acoes = db.get_dict(consAcoes)

                    consAcoesIndutora = """ SELECT a.codigo, a.titulo, sum(at.quantidade * at.valor_unitario) AS valor
                                            FROM planejamento_metaunidade mu
                                            LEFT JOIN planejamento_acao a ON mu.id = a.meta_unidade_id
                                            LEFT JOIN planejamento_atividade AT ON a.id = AT.acao_id
                                            LEFT JOIN planejamento_origemrecurso og ON og.id = AT.tipo_recurso_id,
                                            planejamento_meta m, planejamento_objetivoestrategico oe, planejamento_naturezadespesa n,
                                            financeiro_naturezadespesa fn, planejamento_dimensao d, planejamento_unidadeadministrativa u,
                                            planejamento_configuracao pco
                                            WHERE m.id = mu.meta_id
                                              AND oe.id = m.objetivo_estrategico_id
                                              AND d.id = oe.dimensao_id
                                              AND u.id = mu.unidade_id
                                              AND AT.acao_id = a.id
                                              AND AT.elemento_despesa_id = n.id
                                              AND a.meta_unidade_id = mu.id
                                              AND n.naturezadespesa_id = fn.id
                                              AND u.configuracao_id = pco.id
                                              AND a.acao_indutora_id IS NULL
                                              AND a.status = 'Deferida'
                                              AND m.id = {}
                                            GROUP BY a.codigo,
                                                 a.titulo
                                            ORDER BY upper(a.titulo);""".format(meta['id'])
                    acoes_indutora = db.get_dict(consAcoesIndutora)
                    acoes_final = acoes_indutora + acoes
                    meta['acoes'] = acoes_final
                    meta['valor'] = sum([a['valor'] for a in acoes_final])
                    objetivo_estrategico['valor'] += meta['valor']

                objetivo_estrategico['metas'] = metas

            if objetivos_estrategicos:
                dimensao['objetivos_estrategicos'] = objetivos_estrategicos
                dimensoes.append(dimensao)

    return locals()


@rtr()
@group_required('Administrador de Planejamento')
def renumeracao_acoes_validar_periodo(request):
    title = 'Renumerar Ações'
    periodo_renumerar_acao = False
    configuracao = Configuracao.objects.latest('ano_base__ano')
    if (
        configuracao.data_validacao_final < date.today()
        and configuracao.data_metas_final < date.today()
        and configuracao.data_acoes_final < date.today()
    ):
        periodo_renumerar_acao = True
    return locals()


@rtr()
@group_required('Administrador de Planejamento')
def renumerar_acoes(request):
    configuracao = Configuracao.objects.latest('ano_base__ano')
    if (
        configuracao.data_validacao_final < date.today()
        and configuracao.data_metas_final < date.today()
        and configuracao.data_acoes_final < date.today()
    ):
        metas = Meta.objects.filter(objetivo_estrategico__configuracao__id=configuracao.id)
        for meta in metas:
            acoes = Acao.objects.filter(acao_indutora=None, meta_unidade__meta=meta)
            acoes_induzidas = Acao.objects.filter(meta_unidade__meta=meta, acao_indutora__isnull=False)
            max_codigo_induzidas = 0
            if acoes_induzidas.exists():
                max_codigo_induzidas = acoes_induzidas.latest('codigo').codigo
            for acao in acoes:
                max_codigo_induzidas += 1
                acao.codigo = max_codigo_induzidas
                acao.save()
        return httprr('..', 'Ações renumeradas com sucesso.')
    else:
        raise PermissionDenied
