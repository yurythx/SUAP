from datetime import datetime
from unittest.mock import MagicMock

import pytest

from documento_eletronico.assinar_documento import assinar_documento_com_senha

DATA_EMISSAO = datetime(2026, 7, 18, 17, 20, 50)


@pytest.fixture
def data_emissao_fixa(monkeypatch):
    monkeypatch.setattr('documento_eletronico.assinar_documento.get_datetime_now', MagicMock(return_value=DATA_EMISSAO))
    return DATA_EMISSAO


def montar_documento(eh_documento_pessoal, ultimo_item_do_identificador):
    documento = MagicMock()
    documento.eh_documento_pessoal = eh_documento_pessoal
    documento.setor_dono = None if eh_documento_pessoal else MagicMock()
    documento.get_sugestao_identificador_definitivo.return_value = ('DOC', 7, 2026, ultimo_item_do_identificador)
    return documento


class TestAssinarDocumentoComSenha:
    def test_documento_pessoal_recebe_ultimo_item_do_identificador_como_dono(self, data_emissao_fixa):
        documento = montar_documento(eh_documento_pessoal=True, ultimo_item_do_identificador='Discente/Maria Clara/1111179')

        assinar_documento_com_senha(documento, MagicMock(), MagicMock())

        identificador = documento.atribuir_identificador_e_processar_conteudo_final.call_args.kwargs
        assert identificador['identificador_dono_documento'] == 'Discente/Maria Clara/1111179'
        assert identificador['identificador_setor_sigla'] is None

    def test_documento_de_setor_recebe_ultimo_item_do_identificador_como_sigla(self, data_emissao_fixa):
        documento = montar_documento(eh_documento_pessoal=False, ultimo_item_do_identificador='DIAC/DG/CNAT/RE/IFRN')

        assinar_documento_com_senha(documento, MagicMock(), MagicMock())

        identificador = documento.atribuir_identificador_e_processar_conteudo_final.call_args.kwargs
        assert identificador['identificador_setor_sigla'] == 'DIAC/DG/CNAT/RE/IFRN'
        assert identificador['identificador_dono_documento'] is None

    def test_assina_e_finaliza_o_documento_com_a_data_de_emissao(self, data_emissao_fixa):
        documento = montar_documento(eh_documento_pessoal=True, ultimo_item_do_identificador='Discente/Maria Clara/1111179')
        user = MagicMock()
        papel = MagicMock()

        assinar_documento_com_senha(documento, user, papel)

        identificador = documento.atribuir_identificador_e_processar_conteudo_final.call_args.kwargs
        assert identificador['identificador_tipo_documento_sigla'] == 'DOC'
        assert identificador['identificador_numero'] == 7
        assert identificador['identificador_ano'] == 2026
        assert identificador['data_emissao'] == data_emissao_fixa
        documento.assinar_via_senha.assert_called_once_with(user, papel, data_emissao_fixa)
        documento.finalizar_documento.assert_called_once()
        documento.save.assert_called_once()
