"""Roteiro navegado das tarefas do ``ppc`` — a fonte de ``ppc/docs/usuario.md``.

Um teste por tarefa da doc, na ordem em que a doc as apresenta. As asserções são as mesmas
dos e2e (título, botão, mensagem de sucesso) e existem para a rodada falhar alto quando a
tela mudou de forma: doc que descreve um passo que não existe mais é pior que doc velha.

Marcado ``e2e`` além de ``doc`` de propósito — o ``-m "not e2e"`` do ``suap_check`` precisa
excluir esta suíte, que exige o banco ``*_e2e`` e um browser.

O módulo não tem ``features/``: os estados de domínio (solicitação, PPC em elaboração,
plano de disciplina, modelo) são semeados por ORM no ``doc_seed`` e os passos documentados
são navegados de verdade.
"""

from __future__ import annotations

import sys

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

PAINEL = '/ppc/painel/'
SOLICITACOES = '/admin/ppc/solicitacaoppc/'
PROJETOS = '/admin/ppc/projetopedagogicocurso/'
PLANOS_DISCIPLINA = '/admin/ppc/planodisciplina/'
MODELOS = '/admin/ppc/modeloppc/'


def _anotar(titulo: str, tela: Tela) -> None:
    """Despeja cabeçalhos, botões e rótulos da tela para a redação da doc (não é asserção)."""
    cabecalhos = tela.pagina.get_by_role('heading').all_inner_texts()
    main = ' '.join(tela.pagina.locator('//main').all_inner_texts())[:800]
    sys.stderr.write(
        f'\n[doc:{titulo}] url={tela.pagina.url}'
        f'\n  cabeçalhos: {[c.strip() for c in cabecalhos if c.strip()]}'
        f'\n  botões: {tela.botoes_na_tela()}'
        f'\n  rótulos: {tela.rotulos_na_tela()}'
        f'\n  erros: {tela.erros_na_tela()}'
        f'\n  main: {main!r}\n'
    )


def test_painel(logado_doc, capturar):
    """Tarefa 1 — o painel do PPC resume o andamento de planos, projetos e solicitações."""
    tela = Tela(logado_doc('servidor')).ir(PAINEL)
    assert 'at /' not in tela.pagina.title(), f'painel respondeu página de erro: {tela.pagina.title()}'
    tela.ver_titulo('Painel')
    _anotar('painel', tela)
    capturar(tela.pagina, 'painel')


def test_tramitar_solicitacao_ppc(logado_doc, doc_seed, capturar):
    """Tarefa 2 — a solicitação de criação de PPC e sua tramitação."""
    solicitacao = doc_seed['solicitacao']

    tela = Tela(logado_doc('servidor')).ir(SOLICITACOES)
    assert 'at /' not in tela.pagina.title(), f'solicitações respondeu página de erro: {tela.pagina.title()}'
    _anotar('solicitacoes-listagem', tela)
    capturar(tela.pagina, 'solicitacoes-listagem')
    tela.linha('Curso de Exemplo da Doc').clicar_icone('exibição')

    tela.ver_titulo(f'Solicitação de criação de PPC: {solicitacao.nome_curso}')
    _anotar('solicitacao-tela', tela)
    capturar(tela.pagina, 'solicitacao-tela')
    tela.ver_texto(solicitacao.get_situacao_display())


def test_elaborar_ppc(logado_doc, doc_seed, capturar):
    """Tarefa 3 — o PPC em elaboração: a página do projeto com as seções de conteúdo."""
    ppc = doc_seed['ppc']

    tela = Tela(logado_doc('servidor')).ir(PROJETOS)
    assert 'at /' not in tela.pagina.title(), f'projetos respondeu página de erro: {tela.pagina.title()}'
    _anotar('ppc-listagem', tela)
    capturar(tela.pagina, 'ppc-listagem')
    tela.linha(ppc.nome_curso).clicar_icone('exibição')

    tela.ver_titulo(f'PPC: {ppc.nome_curso}')
    _anotar('ppc-tela', tela)
    capturar(tela.pagina, 'ppc-tela')

    # A elaboração acontece na aba de conteúdo, seção a seção.
    tela.clicar_aba('Conteúdo')
    tela.ver_texto('Identificação do Curso')
    _anotar('ppc-conteudo', tela)
    capturar(tela.pagina, 'ppc-conteudo')


def test_plano_disciplina(logado_doc, doc_seed, capturar):
    """Tarefa 4 — o plano de disciplina, aberto pela listagem do admin."""
    plano = doc_seed['plano_disciplina']

    tela = Tela(logado_doc('servidor')).ir(PLANOS_DISCIPLINA)
    assert 'at /' not in tela.pagina.title(), f'planos respondeu página de erro: {tela.pagina.title()}'
    _anotar('planos-listagem', tela)
    capturar(tela.pagina, 'planos-listagem')
    tela.linha(plano.nome_disciplina).clicar_icone('exibição')

    tela.ver_titulo(str(plano))
    _anotar('plano-tela', tela)
    capturar(tela.pagina, 'plano-tela')


def test_modelo_ppc(logado_doc, doc_seed, capturar):
    """Tarefa 5 — o modelo de PPC e suas seções (Administrador de PPC)."""
    modelo = doc_seed['modelo_ppc']

    tela = Tela(logado_doc('admin_ppc')).ir(MODELOS)
    assert 'at /' not in tela.pagina.title(), f'modelos respondeu página de erro: {tela.pagina.title()}'
    _anotar('modelos-listagem', tela)
    capturar(tela.pagina, 'modelos-listagem')
    tela.linha(modelo.descricao).clicar_icone('exibição')

    tela.ver_titulo(f'Modelo {modelo.descricao}')
    _anotar('modelo-tela', tela)
    capturar(tela.pagina, 'modelo-tela')
    tela.ver_texto('Identificação do Curso')
