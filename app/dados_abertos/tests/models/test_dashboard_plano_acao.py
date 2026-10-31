"""Testes da aba Plano de Ação do dashboard do PDA."""

from types import SimpleNamespace

from django.template.loader import render_to_string

PENDENCIAS = ('sem_recurso', 'sem_ckan', 'prazo_vencido', 'sem_responsavel', 'sem_prazo')


def _relacao(**atributos: object) -> SimpleNamespace:
    """Relação PDA x base como ``montar_dados_bases_pda`` entrega à aba: sem prazo e nunca sincronizada."""
    padrao = {
        'pk': 1,
        'base_dados_id': 1,
        'base_dados': SimpleNamespace(titulo='Contratos', id_remoto='', sincronizado_em=None),
        'herdada': False,
        'em_revisao': False,
        'submetida_consulta_publica': False,
        'responsavel_abertura': None,
        'unidade_responsavel_abertura': None,
        'meta_prazo_abertura': None,
        'frequencia_atualizacao': None,
        'prazo_status': 'sem_prazo',
        'num_recursos': 2,
        'ckan_status': 'pendente',
        'ckan_status_label': 'Aguardando primeira sincronização',
        'ultima_sincronizacao_ckan': None,
    }
    return SimpleNamespace(**(padrao | atributos))


def _renderizar(bases: list[SimpleNamespace], **pendencias: list[SimpleNamespace]) -> str:
    plano_pendencias = {chave: pendencias.get(chave, []) for chave in PENDENCIAS}
    return render_to_string('dadosabertos/plano_acao.html', {'bases_relacionadas': bases, 'plano_pendencias': plano_pendencias})


def test_publicacao_segue_a_situacao_da_aba_ckan() -> None:
    """Dataset no CKAN com recurso pendente não aparece como sincronizado no Plano de Ação.

    A aba CKAN decide pelo ``ckan_status``, que só é ``sincronizado`` quando o dataset **e** todos os
    recursos subiram. O ``id_remoto`` do dataset sozinho não basta, senão a mesma base fica verde em
    uma aba e em alerta na outra.
    """
    parcial = _relacao(
        base_dados=SimpleNamespace(titulo='Contratos', id_remoto='pkg-1', sincronizado_em=None),
        ckan_status='parcial',
        ckan_status_label='Sincronização parcial',
    )

    html = _renderizar([parcial])

    assert 'Sincronizada com o CKAN' not in html
    assert 'Sincronização parcial' in html


def test_titulo_so_acusa_pendencia_que_os_contadores_mostram() -> None:
    """Base ainda não sincronizada não põe o plano "Com pendências" com os contadores zerados.

    Os contadores da aba são prazo vencido, sem responsável, sem prazo e sem recurso de dados. A
    sincronização é acompanhada na aba CKAN, e a base que passa do prazo sem publicar já entra em
    prazo vencido, que só olha a data.
    """
    nao_sincronizada = _relacao()

    html = _renderizar([nao_sincronizada], sem_ckan=[nao_sincronizada])

    assert 'Com pendências' not in html
    assert 'Em dia' in html
