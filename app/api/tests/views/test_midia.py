import datetime
from types import SimpleNamespace

import pytest
from django.utils import timezone

from djtools.middleware import threadlocals as tl
from eventos.enums import EtapaPeriodoSubmissao
from eventos.models import Banner, Evento, FluxoSubmissao, TipoEvento


def _criar_evento(campus, tipo_evento, nome, *, ativo=True, deferido=True, evento_id=None) -> Evento:
    kwargs = {'id': evento_id} if evento_id else {}
    return Evento.objects.create(
        nome=nome,
        apresentacao='Apresentação',
        local='Local',
        data_inicio=datetime.date.today(),
        hora_inicio=datetime.time(8, 0),
        data_fim=datetime.date.today() + datetime.timedelta(days=1),
        hora_fim=datetime.time(18, 0),
        campus=campus,
        tipo=tipo_evento,
        ativo=ativo,
        deferido=deferido,
        submetido=True,
        gera_certificado=False,
        **kwargs,
    )


@pytest.fixture
def dados_midia(servidor_a, campus_a) -> SimpleNamespace:
    tl.context.user = None
    campus = campus_a

    Banner.objects.create(
        titulo='Banner Ativo',
        tipo=Banner.INICIO,
        data_inicio=timezone.now() - datetime.timedelta(days=1),
        data_termino=timezone.now() + datetime.timedelta(days=1),
        imagem='eventos/banner/ativo.jpg',
    )
    Banner.objects.create(
        titulo='Banner Inativo',
        tipo=Banner.INICIO,
        data_inicio=timezone.now() - datetime.timedelta(days=10),
        data_termino=timezone.now() - datetime.timedelta(days=5),
        imagem='eventos/banner/inativo.jpg',
    )

    tipo_evento = TipoEvento.objects.create(descricao='Tipo Teste')

    d = SimpleNamespace(servidor_a=servidor_a)
    d.evento_ativo = _criar_evento(campus, tipo_evento, 'Evento Ativo', evento_id=5497)
    d.evento_inativo = _criar_evento(campus, tipo_evento, 'Evento Inativo', ativo=False)
    d.evento_indeferido = _criar_evento(campus, tipo_evento, 'Evento Indeferido', deferido=False)
    return d


class TestMidia:
    def test_banners_ativos(self, api_client, dados_midia):
        response = api_client.get('/api/midia/banners/', user=dados_midia.servidor_a.get_user())
        assert response.status_code == 200, f'Status: {response.status_code}, Content: {response.content}'
        items = response.json()['results']

        assert len(items) == 1, f'Esperado 1 banner, veio {len(items)}. Data: {items}'
        assert items[0]['titulo'] == 'Banner Ativo'

    def test_eventos(self, api_client, dados_midia):
        response = api_client.get('/api/midia/eventos/ativos-deferidos/', user=dados_midia.servidor_a.get_user())
        assert response.status_code == 200, f'Status: {response.status_code}, Content: {response.content}'
        items = response.json()['results']

        assert len(items) == 1, f'Esperado 1 evento, veio {len(items)}. Data: {items}'
        assert items[0]['nome'] == 'Evento Ativo'
        assert items[0]['periodo_formatado'] == dados_midia.evento_ativo.get_periodo_evento()
        assert items[0]['horario_formatado'] == '08:00 às 18:00'
        assert items[0]['campus'] == dados_midia.evento_ativo.campus.sigla
        assert items[0]['campus_id'] == dados_midia.evento_ativo.campus_id
        assert items[0]['campus_sigla'] == dados_midia.evento_ativo.campus.sigla
        assert items[0]['campus_nome'] == dados_midia.evento_ativo.campus.nome

    def test_evento_sem_data_fim_iniciado_em_data_anterior_estah_finalizado(self, api_client, dados_midia):
        Evento.objects.filter(pk=dados_midia.evento_ativo.pk).update(data_inicio=datetime.date.today() - datetime.timedelta(days=1), data_fim=None)
        FluxoSubmissao.objects.create(
            evento=dados_midia.evento_ativo,
            etapa=EtapaPeriodoSubmissao.SUBMISSAO,
            data_inicio=datetime.date.today() - datetime.timedelta(days=1),
            data_fim=datetime.date.today() + datetime.timedelta(days=1),
        )

        response = api_client.get('/api/midia/eventos/ativos-deferidos/', user=dados_midia.servidor_a.get_user())

        assert response.status_code == 200, f'Status: {response.status_code}, Content: {response.content}'
        evento = response.json()['results'][0]
        assert evento['situacao'] == 'Finalizado'
        assert evento['estah_em_periodo_inscricao'] is False
        assert evento['estah_em_periodo_submissao'] is False

    def test_evento_sem_data_fim_iniciado_hoje_estah_em_andamento(self, api_client, dados_midia):
        Evento.objects.filter(pk=dados_midia.evento_ativo.pk).update(data_fim=None)

        response = api_client.get('/api/midia/eventos/ativos-deferidos/', user=dados_midia.servidor_a.get_user())

        assert response.status_code == 200, f'Status: {response.status_code}, Content: {response.content}'
        evento = response.json()['results'][0]
        assert evento['situacao'] == 'Em andamento'
        assert evento['estah_em_periodo_inscricao'] is True
