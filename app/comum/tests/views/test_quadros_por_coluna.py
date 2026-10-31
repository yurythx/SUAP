"""Testes das funções puras extraídas na refatoração dos quadros do index (sem KEYS Redis).

Cobrem a lógica de distribuição de quadros por coluna e o curto-circuito de cache
quando o Redis está desligado — comportamento reescrito nos commits que substituem
``cache.keys(...)`` por ``get_many``/``delete_pattern``.
"""

import pytest

from comum.views import _carregar_caches_quadros, _coluna_do_layout, _quadros_list_da_coluna


@pytest.mark.parametrize(
    ('coluna_num', 'esperado'),
    [(1, 'esquerda'), (2, 'centro'), (3, 'direita'), (99, 'direita'), (None, 'direita')],
)
def test_coluna_do_layout(coluna_num, esperado):
    assert _coluna_do_layout({'coluna': coluna_num}) == esperado


class TestQuadrosListDaColuna:
    def _layout(self, coluna, escondido=False):
        return {'coluna': coluna, 'escondido': escondido}

    def test_distribui_por_coluna(self):
        layouts = {'A': self._layout(1), 'B': self._layout(2), 'C': self._layout(3)}
        chaves = ['A', 'B', 'C']
        assert _quadros_list_da_coluna('esquerda', list(chaves), layouts) == ['A']
        assert _quadros_list_da_coluna('centro', list(chaves), layouts) == ['B']
        assert _quadros_list_da_coluna('direita', list(chaves), layouts) == ['C']

    def test_quadro_escondido_nao_aparece(self):
        layouts = {'A': self._layout(1, escondido=True)}
        assert _quadros_list_da_coluna('esquerda', ['A'], layouts) == []

    def test_quadro_sem_layout_cai_na_esquerda(self):
        # 'B' não tem layout salvo -> deve cair na esquerda, e só na esquerda
        layouts = {'A': self._layout(3)}
        assert _quadros_list_da_coluna('esquerda', ['A', 'B'], layouts) == ['B']
        assert _quadros_list_da_coluna('direita', ['A', 'B'], layouts) == ['A']

    def test_layout_vazio_conta_como_sem_layout(self):
        # quadro_layout falsy (None/{}) não é "visível", mas ainda é removido dos restantes
        layouts = {'A': None}
        assert _quadros_list_da_coluna('esquerda', ['A'], layouts) == []

    def test_nao_muta_a_lista_de_chaves_recebida(self):
        chaves = ['A', 'B']
        _quadros_list_da_coluna('esquerda', chaves, {'A': self._layout(1)})
        assert chaves == ['A', 'B']


def test_carregar_caches_sem_redis_retorna_dicts_vazios(settings):
    # Sob pytest o Redis é forçado off; a função deve curto-circuitar sem tocar request.
    settings.USE_REDIS = False
    assert _carregar_caches_quadros(None, ['A', 'B']) == ({}, {})


@pytest.mark.usefixtures('atores')
class TestMeusQuadrosView:
    def test_retorna_json_com_as_tres_colunas(self, client):
        client.login(username=self.servidor_a.get_user().username, password='123')
        response = client.get('/comum/index/meus_quadros/')
        assert response.status_code == 200
        assert response['Content-Type'] == 'application/json'
        assert set(response.json()) == {'esquerda', 'centro', 'direita'}
