"""Comando rodando depois da 4.0.0: schema com as constraints de documento, sem a fixture `sem_unicidade_pessoa`."""

from io import StringIO

import pytest
from django.core.management import call_command

from rh.models import PessoaFisica
from rh.tests.factories import PessoaFisicaFactory


@pytest.mark.django_db
@pytest.mark.usefixtures('pessoas_com_relacionamento')
def test_aplicar_anula_cpf_invalido_de_pf_sem_pais() -> None:
    # edição legada: o banco aceita CPF de DV inválido sem país, pois a CHECK só exige país quando o CPF é NULL
    pessoa = PessoaFisicaFactory()
    PessoaFisica.objects.filter(pk=pessoa.pk).update(cpf='529.982.247-24', documento_identificador='529.982.247-24', pais_origem=None)

    call_command('deduplicar_pessoas', 'planejar', stdout=StringIO())
    call_command('deduplicar_pessoas', 'aplicar', stdout=StringIO())

    pessoa.refresh_from_db()
    assert (pessoa.cpf, pessoa.documento_identificador) == (None, f'INVALIDO-{pessoa.pk}-52998224724')
