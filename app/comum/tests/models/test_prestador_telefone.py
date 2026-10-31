"""O telefone do prestador chega como ``PessoaTelefoneCadastro`` (``{'numero': ...}``).

Os formulários de professor externo (edu) e avaliador externo (rh), entre outros, montam
esse dicionário; ``PrestadorServico.update_or_create`` precisa gravar só o número, e não o
dicionário inteiro em ``PessoaTelefone.numero``.
"""

from unittest.mock import patch

import pytest
from comum.models import PessoaTelefone, PrestadorServico
from comum.types import PrestadorServicoCadastro


def _cadastrar(numero: str) -> PrestadorServicoCadastro:
    return {
        'pessoa_fisica': {'cpf': '529.982.247-25', 'nome_registro': 'Fulano Externo'},
        'ativo': True,
        'telefone': {'numero': numero},
    }


@pytest.mark.django_db
def test_cadastro_grava_so_o_numero_do_telefone() -> None:
    with patch('comum.models.send_mail'), patch('comum.models.sync_ldap_user'), patch('comum.models.sync_ldap_setor'):
        retorno = PrestadorServico.update_or_create(_cadastrar('(84) 99999-0000'))

    assert retorno['telefone_created']
    assert retorno['telefone'].numero == '(84) 99999-0000'
    assert PessoaTelefone.objects.get(pessoa=retorno['pessoa_fisica']).numero == '(84) 99999-0000'


@pytest.mark.django_db
def test_novo_cadastro_atualiza_o_telefone_existente() -> None:
    with patch('comum.models.send_mail'), patch('comum.models.sync_ldap_user'), patch('comum.models.sync_ldap_setor'):
        PrestadorServico.update_or_create(_cadastrar('(84) 99999-0000'))
        retorno = PrestadorServico.update_or_create(_cadastrar('(84) 98888-1111'))

    assert not retorno['telefone_created']
    assert list(PessoaTelefone.objects.filter(pessoa=retorno['pessoa_fisica']).values_list('numero', flat=True)) == ['(84) 98888-1111']
