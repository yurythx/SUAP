"""O formulário do admin de profissional liberal recusa, como erro do campo CPF, o documento que já é de outra pessoa."""

from datetime import date

import pytest

from convenios.forms import ProfissionalLiberalForm
from rh.deduplicacao.entrada import MENSAGEM_OUTRA_PESSOA
from rh.tests.factories import PessoaFisicaFactory

pytestmark = pytest.mark.django_db
CPF = '529.982.247-25'


def test_cpf_de_pessoa_com_outro_nascimento_vira_erro_do_campo() -> None:
    PessoaFisicaFactory(cpf=CPF, nascimento_data=date(1990, 1, 1))
    dados = {'nome': 'Ana Souza', 'cpf': CPF, 'sexo': 'F'}

    divergente = ProfissionalLiberalForm(data={**dados, 'nascimento_data': '01/01/1991'})
    mesma_pessoa = ProfissionalLiberalForm(data={**dados, 'nascimento_data': '01/01/1990'})

    assert not divergente.is_valid()
    assert divergente.errors['cpf'] == [MENSAGEM_OUTRA_PESSOA]
    mesma_pessoa.is_valid()
    assert MENSAGEM_OUTRA_PESSOA not in mesma_pessoa.errors.get('cpf', [])
