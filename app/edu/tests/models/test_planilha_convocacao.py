"""Importação da planilha de convocação da pré-matrícula internacional."""

import io

import pandas as pd
import pytest

from comum.models import JustificativaUsuarioExterno, Pais, PrestadorServico, User
from comum.tests.factories import PrestadorServicoFactory
from rh.models import PessoaFisica
from edu.models.internacionalizacao import _importar_convocado, _validar_planilha_convocacao

CABECALHO = 'PASSAPORTE,NOME_COMPLETO,DATA_NASCIMENTO,SEXO,EMAIL,PAIS,CIDADE_NASCIMENTO,CIDADE_RESIDENCIA'


@pytest.mark.parametrize(
    ('passaporte', 'pais', 'coluna'),
    [
        ('AB123456', '', 'PAIS'),
        ('AB123456', '"   "', 'PAIS'),
        ('', 'Argentina', 'PASSAPORTE'),
        ('"   "', 'Argentina', 'PASSAPORTE'),
    ],
)
def test_celula_vazia_na_planilha_aponta_a_linha(passaporte: str, pais: str, coluna: str) -> None:
    planilha = pd.read_csv(
        io.StringIO(f'{CABECALHO}\n{passaporte},Juan Perez Gomez,01/01/1990,M,juan@exemplo.com,{pais},Rosario,Rosario\n'),
        dtype=str,
    )

    with pytest.raises(ValueError, match=f'"{coluna}" contém valor vazio na linha 2'):
        _validar_planilha_convocacao(planilha)


@pytest.mark.django_db
def test_passaporte_com_espacos_reusa_o_prestador_do_convocado() -> None:
    JustificativaUsuarioExterno.objects.create(justificativa='Convocado internacional', ativo=True)
    justificativa = JustificativaUsuarioExterno.objects.first()  # a mesma que `processar` usa
    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA', iso_alfa3='ARG')
    linha = {'NOME_COMPLETO': 'Juan Perez Gomez', 'DATA_NASCIMENTO': '01/01/1990', 'SEXO': 'M', 'EMAIL': 'juan@exemplo.com'}
    _importar_convocado({**linha, 'PASSAPORTE': 'AB123456'}, argentina, justificativa)

    _importar_convocado({**linha, 'PASSAPORTE': 'ab 123 456'}, argentina, justificativa)

    assert PrestadorServico.objects.filter(pessoa_fisica__passaporte='AB123456').count() == 1


@pytest.mark.django_db
def test_passaporte_vazio_nao_casa_prestador_sem_passaporte() -> None:
    JustificativaUsuarioExterno.objects.create(justificativa='Convocado internacional', ativo=True)
    justificativa = JustificativaUsuarioExterno.objects.first()
    brasileiro = PrestadorServicoFactory(pessoa_fisica__passaporte=None, justificativa_cadastro=justificativa)
    linha = {'NOME_COMPLETO': 'Juan Perez Gomez', 'DATA_NASCIMENTO': '01/01/1990', 'SEXO': 'M', 'EMAIL': 'juan@exemplo.com', 'PASSAPORTE': '   '}

    with pytest.raises(ValueError):
        _importar_convocado(linha, Pais.objects.create(codigo='011', nome='ARGENTINA'), justificativa)

    brasileiro.pessoa_fisica.refresh_from_db()
    assert brasileiro.pessoa_fisica.nome != 'Juan Perez Gomez'


@pytest.mark.django_db
def test_mesmo_passaporte_de_outro_pais_nao_sobrescreve_o_outro_convocado() -> None:
    JustificativaUsuarioExterno.objects.create(justificativa='Convocado internacional', ativo=True)
    justificativa = JustificativaUsuarioExterno.objects.first()
    chile, argentina = (
        Pais.objects.create(codigo='013', nome='CHILE', iso_alfa3='CHL'),
        Pais.objects.create(codigo='011', nome='ARGENTINA', iso_alfa3='ARG'),
    )
    linha = {'DATA_NASCIMENTO': '01/01/1990', 'SEXO': 'M', 'EMAIL': 'x@exemplo.com', 'PASSAPORTE': 'AB123456'}
    _importar_convocado({**linha, 'NOME_COMPLETO': 'Pedro Chileno'}, chile, justificativa)

    # o login é a chave ISO + passaporte: o de outro país é outra pessoa, com outro login
    _importar_convocado({**linha, 'NOME_COMPLETO': 'Juan Argentino'}, argentina, justificativa)

    convocados = PrestadorServico.objects.filter(pessoa_fisica__passaporte='AB123456').order_by('matricula')
    assert [(p.matricula, p.pessoa_fisica.nome, p.pessoa_fisica.pais_origem) for p in convocados] == [
        ('ARG-AB123456', 'Juan Argentino', argentina),
        ('CHL-AB123456', 'Pedro Chileno', chile),
    ]


@pytest.mark.usefixtures('sem_unicidade_pessoa')
def test_convocado_legado_sem_pais_e_reusado_e_ganha_o_pais() -> None:
    """Base legada, antes da deduplicação (Release 1), ainda pode ter estrangeiro sem país nem documento identificador."""
    JustificativaUsuarioExterno.objects.create(justificativa='Convocado internacional', ativo=True)
    justificativa = JustificativaUsuarioExterno.objects.first()
    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA', iso_alfa3='ARG')
    linha = {'NOME_COMPLETO': 'Juan Perez Gomez', 'DATA_NASCIMENTO': '01/01/1990', 'SEXO': 'M', 'EMAIL': 'juan@exemplo.com', 'PASSAPORTE': 'AB123456'}
    _importar_convocado(linha, argentina, justificativa)
    # cadastro de antes do país: login só com o número
    legado = PrestadorServico.objects.get()
    User.objects.filter(pk=legado.get_user().pk).update(username='AB123456')
    PrestadorServico.objects.filter(pk=legado.pk).update(matricula='AB123456')
    PessoaFisica.objects.filter(pk=legado.pessoa_fisica_id).update(pais_origem=None, documento_identificador=None)

    _importar_convocado(linha, argentina, justificativa)

    assert list(PrestadorServico.objects.filter(matricula__iexact='AB123456')) == [legado]
    pessoa = PessoaFisica.objects.get(pk=legado.pessoa_fisica_id)
    assert (pessoa.pais_origem, pessoa.documento_identificador) == (argentina, 'ARG-AB123456')


@pytest.mark.django_db
def test_convocado_legado_sem_pais_ambiguo_e_recusado() -> None:
    from rh.tests.factories import PessoaFisicaFactory, cpf_valido

    JustificativaUsuarioExterno.objects.create(justificativa='Convocado internacional', ativo=True)
    justificativa = JustificativaUsuarioExterno.objects.first()
    for n in (1, 2):
        cpf = cpf_valido(n)
        pessoa = PessoaFisicaFactory(cpf=cpf, passaporte='AB123456')
        PrestadorServicoFactory(matricula=''.join(filter(str.isdigit, cpf)), pessoa_fisica=pessoa, justificativa_cadastro=justificativa)
    linha = {'NOME_COMPLETO': 'Juan Perez Gomez', 'DATA_NASCIMENTO': '01/01/1990', 'SEXO': 'M', 'EMAIL': 'juan@exemplo.com', 'PASSAPORTE': 'AB123456'}

    with pytest.raises(ValueError, match='mais de um'):
        _importar_convocado(linha, Pais.objects.create(codigo='011', nome='ARGENTINA'), justificativa)
