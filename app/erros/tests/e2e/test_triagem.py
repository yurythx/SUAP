"""Fluxo: a triagem feita pelo Recebedor de Demandas (modo 2).

As duas ações que um gerente da fila faz e que ninguém mais pode fazer — ``pode_atribuir`` e
``pode_unificar`` são ``in_group(user, 'Recebedor de Demandas')`` (``erros/models.py:174-178``),
o único par de permissões do módulo que não é "Analista":

* **atribuir** entrega o erro a *outra* pessoa. Não confundir com "Assumir", que é o próprio
  analista se pondo como atendente e cai na view ``erro`` (``erros/views.py:354``): aqui quem
  clica não vira atendente, e ``Erro.atribuir`` (``erros/models.py:254-262``) ainda move a
  situação para "Em análise" e notifica o atribuído;
* **unificar** funde erros duplicados no principal: os interessados dos absorvidos migram, os
  absorvidos vão para a situação "Unificado" e a descrição de cada um vira comentário do
  principal (``erros/models.py:264-283``). É o que evita dez erros para o mesmo defeito — e,
  se regredir, o estrago é perder interessado no meio do caminho, sem sintoma na tela.

O ``gerente`` desta suíte é Recebedor de Demandas e **não** é Analista (ver o conftest), então
o que estes testes afirmam é a permissão de grupo, não o acúmulo de papéis.
"""

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

URL_ERRO = '/erros/erro/{}/'
URL_ATRIBUIR = '/erros/atribuir_atendente/{}/'
URL_UNIFICAR = '/erros/unificar_erros/{}/'


def test_gerente_atribui_o_erro_a_um_analista(logado_erros, vinculos_erros, erro_aberto):
    """Atribuir a outra pessoa: o erro sai de "Reportado" com atendente que não é quem clicou."""
    from erros.models import Erro, HistoricoComentarioErro

    atendente = vinculos_erros['atendente']
    tela = Tela(logado_erros('gerente')).ir(URL_ERRO.format(erro_aberto.pk))
    # A permissão vira affordance no menu Opções (`erros/templates/erro.html:83-85`); se o
    # item sumir, o gerente perde a única porta para esta tela.
    tela.clicar_botao('Opções')
    tela.ver_botao('Atribuir atendente')

    tela.ir(URL_ATRIBUIR.format(erro_aberto.pk))
    tela.ver_titulo(f'Atribuir Atendente ao erro #{erro_aberto.pk}')
    # O queryset do campo é restrito a Analista/Desenvolvedor (`erros/forms.py:275-277`) — a
    # busca é pela matrícula, que o `SearchField` de Vinculo indexa (`comum/models.py:680`).
    tela.preencher('Atendente', 'autocomplete', '103011')
    tela.clicar_botao('Enviar')

    tela.sucesso('Usuário atribuído com sucesso.')
    erro_aberto.refresh_from_db()
    assert erro_aberto.atendente_atual == atendente, 'a UI disse que atribuiu, mas o atendente atual não mudou'
    assert erro_aberto.situacao == Erro.SITUACAO_EM_ANALISE, 'atribuir deveria tirar o erro de "Reportado"'
    assert HistoricoComentarioErro.objects.filter(
        erro=erro_aberto, vinculo=vinculos_erros['gerente'], descricao__contains='como atendente principal'
    ).exists(), 'a atribuição deveria ficar registrada em nome de quem atribuiu'


def test_gerente_unifica_erro_duplicado_no_principal(logado_erros, vinculos_erros, erro_aberto, erro_em_analise):
    """Dois erros na mesma view viram um: o absorvido fica "Unificado" e migra para o principal.

    O formulário só oferece erros com a **mesma view** e não finalizados
    (``erros/forms.py:294-296``), e por isso as duas fixturas servem: as duas nascem em
    ``VIEW_ORM``. A busca é pela URL, que é única por execução (o ``uuid4`` de ``criar_erro``)
    — buscar pelo rótulo pegaria o erro de outra execução no banco reusado.
    """
    from erros.models import Erro, HistoricoComentarioErro

    tela = Tela(logado_erros('gerente')).ir(URL_ERRO.format(erro_aberto.pk))
    tela.clicar_botao('Opções')
    tela.ver_botao('Unificar erros')

    tela.ir(URL_UNIFICAR.format(erro_aberto.pk))
    tela.ver_titulo(f'Unificar erros ao erro #{erro_aberto.pk}')
    tela.preencher('Erros', 'autocomplete multiplo', erro_em_analise.url, opcao=f'Erro {erro_em_analise.pk}:')
    tela.clicar_botao('Enviar')

    tela.sucesso('Erros unificados com sucesso.')
    erro_em_analise.refresh_from_db()
    assert erro_em_analise.situacao == Erro.SITUACAO_UNIFICADO, 'a UI disse que unificou, mas o erro absorvido não mudou de situação'
    assert HistoricoComentarioErro.objects.filter(erro=erro_aberto, descricao=erro_em_analise.descricao).exists(), (
        'a descrição do erro absorvido deveria virar comentário do principal'
    )
    assert erro_aberto.interessadoerro_set.filter(vinculo=vinculos_erros['interessado'], ativo=True).exists(), (
        'os interessados do erro absorvido deveriam migrar para o principal'
    )
