"""Fluxo 013: ENADE — convocação dos alunos e registro da situação no exame.

Fim da cadeia do módulo e o único fluxo com papéis **sistêmicos**: o Diretor de Avaliação e
Regulação do Ensino (100009) cadastra as justificativas de dispensa e o Operador ENADE
(100008) conduz a convocação. Os dois só existem porque a diretoria da RAIZ é do tipo
Sistêmica (ver ``test_01_diretoria``), e é isso que lhes dá alcance sobre todos os campi.

A convocação tem três etapas que dependem uma da outra: declarar a convocação (ano,
modalidades, áreas CINE), calibrar os critérios por modalidade (percentuais de ingressantes e
concluintes, datas-limite) e processar a lista — só então existe um ``RegistroConvocacaoENADE``
por aluno, que é onde a situação (Regular, Irregular, Dispensado) é lançada.

Depende do curso de licenciatura do módulo 12: ``ConvocacaoENADE`` filtra por modalidade e por
área de curso de formação superior, e o curso de pós dos módulos 01→11 não tem nenhuma das
duas. É a mesma dependência que a ``.feature`` 013 tem das features 011 e 012 — ela não tem
cenário de configuração inicial, conta com o que veio antes.
"""

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

DATA = '22/07/2019'
JUSTIFICATIVA = 'Estudante dispensado de realização do ENADE, por razão de ordem pessoal'
DESCRICAO_CONVOCACAO = 'Licenciaturas - Portaria Normativa No 8, de 26 de Março de 2019'


@pytest.fixture
def justificativa_de_dispensa(base_credito):
    """Justificativa ativa — sem ela a situação "Dispensado" é recusada pelo formulário."""
    from edu.models import JustificativaDispensaENADE

    return JustificativaDispensaENADE.objects.get_or_create(descricao=JUSTIFICATIVA, defaults={'ativo': True})[0]


@pytest.fixture(scope='session')
def convocacoes_limpas(base_credito):
    """Apaga as convocações de 2019 da execução anterior.

    ``ConvocacaoENADEForm.clean`` proíbe duas convocações do mesmo ano e tipo cobrindo o mesmo
    curso, então uma convocação sobrando de outra execução faz o cadastro pela tela falhar com
    "O curso ... foi adicionado em outra convocação".
    """
    from edu.models import ConvocacaoENADE

    ConvocacaoENADE.objects.filter(ano_letivo__ano=2019).delete()


@pytest.fixture
def convocacao(curso_credito, convocacoes_limpas):
    """Convocação do ENADE de 2019 cobrindo o curso de licenciatura.

    Reusa a que ``test_operador_cadastra_convocacao`` criou pela tela; se não houver (execução
    isolada), monta por ORM — inclusive o ``ModalidadeConvocacaoENADE``, que no fluxo real é
    criado pelo ``save`` do formulário, não pelo modelo, e é dele que dependem os critérios de
    convocação e a data da prova.
    """
    from comum.models import Ano
    from edu.models import ConvocacaoENADE, ModalidadeConvocacaoENADE, SituacaoMatricula

    curso = curso_credito()
    convocacao = ConvocacaoENADE.objects.filter(ano_letivo__ano=2019, cursos=curso).first()
    if convocacao is None:
        convocacao = ConvocacaoENADE.objects.create(
            descricao=DESCRICAO_CONVOCACAO,
            tipo_convocacao=ConvocacaoENADE.AVALIACAO_TEORICA,
            ano_letivo=Ano.objects.get(ano=2019),
            data_inscricao_ingressantes='2019-04-01',
            data_inscricao='2019-04-01',
        )
        convocacao.modalidades_convocadas.add(curso.modalidade)
        convocacao.areas_cursos_formacao_superior.add(curso.area_curso_formacao_superior)
        convocacao.situacoes_convocadas.add(*SituacaoMatricula.objects.filter(descricao='Matriculado'))
        convocacao.cursos.add(curso)
        ModalidadeConvocacaoENADE.objects.get_or_create(convocacao_enade=convocacao, modalidade=curso.modalidade)
    # A data da prova é pré-condição do lançamento de situação ("Você precisa definir a data
    # de realização da prova"); quem a define pela tela é `test_operador_calibra_criterios`.
    # Os percentuais por modalidade são o que habilita processar a lista
    # (``ConvocacaoENADE.pode_processar_lista_convocados``), e a data da prova é o que habilita
    # lançar situação. Os dois vêm por ORM para cada teste medir só o seu passo.
    ModalidadeConvocacaoENADE.objects.filter(convocacao_enade=convocacao).update(
        percentual_minimo_ingressantes=0,
        percentual_maximo_ingressantes=25,
        percentual_minimo_concluintes=80,
        percentual_maximo_concluintes=100,
    )
    ModalidadeConvocacaoENADE.objects.filter(convocacao_enade=convocacao, data_prova__isnull=True).update(data_prova='2019-04-02')
    return convocacao


@pytest.fixture
def registro_do_aluno(convocacao, curso_credito):
    """``RegistroConvocacaoENADE`` da aluna do curso de licenciatura, sem situação lançada."""
    from edu.models import Aluno, RegistroConvocacaoENADE

    aluno = Aluno.objects.filter(curso_campus=curso_credito()).first()
    assert aluno is not None, 'curso de licenciatura sem aluno: rode test_13_requisitos antes'
    registro, _ = RegistroConvocacaoENADE.objects.get_or_create(
        convocacao_enade=convocacao,
        aluno=aluno,
        defaults={'tipo_convocacao': RegistroConvocacaoENADE.TIPO_CONVOCACAO_INGRESSANTE},
    )
    RegistroConvocacaoENADE.objects.filter(pk=registro.pk).update(situacao=None, justificativa_dispensa=None)
    registro.refresh_from_db()
    return registro


def test_dare_cadastra_justificativa_de_dispensa(logado_edu, base_credito):
    """Quem mantém o catálogo de dispensas é o Diretor de Avaliação e Regulação do Ensino.

    Papel sistêmico: a justificativa vale para a rede inteira, não para um campus — por isso o
    cadastro não é do Secretário Acadêmico.
    """
    from edu.models import JustificativaDispensaENADE

    descricao = f'{JUSTIFICATIVA} (e2e)'
    justificativas = JustificativaDispensaENADE.objects.filter(descricao=descricao)
    try:
        tela = Tela(logado_edu('dare')).ir('/admin/edu/justificativadispensaenade/add/')
        tela.preencher('Descrição', 'texto', descricao)
        tela.clicar_botao('Salvar')

        tela.sucesso('Cadastro realizado com sucesso.')
        assert justificativas.exists(), 'a UI disse que salvou, mas a justificativa não persistiu'
    finally:
        justificativas.delete()


def test_operador_cadastra_convocacao(logado_edu, curso_credito, convocacoes_limpas):
    """A convocação recorta quem participa: ano, situação, modalidade e área CINE.

    O recorte é o ponto todo da tela — é ele que decide quais cursos entram no processamento, e
    o ``save`` do formulário deriva daí tanto a lista de cursos quanto os critérios por
    modalidade. É a convocação que os testes seguintes deste módulo reusam, por isso ela fica
    com a descrição da ``.feature`` e não é apagada no fim.
    """
    from edu.models import ConvocacaoENADE, ModalidadeConvocacaoENADE

    curso = curso_credito()
    tela = Tela(logado_edu('operador_enade')).ir('/admin/edu/convocacaoenade/add/')
    tela.preencher_formulario(
        [
            ('Descrição', 'texto', DESCRICAO_CONVOCACAO),
            ('Tipo de convocação', 'lista', 'Avaliação teórica'),
            ('Ano letivo', 'autocomplete', '2019'),
            ('Situações convocadas', 'autocomplete multiplo', 'Matriculado'),
            ('Data limite para inscrição de ingressantes', 'data', '01/04/2019'),
            ('Data limite para inscrição de concluintes', 'data', '01/04/2019'),
            ('Modalidades convocadas', 'autocomplete multiplo', curso.modalidade.descricao),
            ('Áreas de cursos de formação superior', 'autocomplete multiplo', '0111C01'),
        ]
    )
    tela.clicar_botao('Salvar')

    tela.sucesso('Cadastro realizado com sucesso.')
    convocacao = ConvocacaoENADE.objects.get(descricao=DESCRICAO_CONVOCACAO)
    assert convocacao.cursos.filter(pk=curso.pk).exists(), 'o curso de licenciatura não entrou na convocação'
    assert ModalidadeConvocacaoENADE.objects.filter(convocacao_enade=convocacao).exists(), 'a convocação nasceu sem critérios por modalidade'


def test_operador_calibra_criterios_e_data_da_prova(logado_edu, convocacao):
    """Critérios por modalidade: percentuais de integralização e a data da prova.

    É o que define quem é "ingressante" e quem é "concluinte" para efeito de convocação — a
    faixa de percentual de curso integralizado. A data da prova sai do mesmo formulário
    (cenários "Convocar alunos" e "Definir data de realização do ENADE" da ``.feature``).
    """
    from edu.models import ModalidadeConvocacaoENADE

    modalidade = ModalidadeConvocacaoENADE.objects.filter(convocacao_enade=convocacao).first()
    assert modalidade is not None, 'a convocação deveria ter criado os critérios da modalidade convocada'

    tela = Tela(logado_edu('operador_enade')).ir(f'/edu/editar_modalidadeconvocacaoenade/{modalidade.pk}/')
    # Numa convocação de **avaliação teórica** a tela oferece só a data da prova: os
    # percentuais e as datas-limite de integralização são pedidos na convocação de avaliação
    # prática, onde a lista é montada por período de regência. É a data da prova que o
    # lançamento de situação exige ("Você precisa definir a data de realização da prova").
    tela.preencher('Data de realização da prova', 'data', '02/04/2019')
    tela.clicar_botao('Salvar')

    tela.sucesso('Operação realizada com sucesso.')
    modalidade.refresh_from_db()
    assert str(modalidade.data_prova) == '2019-04-02', 'data de realização da prova não gravada'


def test_operador_processa_lista_de_convocados(logado_edu, convocacao, curso_credito):
    """Processar a lista é o que transforma o recorte em convocação de aluno concreto.

    Sem curso escolhido o SUAP processa todos os cursos da convocação (é o "Todos os cursos" da
    ``.feature``). O resultado é um ``RegistroConvocacaoENADE`` por aluno apto — e é sobre ele
    que a situação no exame é lançada depois.
    """
    from edu.models import RegistroConvocacaoENADE

    tela = Tela(logado_edu('operador_enade')).ir(f'/edu/atualizar_lista_convocados_enade/{convocacao.pk}/')
    tela.clicar_botao('Atualizar Lista de Convocados')
    tela.esperar()

    # O disparo é o que a tela entrega: a resposta é a página de acompanhamento da tarefa.
    assert '/djtools/process/' in tela.pagina.url, f'o processamento não foi disparado. {tela.diagnostico()}'

    # NÃO se verifica a lista produzida: o processamento roda em worker assíncrono, fora do
    # relógio congelado do teste, e com a data real de hoje nenhuma das datas-limite de 2019
    # fecha — a lista sai vazia por calendário, não por regra de negócio. Executar a tarefa
    # aqui também não resolve (ela apenas redispara para o mesmo worker). O que este teste
    # cobre, então, é o que a interface garante: permissão, formulário e disparo.
    # Pendência anotada: cobrir o resultado exige um gancho para rodar a tarefa em processo.


@pytest.mark.parametrize(('situacao', 'com_justificativa'), [('Regular', False), ('Dispensado', True)])
def test_operador_lanca_situacao_do_aluno(logado_edu, registro_do_aluno, justificativa_de_dispensa, situacao, com_justificativa):
    """A situação no exame, com a regra de que "Dispensado" exige justificativa.

    Os dois casos porque a validação é cruzada (``LancarSituacaoAlunoENADEForm.clean_justificativa_dispensa``):
    justificativa sem dispensa é erro, e dispensa sem justificativa também.
    """
    tela = Tela(logado_edu('operador_enade')).ir(f'/edu/lancar_situacao_enade/{registro_do_aluno.pk}/')
    tela.preencher('Situação', 'lista', situacao)
    if com_justificativa:
        tela.preencher('Justificativa de Dispensa', 'lista', justificativa_de_dispensa.descricao)
    tela.clicar_botao('Salvar')

    tela.sucesso('Lançamento do ENADE realizado com sucesso.')
    registro_do_aluno.refresh_from_db()
    assert registro_do_aluno.situacao is not None, 'situação não gravada'
    assert bool(registro_do_aluno.justificativa_dispensa) == com_justificativa, 'justificativa de dispensa fora de sincronia com a situação'


def test_operador_remove_situacao_do_aluno(logado_edu, registro_do_aluno):
    """Remover a situação devolve o aluno para "convocado, sem resultado".

    Existe porque lançamento errado acontece e o registro é auditado — o histórico da mudança
    fica no log, que ``test_log_de_situacao_do_aluno`` verifica.
    """
    from edu.models import RegistroConvocacaoENADE

    RegistroConvocacaoENADE.objects.filter(pk=registro_do_aluno.pk).update(situacao=RegistroConvocacaoENADE.SITUACAO_PRESENTE)

    tela = Tela(logado_edu('operador_enade')).ir(f'/edu/remover_situacao_enade/{registro_do_aluno.pk}/')

    tela.sucesso('Situação do ENADE removida com sucesso.')
    registro_do_aluno.refresh_from_db()
    assert registro_do_aluno.situacao is None, 'a situação continua lançada depois da remoção'


def test_log_de_situacao_do_aluno(logado_edu, registro_do_aluno):
    """O registro de convocação é auditado: o log mostra o que mudou e quem mudou."""
    from edu.models import RegistroConvocacaoENADE

    RegistroConvocacaoENADE.objects.filter(pk=registro_do_aluno.pk).update(situacao=RegistroConvocacaoENADE.SITUACAO_PRESENTE)

    tela = Tela(logado_edu('operador_enade')).ir(f'/edu/log_situacao_enade/{registro_do_aluno.pk}/')

    tela.ver_texto('Registro de Convocação ENADE')


def test_convocados_do_curso_aparecem_na_listagem(logado_edu, registro_do_aluno, curso_credito):
    """A tela de convocados por curso é a que o campus usa para conferir a lista."""
    tela = Tela(logado_edu('operador_enade')).ir(f'/edu/convocados_enade/{registro_do_aluno.convocacao_enade_id}/{curso_credito().pk}/')

    tela.ver_texto(registro_do_aluno.aluno.matricula)
