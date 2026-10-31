import csv
import io
import re
from collections import OrderedDict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from django.contrib import messages

import pandas as pd
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.defaultfilters import pluralize, truncatechars
from django.utils import html
from django.utils.safestring import mark_safe
from django.views.decorators.csrf import csrf_exempt

from almoxarifado.forms import (
    BalanceteEDDetalhadoFormFactory,
    BalanceteMaterialFormFactory,
    BuscaEmpenhoForm,
    CancelarItensEntradaForm,
    CancelarRequisicaoSaidaUserForm,
    ConfiguracaoEstoqueForm,
    DevolucaoItemFormFactory,
    EmpenhoConsumoForm,
    EmpenhoPermanenteForm,
    EntradaBuscaForm,
    EntradaDoacaoForm,
    EntradaDoacaoItemConsumoForm,
    EntradaDoacaoItemPermanenteForm,
    EntradaEditarForm,
    GetBalanceteEdForm,
    ImportacaoEstoqueCSVForm,
    NotasFornecimentoFormFactory,
    RelatorioSaldoAtualEDForm,
    RequisicaoBuscaFormFactory,
    TipoEtiquetaForm,
)
from almoxarifado.models import (
    CategoriaMaterialConsumo,
    ConfiguracaoEstoque,
    DevolucaoMaterial,
    Empenho,
    EmpenhoConsumo,
    Entrada,
    EntradaTipo,
    MaterialConsumo,
    MaterialEstoque,
    MaterialTipo,
    MovimentoAlmoxEntrada,
    MovimentoAlmoxEntradaTipo,
    MovimentoAlmoxSaida,
    RequisicaoAlmox,
    RequisicaoAlmoxUO,
    RequisicaoAlmoxUOMaterial,
    RequisicaoAlmoxUser,
    RequisicaoAlmoxUserMaterial,
    UnidadeMedida,
    ajusta_entradas_de_transferencias,
    calcula_valor_medio_atual,
)
from almoxarifado.relatorio import (
    historico_movimentacao,
    relatorio_balancete_ed_detalhado,
    relatorio_balancete_material,
)
from almoxarifado.utils import (
    OPERADOR_ALMOXARIFADO,
    OPERADOR_ALMOXARIFADO_OU_PATRIMONIO,
    TODOS_GRUPOS_ALMOXARIFADO,
)

from comum.models import Configuracao, Vinculo
from comum.relatorios import get_topo_com_titulo, rodape_data_e_assinatura
from comum.utils import get_uo, tl
from djtools import layout, relatorios
from djtools.etiquetas.labels import factory
from djtools.templatetags.filters import format_money_almox, in_group
from djtools.utils import (
    JsonResponse,
    PDFResponse,
    data_extenso,
    date_to_string,
    dict_from_keys_n_values,
    extrair_periodo,
    group_required,
    httprr,
    mask_money,
    permission_required,
    render,
    rtr,
    somar_dias,
    somar_indice,
    str_to_dateBR,
    to_ascii,
    user_has_one_of_perms,
)

from patrimonio.models import EmpenhoPermanente, EntradaPermanente
from rh.models import PessoaJuridica, Servidor, UnidadeOrganizacional


@layout.atribuidos_a_meus_grupos()
def index_atribuidos_a_meus_grupos(request):
    pendencias = []
    if request.user.has_group_cached(
        ['Coordenador de Almoxarifado', 'Operador de Almoxarifado', 'Coordenador de Almoxarifado Sistêmico'], ignore_groups_if_superuser=False
    ):
        qtd_requisicoes_usuario = RequisicaoAlmoxUser.get_pendentes(request.user).count()
        qtd_requisicoes_uo = RequisicaoAlmoxUO.get_pendentes(request.user).count()
        qtd_requisicoes = qtd_requisicoes_usuario + qtd_requisicoes_uo
        if qtd_requisicoes:
            plural = pluralize(qtd_requisicoes, 'ão,ões')
            pendencias.append(
                {
                    'titulo': f'Requisiç{plural} de Almoxarifado',
                    'subtitulo': 'a avaliar',
                    'qtd': qtd_requisicoes,
                    'url': '/almoxarifado/requisicoes_pendentes/',
                }
            )

        qtd_materiais_criticos = len(ConfiguracaoEstoque.get_materiais_criticos())
        if qtd_materiais_criticos:
            plural = pluralize(qtd_materiais_criticos, 'l,is')
            pendencias.append(
                {
                    'titulo': f'Materia{plural} com estoque crítico',
                    'subtitulo': 'a avaliar',
                    'qtd': qtd_materiais_criticos,
                    'url': '/almoxarifado/situacao_estoque/',
                }
            )

        hoje = datetime.now()
        prazo_15_dias = hoje.date() + timedelta(days=15)
        empenhos_entrega_15_dias = (
            Empenho.get_sem_atraso()
            .filter(Q(status='nao_iniciado') | Q(status='iniciado'))
            .filter(data_prazo__gte=hoje.date(), data_prazo__lte=prazo_15_dias, uo=get_uo(request.user))
            .count()
        )
        if empenhos_entrega_15_dias > 0:
            pendencias.append(
                {
                    'titulo': f'Empenho{pluralize(empenhos_entrega_15_dias)} com prazo de entrega em 15 dias',
                    'subtitulo': 'a avaliar',
                    'qtd': empenhos_entrega_15_dias,
                    'url': '/almoxarifado/empenhos/?prazo_15dias=Sim&status=nao_concluido&situacao=sem_atraso&buscaempenho_form=Aguarde...',
                }
            )

    return pendencias


@group_required(TODOS_GRUPOS_ALMOXARIFADO)
def servidor(request, input):
    """
    Retorna servidores que estão na mesma UO do usuário logado.
    --
    Usado somente em /almoxarifado/form_requisicao_usuario_pedido/
    """
    lista = []
    uo = get_uo(request.user)
    if uo:
        servidores = Servidor.objects.filter(pessoa_fisica__nome__istartswith=input, ativo=True)
        if not Configuracao.get_valor_por_chave('almoxarifado', 'descentralizado'):
            servidores = servidores.filter(setor__id__in=uo.setor.ids_descendentes)
        for s in servidores:
            lista.append(f'{s.nome} [<strong>{s.matricula}</strong>]|{s.get_vinculo().pk}\n')
    return HttpResponse(''.join(lista))


@group_required(TODOS_GRUPOS_ALMOXARIFADO)
def fornecedor(request, input):
    """
    Usado somente em /entrada_compra/
    """
    lista = []
    fornecedores = PessoaJuridica.objects.filter(nome__istartswith=input) | PessoaJuridica.objects.filter(cnpj__istartswith=input)
    for f in fornecedores[:10]:
        lista.append(f'{f.nome} [<strong>{f.cnpj}</strong>]|{f.get_vinculo().pk}\n')
    return HttpResponse(''.join(lista))


@group_required(TODOS_GRUPOS_ALMOXARIFADO)
def material_consumo_estoque_uo(request, uo_id, input):
    """
    Retorna materiais que têm estoque na UO passada
    --
    Usado em /almoxarifado/form_requisicao_usuario_pedido/ e
             /almoxarifado/form_requisicao_uo_pedido/
    """
    return HttpResponse(''.join(MaterialConsumo.buscar(palavras=input, com_estoque_em=uo_id, limite=10, autocomplete=True, user=request.user)))


@group_required(TODOS_GRUPOS_ALMOXARIFADO)
def empenho_todos(request, input):
    """
    Usado somente em /entrada_compra/
    """
    lista = []
    empenhos = Empenho.objects.filter(numero__icontains=input)
    if not request.user.has_group_cached('Coordenador de Almoxarifado Sistêmico'):
        empenhos = empenhos.filter(uo=get_uo(request.user))
    for empenho in empenhos:
        if empenho.pendente:
            lista.append('{} (UG: {})|{}\n'.format(empenho.numero, empenho.uo and empenho.uo or '?', empenho.id))
        if len(lista) == 10:
            break
    return HttpResponse(''.join(lista))


###########
# Empenho #
###########


@rtr()
@group_required(TODOS_GRUPOS_ALMOXARIFADO)
def empenho(request, empenho_pk):
    """Tela de detalhes do empenho, com opção para adicionar itens."""
    empenho = get_object_or_404(Empenho, pk=empenho_pk)
    title = f'Empenho {empenho.numero}'
    if not empenho.pode_ver():
        raise PermissionDenied

    resumo_ed = empenho.get_categoria_empenho()
    total = empenho.get_valor_total_categoria()

    link_editar = f'/admin/almoxarifado/empenho/{empenho.id:d}/'
    link_excluir = f'/admin/almoxarifado/empenho/{empenho.id:d}/delete/'

    continuar_cadastrando = int(request.GET.get('continuar_cadastrando', 0)) == 1
    if empenho.tipo_material.nome == 'consumo':
        if request.method == 'POST':
            form = EmpenhoConsumoForm(request.POST)
            form.instance.empenho = empenho
            if form.is_valid():
                continuar_cadastrando = form.cleaned_data['continuar_cadastrando']
                form.save()

                if continuar_cadastrando:
                    return httprr('./?continuar_cadastrando=1', 'Item de Empenho cadastrada com sucesso.')
                else:
                    return httprr('.', 'Item de Empenho cadastrada com sucesso.')

        else:
            form = EmpenhoConsumoForm()

    elif empenho.tipo_material.nome == 'permanente':
        if request.method == 'POST':
            form = EmpenhoPermanenteForm(request.POST)
            form.instance.empenho = empenho
            if form.is_valid():
                continuar_cadastrando = form.cleaned_data['continuar_cadastrando']
                form.save()

                if continuar_cadastrando:
                    return httprr('./?continuar_cadastrando=1', 'Item de Empenho cadastrada com sucesso.')
                else:
                    return httprr('.', 'Item de Empenho cadastrada com sucesso.')
        else:
            form = EmpenhoPermanenteForm()

    return locals()


@permission_required('patrimonio.delete_empenhopermanente')
def empenhopermanente_remover(request, id_empenhopermanente):
    empenhopermanente = get_object_or_404(EmpenhoPermanente, pk=id_empenhopermanente)
    empenho_pk = empenhopermanente.empenho_id
    numero = empenhopermanente.empenho.numero
    if empenhopermanente.can_delete():
        empenhopermanente.delete()
        if len(Empenho.objects.filter(id=empenho_pk)) > 0:
            # forca execucao do AtualizaInformacoes (se for ultimo item pendente, altera status para "Concluído")
            Empenho.objects.get(id=empenho_pk).atualizar_informacoes()

            # avisa sobre remocao do item
            return httprr(empenhopermanente.empenho.get_absolute_url(), 'Item removido com sucesso!')
        else:
            return httprr('/admin/almoxarifado/empenho/', f'O empenho de número {numero} foi removido porque possuia apenas um item!')
    raise PermissionDenied


@permission_required('almoxarifado.delete_empenhoconsumo')
def empenhoconsumo_remover(request, id_empenhoconsumo):
    empenhoconsumo = get_object_or_404(EmpenhoConsumo, pk=id_empenhoconsumo)
    empenho_pk = empenhoconsumo.empenho_id
    numero = empenhoconsumo.empenho.numero
    if empenhoconsumo.can_delete():
        empenhoconsumo.delete()
        if len(Empenho.objects.filter(id=empenho_pk)) > 0:
            # forca execucao do AtualizaInformacoes (se for ultimo item pendente, altera status para "Concluído")
            Empenho.objects.get(id=empenho_pk).atualizar_informacoes()

            # avisa sobre remocao do item
            return httprr(empenhoconsumo.empenho.get_absolute_url(), 'Item removido com sucesso!')
        else:
            return httprr('/admin/almoxarifado/empenho/', f'O empenho de número {numero} foi removido porque possuia apenas um item!')
    raise PermissionDenied


@rtr()
@permission_required('almoxarifado.view_empenho')
def empenhos(request):
    title = 'Empenhos'
    form = BuscaEmpenhoForm(request.GET or None)
    if form.is_valid():
        empenhos = Empenho.objects.all()

        # situação do Empenho
        if form.cleaned_data['situacao'] == 'atrasados':
            empenhos = Empenho.get_atrasados_pendentes()
        elif form.cleaned_data['situacao'] == 'sem_atraso':
            empenhos = Empenho.get_sem_atraso()
        elif form.cleaned_data['situacao'] == 'pendentes':
            empenhos = Empenho.get_pendentes()
        elif form.cleaned_data['situacao'] == 'concluidos_atraso':
            empenhos = Empenho.get_concluidos_com_atraso()

        if request.GET.get('prazo_15dias'):
            hoje = datetime.now()
            prazo_15_dias = hoje.date() + timedelta(days=15)
            empenhos = empenhos.filter(data_prazo__gte=hoje.date(), data_prazo__lte=prazo_15_dias, uo=get_uo(request.user))

        # filtro por Tipo Material?
        if form.cleaned_data['tipo_material']:
            empenhos = empenhos.filter(tipo_material=form.cleaned_data['tipo_material'])

        # filtro por Tipo Licitação?
        if form.cleaned_data['tipo_licitacao']:
            empenhos = empenhos.filter(tipo_licitacao=form.cleaned_data['tipo_licitacao'])

        # filtro por Status
        if form.cleaned_data['status'] == 'nao_concluido':
            empenhos = empenhos.filter(Q(status='nao_iniciado') | Q(status='iniciado'))
        elif form.cleaned_data['status'] != 'todos':
            empenhos = empenhos.filter(status=form.cleaned_data['status'])

        # filtro por UG
        if form.cleaned_data['ug_emitente']:
            empenhos = empenhos.filter(uo=form.cleaned_data['ug_emitente'])

        # busca por Número do Empenho
        if form.cleaned_data['numero_empenho']:
            empenhos = empenhos.filter(numero__icontains=form.cleaned_data['numero_empenho'])

        # busca por Número do Processo
        if form.cleaned_data['numero_processo']:
            empenhos = empenhos.filter(processo=form.cleaned_data['numero_processo'])

        # busca por Fornecedor
        if form.cleaned_data['vinculo_fornecedor']:
            empenhos = empenhos.filter(vinculo_fornecedor=form.cleaned_data['vinculo_fornecedor'])

        # busca por Número da Licitação
        if form.cleaned_data['numero_licitacao']:
            empenhos = empenhos.filter(numero_pregao__icontains=form.cleaned_data['numero_licitacao'])

        # busca por Empenhos com Elemento de Despesa Permanente
        if form.cleaned_data['elemento_despesa']:
            empenhos = empenhos.filter(empenhopermanente__categoria=form.cleaned_data['elemento_despesa'])
        # busca por Empenhos com Elemento de Despesa Consumo
        if form.cleaned_data['elemento_despesa_consumo']:
            empenhos = empenhos.filter(empenhoconsumo__material__categoria=form.cleaned_data['elemento_despesa_consumo'])
        # descrição do item
        if form.cleaned_data['descricao_item']:
            empenhos = empenhos.filter(
                Q(empenhopermanente__descricao__unaccent__icontains=form.cleaned_data['descricao_item'])
                | Q(empenhoconsumo__material__search__contains=to_ascii(form.cleaned_data['descricao_item']).upper())
            )

        # remove duplicados e ordena
        empenhos = empenhos.distinct().order_by('-numero')

    return locals()


@csrf_exempt
@group_required(OPERADOR_ALMOXARIFADO_OU_PATRIMONIO)
def get_itens_empenho(request):
    """
    Utilizado na entrada de nota fiscal (suap/templates/form_entrada.html)
    """
    # FIXME: implementar método get_itens_pendentes na classe Empenho.
    empenho = Empenho.objects.get(id=request.POST['empenho_id'])
    if empenho.tipo_material.nome == 'consumo':
        empenho_itens = EmpenhoConsumo.get_pendentes(empenho)
    else:
        empenho_itens = EmpenhoPermanente.get_pendentes(empenho)
    if not empenho_itens:
        return JsonResponse({'valid': False, 'html': 'O EMPENHO não tem itens pendentes'.decode('utf-8')})
    html = render('empenho_itens.html', {'tipo_material': empenho.tipo_material.nome, 'empenho_itens': empenho_itens})
    vinculo_fornecedor = empenho.vinculo_fornecedor
    vinculo_fornecedor_json = {'id': vinculo_fornecedor.id, 'nome': vinculo_fornecedor.pessoa.nome}
    return JsonResponse({'itens': html.content.decode(), 'vinculo_fornecedor': vinculo_fornecedor_json})


@csrf_exempt
@group_required(OPERADOR_ALMOXARIFADO)
def info_solicitante(request):
    if 'solicitante_id' not in request.POST:
        raise PermissionDenied
    vinculo = Vinculo.objects.get(pk=request.POST['solicitante_id'])
    unidade = vinculo.setor.uo
    setor = f'{vinculo.setor.sigla} - {vinculo.setor.nome} ({unidade})'
    return JsonResponse({'matricula': vinculo.relacionamento.matricula, 'setor': setor})


###########
# Entrada #
###########
def pode_remover_itens_entrada(user, entrada) -> bool:
    """
    Indica se o usuário pode remover itens da entrada de material permanente.

    O Coordenador de Patrimônio atua apenas no próprio campus; o Coordenador de
    Patrimônio Sistêmico, em qualquer um. Entrada sem nenhum item removível — porque
    todos já foram removidos ou porque os que restam têm inventário baixado — não
    oferece a ação.
    """
    if entrada.tipo_material != MaterialTipo.PERMANENTE():
        return False
    if not EntradaPermanente.cancelaveis(entrada).exists():
        return False
    if in_group(user, 'Coordenador de Patrimônio Sistêmico'):
        return True
    return in_group(user, 'Coordenador de Patrimônio') and entrada.uo == get_uo(user)


@rtr()
def entrada(request, entrada_id):
    entrada = get_object_or_404(Entrada, id=entrada_id)
    title = str(entrada)
    if not entrada.pode_ver():
        raise PermissionDenied

    resumo_ed = entrada.get_elem_despesa_entrada()
    total = format_money_almox(entrada.get_valor_total())

    itens_cancelados = entrada.itens_cancelados.select_related('categoria', 'cancelado_por')
    pode_remover_itens = pode_remover_itens_entrada(request.user, entrada)

    return locals()


@rtr()
@group_required('Operador de Almoxarifado, Coordenador de Almoxarifado, Coordenador de Almoxarifado Sistêmico')
def entrada_editar(request, entrada_id):
    entrada = get_object_or_404(Entrada, id=entrada_id)
    title = f'Editar {entrada}'
    if request.method == 'POST':
        form = EntradaEditarForm(request.POST, instance=entrada)
        if form.is_valid():
            form.save()
            return httprr(entrada.get_absolute_url(), f'{form.instance} alterada!')
    else:
        form = EntradaEditarForm(instance=entrada)
    return locals()


@rtr()
@group_required('Coordenador de Almoxarifado, Coordenador de Almoxarifado Sistêmico')
def entrada_remover(request, entrada_id):
    entrada = get_object_or_404(Entrada, id=entrada_id)
    if not entrada.can_delete():
        return httprr(entrada.get_absolute_url(), 'Esta entrada não pode ser removida.', 'error')
    entrada.delete()
    return httprr('/almoxarifado/entrada_busca/', 'Entrada NF removida com sucesso')


@rtr()
@group_required('Coordenador de Patrimônio, Coordenador de Patrimônio Sistêmico')
def entrada_cancelar_itens(request, entrada_id):
    """
    Remove os itens marcados de uma entrada de material permanente.

    Os inventários dos itens selecionados e toda a sua movimentação (carga contábil,
    transferências etc.) são removidos, e um registro auditável com a justificativa fica
    disponível na aba "Itens Removidos" da entrada.
    """
    entrada = get_object_or_404(Entrada, id=entrada_id)
    if not pode_remover_itens_entrada(request.user, entrada):
        raise PermissionDenied

    title = f'Remover Itens — {entrada}'
    itens = list(entrada.entradapermanente_set.order_by('categoria__codigo', 'descricao', 'id'))
    form = CancelarItensEntradaForm(request.POST or None, entrada=entrada)

    if request.method == 'POST' and form.is_valid():
        justificativa = form.cleaned_data['justificativa']
        selecionados = list(form.cleaned_data['itens'])
        with transaction.atomic():
            for item in selecionados:
                item.cancelar(justificativa)
        return httprr(f'{entrada.get_absolute_url()}?tab=itens_removidos', f'{len(selecionados)} item(ns) removido(s) com sucesso.')

    return locals()


@rtr()
@group_required(TODOS_GRUPOS_ALMOXARIFADO)
def adicionar_item(request, entrada_id):
    title = 'Adicionar Item'
    entrada = get_object_or_404(Entrada, pk=entrada_id)

    form = None
    if request.method == 'POST':
        if entrada.tipo_material == MaterialTipo.CONSUMO():
            form = EntradaDoacaoItemConsumoForm(request.POST)
            if form.is_valid():
                # efetua registro em MovimentoAlmoxEntrada
                material = form.cleaned_data['material']
                qtd = form.cleaned_data['qtd']
                valor = form.cleaned_data['valor']
                entrada.efetuar_entrada_material_consumo(material, qtd, valor)
                return httprr('..', 'Item adicionado com sucesso.')

        elif entrada.tipo_material == MaterialTipo.PERMANENTE():
            form = EntradaDoacaoItemPermanenteForm(request.POST)
            form.instance.entrada = entrada
            if form.is_valid():
                form.save()
                return httprr('..', 'Item adicionado com sucesso.')

    else:
        if entrada.tipo_material == MaterialTipo.CONSUMO():
            form = EntradaDoacaoItemConsumoForm()
        elif entrada.tipo_material == MaterialTipo.PERMANENTE():
            form = EntradaDoacaoItemPermanenteForm()

    return locals()


@rtr()
@permission_required('almoxarifado.pode_ver_entrada')
def entrada_busca(request):
    """
    View que exibe tanto o formulário para busca de entradas como também o resultado da busca.
    """
    title = 'Busca de Entradas'
    form = EntradaBuscaForm(request.GET or None)
    if form.is_valid():
        uo = form.cleaned_data['uo']
        vinculo_fornecedor = form.cleaned_data['vinculo_fornecedor']
        tipo_material = form.cleaned_data['tipo_material']
        tipo_entrada = form.cleaned_data['tipo_entrada']
        empenho = form.cleaned_data['empenho']
        processo = form.cleaned_data['processo']
        numero_nota_fiscal = form.cleaned_data['numero_nota_fiscal']
        data_inicial = form.cleaned_data['data_inicial']
        data_final = form.cleaned_data['data_final']
        descricao_material = form.cleaned_data['descricao_material']

        entradas = Entrada.objects.all()
        if uo:
            entradas = entradas.filter(uo=uo)
        if vinculo_fornecedor:
            entradas = entradas.filter(vinculo_fornecedor=vinculo_fornecedor)
        if numero_nota_fiscal:
            entradas = entradas.filter(numero_nota_fiscal__icontains=numero_nota_fiscal)
        if empenho:
            entradas = entradas.filter(
                Q(movimentoalmoxentrada__empenho_consumo__empenho=empenho) | Q(entradapermanente__empenho_permanente__empenho=empenho)
            )
        if processo:
            entradas = entradas.filter(
                Q(entradapermanente__empenho_permanente__empenho__processo=processo)
                | Q(movimentoalmoxentrada__empenho_consumo__empenho__processo=processo)
                | Q(processo=processo)
            )
        if tipo_material:
            entradas = entradas.filter(tipo_material=tipo_material)
            if descricao_material:
                if tipo_material == MaterialTipo.PERMANENTE():
                    entradas = entradas.filter(entradapermanente__descricao__unaccent__icontains=descricao_material)
                elif tipo_material == MaterialTipo.CONSUMO():
                    entradas = entradas.filter(movimentoalmoxentrada__material__nome__unaccent__icontains=descricao_material)
        if tipo_entrada:
            entradas = entradas.filter(tipo_entrada=tipo_entrada)
        if data_inicial:
            entradas = entradas.filter(data__date__gte=data_inicial)
        if data_final:
            entradas = entradas.filter(data__date__lte=data_final)
        entradas = entradas.order_by('-data').distinct()

        # soma por ELEMENTO DE DESPESA
        elementos_despesas, total_entradas = Entrada.total_elementos_despesas(
            uo, vinculo_fornecedor, tipo_material, tipo_entrada, empenho, processo, numero_nota_fiscal, data_inicial, data_final, descricao_material
        )
    parametros = request.GET.urlencode()
    return locals()


@group_required(TODOS_GRUPOS_ALMOXARIFADO)
def entrada_pdf(request, entrada_id):
    """Gera PDF de detalhes da entrada."""
    # Bloqueio de acesso à visualização da entrada com base na permissão do usuários
    if not request.user.has_perm('almoxarifado.pode_ver_entrada'):
        raise PermissionDenied

    entrada = get_object_or_404(Entrada, pk=entrada_id)
    fields = []

    if entrada.tipo_entrada.nome == 'compra':
        assinatura = 'Coordenação de Almoxarifado'
    else:
        assinatura = 'Coordenação de Patrimônio'

    tipo_entrada = entrada.tipo_entrada.nome

    fields.append([f'<b>Campus de Entrada:</b> {entrada.uo}', f'<b>Data de Entrada</b>: {entrada.get_data()}'])

    if tipo_entrada == 'doacao':
        fields.append(['<b>Tipo de Entrada:</b>:', entrada.tipo_entrada.nome.capitalize() + ' - ' + entrada.tipo_material.nome.capitalize()])

    else:
        empenho = entrada.get_empenho()
        processo = ''
        status = ''
        licitacao = ''
        if empenho:
            status = entrada.get_info_prazo()
            processo = empenho.processo or ''
            tipo_licitacao = empenho.tipo_licitacao
            if tipo_licitacao:
                licitacao = tipo_licitacao.nome + ' - ' + (empenho.numero_pregao or '')
            fields.append(
                [
                    '<b>Tipo de Entrada:</b> {}'.format(entrada.tipo_entrada.nome.capitalize() + ' - ' + entrada.tipo_material.nome.capitalize()),
                    f'<b>Situação da Entrada:</b> {status}',
                ]
            )
            fields.append([f'<b>Licitação:</b> {licitacao}', f'<b>Empenho:</b> {empenho}'])

            fields.append(
                [
                    f'<b>Processo do Empenho:</b> {processo}',
                    f'<b>Data de Recebimento do Empenho:</b> {date_to_string(empenho.data_recebimento_empenho)}',
                ]
            )
            fields.append(['<b>Observação:</b>', empenho.observacao])

    fields.append(
        ['<b>Número Nota Fiscal:</b> {}'.format(entrada.numero_nota_fiscal or '-'), f'<b>Data Nota Fiscal:</b> {entrada.get_data_nota_fiscal()}']
    )
    telefones = entrada.vinculo_fornecedor.pessoa.telefones
    fields.append(
        [
            f'<b>Fornecedor:</b> {html.escape(entrada.vinculo_fornecedor.pessoa.nome)}',
            f'<b>CPF/CNPJ Fornecedor:</b> {html.escape(entrada.vinculo_fornecedor.pessoa.get_cpf_ou_cnpj())}',
        ]
    )

    fields.append(['<b>E-mail Fornecedor:</b> {}'.format(entrada.vinculo_fornecedor.email_pessoal or ''), f'<b>Fone Fornecedor:</b> {telefones}'])

    tabela_dados = [['Código', 'Material', 'Cód. ED', 'Conta Contábil', 'Qtd.', 'Valor Unitário', 'Valor Total']]

    for item in entrada.get_itens():
        valor_unit = item.get_valor_unitario()
        valor_unit = valor_unit.replace('.', '')
        valor_unit = valor_unit.replace(',', '.')

        valor_unitario = Decimal(valor_unit)

        valor_unitario = f'{valor_unitario:,}'
        valor_unitario = valor_unitario.replace('.', ';')
        valor_unitario = valor_unitario.replace(',', '.')
        valor_unitario = valor_unitario.replace(';', ',')

        val = item.get_valor()
        val = val.replace('.', '')
        val = val.replace(',', '.')

        valor = Decimal(val)
        valor = f'{valor:,}'
        valor = valor.replace('.', ';')
        valor = valor.replace(',', '.')
        valor = valor.replace(';', ',')

        material = item.get_material()
        codigo = ''
        if entrada.tipo_material == MaterialTipo.CONSUMO():
            material = item.get_material().nome
            codigo = item.get_material().codigo
        planocontas = None
        if item.get_categoria().plano_contas:
            planocontas = item.get_categoria().plano_contas.codigo
        row = [
            codigo,
            truncatechars(html.escape(material), 3743),
            item.get_categoria().codigo,
            planocontas,
            item.qtd,
            item.get_valor_unitario(),
            item.get_valor(),
        ]
        tabela_dados.append(row)

    tabela_info = relatorios.table(fields, w=[95, 95], escape=False)
    tabela_dados = relatorios.table(tabela_dados, head=1, zebra=1, w=[15, 90, 10, 25, 10, 20, 20], count=1, a=['l', 'l', 'c', 'c', 'r', 'r', 'r'])
    p1 = 'Dados da Entrada'
    p2 = 'Itens da Entrada'

    p3 = f'Valor Total: {entrada.get_valor()}'

    body = [
        *get_topo_com_titulo('Detalhamento de Entrada'),
        relatorios.para(p1, style='h2', align='left'),
        relatorios.space(4),
        tabela_info,
        relatorios.space(8),
        relatorios.para(p2, style='h2', align='left'),
        relatorios.space(4),
        tabela_dados,
        relatorios.space(4),
        relatorios.para(p3, align='right'),
    ]

    return PDFResponse(relatorios.PdfReport(body=body, footer_args=rodape_data_e_assinatura(assinatura)).generate(), anexo=False)


@group_required(TODOS_GRUPOS_ALMOXARIFADO)
def entrada_inventarios_pdf(request, entrada_id):
    """Gera PDF de detalhes da entrada."""
    # Bloqueio de acesso à visualização da entrada com base na permissão do usuários
    entrada = get_object_or_404(Entrada, pk=entrada_id)
    fields = []

    if not request.user.has_perm('almoxarifado.pode_ver_entrada') and not entrada.tipo_material == MaterialTipo.PERMANENTE():
        raise PermissionDenied

    if entrada.tipo_entrada.nome == 'compra':
        assinatura = 'Coordenação de Almoxarifado'
    else:
        assinatura = 'Coordenação de Patrimônio'

    tipo_entrada = entrada.tipo_entrada.nome

    fields.append([f'<b>Campus de Entrada:</b> {entrada.uo}', f'<b>Data de Entrada</b>: {entrada.get_data()}'])

    if tipo_entrada == 'doacao':
        fields.append(['<b>Tipo de Entrada:</b>:', entrada.tipo_entrada.nome.capitalize() + ' - ' + entrada.tipo_material.nome.capitalize()])

    else:
        empenho = entrada.get_empenho()
        processo = ''
        status = ''
        licitacao = ''
        if empenho:
            status = entrada.get_info_prazo()
            processo = empenho.processo or ''
            tipo_licitacao = empenho.tipo_licitacao
            if tipo_licitacao:
                licitacao = tipo_licitacao.nome + ' - ' + (empenho.numero_pregao or '')
            fields.append(
                [
                    '<b>Tipo de Entrada:</b> {}'.format(entrada.tipo_entrada.nome.capitalize() + ' - ' + entrada.tipo_material.nome.capitalize()),
                    f'<b>Situação da Entrada:</b> {status}',
                ]
            )
            fields.append([f'<b>Licitação:</b> {licitacao}', f'<b>Empenho:</b> {empenho}'])

            fields.append(
                [
                    f'<b>Processo do Empenho:</b> {processo}',
                    f'<b>Data de Recebimento do Empenho:</b> {date_to_string(empenho.data_recebimento_empenho)}',
                ]
            )
            fields.append(['<b>Observação:</b>', empenho.observacao])

    fields.append(
        ['<b>Número Nota Fiscal:</b> {}'.format(entrada.numero_nota_fiscal or '-'), f'<b>Data Nota Fiscal:</b> {entrada.get_data_nota_fiscal()}']
    )

    telefones = entrada.vinculo_fornecedor.pessoa.telefones
    fields.append(
        [
            f'<b>Fornecedor:</b> {html.escape(entrada.vinculo_fornecedor.pessoa.nome)}',
            f'<b>CPF/CNPJ Fornecedor:</b> {html.escape(entrada.vinculo_fornecedor.pessoa.get_cpf_ou_cnpj())}',
        ]
    )

    fields.append(['<b>E-mail Fornecedor:</b> {}'.format(entrada.vinculo_fornecedor.email_pessoal or ''), f'<b>Fone Fornecedor:</b> {telefones}'])

    tabela_dados = [['Número', 'Material', 'Cód. ED', 'Conta Contábil', 'Valor']]

    for item in entrada.get_inventarios():
        plano_contas = None
        if item.entrada_permanente.categoria.plano_contas is not None:
            plano_contas = item.entrada_permanente.categoria.plano_contas.codigo
        row = [
            item.numero,
            truncatechars(html.escape(item.get_descricao()), 1000),
            item.entrada_permanente.categoria.codigo,
            plano_contas,
            item.get_valor(),
        ]
        tabela_dados.append(row)

    tabela_info = relatorios.table(fields, w=[95, 95], escape=False)
    tabela_dados = relatorios.table(tabela_dados, head=1, zebra=1, w=[15, 100, 20, 20, 25], count=1, a=['l', 'l', 'c', 'c', 'r'])
    p1 = 'Dados da Entrada'
    p2 = 'Inventários da Entrada'

    body = [
        *get_topo_com_titulo('Inventários da Entrada'),
        relatorios.para(p1, style='h2', align='left'),
        relatorios.space(4),
        tabela_info,
        relatorios.space(8),
        relatorios.para(p2, style='h2', align='left'),
        relatorios.space(4),
        tabela_dados,
    ]

    return PDFResponse(relatorios.PdfReport(body=body, footer_args=rodape_data_e_assinatura(assinatura)).generate(), anexo=False)


@rtr()
@group_required(OPERADOR_ALMOXARIFADO_OU_PATRIMONIO)
def entrada_doacao(request):
    title = 'Efetuar Entrada de Doação'
    uo = request.user.get_vinculo().setor.uo
    if not uo:
        raise PermissionDenied
    if request.method == 'POST':
        form = EntradaDoacaoForm(request.POST)
        if form.is_valid():
            form.save()
            return httprr(form.instance.get_absolute_url(), 'Entrada realizada com sucesso.')
    else:
        form = EntradaDoacaoForm()
    return locals()


@rtr()
@group_required(OPERADOR_ALMOXARIFADO_OU_PATRIMONIO)
def entrada_compra(request):
    """Exibe o formulário para efetuar entradas e efetua as entradas."""
    try:
        uo = request.user.get_vinculo().setor.uo
    except AttributeError:
        uo = None
    if not uo:
        raise PermissionDenied
    return {'uo': uo, 'title': 'Efetuar Entrada de Compra'}


@group_required(OPERADOR_ALMOXARIFADO_OU_PATRIMONIO)
def entrada_realizar(request):
    # COMPRA (cada item entrado corresponde a um item empenhado)
    if 'empenho_hidden' not in request.POST:
        return httprr('..', 'Erro ao realizar entrada.')
    empenho = Empenho.objects.get(id=request.POST['empenho_hidden'])
    if empenho.tipo_material.nome == 'consumo':
        tipo_material = MaterialTipo.CONSUMO()
    else:
        tipo_material = MaterialTipo.PERMANENTE()

    entrada = Entrada(
        data=str_to_dateBR(request.POST['data_entrada']),
        tipo_entrada=EntradaTipo.COMPRA(),
        tipo_material=tipo_material,
        numero_nota_fiscal=request.POST['numero_nota'],
        data_nota_fiscal=str_to_dateBR(request.POST['data_nota']),
        uo=request.user.get_vinculo().setor.uo,
        vinculo_fornecedor=Vinculo.objects.get(pk=request.POST['fornecedor_hidden']),
    )
    entrada.save()

    empenho_itens = request.POST.getlist('empenho_itens')
    qtds = request.POST.getlist('qtds')

    # Material de consumo
    if tipo_material.nome == 'consumo':
        for index, id_ in enumerate(empenho_itens):
            qtd_adquirida = int(qtds[index])
            empenho_consumo = EmpenhoConsumo.objects.get(pk=int(id_))
            empenho_consumo.efetuar_entrada(entrada, qtd_adquirida)

    # Material permanente
    else:
        for index, id_ in enumerate(empenho_itens):
            qtd_adquirida = int(qtds[index])
            empenho_permanente = EmpenhoPermanente.objects.get(pk=int(id_))
            empenho_permanente.qtd_adquirida += qtd_adquirida
            empenho_permanente.save()
            entrada_permanente = EntradaPermanente(
                entrada=entrada,
                empenho_permanente=empenho_permanente,
                categoria=empenho_permanente.categoria,
                descricao=empenho_permanente.descricao,
                qtd=qtd_adquirida,
                valor=empenho_permanente.valor,
            )
            entrada_permanente.save(user=request.user)
    empenho.atualizar_informacoes()

    return httprr(entrada.get_absolute_url(), 'Entrada realizada com sucesso.')


@group_required(TODOS_GRUPOS_ALMOXARIFADO)
def entrada_item_estornar(request, tipo_entrada, item_id):
    """Estorna `MovimentoAlmoxEntrada` ou `EntradaPermanente`."""
    Classe = {'consumo': MovimentoAlmoxEntrada, 'permanente': EntradaPermanente}[tipo_entrada]
    item = get_object_or_404(Classe, pk=item_id)
    if not item.can_delete():
        raise PermissionDenied
    if item.entrada.tipo_material == MaterialTipo.CONSUMO():
        material_a_atualizar = MaterialEstoque.objects.get(material=item.material, uo=item.entrada.uo)
        quantidade_atual = material_a_atualizar.quantidade - item.qtd
        valor_medio = 0
        if quantidade_atual != 0:
            valor_medio = (
                (material_a_atualizar.quantidade * material_a_atualizar.valor_medio)
                - (item.qtd * Decimal(item.get_valor_unitario().replace(',', '.')))
            ) / quantidade_atual
        material_a_atualizar.valor_medio = valor_medio
        material_a_atualizar.quantidade = quantidade_atual
        material_a_atualizar.save()
    item.delete()
    entrada_removida = not Entrada.objects.filter(pk=item.entrada.id).count()
    url = entrada_removida and '/almoxarifado/entrada_busca/' or f'/almoxarifado/entrada/{item.entrada.id}/'
    return httprr(url, 'Item de entrada estornado com sucesso!')


@rtr()
@group_required(TODOS_GRUPOS_ALMOXARIFADO)
def detalhar_elemento_despesa(request, elemento_despesa_id):
    title = 'Detalhamento de Elemento de Despesa'

    uo = request.GET.get('uo')
    vinculo_fornecedor = request.GET.get('vinculo_fornecedor')
    numero_nota_fiscal = request.GET.get('numero_nota_fiscal')
    empenho = request.GET.get('numero_nota_fiscal')
    processo = request.GET.get('processo')
    tipo_material = request.GET.get('tipo_material')
    descricao_material = request.GET.get('descricao_material')
    tipo_entrada = request.GET.get('tipo_entrada')
    data_inicial = datetime.strptime(request.GET.get('data_inicial'), '%Y-%m-%d').date() if request.GET.get('data_inicial') else None
    data_final = datetime.strptime(request.GET.get('data_final'), '%Y-%m-%d').date() if request.GET.get('data_final') else None

    entradas = Entrada.objects.all()
    if uo:
        entradas = entradas.filter(uo=uo)
    if vinculo_fornecedor:
        entradas = entradas.filter(vinculo_fornecedor=vinculo_fornecedor)
    if numero_nota_fiscal:
        entradas = entradas.filter(numero_nota_fiscal__icontains=numero_nota_fiscal)
    if empenho:
        entradas = entradas.filter(
            Q(movimentoalmoxentrada__empenho_consumo__empenho=empenho) | Q(entradapermanente__empenho_permanente__empenho=empenho)
        )
    if processo:
        entradas = entradas.filter(
            Q(entradapermanente__empenho_permanente__empenho__processo=processo)
            | Q(movimentoalmoxentrada__empenho_consumo__empenho__processo=processo)
            | Q(processo=processo)
        )
    if tipo_material:
        entradas = entradas.filter(tipo_material=tipo_material)
        if descricao_material:
            if tipo_material == MaterialTipo.PERMANENTE():
                entradas = entradas.filter(entradapermanente__descricao__unaccent__icontains=descricao_material)
            elif tipo_material == MaterialTipo.CONSUMO():
                entradas = entradas.filter(movimentoalmoxentrada__material__nome__unaccent__icontains=descricao_material)
    if tipo_entrada:
        entradas = entradas.filter(tipo_entrada=tipo_entrada)

    if data_inicial:
        entradas = entradas.filter(data__gte=data_inicial)
    if data_final:
        entradas = entradas.filter(data__lte=data_final)
    entradas = entradas.order_by('-data').distinct()

    total = 0
    itens = []
    for entrada in entradas:
        for i in entrada.get_itens():
            if int(i.get_categoria().codigo) == elemento_despesa_id:
                valor = i.get_valor().replace('.', '')
                total += Decimal(valor.replace(',', '.'))
                itens.append(i)
    return locals()


@group_required(TODOS_GRUPOS_ALMOXARIFADO)
def capa_pagamento_pdf(request, entrada_id):
    """Gera PDF para capa de pagamento."""

    # Bloqueio de acesso à visualização da entrada com base na permissão do usuários
    if not request.user.has_perm('almoxarifado.pode_ver_entrada'):
        raise PermissionDenied

    entrada = get_object_or_404(Entrada, pk=entrada_id)
    resumo_ed = entrada.get_elem_despesa_entrada()
    total = entrada.get_valor_total()
    fields = []

    if entrada.tipo_entrada.nome == 'doacao':
        raise PermissionDenied
    else:
        assinatura = 'Coordenação de Almoxarifado'

        empenho = entrada.get_empenho()

        fields.append(['<b>Interessado:</b>', (entrada.vinculo_fornecedor)])

        fields.append(['<b>Número Nota Fiscal:</b>', f'<p align="left"> {html.escape(entrada.numero_nota_fiscal)} </p>'])

        fields.append(['<b>Natureza:</b>:', entrada.tipo_material.nome.capitalize()])

        fields.append(['<b>Empenho:</b>', empenho])

        fields.append(['<b>Valor:</b>', f'<p align="left"> {entrada.get_valor()} </p>'])

        tabela_info = relatorios.table(fields, w=[60, 130], escape=False)

        protocolo = f'Documentação referente ao processo de compra protocolado sob o número: <b> {empenho.processo} </b>'

    p1 = 'Protocolo'
    p2 = 'Documento'
    p3 = 'Total por elemento de despesa'

    tabela_ed = [['Código', 'Conta Contábil', 'Descrição', 'Valor']]

    for ed in resumo_ed:
        codigo = ed['codigo']
        contacontabil = ed['planocontas']
        categoria = ed['categoria']
        valor = ed['valor']

        linha = [codigo, contacontabil, categoria, valor]

        tabela_ed.append(linha)

    total_ajustado = format_money_almox(total)

    total = ['', '', 'TOTAL', total_ajustado]
    tabela_ed.append(total)

    tabela_ed = relatorios.table(tabela_ed, head=1, zebra=1, w=[15, 30, 120, 25], a=['c', 'c', 'r', 'r'])

    body = [
        *get_topo_com_titulo('Capa de Pagamento'),
        relatorios.para(p1, style='h2', align='left', escape=False),
        relatorios.para(protocolo, align='left', escape=False),
        relatorios.para(p2, style='h2', align='left', escape=False),
        relatorios.space(4),
        tabela_info,
        relatorios.space(4),
        relatorios.para(p3, style='h2', align='left'),
        relatorios.space(4),
        tabela_ed,
    ]

    return PDFResponse(relatorios.PdfReport(body=body, footer_args=rodape_data_e_assinatura(assinatura)).generate(), anexo=False)


@group_required(TODOS_GRUPOS_ALMOXARIFADO)
@rtr()
def balancete_ed_detalhado(request):
    """
    Exibe formulário para geração de relatório de Elemento de Despesa detalhado.
    """
    title = 'Balancete Elemento de Despesa Detalhado'
    FormClass = BalanceteEDDetalhadoFormFactory(request.user)
    if request.method == 'POST':
        form = FormClass(request.POST)
        if form.is_valid():
            return relatorio_balancete_ed_detalhado(form.cleaned_data, request)
    else:
        form = FormClass()
    return locals()


###
# Requisições
###


@group_required('Operador de Almoxarifado, Coordenador de Almoxarifado, Coordenador de Almoxarifado Sistêmico')
@rtr()
def form_requisicao_usuario_pedido(request):
    return {
        'uos': UnidadeOrganizacional.objects.suap().all(),
        'title': 'Requisição de Saída de Material para Consumo',
        'get_uo': get_uo(request.user),
    }


@group_required('Operador de Almoxarifado, Coordenador de Almoxarifado, Coordenador de Almoxarifado Sistêmico')
def requisicao_usuario_pedido(request):
    if not request.POST.get('uo_id'):
        return httprr('/almoxarifado/form_requisicao_usuario_pedido/', 'Campus não Informado.', 'error')

    uo_fornecedora = UnidadeOrganizacional.objects.suap().get(id=int(request.POST['uo_id']))

    if request.user.has_group_cached(OPERADOR_ALMOXARIFADO):
        vinculo_solicitante = Vinculo.objects.get(id=int(request.POST['solicitante_hidden']))
    else:
        vinculo_solicitante = request.user.get_vinculo()

    setor_solicitante = vinculo_solicitante.setor
    observacoes = request.POST.get('obs')
    materiais_id = request.POST.getlist('itens_hidden')
    quantidades = request.POST.getlist('quantidades')
    if observacoes and len(observacoes) > 255:
        return httprr(
            '/almoxarifado/form_requisicao_usuario_pedido/',
            'O campo Observações está muito grande. Por favor resuma para até 255 caracteres.',
            'error',
        )

    requisicao = RequisicaoAlmoxUser(
        uo_fornecedora=uo_fornecedora,
        vinculo_solicitante=vinculo_solicitante,
        setor_solicitante=setor_solicitante,
        data=datetime.now(),
        avaliada=False,
        observacoes=observacoes,
    )

    dict_materiais = {}

    try:
        for i in range(len(materiais_id)):
            chave = materiais_id[i]
            if chave not in list(dict_materiais.keys()):
                dict_materiais[chave] = int(quantidades[i])
            else:
                dict_materiais[chave] += int(quantidades[i])
    except Exception:
        descricao = ''
        material = MaterialConsumo.objects.filter(id=chave).first() if str(chave).isdigit() else None
        if material:
            descricao = str(material)
            descricao = descricao[:50] + '...' if len(descricao) > 50 else descricao
        return httprr('/almoxarifado/form_requisicao_usuario_pedido/', f'A quantidade do material {descricao} deve ser um número inteiro.', 'error')
    try:
        with transaction.atomic():
            requisicao.save()
            for i in list(dict_materiais.items()):
                RequisicaoAlmoxUserMaterial(requisicao=requisicao, material=MaterialConsumo.objects.get(id=i[0]), qtd=int(i[1])).save()
    except Exception:
        return httprr(
            '/almoxarifado/requisicoes_pendentes/', 'Erro ao tentar processar requisição. Por favor verifique os itens e tente novamente.', 'error'
        )
    return httprr('/almoxarifado/requisicoes_pendentes/', 'Requisição efetuada com sucesso.')


@rtr()
@group_required('Operador de Almoxarifado, Coordenador de Almoxarifado, Coordenador de Almoxarifado Sistêmico')
def form_requisicao_uo_pedido(request):
    id_uo_usuario_logado = request.user.get_vinculo().setor.uo.id
    uos = UnidadeOrganizacional.objects.suap().exclude(id=id_uo_usuario_logado)
    return {'uos': uos, 'title': 'Requisição de Transferência de Material de Consumo Intercampi', 'get_uo': get_uo(request.user)}


@group_required('Operador de Almoxarifado, Coordenador de Almoxarifado, Coordenador de Almoxarifado Sistêmico')
def requisicao_uo_pedido(request):
    materiais_id = request.POST.getlist('itens_hidden')
    quantidades = request.POST.getlist('quantidades')
    requisicao = RequisicaoAlmoxUO(
        uo_fornecedora=UnidadeOrganizacional.objects.suap().get(id=int(request.POST['uo_id'])),
        vinculo_solicitante=request.user.get_vinculo(),
        uo_solicitante=request.user.get_vinculo().setor.uo,
        data=datetime.now(),
        avaliada=False,
    )
    requisicao.save()
    for i in range(len(materiais_id)):
        RequisicaoAlmoxUOMaterial(requisicao=requisicao, material=MaterialConsumo.objects.get(id=materiais_id[i]), qtd=int(quantidades[i])).save()
    return httprr('/almoxarifado/requisicoes_pendentes/', 'Requisição efetuada com sucesso.')


@group_required('Operador de Almoxarifado, Coordenador de Almoxarifado, Coordenador de Almoxarifado Sistêmico')
@rtr()
def requisicoes_pendentes(request):
    title = 'Requisições Pendentes'
    requisicoes_user = RequisicaoAlmoxUser.get_pendentes(request.user)
    requisicoes_uo = RequisicaoAlmoxUO.get_pendentes(request.user)

    return locals()


@login_required()
def requisicao_detalhe(request, tipo, objeto_id):
    """
    Retorna o detalhamento da requisição selecionada ou formulário para responder
    a requisição.
    """
    requisicao = RequisicaoAlmox.get(tipo, objeto_id)
    title = f'Requisição #{requisicao.id}'
    pode_remover = requisicao.user_can_delete(request.user)
    pode_responder = requisicao.user_pode_responder(request.user)
    pode_ver = requisicao.user_pode_ver(request.user)
    pode_devolver = requisicao.user_pode_devolver_item(request.user)
    itens_requisicao = requisicao.item_set.all()
    itens_devolvidos = (
        DevolucaoMaterial.objects.filter(requisicao_user=requisicao)
        if requisicao.tipo == 'user'
        else DevolucaoMaterial.objects.filter(requisicao_uo=requisicao)
    )
    url = 'almoxarifado/templates/requisicao_detalhe.html'
    dicionario = {
        'requisicao': requisicao,
        'pode_remover': pode_remover,
        'pode_responder': pode_responder,
        'pode_devolver': pode_devolver,
        'itens_requisicao': itens_requisicao,
        'title': title,
    }
    if pode_responder:
        url = 'almoxarifado/templates/form_requisicao_resposta.html'
    elif not pode_ver or (pode_ver and requisicao.avaliada):
        dicionario['itens_devolvidos'] = itens_devolvidos

    return render(url, dicionario)


@group_required('Coordenador de Almoxarifado, Coordenador de Almoxarifado Sistêmico')
def requisicao_remover(request, tipo, requisicao_id):
    requisicao = RequisicaoAlmox.get(tipo, requisicao_id)
    if requisicao.user_can_delete(request.user):
        requisicao.delete()
        return httprr('/almoxarifado/requisicao_busca/', 'Remoção de Requisição realizada com sucesso.')
    else:
        raise PermissionDenied


@group_required('Operador de Almoxarifado, Coordenador de Almoxarifado, Coordenador de Almoxarifado Sistêmico')
def requisicao_resposta(request, tipo, objeto_id):
    try:
        requisicao = RequisicaoAlmox.get(tipo, objeto_id)
    except Exception:
        raise PermissionDenied
    itens_id = request.POST.getlist('idRequisicoesMaterial')
    try:
        quantidades_aceitas = [int(i) for i in request.POST.getlist('quantidadesAceitas')]
        respostas = dict_from_keys_n_values(itens_id, quantidades_aceitas)
        requisicao.avaliar(respostas, request)
    except Exception as e:
        return httprr('/almoxarifado/requisicoes_pendentes/', str(e), 'error')
    msg = f'Saída de Material Realizada. Detalhes: <a href="/almoxarifado/requisicao_detalhe/{tipo}/{objeto_id}/">HTML</a> | <a href="/almoxarifado/relatorio/nota_fornecimento_pdf/{tipo}/{objeto_id}/">PDF</a>'
    return httprr(
        '/almoxarifado/requisicoes_pendentes/',
        mark_safe(msg),
    )


@permission_required('almoxarifado.pode_ver_todas_requisicoes_usuario, almoxarifado.pode_ver_requisicoes_usuario_do_campus')
@rtr()
def requisicao_busca(request):
    """
    Retorna e processa o formulário para busca de requisições e exibe o resultado.
    """
    title = 'Buscar Requisição'
    usuario = request.user

    uo_usuario = usuario.get_vinculo().setor.uo
    FormClass = RequisicaoBuscaFormFactory(usuario)

    if request.method == 'GET' and len(request.GET):
        form = FormClass(request.GET)
        if form.is_valid():
            # Verificação de tipos de requisições que podem ser buscadas pelo usuário
            cleaned_data = form.cleaned_data.copy()

            tipo = cleaned_data.pop('tipo')
            requisicoes = RequisicaoAlmoxUser.objects.none()

            if tipo == 'usuario' and (
                usuario.has_perm('almoxarifado.pode_ver_requisicoes_usuario_do_campus')
                or usuario.has_perm('almoxarifado.pode_ver_todas_requisicoes_usuario')
            ):
                requisicoes = RequisicaoAlmoxUser.objects.all()
                requisicoes = requisicoes.filter(uo_fornecedora=uo_usuario)
            elif tipo == 'uo' and usuario.has_perm('almoxarifado.pode_ver_requisicoes_uo_do_campus'):
                requisicoes = RequisicaoAlmoxUO.objects.all()
                requisicoes = requisicoes.filter(Q(uo_fornecedora=uo_usuario.id) | Q(uo_solicitante=uo_usuario.id))

            dict_filtros = {}

            recursivo = cleaned_data.pop('recursivo')
            material = cleaned_data.pop('material')

            for campo, valor in list(cleaned_data.items()):
                if valor is None:
                    continue

                if campo == 'campus_fornecedor':
                    dict_filtros['uo_fornecedora'] = valor
                elif campo == 'data_inicial':
                    dict_filtros['data__gt'] = valor
                elif campo == 'data_final':
                    dict_filtros['data__lt'] = somar_dias(valor, 1)
                elif campo == 'solicitante':
                    dict_filtros['vinculo_solicitante'] = valor
                elif campo == 'setor':
                    if recursivo:
                        lista = []
                        if tipo == 'usuario':
                            lista.append(valor.id)
                            lista.extend(list(valor.ids_descendentes))
                            dict_filtros['setor_solicitante__id__in'] = lista
                        else:
                            lista = []
                            for descendente in valor.descendentes:
                                lista.append(descendente.uo and descendente.uo.id or None)
                            dict_filtros['uo_solicitante__id__in'] = lista
                    else:
                        if tipo == 'usuario':
                            requisicoes = requisicoes.filter(setor_solicitante__id=valor.id)
                        else:
                            requisicoes = requisicoes.filter(uo_solicitante__id=valor.uo and valor.uo.id or None)
                else:
                    dict_filtros[campo] = valor

            requisicoes = requisicoes.filter(**dict_filtros)

            if material:
                requisicoes = requisicoes.filter(item_set__material=material, item_set__movimentoalmoxsaida__qtd__gt=0)
    else:
        form = FormClass()

    return locals()


@group_required(TODOS_GRUPOS_ALMOXARIFADO)
@rtr()
def material_historico(request, material_id, uo_id=None):
    title = 'Histórico de Movimentação de Material'
    material = get_object_or_404(MaterialConsumo, pk=material_id)

    if uo_id:
        uos = [UnidadeOrganizacional.objects.suap().get(pk=uo_id)]
    else:
        uos = UnidadeOrganizacional.objects.suap().order_by('setor__sigla')

    historicos = OrderedDict()
    for uo in uos:
        movimentos = historico_movimentacao(material, uo)
        if movimentos:
            historicos[str(uo)] = movimentos
        try:
            materialestoque = MaterialEstoque.objects.get(material=material, uo=uo)
        except Exception:
            materialestoque = MaterialEstoque.objects.create(material=material, uo=uo, valor_medio=0, quantidade=0)
        valor_medio = materialestoque.valor_medio
        estoque = materialestoque.quantidade
    return locals()


@rtr()
@login_required()
def balancete_material(request):
    """
    Exibe formulário a ser preenchido com dados para obter o balancete de material de consumo.

    Exibe relatório do balancete de material de consumo e link para geração do PDF correspondente.
    """
    title = 'Balancete de Material de Consumo'

    # Bloqueio do acesso à funcionalidade com base nas permissões do usuário.
    if not user_has_one_of_perms(request.user, ['almoxarifado.pode_ver_relatorios_todos', 'almoxarifado.pode_ver_relatorios_do_campus']):
        raise PermissionDenied

    FormClass = BalanceteMaterialFormFactory(request.user)

    if request.method == 'POST':
        form = FormClass(request.POST)
        if form.is_valid():
            data_ini = form.cleaned_data['faixa'][0]
            data_fim = form.cleaned_data['faixa'][1]
            uo = form.cleaned_data['uos']
            estoque = form.cleaned_data['estoque']
            return relatorio_balancete_material(data_ini, data_fim, uo, estoque, request)
    else:
        form = FormClass()

    return locals()


@group_required('Coordenador de Almoxarifado, Coordenador de Almoxarifado Sistêmico, Auditor')
@rtr()
def situacao_estoque(request):
    uo = request.user.get_vinculo().setor.uo
    title = f'Situação do Estoque {uo}'
    configuracoes = ConfiguracaoEstoque.objects.all().filter(uo=uo).order_by('material__nome')
    return locals()


@group_required('Coordenador de Almoxarifado, Coordenador de Almoxarifado Sistêmico, Auditor')
@rtr()
def configuracao_estoque(request):
    title = 'Controle de Estoque de Materiais'
    uo = request.user.get_vinculo().setor.uo
    if request.method == 'POST':
        if 'ids' in request.POST:
            form = ConfiguracaoEstoqueForm(None, initial={'uo': uo})
            ids = request.POST.getlist('ids')
            for id in ids:
                ce = ConfiguracaoEstoque.objects.get(id=id)
                ce.delete()
        else:
            form = ConfiguracaoEstoqueForm(request.POST, initial={'uo': uo})

            if form.is_valid():
                if form.cleaned_data.get('categoria'):  # filtro por categoria
                    categoria = form.cleaned_data['categoria']
                    intervalo_aquisicao = form.cleaned_data['intervalo_aquisicao']
                    tempo_aquisicao = form.cleaned_data['tempo_aquisicao']
                    for material in categoria.materialconsumo_set.all():
                        if MovimentoAlmoxEntrada.objects.filter(uo=uo).filter(material=material).exists():
                            if not ConfiguracaoEstoque.objects.filter(uo=uo).filter(material=material).exists():
                                ce = ConfiguracaoEstoque()
                                ce.material = material
                                ce.intervalo_aquisicao = intervalo_aquisicao
                                ce.tempo_aquisicao = tempo_aquisicao
                                ce.uo = uo
                                ce.save()
                else:  # filtro por produto
                    intervalo_aquisicao = form.cleaned_data['intervalo_aquisicao']
                    tempo_aquisicao = form.cleaned_data['tempo_aquisicao']
                    material = form.cleaned_data['material']

                    ce = None
                    try:  # material existente
                        ce = ConfiguracaoEstoque.objects.get(uo=uo, material=material)
                    except ConfiguracaoEstoque.DoesNotExist:  # material novo
                        ce = ConfiguracaoEstoque()

                    ce.material = material
                    ce.intervalo_aquisicao = intervalo_aquisicao
                    ce.tempo_aquisicao = tempo_aquisicao
                    ce.uo = uo
                    ce.save()
    else:
        form = ConfiguracaoEstoqueForm(None, initial={'uo': uo})
    configuracaoes = ConfiguracaoEstoque.objects.all().filter(uo=uo).order_by('material__nome')

    return locals()


@group_required('Coordenador de Almoxarifado, Coordenador de Almoxarifado Sistêmico')
@rtr()
def relatorio_compra(request):
    uo = request.user.get_vinculo().setor.uo
    title = f'Lista de Compras {uo}'
    registros = []
    total = 0
    if 'id' in request.GET:
        id_list = request.GET.getlist('id')
        for id in id_list:
            sufixo = str(id)
            material = MaterialConsumo.objects.all().get(pk=id)
            try:
                valor = (request.GET['valor' + sufixo]).replace(',', '.')
                valor = float(valor)
                qtd = float(request.GET['qtd' + sufixo])
            except ValueError, KeyError:
                return httprr('..', 'Valores escolhidos inválidos.', 'error')
            parcial = valor * qtd
            total += parcial
            title = f'Situação do Estoque {uo}'
            registro = {'material': material, 'valor': format_money_almox(f'{valor}'), 'qtd': qtd, 'parcial': format_money_almox(f'{parcial}')}
            registros.append(registro)
        total = format_money_almox(f'{total}')
    if 'pdf' in request.GET and request.GET['pdf'] == '1':
        return relatorio_compra_pdf(request, registros, total)
    else:
        return locals()


def relatorio_compra_pdf(request, registros, total):
    uo = request.user.get_vinculo().setor.uo
    topo = relatorios.get_topo_pdf('Relatório de Compras')
    servidor = request.user.get_relacionamento()
    info = [['UO', uo], ['Servidor', servidor], ['Data', datetime.today().strftime('%d/%m/%Y')], ['Total', f'R$ {total}']]
    dados = [['Material', 'Valor (R$)', 'Quantidade', 'Parcial (R$)']]
    for registro in registros:
        dados.append([registro['material'], registro['valor'], registro['qtd'], registro['parcial']])
    tabela_info = relatorios.table(info, grid=0, w=[30, 100])
    tabela_dados = relatorios.table(dados, head=1, zebra=1, w=[90, 20, 20, 20], count=1)
    body = [*topo, tabela_info, relatorios.space(8), tabela_dados]
    return PDFResponse(relatorios.PdfReport(body=body).generate())


@group_required(TODOS_GRUPOS_ALMOXARIFADO)
@rtr()
def materiais_transferidos(request):
    """
    Retorna e processa o formulário para busca de itens solicitados por pessoa em determinado periodo.
    """
    title = 'Materiais Transferidos'
    usuario = request.user
    FormClass = NotasFornecimentoFormFactory(usuario)
    total = ''
    if request.method == 'GET' and len(request.GET):
        form = FormClass(request.GET)
        if form.is_valid():
            requisicoes = RequisicaoAlmoxUO.objects.all()
            data_inicio = form.cleaned_data.get('data_inicial')
            data_fim = form.cleaned_data.get('data_final')
            vinculo_solicitante = form.cleaned_data.get('vinculo_solicitante')
            data_fim_mais_um_dia = somar_dias(data_fim, 1)
            requisicoes = requisicoes.filter(vinculo_solicitante=vinculo_solicitante, data__gt=data_inicio, data__lt=data_fim_mais_um_dia)
            total_requisicoes = 0
            contador_itens = 0
            for requisicao in requisicoes:
                for item in requisicao.get_itens_aceitos():
                    total_requisicoes += item.valor()
                    contador_itens += 1
    else:
        form = FormClass()

    return locals()


@rtr()
@group_required(TODOS_GRUPOS_ALMOXARIFADO)
def balancete_ed(request):
    title = 'Balancete de Elemento de Despesa'
    formClass = GetBalanceteEdForm(request)
    if request.method == 'POST':
        form = formClass(request.POST)
        if form.is_valid():
            return relatorio_balancete_ed(form.cleaned_data, request)
    else:
        form = formClass()

    return locals()


@rtr()
@group_required(TODOS_GRUPOS_ALMOXARIFADO)
def saldo_ed(request):
    title = 'Relatório Saldo Atual por Elemento de Despesa'
    lista_campi = []
    form = RelatorioSaldoAtualEDForm(request.POST or None, request=request)
    uos = UnidadeOrganizacional.objects.uo().all()
    total_geral = 0

    def format(m):
        if isinstance(m, MovimentoAlmoxSaida):
            m.valor = -m.valor
            m.qtd = -m.qtd
        m.total = abs(m.valor) * m.qtd
        return m

    if form.is_valid():
        uo = form.cleaned_data['campus']
        lista_ed = []
        for c in CategoriaMaterialConsumo.objects.exclude(codigo='63').order_by('codigo'):
            total = 0
            materiais = MaterialConsumo.objects.com_estoque_por_uo(uo=uo)
            materiais = materiais.filter(categoria=c)
            for material in materiais:
                e = [(m.data, m.id, format(m)) for m in material.movimentoalmoxentrada_set.filter(uo=uo)]
                s = [(m.data, m.id, format(m)) for m in material.movimentoalmoxsaida_set.filter(uo=uo)]
                movimentos = e + s
                movimentos.sort()
                movimentos = [i[2] for i in movimentos]
                total += sum(i.total for i in movimentos)
            infos = {}
            infos['categoria'] = c
            infos['saldo'] = total
            total_geral += total
            lista_ed.append(infos)
    return locals()


def montar_tabela_elemento_despesa(user, metodo_entrada, metodo_saida, uo_id, data_ini, data_fim):
    datas = [data_ini, data_fim]
    data_anterior = somar_dias(data_ini, -1)

    cabecalhos_tabela = [
        [
            {'valor': 'Material', 'alinhamento': 'center', 'largura': 90, 'colspan': 2},
            {'valor': 'Estoque em', 'alinhamento': 'center', 'largura': 90, 'colspan': 1},
            {'valor': 'Entradas', 'alinhamento': 'center', 'largura': 60, 'colspan': 5},
            {'valor': 'Saídas', 'alinhamento': 'center', 'largura': 60, 'colspan': 3},
            {'valor': 'Estoque em', 'alinhamento': 'center', 'largura': 20, 'colspan': 1},
        ],
        [
            {'valor': 'Cod.', 'alinhamento': 'center', 'largura': 10, 'colspan': 1},
            {'valor': 'Nome', 'alinhamento': 'left', 'largura': 80, 'colspan': 1},
            {'valor': 'Estoque {}'.format(data_anterior.strftime('%d/%m/%Y')), 'alinhamento': 'right', 'largura': 20, 'colspan': 1},
            {'valor': 'Compra', 'alinhamento': 'right', 'largura': 20, 'colspan': 1},
            {'valor': 'Transf.', 'alinhamento': 'right', 'largura': 20, 'colspan': 1},
            {'valor': 'Doação', 'alinhamento': 'right', 'largura': 20, 'colspan': 1},
            {'valor': 'Devolução', 'alinhamento': 'right', 'largura': 20, 'colspan': 1},
            {'valor': 'Total', 'alinhamento': 'right', 'largura': 20, 'colspan': 1},
            {'valor': 'Consumo', 'alinhamento': 'right', 'largura': 20, 'colspan': 1},
            {'valor': 'Transf.', 'alinhamento': 'right', 'largura': 20, 'colspan': 1},
            {'valor': 'Total', 'alinhamento': 'right', 'largura': 20, 'colspan': 1},
            {'valor': 'Estoque {}'.format(datas[1].strftime('%d/%m/%Y')), 'alinhamento': 'right', 'largura': 20, 'colspan': 1},
        ],
    ]

    corpo_tabela = []
    # XXX: A categoria 63 é excluída do relatório de forma hard-coded porque a categoria
    #      é uma gambiarra para empenhos do tipo serviço. Os servços não devem aparecer
    #      no balancete ED. O balancete material considera a categoria 63.

    for c in CategoriaMaterialConsumo.objects.exclude(codigo='63').order_by('codigo'):
        estoque_anterior = c.estoque(data=data_anterior, uo_id=uo_id)
        estoque_fim_periodo = c.estoque(data=datas[1], uo_id=uo_id)

        # entrada
        c.__getattribute__(metodo_entrada)(datas, uo_id)
        entrada_transferencia = c.__getattribute__('entrada_transferencia')(datas, uo_id)
        entrada_compra = c.__getattribute__('entrada_normal')(datas, uo_id)
        entrada_doacao = c.__getattribute__('entrada_doacao')(datas, uo_id)
        devolucao = c.__getattribute__('devolucao')(datas, uo_id)

        # saída
        saida_consumo = c.__getattribute__('saida_normal')(datas, uo_id)
        saida_transferencia = c.__getattribute__('saida_transferencia')(datas, uo_id)
        c.__getattribute__(metodo_saida)(datas, uo_id)

        corpo_tabela.append(
            [
                c.codigo,
                c.nome,
                mask_money(estoque_anterior.get('valor')),  # estoque (1 período)
                mask_money(entrada_compra.get('valor')),  # Ent. Compra
                mask_money(entrada_transferencia.get('valor')),  # Ent. Transf
                mask_money(entrada_doacao.get('valor')),  # Ent. Doação
                mask_money(devolucao.get('valor')),  # Ent. Doação
                mask_money(
                    entrada_compra.get('valor') + entrada_transferencia.get('valor') + entrada_doacao.get('valor') + devolucao.get('valor')
                ),  # Ent. Total
                mask_money(saida_consumo.get('valor')),  # Saída Consumo
                mask_money(saida_transferencia.get('valor')),  # Saída Transf
                mask_money(saida_consumo.get('valor') + saida_transferencia.get('valor')),  # Saida Total
                mask_money(estoque_fim_periodo.get('valor')),  # estoque (2 período)
            ]
        )
    linha_total = [
        '-',
        'Todos os Elementos de Despesa',
        mask_money(somar_indice(corpo_tabela, 2)),
        mask_money(somar_indice(corpo_tabela, 3)),
        mask_money(somar_indice(corpo_tabela, 4)),
        mask_money(somar_indice(corpo_tabela, 5)),
        mask_money(somar_indice(corpo_tabela, 6)),
        mask_money(somar_indice(corpo_tabela, 7)),
        mask_money(somar_indice(corpo_tabela, 8)),
        mask_money(somar_indice(corpo_tabela, 9)),
        mask_money(somar_indice(corpo_tabela, 10)),
        mask_money(somar_indice(corpo_tabela, 11)),
    ]
    corpo_tabela.append(linha_total)

    tabela = {'cabecalhos': cabecalhos_tabela, 'dados': corpo_tabela}
    uo = uo_id and UnidadeOrganizacional.objects.suap().get(id=uo_id) or 'Todas as Unidades Organizacionais'

    periodo = f'Unidade Organizacional: {uo}<br/>Período: {extrair_periodo(data_ini, data_fim)}'

    setor_pessoa_logada = user.get_vinculo().setor
    uo_pessoa_logada = setor_pessoa_logada.uo

    dados = {
        'cabecalho': {
            'orgao': Configuracao.get_valor_por_chave('comum', 'instituicao'),
            'uo': uo_pessoa_logada.__str__(),
            'setor': setor_pessoa_logada.__str__(),
        },
        'data': data_extenso(),
        'titulo': 'Balancete Elemento de Despesa de Material de Consumo',
        'elementos': [periodo, tabela],
        'cidade': uo_pessoa_logada.municipio,
    }

    return {'titulo': dados['titulo'], 'periodo': periodo, 'tabela': tabela}


def obtem_transferencias(categoria_material_consumo, datas, uo_id):
    transferencias = MovimentoAlmoxEntrada.objects.filter(
        material__in=categoria_material_consumo.materialconsumo_set.all(), requisicao_uo_material__isnull=False
    )
    if datas:
        if len(datas) == 1:
            transferencias = transferencias.filter(data__lt=somar_dias(datas[0], 1))
        else:
            data_inicial = datas[0]
            data_inicial = datetime(data_inicial.year, data_inicial.month, data_inicial.day, 0, 0, 0)

            data_final = datas[1]
            data_final = datetime(data_final.year, data_final.month, data_final.day, 23, 59, 59)

            transferencias = transferencias.filter(data__range=[data_inicial, data_final])
    if uo_id:
        transferencias = transferencias.filter(Q(uo__id=uo_id) | Q(movimento_saida__uo__id=uo_id))

    return transferencias


def processar_transferenicas(corpo_tabela, categoria_material_consumo, entradas):
    total = 0
    for entrada in entradas:
        valor = float(entrada.qtd * entrada.valor)
        corpo_tabela.append(
            [
                f'<a href="{entrada.requisicao_uo_material.requisicao.get_absolute_url()}">Ver Requisição</a>',
                f'{categoria_material_consumo}',
                entrada.requisicao_uo_material.requisicao.uo_fornecedora,
                entrada.requisicao_uo_material.requisicao.uo_solicitante,
                mask_money(f'{valor}'),
            ]
        )
        total += valor
    return total


def montar_tabela_agrupar_elemento_despesa(user, metodo_entrada, metodo_saida, uo_id, data_ini, data_fim):
    # Período: 01/06/2015 até 01/08/2015
    datas = [data_ini, data_fim]
    somar_dias(data_ini, -1)
    cabecalhos_tabela = [
        [
            {'valor': 'Requisição', 'alinhamento': 'center', 'largura': 90, 'colspan': 1},
            {'valor': 'Elemento de Despesa', 'alinhamento': 'center', 'largura': 90, 'colspan': 1},
            {'valor': 'Campus Fornecedor', 'alinhamento': 'center', 'largura': 90, 'colspan': 1},
            {'valor': 'Campus Solicitante', 'alinhamento': 'center', 'largura': 60, 'colspan': 1},
            {'valor': 'Valor', 'alinhamento': 'center', 'largura': 60, 'colspan': 1},
        ]
    ]
    corpo_tabela = []
    total_geral = 0
    for categoria_material_consumo in CategoriaMaterialConsumo.objects.exclude(codigo='63').order_by('codigo'):
        # entrada
        transferencias = obtem_transferencias(categoria_material_consumo, datas, uo_id)
        total = processar_transferenicas(corpo_tabela, categoria_material_consumo, transferencias)
        if total > 0:
            total_geral += total
            corpo_tabela.append(['-', f'Total de transferências com {categoria_material_consumo}', '-', '-', mask_money(total)])
    # OK - Monte a tabela para apresentacao.
    linha_total = ['-', 'Valor total movimentado', '-', '-', mask_money(total_geral)]
    corpo_tabela.append(linha_total)
    tabela = {'cabecalhos': cabecalhos_tabela, 'dados': corpo_tabela}
    uo = uo_id and UnidadeOrganizacional.objects.suap().get(id=uo_id) or 'Todas as Unidades Organizacionais'
    periodo = f'Unidade Organizacional: {uo}<br/>Período: {extrair_periodo(data_ini, data_fim)}'

    return {'titulo': 'Agrupar por elemento de despesa', 'periodo': periodo, 'tabela': tabela}


def relatorio_balancete_ed(cleaned_data, request):
    user = request.user
    data_ini = cleaned_data['faixa'][0]
    data_fim = cleaned_data['faixa'][1]
    uo = cleaned_data['uos']
    if user.has_group_cached('Coordenador de Almoxarifado Sistêmico,Auditor'):
        # Gerente sistêmico e Auditor pode escolher a Unidade Organizacional.
        uo_id = (uo and uo.id) or None
    else:
        uo_id = uo.id

    if uo_id:
        metodo_entrada = 'entrada'
        metodo_saida = 'saida'
    else:
        # Todas as UO's devem desconsiderar transferência entre elas.
        metodo_entrada = 'entrada_normal'
        metodo_saida = 'saida_normal'

    tabela_balancete_ed = montar_tabela_elemento_despesa(request.user, metodo_entrada, metodo_saida, uo_id, data_ini, data_fim)
    tabela_agrupar_elemento_depesa = montar_tabela_agrupar_elemento_despesa(request.user, metodo_entrada, metodo_saida, uo_id, data_ini, data_fim)
    #
    title = 'Balancete Elemento de Despesa de Material de Consumo'
    tabela_balancete_ed['tabela'] = relatorios.montar_tabela_html(tabela_balancete_ed['tabela'], destacar_ultima=True)
    tabela_agrupar_elemento_depesa['tabela'] = relatorios.montar_tabela_html(tabela_agrupar_elemento_depesa['tabela'], destacar_ultima=True)
    return render(
        'relatorio/relatorio_balancete_ed.html',
        {'title': title, 'tabela_balancete_ed': tabela_balancete_ed, 'tabela_agrupar_elemento_depesa': tabela_agrupar_elemento_depesa},
    )


@rtr()
@login_required
def gerar_etiquetas(request):
    title = 'Gerar Etiquetas'
    form = TipoEtiquetaForm(request.POST or None)
    if form.is_valid():
        if request.GET.get('tab') == 'tab_estoque_atual':
            materiais = MaterialConsumo.objects.com_estoque_por_uo(get_uo(request.user))
        elif request.GET.get('tab') == 'tab_teve_estoque_em_meu_campus':
            materiais = MaterialConsumo.objects.teve_estoque_por_uo(get_uo(request.user))
        else:
            materiais = MaterialConsumo.objects.all()
        if 'categoria__id__exact' in list(request.GET.keys()):
            materiais = materiais.filter(categoria__id__exact=request.GET.get('categoria__id__exact'))
        if 'q' in list(request.GET.keys()):
            materiais = materiais.filter(search__icontains=to_ascii(request.GET.get('q')))
        rows = []
        for obj in materiais:
            row = [obj.codigo, obj.nome]
            rows.append(row)
        labels = factory('Pimaco', form.data['tipoetiqueta'])
        f = io.BytesIO()
        labels.generate(rows, f)
        f.seek(0)
        return PDFResponse(f.read(), nome='Etiquetas.pdf')
    return locals()


@rtr()
@login_required
def devolver_item(request, tipo, uo, requisicao):
    title = 'Devolver Item'
    try:
        requisicao = RequisicaoAlmox.get(tipo, requisicao)
    except Exception:
        raise PermissionDenied

    FormClass = DevolucaoItemFormFactory(requisicao)
    form = FormClass(request.POST or None, uo=uo)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            return httprr('..', 'Itens devolvidos com sucesso.')
    return locals()


@rtr()
@login_required()
def atualizar_valor_medio(request, uo_sigla, material):
    uo = UnidadeOrganizacional.objects.suap().get(sigla=uo_sigla)
    calcula_valor_medio_atual(uo, material)

    return httprr(request.META.get('HTTP_REFERER', '..'), 'Atualização realizada.')


@rtr()
@login_required()
def atualizar_movimentacoes(request, uo_sigla, material):
    uo = UnidadeOrganizacional.objects.suap().get(sigla=uo_sigla)
    ajusta_entradas_de_transferencias(uo, material)

    return httprr(request.META.get('HTTP_REFERER', '..'), 'Atualização realizada.')


@rtr()
@login_required()
@group_required('Coordenador de Almoxarifado, Coordenador de Almoxarifado Sistêmico')
def cancelar_requisicaosaida(request, tipo, uo, requisicao):
    title = 'Cancelar requisição de saída'
    try:
        requisicao = RequisicaoAlmox.get(tipo, requisicao)
    except Exception:
        raise PermissionDenied

    if not requisicao.pode_ser_cancelada():
        raise PermissionDenied

    form = CancelarRequisicaoSaidaUserForm(request.POST or None, requisicao=requisicao)
    if form.is_valid():
        form.save()
        return httprr('..', 'Requisição cancelada com sucesso.')

    return locals()


@rtr()
@permission_required('almoxarifado.pode_importar_estoque_csv')
def importar_estoque_csv(request):
    def texto(valor) -> str:
        if valor is None:
            return ''
        if isinstance(valor, list | tuple):
            return ' '.join(str(x) for x in valor)
        return str(valor)

    def so_digitos(valor) -> str:
        return ''.join(ch for ch in texto(valor) if ch.isdigit())

    def decimal_ptbr(valor, campo: str, linha: int) -> Decimal:
        try:
            txt = texto(valor).strip().replace(' ', '').replace('.', '').replace(',', '.')
            return Decimal(txt)
        except InvalidOperation, ValueError:
            raise ValidationError([f'Linha {linha}: valor inválido em {campo} ({valor})'])

    def validar_cnpj(cnpj: str) -> bool:
        cnpj = so_digitos(cnpj)
        if len(cnpj) != 14:
            return False
        if cnpj == cnpj[0] * 14:
            return False

        def calcular_dv(base: str, pesos: list[int]) -> str:
            soma = sum(int(d) * p for d, p in zip(base, pesos, strict=False))
            resto = soma % 11
            return '0' if resto < 2 else str(11 - resto)

        pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        dv1 = calcular_dv(cnpj[:12], pesos1)
        dv2 = calcular_dv(cnpj[:12] + dv1, pesos2)
        return cnpj[-2:] == (dv1 + dv2)

    def chamar_primeiro_existente(obj, nomes_metodos, *args):
        for nome in nomes_metodos:
            if hasattr(obj, nome):
                fn = getattr(obj, nome)
                try:
                    return fn(*args)
                except TypeError:
                    return fn()
        return None

    RE_EMPENHO = re.compile(r'^(?P<prefixo>.+?NE)(?P<seq>\d+)$', re.IGNORECASE)

    def validar_formato_empenho(numero: str):
        numero = texto(numero).strip().upper()
        m = RE_EMPENHO.match(numero)
        if not m:
            raise ValidationError([f'Número de empenho inválido: {numero}. Use formato tipo 2025NE800125.'])
        return m.group('prefixo').upper(), m.group('seq')

    def proximo_numero_empenho(numero_atual: str) -> str:
        prefixo, seq = validar_formato_empenho(numero_atual)
        largura = len(seq)
        return f'{prefixo}{str(int(seq) + 1).zfill(largura)}'

    def criar_empenho(uo, fornecedor, numero_empenho: str, processo):
        return Empenho.objects.create(
            numero=numero_empenho,
            uo=uo,
            vinculo_fornecedor=fornecedor,
            tipo_material=MaterialTipo.CONSUMO(),
            processo=processo,
        )

    def criar_entrada(uo, fornecedor, processo):
        return Entrada.objects.create(
            uo=uo,
            vinculo_fornecedor=fornecedor,
            tipo_entrada=EntradaTipo.COMPRA(),
            tipo_material=MaterialTipo.CONSUMO(),
            processo=processo,
            data=date.today(),
        )

    def obter_uo(sigla):
        sigla = texto(sigla).strip().upper()
        uo = UnidadeOrganizacional.objects.suap().filter(sigla__iexact=sigla).first()
        if not uo:
            raise ValidationError([f'UO não encontrada: {sigla}'])
        return uo

    def obter_categoria(dados_linha):
        codigo = texto(dados_linha.get('categoria_codigo')).strip()
        nome = ' '.join(texto(dados_linha.get('categoria_descricao')).split()).strip()
        linha = dados_linha.get('_linha')

        if not codigo:
            raise ValidationError([f'Linha {linha}: categoria_codigo é obrigatório.'])
        if not nome:
            raise ValidationError([f'Linha {linha}: categoria_descricao é obrigatório.'])

        cat = CategoriaMaterialConsumo.objects.filter(codigo=codigo).first()
        if cat:
            if cat.nome != nome:
                conflito = CategoriaMaterialConsumo.objects.filter(nome__iexact=nome).exclude(id=cat.id).first()
                if conflito:
                    conflito.nome = f'{conflito.nome} (antigo {conflito.codigo})'
                    conflito.save(update_fields=['nome'])
                cat.nome = nome
                cat.save(update_fields=['nome'])
            return cat

        cat_por_nome = CategoriaMaterialConsumo.objects.filter(nome__iexact=nome).first()
        if cat_por_nome:
            conflito_codigo = CategoriaMaterialConsumo.objects.filter(codigo=codigo).exclude(id=cat_por_nome.id).first()
            if conflito_codigo:
                conflito_nome = CategoriaMaterialConsumo.objects.filter(nome__iexact=nome).exclude(id=conflito_codigo.id).first()
                if conflito_nome:
                    conflito_nome.nome = f'{conflito_nome.nome} (antigo {conflito_nome.codigo})'
                    conflito_nome.save(update_fields=['nome'])
                conflito_codigo.nome = nome
                conflito_codigo.save(update_fields=['nome'])
                return conflito_codigo

            cat_por_nome.codigo = codigo
            cat_por_nome.save(update_fields=['codigo'])
            return cat_por_nome

        return CategoriaMaterialConsumo.objects.create(codigo=codigo, nome=nome)

    def obter_unidade_medida(dados_linha):
        sigla = texto(dados_linha.get('unidade_medida_sigla')).strip().upper()
        linha = dados_linha.get('_linha')
        if not sigla:
            raise ValidationError([f'Linha {linha}: unidade_medida_sigla é obrigatória.'])
        unidade, _ = UnidadeMedida.objects.get_or_create(nome=sigla)
        return unidade

    def obter_material(dados_linha):
        linha = int(dados_linha.get('_linha') or 0)
        nome = texto(dados_linha.get('nome')).strip()
        if not nome:
            raise ValidationError([f'Linha {linha}: nome do material é obrigatório.'])

        categoria = obter_categoria(dados_linha)
        unidade = obter_unidade_medida(dados_linha)
        observacao_csv = texto(dados_linha.get('observacao')).strip()

        material = MaterialConsumo.objects.filter(nome__iexact=nome).first()
        if material:
            alterar = False
            campos_update = []

            if material.categoria_id != categoria.id:
                material.categoria = categoria
                alterar = True
                campos_update.append('categoria')

            if hasattr(material, 'unidade_id') and material.unidade_id != unidade.id:
                material.unidade = unidade
                alterar = True
                campos_update.append('unidade')

            # Regra: só sobrescreve se vier preenchida
            if hasattr(material, 'observacao') and observacao_csv:
                atual = texto(getattr(material, 'observacao', '')).strip()
                if atual != observacao_csv:
                    material.observacao = observacao_csv
                    alterar = True
                    campos_update.append('observacao')

            if alterar:
                material.save(update_fields=campos_update)

            return material

        codigo_raw = texto(dados_linha.get('codigo')).strip()
        digitos = ''.join(ch for ch in codigo_raw if ch.isdigit())
        if digitos:
            codigo_6 = digitos[-6:].zfill(6)
        else:
            codigo_6 = codigo_raw[:6] if codigo_raw else ''

        kwargs = {
            'codigo': codigo_6,
            'nome': nome,
            'categoria': categoria,
            'unidade': unidade,
        }
        if hasattr(MaterialConsumo, 'observacao'):
            kwargs['observacao'] = observacao_csv

        return MaterialConsumo.objects.create(**kwargs)

    def pessoa_de_pj(pj: PessoaJuridica):
        for attr in ('pessoa', 'pessoa_ptr'):
            if hasattr(pj, attr):
                return getattr(pj, attr)
        return pj

    def criar_ou_atualizar_pj(cnpj: str, nome_social: str) -> PessoaJuridica:
        pj = PessoaJuridica.objects.filter(cnpj=cnpj).first()
        if pj:
            pessoa = pessoa_de_pj(pj)
            if pessoa and getattr(pessoa, 'nome', None) != nome_social:
                pessoa.nome = nome_social
                pessoa.save(update_fields=['nome'])
            if hasattr(pj, 'nome_social') and pj.nome_social != nome_social:
                pj.nome_social = nome_social
                pj.save(update_fields=['nome_social'])
            return pj

        pj = PessoaJuridica.objects.create(cnpj=cnpj, nome_social=nome_social)
        pessoa = pessoa_de_pj(pj)
        if hasattr(pessoa, 'nome') and pessoa.nome != nome_social:
            pessoa.nome = nome_social
            pessoa.save(update_fields=['nome'])
        return pj

    def obter_fornecedor(df: pd.DataFrame):
        primeiro = df.iloc[0].to_dict()
        cnpj = so_digitos(primeiro.get('cnpj'))
        nome_social = texto(primeiro.get('nome_social')).strip()

        if not cnpj or not nome_social:
            raise ValidationError(['Fornecedor PJ inválido (cnpj / nome_social).'])
        if not validar_cnpj(cnpj):
            raise ValidationError([f'O CNPJ {cnpj} associado a {nome_social} não é válido.'])

        pj = criar_ou_atualizar_pj(cnpj=cnpj, nome_social=nome_social)
        pessoa = pessoa_de_pj(pj)

        ct = ContentType.objects.get_for_model(pj, for_concrete_model=False)
        vinculo, _ = Vinculo.objects.get_or_create(
            tipo_relacionamento=ct,
            id_relacionamento=pj.id,
            defaults={'pessoa': pessoa},
        )
        return vinculo

    def ler_csv(upload):
        raw = upload.read()
        texto_csv = None
        for enc in ('utf-8-sig', 'latin-1'):
            try:
                texto_csv = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if texto_csv is None:
            raise ValidationError(['Não foi possível decodificar o CSV (utf-8-sig/latin-1).'])

        amostra = texto_csv[:4096]
        try:
            dialeto = csv.Sniffer().sniff(amostra, delimiters=';,')
            sep = dialeto.delimiter
        except Exception:
            sep = ','

        df = pd.read_csv(io.StringIO(texto_csv), sep=sep, dtype=str).fillna('')
        df.columns = [c.replace('\ufeff', '').strip() for c in df.columns]
        return df

    def obter_tipo_movimento_entrada():
        tipo = MovimentoAlmoxEntradaTipo.objects.filter(nome__iexact='ENTRADA').first()
        if tipo:
            return tipo
        tipo = MovimentoAlmoxEntradaTipo.objects.order_by('id').first()
        if not tipo:
            raise ValidationError(['Não existe MovimentoAlmoxEntradaTipo cadastrado para vincular no movimento.'])
        return tipo

    def garantir_movimento_entrada(entrada_obj, item_empenho, usuario, valor_unit=None):
        if entrada_obj.movimentoalmoxentrada_set.exists():
            return

        campos_mov = {f.name for f in MovimentoAlmoxEntrada._meta.get_fields()}

        material = getattr(item_empenho, 'material', None)
        if not material:
            raise ValidationError(['MovimentoAlmoxEntrada: item do empenho sem material.'])

        qtd = None
        for attr in ('qtd_adquirida', 'qtd_empenhada', 'qtd'):
            if hasattr(item_empenho, attr):
                qtd = getattr(item_empenho, attr)
                break
        if qtd is None:
            qtd = Decimal('0')

        if valor_unit is None:
            valor_unit = getattr(item_empenho, 'valor', None)

        valor_total = None
        if valor_unit is not None:
            try:
                valor_total = Decimal(valor_unit) * Decimal(qtd)
            except Exception:
                valor_total = None

        estoque, _ = MaterialEstoque.objects.get_or_create(
            material=material,
            uo=entrada_obj.uo,
            defaults={
                'quantidade': Decimal('0'),
                'valor_medio': Decimal(valor_unit) if valor_unit is not None else Decimal('0'),
            },
        )

        kwargs = {
            'entrada': entrada_obj,
        }

        if 'tipo' in campos_mov:
            kwargs['tipo'] = obter_tipo_movimento_entrada()

        if 'qtd' in campos_mov:
            kwargs['qtd'] = qtd

        if 'material' in campos_mov:
            kwargs['material'] = material

        if 'estoque' in campos_mov:
            try:
                field = MovimentoAlmoxEntrada._meta.get_field('estoque')
                internal_type = field.get_internal_type()
            except Exception:
                internal_type = None

            if internal_type in ('ForeignKey', 'OneToOneField'):
                kwargs['estoque_id'] = estoque.id
            else:
                kwargs['estoque'] = estoque.id

        if 'empenho_consumo' in campos_mov:
            kwargs['empenho_consumo'] = item_empenho

        if 'valor_total' in campos_mov and valor_total is not None:
            kwargs['valor_total'] = valor_total

        if 'valor_unitario' in campos_mov and valor_unit is not None:
            kwargs['valor_unitario'] = valor_unit

        if 'valor' in campos_mov and valor_unit is not None:
            kwargs['valor'] = valor_unit

        if 'uo' in campos_mov:
            kwargs['uo'] = entrada_obj.uo

        if 'data' in campos_mov:
            kwargs['data'] = entrada_obj.data

        if 'cadastrado_por' in campos_mov:
            kwargs['cadastrado_por'] = usuario

        if 'usuario' in campos_mov:
            kwargs['usuario'] = usuario

        MovimentoAlmoxEntrada.objects.create(**kwargs)

    title = 'Importar Estoque por CSV'
    form = ImportacaoEstoqueCSVForm(request.POST or None, request.FILES or None)

    if request.method == 'POST' and form.is_valid():
        try:
            df = ler_csv(form.cleaned_data['arquivo'])

            colunas_obrigatorias = {
                'codigo',
                'nome',
                'categoria_codigo',
                'categoria_descricao',
                'uo_sigla',
                'estoque',
                'valor_medio',
                'cnpj',
                'nome_social',
                'unidade_medida_sigla',
                'unidade_medida_descricao',
                'observacao',
            }
            faltando = sorted(colunas_obrigatorias - set(df.columns))
            if faltando:
                raise ValidationError([f'Colunas obrigatórias ausentes: {", ".join(faltando)}'])

            df['_linha'] = df.index + 2

            numero_empenho_inicial = texto(form.cleaned_data['numero_empenho_inicial']).strip().upper()
            validar_formato_empenho(numero_empenho_inicial)

            fornecedor = obter_fornecedor(df)
            usuario = tl.get_user()

            entradas = []

            with transaction.atomic():
                df['uo_sigla'] = df['uo_sigla'].astype(str).str.strip().str.upper()
                if (df['uo_sigla'] == '').any():
                    linha = int(df.loc[df['uo_sigla'] == '', '_linha'].iloc[0])
                    raise ValidationError([f'Linha {linha}: uo_sigla é obrigatório.'])

                for sigla, subdf in df.groupby('uo_sigla', sort=False):
                    uo = obter_uo(sigla)
                    processo = form.cleaned_data['processo']

                    numero_empenho_corrente = numero_empenho_inicial
                    empenho_corrente = criar_empenho(uo, fornecedor, numero_empenho_corrente, processo)
                    entrada_corrente = criar_entrada(uo, fornecedor, processo)
                    itens_no_empenho = 0

                    for _, row in subdf.iterrows():
                        linha = int(row['_linha'])

                        quantidade = decimal_ptbr(row['estoque'], 'estoque', linha)
                        if quantidade <= 0:
                            continue

                        dados_linha = row.to_dict()
                        material = obter_material(dados_linha)
                        valor_unit = decimal_ptbr(row['valor_medio'], 'valor_medio', linha)

                        if itens_no_empenho >= 200:
                            chamar_primeiro_existente(
                                entrada_corrente,
                                ['confirmar', 'concluir', 'efetivar', 'processar', 'finalizar'],
                                usuario,
                            )
                            entradas.append(entrada_corrente)

                            numero_empenho_corrente = proximo_numero_empenho(numero_empenho_corrente)
                            empenho_corrente = criar_empenho(uo, fornecedor, numero_empenho_corrente, processo)
                            entrada_corrente = criar_entrada(uo, fornecedor, processo)
                            itens_no_empenho = 0

                        item_empenho = EmpenhoConsumo.objects.create(
                            empenho=empenho_corrente,
                            material=material,
                            qtd_empenhada=quantidade,
                            qtd_adquirida=quantidade,
                            valor=valor_unit,
                        )
                        itens_no_empenho += 1

                        defaults = {'quantidade': Decimal('0'), 'valor_medio': valor_unit}
                        estoque, created = MaterialEstoque.objects.get_or_create(
                            material=material,
                            uo=entrada_corrente.uo,
                            defaults=defaults,
                        )
                        if (not created) and (estoque.valor_medio is None):
                            estoque.valor_medio = valor_unit
                            estoque.save(update_fields=['valor_medio'])

                        entrada_corrente.efetuar_entrada_material_consumo(material, quantidade, valor_unit, empenho_consumo=item_empenho)

                    chamar_primeiro_existente(
                        entrada_corrente,
                        ['confirmar', 'concluir', 'efetivar', 'processar', 'finalizar'],
                        usuario,
                    )
                    entradas.append(entrada_corrente)

            messages.success(
                request,
                f'Importação concluída. Entradas criadas: {", ".join(str(e.id) for e in entradas)}',
            )
            return redirect(f'/almoxarifado/entrada/{entradas[-1].id}/')

        except ValidationError as e:
            for msg in e.messages:
                messages.error(request, msg)
        except Exception as e:
            import traceback

            messages.error(request, f'Erro ao importar: {e}')
            messages.error(request, traceback.format_exc())

        return redirect(request.path)

    return {
        'title': title,
        'form': form,
    }
