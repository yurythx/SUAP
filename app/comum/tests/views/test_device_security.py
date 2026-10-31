import pytest
from django.contrib import admin as django_admin
from django.contrib.auth.models import Group
from django.test import Client

from comum.forms import DeviceForm
from comum.models import Device, SessionInfo, User
from djtools.contrib.admin.options import ReadOnlyAdmin
from djtools.utils import get_remote_session


@pytest.mark.usefixtures('atores')
class TestDeviceSecurity:
    def _criar_device(self, user: User, user_agent: str = 'Mozilla/5.0 (X11; Linux x86_64)', nickname: str | None = None) -> Device:
        return Device.objects.create(user=user, user_agent=user_agent, nickname=nickname, friendly_name='Dispositivo teste')

    def _configurar_coordenador(self) -> User:
        coordenador = self.servidor_a.get_user()
        coordenador.is_staff = True
        coordenador.groups.add(Group.objects.get(name='Coordenador de Segurança da Informação'))
        coordenador.save(update_fields=['is_staff'])
        coordenador.get_groups_cached(force=True)
        return coordenador

    def test_usuario_nao_pode_apelidar_dispositivo_de_outro(self, client):
        device_b = self._criar_device(self.servidor_b.get_user())
        client.login(username=self.servidor_a.get_user().username, password='123')

        response = client.post(f'/comum/give_nickname_to_device/{device_b.pk}/', {'nickname': 'Ataque'})

        assert response.status_code == 404
        device_b.refresh_from_db()
        assert device_b.nickname is None

    def test_usuario_pode_apelidar_proprio_dispositivo(self, client):
        device_a = self._criar_device(self.servidor_a.get_user())
        client.login(username=self.servidor_a.get_user().username, password='123')

        response = client.post(f'/comum/give_nickname_to_device/{device_a.pk}/', {'nickname': 'Meu notebook'})

        assert response.status_code == 302
        device_a.refresh_from_db()
        assert device_a.nickname == 'Meu notebook'

    def test_superuser_pode_apelidar_qualquer_dispositivo(self, client):
        device_b = self._criar_device(self.servidor_b.get_user())
        client.login(username=self.admin.get_user().username, password='123')

        response = client.post(f'/comum/give_nickname_to_device/{device_b.pk}/', {'nickname': 'Ajuste admin'})

        assert response.status_code == 302
        device_b.refresh_from_db()
        assert device_b.nickname == 'Ajuste admin'

    def test_anonimo_eh_redirecionado(self, client):
        device_a = self._criar_device(self.servidor_a.get_user())

        response = client.post(f'/comum/give_nickname_to_device/{device_a.pk}/', {'nickname': 'Anonimo'})

        assert response.status_code == 302
        device_a.refresh_from_db()
        assert device_a.nickname is None

    def test_apelido_inseguro_e_limpo_no_formulario(self):
        form = DeviceForm(data={'nickname': '<script>alert(1)</script><img src=x onerror=alert(2)>'})
        assert form.is_valid()
        assert '<' not in form.cleaned_data['nickname']

    def test_apelido_apenas_tags_vira_none(self):
        form = DeviceForm(data={'nickname': '<b></b>'})
        assert form.is_valid()
        assert form.cleaned_data['nickname'] is None

    def test_admin_device_nao_renderiza_apelido_inseguro(self, client):
        payload = '<script>alert(1)</script><img src=x onerror=alert(2)>'
        self._criar_device(self.servidor_a.get_user(), nickname=payload)
        client.login(username=self.admin.get_user().username, password='123')

        response = client.get('/admin/comum/device/')

        assert response.status_code == 200
        body = response.content.decode()
        assert payload not in body
        assert '&lt;script&gt;alert(1)&lt;/script&gt;' in body

    def test_readonly_admin_view_object_icon_escapa_apelido(self):
        payload = '<script>alert(1)</script><img src=x onerror=alert(2)>'
        device = self._criar_device(self.servidor_a.get_user(), nickname=payload)
        readonly_admin = ReadOnlyAdmin(Device, django_admin.site)

        html = readonly_admin.view_object_icon(device)

        assert payload not in html
        assert '&lt;script&gt;alert(1)&lt;/script&gt;' in html

    def test_usuario_nao_acessa_view_de_dispositivo_de_outro(self, client):
        device_b = self._criar_device(self.servidor_b.get_user())
        user_a = self.servidor_a.get_user()
        user_a.is_staff = True
        user_a.save()
        client.login(username=user_a.username, password='123')

        response = client.get(f'/admin/comum/device/{device_b.pk}/view/')

        assert response.status_code == 404

    def test_usuario_acessa_view_do_proprio_dispositivo(self, client):
        device_a = self._criar_device(self.servidor_a.get_user())
        user_a = self.servidor_a.get_user()
        user_a.is_staff = True
        user_a.save()
        client.login(username=user_a.username, password='123')

        response = client.get(f'/admin/comum/device/{device_a.pk}/view/')

        assert response.status_code == 200

    def test_superuser_acessa_view_de_qualquer_dispositivo(self, client):
        device_b = self._criar_device(self.servidor_b.get_user())
        client.login(username=self.admin.get_user().username, password='123')

        response = client.get(f'/admin/comum/device/{device_b.pk}/view/')

        assert response.status_code == 200

    def _criar_session_info(self, device: Device, ip_address: str = '10.0.0.1') -> SessionInfo:
        session = Client().session
        return SessionInfo.objects.create(session_id=session.session_key, device=device, ip_address=ip_address)

    def test_coordenador_consulta_dispositivos_e_pode_desativar_terceiros(self, client: Client) -> None:
        coordenador = self._configurar_coordenador()
        device_coordenador = self._criar_device(coordenador, nickname='Dispositivo próprio')
        device_terceiro = self._criar_device(self.servidor_b.get_user(), user_agent='Agente terceiro', nickname='Dispositivo terceiro')
        client.login(username=coordenador.username, password='123')

        response = client.get('/admin/comum/device/', {'q': self.servidor_b.matricula})

        assert response.status_code == 200
        body = response.content.decode()
        assert 'Dispositivo terceiro' in body
        assert 'Dispositivo próprio' not in body
        assert f'/comum/give_nickname_to_device/{device_terceiro.pk}/' not in body
        assert f'/comum/deactivate_device/{device_terceiro.pk}/' in body

        response = client.get('/admin/comum/device/', {'user__id__exact': self.servidor_b.get_user().pk})
        assert 'Dispositivo terceiro' in response.content.decode()
        assert 'Dispositivo próprio' not in response.content.decode()

        response = client.get('/admin/comum/device/', {'user__id__exact': coordenador.pk})
        assert f'/comum/give_nickname_to_device/{device_coordenador.pk}/' in response.content.decode()

    @pytest.mark.parametrize('url_name', ['give_nickname_to_device', 'reactivate_device'])
    def test_coordenador_nao_pode_apelidar_ou_reativar_dispositivo_de_terceiro(self, client: Client, url_name: str) -> None:
        coordenador = self._configurar_coordenador()
        device_terceiro = self._criar_device(self.servidor_b.get_user())
        client.login(username=coordenador.username, password='123')

        response = client.get(f'/comum/{url_name}/{device_terceiro.pk}/')

        assert response.status_code == 404

    def test_coordenador_pode_desativar_dispositivo_de_terceiro(self, client: Client) -> None:
        coordenador = self._configurar_coordenador()
        device_terceiro = self._criar_device(self.servidor_b.get_user())
        client.login(username=coordenador.username, password='123')

        response = client.get(f'/comum/deactivate_device/{device_terceiro.pk}/')

        assert response.status_code == 302
        device_terceiro.refresh_from_db()
        assert not device_terceiro.activated

    def test_coordenador_consulta_sessoes_e_pode_deslogar_terceiros(self, client: Client) -> None:
        coordenador = self._configurar_coordenador()
        session_coordenador = self._criar_session_info(self._criar_device(coordenador), ip_address='10.0.0.1')
        session_terceiro = self._criar_session_info(self._criar_device(self.servidor_b.get_user()), ip_address='10.0.0.2')
        client.login(username=coordenador.username, password='123')

        response = client.get('/admin/comum/sessioninfo/', {'q': self.servidor_b.matricula})

        assert response.status_code == 200
        body = response.content.decode()
        assert '10.0.0.2' in body
        assert '10.0.0.1' not in body
        assert f'/comum/remote_logout/{session_terceiro.pk}/' in body

        response = client.get('/admin/comum/sessioninfo/', {'device__user__id__exact': self.servidor_b.get_user().pk})
        assert '10.0.0.2' in response.content.decode()
        assert '10.0.0.1' not in response.content.decode()

        response = client.get('/admin/comum/sessioninfo/', {'device__user__id__exact': coordenador.pk})
        assert f'/comum/remote_logout/{session_coordenador.pk}/' in response.content.decode()

        sessao_remota = get_remote_session(session_terceiro.session_id)
        assert sessao_remota.exists(session_terceiro.session_id)

        response = client.get(f'/comum/remote_logout/{session_terceiro.pk}/')
        assert response.status_code == 302
        session_terceiro.refresh_from_db()
        assert session_terceiro.expired
        assert not sessao_remota.exists(session_terceiro.session_id)

    def test_usuario_nao_acessa_view_de_sessioninfo_de_outro(self, client):
        session_b = self._criar_session_info(self._criar_device(self.servidor_b.get_user()))
        user_a = self.servidor_a.get_user()
        user_a.is_staff = True
        user_a.save()
        client.login(username=user_a.username, password='123')

        response = client.get(f'/admin/comum/sessioninfo/{session_b.pk}/view/')

        assert response.status_code == 404

    def test_usuario_acessa_view_de_sessioninfo_propria(self, client):
        session_a = self._criar_session_info(self._criar_device(self.servidor_a.get_user()))
        user_a = self.servidor_a.get_user()
        user_a.is_staff = True
        user_a.save()
        client.login(username=user_a.username, password='123')

        response = client.get(f'/admin/comum/sessioninfo/{session_a.pk}/view/')

        assert response.status_code == 200

    def test_superuser_acessa_view_de_qualquer_sessioninfo(self, client):
        session_b = self._criar_session_info(self._criar_device(self.servidor_b.get_user()))
        client.login(username=self.admin.get_user().username, password='123')

        response = client.get(f'/admin/comum/sessioninfo/{session_b.pk}/view/')

        assert response.status_code == 200
