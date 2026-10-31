"""Tela do processo: documento digitalizado compartilhado lista quem pode visualizá-lo.

O compartilhamento trocou ``pessoa_permitida`` por ``vinculo_permitido`` e o template seguia lendo o
nome antigo, então a lista "Pode visualizar" saía vazia em silêncio (#17642).
"""

import pytest

from djtools.middleware import threadlocals as tl
from documento_eletronico.models import CompartilhamentoDocumentoDigitalizadoPessoa
from documento_eletronico.tests.factories import DocumentoDigitalizadoFactory
from processo_eletronico.models import DocumentoDigitalizadoProcesso
from processo_eletronico.tests.factories import ProcessoFactory


@pytest.mark.django_db
def test_lista_quem_pode_visualizar_documento_digitalizado(client, dois_servidores, setor_com_siorg):
    autor = dois_servidores.a.get_user()
    colaborador = dois_servidores.b
    tl.context.user = autor
    try:
        processo = ProcessoFactory(setor_criacao=setor_com_siorg, usuario_gerador=autor)
        documento = DocumentoDigitalizadoFactory(setor_dono=setor_com_siorg, usuario_criacao=autor)
        DocumentoDigitalizadoProcesso.objects.create(processo=processo, documento=documento)
        CompartilhamentoDocumentoDigitalizadoPessoa.objects.create(documento=documento, vinculo_permitido=colaborador.get_vinculo())
    finally:
        tl.context.user = None

    client.force_login(autor)
    resposta = client.get(f'/processo_eletronico/processo/{processo.pk}/')

    assert resposta.status_code == 200
    html = resposta.content.decode()
    assert 'Pode visualizar' in html
    assert colaborador.nome in html.split('Pode visualizar', 1)[1].split('</ul>', 1)[0]
