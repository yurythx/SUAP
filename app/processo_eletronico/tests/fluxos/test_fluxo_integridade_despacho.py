"""Integridade do despacho assinado depois da deduplicação de pessoas (issue 17831).

A assinatura do despacho é um HMAC cuja chave leva o id da pessoa do vínculo assinante no momento da
assinatura. O ``deduplicar_pessoas aplicar`` reaponta ``Vinculo.pessoa`` para a pessoa sobrevivente
(o id antigo fica em ``Vinculo.secret`` e no mapa ``DeduplicacaoPessoa``), e a tela do processo passava
a mostrar como violados os despachos de quem teve a pessoa mesclada — caso típico de bolsista, que tem
um cadastro de aluno e outro de prestador.
"""

from __future__ import annotations

from datetime import date

import pytest
from django.contrib.contenttypes.models import ContentType

from comum.models import Ocupacao, PrestadorServico, Vinculo
from comum.tests.factories import PrestadorServicoFactory
from comum.utils import get_sigla_reitoria
from djtools.utils import get_datetime_now
from processo_eletronico.models import ModeloDespacho, Tramite
from processo_eletronico.tests.factories import ProcessoFactory
from rh.models import DeduplicacaoPessoa, Papel, Setor
from rh.tests.factories import PapelFactory, PessoaFisicaFactory, ServidorFactory, SetorFactory


@pytest.fixture
def processo(sync_permissions, setor_com_siorg):
    SetorFactory(sigla=get_sigla_reitoria(), nome='Reitoria')  # as variáveis do cabeçalho do despacho leem a reitoria
    ModeloDespacho.objects.create(cabecalho='<p>Cabeçalho</p>', rodape='<p>Rodapé</p>')
    autor = ServidorFactory(setor=setor_com_siorg).get_user()
    processo = ProcessoFactory(setor_criacao=setor_com_siorg, usuario_gerador=autor)
    processo.interessados.add(autor.get_vinculo())
    return processo


@pytest.fixture
def bolsista(setor_com_siorg: Setor) -> PrestadorServico:
    """Assinante que não é servidor: bolsista cadastrada como prestadora de serviço."""
    return PrestadorServicoFactory(setor=setor_com_siorg)


def _papel_de_ocupacao(vinculo: Vinculo) -> Papel:
    return PapelFactory(
        servidor=None,
        vinculo=vinculo,
        tipo_papel=Papel.TIPO_PAPEL_OCUPACAO,
        descricao='Bolsista',
        detalhamento='Bolsista',
        data_inicio=date(2026, 1, 1),
        papel_content_type=ContentType.objects.get_for_model(Ocupacao),
        papel_content_id=1,
    )


def _despachar(processo, vinculo: Vinculo, setor: Setor) -> Tramite:
    tramite = Tramite(processo=processo)
    tramite.tramitar_processo(
        remetente_setor=setor,
        remetente_vinculo=vinculo,
        despacho_corpo='<p>Encaminho para providências.</p>',
        destinatario_vinculo=None,
        destinatario_setor=setor,
        papel=_papel_de_ocupacao(vinculo),
    )
    return tramite


def _mesclar_pessoa_do_vinculo(vinculo: Vinculo) -> None:
    """O que o ``deduplicar_pessoas aplicar`` faz com o vínculo da pessoa perdedora."""
    sobrevivente = PessoaFisicaFactory()
    DeduplicacaoPessoa.objects.create(
        pf_id=vinculo.pessoa_id, sobrevivente_id=sobrevivente.pk, acao=DeduplicacaoPessoa.MESCLADA, aplicado_em=get_datetime_now()
    )
    Vinculo.objects.filter(pk=vinculo.pk).update(pessoa=sobrevivente)


def _recarregado(tramite: Tramite) -> Tramite:
    return Tramite.objects.select_related('assinaturatramite__assinatura__vinculo').get(pk=tramite.pk)


def test_despacho_de_bolsista_continua_valido_depois_de_mesclar_a_pessoa(processo, bolsista, setor_com_siorg):
    vinculo = bolsista.get_vinculo()
    tramite = _despachar(processo, vinculo, setor_com_siorg)
    assert _recarregado(tramite).valido

    _mesclar_pessoa_do_vinculo(vinculo)

    assert _recarregado(tramite).valido


def test_despacho_de_usuario_externo_legado_continua_valido_depois_de_mesclar_a_pessoa(processo, bolsista, setor_com_siorg):
    """Vínculo de usuário externo migrado em 2022 tem ``secret`` diferente do id da pessoa: só o mapa da deduplicação acha o id antigo."""
    vinculo = bolsista.get_vinculo()
    Vinculo.objects.filter(pk=vinculo.pk).update(secret=bolsista.pk)
    vinculo.refresh_from_db()
    assert vinculo.secret != vinculo.pessoa_id
    tramite = _despachar(processo, vinculo, setor_com_siorg)

    _mesclar_pessoa_do_vinculo(vinculo)

    assert _recarregado(tramite).valido


def test_despacho_alterado_depois_de_assinado_continua_violado(processo, bolsista, setor_com_siorg):
    vinculo = bolsista.get_vinculo()
    tramite = _despachar(processo, vinculo, setor_com_siorg)
    _mesclar_pessoa_do_vinculo(vinculo)

    Tramite.objects.filter(pk=tramite.pk).update(despacho_corpo='<p>Texto adulterado.</p>')

    assert not _recarregado(tramite).valido
