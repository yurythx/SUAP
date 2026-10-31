"""Deferimento de abertura extemporânea do Censo (``AberturaExtemporanea.deferir``)."""

import pytest

from comum.models import Configuracao
from edu.models import AberturaExtemporanea, ConfiguracaoAberturaExtemporanea


@pytest.mark.django_db
def test_deferir_sem_sigla_da_instituicao_falha_com_mensagem_clara() -> None:
    ConfiguracaoAberturaExtemporanea.objects.create(
        modelo_requerimento='modelo.docx', ativo=True, tipo_modelo=ConfiguracaoAberturaExtemporanea.TIPO_MULTIPLUS_CAMPI
    )
    Configuracao.objects.filter(app='comum', chave='instituicao_sigla').delete()
    Configuracao.clear_cache()
    abertura = AberturaExtemporanea(campi='CP1: 10')

    # A sigla monta o #EMAIL_CAMPUS# do requerimento assinado: vazia, sairia "gabin.x@.edu.br".
    with pytest.raises(Exception, match='instituicao_sigla'):
        abertura.deferir(user=None, id_certificado=None, senha_certificado=None)
