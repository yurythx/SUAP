"""Fluxo principal de abertura de processo por requerimento (modo 2)."""

from typing import Any
from uuid import uuid4

import pytest
from playwright.sync_api import expect

from djtools.e2e_fixtures import SENHA_E2E
from djtools.e2e_ui import Tela
from processo_eletronico.tests.e2e.test_02_fluxo_basico import _selecionar_tipo

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

REQUERIMENTOS = '/admin/processo_eletronico/requerimento/'
CADASTRAR_REQUERIMENTO = '/processo_eletronico/cadastrar_requerimento/'
GERENCIAR_REQUERIMENTO = '/processo_eletronico/gerenciar_requerimento/{}/'
FINALIZAR_REQUERIMENTO = '/processo_eletronico/finalizar_requerimento/{}/'


def _senha(tela: Tela) -> Tela:
    """Preenche a senha na etapa de geração do processo."""
    campo = tela.loc('//input[@type="password"]').first
    expect(campo).to_be_visible()
    campo.fill(SENHA_E2E)
    return tela


def test_servidor_gera_processo_por_requerimento(logado_processo_eletronico: Any) -> None:
    """Cria requerimento e o converte em processo já encaminhado."""
    tela = Tela(logado_processo_eletronico('servidor')).ir(REQUERIMENTOS).ver_titulo('Requerimentos')
    tela.ver_botao('Adicionar Requerimento').ir(CADASTRAR_REQUERIMENTO).ver_titulo('Adicionar Requerimento')

    assunto = f'Abertura por requerimento E2E {uuid4().hex[:8]}'
    _selecionar_tipo(tela, 'Acesso à Informação: Demanda do e-SIC')
    tela.preencher_formulario([('Assunto', 'texto', assunto), ('Descrição', 'textarea', 'Solicitação criada pelo fluxo E2E.')])
    tela.clicar_botao('Salvar').sucesso('Requerimento cadastrado com sucesso.')

    from processo_eletronico.models import Requerimento

    requerimento = Requerimento.objects.get(assunto=assunto)
    tela.ir(GERENCIAR_REQUERIMENTO.format(requerimento.pk)).ver_titulo(f'Requerimento #{requerimento.get_numero_requerimento()}')
    tela.ver_botao('Gerar Processo Eletrônico').ir(FINALIZAR_REQUERIMENTO.format(requerimento.pk))
    tela.ver_titulo(f'Finalizar Requerimento {requerimento.get_numero_requerimento()}')

    papel = requerimento.interessado.relacionamento.papeis_ativos.first()
    assert papel is not None
    tela.preencher_formulario(
        [
            ('Destino do primeiro trâmite', 'radio', 'Buscar usando o Autocompletar'),
            ('Setor de Destino', 'autocomplete', 'A1'),
            ('Perfil', 'lista', str(papel)),
        ]
    )
    _senha(tela).clicar_botao('Enviar').sucesso(
        'Requerimento finalizado com sucesso. Este processo foi gerado com base nos dados do requerimento finalizado.'
    )

    requerimento.refresh_from_db()
    assert requerimento.is_finalizado()
    assert requerimento.processo is not None
    assert requerimento.processo.assunto == assunto
    assert requerimento.processo.ultimo_tramite.destinatario_setor.sigla == 'A1'
