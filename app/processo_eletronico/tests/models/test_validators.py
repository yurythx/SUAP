"""Testes unitários para os métodos clean() dos modelos do app processo_eletronico.

Testes de lógica pura — sem acesso ao banco de dados.
"""

from unittest import mock

from django.core.exceptions import ValidationError

from processo_eletronico.models import DocumentoTextoProcesso, TipoProcesso
import pytest


class TipoProcessoCleanTestCase:
    """Testes para o método clean() de TipoProcesso."""

    @pytest.fixture(autouse=True)
    def _auto_setup(self):
        self.tipo = TipoProcesso()

    @mock.patch.object(TipoProcesso, 'niveis_acesso_permitidos', new_callable=mock.PropertyMock)
    def test_niveis_acesso_vazio_raise_validation_error(self, mock_niveis):
        """Deve levantar ValidationError quando niveis_acesso_permitidos retorna lista de keys vazia."""
        mock_niveis.return_value = ([], [])
        with pytest.raises(ValidationError):
            self.tipo.clean()

    @mock.patch.object(TipoProcesso, 'niveis_acesso_permitidos', new_callable=mock.PropertyMock)
    @mock.patch('processo_eletronico.models.format_iterable')
    def test_nivel_acesso_default_fora_das_keys_permitidas_raise_validation_error(self, mock_format_iterable, mock_niveis):
        """Deve levantar ValidationError com chave nivel_acesso_default quando
        nivel_acesso_default não está presente nas keys de niveis_acesso_permitidos."""
        mock_niveis.return_value = ([1], ['Privado'])
        mock_format_iterable.return_value = 'Privado'
        self.tipo.nivel_acesso_default = 2
        with pytest.raises(ValidationError):
            self.tipo.clean()

    @mock.patch.object(TipoProcesso, 'niveis_acesso_permitidos', new_callable=mock.PropertyMock)
    def test_nivel_acesso_default_dentro_das_keys_permitidas_sem_erro(self, mock_niveis):
        """Não deve levantar erro quando nivel_acesso_default está presente nas keys permitidas."""
        mock_niveis.return_value = ([1, 2], ['Privado', 'Público'])
        self.tipo.nivel_acesso_default = 2
        # Não deve levantar exceção
        self.tipo.clean()

    @mock.patch.object(TipoProcesso, 'niveis_acesso_permitidos', new_callable=mock.PropertyMock)
    def test_nivel_acesso_default_none_sem_erro(self, mock_niveis):
        """Não deve levantar erro quando nivel_acesso_default é None (ignorado pelo clean)."""
        mock_niveis.return_value = ([1], ['Privado'])
        self.tipo.nivel_acesso_default = None
        # Não deve levantar exceção
        self.tipo.clean()


class DocumentoTextoProcessoCleanTestCase:
    """Testes para o método clean() de DocumentoTextoProcesso."""

    @pytest.fixture(autouse=True)
    def _auto_setup(self):
        self.docproc = DocumentoTextoProcesso()
        # Usa set_cached_value para o FK documento (não tem restrição null).
        documento = mock.MagicMock()
        DocumentoTextoProcesso._meta.get_field('documento').set_cached_value(self.docproc, documento)
        self.documento = documento
        # O FK processo não permite null=True, então usamos PropertyMock
        # para substituir o descriptor e evitar acesso ao banco.
        self._patch_processo = mock.patch.object(
            DocumentoTextoProcesso,
            'processo',
            new_callable=mock.PropertyMock,
        )
        self.mock_processo = self._patch_processo.start()
        self.mock_processo.return_value = None

    def teardown_method(self):
        self._patch_processo.stop()

    def test_sem_processo_documento_nao_assinado_raise_validation_error(self):
        """Deve levantar ValidationError quando processo é None e documento
        não está assinado nem finalizado."""
        self.documento.estah_assinado = False
        self.documento.estah_finalizado = False
        with pytest.raises(ValidationError):
            self.docproc.clean()

    def test_sem_processo_documento_assinado_sem_erro(self):
        """Não deve levantar erro quando processo é None mas documento está assinado."""
        self.documento.estah_assinado = True
        self.documento.estah_finalizado = False
        self.docproc.clean()

    def test_sem_processo_documento_finalizado_sem_erro(self):
        """Não deve levantar erro quando processo é None mas documento está finalizado."""
        self.documento.estah_assinado = False
        self.documento.estah_finalizado = True
        self.docproc.clean()

    def test_com_processo_definido_sem_erro(self):
        """Não deve levantar erro quando processo está definido,
        independentemente do estado do documento."""
        self.mock_processo.return_value = mock.MagicMock()
        self.documento.estah_assinado = False
        self.documento.estah_finalizado = False
        self.docproc.clean()
