import pytest

from pnp.models import AreaTematicaPNP
from pnp.tasks import importar_areas_tematicas, normalizar_codigo_area
from rh.models import AreaConhecimento


def test_normalizar_codigo_area_converte_para_o_formato_do_suap():
    assert normalizar_codigo_area('1.03.00.00-7') == '10300007'
    assert normalizar_codigo_area('8.03.05.03-2') == '80305032'


@pytest.mark.django_db
def test_importa_todas_as_linhas_vinculando_apenas_as_derivaveis():
    area = AreaConhecimento.objects.create(codigo='10300007', descricao='CIÊNCIA DA COMPUTAÇÃO')

    importar_areas_tematicas([['1.03.00.00-7', 'Ciência da Computação'], ['9.23.00.00-6', 'Secretariado Executivo']])

    vinculada = AreaTematicaPNP.objects.get(codigo='1.03.00.00-7')
    assert (vinculada.area, vinculada.nome) == (area, 'Ciência da Computação')

    assert AreaTematicaPNP.objects.get(codigo='9.23.00.00-6').area is None


@pytest.mark.django_db
def test_reimportacao_nao_duplica_e_atualiza_o_nome():
    area = AreaConhecimento.objects.create(codigo='10300007', descricao='CIÊNCIA DA COMPUTAÇÃO')
    importar_areas_tematicas([['1.03.00.00-7', 'Ciência da Computação']])

    importar_areas_tematicas([['1.03.00.00-7', 'Ciências da Computação']])

    registro = AreaTematicaPNP.objects.get()
    assert (registro.area, registro.nome) == (area, 'Ciências da Computação')


@pytest.mark.django_db
def test_area_do_conhecimento_e_vinculada_quando_passa_a_existir():
    importar_areas_tematicas([['1.03.00.00-7', 'Ciência da Computação']])
    assert AreaTematicaPNP.objects.get().area is None

    area = AreaConhecimento.objects.create(codigo='10300007', descricao='CIÊNCIA DA COMPUTAÇÃO')
    importar_areas_tematicas([['1.03.00.00-7', 'Ciência da Computação']])

    assert AreaTematicaPNP.objects.get().area == area


@pytest.mark.django_db
def test_area_ja_vinculada_a_outro_codigo_nao_e_roubada():
    area = AreaConhecimento.objects.create(codigo='10300007', descricao='CIÊNCIA DA COMPUTAÇÃO')
    AreaTematicaPNP.objects.create(codigo='outro-codigo', nome='OUTRO REGISTRO', area=area)

    importar_areas_tematicas([['1.03.00.00-7', 'Ciência da Computação']])

    assert AreaTematicaPNP.objects.get(codigo='1.03.00.00-7').area is None
    assert AreaTematicaPNP.objects.get(codigo='outro-codigo').area == area
