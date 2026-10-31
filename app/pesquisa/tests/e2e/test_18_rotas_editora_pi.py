"""Smoke das rotas de obra (editora) e de propriedade intelectual do `pesquisa`.

Separadas do `test_17_rotas.py` porque os alvos vêm só do 12-14 (edital de publicação e obra) e do
16 (registro de PI), que não dependem da cadeia 01-11: é o que deixa a suíte `pesquisa-2`
(`DIVISOES_E2E` no `suap_check`) rodar sozinha, num banco novo. Mesma mecânica do 17 — GET em lote
por papel, e a falha lista todas as rotas quebradas de uma vez.
"""

import pytest

from pesquisa.tests.e2e.alvos_rotas import relatorio_de_guardadas

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

ROTAS_DE_PI = [
    '/pesquisa/adicionar_certificado_registro_pi/{registro_pi}/',
    '/pesquisa/adicionar_termo_cessao_pi/{registro_pi}/',
    '/pesquisa/classificacao_locarno/{registro_pi}/',
    '/pesquisa/importar_dados_di_inpi/{registro_pi}/',
    '/pesquisa/pi_visualizar/{registro_pi}/',
]

ROTAS_DE_OBRA = [
    '/pesquisa/alterar_autor/{obra}/',
    '/pesquisa/alterar_situacao_obra/{obra}/',
    '/pesquisa/avaliar_diagramacao/{obra}/',
    '/pesquisa/cadastrar_diagramacao/{obra}/',
    '/pesquisa/cadastrar_ficha_catalografica/{obra}/',
    '/pesquisa/cadastrar_isbn/{obra}/',
    '/pesquisa/cancelar_obra/{obra}/',
    '/pesquisa/checklist_obra/{obra}/',
    '/pesquisa/checklist_obra_diagramador/{obra}/',
    '/pesquisa/concluir_obra/{obra}/',
    '/pesquisa/enviar_arquivo_corrigido/{obra}/',
    '/pesquisa/indicar_conselheiro_obra/{obra}/',
    '/pesquisa/indicar_diagramador_obra/{obra}/',
    '/pesquisa/indicar_parecerista_obra/{obra}/',
    '/pesquisa/indicar_revisor_obra/{obra}/',
    '/pesquisa/obra/{obra}/',
    '/pesquisa/parecerista_avaliar_obra/{obra}/',
    '/pesquisa/reenviar_obra/{obra}/',
    '/pesquisa/registrar_posicao_conselho_obra/{obra}/',
    '/pesquisa/revisar_obra/{obra}/',
    '/pesquisa/revisor_emitir_parecer/{obra}/',
    '/pesquisa/validar_termos/{obra}/',
]


def test_rotas_de_obra_e_pi_abrem(abrir_rotas, alvos, guardadas):
    """O diretor abre as rotas do registro de PI e a editora, as da obra."""
    abrir_rotas('diretor', ROTAS_DE_PI, alvos)
    abrir_rotas('integrante_editora', ROTAS_DE_OBRA, alvos)
    relatorio_de_guardadas(guardadas)
