"""Migração de alunos por CSV (``ImportadorAlunos``): uma linha já validada vira aluno + pessoa física."""

import datetime

import pytest

from comum.models import Pais as PaisPessoa
from comum.tests.factories import AnoFactory
from edu.models import Pais
from edu.migracao import salvar_aluno
from edu.tests.factories import SituacaoMatriculaFactory


@pytest.mark.django_db
def test_estrangeiro_so_com_passaporte_cria_pessoa_pelo_passaporte_e_pais() -> None:
    PaisPessoa.objects.create(codigo='011', nome='ARGENTINA', iso_alfa3='ARG')
    argentina = Pais.objects.create(sigla='AR', nome='Argentina', codigo='999')  # código de outro esquema: a conversão é pelo nome
    registro = {
        'matricula': '20261ESTRANG01',
        'nacionalidade': 'Estrangeira',
        'passaporte': 'ab 123456',
        'pais_origem_id': argentina.pk,
        'ano_letivo_id': AnoFactory(ano=2026).pk,
        'periodo_letivo': 1,
        'situacao_id': SituacaoMatriculaFactory().pk,
        'ano_let_prev_conclusao': 2029,
        'data_matricula': datetime.datetime(2026, 2, 1),
        'PessoaFisica': {
            'cpf': None,
            'nome_registro': 'Juan Perez Gomez',
            'nome_social': None,
            'sexo': 'M',
            'nascimento_data': datetime.date(2000, 1, 1),
            'raca_id': None,
        },
    }

    aluno = salvar_aluno(registro)

    pessoa = aluno.pessoa_fisica
    pessoa.refresh_from_db()
    assert (pessoa.passaporte, pessoa.pais_origem.codigo, pessoa.documento_identificador) == ('AB123456', '011', 'ARG-AB123456')


@pytest.mark.django_db
def test_validacao_da_linha_recusa_passaporte_invalido() -> None:
    from edu.validators import validar_alunos

    linha = {'Aluno.nacionalidade': 'Estrangeira', 'Aluno.passaporte': 'AAAAAA'}

    _, erros = validar_alunos(linha, ignorar_obrigatorios=True)
    _, erros_validos = validar_alunos({**linha, 'Aluno.passaporte': 'AB123456'}, ignorar_obrigatorios=True)

    assert [erro for erro in erros if 'Aluno.passaporte' in erro]
    assert not [erro for erro in erros_validos if 'Aluno.passaporte' in erro]


@pytest.mark.django_db
def test_planilha_nao_troca_o_documento_da_pessoa_do_aluno_mas_atualiza_o_resto() -> None:
    from edu.tests.factories import AlunoFactory
    from rh.tests.factories import cpf_valido

    # depois da deduplicação a PF do aluno pode ser a do servidor: o CPF dela só muda pelo SIAPE ou pelo formulário de PF
    aluno = AlunoFactory(pessoa_fisica__cpf=cpf_valido(970), pessoa_fisica__nome_registro='Nome Antigo')
    registro = {'matricula': aluno.matricula, 'PessoaFisica': {'cpf': cpf_valido(971), 'nome_registro': 'Nome Novo'}}

    salvar_aluno(registro)

    pessoa = aluno.pessoa_fisica
    pessoa.refresh_from_db()
    assert (pessoa.cpf, pessoa.nome_registro) == (cpf_valido(970), 'Nome Novo')


@pytest.mark.django_db
def test_linha_que_daria_ao_aluno_o_cpf_de_outra_pessoa_vira_erro_de_validacao() -> None:
    # cosinf/suap#17672: antes, a linha derrubava a importação inteira no meio (rollback); agora vai para o arquivo de erros
    from edu.migracao import ImportadorAlunos
    from edu.tests.factories import AlunoFactory
    from rh.models import PessoaFisica
    from rh.tests.factories import PessoaFisicaFactory, cpf_valido

    aluno = AlunoFactory(pessoa_fisica__cpf=cpf_valido(972))
    PessoaFisica.objects.filter(pk=aluno.pessoa_fisica_id).update(cpf=None, documento_identificador=f'SEMDOC-{aluno.pessoa_fisica_id}')
    PessoaFisicaFactory(cpf=cpf_valido(973))
    linha = {'Aluno.matricula': aluno.matricula, 'Aluno.PessoaFisica.cpf': cpf_valido(973)}

    _, erros = ImportadorAlunos('', apenas_validar=True, ignorar_obrigatorios=True).validar_linha(linha, ignorar_obrigatorios=True)

    assert [erro for erro in erros if aluno.matricula in erro and 'outra pessoa' in erro]
