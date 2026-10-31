"""Capturas dos auxílios: eventuais (solicitados pelo aluno ou registrados) e da coordenação."""

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

TIPO_EVENTUAL = 'Doc Material escolar'
TIPO_COORDENACAO = 'Doc Apoio a eventos'


@pytest.fixture
def sem_auxilios_doc(django_db_blocker):
    from ae.models import TipoAtendimentoSetor, TipoAuxilioEventual

    with django_db_blocker.unblock():
        TipoAuxilioEventual.objects.filter(nome=TIPO_EVENTUAL).delete()
        TipoAtendimentoSetor.objects.filter(nome=TIPO_COORDENACAO).delete()


def test_captura_auxilio_eventual_solicitado(logado_doc, ae_fluxos, caracterizacao_pronta, sem_auxilios_doc, capturar):
    """Tipo cadastrado, ofertado no campus, solicitado, avaliado e comprovado."""
    from ae.models import SolicitacaoAuxilioAluno

    tela = Tela(logado_doc('coordenador')).ir('/admin/ae/tipoauxilioeventual/add/').ver_titulo('Adicionar Tipo de Auxílio Eventual')
    tela.preencher_formulario(
        [
            ('Nome', 'texto', TIPO_EVENTUAL),
            ('Descrição', 'textarea', 'Compra de material escolar.'),
            ('Prazo para comprovação da utilização (em dias)', 'texto', '10'),
        ]
    )
    capturar(tela.pagina, 'tipo-auxilio-eventual-formulario')
    tela.clicar_botao('Salvar').sucesso('Cadastro realizado com sucesso.')

    assistente = Tela(logado_doc('assistente_social')).ir(f'/admin/ae/tipoauxilioeventual/?q={TIPO_EVENTUAL}')
    assistente.linha(TIPO_EVENTUAL).clicar_botao('Incluir meu campus')
    assistente.sucesso('Modificação realizada com sucesso.')

    aluno = Tela(logado_doc('aluno')).ir('/').clicar_botao('Solicitar Auxílio Eventual')
    aluno.ver_titulo('Adicionar Solicitação de Auxílios Eventuais').preencher_formulario(
        [('Tipo do Auxílio', 'autocomplete', TIPO_EVENTUAL), ('Motivo da Solicitação', 'textarea', 'Preciso de material para as aulas práticas.')]
    )
    capturar(aluno.pagina, 'auxilio-eventual-solicitacao')
    aluno.clicar_botao('Salvar').sucesso('Cadastro realizado com sucesso.')

    assistente.ir('/admin/ae/solicitacaoauxilioaluno/')
    capturar(assistente.pagina, 'auxilio-eventual-solicitacoes')
    assistente.linha(TIPO_EVENTUAL).clicar_botao('Avaliar')
    assistente.ver_titulo('Avaliar Solicitação de Auxílio Eventual').preencher_formulario(
        [('Deferida', 'checkbox', 'marcar'), ('Parecer da Avaliação', 'textarea', 'Necessidade comprovada.')]
    )
    capturar(assistente.pagina, 'auxilio-eventual-avaliacao')
    assistente.clicar_botao('Salvar').sucesso('Solicitação avaliada com sucesso.')

    aluno.ir('/admin/ae/solicitacaoauxilioaluno/').linha(TIPO_EVENTUAL).clicar_botao('Adicionar comprovante de utilização')
    aluno.ver_titulo('Enviar Comprovante da Utilização do Auxílio')
    aluno.preencher('Comprovantes da Utilização do Auxílio', 'arquivo', 'comprovante.png').clicar_botao('Salvar')
    aluno.sucesso('Comprovante cadastrado com sucesso.')

    assistente.ir('/admin/ae/solicitacaoauxilioaluno/').linha(TIPO_EVENTUAL).clicar_botao('Avaliar comprovante')
    assistente.ver_titulo('Avaliar comprovante de utilização do auxílio').preencher('Deferida', 'checkbox', 'marcar')
    capturar(assistente.pagina, 'auxilio-eventual-comprovante-avaliacao')
    assistente.clicar_botao('Salvar').sucesso('Comprovante avaliado com sucesso.')

    solicitacao = SolicitacaoAuxilioAluno.objects.get(aluno=ae_fluxos['aluno'], tipo_auxilio__nome=TIPO_EVENTUAL)
    assert solicitacao.deferida
    assert not solicitacao.comprovacao_pendente


def test_captura_auxilio_eventual_registrado(logado_doc, ae_fluxos, sem_auxilios_doc, django_db_blocker, capturar):
    """A Assistente Social registra um auxílio eventual concedido sem solicitação do aluno."""
    from ae.models import AuxilioEventual, TipoAuxilioEventual

    with django_db_blocker.unblock():
        TipoAuxilioEventual.objects.create(nome=TIPO_EVENTUAL, descricao='Compra de material escolar.')

    tela = Tela(logado_doc('assistente_social')).ir('/admin/ae/auxilioeventual/add/').ver_titulo('Adicionar Auxílio Eventual')
    tela.preencher_formulario(
        [
            ('Aluno', 'autocomplete', ae_fluxos['aluno'].matricula),
            ('Tipo do Auxílio', 'autocomplete', TIPO_EVENTUAL),
            ('Atendimento', 'data e hora', '03/06/2024 10:00'),
            ('Valor', 'texto', '80,00'),
        ]
    )
    capturar(tela.pagina, 'auxilio-eventual-formulario')
    tela.clicar_botao('Salvar').sucesso('Cadastro realizado com sucesso.')
    assert AuxilioEventual.objects.filter(aluno=ae_fluxos['aluno'], tipo_auxilio__nome=TIPO_EVENTUAL).exists()


def test_captura_auxilio_coordenacao(logado_doc, ae_fluxos, sem_auxilios_doc, django_db_blocker, capturar):
    """A coordenação do campus registra um auxílio concedido a um grupo de alunos."""
    from ae.models import AtendimentoSetor, TipoAtendimentoSetor

    with django_db_blocker.unblock():
        TipoAtendimentoSetor.objects.create(nome=TIPO_COORDENACAO, descricao='Apoio à participação em eventos.')

    tela = Tela(logado_doc('coordenador_campus')).ir('/admin/ae/atendimentosetor/add/').ver_titulo('Adicionar Auxílio')
    tela.preencher_formulario(
        [
            ('Campus', 'autocomplete', 'CZN'),
            ('Tipo de Auxílio', 'autocomplete', TIPO_COORDENACAO),
            ('Data de Início', 'data e hora', '03/06/2024 08:00'),
            ('Valor Total Utilizado', 'texto', '500,00'),
            ('Alunos', 'autocomplete multiplo', ae_fluxos['aluno'].matricula),
        ]
    )
    capturar(tela.pagina, 'auxilio-coordenacao-formulario')
    tela.clicar_botao('Salvar').sucesso('Cadastro realizado com sucesso.')
    assert AtendimentoSetor.objects.filter(tipoatendimentosetor__nome=TIPO_COORDENACAO).exists()
