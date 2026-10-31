"""Capturas da coordenação: bolsas, financeiro, folha de pagamento, dashboard e CadÚnico."""

from datetime import date

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

CATEGORIA = 'Doc Monitoria'


def test_captura_participacao_em_bolsa(logado_doc, ae_fluxos, caracterizacao_pronta, django_db_blocker, capturar):
    """A coordenação inclui um aluno numa bolsa que não está ligada a programa."""
    from ae.models import CategoriaBolsa, ParticipacaoBolsa

    aluno = ae_fluxos['aluno']
    with django_db_blocker.unblock():
        ParticipacaoBolsa.objects.filter(aluno=aluno).delete()
        CategoriaBolsa.objects.get_or_create(nome=CATEGORIA, defaults={'vinculo_programa': False, 'ativa': True})

    tela = Tela(logado_doc('coordenador_campus')).ir('/ae/participacoes_bolsas/').ver_titulo('Participações em Bolsas')
    tela.clicar_botao('Adicionar Participação')
    popup = tela.popup().ver_titulo('Adicionar Participação')
    popup.preencher_formulario(
        [
            ('Aluno', 'autocomplete', aluno.matricula),
            ('Categoria da Bolsa', 'lista', CATEGORIA),
            ('Data de Entrada', 'data', '03/06/2024'),
        ]
    )
    tela.pagina.locator('.fancybox-slide--complete').wait_for()
    capturar(tela.pagina, 'bolsa-participacao-formulario')
    tela = popup.salvar_no_popup('Salvar')
    tela.sucesso('Participação adicionada com sucesso')
    capturar(tela.pagina, 'bolsas-participacoes')
    assert ParticipacaoBolsa.objects.filter(aluno=aluno, categoria__nome=CATEGORIA).exists()


def test_captura_valor_da_bolsa(logado_doc, ae_fluxos, django_db_blocker, capturar):
    """A coordenação cadastra o valor mensal da bolsa do campus no ano."""
    from ae.models import OfertaValorBolsa

    campus = ae_fluxos['programas']['TRB'].instituicao
    with django_db_blocker.unblock():
        OfertaValorBolsa.objects.filter(campus=campus, data_inicio__year=2024).delete()

    tela = Tela(logado_doc('coordenador_campus')).ir('/admin/ae/ofertavalorbolsa/add/').ver_titulo('Adicionar Valor da Bolsa')
    tela.preencher_formulario(
        [
            ('Campus', 'lista', 'CZN'),
            ('Valor Mensal da Bolsa (R$)', 'texto', '700,00'),
            ('Data Inicial', 'data', '01/01/2024'),
            ('Data Final', 'data', '31/12/2024'),
        ]
    )
    capturar(tela.pagina, 'financeiro-valor-bolsa-formulario')
    tela.clicar_botao('Salvar').sucesso('Cadastro realizado com sucesso.')
    assert OfertaValorBolsa.objects.filter(campus=campus, data_inicio__year=2024).exists()


def test_captura_folha_de_pagamento(logado_doc, ae_fluxos, inscricao_deferida, django_db_blocker, capturar):
    """Gera a folha de junho do Auxílio Transporte com um participante com valor concedido."""
    from ae.models import Participacao, ParticipacaoPasseEstudantil

    programa = ae_fluxos['programas']['PAS']
    inscricao = inscricao_deferida(programa)
    with django_db_blocker.unblock():
        participacao = Participacao.objects.create(
            programa=programa, aluno=inscricao.aluno, inscricao=inscricao, data_inicio=date(2024, 6, 3), motivo_entrada='Doc folha'
        )
        ParticipacaoPasseEstudantil.objects.create(participacao=participacao, valor_concedido=100)

    tela = Tela(logado_doc('assistente_social')).ir('/ae/redireciona_folha_pagamento/').ver_titulo('Gerar Folha de Pagamento')
    tela.preencher('Tipo do Programa', 'lista', 'Auxílio Transporte')
    capturar(tela.pagina, 'folha-pagamento-gerar')
    tela.clicar_botao('Enviar').ver_texto('Folha de Pagamento')
    tela.preencher_formulario(
        [
            ('Ano', 'lista', '2024'),
            ('Mês', 'lista', 'Junho'),
            ('Nome', 'checkbox', 'marcar'),
            ('Matrícula', 'checkbox', 'marcar'),
            ('Valor a Pagar', 'checkbox', 'marcar'),
        ]
    ).clicar_botao('Enviar')
    tela.ver_texto('Folha de pagamento processada com sucesso.').clicar_botao('Continuar')
    tela.ver_texto(inscricao.aluno.matricula)
    capturar(tela.pagina, 'folha-pagamento')


def test_captura_dashboard(logado_doc, ae_fluxos, capturar):
    """O dashboard do ano, com o checklist de cadastros do financeiro."""
    tela = Tela(logado_doc('assistente_social')).ir('/ae/dashboard/').ver_titulo('Dashboard')
    tela.preencher('Filtrar por Ano', 'lista', '2024').clicar_botao('Enviar')
    tela.ver_texto('Checklist')
    capturar(tela.pagina, 'dashboard')


def test_captura_agendamento_cadunico(logado_doc, ae_fluxos, django_db_blocker, capturar):
    """O coordenador sistêmico agenda a importação dos dados do CadÚnico."""
    from ae.models import ImportacaoCadunico

    with django_db_blocker.unblock():
        ImportacaoCadunico.objects.all().delete()

    tela = Tela(logado_doc('coordenador')).ir('/admin/ae/importacaocadunico/add/').ver_texto('Adicionar Importac')
    tela.preencher('Data da Importação', 'data', '03/06/2024')
    capturar(tela.pagina, 'cadunico-importacao-formulario')
    tela.clicar_botao('Salvar').sucesso('Cadastro realizado com sucesso.')
    assert ImportacaoCadunico.objects.exists()
