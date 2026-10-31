import pytest

from rh.models import Servidor
from rh.tests.factories import ServidorFactory


@pytest.fixture
def servidores_com_vinculo(db, sync_permissions):
    """Três servidores — o mínimo para a contagem de queries provar escala com N.

    O `ServidorFactory.save` cria o `Vinculo`; antes estes testes pegavam os servidores
    que o `suap_data` deixava no banco.
    """
    return ServidorFactory.create_batch(3)


class TestGetVinculoPrefetch:
    """N+1: `get_vinculo()` deve usar o cache de `prefetch_related('vinculos')`.

    Depois que os 8 campos migraram para `comum.Vinculo`, as properties do papel
    (`email_pessoal`/`foto`/`raca`/...) leem via `get_vinculo()`. Com a impl.
    prefetch-friendly (`self.vinculos.all()`), acessar essas properties numa
    listagem prefetchada não deve gerar query por objeto.
    """

    def _ids(self, servidores):
        return [servidor.id for servidor in servidores]

    def test_prefetch_zera_queries_no_acesso_a_property(self, django_assert_num_queries, servidores_com_vinculo):
        ids = self._ids(servidores_com_vinculo)
        assert len(ids) >= 2, 'são necessários >=2 servidores com vínculo para provar a escala'
        servidores = list(Servidor.objects.filter(id__in=ids).prefetch_related('vinculos'))
        # Após o prefetch, acessar email_pessoal (property -> get_vinculo -> vinculo.email_pessoal)
        # não deve disparar NENHUMA query, independentemente do número de servidores.
        with django_assert_num_queries(0):
            for s in servidores:
                _ = s.email_pessoal

    def test_sem_prefetch_escala_com_n(self, django_assert_num_queries, servidores_com_vinculo):
        ids = self._ids(servidores_com_vinculo)
        assert len(ids) >= 2
        servidores = list(Servidor.objects.filter(id__in=ids))
        # Aquece o cache de ContentType da GenericRelation (senão o 1º acesso somaria +1 query).
        _ = servidores[0].email_pessoal
        # Sem prefetch, cada servidor dispara 1 query em get_vinculo -> escala com N (prova o N+1).
        with django_assert_num_queries(len(ids)):
            for s in servidores:
                _ = s.email_pessoal
