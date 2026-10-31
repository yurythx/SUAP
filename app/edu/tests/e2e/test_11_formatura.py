"""Fluxo 010: formar o aluno — TCC, modelo de documento, livro de registros e diploma.

Último elo da cadeia: com o período fechado, o que falta para o aluno sair formado é o
trabalho de conclusão registrado e a infraestrutura de emissão (modelo de documento .docx +
livro de registros com numeração). O diploma em si é emitido pelo Coordenador de Registros
Acadêmicos.

A emissão propriamente dita **não é verificada de ponta a ponta, e a ``.feature`` do behave
também não a verifica** — os passos de preenchimento estão comentados lá desde que o
requisito "aluno com todos os requisitos cumpridos" ficou pendente (ver
``010.EDU.formar.aluno.feature``, cenário "Emitir Registro de Emissão de Diploma"). Aqui a
cobertura vai até onde ela existe: as duas telas respondem para o papel certo.

Não repete o que já está coberto: registrar aula e lançar nota com a posse no registro são
os mesmos formulários do módulo 06 (``test_06_encerramento``), só em outro diário, e as abas
do prontuário do aluno são o módulo 08.
"""

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

DATA = '22/07/2019'
MATRICULA_ALUNO = '20191101010001'


@pytest.fixture
def aluno_renovado(seed_matricula_renovada):
    """Aluno com 2019.1 fechado e matrícula renovada em 2019.2 — pronto para concluir."""
    from edu.models import Aluno

    return Aluno.objects.get(matricula=MATRICULA_ALUNO)


@pytest.fixture
def sufixo():
    from uuid import uuid4

    return uuid4().hex[:6].upper()


def test_secretaria_cadastra_tcc_do_aluno(logado_edu, aluno_renovado):
    """O TCC é pré-requisito de conclusão quando a matriz exige (``Matriz.exige_tcc``).

    A tela cobra banca (presidente) e orientação, e é por ela que a secretaria registra a
    defesa — sem esse registro o aluno não integraliza o curso.
    """
    from edu.models import ProjetoFinal

    projetos = ProjetoFinal.objects.filter(matricula_periodo__aluno=aluno_renovado, titulo='Meu TCC de e2e')
    try:
        tela = Tela(logado_edu('secretario')).ir(f'/edu/adicionar_projeto_final/{aluno_renovado.pk}/')
        tela.preencher_formulario(
            [
                ('Ano Letivo', 'lista', '2019'),
                ('Período Letivo', 'lista', '2'),
                ('Título do Trabalho', 'texto', 'Meu TCC de e2e'),
                ('Resumo do Trabalho', 'textarea', 'Resumo do trabalho de conclusão.'),
                ('Tipo de Trabalho', 'lista', 'Monografia'),
                ('Orientador', 'autocomplete', '100007'),
                # Presidente vem de `Professor.objects`, cujo autocomplete busca por nome; o
                # Orientador vem de `Vinculo.objects`, que aceita a matrícula.
                ('Presidente', 'autocomplete', 'Servidor P'),
                ('Defesa Online', 'checkbox', 'marcar'),
            ]
        )
        tela.clicar_botao('Salvar')

        tela.sucesso('TCC / Relatório adicionado com sucesso.')
        assert projetos.exists(), 'a UI disse que salvou, mas o TCC não persistiu'
    finally:
        projetos.delete()


def test_admin_cadastra_modelo_de_documento(logado_edu, sufixo):
    """O diploma é gerado a partir de um ``.docx`` com marcações (#ALUNO#, #CURSO#...).

    Sem modelo ativo para a modalidade do curso não há o que imprimir — é o primeiro dos dois
    cadastros que habilitam a emissão.
    """
    from edu.models import ModeloDocumento

    descricao = f'Diploma E2E {sufixo}'
    modelos = ModeloDocumento.objects.filter(descricao=descricao)
    try:
        tela = Tela(logado_edu('admin_academico')).ir('/admin/edu/modelodocumento/add/')
        tela.preencher_formulario(
            [
                ('Descrição', 'texto', descricao),
                ('Tipo', 'lista', 'DIPLOMA/CERTIFICADO'),
                ('Modalidade de Ensino', 'autocomplete', 'Especialização'),
                ('Template', 'arquivo', 'arquivo.docx'),
            ]
        )
        tela.clicar_botao('Salvar')

        tela.sucesso('Cadastro realizado com sucesso.')
        assert modelos.exists(), 'a UI disse que salvou, mas o modelo não persistiu'
    finally:
        modelos.delete()


def test_admin_configura_livro_de_registros(logado_edu, sufixo):
    """O livro é o controle legal da emissão: número de livro, folha e registro correntes.

    O SUAP incrementa esses contadores a cada diploma emitido, então a configuração é por
    campus e por conjunto de modalidades.
    """
    from edu.models import ConfiguracaoLivro

    descricao = f'Livro E2E {sufixo}'
    livros = ConfiguracaoLivro.objects.filter(descricao=descricao)
    try:
        tela = Tela(logado_edu('admin_academico')).ir('/admin/edu/configuracaolivro/add/')
        tela.preencher_formulario(
            [
                ('Descrição', 'texto', descricao),
                ('Campus', 'autocomplete', 'CEN'),
                ('Modalidades de Ensino', 'autocomplete multiplo', 'Especialização'),
                ('Nº do Livro Atual', 'texto', '1'),
                ('Folhas por Livro', 'texto', '200'),
                ('Nº da Folha Atual', 'texto', '1'),
                ('Nº do Registro Atual', 'texto', '1'),
            ]
        )
        tela.clicar_botao('Salvar')

        tela.sucesso('Cadastro realizado com sucesso.')
        livro = livros.get()
        assert livro.modalidades.exists(), 'livro sem modalidade não serve para emitir nada'
    finally:
        livros.delete()


def test_fecha_o_periodo_2019_2(logado_edu, aluno_renovado):
    """Fechar 2019.2 é o que consolida o último período antes da formatura.

    Mesmo assistente do módulo 06, outro período — e é aqui que ele importa: o diploma exige
    período fechado. Assíncrono como lá, então a asserção espera o banco.
    """
    import time

    from djtools.e2e_fixtures import escolher_autocomplete
    from edu.models import MatriculaPeriodo, SituacaoMatriculaPeriodo

    # A turma vem da matrícula do aluno, não de um `get` por curso/período: a renovação gera
    # uma turma por período da matriz e o `get` encontraria mais de uma.
    matricula_periodo = MatriculaPeriodo.objects.filter(aluno=aluno_renovado, ano_letivo__ano=2019, periodo_letivo=2).exclude(turma=None).first()
    assert matricula_periodo is not None, 'o aluno deveria estar em turma de 2019.2 depois da renovação'
    turma = matricula_periodo.turma
    MatriculaPeriodo.objects.filter(turma=turma).update(situacao=SituacaoMatriculaPeriodo.MATRICULADO)

    page = logado_edu('admin_academico')
    page.goto('/edu/fechar_periodo_letivo/')
    page.select_option('select[name=ano_letivo]', label='2019')
    page.select_option('select[name=periodo_letivo]', label='2')
    page.check('input[name=tipo][value="TURMA"]')
    # SEM `opcao=''`: o rótulo do resultado É o código da turma, então dá para ancorar nele.
    # `opcao=''` aceita o primeiro resultado seja qual for — e o AJAX do select2 dispara sobre
    # PREFIXOS do texto digitado, então o primeiro resultado costuma ser o de uma busca por
    # "2019...", não pela turma inteira. Foi assim que o assistente recebeu `turma=1` em vez
    # da turma alvo e travou em "Aguarde...". Ancorado, o clique espera a opção certa aparecer.
    escolher_autocomplete(page, 'turma', str(turma))
    page.click('input[type=submit][value="Continuar"]')
    try:
        page.wait_for_selector('input[name=confirmado]', timeout=10000)
    except Exception as falha:
        from djtools.e2e_ui import Tela

        raise AssertionError(f'o assistente de fechamento não avançou. {Tela(page).diagnostico()}') from falha
    page.check('input[name=forcar_fechamento]')
    page.check('input[name=confirmado]')
    page.click('input[type=submit][value="Finalizar"]')

    for _ in range(30):
        if not MatriculaPeriodo.objects.filter(turma=turma, situacao=SituacaoMatriculaPeriodo.MATRICULADO).exists():
            return
        time.sleep(1)
    raise AssertionError('o período 2019.2 continua matriculado depois do fechamento')


def test_coordenador_de_registros_alcanca_a_emissao_de_diploma(logado_edu, aluno_renovado):
    """As duas telas de diploma respondem para o Coordenador de Registros Acadêmicos.

    Verificação de acesso, não de emissão: a emissão exige aluno com todos os requisitos
    cumpridos (inclusive colação de grau), pendência que a própria ``.feature`` 010 registra
    com os passos comentados. ``edu.emitir_diploma`` é a permissão que separa este papel dos
    outros — o Secretário Acadêmico não passa daqui.
    """
    tela = Tela(logado_edu('registros_academicos'))
    resposta = tela.pagina.goto('/edu/emitir_diploma/')
    assert resposta.status == 200, 'o coordenador de registros acadêmicos não alcançou a emissão de diploma'

    resposta = tela.pagina.goto('/admin/edu/registroemissaodiploma/')
    assert resposta.status == 200, 'a listagem de registros de emissão não abriu'

    assert logado_edu('professor').goto('/edu/emitir_diploma/').status == 403, 'a emissão de diploma abriu para quem não emite diploma'
