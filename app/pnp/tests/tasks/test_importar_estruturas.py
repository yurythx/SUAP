import pytest

from pnp.models import EstruturaPNP
from pnp.tasks import importar_estruturas, normalizar
from rh.models import Setor, TipoUnidadeOrganizacional, UnidadeOrganizacional


def criar_uo(nome: str, sigla: str) -> UnidadeOrganizacional:
    tipo, _ = TipoUnidadeOrganizacional.objects.get_or_create(
        id=UnidadeOrganizacional.TIPO_CAMPUS_PRODUTIVO, defaults={'descricao': 'Campus Produtivo'}
    )
    setor = Setor.objects.create(nome=nome, sigla=sigla)
    return UnidadeOrganizacional.objects.create(nome=nome, sigla=sigla, setor=setor, tipo=tipo)


def test_normalizar_ignora_acento_pontuacao_e_caixa():
    assert normalizar('Campus Natal Central') == normalizar('CAMPUS NATAL - CENTRAL')
    assert normalizar('Campus Avançado Natal Zona Leste') == normalizar('CAMPUS AVANÇADO NATAL-ZONA LESTE')
    assert normalizar('Campus Apodi') != normalizar('Campus Caicó')


@pytest.mark.django_db
def test_importa_todas_as_linhas_vinculando_apenas_as_derivaveis():
    uo = criar_uo('CAMPUS NATAL - CENTRAL', 'CNAT')

    importar_estruturas([['26435.2408102.01.001', 'Campus Natal Central'], ['26435.9999999.01.001', 'Campus Inexistente']])

    vinculada = EstruturaPNP.objects.get(codigo='26435.2408102.01.001')
    assert (vinculada.uo, vinculada.nome) == (uo, 'Campus Natal Central')

    sem_unidade = EstruturaPNP.objects.get(codigo='26435.9999999.01.001')
    assert (sem_unidade.uo, sem_unidade.nome) == (None, 'Campus Inexistente')


@pytest.mark.django_db
def test_reimportacao_atualiza_o_nome_vindo_da_pnp():
    importar_estruturas([['26435.2401008.01.001', 'Campus Apodi']])

    importar_estruturas([['26435.2401008.01.001', 'Campus Apodi (RN)']])

    assert EstruturaPNP.objects.get().nome == 'Campus Apodi (RN)'


@pytest.mark.django_db
def test_reimportacao_nao_duplica_nem_desfaz_vinculo_manual():
    uo = criar_uo('REITORIA', 'RE')
    linhas = [['26435.2408102.05.001', 'Reitoria do Instituto Federal do Rio Grande do Norte']]
    importar_estruturas(linhas)

    # a unidade não foi derivada do nome, então o operador a informa pelo admin
    estrutura = EstruturaPNP.objects.get()
    estrutura.uo = uo
    estrutura.save()

    importar_estruturas(linhas)

    assert EstruturaPNP.objects.count() == 1
    assert EstruturaPNP.objects.get().uo == uo


@pytest.mark.django_db
def test_reimportacao_atualiza_o_vinculo_quando_a_unidade_passa_a_casar():
    importar_estruturas([['26435.2401008.01.001', 'Campus Apodi']])
    assert EstruturaPNP.objects.get().uo is None

    uo = criar_uo('CAMPUS APODI', 'AP')
    importar_estruturas([['26435.2401008.01.001', 'Campus Apodi']])

    assert EstruturaPNP.objects.count() == 1
    assert EstruturaPNP.objects.get().uo == uo


@pytest.mark.django_db
def test_nomes_ambiguos_sao_cadastrados_sem_unidade():
    criar_uo('CAMPUS APODI', 'AP1')
    criar_uo('Campus Apodi', 'AP2')

    importar_estruturas([['26435.2401008.01.001', 'Campus Apodi']])

    assert EstruturaPNP.objects.get().uo is None


@pytest.mark.django_db
def test_unidade_ja_vinculada_a_outro_codigo_nao_e_roubada():
    uo = criar_uo('CAMPUS APODI', 'AP')
    importar_estruturas([['26435.2401008.01.001', 'Campus Apodi']])

    importar_estruturas([['26435.2401008.01.002', 'Campus Apodi']])

    assert EstruturaPNP.objects.get(codigo='26435.2401008.01.001').uo == uo
    assert EstruturaPNP.objects.get(codigo='26435.2401008.01.002').uo is None
