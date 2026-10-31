import pytest

from comum.models import Pais
from comum.tests.factories import PrestadorServicoFactory
from pesquisa.forms import ColaboradorExternoForm
from pesquisa.models import ColaboradorExterno
from rh.enums import Nacionalidade
from rh.tests.factories import PessoaFisicaFactory, TitulacaoFactory, cpf_valido

pytestmark = pytest.mark.django_db


def _dados(titulacao_id: int, **extra: object) -> dict:
    return {
        'nome': 'Ana Estrangeira',
        'email': 'ana@exemplo.com',
        'telefone': '(84) 99999-9999',
        'titulacao': titulacao_id,
        'nacionalidade': Nacionalidade.ESTRANGEIRO,
        'passaporte': 'AB123456',
        **extra,
    }


def _colaborador(pais: Pais, n: int = 911) -> ColaboradorExterno:
    cpf = cpf_valido(n)
    pessoa = PessoaFisicaFactory(cpf=cpf, passaporte='AB123456', pais_origem=pais, nacionalidade=Nacionalidade.ESTRANGEIRO)
    prestador = PrestadorServicoFactory(pessoa_fisica=pessoa, matricula=cpf.replace('.', '').replace('-', ''))
    return ColaboradorExterno.objects.create(nome='Ana', prestador=prestador, email='ana@exemplo.com', titulacao=TitulacaoFactory())


def test_passaporte_do_mesmo_pais_de_outro_colaborador_e_recusado() -> None:
    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA')
    colaborador = _colaborador(argentina)

    form = ColaboradorExternoForm(data=_dados(colaborador.titulacao_id, pais_origem=argentina.pk))

    assert not form.is_valid()
    assert 'Este passaporte já está sendo usado por outro colaborador externo.' in form.errors['passaporte']


def test_edicao_do_proprio_colaborador_estrangeiro_nao_acusa_o_proprio_passaporte() -> None:
    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA')
    colaborador = _colaborador(argentina)

    form = ColaboradorExternoForm(data=_dados(colaborador.titulacao_id), instance=colaborador)

    assert form.is_valid(), form.errors


@pytest.mark.usefixtures('sem_unicidade_pessoa')
def test_colaborador_que_divide_o_passaporte_com_outro_continua_editavel() -> None:
    """Base legada, antes da deduplicação (Release 1), ainda pode ter o par país+passaporte repetido."""
    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA')
    colaborador = _colaborador(argentina)
    _colaborador(argentina, n=912)

    form = ColaboradorExternoForm(data=_dados(colaborador.titulacao_id, email='novo@exemplo.com'), instance=colaborador)

    assert form.is_valid(), form.errors
