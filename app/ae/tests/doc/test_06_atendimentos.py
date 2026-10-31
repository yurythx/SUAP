"""Capturas dos registros do Serviço Social: atendimentos, ações educativas e atividades diversas."""

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

ACAO = 'Doc Roda de conversa sobre permanência'
TIPO_ATIVIDADE = 'Doc Visita domiciliar'


def test_captura_atendimento_individual(logado_doc, ae_fluxos, django_db_blocker, capturar):
    """A Assistente Social registra um atendimento individual a um aluno."""
    from ae.models import DemandaAlunoAtendida

    aluno = ae_fluxos['aluno']
    with django_db_blocker.unblock():
        DemandaAlunoAtendida.objects.filter(aluno=aluno).delete()

    tela = Tela(logado_doc('assistente_social')).ir('/ae/lista_alunodemandaatendida/')
    tela.clicar_botao('Adicionar Atendimento Individual').ver_titulo('Adicionar Atendimento Individual')
    tela.preencher_formulario(
        [
            ('Tipo de Atendimento', 'autocomplete', 'Almoço'),
            ('Campus', 'autocomplete', 'CZN'),
            ('Aluno', 'autocomplete', aluno.matricula),
            ('Quantidade', 'texto', '1'),
        ]
    )
    capturar(tela.pagina, 'atendimento-individual-formulario')
    tela.clicar_botao('Salvar').sucesso('Cadastro realizado com sucesso.')
    assert DemandaAlunoAtendida.objects.filter(aluno=aluno).exists()


def test_captura_acao_educativa_e_atividade_diversa(logado_doc, ae_fluxos, django_db_blocker, capturar):
    """Registra uma ação educativa e uma atividade diversa do Serviço Social."""
    from ae.models import AcaoEducativa, AtividadeDiversa, TipoAtividadeDiversa

    with django_db_blocker.unblock():
        AcaoEducativa.objects.filter(titulo=ACAO).delete()
        AtividadeDiversa.objects.filter(tipo__nome=TIPO_ATIVIDADE).delete()
        TipoAtividadeDiversa.objects.get_or_create(nome=TIPO_ATIVIDADE)

    tela = Tela(logado_doc('assistente_social')).ir('/admin/ae/acaoeducativa/add/').ver_titulo('Adicionar Ação Educativa')
    tela.preencher_formulario(
        [
            ('Título', 'texto', ACAO),
            ('Campus', 'autocomplete', 'CZN'),
            ('Data de Início', 'data e hora', '03/06/2024 14:00'),
            ('Descrição', 'textarea', 'Encontro com os alunos ingressantes.'),
            ('Servidores Envolvidos', 'autocomplete multiplo', 'Assistente Social'),
        ]
    )
    capturar(tela.pagina, 'acao-educativa-formulario')
    tela.clicar_botao('Salvar').sucesso('Cadastro realizado com sucesso.')

    tela.ir('/admin/ae/atividadediversa/add/').ver_titulo('Adicionar Atividade Diversa')
    tela.preencher_formulario(
        [
            ('Tipo', 'autocomplete', TIPO_ATIVIDADE),
            ('Campus', 'autocomplete', 'CZN'),
            ('Data de Início', 'data e hora', '03/06/2024 09:00'),
            ('Observação', 'textarea', 'Visita à família do aluno.'),
            ('Servidores Envolvidos', 'autocomplete multiplo', 'Assistente Social'),
        ]
    )
    capturar(tela.pagina, 'atividade-diversa-formulario')
    tela.clicar_botao('Salvar').sucesso('Cadastro realizado com sucesso.')
    assert AtividadeDiversa.objects.filter(tipo__nome=TIPO_ATIVIDADE).exists()
