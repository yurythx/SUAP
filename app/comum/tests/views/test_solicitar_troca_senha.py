import pytest

from comum.forms import SoliticarTrocarSenhaForm
from comum.models import Pais
from comum.tests.factories import PrestadorServicoFactory
from rh.enums import Nacionalidade
from rh.tests.factories import PessoaFisicaFactory

pytestmark = pytest.mark.django_db


def _form(username: str, cpf_passaporte: str) -> SoliticarTrocarSenhaForm:
    form = SoliticarTrocarSenhaForm(data={'username': username, 'cpf_passaporte': cpf_passaporte})
    del form.fields['recaptcha']
    return form


def test_estrangeiro_acha_o_usuario_pelo_passaporte_com_pontuacao() -> None:
    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA', iso_alfa3='ARG')
    pessoa = PessoaFisicaFactory(cpf=None, passaporte='AB123456', pais_origem=argentina, nacionalidade=Nacionalidade.ESTRANGEIRO)
    prestador = PrestadorServicoFactory(pessoa_fisica=pessoa)

    form = _form(prestador.matricula, 'ab-123.456')

    form.is_valid()
    assert 'Nenhum usuário encontrado com os dados especificados.' not in form.non_field_errors()


def test_passaporte_so_com_pontuacao_nao_casa_usuario_sem_passaporte() -> None:
    """``passaporte=None`` viraria ``IS NULL`` e casaria qualquer usuário sem passaporte."""
    prestador = PrestadorServicoFactory()

    form = _form(prestador.matricula, '---')

    assert not form.is_valid()
    assert 'Nenhum usuário encontrado com os dados especificados.' in form.non_field_errors()
