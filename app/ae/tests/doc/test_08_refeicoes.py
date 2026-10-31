"""Capturas do controle de refeições: o aluno solicita e o Serviço Social avalia."""

from datetime import time

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]


@pytest.fixture
def refeicao_solicitavel(ae_fluxos, caracterizacao_pronta, django_db_blocker):
    """Libera a solicitação no programa de alimentação e restaura o impedimento ao fim.

    O relógio está em 03/06/2024 12:00; com o horário "dia anterior, 08h às 18h" a
    solicitação feita agora é para o almoço de terça, 04/06, que tem oferta no seed.
    """
    from ae.models import (
        HorarioJustificativaFalta,
        HorarioSolicitacaoRefeicao,
        Participacao,
        SolicitacaoRefeicaoAluno,
        TipoRefeicao,
    )

    programa = ae_fluxos['programas']['ALM']
    aluno = ae_fluxos['aluno']
    horario = {
        'uo': programa.instituicao,
        'tipo_refeicao': TipoRefeicao.TIPO_ALMOCO,
        'hora_inicio': time(8),
        'dia_inicio': HorarioSolicitacaoRefeicao.DIA_ANTERIOR,
        'hora_fim': time(18),
        'dia_fim': HorarioSolicitacaoRefeicao.DIA_ANTERIOR,
    }
    with django_db_blocker.unblock():
        SolicitacaoRefeicaoAluno.objects.filter(aluno=aluno).delete()
        Participacao.objects.filter(aluno=aluno, programa=programa).delete()
        HorarioSolicitacaoRefeicao.objects.get_or_create(**horario)
        HorarioJustificativaFalta.objects.get_or_create(**horario)
        programa.impedir_solicitacao_beneficio = False
        programa.save(update_fields=['impedir_solicitacao_beneficio'])
        pessoa = aluno.pessoa_fisica
        pessoa.tem_digital_fraca = True
        pessoa.save(update_fields=['tem_digital_fraca'])
    yield programa
    with django_db_blocker.unblock():
        programa.impedir_solicitacao_beneficio = True
        programa.save(update_fields=['impedir_solicitacao_beneficio'])


def test_captura_solicitacao_e_avaliacao_de_refeicao(logado_doc, ae_fluxos, refeicao_solicitavel, capturar):
    from ae.models import SolicitacaoRefeicaoAluno

    programa = refeicao_solicitavel
    aluno = ae_fluxos['aluno']
    tela = Tela(logado_doc('aluno')).ir(f'/ae/solicitar_refeicao/{programa.pk}/').ver_titulo('Solicitar Refeição')
    tela.preencher('Tipo de Refeição', 'lista', 'Almoço')
    tela.preencher_formulario([('Motivo da Solicitação', 'lista', 'Aula no turno inverso'), ('Solicitação para', 'lista', '04/06/2024 (terça)')])
    capturar(tela.pagina, 'refeicao-solicitacao')
    tela.clicar_botao('Salvar').sucesso('Solicitação registrada com sucesso.')

    staff = Tela(logado_doc('assistente_social')).ir('/ae/redireciona_avaliar_solicitacao_refeicao/')
    staff.preencher('Data da Refeição', 'data', '04/06/2024').clicar_botao('Enviar')
    staff.ver_texto(aluno.matricula)
    capturar(staff.pagina, 'refeicao-avaliar-solicitacoes')
    staff.linha(aluno.matricula).clicar_botao('Deferir')
    staff.sucesso('Solicitação avaliada com sucesso.')
    assert SolicitacaoRefeicaoAluno.objects.get(aluno=aluno, programa=programa).deferida
