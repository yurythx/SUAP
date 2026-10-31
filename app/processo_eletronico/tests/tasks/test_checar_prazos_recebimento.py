"""Recebimento automático, pelo comando, dos processos com prazo de recebimento vencido."""

from datetime import timedelta
from io import StringIO

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.utils import timezone

from comum.models import Configuracao
from processo_eletronico.models import PrazoRecebimentoProcesso, Processo, Tramite
from processo_eletronico.tests.factories import ApensamentoFactory, ApensamentoProcessoFactory, ProcessoFactory, TramiteFactory
from rh.models import Setor
from rh.tests.factories import ServidorFactory, SetorFactory

pytestmark = pytest.mark.django_db
COMANDO = 'processo_eletronico_checar_prazos_recebimento'


def test_processos_apensados_com_prazo_vencido_sao_recebidos_sem_interromper_o_comando(sync_permissions: None, setor_com_siorg: Setor) -> None:
    """O recebimento do primeiro já recebe o apensado; o segundo prazo não pode recebê-lo de novo (#17774)."""
    cache.clear()
    Configuracao.objects.create(app='processo_eletronico', chave='prazo_recebimento_processo', valor='1')
    remetente = ServidorFactory(setor=setor_com_siorg)
    destinatario = ServidorFactory(setor=SetorFactory()).get_vinculo()
    apensamento = ApensamentoFactory()
    prazos = []
    for _ in range(2):
        # Sigiloso: o trâmite vai direto à pessoa, que é quem o comando registra como recebedora.
        processo = ProcessoFactory(setor_criacao=setor_com_siorg, usuario_gerador=remetente.get_user(), nivel_acesso=Processo.NIVEL_ACESSO_PRIVADO)
        processo.interessados.add(destinatario)  # o post_save do NUP 17 exige um interessado
        ApensamentoProcessoFactory(apensamento=apensamento, processo=processo)
        tramite = TramiteFactory(
            processo=processo,
            remetente_setor=setor_com_siorg,
            remetente_vinculo=remetente.get_vinculo(),
            destinatario_vinculo=destinatario,
        )
        prazos.append(PrazoRecebimentoProcesso.objects.create(tramite=tramite, limite=timezone.now() - timedelta(days=1)))

    call_command(COMANDO, stdout=StringIO())

    tramites = Tramite.objects.filter(prazorecebimentoprocesso__in=prazos)
    assert sorted(tramites.values_list('recebido_por', flat=True)) == [destinatario.pk, destinatario.pk]
    assert PrazoRecebimentoProcesso.objects.filter(pk__in=[p.pk for p in prazos], decorrido=True).count() == len(prazos)
