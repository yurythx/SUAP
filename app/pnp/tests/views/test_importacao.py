import pytest
from django.contrib import admin
from django.contrib.auth.models import Permission
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory

from comum.models import User
from pnp.admin import AreaTematicaPNPAdmin, EixoPNPAdmin, EstruturaPNPAdmin, MatriculaPNPAdmin, ServidorPNPAdmin
from pnp.models import AreaTematicaPNP, EixoPNP, EstruturaPNP, MatriculaPNP, ServidorPNP

ADMINS = {
    EstruturaPNPAdmin: (EstruturaPNP, ['tab_sem_unidade', 'tab_com_unidade']),
    AreaTematicaPNPAdmin: (AreaTematicaPNP, ['tab_sem_area', 'tab_com_area']),
    EixoPNPAdmin: (EixoPNP, ['tab_sem_eixo_tecnologico', 'tab_com_eixo_tecnologico']),
    MatriculaPNPAdmin: (MatriculaPNP, ['tab_sem_aluno', 'tab_com_aluno']),
    ServidorPNPAdmin: (ServidorPNP, ['tab_sem_servidor', 'tab_com_servidor', 'tab_sem_estrutura']),
}


def get_admin(admin_class):
    return admin_class(ADMINS[admin_class][0], admin.site)


@pytest.fixture(params=list(ADMINS), ids=lambda admin_class: admin_class.__name__)
def model_admin(request):
    return get_admin(request.param)


def criar_request(model_admin, com_permissao: bool, superusuario: bool = False):
    """Monta um GET autenticado para a view de importação, com sessão e mensagens."""
    model_name = model_admin.model._meta.model_name
    user = User.objects.create_user(
        username=f'usuario_{model_name}_{com_permissao}_{superusuario}', password='senha', is_staff=True, is_superuser=superusuario
    )
    if com_permissao:
        user.user_permissions.add(Permission.objects.get(codename=f'add_{model_name}'))
    request = RequestFactory().get(f'/admin/pnp/{model_name}/importar/')
    request.user = user
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    return request


@pytest.mark.django_db
def test_sem_permissao_de_adicionar_nao_acessa_a_importacao(model_admin):
    with pytest.raises(PermissionDenied):
        model_admin.importar(criar_request(model_admin, com_permissao=False))


@pytest.mark.django_db
def test_com_permissao_de_adicionar_renderiza_o_formulario(model_admin):
    resposta = model_admin.importar(criar_request(model_admin, com_permissao=True))

    assert resposta.status_code == 200
    assert b'name="arquivo"' in resposta.content


@pytest.mark.django_db
def test_botao_de_importar_so_aparece_para_quem_pode_adicionar(model_admin):
    def labels(com_permissao):
        return [item['label'] for item in model_admin.get_action_bar(criar_request(model_admin, com_permissao))]

    assert model_admin.importacao_title in labels(com_permissao=True)
    assert model_admin.importacao_title not in labels(com_permissao=False)


@pytest.mark.django_db
def test_as_abas_declaradas_existem(model_admin):
    request = criar_request(model_admin, com_permissao=True)

    assert model_admin.get_tabs(request) == ADMINS[type(model_admin)][1]
    for aba in model_admin.get_tabs(request):
        assert getattr(model_admin, aba)(request, model_admin.model.objects.all()) is not None


@pytest.mark.django_db
def test_as_abas_aparecem_na_listagem(model_admin):
    """get_tabs só chega à tela se o CustomTabListFilter estiver no list_filter."""
    request = criar_request(model_admin, com_permissao=True, superusuario=True)
    request.path = f'/admin/pnp/{model_admin.model._meta.model_name}/'

    html = model_admin.changelist_view(request).render().content.decode()

    for aba in model_admin.get_tabs(request):
        assert getattr(model_admin, aba).short_description in html


@pytest.mark.django_db
def test_abas_separam_as_estruturas_com_e_sem_unidade():
    model_admin = get_admin(EstruturaPNPAdmin)
    request = criar_request(model_admin, com_permissao=True)
    EstruturaPNP.objects.create(codigo='sem-unidade')

    assert [e.codigo for e in model_admin.tab_sem_unidade(request, EstruturaPNP.objects.all())] == ['sem-unidade']
    assert not model_admin.tab_com_unidade(request, EstruturaPNP.objects.all()).exists()


@pytest.mark.django_db
def test_abas_separam_os_servidores_sem_vinculo_e_sem_estrutura():
    model_admin = get_admin(ServidorPNPAdmin)
    request = criar_request(model_admin, com_permissao=True)
    ServidorPNP.objects.create(matricula='123', nome='FULANO')

    queryset = ServidorPNP.objects.all()
    assert [s.matricula for s in model_admin.tab_sem_servidor(request, queryset)] == ['123']
    assert [s.matricula for s in model_admin.tab_sem_estrutura(request, queryset)] == ['123']
    assert not model_admin.tab_com_servidor(request, queryset).exists()
