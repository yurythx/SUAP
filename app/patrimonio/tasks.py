import calendar
import datetime
import re
import tempfile
from decimal import Decimal

from django.conf import settings
from django.db.models import Max, OuterRef, Subquery, Sum

from comum.relatorios import get_topo_com_titulo
from djtools import relatorios
from djtools.assincrono import task
from djtools.templatetags.filters import format_datetime, format_money_almox
from djtools.utils import CsvResponse, XlsResponse, date_to_string, render
from patrimonio.models import (
    CategoriaMaterialPermanente,
    ConferenciaItem,
    Inventario,
    InventarioCargaContabil,
    InventarioValor,
    MovimentoPatrim,
    MovimentoPatrimTipo,
    Requisicao,
    RequisicaoItem,
)
from patrimonio.pdf import get_rodape_termos
from rh.models import UnidadeOrganizacional


def truncate(string, width):
    if len(string) > width:
        string = string[: width - 3] + '...'
    return string


@task('Exportar Relatório de Termos para PDF')
def exportar_relatorio_termos_pdf(servidor, args, titulo, task=None):
    # multiplica por 2 para só chegar a 50%, no edu estava assim

    dados_inv = Inventario.get_inventarios_carga_user(servidor, **args)
    topo = get_topo_com_titulo(titulo)

    descricoes = dados_inv['descricoes']
    nome = servidor.pessoa_fisica.nome
    dados = [['#', 'Número', 'Descrição', 'Sala', 'Conservação', 'Valor']]
    total = 0
    index = 0
    for item in task.iterate(dados_inv['inventarios']):
        valor = item['valor']
        numero = item['numero']
        id = item['id']
        descricao = descricoes[id] if id in descricoes else item['entrada_permanente__descricao']
        sala = '-'.join([item['sala__nome'] or '', item['sala__predio__nome'] or '', item['sala__predio__uo__sigla'] or ''])
        dados.append(
            [index + 1, numero, re.sub('[\t\r\n]', '', truncate(descricao, 3400)), sala, item['estado_conservacao'] or '-', format_money_almox(valor)]
        )
        if valor is not None:
            total = total + float(valor)
        index += 1

    total = format_money_almox(total)
    info_total = [['', '', '', '', '', total]]
    widths = [10, 15, 96, 40, 22, 20]
    tabela_total = relatorios.table(info_total, w=widths)
    rodape = get_rodape_termos(nome)
    tabela_dados = relatorios.table(dados, head=1, zebra=1, w=widths, count=0, a=['r', 'c', 'l', 'c', 'c', 'r'])
    para_responsavel = relatorios.para(
        'Responsável: <b>{} (Matrícula: {})</b><br/>Setor: <b>{} ({})</b>'.format(
            servidor.pessoa_fisica.nome,
            servidor.matricula,
            servidor.setor.nome if servidor.setor else 'Sem setor',
            servidor.setor.sigla if servidor.setor else '',
        ),
        escape=False,
    )
    body = [*topo, para_responsavel, relatorios.space(5), tabela_dados, tabela_total, *rodape]

    pdf_content = relatorios.PdfReport(body=body, header_args=None, paper='A4', creation_date=True).generate()

    tmp = tempfile.NamedTemporaryFile(suffix='.pdf', mode='w+b', delete=False)
    tmp.write(pdf_content)
    tmp.close()
    return task.finalize('Arquivo gerado com sucesso.', '..', file_path=tmp.name)


@task('Gerar Relatório de Totalização por Campus')
def gerar_relatorio_totalizacao_campus(request, queryset, campus, ano, mes, task=None):
    categorias = []
    total_geral = []
    if ano:
        data_final = datetime.date(ano, int(mes), calendar.monthrange(ano, int(mes))[1])
    else:
        data_final = datetime.date.today()

    total = Decimal('0.0')
    for elem in task.iterate(queryset.order_by('codigo')):
        invs_baixa = Inventario.baixados.filter(
            entrada_permanente__categoria=elem,
            cargas_contabeis__campus=campus,
            movimentopatrim__tipo__id=MovimentoPatrimTipo.BAIXA().pk,
            movimentopatrim__data__lte=data_final,
        ).values_list('id', flat=True)

        depreciaveis = Inventario.objects.filter(
            entrada_permanente__categoria=elem, cargas_contabeis__campus=campus, cargas_contabeis__data__lte=data_final
        )
        ids = []
        for i in depreciaveis:
            cc = InventarioCargaContabil.objects.filter(inventario=i, data__lte=data_final).annotate(max=Max('data')).order_by('-data', '-id')

            if cc.exists():
                if cc[0].campus != campus:
                    ids.append(cc[0].inventario.id)
        ids = list(set(ids) | set(invs_baixa))

        total_categoria = (
            Inventario.objects.exclude(id__in=ids)
            .filter(entrada_permanente__categoria=elem, cargas_contabeis__campus=campus, cargas_contabeis__data__lte=data_final)
            .annotate(max=Max('cargas_contabeis__data'))
            .aggregate(total=Sum('entrada_permanente__valor'))
        )
        if elem.plano_contas is not None:
            plano_contas = elem.plano_contas.codigo
        else:
            plano_contas = '-'

        categorias.append(
            {
                'codigo': elem.codigo,
                'nome': elem.nome,
                'id': elem.id,
                'plano_contas': plano_contas,
                'total': format_money_almox(total_categoria['total'] or 0),
            }
        )

        total += total_categoria['total'] or 0
    total_geral.append(total)
    dados = {
        'categorias': categorias,
        'total_geral': total_geral,
        'data_final': data_final,
        'campus': campus,
    }

    campus = dados['campus']
    categorias = dados['categorias']
    total_geral = dados['total_geral']
    data_final = dados['data_final']
    menu_as_html = request.session.get('menu_as_html', '')
    debug = settings.DEBUG
    response = render(
        'patrimonio/templates/relatorio/totalizacao_campus.html',
        {
            'campus': campus,
            'categorias': categorias,
            'total_geral': total_geral,
            'data_final': data_final,
            'menu_as_html': menu_as_html,
            'debug': debug,
        },
        request=request,
    )

    tmp = tempfile.NamedTemporaryFile(suffix='.html', mode='w+b', delete=False)
    tmp.write(response.content)
    tmp.close()

    return task.finalize('Relatório gerado com sucesso.', '..', file_path=tmp.name)


@task('Exportar Relatório de Depreciação por Contas Contábeis para PDF')
def exportar_relatorio_depreciacao_pdf(mes, ano, campus, task=None):
    titulo = relatorios.para('Relatório de Depreciação por Contas Contábeis', style='h1', align='c')
    data = relatorios.para(f'Período: {mes}/{ano}', style='h5', align='c')
    tabela_registros = [
        ['Conta Contábil', 'Código', 'Plano de Contas', 'Valor Bruto', 'Valor Depreciação Acumulada', 'Valor Líquido', 'Valor Depreciação Mensal']
    ]
    planocontabil = CategoriaMaterialPermanente.objects.all().order_by('plano_contas__codigo')
    totalizador_valor_bruto = 0
    totalizador_depreciacao_acumulada = 0
    totalizador_valor_liquido = 0
    totalizador_valor_depreciado = 0
    uo = UnidadeOrganizacional.objects.suap().get(pk=campus.id)
    campus = relatorios.para(f'Campus: {uo}', style='h5', align='c')
    data_final = datetime.date(int(ano), int(mes), calendar.monthrange(int(ano), int(mes))[1])

    for elem in task.iterate(planocontabil):
        baixados = Inventario.baixados.filter(
            entrada_permanente__categoria=elem, movimentopatrim__tipo__id=MovimentoPatrimTipo.BAIXA().pk, movimentopatrim__data__lte=data_final
        )
        invs_baixa = []
        for b in baixados:
            if MovimentoPatrim.objects.filter(inventario=b, tipo__id=MovimentoPatrimTipo.BAIXA().pk, data__lte=data_final):
                invs_baixa.append(b.id)

        depreciaveis = Inventario.objects.filter(
            entrada_permanente__categoria=elem, cargas_contabeis__campus=uo, cargas_contabeis__data__lte=data_final
        )

        ids = []
        for i in depreciaveis:
            cc = InventarioCargaContabil.objects.filter(inventario=i, data__lte=data_final).order_by('-data', '-id')

            if cc.exists():
                if cc[0].campus != uo:
                    ids.append(cc[0].inventario.id)
        ids = list(set(ids) | set(invs_baixa))
        valor_bruto = (
            Inventario.objects.exclude(id__in=ids)
            .filter(entrada_permanente__categoria=elem, cargas_contabeis__campus=uo, cargas_contabeis__data__lte=data_final)
            .annotate(max=Max('cargas_contabeis__data'))
            .aggregate(total=Sum('entrada_permanente__valor'))
        )
        invs = (
            Inventario.objects.exclude(id__in=ids)
            .filter(entrada_permanente__categoria=elem, cargas_contabeis__campus=uo, cargas_contabeis__data__lte=data_final)
            .annotate(max=Max('cargas_contabeis__data'))
        )

        valor_liquido = 0
        total_depreciacao = 0

        mes = int(mes)
        ano = int(ano)

        if mes == 12:
            proximo_mes = 1
            proximo_ano = ano + 1
        else:
            proximo_mes = mes + 1
            proximo_ano = ano

        if mes == 1:
            mes_anterior = 12
            ano_anterior = ano - 1
        else:
            mes_anterior = mes - 1
            ano_anterior = ano

        for inv in invs:
            valor_atual = 0
            if InventarioValor.objects.filter(inventario=inv, data__month=mes, data__year=ano).exists():
                valor_atual = InventarioValor.objects.get(inventario=inv, data__month=mes, data__year=ano).valor
            else:
                if inv.valor:
                    valor_atual = inv.valor
                else:
                    valor_atual = inv.entrada_permanente.valor
            valor_liquido += valor_atual
            valor_deprec = 0

            if InventarioValor.objects.filter(inventario=inv, data__month=mes, data__year=ano).exists():
                valor_deprec_atual = InventarioValor.objects.get(inventario=inv, data__month=mes, data__year=ano).valor
                if InventarioValor.objects.filter(inventario=inv, data__month=mes_anterior, data__year=ano_anterior).exists():
                    valor_deprec = (
                        InventarioValor.objects.get(inventario=inv, data__month=mes_anterior, data__year=ano_anterior).valor - valor_deprec_atual
                    )

                elif InventarioValor.objects.filter(inventario=inv, data__month=proximo_mes, data__year=proximo_ano).exists():
                    valor_deprec = (
                        valor_deprec_atual - InventarioValor.objects.get(inventario=inv, data__month=proximo_mes, data__year=proximo_ano).valor
                    )
                else:
                    valor_deprec = inv.entrada_permanente.valor - valor_deprec_atual
            total_depreciacao += valor_deprec

        planocontas_codigo = elem.plano_contas.codigo if elem.plano_contas and elem.plano_contas.codigo else '-'
        row = [
            planocontas_codigo,
            elem.codigo,
            elem.nome,
            format_money_almox(valor_bruto['total'] or 0),
            format_money_almox((valor_bruto['total'] or 0) - valor_liquido),
            format_money_almox(valor_liquido or 0),
            format_money_almox(total_depreciacao or 0),
        ]
        tabela_registros.append(row)
        totalizador_valor_bruto += valor_bruto['total'] or 0
        totalizador_valor_liquido += valor_liquido
        totalizador_depreciacao_acumulada = totalizador_valor_bruto - totalizador_valor_liquido
        totalizador_valor_depreciado += total_depreciacao
    totalizador = [
        '-',
        '-',
        'Todas as Categorias',
        format_money_almox(totalizador_valor_bruto),
        format_money_almox(totalizador_depreciacao_acumulada),
        format_money_almox(totalizador_valor_liquido),
        format_money_almox(totalizador_valor_depreciado),
    ]
    tabela_registros.append(totalizador)
    tabela_registros = relatorios.table(tabela_registros, head=1, zebra=1, w=[20, 15, 92, 31, 31, 31, 39], a=['l', 'l', 'l', 'r', 'r', 'r', 'r'])
    body = [*relatorios.get_topo_pdf(), titulo, data, campus, relatorios.space(8), tabela_registros]

    meu_pdf = relatorios.PdfReport(body=body, paper='-A4').generate()

    tmp = tempfile.NamedTemporaryFile(suffix='.pdf', mode='w+b', delete=False)
    tmp.write(meu_pdf)
    tmp.close()

    return task.finalize('Arquivo gerado com sucesso.', '..', file_path=tmp.name)


def anotacoes_ultima_conferencia():
    """Anotações da última conferência de cada inventário, evitando uma consulta por linha."""
    # O `-id` desempata coletas no mesmo instante, garantindo que as duas subqueries leiam o mesmo item.
    ultima = ConferenciaItem.objects.filter(inventario=OuterRef('pk')).order_by('-dh_coleta', '-id')[:1]
    return {
        'ultima_conferencia_id': Subquery(ultima.values('conferencia_id')),
        'ultima_conferencia_dh': Subquery(ultima.values('dh_coleta')),
    }


def ultima_conferencia_exportacao(inventario: Inventario):
    if not inventario.ultima_conferencia_id:
        return '-'
    return f'Conferência {inventario.ultima_conferencia_id} - {format_datetime(inventario.ultima_conferencia_dh)}'


def anotacoes_ultima_requisicao():
    """Anotações da última requisição de cada inventário (mesmo critério de `Inventario.get_ultima_requisicao`)."""
    ultima = RequisicaoItem.objects.filter(inventario=OuterRef('pk')).order_by('-id')[:1]
    return {
        'ultima_requisicao_id': Subquery(ultima.values('requisicao_id')),
        'ultima_requisicao_status': Subquery(ultima.values('requisicao__status')),
        'ultima_requisicao_destinatario': Subquery(ultima.values('requisicao__vinculo_destino__pessoa__nome')),
    }


def ultima_requisicao_exportacao(inventario: Inventario):
    if not inventario.ultima_requisicao_id:
        return '-'
    situacao = dict(Requisicao.STATUS_CHOICES).get(inventario.ultima_requisicao_status, '-')
    destinatario = inventario.ultima_requisicao_destinatario or '-'
    return f'Requisição #{inventario.ultima_requisicao_id} - Destinatário: {destinatario} - Situação: {situacao}'


@task('Exportar Relatório de Busca')
def inventario_dados_exportacao(inventarios, format: str, ver_observacao: bool = False, task=None):
    """
    Monta tabela de dados retornados da busca de inventários para
    exportação via XLS ou CSV.
    """
    rows = []
    header = [
        '#',
        'NUMERO',
        'STATUS',
        'ED',
        'DESCRICAO',
        'RÓTULOS',
        'CARGA ATUAL',
        'SETOR DO RESPONSÁVEL',
        'CAMPUS DA CARGA',
        'VALOR AQUISIÇÃO',
        'VALOR DEPRECIADO',
        'NUMERO NOTA FISCAL',
        'NÚMERO DE SÉRIE',
        'DATA DA ENTRADA',
        'DATA DA CARGA',
        'FORNECEDOR',
        'SALA',
        'ESTADO DE CONSERVAÇÃO',
        'ÚLTIMA REQUISIÇÃO',
        'ÚLTIMA CONFERÊNCIA',
    ] + (['OBSERVAÇÃO'] if ver_observacao else [])
    rows.append(header)
    count = 0
    total_depreciado = 0
    total_aquisicao = 0
    inventarios = (
        inventarios.select_related(
            'entrada_permanente',
            'entrada_permanente__categoria',
            'responsavel_vinculo',
            'responsavel_vinculo__setor',
            'responsavel_vinculo__setor__uo',
            'responsavel_vinculo__pessoa',
            'status',
            'sala',
            'sala__predio',
            'entrada_permanente__entrada__vinculo_fornecedor',
        )
        .prefetch_related('rotulos', 'movimentopatrim_set')
        .only(
            'numero',
            'valor',
            'status__nome',
            'entrada_permanente__valor',
            'entrada_permanente__categoria__codigo',
            'descricao',
            'responsavel_vinculo',
            'responsavel_vinculo__pessoa__nome',
            'responsavel_vinculo__setor',
            'numero_serie',
            'estado_conservacao',
            'sala__nome',
            'sala__predio__nome',
            'entrada_permanente__entrada__numero_nota_fiscal',
            'entrada_permanente__entrada__vinculo_fornecedor__pessoa__nome',
            'observacao',
        )
        .annotate(**anotacoes_ultima_requisicao(), **anotacoes_ultima_conferencia())
    )
    for inventario in task.iterate(inventarios):
        count += 1
        row = [count, inventario.numero, inventario.status, inventario.entrada_permanente.categoria.codigo, inventario.get_descricao()]
        rotulos = [rotulo.nome for rotulo in inventario.rotulos.all()]
        if rotulos:
            rotulos = '|'.join(rotulos)
        row.append(rotulos or '-')

        responsavel = '-'
        setor_responsavel = '-'
        campus = '-'
        if inventario.responsavel_vinculo_id:
            setor = inventario.responsavel_vinculo.setor
            if setor:
                setor_responsavel = str(setor)
                campus = setor.uo
                if campus:
                    campus = str(campus)
            responsavel = f'{inventario.responsavel_vinculo.pessoa.nome}({campus} {setor_responsavel})'
        row.append(str(responsavel))
        row.append(str(setor_responsavel))
        row.append(str(campus))
        row.append(inventario.entrada_permanente.valor)
        row.append(inventario.valor)
        row.append(inventario.entrada_permanente.entrada.numero_nota_fiscal or '-')
        row.append(inventario.numero_serie)
        data_entrada = inventario.entrada_permanente.entrada.data
        data_carga = inventario.get_data_carga()
        row.append(date_to_string(data_entrada))
        row.append(date_to_string(data_carga))
        entrada = inventario.entrada_permanente.entrada
        fornecedor = '-'
        if entrada.vinculo_fornecedor_id:
            fornecedor = entrada.vinculo_fornecedor.pessoa.nome or '-'
        row.append(str(fornecedor))
        sala = f'{inventario.sala.nome}({inventario.sala.predio.nome})' if inventario.sala_id else '-'
        row.append(str(sala))
        row.append(f'{inventario.get_estado_conservacao_display()}')
        row.append(ultima_requisicao_exportacao(inventario))
        row.append(ultima_conferencia_exportacao(inventario))
        row.extend([inventario.observacao or '-'] if ver_observacao else [])

        if inventario.valor:
            total_depreciado += float(inventario.valor)
        total_aquisicao += float(inventario.entrada_permanente.valor)

        for index, column in enumerate(row):
            row[index] = column
        rows.append(row)
    rodape = ['', '', '', '', '', '', '', '', 'TOTAL', total_aquisicao, total_depreciado]
    rows.append(rodape)
    if format == 'xls' and len(rows) < 65000:
        return XlsResponse(rows, processo=task)
    else:
        return CsvResponse(rows, processo=task)


@task('Deferir Requisições')
def deferir_requisicao(requisicao, request, sala, task=None):
    requisicao.deferir_requisicao(request.user, sala, task)
    task.finalize('Transferência deferida com sucesso.', url=f'/patrimonio/requisicao/{requisicao.pk}')


@task('Migrar Inventários')
def migrar_inventarios(conteudo, nome, processo, task=None):
    """
    Importa o acervo da planilha em segundo plano.

    A planilha viaja como **conteúdo**, não como caminho: nunca foi gravada em lugar nenhum, veio
    do navegador com a confirmação e daqui em diante só existe como bytes (`nome` só serve para a
    extensão decidir o formato). O histórico da execução fica no próprio `djtools.Task`.
    """
    from patrimonio import migrador

    conferencia = migrador.conferir(migrador.como_arquivo(conteudo, nome))
    # O usuário vem da própria Task: `tl.get_user()` é thread-local e a task roda em outra
    # thread (ou em outro processo, sob Celery), onde o middleware nunca passou.
    resumo = migrador.executar(conferencia, task.user, processo, task)

    links = ', '.join(f'<a href="/almoxarifado/entrada/{pk}/">#{pk}</a>' for pk in resumo['entradas_criadas'][:20])
    task.finalize(
        f'Migração concluída: {resumo["bens"]} bens importados '
        f'({resumo["com_responsavel"]} com carga, {resumo["pendentes"]} pendentes) '
        f'em {len(resumo["entradas_criadas"])} entrada(s): {links}.',
        url='/patrimonio/migracao/',
    )
