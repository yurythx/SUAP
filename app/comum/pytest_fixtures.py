import logging
from unittest import mock

import pytest
from django.apps import apps
from django.conf import settings
from django.contrib.auth.models import Group
from django.core.management import call_command


logger = logging.getLogger(__name__)
_MISSING = object()

Municipio = apps.get_model('comum', 'Municipio')
Configuracao = apps.get_model('comum', 'Configuracao')
PrestadorServico = apps.get_model('comum', 'PrestadorServico')
PessoaFisica = apps.get_model('rh', 'PessoaFisica')
PessoaJuridica = apps.get_model('rh', 'PessoaJuridica')
Setor = apps.get_model('rh', 'Setor')
Servidor = apps.get_model('rh', 'Servidor')
UnidadeOrganizacional = apps.get_model('rh', 'UnidadeOrganizacional')
TipoUnidadeOrganizacional = apps.get_model('rh', 'TipoUnidadeOrganizacional')
Situacao = apps.get_model('rh', 'Situacao')
GrupoCargoEmprego = apps.get_model('rh', 'GrupoCargoEmprego')
CargoEmprego = apps.get_model('rh', 'CargoEmprego')
JornadaTrabalho = apps.get_model('rh', 'JornadaTrabalho')
Ano = apps.get_model('comum', 'Ano')
Turno = apps.get_model('edu', 'Turno')
Titulacao = apps.get_model('rh', 'Titulacao')
Modalidade = apps.get_model('edu', 'Modalidade')
NivelEnsino = apps.get_model('edu', 'NivelEnsino')
ConfiguracaoAvaliacao = apps.get_model('edu', 'ConfiguracaoAvaliacao')
ItemConfiguracaoAvaliacao = apps.get_model('edu', 'ItemConfiguracaoAvaliacao')
SituacaoMatricula = apps.get_model('edu', 'SituacaoMatricula')
SituacaoMatriculaPeriodo = apps.get_model('edu', 'SituacaoMatriculaPeriodo')


def adaptar_suap_client(client):
    if getattr(client, '_suap_adapted', False):
        return client

    client.user = None
    django_login = client.login
    django_logout = client.logout
    django_get = client.get
    django_post = client.post

    def login(**credentials):
        user = credentials.pop('user', None)
        if user:
            client.user = user
            from comum.utils import tl

            tl.context.user = user
            client.force_login(user)
            return True

        logged = django_login(**credentials)
        if logged:
            username = credentials.get('username')
            if username:
                User = apps.get_model('comum', 'User')
                client.user = User.objects.filter(username=username).first()
        return logged

    def logout():
        client.user = None
        return django_logout()

    def get(path, data=None, silent=False, *args, **kwargs):
        return django_get(path, data, *args, **kwargs)

    def post(path, data=None, silent=False, *args, **kwargs):
        if data is None:
            data = {}
        kwargs.setdefault('HTTP_REFERER', 'http://testserver/')
        response = django_post(path, data, *args, **kwargs)
        lines = response.content.decode('utf-8').split('\n')
        from django.core.management.color import color_style

        for idx, line in enumerate(lines):
            if line.find('errorlist') > 0:
                line_before = lines[idx - 1].strip()
                error_msg = line[line.find('<li') + 4 : line.find('</li')]
                msg = f'[WARNING FORM at {path}] {line_before}: {error_msg}'
                response.error = color_style().SQL_KEYWORD(msg)
                if not silent:
                    logger.error(response.error)
        return response

    client.login = login
    client.logout = logout
    client.get = get
    client.post = post
    client._suap_adapted = True
    return client


def cadastrar_setor(sigla, superior=None, codigo=None):
    qs = Setor.objects.filter(sigla=sigla, codigo=None)
    if qs.exists():
        setor = qs[0]
    else:
        setor = Setor.objects.create(sigla=sigla, nome=sigla, superior=superior)
    superior_siap = None
    if superior:
        qs = Setor.objects.filter(sigla=superior.sigla, codigo__isnull=False)
        if qs.exists():
            superior_siap = qs[0]
    qs = Setor.objects.filter(sigla=sigla, codigo=codigo or sigla)
    if qs.exists():
        setor_siap = qs[0]
    else:
        setor_siap = Setor.objects.create(sigla=sigla, nome=sigla, superior=superior_siap, codigo=codigo or sigla)

    if codigo:
        qs = UnidadeOrganizacional.objects.filter(codigo_ug=codigo)
        if qs.exists():
            campus = qs[0]
        else:
            campus = UnidadeOrganizacional.objects.suap().create(
                setor=setor, codigo_ug=codigo, nome=sigla, sigla=sigla, codigo_protocolo=f'3{setor.id}'.zfill(5)
            )
        qs = UnidadeOrganizacional.objects.filter(setor=setor_siap, equivalente=campus)
        if not qs.exists():
            UnidadeOrganizacional.objects.create(setor=setor_siap, equivalente=campus, codigo_protocolo=f'3{setor_siap.id}'.zfill(5))
    setor.uo = setor._get_uo()
    setor.codigo_siorg = f'1{setor.id}'.zfill(6)
    setor.save(update_fields=['uo'])
    setor_siap.codigo_siorg = f'2{setor.id}'.zfill(6)
    setor_siap.uo = setor_siap._get_uo()
    setor_siap.save(update_fields=['uo'])
    return setor, setor_siap


def _definir_endereco(uo, *endereco):
    for dictionary in endereco:
        for key in dictionary:
            setattr(uo, key, dictionary[key])
    uo.save()


def _override_settings_for_fixture(request, **overrides):
    previous_values = {name: getattr(settings, name, _MISSING) for name in overrides}
    for name, value in overrides.items():
        setattr(settings, name, value)

    def restore():
        for name, value in previous_values.items():
            if value is _MISSING:
                delattr(settings, name)
            else:
                setattr(settings, name, value)

    request.addfinalizer(restore)


@pytest.fixture(scope='session')
def _permissions_synced(django_db_setup, django_db_blocker):
    """Roda `sync_permissions` UMA vez por sessão (o comando custa dezenas de segundos).

    Era o maior gargalo da suíte por ser class-scoped (rodava ~uma vez por classe).
    Os grupos/permissões são globais e idempotentes e os dados são commitados
    (`django_db_blocker.unblock`), então persistem por toda a sessão.

    IMPORTANTE: este fixture NÃO é importado pelos conftests das apps — fica
    disponível só via `pytest_plugins` no conftest raiz, logo é registrado uma
    única vez. Se fosse importado em cada conftest, o pytest o re-registraria por
    namespace e ele rodaria uma vez por app (não uma vez por sessão)."""
    with django_db_blocker.unblock():
        call_command('sync_permissions', verbosity=0)


@pytest.fixture(scope='class')
def sync_permissions(request, _permissions_synced):
    # Wrapper fino que os conftests das apps importam. O trabalho pesado roda
    # uma única vez por sessão (_permissions_synced); aqui só garantimos
    # DEBUG=True por classe — barato e restaurado ao fim dela.
    _override_settings_for_fixture(request, DEBUG=True)


@pytest.fixture
def suap_client():
    """Wrapper SUAP sobre `django.test.Client`.

    NÃO depende do fixture `client` do pytest-django: isso evitaria o conftest
    desses apps poder sobrescrever `client` (ex.: `def client(suap_client, ...)`)
    sem entrar em recursão de resolução de fixture.
    """
    from django.test import Client

    return adaptar_suap_client(Client())


def authenticate_side_effect(request, key, *args):
    user = request.META.get('user')
    token = None
    if user and user.is_authenticated:
        request.user = user
        token = 'token'
    application = request.META.get('application')
    if application:
        request.application = application
        token = 'application'
    return token


@pytest.fixture(scope='class')
def api_auth_mocks():
    auth_patcher = mock.patch('djtools.ninja.auth.SessionAuth.authenticate', side_effect=authenticate_side_effect)
    trusted_auth_patcher = mock.patch('djtools.ninja.auth.TrustedAppAuth.authenticate', side_effect=authenticate_side_effect)
    auth_patcher.start()
    trusted_auth_patcher.start()
    yield
    trusted_auth_patcher.stop()
    auth_patcher.stop()


def get_text_array(texto):
    if isinstance(texto, str):
        return [texto]
    if not hasattr(texto, '__iter__'):
        return [texto]
    return texto


def assert_no_validation_errors(response, url=None, data=None, content=None):
    errors = []
    erro_note = ''
    for line in response.content.decode().split('\n'):
        if line.find('"errorlist"') > 0:
            errors.append(line[line.find('<li') + 4 : line.find('</li')])
        elif line.find(' errornote ') > 0 or erro_note:
            index_inicial = line.find('<p')
            index_final = line.find('</p>')
            if index_final > 0 and index_inicial < index_final:
                erro_note += line[index_inicial:index_final]
                break
            elif index_final > 0 and (index_inicial < 0 or index_inicial > index_final):
                erro_note += line[: index_final + 4]
                break
            elif index_inicial > 0 > index_final:
                erro_note += line[index_inicial:]
            elif index_inicial < 0 and index_final < 0 and erro_note:
                erro_note += line[:]
    if erro_note:
        errors.append(erro_note)
    if errors:
        file = open('/tmp/testcase.html', 'w')
        file.write(response.content.decode())
        file.close()
        raise Exception('Erros apresentados no form:\n' + ('\n'.join(errors)) + f'\n{url}\n{data}\n{content}')
    return True


def assert_redirects(response, expected_url, status_code=302):
    assert response.status_code == status_code
    assert response.headers['Location'] == expected_url


def verificar_perfil_contains(
    client,
    user,
    url,
    data=None,
    text='',
    verificar_sem_perfil=False,
    pode_sem_perfil=False,
    perfis_corretos=None,
    perfis_errados=None,
    error_status_code=None,
):
    if perfis_errados is None:
        perfis_errados = []
    if perfis_corretos is None:
        perfis_corretos = []
    if data is None:
        data = {}

    grupos_do_usuario = list(user.groups.all())

    for perfil in perfis_corretos:
        user.groups.remove(Group.objects.get(name=perfil))
    for perfil in perfis_errados:
        user.groups.remove(Group.objects.get(name=perfil))

    if verificar_sem_perfil:
        response = client.get(url, data)
        if pode_sem_perfil:
            for text_for in get_text_array(text):
                assert text_for in response.content.decode(), f'Usuário "{user}" sem perfil'
        else:
            if not (error_status_code and (response.status_code == error_status_code == 403 or response.status_code == error_status_code)):
                for text_for in get_text_array(text):
                    assert text_for not in response.content.decode(), f'Usuario "{user}" sem perfil'

    for perfil in perfis_corretos:
        user.groups.add(Group.objects.get(name=perfil))
        response = client.get(url, data)
        for text_perfil in get_text_array(text):
            assert text_perfil in response.content.decode(), f'Usuário "{user}" perfil correto {perfil}'
        user.groups.remove(Group.objects.get(name=perfil))

    for perfil in perfis_errados:
        user.groups.add(Group.objects.get(name=perfil))
        response = client.get(url, data, silent=True)
        if not (error_status_code and (response.status_code == error_status_code == 403 or response.status_code == error_status_code)):
            for text_perfil in get_text_array(text):
                assert text_perfil not in response.content.decode(), f'Usuário "{user}" perfil errado {perfil}'
        user.groups.remove(Group.objects.get(name=perfil))

    for grupo in grupos_do_usuario:
        user.groups.add(grupo)


def verificar_perfil_not_contains(
    client,
    user,
    url,
    data=None,
    text='',
    verificar_sem_perfil=False,
    pode_sem_perfil=False,
    perfis_corretos=(),
    perfis_errados=(),
    success_status_code=None,
):
    if data is None:
        data = {}

    grupos_do_usuario = list(user.groups.all())

    for perfil in perfis_corretos:
        user.groups.remove(Group.objects.get(name=perfil))
    for perfil in perfis_errados:
        user.groups.remove(Group.objects.get(name=perfil))

    if verificar_sem_perfil:
        response = client.get(url, data)
        if pode_sem_perfil:
            if not (success_status_code and (response.status_code == success_status_code == 403 or response.status_code == success_status_code)):
                for text_perfil in get_text_array(text):
                    assert text_perfil not in response.content.decode(), f'Usuário "{user}" sem perfil'
        else:
            for text_perfil in get_text_array(text):
                assert text_perfil in response.content.decode(), f'Usuário "{user}" sem perfil'

    for perfil in perfis_corretos:
        user.groups.add(Group.objects.get(name=perfil))
        response = client.get(url, data)
        if not (success_status_code and success_status_code == 403 and response.status_code == success_status_code):
            for text_perfil in get_text_array(text):
                assert text_perfil not in response.content.decode(), f'Usuário "{user}" perfil correto {perfil}'
            user.groups.remove(Group.objects.get(name=perfil))

    for perfil in perfis_errados:
        user.groups.add(Group.objects.get(name=perfil))
        response = client.get(url, data, silent=True)
        for text_perfil in get_text_array(text):
            assert text_perfil in response.content.decode(), f'Usuário "{user}" perfil errado {perfil}'
        user.groups.remove(Group.objects.get(name=perfil))

    for grupo in grupos_do_usuario:
        user.groups.add(grupo)


def verificar_perfil_status(
    client,
    user,
    url,
    data=None,
    verificar_sem_perfil=True,
    pode_sem_perfil=False,
    perfis_corretos=None,
    perfis_errados=None,
    success_status_code=200,
    error_status_code=403,
):
    if perfis_errados is None:
        perfis_errados = []
    if perfis_corretos is None:
        perfis_corretos = []
    if data is None:
        data = {}

    grupos_do_usuario = list(user.groups.all())

    for perfil in perfis_corretos:
        user.groups.remove(Group.objects.get(name=perfil))
    for perfil in perfis_errados:
        user.groups.remove(Group.objects.get(name=perfil))

    if verificar_sem_perfil:
        response = client.get(url, data)
        if pode_sem_perfil:
            assert response.status_code == success_status_code, f'Usuário "{user}" sem perfil {response.status_code}!={success_status_code}'
        else:
            assert response.status_code == error_status_code, f'Usuário "{user}" sem perfil {response.status_code}!={error_status_code}'

    for perfil in perfis_corretos:
        user.groups.add(Group.objects.get(name=perfil))
        response = client.get(url, data)
        assert response.status_code == success_status_code, f'Usuário "{user}" perfil correto {perfil} {response.status_code}!={success_status_code}'
        user.groups.remove(Group.objects.get(name=perfil))

    if url.startswith('/admin/'):
        error_status_code = [error_status_code, 404]

    for perfil in perfis_errados:
        user.groups.add(Group.objects.get(name=perfil))
        response = client.get(url, data, silent=True)
        if isinstance(error_status_code, list):
            assert response.status_code in error_status_code, f'Usuário "{user}" perfil errado {perfil} {response.status_code}!={error_status_code}'
        else:
            assert response.status_code == error_status_code, f'Usuário "{user}" perfil errado {perfil} {response.status_code}!={error_status_code}'
        user.groups.remove(Group.objects.get(name=perfil))

    for grupo in grupos_do_usuario:
        user.groups.add(grupo)


def verificar_perfil_submit(
    client,
    user,
    url,
    data=None,
    queryset=None,
    verificar_sem_perfil=True,
    pode_sem_perfil=False,
    perfis_corretos=(),
    perfis_errados=(),
    incremento=1,
    success_status_code=200,
    error_status_code=403,
    after_submit=None,
    modificou=None,
    contains_text=None,
    not_contains_text=None,
    contains_text_perfis_errados=None,
):
    if data is None:
        data = {}

    grupos_do_usuario = list(user.groups.all())

    for perfil in perfis_corretos:
        user.groups.remove(Group.objects.get(name=perfil))
    for perfil in perfis_errados:
        user.groups.remove(Group.objects.get(name=perfil))

    if verificar_sem_perfil:
        if pode_sem_perfil:
            qtd = queryset.count() + incremento
            response = client.post(url, data)
            if modificou:
                assert modificou(), f'Usuário "{user}" sem perfil não modificou'
        else:
            qtd = queryset.count()
            response = client.post(url, data)
            if modificou and (response.status_code != 403 or response.status_code != error_status_code):
                assert not modificou(), f'Usuário "{user}" sem perfil modificou'

        assert queryset.count() == qtd, f'Usuário "{user}" sem perfil {queryset.count()}!={qtd}'
        if after_submit:
            after_submit()

    for perfil in perfis_corretos:
        qtd = queryset.count() + incremento
        user.groups.add(Group.objects.get(name=perfil))
        if contains_text or not_contains_text:
            response = client.post(url, data, follow=True)
        else:
            response = client.post(url, data)

        if not contains_text:
            assert_no_validation_errors(response)

        assert response.status_code == success_status_code, f'Usuário "{user}" perfil correto {perfil} {response.status_code}!={success_status_code}'
        assert queryset.count() == qtd, f'Usuário "{user}" perfil correto {perfil} {queryset.count()}!={qtd}'
        if contains_text or not_contains_text:
            if response.get('Location'):
                response = client.get(response.get('Location'), {})

            if contains_text:
                for contains_text_perfil in get_text_array(contains_text):
                    assert contains_text_perfil in response.content.decode(), f'Usuário "{user}" perfil correto {perfil}'
            if not_contains_text:
                for not_contains_text_perfil in get_text_array(not_contains_text):
                    assert not_contains_text_perfil not in response.content.decode(), f'Usuário "{user}" perfil correto {perfil}'
        if modificou:
            assert modificou(), f'Usuário "{user}" perfil {perfil} não modificou'
        if after_submit:
            after_submit()
        user.groups.remove(Group.objects.get(name=perfil))

    if url.startswith('/admin/'):
        error_status_code = [error_status_code, 404]

    for perfil in perfis_errados:
        qtd = queryset.count()
        user.groups.add(Group.objects.get(name=perfil))
        if contains_text_perfis_errados:
            response = client.post(url, data, silent=True, follow=True)
            if (
                response.status_code != 403
                or (isinstance(error_status_code, list) and response.status_code not in error_status_code)
                or (response.status_code != error_status_code)
            ):
                for contains_text_perfis_errados_item in get_text_array(contains_text_perfis_errados):
                    assert contains_text_perfis_errados_item in response.content.decode(), f'Usuário "{user}" perfil errado {perfil}'
        else:
            response = client.post(url, data, silent=True)
            if isinstance(error_status_code, list):
                assert response.status_code in error_status_code, (
                    f'Usuário "{user}" perfil errado {perfil} {response.status_code}!={error_status_code}'
                )
            else:
                assert response.status_code == error_status_code, (
                    f'Usuário "{user}" perfil errado {perfil} {response.status_code}!={error_status_code}'
                )

        assert queryset.count() == qtd, f'Usuário "{user}" perfil errado {perfil} {queryset.count()}!={qtd}'
        if modificou and (response.status_code != 403 or response.status_code != error_status_code):
            assert not modificou(), f'Usuário "{user}" perfil {perfil} modificou'
        if after_submit:
            after_submit()
        user.groups.remove(Group.objects.get(name=perfil))

    for grupo in grupos_do_usuario:
        user.groups.add(grupo)
