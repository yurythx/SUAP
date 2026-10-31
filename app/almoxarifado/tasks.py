import tempfile

from django.conf import settings
from django.core.cache import cache

from almoxarifado.models import MaterialConsumo
from comum.models import Configuracao
from comum.utils import get_setor, get_uo
from djtools.assincrono import task
from djtools.relatorios import RelatorioPDF, montar_tabela_html
from djtools.utils import data_extenso, extrair_periodo, mask_money, randomic, render, somar_dias, somar_indice, somar_qtd
from rh.models import UnidadeOrganizacional


def balancete_material_dados(data_ini, data_fim, uo, estoque, user, task):
    datas = [data_ini, data_fim]
    data_anterior = somar_dias(data_ini, -1)

    # Restrição da seleção de UO baseada na permissão do usuário
    if user.has_perm('almoxarifado.pode_ver_relatorios_todos'):
        uo_id = (uo and uo.id) or None
    else:
        uo_id = uo.id
    cabecalhos_tabela = [
        [
            {'valor': '', 'alinhamento': 'center', 'largura': 6, 'colspan': 1},
            {'valor': '', 'alinhamento': 'left', 'largura': 10, 'colspan': 1},
            {'valor': '', 'alinhamento': 'left', 'largura': 50, 'colspan': 1},
            {'valor': 'Estoque {}'.format(data_anterior.strftime('%d/%m/%Y')), 'alinhamento': 'center', 'largura': 30, 'colspan': 2},
            {'valor': 'Entrada Período', 'alinhamento': 'center', 'largura': 30, 'colspan': 2},
            {'valor': 'Saída Período', 'alinhamento': 'center', 'largura': 30, 'colspan': 2},
            {'valor': 'Estoque {}'.format(datas[1].strftime('%d/%m/%Y')), 'alinhamento': 'center', 'largura': 30, 'colspan': 2},
        ],
        [
            {'valor': 'ED', 'alinhamento': 'center', 'largura': 6, 'colspan': 1},
            {'valor': 'Cod.', 'alinhamento': 'left', 'largura': 10, 'colspan': 1},
            {'valor': 'Nome', 'alinhamento': 'left', 'largura': 50, 'colspan': 1},
            {'valor': 'Qtd.', 'alinhamento': 'right', 'largura': 15, 'colspan': 1},
            {'valor': 'Valor', 'alinhamento': 'right', 'largura': 15, 'colspan': 1},
            {'valor': 'Qtd.', 'alinhamento': 'right', 'largura': 15, 'colspan': 1},
            {'valor': 'Valor', 'alinhamento': 'right', 'largura': 15, 'colspan': 1},
            {'valor': 'Qtd.', 'alinhamento': 'right', 'largura': 15, 'colspan': 1},
            {'valor': 'Valor', 'alinhamento': 'right', 'largura': 15, 'colspan': 1},
            {'valor': 'Qtd.', 'alinhamento': 'right', 'largura': 15, 'colspan': 1},
            {'valor': 'Valor', 'alinhamento': 'right', 'largura': 15, 'colspan': 1},
        ],
    ]
    if uo_id:
        metodo_entrada = 'entrada'
        metodo_saida = 'saida'
    else:
        # Todas as UO's devem desconsiderar transferência entre elas.
        metodo_entrada = 'entrada_normal'
        metodo_saida = 'saida_normal'

    corpo_tabela = []

    for material in task.iterate(MaterialConsumo.get_movimentados(datas[1], uo_id)):
        estoque_anterior = material.estoque(data=data_anterior, uo_id=uo_id)
        estoque_fim_periodo = material.estoque(data=datas[1], uo_id=uo_id)
        entrada_periodo = material.__getattribute__(metodo_entrada)(datas, uo_id)
        saida_periodo = material.__getattribute__(metodo_saida)(datas, uo_id)

        if estoque is True:
            if entrada_periodo.get('qtd') > 0 or saida_periodo.get('qtd') > 0:
                corpo_tabela.append(
                    [
                        material.categoria.codigo,
                        f'{material.codigo}',
                        f'{material.nome}',
                        int(estoque_anterior.get('qtd')),
                        mask_money(estoque_anterior.get('valor')),
                        int(entrada_periodo.get('qtd')),
                        mask_money(entrada_periodo.get('valor')),
                        int(saida_periodo.get('qtd')),
                        mask_money(saida_periodo.get('valor')),
                        int(estoque_fim_periodo.get('qtd')),
                        mask_money(estoque_fim_periodo.get('valor')),
                    ]
                )
        else:
            corpo_tabela.append(
                [
                    material.categoria.codigo,
                    f'{material.codigo}',
                    f'{material.nome}',
                    int(estoque_anterior.get('qtd')),
                    mask_money(estoque_anterior.get('valor')),
                    int(entrada_periodo.get('qtd')),
                    mask_money(entrada_periodo.get('valor')),
                    int(saida_periodo.get('qtd')),
                    mask_money(saida_periodo.get('valor')),
                    int(estoque_fim_periodo.get('qtd')),
                    mask_money(estoque_fim_periodo.get('valor')),
                ]
            )

    linha_total = [
        '-',
        '-',
        'Todos os Materiais de Consumo',
        int(somar_indice(corpo_tabela, 3)),
        mask_money(somar_indice(corpo_tabela, 4)),
        int(somar_indice(corpo_tabela, 5)),
        mask_money(somar_indice(corpo_tabela, 6)),
        int(somar_indice(corpo_tabela, 7)),
        mask_money(somar_indice(corpo_tabela, 8)),
        int(somar_indice(corpo_tabela, 9)),
        mask_money(somar_indice(corpo_tabela, 10)),
    ]
    corpo_tabela.append(linha_total)

    tabela = {'cabecalhos': cabecalhos_tabela, 'dados': corpo_tabela}
    uo = uo_id and UnidadeOrganizacional.objects.suap().get(id=uo_id) or 'Todas as Unidades Organizacionais'
    p = f'Unidade Organizacional: {uo}<br/>Período: {extrair_periodo(data_ini, data_fim)}'

    dados = {
        'cabecalho': {'orgao': Configuracao.get_valor_por_chave('comum', 'instituicao'), 'uo': str(get_uo(user)), 'setor': str(get_setor(user))},
        'data': data_extenso(),
        'titulo': 'Balancete Material de Consumo',
        'elementos': [p, tabela],
        'cidade': user.get_vinculo().setor.uo.municipio,
    }

    return dados


@task('Gerar Balancete de Material')
def gerar_balancete_material(data_ini, data_fim, uo, estoque, request, task=None):
    dados = balancete_material_dados(data_ini, data_fim, uo, estoque, request.user, task)
    titulo = dados['titulo']
    p, tabela = dados['elementos']
    tabela = montar_tabela_html(tabela, destacar_ultima=True)
    uo_id = uo and uo.id or 0
    link_pdf = f'/almoxarifado/relatorio/balancete_material_pdf?uo={uo_id}&dt_ini={data_ini}&dt_fim={data_fim}&estoque={estoque}'
    tmp = tempfile.NamedTemporaryFile(suffix='.html', mode='w+b', delete=False)
    tmp.write(
        render(
            'relatorio.html',
            {
                'title': titulo,
                'p': p,
                'tabela': tabela,
                'link_pdf': link_pdf,
                'menu_as_html': request.session.get('menu_as_html', ''),
                'debug': settings.DEBUG,
            },
            request=request,
        ).content
    )
    tmp.close()
    return task.finalize('Balancete gerado com sucesso.', '..', file_path=tmp.name)


@task('Exportar Balancete de Material para PDF')
def exportar_balancete_material_pdf(data_ini, data_fim, uo, estoque, request, task=None):
    task.start_progress()
    dados = balancete_material_dados(data_ini, data_fim, uo, estoque, request.user, task)
    task.update_progress(50)
    pdf_content = RelatorioPDF(dados, paisagem=True).montar()
    task.update_progress(70)
    tmp = tempfile.NamedTemporaryFile(suffix='.pdf', mode='w+b', delete=False)
    tmp.write(pdf_content)
    tmp.close()
    task.update_progress(90)
    return task.finalize('Arquivo gerado com sucesso.', '..', file_path=tmp.name)


@task('Gerar Relatório de Balancete de Elemento de Despesa Detalhado')
def relatorio_balancete_ed_detalhado(cleaned_data, request, task=None):
    data_ini = cleaned_data['data_inicial']
    data_fim = cleaned_data['data_final']
    datas = [data_ini, data_fim]
    data_anterior = somar_dias(data_ini, -1)
    ed = cleaned_data['elemento_de_despesa']
    ed_itens = ed.materialconsumo_set.all().order_by('nome')
    apenas_em_estoque = cleaned_data['estoque']

    # Restrição de visualização de materiais de consumo com base na permissão do usuário.
    usuario = request.user
    if usuario.has_perm('almoxarifado.pode_ver_relatorios_todos'):
        uo = cleaned_data['uo'] or None
        uo_id = uo and uo.id or None
    else:
        uo = get_uo(usuario)
        uo_id = uo and uo.id or None

    if uo:
        metodo_entrada = 'entrada'
        metodo_saida = 'saida'
    else:
        # Todas as UO's devem desconsiderar transferência entre elas.
        metodo_entrada = 'entrada_normal'
        metodo_saida = 'saida_normal'

    cabecalhos_tabela = [
        [
            {'valor': '', 'alinhamento': 'center', 'largura': 6, 'colspan': 1},
            {'valor': '', 'alinhamento': 'left', 'largura': 80, 'colspan': 1},
            {'valor': 'Estoque {}'.format(data_anterior.strftime('%d/%m/%Y')), 'alinhamento': 'center', 'largura': 47, 'colspan': 3},
            {'valor': 'Entrada Período', 'alinhamento': 'center', 'largura': 47, 'colspan': 3},
            {'valor': 'Saída Período', 'alinhamento': 'center', 'largura': 47, 'colspan': 3},
            {'valor': 'Estoque {}'.format(datas[1].strftime('%d/%m/%Y')), 'alinhamento': 'center', 'largura': 47, 'colspan': 3},
        ],
        [
            {'valor': '#', 'alinhamento': 'center', 'largura': 6, 'colspan': 1},
            {'valor': 'Nome', 'alinhamento': 'left', 'largura': 80, 'colspan': 1},
            {'valor': 'Qtd.', 'alinhamento': 'right', 'largura': 13, 'colspan': 1},
            {'valor': 'Valor Médio', 'alinhamento': 'right', 'largura': 17, 'colspan': 1},
            {'valor': 'Valor', 'alinhamento': 'right', 'largura': 17, 'colspan': 1},
            {'valor': 'Qtd.', 'alinhamento': 'right', 'largura': 13, 'colspan': 1},
            {'valor': 'Valor Médio', 'alinhamento': 'right', 'largura': 17, 'colspan': 1},
            {'valor': 'Valor', 'alinhamento': 'right', 'largura': 17, 'colspan': 1},
            {'valor': 'Qtd.', 'alinhamento': 'right', 'largura': 13, 'colspan': 1},
            {'valor': 'Valor Médio', 'alinhamento': 'right', 'largura': 17, 'colspan': 1},
            {'valor': 'Valor', 'alinhamento': 'right', 'largura': 17, 'colspan': 1},
            {'valor': 'Qtd.', 'alinhamento': 'right', 'largura': 13, 'colspan': 1},
            {'valor': 'Valor Médio', 'alinhamento': 'right', 'largura': 17, 'colspan': 1},
            {'valor': 'Valor', 'alinhamento': 'right', 'largura': 17, 'colspan': 1},
        ],
    ]
    corpo_tabela = []

    for index, item in task.iterate(list(enumerate(ed_itens))):
        estoque_anterior = item.estoque(data=data_anterior, uo_id=uo_id)
        estoque_fim_periodo = item.estoque(data=datas[1], uo_id=uo_id)
        devolucao_periodo = item.__getattribute__('devolucao')(datas, uo_id)
        entrada_periodo = item.__getattribute__(metodo_entrada)(datas, uo_id)
        saida_periodo = item.__getattribute__(metodo_saida)(datas, uo_id)
        if (
            apenas_em_estoque
            and estoque_anterior.get('qtd') == 0
            and estoque_fim_periodo.get('qtd') == 0
            and saida_periodo.get('qtd') == 0
            and entrada_periodo.get('qtd') == 0
        ):
            continue
        valor_medio = 0
        if estoque_anterior.get('qtd') != 0:
            valor_medio = estoque_anterior.get('valor') / estoque_anterior.get('qtd')

        valor_medio_entrada = 0
        valor_entrada = entrada_periodo.get('valor')
        if entrada_periodo.get('qtd') != 0:
            if devolucao_periodo.get('qtd') != 0:
                valor_entrada = entrada_periodo.get('valor') + devolucao_periodo.get('valor')
                valor_medio_entrada = valor_entrada / (entrada_periodo.get('qtd') + devolucao_periodo.get('qtd'))
            else:
                valor_medio_entrada = entrada_periodo.get('valor') / entrada_periodo.get('qtd')

        estoque_entrada = entrada_periodo.get('qtd')
        if devolucao_periodo.get('qtd') != 0:
            estoque_entrada = entrada_periodo.get('qtd') + devolucao_periodo.get('qtd')

        valor_medio_saida = 0
        if saida_periodo.get('qtd') != 0:
            valor_medio_saida = saida_periodo.get('valor') / saida_periodo.get('qtd')

        valor_medio_estoque_final = 0
        if estoque_fim_periodo.get('qtd') != 0:
            valor_medio_estoque_final = estoque_fim_periodo.get('valor') / estoque_fim_periodo.get('qtd')

        corpo_tabela.append(
            [
                index + 1,
                item.nome,
                int(estoque_anterior.get('qtd')),
                mask_money(valor_medio),
                mask_money(estoque_anterior.get('valor')),
                int(estoque_entrada),
                mask_money(valor_medio_entrada),
                mask_money(valor_entrada),
                int(saida_periodo.get('qtd')),
                mask_money(valor_medio_saida),
                mask_money(saida_periodo.get('valor')),
                int(estoque_fim_periodo.get('qtd')),
                mask_money(valor_medio_estoque_final),
                mask_money(estoque_fim_periodo.get('valor')),
            ]
        )

    linha_total = [
        '-',
        'TODOS OS MATERIAIS DO ELEMENTOS DE DESPESA',
        somar_qtd(corpo_tabela, 2),
        '-',
        mask_money(somar_indice(corpo_tabela, 4)),
        somar_qtd(corpo_tabela, 5),
        '-',
        mask_money(somar_indice(corpo_tabela, 7)),
        somar_qtd(corpo_tabela, 8),
        '-',
        mask_money(somar_indice(corpo_tabela, 10)),
        somar_qtd(corpo_tabela, 11),
        '-',
        mask_money(somar_indice(corpo_tabela, 13)),
    ]

    corpo_tabela.append(linha_total)
    tabela = {'cabecalhos': cabecalhos_tabela, 'dados': corpo_tabela}
    uo = uo or 'Todas as Unidades Organizacionais'
    p = f'Elemento de Despesa: {ed.id} - {ed.nome}'
    p += f'<br/>Período: {extrair_periodo(data_ini, data_fim)}'
    p += f'<br/>Unidade Organizacional: {uo}'
    dados = {
        'cabecalho': {
            'orgao': Configuracao.get_valor_por_chave('comum', 'instituicao'),
            'uo': str(get_uo(usuario)),
            'setor': str(get_setor(usuario)),
        },
        'data': data_extenso(),
        'titulo': 'Balancete Elemento de Despesa Detalhado',
        'elementos': [p, tabela],
    }
    id_ = randomic()
    cache.set(id_, dados)

    task.finalize('Balancete Elemento de Despesa Detalhado.', f'/almoxarifado/relatorio/balancete_ed_detalhado_html/{id_}/')


@task('Exportar Relatório de Balancete de Elemento de Despesa Detalhado para PDF')
def balancete_ed_detalhado_pdf(dados, task=None):
    pdf_content = RelatorioPDF(dados, paisagem=True).montar()
    tmp = tempfile.NamedTemporaryFile(suffix='.pdf', mode='w+b', delete=False)
    tmp.write(pdf_content)
    tmp.close()
    task.finalize('Arquivo gerado com sucesso.', '..', file_path=tmp.name)
