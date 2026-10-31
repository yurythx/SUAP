"""Um anexo ausente no storage não pode derrubar a tela do processo.

O tamanho do arquivo é lido do storage de objetos na renderização. Quando o registro existe no
banco mas o objeto não está no bucket, a leitura falha — e, sem tratamento, o processo inteiro
responde 500 por causa de um único anexo.
"""

from rsc_tae.templatetags.rsc_tae_extras import tamanho_arquivo

INDISPONIVEL = 'arquivo indisponível'


class _ArquivoComErro:
    """Arquivo cujo ``size`` estoura, como o do storage quando o objeto não está no bucket."""

    def __init__(self, erro):
        self._erro = erro

    @property
    def size(self):
        raise self._erro


class _ClientErroDoStorage(Exception):
    """Sósia do ``botocore.exceptions.ClientError``: não é ``OSError``, e por isso escapava."""


def test_tamanho_avisa_quando_o_objeto_nao_esta_no_bucket():
    arquivo = _ArquivoComErro(FileNotFoundError('File does not exist: rsc_tae/.../anexo.pdf'))

    assert tamanho_arquivo(arquivo) == INDISPONIVEL


def test_tamanho_avisa_quando_o_storage_recusa_a_chave():
    """A 400 do ``head_object`` sobe como ``ClientError``, que não é ``OSError``."""
    arquivo = _ArquivoComErro(_ClientErroDoStorage('An error occurred (400) when calling the HeadObject operation'))

    assert tamanho_arquivo(arquivo) == INDISPONIVEL
