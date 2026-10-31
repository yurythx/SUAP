"""Checagem do gate de paridade (``bin/scripts/paridade_e2e.py``), sem banco e sem Django.

Monta um módulo falso em ``tmp_path`` com uma ``.feature`` e um teste marcado, e afirma o
comportamento que autoriza uma deleção irreversível: cenário comentado fora do denominador,
homônimo colapsando em 1, dispensa com motivo saindo dos órfãos, e teste vermelho no junit
derrubando TODOS os cenários que ele declara.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'bin' / 'scripts'))

import paridade_e2e


def _montar_modulo(raiz: Path, feature: str, teste: str = '', conftest: str = '') -> None:
    (raiz / 'features').mkdir(parents=True)
    (raiz / 'features' / '001.x.feature').write_text(feature, encoding='utf-8')
    (raiz / 'tests' / 'e2e').mkdir(parents=True)
    if teste:
        (raiz / 'tests' / 'e2e' / 'test_x.py').write_text(teste, encoding='utf-8')
    if conftest:
        (raiz / 'tests' / 'e2e' / 'conftest.py').write_text(conftest, encoding='utf-8')


FEATURE = """
Funcionalidade: X
  Cenário: Cadastrar
  Cenário: Sai do sistema
  Cenário: Sai do sistema
#  Cenário: Comentado
  Esquema do Cenário: Variantes
    Exemplos:
      | a |
      | 1 |
"""


def test_denominador_ignora_comentado_e_colapsa_homonimo(tmp_path, monkeypatch):
    _montar_modulo(tmp_path / 'mod', FEATURE)
    monkeypatch.chdir(tmp_path)
    ativos = paridade_e2e.cenarios_ativos('mod')

    nomes = sorted(nome for _, nome in ativos)
    assert nomes == ['Cadastrar', 'Sai do sistema', 'Variantes'], nomes
    assert [vezes for chave, vezes in ativos.items() if chave[1] == 'Sai do sistema'] == [2]


def test_marcador_cobre_e_dispensa_tira_do_orfao(tmp_path, monkeypatch):
    teste = """
import pytest


@pytest.mark.cenario('mod/features/001.x.feature', 'Cadastrar', 'Variantes')
def test_ciclo():
    pass
"""
    conftest = """
CENARIOS_DISPENSADOS = {('mod/features/001.x.feature', 'Sai do sistema'): 'contexto novo por teste'}
"""
    _montar_modulo(tmp_path / 'mod', FEATURE, teste, conftest)
    monkeypatch.chdir(tmp_path)

    assert len(paridade_e2e.marcadores('mod')) == 2
    assert paridade_e2e.dispensas('mod') == {('mod/features/001.x.feature', 'Sai do sistema'): 'contexto novo por teste'}
    assert paridade_e2e.relatar('mod', None) == 0, 'sem órfãos, o gate tem de fechar'


def test_modo_rotas_casa_parametro_e_respeita_dispensa(tmp_path, monkeypatch):
    """Modo 2: rota com `<int:pk>` casa com a URL concreta do teste; dispensa sai das descobertas."""
    raiz = tmp_path / 'mod'
    _montar_modulo(raiz, FEATURE)
    (raiz / 'urls.py').write_text(
        "from django.urls import path\nurlpatterns = [path('listar/', 1), path('editar/<int:pk>/', 2), path('relatorio/', 3)]\n",
        encoding='utf-8',
    )
    (raiz / 'tests' / 'e2e' / 'test_x.py').write_text("LISTA = '/mod/listar/'\n\n\ndef test_a():\n    ir('/mod/editar/7/')\n", encoding='utf-8')
    (raiz / 'tests' / 'e2e' / 'conftest.py').write_text(
        "ROTAS_DISPENSADAS = {'/mod/relatorio/': 'gera PDF, sem asserção pela UI'}\n", encoding='utf-8'
    )
    monkeypatch.chdir(tmp_path)

    assert set(paridade_e2e.rotas_do_modulo('mod')) == {'/mod/listar/', '/mod/editar/<int:pk>/', '/mod/relatorio/'}
    assert paridade_e2e.urls_nos_testes('mod') == {'/mod/listar/', '/mod/editar/7/'}
    assert paridade_e2e.relatar_rotas('mod') == 0, 'duas rotas cobertas e uma dispensada: o gate fecha'


def test_modo_rotas_reprova_rota_sem_teste(tmp_path, monkeypatch):
    raiz = tmp_path / 'mod'
    _montar_modulo(raiz, FEATURE)
    (raiz / 'urls.py').write_text("from django.urls import path\nurlpatterns = [path('esquecida/', 1)]\n", encoding='utf-8')
    monkeypatch.chdir(tmp_path)

    assert paridade_e2e.relatar_rotas('mod') == 1


def test_teste_vermelho_derruba_todos_os_cenarios_que_declara(tmp_path, monkeypatch):
    teste = """
import pytest


@pytest.mark.cenario('mod/features/001.x.feature', 'Cadastrar', 'Variantes')
def test_ciclo():
    pass
"""
    conftest = "CENARIOS_DISPENSADOS = {('mod/features/001.x.feature', 'Sai do sistema'): 'motivo'}\n"
    _montar_modulo(tmp_path / 'mod', FEATURE, teste, conftest)
    junit = tmp_path / 'e2e.xml'
    junit.write_text(
        '<testsuites><testsuite><testcase file="mod/tests/e2e/test_x.py" name="test_ciclo">'
        '<failure message="boom"/></testcase></testsuite></testsuites>',
        encoding='utf-8',
    )
    monkeypatch.chdir(tmp_path)

    assert paridade_e2e.vermelhos(str(junit)) == {'mod/tests/e2e/test_x.py::test_ciclo'}
    assert paridade_e2e.relatar('mod', str(junit)) == 1, 'um teste vermelho tem de reprovar o módulo'
