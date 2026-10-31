"""Fixtures da documentação de usuário do Processo Eletrônico.

As telas são navegadas de verdade; as capturas vão para ``docs/usuario/`` e permanecem fora
do Git. O seed e os papéis são reutilizados da suíte E2E do módulo.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from django.conf import settings

from djtools.e2e_fixtures import *  # noqa: F403
from processo_eletronico.tests.e2e.conftest import *  # noqa: F403

DESTINO = Path(settings.BASE_DIR) / 'processo_eletronico' / 'docs' / 'usuario'
capturar = capturas(DESTINO)  # noqa: F405


@pytest.fixture(autouse=True)
def limpar_estado_documentacao(estado_processo: None) -> None:
    """Remove efeitos de uma tarefa antes da próxima captura."""
    from processo_eletronico.models import (
        ComentarioProcesso,
        DocumentoDigitalizadoProcesso,
        DocumentoTextoProcesso,
        PrioridadeTramite,
        Processo,
        ProcessosRelacionados,
        SolicitacaoAlteracaoNivelAcesso,
        SolicitacaoCiencia,
        SolicitacaoDespacho,
        SolicitacaoJuntada,
    )

    processos = Processo.objects.filter(numero_protocolo__in=['23001.000001.2019-68', '23001.000002.2019-11'])
    ComentarioProcesso.objects.filter(processo__in=processos).delete()
    DocumentoDigitalizadoProcesso.objects.filter(processo__in=processos).delete()
    DocumentoTextoProcesso.objects.filter(processo__in=processos).delete()
    PrioridadeTramite.objects.filter(tramite__processo__in=processos).delete()
    SolicitacaoCiencia.objects.filter(processo__in=processos).delete()
    SolicitacaoDespacho.objects.filter(processo__in=processos).delete()
    SolicitacaoJuntada.objects.filter(tramite__processo__in=processos).delete()
    SolicitacaoAlteracaoNivelAcesso.objects.filter(processo__in=processos).delete()
    ProcessosRelacionados.objects.filter(processo_origem__in=processos).delete()
    ProcessosRelacionados.objects.filter(processo_alvo__in=processos).delete()
    for processo in processos:
        processo.acompanhantes_processo.clear()


@pytest.fixture
def processo_documentacao(processo_seed: bool) -> Any:
    """Cria (ou reinicia) um processo próprio da documentação, no setor A1, já recebido pelo chefe.

    Finalizar e apensar mudam o processo de um jeito que a limpeza acima não desfaz; por isso
    essas tarefas usam processos à parte, e os dois processos fixos das outras capturas ficam
    intactos. O helper do e2e é idempotente pelo número: reabre o processo a cada rodada.
    """
    from processo_eletronico.models import ApensamentoProcesso, Processo, TipoProcesso
    from processo_eletronico.tests.e2e.conftest import _criar_processo, _vinculo

    tipo = TipoProcesso.objects.get(nome='Acesso à Informação: Demanda do e-SIC')

    def _criar(numero: str) -> Any:
        ApensamentoProcesso.objects.filter(processo__numero_protocolo=numero).delete()
        return _criar_processo(numero, '128002', 'A1', tipo, _vinculo('128001'), True)

    return _criar


@pytest.fixture
def solicitacao_despacho_documentacao(limpar_estado_documentacao: None, processo_seed: bool) -> Any:
    """Cria solicitação pendente para captura do deferimento."""
    from processo_eletronico.models import SolicitacaoDespacho
    from processo_eletronico.tests.e2e.test_03_fluxos_complementares import _processo, _vinculo
    from rh.models import Setor

    processo = _processo('23001.000001.2019-68')
    return SolicitacaoDespacho.objects.create(
        processo=processo,
        despacho_corpo='Despacho criado pela massa de documentação.',
        remetente_setor=Setor.objects.suap().get(sigla='A1'),
        remetente_vinculo=_vinculo('128002'),
        solicitado=_vinculo('128001'),
        destinatario_setor_tramite=Setor.objects.suap().get(sigla='A2'),
    )


@pytest.fixture
def solicitacao_ciencia_documentacao(limpar_estado_documentacao: None, processo_seed: bool) -> Any:
    """Cria solicitação pendente para captura do atendimento da ciência."""
    from datetime import timedelta

    from django.utils.timezone import now
    from processo_eletronico.models import SolicitacaoCiencia
    from processo_eletronico.tests.e2e.test_03_fluxos_complementares import _processo, _usuario, _vinculo

    processo = _processo('23001.000001.2019-68')
    return SolicitacaoCiencia.objects.create(
        processo=processo,
        tramite=processo.ultimo_tramite,
        solicitante=_usuario('128002'),
        solicitado=_vinculo('128003'),
        data_limite_ciencia=now() + timedelta(days=30),
        motivo='Solicitação criada pela massa de documentação.',
        tipo=SolicitacaoCiencia.TIPO_NOTIFICACAO,
    )
