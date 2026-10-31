"""Testes dos predicados que marcam sozinhas as ações do checklist do PDA."""

import datetime

import pytest

from dados_abertos.enums import SituacaoLAI
from dados_abertos.models import BaseDados, PDABaseDados, PlanoDadosAbertos, RecursoDados
from dados_abertos.services import acoes_automaticas_service as acoes


@pytest.fixture
def pda(db):
    plano = PlanoDadosAbertos.objects.create(
        titulo='PDA 2026',
        vigencia_inicio=datetime.date(2026, 1, 1),
        vigencia_fim=datetime.date(2026, 12, 31),
    )
    for nome in ('contratos', 'servidores'):
        base = BaseDados.objects.create(nome=nome, titulo=nome.title())
        PDABaseDados.objects.create(pda=plano, base_dados=base)
    return plano


def _primeira(pda) -> PDABaseDados:
    return pda.bases_relacionadas.order_by('id').first()


@pytest.mark.parametrize(
    ('condicao', 'preparar'),
    [
        (
            'bases_com_recurso',
            lambda rel: RecursoDados.objects.create(dataset=rel.base_dados, nome='csv', formato='CSV', url='https://exemplo.br/a.csv'),
        ),
        (
            'bases_liberadas_lai',
            lambda rel: PDABaseDados.objects.filter(pk=rel.pk).update(situacao_lai=SituacaoLAI.LIBERADO),
        ),
        (
            'bases_sincronizadas_ckan',
            lambda rel: BaseDados.objects.filter(pk=rel.base_dados_id).update(
                id_remoto='pkg-1', sincronizado_em=datetime.datetime(2026, 9, 1, 10, 0)
            ),
        ),
    ],
)
def test_etapa_de_abertura_fecha_com_uma_base(pda, condicao, preparar, monkeypatch):
    """Uma base basta para a ação de Abertura e Publicação, mesmo com a outra ainda pendente.

    A etapa acompanha a abertura, que é incremental: exigir as duas travava o checklist do PDA
    inteiro enquanto uma única base não tivesse recurso, liberação ou sincronização.
    """
    monkeypatch.setattr(RecursoDados, '_download_and_attach_file_from_url', lambda self: None, raising=False)
    predicado = acoes.PREDICADOS[condicao]

    assert predicado(pda) is False

    preparar(_primeira(pda))

    assert predicado(pda) is True
