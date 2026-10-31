"""Testes DB-free do guarda de posse da view ``avaliacao_integrada.views.questionario`` (#17040).

A view decorada com ``@rtr`` é desembrulhada com ``inspect.unwrap`` para chamar o corpo cru,
e os toques de ORM são mockados — o que se testa é só quem a view deixa entrar.

O ponto sensível é o mock de ``pode_visualizar_questionario_terceiros``: ele é um **método**,
e o defeito consistia em referenciá-lo sem os parênteses. Por isso o mock devolve ``False``
por chamada em vez de ser um atributo ``False``: assim o objeto-método continua *truthy* e o
código defeituoso volta a passar por pré-visualização, fazendo estes testes falharem.
"""

import datetime
from inspect import unwrap
from unittest.mock import MagicMock, patch

from avaliacao_integrada import views

# make_request: fixture em avaliacao_integrada/tests/views/conftest.py


def _respondente(pode_ver_terceiros: bool) -> MagicMock:
    """Respondente de outra pessoa, numa avaliação dentro do prazo."""
    respondente = MagicMock()
    respondente.avaliacao.data_termino = datetime.date.today() + datetime.timedelta(days=30)
    respondente.avaliacao.pode_visualizar_questionario_terceiros = MagicMock(return_value=pode_ver_terceiros)
    return respondente


def _chamar(request, respondente):
    with patch.object(views, 'get_object_or_404', return_value=respondente), patch.object(views, 'httprr', return_value='REDIRECT'):
        return unwrap(views.questionario)(request, pk=1)


def test_questionario_de_terceiro_sem_permissao_e_recusado(make_request):
    """Sem ``pode_visualizar_questionario_terceiros``, ninguém abre o questionário alheio."""
    request = make_request()
    resposta = _chamar(request, _respondente(pode_ver_terceiros=False))
    assert resposta == 'REDIRECT', 'a view deixou passar o questionário de outra pessoa'


def test_questionario_de_terceiro_com_permissao_entra_como_previsualizacao(make_request):
    """Com a permissão, a view segue adiante — e em modo somente leitura."""
    request = make_request()
    respondente = _respondente(pode_ver_terceiros=True)
    montagem = {}

    def _montar(_request, dados_montagem):
        montagem.update(dados_montagem)
        raise RuntimeError('parar aqui: o que importa é o que chegou em dados_montagem')

    with patch.object(views, 'montar_formulario', side_effect=_montar):
        try:
            _chamar(request, respondente)
        except RuntimeError:
            pass

    assert montagem.get('eh_previsualizacao') is True, 'pré-visualização não foi propagada: carregaria e gravaria por cima das respostas alheias'
