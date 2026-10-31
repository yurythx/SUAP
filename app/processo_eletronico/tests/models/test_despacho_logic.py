"""Testes unitários para as propriedades de lógica pura do modelo Despacho (Tramite).

O modelo concreto é ``Tramite``, mas o domínio de negócio o trata como "despacho".
As propriedades testadas aqui não realizam consultas ao banco de dados.
"""

from datetime import datetime

from processo_eletronico.models import Tramite


class DespachoLogicPropertiesTestCase:
    """Testa as propriedades de lógica pura do modelo Tramite (Despacho)."""

    def setup_method(self):
        self.despacho = Tramite()
        # Pré-carrega o cache do OneToOneField para evitar acesso ao banco
        # quando a propriedade eh_tramite_externo for lida.
        Tramite._meta.get_field('tramite_barramento').set_cached_value(self.despacho, None)

    # --- eh_despacho ---

    def test_eh_despacho_sempre_verdadeiro(self):
        """eh_despacho deve sempre retornar True."""
        assert self.despacho.eh_despacho is True
        # Garantir que o valor se mantém mesmo sem nenhum campo preenchido
        assert Tramite().eh_despacho is True

    # --- foi_recebido ---

    def test_foi_recebido_com_recebido_por_id(self):
        """foi_recebido deve retornar True quando recebido_por_id está definido."""
        self.despacho.recebido_por_id = 42
        assert self.despacho.foi_recebido is True

    def test_foi_recebido_sem_recebido_por_id(self):
        """foi_recebido deve retornar False quando recebido_por_id é None."""
        self.despacho.recebido_por_id = None
        assert self.despacho.foi_recebido is False

    def test_foi_recebido_recebido_por_id_falso(self):
        """foi_recebido deve retornar False quando recebido_por_id é falsy (0)."""
        self.despacho.recebido_por_id = 0
        assert self.despacho.foi_recebido is False

    # --- recebido ---

    def test_recebido_com_data_hora_recebimento(self):
        """recebido deve retornar True quando data_hora_recebimento está preenchido."""
        self.despacho.data_hora_recebimento = datetime(2025, 1, 15, 10, 30, 0)
        assert self.despacho.recebido is True

    def test_recebido_sem_data_hora_recebimento(self):
        """recebido deve retornar False quando data_hora_recebimento é None."""
        self.despacho.data_hora_recebimento = None
        assert self.despacho.recebido is False

    # --- eh_tramite_externo ---

    def test_eh_tramite_externo_com_tramite_barramento(self):
        """eh_tramite_externo deve retornar True quando tramite_barramento está preenchido."""
        Tramite._meta.get_field('tramite_barramento').set_cached_value(self.despacho, object())
        assert self.despacho.eh_tramite_externo is True

    def test_eh_tramite_externo_sem_tramite_barramento(self):
        """eh_tramite_externo deve retornar False quando tramite_barramento é None."""
        Tramite._meta.get_field('tramite_barramento').set_cached_value(self.despacho, None)
        assert self.despacho.eh_tramite_externo is False

    # --- status ---

    def test_status_quando_recebido(self):
        """status deve retornar 'Recebido' quando o despacho foi recebido."""
        self.despacho.data_hora_recebimento = datetime(2025, 1, 15, 10, 30, 0)
        assert self.despacho.status == 'Recebido'

    def test_status_quando_aguardando_recebimento(self):
        """status deve retornar 'Aguardando recebimento' quando o despacho não foi recebido."""
        self.despacho.data_hora_recebimento = None
        assert self.despacho.status == 'Aguardando recebimento'
