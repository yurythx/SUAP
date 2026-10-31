"""Corte dos módulos acadêmicos no perfil administrativo (DISABLE_EDU)."""

import pytest
from django.http import Http404, HttpResponse
from django.test import RequestFactory

from djtools.middleware.modulos_ocultos import ModulosOcultosMiddleware
from djtools.modulos_ocultos import area_api_oculta, caminho_oculto, item_menu_oculto, menu_visivel


@pytest.fixture
def perfil_administrativo(settings):
    settings.DISABLE_EDU = True


def test_com_a_flag_desligada_nada_e_oculto(settings):
    settings.DISABLE_EDU = False

    assert caminho_oculto('/edu/alunos/') is False
    assert area_api_oculta('ensino') is False
    assert item_menu_oculto({'hierarchy': 'Ensino::Alunos', 'url': '/edu/alunos/'}) is False


def test_urls_academicas_ficam_ocultas(perfil_administrativo):
    assert caminho_oculto('/edu/alunos/') is True
    assert caminho_oculto('/admin/edu/aluno/') is True
    assert caminho_oculto('/json/pesquisa/Projeto/') is True
    assert caminho_oculto('/chained_select/ae/Demanda/') is True
    assert caminho_oculto('/api/ensino/alunos/') is True
    assert caminho_oculto('/api/extensao/projetos/') is True
    assert caminho_oculto('/djtools/breadcrumbs_reset/ensino_alunos/edu/alunos/') is True


def test_urls_administrativas_continuam_abertas(perfil_administrativo):
    assert caminho_oculto('/rh/servidores/') is False
    assert caminho_oculto('/admin/rh/servidor/') is False
    assert caminho_oculto('/admin/') is False
    assert caminho_oculto('/cursos/') is False
    assert caminho_oculto('/gestao/periodo_referencia/') is False
    assert caminho_oculto('/api/rh/servidores/') is False
    assert caminho_oculto('/static/edu/css/edu.css') is False
    assert caminho_oculto('/accounts/login/') is False


def test_menu_esconde_blocos_e_carreira_docente(perfil_administrativo):
    itens = [
        {'hierarchy': 'Ensino::Alunos', 'url': '/admin/edu/aluno/'},
        {'hierarchy': 'Atividades Estudantis::Saúde::Prontuários', 'url': '/saude/prontuarios/'},
        {'hierarchy': 'Gestão de Pessoas::Desenvolvimento de Pessoal::Docentes::Professor Titular::Avaliadores', 'url': '/professor_titular/'},
        {'hierarchy': 'Gestão de Pessoas::Administração de Pessoal::Cadastros::Servidores', 'url': '/admin/rh/servidor/'},
        {'hierarchy': 'Atividades Estudantis::Variáveis de Gestão', 'url': '/gestao/exibir_variaveis/Social/'},
    ]

    visiveis = menu_visivel(itens)

    assert visiveis == [itens[3]]


def test_middleware_responde_404_no_academico_e_libera_o_resto(perfil_administrativo):
    middleware = ModulosOcultosMiddleware(lambda request: HttpResponse('ok'))

    with pytest.raises(Http404):
        middleware(RequestFactory().get('/edu/alunos/'))

    resposta = middleware(RequestFactory().get('/ponto/'))
    assert resposta.content == b'ok'
