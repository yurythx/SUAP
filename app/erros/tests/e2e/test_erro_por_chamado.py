"""Fluxo: reclassificar um chamado da central de serviços em erro do SUAP (modo 2).

É a única porta de entrada do módulo que não vem do usuário final: quem atende um chamado
percebe que aquilo não é dúvida, é defeito, e reclassifica. A rota é
``/erros/reportar_erro_por_chamado/<chamado_pk>/`` e ela existe para não perder o contexto do
atendimento no caminho — ``ReportarErroPorChamadoForm.processar``
(``erros/forms.py:121-148``) faz quatro coisas de uma vez, e é a terceira que costuma sumir
numa refatoração sem ninguém notar:

1. abre o erro em nome de quem reclassificou;
2. registra na linha do tempo do erro de que chamado ele veio;
3. **transfere os interessados do chamado para o erro** — sem isso, quem abriu o chamado
   nunca mais sabe o que aconteceu com o próprio problema;
4. comenta no chamado, com link, que o erro foi aberto.

A permissão é do outro módulo (``Chamado.pode_reclassificar``,
``centralservicos/models.py:1932``): o ``atendente`` desta suíte é responsável do grupo de
atendimento do chamado (ver a fixture ``chamado_reclassificavel``), e é por isso que ele passa.
"""

from uuid import uuid4

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

URL_POR_CHAMADO = '/erros/reportar_erro_por_chamado/{}/'

# Página real (o formulário recusa URL que não resolva para uma view,
# ``erros/forms.py:116-119``) e deliberadamente a `VIEW_SECUNDARIA` do conftest, não a
# `VIEW_ORM`: este é o único teste em que o **atendente** é informante, e um erro dele em
# `VIEW_ORM` faria as duas listas de similares aparecerem juntas em `test_navegacao`, que
# roda depois na ordem alfabética da coleta.
URL_COM_ERRO = 'http://localhost:8000/comum/acessibilidade/'
VIEW_COM_ERRO = 'comum.views.acessibilidade'

DESCRICAO_LABEL = 'Descreva a operação que você estava realizando antes de ocorrer o erro'


def test_atendente_reclassifica_chamado_em_erro(logado_erros, vinculos_erros, chamado_reclassificavel):
    """O erro nasce do chamado com os dois lados ligados: histórico no erro, comunicação no chamado."""
    from centralservicos.models import Comunicacao
    from erros.models import Erro, HistoricoComentarioErro

    descricao = f'Ao abrir a página de acessibilidade o sistema apresentou erro 500. (e2e {uuid4().hex[:8]})'
    tela = Tela(logado_erros('atendente')).ir(URL_POR_CHAMADO.format(chamado_reclassificavel.pk))
    tela.ver_titulo(f'Reportar erro a partir do chamado #{chamado_reclassificavel.pk}')

    tela.preencher_formulario(
        [
            ('URL com Erro', 'texto', URL_COM_ERRO),
            (DESCRICAO_LABEL, 'textarea', descricao),
        ]
    )
    tela.clicar_botao('Enviar')

    tela.sucesso('Erro reportado com sucesso.')
    erro = Erro.objects.filter(descricao=descricao).first()
    assert erro is not None, 'a UI disse que reportou, mas o erro não persistiu'
    assert erro.informante == vinculos_erros['atendente'], 'o erro deveria nascer em nome de quem reclassificou'
    assert erro.view == VIEW_COM_ERRO, f'a view deveria sair da URL informada, veio {erro.view!r}'

    assert HistoricoComentarioErro.objects.filter(erro=erro, descricao__contains=f'#{chamado_reclassificavel.pk}').exists(), (
        'a linha do tempo do erro deveria dizer de qual chamado ele veio'
    )
    assert erro.interessadoerro_set.filter(vinculo=vinculos_erros['interessado'], ativo=True).exists(), (
        'o interessado do chamado deveria ter sido transferido para o erro'
    )
    assert Comunicacao.objects.filter(chamado=chamado_reclassificavel, texto__contains=f'#{erro.pk}').exists(), (
        'o chamado deveria receber a comunicação automática com o link do erro'
    )
