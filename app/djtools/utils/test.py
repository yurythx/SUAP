import os


def running_tests():
    """
    Verifica a execução, atual, está sendo a partir dos testes.

    Returns:
        True se a execução for a partir dos testes.
    """
    import sys

    return 'test_suap' in sys.argv or 'test' in sys.argv or 'test_behave' in sys.argv or os.environ.get('PYTEST_CURRENT_TEST')


def ignore_request_for_tests(request):
    """
    Determina se a requisição atual deve ser ignorada.

    Uma requisição é ignorada se:
    1. O ambiente está rodando testes.
    2. O caminho da requisição corresponde a um arquivo estático, admin jsi18n, mídia, ou termina com .js/.css.

    Args:
        request: Objeto HttpRequest da requisição atual.

    Returns:
        True se a requisição deve ser ignorada, False caso contrário.
    """

    if running_tests():
        path = request.path
        if path.startswith(('/static/', '/admin/jsi18n/', '/media/')) or path.endswith(('.js', '.css')):
            return True
    return False
