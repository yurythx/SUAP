"""Consulta dos indicadores: isolamento por chefia e período das movimentações."""

from datetime import datetime

import pytest
from django.db.models import Q
from django.test import Client
from django.urls import get_resolver
from freezegun import freeze_time

from processo_eletronico.models import Processo, Tramite
from processo_eletronico.tests.factories import ProcessoFactory, TramiteFactory
from rh.models import Setor
from rh.tests.factories import ServidorFactory, ServidorFuncaoChefiaFactory, SetorFactory, SetorSiapeFactory

URL = '/processo_eletronico/processo_eletronico_numeros/'
pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf_antes_do_relogio() -> None:
    """Importa ``suap/urls.py`` antes do ``freeze_time``: sob ``FakeDate`` o django-ninja quebra o import de
    ``suap/api.py`` e o worker passa a responder ``ConfigError: Router@'' has already been attached``
    (ver ``djtools.e2e_fixtures.aquecer_urlconf``)."""
    assert get_resolver().url_patterns


def test_chefe_consulta_apenas_sua_arvore(client: Client, sync_permissions: None, setor_com_siorg: Setor) -> None:
    superior = SetorFactory()
    setor_com_siorg.superior = superior
    setor_com_siorg.save()
    filho = SetorFactory(superior=setor_com_siorg)
    neto = SetorFactory(superior=filho)
    alheio = SetorFactory()
    servidor = ServidorFactory(setor=setor_com_siorg)
    ServidorFuncaoChefiaFactory(servidor=servidor, setor=SetorSiapeFactory(), setor_suap=setor_com_siorg)
    client.force_login(servidor.get_user())

    resposta = client.get(URL)
    assert resposta.status_code == 200
    assert resposta.context['form']['setor'].value() == str(setor_com_siorg.pk)
    assert {linha['setor'].pk for linha in resposta.context['numeros_setores']} == {setor_com_siorg.pk, filho.pk, neto.pk}
    assert 'Geral por Situação' not in resposta.content.decode()
    assert URL in resposta.content.decode()  # Entrada no menu da chefia.

    resposta = client.get(URL, {'setor': filho.pk})
    assert {linha['setor'].pk for linha in resposta.context['numeros_setores']} == {filho.pk, neto.pk}
    for setor in (superior, alheio):
        resposta = client.get(URL, {'setor': setor.pk})
        assert resposta.context['form'].errors.get('setor')
        assert not resposta.context['numeros_setores']


def test_servidor_sem_chefia_nao_acessa(client: Client, sync_permissions: None) -> None:
    client.force_login(ServidorFactory().get_user())
    assert client.get(URL).status_code == 403


def test_periodo_conta_processos_distintos_nos_limites(client: Client, sync_permissions: None, setor_com_siorg: Setor) -> None:
    servidor = ServidorFactory(setor=setor_com_siorg)
    ServidorFuncaoChefiaFactory(servidor=servidor, setor=SetorSiapeFactory(), setor_suap=setor_com_siorg)
    usuario = servidor.get_user()
    processo = ProcessoFactory(setor_criacao=setor_com_siorg, usuario_gerador=usuario)
    processo.interessados.add(usuario.get_vinculo())
    for data in (datetime(2026, 8, 1), datetime(2026, 8, 31, 23, 59, 59), datetime(2026, 9, 1)):
        tramite = TramiteFactory(processo=processo, remetente_setor=setor_com_siorg, destinatario_setor=setor_com_siorg)
        Tramite.objects.filter(pk=tramite.pk).update(data_hora_encaminhamento=data)
    Processo.objects.filter(pk=processo.pk).update(data_hora_criacao=datetime(2026, 8, 1))
    client.force_login(usuario)

    resposta = client.get(URL, {'data_inicio': '01/08/2026', 'data_final': '31/08/2026'})
    assert resposta.status_code == 200
    assert not resposta.context['form'].errors
    linha = resposta.context['numeros_setores'][0]
    esperados = Tramite.objects.filter(destinatario_setor=setor_com_siorg, data_hora_encaminhamento__month=8).values('processo').distinct().count()
    assert linha['entradas'] == esperados
    assert linha['saidas'] == esperados
    assert linha['criados'] == Processo.objects.filter(pk=processo.pk).count()

    resposta = client.get(URL, {'data_inicio': '31/08/2026', 'data_final': '31/08/2026'})
    assert resposta.context['numeros_setores'][0]['entradas'] == esperados
    assert resposta.context['numeros_setores'][0]['criados'] == 0
    resposta = client.get(URL, {'data_inicio': '02/09/2026'})
    assert resposta.context['numeros_setores'][0]['entradas'] == 0
    resposta = client.get(URL, {'data_inicio': '31/08/2026', 'data_final': '01/08/2026'})
    assert resposta.context['form'].errors.get('data_final')
    assert not resposta.context['numeros_setores']


def test_superusuario_pode_selecionar_outro_setor(client: Client, sync_permissions: None) -> None:
    usuario = ServidorFactory().get_user()
    usuario.is_superuser = True
    usuario.save()
    alheio = SetorFactory()
    client.force_login(usuario)
    resposta = client.get(URL, {'setor': alheio.pk})
    assert resposta.status_code == 200
    assert {linha['setor'].pk for linha in resposta.context['numeros_setores']} == {alheio.pk}
    assert 'Geral por Situação' in resposta.content.decode()


@freeze_time('2026-03-15')
def test_painel_gerencial_consolida_periodos_sem_duplicar_processos(client: Client, sync_permissions: None, setor_com_siorg: Setor) -> None:
    servidor = ServidorFactory(setor=setor_com_siorg)
    ServidorFuncaoChefiaFactory(servidor=servidor, setor=SetorSiapeFactory(), setor_suap=setor_com_siorg)
    usuario = servidor.get_user()
    filho = SetorFactory(superior=setor_com_siorg)
    alheio = SetorFactory()
    processo = ProcessoFactory(setor_criacao=setor_com_siorg, usuario_gerador=usuario)
    processo.interessados.add(usuario.get_vinculo())
    for data in (datetime(2025, 12, 31, 23, 59, 59), datetime(2026, 1, 1), datetime(2026, 1, 31, 23, 59, 59), datetime(2026, 3, 1)):
        tramite = TramiteFactory(processo=processo, remetente_setor=setor_com_siorg, destinatario_setor=filho)
        Tramite.objects.filter(pk=tramite.pk).update(data_hora_encaminhamento=data)
    for setor in (filho, alheio):
        outro = ProcessoFactory(setor_criacao=setor_com_siorg, usuario_gerador=usuario)
        outro.interessados.add(usuario.get_vinculo())
        tramite = TramiteFactory(processo=outro, remetente_setor=setor, destinatario_setor=setor)
        Tramite.objects.filter(pk=tramite.pk).update(data_hora_encaminhamento=datetime(2026, 3, 10))
    client.force_login(usuario)
    escopo = Tramite.objects.filter(Q(remetente_setor__in=[setor_com_siorg, filho]) | Q(destinatario_setor__in=[setor_com_siorg, filho]))

    resposta = client.get(URL)
    assert resposta.status_code == 200
    assert not resposta.context['form'].errors
    indicadores = resposta.context['indicadores']
    no_ano = escopo.filter(data_hora_encaminhamento__year=2026)
    assert indicadores['resumo']['processos'] == no_ano.values('processo').distinct().count()
    assert indicadores['resumo']['tramitacoes'] == no_ano.count()
    assert [linha['rotulo'] for linha in indicadores['serie']] == ['01/2026', '02/2026', '03/2026']
    assert indicadores['serie'][1]['tramitacoes'] == 0
    assert indicadores['serie'][0]['processos'] == no_ano.filter(data_hora_encaminhamento__month=1).values('processo').distinct().count()
    assert 'grafico_tramitacao' in resposta.content.decode()

    resposta = client.get(URL, {'periodo': 'todo', 'agrupamento': 'ano'})
    indicadores = resposta.context['indicadores']
    assert [linha['rotulo'] for linha in indicadores['serie']] == ['2025', '2026']
    assert indicadores['resumo']['processos'] == escopo.values('processo').distinct().count()
    assert indicadores['resumo']['tramitacoes'] == escopo.count()
    assert indicadores['serie'][0]['tramitacoes'] == escopo.filter(data_hora_encaminhamento__year=2025).count()

    resposta = client.get(URL, {'periodo': 'todo', 'abrangencia': 'setor'})
    assert (
        resposta.context['indicadores']['resumo']['processos'] == escopo.filter(remetente_setor=setor_com_siorg).values('processo').distinct().count()
    )
    assert {linha['setor'].pk for linha in resposta.context['numeros_setores']} == {setor_com_siorg.pk}
    for periodo, esperado in (
        ('mes_atual', no_ano.filter(data_hora_encaminhamento__month=3)),
        ('mes_anterior', no_ano.filter(data_hora_encaminhamento__month=2)),
        ('ano_anterior', escopo.filter(data_hora_encaminhamento__year=2025)),
    ):
        resposta = client.get(URL, {'periodo': periodo})
        assert resposta.context['indicadores']['resumo']['tramitacoes'] == esperado.count()

    resposta = client.get(URL, {'data_inicio': '31/12/2025', 'data_final': '01/01/2026'})
    esperado = escopo.filter(data_hora_encaminhamento__gte=datetime(2025, 12, 31), data_hora_encaminhamento__lte=datetime(2026, 1, 1, 23, 59, 59))
    assert resposta.context['indicadores']['resumo']['tramitacoes'] == esperado.count()
    assert resposta.context['indicadores']['resumo']['processos'] == esperado.values('processo').distinct().count()
