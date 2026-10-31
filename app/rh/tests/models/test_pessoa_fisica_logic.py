from datetime import date
from unittest import mock

from rh.models import PessoaFisica, Banco


class TestBancoDisplay:
    """Testes para a propriedade ``banco_display``."""

    def test_com_todos_campos_preenchidos(self):
        """Deve retornar string formatada quando todos campos estão preenchidos."""
        banco = Banco(nome='Banco do Brasil')
        banco.pk = 1
        pf = PessoaFisica(
            nome='Teste',
            pagto_banco=banco,
            pagto_agencia='1234-5',
            pagto_ccor='67890-1',
        )
        assert pf.banco_display == 'Banco do Brasil, AG: 1234-5, CC: 67890-1'

    def test_com_campos_none(self):
        """Deve lidar graciosamente com valores None sem levantar exceção."""
        pf = PessoaFisica(nome='Teste')
        assert pf.banco_display is not None


class TestCtpsDisplay:
    """Testes para a propriedade ``ctps_display``."""

    def test_com_todos_campos_preenchidos(self):
        """Deve retornar string formatada com todos os campos incluindo data."""
        pf = PessoaFisica(
            nome='Teste',
            ctps_numero='123456',
            ctps_uf='SP',
            ctps_data_prim_emprego=date(2010, 3, 15),
            ctps_serie='001',
        )
        expected = 'Número: 123456, UF: SP, Prim.Emprego: 15/03/2010, Série: 001'
        assert pf.ctps_display == expected

    def test_com_campos_none(self):
        """Deve usar strings vazias no lugar de campos None."""
        pf = PessoaFisica(nome='Teste')
        expected = 'Número: , UF: , Prim.Emprego: , Série: '
        assert pf.ctps_display == expected


class TestCnhDisplay:
    """Testes para a propriedade ``cnh_display``.

    Observação: ``cnh_emissao`` e ``cnh_validade`` usam ``or ''`` sem
    ``strftime``, portanto datas aparecem no formato ISO (``str()`` nativo).
    """

    def test_com_todos_campos_preenchidos(self):
        """Deve retornar string formatada com todos os campos."""
        pf = PessoaFisica(
            nome='Teste',
            cnh_carteira='123456',
            cnh_registro='789012',
            cnh_categoria='AB',
            cnh_emissao=date(2020, 1, 15),
            cnh_uf='SP',
            cnh_validade=date(2030, 1, 15),
        )
        expected = 'Cart: 123456, Reg: 789012, Categ: AB, Emissão: 2020-01-15, UF: SP, Validade: 2030-01-15'
        assert pf.cnh_display == expected

    def test_com_campos_none(self):
        """Deve usar strings vazias no lugar de campos None."""
        pf = PessoaFisica(nome='Teste')
        expected = 'Cart: , Reg: , Categ: , Emissão: , UF: , Validade: '
        assert pf.cnh_display == expected


class TestRgDisplay:
    """Testes para a propriedade ``rg_display``."""

    def test_com_todos_campos_preenchidos(self):
        """Deve retornar 'RG - Orgao/UF - Data' com data formatada."""
        pf = PessoaFisica(
            nome='Teste',
            rg='12.345.678-9',
            rg_orgao='SSP',
            rg_uf='SP',
            rg_data=date(2005, 6, 10),
        )
        expected = '12.345.678-9 - SSP/SP - 10/06/2005'
        assert pf.rg_display == expected

    def test_com_campos_opcionais_none(self):
        """Deve usar strings vazias para orgão/UF e data quando None."""
        pf = PessoaFisica(
            nome='Teste',
            rg='12.345.678-9',
            rg_orgao=None,
            rg_uf=None,
            rg_data=None,
        )
        expected = '12.345.678-9 - / - '
        assert pf.rg_display == expected


class TestTituloEleitoralDisplay:
    """Testes para a propriedade ``titulo_eleitoral_display``."""

    def test_com_todos_campos_preenchidos(self):
        """Deve retornar string formatada com todos os campos."""
        pf = PessoaFisica(
            nome='Teste',
            titulo_numero='123456789012',
            titulo_zona='123',
            titulo_secao='4567',
            titulo_uf='SP',
            titulo_data_emissao=date(2000, 1, 1),
        )
        expected = 'Número: 123456789012, Zona: 123, Seção: 4567, UF: SP, Emissão: 01/01/2000'
        assert pf.titulo_eleitoral_display == expected

    def test_com_campos_none(self):
        """Deve usar strings vazias no lugar de campos None."""
        pf = PessoaFisica(nome='Teste')
        expected = 'Número: , Zona: , Seção: , UF: , Emissão: '
        assert pf.titulo_eleitoral_display == expected


class TestIdade:
    """Testes para a propriedade ``idade``."""

    @mock.patch('rh.models.pessoa.pessoa_fisica.get_age', return_value=30)
    def test_com_nascimento_data(self, mock_get_age):
        """Deve retornar o resultado de ``get_age`` quando ``nascimento_data`` está preenchido."""
        pf = PessoaFisica(nome='Teste', nascimento_data=date(1994, 5, 16))
        assert pf.idade == 30
        mock_get_age.assert_called_once_with(date(1994, 5, 16))

    def test_sem_nascimento_data(self):
        """Deve retornar ``'-'`` quando ``nascimento_data`` é ``None``."""
        pf = PessoaFisica(nome='Teste')
        assert pf.idade == '-'


class TestPrimeiroUltimoNome:
    """Testes para a propriedade ``primeiro_ultimo_nome``."""

    def test_nome_unico(self):
        """Com um único nome, retorna (nome, nome)."""
        pf = PessoaFisica(nome='Maria')
        assert pf.primeiro_ultimo_nome == ('Maria', 'Maria')

    def test_dois_nomes(self):
        """Com dois nomes, retorna (primeiro, último)."""
        pf = PessoaFisica(nome='Maria Silva')
        assert pf.primeiro_ultimo_nome == ('Maria', 'Silva')

    def test_multiplos_nomes(self):
        """Com vários nomes, retorna (primeiro, último)."""
        pf = PessoaFisica(nome='Maria Joaquina da Silva')
        assert pf.primeiro_ultimo_nome == ('Maria', 'Silva')


class TestTipoSanguineo:
    """Testes para a propriedade ``tipo_sanguineo``."""

    def test_grupo_a_fator_positivo(self):
        """Deve retornar ``'A+'`` para grupo ``'A'`` e fator ``'+'``."""
        pf = PessoaFisica(nome='Teste', grupo_sanguineo='A', fator_rh='+')
        assert pf.tipo_sanguineo == 'A+'

    def test_grupo_o_fator_negativo(self):
        """Deve retornar ``'O-'`` para grupo ``'O'`` e fator ``'-'``."""
        pf = PessoaFisica(nome='Teste', grupo_sanguineo='O', fator_rh='-')
        assert pf.tipo_sanguineo == 'O-'

    def test_valores_none(self):
        """Deve concatenar os display values ``'-------'`` de cada campo quando ``None``."""
        pf = PessoaFisica(nome='Teste')
        assert pf.tipo_sanguineo == '--------------'  # '-------' + '-------' = 14 traços
