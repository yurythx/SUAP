"""Fluxo 005: avaliação por conceito — lançamento em letra e boletim.

Variante do lançamento de nota, e não um fluxo novo: a mesma etapa, o mesmo diário, a
mesma entrega — só que a estrutura de curso é "Conceito" em vez de "Nota", e aí o SUAP
aceita as letras de ``settings.REPRESENTACAO_CONCEITUAL`` (A=100, B=80, C=60, D=0) e
converte para nota internamente. O que se cobre é justamente essa conversão: a letra
digitada tem de virar nota no banco e voltar como letra no boletim.

Roda sobre o curso 20202 ("[CONCEITO]"), separado do 10101 dos módulos 05→07 de propósito:
é o mesmo componente (POS.0001) em outra matriz, com outra estrutura de curso.
"""

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

DATA = '21/03/2019'
CONCEITO = 'B'


@pytest.fixture
def diario_conceito(seed_conceito):
    """Diário POS.0001 da turma do curso "[CONCEITO]", com a etapa 1 em posse do professor.

    Zera conceito, aula e posse como o módulo 05 faz com o diário de nota: entregar a etapa
    é irreversível pela tela do professor e a suíte não dá flush.
    """
    from edu.models import Aula, Diario, MatriculaDiario, NotaAvaliacao

    # `turma__periodo_letivo=1` não é redundante: `test_03_turmas` gera turmas de 2019.2
    # nesse mesmo curso pelo assistente, e sem o recorte o `get` encontra dois diários.
    diario = Diario.objects.get(componente_curricular__componente__sigla='POS.0001', turma__curso_campus__codigo='20202', turma__periodo_letivo=1)
    assert diario.is_lancamento_conceito(), 'o diário do curso 20202 não está configurado para conceito'
    Diario.objects.filter(pk=diario.pk).update(posse_etapa_1=Diario.POSSE_PROFESSOR, situacao=Diario.SITUACAO_ABERTO)
    Aula.objects.filter(professor_diario__diario=diario, etapa=1).delete()
    NotaAvaliacao.objects.filter(matricula_diario__diario=diario, item_configuracao_avaliacao__configuracao_avaliacao__etapa=1).update(nota=None)
    MatriculaDiario.objects.filter(diario=diario).update(nota_1=None, situacao=MatriculaDiario.SITUACAO_CURSANDO)
    diario.refresh_from_db()
    return diario


def test_professor_registra_conceitos_e_entrega_etapa(logado_edu, relogio, diario_conceito):
    """Conceito por avaliação, conceito final por aluno, e a etapa fecha.

    São dois endpoints diferentes e os dois precisam ser exercitados: o conceito da avaliação
    (``registrar_conceito_ajax``, por ``NotaAvaliacao``) e o conceito consolidado da etapa
    (``registrar_conceito_final_ajax``, por ``MatriculaDiario``). Sem o segundo a etapa não
    tem nota de etapa e a entrega é recusada.

    Os PKs saem de queryset, nunca literais como na ``.feature``: aqui o banco é reusado
    entre execuções e ``/edu/registrar_conceito_ajax/5/A`` apontaria para outro aluno.
    """
    from edu.models import Aula, MatriculaDiario, NotaAvaliacao, ProfessorDiario

    matriculas = MatriculaDiario.objects.filter(diario=diario_conceito, situacao=MatriculaDiario.SITUACAO_CURSANDO)
    assert matriculas.exists(), 'diário de conceito sem aluno cursando'

    page = logado_edu('professor')
    for matricula_diario in matriculas:
        avaliacoes = NotaAvaliacao.objects.filter(matricula_diario=matricula_diario, item_configuracao_avaliacao__configuracao_avaliacao__etapa=1)
        for avaliacao in avaliacoes:
            resposta = page.goto(f'/edu/registrar_conceito_ajax/{avaliacao.pk}/{CONCEITO}/')
            assert resposta.status == 200, 'o endpoint de conceito recusou o lançamento'
        resposta = page.goto(f'/edu/registrar_conceito_final_ajax/{matricula_diario.pk}/1/{CONCEITO}/')
        assert resposta.status == 200, 'o endpoint de conceito final recusou o lançamento'

    # B = 80 na configuração de `REPRESENTACAO_CONCEITUAL`: é assim que o conceito é gravado.
    matricula_diario = matriculas.first()
    matricula_diario.refresh_from_db()
    assert matricula_diario.nota_1 == 80, f'conceito {CONCEITO} não converteu para nota'

    # Sem aula registrada a etapa não pode ser entregue.
    professor_diario = ProfessorDiario.objects.get(diario=diario_conceito, professor__vinculo__user__username='100007')
    Aula.objects.create(etapa=1, quantidade=60, data='2019-03-20', conteudo='Apresentação da disciplina', professor_diario=professor_diario)

    relogio.congelar('20/07/2019')
    tela = Tela(page).ir(f'/edu/entregar_etapa/{diario_conceito.pk}/1/')
    tela.clicar_botao('Confirmar Entrega')

    tela.sucesso('Etapa entregue com sucesso.')
    diario_conceito.refresh_from_db()
    assert diario_conceito.em_posse_do_registro(1), 'etapa entregue mas a posse não passou para o registro escolar'


def test_conceito_aparece_no_boletim_do_aluno(logado_edu, relogio, diario_conceito):
    """O boletim mostra a letra, não o número — é a volta da conversão.

    O conceito é lançado por ORM porque o caminho de interface dele é o teste anterior; o que
    esta verificação cobre é o boletim do prontuário, que a secretaria usa para conferir.
    """
    from edu.models import MatriculaDiario

    matricula_diario = MatriculaDiario.objects.filter(diario=diario_conceito, situacao=MatriculaDiario.SITUACAO_CURSANDO).first()
    MatriculaDiario.objects.filter(pk=matricula_diario.pk).update(nota_1=80)
    aluno = matricula_diario.matricula_periodo.aluno

    relogio.congelar('20/07/2019')
    tela = Tela(logado_edu('secretario')).ir(f'/edu/aluno/{aluno.matricula}/?tab=boletins')

    tela.ver_texto(CONCEITO)
