import pytest
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.test import Client

from comum.models import SenhaExposta, User
from djtools.menu import get_menu_from_file, get_menu_json_as_html
from rh.models import Servidor


@pytest.mark.usefixtures('atores')
class TestSegurancaInformacao:
    def _usuario_no_grupo(self, grupo: str, servidor: Servidor | None = None) -> User:
        user = (servidor or self.servidor_a).get_user()
        user.is_staff = True
        user.groups.add(Group.objects.get(name=grupo))
        user.save(update_fields=['is_staff'])
        user.get_groups_cached(force=True)
        return user

    def test_grupo_tem_somente_permissoes_de_leitura_planejadas(self) -> None:
        grupo = Group.objects.get(name='Coordenador de Segurança da Informação')

        permissoes = set(grupo.permissions.values_list('content_type__app_label', 'codename'))

        esperadas = {
            ('comum', 'is_coordenador_de_seguranca_da_informacao'),
            ('comum', 'view_device'),
            ('comum', 'view_senhaexposta'),
            ('comum', 'view_sessioninfo'),
            ('djtools', 'view_emailenviadolog'),
        }
        assert permissoes == esperadas
        assert not {
            codename
            for app_label, codename in permissoes
            if app_label in {'comum', 'djtools'} and codename.startswith(('add_', 'change_', 'delete_'))
        }

    def test_senhas_expostas_respeitam_os_tres_niveis_de_visibilidade(self, client: Client) -> None:
        coordenador = self._usuario_no_grupo('Coordenador de Segurança da Informação')
        coordenador_ti = self._usuario_no_grupo('Coordenador de TI sistêmico', self.servidor_c)
        user_b = self.servidor_b.get_user()
        senha_coordenador = SenhaExposta.objects.create(usuario=coordenador, email='coordenador@example.org', senha='segredo-a')
        senha_terceiro = SenhaExposta.objects.create(usuario=user_b, email='terceiro@example.org', senha='segredo-b')

        client.login(username=coordenador.username, password='123')
        response = client.get('/admin/comum/senhaexposta/', {'usuario__id__exact': user_b.pk})
        assert response.status_code == 200
        assert 'terceiro@example.org' in response.content.decode()
        assert 'coordenador@example.org' not in response.content.decode()
        assert client.get(f'/admin/comum/senhaexposta/{senha_terceiro.pk}/view/').status_code == 200

        client.login(username=coordenador_ti.username, password='123')
        response = client.get('/admin/comum/senhaexposta/')
        assert 'terceiro@example.org' in response.content.decode()
        assert 'coordenador@example.org' in response.content.decode()

        user_b.is_staff = True
        user_b.save(update_fields=['is_staff'])
        client.login(username=user_b.username, password='123')
        response = client.get('/admin/comum/senhaexposta/')
        assert 'terceiro@example.org' in response.content.decode()
        assert 'coordenador@example.org' not in response.content.decode()
        assert client.get(f'/admin/comum/senhaexposta/{senha_coordenador.pk}/view/').status_code == 404

    def test_menu_do_coordenador_reune_os_destinos_em_seguranca(self) -> None:
        coordenador = self._usuario_no_grupo('Coordenador de Segurança da Informação')
        cache.delete('menus')

        menu = get_menu_json_as_html(coordenador)

        for label in ('Dispositivos', 'Sessões', 'Senhas Expostas', 'Histórico de Objetos', 'Acesso', 'Emails enviados'):
            assert label in menu
        assert '>Logs<' in menu

        itens_logs = [
            item
            for item in get_menu_from_file('djtools')
            if item.get('url') in {'/djtools/history/', '/djtools/access_logs/', '/admin/djtools/emailenviadolog/'}
        ]
        assert {item['hierarchy'] for item in itens_logs} == {
            'Tec. da Informação::Segurança::Logs::Histórico de Objetos',
            'Tec. da Informação::Segurança::Logs::Acesso',
            'Tec. da Informação::Segurança::Logs::Emails enviados',
        }

        item_sessoes = next(item for item in get_menu_from_file('comum') if item.get('url') == '/admin/comum/sessioninfo/')
        assert item_sessoes['permissions_required'] == ['comum.view_sessioninfo', 'comum.view_manutencaoprogramada']

    @pytest.mark.parametrize('url', ['/djtools/history/', '/djtools/access_logs/', '/admin/djtools/emailenviadolog/'])
    def test_coordenador_acessa_consultas_de_log(self, client: Client, url: str) -> None:
        coordenador = self._usuario_no_grupo('Coordenador de Segurança da Informação')
        client.login(username=coordenador.username, password='123')

        response = client.get(url)

        assert response.status_code in {200, 302}

    @pytest.mark.parametrize('url', ['/djtools/history/', '/djtools/access_logs/', '/admin/djtools/emailenviadolog/'])
    def test_usuario_sem_permissao_nao_acessa_consultas_de_log(self, client: Client, url: str) -> None:
        user = self.servidor_b.get_user()
        user.is_staff = True
        user.save(update_fields=['is_staff'])
        client.login(username=user.username, password='123')

        response = client.get(url)

        assert response.status_code == 403
