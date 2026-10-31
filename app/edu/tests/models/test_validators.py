import pytest
from django.core.exceptions import ValidationError
from django.test import override_settings

from edu.models.atividades_complementares import AtividadeComplementar
from edu.models.cadastros_gerais import Cidade
from edu.models.cursos import Matriz, Minicurso
from edu.models.plano_oferta import PrevisaoQuantidadeAlunos
from edu.validators import validar_nota


class _PaisFake:
    def __init__(self, nome):
        self.nome = nome


def _define_pais_sem_banco(cidade, pais):
    Cidade._meta.get_field('pais').set_cached_value(cidade, pais)


def _assert_valida(model):
    try:
        model.clean()
    except ValidationError as exc:
        raise AssertionError(f'Validacao inesperada: {exc}') from exc


def test_atividade_complementar_rejeita_descricao_maior_que_100_quando_deferida():
    atividade = AtividadeComplementar(descricao='a' * 101, deferida=True)

    with pytest.raises(ValidationError):
        atividade.clean()


def test_atividade_complementar_aceita_descricao_ate_100_quando_deferida():
    atividade = AtividadeComplementar(descricao='a' * 100, deferida=True)

    _assert_valida(atividade)


def test_atividade_complementar_exige_razao_indeferimento_quando_nao_deferida():
    atividade = AtividadeComplementar(deferida=False, razao_indeferimento=None)

    with pytest.raises(ValidationError):
        atividade.clean()


def test_atividade_complementar_aceita_razao_quando_nao_deferida():
    atividade = AtividadeComplementar(deferida=False, razao_indeferimento='Motivo registrado')

    _assert_valida(atividade)


def test_atividade_complementar_nao_dispara_regra_quando_deferida_nula():
    atividade = AtividadeComplementar(deferida=None)

    _assert_valida(atividade)


@pytest.mark.parametrize('taxa', [-1, 101])
def test_previsao_quantidade_alunos_rejeita_taxa_evasao_fora_do_intervalo(taxa):
    previsao = PrevisaoQuantidadeAlunos(taxa_evasao_1=taxa)

    with pytest.raises(ValidationError):
        previsao.clean()


@pytest.mark.parametrize('taxa', [0, 50, 100])
def test_previsao_quantidade_alunos_aceita_taxa_evasao_no_intervalo(taxa):
    previsao = PrevisaoQuantidadeAlunos(taxa_evasao_1=taxa)

    _assert_valida(previsao)


def test_cidade_rejeita_codigo_quando_pais_nao_brasil():
    cidade = Cidade(codigo='456')
    _define_pais_sem_banco(cidade, _PaisFake('Argentina'))

    with pytest.raises(ValidationError):
        cidade.clean()


def test_cidade_aceita_codigo_quando_pais_brasil():
    cidade = Cidade(codigo='123')
    _define_pais_sem_banco(cidade, _PaisFake('Brasil'))

    _assert_valida(cidade)


def test_cidade_sem_codigo_e_sem_pais_rejeita():
    cidade = Cidade(codigo=None)

    with pytest.raises(ValidationError):
        cidade.clean()


def test_cidade_com_codigo_sem_pais_aceita():
    cidade = Cidade(codigo='789')

    _assert_valida(cidade)


def test_matriz_ativa_com_data_fim_rejeita():
    matriz = Matriz(ativo=True, data_fim='2025-12-31')

    with pytest.raises(ValidationError):
        matriz.clean()


def test_matriz_ativa_sem_data_fim_aceita():
    matriz = Matriz(ativo=True, data_fim=None)

    _assert_valida(matriz)


def test_matriz_inativa_sem_data_fim_rejeita():
    matriz = Matriz(ativo=False, data_fim=None)

    with pytest.raises(ValidationError):
        matriz.clean()


def test_matriz_inativa_com_data_fim_aceita():
    matriz = Matriz(ativo=False, data_fim='2025-06-30')

    _assert_valida(matriz)


@pytest.mark.parametrize('carga_horaria', [None, 0, 161])
def test_minicurso_rejeita_carga_horaria_fora_do_intervalo(carga_horaria):
    minicurso = Minicurso(ch_total=carga_horaria)

    with pytest.raises(ValidationError):
        minicurso.clean()


@pytest.mark.parametrize('carga_horaria', [1, 80, 160])
def test_minicurso_aceita_carga_horaria_no_intervalo(carga_horaria):
    minicurso = Minicurso(ch_total=carga_horaria)

    _assert_valida(minicurso)


# (NOTA_DECIMAL, CASA_DECIMAL, nota válida → valor, fora da faixa → mensagem, não numérica → mensagem)
MODOS_NOTA = [
    pytest.param(False, 0, ('85', 85), ('101', 'O campo Nota deve estar entre 0 e 100.'), ('abc', 'deve ser um número inteiro'), id='inteira'),
    pytest.param(
        True,
        1,
        ('8.5', 85),
        ('10.1', 'O campo Nota deve estar entre 0 e 10 com 1 casas decimais.'),
        ('abc', 'Ocorreu um erro na conversão'),
        id='1-casa',
    ),
    pytest.param(
        True,
        2,
        ('8.75', 875),
        ('10.01', 'O campo Nota deve estar entre 0 e 10 com 2 casas decimais.'),
        ('abc', 'Ocorreu um erro na conversão'),
        id='2-casas',
    ),
]


@pytest.mark.parametrize(('nota_decimal', 'casa_decimal', 'valida', 'fora_da_faixa', 'nao_numerica'), MODOS_NOTA)
def test_validar_nota_levanta_a_mesma_mensagem_que_acumula(nota_decimal, casa_decimal, valida, fora_da_faixa, nao_numerica):
    # Com raise_exception=True a mensagem específica não pode virar "erro na conversão" (#17458).
    with override_settings(NOTA_DECIMAL=nota_decimal, CASA_DECIMAL=casa_decimal):
        assert validar_nota(valida[0], 'Nota', raise_exception=True) == valida[1]
        for valor, mensagem in (fora_da_faixa, nao_numerica):
            erros = []
            assert validar_nota(valor, 'Nota', erros=erros) is None
            assert len(erros) == 1
            assert mensagem in erros[0]
            with pytest.raises(ValueError) as excinfo:
                validar_nota(valor, 'Nota', raise_exception=True)
            assert str(excinfo.value) == erros[0]
