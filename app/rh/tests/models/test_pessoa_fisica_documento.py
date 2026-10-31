import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from comum.models import Pais, PessoaEndereco
from rh.models import PessoaFisica
from rh.tests.factories import PessoaFisicaFactory


@pytest.mark.usefixtures('sem_unicidade_pessoa')
def test_sem_unicidade_pessoa_permite_documento_repetido_e_nulo() -> None:
    a, b, c = PessoaFisicaFactory(), PessoaFisicaFactory(), PessoaFisicaFactory()

    PessoaFisica.objects.filter(pk__in=[a.pk, b.pk]).update(documento_identificador='529.982.247-25')
    PessoaFisica.objects.filter(pk=c.pk).update(documento_identificador=None)

    assert PessoaFisica.objects.filter(documento_identificador='529.982.247-25').count() == 2
    assert PessoaFisica.objects.filter(pk=c.pk, documento_identificador__isnull=True).exists()


@pytest.mark.usefixtures('sem_unicidade_pessoa')
def test_sem_unicidade_pessoa_derruba_a_check_de_pais() -> None:
    # linha legada: sem CPF, sem país, documento comum
    pessoa = PessoaFisicaFactory()

    PessoaFisica.objects.filter(pk=pessoa.pk).update(cpf=None, pais_origem=None, documento_identificador='X')

    assert PessoaFisica.objects.filter(pk=pessoa.pk, cpf__isnull=True, pais_origem__isnull=True, documento_identificador='X').exists()


@pytest.mark.django_db
def test_sem_cpf_exige_pais_ou_documento_sintetico() -> None:
    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA', iso_alfa3='ARG')
    PessoaFisicaFactory(cpf='529.982.247-25')
    estrangeira = PessoaFisicaFactory(cpf=None, passaporte='AB123456', pais_origem=argentina)

    with transaction.atomic(), pytest.raises(IntegrityError, match='pessoa_fisica_sem_cpf_exige_pais'):
        PessoaFisica.objects.filter(pk=estrangeira.pk).update(cpf=None, pais_origem=None, documento_identificador='X')


@pytest.mark.django_db
def test_save_formata_cpf_e_usa_como_documento() -> None:
    pessoa = PessoaFisicaFactory(cpf='52998224725')

    pessoa.refresh_from_db()
    assert pessoa.cpf == '529.982.247-25'
    assert pessoa.documento_identificador == '529.982.247-25'


@pytest.mark.django_db
def test_save_sem_cpf_usa_passaporte_com_iso_do_pais() -> None:
    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA', iso_alfa3='ARG')

    pessoa = PessoaFisicaFactory(cpf=None, passaporte=' ab 123456 ', pais_origem=argentina)

    pessoa.refresh_from_db()
    assert pessoa.passaporte == 'AB123456'
    assert pessoa.documento_identificador == 'ARG-AB123456'
    # a busca acha o estrangeiro pelo número, pela sigla do país ou pelo documento
    assert 'ARG-AB123456' in pessoa.search_fields_optimized


@pytest.mark.django_db
def test_pessoa_nova_com_pais_sem_iso_e_recusada() -> None:
    sem_iso = Pais.objects.create(codigo='005', nome='ALEMANHA ORIENTAL')

    with pytest.raises(ValidationError, match=r'País sem código ISO 3166-1 alfa-3; peça ao administrador para preencher em Países.'):
        PessoaFisicaFactory(cpf=None, passaporte='AB123456', pais_origem=sem_iso)


@pytest.mark.django_db
def test_pessoa_nova_com_cpf_e_pais_sem_iso_e_aceita() -> None:
    sem_iso = Pais.objects.create(codigo='005', nome='ALEMANHA ORIENTAL')

    pessoa = PessoaFisicaFactory(cpf='52998224725', passaporte='AB123456', pais_origem=sem_iso)

    assert pessoa.documento_identificador == '529.982.247-25'


@pytest.mark.django_db
def test_passaporte_sem_pais_nao_e_documento() -> None:
    with pytest.raises(ValidationError):
        PessoaFisica(nome='Estrangeira', passaporte='AB123456').save()


@pytest.mark.django_db
def test_save_nao_anula_cpf_com_dv_errado_do_legado() -> None:
    pessoa = PessoaFisicaFactory()
    PessoaFisica.objects.filter(pk=pessoa.pk).update(cpf='52998224724')  # legado: anular é decisão auditada da higiene

    pessoa = PessoaFisica.objects.get(pk=pessoa.pk)
    pessoa.nome = 'Outro Nome'
    pessoa.save()

    pessoa.refresh_from_db()
    assert pessoa.cpf == '529.982.247-24'


@pytest.mark.django_db
@pytest.mark.parametrize(
    'documentos',
    [{'cpf': '529.982.247-24'}, {'cpf': '111.111.111-11'}, {'passaporte': 'AAAAAA', 'pais': True}, {'passaporte': 'AB1', 'pais': True}],
)
def test_pessoa_nova_com_documento_invalido_e_recusada(documentos: dict) -> None:
    pais = Pais.objects.create(codigo='011', nome='ARGENTINA') if documentos.pop('pais', False) else None

    with pytest.raises(ValidationError):
        PessoaFisica(nome='Documento Inválido', pais_origem=pais, **documentos).save()


@pytest.mark.django_db
def test_pessoa_nova_sem_documento_e_recusada() -> None:
    with pytest.raises(ValidationError):
        PessoaFisica(nome='Sem Documento').save()


@pytest.mark.django_db
def test_pessoa_legada_sem_documento_continua_salvavel(sem_unicidade_pessoa: None) -> None:
    pessoa = PessoaFisicaFactory()
    PessoaFisica.objects.filter(pk=pessoa.pk).update(cpf=None, passaporte=None, documento_identificador='SEMDOC-1')

    pessoa = PessoaFisica.objects.get(pk=pessoa.pk)
    pessoa.nome_mae = 'Maria'
    pessoa.save()

    pessoa.refresh_from_db()
    assert pessoa.documento_identificador == f'SEMDOC-{pessoa.pk}'


@pytest.mark.django_db
def test_pessoa_existente_que_perde_o_documento_ganha_sintetico() -> None:
    pessoa = PessoaFisicaFactory(cpf='529.982.247-25')

    pessoa.cpf = None
    pessoa.save()

    pessoa.refresh_from_db()
    assert pessoa.documento_identificador == f'SEMDOC-{pessoa.pk}'


@pytest.mark.django_db
def test_corrigir_documento_troca_o_sintetico(sem_unicidade_pessoa: None) -> None:
    pessoa = PessoaFisicaFactory()
    PessoaFisica.objects.filter(pk=pessoa.pk).update(cpf=None, documento_identificador='CONFLITO-1-529.982.247-25')

    pessoa = PessoaFisica.objects.get(pk=pessoa.pk)
    pessoa.cpf = '390.533.447-05'
    pessoa.save()

    pessoa.refresh_from_db()
    assert pessoa.documento_identificador == '390.533.447-05'


@pytest.mark.django_db
def test_endereco_e_o_mais_recente() -> None:
    pessoa = PessoaFisicaFactory()
    PessoaEndereco.objects.create(pessoa=pessoa, logradouro='Rua Antiga')
    PessoaEndereco.objects.create(pessoa=pessoa, logradouro='Rua Nova')

    assert pessoa.pessoaendereco.logradouro == 'Rua Nova'


def test_save_com_usernames_alem_do_limite_cabe_na_busca(db: None) -> None:
    from django.contrib.contenttypes.models import ContentType

    from comum.models import Vinculo
    from comum.tests.factories import UserFactory
    from rh.models import PessoaExterna

    # a sobrevivente de uma mescla grande recebe os vínculos de todas as perdedoras
    pessoa = PessoaFisicaFactory(cpf='529.982.247-25')
    tipo = ContentType.objects.get_for_model(PessoaExterna)
    for n in range(9):
        Vinculo.objects.create(pessoa=pessoa, user=UserFactory(username=f'{"u" * 48}{n}'), tipo_relacionamento=tipo, id_relacionamento=n + 1)

    pessoa.save()

    pessoa.refresh_from_db()
    assert len(pessoa.search_fields_optimized) == 400
    assert '52998224725' in pessoa.search_fields_optimized  # a busca pelo CPF só com dígitos não é cortada
