"""Tarefa 4 — matricular um aluno do zero.

Duas etapas de um objetivo só: a **Matrícula Institucional** (cinco passos que só avançam
quando o anterior valida, e o único ponto do módulo que cria pessoa, usuário e matrícula de
uma vez) e a matrícula **na turma**, que é o que dá ao aluno os diários onde a nota será
lançada. Ninguém faz a primeira sem a segunda.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from playwright.sync_api import expect
from pycpfcnpj import gen

from djtools.e2e_fixtures import mensagem_de_sucesso
from djtools.e2e_ui import Tela
from edu.tests.doc.conftest import anotar, escolher

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

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
    from edu.models import Turma

    return Turma.objects.get(ano_letivo__ano=2019, periodo_letivo=1, curso_campus__codigo='10101')


@pytest.fixture
def aluno_sem_turma(turma_2019_1, sufixo, cpf_novo):
    """Aluno matriculado no curso mas ainda fora da turma — o alvo da etapa 2."""
    from comum.models import Ano, Raca
    from edu.models import Cidade, FormaIngresso
    from edu.tests.e2e.seed import cadastrar_aluno, matricular_aluno
    from rh.models import PessoaFisica

    pessoa = PessoaFisica()
    pessoa.cpf = cpf_novo
    pessoa.nome_registro = f'Aluno DOC {sufixo}'
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


def test_efetuar_matricula_institucional(logado_edu, sufixo, cpf_novo, capturar):
    """Etapa 1 — os cinco passos da matrícula direta, do CPF até a matrícula gerada."""
    from edu.models import Aluno

    nome = f'Joana {sufixo}'
    page = logado_edu('secretario')
    tela = Tela(page).ir('/edu/efetuar_matricula/')
    expect(page.get_by_role('heading', name='Matrícula Institucional')).to_be_visible()
    anotar('matricula-passo-1', tela)
    capturar(page, 'matricula-passo-1')

    page.select_option('select[name=nacionalidade]', label='Brasileira')
    page.fill('input[name=cpf]', cpf_novo)
    page.click('input[type=submit][value="Continuar"]')

    anotar('matricula-passo-2', Tela(page))
    page.fill('input[name=nome]', nome)
    page.select_option('select[name=sexo]', label='Feminino')
    page.fill('input[name=data_nascimento]', '1990-10-10')
    page.select_option('select[name=estado_civil]', label='Solteiro')
    page.fill('input[name=nome_mae]', 'Maria da Silva')
    page.fill('input[name=logradouro]', 'Rua abcd')
    page.fill('input[name=numero]', '123')
    page.fill('input[name=bairro]', 'qwer')
    escolher(page, 'cidade', 'Natal')
    page.select_option('select[name=tipo_zona_residencial]', label='Urbana')
    capturar(page, 'matricula-passo-2')
    page.click('input[type=submit][value="Continuar"]')

    anotar('matricula-passo-3', Tela(page))
    page.fill('input[name=email_pessoal]', f'{nome.split(maxsplit=1)[0].lower()}.doc@email.com')
    page.select_option('select[name=aluno_pne]', label='Não')
    page.select_option('select[name=utiliza_transporte_escolar_publico]', label='Não')
    escolher(page, 'naturalidade', 'Natal')
    page.select_option('select[name=raca]', label='Parda')
    page.select_option('select[name=nivel_ensino_anterior]', label='Fundamental')
    page.select_option('select[name=tipo_instituicao_origem]', label='Pública')
    page.select_option('select[name=ano_conclusao_estudo_anterior]', label='2018')
    page.click('input[type=submit][value="Continuar"]')

    anotar('matricula-passo-4', Tela(page))
    page.select_option('select[name=tipo_certidao]', label='Nascimento')
    capturar(page, 'matricula-passo-4')
    page.click('input[type=submit][value="Continuar"]')

    anotar('matricula-passo-5', Tela(page))
    page.select_option('select[name=ano_letivo]', label='2019')
    page.select_option('select[name=periodo_letivo]', label='1')
    page.select_option('select[name=turno]', label='Matutino')
    page.select_option('select[name=forma_ingresso]', label='Ampla Concorrência')
    page.select_option('select[name=possui_convenio]', label='Não')
    page.select_option('select[name=possui_orientador]', label='Não')
    escolher(page, 'matriz_curso', '10101', opcao='')
    capturar(page, 'matricula-passo-5')
    page.click('input[type=submit][value="Finalizar Matrícula Institucional"]')

    mensagem_de_sucesso(page, 'Matrícula realizada com sucesso.')
    aluno = Aluno.objects.filter(pessoa_fisica__cpf=cpf_novo).first()
    assert aluno is not None, 'a UI disse que matriculou, mas não persistiu'
    assert aluno.matricula, 'aluno sem número de matrícula: o sequencial não foi gerado'
    capturar(page, 'matricula-resultado')
    anotar('matricula-resultado', Tela(page))


def test_matricular_aluno_em_turma(logado_edu, turma_2019_1, aluno_sem_turma, capturar):
    """Etapa 2 — da matrícula no curso para a turma: é isso que cria os diários do aluno."""
    from edu.models import MatriculaDiario

    page = logado_edu('secretario')
    tela = Tela(page).ir(f'/edu/turma/{turma_2019_1.pk}/?tab=dados_alunos')
    anotar('turma-alunos', tela)
    capturar(page, 'turma-alunos')

    page.get_by_role('link', name='Adicionar alunos').first.click()
    tela.esperar()
    anotar('turma-adicionar-alunos', Tela(page))
    caixa = page.locator(f'input[type=checkbox][value="{aluno_sem_turma.matriculaperiodo_set.first().pk}"]')
    expect(caixa).to_be_visible()
    caixa.check()
    capturar(page, 'turma-adicionar-alunos')
    page.click('input[type=submit][value="Matricular Alunos Selecionados"]')

    mensagem_de_sucesso(page, 'Aluno(s) matriculado(s) com sucesso.')
    assert MatriculaDiario.objects.filter(matricula_periodo__aluno=aluno_sem_turma).exists(), (
        'aluno matriculado na turma mas sem diário: a turma não propagou os diários'
    )
