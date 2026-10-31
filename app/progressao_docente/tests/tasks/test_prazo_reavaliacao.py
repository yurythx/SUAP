"""Testes dos prazos do ciclo de reavaliação (progressão docente).

Cobre as duas etapas que ficavam sem relógio e travavam o processo
indefinidamente (chamado 10625): a edição para reavaliação, com a bola no
avaliado, e a reavaliação propriamente dita, com a bola no avaliador.
"""

import importlib
from datetime import date, datetime, timedelta

import pytest
from django.apps.registry import apps
from django.core.management import call_command
from django.test import RequestFactory

from progressao_docente.tests.factories import AvaliacaoFactory, ProgressaoDocenteFactory
from rh.tests.factories import ServidorFactory

ProgressaoDocente = apps.get_model('progressao_docente', 'ProgressaoDocente')
Avaliacao = apps.get_model('progressao_docente', 'Avaliacao')
Formulario = apps.get_model('progressao_docente', 'Formulario')
RecursoAvaliacao = apps.get_model('progressao_docente', 'RecursoAvaliacao')

migracao = importlib.import_module('progressao_docente.migrations.0047_carimbar_relogios_reavaliacao')

pytestmark = pytest.mark.django_db


def _criar_avaliacao(*, situacao, situacao_processo=None, **datas):
    """Avaliação com avaliado e avaliador próprios.

    Nenhum teste daqui depende de QUEM são — só de que sejam pessoas distintas. O avaliado
    sai em ``avaliacao.progressao.avaliado`` e o avaliador em ``avaliacao.avaliadores.first()``
    para quem precisar autenticar um dos dois.
    """
    progressao = ProgressaoDocenteFactory(situacao=situacao_processo or ProgressaoDocente.REAVALIACAO)
    avaliacao = AvaliacaoFactory(progressao=progressao, situacao=situacao, **datas)
    # calcular_pontuacao_avaliacao acessa avaliadores.first(); no fluxo real sempre há avaliador aqui.
    avaliacao.avaliadores.add(ServidorFactory())
    return avaliacao


def _dias_atras(dias):
    return None if dias is None else datetime.now() - timedelta(days=dias)


def _em_edicao(*, dias_atras_liberacao):
    return _criar_avaliacao(
        situacao=Avaliacao.EDITACAO_PARA_REAVALIACAO,
        data_liberacao_edicao_reavaliacao=_dias_atras(dias_atras_liberacao),
    )


def _em_reavaliacao(*, dias_atras_liberacao):
    return _criar_avaliacao(
        situacao=Avaliacao.REAVALIACAO,
        data_liberacao_reavaliacao=_dias_atras(dias_atras_liberacao),
        data_liberacao_ciencia=_dias_atras(365),
    )


def _request(user, **post):
    factory = RequestFactory()
    request = factory.post('/progressao_docente/', post) if post else factory.get('/progressao_docente/')
    request.user = user
    return request


# ---------------------------------------------------------------------------
# Edição para reavaliação (bola com o avaliado)
# ---------------------------------------------------------------------------


def test_campos_edicao_reavaliacao_defaults(sync_permissions):
    avaliacao = _em_edicao(dias_atras_liberacao=None)
    assert avaliacao.data_liberacao_edicao_reavaliacao is None
    assert avaliacao.edicao_reavaliacao_expirada is False
    assert avaliacao.reavaliacao_expirada is False


def test_prazo_edicao_reavaliacao_vencido(sync_permissions):
    # liberada há 10 dias, tempo_adicao_edicao padrão 2 => vencida
    avaliacao = _em_edicao(dias_atras_liberacao=10)
    assert avaliacao.prazo_edicao_reavaliacao_vencido() is True


def test_prazo_edicao_reavaliacao_nao_vencido(sync_permissions):
    avaliacao = _em_edicao(dias_atras_liberacao=0)
    assert avaliacao.prazo_edicao_reavaliacao_vencido() is False


def test_prazo_edicao_reavaliacao_sem_data_nao_vence(sync_permissions):
    avaliacao = _em_edicao(dias_atras_liberacao=None)
    assert avaliacao.prazo_edicao_reavaliacao_vencido() is False


def test_prazo_edicao_reavaliacao_fora_da_situacao_nao_vence(sync_permissions):
    avaliacao = _criar_avaliacao(
        situacao=Avaliacao.EM_AVALIACAO,
        data_liberacao_edicao_reavaliacao=_dias_atras(365),
    )
    assert avaliacao.prazo_edicao_reavaliacao_vencido() is False


def test_data_limite_etapa_atual_para_edicao_reavaliacao(sync_permissions):
    avaliacao = _em_edicao(dias_atras_liberacao=0)
    assert avaliacao.data_limite_etapa_atual() is not None
    assert avaliacao.dias_restantes_etapa_atual() is not None


def test_expirar_edicao_reavaliacao_conclui_e_marca_flag(sync_permissions):
    avaliacao = _em_edicao(dias_atras_liberacao=10)
    assert avaliacao.expirar_edicao_reavaliacao() is True
    avaliacao.refresh_from_db()
    assert avaliacao.situacao == Avaliacao.CONCLUIDA
    assert avaliacao.edicao_reavaliacao_expirada is True
    assert avaliacao.finalizada is True


def test_expirar_edicao_reavaliacao_avanca_o_processo(sync_permissions):
    avaliacao = _em_edicao(dias_atras_liberacao=10)
    avaliacao.expirar_edicao_reavaliacao()
    avaliacao.progressao.refresh_from_db()
    assert avaliacao.progressao.situacao == ProgressaoDocente.CIENTE_RESULTADO


def test_expirar_edicao_reavaliacao_idempotente(sync_permissions):
    avaliacao = _em_edicao(dias_atras_liberacao=10)
    assert avaliacao.expirar_edicao_reavaliacao() is True
    avaliacao.refresh_from_db()
    assert avaliacao.expirar_edicao_reavaliacao() is False


def test_expirar_edicao_reavaliacao_nao_vencida_nao_tramita(sync_permissions):
    avaliacao = _em_edicao(dias_atras_liberacao=0)
    assert avaliacao.expirar_edicao_reavaliacao() is False
    avaliacao.refresh_from_db()
    assert avaliacao.situacao == Avaliacao.EDITACAO_PARA_REAVALIACAO


def test_expirar_edicao_reavaliacao_persiste_estado_com_falha_de_notificacao(sync_permissions, monkeypatch):
    avaliacao = _em_edicao(dias_atras_liberacao=10)

    def _falhar(self):
        raise RuntimeError('falha no envio de e-mail')

    monkeypatch.setattr(Avaliacao, '_notificar_expiracao_edicao_reavaliacao', _falhar)
    assert avaliacao.expirar_edicao_reavaliacao() is True
    avaliacao.refresh_from_db()
    assert avaliacao.situacao == Avaliacao.CONCLUIDA
    assert avaliacao.edicao_reavaliacao_expirada is True


def test_reabrir_para_edicao_reavaliacao_grava_data_liberacao(sync_permissions):
    avaliacao = _criar_avaliacao(
        situacao=Avaliacao.AGUARDANDO_CIENCIA_RESULTADO,
        situacao_processo=ProgressaoDocente.AGUARDANDO_CIENCIA_RESULTADO,
    )
    avaliacao.reabrir_para_edicao_reavaliacao()
    avaliacao.refresh_from_db()
    assert avaliacao.situacao == Avaliacao.EDITACAO_PARA_REAVALIACAO
    assert avaliacao.data_liberacao_edicao_reavaliacao is not None


def test_manifestacao_edicao_reavaliacao_html_expirada(sync_permissions):
    avaliacao = _em_edicao(dias_atras_liberacao=10)
    avaliacao.expirar_edicao_reavaliacao()
    avaliacao.refresh_from_db()
    assert 'não houve manifestação no prazo' in avaliacao.manifestacao_edicao_reavaliacao_html()


def test_manifestacao_edicao_reavaliacao_html_pendente(sync_permissions):
    avaliacao = _em_edicao(dias_atras_liberacao=0)
    assert 'Pendente' in avaliacao.manifestacao_edicao_reavaliacao_html()


def test_manifestacao_edicao_reavaliacao_html_vazia_fora_da_etapa(sync_permissions):
    avaliacao = _criar_avaliacao(situacao=Avaliacao.EM_AVALIACAO)
    assert avaliacao.manifestacao_edicao_reavaliacao_html() == ''


# ---------------------------------------------------------------------------
# Reavaliação (bola com o avaliador)
# ---------------------------------------------------------------------------


def test_prazo_reavaliacao_vencido(sync_permissions):
    # liberada há 10 dias, tempo_reavaliacao padrão 2 => vencida
    avaliacao = _em_reavaliacao(dias_atras_liberacao=10)
    assert avaliacao.prazo_reavaliacao_vencido() is True


def test_prazo_reavaliacao_nao_vencido(sync_permissions):
    avaliacao = _em_reavaliacao(dias_atras_liberacao=0)
    assert avaliacao.prazo_reavaliacao_vencido() is False


def test_prazo_reavaliacao_sem_data_nao_vence(sync_permissions):
    avaliacao = _em_reavaliacao(dias_atras_liberacao=None)
    assert avaliacao.prazo_reavaliacao_vencido() is False


def test_expirar_reavaliacao_encaminha_para_ciencia(sync_permissions):
    avaliacao = _em_reavaliacao(dias_atras_liberacao=10)
    assert avaliacao.expirar_reavaliacao() is True
    avaliacao.refresh_from_db()
    assert avaliacao.situacao == Avaliacao.AGUARDANDO_CIENCIA_RESULTADO
    assert avaliacao.reavaliacao_expirada is True


def test_expirar_reavaliacao_abre_prazo_novo_de_ciencia(sync_permissions):
    """Sem re-carimbar data_liberacao_ciencia, a ciência nasceria vencida e o
    avaliado perderia a chance de se manifestar sobre o resultado da reavaliação."""
    avaliacao = _em_reavaliacao(dias_atras_liberacao=10)
    avaliacao.expirar_reavaliacao()
    avaliacao.refresh_from_db()
    assert avaliacao.prazo_ciencia_vencido() is False


def test_expirar_reavaliacao_finaliza_recursos_em_aberto(sync_permissions):
    avaliacao = _em_reavaliacao(dias_atras_liberacao=10)
    recurso = RecursoAvaliacao.objects.create(
        avaliacao=avaliacao,
        texto_recurso='Discordo da pontuação.',
        situacao=RecursoAvaliacao.EM_REAVALIACAO,
        data_cadastro_recurso=datetime.now(),
    )
    avaliacao.expirar_reavaliacao()
    recurso.refresh_from_db()
    assert recurso.situacao == RecursoAvaliacao.FINALIZADO
    assert recurso.data_conclusao_reavaliacao is not None
    assert 'prazo' in recurso.texto_conclusao_reavaliacao


def test_expirar_reavaliacao_idempotente(sync_permissions):
    avaliacao = _em_reavaliacao(dias_atras_liberacao=10)
    assert avaliacao.expirar_reavaliacao() is True
    avaliacao.refresh_from_db()
    assert avaliacao.expirar_reavaliacao() is False


def test_expirar_reavaliacao_nao_vencida_nao_tramita(sync_permissions):
    avaliacao = _em_reavaliacao(dias_atras_liberacao=0)
    assert avaliacao.expirar_reavaliacao() is False
    avaliacao.refresh_from_db()
    assert avaliacao.situacao == Avaliacao.REAVALIACAO


def test_expirar_reavaliacao_persiste_estado_com_falha_de_notificacao(sync_permissions, monkeypatch):
    avaliacao = _em_reavaliacao(dias_atras_liberacao=10)

    def _falhar(self):
        raise RuntimeError('falha no envio de e-mail')

    monkeypatch.setattr(Avaliacao, '_notificar_expiracao_reavaliacao', _falhar)
    assert avaliacao.expirar_reavaliacao() is True
    avaliacao.refresh_from_db()
    assert avaliacao.situacao == Avaliacao.AGUARDANDO_CIENCIA_RESULTADO


def test_manifestacao_reavaliacao_html_expirada(sync_permissions):
    avaliacao = _em_reavaliacao(dias_atras_liberacao=10)
    avaliacao.expirar_reavaliacao()
    avaliacao.refresh_from_db()
    assert 'não houve manifestação no prazo' in avaliacao.manifestacao_reavaliacao_html()


def test_manifestacao_reavaliacao_html_vazia_sem_expiracao(sync_permissions):
    avaliacao = _em_reavaliacao(dias_atras_liberacao=0)
    assert avaliacao.manifestacao_reavaliacao_html() == ''


# ---------------------------------------------------------------------------
# Relógios do ciclo (bugs de carimbo)
# ---------------------------------------------------------------------------


def test_concluir_preenchimento_para_reavaliacao_carimba_data_de_reavaliacao(sync_permissions):
    """Ao devolver a avaliação editada ao avaliador, o relógio que passa a valer é o
    da reavaliação. Carimbar só data_liberacao_avaliacao deixava o prazo apontando
    para o recurso original, já vencido."""
    avaliacao = _em_edicao(dias_atras_liberacao=0)
    avaliado = avaliacao.progressao.avaliado
    avaliacao.data_liberacao_reavaliacao = _dias_atras(365)
    avaliacao.save()

    avaliacao.concluir_preenchimento_avaliacao(_request(avaliado.get_user()))

    avaliacao.refresh_from_db()
    assert avaliacao.situacao == Avaliacao.REAVALIACAO
    assert avaliacao.prazo_reavaliacao_vencido() is False


def test_finalizar_reavaliacao_carimba_data_de_ciencia(sync_permissions):
    """Mesmo motivo, no outro sentido: concluída a reavaliação, o avaliado precisa de
    um prazo de ciência novo, não do que sobrou da ciência anterior."""
    avaliacao = _em_reavaliacao(dias_atras_liberacao=0)
    avaliador = avaliacao.avaliadores.first()

    avaliacao.finalizar_reavaliacao(_request(avaliador.get_user(), texto_conclusao_reavaliacao='Mantida a pontuação.'))

    avaliacao.refresh_from_db()
    assert avaliacao.situacao == Avaliacao.AGUARDANDO_CIENCIA_RESULTADO
    assert avaliacao.prazo_ciencia_vencido() is False


# ---------------------------------------------------------------------------
# Comando agendado
# ---------------------------------------------------------------------------


def test_command_processa_edicao_reavaliacao_vencida(sync_permissions):
    vencida = _em_edicao(dias_atras_liberacao=10)
    no_prazo = _em_edicao(dias_atras_liberacao=0)

    call_command('processar_prazos_avaliacao')

    vencida.refresh_from_db()
    no_prazo.refresh_from_db()
    assert vencida.situacao == Avaliacao.CONCLUIDA
    assert vencida.edicao_reavaliacao_expirada is True
    assert no_prazo.situacao == Avaliacao.EDITACAO_PARA_REAVALIACAO


def test_command_processa_reavaliacao_vencida(sync_permissions):
    vencida = _em_reavaliacao(dias_atras_liberacao=10)
    no_prazo = _em_reavaliacao(dias_atras_liberacao=0)

    call_command('processar_prazos_avaliacao')

    vencida.refresh_from_db()
    no_prazo.refresh_from_db()
    assert vencida.situacao == Avaliacao.AGUARDANDO_CIENCIA_RESULTADO
    assert vencida.reavaliacao_expirada is True
    assert no_prazo.situacao == Avaliacao.REAVALIACAO


def test_command_continua_lote_apos_falha_de_notificacao(sync_permissions, monkeypatch):
    a1 = _em_edicao(dias_atras_liberacao=10)
    a2 = _em_edicao(dias_atras_liberacao=10)

    def _falhar(self):
        raise RuntimeError('falha no envio de e-mail')

    monkeypatch.setattr(Avaliacao, '_notificar_expiracao_edicao_reavaliacao', _falhar)
    call_command('processar_prazos_avaliacao')

    a1.refresh_from_db()
    a2.refresh_from_db()
    assert a1.situacao == Avaliacao.CONCLUIDA
    assert a2.situacao == Avaliacao.CONCLUIDA


# ---------------------------------------------------------------------------
# Migração de carimbo dos relógios (backlog já parado)
# ---------------------------------------------------------------------------


class TestMigracaoCarimbarRelogios:
    """Sem o carimbo, o backlog parado nasceria sem relógio e continuaria parado —
    justamente o caso do chamado 10625."""

    class _AppsFalso:
        """Entrega o modelo atual no lugar do histórico.

        `carimbar_relogios` só usa ORM básico (`filter`/`update`); o pytest do SUAP roda
        com `--no-migrations`, então não há estado histórico disponível.
        """

        def get_model(self, app_label, model_name):
            assert (app_label, model_name.lower()) == ('progressao_docente', 'avaliacao')
            return Avaliacao

    def test_carimba_edicao_para_reavaliacao_sem_data(self, sync_permissions):
        avaliacao = _em_edicao(dias_atras_liberacao=None)

        migracao.carimbar_relogios(self._AppsFalso(), None)

        avaliacao.refresh_from_db()
        assert avaliacao.data_liberacao_edicao_reavaliacao is not None
        assert avaliacao.prazo_edicao_reavaliacao_vencido() is False

    def test_reinicia_reavaliacao_com_data_antiga(self, sync_permissions):
        """Um prazo de reavaliação herdado do recurso original venceria já na primeira
        varredura, tirando a avaliação do avaliador sem aviso."""
        avaliacao = _em_reavaliacao(dias_atras_liberacao=365)

        migracao.carimbar_relogios(self._AppsFalso(), None)

        avaliacao.refresh_from_db()
        assert avaliacao.prazo_reavaliacao_vencido() is False

    def test_nao_toca_em_outras_situacoes(self, sync_permissions):
        avaliacao = _criar_avaliacao(situacao=Avaliacao.EM_AVALIACAO)

        migracao.carimbar_relogios(self._AppsFalso(), None)

        avaliacao.refresh_from_db()
        assert avaliacao.data_liberacao_edicao_reavaliacao is None
        assert avaliacao.data_liberacao_reavaliacao is None


# ---------------------------------------------------------------------------
# Contagem regressiva exibida no admin
# ---------------------------------------------------------------------------


class TestTempoRestanteSegueAConfiguracao:
    """As colunas de tempo restante liam as constantes de classe (30/10/2), enquanto o
    trâmite automático lê a ConfiguracaoProgressaoDocente. Com o prazo agora sendo
    aplicado, a contagem exibida não pode divergir da que expira a etapa.

    Liberada agora, uma etapa de N dias mostra N: o `+ 1` da contagem inclui o dia
    corrente, e a fração de segundo já decorrida consome o dia final."""

    PRAZO_CONFIGURADO = 9

    @pytest.fixture
    def config(self):
        ConfiguracaoProgressaoDocente = apps.get_model('progressao_docente', 'ConfiguracaoProgressaoDocente')
        return ConfiguracaoProgressaoDocente.objects.create(
            descricao='CONFIG_EMAILS_TEMPOS',
            tempo_preenchimento=self.PRAZO_CONFIGURADO,
            tempo_avaliacao=self.PRAZO_CONFIGURADO,
            tempo_ciencia=self.PRAZO_CONFIGURADO,
            tempo_adicao_edicao=self.PRAZO_CONFIGURADO,
            tempo_reavaliacao=self.PRAZO_CONFIGURADO,
        )

    def test_preenchimento(self, sync_permissions, config):
        avaliacao = _criar_avaliacao(
            situacao=Avaliacao.AGUARDANDO_PREENCHIMENTO,
            data_liberacao_preenchimento=_dias_atras(0),
        )
        assert avaliacao.get_tempo_restante_preenchimento == self.PRAZO_CONFIGURADO

    def test_avaliacao(self, sync_permissions, config):
        avaliacao = _criar_avaliacao(
            situacao=Avaliacao.EM_AVALIACAO,
            data_liberacao_avaliacao=_dias_atras(0),
        )
        assert avaliacao.get_tempo_restante_avaliacao == self.PRAZO_CONFIGURADO

    def test_reavaliacao(self, sync_permissions, config):
        avaliacao = _em_reavaliacao(dias_atras_liberacao=0)
        assert avaliacao.get_tempo_restante_reavaliacao == self.PRAZO_CONFIGURADO

    def test_edicao_para_reavaliacao(self, sync_permissions, config):
        avaliacao = _em_edicao(dias_atras_liberacao=0)
        assert avaliacao.get_tempo_restante_edicao_reavaliacao == self.PRAZO_CONFIGURADO

    def test_sem_data_de_liberacao_nao_ha_contagem(self, sync_permissions, config):
        avaliacao = _em_edicao(dias_atras_liberacao=None)
        assert avaliacao.get_tempo_restante_edicao_reavaliacao is None

    def test_prazo_estourado_fica_negativo(self, sync_permissions, config):
        # sinalizado, e não saturado em 0: é assim que a coluna "Prazo" já contava, e as duas
        # precisam concordar (o admin é quem traduz o negativo para "prazo vencido há N dias")
        avaliacao = _em_edicao(dias_atras_liberacao=365)
        assert avaliacao.get_tempo_restante_edicao_reavaliacao < 0


class TestColunasDeTempoNoAdmin:
    """As colunas checavam o contador errado (copy-paste): a de preenchimento decidia pelo
    contador da avaliação e, com este zerado, imprimia "Restam None dia(s)"."""

    def _admin(self):
        from django.contrib.admin.sites import AdminSite

        from progressao_docente.admin import AvaliacaoAdmin

        return AvaliacaoAdmin(Avaliacao, AdminSite())

    def test_preenchimento_sem_data_e_avaliacao_estourada(self, sync_permissions):
        avaliacao = _criar_avaliacao(
            situacao=Avaliacao.AGUARDANDO_PREENCHIMENTO,
            data_liberacao_avaliacao=_dias_atras(365),
        )
        assert avaliacao.get_tempo_restante_preenchimento is None
        assert avaliacao.get_tempo_restante_avaliacao < 0  # etapa da avaliação vencida há muito
        assert self._admin().get_tempo_restante_preenchimento(avaliacao) == 'Informação indisponível'

    def test_preenchimento_com_data(self, sync_permissions):
        avaliacao = _criar_avaliacao(
            situacao=Avaliacao.AGUARDANDO_PREENCHIMENTO,
            data_liberacao_preenchimento=_dias_atras(0),
        )
        assert 'dia(s)' in self._admin().get_tempo_restante_preenchimento(avaliacao)

    def test_edicao_para_reavaliacao_tem_coluna_propria(self, sync_permissions):
        avaliacao = _em_edicao(dias_atras_liberacao=0)
        assert 'dia(s)' in self._admin().get_tempo_restante_edicao_reavaliacao(avaliacao)

    def test_edicao_para_reavaliacao_sem_data(self, sync_permissions):
        avaliacao = _em_edicao(dias_atras_liberacao=None)
        assert self._admin().get_tempo_restante_edicao_reavaliacao(avaliacao) == 'Informação indisponível'


# ---------------------------------------------------------------------------
# Configuração com prazo NULL (achado do code-review do !18905)
# ---------------------------------------------------------------------------


class TestPrazoNuloNaConfiguracao:
    """Os cinco prazos são `null=True` na ConfiguracaoProgressaoDocente. `tempo_adicao_edicao`
    era campo morto até este MR, então a linha CONFIG_EMAILS_TEMPOS de produção provavelmente
    tem NULL nele — e `timedelta(days=None)` aborta o lote inteiro do cron."""

    @pytest.fixture
    def config_com_nulos(self):
        ConfiguracaoProgressaoDocente = apps.get_model('progressao_docente', 'ConfiguracaoProgressaoDocente')
        return ConfiguracaoProgressaoDocente.objects.create(
            descricao='CONFIG_EMAILS_TEMPOS',
            tempo_preenchimento=30,
            tempo_avaliacao=10,
            tempo_ciencia=None,
            tempo_adicao_edicao=None,
            tempo_reavaliacao=None,
        )

    def test_data_limite_nao_estoura_com_prazo_nulo(self, sync_permissions, config_com_nulos):
        avaliacao = _em_edicao(dias_atras_liberacao=0)
        assert avaliacao.data_limite_etapa_atual() is not None

    def test_prazo_nulo_cai_no_padrao(self, sync_permissions, config_com_nulos):
        avaliacao = _em_edicao(dias_atras_liberacao=0)
        # padrão de tempo_adicao_edicao é 2
        assert avaliacao.dias_restantes_etapa_atual() == 2

    def test_command_nao_aborta_o_lote_com_prazo_nulo(self, sync_permissions, config_com_nulos):
        vencida = _em_edicao(dias_atras_liberacao=10)

        call_command('processar_prazos_avaliacao')

        vencida.refresh_from_db()
        assert vencida.situacao == Avaliacao.CONCLUIDA


# ---------------------------------------------------------------------------
# Permissão de preparar_edicao_reavaliacao (achado do code-review do !18905)
# ---------------------------------------------------------------------------


class TestPermissaoPrepararEdicaoReavaliacao:
    """A guarda comparava `processo.avaliado.get_vinculo()` com uma variável que recebia esse
    mesmo valor — sempre True. Com o relógio agora disparando na reabertura, um terceiro
    conseguia forçar a conclusão automática do processo alheio."""

    def _avaliacao_em_ciencia(self):
        return _criar_avaliacao(
            situacao=Avaliacao.AGUARDANDO_CIENCIA_RESULTADO,
            situacao_processo=ProgressaoDocente.AGUARDANDO_CIENCIA_RESULTADO,
            data_liberacao_ciencia=_dias_atras(0),
        )

    def test_terceiro_nao_reabre_processo_alheio(self, sync_permissions):
        from django.core.exceptions import PermissionDenied

        from progressao_docente.views import preparar_edicao_reavaliacao

        avaliacao = self._avaliacao_em_ciencia()
        with pytest.raises(PermissionDenied):
            preparar_edicao_reavaliacao(_request(ServidorFactory().get_user()), avaliacao.pk)

        avaliacao.refresh_from_db()
        assert avaliacao.situacao == Avaliacao.AGUARDANDO_CIENCIA_RESULTADO
        assert avaliacao.data_liberacao_edicao_reavaliacao is None

    def test_avaliado_reabre_o_proprio_processo(self, sync_permissions):
        from progressao_docente.views import preparar_edicao_reavaliacao

        avaliacao = self._avaliacao_em_ciencia()
        resposta = preparar_edicao_reavaliacao(_request(avaliacao.progressao.avaliado.get_user()), avaliacao.pk)

        assert resposta.status_code == 302
        avaliacao.refresh_from_db()
        assert avaliacao.situacao == Avaliacao.EDITACAO_PARA_REAVALIACAO
        assert avaliacao.data_liberacao_edicao_reavaliacao is not None

    def test_reentrada_nao_reinicia_o_relogio(self, sync_permissions):
        """Voltar à URL já estando em edição não pode renovar o prazo — seria um jeito de
        adiar a etapa indefinidamente."""
        from progressao_docente.views import preparar_edicao_reavaliacao

        avaliacao = _em_edicao(dias_atras_liberacao=1)
        liberacao_original = avaliacao.data_liberacao_edicao_reavaliacao

        resposta = preparar_edicao_reavaliacao(_request(avaliacao.progressao.avaliado.get_user()), avaliacao.pk)

        assert resposta.status_code == 302
        avaliacao.refresh_from_db()
        assert avaliacao.data_liberacao_edicao_reavaliacao == liberacao_original


# ---------------------------------------------------------------------------
# Convenção única das contagens regressivas (achado do code-review do !18905)
# ---------------------------------------------------------------------------


def test_contagens_regressivas_concordam(sync_permissions):
    """`_dias_restantes_da_etapa` (colunas "Tempo para ...") e `dias_restantes_etapa_atual`
    (coluna "Prazo") descreviam a mesma etapa com um dia de diferença."""
    # liberação no fim do dia anterior: a diferença pura de datas e a de datetimes+1
    # discordavam exatamente nesse formato
    avaliacao = _em_edicao(dias_atras_liberacao=1)
    avaliacao.data_liberacao_edicao_reavaliacao = avaliacao.data_liberacao_edicao_reavaliacao.replace(hour=23, minute=59)
    avaliacao.save()
    assert avaliacao.get_tempo_restante_edicao_reavaliacao == avaliacao.dias_restantes_etapa_atual()


def test_coluna_do_admin_nao_diz_restam_zero_dias(sync_permissions):
    from django.contrib.admin.sites import AdminSite

    from progressao_docente.admin import AvaliacaoAdmin

    avaliacao = _em_edicao(dias_atras_liberacao=365)
    texto = AvaliacaoAdmin(Avaliacao, AdminSite()).get_tempo_restante_edicao_reavaliacao(avaliacao)
    assert 'Restam 0' not in texto
    assert 'vencido' in texto.lower()
