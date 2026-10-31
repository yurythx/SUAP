# tests/test_crosstab_bidimensional.py
from types import SimpleNamespace

import pytest
from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test.utils import CaptureQueriesContext

from djtools.crosstab.bidimensional import TabelaBidimensional


# ----------------------------
# Infra básica “QS/Manager” em memória
# Mock simples para simular filtro por id__in
# ----------------------------
class InMemoryQS:
    def __init__(self, items):
        self._items = list(items)

    # Simula filtro por id__in
    def filter(self, **kwargs):
        if not kwargs:
            return InMemoryQS(self._items)
        if 'id__in' in kwargs:
            ids = set(kwargs['id__in'])
            return InMemoryQS([x for x in self._items if getattr(x, 'id', None) in ids])
        # aceitar filtros adicionais sem efeito (para robustez)
        return InMemoryQS(self._items)

    # Apenas devolve a própria lista (a classe genérica só itera)
    def order_by(self, *_args, **_kwargs):
        return InMemoryQS(self._items)

    # Permite: list(qs), for obj in qs, etc.
    def __iter__(self):
        return iter(self._items)

    def __len__(self):
        return len(self._items)


class InMemoryManager:
    """
    Simula um Manager/Model com .objects.filter(id__in=...).
    """

    def __init__(self, items):
        self._qs = InMemoryQS(items)

    def filter(self, **kwargs):
        return self._qs.filter(**kwargs)


# ----------------------------
# Auxiliares de rotulagem
# ----------------------------
def hlabel(o):  # horizontal
    return f'H{o.id}'


def vlabel(o):  # vertical
    return f'V{o.id}'


# ----------------------------
# Testes
# python manage.py test_suap djtools.tests.test_crosstab_bidimensional.TestCrosstabBidimensional
# ----------------------------
class TestCrosstabBidimensional:
    def setup_method(self):
        # Domínio vertical (ids 1 e 2) e horizontal (ids 10, 20, 30)
        self.v_items = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
        self.h_items = [SimpleNamespace(id=10), SimpleNamespace(id=20), SimpleNamespace(id=30)]
        self.VSRC = InMemoryManager(self.v_items)
        self.HSRC = InMemoryManager(self.h_items)

    def test_bidimensional_count_matrix_and_totals(self):
        """
        Testa tabela bidimensional com count_func simulando contagens.
        Verifica matriz de contagens e totais por linha/coluna.
        Verifica também cabeçalho e número de linhas (itens verticais + rodapé TOTAL).
        """
        # Mapa de contagens simuladas por (v_id, h_id)
        counts = {
            (1, 10): 2,
            (1, 20): 0,
            (1, 30): 5,
            (2, 10): 1,
            (2, 20): 3,
            (2, 30): 4,
        }

        def count_func(_qs, lookup):
            v_id = lookup.get('vkey')  # chave que definiremos ao instanciar
            h_id = lookup.get('hkey')
            return counts.get((v_id, h_id), 0)

        tabela = TabelaBidimensional(
            descricao='Teste VxH',
            qs=None,  # não usado quando count_func é fornecida
            vertical_key='vkey',
            vertical_source=self.VSRC,
            horizontal_key='hkey',
            horizontal_source=self.HSRC,
            vertical_label=vlabel,
            horizontal_label=hlabel,
            vertical_header_name='Categoria',
            vertical_ids=[1, 2],
            horizontal_ids=[10, 20, 30],
            count_func=count_func,
        )

        # Cabeçalho
        assert tabela.colunas == ['Categoria', 'H10', 'H20', 'H30', 'TOTAL']

        # Registros (duas linhas + rodapé TOTAL)
        assert len(tabela.registros) == 3

        # Linha 1 (V1)
        r1 = tabela.registros[0]
        # índice 0 = rótulo vertical; depois valores e por fim o total da linha
        assert r1[0] == 'V1'
        assert r1[1] == 2
        assert r1[2] == 0
        assert r1[3] == 5
        assert r1[4] == 7  # total linha

        # Linha 2 (V2)
        r2 = tabela.registros[1]
        assert r2[0] == 'V2'
        assert r2[1] == 1
        assert r2[2] == 3
        assert r2[3] == 4
        assert r2[4] == 8  # total linha

        # Rodapé TOTAL
        rT = tabela.registros[2]
        assert rT[0] == 'TOTAL'
        # totais por coluna horizontal
        assert rT[1] == 3  # 2+1
        assert rT[2] == 3  # 0+3
        assert rT[3] == 9  # 5+4
        assert rT[4] == 15  # total geral

    def test_bidimensional_with_not_identified_row(self):
        """
        Testa tabela bidimensional com linha "Não identificado"
        (vertical_key IS NULL) e contagens simuladas.
        Verifica matriz de contagens e totais por linha/coluna.
        Verifica também cabeçalho e número de linhas (itens verticais + NI + rodapé TOTAL).

        """
        # Considera-se uma linha adicional com vertical_key IS NULL
        counts = {
            (1, 10): 1,
            (1, 20): 1,
            (1, 30): 1,
            (2, 10): 0,
            (2, 20): 2,
            (2, 30): 3,
            ('__NULL__', 10): 5,
            ('__NULL__', 20): 0,
            ('__NULL__', 30): 1,
        }

        def count_func(_qs, lookup):
            if lookup.get('vkey__isnull'):
                v = '__NULL__'
            else:
                v = lookup.get('vkey')
            h = lookup.get('hkey')
            return counts.get((v, h), 0)

        tabela = TabelaBidimensional(
            descricao='VxH com NULL',
            qs=None,
            vertical_key='vkey',
            vertical_source=self.VSRC,
            horizontal_key='hkey',
            horizontal_source=self.HSRC,
            vertical_ids=[1, 2],
            horizontal_ids=[10, 20, 30],
            vertical_include_null_value=True,
            count_func=count_func,
        )

        # Linhas: V1, V2, "Não identificado", TOTAL
        assert len(tabela.registros) == 4

        r_ni = tabela.registros[2]
        assert r_ni[0] == 'Não identificado'
        assert r_ni[1] == 5
        assert r_ni[2] == 0
        assert r_ni[3] == 1
        # total da linha NI
        assert r_ni[4] == r_ni[1] + r_ni[2] + r_ni[3]

        # Rodapé total = soma de V1, V2 e NI
        rT = tabela.registros[3]
        assert rT[1] == 1 + 0 + 5  # col H10
        assert rT[2] == 1 + 2 + 0  # col H20
        assert rT[3] == 1 + 3 + 1  # col H30
        assert rT[4] == rT[1] + rT[2] + rT[3]

    def test_unidimensional_with_extra_columns(self):
        """
        Testa tabela unidimensional (sem eixo horizontal) com colunas extras
        e contagens simuladas.
        Verifica cabeçalho, número de linhas (itens verticais, sem rodapé TOTAL)
        e valores por linha.
        """
        # Vertical de 2 itens, sem eixo horizontal
        v_items = [
            SimpleNamespace(id=1, codigo='C1', desc='Curso 1', campus='UO A', mod='Presencial'),
            SimpleNamespace(id=2, codigo='C2', desc='Curso 2', campus='UO B', mod='EAD'),
        ]
        VSRC = InMemoryManager(v_items)

        counts = {1: 7, 2: 0}

        def count_func(_qs, lookup):
            v_id = lookup.get('vkey')
            return counts.get(v_id, 0)

        tabela = TabelaBidimensional(
            descricao='Unidimensional',
            qs=None,
            vertical_key='vkey',
            vertical_source=VSRC,
            horizontal_key=None,
            horizontal_source=None,
            vertical_ids=[1, 2],
            uni_extra_columns=[
                ('Código', lambda o: o.codigo),
                ('Descrição', lambda o: o.desc),
                ('Câmpus', lambda o: o.campus),
                ('Modalidade', lambda o: o.mod),
            ],
            count_func=count_func,
        )

        # Cabeçalho
        assert tabela.colunas == ['Código', 'Descrição', 'Câmpus', 'Modalidade', 'QTD']

        # Linhas (sem rodapé total no modo unidimensional)
        assert len(tabela.registros) == 2
        r1 = tabela.registros[0]
        assert r1[0] == 'C1'
        assert r1[1] == 'Curso 1'
        assert r1[2] == 'UO A'
        assert r1[3] == 'Presencial'
        assert r1[4] == 7

        r2 = tabela.registros[1]
        assert r2[0] == 'C2'
        assert r2[1] == 'Curso 2'
        assert r2[2] == 'UO B'
        assert r2[3] == 'EAD'
        assert r2[4] == 0


@pytest.mark.django_db
class CrosstabBidimensionalAggDBTest:
    """
    Exercita o caminho PADRÃO (sem count_func): a tabela conta direto sobre um
    QuerySet real, agregando em UMA query (GROUP BY) em vez de um .count() por
    célula. Usa admin.LogEntry como tabela de fatos por ter dois FKs
    (user, content_type) — sendo content_type anulável, cobre também a linha
    "Não identificado". O Meta.ordering do LogEntry ('-action_time') garante que
    o QuerySet chega ordenado, exercitando o .order_by() que limpa a ordenação
    antes do GROUP BY (sem ele, o Django fragmentaria as contagens).
    """

    def _setup_fatos(self):
        User = get_user_model()
        u1 = User.objects.create(username='cross_u1')
        u2 = User.objects.create(username='cross_u2')
        ct_user = ContentType.objects.get_for_model(User)
        ct_le = ContentType.objects.get_for_model(LogEntry)

        # (user, content_type) -> quantidade de LogEntry; None = content_type nulo
        plano = {
            (u1, ct_user): 2,
            (u1, ct_le): 1,
            (u2, ct_user): 3,
            (u2, None): 4,  # alimenta a linha "Não identificado" (content_type IS NULL)
        }
        for (user, ct), qtd in plano.items():
            for _ in range(qtd):
                LogEntry.objects.create(user=user, content_type=ct, object_id='1', object_repr='x', action_flag=1, change_message='')
        return [u1, u2], [ct_user, ct_le]

    def _build(self):
        usuarios, cts = self._setup_fatos()
        # escopado aos usuários criados aqui (hermético: o banco pode conter outros
        # LogEntry de fixtures/testes anteriores). .filter() preserva o Meta.ordering
        # '-action_time', então o caminho do order_by() continua exercitado.
        qs = LogEntry.objects.filter(user__in=usuarios)
        tabela = TabelaBidimensional(
            descricao='LogEntry por content_type x user',
            qs=qs,
            vertical_key='content_type__id',
            vertical_source=ContentType,
            horizontal_key='user__id',
            horizontal_source=get_user_model(),
            vertical_include_null_value=True,
        )
        return tabela, qs, usuarios, cts

    def test_agregacao_bate_com_contagem_por_celula(self):
        """
        A saída agregada (GROUP BY) deve bater com as contagens por célula da
        semântica antiga: total geral, totais por coluna (user) e totais por
        linha (content_type + linha NULL). Comparações por multiconjunto, então
        independem da ordenação das dimensões.
        """
        tabela, qs, usuarios, cts = self._build()

        n_cols = len(tabela.colunas) - 2  # exclui rótulo vertical e coluna TOTAL
        total_key = n_cols + 1

        footer = tabela.registros[-1]
        assert footer[0] == 'TOTAL'

        # total geral
        assert footer[total_key] == qs.count()

        # totais por coluna (um por user presente)
        col_totals = sorted(footer[i] for i in range(1, n_cols + 1))
        esperado_cols = sorted(qs.filter(user=u).count() for u in usuarios)
        assert col_totals == esperado_cols

        # totais por linha (content_type + linha "Não identificado")
        row_totals = sorted(r[total_key] for r in tabela.registros[:-1])
        esperado_rows = sorted([qs.filter(content_type=ct).count() for ct in cts] + [qs.filter(content_type__isnull=True).count()])
        assert row_totals == esperado_rows

    def test_linha_nao_identificado_presente_e_correta(self):
        """A linha de content_type IS NULL deve aparecer com a contagem certa."""
        tabela, qs, _usuarios, _cts = self._build()
        linhas_ni = [r for r in tabela.registros if r.get(0) == 'Não identificado']
        assert len(linhas_ni) == 1
        # u2 tem 4 LogEntry sem content_type
        total_nulos = qs.filter(content_type__isnull=True).count()
        assert total_nulos == 4
        # último valor numérico da linha é o total da linha
        r_ni = linhas_ni[0]
        total_linha = r_ni[max(k for k in r_ni if isinstance(k, int))]
        assert total_linha == total_nulos

    def test_sem_n_mais_1_numero_de_queries_constante(self):
        """
        Regressão do N+1: montar a tabela faz um número PEQUENO e constante de
        queries (agregação única), não O(linhas x colunas) counts.
        """
        # popula os fatos primeiro; medimos apenas as queries da MONTAGEM da tabela.
        usuarios, _cts = self._setup_fatos()
        with CaptureQueriesContext(connection) as ctx_montagem:
            qs = LogEntry.objects.filter(user__in=usuarios)
            TabelaBidimensional(
                descricao='x',
                qs=qs,
                vertical_key='content_type__id',
                vertical_source=ContentType,
                horizontal_key='user__id',
                horizontal_source=get_user_model(),
                vertical_include_null_value=True,
            )
        assert len(ctx_montagem.captured_queries) <= 5, [q['sql'] for q in ctx_montagem.captured_queries]
