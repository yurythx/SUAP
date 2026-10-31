"""Upload manual de documento na pasta documental do aluno (#14802).

O nome do tipo (``TipoAlunoArquivo.nome``, até 120 caracteres) é copiado para o
``nome_exibicao`` e a ``descricao`` do ``AlunoArquivo``; com um tipo de nome longo o
upload estourava ``DataError`` porque esses campos eram mais curtos que o nome do tipo.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from edu.models import AlunoArquivo
from edu.tests.factories import AlunoFactory, TipoAlunoArquivoFactory
from rh.tests.factories import ServidorFactory

pytestmark = pytest.mark.django_db

PDF = b'%PDF-1.4 documento da pasta documental'


def test_upload_com_tipo_de_nome_longo_grava_o_nome_completo(client: Client, sync_permissions: None) -> None:
    user = ServidorFactory().get_user()
    user.user_permissions.add(Permission.objects.get(codename='add_alunoarquivo', content_type__app_label='edu'))
    client.force_login(user)
    aluno = AlunoFactory()
    nome_longo = 'Declaração de Comprovação de Conclusão do Ensino Médio em Escola Pública da Rede Estadual de Ensino do Rio de Janeiro'
    tipo = TipoAlunoArquivoFactory(nome=nome_longo[:120])

    resposta = client.post(
        f'/edu/upload_arquivo_unico/{aluno.pk}/',
        {'tipo': tipo.pk, 'conteudo': SimpleUploadedFile('declaracao.pdf', PDF, content_type='application/pdf')},
    )

    assert resposta.status_code == 302
    documento = AlunoArquivo.objects.get(aluno=aluno)
    assert documento.tipo == tipo
    assert documento.nome_exibicao == tipo.nome
    assert documento.descricao == tipo.nome
