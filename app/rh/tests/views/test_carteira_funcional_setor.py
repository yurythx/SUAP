"""Testes da geração de carteiras funcionais por setor (``/rh/carteira_funcional_setor/<setor>/<abrangencia>/``).

A tela do setor oferece "Gerar Carteiras Não Registradas" (``unregistered``) e "Gerar Todas as
Carteiras" (``all``). Com o modelo 2016 ativo a view não desenha o PDF: guarda os servidores
escolhidos na sessão e redireciona para ``/rh/imprimir_carteira_funcional_pdf`` — é essa lista
que os testes conferem.
"""

from __future__ import annotations

import datetime

import pytest
from django.contrib.auth.models import Permission

from comum.models import DocumentoControle, DocumentoControleTipo, Municipio, TipoCarteiraFuncional, User
from djtools.choices import SituacaoSolicitacaoDocumento
from rh.models import Servidor, Situacao
from rh.tests.factories import ServidorFactory, SetorFactory, SituacaoFactory

URL = '/rh/carteira_funcional_setor/{setor}/{abrangencia}/'
IMPRIMIR = '/rh/imprimir_carteira_funcional_pdf'


def _servidor_apto(setor, situacao) -> Servidor:
    """Servidor com tudo o que ``Servidor.pode_gerar_carteira_funcional`` exige."""
    servidor = ServidorFactory(setor=setor, situacao=situacao)
    pessoa_fisica = servidor.pessoa_fisica
    pessoa_fisica.grupo_sanguineo = 'O'
    pessoa_fisica.fator_rh = '+'
    pessoa_fisica.nome_mae = 'Maria'
    pessoa_fisica.rg = '123456'
    pessoa_fisica.rg_orgao = 'SSP'
    pessoa_fisica.nascimento_municipio = Municipio.get_or_create('Natal', 'RN')[0]
    pessoa_fisica.nascimento_data = datetime.date(1980, 1, 1)
    pessoa_fisica.save()
    vinculo = servidor.get_vinculo()
    vinculo.foto = 'fotos/carteira.jpg'
    vinculo.save()
    return Servidor.objects.get(pk=servidor.pk)


def _operador() -> User:
    """Servidor de outro setor com ``rh.pode_gerar_carteira``, relido para não herdar cache de permissão."""
    user = ServidorFactory(setor=SetorFactory(sigla='OPE')).get_user()
    user.user_permissions.add(Permission.objects.get(codename='pode_gerar_carteira', content_type__app_label='rh'))
    return User.objects.get(pk=user.pk)


@pytest.fixture
def setor_com_carteiras(sync_permissions):
    """Setor com dois servidores aptos; só o primeiro já tem carteira funcional registrada."""
    situacao = SituacaoFactory(codigo=Situacao.ATIVO_PERMANENTE)
    tipo = DocumentoControleTipo.objects.create(identificador=DocumentoControleTipo.CARTEIRA_FUNCIONAL)
    tipo.abrangencia.add(situacao)
    TipoCarteiraFuncional.objects.create(nome='Modelo 2016', template=TipoCarteiraFuncional.MODELO_2016, ativo=True)

    setor = SetorFactory(sigla='CAR')
    registrado = _servidor_apto(setor, situacao)
    sem_carteira = _servidor_apto(setor, situacao)
    # bulk_create: ``DocumentoControle.save`` exige um request no threadlocal.
    DocumentoControle.objects.bulk_create(
        [
            DocumentoControle(
                documento_tipo=tipo,
                solicitante_vinculo=registrado.get_vinculo(),
                justificativa='Carteira já emitida',
                status_solicitacao=SituacaoSolicitacaoDocumento.ATENDIDA,
                data_solicitacao=datetime.datetime.now(),
            )
        ]
    )
    return setor, registrado, sem_carteira


@pytest.mark.django_db
def test_carteiras_nao_registradas_excluem_quem_ja_tem_carteira(client, setor_com_carteiras) -> None:
    setor, _registrado, sem_carteira = setor_com_carteiras
    client.force_login(_operador())

    resposta = client.get(URL.format(setor=setor.pk, abrangencia='unregistered'))

    assert resposta.status_code == 302
    assert resposta.url == IMPRIMIR
    assert client.session['_servidores_ids'] == [sem_carteira.pk], 'a carteira foi gerada de novo para quem já tem uma registrada'


@pytest.mark.django_db
def test_todas_as_carteiras_incluem_quem_ja_tem_carteira(client, setor_com_carteiras) -> None:
    setor, registrado, sem_carteira = setor_com_carteiras
    client.force_login(_operador())

    resposta = client.get(URL.format(setor=setor.pk, abrangencia='all'))

    assert resposta.status_code == 302
    assert resposta.url == IMPRIMIR
    assert sorted(client.session['_servidores_ids']) == sorted([registrado.pk, sem_carteira.pk])
