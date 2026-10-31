"""Smoke das telas de consulta e dos documentos do RSC que os fluxos só alcançam por clique ou não alcançam.

Cada rota é aberta pela CPPD (que vê todos os processos) sobre um processo já enviado, e a asserção é o que
ela entrega: o texto da tela ou do documento, o caminho do arquivo no visualizador, ou o arquivo baixado (PDF mesclado,
ZIP, planilha). ``processos_pagamento_*`` e
``popup_avaliacao_pagamento_avaliador`` não têm template próprio e caem no ``default.html``: só o título e o
filtro aparecem, e o teste afirma isso, que é o comportamento atual.
"""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest
from playwright.sync_api import Page

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

# (rota, o que a resposta precisa trazer: texto da tela ou tipo do arquivo). Sob teste o ``@documento`` devolve o
# HTML que viraria PDF, então os documentos também se afirmam pelo texto.
CASOS = [
    ('/rsc/requerimento_pdf/{processo}/', 'Docente RSC Avaliado'),
    ('/rsc/formulario_pontuacao_pdf/{processo}/', 'RECONHECIMENTO DE SABERES E COMPETÊNCIAS - RSC-II'),
    ('/rsc/relatorio_descritivo_pdf/{processo}/', 'Descrição do comprovante'),
    ('/rsc/documentos_anexados_pdf/{processo}/', 'comprovante.pdf'),
    ('/rsc/imprimir_documentos_pdf/{reprovado}/', 'RESULTADO FINAL DA AVALIAÇÃO'),
    ('/rsc/gerar_processo_completo/{processo}/', 'application/pdf'),
    ('/rsc/download_arquivos/{processo}/', 'arquivos_processo_'),
    ('/rsc/relatorio_descritivo/{processo}/', 'Descrição do comprovante'),
    ('/rsc/quadro_resumo_pontuacao_requerida/{processo}/', 'Critério E2E RSC-II'),
    ('/rsc/documentos_preliminares/{processo}/', 'Concessão da última RT'),
    ('/rsc/visualizar_arquivo_pdf/{arquivo}/', '{arquivo_diretorio}'),
    ('/rsc/visualizar_arquivo_exigido_pdf/{exigido}/', '{exigido_diretorio}'),
    ('/rsc/dashboard/', 'Painel RSC'),
    ('/rsc/relatorio_situacao/', 'Situação dos processos'),
    ('/rsc/relatorio_situacao/?xls=1', XLSX),
    ('/rsc/processos_pagamento_avaliador_interno/', 'Processos para Pagamento de Avaliadores Internos'),
    ('/rsc/processos_pagamento_avaliador_externo/', 'Processos para Pagamento de Avaliadores Externos'),
    ('/rsc/popup_avaliacao_pagamento_avaliador/{avaliador}/', 'Avaliações para Pagamento do Avaliador'),
]


@pytest.fixture
def alvos(rsc_seed: dict, processo_rsc: Callable[..., Any], banca: Callable[..., tuple[Any, Any]]) -> SimpleNamespace:
    """Processo enviado à CPPD e, para o despacho final, um reprovado pela banca (o deferido exige a data de retroatividade)."""
    from rh.models import Avaliador
    from rsc.models import Avaliacao, ProcessoAvaliador, ProcessoRSC

    processo = processo_rsc(ProcessoRSC.STATUS_AGUARDANDO_VALIDACAO_CPPD)
    reprovado = processo_rsc(ProcessoRSC.STATUS_REPROVADO)
    _, avaliacao = banca(reprovado, status=ProcessoAvaliador.AVALIACAO_FINALIZADA)
    Avaliacao.objects.filter(pk=avaliacao.pk).update(status=Avaliacao.INDEFERIDA, motivo_indeferimento='Pontuação insuficiente.')
    return SimpleNamespace(
        processo=processo.pk,
        reprovado=reprovado.pk,
        arquivo=processo.arquivo_set.first().encrypted_pk,
        arquivo_diretorio=processo.arquivo_set.first().diretorio,
        exigido=processo.arquivosexigidos_set.first().encrypted_pk,
        exigido_diretorio=processo.arquivosexigidos_set.first().diretorio,
        avaliador=Avaliador.objects.get(vinculo=rsc_seed['avaliador'].get_vinculo()).pk,
    )


@pytest.mark.parametrize(('rota', 'esperado'), CASOS, ids=[caso[0] for caso in CASOS])
def test_rota_entrega_o_conteudo(logado_rsc: Callable[[str], Page], alvos: SimpleNamespace, rota: str, esperado: str) -> None:
    tela = Tela(logado_rsc('membro'))
    url = rota.format(**vars(alvos))
    resposta = tela.buscar(url)
    assert resposta.status == 200, f'{url}: HTTP {resposta.status}: {resposta.text()[:500]}'
    tipo = resposta.headers.get('content-type', '')
    esperado = esperado.format(**vars(alvos))
    if esperado in ('application/pdf', XLSX):
        assert tipo.startswith(esperado), f'{url}: esperava {esperado}, veio {tipo}'
    elif esperado == 'arquivos_processo_':
        assert esperado in resposta.headers.get('content-disposition', ''), f'{url}: sem o ZIP do processo'
    else:
        assert esperado in resposta.text(), f'{url}: {esperado!r} ausente'
