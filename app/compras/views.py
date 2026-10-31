from datetime import date, datetime

import pandas as pd
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Exists, OuterRef, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.defaultfilters import pluralize
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.views.decorators.csrf import csrf_exempt

from compras.forms import (
    AdicionarComentarioForm,
    AtualizarEtapaAtualForm,
    CalendarioForm,
    CalendarioProcessoCompraForm,
    FaseForm,
    ProcessoCompraCampusMaterialFormFactory,
    ProcessoCompraFormFactory,
)
from compras.models import (
    Calendario,
    CategoriaCompra,
    ComentarioEtapaCompra,
    Compra,
    EtapaCompra,
    EtapasProcessoCompra,
    Evento,
    Fase,
    Nucleo,
    Processo,
    ProcessoCompra,
    ProcessoCompraCampus,
    ProcessoCompraCampusMaterial,
    SolicitacaoParticipacao,
    TipoCalendario,
)
from comum.models import Ano
from comum.utils import get_uo
from djtools import layout
from djtools.html.calendarios import Calendario as Cal
from djtools.utils import JsonResponse, XlsResponse, group_required, httprr, permission_required, rtr, transaction
from materiais.models import Material, MaterialCotacao
from rh.models import UnidadeOrganizacional


@layout.quadro('Gestão de Processos de Compras', icone='cart-shopping', pode_esconder=True)
def index_quadros_processos_compras(quadro, request):
    eh_gerente_de_compras = request.user.has_group_cached('Gerenciador de Compras')
    request.user.has_group_cached('Gerenciador de Compras')
    if eh_gerente_de_compras:
        qtd_compras_sistemico = Compra.objects.filter(tipo_calendario=TipoCalendario.SISTEMICO, data_conclusao__isnull=True)
        if qtd_compras_sistemico.exists():
            qtd = qtd_compras_sistemico.count()
            quadro.add_item(
                layout.ItemContador(
                    titulo=f'Compr{pluralize(qtd, "a,as")} Sistêmic{pluralize(qtd, "a,as")}',
                    subtitulo='',
                    qtd=qtd,
                    url='/admin/compras/compra/?tipo_calendario__exact=sistemico&concluido__exact=0',
                )
            )

        qtd_compras_nucleo = Compra.objects.filter(tipo_calendario=TipoCalendario.NUCLEO_COMPRAS, data_conclusao__isnull=True)
        nucleo_do_servidor_logado = Nucleo.objects.filter(componentes__id=request.user.get_relacionamento().id).first()
        if nucleo_do_servidor_logado and qtd_compras_nucleo.exists():
            qtd = qtd_compras_nucleo.count()
            quadro.add_item(
                layout.ItemContador(
                    titulo=f'Compr{pluralize(qtd, "a,as")} do Meu Núcleo',
                    subtitulo='',
                    qtd=qtd,
                    url=f'/admin/compras/compra/?tipo_calendario__exact=nucleo_compras&nucleo_responsavel={nucleo_do_servidor_logado.id}&concluido__exact=0',
                )
            )

        if request.user.get_vinculo().eh_servidor():
            campus_id_usuario = request.user.get_relacionamento().setor.uo.id
            qtd_compras_campus = Compra.objects.filter(
                tipo_calendario=TipoCalendario.CAMPUS, campus_responsavel__id=campus_id_usuario, data_conclusao__isnull=True
            )
            if qtd_compras_campus.exists():
                qtd = qtd_compras_campus.count()
                quadro.add_item(
                    layout.ItemContador(
                        titulo=f'Compr{pluralize(qtd, "a,as")} do Meu Campus',
                        subtitulo='',
                        qtd=qtd,
                        url=f'/admin/compras/compra/?tipo_calendario__exact=campus&campus_responsavel={campus_id_usuario}&concluido__exact=0',
                    )
                )

    return quadro


@layout.info()
def index_infos(request):
    infos = []

    if request.user.has_group_cached('Gerenciador de Compras'):
        for processos in (
            ProcessoCompra.get_no_periodo_para_mim().only('pk', 'descricao').order_by('data_inicio', 'data_fim', 'processocompracampus__campus')
        ):
            infos.append({'url': f'/compras/processo_compra/{processos.pk}', 'titulo': f'Processo de compra: {processos.descricao}.'})

    return infos


@layout.atribuidos_a_meus_grupos()
def index_atribuidos_a_meus_grupos(request):
    pendencias = []

    if request.user.has_perm('compras.view_processocompra'):
        solicitacao = SolicitacaoParticipacao.objects.filter(fase_id=OuterRef('id'), campus_solicitante=get_uo(request.user))
        for fase in (
            Fase.objects.annotate(has_solicitacao=Exists(solicitacao))
            .filter(fase_inicial=True, has_solicitacao=True)
            .order_by('fase_inicial')
            .only('descricao', 'processo__tipo_processo__descricao')
        ):
            pendencias.append(
                {
                    'url': f'/compras/solicitar_participacao/{fase.id}/',
                    'titulo': f'A fase <strong>{fase.descricao}</strong> do processo <strong>{fase.processo.tipo_processo.descricao}</strong> está aberta e você pode <strong>solicitar a participação do seu campus</strong>.',
                }
            )

    return pendencias


@permission_required('compras.add_processocompracampusmaterial')
@rtr()
def processo_compra(request, pk):
    obj = ProcessoCompra.objects.get(pk=pk)
    materiais_ids = set(
        ProcessoCompraCampusMaterial.objects.filter(processo_compra_campus__processo_compra=pk)
        .values_list('material', flat=True)
        .order_by('material')
    )
    cotacoes_anexos = MaterialCotacao.objects.filter(material__in=materiais_ids, arquivo__isnull=False).exclude(arquivo='').exists()
    return locals()


@login_required
@rtr()
def cronograma_compra(request, pk):
    obj = Compra.objects.get(pk=pk)
    title = 'Cronograma do processo de compra'
    if obj.processo:
        title = f'Cronograma do processo: {obj.processo.numero_protocolo_fisico}'
    pode_registrar_conclusao = obj.pode_registrar_conclusao(request.user)
    etapas_ = EtapaCompra.objects.filter(compra_id=pk).order_by('data_inicio')
    etapas = []
    for etapa in etapas_:
        descricao_etapa = EtapasProcessoCompra.get_display(etapa.etapa)
        etapas.append(
            {
                'etapa': descricao_etapa,
                'id': etapa.id,
                'data_inicio': etapa.data_inicio,
                'data_fim': etapa.data_fim,
                'executada': etapa.executada,
                'ultimo_comentario': etapa.comentarios.order_by('id').last().comentario if etapa.comentarios.exists() else None,
                'fase_etapa': 'Interna' if EtapasProcessoCompra.is_fase_interna(etapa.etapa) else 'Externa',
                'qtd_comentarios': ComentarioEtapaCompra.objects.filter(etapa_compra__id=etapa.id).count(),
            }
        )
    return locals()


@group_required('Gerenciador de Compras')
@rtr()
def atualizar_etapa_atual(request, pk):
    obj = Compra.objects.get(pk=pk)
    title = 'Atualizar Etapa Atual'
    form = AtualizarEtapaAtualForm(request.POST or None, instance=obj)
    if form.is_valid():
        form.save()
        return httprr('/admin/compras/compra/', 'Etapa atual atualizada com sucesso.')
    return locals()


@permission_required('compras.pode_gerenciar_processocompra')
def processo_compra_validar(request, pk):
    obj = ProcessoCompra.objects.get(pk=pk)
    if not obj.pode_validar(request.user):
        raise PermissionDenied
    obj.validar(request.user)
    return httprr(f'/compras/processo_compra/{pk}/', 'Processo validado com sucesso.')


@permission_required('compras.pode_gerenciar_processocompra')
def processo_compra_relatorio_ug(request, pk):
    pcompra = ProcessoCompra.objects.get(pk=pk)
    consulta = (
        ProcessoCompraCampusMaterial.objects.filter(processo_compra_campus__in=pcompra.processocompracampus_set.all())
        .values(
            'processo_compra_campus__processo_compra__tags__descricao',
            'processo_compra_campus__campus__codigo_ug',
            'material__id',
            'material__codigo_catmat',
            'material__especificacao',
            'material__unidade_medida__descricao',
            'valor_unitario',
        )
        .annotate(soma_qtd=Sum('qtd'), soma_valor_total=Sum('valor_total'))
        .order_by('processo_compra_campus__processo_compra__tags__descricao', 'processo_compra_campus__campus__codigo_ug', 'material__id')
    )
    rows = [['Tag', 'UG', 'Material ID', 'CATMAT', 'Material Especificação', 'Unidade medida', 'Qtd.', 'Valor Unit.', 'Valor Total']]
    for row in consulta:
        rows.append(
            [
                row['processo_compra_campus__processo_compra__tags__descricao'],
                row['processo_compra_campus__campus__codigo_ug'],
                row['material__id'],
                row['material__codigo_catmat'],
                row['material__especificacao'],
                row['material__unidade_medida__descricao'],
                row['soma_qtd'],
                row['valor_unitario'],
                row['soma_valor_total'],
            ]
        )
    #
    return XlsResponse(rows=rows, convert_to_ascii=True)


@permission_required('compras.pode_gerenciar_processocompra')
def processo_compra_relatorio_campus(request, pk):
    pcompra = ProcessoCompra.objects.get(pk=pk)
    consulta = (
        ProcessoCompraCampusMaterial.objects.filter(processo_compra_campus__in=pcompra.processocompracampus_set.all())
        .values(
            'processo_compra_campus__processo_compra__tags__descricao',
            'processo_compra_campus__campus__setor__sigla',
            'material__id',
            'material__especificacao',
            'material__unidade_medida__descricao',
            'valor_unitario',
        )
        .annotate(soma_qtd=Sum('qtd'), soma_valor_total=Sum('valor_total'))
        .order_by('processo_compra_campus__processo_compra__tags__descricao', 'processo_compra_campus__campus__setor__sigla', 'material__id')
    )
    if consulta:
        relatorio = {}
        materiais = {}
        campus = []

        for r in consulta:
            if r['material__id'] not in materiais:
                materiais[r['material__id']] = r['material__especificacao']
        for registro in consulta:
            if registro['material__id'] not in relatorio:
                relatorio[registro['material__id']] = {}

            if registro['processo_compra_campus__campus__setor__sigla'] not in campus:
                campus.append(registro['processo_compra_campus__campus__setor__sigla'])

            if registro['processo_compra_campus__campus__setor__sigla'] not in relatorio[registro['material__id']]:
                relatorio[registro['material__id']][registro['processo_compra_campus__campus__setor__sigla']] = registro['soma_qtd']
            else:
                relatorio[registro['material__id']][registro['processo_compra_campus__campus__setor__sigla']] += registro['soma_qtd']
        #
        rows = []
        rows.append(['ID', 'Catmat', 'Material', *campus])
        for material, mat_campus in list(relatorio.items()):
            row = []
            row.append(material)
            mat = Material.objects.get(id=material)
            row.append(mat.codigo_catmat)
            row.append(materiais[material])
            for c in campus:
                if c in mat_campus:
                    row.append(mat_campus[c])
                else:
                    row.append('0')
            rows.append(row)
    return XlsResponse(rows=rows, convert_to_ascii=True)


@permission_required('compras.pode_gerenciar_processocompra')
def processo_compra_relatorio_geral(request, pk):
    pcompra = ProcessoCompra.objects.get(pk=pk)
    consulta = (
        ProcessoCompraCampusMaterial.objects.filter(processo_compra_campus__in=pcompra.processocompracampus_set.all())
        .values(
            'processo_compra_campus__processo_compra__tags__descricao',
            'material__id',
            'material__especificacao',
            'material__unidade_medida__descricao',
            'valor_unitario',
        )
        .annotate(soma_qtd=Sum('qtd'), soma_valor_total=Sum('valor_total'))
        .order_by('processo_compra_campus__processo_compra__tags__descricao', 'material__id')
    )
    # verifica se existem dados retornados
    rows = [['Tag', 'Material ID', 'Material Especificação', 'Material Descrição', 'Unidade medida', 'Qtd.', 'Valor Unit.', 'Valor Total']]
    for row in consulta:
        rows.append(
            [
                row['processo_compra_campus__processo_compra__tags__descricao'],
                row['material__id'],
                row['material__especificacao'],
                Material.objects.get(id=row['material__id']).descricao,
                row['material__unidade_medida__descricao'],
                row['soma_qtd'],
                row['valor_unitario'],
                row['soma_valor_total'],
            ]
        )
    return XlsResponse(rows=rows, convert_to_ascii=True)


@rtr()
@permission_required('compras.add_processocompracampusmaterial')
def relatorio_processo_compra_campus(request, pk):
    pcompra = ProcessoCompraCampus.objects.get(pk=pk)
    consulta = (
        ProcessoCompraCampusMaterial.objects.filter(processo_compra_campus=pcompra)
        .values(
            'processo_compra_campus__processo_compra__tags__descricao',
            'material__id',
            'material__especificacao',
            'material__unidade_medida__descricao',
            'valor_unitario',
        )
        .annotate(soma_qtd=Sum('qtd'), soma_valor_total=Sum('valor_total'))
        .order_by('processo_compra_campus__processo_compra__tags__descricao', 'material__id')
    )
    # verifica se existem dados retornados
    rows = [['Tag', 'Material ID', 'Material Especificação', 'Material Descrição', 'Unidade medida', 'Qtd.', 'Valor Unit.', 'Valor Total']]
    for row in consulta:
        rows.append(
            [
                row['processo_compra_campus__processo_compra__tags__descricao'],
                row['material__id'],
                row['material__especificacao'],
                Material.objects.get(id=row['material__id']).descricao,
                row['material__unidade_medida__descricao'],
                row['soma_qtd'],
                row['valor_unitario'],
                row['soma_valor_total'],
            ]
        )
    return XlsResponse(rows=rows, convert_to_ascii=True)


@permission_required('compras.pode_gerenciar_processocompra')
def processo_compra_relatorio_cotacao(request, pk):
    processo_compra = get_object_or_404(ProcessoCompra, pk=pk)

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=processo_compra.xlsx'

    header = ['Tag', 'Material ID', 'Valor da Cotação', 'Data', 'Site', 'UASG', 'Número Pregão', 'Número Item', 'Data Validade']
    data = []
    merge_info = []

    p_materiais = processo_compra.processocompramaterial_set.all().distinct()

    current_row = 2  # 1-based index, starting after header

    for p_material in p_materiais:
        material = p_material.material
        cotacoes = processo_compra.processomaterialcotacao_set.filter(material=material).values_list('cotacao__id', flat=True).distinct()
        cotacoes = MaterialCotacao.objects.filter(pk__in=cotacoes)
        n_cotacoes = cotacoes.count()

        tags_str = ', '.join(processo_compra.tags.all().values_list('descricao', flat=True))

        if n_cotacoes > 0:
            if n_cotacoes > 1:
                merge_info.append((current_row, current_row + n_cotacoes - 1, 1, 1))  # Tag
                merge_info.append((current_row, current_row + n_cotacoes - 1, 2, 2))  # Material ID

            for cotacao in cotacoes:
                row = {
                    'Tag': tags_str,
                    'Material ID': material.id,
                    'Valor da Cotação': cotacao.valor,
                    'Data': cotacao.data.strftime('%d/%m/%Y'),
                    'Site': cotacao.site,
                    'UASG': cotacao.uasg,
                    'Número Pregão': cotacao.numero_pregao,
                    'Número Item': cotacao.numero_item,
                    'Data Validade': cotacao.data_validade.strftime('%d/%m/%Y') if cotacao.data_validade else '-',
                }
                data.append(row)
                current_row += 1
        else:
            # Handle case with no cotacoes if necessary, though original loop implies there are cotacoes or it skips?
            # Original code iterates cotacoes. If empty, it does nothing for this material?
            # "sheet.write_merge(linha, linha + n_cotacoes - 1..."
            # If n_cotacoes is 0, range is invalid. Assuming there's at least one or logic handles it.
            # Actually if n_cotacoes is 0, the inner loop doesn't run, but the write_merge might be problematic in original code if n_cotacoes is 0.
            # But let's assume we only add rows if there are cotacoes.
            pass

    df = pd.DataFrame(data, columns=header)

    with pd.ExcelWriter(response, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Cotacao', index=False)
        worksheet = writer.sheets['Cotacao']

        for start_row, end_row, start_col, end_col in merge_info:
            worksheet.merge_cells(start_row=start_row, start_column=start_col, end_row=end_row, end_column=end_col)
            # Center align merged cells
            # from openpyxl.styles import Alignment
            # cell = worksheet.cell(row=start_row, column=start_col)
            # cell.alignment = Alignment(horizontal='center', vertical='center')

    return response


@permission_required('compras.add_processocompracampusmaterial')
@rtr()
def processo_compra_campus(request, pk):
    obj = ProcessoCompraCampus.objects.get(pk=pk)

    itens = obj.get_itens()

    # tem filtro?
    if request.method == 'GET' and 'q' in request.GET and request.GET['q']:
        query = request.GET['q']

        # filtra campos não inteiros
        itens = obj.get_itens().filter(Q(material__descricao__unaccent__icontains=query) | Q(material__especificacao__icontains=query))

        # tem campo inteiro?
        if query.isdigit():
            # filtra o campo inteiro e concatena com o queryset anterior
            itens = itens | obj.get_itens().filter(Q(material__id=query) | Q(material__codigo_catmat=query))

            # remove duplicidades
        itens = itens.distinct()

    if obj.estah_no_periodo():
        FormClass = ProcessoCompraCampusMaterialFormFactory(obj)
        form = FormClass(request.POST or None, initial={'processo_compra_campus': pk})
        if form.is_valid():
            form.save()
            return httprr('.', 'Item adicionado com sucesso.')
    return locals()


@rtr()
def processo_compra_campus_validar(request, pk):
    obj = ProcessoCompraCampus.objects.get(pk=pk)
    if not obj.pode_validar(request.user):
        raise PermissionDenied
    obj.validar(request.user)
    return httprr(f'/compras/processo_compra_campus/{pk}/', 'Processo validado com sucesso.')


@rtr()
@permission_required('compras.change_processocompra')
def processo_compra_editar(request, pk):
    title = 'Editar Processo de Compra'
    processo_compra = ProcessoCompra.objects.get(id=pk)
    FormClass = ProcessoCompraFormFactory(instance=processo_compra)
    if request.method == 'POST':
        form = FormClass(request.POST)
        if form.is_valid():
            processo_compra.descricao = form.cleaned_data['descricao']
            processo_compra.observacao = form.cleaned_data['observacao']
            processo_compra.data_inicio = form.cleaned_data['data_inicio']
            processo_compra.data_fim = form.cleaned_data['data_fim']
            if form.cleaned_data['update_data'] is True:
                processo_compra.processocompracampus_set.update(data_inicio=processo_compra.data_inicio)
                processo_compra.processocompracampus_set.update(data_fim=processo_compra.data_fim)
            processo_compra.save()
            return httprr('.', 'Processo Compra editada com sucesso')
    else:
        form = FormClass()
    return locals()


@permission_required('compras.pode_gerenciar_processocompra')
def preencher_materiais_ausentes_campus(request, pk):
    processo_compra_campus = ProcessoCompraCampus.objects.get(id=pk)

    # "Processo Compra Campus" deve ter sido VALIDADO, ao contrário de "Processo Compra"
    if (processo_compra_campus.status == ProcessoCompraCampus.STATUS_VALIDADO) and (
        processo_compra_campus.processo_compra.status == ProcessoCompra.STATUS_AGUARDANDO_VALIDACAO
    ):
        processo_compra_campus.preencher_materiais_ausentes(request.user)
        return httprr(f'/compras/processo_compra_campus/{pk}', 'Preenchimento de materiais ausentes efetuado com sucesso.')
    else:
        raise PermissionDenied('Operação não permitida.')


@rtr()
def detalhar_anexos(request, pk):
    title = 'Cotações com Anexos'
    materiais_ids = set(
        ProcessoCompraCampusMaterial.objects.filter(processo_compra_campus__processo_compra=pk)
        .values_list('material', flat=True)
        .order_by('material')
    )
    cotacao = MaterialCotacao.objects.filter(material__in=materiais_ids, arquivo__isnull=False).exclude(arquivo='')
    return locals()


@rtr()
@permission_required('compras.view_fase')
def calendarios_referencia(request):
    title = 'Calendários de Compras e Aquisições'
    ano = Ano.objects.filter(ano=date.today().year).first()
    eventos = Evento.objects.filter(ativo=True)
    calendarios = Calendario.objects.filter(ativo=True)
    form = CalendarioForm(request.POST or None)
    if form.is_valid():
        if form.cleaned_data.get('ano'):
            ano = form.cleaned_data['ano']
            data_ini = date(ano.ano, 1, 1)
            data_fim = date(ano.ano, 12, 31)
            eventos = eventos.filter(data_inicio__lte=data_fim, data_fim__gte=data_ini)
            calendarios = calendarios.filter(id__in=eventos.values_list('tipo_evento__calendario__id', flat=True))
        if form.cleaned_data.get('calendario'):
            calendario = form.cleaned_data['calendario']
            eventos = eventos.filter(tipo_evento__calendario=calendario)
            calendarios = calendarios.filter(id=calendario.id)

    lista_calendarios = []
    for registro in calendarios:
        calendario = Cal()
        for evento in eventos.filter(tipo_evento__calendario=registro):
            calendario.adicionar_evento_calendario(
                evento.data_inicio, evento.data_fim, evento.tipo_evento.descricao, evento.tipo_evento.cor, evento.tipo_evento.descricao
            )

        calendario_ano = calendario.formato_ano_calendario_compras(ano.ano)
        lista_calendarios.append([registro.descricao, calendario_ano])

    return locals()


@rtr()
@csrf_exempt
@login_required
@group_required('Gerenciador de Compras, Servidor')
def calendarios_processos_compras(request):
    title = 'Calendários de Compras e Aquisições'
    ano = Ano.objects.filter(ano=date.today().year).first()
    etapas = EtapaCompra.objects.all()
    initial = {'ano': ano, 'tipo_calendario': TipoCalendario.CAMPUS, 'campus_responsavel': request.user.get_relacionamento().setor.uo}
    form = CalendarioProcessoCompraForm(request.GET or None, user=request.user, initial=initial)
    if form.is_valid():
        if form.cleaned_data.get('ano'):
            ano = form.cleaned_data['ano']
            data_ini = date(ano.ano, 1, 1)
            data_fim = date(ano.ano, 12, 31)
            etapas = etapas.filter(data_inicio__lte=data_fim, data_fim__gte=data_ini)

        if form.cleaned_data.get('tipo_calendario'):
            tipo_calendario = form.cleaned_data['tipo_calendario']
            etapas = etapas.filter(compra__tipo_calendario=tipo_calendario)

        if form.cleaned_data.get('tipo_compra'):
            tipo_compra = form.cleaned_data['tipo_compra']
            etapas = etapas.filter(compra__tipo_compra=tipo_compra)

        if form.cleaned_data.get('etapa_atual'):
            etapa_atual = form.cleaned_data['etapa_atual']
            etapas = etapas.filter(compra__etapa_atual=etapa_atual, etapa=etapa_atual)

        if form.cleaned_data.get('categoria'):
            categoria = form.cleaned_data['categoria']
            etapas = etapas.filter(compra__categoria__descricao=categoria, compra__categoria__ativo=True)

        if form.cleaned_data.get('nucleo_responsavel'):
            nucleo_responsavel = form.cleaned_data['nucleo_responsavel']
            etapas = etapas.filter(compra__nucleo_responsavel=nucleo_responsavel)

        if form.cleaned_data.get('campus_responsavel'):
            campus_responsavel = form.cleaned_data['campus_responsavel']
            etapas = etapas.filter(compra__campus_responsavel=campus_responsavel)

        if form.cleaned_data.get('processo'):
            processo = form.cleaned_data['processo']
            etapas = etapas.filter(compra__processo=processo)
    else:
        etapas = etapas.filter(compra__tipo_calendario=TipoCalendario.CAMPUS, compra__campus_responsavel=request.user.get_relacionamento().setor.uo)
    lista_calendarios = []
    calendarios = list(etapas.values_list('compra__tipo_calendario', flat=True).distinct())
    for registro in calendarios:
        calendario = Cal()
        calendario.escape_html = False
        for etapa in etapas.filter(compra__tipo_calendario=registro):
            etapa_label = f'{EtapasProcessoCompra.get_display(etapa.etapa)}'
            if etapa.compra.processo:
                link_processo_etapa = mark_safe(
                    f'<a class="popup" href="/processo_eletronico/processo/{etapa.compra.processo.pk}/" alt=f"Assunto: {etapa.compra.processo.assunto}">{etapa.compra.processo.numero_protocolo_fisico}</a>'
                )

                etapa_label = f'{EtapasProcessoCompra.get_display(etapa.etapa)} - Processo: {link_processo_etapa}'
            cor = etapa.compra.categoria.cor if etapa.compra.categoria else 'compras'
            calendario.adicionar_evento_calendario(etapa.data_inicio, etapa.data_fim, etapa_label, cor, etapa.etapa)
        titulo = f'{TipoCalendario.get_display(registro)} / {ano}'
        subtitulo = ''
        calendario_ano = calendario.formato_ano_calendario_compras(ano.ano)
        lista_calendarios.append([registro, calendario_ano, titulo, subtitulo])
        categorias = CategoriaCompra.objects.filter(ativo=True)

    return locals()


@rtr()
@permission_required('compras.add_fase')
def adicionar_fase(request, pk):
    processo = get_object_or_404(Processo, pk=pk)
    if request.user.get_relacionamento() not in processo.tipo_processo.nucleo_responsavel.componentes.all() and not request.user.has_perm(
        'compras.add_calendario'
    ):
        raise PermissionDenied
    title = f'Adicionar Fase - {processo}'
    form = FaseForm(request.POST or None)
    if form.is_valid():
        o = form.save(False)
        o.processo = processo
        o.save()
        return httprr('/admin/compras/processo/', 'Fase cadastrada com sucesso.')
    return locals()


@rtr()
@permission_required('compras.view_processocompra')
def solicitar_participacao(request, pk):
    fase = get_object_or_404(Fase, pk=pk)
    if fase.fase_inicial:
        title = 'Solicitar Participação'
        if request.POST:
            o = SolicitacaoParticipacao()
            o.fase = fase
            o.solicitada_em = datetime.now()
            o.solicitada_por = request.user.get_relacionamento()
            o.campus_solicitante = get_uo(request.user)
            o.save()
            return httprr('/', 'Solicitação de participação cadastrada com sucesso.')

        return locals()
    else:
        raise PermissionDenied


def registrar_conclusao_processo_compra(request, pk):
    compra = get_object_or_404(Compra, pk=pk)
    if not compra.pode_registrar_conclusao(request.user):
        raise PermissionDenied
    compra.registrar_conclusao(request.user)
    return httprr(f'/compras/compra/{pk}/cronograma/', 'Conclusão registrada com sucesso.')


def retornar_cronograma_processo_compra(request, pk):
    compra = get_object_or_404(Compra, pk=pk)
    if not compra.pode_retornar_cronograma(request.user):
        raise PermissionDenied
    compra.concluido = False
    compra.save()
    return httprr(f'/compras/compra/{pk}/cronograma/', 'Cronograma retornado com sucesso.')


@login_required()
def gerenciar_execucao_etapa(request, pk_etapacompra):
    etapa = get_object_or_404(EtapaCompra, pk=pk_etapacompra)
    if not etapa.pode_registrar_execucao(request.user):
        raise PermissionDenied
    if etapa.executada:
        etapa.executada = False
        etapa.save()
        return httprr(f'/compras/compra/{etapa.compra.pk}/cronograma/', 'Registro desmarcado com sucesso.')
    else:
        etapa.executada = True
        etapa.save()
        return httprr(f'/compras/compra/{etapa.compra.pk}/cronograma/', 'Execução registrada com sucesso.')


@rtr()
@login_required()
def gerenciar_comentarios_etapa(request, pk_etapacompra):
    etapacompra = get_object_or_404(EtapaCompra, pk=pk_etapacompra)
    title = f'Comentários da etapa: {EtapasProcessoCompra.get_display(etapacompra.etapa)}'
    comentarios = ComentarioEtapaCompra.objects.filter(etapa_compra=etapacompra)
    return locals()


@rtr()
@login_required()
def adicionar_comentario_etapa(request, pk_etapacompra):
    etapacompra = get_object_or_404(EtapaCompra, pk=pk_etapacompra)
    title = f'Comentários da etapa: {EtapasProcessoCompra.get_display(etapacompra.etapa)}'
    if not etapacompra.pode_registrar_execucao(request.user):
        raise PermissionDenied
    comentario = ComentarioEtapaCompra(etapa_compra=etapacompra, vinculo=request.user.get_vinculo())
    form = AdicionarComentarioForm(request.POST or None, request=request, instance=comentario)
    if form.is_valid():
        form.save()
        return httprr(reverse('cronograma_compra', args=[etapacompra.compra.id]), 'Comentário adicionado com sucesso.', close_popup=True)

    return locals()


@rtr()
@login_required()
def excluir_comentario_etapa(request, pk_comentario, somente_desconsiderar=False):
    comentario = get_object_or_404(ComentarioEtapaCompra, pk=pk_comentario)
    etapacompra = get_object_or_404(EtapaCompra, pk=comentario.etapa_compra.id)

    if not etapacompra.pode_registrar_execucao(request.user):
        raise PermissionDenied

    with transaction.atomic():
        if somente_desconsiderar:
            comentario.desconsiderado_em = datetime.now()
            comentario.save()
            return httprr(reverse('cronograma_compra', args=[etapacompra.compra.id]), 'Comentário desconsiderado com sucesso.', close_popup=True)
        else:
            comentario.delete()
            return httprr(reverse('cronograma_compra', args=[etapacompra.compra.id]), 'Comentário excluído com sucesso.', close_popup=True)

    return locals()


@rtr()
@login_required()
def desconsiderar_comentario_etapa(request, pk_comentario):
    return excluir_comentario_etapa(request, pk_comentario, somente_desconsiderar=True)


@login_required
def get_campi_vinculados_json(request):
    """
    View para ser chamada via AJAX que retorna uma lista de campi
    baseado no tipo de calendário ('sistemico' ou 'nucleo_compras').
    """

    # Pega o parâmetro 'tipo' da requisição GET (ex: ?tipo=sistemico)
    tipo = request.GET.get('tipo', None)
    campi_list = []
    if tipo == 'sistemico':
        campi_list = list(UnidadeOrganizacional.objects.filter(nucleo_campi_vinculados__isnull=False).distinct().values('id', 'sigla'))
    elif tipo == 'nucleo_compras':
        nucleo_id = request.GET.get('nucleo_id', None)
        if nucleo_id:
            try:
                nucleo = Nucleo.objects.get(pk=nucleo_id)
                campi_list = list(nucleo.campi_vinculados.values('id', 'sigla'))
            except Nucleo.DoesNotExist:
                pass

    response_data = {'campi': campi_list}
    return JsonResponse(response_data)
