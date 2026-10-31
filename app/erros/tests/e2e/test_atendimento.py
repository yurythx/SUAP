"""Fluxo: o desfecho do atendimento e a saída de um atendente auxiliar (modo 2).

O que nenhuma ``.feature`` cobre e é a parte mais cara de regredir:

* **resolver um erro publica uma atualização**. ``gerenciar_situacao`` com "Resolvido" chama
  ``Erro.editar_atualizacao`` (``erros/models.py:358-359``), que converte os três campos de
  atualização do erro num ``demandas.Atualizacao`` — a nota de versão que o SUAP mostra a
  todos os usuários — e a etiqueta o módulo afetado. Se essa ponte quebrar, o erro é resolvido
  do mesmo jeito e a nota simplesmente deixa de existir, sem erro nenhum na tela;
* **o atendente auxiliar sai sozinho**. ``remover_atendente`` (``erros/views.py:568-578``) é a
  única ação do módulo cuja autorização não passa por grupo nem por ``pode_*``: ela compara o
  vínculo logado com o da URL e recusa remover o atendente **atual**. É a regra que impede um
  auxiliar de derrubar o principal por uma URL montada à mão.
"""

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

URL_ERRO = '/erros/erro/{}/'
URL_EDITAR_ATUALIZACAO = '/erros/editar_atualizacao/{}/'
URL_ALTERAR_SITUACAO = '/erros/alterar_situacao_erro/{}/'
URL_REMOVER_ATENDENTE = '/erros/remover_atendente/{}/{}/'

# `situacao=3` é `Erro.SITUACAO_RESOLVIDO`; é assim que o menu "Alterar situação" monta o link
# (`erros/templates/erro.html:54`).
SITUACAO_RESOLVIDO = 3

TITULO_ATUALIZACAO = 'Correção do quadro de erros da página inicial'
GRUPO_ENVOLVIDO = 'Analista'


def test_atendente_registra_atualizacao_e_resolve_o_erro(logado_erros, erro_em_analise):
    """Preencher a atualização e então resolver, num teste só: resolver é o que a publica.

    A aba "Atualização" grava apenas os três campos no próprio ``Erro``
    (``erros/views.py:594-597``); o ``demandas.Atualizacao`` só nasce quando a situação vai
    para "Resolvido". Separar isso em dois testes deixaria de fora exatamente a ligação entre
    as duas telas, que é onde mora a regra.
    """
    from erros.models import Erro

    tela = Tela(logado_erros('atendente')).ir(URL_ERRO.format(erro_em_analise.pk))
    tela.clicar_aba('Atualização')
    tela.aba('Atualização').ver_texto('Não há atualização informada.')

    tela.ir(URL_EDITAR_ATUALIZACAO.format(erro_em_analise.pk))
    tela.ver_titulo(f'Criar Atualização para o Erro #{erro_em_analise.pk}')
    tela.preencher_formulario(
        [
            ('Título', 'texto', TITULO_ATUALIZACAO),
            ('Tipo', 'lista', 'Bug'),
            ('Grupos Envolvidos', 'autocomplete multiplo', GRUPO_ENVOLVIDO),
        ]
    )
    # "Salvar" e não "Enviar": `render_form` rotula o submit pelo tipo do formulário
    # (`djtools/templatetags/tags/utils.py:260-264`), e este é o único do módulo que é
    # ModelForm — os outros (atribuir, unificar, anexo, alterar URL) são FormPlus.
    tela.clicar_botao('Salvar')

    tela.sucesso('Atualização editada com sucesso.')
    erro_em_analise.refresh_from_db()
    assert erro_em_analise.titulo_atualizacao == TITULO_ATUALIZACAO, 'a UI disse que gravou, mas a atualização não persistiu'
    assert erro_em_analise.grupos_atualizacao.filter(name=GRUPO_ENVOLVIDO).exists(), 'o grupo envolvido deveria ter sido vinculado'

    # A tela de "Resolvido" é o mesmo formulário de atualização, agora opcional
    # (`erros/views.py:425-430`): é a última chance de descrever a correção antes de fechar.
    tela.ir(f'{URL_ALTERAR_SITUACAO.format(erro_em_analise.pk)}?situacao={SITUACAO_RESOLVIDO}')
    tela.ver_titulo('Criar Atualização')
    # A tela também oferece "Pular" (`EXTRA_BUTTONS` de `erros/forms.py:316`); "Salvar"
    # reaproveita o que a aba já gravou, que é o caminho que publica a nota de versão.
    tela.clicar_botao('Salvar')

    tela.sucesso('Situação alterada com sucesso.')
    erro_em_analise.refresh_from_db()
    assert erro_em_analise.situacao == Erro.SITUACAO_RESOLVIDO, 'a UI disse que alterou, mas a situação não persistiu'
    assert erro_em_analise.atualizacao is not None, 'resolver deveria publicar a atualização (demandas.Atualizacao)'
    assert erro_em_analise.atualizacao.descricao == TITULO_ATUALIZACAO
    assert erro_em_analise.atualizacao.tags.filter(nome=erro_em_analise.modulo_afetado_display).exists(), (
        'a atualização deveria ser etiquetada com o módulo afetado'
    )


def test_atendente_auxiliar_se_remove_do_atendimento(logado_erros, vinculos_erros, erro_com_atendente_auxiliar):
    """O auxiliar sai; o principal e o erro continuam onde estavam.

    A remoção não apaga histórico: registra "se removeu do atendimento." como comentário
    automático (``erros/views.py:574-576``), que é o rastro que o atendimento precisa manter.
    """
    from erros.models import AtendenteErro, HistoricoComentarioErro

    auxiliar = vinculos_erros['atendente_auxiliar']
    tela = Tela(logado_erros('atendente_auxiliar')).ir(URL_ERRO.format(erro_com_atendente_auxiliar.pk))
    tela.ver_botao('Me remover do atendimento')

    tela.ir(URL_REMOVER_ATENDENTE.format(erro_com_atendente_auxiliar.pk, auxiliar.pk))

    tela.sucesso('Remoção realizada com sucesso.')
    assert not AtendenteErro.objects.filter(erro=erro_com_atendente_auxiliar, vinculo=auxiliar).exists(), (
        'a UI disse que removeu, mas o vínculo de atendente continua'
    )
    assert HistoricoComentarioErro.objects.filter(
        erro=erro_com_atendente_auxiliar, vinculo=auxiliar, descricao='se removeu do atendimento.'
    ).exists(), 'a saída do auxiliar deveria ficar registrada na linha do tempo'
    erro_com_atendente_auxiliar.refresh_from_db()
    assert erro_com_atendente_auxiliar.atendente_atual == vinculos_erros['atendente'], (
        'o atendente principal não pode ser afetado pela saída do auxiliar'
    )
