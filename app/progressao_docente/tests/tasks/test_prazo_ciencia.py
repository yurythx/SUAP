"""Testes do trâmite automático da ciência do resultado (progressão docente)."""

from datetime import datetime, timedelta

import pytest
from django.apps.registry import apps
from django.core.management import call_command

from progressao_docente.tests.factories import AvaliacaoFactory, ProgressaoDocenteFactory
from rh.tests.factories import ServidorFactory

ProgressaoDocente = apps.get_model('progressao_docente', 'ProgressaoDocente')
Avaliacao = apps.get_model('progressao_docente', 'Avaliacao')

pytestmark = pytest.mark.django_db


def _criar_avaliacao_ciencia(*, dias_atras_liberacao, situacao=Avaliacao.AGUARDANDO_CIENCIA_RESULTADO):
    """Avaliação aguardando ciência. Cada chamada tem o seu avaliado — é o que dá aos testes
    de lote (``call_command``) duas avaliações de pessoas diferentes, como antes."""
    progressao = ProgressaoDocenteFactory(situacao=ProgressaoDocente.AGUARDANDO_CIENCIA_RESULTADO)
    liberacao = None if dias_atras_liberacao is None else datetime.now() - timedelta(days=dias_atras_liberacao)
    return AvaliacaoFactory(progressao=progressao, situacao=situacao, data_liberacao_ciencia=liberacao)


def test_campos_ciencia_defaults(sync_permissions):
    avaliacao = _criar_avaliacao_ciencia(dias_atras_liberacao=None)
    assert avaliacao.ciencia_expirada is False
    assert avaliacao.data_liberacao_ciencia is None


def test_prazo_ciencia_vencido(sync_permissions):
    # liberada há 10 dias, tempo_ciencia padrão 2 => vencida
    avaliacao = _criar_avaliacao_ciencia(dias_atras_liberacao=10)
    assert avaliacao.prazo_ciencia_vencido() is True


def test_prazo_ciencia_nao_vencido(sync_permissions):
    # liberada hoje, tempo_ciencia padrão 2 => ainda no prazo
    avaliacao = _criar_avaliacao_ciencia(dias_atras_liberacao=0)
    assert avaliacao.prazo_ciencia_vencido() is False


def test_prazo_ciencia_sem_data_nao_vence(sync_permissions):
    avaliacao = _criar_avaliacao_ciencia(dias_atras_liberacao=None)
    assert avaliacao.prazo_ciencia_vencido() is False


def test_data_limite_etapa_atual_para_ciencia(sync_permissions):
    avaliacao = _criar_avaliacao_ciencia(dias_atras_liberacao=0)
    limite = avaliacao.data_limite_etapa_atual()
    assert limite is not None
    assert avaliacao.dias_restantes_etapa_atual() is not None


def test_expirar_ciencia_conclui_e_marca_flag(sync_permissions):
    avaliacao = _criar_avaliacao_ciencia(dias_atras_liberacao=10)
    assert avaliacao.expirar_ciencia() is True
    avaliacao.refresh_from_db()
    assert avaliacao.situacao == Avaliacao.CONCLUIDA
    assert avaliacao.ciencia_expirada is True
    assert avaliacao.finalizada is True


def test_expirar_ciencia_idempotente(sync_permissions):
    avaliacao = _criar_avaliacao_ciencia(dias_atras_liberacao=10)
    assert avaliacao.expirar_ciencia() is True
    avaliacao.refresh_from_db()
    assert avaliacao.expirar_ciencia() is False  # já concluída (estado persistido)


def test_expirar_ciencia_nao_vencida_nao_tramita(sync_permissions):
    avaliacao = _criar_avaliacao_ciencia(dias_atras_liberacao=0)
    assert avaliacao.expirar_ciencia() is False
    avaliacao.refresh_from_db()
    assert avaliacao.situacao == Avaliacao.AGUARDANDO_CIENCIA_RESULTADO


def test_expirar_ciencia_persiste_estado_com_falha_de_notificacao(sync_permissions, monkeypatch):
    # notificação best-effort: falha de e-mail não reverte a conclusão nem propaga exceção
    avaliacao = _criar_avaliacao_ciencia(dias_atras_liberacao=10)

    def _falhar(self):
        raise RuntimeError('falha no envio de e-mail')

    monkeypatch.setattr(Avaliacao, '_notificar_expiracao_ciencia', _falhar)
    assert avaliacao.expirar_ciencia() is True
    avaliacao.refresh_from_db()
    assert avaliacao.situacao == Avaliacao.CONCLUIDA
    assert avaliacao.ciencia_expirada is True


def test_command_ciencia_continua_lote_apos_falha_de_notificacao(sync_permissions, monkeypatch):
    # uma falha de e-mail em uma avaliação não deve abortar a tramitação das demais
    a1 = _criar_avaliacao_ciencia(dias_atras_liberacao=10)
    a2 = _criar_avaliacao_ciencia(dias_atras_liberacao=10)

    def _falhar(self):
        raise RuntimeError('falha no envio de e-mail')

    monkeypatch.setattr(Avaliacao, '_notificar_expiracao_ciencia', _falhar)
    call_command('processar_prazos_avaliacao')

    a1.refresh_from_db()
    a2.refresh_from_db()
    assert a1.situacao == Avaliacao.CONCLUIDA
    assert a2.situacao == Avaliacao.CONCLUIDA


def test_encaminhar_para_ciencia_grava_data_liberacao(sync_permissions):
    progressao = ProgressaoDocenteFactory(situacao=ProgressaoDocente.EM_AVALIACAO)
    avaliacao = AvaliacaoFactory(progressao=progressao, situacao=Avaliacao.EM_AVALIACAO)
    # no fluxo real há avaliador(es) ao encaminhar; calcular_pontuacao_avaliacao acessa avaliadores.first()
    avaliacao.avaliadores.add(ServidorFactory())

    avaliacao.encaminhar_avaliacao_para_ciencia(request=None)
    avaliacao.refresh_from_db()
    assert avaliacao.situacao == Avaliacao.AGUARDANDO_CIENCIA_RESULTADO
    assert avaliacao.data_liberacao_ciencia is not None


def test_manifestacao_ciencia_html_expirada(sync_permissions):
    avaliacao = _criar_avaliacao_ciencia(dias_atras_liberacao=10)
    avaliacao.expirar_ciencia()
    avaliacao.refresh_from_db()
    html = avaliacao.manifestacao_ciencia_html()
    assert 'não houve manifestação no prazo' in html


def test_manifestacao_ciencia_html_pendente(sync_permissions):
    avaliacao = _criar_avaliacao_ciencia(dias_atras_liberacao=0)
    assert 'Pendente' in avaliacao.manifestacao_ciencia_html()


def test_manifestacao_ciencia_html_vazia_concluida_sem_ciencia(sync_permissions):
    # concluída sem assinatura e sem expiração (ex.: conclusão manual) não está "pendente"
    avaliacao = _criar_avaliacao_ciencia(dias_atras_liberacao=0, situacao=Avaliacao.CONCLUIDA)
    assert avaliacao.manifestacao_ciencia_html() == ''


def test_manifestacao_ciencia_html_vazia_antes_da_etapa(sync_permissions):
    # etapa anterior à ciência (ex.: em avaliação) não deve exibir manifestação de ciência
    avaliacao = _criar_avaliacao_ciencia(dias_atras_liberacao=0, situacao=Avaliacao.EM_AVALIACAO)
    assert avaliacao.manifestacao_ciencia_html() == ''


def test_manifestacao_ciencia_html_assinada(sync_permissions):
    avaliacao = _criar_avaliacao_ciencia(dias_atras_liberacao=0)
    avaliacao.assinatura_avaliado_processo = 'ASSINATURA'
    avaliacao.data_assinatura_avaliado_processo = datetime.now()
    avaliacao.save()
    assert 'Ciente' in avaliacao.manifestacao_ciencia_html()


def test_manifestacao_preenchimento_html_expirado(sync_permissions):
    avaliacao = _criar_avaliacao_ciencia(dias_atras_liberacao=0)
    avaliacao.preenchimento_expirado = True
    avaliacao.save()
    assert 'não houve manifestação no prazo' in avaliacao.manifestacao_preenchimento_html()


def test_manifestacao_preenchimento_html_vazio(sync_permissions):
    avaliacao = _criar_avaliacao_ciencia(dias_atras_liberacao=0)
    assert avaliacao.manifestacao_preenchimento_html() == ''


def test_command_processa_ciencia_vencida(sync_permissions):
    vencida = _criar_avaliacao_ciencia(dias_atras_liberacao=10)
    no_prazo = _criar_avaliacao_ciencia(dias_atras_liberacao=0)

    call_command('processar_prazos_avaliacao')

    vencida.refresh_from_db()
    no_prazo.refresh_from_db()
    assert vencida.situacao == Avaliacao.CONCLUIDA
    assert vencida.ciencia_expirada is True
    assert no_prazo.situacao == Avaliacao.AGUARDANDO_CIENCIA_RESULTADO
    # com a única avaliação concluída, o processo avança para CIENTE_RESULTADO (Avaliacao.save)
    vencida.progressao.refresh_from_db()
    assert vencida.progressao.situacao == ProgressaoDocente.CIENTE_RESULTADO


def test_forcar_expiracao_ciencia_dentro_do_prazo(sync_permissions):
    # mesmo dentro do prazo, antecipar data_liberacao_ciencia força a ciência tácita
    avaliacao = _criar_avaliacao_ciencia(dias_atras_liberacao=0)
    avaliacao.data_liberacao_ciencia = datetime.now() - timedelta(days=365)
    avaliacao.save()
    assert avaliacao.expirar_ciencia() is True
    avaliacao.refresh_from_db()
    assert avaliacao.situacao == Avaliacao.CONCLUIDA
    assert avaliacao.ciencia_expirada is True


def test_expirar_ciencia_situacao_invalida_nao_tramita(sync_permissions):
    # fora de AGUARDANDO_CIENCIA_RESULTADO não há ciência a expirar, mesmo com prazo vencido
    avaliacao = _criar_avaliacao_ciencia(dias_atras_liberacao=365, situacao=Avaliacao.EM_AVALIACAO)
    assert avaliacao.expirar_ciencia() is False
    avaliacao.refresh_from_db()
    assert avaliacao.situacao == Avaliacao.EM_AVALIACAO
