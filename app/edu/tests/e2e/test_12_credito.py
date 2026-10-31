"""Fluxo 011: curso em regime de crédito — estrutura, curso, matriz e pré/co-requisitos.

Regime de crédito é o outro modelo acadêmico do SUAP, ao lado do seriado dos módulos
01→11: o aluno não avança por período fechado, avança por componente aprovado, e é por isso
que existe **pré-requisito** e **co-requisito** — a matrícula em disciplina passa a ser
validada contra o histórico. Este módulo monta esse mundo pela interface: a estrutura com
``Tipo de Avaliação = Crédito``, o curso de licenciatura, a matriz de 8 períodos e a teia de
requisitos entre os componentes.

Os nomes são os da ``.feature`` (curso "Licenciatura em Geografia", código 20101) e não
levam sufixo aleatório como no módulo 02: os módulos 13 (gerar turmas validando requisitos)
e 14 (ENADE) procuram exatamente esse curso, igual ao behave, em que as features 011→013
rodam em sequência sobre o mesmo banco. Quem garante que a execução anterior não atrapalha é
a limpeza da fixture ``base_credito``.

Os testes deste módulo são **encadeados** e correm na ordem em que estão escritos — a matriz
precisa da estrutura, o vínculo precisa da matriz, o requisito precisa do vínculo. É a mesma
dependência que a ``.feature`` tem entre seus cenários.
"""

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

DATA = '22/07/2019'
CODIGO_CURSO = '20101'
NOME = 'Licenciatura em Geografia'


def test_cadastra_estrutura_em_regime_de_credito(logado_edu, base_credito):
    """Estrutura de crédito: o que muda é o ``Tipo de Avaliação`` — e o que ele destrava.

    Escolher "Crédito" faz a tela cobrar limites por disciplina (mínimo e máximo por período,
    períodos subsequentes para matrícula, cancelamentos) que o regime seriado não tem, porque
    no crédito é o aluno que monta o próprio período.
    """
    from edu.models import EstruturaCurso

    tela = Tela(logado_edu('admin_academico')).ir('/admin/edu/estruturacurso/add/')
    tela.preencher_formulario(
        [
            ('Descrição', 'texto', 'Licenciatura'),
            ('Está Ativa', 'checkbox', 'marcar'),
            ('Tipo de Avaliação', 'radio', 'Crédito'),
            ('Número mínimo de disciplinas por período', 'texto', '1'),
            ('Número máximo de disciplinas extras por período', 'texto', '2'),
            ('Número máximo de períodos subsequentes para matrícula em disciplina', 'texto', '10'),
            ('Número máximo de cancelamentos de disciplinas', 'texto', '1'),
            ('Critério de Avaliação', 'radio', 'Nota'),
            ('Média para passar sem prova final', 'texto', '60'),
            ('Média para não reprovar direto', 'texto', '20'),
            ('Média para aprovação após avaliação final', 'texto', '60'),
            ('Percentual Mínimo de Frequência', 'texto', '75'),
            ('Forma de Cálculo', 'radio', 'Média dos componentes pela carga horária dos componentes'),
            ('Número Máximo de Matrículas em Períodos', 'texto', '16'),
            ('Número Máximo de Reprovações no Mesmo Período', 'texto', '0'),
            ('Número Máximo de Reprovações na Mesma Disciplina', 'texto', '0'),
            ('Número máximo de trancamentos voluntários', 'texto', '2'),
            ('Exige integralização do período de ingresso', 'checkbox', 'marcar'),
            ('Percentual Máximo de Aproveitamento', 'texto', '50'),
            ('Número Máximo de Certificações por Período', 'texto', '4'),
            ('Média para Certificação', 'texto', '60'),
        ]
    )
    tela.clicar_botao('Salvar')

    tela.sucesso('Cadastro realizado com sucesso.')
    estrutura = EstruturaCurso.objects.get(descricao='Licenciatura')
    assert estrutura.tipo_avaliacao == EstruturaCurso.TIPO_AVALIACAO_CREDITO, 'a estrutura não ficou em regime de crédito'


def test_cadastra_area_de_curso(logado_edu, base_credito):
    """Área de curso é a classificação interna usada em relatório e no cadastro do curso."""
    from edu.models import AreaCurso

    tela = Tela(logado_edu('admin_academico')).ir('/admin/edu/areacurso/add/')
    tela.preencher('Descrição', 'texto', 'Ciências Humanas')
    tela.clicar_botao('Salvar')

    tela.sucesso('Cadastro realizado com sucesso.')
    assert AreaCurso.objects.filter(descricao='Ciências Humanas').exists(), 'área de curso não persistiu'


def test_cadastra_configuracao_de_atpa(logado_edu, base_credito):
    """ATPA (Atividades Teórico-Práticas de Aprofundamento) é exigência das licenciaturas.

    Como a AACC do módulo 02, nasce vazia — a mensagem do SUAP já manda adicionar os tipos —
    e é referenciada pela matriz, que declara quantas horas de ATPA o curso exige.
    """
    from edu.models import ConfiguracaoAtividadeAprofundamento

    tela = Tela(logado_edu('admin_academico')).ir('/admin/edu/configuracaoatividadeaprofundamento/add/')
    tela.preencher('Descrição', 'texto', 'ATPA Licenciaturas 2018')
    tela.clicar_botao('Salvar')

    tela.sucesso('Configuração cadastrada com sucesso.')
    assert ConfiguracaoAtividadeAprofundamento.objects.filter(descricao='ATPA Licenciaturas 2018').exists(), 'configuração de ATPA não persistiu'


def test_cadastra_curso_de_licenciatura(logado_edu, base_credito):
    """Curso de graduação: exige ENADE, exige colação de grau e tem área CINE.

    São três campos que o curso de pós do módulo 02 não usa e que puxam funcionalidade
    inteira: a área do curso de formação superior (código CINE) é o que a convocação do ENADE
    filtra no módulo 14, e a colação de grau entra nos requisitos de conclusão.
    """
    from edu.models import CursoCampus

    tela = Tela(logado_edu('admin_academico')).ir('/admin/edu/cursocampus/add/')
    tela.preencher_formulario(
        [
            ('Descrição', 'texto', NOME),
            ('Descrição no Diploma e Histórico', 'texto', NOME),
            ('Formação de Professores', 'checkbox', 'marcar'),
            ('Ano letivo', 'autocomplete', '2019'),
            ('Período letivo', 'lista', '1'),
            ('Data de criação', 'data', '15/03/2019'),
            ('Quantidade de vagas anuais autorizadas', 'texto', '10'),
            ('Ativo', 'checkbox', 'marcar'),
            ('Código', 'texto', CODIGO_CURSO),
            ('Modalidade de Ensino', 'autocomplete', 'Licenciatura'),
            ('Área do curso de formação superior', 'autocomplete', '0111C01'),
            ('Área de curso', 'autocomplete', 'Ciências Humanas'),
            ('Periodicidade', 'lista', 'Semestral'),
            ('Diretoria', 'autocomplete', 'DIAC/CEN'),
            ('Exige ENADE', 'checkbox', 'marcar'),
            ('Exige colação de grau', 'checkbox', 'marcar'),
            ('Certificado/Diploma Emitido pelo Campus', 'checkbox', 'marcar'),
            ('Fator de Esforço de Curso (FEC)', 'texto', '1'),
            ('Masculino', 'texto', 'Licenciado em Geografia'),
            ('Feminino', 'texto', 'Licenciada em Geografia'),
        ]
    )
    tela.clicar_botao('Salvar')

    tela.sucesso('Curso cadastrado com sucesso.')
    curso = CursoCampus.objects.get(codigo=CODIGO_CURSO)
    assert curso.exige_enade, 'o curso precisa exigir ENADE para a convocação do módulo 14 alcançá-lo'


def test_cadastra_matriz_de_licenciatura(logado_edu, base_credito):
    """Matriz de 8 períodos com as cargas horárias exigidas por tipo de componente.

    A estrutura de crédito e a configuração de ATPA cadastradas antes entram aqui — é a
    matriz que amarra as duas ao curso.
    """
    from edu.models import Matriz

    tela = Tela(logado_edu('admin_academico')).ir('/admin/edu/matriz/add/')
    tela.preencher_formulario(
        [
            ('Descrição', 'texto', NOME),
            ('Ano Criação', 'autocomplete', '2019'),
            ('Período Criação', 'lista', '1'),
            ('Nível de Ensino', 'autocomplete', 'Graduação'),
            ('Natureza de participação', 'autocomplete', 'Presencial'),
            ('Ativa', 'checkbox', 'marcar'),
            ('Data de início', 'data', '15/03/2019'),
            ('PPP', 'arquivo', 'arquivo.pdf'),
            ('Quantidade de Períodos Letivos', 'lista', '8'),
            ('Estrutura de curso', 'autocomplete', 'Licenciatura'),
            ('Componentes obrigatórios', 'texto', '1920'),
            ('Componentes optativos', 'texto', '180'),
            ('Componentes eletivos', 'texto', '0'),
            ('Componentes de extensão', 'texto', '0'),
            ('Seminários', 'texto', '244'),
            ('Prática Profissional', 'texto', '800'),
            ('Trabalho de Conclusão de Curso', 'texto', '0'),
            ('Carga horária total de atividades de extensão', 'texto', '0'),
            ('Carga horária de extensão em outros componentes', 'texto', '0'),
            ('Atividades complementares', 'texto', '0'),
            ('Atividades Teórico-Práticas de Aprofundamento', 'texto', '200'),
            ('Prática como Componente Curricular', 'texto', '0'),
            ('Visita Técnica/Aula de Campo', 'texto', '0'),
            ('Configuração de ATPA', 'autocomplete', 'ATPA Licenciaturas 2018'),
            ('Exige TCC', 'checkbox', 'marcar'),
            ('Período Mínimo para Estágio Obrigatório', 'lista', '1'),
        ]
    )
    tela.clicar_botao('Salvar')

    tela.sucesso('Matriz cadastrada com sucesso.')
    assert Matriz.objects.filter(descricao=NOME).exists(), 'matriz de licenciatura não persistiu'


@pytest.fixture
def matriz_credito(base_credito):
    """Matriz da licenciatura com os componentes LIC.0002→0004 já vinculados.

    Os três vêm do replay (``os cadastros iniciais de componente curricular``, o mesmo step
    que a ``.feature`` 011 usa antes de vincular o primeiro componente pela tela): sem eles
    não há o que colocar como pré ou co-requisito.
    """
    from edu.tests.e2e import seed
    from edu.models import Matriz

    matriz = Matriz.objects.filter(descricao=NOME).first()
    assert matriz is not None, 'matriz "Licenciatura em Geografia" ausente: rode test_cadastra_matriz_de_licenciatura antes'
    seed.step_cadastro_componente_curricular(None)
    return matriz


def test_vincula_componente_a_matriz_de_credito(logado_edu, matriz_credito):
    """No crédito o componente curricular carrega o período sugerido, não obrigatório.

    ``Qtd. Avaliações = Duas`` aqui (contra "Uma" na pós do módulo 02) porque a graduação
    fecha por bimestre — é esse número que define quantas etapas o diário vai ter.
    """
    from edu.models import ComponenteCurricular

    tela = Tela(logado_edu('admin_academico')).ir(f'/edu/matriz/{matriz_credito.pk}/vincular_componente/')
    tela.preencher_formulario(
        [
            ('Componente', 'autocomplete', 'LIC.0001'),
            ('Periodo letivo', 'lista', '1'),
            ('Tipo', 'lista', 'Regular'),
            ('Qtd. Avaliações', 'lista', 'Duas'),
            ('Núcleo', 'autocomplete', 'Formação'),
            ('Teórica', 'texto', '30'),
        ]
    )
    tela.clicar_botao('Vincular Componente')

    tela.sucesso('Componente de matriz adicionado com sucesso.')
    assert ComponenteCurricular.objects.filter(matriz=matriz_credito, componente__sigla='LIC.0001').exists(), 'componente não vinculado à matriz'


def test_define_pre_e_co_requisitos(logado_edu, matriz_credito):
    """Pré-requisito e co-requisito: a regra que o crédito tem e o seriado não.

    Pré-requisito é "só depois de aprovado em"; co-requisito é "junto com". Os dois são
    definidos no mesmo popup da aba Pré/Co-Requisitos, em quadros diferentes — e é essa
    diferença de quadro que o teste percorre, porque trocá-los é a regressão silenciosa
    possível aqui (a matrícula passaria a aceitar o que deveria barrar).
    """
    from edu.models import ComponenteCurricular

    componentes = {componente.componente.sigla: componente for componente in ComponenteCurricular.objects.filter(matriz=matriz_credito)}
    assert {'LIC.0001', 'LIC.0002', 'LIC.0003'} <= set(componentes), f'matriz sem os componentes esperados: {sorted(componentes)}'

    tela = Tela(logado_edu('admin_academico'))
    for sigla, quadro, requisito in (('LIC.0002', 'Pré-requisitos', 'LIC.0001'), ('LIC.0003', 'Co-requisitos', 'LIC.0002')):
        tela.ir(f'/edu/definir_requisitos/{componentes[sigla].pk}/')
        tela.quadro(quadro).selecionar_item(requisito)
        tela.clicar_botao('Salvar')
        tela.sucesso('Requisitos definidos com sucesso.')

    componentes['LIC.0002'].refresh_from_db()
    componentes['LIC.0003'].refresh_from_db()
    assert componentes['LIC.0002'].pre_requisitos.filter(componente__sigla='LIC.0001').exists(), 'pré-requisito não gravado'
    assert componentes['LIC.0003'].co_requisitos.filter(componente__sigla='LIC.0002').exists(), 'co-requisito não gravado'


def test_vincula_matriz_ao_curso_de_credito(logado_edu, matriz_credito):
    """Curso + matriz: é o vínculo que habilita gerar turma (módulo 13) e matricular aluno."""
    from edu.models import CursoCampus, MatrizCurso

    curso = CursoCampus.objects.get(codigo=CODIGO_CURSO)
    tela = Tela(logado_edu('admin_academico')).ir(f'/edu/cursocampus/{curso.pk}/?tab=matrizes')
    tela.clicar_botao('Vincular Matriz')
    popup = tela.popup()
    popup.preencher('Matriz', 'autocomplete', NOME)
    popup.salvar_no_popup('Salvar')

    tela.sucesso('Matriz adicionada com sucesso.')
    assert MatrizCurso.objects.filter(curso_campus=curso, matriz=matriz_credito).exists(), 'matriz não vinculada ao curso'
