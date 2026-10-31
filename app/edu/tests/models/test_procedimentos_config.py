"""Testes unitários (sem DB) das regras de prazo de ``ConfiguracaoPedidoMatricula``.

``pode_ser_alterado``/``pode_processar`` comparam ``data_fim`` com hoje; ``is_processado``
(que toca o banco) é mockado. Nenhum teste toca o banco.
"""

import datetime
from unittest.mock import patch

from edu.models.procedimentos import ConfiguracaoPedidoMatricula


def _config(dias_para_fim):
    config = ConfiguracaoPedidoMatricula()
    config.data_fim = datetime.date.today() + datetime.timedelta(days=dias_para_fim)
    return config


def test_pode_ser_alterado_quando_prazo_em_aberto():
    assert _config(dias_para_fim=1).pode_ser_alterado() is True


def test_nao_pode_ser_alterado_apos_prazo():
    assert _config(dias_para_fim=-1).pode_ser_alterado() is False


def test_pode_processar_quando_prazo_encerrado_e_nao_processado():
    with patch.object(ConfiguracaoPedidoMatricula, 'is_processado', return_value=False):
        assert _config(dias_para_fim=-1).pode_processar() is True


def test_nao_pode_processar_se_ja_processado():
    with patch.object(ConfiguracaoPedidoMatricula, 'is_processado', return_value=True):
        assert _config(dias_para_fim=-1).pode_processar() is False


def test_nao_pode_processar_se_prazo_ainda_aberto():
    with patch.object(ConfiguracaoPedidoMatricula, 'is_processado', return_value=False):
        assert _config(dias_para_fim=1).pode_processar() is False
