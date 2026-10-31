from django.contrib import admin
from django.test import RequestFactory, SimpleTestCase

from eventos.admin import AvaliacaoTrabalhosFilter, EventoAdmin
from eventos.models import Evento


class TestAvaliacaoTrabalhosFilter(SimpleTestCase):
    def setUp(self) -> None:
        self.request = RequestFactory().get('/admin/eventos/evento/')
        self.model_admin = EventoAdmin(Evento, admin.site)

    def test_nao_altera_queryset_sem_opcao_selecionada(self) -> None:
        filtro = AvaliacaoTrabalhosFilter(self.request, {}, Evento, self.model_admin)
        queryset = Evento.objects.all()

        assert filtro.queryset(self.request, queryset) is queryset

    def test_filtra_avaliacoes_pendentes_com_exists(self) -> None:
        parametros = {'avaliacao_trabalhos': ['pendente']}
        filtro = AvaliacaoTrabalhosFilter(self.request, parametros, Evento, self.model_admin)

        queryset = filtro.queryset(self.request, Evento.objects.all())
        sql = str(queryset.query)

        assert 'EXISTS' in sql
        assert 'nota' in sql
        assert 'RDU' in sql
