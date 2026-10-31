"""Filtros de campus e setor dono da listagem de documentos (#16372).

O filtro de setor depende do de campus, e o recorte é feito no navegador (``admin/filter_setor_por_campus.html``): o
servidor entrega os setores de todos os campi, cada um com o id do seu campus, para que a lista
acompanhe o campus na hora — inclusive quando ele é limpo. O fluxo no navegador está em
``documento_eletronico/tests/e2e/test_04_filtros.py``.
"""

from __future__ import annotations

import re

import pytest
from django.test import Client

from rh.models import Setor
from rh.tests.factories import ServidorFactory, SetorFactory

pytestmark = pytest.mark.django_db

URL = '/admin/documento_eletronico/documentotexto/'


def _filtro(html: str, parametro: str) -> str:
    """O ``<select>`` do filtro ``parametro`` e o script que vem logo depois dele."""
    filtro = re.search(rf'<select[^>]*id="{parametro}_select".*?</script>', html, re.DOTALL)
    assert filtro, parametro
    return filtro.group(0)


def _campus_dos_setores(filtro: str) -> dict[str, str]:
    """``{valor da opção: data-campus}`` das opções de setor."""
    return {valor: campus for campus, valor in re.findall(r'data-campus="([^"]*)"\s*value="([^"]*)"', filtro)}


@pytest.mark.parametrize('com_campus', [False, True], ids=['sem_campus', 'com_campus_escolhido'])
def test_filtro_de_setor_traz_os_setores_de_todos_os_campi_com_o_seu_campus(client: Client, sync_permissions: None, com_campus: bool) -> None:
    setor_a, setor_b = SetorFactory(), SetorFactory()
    client.force_login(ServidorFactory(setor=setor_a).get_user())
    filtros = {'opcao': '1', 'setor_donouo': setor_a.uo_id} if com_campus else {'opcao': '1'}

    html = client.get(URL, filtros).content.decode()
    filtro = _filtro(html, 'setor_dono')

    esperado = {f'setor_dono={pk}': str(uo_id or '') for pk, uo_id in Setor.objects.suap().filter(excluido=False).values_list('pk', 'uo_id')}
    assert _campus_dos_setores(filtro) == esperado
    assert esperado[f'setor_dono={setor_b.pk}'] == str(setor_b.uo_id)
    # O setor depende do filtro de campus, que a página também traz.
    assert 'djtListFilterPorCampus("#setor_dono_select", "#setor_donouo_select")' in filtro
    assert f'value="setor_donouo={setor_b.uo_id}"' in _filtro(html, 'setor_donouo')
