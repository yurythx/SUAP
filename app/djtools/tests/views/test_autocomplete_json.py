"""Autocomplete JSON genérico (``/json/<app>/<model>/``) com o queryset do ``Vinculo`` e do ``Aluno``."""

from functools import reduce
from operator import and_

import pytest
from django.db import connection
from django.db.models import Q, QuerySet
from django.test.client import Client
from django.test.utils import CaptureQueriesContext

from comum.models import Vinculo
from comum.tests.factories import PrestadorServicoFactory
from djtools.utils import autocomplete
from djtools.utils.serialization import timeless_dump_qs
from edu.models import Aluno
from edu.tests.factories import AlunoFactory
from rh.tests.factories import ServidorFactory


@pytest.mark.django_db
def test_pagina_incompleta_de_vinculos_nao_conta_o_total_no_banco(client: Client, sync_permissions: None) -> None:
    """Página com menos itens que o tamanho da página já dá o total: sem ``COUNT(*)`` (#17680)."""
    servidor = ServidorFactory(pessoa_fisica__nome='Fulano Servidor')
    ServidorFactory(pessoa_fisica__nome='Fulano Outro Servidor')
    AlunoFactory(pessoa_fisica__nome='Fulano Aluno')
    PrestadorServicoFactory(pessoa_fisica__nome='Fulano Prestador')
    client.force_login(servidor.get_user())
    esperado = [(v.pk, str(v)) for v in Vinculo.objects.filter(search__icontains='fulano')]

    with CaptureQueriesContext(connection) as ctx:
        resposta = client.get('/json/comum/vinculo/', {'q': 'fulano', 'control': timeless_dump_qs(Vinculo.objects.all().query)})

    dados = resposta.json()
    assert [(item['id'], item['text']) for item in dados['items']] == esperado
    assert dados['total'] == len(esperado)
    assert [q['sql'] for q in ctx.captured_queries if q['sql'].startswith('SELECT COUNT(*)') and 'comum_vinculo' in q['sql']] == []
    # Medido: 38 queries com o COUNT, 37 sem (o resto é middleware e a renderização dos 4 itens).
    assert len(ctx.captured_queries) <= 37


def _get_autocomplete_vinculos(client: Client) -> tuple[list[tuple[int, str]], int]:
    """Pares ``(id, texto)`` de ``GET /json/comum/vinculo/?q=fulano`` e o número de queries da requisição."""
    with CaptureQueriesContext(connection) as ctx:
        resposta = client.get('/json/comum/vinculo/', {'q': 'fulano', 'control': timeless_dump_qs(Vinculo.objects.all().query)})
    return [(item['id'], item['text']) for item in resposta.json()['items']], len(ctx.captured_queries)


def _criar_servidor_e_aluno(sufixo: str) -> None:
    ServidorFactory(pessoa_fisica__nome=f'Fulano Servidor {sufixo}')
    AlunoFactory(pessoa_fisica__nome=f'Fulano Aluno {sufixo}')


@pytest.mark.django_db
def test_renderizacao_dos_vinculos_nao_cresce_com_a_pagina(client: Client, sync_permissions: None) -> None:
    """O rótulo de cada vínculo sai do alvo do GenericForeignKey já carregado em lote: sem N+1 (#17694)."""
    logado = ServidorFactory(pessoa_fisica__nome='Beltrano Logado')
    client.force_login(logado.get_user())
    _criar_servidor_e_aluno('0')
    _get_autocomplete_vinculos(client)  # aquecimento: caches de sessão/ContentType não entram na conta
    _, queries_com_2 = _get_autocomplete_vinculos(client)

    for sufixo in ('1', '2'):
        _criar_servidor_e_aluno(sufixo)
    itens, queries_com_6 = _get_autocomplete_vinculos(client)

    assert itens == [(v.pk, str(v)) for v in Vinculo.objects.filter(search__icontains='fulano')]
    assert len(itens) == 6
    # Medido: 20 → 41 queries de 2 para 6 vínculos (+21); com o cache do GFK e o prefetch do Servidor, 10 → 11.
    # O +1 é o mapa de setores, recarregado uma vez porque a factory criou setores novos, não por item.
    assert queries_com_6 - queries_com_2 <= 1, (queries_com_2, queries_com_6)


def _alunos_esperados(*palavras: str) -> list[int]:
    """Cada palavra no nome/busca da pessoa ou na matrícula, por nome e pk: a semântica de ``Aluno.SEARCH_FIELDS``."""
    condicoes = [Q(pessoa_fisica__search_fields_optimized__icontains=p) | Q(matricula__icontains=p) for p in palavras]
    return list(_alunos_do_widget().filter(reduce(and_, condicoes)).order_by('pessoa_fisica__nome', 'pk').values_list('pk', flat=True)[:20])


def _alunos_do_widget() -> QuerySet[Aluno]:
    """Queryset do widget com filtro próprio, que a busca (e a sonda) precisa respeitar: tira a ANA MARIA SOUZA."""
    return Aluno.objects.exclude(matricula='20180001')


# limite 1: a sonda estoura com dois resultados e a busca usa o OR entre as tabelas; no padrão, os ids da sonda (#17813)
@pytest.mark.parametrize('limite', [None, 1], ids=['ids_da_sonda', 'or_entre_tabelas'])
@pytest.mark.parametrize(
    'q',
    ['maria', '0042', 'maria 0042', 'souza 2019', 'zzzz'],
    ids=['nome_comum', 'matricula_parcial', 'nome_e_matricula', 'cruzado', 'sem_resultado'],
)
@pytest.mark.django_db
def test_aluno_por_nome_ou_matricula(client: Client, sync_permissions: None, monkeypatch: pytest.MonkeyPatch, q: str, limite: int | None) -> None:
    if limite is not None:
        monkeypatch.setattr(autocomplete, 'LIMITE_SONDA', limite)
    client.force_login(ServidorFactory(pessoa_fisica__nome='Beltrano Logado').get_user())
    for nome, matricula in [
        ('MARIA DA SILVA', '20190042'),
        ('ANA MARIA SOUZA', '20180001'),
        ('JOSÉ SOUZA', '20190777'),
        ('MÁRIA COM ACENTO', '20170042'),
        ('PEDRO LIMA', '20160099'),
        ('MARIA DA SILVA', '20150500'),  # empate no nome: a pk desempata
    ]:
        AlunoFactory(pessoa_fisica__nome=nome, matricula=matricula)

    resposta = client.get(
        '/json/edu/aluno/', {'q': q, 'control': timeless_dump_qs(_alunos_do_widget().query), 'search_fields': ','.join(Aluno.SEARCH_FIELDS)}
    )

    ids = [item['id'] for item in resposta.json()['items']]
    assert ids == _alunos_esperados(*q.split())
    assert ids or q == 'zzzz'
