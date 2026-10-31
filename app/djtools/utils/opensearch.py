import time

from opensearchpy import OpenSearch


def get_opensearch_client():
    """
    Retorna o cliente do OpenSearch.
    """

    from comum.models import Configuracao

    host = Configuracao.get_valor_por_chave('djtools', 'opensearch_host')
    port = Configuracao.get_valor_por_chave('djtools', 'opensearch_port')
    auth = (Configuracao.get_valor_por_chave('djtools', 'opensearch_user'), Configuracao.get_valor_por_chave('djtools', 'opensearch_password'))

    client = OpenSearch(
        hosts=[{'host': host, 'port': port}],
        http_compress=True,
        http_auth=auth,
        use_ssl=True,
        verify_certs=False,
        ssl_assert_hostname=False,
        ssl_show_warn=False,
    )
    return client


def _sanitize_surrogates(data):
    """
    Remove ou substitui caracteres 'surrogate' que não podem ser codificados em UTF-8.
    """
    if isinstance(data, str):
        # Tenta codificar e decodificar ignorando erros de surrogate
        return data.encode('utf-8', 'replace').decode('utf-8')
    elif isinstance(data, dict):
        return {k: _sanitize_surrogates(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_sanitize_surrogates(i) for i in data]
    return data


def _search_opensearch(index_key, query, page=0, size=100, sort=None):
    """
    Função auxiliar para realizar buscas no OpenSearch.
    """
    from comum.models import Configuracao

    index = Configuracao.get_valor_por_chave('djtools', index_key)
    opensearch_timeout = int(Configuracao.get_valor_por_chave('djtools', 'opensearch_timeout') or '30')
    body = {'from': page * size, 'size': size, 'query': query}
    if sort:
        body['sort'] = sort

    client = get_opensearch_client()
    retries = 5
    for attempt in range(retries):
        try:
            response = client.search(body=body, index=index, timeout=opensearch_timeout)
            # Sanitiza a resposta antes de retornar
            return _sanitize_surrogates(response)
        except Exception:
            if attempt < retries - 1:
                time.sleep(1)  # Aguarda 1 segundo antes de tentar novamente
            else:
                raise


def get_opensearch_query_history(query, page=0, size=100, sort=None):
    """
    Retorna o índice de histórico do OpenSearch.
    """
    return _search_opensearch('opensearch_history_index', query, page, size, sort)


def get_opensearch_query_access_logs(query, page=0, size=100, sort=None):
    """
    Retorna o índice de Access Logs do OpenSearch.
    """
    return _search_opensearch('opensearch_access_logs_index', query, page, size, sort)


def get_opensearch_query_email_logs(query, page=0, size=100, sort=None):
    """
    Retorna o índice de envio de emails do OpenSearch.
    """
    return _search_opensearch('opensearch_email_index', query, page, size, sort)
