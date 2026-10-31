from rh.utils import truncar_nome_arquivo


class TestTruncarNomeArquivo:
    """Testes para rh.utils.truncar_nome_arquivo."""

    def test_nome_curto_inalterado(self):
        """Nome dentro do limite não é alterado."""
        assert truncar_nome_arquivo('documento.pdf', 200) == 'documento.pdf'

    def test_nome_longo_truncado_preservando_extensao(self):
        """Nome maior que o limite é truncado mantendo a extensão."""
        resultado = truncar_nome_arquivo('a' * 300 + '.pdf', 200)
        assert len(resultado) == 200
        assert resultado.endswith('.pdf')
        assert resultado == 'a' * 196 + '.pdf'

    def test_no_limite_exato_inalterado(self):
        """Nome com exatamente max_length caracteres não é truncado."""
        nome = 'a' * 196 + '.pdf'  # 200 chars
        assert truncar_nome_arquivo(nome, 200) == nome

    def test_sem_extensao(self):
        """Nome sem extensão é truncado para max_length."""
        resultado = truncar_nome_arquivo('x' * 300, 200)
        assert len(resultado) == 200
        assert resultado == 'x' * 200

    def test_extensao_patologica_maior_que_limite(self):
        """Extensão maior que o limite: trunca o resultado final em max_length."""
        nome = 'arquivo.' + 'e' * 300
        resultado = truncar_nome_arquivo(nome, 200)
        assert len(resultado) == 200

    def test_vazio(self):
        """Nome vazio é retornado como está (sem erro)."""
        assert truncar_nome_arquivo('', 200) == ''

    def test_unicode_respeita_limite_de_bytes(self):
        """Nome com acentos (multibyte UTF-8) é truncado por bytes, não caracteres."""
        # 'ç' ocupa 2 bytes em UTF-8: 200 'ç' = 400 bytes, acima do limite.
        resultado = truncar_nome_arquivo('ç' * 200 + '.pdf', 200)
        assert len(resultado.encode('utf-8')) <= 200
        assert resultado.endswith('.pdf')

    def test_unicode_nao_quebra_caractere(self):
        """O truncamento por bytes não deixa um caractere multibyte pela metade."""
        resultado = truncar_nome_arquivo('á' * 300, 201)
        # Decodifica sem erro = nenhum caractere foi partido ao meio.
        assert resultado == resultado.encode('utf-8').decode('utf-8')
        assert len(resultado.encode('utf-8')) <= 201

    def test_multiplos_pontos_curto_inalterado(self):
        """Nome com múltiplas extensões dentro do limite não é alterado."""
        assert truncar_nome_arquivo('backup.tar.gz', 200) == 'backup.tar.gz'

    def test_multiplos_pontos_longo_preserva_ultima_extensao(self):
        """Nome longo com múltiplos pontos: splitext preserva só a última extensão."""
        resultado = truncar_nome_arquivo('b' * 300 + '.tar.gz', 200)
        assert len(resultado.encode('utf-8')) <= 200
        assert resultado.endswith('.gz')
