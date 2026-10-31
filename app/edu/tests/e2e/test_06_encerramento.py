"""Fluxo 007: encerrar o período letivo — fechar, reabrir e retomar a posse do diário.

Sexto elo. O fechamento é o que consolida a situação do aluno no período (aprovado,
reprovado, em dependência) e é pré-requisito da renovação de matrícula do módulo 07.
Duas particularidades que só aparecem no browser:

* o processamento é **assíncrono** (``edu/tasks.py:fechar_periodo``): o submit não
  responde com a mensagem de sucesso, responde com a tela de acompanhamento da tarefa;
* fechar e reabrir são o mesmo formulário em duas rotas, e cada um só aceita matrícula na
  situação oposta — por isso cada teste monta a sua pré-condição por ORM e usa a
  interface só para a ação que está medindo.
"""

import pytest
from playwright.sync_api import expect

from djtools.e2e_fixtures import escolher_autocomplete, mensagem_de_sucesso
from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

DATA = '20/07/2019'
FECHAR = '/edu/fechar_periodo_letivo/'
REABRIR = '/edu/abrir_periodo_letivo/'


@pytest.fixture
def turma_2019_1(seed_periodo_executado):
    """Turma 2019.1 do curso 10101, com a etapa 1 já executada (aula, nota, entrega)."""
    from edu.models import Turma

    return Turma.objects.get(ano_letivo__ano=2019, periodo_letivo=1, curso_campus__codigo='10101')


@pytest.fixture
def periodo_aberto(turma_2019_1):
    """Garante matrícula-período MATRICULADA na turma — o que "Fechar Período" consome."""
    from edu.models import MatriculaPeriodo, SituacaoMatriculaPeriodo

    MatriculaPeriodo.objects.filter(turma=turma_2019_1).update(situacao=SituacaoMatriculaPeriodo.MATRICULADO)
    return turma_2019_1


@pytest.fixture
def periodo_fechado(turma_2019_1):
    """Garante matrícula-período já fechada — o que "Reabrir Período" consome."""
    from edu.models import MatriculaPeriodo, SituacaoMatriculaPeriodo

    MatriculaPeriodo.objects.filter(turma=turma_2019_1).update(situacao=SituacaoMatriculaPeriodo.APROVADO)
    return turma_2019_1


def _preencher_selecao_por_turma(page, turma) -> None:
    """Passo 1 dos dois assistentes: ano, período, tipo "Por Turma" e a turma."""
    page.select_option('select[name=ano_letivo]', label='2019')
    page.select_option('select[name=periodo_letivo]', label='1')
    page.check('input[name=tipo][value="TURMA"]')
    # Sem `opcao=''` pelo mesmo motivo de `test_11_formatura`: o rótulo é o próprio código da
    # turma, e aceitar "o primeiro resultado" pega a resposta do AJAX disparado sobre um
    # prefixo do texto digitado — turma errada, assistente travado.
    escolher_autocomplete(page, 'turma', str(turma))
    page.click('input[type=submit][value="Continuar"]')


def test_fecha_periodo_letivo_por_turma(logado_edu, periodo_aberto):
    """Fechamento forçado: o admin acadêmico encerra o período mesmo com pendência no diário."""
    from edu.models import MatriculaPeriodo, SituacaoMatriculaPeriodo

    page = logado_edu('admin_academico')
    page.goto(FECHAR)
    expect(page.get_by_role('heading', name='Fechar período letivo')).to_be_visible()
    _preencher_selecao_por_turma(page, periodo_aberto)

    page.check('input[name=forcar_fechamento]')
    page.check('input[name=confirmado]')
    page.click('input[type=submit][value="Finalizar"]')

    # Processamento assíncrono: a resposta é a tela da tarefa, não a mensagem de sucesso.
    expect(page.get_by_role('heading', name='Fechar Período')).to_be_visible()
    _esperar(
        lambda: not MatriculaPeriodo.objects.filter(turma=periodo_aberto, situacao=SituacaoMatriculaPeriodo.MATRICULADO).exists(),
        'o período continua matriculado depois do fechamento',
    )


def test_reabre_periodo_letivo_por_turma(logado_edu, periodo_fechado):
    """Reabrir devolve o período à situação matriculada, para ajuste de nota e falta."""
    from edu.models import MatriculaPeriodo, SituacaoMatriculaPeriodo

    page = logado_edu('secretario')
    page.goto(REABRIR)
    _preencher_selecao_por_turma(page, periodo_fechado)

    page.check('input[name=confirmado]')
    page.click('input[type=submit][value="Finalizar"]')

    expect(page.get_by_role('heading', name='Abrir Período')).to_be_visible()
    _esperar(
        lambda: MatriculaPeriodo.objects.filter(turma=periodo_fechado, situacao=SituacaoMatriculaPeriodo.MATRICULADO).exists(),
        'o período não voltou para matriculado depois da reabertura',
    )


def test_secretaria_transfere_posse_do_diario(logado_edu, turma_2019_1):
    """A secretaria puxa a posse da etapa para si — é como ela corrige nota já entregue."""
    from edu.models import Diario

    diario = turma_2019_1.diario_set.get(componente_curricular__componente__sigla='POS.0003')
    Diario.objects.filter(pk=diario.pk).update(posse_etapa_1=Diario.POSSE_PROFESSOR)

    page = logado_edu('secretario')
    # Destino 0 = Registro Escolar, 1 = Professor (``Diario.POSSE_CHOICES``).
    page.goto(f'/edu/transferir_posse_diario/{diario.pk}/1/{Diario.POSSE_REGISTRO_ESCOLAR}/')

    mensagem_de_sucesso(page, 'Posse transferida com sucesso')
    diario.refresh_from_db()
    assert diario.em_posse_do_registro(1), 'a posse da etapa 1 não passou para o registro escolar'


@pytest.fixture
def diario_em_posse_do_registro(turma_2019_1):
    """Diário POS.0003 com a etapa 1 na mão do registro escolar.

    É a situação em que a secretaria pode lançar aula e nota em nome do professor — o que
    a funcionalidade 007 cobre depois de transferir a posse.
    """
    from edu.models import Diario

    diario = turma_2019_1.diario_set.get(componente_curricular__componente__sigla='POS.0003')
    Diario.objects.filter(pk=diario.pk).update(posse_etapa_1=Diario.POSSE_REGISTRO_ESCOLAR, situacao=Diario.SITUACAO_ABERTO)
    diario.refresh_from_db()
    return diario


def test_secretaria_devolve_posse_ao_professor(logado_edu, turma_2019_1):
    """O outro sentido da transferência: devolver a etapa para o professor ajustar.

    Os dois sentidos importam porque são a única forma de destravar um diário entregue —
    ``test_secretaria_transfere_posse_do_diario`` cobre o caminho de ida.
    """
    from edu.models import Diario

    diario = turma_2019_1.diario_set.get(componente_curricular__componente__sigla='POS.0003')
    Diario.objects.filter(pk=diario.pk).update(posse_etapa_1=Diario.POSSE_REGISTRO_ESCOLAR)

    page = logado_edu('secretario')
    page.goto(f'/edu/transferir_posse_diario/{diario.pk}/1/{Diario.POSSE_PROFESSOR}/')

    mensagem_de_sucesso(page, 'Posse transferida com sucesso')
    diario.refresh_from_db()
    assert not diario.em_posse_do_registro(1), 'a posse da etapa 1 não voltou para o professor'


def test_secretaria_registra_aula_em_posse_do_registro(logado_edu, diario_em_posse_do_registro):
    """Com a posse no registro, é a secretaria quem cadastra a aula — pela tela de chamada.

    A porta dela é ``/edu/registrar_chamada/<diário>/<etapa>/`` (link "Registro de aula/falta"
    da tela de diário), diferente da do professor (``/edu/meu_diario/``), mas o formulário de
    aula é o mesmo.
    """
    from edu.models import Aula

    diario = diario_em_posse_do_registro
    aulas = Aula.objects.filter(professor_diario__diario=diario, conteudo='Aula lançada pelo registro')
    try:
        tela = Tela(logado_edu('secretario')).ir(f'/edu/registrar_chamada/{diario.pk}/1/')
        tela.ir(f'/edu/adicionar_aula_diario/{diario.pk}/1/')
        tela.preencher_formulario(
            [
                ('Quantidade', 'texto', '60'),
                ('Etapa', 'lista', 'Primeira'),
                ('Data', 'data', '21/03/2019'),
                ('Conteúdo', 'textarea', 'Aula lançada pelo registro'),
            ]
        )
        tela.clicar_botao('Salvar')

        tela.sucesso('Aula cadastrada/atualizada com sucesso.')
        assert aulas.exists(), 'a UI disse que salvou, mas a aula não persistiu'
    finally:
        aulas.delete()


def test_secretaria_lanca_nota_em_posse_do_registro(logado_edu, diario_em_posse_do_registro):
    """Nota lançada pela secretaria usa o mesmo endpoint AJAX da planilha do professor.

    Sem a posse do registro o endpoint responde "A etapa precisa estar em posse do
    professor" — a posse é a chave de quem pode escrever, não o papel de quem está logado.
    """
    from edu.models import MatriculaDiario, NotaAvaliacao

    avaliacao = NotaAvaliacao.objects.filter(
        matricula_diario__diario=diario_em_posse_do_registro,
        matricula_diario__situacao=MatriculaDiario.SITUACAO_CURSANDO,
        item_configuracao_avaliacao__configuracao_avaliacao__etapa=1,
    ).first()
    assert avaliacao is not None, 'diário sem avaliação para aluno cursando: nada a lançar'

    page = logado_edu('secretario')
    resposta = page.goto(f'/edu/registrar_nota_ajax/{avaliacao.pk}/80/')

    assert resposta.status == 200, 'o endpoint de nota recusou o lançamento pela secretaria'
    avaliacao.refresh_from_db()
    assert avaliacao.nota == 80, 'nota não gravada'


def _esperar(condicao, mensagem: str, tentativas: int = 30) -> None:
    """Espera a tarefa assíncrona refletir no banco.

    O fechamento roda fora do ciclo da request; sem esta espera a asserção mediria o
    estado anterior e o teste falharia (ou passaria) por corrida, não por regressão.
    """
    import time

    for _ in range(tentativas):
        if condicao():
            return
        time.sleep(1)
    raise AssertionError(mensagem)
