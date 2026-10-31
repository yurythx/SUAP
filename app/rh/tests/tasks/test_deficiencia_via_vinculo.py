import pytest

from djtools.utils import getattr_coalesce
from rh.models import Deficiencia, GrupoDeficiencia, Servidor
from rh.tasks import CAMPOS_VIA_VINCULO, perform_queryset
from rh.tests.factories import ServidorFactory


@pytest.fixture
def servidores(db, sync_permissions):
    """Três servidores com vínculo — o `ServidorFactory.save` cria o `Vinculo`.

    Antes estes testes garimpavam no banco os servidores que o `suap_data` deixava.
    """
    return ServidorFactory.create_batch(3)


@pytest.mark.usefixtures('servidores')
class TestDeficienciaViaVinculo:
    """`deficiencia` migrou de PessoaFisica para `comum.Vinculo`.

    Sem a property em `AbstractRelacionamento`, `getattr(servidor, 'deficiencia')`
    caía no `__getattr__` -> `pessoa_fisica.deficiencia` (campo removido) e virava
    `None`, fazendo o relatório de busca de servidores exibir "Nenhum" para todo
    mundo na coluna Deficiência.
    """

    def _servidor_com_vinculo(self):
        return Servidor.objects.filter(vinculos__isnull=False).distinct().first()

    def _deficiencia(self):
        grupo = GrupoDeficiencia.objects.create(codigo='01', descricao='Deficiência Física')
        return Deficiencia.objects.create(grupo_deficiencia=grupo, codigo='0101', descricao='Paraplegia')

    def test_e_property_e_nao_campo_do_servidor(self):
        assert isinstance(Servidor.deficiencia, property)
        assert 'deficiencia' not in {campo.name for campo in Servidor._meta.get_fields()}

    def test_le_a_deficiencia_do_vinculo(self):
        servidor = self._servidor_com_vinculo()
        assert servidor is not None, 'é preciso ao menos 1 servidor com vínculo'
        deficiencia = self._deficiencia()
        vinculo = servidor.get_vinculo()
        vinculo.deficiencia = deficiencia
        vinculo.save()

        assert Servidor.objects.get(pk=servidor.pk).deficiencia == deficiencia

    def test_sem_vinculo_retorna_none(self):
        servidor = Servidor.objects.filter(vinculos__isnull=True).first()
        if servidor is None:
            pytest.skip('não há servidor sem vínculo: o ServidorFactory sempre cria um')
        assert servidor.deficiencia is None

    @pytest.mark.parametrize('campo', sorted(CAMPOS_VIA_VINCULO))
    def test_perform_queryset_prefetcha_todo_campo_do_vinculo(self, campo, django_assert_num_queries):
        """Guarda o N+1 de cada campo lido pelo vínculo, um por linha do relatório.

        `email_notificacao` é o caso difícil: a property do Vinculo atravessa a GFK
        `relacionamento` e, no último fallback, o `__getattr__` do papel até pessoa_fisica.
        """
        ids = list(Servidor.objects.filter(vinculos__isnull=False).distinct().values_list('id', flat=True)[:5])
        assert len(ids) >= 2, 'são necessários >=2 servidores com vínculo para provar a escala'
        servidores = list(perform_queryset(Servidor.objects.filter(id__in=ids), [campo]))
        with django_assert_num_queries(0):
            for servidor in servidores:
                _ = getattr_coalesce(servidor, campo)
