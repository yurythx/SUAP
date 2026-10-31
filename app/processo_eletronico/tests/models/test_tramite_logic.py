"""Testes unitários para as propriedades de lógica pura do modelo Tramite.

Propriedades testadas: hash_conteudo, conteudo, atrasado.
Nenhuma destas propriedades realiza consultas ao banco de dados.
"""

from datetime import datetime, timedelta
from unittest import mock

from documento_eletronico.utils import gerar_hash
from processo_eletronico.models import Tramite


class TramiteLogicPropertiesTestCase:
    """Testa as propriedades de lógica pura do modelo Tramite (não-DB)."""

    def setup_method(self):
        self.tramite = Tramite()
        # Pré-carrega o cache do OneToOneField para evitar acesso ao banco
        # quando a propriedade eh_tramite_externo for lida indiretamente.
        Tramite._meta.get_field('tramite_barramento').set_cached_value(self.tramite, None)

    # --- hash_conteudo ---

    def test_hash_conteudo_com_todos_campos_preenchidos(self):
        """hash_conteudo deve retornar sha512 da concatenação de
        str(id) + cabecalho + corpo + rodape quando todos os campos estão preenchidos."""
        self.tramite.id = 42
        self.tramite.despacho_cabecalho = 'Cabeçalho do despacho'
        self.tramite.despacho_corpo = 'Corpo do despacho'
        self.tramite.despacho_rodape = 'Rodapé do despacho'
        expected = gerar_hash('42Cabeçalho do despachoCorpo do despachoRodapé do despacho')
        assert self.tramite.hash_conteudo == expected

    def test_hash_conteudo_com_campos_none(self):
        """hash_conteudo deve retornar sha512 apenas do id quando os campos são None."""
        self.tramite.id = 42
        self.tramite.despacho_cabecalho = None
        self.tramite.despacho_corpo = None
        self.tramite.despacho_rodape = None
        expected = gerar_hash('42')
        assert self.tramite.hash_conteudo == expected

    def test_hash_conteudo_com_campos_vazios(self):
        """hash_conteudo deve retornar sha512 apenas do id quando os campos são strings vazias."""
        self.tramite.id = 42
        self.tramite.despacho_cabecalho = ''
        self.tramite.despacho_corpo = ''
        self.tramite.despacho_rodape = ''
        expected = gerar_hash('42')
        assert self.tramite.hash_conteudo == expected

    def test_hash_conteudo_com_id_none(self):
        """hash_conteudo deve retornar sha512 de 'None' quando id é None."""
        self.tramite.id = None
        self.tramite.despacho_cabecalho = None
        self.tramite.despacho_corpo = None
        self.tramite.despacho_rodape = None
        expected = gerar_hash('None')
        assert self.tramite.hash_conteudo == expected

    # --- conteudo ---

    def test_conteudo_com_todos_campos_preenchidos(self):
        """conteudo deve retornar str(id) + cabecalho + corpo + rodape quando todos preenchidos."""
        self.tramite.id = 42
        self.tramite.despacho_cabecalho = 'Cabeçalho'
        self.tramite.despacho_corpo = 'Corpo'
        self.tramite.despacho_rodape = 'Rodapé'
        expected = '42CabeçalhoCorpoRodapé'
        assert self.tramite.conteudo == expected

    def test_conteudo_com_campos_vazios(self):
        """conteudo deve retornar None quando os três campos são strings vazias."""
        self.tramite.id = 42
        self.tramite.despacho_cabecalho = ''
        self.tramite.despacho_corpo = ''
        self.tramite.despacho_rodape = ''
        assert self.tramite.conteudo is None

    # --- atrasado ---

    @mock.patch('processo_eletronico.models.datetime')
    def test_atrasado_quando_31_dias_atras(self, mock_datetime):
        """atrasado deve retornar True quando encaminhado há 31 dias."""
        hoje = datetime(2025, 6, 15, 12, 0, 0)
        mock_datetime.today.return_value = hoje
        self.tramite.data_hora_encaminhamento = hoje - timedelta(days=31)
        assert self.tramite.atrasado is True

    @mock.patch('processo_eletronico.models.datetime')
    def test_atrasado_quando_1_dia_atras(self, mock_datetime):
        """atrasado deve retornar False quando encaminhado há 1 dia."""
        hoje = datetime(2025, 6, 15, 12, 0, 0)
        mock_datetime.today.return_value = hoje
        self.tramite.data_hora_encaminhamento = hoje - timedelta(days=1)
        assert self.tramite.atrasado is False

    @mock.patch('processo_eletronico.models.datetime')
    def test_atrasado_quando_exatamente_30_dias_atras(self, mock_datetime):
        """atrasado deve retornar True quando encaminhado há exatos 30 dias (limite inclusivo)."""
        hoje = datetime(2025, 6, 15, 12, 0, 0)
        mock_datetime.today.return_value = hoje
        self.tramite.data_hora_encaminhamento = hoje - timedelta(days=30)
        assert self.tramite.atrasado is True

    @mock.patch('processo_eletronico.models.datetime')
    def test_atrasado_quando_29_dias_atras(self, mock_datetime):
        """atrasado deve retornar False quando encaminhado há 29 dias."""
        hoje = datetime(2025, 6, 15, 12, 0, 0)
        mock_datetime.today.return_value = hoje
        self.tramite.data_hora_encaminhamento = hoje - timedelta(days=29)
        assert self.tramite.atrasado is False


class TramiteLabelPropertiesTestCase:
    """Testa as propriedades destinatario_label e remetente_label do modelo Tramite."""

    def setup_method(self):
        self.tramite = Tramite()
        Tramite._meta.get_field('tramite_barramento').set_cached_value(self.tramite, None)

    def test_destinatario_label_com_setor(self):
        """destinatario_label deve retornar str(setor) quando destinatario_setor está definido."""
        mock_setor = mock.MagicMock()
        mock_setor.__str__ = mock.MagicMock(return_value='Setor Destino')
        Tramite._meta.get_field('destinatario_setor').set_cached_value(self.tramite, mock_setor)
        assert self.tramite.destinatario_label == 'Setor Destino'

    def test_destinatario_label_sem_setor_com_vinculo(self):
        """destinatario_label deve retornar nome_usual do vinculo quando destinatario_setor é None."""
        Tramite._meta.get_field('destinatario_setor').set_cached_value(self.tramite, None)
        mock_vinculo = mock.MagicMock()
        mock_vinculo.pessoa.nome_usual = 'João Silva'
        Tramite._meta.get_field('destinatario_vinculo').set_cached_value(self.tramite, mock_vinculo)
        assert self.tramite.destinatario_label == 'João Silva'

    def test_remetente_label_com_setor(self):
        """remetente_label deve retornar str(setor) quando remetente_setor está definido."""
        mock_setor = mock.MagicMock()
        mock_setor.__str__ = mock.MagicMock(return_value='Setor Origem')
        Tramite._meta.get_field('remetente_setor').set_cached_value(self.tramite, mock_setor)
        assert self.tramite.remetente_label == 'Setor Origem'

    def test_remetente_label_sem_setor_com_vinculo(self):
        """remetente_label deve retornar nome_usual do vinculo quando remetente_setor é None."""
        Tramite._meta.get_field('remetente_setor').set_cached_value(self.tramite, None)
        mock_vinculo = mock.MagicMock()
        mock_vinculo.nome_usual = 'Maria Souza'
        Tramite._meta.get_field('remetente_vinculo').set_cached_value(self.tramite, mock_vinculo)
        assert self.tramite.remetente_label == 'Maria Souza'
