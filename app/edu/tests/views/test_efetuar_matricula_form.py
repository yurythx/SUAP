"""Recusa, no formulário de matrícula institucional, do documento que já pertence a outra pessoa."""

import datetime

import pytest
from django.core.exceptions import ValidationError
from django.http import QueryDict

from comum.models import Pais as PaisPessoa
from edu.forms.matriculas import EfetuarMatriculaForm
from edu.models import Pais
from rh.deduplicacao.entrada import MENSAGEM_OUTRA_PESSOA
from rh.tests.factories import PessoaFisicaFactory


def _submeter(**dados: str) -> EfetuarMatriculaForm:
    """Submete a etapa do wizard que contém o campo de maior etapa presente em ``dados``."""
    data = QueryDict(mutable=True)
    data.update(dados)
    form = EfetuarMatriculaForm(None, None, data=data)
    form.is_valid()
    return form


@pytest.mark.django_db
def test_cpf_de_pessoa_com_outro_nascimento_e_recusado_na_data_de_nascimento() -> None:
    pessoa = PessoaFisicaFactory(nascimento_data=datetime.date(1990, 1, 1))

    form = _submeter(nacionalidade='Brasileira', cpf=pessoa.cpf, nome='Fulano de Tal', data_nascimento='01/01/1991')

    assert MENSAGEM_OUTRA_PESSOA in form.errors.get('data_nascimento', [])


@pytest.mark.django_db
def test_passaporte_de_pessoa_com_outro_nascimento_e_recusado_no_pais_de_origem() -> None:
    PessoaFisicaFactory(
        cpf=None,
        passaporte='AB123456',
        pais_origem=PaisPessoa.objects.create(codigo='011', nome='ARGENTINA', iso_alfa3='ARG'),
        nascimento_data=datetime.date(1990, 1, 1),
    )
    argentina = Pais.objects.create(sigla='AR', nome='Argentina')

    form = _submeter(
        nacionalidade='Estrangeira', passaporte='AB123456', nome='Juan Perez Gomez', data_nascimento='01/01/1991', pais_origem=str(argentina.pk)
    )

    # a etapa do país esconde o fieldset da data de nascimento: a recusa tem de sair no campo visível
    assert MENSAGEM_OUTRA_PESSOA in form.errors.get('pais_origem', [])
    assert MENSAGEM_OUTRA_PESSOA not in form.errors.get('data_nascimento', [])


@pytest.mark.django_db
def test_passaporte_recusado_com_os_valores_crus_do_catalogo() -> None:
    """A matrícula pelo catálogo (``get_form`` do provedor) põe o pk do país em texto no ``cleaned_data`` e chama o ``clean_*`` direto."""
    PessoaFisicaFactory(
        cpf=None,
        passaporte='AB123456',
        pais_origem=PaisPessoa.objects.create(codigo='011', nome='ARGENTINA', iso_alfa3='ARG'),
        nascimento_data=datetime.date(1990, 1, 1),
    )
    argentina = Pais.objects.create(sigla='AR', nome='Argentina')
    form = EfetuarMatriculaForm(None, None)
    dados = {'nacionalidade': 'Estrangeira', 'passaporte': 'AB123456', 'data_nascimento': '1991-01-01', 'pais_origem': str(argentina.pk)}
    for campo, valor in dados.items():
        form.data[campo] = valor
        form.cleaned_data[campo] = valor

    with pytest.raises(ValidationError) as erro:
        form.clean_pais_origem()

    assert erro.value.messages == [MENSAGEM_OUTRA_PESSOA]
