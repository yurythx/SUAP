def montar_paragrafo_html(texto):
    """
    Cria um parágrafo **HTML**.

    Args:
        texto (string): texto do parágrafo.

    Returns:
        String contendo o *HTML* do parágrafo.
    """
    return f'<p style="clear: both;">{texto}</p>'


def montar_tabela_html(tabela, css='results', alternar=None, destacar_ultima=False):
    """
    Cria uma tabela **HTML** com base na tabela (**dict**) passado.

    Args:
        tabela (dict): dicionário com os dados para montar a tabela;
        css (string): classe **CSS** para a tabela;
        alternar (list): classes que serão utilizads na montagem das linhas, alternado os valores;
        destacar_ultima (bool): indica se é para destacar a última linha da tabela.

    Examples:
        Entrada::

            {
                'cabecalhos': [
                    [{'valor': 'item', 'largura': 20, 'colspan': 2}],
                    [
                        {'valor': 'id', 'largura': 10, 'colspan': 1, 'alinhamento': 'right'},
                        {'valor': 'nome', 'largura': 10, 'colspan': 1, 'alinhamento': 'left'},
                    ],
                ],
                'dados': [
                    [1, 'bola de futebol'],
                ],
            }

        Saída::

            <table class="results">
                <thead>
                    <tr><th colspan="2">item</th></tr>
                    <tr><th colspan="1">id</th><th colspan="1">nome</th></tr>
                </thead>
                <tbody>
                    <tr>
                        <td align="right">1</td>
                        <td align="left">bola de futebol</td>
                    </tr>
                </tbody>
            </table>

        Returns:
            String com o código **HTML** da tabela.
    """
    if alternar is None:
        alternar = ['row1', 'row2']
    html = ['<table>']

    # Montando o THEAD
    cabecalhos = tabela['cabecalhos']
    html.append('<thead>')
    for c in cabecalhos:
        html.append('<tr>')
        for i in c:
            html.append('<th colspan="{}" align="{}">{}</th>'.format(i.get('colspan', 1), i.get('alinhamento', 'center'), i['valor']))
        html.append('</tr>')
    html.append('</thead>')

    # Montando o TBODY
    html.append('<tbody>')
    ultima_linha_eh_total = '' in tabela['dados'][-1]
    posicao_ultima_linha = len(tabela['dados']) - 1

    for index, d in enumerate(tabela['dados']):
        css_classes = alternar[index % 2]
        if ultima_linha_eh_total and index == posicao_ultima_linha:
            css_classes += ' total'
        html.append(f'<tr class="{css_classes}">')
        for index, item in enumerate(d):
            alinhamento = c[index]['alinhamento']
            html.append(f'<td align="{alinhamento}">{item}</td>')
        html.append('</tr>')

    html.append('</tbody></table>')

    return ''.join(html)


def montar_elementos_html(elementos):
    """
    Cria um elemento **HTML**.

    Args:
        elementos (list): lista com os elementos a serem montados.

    Returns:
        String com o elemento rendereizado em **HTML**
    """
    html = []
    for e in elementos:
        if isinstance(e, dict):
            html.append(montar_tabela_html(e))
        elif isinstance(e, str):
            html.append(montar_paragrafo_html(e))
    return ''.join(html)
