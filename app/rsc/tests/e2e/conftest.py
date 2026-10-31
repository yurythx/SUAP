"""RSC docente: seed por factories com docente, CPPD e banca; processo novo por teste.

Os arquivos são independentes: o processo é estado consumível (cada transição o tira da situação que
o teste seguinte esperaria), então ``processo_rsc`` monta um novo, na situação pedida, com os
comprovantes e documentos preliminares gravados no storage. Papéis e avaliadores nascem no seed de
sessão, antes da primeira request, por causa do cache de permissão por processo. Sem relógio
congelado: as datas de referência ficam no passado fixo e os prazos da banca contam de hoje.

Rodar::

    TEST_DATABASE_NAME=test_suap_e2e DJANGO_SETTINGS_MODULE=suap.settings_test \\
        uv run pytest rsc/tests/e2e --create-db
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Page

from djtools.e2e_fixtures import *  # noqa: F403
from djtools.e2e_fixtures import campus, servidor_com_login

PAPEIS = {
    'docente': '7717101',
    'membro': '7717102',
    'avaliador': '7717104',
    'reserva': '7717105',
}
# matrícula -> (nome, grupos, docente)
SERVIDORES = {
    '7717101': ('Docente RSC Avaliado', ['Servidor'], True),
    '7717102': ('Membro CPPD RSC', ['Servidor', 'Membro CPPD'], False),
    '7717104': ('Avaliadora RSC Interna', ['Servidor', 'Avaliador Interno'], True),
    '7717105': ('Avaliador RSC Reserva', ['Servidor', 'Avaliador Interno'], True),
}
NIVEIS = ('RSC-I', 'RSC-II', 'RSC-III')

ROTAS_DISPENSADAS = {
    '/rsc/imprimir_processo/<int:processo_id>/': (
        'O template é um esqueleto de exemplo (action-bar com "suboption 1/2/3"), sem nenhum dado do processo: não há tela a afirmar. Achado do MR.'
    ),
    '/rsc/atualizar_processo_eletronico_rsc/': 'Troca o processo eletrônico vinculado; exige processo eletrônico real (TipoProcesso 517), fora do seed.',
    '/rsc/gerar_processo_eletronico/<int:processo_id>/': 'Abre processo eletrônico com TipoProcesso id=517 fixo, que o seed não tem.',
    '/rsc/clonar_processo_rsc_mantendo_mesmo_processo_eletronico/<int:processo_id>/': (
        'Clona carregando o processo eletrônico do original; sem processo eletrônico no seed, o caminho é o mesmo do `clonar_processo_rsc`, coberto.'
    ),
    '/rsc/enviar_processo_rsc/<int:processo_id>/': (
        'Exige assinatura digital do requerimento (SuapAssinaturaForm) e abre processo eletrônico com TipoProcesso id=517; '
        'o envio sem processo eletrônico é coberto por `salvar_processo_rsc` com `enviar_processo`.'
    ),
    '/rsc/finalizar_processo/<int:processo_id>/': (
        'Gera os PDFs e anexa ao processo eletrônico com TipoDocumento id=5 fixo; sem processo eletrônico no seed a view cai '
        'no `except` e não finaliza.'
    ),
}


@pytest.fixture(scope='session')
def rsc_seed(e2e_seed: None) -> dict[str, Any]:
    from comum.tests.factories import PessoaTelefoneFactory
    from rh.models import Avaliador
    from rh.tests.factories import AvaliadorFactory, BancoFactory, SituacaoFactory
    from rsc.tests.factories import ConfiguracaoRSCFactory, CriterioFactory, DiretrizFactory, ParametroPagamentoFactory, TipoRscFactory

    setor = campus('E2ERSC', 'Campus RSC E2E')
    permanente = SituacaoFactory()
    servidores = {}
    for matricula, (nome, grupos, docente) in SERVIDORES.items():
        servidores[matricula] = servidor_com_login(
            matricula, setor, grupos=grupos, staff=True, pessoa_fisica__nome=nome, eh_docente=docente, situacao=permanente
        )
    banco = BancoFactory()
    for papel in ('avaliador', 'reserva'):
        servidor = servidores[PAPEIS[papel]]
        if not Avaliador.objects.filter(vinculo=servidor.get_vinculo()).exists():
            AvaliadorFactory(
                vinculo=servidor.get_vinculo(),
                matricula_siape=servidor.matricula,
                email_contato=f'{servidor.matricula}@e2e.rsc',
                banco=banco,
                numero_agencia='1234-5',
                tipo_conta=Avaliador.TIPOCONTA_CONTACORRENTE,
                numero_conta='12345-6',
            )
            PessoaTelefoneFactory(pessoa=servidor.pessoa_fisica.pessoa_ptr)
    ConfiguracaoRSCFactory()
    if not ParametroPagamentoFactory._meta.model.objects.exists():
        ParametroPagamentoFactory()
    criterios = {}
    for nivel in NIVEIS:
        tipo = TipoRscFactory(nome=nivel, categoria='docente')
        criterio = CriterioFactory._meta.model.objects.filter(diretriz__tipo_rsc=tipo, nome=f'Critério E2E {nivel}').first()
        criterios[nivel] = criterio or CriterioFactory(
            diretriz=DiretrizFactory(tipo_rsc=tipo, nome=f'Diretriz E2E {nivel}'), nome=f'Critério E2E {nivel}'
        )
    return {
        'setor': setor,
        'criterios': criterios,
        **{papel: servidores[matricula] for papel, matricula in PAPEIS.items()},
    }


@pytest.fixture
def logado_rsc(logado: Callable[[str], Page], rsc_seed: dict[str, Any]) -> Callable[[str], Page]:
    def _logado(papel: str) -> Page:
        assert papel in PAPEIS, f'papel desconhecido: {papel}'
        return logado(PAPEIS[papel])

    return _logado


def _gravar_pdf(diretorio: str) -> None:
    from django.conf import settings
    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage

    from djtools.e2e_ui import ARQUIVOS

    default_storage.save(diretorio, ContentFile(Path(settings.BASE_DIR, ARQUIVOS['pdf']).read_bytes()))


@pytest.fixture
def processo_rsc(rsc_seed: dict[str, Any]) -> Callable[..., Any]:
    """``(status, nivel='RSC-II') -> ProcessoRSC`` do docente do seed, com um comprovante por nível e os 3 preliminares."""
    from rsc.tests.factories import ArquivoFactory, ArquivosExigidosFactory, ProcessoRSCFactory

    def _processo(status: int, nivel: str = 'RSC-II') -> Any:
        criterios = rsc_seed['criterios']
        processo = ProcessoRSCFactory(
            servidor=rsc_seed['docente'],
            tipo_rsc=criterios[nivel].diretriz.tipo_rsc,
            status=status,
            data_concessao_ultima_rt=date(2014, 1, 1),
            data_exercio_carreira=date(2010, 1, 1),
            data_conclusao_titulacao_rsc_pretendido=date(2012, 1, 1),
            pontuacao_pretendida=3,
            pontuacao_pretendida_rsc1=1,
            pontuacao_pretendida_rsc2=1,
            pontuacao_pretendida_rsc3=1,
        )
        for criterio in criterios.values():
            _gravar_pdf(ArquivoFactory(processo=processo, criterio=criterio).diretorio)
        for tipo in (1, 2, 3):
            _gravar_pdf(ArquivosExigidosFactory(processo=processo, tipo=tipo).diretorio)
        return processo

    return _processo


@pytest.fixture
def banca(rsc_seed: dict[str, Any]) -> Callable[..., tuple[Any, Any]]:
    """``(processo, papel='avaliador', status=EM_AVALIACAO) -> (ProcessoAvaliador, Avaliacao)`` com um item por arquivo."""
    from rh.models import Avaliador
    from rsc.models import ProcessoAvaliador
    from rsc.tests.factories import AvaliacaoFactory, AvaliacaoItemFactory, ProcessoAvaliadorFactory

    def _banca(processo: object, papel: str = 'avaliador', status: int = ProcessoAvaliador.EM_AVALIACAO) -> tuple[Any, Any]:
        avaliador = Avaliador.objects.get(vinculo=rsc_seed[papel].get_vinculo())
        processo_avaliador = ProcessoAvaliadorFactory(processo=processo, avaliador=avaliador, status=status)
        avaliacao = AvaliacaoFactory(processo=processo, avaliador=avaliador)
        for arquivo in processo.arquivo_set.all():
            AvaliacaoItemFactory(avaliacao=avaliacao, arquivo=arquivo)
        return processo_avaliador, avaliacao

    return _banca
