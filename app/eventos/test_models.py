from types import SimpleNamespace
from unittest.mock import Mock, patch

from eventos.models import Evento


def _mock_queryset(exists: bool) -> Mock:
    queryset = Mock()
    queryset.exists.return_value = exists
    return queryset


def test_pode_avaliar_retorna_true_para_avaliador_sistemico_sem_consultar_uo() -> None:
    evento = SimpleNamespace(dimensoes=Mock(), campus=object())
    user = Mock()
    user.groups.filter.return_value = _mock_queryset(True)

    with patch('eventos.models.get_uo') as get_uo:
        assert Evento.pode_avaliar(evento, user) is True

    get_uo.assert_not_called()


def test_pode_avaliar_retorna_false_para_avaliador_local_sem_uo() -> None:
    evento = SimpleNamespace(dimensoes=Mock(), campus=object())
    user = Mock()
    user.groups.filter.side_effect = [_mock_queryset(False), _mock_queryset(True)]

    with patch('eventos.models.get_uo', return_value=None):
        assert Evento.pode_avaliar(evento, user) is False


def test_pode_avaliar_retorna_true_para_avaliador_local_do_campus() -> None:
    campus = object()
    evento = SimpleNamespace(dimensoes=Mock(), campus=campus)
    user = Mock()
    user.groups.filter.side_effect = [_mock_queryset(False), _mock_queryset(True)]

    with patch('eventos.models.get_uo', return_value=campus):
        assert Evento.pode_avaliar(evento, user) is True
