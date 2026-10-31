"""Fluxo 009: a área do aluno — o outro lado de tudo que os módulos anteriores gravaram.

Oitavo elo. Aqui não se cria nada: verifica-se que o histórico, o boletim e os requisitos
de conclusão **refletem** o que a secretaria e o professor lançaram. É a única cobertura
do módulo que roda com um usuário de vínculo "aluno" (grupo, menu e permissões diferentes
dos servidores) e a que pega quebra de template das abas do prontuário.
"""

import pytest
from playwright.sync_api import expect

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

DATA = '22/07/2019'
MATRICULA_ALUNO = '20191101010001'
SENHA_ALUNO = '123'


@pytest.fixture
def aluno(seed_matricula_renovada):
    """Aluno com 2019.1 fechado e 2019.2 renovado — histórico já tem o que mostrar."""
    from edu.models import Aluno

    return Aluno.objects.get(matricula=MATRICULA_ALUNO)


def test_aluno_acessa_os_proprios_dados_academicos(logado_edu, aluno):
    page = logado_edu(MATRICULA_ALUNO, senha=SENHA_ALUNO)
    page.goto('/edu/meus_dados_academicos/')
    expect(page.get_by_role('heading', name=aluno.pessoa_fisica.nome)).to_be_visible()


@pytest.mark.parametrize(
    ('aba', 'texto'),
    [
        ('dados_academicos', 'Matrículas em Períodos'),
        ('historico', 'Componentes Curriculares'),
        ('requisitos', 'Requisitos'),
    ],
)
def test_aluno_ve_as_abas_do_prontuario(logado_edu, aluno, aba, texto):
    """Cada aba do prontuário é montada por uma consulta diferente sobre o histórico.

    Parametrizado porque o que se mede é a mesma coisa em três recortes; um teste por aba
    deixaria explícito qual quebrou sem repetir o corpo.
    """
    page = logado_edu(MATRICULA_ALUNO, senha=SENHA_ALUNO)
    page.goto(f'/edu/aluno/{aluno.matricula}/?tab={aba}')
    expect(page.get_by_text(texto).first).to_be_visible()


def test_aluno_ve_suas_disciplinas_do_periodo(logado_edu, aluno):
    """ "Minhas disciplinas" é a porta do aluno para o diário — filtrada por período.

    Depois da renovação de matrícula (módulo 07) o aluno tem diários em 2019.2; é esse
    recorte que o filtro seleciona.
    """
    from edu.models import MatriculaDiario

    matricula_diario = MatriculaDiario.objects.filter(matricula_periodo__aluno=aluno, diario__turma__periodo_letivo=2).first()
    assert matricula_diario is not None, 'o aluno deveria ter diário em 2019.2 depois da renovação'

    tela = Tela(logado_edu(MATRICULA_ALUNO, senha=SENHA_ALUNO)).ir('/edu/disciplinas/')
    # O filtro desta tela não tem botão: o `select` submete sozinho no `change`.
    tela.preencher('Período', 'lista', '2019.2')
    tela.esperar()

    tela.ver_texto(matricula_diario.diario.componente_curricular.componente.sigla)


def test_aluno_atualiza_os_proprios_dados_pessoais(logado_edu, aluno):
    """O aluno mantém seu cadastro — e só o dele (``atualizar_meus_dados_pessoais`` recusa
    quem não é o dono da matrícula).

    O campo escolhido é o do transporte escolar porque é o único da tela que se resolve numa
    lista de duas opções e tem efeito observável direto em ``Aluno``.
    """
    tela = Tela(logado_edu(MATRICULA_ALUNO, senha=SENHA_ALUNO)).ir(f'/edu/atualizar_meus_dados_pessoais/{aluno.matricula}/')
    tela.preencher('Utiliza Transporte Escolar Público', 'lista', 'Não')
    tela.clicar_botao('Enviar')

    tela.sucesso('Dados Pessoais atualizados com sucesso.')
    aluno.refresh_from_db()
    # "Não" grava valor vazio, não `False` — o que importa é o transporte ficar desligado.
    assert not aluno.poder_publico_responsavel_transporte, 'a resposta "Não" deveria desligar o transporte escolar'


@pytest.fixture
def banco_cadastrado(aluno):
    """Um banco na base — sem ele o autocomplete de instituição do dado bancário é vazio."""
    from rh.models import Banco

    return Banco.objects.get_or_create(codigo='001', sigla='BB', defaults={'nome': 'Banco do Brasil'})[0]


def test_aluno_adiciona_dados_bancarios(logado_edu, aluno, banco_cadastrado):
    """Dado bancário do aluno mora no módulo de assistência estudantil (``ae``).

    Está aqui porque a tela é a do prontuário do aluno no edu (aba "Dados bancários") — é o
    caminho da funcionalidade 009, e é o dado que a assistência usa para pagar auxílio.
    """
    from ae.models import DadosBancarios

    dados = DadosBancarios.objects.filter(aluno=aluno, numero_conta='12345')
    try:
        tela = Tela(logado_edu(MATRICULA_ALUNO, senha=SENHA_ALUNO)).ir(f'/ae/adicionar_dado_bancario/{aluno.pk}/')
        # Dado bancário é informação sensível: a tela pede um código antes de liberar o
        # formulário. Só depois de "Autenticar" os campos do banco existem.
        tela.preencher('Código', 'texto', '123456')
        tela.clicar_botao('Autenticar')
        tela.preencher('Banco', 'autocomplete', banco_cadastrado.nome)
        tela.preencher('Número da Agência', 'texto', '123456')
        tela.preencher('Tipo da Conta', 'lista', 'Conta Corrente')
        tela.preencher('Número da Conta', 'texto', '12345')
        tela.clicar_botao('Salvar')

        tela.sucesso('Dados bancários adicionado com sucesso.')
        assert dados.exists(), 'a UI disse que salvou, mas o dado bancário não persistiu'
    finally:
        dados.delete()


@pytest.fixture
def tipo_de_atividade_complementar(aluno):
    """Tipo de atividade complementar ofertado à matriz do aluno.

    Não basta o tipo existir: a tela só oferece os tipos que a **configuração de AACC da
    matriz** contempla (``ItemConfiguracaoAtividadeComplementar``), que é o que limita a carga
    horária aproveitável. Montado por ORM porque o cadastro dessas duas telas é coberto no
    módulo 02.
    """
    from edu.models import ConfiguracaoAtividadeComplementar, ItemConfiguracaoAtividadeComplementar, Matriz, TipoAtividadeComplementar

    tipo = TipoAtividadeComplementar.objects.get_or_create(descricao='Atividade Complementar E2E')[0]
    tipo.modalidades.add(aluno.curso_campus.modalidade)
    configuracao = ConfiguracaoAtividadeComplementar.objects.get_or_create(descricao='Configuração AACC E2E')[0]
    ItemConfiguracaoAtividadeComplementar.objects.get_or_create(configuracao=configuracao, tipo=tipo, defaults={'fator_conversao': 1})
    Matriz.objects.filter(pk=aluno.matriz_id).update(configuracao_atividade_academica=configuracao)
    return tipo


def test_aluno_informa_atividade_complementar(logado_edu, aluno, tipo_de_atividade_complementar):
    """Atividade complementar declarada pelo aluno entra como solicitação, não como fato.

    A própria mensagem do SUAP diz que falta validação presencial — ou seja, o que a tela
    grava é uma ``AtividadeComplementar`` pendente, e é isso que se verifica.
    """
    from edu.models import AtividadeComplementar

    tipo = tipo_de_atividade_complementar
    atividades = AtividadeComplementar.objects.filter(aluno=aluno, descricao='Atividade de e2e')
    try:
        tela = Tela(logado_edu(MATRICULA_ALUNO, senha=SENHA_ALUNO)).ir('/edu/solicitar_atividade_complementar/')
        tela.preencher_formulario(
            [
                ('Ano Letivo', 'lista', '2019'),
                ('Período Letivo', 'lista', '1'),
                ('Tipo', 'lista', tipo.descricao),
                ('Atividade', 'texto', 'Atividade de e2e'),
                ('Data de Início da Atividade', 'data', '01/01/2019'),
                ('Data da Conclusão da Atividade', 'data', '01/01/2019'),
                ('Carga Horária', 'texto', '10'),
                ('Anexo', 'arquivo', 'arquivo.pdf'),
            ]
        )
        tela.clicar_botao('Salvar')

        tela.sucesso('Atividade complementar adicionada com sucesso.')
        assert atividades.exists(), 'a UI disse que salvou, mas a atividade não persistiu'
    finally:
        atividades.delete()


def test_aluno_tem_os_documentos_academicos_disponiveis(logado_edu, aluno):
    """Declarações e comprovantes são emitidos da própria área do aluno.

    Verificação de disponibilidade, não de conteúdo: cada documento é um PDF gerado por
    ``@documento()``, e o que a funcionalidade 009 descreve é o aluno encontrar os botões.
    """
    tela = Tela(logado_edu(MATRICULA_ALUNO, senha=SENHA_ALUNO)).ir('/edu/meus_dados_academicos/')
    tela.clicar_botao('Documentos')

    # Os documentos saem como itens de menu (links), não como botões de ação da tela.
    tela.ver_texto('Histórico Parcial')
    tela.ver_texto('Comprovante de Dados Acadêmicos')


def test_secretaria_abre_a_ficha_do_aluno(logado_edu, aluno):
    """A mesma ficha vista pela secretaria — é por ela que se corrige dado cadastral."""
    page = logado_edu('secretario')
    page.goto(f'/edu/aluno/{aluno.matricula}/')
    expect(page.get_by_role('heading', name=aluno.pessoa_fisica.nome)).to_be_visible()
    expect(page.get_by_text(MATRICULA_ALUNO).first).to_be_visible()


def test_aluno_nao_ve_a_ficha_de_outro_aluno(logado_edu, aluno):
    """Fronteira de acesso: prontuário é dado pessoal, não listagem pública."""
    from edu.models import Aluno

    outro = Aluno.objects.exclude(matricula=MATRICULA_ALUNO).filter(curso_campus=aluno.curso_campus).first()
    assert outro is not None, 'o replay deveria ter matriculado mais de um aluno no curso'

    page = logado_edu(MATRICULA_ALUNO, senha=SENHA_ALUNO)
    page.goto(f'/edu/aluno/{outro.matricula}/')

    # O SUAP não responde 403 aqui: redireciona para a página inicial. O que importa é que
    # o prontuário do outro aluno não chega a ser renderizado.
    assert f'/edu/aluno/{outro.matricula}/' not in page.url, 'aluno permaneceu no prontuário de outro aluno'
    expect(page.get_by_text(outro.matricula)).to_have_count(0)


def test_aluno_ve_a_propria_tela_inicial(logado_edu, aluno):
    """A tela inicial do aluno é o painel dele: curso, pendências e avisos.

    Verificação de renderização, não de conteúdo: as pendências que aparecem ali dependem de
    questionário e de configuração de renovação vigentes, que variam com a data congelada de
    cada módulo — o que é estável é o painel trazer o vínculo acadêmico do aluno.
    """
    tela = Tela(logado_edu(MATRICULA_ALUNO, senha=SENHA_ALUNO)).ir('/')

    # A tela inicial do aluno é feita de quadros de atalho; o quadro "Ensino" com "Minhas
    # disciplinas" é o que só existe para quem tem vínculo de aluno.
    tela.ver_texto('Minhas disciplinas')
    tela.ver_texto('Meus dados')
