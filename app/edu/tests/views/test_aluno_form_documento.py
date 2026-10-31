"""O formulário de aluno grava na pessoa física o passaporte e o país, que formam o documento do estrangeiro sem CPF."""

import pytest
from django.forms.models import model_to_dict

from comum.models import Configuracao, Pais
from edu.forms.alunos import AlunoForm
from edu.models import Aluno
from edu.tests.factories import AlunoFactory, CursoCampusFactory, PaisFactory
from rh.models import PessoaFisica
from rh.tests.factories import PessoaFisicaFactory

pytestmark = pytest.mark.django_db
PASSAPORTE = 'AQ669473'


@pytest.fixture
def colombia() -> Pais:
    return Pais.objects.create(codigo='169', nome='COLOMBIA', iso_alfa3='COL')


def _estrangeira_sem_pais(pais: Pais) -> Aluno:
    """A estrangeira legada sem país: a deduplicação deu a ela o sintético ``SEMPAIS-`` (a PF nova exige o país, por isso o update)."""
    pessoa = PessoaFisicaFactory(cpf=None, passaporte=PASSAPORTE, pais_origem=pais)
    PessoaFisica.objects.filter(pk=pessoa.pk).update(pais_origem=None, documento_identificador=f'SEMPAIS-{pessoa.pk}-{PASSAPORTE}')
    return AlunoFactory(pessoa_fisica_id=pessoa.pk, nacionalidade='Estrangeira', passaporte=PASSAPORTE, curso_campus=CursoCampusFactory())


def _enviar(aluno: Aluno, **dados: object) -> AlunoForm:
    # a edição parcial (aluno migrado) dispensa os obrigatórios: só o que o teste envia é conferido
    Configuracao.objects.create(app='edu', chave='permite_editar_parcialmente_alunos_migrados', valor='True', descricao='')
    aluno.codigo_academico = '1'
    pessoa = PessoaFisica.objects.get(pk=aluno.pessoa_fisica_id)
    campos = {'nome': pessoa.nome_registro, 'data_nascimento': pessoa.nascimento_data, 'sexo': pessoa.sexo}
    data = {campo: valor for campo, valor in {**model_to_dict(aluno), **campos, **dados}.items() if valor is not None}
    form = AlunoForm(data=data, instance=aluno)
    if form.is_valid():
        form.save()
    return form


def test_preencher_o_pais_corrige_o_documento_da_pessoa(colombia: Pais) -> None:
    aluno = _estrangeira_sem_pais(colombia)

    form = _enviar(aluno, pais_origem=PaisFactory(sigla='COL', nome='Colômbia').pk)

    assert form.errors == {}
    pessoa = PessoaFisica.objects.get(pk=aluno.pessoa_fisica_id)
    assert (pessoa.pais_origem, pessoa.documento_identificador) == (colombia, f'COL-{PASSAPORTE}')


def test_par_de_outra_pessoa_e_erro_do_passaporte(colombia: Pais) -> None:
    aluno = _estrangeira_sem_pais(colombia)
    PessoaFisicaFactory(cpf=None, passaporte=PASSAPORTE, pais_origem=colombia)

    form = _enviar(aluno, pais_origem=PaisFactory(sigla='COL', nome='Colômbia').pk)

    assert form.errors.get('passaporte') == ['Passaporte já pertence a outra pessoa']
    assert PessoaFisica.objects.get(pk=aluno.pessoa_fisica_id).documento_identificador.startswith('SEMPAIS-')
