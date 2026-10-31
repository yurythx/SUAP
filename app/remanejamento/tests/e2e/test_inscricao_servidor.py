"""Fluxo: o servidor se inscreve, confere o comprovante e desiste — o lado do candidato.

É o único fluxo do módulo que o servidor comum executa sozinho, e o que mais depende de
prazo: ``inscrever`` (``views.py:494``) cruza período de inscrição, cargo/área contemplados
pelo edital e afastamento impeditivo vigente antes de mostrar o formulário.

Duas regressões que este arquivo pega:

* a **entrada** pela página inicial. O atalho "Inscrever-se para Remoção Interna" é montado
  por ``index_inscricoes`` (``views.py:86``) a partir de ``get_em_periodo_de_inscricao_servidor``:
  se essa consulta regredir, o servidor deixa de ter caminho até a tela — a rota continua
  respondendo 200 e nenhum teste que fosse direto na URL perceberia;
* a **ordem de preferência por campus**, que não é campo do model: cada campus do edital vira
  um ``IntegerFieldPlus`` dinâmico (``forms.py:315-319``) e o ``save`` do formulário
  transforma em ``InscricaoItem``. É essa lista que o processamento do resultado consome.
"""

import datetime

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

INSCREVER = '/remanejamento/inscrever/{}/'
INSCRICAO = '/remanejamento/inscricao/{}/'
DESISTIR = '/remanejamento/inscricao/{}/desistir/'


def test_servidor_se_inscreve_a_partir_da_pagina_inicial(logado_remanejamento, servidores, edital_com_inscricoes_abertas):
    """Entra pelo atalho da página inicial, preenche a inscrição e confere o comprovante.

    A ordem de preferência é 1 para o campus de destino e nenhuma para o de origem: o
    ``clean`` do formulário (``forms.py:355-363``) exige pelo menos uma preferência e recusa
    repetição de número, e é essa lista que decide para onde o servidor pode ser removido.
    """
    from remanejamento.models import Inscricao

    servidor = servidores['inscrevente']
    tela = Tela(logado_remanejamento('inscrevente')).ir('/')
    tela.clicar_link(f'Inscrever-se para Remoção Interna: {edital_com_inscricoes_abertas.titulo}')

    tela.ver_titulo('Inscrição para Edital de Remoção Interna')
    assert tela.pagina.url.endswith(INSCREVER.format(edital_com_inscricoes_abertas.pk)), (
        f'o atalho da página inicial deveria levar à inscrição do edital, foi para {tela.pagina.url!r}'
    )
    tela.preencher_formulario(
        [
            ('Concurso para ingresso foi do IFRN?', 'lista', 'Sim'),
            ('Classificação no concurso para ingresso no IFRN', 'número', '3'),
            ('Número', 'texto', '12'),
            ('Data', 'data', '02/02/2011'),
            ('Página', 'texto', '2'),
            ('Seção', 'texto', '2'),
            ('B0', 'número', '1'),
        ]
    )
    tela.clicar_botao('Salvar')

    tela.sucesso('Inscrição realizada com sucesso')
    inscricao = Inscricao.objects.filter(edital=edital_com_inscricoes_abertas, servidor=servidor).last()
    assert inscricao, 'a UI disse que inscreveu, mas a inscrição não persistiu'
    assert inscricao.confirmada, 'a inscrição nasceu sem confirmação'
    assert list(inscricao.inscricaoitem_set.values_list('campus__sigla', 'preferencia')) == [('B0', 1)], (
        'a ordem de preferência por campus não virou InscricaoItem'
    )

    # O comprovante é o destino do `httprr` do cadastro (`views.py:536`); a frase de
    # autenticidade só existe se `atualizar_frases` tiver rodado no save.
    tela.ver_titulo(f'Comprovante de Inscrição #{inscricao.pk}')
    tela.quadro('Autenticidade da inscrição').ver_texto(inscricao.frase_hash)


def test_servidor_desiste_da_inscricao(logado_remanejamento, servidores, edital_com_inscricoes_abertas):
    """Cancela a própria inscrição dentro do período de desistência e vê o status mudar.

    ``is_pode_desistir`` (``models.py:1411``) exige janela de desistência aberta **e** ser o
    dono da inscrição; ``efetivar_desistencia`` desconfirma e carimba a data. O botão pede
    confirmação nativa (``comum/static/comum/js/main.js:458``), que o contexto do ``logado``
    aceita automaticamente.

    A asserção é sobre o fato positivo (o carimbo de desistência), não sobre a ausência do
    botão: ``inscricao_desistir`` redireciona sem mensagem de feedback (``views.py:606``), então
    não há banner a afirmar.
    """
    from remanejamento.models import Inscricao
    from remanejamento.tests.e2e.conftest import criar_inscricao

    inscricao = criar_inscricao(edital_com_inscricoes_abertas, servidores['inscrevente'])
    tela = Tela(logado_remanejamento('inscrevente')).ir(INSCRICAO.format(inscricao.pk))
    tela.ver_texto('Confirmada')

    tela.clicar_botao('Cancelar inscrição (Desistir)')

    tela.ver_texto('Desistência em')
    inscricao.refresh_from_db()
    assert not inscricao.confirmada, 'a UI mostrou a desistência, mas a inscrição continua confirmada'
    assert inscricao.data_desistencia, 'a desistência não foi carimbada'
    assert inscricao.data_desistencia.date() == datetime.date.today(), 'a data da desistência não é a de hoje'
    assert tela.pagina.url.endswith(INSCRICAO.format(inscricao.pk)), f'o cancelamento deveria voltar ao comprovante, foi para {tela.pagina.url!r}'
