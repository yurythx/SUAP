"""Fluxo: registro da conclusão do projeto (modo 2).

Validada a execução (008), o coordenador registra a conclusão. É o fecho do plano de trabalho:
resultados alcançados, disseminação e observações — e é o que a feature 011 (validação) e a 010
(finalização) exigem existir.

O que este arquivo pega: o botão "Registrar/Editar Conclusão" na aba "Conclusão" e os três
textos longos do popup. É um teste curto para uma regra dura: sem registro de conclusão,
``pode_finalizar_conclusao`` recusa, e as features 010 e 011 não têm sobre o que agir. A
asserção de domínio é ``RegistroConclusaoProjeto`` — a tabela que a 010 e a 011 leem de volta.
"""

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# A data que a feature 009 fixa: a mesma janela de execução das features 007/008.
DATA = '20/01/2018'

MEUS_PROJETOS = '/pesquisa/meus_projetos/'

TITULO_PROJETO = 'Título do projeto'


def test_registrar_conclusao_do_projeto(logado_pesquisa):
    """O coordenador registra a conclusão do projeto no popup da aba "Conclusão".

    Os três campos (``Resultados Alcançados``, ``Disseminação dos Resultados``, ``Observação``)
    são texto livre e nenhum é obrigatório — o que significa que a mensagem de sucesso apareceria
    mesmo com o formulário em branco. Por isso a asserção vai nos três textos no ORM.
    """
    from pesquisa.models import RegistroConclusaoProjeto

    tela = Tela(logado_pesquisa('coordenador_projeto'))
    tela.ir(MEUS_PROJETOS)
    tela.ver_titulo('Meus Projetos')
    tela.clicar_icone('exibição')
    tela.ver_titulo('Projeto de Pesquisa')

    tela.clicar_aba('Conclusão')
    tela.clicar_botao('Registrar/Editar Conclusão')

    popup = tela.popup()
    popup.preencher_formulario(
        [
            ('Resultados Alcançados', 'TextArea', 'descricao dos resultados alcancados'),
            ('Disseminação dos Resultados', 'TextArea', 'descricao da disseminacao'),
            ('Observação', 'TextArea', 'Obs sobre a conclusão'),
        ]
    )
    popup.salvar_no_popup('Salvar')

    tela.sucesso('Conclusão do projeto registrada com sucesso.')
    registro = RegistroConclusaoProjeto.objects.filter(projeto__titulo=TITULO_PROJETO).order_by('-id').first()
    assert registro is not None, 'a UI disse que registrou, mas não há registro de conclusão'
    assert registro.resultados_alcancados == 'descricao dos resultados alcancados', (
        'a UI disse que registrou, mas os resultados alcançados não persistirão'
    )
