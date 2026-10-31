"""Capturas do fluxo de inscrição de um aluno."""

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]


def _grupo_familiar(tela: Tela) -> Tela:
    return tela.preencher_formulario(
        [
            ('Renda do Estudante', 'texto', '430,00'),
            ('Você estudou em escola particular com BOLSA DE ESTUDO INTEGRAL (ou seja, sem pagamento de mensalidade)?', 'lista', 'Não'),
            (
                'Você recebe acompanhamento pedagógico específico pelo NAPNE (Núcleo de Atendimento às Pessoas com necessidades educacionais específicas)?',
                'lista',
                'Não',
            ),
            ('Você reside ou é oriundo de comunidades tradicionais, quilombola ou indígena?', 'lista', 'Não'),
            ('Você mora ou já morou em abrigo institucional (orfanato)?', 'lista', 'Não, nunca morei'),
        ]
    ).clicar_botao('Continuar')


def test_captura_caracterizacao(logado_ae, caracterizacao_pronta, capturar):
    """Captura a tela independente de caracterização socioeconômica."""
    tela = Tela(logado_ae('aluno')).ir('/ae/caracterizacao/').ver_titulo('Caracterização Social')
    capturar(tela.pagina, 'caracterizacao-formulario')


def test_captura_fluxo_de_inscricao(logado_ae, caracterizacao_pronta, capturar):
    """Executa a inscrição e captura cada tela distinta do fluxo."""
    identificacao = Tela(logado_ae('assistente_social')).ir('/admin/ae/inscricao/').clicar_botao('Efetuar Inscrição')
    identificacao.ver_titulo('Efetuar Inscrição em Programa')
    capturar(identificacao.pagina, 'inscricao-identificacao')

    tela = Tela(logado_ae('aluno')).ir('/').clicar_link('Inscrever-se em: Alimentação Estudantil (CZN)')
    if 'two_factor_authentication' in tela.pagina.url:
        tela.preencher('Código', 'texto', '123456').clicar_botao('Autenticar')
    tela.ver_titulo('Inscrição para Alimentação Estudantil (CZN): Caracterização Socioeconômica')
    capturar(tela.pagina, 'inscricao-caracterizacao')

    tela.clicar_botao('Continuar').ver_titulo('Inscrição para Alimentação Estudantil (CZN): Caracterização do Grupo Familiar')
    capturar(tela.pagina, 'inscricao-grupo-familiar')

    _grupo_familiar(tela).ver_titulo('Inscrição para Alimentação Estudantil (CZN): Documentação')
    capturar(tela.pagina, 'inscricao-documentacao')
    tela.preencher('Comprovante de Residência', 'arquivo', 'comprovante.png').clicar_botao('Continuar')
    tela.sucesso('Informe as refeições que você deseja obter.')
    tela.ver_titulo('Inscrição para Alimentação Estudantil (CZN): Detalhamento')
    capturar(tela.pagina, 'inscricao-detalhamento')

    tela.preencher_formulario([('Motivo da inscrição', 'autocomplete', 'Aula no turno inverso'), ('Segunda', 'checkbox', 'marcar')]).clicar_botao(
        'Continuar'
    )
    tela.sucesso('Inscrição realizada com sucesso.')
    capturar(tela.pagina, 'inscricao-confirmacao')


def test_captura_minhas_inscricoes(logado_ae, ae_fluxos, inscricao_deferida, capturar):
    """Captura a aba em que o aluno acompanha as próprias inscrições."""
    inscricao_deferida(ae_fluxos['programas']['ALM'])
    tela = Tela(logado_ae('aluno')).ir('/ae/redireciona_minhas_inscricoes/')
    tela.ver_texto('Inscrições em Programas de Assistência Estudantil').ver_texto('Alimentação Estudantil (CZN)')
    capturar(tela.pagina, 'minhas-inscricoes')
