"""Smoke de rota do nada consta — família que o behave nunca cobriu.

Os objetos vêm de ``seed_rotas.criar_nada_consta`` e ficam no aluno do smoke: o registro
aparece na aba "Nada Consta" do prontuário, que ``test_08_aluno`` inspeciona no aluno da
cadeia. Nenhum ``.get()`` da cadeia consulta estes models — verificado por grep antes de
escrever a fábrica.
"""

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

NADA_CONSTA = (
    '/edu/informar_responsaveis_nada_consta/{configuracao_nada_consta}/',
    # `avaliar_registro_nada_consta` fica de fora: `obj.pode_avaliar(request.user)` exige o
    # responsável cadastrado na configuração (403). Descoberta, não dispensada.
    '/edu/declaracao_item_nada_consta/{nada_consta}/',
    '/edu/revogar_registro_nada_consta/{nada_consta}/',
)


def test_rotas_de_nada_consta_abrem(abrir_rotas):
    abrir_rotas('admin_academico', NADA_CONSTA)
