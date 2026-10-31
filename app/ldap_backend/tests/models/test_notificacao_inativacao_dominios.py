"""E-mails do AD listados como institucionais no aviso de inativação de conta."""

import logging
from types import SimpleNamespace

import pytest
from django.test import override_settings

from comum.models import Configuracao
from ldap_backend.models import LdapConf


class AlunoFalso:
    _meta = SimpleNamespace(verbose_name='Aluno')
    matricula = '20261000'
    curso_campus = 'Curso'
    pessoa_fisica = SimpleNamespace(nome='Fulano', eh_estrangeiro=False)
    email_pessoal = 'fulano@gmail.com'
    email_notificacao = email_academico = email_google_classroom = None

    def get_vinculo(self) -> SimpleNamespace:
        return SimpleNamespace(user=None)


def _mensagem_de_inativacao(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> str:
    # Fronteira externa: o AD.
    monkeypatch.setattr(LdapConf, 'get_emails_ad', lambda self, username: ['fulano@ifrn.edu.br', 'fulano@gmail.com'])
    Configuracao.clear_cache()
    with override_settings(DEBUG=True), caplog.at_level(logging.INFO, logger='ldap_backend.models'):
        LdapConf().notificar_usuario_inativacao(AlunoFalso(), dia_da_desativacao=30)
    return caplog.text


@pytest.mark.django_db
def test_sem_dominios_configurados_nenhum_email_do_ad_e_institucional(monkeypatch, caplog) -> None:
    Configuracao.objects.filter(app='comum', chave='dominios_institucionais').delete()

    mensagem = _mensagem_de_inativacao(monkeypatch, caplog)

    assert 'será inativada em' in mensagem
    assert 'fulano@ifrn.edu.br' not in mensagem
    assert 'fulano@gmail.com' not in mensagem


@pytest.mark.django_db
def test_pedaco_vazio_da_lista_de_dominios_nao_casa_qualquer_email(monkeypatch, caplog) -> None:
    Configuracao.objects.update_or_create(app='comum', chave='dominios_institucionais', defaults={'valor': '@ifrn.edu.br;'})

    mensagem = _mensagem_de_inativacao(monkeypatch, caplog)

    assert 'A conta de e-mail <b>fulano@ifrn.edu.br</b> será inativada' in mensagem
    assert 'fulano@gmail.com' not in mensagem


@pytest.mark.django_db
def test_sem_sigla_da_instituicao_aviso_usa_texto_neutro(monkeypatch, caplog) -> None:
    Configuracao.objects.filter(app='comum', chave='instituicao_sigla').delete()

    mensagem = _mensagem_de_inativacao(monkeypatch, caplog)

    assert 'None' not in mensagem
    assert '[SUAP] Informações relevantes sobre a sua conta no SUAP\n' in mensagem
    assert 'encerramento do seu vínculo com a instituição</b>' in mensagem
    assert 'sua conta no SUAP será inativada' in mensagem


@pytest.mark.django_db
def test_com_sigla_da_instituicao_aviso_cita_a_sigla(monkeypatch, caplog) -> None:
    Configuracao.objects.update_or_create(app='comum', chave='instituicao_sigla', defaults={'valor': 'IFRN'})

    mensagem = _mensagem_de_inativacao(monkeypatch, caplog)

    assert '[SUAP] Informações relevantes sobre a sua conta no IFRN\n' in mensagem
    assert 'encerramento do seu vínculo com o IFRN</b>' in mensagem
    assert 'sua conta no SUAP do IFRN será inativada' in mensagem
