"""Busca do vínculo (``Vinculo.search``) pelo CPF com e sem máscara, no autocomplete e no backfill da migration 0124."""

from __future__ import annotations

import importlib
import re
from types import SimpleNamespace

import pytest
from django.apps import apps as django_apps
from django.db import connection

from comum.models import Pais, Vinculo
from djtools.utils.autocomplete import generic_search_json
from djtools.utils.serialization import timeless_dump_qs

from rh.models import PessoaFisica
from rh.tests.factories import PessoaJuridicaFactory, ServidorFactory

pytestmark = pytest.mark.django_db


def _autocomplete(q: str) -> list[int]:
    res = generic_search_json(Vinculo, q=q, search_fields=Vinculo.SEARCH_FIELDS, control=timeless_dump_qs(Vinculo.objects.all().query), page=1)
    return [item['id'] for item in res['items']]


@pytest.mark.parametrize('formato', [lambda cpf: cpf, lambda cpf: re.sub(r'\D', '', cpf)], ids=['com_mascara', 'sem_mascara'])
def test_autocomplete_acha_vinculo_pelo_cpf(sync_permissions, formato) -> None:
    servidor = ServidorFactory()

    assert _autocomplete(formato(servidor.cpf)) == [servidor.get_vinculo().pk]


def _vinculo_pf() -> Vinculo:
    return ServidorFactory().get_vinculo()


def _vinculo_pj() -> Vinculo:
    return PessoaJuridicaFactory().get_vinculo()


def _vinculo_pf_sem_cpf() -> Vinculo:
    vinculo = ServidorFactory().get_vinculo()
    PessoaFisica.objects.filter(pk=vinculo.pessoa_id).update(cpf=None, pais_origem=Pais.objects.create(codigo='011', nome='ARGENTINA'))
    return Vinculo.objects.get(pk=vinculo.pk)


@pytest.mark.parametrize('criar', [_vinculo_pf, _vinculo_pj, _vinculo_pf_sem_cpf], ids=['pf', 'pj', 'pf_sem_cpf'])
def test_backfill_anexa_documento_sem_mascara(sync_permissions, criar) -> None:
    migracao = importlib.import_module('comum.migrations.0124_vinculo_search_documento_sem_mascara')
    vinculo = criar()
    documento = vinculo.cpf_ou_cnpj_sem_mascara.upper()
    # o search como era gravado antes da 0124: sem o documento sem máscara no fim
    antigo = Vinculo._meta.get_field('search').pre_save(vinculo, add=False).removesuffix(f' {documento}')
    Vinculo.objects.filter(pk=vinculo.pk).update(search=antigo)

    migracao.anexar_documento_sem_mascara(django_apps, SimpleNamespace(connection=connection))
    depois = Vinculo.objects.get(pk=vinculo.pk).search
    migracao.anexar_documento_sem_mascara(django_apps, SimpleNamespace(connection=connection))

    assert Vinculo.objects.get(pk=vinculo.pk).search == depois, 'rodar de novo não pode mudar nada'
    if documento:
        assert _autocomplete(documento) == [vinculo.pk]
    else:
        assert depois == antigo
