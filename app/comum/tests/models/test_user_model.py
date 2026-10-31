from types import SimpleNamespace

import pytest
from django.contrib.auth.models import AnonymousUser

from comum.models import User


class GroupsDouble:
    def __init__(self, names=()):
        self.names = set(names)
        self._exists = False

    def filter(self, **lookups):
        if 'name__in' in lookups:
            self._exists = bool(self.names.intersection(lookups['name__in']))
        elif lookups.get('name__endswith'):
            self._exists = any(name.endswith(lookups['name__endswith']) for name in self.names)
        else:
            self._exists = False
        return self

    def all(self):
        return self

    def exists(self):
        return self._exists


@pytest.fixture(autouse=True)
def clear_user_model_caches():
    User.VINCULOS.clear()
    User.PESSOAS_FISICAS.clear()


@pytest.fixture
def user():
    return SimpleNamespace(groups=GroupsDouble(), is_superuser=False)


@pytest.fixture
def superuser():
    return SimpleNamespace(groups=GroupsDouble(), is_superuser=True)


class TestUserHasGroup:
    def test_superuser_sempre_tem_qualquer_grupo(self, superuser):
        assert User.has_group(superuser, 'GrupoInexistente')

    def test_nao_superuser_nao_tem_grupo_que_nao_possui(self, user):
        assert not User.has_group(user, 'GrupoInexistente')

    def test_retorna_true_quando_usuario_tem_grupo_por_string(self, user):
        user.groups = GroupsDouble(['GrupoTeste'])
        assert User.has_group(user, 'GrupoTeste')

    def test_retorna_true_quando_usuario_tem_um_dos_grupos_por_string_virgulada(self, user):
        user.groups = GroupsDouble(['GrupoA'])
        assert User.has_group(user, 'GrupoInexistente,GrupoA')

    def test_retorna_true_quando_usuario_tem_grupo_por_iterable(self, user):
        user.groups = GroupsDouble(['GrupoIterable'])
        assert User.has_group(user, ['GrupoIterable'])


class TestUserIsConfigurador:
    def test_usuario_em_grupo_configurador_retorna_true(self, user):
        user.groups = GroupsDouble(['Almoxarifado Configurador'])
        assert User.is_configurador(user)

    def test_usuario_sem_grupo_configurador_retorna_false(self, user):
        assert not User.is_configurador(user)


class TestUserGetTipo:
    def test_servidor_retorna_tipo_correto(self):
        user = User(eh_servidor=True)
        assert 'Servidor' in user.get_tipo()

    def test_servidor_docente_retorna_docente(self):
        user = User(eh_servidor=True, eh_docente=True)
        assert 'Docente' in user.get_tipo()

    def test_estagiario_nao_eh_exibido_como_servidor(self):
        user = User(eh_servidor=True)
        user.get_relacionamento = lambda: SimpleNamespace(eh_estagiario=True)
        assert user.get_tipo() == 'Estagiário'


class TestUserGetVinculo:
    @pytest.fixture(autouse=True)
    def _limpar_cache_global(self):
        """`User.VINCULOS`/`PESSOAS_FISICAS` são class-level. Sem teardown explícito,
        o `object()` injetado vaza para o post_save signal de outros testes (causa
        `'object' object has no attribute 'pessoa'` em paralelo no CI)."""
        yield
        User.VINCULOS.pop(1, None)
        User.PESSOAS_FISICAS.pop(1, None)

    def test_servidor_tem_vinculo(self):
        vinculo = object()
        user = User(id=1)
        User.VINCULOS[user.id] = vinculo
        assert user.get_vinculo() is vinculo

    def test_servidor_tem_profile(self):
        profile = object()
        pessoa = type('Pessoa', (), {'pessoafisica': profile})()
        vinculo = type('Vinculo', (), {'pessoa': pessoa})()
        user = User(id=1)
        User.VINCULOS[user.id] = vinculo
        assert user.get_profile() is profile


class TestUserAutenticacaoDoisFatores:
    def test_sem_autenticacao_habilitada_retorna_false(self):
        assert not User().autenticacaodoisfatores_habilitada()


class TestUserHasGroupCached:
    def test_superuser_retorna_true_ignorando_grupos(self, superuser):
        assert User.has_group_cached(superuser, 'QualquerGrupo')

    def test_nao_superuser_retorna_true_quando_tem_grupo(self):
        user = SimpleNamespace(is_superuser=False, get_groups_cached=lambda: {'GrupoCache'})
        assert User.has_group_cached(user, 'GrupoCache')


class TestAnonymousUserGrupos:
    """O usuário anônimo aceita a mesma assinatura de User.has_group/has_group_cached."""

    def test_has_group_cached_aceita_ignore_groups_if_superuser(self):
        assert AnonymousUser().has_group_cached('QualquerGrupo', ignore_groups_if_superuser=False) is False

    def test_has_group_cached_aceita_any(self):
        assert AnonymousUser().has_group_cached(['A', 'B'], any=False) is False

    def test_has_group_retorna_false(self):
        assert AnonymousUser().has_group('QualquerGrupo') is False
