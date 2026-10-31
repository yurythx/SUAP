"""O formulário de pessoa externa da saúde recusa, como erro do campo CPF, o documento que já é de outra pessoa."""

from datetime import date

import pytest

from rh.deduplicacao.entrada import MENSAGEM_OUTRA_PESSOA
from rh.models import PessoaFisica
from rh.tests.factories import PessoaFisicaFactory
from saude.forms import PessoaExternaForm

pytestmark = pytest.mark.django_db
CPF = '529.982.247-25'


def test_cpf_de_pessoa_com_outro_nascimento_vira_erro_do_campo() -> None:
    PessoaFisicaFactory(cpf=CPF, nascimento_data=date(1990, 1, 1))
    antes = PessoaFisica.objects.count()
    dados = {'nome': 'Ana Souza', 'cpf': CPF, 'sexo': 'F', 'nome_mae': 'Maria Souza'}

    divergente = PessoaExternaForm(data={**dados, 'nascimento_data': '01/01/1991'})
    mesma_pessoa = PessoaExternaForm(data={**dados, 'nascimento_data': '01/01/1990'})

    assert not divergente.is_valid()
    assert MENSAGEM_OUTRA_PESSOA in divergente.errors['cpf']
    mesma_pessoa.is_valid()
    assert MENSAGEM_OUTRA_PESSOA not in mesma_pessoa.errors.get('cpf', [])
    assert PessoaFisica.objects.count() == antes
