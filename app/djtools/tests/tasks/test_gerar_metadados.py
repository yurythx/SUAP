from io import StringIO

import pytest
from django.core.management import call_command
from django.db import DataError, IntegrityError, connection
from django.db.models import Model
from django.test.utils import CaptureQueriesContext

from djtools.management.commands import gerar_metadados
from djtools.metadados import Metadados
from djtools.models import MetadadoCampo, MetadadoChoice, MetadadoTabela, MetadadoTransicao
from edu.models import ComponenteCurricular


def _conteudo() -> list:
    return [
        sorted(M.objects.values_list(*[f.name for f in M._meta.fields if f.name != 'id']), key=repr)
        for M in (MetadadoTabela, MetadadoCampo, MetadadoChoice, MetadadoTransicao)
    ]


@pytest.mark.django_db
def test_choice_repetido_viola_chave_unica() -> None:
    MetadadoChoice.objects.create(tabela='t', coluna='c', valor='1', rotulo='A', ordem=0)
    with pytest.raises(IntegrityError):
        MetadadoChoice.objects.create(tabela='t', coluna='c', valor='1', rotulo='B', ordem=1)


@pytest.mark.django_db
def test_gerar_metadados_popula_e_e_idempotente() -> None:
    call_command('gerar_metadados', stdout=StringIO())
    assert MetadadoChoice.objects.filter(tabela='edu_componentecurricular', coluna='tipo', valor='1', rotulo='Regular').exists()
    assert MetadadoChoice.objects.filter(tabela='edu_componentecurricular', coluna='tipo').count() == len(
        ComponenteCurricular._meta.get_field('tipo').choices
    )
    assert MetadadoCampo.objects.filter(tabela='edu_componentecurricular', coluna='tipo').exists()
    assert MetadadoTabela.objects.get(tabela='auth_permission').verbose_name == 'permissão'
    assert MetadadoChoice.objects.filter(valor__isnull=True).exists()
    antes = _conteudo()
    call_command('gerar_metadados', stdout=StringIO())
    assert _conteudo() == antes


@pytest.mark.django_db
def test_join_de_choice_bool_com_cast_do_postgres() -> None:
    call_command('gerar_metadados', stdout=StringIO())
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT rotulo FROM metadados_choices WHERE tabela = 'edu_requerimentoaproveitamentoestudo' AND coluna = 'interno' AND valor = true::text"
        )
        assert cursor.fetchone() == ('Nesta instituição',)


@pytest.mark.django_db
def test_erro_num_model_nao_aborta(monkeypatch: pytest.MonkeyPatch) -> None:
    original = gerar_metadados.coletar

    def coletar_falhando(model: type[Model]) -> Metadados:
        if model is ComponenteCurricular:
            raise ValueError('quebrado')
        return original(model)

    monkeypatch.setattr(gerar_metadados, 'coletar', coletar_falhando)
    saida = StringIO()
    call_command('gerar_metadados', stdout=saida)
    assert 'edu.ComponenteCurricular: quebrado' in saida.getvalue()
    assert MetadadoTabela.objects.filter(tabela='djtools_task').exists()
    assert not MetadadoTabela.objects.filter(tabela='edu_componentecurricular').exists()


@pytest.mark.django_db
def test_regravacao_nao_carrega_linhas_nem_dispara_signals() -> None:
    call_command('gerar_metadados', stdout=StringIO())
    with CaptureQueriesContext(connection) as consultas:
        call_command('gerar_metadados', stdout=StringIO())
    sqls = [q['sql'] for q in consultas.captured_queries]
    assert any(sql.startswith('DELETE FROM "metadados_choices"') for sql in sqls)
    assert not [sql for sql in sqls if sql.startswith('SELECT') and 'metadados_' in sql]


@pytest.mark.django_db
def test_erro_de_gravacao_nao_aborta_e_preserva_conteudo_anterior(monkeypatch: pytest.MonkeyPatch) -> None:
    call_command('gerar_metadados', stdout=StringIO())
    antes = _conteudo()
    original = type(MetadadoChoice.objects).bulk_create

    def bulk_create_falhando(self, objs, *args, **kwargs):
        if self.model is MetadadoChoice:
            raise DataError('x')
        return original(self, objs, *args, **kwargs)

    monkeypatch.setattr(type(MetadadoChoice.objects), 'bulk_create', bulk_create_falhando)
    saida = StringIO()
    call_command('gerar_metadados', stdout=saida)
    assert 'Metadados não gravados: x' in saida.getvalue()
    assert _conteudo() == antes
