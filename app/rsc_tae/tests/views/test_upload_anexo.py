"""Upload do anexo do item: nome que o storage aceita e falha de gravação que não vira 500.

O ``FileFieldPlus`` acrescenta ``-<uuid>`` ao nome, e o Django só o encurta DEPOIS de perguntar
ao storage se ele já existe (``Storage.get_available_name`` → ``head_object``). Um nome longo —
e os anexos daqui são portarias com nome extenso — chegava inteiro ao bucket e voltava como
``ClientError: 400 Bad Request``, abortando o upload.
"""

from decimal import Decimal
from unittest import mock

import pytest
from botocore.exceptions import ClientError
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile

from rsc_tae.models import (
    GrupoSaberCompetencia,
    Nivel,
    ProcessoRSCTae,
    Requisito,
    RolSaberCompetencia,
    RolSaberCompetenciaAnexo,
)
from rsc_tae.views.api import LIMITE_BYTES_SEGMENTO_STORAGE, _encurtar_nome_enviado

_PDF = b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n'


def _arquivo_pdf(nome='doc.pdf'):
    return SimpleUploadedFile(nome, _PDF, content_type='application/pdf')


def test_nome_que_ja_cabia_chega_intacto_ao_storage():
    assert _encurtar_nome_enviado('Portaria-1533-2012.pdf') == 'Portaria-1533-2012.pdf'


def test_corte_respeita_o_limite_em_bytes_com_acentuacao():
    """O limite do storage é em bytes: cada acento ocupa dois, e cortar por caractere não basta."""
    encurtado = _encurtar_nome_enviado(f'{"Designação-de-servidores-à-comissão" * 20}.pdf')

    assert len(encurtado.encode('utf-8')) <= LIMITE_BYTES_SEGMENTO_STORAGE


@pytest.mark.django_db(databases='__all__')
class TestUploadAnexoItem:
    ATORES = ('servidor_a',)

    @pytest.fixture(autouse=True)
    def _setup(self, atores):
        requisito = Requisito.objects.create(numero=91, descricao='Requisito I', descricao_curta='I', numeral_romano='I')
        grupo = GrupoSaberCompetencia.objects.create(requisito=requisito, numero=1, pontuacao_unidade=Decimal('0.500'), descricao='Grupo')
        self.item = RolSaberCompetencia.objects.create(numero=1, grupo=grupo, titulo='Item', descricao='Item', unidade_medida='unidade')
        nivel = Nivel.objects.create(nome='Nível Teste', numero_minimo_itens=0, pontuacao_minima=0)
        self.processo = ProcessoRSCTae.objects.create(vinculo=self.servidor_a.get_vinculo(), nivel_requisitado=nivel)
        self.client.login(user=self.servidor_a.get_user())

    def _upload(self, arquivo):
        return self.client.post(
            f'/rsc_tae/processo/{self.processo.id}/item/{self.item.id}/anexos/upload/',
            {'arquivo': arquivo, 'pontuacao': '1,00'},
        )

    def test_storage_nunca_e_consultado_com_uma_chave_longa_demais(self):
        """O ponto exato da falha: ``get_available_name`` consulta o storage ANTES de truncar.

        Não basta olhar o nome gravado — no sistema de arquivos dos testes o Django encurta
        sozinho depois da consulta, e o assert passaria mesmo com o bug. O que prova a correção
        é a chave com que o storage é perguntado, que em produção vira o ``head_object``.
        """
        campo = RolSaberCompetenciaAnexo._meta.get_field('arquivo')

        with mock.patch.object(default_storage, 'exists', wraps=default_storage.exists) as consulta:
            resposta = self._upload(_arquivo_pdf(f'{"Portaria-que-designa-coordenadores-de-nucleo" * 10}.pdf'))

        assert resposta.status_code == 200
        chaves = [chamada.args[0] for chamada in consulta.call_args_list]
        assert chaves, 'o storage precisa ter sido consultado para o teste dizer algo'
        assert all(len(chave) <= campo.max_length for chave in chaves)
        assert all(len(chave.rsplit('/', 1)[-1].encode('utf-8')) <= LIMITE_BYTES_SEGMENTO_STORAGE for chave in chaves)

    def test_nome_de_exibicao_preserva_o_que_o_servidor_enviou(self):
        """O corte é só da chave do storage: o nome que o servidor reconhece continua na tela."""
        self._upload(_arquivo_pdf('Portaria-1533-2012-RE.pdf'))

        assert RolSaberCompetenciaAnexo.objects.get(processo=self.processo).nome_original == 'Portaria-1533-2012-RE.pdf'

    def test_falha_do_storage_responde_502_sem_deixar_anexo_orfao(self):
        """Sem tratamento a falha vira 500 sem mensagem no AJAX e deixa a transação quebrada."""
        erro = ClientError({'Error': {'Code': '400', 'Message': 'Bad Request'}}, 'HeadObject')

        with mock.patch.object(default_storage, 'save', side_effect=erro):
            resposta = self._upload(_arquivo_pdf())

        assert resposta.status_code == 502
        assert 'Não foi possível armazenar o arquivo' in resposta.json()['msg']
        assert not RolSaberCompetenciaAnexo.objects.filter(processo=self.processo).exists()
