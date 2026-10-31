"""O cadastro de professor externo recusa, como erro do campo CPF, o documento que já é de outra pessoa."""

from datetime import date

import pytest
from django.test import RequestFactory

from edu.forms import ProfessorExternoForm
from rh.deduplicacao.entrada import MENSAGEM_OUTRA_PESSOA
from rh.tests.factories import PessoaFisicaFactory

pytestmark = pytest.mark.django_db
CPF = '529.982.247-25'


def test_cpf_de_pessoa_com_outro_nascimento_vira_erro_do_campo() -> None:
    PessoaFisicaFactory(cpf=CPF, nascimento_data=date(1990, 1, 1))
    dados = {'nome': 'Ana Souza', 'cpf': CPF, 'nacionalidade': '1', 'sexo': 'F', 'email': 'ana@externo.com'}

    def formulario(nascimento: str) -> ProfessorExternoForm:
        data = {**dados, 'nascimento_data': nascimento}
        return ProfessorExternoForm(data=data, request=RequestFactory().post('/', data))

    divergente = formulario('01/01/1991')
    mesma_pessoa = formulario('01/01/1990')

    assert not divergente.is_valid()
    assert MENSAGEM_OUTRA_PESSOA in divergente.errors['cpf']
    mesma_pessoa.is_valid()
    assert MENSAGEM_OUTRA_PESSOA not in mesma_pessoa.errors.get('cpf', [])


@pytest.mark.usefixtures('sem_unicidade_pessoa')
def test_legado_sem_pais_com_o_mesmo_numero_bloqueia_o_estrangeiro_novo() -> None:
    """Base legada, antes da deduplicação (Release 1), ainda pode ter estrangeiro sem CPF e sem país. Sem o país do legado (login
    só o número) não dá para saber se é outra pessoa: o cadastro novo é recusado, não duplicado."""
    from comum.models import Pais, PrestadorServico, User
    from comum.tests.factories import PrestadorServicoFactory
    from rh.enums import Nacionalidade

    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA', iso_alfa3='ARG')
    pessoa = PessoaFisicaFactory(cpf='', passaporte='AB123456', pais_origem=argentina, nacionalidade=Nacionalidade.ESTRANGEIRO)
    legado = PrestadorServicoFactory(pessoa_fisica=pessoa)
    User.objects.filter(pk=legado.get_user().pk).update(username='AB123456')
    PrestadorServico.objects.filter(pk=legado.pk).update(matricula='AB123456')
    type(pessoa).objects.filter(pk=pessoa.pk).update(pais_origem=None)
    data = {
        'nome': 'Ana Estrangeira',
        'nacionalidade': str(Nacionalidade.ESTRANGEIRO),
        'passaporte': 'AB123456',
        'pais_origem': argentina.pk,
        'sexo': 'F',
        'email': 'ana@externo.com',
    }

    form = ProfessorExternoForm(data=data, request=RequestFactory().post('/', data))

    assert not form.is_valid()
    assert 'O usuário AB123456 já existe.' in form.errors['passaporte']


@pytest.mark.usefixtures('sync_permissions')
def test_edicao_de_professor_estrangeiro_le_os_documentos_somente_leitura() -> None:
    """Na edição, passaporte e nacionalidade não vêm no POST (somente leitura): a validação usa os do cadastro."""
    from comum.models import Pais
    from comum.tests.factories import PrestadorServicoFactory
    from edu.models import Professor
    from rh.enums import Nacionalidade

    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA', iso_alfa3='ARG')
    pessoa = PessoaFisicaFactory(cpf=None, passaporte='AB123456', pais_origem=argentina, nacionalidade=Nacionalidade.ESTRANGEIRO)
    professor = Professor.objects.create(vinculo=PrestadorServicoFactory(pessoa_fisica=pessoa).get_vinculo())
    data = {'nome': 'Ana Estrangeira', 'sexo': 'F', 'email': 'ana@externo.com', 'cpf': '529.982.247-25', 'passaporte': 'ZZ999999'}

    form = ProfessorExternoForm(data=data, instance=professor, request=RequestFactory().post('/', data))
    form.is_valid()

    assert 'passaporte' not in form.errors
    assert 'cpf' not in form.errors
    assert (form.cleaned_data['cpf'], form.cleaned_data['passaporte'], form['nacionalidade'].value()) == (None, 'AB123456', Nacionalidade.ESTRANGEIRO)
