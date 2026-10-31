from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.utils.safestring import mark_safe
from django.views.decorators.csrf import csrf_exempt

from djtools.utils import JsonResponse, httprr, render, rtr, permission_required
from materiais.forms import MaterialCotacaoFormFactory, RequisicaoAvaliarForm, SituacaoCotacaoForm
from materiais.models import Categoria, Material, MaterialCotacao, MaterialTag, Requisicao


@permission_required('materiais.delete_materialcotacao')
@rtr()
def materialcotacao_remover(request, pk):
    materialCotacao = MaterialCotacao.objects.get(id=pk)
    material_id = materialCotacao.material.id
    materialCotacao.delete()
    return httprr(f'/admin/materiais/material/{material_id}/', 'Cotação de Material removido com sucesso')


@rtr()
def requisicao(request, pk):
    requisicao = Requisicao.objects.get(pk=pk)
    return locals()


@permission_required('materiais.change_material')
@rtr()
def requisicao_avaliar(request, pk):
    title = 'Avaliar requisição'
    requisicao = Requisicao.get_pendentes().get(pk=pk)
    form = RequisicaoAvaliarForm(request.POST or None, instance=requisicao)
    if form.is_valid():
        form.cleaned_data.pop('requerimento')
        form.instance.avaliar(**form.cleaned_data)
        return httprr('/admin/materiais/requisicao/', 'Requisição avaliada com sucesso!')
    return locals()


def requisicao_pendente_remover(request, pk):
    requisicao = Requisicao.get_pendentes().get(pk=pk)
    if not requisicao.pode_remover_pendente():
        raise PermissionDenied
    requisicao.delete()
    return httprr('/admin/materiais/requisicao/', 'Remoção de Requisição Pendente foi realizada com sucesso.')


@rtr()
@permission_required('materiais.add_material')
def relatorio_cotacao(request):
    """
    Exibe materiais separados por cotação.

    """
    title = 'Materiais sem cotação por tag'
    tags = MaterialTag.objects.all()
    dados = []
    for t in tags:
        material = {}
        material['total'] = Material.objects.filter(tags=MaterialTag.objects.get(id=t.id), materialcotacao__isnull=True, ativo=True).count()
        material['descricao'] = MaterialTag.objects.get(id=t.id)
        dados.append(material)

    return locals()


@login_required
@csrf_exempt
def get_categorias(request):
    data = request.POST or request.GET
    id = data.get('filter_pks') or 0
    label = data.get('label')
    categorias_qs = Categoria.objects.filter(sub_elemento_nd_id=id)
    categorias = []
    for categoria in categorias_qs:
        categorias.append({'id': categoria.id, label: str(categoria)})

    return JsonResponse(categorias)


@login_required
@rtr()
def adicionar_cotacao(request, material_id):
    title = 'Adicionar Cotação'
    material = get_object_or_404(Material, pk=material_id)
    FormClass = MaterialCotacaoFormFactory(tipo=request.GET.get('tipo', None), material=material)
    form = FormClass(request.POST or None, request.FILES or None)
    if form.is_valid():
        form.save()
        return httprr(f'/materiais/visualizar_materialcotacoes/{material.id}/', 'Cotação adicionada com sucesso.')
    return locals()


@login_required
@rtr()
def editar_cotacao(request, materialcotacao_id, material_id):
    title = 'Editar Cotação'
    material = get_object_or_404(Material, pk=material_id)
    materialcotacao = get_object_or_404(MaterialCotacao, pk=materialcotacao_id)
    FormClass = MaterialCotacaoFormFactory(tipo=request.GET.get('tipo', None), material=material)
    form = FormClass(request.POST or None, request.FILES or None, instance=materialcotacao)
    if form.is_valid():
        form.save()
        return httprr(f'/materiais/visualizar_materialcotacoes/{material.id}/', 'Cotação editada com sucesso.')
    return locals()


@login_required
@rtr()
def visualizar_cotacoes(request, material_id):
    title = f'Material {material_id}'
    material = get_object_or_404(Material, pk=material_id)
    materialcotacao = MaterialCotacao.objects.filter(material_id=material_id)
    return locals()


@login_required
@rtr()
def detalhar_cotacoes(request, material_id, materialcotacao_id):
    title = f'Material Cotação {materialcotacao_id}'
    material = get_object_or_404(Material, pk=material_id)
    materialcotacao = get_object_or_404(MaterialCotacao, pk=materialcotacao_id)
    return locals()


@login_required
@rtr()
def ativar_cotacao(request, materialcotacao_id):
    title = f'Ativar Cotação {materialcotacao_id}'
    materialcotacao = get_object_or_404(MaterialCotacao, pk=materialcotacao_id)
    form = SituacaoCotacaoForm(request.POST or None)
    if form.is_valid():
        materialcotacao.data_validade = form.cleaned_data['data_validade']
        materialcotacao.ativo = True
        materialcotacao.save()
        return httprr('.', 'Cotação ativada com sucesso.')
    return locals()


@login_required
@rtr()
def inativar_cotacao(request, materialcotacao_id):
    materialcotacao = get_object_or_404(MaterialCotacao, pk=materialcotacao_id)
    materialcotacao.ativo = False
    materialcotacao.save()
    return httprr(f'/materiais/visualizar_materialcotacoes/{materialcotacao.material.id}/', 'Cotação inativada com sucesso.')


@login_required()
def visualizar_arquivo_pdf(request, materialcotacao_id):
    materialcotacao = get_object_or_404(MaterialCotacao, pk=materialcotacao_id)
    pdf_data = mark_safe(materialcotacao.arquivo.url)
    return render('viewer.html', locals())
