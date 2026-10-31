"""Fluxo: finalização do projeto (modo 2).

Conclusão registrada (009) e validada (011 — que na ordem da feature vem depois, mas na cadeia
de dados é a validação que libera a finalização), o coordenador finaliza o projeto.

O que este arquivo pega: a pré-condição inteira da finalização numa asserção de domínio. O
botão "Finalizar Conclusão" só existe quando o projeto está em ``PERIODO_EXECUCAO`` e tem
conclusão registrada — ``Projeto.pode_finalizar_conclusao`` —, então o teste é o que prova que
a cadeia 002→009 produziu o estado que a finalização exige. Se ele passa com o botão visível, a
execução, o monitoramento e a conclusão estão todos de pé.
"""

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# A data que a feature 010 fixa: a mesma janela de execução.
DATA = '20/01/2018'

MEUS_PROJETOS = '/pesquisa/meus_projetos/'

TITULO_PROJETO = 'Título do projeto'


def test_finalizar_o_projeto(logado_pesquisa):
    """O coordenador finaliza a conclusão do projeto.

    A asserção é ``data_finalizacao_conclusao``, não a mensagem: é esse carimbo que tira o
    projeto da execução e o torna elegível à validação final da feature 011, e é o mesmo campo
    que ``Projeto.get_status`` consulta para dizer "Concluído".
    """
    from pesquisa.models import Projeto

    tela = Tela(logado_pesquisa('coordenador_projeto'))
    tela.ir(MEUS_PROJETOS)
    tela.ver_titulo('Meus Projetos')
    tela.clicar_icone('exibição')
    tela.ver_titulo('Projeto de Pesquisa')

    tela.clicar_aba('Conclusão')
    tela.ver_botao('Finalizar Conclusão')
    tela.clicar_botao('Finalizar Conclusão')

    tela.sucesso('Conclusão finalizada com sucesso.')
    projeto = Projeto.objects.get(titulo=TITULO_PROJETO)
    projeto.refresh_from_db()
    assert projeto.data_finalizacao_conclusao is not None, 'a UI disse que finalizou, mas o projeto ficou sem data de finalização'


def test_projeto_finalizado_nao_troca_de_coordenador(logado_pesquisa, projeto_do_fluxo):
    """#17573: projeto finalizado é somente leitura — a tela não oferece "Substituir Coordenador".

    A view aceitava o coordenador do projeto (``is_responsavel``) em qualquer estado, e o
    Coordenador de Pesquisa do campus mesmo com o projeto somente leitura.
    """
    projeto = projeto_do_fluxo()
    assert projeto.data_finalizacao_conclusao, 'a finalização deveria deixar o projeto somente leitura'
    url = f'/pesquisa/alterar_coordenador/{projeto.pk}/'
    respostas = {papel: Tela(logado_pesquisa(papel)).buscar(url).status for papel in ('coordenador_projeto', 'coordenador_pesquisa')}
    assert respostas == {'coordenador_projeto': 403, 'coordenador_pesquisa': 403}, respostas
