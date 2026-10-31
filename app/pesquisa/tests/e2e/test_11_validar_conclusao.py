"""Fluxo: validação da conclusão do projeto (modo 2).

Último passo da cadeia do PESQUISA: o supervisor emite o parecer de aprovação da conclusão
registrada na 009. É o mesmo Coordenador de Pesquisa que pré-avaliou (003) e monitorou (008) —
o supervisor do projeto é, por padrão, quem fez a pré-seleção.

O que este arquivo pega: a aba "Conclusão do Projeto" dentro de ``Validar Execução`` (que é a
mesma tela de monitoramento da 008, com uma aba a mais) e o popup de parecer com o checkbox
``Aprovado`` mais a observação. A asserção de domínio é ``aprovado`` no
``RegistroConclusaoProjeto``: sem ele o projeto fica com conclusão registrada e nunca aceita, e
``Projeto.pode_exibir_botao_finalizar_relatorios`` / ``pode_finalizar_conclusao`` continuariam
dizendo que falta algo.
"""

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# A data que a feature 011 fixa: a mesma janela de execução das features 007→010.
DATA = '20/01/2018'

MONITORAMENTO = '/pesquisa/projetos_em_execucao/'

TITULO_PROJETO = 'Título do projeto'


def test_validar_conclusao(logado_pesquisa):
    """O supervisor aprova a conclusão do projeto.

    O ``Observação`` é preenchido junto do checkbox de propósito: a feature pede os dois, e um
    parecer de aprovação sem texto é indistinguível de um clique acidental no histórico do
    projeto — que é o que o campo guarda.
    """
    from pesquisa.models import RegistroConclusaoProjeto

    tela = Tela(logado_pesquisa('coordenador_pesquisa'))
    tela.ir(MONITORAMENTO)
    tela.ver_titulo('Monitoramento')

    tela.linha(TITULO_PROJETO)
    tela.ver_botao('Acompanhar Validação')
    tela.linha(TITULO_PROJETO).clicar_botao('Acompanhar Validação')
    tela.ver_titulo('Validar Execução')

    tela.clicar_aba('Conclusão do Projeto')
    tela.clicar_botao('Emitir parecer')

    popup = tela.popup()
    popup.preencher_formulario(
        [
            ('Aprovado', 'checkbox', 'marcar'),
            ('Observação', 'TextArea', 'Obs sobre a finalização'),
        ]
    )
    popup.salvar_no_popup('Enviar')

    tela.sucesso('Conclusão do projeto registrada com sucesso.')
    registro = RegistroConclusaoProjeto.objects.filter(projeto__titulo=TITULO_PROJETO).order_by('-id').first()
    assert registro is not None, 'a UI disse que registrou, mas não há registro de conclusão'
    assert registro.aprovado, 'a UI disse que validou, mas a conclusão não ficou aprovada'
    assert registro.dt_avaliacao is not None, 'a UI disse que validou, mas o parecer ficou sem data'
    assert registro.obs_avaliador == 'Obs sobre a finalização', (
        f'a UI disse que validou, mas a observação do parecer gravou {registro.obs_avaliador!r}'
    )
