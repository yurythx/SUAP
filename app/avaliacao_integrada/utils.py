import urllib.parse


def atualizar_parametro_tab(url, tab, n_eixos):
    """
    Atualiza o parâmetro 'tab' na URL para o próximo valor, garantindo que só exista um,
    e no formato tab=tab0, tab=tab1, etc. Se já estiver na última tab, mantém.
    """
    parsed = urllib.parse.urlparse(url)
    query = dict(urllib.parse.parse_qsl(parsed.query))
    if not tab and n_eixos > 1:
        query['tab'] = 'tab1'
    elif tab:
        try:
            current_tab = int(tab.replace('tab', ''))
        except ValueError, TypeError, AttributeError:
            current_tab = 0
        if current_tab < n_eixos - 1:
            query['tab'] = f'tab{current_tab + 1}'
        else:
            query['tab'] = f'tab{current_tab}'  # Mantém na última tab
    new_query = urllib.parse.urlencode(query)
    return urllib.parse.urlunparse(parsed._replace(query=new_query))
