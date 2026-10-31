"""Tarefas 6 e 7 — executar o diário e pedir o relançamento de uma etapa.

Tarefa 6 é o dia a dia do professor: forma de avaliação, aula, falta, nota e entrega da
etapa. Tarefa 7 é o que ele faz depois de entregar — a etapa sai da mão dele e só volta
por uma solicitação que a secretaria defere.

Aqui a nota e a falta são lançadas **pela planilha**, preenchendo o campo e saindo dele
(``blur``), e não chamando o endpoint AJAX direto como fazem os e2e: o passo que a doc
escreve é "digite a nota e saia do campo", e é ele que precisa ter sido executado.
"""

from __future__ import annotations

import pytest

from djtools.e2e_ui import Tela
from edu.tests.doc.conftest import anotar

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

DATA = '21/03/2019'
MATRICULA_ALUNO = '20191101010001'


@pytest.fixture
def diario_do_professor(edu_seed):
    """Diário POS.0001 da turma 2019.1 do curso 10101, com a etapa 1 em posse do professor.

    Devolve também o **período letivo do aluno** para *matriculado*. Não é zelo: a validação
    "todas as notas lançadas" só olha para matrícula-período MATRICULADA
    (``edu/models/diarios.py:597``), e as tarefas 8 e 10 fecham o período 2019.1 no mesmo
    banco. Sem esta linha, rodar esta fatia depois daquelas faz a entrega **sem nota** ser
    aceita — e a doc afirma o contrário. Medido em 03/08/2026.
    """
    from edu.models import Aula, Diario, MatriculaDiario, MatriculaPeriodo, NotaAvaliacao, SituacaoMatriculaPeriodo, SolicitacaoRelancamentoEtapa

    diario = Diario.objects.get(
        componente_curricular__componente__sigla='POS.0001',
        turma__curso_campus__codigo='10101',
        turma__periodo_letivo=1,
    )
    Diario.objects.filter(pk=diario.pk).update(posse_etapa_1=Diario.POSSE_PROFESSOR, situacao=Diario.SITUACAO_ABERTO)
    Aula.objects.filter(professor_diario__diario=diario, etapa=1).delete()
    NotaAvaliacao.objects.filter(matricula_diario__diario=diario, item_configuracao_avaliacao__configuracao_avaliacao__etapa=1).update(nota=None)
    MatriculaDiario.objects.filter(diario=diario).update(nota_1=None, situacao=MatriculaDiario.SITUACAO_CURSANDO)
    SolicitacaoRelancamentoEtapa.objects.filter(professor_diario__diario=diario).delete()
    MatriculaPeriodo.objects.filter(turma=diario.turma).update(situacao=SituacaoMatriculaPeriodo.MATRICULADO)
    diario.refresh_from_db()
    return diario


def test_meus_diarios(logado_edu, diario_do_professor, capturar):
    """A porta de entrada do professor: os diários dele, filtrados por período letivo."""
    page = logado_edu('professor')
    tela = Tela(page).ir('/edu/meus_diarios/')
    anotar('meus-diarios', tela)
    page.select_option('select[name=ano-periodo]', label='2019.1')
    tela.esperar()
    capturar(page, 'meus-diarios')

    link = page.get_by_role('link', name=f'{diario_do_professor.pk} - POS.0001')
    link.first.click()
    tela.esperar()
    # Nome distinto de `diario-professor` (a captura do popup de vínculo, na tarefa 4): dois
    # `capturar` com o mesmo nome sobrescrevem o mesmo arquivo e a doc ilustra a tela errada.
    anotar('diario-etapa', tela)
    capturar(page, 'diario-etapa')
    tela.ver_titulo('POS.0001')


def test_configurar_forma_de_avaliacao(logado_edu, diario_do_professor, capturar):
    """Quantas avaliações a etapa cobra, com que sigla e em que data."""
    configuracao = diario_do_professor.configuracao_avaliacao_1()
    item = configuracao.itemconfiguracaoavaliacao_set.first()
    assert item is not None, 'a configuração de avaliação nasce com um item; sem ele não há o que editar'
    original = (item.sigla, item.descricao)
    try:
        tela = Tela(logado_edu('professor')).ir(f'/admin/edu/configuracaoavaliacao/{configuracao.pk}/change/')
        anotar('forma-avaliacao', tela)
        tela.preencher_linha(0, 'sigla', 'texto', 'S1')
        tela.preencher_linha(0, 'descricao', 'texto', 'Avaliação final')
        tela.preencher_linha(0, 'data', 'data', '20/07/2019')
        capturar(tela.pagina, 'forma-avaliacao')
        tela.clicar_botao('Salvar')

        tela.sucesso('Atualização realizada com sucesso.')
        item.refresh_from_db()
        assert item.sigla == 'S1', 'a UI disse que salvou, mas a avaliação não mudou'
    finally:
        type(item).objects.filter(pk=item.pk).update(sigla=original[0], descricao=original[1])


def test_registrar_aula_lancar_falta_e_nota(logado_edu, relogio, diario_do_professor, capturar):
    """O ciclo completo da etapa: aula → falta → nota → entrega.

    Num teste só porque cada passo é pré-condição do seguinte e o SUAP recusa a ordem
    trocada: sem aula não há chamada, sem nota lançada a etapa não é entregue.
    """
    from edu.models import Aula, Falta, MatriculaDiario, NotaAvaliacao

    page = logado_edu('professor')
    tela = Tela(page)

    # -- aula ---------------------------------------------------------------------------
    tela.ir(f'/edu/adicionar_aula_diario/{diario_do_professor.pk}/1/')
    tela.ver_titulo('Adicionar Aula')
    anotar('aula-formulario', tela)
    tela.preencher_formulario(
        [
            ('Quantidade', 'texto', '60'),
            ('Etapa', 'lista', 'Primeira'),
            ('Data', 'data', '20/03/2019'),
            ('Conteúdo', 'textarea', 'Apresentação da disciplina'),
        ]
    )
    capturar(page, 'aula-formulario')
    tela.clicar_botao('Salvar')
    tela.sucesso('Aula cadastrada/atualizada com sucesso.')
    aula = Aula.objects.filter(professor_diario__diario=diario_do_professor, etapa=1).first()
    assert aula is not None, 'a UI disse que salvou, mas a aula não persistiu'

    # -- falta --------------------------------------------------------------------------
    matricula_diario = MatriculaDiario.objects.filter(diario=diario_do_professor, situacao=MatriculaDiario.SITUACAO_CURSANDO).first()
    assert matricula_diario is not None, 'diário sem aluno cursando: nada a chamar'
    tela.ir(f'/edu/meu_diario/{diario_do_professor.pk}/1/?tab=faltas')
    anotar('diario-faltas', tela)
    campo = page.locator(f'input[name="{matricula_diario.pk};{aula.pk}"]')
    campo.fill('1')
    campo.blur()
    tela.esperar()
    capturar(page, 'diario-faltas')
    assert Falta.objects.filter(matricula_diario=matricula_diario, aula=aula, quantidade=1).exists(), (
        'falta digitada na planilha não persistiu: a gravação por saída do campo mudou'
    )

    # -- nota ---------------------------------------------------------------------------
    tela.ir(f'/edu/meu_diario/{diario_do_professor.pk}/1/?tab=notas')
    anotar('diario-notas', tela)
    avaliacoes = NotaAvaliacao.objects.filter(
        matricula_diario__diario=diario_do_professor,
        matricula_diario__situacao=MatriculaDiario.SITUACAO_CURSANDO,
        item_configuracao_avaliacao__configuracao_avaliacao__etapa=1,
    )
    for avaliacao in avaliacoes:
        nota = page.locator(f'input[name="1;{avaliacao.matricula_diario_id};{avaliacao.item_configuracao_avaliacao_id}"]')
        nota.fill('70')
        nota.blur()
        tela.esperar()
    capturar(page, 'diario-notas')
    for avaliacao in avaliacoes:
        avaliacao.refresh_from_db()
        assert avaliacao.nota == 70, 'nota digitada na planilha não persistiu'

    # -- entrega da etapa ---------------------------------------------------------------
    # A entrega só é aceita dentro da janela do calendário (a etapa 1 vai até 18/07/2019).
    relogio.congelar('20/07/2019')
    tela.ir(f'/edu/entregar_etapa/{diario_do_professor.pk}/1/')
    anotar('etapa-entrega', tela)
    capturar(page, 'etapa-entrega')
    page.click('input[type=submit]')
    tela.sucesso('Etapa entregue com sucesso.')

    diario_do_professor.refresh_from_db()
    assert diario_do_professor.em_posse_do_registro(1), 'etapa entregue mas a posse não passou para o registro escolar'


def test_entrega_sem_nota_e_recusada(logado_edu, relogio, diario_do_professor):
    """A validação que a doc afirma: sem todas as notas lançadas, a etapa não é entregue."""
    from edu.models import Aula, ProfessorDiario

    professor_diario = ProfessorDiario.objects.get(diario=diario_do_professor, professor__vinculo__user__username='100007')
    Aula.objects.create(etapa=1, quantidade=60, data='2019-03-20', conteudo='Apresentação', professor_diario=professor_diario)

    relogio.congelar('20/07/2019')
    tela = Tela(logado_edu('professor')).ir(f'/edu/entregar_etapa/{diario_do_professor.pk}/1/')
    tela.pagina.click('input[type=submit]')
    tela.esperar()

    # Busca no conteúdo inteiro, e não só no banner de erro: o que a doc afirma é que a
    # entrega é RECUSADA, e a recusa aparece ora como banner, ora como texto da própria tela
    # de confirmação. O diagnóstico entra na mensagem porque este é o único teste da suíte
    # cujo desfecho esperado é um erro — se ele mudar de forma, a doc precisa saber qual é.
    assert 'notas forem lançadas' in tela.pagina.content(), f'a entrega sem nota não foi recusada. {tela.diagnostico()}'
    diario_do_professor.refresh_from_db()
    assert not diario_do_professor.em_posse_do_registro(1), 'a etapa foi entregue mesmo com aluno sem nota'


def test_solicitar_e_deferir_relancamento(logado_edu, relogio, diario_do_professor, capturar):
    """Tarefa 7 — os dois lados do relançamento: o professor pede, a secretaria defere."""
    from edu.models import Aula, ProfessorDiario, SolicitacaoRelancamentoEtapa

    professor_diario = ProfessorDiario.objects.get(diario=diario_do_professor, professor__vinculo__user__username='100007')
    Aula.objects.create(etapa=1, quantidade=60, data='2019-03-20', conteudo='Apresentação', professor_diario=professor_diario)
    # Pré-condição montada por ORM: sem etapa entregue não existe relançamento a pedir, e a
    # entrega pela interface é a tarefa 6.
    diario_do_professor.entregar_etapa(1)

    relogio.congelar('20/07/2019')
    tela = Tela(logado_edu('professor')).ir(f'/edu/solicitar_relancamento_etapa/{professor_diario.pk}/1/')
    anotar('relancamento-formulario', tela)
    tela.preencher('Motivo', 'textarea', 'Faltou lançar a nota de um aluno.')
    capturar(tela.pagina, 'relancamento-formulario')
    tela.pagina.click('input[type=submit]')
    tela.sucesso('Solicitação enviada com sucesso.')

    solicitacao = SolicitacaoRelancamentoEtapa.objects.filter(professor_diario=professor_diario, etapa=1).first()
    assert solicitacao is not None, 'solicitação de relançamento não registrada'

    secretaria = Tela(logado_edu('secretario')).ir('/admin/edu/solicitacaousuario/?tab=tab_pendentes')
    anotar('solicitacoes-pendentes', secretaria)
    capturar(secretaria.pagina, 'solicitacoes-pendentes')
    secretaria.ir(f'/edu/solicitacaousuario/{solicitacao.pk}/')
    anotar('solicitacao-detalhe', secretaria)
    capturar(secretaria.pagina, 'solicitacao-detalhe')
    secretaria.clicar_botao('Deferir')

    secretaria.sucesso('Solicitação deferida com sucesso.')
    diario_do_professor.refresh_from_db()
    assert not diario_do_professor.em_posse_do_registro(1), 'solicitação deferida mas a posse não voltou ao professor'
