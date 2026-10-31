"""Tarefas 15 e 16 — o ENADE: convocar os alunos e lançar a situação de cada um.

Dois papéis sistêmicos e uma cadeia própria: o Diretor de Avaliação e Regulação do Ensino
mantém o catálogo de justificativas de dispensa, e o Operador ENADE cria a convocação,
processa a lista de convocados e lança a situação de cada aluno no exame.

**Pré-condição de dado**: o ENADE só alcança curso de graduação com "Exige ENADE" e área
CINE — a "Licenciatura em Geografia". Nos e2e ela é cadastrada pela interface
(``test_12_credito.py`` → ``test_13_requisitos.py``), porque lá o cadastro *é* o que se
testa e a cadeia 12→13→14 roda numa invocação só. Aqui não: a rodada de doc coleta apenas
``edu/tests/doc`` e não documenta esse cadastro, então o curso e a aluna vêm do replay ORM
``seed.step_cadastro_curso_licenciatura`` — pré-condição se semeia, não se espera.
"""

from __future__ import annotations

import pytest

from djtools.e2e_ui import Tela
from edu.tests.doc.conftest import anotar, desfocar

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

DATA = '22/07/2019'
JUSTIFICATIVA = 'Estudante dispensado de realização do ENADE, por razão de ordem pessoal'
DESCRICAO_CONVOCACAO = 'Licenciaturas - Portaria Normativa No 8, de 26 de Março de 2019'


@pytest.fixture
def curso_de_licenciatura(edu_seed, relogio):
    """Curso de graduação com ENADE exigido, e a aluna matriculada nele — a convocada.

    Semeado por ORM (``seed.step_cadastro_curso_licenciatura``) e não pela interface: quem o
    cadastra pela tela é ``edu/tests/e2e/test_12_credito.py``, que esta rodada não coleta.
    """
    from edu.tests.e2e import seed

    return seed.step_cadastro_curso_licenciatura(relogio)


@pytest.fixture
def convocacoes_limpas(curso_de_licenciatura):
    """Sem isto, a convocação da execução anterior faz o cadastro falhar por duplicidade."""
    from edu.models import ConvocacaoENADE

    ConvocacaoENADE.objects.filter(ano_letivo__ano=2019).delete()
    return True


@pytest.fixture
def justificativa_de_dispensa(edu_seed):
    from edu.models import JustificativaDispensaENADE

    return JustificativaDispensaENADE.objects.get_or_create(descricao=JUSTIFICATIVA, defaults={'ativo': True})[0]


@pytest.fixture
def registro_do_aluno(curso_de_licenciatura):
    """Aluno já convocado, sem situação lançada — o que a tarefa 16 preenche.

    Montado por ORM porque o processamento da lista roda em worker assíncrono, fora do
    relógio congelado (ver ``test_processar_lista_de_convocados``).
    """
    from comum.models import Ano
    from edu.models import Aluno, ConvocacaoENADE, ModalidadeConvocacaoENADE, RegistroConvocacaoENADE, SituacaoMatricula

    convocacao = ConvocacaoENADE.objects.filter(ano_letivo__ano=2019, cursos=curso_de_licenciatura).first()
    if convocacao is None:
        convocacao = ConvocacaoENADE.objects.create(
            descricao=DESCRICAO_CONVOCACAO,
            tipo_convocacao=ConvocacaoENADE.AVALIACAO_TEORICA,
            ano_letivo=Ano.objects.get(ano=2019),
            data_inscricao_ingressantes='2019-04-01',
            data_inscricao='2019-04-01',
        )
        convocacao.modalidades_convocadas.add(curso_de_licenciatura.modalidade)
        convocacao.areas_cursos_formacao_superior.add(curso_de_licenciatura.area_curso_formacao_superior)
        convocacao.situacoes_convocadas.add(*SituacaoMatricula.objects.filter(descricao='Matriculado'))
        convocacao.cursos.add(curso_de_licenciatura)
        ModalidadeConvocacaoENADE.objects.get_or_create(convocacao_enade=convocacao, modalidade=curso_de_licenciatura.modalidade)
    # Os percentuais por modalidade são o que habilita o botão "Atualizar Lista de Convocados"
    # (``ConvocacaoENADE.pode_processar_lista_convocados``); a data da prova é o que habilita
    # lançar situação. Sem os dois, a tela da convocação nem oferece a ação.
    ModalidadeConvocacaoENADE.objects.filter(convocacao_enade=convocacao).update(
        percentual_minimo_ingressantes=0,
        percentual_maximo_ingressantes=25,
        percentual_minimo_concluintes=80,
        percentual_maximo_concluintes=100,
    )
    ModalidadeConvocacaoENADE.objects.filter(convocacao_enade=convocacao, data_prova__isnull=True).update(data_prova='2019-04-02')

    aluno = Aluno.objects.filter(curso_campus=curso_de_licenciatura).first()
    assert aluno is not None, 'curso de licenciatura sem aluno matriculado'
    registro, _ = RegistroConvocacaoENADE.objects.get_or_create(
        convocacao_enade=convocacao,
        aluno=aluno,
        defaults={'tipo_convocacao': RegistroConvocacaoENADE.TIPO_CONVOCACAO_INGRESSANTE},
    )
    RegistroConvocacaoENADE.objects.filter(pk=registro.pk).update(situacao=None, justificativa_dispensa=None)
    registro.refresh_from_db()
    return registro


def test_cadastrar_justificativa_de_dispensa(logado_edu, edu_seed, capturar):
    """Tarefa 15, etapa 0 — o catálogo de dispensas, mantido pelo papel sistêmico."""
    from edu.models import JustificativaDispensaENADE

    descricao = f'{JUSTIFICATIVA} (doc)'
    justificativas = JustificativaDispensaENADE.objects.filter(descricao=descricao)
    try:
        tela = Tela(logado_edu('dare')).ir('/admin/edu/justificativadispensaenade/')
        anotar('enade-justificativas', tela)
        tela.clicar_botao('Adicionar Justif. de Dispensa do ENADE')
        anotar('enade-justificativa-formulario', tela)
        tela.preencher('Descrição', 'texto', descricao)
        capturar(tela.pagina, 'enade-justificativa')
        tela.clicar_botao('Salvar')

        tela.sucesso('Cadastro realizado com sucesso.')
        assert justificativas.exists(), 'a UI disse que salvou, mas a justificativa não persistiu'
    finally:
        justificativas.delete()


def test_cadastrar_convocacao(logado_edu, curso_de_licenciatura, convocacoes_limpas, capturar):
    """Tarefa 15, etapa 1 — a convocação e o recorte de quem participa."""
    from edu.models import ConvocacaoENADE, ModalidadeConvocacaoENADE

    tela = Tela(logado_edu('operador_enade')).ir('/admin/edu/convocacaoenade/')
    tela.ver_titulo('Convocações do ENADE')
    anotar('enade-listagem', tela)
    capturar(tela.pagina, 'enade-listagem')
    tela.clicar_botao('Adicionar Convocação do ENADE')
    anotar('enade-formulario', tela)
    # Autocompletes num bloco à parte, depois do `desfocar`: a digitação do select2 vaza para
    # o campo focado antes quando o widget demora a abrir (ver `escolher`, no conftest) — e o
    # campo anterior aqui seria a Descrição, que é como a convocação é encontrada depois.
    tela.preencher_formulario(
        [
            ('Descrição', 'texto', DESCRICAO_CONVOCACAO),
            ('Tipo de convocação', 'lista', 'Avaliação teórica'),
            ('Data limite para inscrição de ingressantes', 'data', '01/04/2019'),
            ('Data limite para inscrição de concluintes', 'data', '01/04/2019'),
        ]
    )
    desfocar(tela.pagina)
    tela.preencher_formulario(
        [
            ('Ano letivo', 'autocomplete', '2019'),
            ('Situações convocadas', 'autocomplete multiplo', 'Matriculado'),
            ('Modalidades convocadas', 'autocomplete multiplo', curso_de_licenciatura.modalidade.descricao),
            ('Áreas de cursos de formação superior', 'autocomplete multiplo', '0111C01'),
        ]
    )
    capturar(tela.pagina, 'enade-formulario')
    tela.clicar_botao('Salvar')

    tela.sucesso('Cadastro realizado com sucesso.')
    convocacao = ConvocacaoENADE.objects.get(descricao=DESCRICAO_CONVOCACAO)
    assert convocacao.cursos.filter(pk=curso_de_licenciatura.pk).exists(), 'o curso de licenciatura não entrou na convocação'
    anotar('enade-ficha', tela)
    capturar(tela.pagina, 'enade-ficha')

    modalidade = ModalidadeConvocacaoENADE.objects.filter(convocacao_enade=convocacao).first()
    assert modalidade is not None, 'a convocação nasceu sem critérios por modalidade'
    tela.ir(f'/edu/editar_modalidadeconvocacaoenade/{modalidade.pk}/')
    anotar('enade-modalidade', tela)
    tela.preencher('Data de realização da prova', 'data', '02/04/2019')
    capturar(tela.pagina, 'enade-modalidade')
    tela.clicar_botao('Salvar')

    tela.sucesso('Operação realizada com sucesso.')
    modalidade.refresh_from_db()
    assert str(modalidade.data_prova) == '2019-04-02', 'data de realização da prova não gravada'


def test_processar_lista_de_convocados(logado_edu, registro_do_aluno, capturar):
    """Tarefa 15, etapa 2 — o processamento que transforma o recorte em aluno convocado.

    Só o disparo é verificável aqui: a tarefa roda em worker assíncrono, fora do relógio
    congelado, e com a data real de hoje nenhuma das datas-limite de 2019 fecha — a lista
    sairia vazia por calendário, não por regra de negócio.
    """
    convocacao = registro_do_aluno.convocacao_enade
    tela = Tela(logado_edu('operador_enade')).ir(f'/edu/atualizar_lista_convocados_enade/{convocacao.pk}/')
    anotar('enade-processar', tela)
    capturar(tela.pagina, 'enade-processar')
    tela.clicar_botao('Atualizar Lista de Convocados')
    tela.esperar()

    assert '/djtools/process/' in tela.pagina.url, f'o processamento não foi disparado. {tela.diagnostico()}'


def test_lancar_situacao_do_aluno(logado_edu, registro_do_aluno, justificativa_de_dispensa, curso_de_licenciatura, capturar):
    """Tarefa 16 — a situação no exame, a dispensa com justificativa e a lista por curso."""
    from edu.models import RegistroConvocacaoENADE

    convocados = f'/edu/convocados_enade/{registro_do_aluno.convocacao_enade_id}/{curso_de_licenciatura.pk}/'
    tela = Tela(logado_edu('operador_enade')).ir(convocados)
    anotar('enade-convocados', tela)
    tela.ver_texto(registro_do_aluno.aluno.matricula)
    capturar(tela.pagina, 'enade-convocados')

    tela.ir(f'/edu/lancar_situacao_enade/{registro_do_aluno.pk}/')
    anotar('enade-situacao', tela)
    tela.preencher('Situação', 'lista', 'Dispensado')
    tela.preencher('Justificativa de Dispensa', 'lista', justificativa_de_dispensa.descricao)
    capturar(tela.pagina, 'enade-situacao')
    tela.clicar_botao('Salvar')

    tela.sucesso('Lançamento do ENADE realizado com sucesso.')
    registro_do_aluno.refresh_from_db()
    assert registro_do_aluno.situacao is not None, 'situação não gravada'
    assert registro_do_aluno.justificativa_dispensa, 'dispensa gravada sem justificativa'

    # Remover devolve o aluno para "convocado, sem resultado" — e o log guarda a mudança.
    tela.ir(f'/edu/remover_situacao_enade/{registro_do_aluno.pk}/')
    tela.sucesso('Situação do ENADE removida com sucesso.')
    assert RegistroConvocacaoENADE.objects.get(pk=registro_do_aluno.pk).situacao is None, 'a situação continua lançada depois da remoção'

    tela.ir(f'/edu/log_situacao_enade/{registro_do_aluno.pk}/')
    anotar('enade-log', tela)
    tela.ver_texto('Registro de Convocação ENADE')
    capturar(tela.pagina, 'enade-log')
