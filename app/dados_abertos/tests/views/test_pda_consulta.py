"""O PDA é aberto a todo servidor, somente para consulta."""

import datetime

import pytest
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory
from django.urls import reverse

from comum.models import User
from dados_abertos import views
from dados_abertos.models import Acao, Etapa, PDAAcao, PlanoDadosAbertos
from rh.tests.factories import ServidorFactory

SENHA = '123'


@pytest.fixture
def cliente_servidor(client, db, sync_permissions):
    """Servidor comum, sem nenhum grupo do módulo além do ``Servidor`` que todo servidor recebe."""
    usuario = ServidorFactory().get_user()
    usuario.set_password(SENHA)
    usuario.save()
    assert client.login(username=usuario.username, password=SENHA)
    return client


@pytest.fixture
def pda(db) -> PlanoDadosAbertos:
    return PlanoDadosAbertos.objects.create(
        titulo='PDA 2026-2027',
        vigencia_inicio=datetime.date(2026, 1, 1),
        vigencia_fim=datetime.date(2027, 12, 31),
    )


def test_servidor_consulta_o_pda_sem_opcoes_de_alteracao(cliente_servidor, pda):
    """A listagem abre com o ícone de visualizar, e só com ele."""
    resposta = cliente_servidor.get(reverse('admin:dados_abertos_planodadosabertos_changelist'))

    assert resposta.status_code == 200
    html = resposta.content.decode()
    assert reverse('dados_abertos:pda_detalhe', args=[pda.pk]) in html
    assert reverse('dados_abertos:criar_versao_pda', args=[pda.pk]) not in html
    assert reverse('dados_abertos:gerar_documento_versao_pda', args=[pda.pk]) not in html
    assert cliente_servidor.get(reverse('dados_abertos:pda_detalhe', args=[pda.pk])).status_code == 200


def test_servidor_nao_marca_acao_do_checklist(cliente_servidor, pda):
    """O dashboard é visível a todos, mas o checklist só muda por quem pode alterar o PDA."""
    etapa = Etapa.objects.create(titulo='Grupo de Trabalho', ordem=1)
    acao = Acao.objects.create(etapa=etapa, titulo='Registrar portaria', ordem=1, obrigatoria=False)
    PDAAcao.objects.create(pda=pda, acao=acao)

    resposta = cliente_servidor.post(reverse('dados_abertos:toggle_acao_pda', args=[pda.pk, acao.pk]), {'concluida': 'true'})

    assert resposta.status_code == 403
    assert not PDAAcao.objects.get(pda=pda, acao=acao).concluida


def test_usuario_sem_permissao_nao_abre_o_dashboard(pda):
    """O dashboard é do servidor: quem não pode consultar o PDA não entra nem pela URL.

    A view é chamada direto porque, pelo cliente, o middleware do SUAP já barra usuário sem
    vínculo — e todo servidor ganha a permissão pelo grupo ``Servidor``.
    """
    requisicao = RequestFactory().get(reverse('dados_abertos:dashboard'))
    requisicao.user = User.objects.create_user(username='externo', password=SENHA)

    with pytest.raises(PermissionDenied):
        views.dashboard(requisicao)
