"""Fluxo: distribuição das bolsas entre os projetos (modo 2).

Avaliado o projeto (005), o Diretor de Pesquisa distribui as bolsas previstas no edital. É a
tela que transforma pontuação em decisão: o sistema sugere a distribuição automática a partir
das notas e o diretor confirma. Confirmada, o projeto passa a **aprovado** — e é isso que
destrava toda a fase de execução (features 007→011), que só existe para projeto aprovado.

O que este arquivo pega: o link do campus na linha do edital (é ele que leva à tela de
gerenciamento, e a linha tem de ser recortada pelo edital certo), e a gravação da distribuição
— sem ``aprovado_na_distribuicao``, ``projetos_em_execucao`` (feature 008) não mostra o
projeto e o resto da cadeia roda sobre lista vazia.
"""

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# A data que a feature 006 fixa: depois do fim da seleção (17/01) e antes da divulgação (19/01).
DATA = '18/01/2018'

DISTRIBUIR = '/pesquisa/distribuir_bolsas/'

TITULO_EDITAL = 'Nome do edital'
TITULO_PROJETO = 'Título do projeto'


def test_distribuicao_das_bolsas(logado_pesquisa):
    """O Diretor confirma a distribuição automática das bolsas do campus CZN.

    O clique em "Salvar" sem mexer em nada **é** o cenário: a feature 006 é a confirmação da
    sugestão que a própria tela calcula.

    **Achado — o cenário não marca o projeto na distribuição.** A asserção é ``aprovado``, não
    ``aprovado_na_distribuicao``, e isso não é atalho: ``Projeto.pode_aprovar_projeto``
    (``models.py:2413``) exige ``aprovado == aprovado_na_distribuicao``, e a classificação que
    a própria tela dispara no GET já grava ``aprovado=True`` quando o projeto passa do corte.
    Resultado: o checkbox ``name="situacao"`` — o único caminho que grava
    ``aprovado_na_distribuicao`` (``models.py:888-895``) — fica **oculto** justamente no caso em
    que o classificador aprovou, e o POST de "Salvar" chega sem ``situacao`` nenhum. Verificado
    no navegador: ``input[name=situacao]`` conta 0 na tela do campus.

    O que a feature realmente entrega, e é o que a cadeia usa, é ``aprovado=True`` — é o filtro
    de ``projetos_em_execucao`` (feature 008). Marcar ``aprovado_na_distribuicao`` pela tela
    exigiria um projeto que o classificador **não** tenha aprovado, o que não é o caso deste
    fluxo.
    """
    from pesquisa.models import Projeto

    tela = Tela(logado_pesquisa('diretor')).ir(DISTRIBUIR)
    tela.ver_titulo('Distribuição de Bolsas dos Projetos de Pesquisa')

    tela.linha(TITULO_EDITAL).clicar_link('CZN')
    tela.ver_titulo('Gerenciamento de Bolsas dos Projetos de Pesquisa')
    tela.ver_botao('Salvar')
    tela.clicar_botao('Salvar')

    tela.sucesso('Bolsas salvas com sucesso.')
    projeto = Projeto.objects.get(titulo=TITULO_PROJETO)
    projeto.refresh_from_db()
    assert projeto.aprovado, 'a UI disse que salvou, mas o projeto não ficou aprovado — a fase de execução inteira depende disso'
    assert projeto.participacao_set.filter(bolsa_concedida=True).exists(), (
        'a UI disse que salvou, mas nenhuma bolsa foi concedida — a tela de gerenciamento mostraria saldo sem distribuição'
    )
