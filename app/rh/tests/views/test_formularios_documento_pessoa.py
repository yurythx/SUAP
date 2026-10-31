"""Formulários que criam pessoa recusam, como erro do campo CPF, o documento que já é de outra pessoa."""

from datetime import date

import pytest
from django.forms import modelform_factory

from rh.deduplicacao.entrada import MENSAGEM_OUTRA_PESSOA
from rh.forms import AvaliadorExternoForm, PessoaExternaForm, PessoaFisicaForm
from rh.models import PessoaFisica
from rh.tests.factories import PessoaFisicaFactory

pytestmark = pytest.mark.django_db
CPF = '529.982.247-25'


@pytest.mark.parametrize('formulario', [AvaliadorExternoForm, PessoaExternaForm])
def test_cpf_de_pessoa_com_outro_nascimento_vira_erro_do_campo(formulario: type) -> None:
    PessoaFisicaFactory(cpf=CPF, nascimento_data=date(1990, 1, 1))
    dados = {'nome': 'Ana Souza', 'cpf': CPF, 'email': 'ana@externo.com', 'numero_telefone': '(84) 99999-9999'}

    divergente = formulario(data={**dados, 'nascimento_data': '01/01/1991'})
    mesma_pessoa = formulario(data={**dados, 'nascimento_data': '01/01/1990'})

    assert not divergente.is_valid()
    assert MENSAGEM_OUTRA_PESSOA in divergente.errors['cpf']
    mesma_pessoa.is_valid()
    assert MENSAGEM_OUTRA_PESSOA not in mesma_pessoa.errors.get('cpf', [])


def test_pessoa_fisica_form_reconhece_cpf_legado_so_com_digitos() -> None:
    legado = PessoaFisicaFactory(cpf=CPF)
    PessoaFisica.objects.filter(pk=legado.pk).update(cpf='52998224725')

    form = PessoaFisicaForm(data={'nome': 'Ana Souza', 'cpf': CPF})

    assert not form.is_valid()
    assert 'Já existe uma pessoa física com este CPF.' in form.errors['cpf']


def test_avaliador_editando_o_proprio_cadastro_nao_e_recusado_pelo_nascimento() -> None:
    from django.test import RequestFactory

    from comum.tests.factories import PrestadorServicoFactory, UserFactory
    from rh.models import Avaliador

    prestador = PrestadorServicoFactory(matricula='52998224725', pessoa_fisica__cpf=CPF, pessoa_fisica__nascimento_data=date(1990, 1, 1))
    avaliador = Avaliador.objects.create(vinculo=prestador.get_vinculo())
    request = RequestFactory().post('/')
    request.user = UserFactory(is_superuser=True)  # com rh.eh_rh_sistemico o CPF é campo editável, não somente leitura
    dados = {'nome': 'Ana Souza', 'cpf': CPF, 'email': 'ana@externo.com', 'numero_telefone': '(84) 99999-9999', 'nascimento_data': '01/01/1991'}

    form = AvaliadorExternoForm(data=dados, instance=avaliador, request=request)
    form.is_valid()

    assert MENSAGEM_OUTRA_PESSOA not in form.errors.get('cpf', [])


def test_pessoa_fisica_form_com_duplicata_legada_edita_sem_trocar_o_cpf(sem_unicidade_pessoa: None) -> None:
    pessoa = PessoaFisicaFactory(cpf=CPF)
    PessoaFisicaFactory(cpf=CPF)
    outra = PessoaFisicaFactory()

    mesma = PessoaFisicaForm(data={'nome': 'Ana Souza', 'cpf': CPF}, instance=pessoa)
    trocando = PessoaFisicaForm(data={'nome': outra.nome, 'cpf': CPF}, instance=outra)
    mesma.is_valid()
    trocando.is_valid()

    assert 'Já existe uma pessoa física com este CPF.' not in mesma.errors.get('cpf', [])
    assert 'Já existe uma pessoa física com este CPF.' in trocando.errors['cpf']


def test_edicao_da_externa_recusa_trocar_o_cpf_da_pessoa_com_documento() -> None:
    from rh.models import PessoaExterna

    externa = PessoaExterna(cpf=CPF, nome='Ana Souza')
    externa.save()
    dados = {'nome': 'Ana Souza', 'sexo': 'F', 'email': 'ana@externo.com', 'cpf': '390.533.447-05'}

    form = PessoaExternaForm(data=dados, instance=externa)

    assert not form.is_valid()
    assert PessoaExterna.MENSAGEM_TROCA_DE_CPF in form.errors['cpf']
    externa.refresh_from_db()
    assert (externa.cpf, externa.pessoa_fisica.cpf) == (CPF, CPF)


def test_edicao_da_externa_legada_com_cpf_divergente_so_recusa_a_troca() -> None:
    from rh.models import PessoaExterna

    externa = PessoaExterna(cpf=CPF, nome='Ana Souza')
    externa.save()
    PessoaExterna.objects.filter(pk=externa.pk).update(cpf='390.533.447-05')  # legado: já divergia da PF antes da guarda
    externa = PessoaExterna.objects.get(pk=externa.pk)
    dados = {'nome': 'Ana Souza Lima', 'sexo': 'F', 'email': 'ana@externo.com', 'cpf': '390.533.447-05'}

    assert PessoaExternaForm(data=dados, instance=externa).is_valid()
    trocando = PessoaExternaForm(data={**dados, 'cpf': '111.444.777-35'}, instance=externa)
    assert not trocando.is_valid()
    assert PessoaExterna.MENSAGEM_TROCA_DE_CPF in trocando.errors['cpf']


def test_pessoa_fisica_form_recusa_passaporte_e_pais_de_outra_pessoa() -> None:
    from comum.models import Pais
    from rh.deduplicacao.entrada import MENSAGEM_PASSAPORTE_OUTRA_PESSOA

    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA', iso_alfa3='ARG')
    dona = PessoaFisicaFactory(cpf=None, passaporte='AB123456', pais_origem=argentina)
    outra = PessoaFisicaFactory(cpf=None, passaporte='CD654321', pais_origem=argentina)

    # os campos do PessoaFisicaAdmin.get_form: sem o país, vale o da instância
    formulario = modelform_factory(PessoaFisica, form=PessoaFisicaForm, fields=('nome', 'sexo', 'cpf', 'passaporte', 'nascimento_data'))
    trocando = formulario(data={'nome': outra.nome, 'cpf': CPF, 'passaporte': 'ab 123456'}, instance=outra)
    propria = formulario(data={'nome': dona.nome, 'cpf': '390.533.447-05', 'passaporte': 'ab 123456'}, instance=dona)
    trocando.is_valid()
    propria.is_valid()

    assert MENSAGEM_PASSAPORTE_OUTRA_PESSOA in trocando.errors['passaporte']
    assert 'passaporte' in propria.changed_data  # o mesmo passaporte noutro formato passa pela verificação
    assert MENSAGEM_PASSAPORTE_OUTRA_PESSOA not in propria.errors.get('passaporte', [])


def test_pessoa_fisica_form_sem_trocar_o_passaporte_edita_com_par_legado_repetido(sem_unicidade_pessoa: None) -> None:
    from comum.models import Pais
    from rh.deduplicacao.entrada import MENSAGEM_PASSAPORTE_OUTRA_PESSOA

    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA', iso_alfa3='ARG')
    pessoa = PessoaFisicaFactory(cpf=None, passaporte='AB123456', pais_origem=argentina)
    PessoaFisicaFactory(cpf=None, passaporte='AB123456', pais_origem=argentina)  # Release 1: o planejar ainda não separou
    formulario = modelform_factory(PessoaFisica, form=PessoaFisicaForm, fields=('nome', 'sexo', 'cpf', 'passaporte', 'nascimento_data'))

    form = formulario(data={'nome': 'Novo Nome', 'cpf': CPF, 'passaporte': 'AB123456'}, instance=pessoa)
    form.is_valid()

    assert MENSAGEM_PASSAPORTE_OUTRA_PESSOA not in form.errors.get('passaporte', [])


def test_prestador_legado_sem_documento_recebendo_cpf_de_outra_pessoa_vira_erro_do_campo() -> None:
    # cosinf/suap#17672: a PF do próprio login (legada, sem documento) não recebe o CPF que já é de outra PF; antes, 500 no save()
    from comum.models import Vinculo
    from comum.tests.factories import PrestadorServicoFactory, UserFactory

    prestador = PrestadorServicoFactory(matricula='52998224725', pessoa_fisica__cpf='111.444.777-35')
    Vinculo.objects.filter(pk=prestador.get_vinculo().pk).update(user=UserFactory(username='52998224725'))  # o login é o CPF
    PessoaFisica.objects.filter(pk=prestador.pessoa_fisica_id).update(cpf=None, documento_identificador=f'SEMDOC-{prestador.pessoa_fisica_id}')
    PessoaFisicaFactory(cpf=CPF)
    dados = {'nome': 'Ana Souza', 'cpf': CPF, 'email': 'ana@externo.com', 'numero_telefone': '(84) 99999-9999', 'nascimento_data': '01/01/1990'}

    form = AvaliadorExternoForm(data=dados)

    assert not form.is_valid()
    assert MENSAGEM_OUTRA_PESSOA in form.errors['cpf']
