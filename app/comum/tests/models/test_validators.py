"""Comportamento observável dos validadores de importação (``comum/validators.py``).

São funções puras usadas pela importação em massa do ``edu`` (``edu/validators.py`` →
``edu/tasks.py``), que lê planilhas e valida campo a campo. Duas coisas são contrato aqui
e por isso os testes afirmam ambas: o **valor devolvido** (que vai para o banco) e a
**mensagem de erro** (que aparece para quem subiu a planilha).

Os três modos de erro de ``handle_error`` são distintos e testados separadamente:
``raise_exception=True`` levanta ``ValueError`` (não ``ValidationError`` do Django),
``erros=[]`` acumula a mensagem na lista, e o padrão (sem os dois) devolve ``None``
silenciosamente — o erro não é registrado em lugar nenhum.

Quase tudo aqui roda sem banco. Só ``extrair_ano`` e ``validar_modelo`` consultam o ORM.
"""

from __future__ import annotations

import datetime

import pytest

from comum.models import Ano, AreaAtuacao, Predio
from comum.tests.factories import AnoFactory, AreaAtuacaoFactory, PredioFactory
from comum.validators import (
    extrair_ano,
    extrair_periodo_letivo,
    handle_error,
    validar_booleano,
    validar_data,
    validar_decimal,
    validar_formatacao_cpf,
    validar_inteiro,
    validar_modelo,
    validar_string,
)


class TestHandleError:
    """Os três destinos possíveis de uma mensagem de erro."""

    def test_sem_lista_e_sem_raise_o_erro_some(self) -> None:
        # Modo padrão de todos os validadores: nada é levantado e nada é registrado.
        assert handle_error('deu ruim', None, False) is None

    def test_com_lista_acumula_a_mensagem(self) -> None:
        erros: list[str] = []
        handle_error('deu ruim', erros, False)
        assert erros == ['deu ruim']

    def test_com_raise_levanta_value_error_com_a_mensagem(self) -> None:
        with pytest.raises(ValueError, match='deu ruim'):
            handle_error('deu ruim', None, True)


class TestValidarFormatacaoCpf:
    @pytest.mark.parametrize('valor', ['123.456.789-09', '12345678909', '  12345678909  ', '1-2-3-4-5-6-7-8-9-0-9'])
    def test_devolve_o_cpf_no_formato_canonico(self, valor: str) -> None:
        # #17410: o formato gravado em PessoaFisica.cpf é "000.000.000-00" (ver mask_cpf).
        assert validar_formatacao_cpf(valor, 'CPF') == '123.456.789-09'

    def test_recusa_dez_digitos(self) -> None:
        with pytest.raises(ValueError, match='deve conter exatamente 11 dígitos'):
            validar_formatacao_cpf('123.456.789-0', 'CPF', raise_exception=True)

    def test_recusa_quantidade_errada_de_digitos(self) -> None:
        with pytest.raises(ValueError, match='deve conter exatamente 11 dígitos'):
            validar_formatacao_cpf('123', 'CPF', raise_exception=True)

    def test_campo_obrigatorio_vazio_e_recusado(self) -> None:
        with pytest.raises(ValueError, match='é obrigatório e não pode estar vazio'):
            validar_formatacao_cpf('', 'CPF', raise_exception=True)

    @pytest.mark.parametrize('vazio', ['', None])
    def test_campo_opcional_vazio_vira_string_vazia(self, vazio: str | None) -> None:
        assert validar_formatacao_cpf(vazio, 'CPF', obrigatorio=False) == ''

    def test_acumula_o_erro_na_lista_quando_pedido(self) -> None:
        erros: list[str] = []
        assert validar_formatacao_cpf('abc', 'CPF', erros=erros) is None
        assert erros == ['O campo CPF deve conter exatamente 11 dígitos. Valor fornecido: "abc".']

    def test_dv_invalido_vira_erro_da_linha(self) -> None:
        # #17410: pontuação não é recusada, mas o dígito verificador é conferido.
        erros: list[str] = []
        assert validar_formatacao_cpf('123.456.789-00', 'CPF', erros=erros) is None
        assert erros == ['O campo CPF contém um CPF inválido (dígito verificador não confere). Valor fornecido: "123.456.789-00".']

    def test_dv_invalido_levanta_no_modo_excecao(self) -> None:
        with pytest.raises(ValueError, match='contém um CPF inválido'):
            validar_formatacao_cpf('12345678900', 'CPF', raise_exception=True)

    @pytest.mark.parametrize('valor', ['111.111.111-11', '00000000000'])
    def test_sequencia_repetida_e_recusada(self, valor: str) -> None:
        # O cálculo do DV fecha para sequências repetidas; elas são recusadas à parte.
        erros: list[str] = []
        assert validar_formatacao_cpf(valor, 'CPF', erros=erros) is None
        assert erros == [f'O campo CPF contém um CPF inválido (dígito verificador não confere). Valor fornecido: "{valor}".']


class TestValidarString:
    def test_remove_espacos_das_bordas(self) -> None:
        assert validar_string('  Ada Lovelace  ', 'Nome') == 'Ada Lovelace'

    def test_recusa_valor_acima_do_comprimento_maximo(self) -> None:
        with pytest.raises(ValueError, match='excede o comprimento máximo de 3 caracteres'):
            validar_string('abcdef', 'Sigla', max_len=3, raise_exception=True)

    def test_campo_obrigatorio_vazio_e_recusado(self) -> None:
        with pytest.raises(ValueError, match='é obrigatório e não pode estar vazio'):
            validar_string('', 'Nome', raise_exception=True)

    def test_ignorar_obrigatorios_desliga_a_exigencia(self) -> None:
        assert validar_string('', 'Nome', ignorar_obrigatorios=True, raise_exception=True) == ''


class TestValidarInteiro:
    def test_converte_string_para_inteiro(self) -> None:
        assert validar_inteiro('42', nome_campo='Carga Horária') == 42

    def test_zero_em_string_e_valor_legitimo(self) -> None:
        assert validar_inteiro('0', 0, None, 'Carga Horária') == 0

    def test_string_vazia_opcional_vira_none(self) -> None:
        assert validar_inteiro('', nome_campo='Carga Horária', ignorar_obrigatorios=True) is None

    def test_recusa_valor_nao_inteiro(self) -> None:
        with pytest.raises(ValueError, match='requer um valor inteiro válido'):
            validar_inteiro('10.5', nome_campo='Carga Horária', raise_exception=True)

    def test_reporta_a_faixa_quando_acumula_em_lista(self) -> None:
        erros: list[str] = []
        assert validar_inteiro('20', 1, 13, 'Períodos', erros=erros) is None
        assert erros == ['O campo Períodos deve estar entre 1 e 13.']

    def test_com_raise_reporta_a_faixa_e_nao_o_tipo(self) -> None:
        # Mesma mensagem do modo lista (teste acima): o número é inteiro, o problema é a faixa (#17409).
        with pytest.raises(ValueError, match='O campo Períodos deve estar entre 1 e 13'):
            validar_inteiro('20', 1, 13, 'Períodos', raise_exception=True)

    def test_inteiro_zero_obrigatorio_e_valor_legitimo(self) -> None:
        # Zero é inteiro válido, não "campo vazio" — vale também para o int já convertido (#17411).
        assert validar_inteiro(0, nome_campo='Carga Horária', raise_exception=True) == 0

    @pytest.mark.parametrize('vazio', [None, '', '   '])
    def test_vazio_obrigatorio_e_recusado(self, vazio: str | None) -> None:
        with pytest.raises(ValueError, match='é obrigatório e não pode estar vazio'):
            validar_inteiro(vazio, nome_campo='Carga Horária', raise_exception=True)

    def test_none_opcional_vira_none(self) -> None:
        assert validar_inteiro(None, nome_campo='Carga Horária', ignorar_obrigatorios=True, raise_exception=True) is None

    def test_tipo_nao_numerico_vira_mensagem_na_lista(self) -> None:
        erros: list[str] = []
        assert validar_inteiro(['1'], nome_campo='Carga Horária', erros=erros) is None  # pyright: ignore[reportArgumentType] -- tipo fora do contrato, de propósito
        assert erros == ['O campo Carga Horária requer um valor inteiro válido. "[\'1\']" foi informado.']


class TestValidarDecimal:
    def test_converte_string_para_float(self) -> None:
        assert validar_decimal('10.5', nome_campo='Nota') == 10.5

    def test_recusa_decimal_com_virgula(self) -> None:
        # Vale registrar: a planilha é pt-BR, mas só o ponto é aceito como separador.
        with pytest.raises(ValueError, match='requer um valor decimal válido'):
            validar_decimal('10,5', nome_campo='Nota', raise_exception=True)

    def test_reporta_a_faixa_quando_acumula_em_lista(self) -> None:
        erros: list[str] = []
        assert validar_decimal('99.9', 0, 10, 'Nota', erros=erros) is None
        assert erros == ['O campo Nota deve estar entre 0 e 10.']

    def test_campo_obrigatorio_vazio_e_recusado(self) -> None:
        with pytest.raises(ValueError, match='é obrigatório e não pode estar vazio'):
            validar_decimal('', nome_campo='Nota', raise_exception=True)

    def test_string_vazia_opcional_vira_none(self) -> None:
        assert validar_decimal('', nome_campo='Nota', ignorar_obrigatorios=True) is None

    def test_zero_float_obrigatorio_e_valor_legitimo(self) -> None:
        assert validar_decimal(0.0, nome_campo='Nota', raise_exception=True) == 0.0

    def test_none_obrigatorio_e_recusado(self) -> None:
        with pytest.raises(ValueError, match='é obrigatório e não pode estar vazio'):
            validar_decimal(None, nome_campo='Nota', raise_exception=True)

    def test_com_raise_reporta_a_faixa_e_nao_o_tipo(self) -> None:
        with pytest.raises(ValueError, match='O campo Nota deve estar entre 0 e 10'):
            validar_decimal('99.9', 0, 10, 'Nota', raise_exception=True)


class TestValidarData:
    def test_converte_data_no_formato_brasileiro(self) -> None:
        assert validar_data('05/02/2024', 'Data de Início') == datetime.date(2024, 2, 5)

    def test_string_vazia_vira_none(self) -> None:
        assert validar_data('', 'Data de Início') is None

    @pytest.mark.parametrize('valor', ['2024-02-05', '31/02/2024', None])
    def test_recusa_o_que_nao_for_dd_mm_yyyy(self, valor: str | None) -> None:
        with pytest.raises(ValueError, match='requer uma data válida no formato dd/mm/yyyy'):
            validar_data(valor, 'Data de Início', raise_exception=True)


class TestValidarBooleano:
    @pytest.mark.parametrize('valor', ['1', 'Sim', 'SIM', 'true', 'True'])
    def test_reconhece_as_formas_de_verdadeiro(self, valor: str) -> None:
        assert validar_booleano(valor, 'Ativo') is True

    @pytest.mark.parametrize('valor', ['0', 'Não', 'nao', 'false', 'FALSE'])
    def test_reconhece_as_formas_de_falso(self, valor: str) -> None:
        assert validar_booleano(valor, 'Ativo') is False

    def test_string_vazia_vira_none(self) -> None:
        assert validar_booleano('', 'Ativo') is None

    def test_recusa_valor_desconhecido(self) -> None:
        with pytest.raises(ValueError, match=r'requer um valor booleano \(1, Sim, 0, Não, True, False\)'):
            validar_booleano('talvez', 'Ativo', raise_exception=True)

    @pytest.mark.parametrize('valor', [True, 1])
    def test_bool_e_int_nativos_de_verdadeiro(self, valor: object) -> None:
        # A docstring anuncia aceitar ``1``/``True``: o tipo nativo vale como a string (#17411).
        assert validar_booleano(valor, 'Ativo', raise_exception=True) is True

    @pytest.mark.parametrize('valor', [False, 0])
    def test_bool_e_int_nativos_de_falso(self, valor: object) -> None:
        assert validar_booleano(valor, 'Ativo', raise_exception=True) is False

    def test_none_vira_none_como_a_string_vazia(self) -> None:
        assert validar_booleano(None, 'Ativo', raise_exception=True) is None

    @pytest.mark.parametrize('valor', [2, 1.5, ['1']])
    def test_tipo_desconhecido_vira_erro_de_validacao(self, valor: object) -> None:
        """Não-string fora do vocabulário vira mensagem da linha, não exceção de tipo que derruba o lote."""
        erros: list[str] = []
        assert validar_booleano(valor, 'Ativo', erros=erros) is None
        assert erros == ['O campo Ativo requer um valor booleano (1, Sim, 0, Não, True, False).']
        with pytest.raises(ValueError, match=r'requer um valor booleano \(1, Sim, 0, Não, True, False\)'):
            validar_booleano(valor, 'Ativo', raise_exception=True)


class TestExtrairPeriodoLetivo:
    @pytest.mark.parametrize(('mes', 'periodo'), [(1, 1), (6, 1), (7, 2), (12, 2)])
    def test_primeiro_semestre_vai_ate_junho(self, mes: int, periodo: int) -> None:
        assert extrair_periodo_letivo(datetime.date(2024, mes, 15)) == periodo


@pytest.mark.django_db
class TestExtrairAno:
    def test_devolve_o_ano_cadastrado(self) -> None:
        ano = AnoFactory(ano=2024)
        assert extrair_ano(datetime.date(2024, 5, 1)) == ano

    def test_ano_inexistente_e_erro(self) -> None:
        Ano.objects.filter(ano=1900).delete()
        with pytest.raises(ValueError, match='Nenhum objeto Ano correspondente a 1900 foi encontrado'):
            extrair_ano(datetime.date(1900, 5, 1))

    def test_sem_data_nao_consulta_nada(self) -> None:
        assert extrair_ano(None) is None


@pytest.mark.django_db
class TestValidarModelo:
    def test_busca_por_campo_numerico_e_devolve_o_id(self) -> None:
        # A docstring promete "o objeto do modelo"; o retorno real é a pk.
        ano = AnoFactory(ano=2031)
        assert validar_modelo('2031', Ano, 'Ano', campo_modelo='ano') == ano.id

    def test_busca_em_campo_de_texto_ignora_caixa(self) -> None:
        area = AreaAtuacaoFactory(nome='Ensino Superior')
        assert validar_modelo('  ensino superior  ', AreaAtuacao, 'Área', campo_modelo='nome') == area.id

    def test_percorre_relacionamento_no_campo_modelo(self) -> None:
        predio = PredioFactory()
        sigla = predio.uo.setor.sigla
        assert validar_modelo(sigla, Predio, 'Prédio', campo_modelo='uo__setor__sigla') == predio.id

    def test_registro_inexistente_vira_erro_com_o_valor_procurado(self) -> None:
        erros: list[str] = []
        assert validar_modelo('Inexistente', AreaAtuacao, 'Área', campo_modelo='nome', erros=erros) is None
        assert erros == ['O campo Área com nome "Inexistente" não foi encontrado.']

    def test_com_raise_reporta_o_registro_nao_encontrado(self) -> None:
        # Mesma mensagem do modo lista (teste acima), não a genérica 'requer um valor válido' (#17409).
        with pytest.raises(ValueError, match='O campo Área com nome "Inexistente" não foi encontrado'):
            validar_modelo('Inexistente', AreaAtuacao, 'Área', campo_modelo='nome', raise_exception=True)

    def test_forcar_criacao_cadastra_o_registro_ausente(self) -> None:
        antes = AreaAtuacao.objects.filter(nome='Área Nova').count()
        resultado = validar_modelo('Área Nova', AreaAtuacao, 'Área', campo_modelo='nome', forcar_criacao=True)
        assert AreaAtuacao.objects.filter(nome='Área Nova').count() == antes + 1
        assert resultado == AreaAtuacao.objects.get(nome='Área Nova').pk

    @pytest.mark.parametrize('nulo', ['', '0'])
    def test_valores_nulos_convencionados_viram_none(self, nulo: str) -> None:
        assert validar_modelo(nulo, AreaAtuacao, 'Área', campo_modelo='nome', obrigatorio=False) is None

    def test_campo_obrigatorio_vazio_e_recusado(self) -> None:
        with pytest.raises(ValueError, match='é obrigatório e não pode estar vazio'):
            validar_modelo('', AreaAtuacao, 'Área', campo_modelo='nome', raise_exception=True)

    def test_ignorar_obrigatorios_desliga_a_exigencia(self) -> None:
        assert validar_modelo('', AreaAtuacao, 'Área', campo_modelo='nome', ignorar_obrigatorios=True, raise_exception=True) is None

    def test_pk_ja_convertida_para_inteiro_e_aceita(self) -> None:
        # Quem já resolveu o id passa ``int``: vale como a string equivalente (#17411).
        ano = AnoFactory(ano=2032)
        assert validar_modelo(ano.id, Ano, 'Ano', raise_exception=True) == ano.id

    def test_pk_inteira_inexistente_vira_mensagem_na_lista(self) -> None:
        erros: list[str] = []
        pk = (Ano.objects.order_by('-id').values_list('id', flat=True).first() or 0) + 1000
        assert validar_modelo(pk, Ano, 'Ano', erros=erros) is None
        assert erros == [f'O campo Ano com id "{pk}" não foi encontrado.']

    def test_none_opcional_vira_none(self) -> None:
        assert validar_modelo(None, AreaAtuacao, 'Área', campo_modelo='nome', obrigatorio=False, raise_exception=True) is None

    def test_valor_ambiguo_devolve_o_primeiro_sem_avisar(self) -> None:
        """Dois registros com o mesmo nome: a busca resolve pelo menor id, calada.

        O ``except modelo.MultipleObjectsReturned`` do fim é inalcançável — quem levanta
        essa exceção é ``.get()``, e aqui a consulta é ``.filter().first()``.
        """
        predio = PredioFactory(nome='Bloco Central')
        PredioFactory(nome='Bloco Central')  # unique_together (nome, uo): precisa de outro campus
        assert validar_modelo('Bloco Central', Predio, 'Prédio', campo_modelo='nome') == predio.id
