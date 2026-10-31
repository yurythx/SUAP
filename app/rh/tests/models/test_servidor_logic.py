from datetime import date
from unittest.mock import MagicMock

from comum.models import DocumentoControleTipo, Municipio
from rh.models import Servidor
from rh.models.carreira.situacao import Situacao
from rh.tests.factories import ServidorFactory, SituacaoFactory


class TestEhAposentado:
    """Testes para a propriedade ``Servidor.eh_aposentado``."""

    def test_aposentado_retorna_true(self):
        """Deve retornar ``True`` quando a situação do servidor é APOSENTADOS."""
        servidor = Servidor()
        mock_situacao = MagicMock()
        mock_situacao.codigo = Situacao.APOSENTADOS
        Servidor._meta.get_field('situacao').set_cached_value(servidor, mock_situacao)
        assert servidor.eh_aposentado is True

    def test_nao_aposentado_retorna_false(self):
        """Deve retornar ``False`` quando a situação do servidor não é APOSENTADOS."""
        servidor = Servidor()
        mock_situacao = MagicMock()
        mock_situacao.codigo = Situacao.ATIVO_PERMANENTE
        Servidor._meta.get_field('situacao').set_cached_value(servidor, mock_situacao)
        assert servidor.eh_aposentado is False


class TestEhEstagiario:
    """Testes para a propriedade ``Servidor.eh_estagiario``."""

    def test_estagiario_retorna_true(self):
        """Deve retornar ``True`` quando a situação do servidor é ESTAGIARIO."""
        servidor = Servidor()
        mock_situacao = MagicMock()
        mock_situacao.codigo = Situacao.ESTAGIARIO
        Servidor._meta.get_field('situacao').set_cached_value(servidor, mock_situacao)
        assert servidor.eh_estagiario is True

    def test_estagiario_sigepe_retorna_true(self):
        """Deve retornar ``True`` quando a situação do servidor é ESTAGIARIO_SIGEPE."""
        servidor = Servidor()
        mock_situacao = MagicMock()
        mock_situacao.codigo = Situacao.ESTAGIARIO_SIGEPE
        Servidor._meta.get_field('situacao').set_cached_value(servidor, mock_situacao)
        assert servidor.eh_estagiario is True

    def test_nao_estagiario_retorna_false(self):
        """Deve retornar ``False`` quando a situação do servidor não é de estagiário."""
        servidor = Servidor()
        mock_situacao = MagicMock()
        mock_situacao.codigo = Situacao.ATIVO_PERMANENTE
        Servidor._meta.get_field('situacao').set_cached_value(servidor, mock_situacao)
        assert servidor.eh_estagiario is False


class TestExtComboTemplate:
    def test_identifica_estagiario_sem_consultar_cargo(self):
        servidor = Servidor(matricula='123')
        Servidor._meta.get_field('pessoa_fisica').set_cached_value(servidor, MagicMock(nome='Maria'))
        Servidor._meta.get_field('setor').set_cached_value(servidor, None)
        Servidor._meta.get_field('cargo_emprego').set_cached_value(servidor, None)
        Servidor._meta.get_field('situacao').set_cached_value(servidor, MagicMock(codigo=Situacao.ESTAGIARIO))
        servidor.get_foto_75x100_url = MagicMock(return_value='/foto.jpg')

        template = servidor.get_ext_combo_template()

        assert 'Estagiário' in template
        assert 'Cargo' not in template


class TestGetGrupoCargoEmprego:
    """Testes para a propriedade ``Servidor.get_grupo_cargo_emprego``."""

    def test_com_cargo_emprego_retorna_grupo(self):
        """Deve retornar o grupo_cargo_emprego quando cargo_emprego está definido."""
        servidor = Servidor()
        mock_cargo = MagicMock()
        mock_grupo = MagicMock()
        mock_cargo.grupo_cargo_emprego = mock_grupo
        Servidor._meta.get_field('cargo_emprego').set_cached_value(servidor, mock_cargo)
        assert servidor.get_grupo_cargo_emprego is mock_grupo

    def test_sem_cargo_emprego_retorna_none(self):
        """Deve retornar None quando cargo_emprego é None."""
        servidor = Servidor()
        Servidor._meta.get_field('cargo_emprego').set_cached_value(servidor, None)
        assert servidor.get_grupo_cargo_emprego is None


class TestPodeGerarCarteiraFuncional:
    """Testes para ``Servidor.pode_gerar_carteira_funcional`` (#17404)."""

    def test_cadastro_completo_na_abrangencia_pode_gerar(self) -> None:
        situacao = SituacaoFactory(codigo=Situacao.ATIVO_PERMANENTE)
        servidor = ServidorFactory(situacao=situacao)
        pessoa_fisica = servidor.pessoa_fisica
        pessoa_fisica.grupo_sanguineo = 'O'
        pessoa_fisica.fator_rh = '+'
        pessoa_fisica.nome_mae = 'Maria'
        pessoa_fisica.rg = '123456'
        pessoa_fisica.rg_orgao = 'SSP'
        pessoa_fisica.nascimento_municipio = Municipio.get_or_create('Natal', 'RN')[0]
        pessoa_fisica.nascimento_data = date(1980, 1, 1)
        pessoa_fisica.save()
        vinculo = servidor.get_vinculo()
        vinculo.foto = 'fotos/carteira.jpg'
        vinculo.save()
        # Sem o tipo de documento cadastrado não há abrangência: False, sem estourar.
        assert Servidor.objects.get(pk=servidor.pk).pode_gerar_carteira_funcional() is False

        carteira = DocumentoControleTipo.objects.create(identificador=DocumentoControleTipo.CARTEIRA_FUNCIONAL)
        carteira.abrangencia.add(situacao)

        assert Servidor.objects.get(pk=servidor.pk).pode_gerar_carteira_funcional() is True

        carteira.abrangencia.remove(situacao)
        assert Servidor.objects.get(pk=servidor.pk).pode_gerar_carteira_funcional() is False
