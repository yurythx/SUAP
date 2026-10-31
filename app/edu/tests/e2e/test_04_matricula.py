"""Fluxo 004: matricular aluno — forma de ingresso, matrícula direta e turma.

Quarto elo. A **Matrícula Institucional** é o formulário mais longo do SUAP: cinco passos
que só avançam quando o anterior valida, e é o único ponto do módulo que cria a pessoa,
o usuário e a matrícula de uma vez. Depois dela, matricular na turma é o que dá ao aluno
os diários onde a nota será lançada no módulo 05.
"""

from uuid import uuid4

import pytest
from playwright.sync_api import expect
from pycpfcnpj import gen

from djtools.e2e_fixtures import escolher_autocomplete, mensagem_de_sucesso
from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

DATA = '10/03/2019'


@pytest.fixture
def sufixo():
    """Sufixo só com letras: o cadastro recusa dígito em campo de nome de pessoa."""
    return ''.join(chr(ord('A') + int(digito, 16) % 26) for digito in uuid4().hex[:6])


@pytest.fixture
def cpf_novo():
    """CPF válido e inédito — o passo 1 recusa CPF já cadastrado e valida os dígitos."""
    numero = gen.cpf()
    return f'{numero[:3]}.{numero[3:6]}.{numero[6:9]}-{numero[9:]}'


@pytest.fixture
def turma_2019_1(edu_seed):
    """Turma 2019.1 do curso 10101 — a que o replay monta e o módulo 05 executa."""
    from edu.models import Turma

    return Turma.objects.get(ano_letivo__ano=2019, periodo_letivo=1, curso_campus__codigo='10101')


@pytest.fixture
def aluno_sem_turma(turma_2019_1, sufixo, cpf_novo):
    """Aluno matriculado no curso mas AINDA fora da turma.

    Criado por ORM (mesmas funções que o replay usa) para o teste de "adicionar alunos à
    turma" não depender do teste da matrícula institucional ter rodado antes.

    Não há limpeza: apagar um `Aluno` dispara o log do `LogModel`, que grava em
    `django_admin_log` com o usuário do threadlocal e estoura FK fora de request. Cada
    execução cria um aluno de CPF novo, e ele sai da lista de "adicionar alunos" assim
    que é matriculado — o resíduo é inerte.
    """
    from comum.models import Ano, Raca
    from edu.tests.e2e.seed import cadastrar_aluno, matricular_aluno
    from edu.models import Cidade, FormaIngresso
    from rh.models import PessoaFisica

    pessoa = PessoaFisica()
    pessoa.cpf = cpf_novo
    pessoa.nome_registro = f'Aluno E2E {sufixo}'
    pessoa.sexo = 'M'
    pessoa.nascimento_data = '1990-10-10'
    pessoa.raca = Raca.objects.get(descricao='Parda')
    pessoa.save()

    aluno = cadastrar_aluno(
        pessoa,
        Cidade.objects.get(nome='Natal'),
        Ano.objects.get(ano=2019),
        FormaIngresso.objects.get(descricao='Ampla Concorrência'),
        turma_2019_1.curso_campus,
        turma_2019_1.matriz,
    )
    matricular_aluno(aluno, Ano.objects.get(ano=2019), turma_2019_1.curso_campus, turma_2019_1.matriz)
    return aluno


def test_cadastra_forma_de_ingresso(logado_edu, sufixo):
    """Forma de ingresso é o que o SUAP exporta para CENSUP/EDUCACENSO — cadastro simples."""
    from edu.models import FormaIngresso

    descricao = f'Ampla Concorrência {sufixo}'
    page = logado_edu('admin_academico')
    try:
        page.goto('/admin/edu/formaingresso/add/')
        page.fill('input[name=descricao]', descricao)
        page.check('input[name=ativo]')
        page.select_option('select[name=classificacao_censup]', label='Enem')
        page.select_option('select[name=classificacao_educacenso]', label='Exame de seleção sem reserva de vaga')
        page.click('input[name=_save]')

        mensagem_de_sucesso(page, 'Cadastro realizado com sucesso.')
        assert FormaIngresso.objects.filter(descricao=descricao).exists(), 'a UI disse que salvou, mas não persistiu'
    finally:
        FormaIngresso.objects.filter(descricao=descricao).delete()


def test_efetua_matricula_institucional(logado_edu, sufixo, cpf_novo):
    """Os cinco passos da matrícula direta, do CPF até o aluno com matrícula gerada."""
    from edu.models import Aluno

    # Sem dígitos no nome: o formulário recusa (por isso não há "E2E" aqui).
    nome = f'Joana {sufixo}'
    page = logado_edu('secretario')
    _preencher_matricula_institucional(page, nome, cpf_novo)

    mensagem_de_sucesso(page, 'Matrícula realizada com sucesso.')
    aluno = Aluno.objects.filter(pessoa_fisica__cpf=cpf_novo).first()
    assert aluno is not None, 'a UI disse que matriculou, mas não persistiu'
    assert aluno.matricula, 'aluno sem número de matrícula: o sequencial não foi gerado'
    assert aluno.curso_campus.codigo == '10101', 'aluno vinculado a outro curso que não o escolhido'


def _preencher_matricula_institucional(page, nome: str, cpf: str) -> None:
    page.goto('/edu/efetuar_matricula/')
    expect(page.get_by_role('heading', name='Matrícula Institucional')).to_be_visible()

    # Passo 1 — Identificação
    page.select_option('select[name=nacionalidade]', label='Brasileira')
    page.fill('input[name=cpf]', cpf)
    page.click('input[type=submit][value="Continuar"]')

    # Passo 2 — Dados pessoais, familiares e endereço
    page.fill('input[name=nome]', nome)
    page.select_option('select[name=sexo]', label='Feminino')
    page.fill('input[name=data_nascimento]', '1990-10-10')
    page.select_option('select[name=estado_civil]', label='Solteiro')
    page.fill('input[name=nome_mae]', 'Maria da Silva')
    page.fill('input[name=logradouro]', 'Rua abcd')
    page.fill('input[name=numero]', '123')
    page.fill('input[name=bairro]', 'qwer')
    escolher_autocomplete(page, 'cidade', 'Natal')
    page.select_option('select[name=tipo_zona_residencial]', label='Urbana')
    page.click('input[type=submit][value="Continuar"]')

    # Passo 3 — Contato, transporte, outras informações e escolaridade anterior
    page.fill('input[name=email_pessoal]', f'{nome.split(maxsplit=1)[0].lower()}.e2e@email.com')
    page.select_option('select[name=aluno_pne]', label='Não')
    page.select_option('select[name=utiliza_transporte_escolar_publico]', label='Não')
    # Para brasileiro o autocomplete de Naturalidade só lista cidade com código IBGE.
    escolher_autocomplete(page, 'naturalidade', 'Natal')
    page.select_option('select[name=raca]', label='Parda')
    page.select_option('select[name=nivel_ensino_anterior]', label='Fundamental')
    page.select_option('select[name=tipo_instituicao_origem]', label='Pública')
    page.select_option('select[name=ano_conclusao_estudo_anterior]', label='2018')
    page.click('input[type=submit][value="Continuar"]')

    # Passo 4 — Documentos
    page.select_option('select[name=tipo_certidao]', label='Nascimento')
    page.click('input[type=submit][value="Continuar"]')

    # Passo 5 — Dados da matrícula
    page.select_option('select[name=ano_letivo]', label='2019')
    page.select_option('select[name=periodo_letivo]', label='1')
    page.select_option('select[name=turno]', label='Matutino')
    page.select_option('select[name=forma_ingresso]', label='Ampla Concorrência')
    page.select_option('select[name=possui_convenio]', label='Não')
    page.select_option('select[name=possui_orientador]', label='Não')
    escolher_autocomplete(page, 'matriz_curso', '10101', opcao='')
    page.click('input[type=submit][value="Finalizar Matrícula Institucional"]')


def test_matricula_aluno_em_turma(logado_edu, turma_2019_1, aluno_sem_turma):
    """Da matrícula no curso para a matrícula na turma: é isso que cria os diários do aluno."""
    from edu.models import MatriculaDiario

    page = logado_edu('secretario')
    page.goto(f'/edu/turma/{turma_2019_1.pk}/?tab=dados_alunos')
    page.get_by_role('link', name='Adicionar alunos').first.click()

    caixa = page.locator(f'input[type=checkbox][value="{aluno_sem_turma.matriculaperiodo_set.first().pk}"]')
    expect(caixa).to_be_visible()
    caixa.check()
    page.click('input[type=submit][value="Matricular Alunos Selecionados"]')

    mensagem_de_sucesso(page, 'Aluno(s) matriculado(s) com sucesso.')
    assert MatriculaDiario.objects.filter(matricula_periodo__aluno=aluno_sem_turma).exists(), (
        'aluno matriculado na turma mas sem diário: a turma não propagou os diários'
    )


def test_aluno_nao_efetua_matricula(logado_edu, edu_seed):
    """A matrícula institucional é da secretaria; o professor não alcança a tela."""
    page = logado_edu('professor')
    assert page.goto('/edu/efetuar_matricula/').status == 403


def test_cadastra_convenio(logado_edu, sufixo):
    """Convênio é o que amarra a matrícula a um programa (PRONATEC e afins)."""
    from edu.models import Convenio

    descricao = f'PRONATEC {sufixo}'
    convenios = Convenio.objects.filter(descricao=descricao)
    try:
        tela = Tela(logado_edu('admin_academico')).ir('/admin/edu/convenio/add/')
        tela.preencher('Descrição', 'texto', descricao)
        tela.clicar_botao('Salvar')

        tela.sucesso('Cadastro realizado com sucesso.')
        assert convenios.exists(), 'a UI disse que salvou, mas não persistiu'
    finally:
        convenios.delete()


def test_cadastra_cidade(logado_edu, sufixo):
    """Cidade alimenta a naturalidade da matrícula institucional.

    O código do IBGE não é decorativo: o autocomplete de Naturalidade só lista cidade
    brasileira com ``codigo`` preenchido — foi por isso que a matrícula institucional falhava
    quando o replay criava "Natal" sem código.
    """
    from edu.models import Cidade

    nome = f'Natal {sufixo}'
    cidades = Cidade.objects.filter(nome=nome)
    try:
        tela = Tela(logado_edu('admin_academico')).ir('/admin/edu/cidade/add/')
        tela.preencher_formulario(
            [
                ('Nome', 'texto', nome),
                ('Estado', 'lista', 'Rio Grande do Norte'),
                ('País', 'autocomplete', 'Brasil'),
                ('CEP Inicial', 'texto', '59000000'),
                ('CEP Final', 'texto', '59149999'),
                ('Código', 'texto', f'24{uuid4().int % 10**5:05d}'),
            ]
        )
        tela.clicar_botao('Salvar')

        tela.sucesso('Cadastro realizado com sucesso.')
        cidade = cidades.get()
        assert cidade.codigo, 'cidade sem código do IBGE não aparece na naturalidade'
    finally:
        cidades.delete()
