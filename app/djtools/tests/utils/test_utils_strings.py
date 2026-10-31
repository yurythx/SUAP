from djtools.utils.strings import (
    convert_bytes_to_strb64,
    convert_strb64_to_bytes,
    eh_nome_completo,
    force_utf8_string,
    gera_nomes,
    human_str,
    insert_space,
    normalizar_token_email_conta,
    normalizar_nome_proprio,
    normalizar_termos_busca,
    replace_ignore_case_accent,
    retira_acentos,
    retira_caracteres_ocultos,
    retirar_preposicoes_nome,
    to_ascii,
    tooltip_text,
    validar_email_conta_institucional,
)


class TestEhNomeCompleto:
    def test_full_name(self):
        assert eh_nome_completo('João Silva') is True

    def test_single_word(self):
        assert eh_nome_completo('João') is False

    def test_name_with_numbers(self):
        assert eh_nome_completo('João 123') is False

    def test_triple_name(self):
        assert eh_nome_completo('Maria da Silva') is True


class TestNormalizarNomeProprio:
    def test_simple_name(self):
        assert normalizar_nome_proprio('joão silva') == 'João Silva'

    def test_with_preposition(self):
        assert normalizar_nome_proprio('maria da silva') == 'Maria da Silva'

    def test_with_roman_numeral(self):
        assert normalizar_nome_proprio('joão paulo ii') == 'João Paulo II'

    def test_with_abbreviation(self):
        assert normalizar_nome_proprio('m. silva') == 'M. Silva'

    def test_already_normalized(self):
        assert normalizar_nome_proprio('José Santos') == 'José Santos'


class TestTooltipText:
    def test_creates_span(self):
        result = tooltip_text('Texto', 'Descrição')
        assert result == '<span class="hint" aria-label="Descrição">Texto</span>'


class TestHumanStr:
    def test_none_returns_blank(self):
        assert human_str(None) == ''

    def test_none_with_blank(self):
        assert human_str(None, blank='-') == '-'

    def test_true_returns_sim(self):
        assert human_str(True) == 'Sim'

    def test_false_returns_nao(self):
        assert human_str(False) == 'Não'

    def test_string_returns_itself(self):
        assert human_str('teste') == 'teste'

    def test_date_format(self):
        from datetime import date

        assert human_str(date(2024, 1, 5)) == '05/01/2024'


class TestForceUtf8String:
    def test_string_preserved(self):
        assert force_utf8_string('hello') == 'hello'

    def test_unicode_string(self):
        assert force_utf8_string('café') == 'café'

    def test_non_string(self):
        assert force_utf8_string(42) == '42'


class TestReplaceIgnoreCaseAccent:
    def test_replace_simple(self):
        result = replace_ignore_case_accent('café com leite', 'café', 'chá')
        assert result == 'chá com leite'

    def test_replace_case_insensitive(self):
        result = replace_ignore_case_accent('Café com leite', 'café', 'chá')
        assert result == 'chá com leite'

    def test_replace_with_accent_insensitive(self):
        result = replace_ignore_case_accent('João foi à praia', 'joao', 'João')
        assert result == 'João foi à praia'

    def test_no_match_returns_original(self):
        result = replace_ignore_case_accent('hello world', 'xyz', 'abc')
        assert result == 'hello world'


class TestToAscii:
    def test_removes_accents(self):
        assert to_ascii('café') == 'cafe'

    def test_removes_cedilla(self):
        assert to_ascii('João') == 'Joao'

    def test_already_ascii(self):
        assert to_ascii('hello') == 'hello'

    def test_non_string(self):
        assert to_ascii(42) == '42'


class TestNormalizarTokenEmailConta:
    def test_remove_caracteres_especiais(self):
        assert normalizar_token_email_conta('D"Arc') == 'darc'

    def test_remove_acentos(self):
        assert normalizar_token_email_conta('José') == 'jose'


class TestValidarEmailContaInstitucional:
    def test_email_com_pontos_e_numeros(self):
        assert validar_email_conta_institucional('carlos.silva1@academico.ifrn.edu.br') is True

    def test_email_vazio(self):
        assert validar_email_conta_institucional('') is True

    def test_rejeita_aspas_no_prefixo(self):
        assert validar_email_conta_institucional('d"arc.dantas@academico.ifrn.edu.br') is False

    def test_rejeita_ponto_duplicado(self):
        assert validar_email_conta_institucional('carlos..silva@academico.ifrn.edu.br') is False


class TestNormalizarTermosBusca:
    def test_removes_prepositions(self):
        result, _removed = normalizar_termos_busca('joao da silva')
        assert result == 'joao silva'

    def test_short_words_removed(self):
        result, _removed = normalizar_termos_busca('a b c joao')
        assert result == 'joao'

    def test_prepositions_returned(self):
        _result, removed = normalizar_termos_busca('joao da silva')
        assert 'da' in removed


class TestConvertBytesStrb64:
    def test_roundtrip(self):
        original = b'hello world'
        encoded = convert_bytes_to_strb64(original)
        decoded = convert_strb64_to_bytes(encoded)
        assert decoded == original

    def test_binary_data(self):
        original = bytes(range(256))
        encoded = convert_bytes_to_strb64(original)
        decoded = convert_strb64_to_bytes(encoded)
        assert decoded == original


class TestRetiraAcentes:
    def test_removes_accents(self):
        assert retira_acentos('café') == 'cafe'

    def test_removes_tilde(self):
        assert retira_acentos('João') == 'Joao'

    def test_no_accents(self):
        assert retira_acentos('hello') == 'hello'


class TestRetiraCaracteresOcultos:
    def test_normal_text(self):
        assert retira_caracteres_ocultos('hello') == 'hello'

    def test_removes_null(self):
        assert retira_caracteres_ocultos('hel\x00lo') == 'hello'


class TestRetirarPreposicoesNome:
    def test_removes_prepositions(self):
        assert retirar_preposicoes_nome('João da Silva Santos') == 'João Silva Santos'

    def test_no_prepositions(self):
        assert retirar_preposicoes_nome('João Silva') == 'João Silva'

    def test_empty_string(self):
        assert retirar_preposicoes_nome('') == ''


class TestGeraNomes:
    def test_generates_combinations(self):
        nomes = gera_nomes('João Silva')
        assert 'JOAO SILVA' in nomes
        assert len(nomes) >= 2


class TestInsertSpace:
    def test_inserts_at_index(self):
        assert insert_space('hello', 2) == 'he llo'

    def test_index_past_end(self):
        assert insert_space('hi', 10) == 'hi'

    def test_empty_string(self):
        assert insert_space('', 0) == ''
