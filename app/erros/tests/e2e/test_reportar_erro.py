"""Fluxo: abertura de um erro pelo próprio usuário (feature 001 do behave).

É a porta de entrada do módulo — sem ela não existe erro nenhum para atender. O caminho passa
por três peças que quebram calado: o botão "Reportar erro" do rodapé, que carrega a URL da
página atual em base64 (`comum/templates/admin/base.html:228`); a triagem de duplicidade, que
troca o formulário por uma lista de erros similares quando já existe erro aberto para a mesma
view (`erros/views.py:238-243`); e o assistente de dois passos do `ReportarErroForm`, cujo
primeiro passo é só a confirmação de ciência.
"""

from uuid import uuid4

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

DESCRICAO_LABEL = 'Descreva a operação que você estava realizando antes de ocorrer o erro e a mensagem de erro que o sistema apresentou'


def test_usuario_reporta_erro_da_pagina_em_que_esta(logado_erros):
    """Reporta a partir de "/" e confere que o erro nasce no módulo daquela página.

    O título esperado não é escrito à mão ("Erro 1: Comum", como na feature): ele sai do
    próprio objeto, porque a numeração depende do banco reusado e o módulo afetado é derivado
    da view por `get_auto_modulo_afetado` (`erros/utils.py:207`) — é justamente essa derivação
    que o teste afirma.
    """
    from erros.models import Erro

    tela = Tela(logado_erros('interessado')).ir('/')
    tela.clicar_link('Reportar erro')
    tela.ver_titulo('Reportar Erro no SUAP')
    # Âncora do ramo certo: com um erro aberto para a mesma view a tela tem o MESMO título e
    # mostra a lista de similares, e a falha só apareceria dois passos adiante.
    tela.ver_texto('Instruções para Abertura de Erro')

    tela.preencher_formulario(
        [
            ('Li as instruções', 'checkbox', 'marcar'),
            ('Concordo em compartilhar meus dados', 'checkbox', 'marcar'),
        ]
    )
    tela.clicar_botao('Continuar')

    descricao = f'O quadro de erros não está sendo exibido. (e2e {uuid4().hex[:8]})'
    tela.preencher(DESCRICAO_LABEL, 'textarea', descricao)
    tela.clicar_botao('Finalizar')

    tela.sucesso('Erro reportado com sucesso.')
    erro = Erro.objects.filter(descricao=descricao).first()
    assert erro is not None, 'a UI disse que reportou, mas não persistiu'
    assert erro.view == 'comum.views.index', f'o erro deveria apontar para a view da página de origem, veio {erro.view!r}'
    assert erro.interessadoerro_set.filter(vinculo=erro.informante, ativo=True).exists(), 'quem reporta tem de nascer interessado no próprio erro'

    tela.ver_titulo(f'Erro {erro.pk}: {erro.modulo_afetado_display}')
