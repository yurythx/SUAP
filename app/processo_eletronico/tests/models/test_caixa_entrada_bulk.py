"""Testes do cache bulk de ``Processo.esta_na_caixa_entrada``.

O cache colapsa N ``EXISTS`` (um por processo) em uma única consulta base por
chave ``(setores, user, recebido)``, mas só no render GET da view
``caixa_processos``. Fora desse escopo o método recai no ``.exists()`` ao vivo.

Lógica pura (gate + memoização) validada com mocks, sem tocar o banco.
"""

from types import SimpleNamespace
from unittest import mock

from processo_eletronico import models as m
from processo_eletronico.models import Processo, Tramite

MODELS = 'processo_eletronico.models'


class FakeCaixaQS:
    """Queryset fake de ``get_caixa_entrada`` que conta as filtragens aplicadas."""

    def __init__(self, ids):
        self._ids = list(ids)
        self._processo = None

    def filter(self, **kwargs):
        if 'processo' in kwargs:
            self._processo = kwargs['processo']
        return self

    def values_list(self, field, flat=False):
        assert field == 'processo_id'
        return list(self._ids)

    def exists(self):
        return self._processo is not None and self._processo.pk in self._ids


def _processo(pk):
    p = Processo()
    p.pk = pk
    return p


def _request_caixa():
    return SimpleNamespace(method='GET', resolver_match=SimpleNamespace(url_name='caixa_processos'))


def _setores():
    return [SimpleNamespace(pk=2316), SimpleNamespace(pk=781)]


def test_bulk_colapsa_em_uma_consulta_e_acerta_pertinencia():
    """Sob o gate, N processos => 1 chamada a get_caixa_entrada; pertinência correta."""
    fake = FakeCaixaQS(ids=[10, 20])
    user = SimpleNamespace(id=1524414)
    with (
        mock.patch(f'{MODELS}.get_request', return_value=_request_caixa()),
        mock.patch(f'{MODELS}.get_user', return_value=user),
        mock.patch.object(Tramite, 'get_caixa_entrada', return_value=fake) as gce,
    ):
        setores = _setores()
        assert _processo(10).esta_na_caixa_entrada(setores=setores, user=user, recebido=True) is True
        assert _processo(20).esta_na_caixa_entrada(setores=setores, user=user, recebido=True) is True
        assert _processo(99).esta_na_caixa_entrada(setores=setores, user=user, recebido=True) is False
        # Uma única consulta base para os 3 processos (mesma chave de cache).
        assert gce.call_count == 1


def test_chave_distinta_por_recebido_refaz_consulta():
    """Chaves (setores,user,recebido) distintas não compartilham cache."""
    fake = FakeCaixaQS(ids=[10])
    user = SimpleNamespace(id=1)
    with (
        mock.patch(f'{MODELS}.get_request', return_value=_request_caixa()),
        mock.patch(f'{MODELS}.get_user', return_value=user),
        mock.patch.object(Tramite, 'get_caixa_entrada', return_value=fake) as gce,
    ):
        setores = _setores()
        _processo(10).esta_na_caixa_entrada(setores=setores, user=user, recebido=True)
        _processo(10).esta_na_caixa_entrada(setores=setores, user=user, recebido=False)
        assert gce.call_count == 2


def test_fora_do_gate_recai_no_exists():
    """Sem request (shell/celery) usa o caminho .exists() ao vivo, não o cache."""
    fake = FakeCaixaQS(ids=[10])
    user = SimpleNamespace(id=1)
    with (
        mock.patch(f'{MODELS}.get_request', return_value=None),
        mock.patch.object(Tramite, 'get_caixa_entrada', return_value=fake) as gce,
    ):
        assert _processo(10).esta_na_caixa_entrada(setores=_setores(), user=user, recebido=True) is True
        assert _processo(99).esta_na_caixa_entrada(setores=_setores(), user=user, recebido=True) is False
        assert gce.call_count == 2  # uma query por processo (sem bulk)


def test_gate_ignora_outras_views_e_metodos():
    """POST, ou GET em outra view, não ativam o bulk (evita staleness intra-request)."""
    fake = FakeCaixaQS(ids=[10])
    user = SimpleNamespace(id=1)
    cenarios = [
        SimpleNamespace(method='POST', resolver_match=SimpleNamespace(url_name='caixa_processos')),
        SimpleNamespace(method='GET', resolver_match=SimpleNamespace(url_name='encaminhar_processo')),
        SimpleNamespace(method='GET', resolver_match=None),
    ]
    for req in cenarios:
        with (
            mock.patch(f'{MODELS}.get_request', return_value=req),
            mock.patch.object(Tramite, 'get_caixa_entrada', return_value=fake) as gce,
        ):
            _processo(10).esta_na_caixa_entrada(setores=_setores(), user=user, recebido=True)
            _processo(20).esta_na_caixa_entrada(setores=_setores(), user=user, recebido=True)
            assert gce.call_count == 2  # fallback .exists() por processo, sem cache


def _chain_values_list(valores):
    """MagicMock encadeável (filter/exclude/values_list) que devolve ``valores``."""
    chain = mock.MagicMock()
    chain.filter.return_value = chain
    chain.exclude.return_value = chain
    chain.values_list.return_value = list(valores)
    return chain


def test_documento_pendente_bulk_colapsa_e_acerta():
    """#3: tem_documento_pendente sob o gate => 1 query para N processos; pertinência correta."""
    chain = _chain_values_list([10, 20])
    with (
        mock.patch(f'{MODELS}.get_request', return_value=_request_caixa()),
        mock.patch.object(m.DocumentoTextoProcesso, 'objects', chain),
    ):
        assert _processo(10).tem_documento_pendente() is True
        assert _processo(20).tem_documento_pendente() is True
        assert _processo(99).tem_documento_pendente() is False
        assert chain.filter.call_count == 1  # consulta base única (cache por request)


def test_retorno_pendente_bulk_colapsa_e_acerta():
    """#2: eh_resposta_retorno_programado sob o gate => 1 query para N trâmites; pertinência correta."""
    chain = _chain_values_list([10, 20])

    def _tramite(processo_id):
        t = Tramite()
        t.processo_id = processo_id
        return t

    with (
        mock.patch(f'{MODELS}.get_request', return_value=_request_caixa()),
        mock.patch.object(m.TramiteRetornoProgramado, 'objects', chain),
    ):
        assert _tramite(10).eh_resposta_retorno_programado is True
        assert _tramite(20).eh_resposta_retorno_programado is True
        assert _tramite(99).eh_resposta_retorno_programado is False
        assert chain.filter.call_count == 1
