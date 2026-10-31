import pytest
from django.contrib import admin
from django.test import RequestFactory

from rh.admin import EstrangeiroListFilter, ServidorAdmin
from rh.enums import Nacionalidade
from rh.models import PessoaFisica, Servidor
from rh.tests.factories import ServidorFactory

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures('sync_permissions')]


def test_filtro_estrangeiro_do_servidor_usa_a_nacionalidade_da_pessoa() -> None:
    estrangeiro, brasileiro = ServidorFactory(), ServidorFactory()
    PessoaFisica.objects.filter(pk=estrangeiro.pessoa_fisica_id).update(nacionalidade=Nacionalidade.ESTRANGEIRO)
    servidores = Servidor.objects.filter(pk__in=[estrangeiro.pk, brasileiro.pk])
    model_admin = ServidorAdmin(Servidor, admin.site)

    def filtrar(valor: str) -> list[int]:
        filtro = EstrangeiroListFilter(RequestFactory().get('/'), {'estrangeiro': [valor]}, Servidor, model_admin)
        return list(filtro.queryset(None, servidores).values_list('pk', flat=True))

    assert EstrangeiroListFilter in ServidorAdmin.list_filter
    assert (filtrar('sim'), filtrar('nao')) == ([estrangeiro.pk], [brasileiro.pk])
