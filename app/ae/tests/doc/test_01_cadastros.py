"""Capturas das telas de cadastro usadas no manual do AE."""

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]


def test_captura_telas_de_cadastro(logado_ae, ae_fluxos, capturar):
    """Navega pelas telas de apoio e captura os formulários do manual."""
    telas = (
        ('coordenador', '/admin/ae/tipoprograma/add/', 'Adicionar Tipo de Programa', 'tipos-programas-formulario'),
        ('coordenador', '/admin/ae/programa/', 'Programas', 'programas-lista'),
        ('coordenador', '/admin/ae/programa/add/', 'Adicionar Programa', 'programas-formulario'),
        ('coordenador', '/admin/ae/edital/add/', 'Adicionar Edital da Assistência Estudantil', 'editais-formulario'),
        ('coordenador', '/admin/ae/periodoinscricao/add/', 'Adicionar Período de Inscrição', 'periodos-inscricao-formulario'),
        ('assistente_social', '/admin/ae/ofertaalimentacao/add/', 'Adicionar Oferta de Refeições', 'ofertas-alimentacao-formulario'),
        ('assistente_social', '/admin/ae/ofertaturma/add/', 'Adicionar Oferta de Turmas de Idioma', 'turmas-idioma-formulario'),
        ('assistente_social', '/admin/ae/ofertabolsa/add/', 'Adicionar Oferta de Bolsa de Inic. Profissional', 'ofertas-bolsa-formulario'),
    )
    for papel, rota, titulo, nome in telas:
        tela = Tela(logado_ae(papel)).ir(rota).ver_titulo(titulo)
        capturar(tela.pagina, nome)
