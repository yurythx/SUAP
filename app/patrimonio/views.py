import io
import json
import urllib.parse
from datetime import date, datetime, timedelta
from decimal import Decimal

import qrcode
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Count, Sum
from django.dispatch import receiver
from django.http import Http404, HttpResponse
from django.http.response import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.defaultfilters import pluralize
from django.views.decorators.csrf import csrf_exempt

from almoxarifado.utils import OPERADOR_ALMOXARIFADO_OU_PATRIMONIO
from centralservicos.models import Chamado
from comum.models import Configuracao, Sala
from comum.utils import get_setor, get_uo
from djtools import layout
from djtools.templatetags.filters import format_datetime
from djtools.utils import (
    calendario,
    date_to_string,
    generate_autocomplete_dict,
    group_required,
    httprr,
    is_ajax,
    permission_required,
    render,
    render_to_string,
    rtr,
    send_mail,
    somar_dias,
    to_ascii,
)
from patrimonio import migrador, tasks
from patrimonio.forms import (
    AjusteInventarioForm,
    AvaliarInventariosForm,
    BaixaFormFactory,
    BaixaInventarioFormFactory,
    CampusFiltroInconsistenteForm,
    CargaFiltroForm,
    CargaFormFactory,
    CautelaInventarioForm,
    DeferirRequisicaoForm,
    EdicaoPADestinoForm,
    EdicaoPAOrigemForm,
    EditarInventario,
    FiltroInventariosNaoConferidosForm,
    FormTotalizacaoEdPeriodo,
    FotoInventarioForm,
    InconsistenciaFormFactory,
    IndeferirRequisicaoForm,
    InformarPADestinoForm,
    InformarPAOrigemForm,
    InventarioBuscaFormFactory,
    InventariosEditarEmLoteFormFactory,
    MigracaoInventarioForm,
    ReavaliacaoInventarioForm,
    RequisicaoInventarioUsoPessoalForm,
    RequisicaoTransferenciaColetorFormFactory,
    RequisicaoTransferenciaForm,
    ServidorCargaFormFactory,
)
from patrimonio.models import (
    Baixa,
    Cautela,
    CautelaInventario,
    ConferenciaItem,
    ConferenciaSala,
    DescricaoInventario,
    EntradaPermanente,
    FotoInventario,
    Inventario,
    InventarioCargaContabil,
    InventarioReavaliacao,
    InventarioRotulo,
    InventarioTipoUsoPessoal,
    InventarioValor,
    MovimentoPatrim,
    Requisicao,
    RequisicaoHistorico,
    RequisicaoInventarioUsoPessoal,
    RequisicaoItem,
)
from patrimonio.relatorio import totalizacaoCategoriaPeriodo, totalizacaoPlanoContasPeriodo
from patrimonio.utils import AUDITOR, OPERADOR_PATRIMONIO
from rh.forms import Meses
from rh.models import Servidor, UnidadeOrganizacional
from rh.views import rh_servidor_view_tab


@layout.atribuidos_a_mim()
def index_atribuidos_a_mim(request):
    pendencias = []
    usuario = request.user
    if usuario.eh_servidor:
        vinculo = usuario.get_vinculo()
        qtd = Requisicao.get_aguardando_aprovacao_servidor(vinculo).count()
        if qtd:
            pendencias.append(
                {
                    'titulo': f'Requisiç{pluralize(qtd, "ão,ões")} de Patrimônio',
                    'subtitulo': 'aguardando aprovação',
                    'qtd': qtd,
                    'url': '/admin/patrimonio/requisicao/?tab=tab_aguardando_aprovacao_servidor',
                }
            )
    return pendencias


@layout.atribuidos_a_meus_grupos()
def index_atribuidos_a_meus_grupos(request):
    pendencias = []
    usuario = request.user
    if usuario.has_group_cached('Coordenador de Patrimônio', ignore_groups_if_superuser=False):
        uo_usuario = get_uo(usuario)
        requisicoes_campus_aguardando_destino = Requisicao.get_requisicoes_campus_aguardando_destino(uo_usuario).count()
        if requisicoes_campus_aguardando_destino:
            pendencias.append(
                {
                    'titulo': f'Requisiç{pluralize(requisicoes_campus_aguardando_destino, "ão,ões")} de Transferência',
                    'subtitulo': 'a aprovar',
                    'qtd': requisicoes_campus_aguardando_destino,
                    'url': f'/admin/patrimonio/requisicao/?campus_origem__id__exact={get_uo(request.user).pk}&status__exact=1',
                }
            )

    return pendencias


@layout.info()
def index_infos(request):
    infos = []

    # Inventário de Uso pessoal (netbooks, notebooks, entre outros cedidos pela instituição)
    inventarios_uso_pessoal = RequisicaoInventarioUsoPessoal.tipos_uso_pessoal_permitidos(request.user)
    for invs in inventarios_uso_pessoal:
        infos.append({'url': f'patrimonio/requisicao_inventario_uso_pessoal/{invs.pk}', 'titulo': f'Requisitar {invs.descricao}.'})

    return infos


@layout.quadro('Patrimônio', icone='building')
def index_quadros(quadro, request):
    usuario = request.user
    if usuario.eh_servidor:
        if usuario.has_perm('comum.is_contador_de_patrimonio', ignore_superuser=True):
            uo_usuario = get_setor(usuario).uo
            if uo_usuario:
                qtd_requisicoes_aguardando_informacao_pa_origem = Requisicao.get_qs_aguardando_informacao_pa_origem(uo_usuario).count()
                if qtd_requisicoes_aguardando_informacao_pa_origem:
                    quadro.add_item(
                        layout.ItemContador(
                            titulo=f'Requisiç{pluralize(qtd_requisicoes_aguardando_informacao_pa_origem, "ão,ões")} de Transferência',
                            subtitulo='Aguardando PA Campus Origem',
                            qtd=qtd_requisicoes_aguardando_informacao_pa_origem,
                            url='/admin/patrimonio/requisicao/?tab=tab_aguardando_informacao_pa_origem',
                        )
                    )
                qtd_requisicoes_aguardando_informacao_pa_destino = Requisicao.get_qs_aguardando_informacao_pa_destino(uo_usuario).count()
                if qtd_requisicoes_aguardando_informacao_pa_destino:
                    quadro.add_item(
                        layout.ItemContador(
                            titulo=f'Requisiç{pluralize(qtd_requisicoes_aguardando_informacao_pa_destino, "ão,ões")} de Transferência',
                            subtitulo='Aguardando PA Campus Destino',
                            qtd=qtd_requisicoes_aguardando_informacao_pa_destino,
                            url='/admin/patrimonio/requisicao/?tab=tab_aguardando_informacao_pa_destino',
                        )
                    )

    if request.user.has_group_cached(
        ['Operador de Patrimônio', 'Coordenador de Patrimônio', 'Coordenador de Patrimônio Sistêmico'], ignore_groups_if_superuser=False
    ):
        if request.user.has_perm('patrimonio.pode_alterar_carga_contabil_do_campus'):
            qtd_carga_contabil_inconsistentes = Inventario.get_carga_contabil_inconsistentes(request.user).count()
            if qtd_carga_contabil_inconsistentes:
                quadro.add_item(
                    layout.ItemContador(
                        titulo=f'Inventário{pluralize(qtd_carga_contabil_inconsistentes)}',
                        subtitulo='Com carga contábil diferente do campus do responsável',
                        qtd=qtd_carga_contabil_inconsistentes,
                        url='/patrimonio/listar_inventarios_carga_contabil_inconsistentes/',
                    )
                )
        vinculo = request.user.get_vinculo()
        uo = get_uo(request.user)
        if vinculo and uo:
            qtd_pendentes = Inventario.get_pendentes(uo=uo).count()
            if qtd_pendentes:
                quadro.add_item(
                    layout.ItemContador(
                        titulo=f'Inventário{pluralize(qtd_pendentes)}',
                        subtitulo='Sem carga',
                        qtd=qtd_pendentes,
                        url='/patrimonio/inventarios_pendentes/',
                    )
                )
            qtd_servidores_inativos_com_carga = Inventario.servidores_inativos_com_carga(uo=uo).count()
            if qtd_servidores_inativos_com_carga:
                quadro.add_item(
                    layout.ItemContador(
                        titulo=f'Servidor{pluralize(qtd_servidores_inativos_com_carga, ",es")} Inativo{pluralize(qtd_servidores_inativos_com_carga)}',
                        subtitulo='Com carga',
                        qtd=qtd_servidores_inativos_com_carga,
                        url=f'/patrimonio/servidores_com_carga/?ativos=3&com_funcao=1&unidade_organizacional={uo.id}',
                    )
                )

    return quadro


@rtr()
@group_required(OPERADOR_PATRIMONIO)
def carga(request):
    title = 'Criar Requisição de Carga de Inventários Pendentes'
    FormClass = CargaFormFactory(request)
    form_carga = FormClass(request.POST or None)
    if form_carga.is_valid():
        form_carga.save()
        return httprr('.', 'Requisição criada com sucesso.')

    inventarios = None
    if request.GET:
        form_filtro = CargaFiltroForm(request.GET)
        if form_filtro.is_valid():
            inventarios = Inventario.get_pendentes(uo=form_filtro.cleaned_data['campus'])
            for descricao in form_filtro.cleaned_data['descricao'].replace("'", ' ').split():
                inventarios = inventarios.filter(descricao__unaccent__icontains=descricao)
            if form_filtro.cleaned_data['numero']:
                inventarios = inventarios.filter(numero__icontains=form_filtro.cleaned_data['numero'])
        elif form_filtro.is_bound:
            inventarios = Inventario.pendentes.all()
            form_filtro = CargaFiltroForm()
    else:
        uo_user = get_uo()
        inventarios = Inventario.get_pendentes(uo=uo_user)

        form_filtro = CargaFiltroForm({'campus': uo_user.id})

    inventarios = inventarios.select_related('entrada_permanente', 'entrada_permanente__categoria', 'entrada_permanente__entrada__uo')

    inventarios_ids = [int(i) for i in request.POST.getlist('inventarios')]
    return locals()


@login_required
def exibir_inventarios_pendentes(request):
    if request.user.eh_servidor:
        servidor = request.user.get_relacionamento()
        return HttpResponseRedirect(f'/patrimonio/carga/?descricao=&campus={servidor.campus.id}')

    raise PermissionDenied


@rtr()
@transaction.atomic()
@group_required(','.join(OPERADOR_PATRIMONIO + AUDITOR))
def baixa(request, baixa_pk):
    """
    Tela para efetuar baixas
    """
    baixa = get_object_or_404(Baixa, pk=baixa_pk)

    # Auditor apenas visualiza
    if request.method == 'POST' and request.user.groups.filter(name='Auditor').exists():
        return httprr('.', 'Você possui permissão apenas para visualizar esta baixa.', 'alert')

    itens = baixa.movimentopatrim_set.order_by('inventario__numero')
    resumo_ed = baixa.get_total_categoria()

    valor_total_inicial = baixa.get_valor_inicial()
    valor_total = baixa.get_valor()
    valor_depreciacao_acumulada = baixa.get_valor_inicial() - baixa.get_valor()

    FormClass = BaixaInventarioFormFactory(request.user)
    form = FormClass(request.POST or None)

    if form.is_valid():
        if form.cleaned_data['tipo_baixa'] == 'inventario':
            Inventario.efetuar_baixa(baixa=baixa, inventarios=form.cleaned_data['inventario'])
            return httprr('.', 'Baixa efetuada com sucesso.')

        elif form.cleaned_data['tipo_baixa'] == 'rotulo':
            inventarios = Inventario.objects.filter(rotulos=form.cleaned_data['rotulo'])

            for inventario in inventarios:
                Inventario.efetuar_baixa(inventarios=inventario, baixa=baixa)

            return httprr('.', 'Baixa efetuada com sucesso.')

        elif form.cleaned_data['tipo_baixa'] == 'faixa':
            for inventario in form.cleaned_data['faixa']:
                Inventario.efetuar_baixa(inventarios=inventario, baixa=baixa)

            return httprr('.', 'Baixa efetuada com sucesso.')

    return locals()


@rtr('patrimonio/templates/baixa_editar.html')
@group_required(OPERADOR_PATRIMONIO)
def baixa_editar(request, baixa_pk):
    """
    Tela para editar baixas
    """
    baixa = get_object_or_404(Baixa, pk=baixa_pk)

    # campus do usuário logado
    uo = get_uo(request.user)

    # não permite alterar baixas que não são do seu campus
    if uo.id != baixa.uo_id:
        return httprr('/admin/patrimonio/baixa/', 'Você não pode editar baixas que não são do seu campus.', 'error')

    FormClass = BaixaFormFactory(uo, instance=baixa)
    if request.method == 'POST':
        form = FormClass(request.POST)
        if form.is_valid():
            baixa.tipo = form.cleaned_data['tipo']
            baixa.data = form.cleaned_data['data']
            baixa.numero = form.cleaned_data['numero']
            baixa.observacao = form.cleaned_data['observacao']
            baixa.processo = form.cleaned_data['processo']
            baixa.uo = form.cleaned_data['uo']
            baixa.save()
            return httprr('/admin/patrimonio/baixa/', 'Baixa editada com sucesso')
    else:
        form = FormClass()
    return locals()


@rtr()
def baixa_remover(request, baixa_pk):
    baixa = get_object_or_404(Baixa, pk=baixa_pk)

    # campus do usuário logado
    uo = get_uo(request.user)

    # não permite alterar baixas que não são do seu campus
    if uo.id != baixa.uo_id:
        return httprr(f'/patrimonio/baixa/{baixa_pk}/', 'Você não pode excluir baixas que não são do seu campus.', 'error')

    baixa.delete()
    return httprr('/admin/patrimonio/baixa/', 'Baixa removida com sucesso')


@rtr()
@permission_required('patrimonio.delete_baixa')
def baixa_remover_item(request, baixa_pk, movimentopatrim_pk):
    baixa = Baixa.objects.get(id=baixa_pk)
    baixa.delete_item(movimentopatrim_pk)
    return httprr(f'/patrimonio/baixa/{baixa_pk}/', 'Item de Baixa removida com sucesso')


###############
# INVENTÁRIOS #
###############


def filtrar_por_numero(inventarios, numero):
    if '-' in numero:
        faixa = numero.split('-')
        a = int(faixa[0])
        b = int(faixa[1])
        if a < b:
            return inventarios.filter(numero__gte=a, numero__lte=b)
        return inventarios.filter(numero__gte=b, numero__lte=a)
    if ',' in numero:
        faixa = numero.split(',')
        return inventarios.filter(numero__in=faixa)
    return inventarios.filter(numero=numero)


def filtrar_por_valor(inventarios, valor):
    valor = valor.replace(',', '.')
    igualdade = valor.count('=') == 1
    if igualdade:
        valor = valor.replace('=', '')
    valor_em_decimal = None
    try:
        valor_em_decimal = Decimal(valor[1:])
    except Exception:
        pass

    if valor_em_decimal and '<' in valor:
        return inventarios.filter(valor__lte=valor_em_decimal) if igualdade else inventarios.filter(valor__lt=valor_em_decimal)
    if valor_em_decimal and '>' in valor:
        return inventarios.filter(valor__gte=valor_em_decimal) if igualdade else inventarios.filter(valor__gt=valor_em_decimal)
    if igualdade:
        return inventarios
    try:
        return inventarios.filter(valor=Decimal(valor))
    except Exception:
        return inventarios


def filtrar_por_descricao(inventarios, descricao):
    for token in descricao.split():
        inventarios = inventarios.filter(campo_busca__icontains=token)
    return inventarios


def filtrar_por_numero_transferencia(inventarios, numero_transferencia):
    return inventarios.filter(id__in=RequisicaoItem.objects.filter(requisicao__id=numero_transferencia).values_list('inventario__id', flat=True))


def filtrar_por_campus_sala(inventarios, campus_sala):
    sala_uo = Sala.ativas.filter(predio__uo=campus_sala)
    if sala_uo:
        return inventarios.filter(responsavel_vinculo__setor__uo=campus_sala)
    return inventarios


def filtrar_por_setor(inventarios, setor, recursivo):
    if recursivo:
        id_setor_pai = setor.id
        lista_ids_setores_descendentes = list(setor.ids_descendentes)
        filtro_recursivo = [id_setor_pai, *lista_ids_setores_descendentes]
        return inventarios.filter(responsavel_vinculo__setor__id__in=filtro_recursivo)
    return inventarios.filter(responsavel_vinculo__setor=setor)


def filtrar_inventarios(dados):
    """
    Realiza o filter do queryset que retorna o resultado da busca de inventários por
    meio do InventarioBuscaForm.
    """
    inventarios = Inventario.objects.all()

    filtros_simples = [
        (dados.get('numero'), filtrar_por_numero),
        (dados.get('valor'), filtrar_por_valor),
        (dados.get('descricao'), filtrar_por_descricao),
        (dados.get('observacao'), lambda qs, v: qs.filter(observacao__icontains=v)),
        (dados.get('status'), lambda qs, v: qs.filter(status=v)),
        (dados.get('rotulos'), lambda qs, v: qs.filter(rotulos=v)),
        (dados.get('numero_serie'), lambda qs, v: qs.filter(numero_serie__icontains=v)),
        (dados.get('elemento_despesa'), lambda qs, v: qs.filter(entrada_permanente__categoria=v)),
        (dados.get('numero_transferencia'), filtrar_por_numero_transferencia),
        (dados.get('sala'), lambda qs, v: qs.filter(sala=v)),
        (dados.get('campus_sala'), filtrar_por_campus_sala),
        (dados.get('responsavel'), lambda qs, v: qs.filter(responsavel_vinculo=v.get_vinculo())),
        (dados.get('campus'), lambda qs, v: qs.filter(carga_contabil__campus=v)),
        (dados.get('data_inicial'), lambda qs, v: qs.filter(entrada_permanente__entrada__data__gte=v)),
        (dados.get('data_final'), lambda qs, v: qs.filter(entrada_permanente__entrada__data__lte=v)),
        (dados.get('fornecedor'), lambda qs, v: qs.filter(entrada_permanente__entrada__vinculo_fornecedor=v.get_vinculo())),
        (dados.get('estado_conservacao'), lambda qs, v: qs.filter(estado_conservacao=v)),
    ]
    for valor, aplicar_filtro in filtros_simples:
        if valor:
            inventarios = aplicar_filtro(inventarios, valor)

    setor = dados.get('setor_responsavel')
    if setor:
        inventarios = filtrar_por_setor(inventarios, setor, dados.get('recursivo'))

    return inventarios.order_by('numero')


def otimizar_para_listagem(inventarios):
    """Pré-carrega os relacionamentos usados pelas colunas da listagem, evitando N+1 por linha.

    ponytail: cobre apenas as colunas exibidas por padrão. As colunas opcionais
    ver_data_carga, ver_ultima_requisicao e ver_ultima_conferencia continuam N+1 por linha;
    adicionar prefetch para elas se passarem a ser exibidas por padrão.
    """
    return inventarios.select_related(
        'status',
        'sala__predio__uo',
        'responsavel_vinculo__setor__uo__setor',
        'entrada_permanente__categoria',
        'entrada_permanente__entrada',
    ).prefetch_related('rotulos', 'responsavel_vinculo__relacionamento')


@rtr()
def inventario_busca(request):
    """
    Exibe e processa o Form de busca de inventários.
    Exporta resultados da busca para formatos XLS e CSV.
    Aplica rótulo, sala e estado de conservação a inventários selecionados da
    listagem de resultados retornada da busca.

    """
    title = 'Busca de Inventários'

    if not request.user.has_perm('patrimonio.ver_inventarios') and not request.user.has_perm('patrimonio.pode_ver_propria_carga'):
        raise PermissionDenied

    user_pode_editar = request.user.has_perm('patrimonio.editar_todos') or request.user.has_perm('patrimonio.editar_do_meu_campus')

    FormClass = InventarioBuscaFormFactory(request.user)
    form = FormClass(request.GET or None)
    form_collapsed = ''
    if form.is_valid():
        form_collapsed = 'collapsed'
        inventarios = filtrar_inventarios(form.cleaned_data)
        url_base = request.path + '?' + request.GET.urlencode()
        url_csv = url_base + '&format=csv'
        url_xls = url_base + '&format=xls'
        if request.method == 'GET':
            formato = request.GET.get('format')
            if formato in ['xls', 'csv']:
                return tasks.inventario_dados_exportacao(inventarios, formato, form.cleaned_data['ver_observacao'])

        # A exportação tem seu próprio select_related/only; otimiza apenas a listagem HTML.
        inventarios = otimizar_para_listagem(inventarios)

        ver_sala = form.cleaned_data['ver_sala']
        ver_responsavel = form.cleaned_data['ver_responsavel']
        ver_elemento_despesa = form.cleaned_data['ver_elemento_despesa']
        ver_situacao = form.cleaned_data['ver_situacao']
        ver_rotulo = form.cleaned_data['ver_rotulo']
        ver_numeroserie = form.cleaned_data['ver_numeroserie']
        ver_estado_conservacao = form.cleaned_data['ver_estado_conservacao']
        ver_data_entrada = form.cleaned_data['ver_data_entrada']
        ver_data_carga = form.cleaned_data['ver_data_carga']
        ver_fornecedor = form.cleaned_data['ver_fornecedor']
        ver_valor = form.cleaned_data['ver_valor']
        ver_valor_inicial = form.cleaned_data['ver_valor_inicial']
        ver_ultima_requisicao = form.cleaned_data['ver_ultima_requisicao']
        ver_ultima_conferencia = form.cleaned_data['ver_ultima_conferencia']
        ver_observacao = form.cleaned_data['ver_observacao']
        try:
            opcao_visualizacao = int(form.cleaned_data['opcoes_visualizacao'])
        except Exception:
            opcao_visualizacao = 50

        form_edicao_lote = None
        if (
            request.user.has_perm('patrimonio.editar_todos')
            and form.cleaned_data['campus']
            or request.user.has_perm('patrimonio.editar_do_meu_campus')
            and get_uo() == form.cleaned_data['campus']
        ):
            form_edicao_lote = True
        if form_edicao_lote:
            campus = form.cleaned_data['campus']
            FormClass = InventariosEditarEmLoteFormFactory(campus=campus)
            form_rotulo_sala = FormClass()
    return locals()


@rtr()
@transaction.atomic()
def inventario_editar(request, inventario_id):
    inventario = get_object_or_404(Inventario, pk=inventario_id)
    title = f'Inventário {inventario.numero}'

    if not inventario.user_pode_editar():
        raise PermissionDenied

    entrada_permanente = EntradaPermanente.objects.filter(id=inventario.entrada_permanente.id).first()
    elemento_despesa = None
    if entrada_permanente:
        elemento_despesa = entrada_permanente.categoria
    form = EditarInventario(request.POST or None, instance=inventario, request=request, initial={'elemento_despesa': elemento_despesa})
    if form.is_valid():
        form.save()
        if 'elemento_despesa' in form.changed_data:
            entrada_permanente = EntradaPermanente.objects.get(id=inventario.entrada_permanente.id)
            entrada_permanente.categoria = form.cleaned_data['elemento_despesa']
            entrada_permanente.save()
        if 'descricao' in form.changed_data:
            DescricaoInventario.objects.create(inventario=inventario, descricao=form.cleaned_data['descricao'])

        return httprr(f'/patrimonio/inventario/{inventario.numero}/', 'Inventário salvo com sucesso.')

    return locals()


@rtr()
@login_required()
def inventario(request, inventario_numero):
    inventario = get_object_or_404(Inventario, numero=inventario_numero)
    title = f'Inventário {inventario.numero}'
    historico_requisicao = Requisicao.objects.filter(itens__inventario=inventario).order_by('-id')
    reavaliacao = InventarioReavaliacao.objects.filter(inventario=inventario).order_by('data')
    depreciacao = InventarioValor.objects.filter(inventario=inventario).order_by('data')
    percentual_residual = int(inventario.entrada_permanente.categoria.percentual_residual * 100)
    chamados = Chamado.get_chamados_por_patrimonio([inventario])

    return locals()


def inventario_adicionar_rotulo_sala(request):
    try:
        rotulo_id = request.POST['rotulo'].strip('[').strip(']')
        if rotulo_id:
            rotulo = InventarioRotulo.objects.get(id=int(rotulo_id))
        else:
            rotulo = None
    except InventarioRotulo.DoesNotExist, KeyError:
        rotulo = None

    try:
        sala_id = request.POST['sala'].strip('[').strip(']')
        if sala_id:
            sala = Sala.objects.get(id=int(sala_id))
        else:
            sala = None
    except Sala.DoesNotExist, KeyError:
        sala = None

    conservacao = None
    if 'conservacao' in request.POST:
        conservacao = request.POST['conservacao'].strip('[').strip(']')
    remove_rotulo = None
    if 'exclusao_rotulo' in request.POST:
        remove_rotulo = request.POST['exclusao_rotulo'].strip('[').strip(']')

    ids_inventarios = request.POST.getlist('marcados')
    inventarios = [Inventario.objects.get(id=i) for i in ids_inventarios]

    uso_pessoal = None
    if request.POST.get('tipo_uso_pessoal'):
        uso_pessoal = InventarioTipoUsoPessoal.objects.get(pk=request.POST['tipo_uso_pessoal'])

    msg = 'Modificações realizadas com sucesso.'
    fotos = None
    if request.FILES:
        fotos = request.FILES.getlist('fotos')
    for inventario in inventarios:
        if rotulo:
            inventario.rotulos.add(rotulo)
        if remove_rotulo:
            for r in inventario.rotulos.all():
                inventario.rotulos.remove(r)
        if sala:
            inventario.sala = sala
        if conservacao:
            inventario.estado_conservacao = conservacao

        if uso_pessoal:
            inventario.tipo_uso_pessoal = uso_pessoal
        if fotos:
            if not request.POST['descricao_fotos'] or not request.POST['data_fotos']:
                return httprr(request.META.get('HTTP_REFERER', '..'), 'Informe a descrição e a data das fotos', tag='error')

            for foto in fotos:
                nova_foto = FotoInventario()
                nova_foto.inventario = inventario
                nova_foto.descricao = request.POST['descricao_fotos']
                nova_foto.data = request.POST['data_fotos']
                nova_foto.foto = foto
                nova_foto.save()

        inventario.save()
    return httprr(request.META.get('HTTP_REFERER', '/patrimonio/inventario_busca/'), msg)


###
# Servidores
###


@rtr()
@group_required(','.join(OPERADOR_PATRIMONIO + AUDITOR))
def servidores_com_carga(request):
    title = 'Servidores com carga'

    servidores_qs = Inventario.get_servidores_com_carga(ativo=None, tem_funcao=None, uo=get_uo(request.user))

    FormClass = ServidorCargaFormFactory(request.user)
    form = FormClass(request.GET or None)

    if form.is_valid():
        ativo = form.cleaned_data['ativos']
        tem_funcao = form.cleaned_data['com_funcao']
        unidade_organizacional = form.cleaned_data['unidade_organizacional']

        servidores_qs = Inventario.get_servidores_com_carga(ativo=ativo, tem_funcao=tem_funcao, uo=unidade_organizacional)

    servidores = list(servidores_qs)

    lista_campus = []
    ids_campus = {s.setor.uo.id for s in servidores if s.setor and s.setor.uo}

    for id_campus in ids_campus:
        campus = {
            'nome_campus': str(UnidadeOrganizacional.objects.suap().get(id=id_campus)),
            'servidores': [s for s in servidores if s.setor and s.setor.uo and s.setor.uo.id == id_campus],
        }
        lista_campus.append(campus)

    serv_nenhum = [s for s in servidores if not s.setor or not s.setor.uo]

    if serv_nenhum:
        lista_campus.append({'nome_campus': 'Nenhum', 'servidores': serv_nenhum})

    return locals()


###
# Cautela
###


@rtr()
@group_required(','.join(OPERADOR_PATRIMONIO + AUDITOR))
def cautela(request, cautela_pk):
    """Tela de detalhes da cautela, com opções para adicionar itens."""
    cautela = Cautela.objects.get(pk=cautela_pk)

    link_editar = f'/admin/patrimonio/cautela/{cautela.id}/change/'

    if request.method == 'POST':
        form = CautelaInventarioForm(request.POST)
        form.instance.cautela = cautela
        if form.is_valid():
            form.save()
            return httprr('.', 'Item da Cautela cadastrado com sucesso.')
    else:
        form = CautelaInventarioForm()

    return locals()


def cautelainventario_remover(request, id_cautelainventario):
    cautelainventario = CautelaInventario.objects.select_related('inventario').get(id=id_cautelainventario)
    cautelainventario.delete()
    return httprr(cautelainventario.cautela.get_absolute_url(), 'Item removido com sucesso!')


@rtr()
@group_required(OPERADOR_PATRIMONIO)
def cautela_adicionar(request):
    title = 'Efetuar Cautela'
    if request.method == 'POST':
        form = CautelaInventarioForm(request.POST)
        if form.is_valid():
            cautela = Cautela(
                responsavel=str(form.cleaned_data['responsavel']),
                data_inicio=form.cleaned_data['data_inicio'],
                data_fim=form.cleaned_data['data_fim'],
                descricao=form.cleaned_data['descricao'],
            )
            cautela.save()
            for inventario in form.cleaned_data['inventarios']:
                cautela_inventario = CautelaInventario(inventario=inventario, cautela=cautela)
                cautela_inventario.save()
            msg = 'Cautela efetuada com sucesso.'
            return httprr('/admin/patrimonio/cautela/', msg)
    else:
        form = CautelaInventarioForm()
    return locals()


@rtr()
@group_required(','.join(OPERADOR_PATRIMONIO + AUDITOR))
def tela_cautela_detalhe(request, cautela_id):
    cautela = Cautela.objects.get(id=cautela_id)
    ci = CautelaInventario.objects.filter(cautela=cautela)
    objeto = {}
    resposta = []
    for i in ci:
        objeto['numero'] = i.inventario.numero
        objeto['descricao'] = i.inventario.get_descricao()
        resposta.append(objeto)
        objeto = {}
    return {'resposta': resposta, 'cautela': cautela}


###
# Relatórios
###


@group_required(OPERADOR_ALMOXARIFADO_OU_PATRIMONIO)
@rtr()
def totalizacao_ed_periodo(request):
    title = 'Totalização por Elemento de Despesa por Período de Entrada'
    form = FormTotalizacaoEdPeriodo(request.GET or None)
    if form.is_valid():
        resposta, total = totalizacaoCategoriaPeriodo(form.cleaned_data['ano'], int(form.cleaned_data['mes']), form.cleaned_data['doacoes'])
        request.session['resposta'] = {
            'resposta': resposta,
            'total': total,
            'ano': form.cleaned_data['ano'],
            'mes': Meses.get_mes(int(form.cleaned_data['mes'])),
            'doacoes_inclusas': form.cleaned_data['doacoes'],
        }
        return render('patrimonio/templates/relatorio/totalizacao_ed_Periodo.html', request.session['resposta'])
    else:
        return locals()


@group_required(OPERADOR_PATRIMONIO)
def telarelatoriobaixa(request):
    return render('patrimonio/templates/relatorio/baixa.html', {})


# O relatório a seguir apresenta as movimentações patrimoniais agrupadas por data e responsável.
# Serão exibidos apenas as movimentações ocorridas nos últimos sete dias (de movimentação efetiva) anteriores à data limite.
@rtr()
def inventarios_cargas(request):
    movimentos = []
    limite_inferior = datetime.today()
    limite_superior = datetime.today()

    if 'limite' in request.GET:
        limite_inferior = datetime.strptime(request.GET['limite_inferior'], '%d/%m/%Y')
        limite_superior = datetime.strptime(request.GET['limite_superior'], '%d/%m/%Y')
        if request.GET['limite'] == 'superior':
            datas = MovimentoPatrim.objects.filter(vinculo__isnull=False, data__gt=limite_superior).dates('data', 'day', order='DESC')[:7]
        else:
            datas = MovimentoPatrim.objects.filter(vinculo__isnull=False, data__lt=limite_inferior).dates('data', 'day', order='DESC')[:7]
    else:
        datas = MovimentoPatrim.objects.filter(vinculo__isnull=False).dates('data', 'day', order='DESC')[:7]

    for dia in datas:
        depois = dia + timedelta(days=1)
        registros = MovimentoPatrim.objects.filter(vinculo__isnull=False, data__gt=dia, data__lt=depois).order_by('-data', 'vinculo')[:5]
        movimentos.extend(list(registros))

    if len(datas) > 0:
        limite_superior = datas[0]  # primeira data da lista
    if len(datas) > 1:
        limite_inferior = datas[len(datas) - 1]  # ultima data da lista
    if len(datas) == 1:
        limite_inferior = limite_superior

    # formata os objetos do tipo data para string
    limite_inferior = date_to_string(limite_inferior)
    limite_superior_mais_um = date_to_string(somar_dias(limite_superior, 1))
    limite_superior = date_to_string(limite_superior)

    return render(
        'patrimonio/templates/inventarios_carga.html',
        {
            'movimentos': movimentos,
            'limite_superior': limite_superior,
            'limite_superior_mais_um': limite_superior_mais_um,
            'limite_inferior': limite_inferior,
        },
    )


@rtr()
def adicionar_foto_inventario(request, inventario_id):
    title = 'Adicionar foto'
    inventario = Inventario.objects.get(id=inventario_id)
    form = FotoInventarioForm(request.POST or None, files=request.FILES or None)
    if form.is_valid():
        i = form.save(False)
        i.inventario = inventario
        i.save()
        return httprr('..', 'Foto adicionada com sucesso')

    return locals()


def remover_foto_inventario(request, inventario_numero, foto_id):
    fotoinventario = FotoInventario.objects.filter(id=foto_id).first()
    if fotoinventario is None:
        return httprr(f'/patrimonio/inventario/{inventario_numero}/', 'Foto não localizada.', 'error')
    else:
        fotoinventario.delete()
        return httprr(f'/patrimonio/inventario/{inventario_numero}/', 'Foto removida com sucesso.')


def visualizar_foto_inventario(request, foto_id):
    try:
        fotoinventario = FotoInventario.objects.get(pk=foto_id)
    except FotoInventario.DoesNotExist:
        return httprr('..', 'Esta foto não existe.', 'error')

    return HttpResponse(fotoinventario.foto.read(), content_type='image/png')


def requisicao_enviar_email(requisicao):
    titulo = f'[SUAP] Comprovante de Inscrição para Recebimento de {requisicao.tipo_uso_pessoal.descricao} (Matrícula: {requisicao.vinculo.relacionamento.matricula})'
    texto = f"""
        <h1>Patrimônio</h1>
        <p>A inscrição do servidor {requisicao.vinculo.pessoa.nome}, matrícula {requisicao.vinculo.relacionamento.matricula}, foi realizada com sucesso.</p>
        <dl>
            <dt>Item Solicitado:</dt><dd>{requisicao.tipo_uso_pessoal.descricao}</dd>
            <dt>Data/Hora da Inscrição:</dt><dd>{calendario.datetime_to_string(requisicao.horario)}</dd>
        </dl>"""

    email_destino = [requisicao.vinculo.email_notificacao]

    # enviar e-mail com cópia?
    if len(requisicao.tipo_uso_pessoal.enviar_email_copia) > 0:
        email_destino.append(requisicao.tipo_uso_pessoal.enviar_email_copia)

    return send_mail(titulo, texto, settings.DEFAULT_FROM_EMAIL, email_destino)


@login_required()
@rtr()
def requisicao_inventario_uso_pessoal(request, pk):
    # verifica novamente se usuário logado tem permissão (ou se já respondeu a requisição)
    if int(pk) in RequisicaoInventarioUsoPessoal.tipos_uso_pessoal_permitidos(request.user).values_list('pk', flat=True):
        tipo_uso_pessoal = InventarioTipoUsoPessoal.objects.get(pk=pk)
        form = RequisicaoInventarioUsoPessoalForm(request.POST or None)
        if form.is_valid():
            if form.cleaned_data['confirmacao']:
                r = RequisicaoInventarioUsoPessoal()
                r.vinculo = request.user.get_vinculo()
                r.tipo_uso_pessoal = tipo_uso_pessoal
                r.save()

                # envia e-mail
                if r.tipo_uso_pessoal.enviar_email_inscrito:
                    requisicao_enviar_email(r)

                return httprr(
                    '/patrimonio/requisicao_inventario_uso_pessoal_listar/',
                    'Requisição cadastrada com sucesso. Acesse Administração -> Patrimônio -> Requisição de Equipamentos para acompanhar.',
                )
            else:
                return httprr('/', 'A sua requisição não foi cadastrada.')

        return locals()


@rtr()
@login_required()
def requisicao_inventario_uso_pessoal_listar(request):
    title = 'Requisições de Equipamentos'
    requisicoes = RequisicaoInventarioUsoPessoal.objects.filter(vinculo=request.user.get_vinculo())

    return locals()


@rtr()
@login_required()
def remover_rotulo(request, inventario_id, rotulo_id):
    inventario = get_object_or_404(Inventario, pk=inventario_id)
    if not inventario.rotulos.filter(pk=rotulo_id).exists():
        raise Http404

    rotulo = inventario.rotulos.get(pk=rotulo_id)
    inventario.rotulos.remove(rotulo)
    return HttpResponse('Rótulo removido com sucesso.')


@rtr()
@group_required('Operador de Patrimônio, Coordenador de Patrimônio, Coordenador de Patrimônio Sistêmico')
def autorizar_coletor(request, conferencia_id):
    title = 'QRCode para Leitura'
    conferencia = get_object_or_404(ConferenciaSala, pk=conferencia_id)

    return locals()


@group_required('Operador de Patrimônio, Coordenador de Patrimônio, Coordenador de Patrimônio Sistêmico')
def conferencia_visualizar_qrcode(request, conferencia_id):
    conferencia = get_object_or_404(ConferenciaSala, pk=conferencia_id)

    # gerando qrcode
    qrcode_texto = (
        str(conferencia.id)
        + '|'
        + to_ascii(conferencia.sala.nome.replace('|', '/'))
        + '|'
        + format_datetime(conferencia.dh_criacao)
        + '|'
        + conferencia.token
        + '|'
        + str(conferencia.sala.id)
        + '|'
        + str(conferencia.sala.predio.uo.id)
    )
    img = qrcode.make(qrcode_texto)
    fp = io.BytesIO()
    img.save(fp, 'png')

    return HttpResponse(fp.getvalue(), content_type='image/png')


@rtr()
@permission_required('patrimonio.view_conferenciasala')
def conferenciasala(request, conferencia_id):
    conferencia = get_object_or_404(ConferenciaSala, pk=conferencia_id)
    title = f'Conferência de Sala #{conferencia.id}'

    conferencias_itens = conferencia.conferenciaitem_set.all()
    q_conferencias = request.GET.get('q_conferencias_itens', '')
    if q_conferencias:
        conferencias_itens = conferencias_itens.filter(inventario__campo_busca__icontains=q_conferencias)
    conferencia_total = conferencias_itens.aggregate(total=Sum('inventario__entrada_permanente__valor'), qtd=Count('inventario'))

    ids = ConferenciaItem.objects.filter(conferencia=conferencia).values_list('inventario', flat=True)
    inventarios_nao_coletados = Inventario.objects.filter(sala=conferencia.sala).exclude(pk__in=ids)
    q_inventarios_nao_coletados = request.GET.get('q_inventarios_nao_coletados', '')
    if q_inventarios_nao_coletados:
        inventarios_nao_coletados = inventarios_nao_coletados.filter(campo_busca__icontains=q_inventarios_nao_coletados)

    inventarios_erros = conferencia.conferenciaitemerro_set.all()
    q_inventarios_erros = request.GET.get('q_inventarios_erros', '')
    if q_inventarios_erros:
        inventarios_erros = inventarios_erros.filter(inventario__icontains=q_inventarios_erros)
    return locals()


@rtr()
@group_required('Operador de Patrimônio, Coordenador de Patrimônio, Coordenador de Patrimônio Sistêmico')
def baixar_app_conferencia(request):
    caminho_apk = Configuracao.get_valor_por_chave('patrimonio', 'apk_suap_inventario')

    if caminho_apk:
        try:
            apk = default_storage.open(caminho_apk)
            response = HttpResponse(apk.read(), content_type='application/vnd.android.package-archive')
            response['Content-Disposition'] = 'attachment; filename=suap-inventario.apk'
            return response
        except Exception:
            return httprr('.', 'Arquivo de instalação não encontrado.', 'error')

    return httprr('.', 'Aplicativo não cadastrado no sistema.', 'error')


@rtr()
def conferenciasala_item_remover(request, item_id):
    item = get_object_or_404(ConferenciaItem, pk=item_id)
    item.delete()
    return httprr('..', 'Item removido com sucesso')


@rtr()
@group_required('Operador de Patrimônio, Coordenador de Patrimônio, Coordenador de Patrimônio Sistêmico')
def imprimir_conferencia(request, conferencia_id):
    title = 'Detalhes da Conferência'
    conferencia = get_object_or_404(ConferenciaSala, pk=conferencia_id)
    conferencia_total = conferencia.conferenciaitem_set.aggregate(total=Sum('inventario__entrada_permanente__valor'), qtd=Count('inventario'))

    FormClass = RequisicaoTransferenciaColetorFormFactory(request)
    form_requisicao = FormClass(request.POST or None)
    if form_requisicao.is_valid():
        form_requisicao.save()
        return httprr('/admin/patrimonio/requisicao/', 'Requisição criada com sucesso.')
    ids = ConferenciaItem.objects.filter(conferencia=conferencia).values_list('inventario', flat=True)
    inventarios_nao_coletados = Inventario.objects.filter(sala=conferencia.sala).exclude(pk__in=ids)
    return locals()


@rtr()
@group_required('Coordenador de Patrimônio, Coordenador de Patrimônio Sistêmico')
def reavaliar_inventario(request, inventario_id):
    title = 'Reavaliar Inventário'
    inventario = get_object_or_404(Inventario, pk=inventario_id)
    vida_util_anos_do_inventario = inventario.entrada_permanente.categoria.vida_util_em_anos
    percentual_residual_do_inventario = inventario.entrada_permanente.categoria.percentual_residual

    form = ReavaliacaoInventarioForm(request.POST or None, initial={'inventario': inventario})

    if form.is_valid():
        valor_inventario = form.cleaned_data['valor'] + inventario.valor
        InventarioReavaliacao.objects.create(
            percentual_residual=percentual_residual_do_inventario,
            vida_util_em_anos=vida_util_anos_do_inventario,
            inventario_id=inventario.id,
            data=datetime.today(),
            valor=valor_inventario,
            tipo=InventarioReavaliacao.MANUAL_REAVALIACAO,
            motivo=form.cleaned_data['motivo'],
            valor_anterior=Decimal(f'{inventario.valor:.2f}'),
        )
        valor_novo = form.cleaned_data['valor'] + inventario.valor
        inventario.valor = valor_novo
        inventario.save()

        return httprr('..', 'Inventário reavaliado com sucesso.')
    return locals()


@rtr()
@group_required('Coordenador de Patrimônio, Coordenador de Patrimônio Sistêmico')
def ajustar_valor_inventario(request, inventario_id):
    title = 'Ajustar Valor Recuperável Inventário'
    inventario = get_object_or_404(Inventario, pk=inventario_id)
    vida_util_anos_do_inventario = inventario.entrada_permanente.categoria.vida_util_em_anos
    percentual_residual_do_inventario = inventario.entrada_permanente.categoria.percentual_residual

    form = AjusteInventarioForm(request.POST or None, initial={'inventario': inventario})

    if form.is_valid():
        valor_inventario = inventario.valor - form.cleaned_data['valor']
        InventarioReavaliacao.objects.create(
            percentual_residual=percentual_residual_do_inventario,
            vida_util_em_anos=vida_util_anos_do_inventario,
            inventario_id=inventario.id,
            data=datetime.today(),
            valor=valor_inventario,
            tipo=InventarioReavaliacao.MANUAL_AJUSTE_VALOR_RECUPERAVEL,
            motivo=form.cleaned_data['motivo'],
            valor_anterior=inventario.valor,
        )
        inventario.valor = valor_inventario
        inventario.save()

        return httprr('..', 'Ajuste do valor recuperável realizado com sucesso.')
    return locals()


@rtr()
@login_required
def requisitar_transferencia(request):
    title = 'Requisitar Transferência'
    if not request.user.has_perm('patrimonio.change_requisicao'):
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    form = RequisicaoTransferenciaForm(request.POST or None, request=request)
    if form.is_valid():
        form.save()
        return httprr('/admin/patrimonio/requisicao/', 'Requisição de transferência de patrimônio efetuada com sucesso.')
    return locals()


@rtr()
@login_required
def requisicao(request, id_requisicao):
    title = f'Requisição de Transferência #{id_requisicao}'
    dia_inicio_bloqueio = Configuracao.get_valor_por_chave('patrimonio', 'dia_inicio_bloqueio')
    requisicao = get_object_or_404(Requisicao, pk=id_requisicao)

    itens = requisicao.itens.all().order_by('situacao', 'inventario__entrada_permanente__categoria__nome')

    soma_itens = itens.aggregate(total=Sum('inventario__valor'))['total']
    total_itens_requisicao_deferida = itens.aggregate(total=Sum('valor'))['total']

    despesas = (
        itens.values(
            'inventario__entrada_permanente__categoria__codigo',
            'inventario__entrada_permanente__categoria__nome',
            'inventario__entrada_permanente__categoria__plano_contas',
            'inventario__entrada_permanente__categoria__plano_contas__codigo',
        )
        .annotate(
            total_inicial=Sum('inventario__entrada_permanente__valor') or 0,
            total_contabil=Sum('inventario__valor') or 0,
            total_requisicao=Sum('valor') or 0,
        )
        .order_by('inventario__entrada_permanente__categoria__nome')
    )
    total_despesas = despesas.aggregate(
        total_elementos_despesas=Sum('total_inicial') or 0,
        total_despesas_depreciada=Sum('total_contabil') or 0,
        total_despesas_requisicao=Sum('total_requisicao') or 0,
    )
    total_requisicao_acumulada = (total_despesas['total_elementos_despesas'] or 0) - (total_despesas['total_despesas_requisicao'] or 0)
    total_depreciacao_acumulada = (total_despesas['total_elementos_despesas'] or 0) - (total_despesas['total_despesas_depreciada'] or 0)
    elemento_despesa = []

    for ed in despesas:
        plano_contas = None
        if ed['inventario__entrada_permanente__categoria__plano_contas'] is not None:
            plano_contas = ed['inventario__entrada_permanente__categoria__plano_contas__codigo']
        elemento_despesa.append(
            {
                'codigo': ed['inventario__entrada_permanente__categoria__codigo'],
                'plano_contas': plano_contas,
                'nome': ed['inventario__entrada_permanente__categoria__nome'],
                'total_inicial': ed['total_inicial'],
                'total_contabil': ed['total_contabil'],
                'total_requisicao': ed['total_requisicao'] or 0,
                'total_requisicao_acumulada': ed['total_inicial'] - (ed['total_requisicao'] or 0),
                'total_depreciacao_acumulada': ed['total_inicial'] - ed['total_contabil'],
            }
        )

    itens_aprovados = requisicao.itens.filter(situacao=RequisicaoItem.APROVADO).order_by(
        'situacao', 'inventario__entrada_permanente__categoria__nome'
    )

    soma_itens_aprocados = itens_aprovados.aggregate(total=Sum('inventario__valor'))['total']
    total_itens_requisicao_deferida = itens_aprovados.aggregate(total=Sum('valor'))['total']

    despesas_aprovadas = (
        itens_aprovados.values(
            'inventario__entrada_permanente__categoria__codigo',
            'inventario__entrada_permanente__categoria__nome',
            'inventario__entrada_permanente__categoria__plano_contas',
            'inventario__entrada_permanente__categoria__plano_contas__codigo',
        )
        .annotate(
            total_inicial=Sum('inventario__entrada_permanente__valor'),
            total_contabil=Sum('inventario__valor') or 0,
            total_requisicao=Sum('valor') or 0,
        )
        .order_by('inventario__entrada_permanente__categoria__nome')
    )
    total_despesas_aprovada = despesas_aprovadas.aggregate(
        total_elementos_despesas=Sum('total_inicial'),
        total_despesas_depreciada=Sum('total_contabil') or 0,
        total_despesas_requisicao=Sum('total_requisicao') or 0,
    )
    total_requisicao_acumulada_aprovada = (total_despesas_aprovada['total_elementos_despesas'] or 0) - (
        total_despesas_aprovada['total_despesas_requisicao'] or 0
    )
    total_depreciacao_acumulada_aprovada = (total_despesas_aprovada['total_elementos_despesas'] or 0) - (
        total_despesas_aprovada['total_despesas_depreciada'] or 0
    )

    elemento_despesa_aprovada = []

    for ed_aprovada in despesas_aprovadas:
        plano_contas = None
        if ed_aprovada['inventario__entrada_permanente__categoria__plano_contas'] is not None:
            plano_contas = ed_aprovada['inventario__entrada_permanente__categoria__plano_contas__codigo']
        elemento_despesa_aprovada.append(
            {
                'codigo': ed_aprovada['inventario__entrada_permanente__categoria__codigo'],
                'plano_contas': plano_contas,
                'nome': ed_aprovada['inventario__entrada_permanente__categoria__nome'],
                'total_inicial': ed_aprovada['total_inicial'],
                'total_contabil': ed_aprovada['total_contabil'],
                'total_requisicao': ed_aprovada['total_requisicao'] or 0,
                'total_requisicao_acumulada': ed_aprovada['total_inicial'] - (ed_aprovada['total_requisicao'] or 0),
                'total_depreciacao_acumulada': ed_aprovada['total_inicial'] - ed_aprovada['total_contabil'],
            }
        )
    historicorequisicao = RequisicaoHistorico.objects.filter(requisicao=requisicao).order_by('alterado_em')
    form = AvaliarInventariosForm(request.POST or None, instance=requisicao, request=request)
    form.fields['itens'].queryset = itens
    if form.is_valid():
        form.save()
        return httprr('.', 'Inventários avaliados com sucesso. Para prosseguir, você deve Deferir/Indeferir esta requisição.')

    return locals()


@rtr()
@login_required
def cancelar_requisicao(request, requisicao_id):
    requisicao = get_object_or_404(Requisicao, pk=requisicao_id)
    if not requisicao.pode_cancelar():
        raise PermissionDenied

    requisicao.cancelar_requisicao(request.user)
    return httprr('..', 'Requisição cancelada com sucesso.')


@rtr()
@login_required
def indeferir_requisicao(request, requisicao_id):
    title = 'Indeferir Requisição'
    requisicao = get_object_or_404(Requisicao, pk=requisicao_id)
    if not requisicao.pode_avaliar():
        raise PermissionDenied

    form = IndeferirRequisicaoForm(request.POST or None, instance=requisicao, request=request)
    if form.is_valid():
        form.save()
        return httprr('..', 'Requisição indeferida com sucesso.')

    return locals()


@rtr()
@login_required
def deferir_requisicao(request, requisicao_id):
    title = 'Localização dos Itens'
    requisicao = get_object_or_404(Requisicao, pk=requisicao_id)
    dia_inicio_bloqueio = Configuracao.get_valor_por_chave('patrimonio', 'dia_inicio_bloqueio')
    if not requisicao.pode_avaliar():
        return httprr(f'/patrimonio/requisicao/{requisicao_id}', 'Esta requisição não está mais disponível para avaliação.', 'error')
    if date.today().day >= int(dia_inicio_bloqueio) and requisicao.tipo == Requisicao.TIPO_DIFERENTES_CAMPI:
        return httprr(
            f'/patrimonio/requisicao/{requisicao_id}', 'Avaliação indisponível neste período. Disponível novamente no próximo mês.', 'error'
        )

    form = DeferirRequisicaoForm(request.POST or None, instance=requisicao, request=request)
    if form.is_valid():
        return tasks.deferir_requisicao(form.instance, request, form.cleaned_data['sala'])

    return locals()


@rtr()
@login_required
def informar_pa_origem_requisicao(request, requisicao_id):
    title = 'PA campus de origem da Requisição'
    requisicao = get_object_or_404(Requisicao, pk=requisicao_id)
    if not requisicao.pode_informar_pa_origem():
        raise PermissionDenied

    form = InformarPAOrigemForm(request.POST or None, instance=requisicao, request=request)
    if form.is_valid():
        form.save()
        return httprr('..', 'O número da PA foi cadastrado com sucesso.')

    return locals()


@rtr()
@login_required
def editar_pa_origem_requisicao(request, requisicao_id):
    title = 'Editar PA de Campus Origem da Requisição'
    requisicao = get_object_or_404(Requisicao, pk=requisicao_id)
    if not requisicao.pode_editar_pa_origem():
        raise PermissionDenied

    form = EdicaoPAOrigemForm(request.POST or None, requisicao=requisicao, request=request)
    if form.is_valid():
        requisicao.numero_pa_origem = form.cleaned_data['numero_pa_origem']
        requisicao.save()
        return httprr('..', 'O número da PA foi editado com sucesso. Transferência finalizada.')

    return locals()


@rtr()
@login_required
def informar_pa_destino_requisicao(request, requisicao_id):
    title = 'PA campus de destino da Requisição'
    requisicao = get_object_or_404(Requisicao, pk=requisicao_id)
    if not requisicao.pode_informar_pa_destino():
        raise PermissionDenied

    form = InformarPADestinoForm(request.POST or None, instance=requisicao, request=request)
    if form.is_valid():
        form.save()
        return httprr('..', 'O número da PA foi cadastrado com sucesso.')

    return locals()


@rtr()
@login_required
def editar_pa_destino_requisicao(request, requisicao_id):
    title = 'Editar PA de campus destino da Requisição'
    requisicao = get_object_or_404(Requisicao, pk=requisicao_id)
    if not requisicao.pode_editar_pa_destino():
        raise PermissionDenied

    form = EdicaoPADestinoForm(request.POST or None, requisicao=requisicao, request=request)
    if form.is_valid():
        requisicao.numero_pa_destino = form.cleaned_data['numero_pa_destino']
        requisicao.save()
        return httprr('..', 'O número da PA foi editado com sucesso.')

    return locals()


@rtr()
@login_required()
def listar_inventarios_carga_contabil_inconsistentes(request):
    eh_auditor = request.user.groups.filter(name='Auditor').exists()
    pode_alterar = request.user.has_perm('patrimonio.pode_alterar_carga_contabil')
    if not (pode_alterar or eh_auditor):
        raise PermissionDenied
    if request.method == 'POST' and eh_auditor and not pode_alterar:
        raise PermissionDenied
    title = 'Listagem de Inventários com Carga Contábil Diferente do Campus do Responsável'
    FormClass = InconsistenciaFormFactory(request)
    form_inconsistente = FormClass(request.POST or None)
    if form_inconsistente.is_valid():
        form_inconsistente.save()
        return httprr('/admin/patrimonio/requisicao/', 'Requisição criada com sucesso.')
    form_filtro = CampusFiltroInconsistenteForm(request.GET or None)
    inventarios_inconsistentes = Inventario.get_carga_contabil_inconsistentes(request.user)
    inventarios_inconsistentes_campus = Inventario.get_carga_contabil_inconsistentes_campus(request.user)
    ids = list(inventarios_inconsistentes.values_list('id', flat=True))
    inventarios = inventarios_inconsistentes.exclude(
        id__in=Requisicao.get_qs_aguardando().filter(itens__inventario__id__in=ids).values_list('itens__inventario')
    )
    if form_filtro.is_valid():
        if form_filtro.cleaned_data['campus']:
            inventarios = inventarios.filter(responsavel_vinculo__setor__uo=form_filtro.cleaned_data['campus'])
        if form_filtro.cleaned_data['servidor']:
            inventarios = inventarios.filter(responsavel_vinculo=form_filtro.cleaned_data['servidor'].get_vinculo())
    inventarios_pendentes = inventarios_inconsistentes.filter(
        id__in=Requisicao.get_qs_aguardando().filter(itens__inventario__id__in=ids).values_list('itens__inventario')
    )
    return locals()


@rtr()
def historico_movimentacao_inventario(request, inventario_numero):
    inventario = get_object_or_404(Inventario, numero=inventario_numero)
    title = f'Histórico de Movimentações do Inventário {inventario.numero}'

    return locals()


@rtr()
@permission_required('patrimonio.pode_alterar_carga_contabil')
def corrigir_carga_contabil(request, inventario_id):
    inventario = get_object_or_404(Inventario, pk=inventario_id)
    if not Inventario.get_carga_contabil_inconsistentes(request.user).filter(id=inventario_id).exists():
        raise PermissionDenied

    inventario.corrigir_carga_contabil(request.user)
    return httprr('/patrimonio/listar_inventarios_carga_contabil_inconsistentes/', 'Inventário corrigido com sucesso.')


@rtr()
def totalizacao_ed_periodo_planocontas(request):
    title = 'Totalização por Elemento de Despesa por Período de Entrada'
    form = FormTotalizacaoEdPeriodo(request.GET or None)
    if form.is_valid():
        resposta, total = totalizacaoPlanoContasPeriodo(form.cleaned_data['ano'], int(form.cleaned_data['mes']), form.cleaned_data['doacoes'])
        request.session['resposta'] = {
            'resposta': resposta,
            'total': total,
            'ano': form.cleaned_data['ano'],
            'mes': Meses.get_mes(int(form.cleaned_data['mes'])),
            'doacoes_inclusas': form.cleaned_data['doacoes'],
        }
        return render('patrimonio/templates/relatorio/totalizacao_ed_periodoplanocontas.html', request.session['resposta'])
    else:
        return locals()


# View que se conecta a view rh.views.servidor
@receiver(rh_servidor_view_tab)
def servidor_view_tab_signal(sender, request, servidor, verificacao_propria, eh_chefe, **kwargs):
    inventarios = Inventario.objects.filter(responsavel_vinculo=servidor.get_vinculo())

    if inventarios.exists():
        return render_to_string(
            template_name='patrimonio/templates/servidor_view_tab.html',
            context={
                'lps_context': {'nome_modulo': 'patrimonio'},
                'servidor': servidor,
                'inventarios': inventarios,
                'verificacao_propria': verificacao_propria,
            },
            request=request,
        )
    return False


@permission_required('patrimonio.change_requisicao')
@csrf_exempt
def filtra_inventario_transferencia(request):
    data = []

    def get_ext_combo_template(obj):
        data = obj.descricao
        data = (data[:75] + '..') if len(data) > 75 else data
        return f'{obj.numero} - {data}'

    if request.method == 'POST':
        filter_pks = json.loads(request.POST.get('filter_pks', ''))
        if filter_pks and filter_pks['servidor_origem']:
            servidor_obj = Servidor.objects.get(id=filter_pks['servidor_origem'])
            lista_resultado = Inventario.ativos.filter(responsavel_vinculo=servidor_obj.get_vinculo()).exclude(
                requisicaoitem__requisicao__status=Requisicao.STATUS_AGUARDANDO_APROVACAO_SERVIDOR_DESTINO
            )
        else:
            lista_resultado = Inventario.ativos.exclude(requisicaoitem__requisicao__status=Requisicao.STATUS_AGUARDANDO_APROVACAO_SERVIDOR_DESTINO)

        if request.POST.get('q'):
            lista_resultado = lista_resultado.filter(campo_busca__icontains=request.POST.get('q'))
        data = generate_autocomplete_dict(lista_resultado, int(request.POST.get('page', 1)), ext_combo_template_text=get_ext_combo_template)
    return HttpResponse(json.dumps(data), content_type='application/json')


@rtr()
@login_required()
def atualizar_carga_contabil(request, requisicao_id):
    requisicao = get_object_or_404(Requisicao, pk=requisicao_id)
    itens = requisicao.itens.all()
    for i in itens:
        cc = InventarioCargaContabil.objects.filter(inventario=i.inventario).order_by('-id')[0]
        if cc.campus != i.inventario.carga_contabil.campus:
            i.inventario.carga_contabil = cc
            i.inventario.save()

    return httprr('..', 'Cargas Contábeis atualizadas com sucesso.')


@rtr()
@group_required('Operador de Patrimônio, Coordenador de Patrimônio, Coordenador de Patrimônio Sistêmico, Auditor')
def inventarios_nao_conferidos(request):
    title = 'Inventários não conferidos'

    def consultar_inventarios(cleaned_data):
        campus = cleaned_data.get('campus')
        data_inicial = cleaned_data.get('data_inicial')
        data_final = cleaned_data.get('data_final')

        qs_conferencias = ConferenciaItem.objects.only('dh_coleta', 'inventario_id')
        if data_inicial:
            qs_conferencias = qs_conferencias.filter(dh_coleta__date__gte=data_inicial)
        if data_final:
            qs_conferencias = qs_conferencias.filter(dh_coleta__date__lte=data_final)
        ids_inventarios_conferidos = qs_conferencias.values_list('inventario_id', flat=True).distinct()

        inventarios = Inventario.depreciaveis.exclude(pk__in=ids_inventarios_conferidos)
        if campus:
            inventarios = inventarios.filter(sala__predio__uo=campus)
        return inventarios

    form = FiltroInventariosNaoConferidosForm(request.POST or request.GET or None)
    if form.is_valid():
        inventarios = consultar_inventarios(form.cleaned_data)
        resultados_por_pagina = form.cleaned_data.get('resultados_por_pagina') or 50

        url_base = request.path + '?' + request.GET.urlencode()
        url_csv = url_base + '&format=csv'
        url_xls = url_base + '&format=xls'
        if request.method == 'GET':
            formato = request.GET.get('format')
            if formato in ['xls', 'csv']:
                return tasks.inventario_dados_exportacao(inventarios, formato)

        params = request.GET.dict()
        if 'order_by' in params:
            order_params = params.pop('order_by', '').split('-')
            order_str = order_params[0]
            order_sign = ''
            if len(order_params) > 1:
                order_str = order_params[1]
                order_sign = '-'

            if order_str == 'numero':
                inventarios = inventarios.order_by(f'{order_sign}numero')
            if order_str == 'descricao':
                inventarios = inventarios.order_by(f'{order_sign}descricao')
            if order_str == 'sala':
                inventarios = inventarios.order_by(f'{order_sign}sala__nome')
            if order_str == 'responsavel':
                inventarios = inventarios.order_by(f'{order_sign}responsavel_vinculo__pessoa__nome')

        params = urllib.parse.urlencode(params)

    return locals()


TEMPLATE_CONFERENCIA = 'patrimonio/templates/migracao_conferencia.html'
"""Trecho da tela com o resultado da conferência, devolvido isolado na chamada assíncrona."""


def despachar_migracao(request, arquivo, conferencia, processo):
    """
    Manda para segundo plano a planilha que o usuário acabou de confirmar.

    A reconferência é o que garante que o gravado é o que foi conferido; a tela não é a dona dessa
    garantia.
    """
    if not conferencia.valida:
        return httprr('.', 'A planilha tem erros e não pode ser importada. Confira o arquivo e envie de novo.', 'error')
    arquivo.seek(0)
    return tasks.migrar_inventarios(arquivo.read(), arquivo.name, processo)


@rtr()
@permission_required('patrimonio.pode_migrar_inventario')
def migracao(request):
    """
    Importa um acervo de inventários a partir de planilha, em dois passos na mesma tela.

    Os passos são do usuário, não do servidor: conferir devolve só o resultado, sem gravar nada nem
    recarregar a página, e a planilha fica no navegador, presa ao campo de arquivo; confirmar
    reenvia o mesmo formulário. É o que permite não guardar a planilha em disco, storage ou sessão.
    """
    title = 'Migrar Inventários'
    colunas = migrador.COLUNAS

    form = MigracaoInventarioForm(request.POST or None, request.FILES or None)
    conferencia = None
    erro_de_leitura = None

    if form.is_valid():
        arquivo = form.cleaned_data['arquivo']
        try:
            conferencia = migrador.conferir(arquivo)
        except ValidationError as erro:
            erro_de_leitura = ' '.join(erro.messages)
        else:
            if request.POST.get('confirmar'):
                return despachar_migracao(request, arquivo, conferencia, form.cleaned_data['processo'])

    if is_ajax(request):
        return render(TEMPLATE_CONFERENCIA, locals(), request)
    if erro_de_leitura:
        return httprr('.', erro_de_leitura, 'error')

    return locals()


@permission_required('patrimonio.pode_migrar_inventario')
def migracao_modelo(request):
    """Baixa a planilha modelo, com uma aba de exemplo e outra explicando cada coluna."""
    resposta = HttpResponse(
        migrador.gerar_planilha_modelo(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    resposta['Content-Disposition'] = 'attachment; filename="modelo-migracao-inventarios.xlsx"'
    return resposta
