import pytest

from edu.models import EixoTecnologico
from pnp.models import EixoPNP
from pnp.tasks import importar_eixos


@pytest.mark.django_db
def test_importa_eixos_e_subeixos_vinculando_apenas_os_deriveis():
    tecnologico = EixoTecnologico.objects.create(descricao='Informação e comunicação', codigo_inep='6')

    importar_eixos([['19', 'Informação e Comunicação'], ['1901', 'Informática']])

    eixo = EixoPNP.objects.get(codigo='19')
    assert (eixo.eixo_tecnologico, eixo.nome) == (tecnologico, 'Informação e Comunicação')

    subeixo = EixoPNP.objects.get(codigo='1901')
    assert (subeixo.eixo_tecnologico, subeixo.nome) == (None, 'Informática')


@pytest.mark.django_db
def test_o_codigo_da_pnp_nao_e_confundido_com_o_codigo_inep():
    """A PNP numera o eixo de infraestrutura como 20 e o INEP como 7; o vínculo é pelo nome."""
    tecnologico = EixoTecnologico.objects.create(descricao='Infraestrutura', codigo_inep='7')

    importar_eixos([['20', 'Infraestrutura']])

    assert EixoPNP.objects.get(codigo='20').eixo_tecnologico == tecnologico


@pytest.mark.django_db
def test_subeixos_de_mesmo_nome_em_eixos_diferentes_coexistem():
    importar_eixos([['1903', 'Comunicação'], ['2704', 'Comunicação']])

    assert EixoPNP.objects.filter(nome='Comunicação').count() == 2


@pytest.mark.django_db
def test_reimportacao_nao_duplica_e_atualiza_o_nome():
    tecnologico = EixoTecnologico.objects.create(descricao='Segurança', codigo_inep='13')
    importar_eixos([['31', 'Segurança']])

    importar_eixos([['31', 'SEGURANÇA']])

    registro = EixoPNP.objects.get()
    assert (registro.eixo_tecnologico, registro.nome) == (tecnologico, 'SEGURANÇA')


@pytest.mark.django_db
def test_eixo_tecnologico_ja_vinculado_a_outro_codigo_nao_e_roubado():
    tecnologico = EixoTecnologico.objects.create(descricao='Segurança', codigo_inep='13')
    EixoPNP.objects.create(codigo='outro-codigo', nome='OUTRO REGISTRO', eixo_tecnologico=tecnologico)

    importar_eixos([['31', 'Segurança']])

    assert EixoPNP.objects.get(codigo='31').eixo_tecnologico is None
    assert EixoPNP.objects.get(codigo='outro-codigo').eixo_tecnologico == tecnologico
