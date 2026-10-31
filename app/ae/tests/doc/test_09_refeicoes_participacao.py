"""Capturas do controle de refeições do participante: falta, suspensão, alteração e relatório diário."""

from datetime import date, datetime

import pytest

from ae.tests.doc.test_08_refeicoes import refeicao_solicitavel
from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]


@pytest.fixture
def participacao_alimentacao(refeicao_solicitavel, inscricao_deferida, django_db_blocker):
    """Participante do almoço de segunda e terça, com os horários de solicitação e de falta do campus."""
    from ae.models import (
        AlteracaoParticipacaoAlimentacao,
        CategoriaAlimentacao,
        HistoricoFaltasAlimentacao,
        MotivoSolicitacaoRefeicao,
        Participacao,
        ParticipacaoAlimentacao,
        SolicitacaoAlimentacao,
    )

    programa = refeicao_solicitavel
    inscricao = inscricao_deferida(programa)
    with django_db_blocker.unblock():
        HistoricoFaltasAlimentacao.objects.filter(aluno=inscricao.aluno).delete()
        AlteracaoParticipacaoAlimentacao.objects.filter(participacao__aluno=inscricao.aluno).delete()
        participacao = Participacao.objects.create(
            programa=programa, aluno=inscricao.aluno, inscricao=inscricao, data_inicio=date(2024, 6, 3), motivo_entrada='Doc refeições'
        )
        return ParticipacaoAlimentacao.objects.create(
            participacao=participacao,
            categoria=CategoriaAlimentacao.objects.get(nome='AS'),
            motivo_atendimento=MotivoSolicitacaoRefeicao.objects.get(descricao='Aula no turno inverso'),
            solicitacao_atendida_cafe=SolicitacaoAlimentacao.objects.create(),
            solicitacao_atendida_almoco=SolicitacaoAlimentacao.objects.create(seg=True, ter=True),
            solicitacao_atendida_janta=SolicitacaoAlimentacao.objects.create(),
        )


def _capturar_popup(tela: Tela, capturar, nome: str) -> None:
    tela.pagina.locator('.fancybox-slide--complete').wait_for()
    capturar(tela.pagina, nome)


def test_captura_informar_falta(logado_doc, participacao_alimentacao, capturar):
    """O participante avisa com antecedência que não vai almoçar."""
    from ae.models import HistoricoFaltasAlimentacao

    participacao = participacao_alimentacao.participacao
    tela = Tela(logado_doc('aluno')).ir(f'/ae/justificar_falta/{participacao.aluno.pk}/{participacao.programa.pk}/')
    tela.ver_titulo('Informar falta no Programa de Alimentação').preencher_formulario(
        [
            ('Dia da Refeição', 'data', '04/06/2024'),
            ('Tipo de Refeição', 'lista', 'Almoço'),
            ('Justificativa', 'textarea', 'Consulta médica no horário do almoço.'),
        ]
    )
    capturar(tela.pagina, 'refeicao-informar-falta')
    tela.clicar_botao('Enviar').sucesso('Justificativa cadastrada com sucesso.')
    assert HistoricoFaltasAlimentacao.objects.filter(aluno=participacao.aluno, justificativa__isnull=False).exists()


def test_captura_participacao_suspensa(logado_doc, participacao_alimentacao, django_db_blocker, capturar):
    """O Serviço Social agenda o desbloqueio de uma participação suspensa e depois a libera."""
    from ae.models import ParticipacaoAlimentacao

    with django_db_blocker.unblock():
        participacao_alimentacao.suspensa = True
        participacao_alimentacao.suspensa_em = date(2024, 5, 31)
        participacao_alimentacao.save(update_fields=['suspensa', 'suspensa_em'])

    programa = participacao_alimentacao.participacao.programa
    tela = Tela(logado_doc('assistente_social')).ir(f'/ae/liberar_participacao_alimentacao/{programa.pk}/')
    tela.ver_titulo('Participações Suspensas')
    capturar(tela.pagina, 'refeicao-participacoes-suspensas')

    tela.clicar_botao('Agendar Desbloqueio').ver_titulo('Data de Desbloqueio Automático')
    tela.preencher('Data da Liberação', 'data', '10/06/2024')
    capturar(tela.pagina, 'refeicao-agendar-desbloqueio')
    tela.clicar_botao('Salvar').sucesso('Agendamento de desbloqueio realizado com sucesso.')

    tela.clicar_botao('Liberar Participação').sucesso('Participação liberada com sucesso.')
    assert not ParticipacaoAlimentacao.objects.get(pk=participacao_alimentacao.pk).suspensa


def test_captura_alteracao_de_refeicoes(logado_doc, ae_fluxos, participacao_alimentacao, django_db_blocker, capturar):
    """O participante pede para trocar os dias de almoço e o Serviço Social defere."""
    from ae.models import AlteracaoParticipacaoAlimentacao

    programa = participacao_alimentacao.participacao.programa
    with django_db_blocker.unblock():
        programa.data_inicio_alteracoes = datetime(2024, 6, 1)
        programa.data_fim_alteracoes = datetime(2024, 6, 30, 23, 59)
        programa.save(update_fields=['data_inicio_alteracoes', 'data_fim_alteracoes'])
    try:
        aluno = Tela(logado_doc('aluno')).ir(f'/edu/aluno/{ae_fluxos["aluno"].matricula}/?tab=atividades_estudantis')
        # Página inteira, não popup: ao enviar, a view volta para a aba do aluno com a mensagem.
        aluno.clicar_botao('Solicitar Alteração de Dias/Refeições')
        aluno.ver_titulo('Solicitar Alteração de Dias/Refeições').preencher_formulario(
            [('Almoço', 'checkbox multiplo', 'Quarta'), ('Motivo da Solicitação', 'textarea', 'Mudança no horário das aulas práticas.')]
        )
        capturar(aluno.pagina, 'refeicao-solicitar-alteracao')
        aluno.clicar_botao('Enviar').sucesso('Solicitação realizada com sucesso.')

        tela = Tela(logado_doc('assistente_social')).ir('/admin/ae/alteracaoparticipacaoalimentacao/?deferida__isnull=True')
        capturar(tela.pagina, 'refeicao-alteracoes-pendentes')
        tela.clicar_botao('Deferir')
        popup = tela.popup().ver_titulo('Deferir Alteração de Participação')
        popup.preencher_formulario([('Data de Saída', 'data', '09/06/2024'), ('Categoria', 'lista', 'AS'), ('Almoço', 'checkbox multiplo', 'Quarta')])
        _capturar_popup(tela, capturar, 'refeicao-deferir-alteracao')
        popup.clicar_botao('Salvar').sucesso('Solicitação deferida com sucesso.')
        assert AlteracaoParticipacaoAlimentacao.objects.get(participacao=participacao_alimentacao.participacao).deferida
    finally:
        with django_db_blocker.unblock():
            programa.data_inicio_alteracoes = programa.data_fim_alteracoes = None
            programa.save(update_fields=['data_inicio_alteracoes', 'data_fim_alteracoes'])


def test_captura_relatorio_diario(logado_doc, participacao_alimentacao, capturar):
    """O relatório diário das refeições de um dia útil, gerado em PDF."""
    tela = Tela(logado_doc('assistente_social')).ir('/ae/redireciona_relatorio_diario/').ver_titulo('Relatório Diário')
    tela.preencher('Data', 'data', '04/06/2024')
    capturar(tela.pagina, 'refeicao-relatorio-diario')
    tela.clicar_botao('Enviar').ver_texto('100 %')
    capturar(tela.pagina, 'refeicao-relatorio-diario-processado')
