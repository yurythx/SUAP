"""Substrato da rodada de geração da doc de usuário do ``pafc``.

Esta suíte NÃO é de regressão: ela navega o sistema vivo para *descobrir* o que a doc de
usuário vai afirmar e para capturar as telas. Cada teste é um roteiro de tarefa; a asserção
existe só para a rodada falhar alto quando a tela mudou de forma (senão a doc sairia
descrevendo um passo que já não existe).

O módulo não tem ``features/`` nem ``tests/e2e/`` — o roteiro e o seed foram PROPOSTOS
por este subagente a partir de ``menu.yaml``, ``urls.py`` e ``models.py`` (nada foi colhido
de ``.feature``, e a revisão do MR precisa saber disso).

Papéis: ``servidor`` (grupo ``Servidor`` — concede ``pafc.view_pafc``) e ``admin_pafc``
(grupo ``Administrador de PAFC`` — modelos e solicitações de tramitação).

O seed reproduz o mínimo que as telas navegadas exigem: o domínio de PPC que o PAFC
referencia (Diretriz → ModeloPPC → Solicitação → PPC), o ``ModeloPAFC``, um ``PAFC`` em
**Em elaboração** (a tela principal do acompanhamento) e outro em **Aguardando aprovação
do CONSEPEX** com PPC aprovado (o estado do ad referendum), além da ``Configuracao`` que
marca o setor da secretaria dos conselhos — condição de ``is_secretario_conselho``
(``ppc/models.py:2620``), exigida para solicitar o ad referendum.

Rodar::

    DATABASE_PORT=5432 TEST_DATABASE_NAME=test_suap_doc_e2e \\
        DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest -m doc pafc/tests/doc/
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from django.conf import settings

from djtools.e2e_fixtures import *  # noqa: F403
from djtools.e2e_fixtures import campus, criar_servidores, setor


PAPEIS = {'servidor': '155301', 'admin_pafc': '155302'}

# Matrícula -> (nome, grupos); os dois no setor A1 (sob o campus A0).
SERVIDORES = {
    '155301': ('Servidor PAFC Doc', ['Servidor']),
    '155302': ('Admin PAFC Doc', ['Administrador de PAFC']),
}

DESTINO = Path(settings.BASE_DIR) / 'pafc' / 'docs' / 'usuario'

# A fixture `capturar` é compartilhada (`djtools/e2e_fixtures.py`): viewport, teto do WebP e
# limpeza do destino são os mesmos em todo módulo — só o destino muda.
capturar = capturas(DESTINO)  # noqa: F405


def _criar_dominio(servidor, setor) -> dict:
    """Domínio mínimo de PPC + ModeloPAFC + dois PAFCs, via ORM."""
    from comum.models import Ano, Configuracao
    from edu.models import EstruturaCurso, Modalidade, NaturezaParticipacao
    from pafc.models import ModeloPAFC, PAFC
    from ppc.models import Conteudo, Diretriz, ModeloPPC, ProjetoPedagogicoCurso, Secao, SolicitacaoPPC

    ano = Ano.objects.get_or_create(ano=date.today().year)[0]
    modalidade = Modalidade.objects.get_or_create(descricao='Técnico Integrado')[0]
    natureza = NaturezaParticipacao.objects.get_or_create(descricao='Presencial')[0]

    estrutura, _ = EstruturaCurso.objects.get_or_create(
        descricao='Estrutura de curso doc pafc',
        tipo_avaliacao=EstruturaCurso.TIPO_AVALIACAO_SERIADO,
        criterio_avaliacao=EstruturaCurso.CRITERIO_AVALIACAO_NOTA,
    )

    diretriz, _ = Diretriz.objects.get_or_create(
        descricao='Diretriz doc de usuário (pafc)',
        ano=ano,
        estrutura_curso=estrutura,
        tipo_oferta=modalidade,
        modalidade=natureza,
        qtd_min_periodos=3,
        qtd_max_periodos=6,
        ch_min_curso=2400,
        ch_max_curso=3200,
        ch_min_cc_obrigatorio=1800,
        ch_max_cc_obrigatorio=2400,
        ch_min_cc_optativo=200,
        ch_max_cc_optativo=400,
        ch_min_cc_eletivo=0,
        ch_max_cc_eletivo=100,
        ch_min_pratica=200,
        ch_max_pratica=400,
        ch_min_ac=100,
        ch_max_ac=200,
        ch_min_atpa=0,
        ch_max_atpa=100,
        ch_min_cc_regular=0,
        ch_max_cc_regular=0,
        ch_min_cc_extensao=0,
        ch_max_cc_extensao=0,
        ch_min_cc_tcc=100,
        ch_max_cc_tcc=200,
        equivalencia_hr_ha=0.75,
        equivalencia_hr_credito=0.75,
    )

    modelo_ppc, _ = ModeloPPC.objects.get_or_create(
        descricao='Modelo de PPC doc de usuário (pafc)',
        tipo_oferta=modalidade,
        modalidade=natureza,
        ativo=True,
    )
    secao, _ = Secao.objects.get_or_create(titulo='Identificação do Curso', ordem_exibicao=1, modelo_ppc=modelo_ppc)
    Conteudo.objects.get_or_create(secao=secao, ordem_exibicao=1, texto='Texto do conteúdo do modelo de PPC (pafc).')

    solicitacao, _ = SolicitacaoPPC.objects.get_or_create(
        solicitante=servidor,
        setor_solicitacao=setor,
        tipo_solicitacao=SolicitacaoPPC.TIPO_CRIACAO,
        justificativa='Justificativa da solicitação de criação de PPC (doc de usuário).',
        tipo_oferta=modalidade,
        modalidade=natureza,
        nome_curso='Curso de Exemplo da Doc',
    )

    ppc, _ = ProjetoPedagogicoCurso.objects.get_or_create(
        nome_curso='Curso de Exemplo da Doc',
        modelo_ppc=modelo_ppc,
        diretriz=diretriz,
        solicitacao=solicitacao,
        situacao=ProjetoPedagogicoCurso.APROVADO,
        periodicidade=1,
        ch_curso=3000,
    )

    # Um segundo PPC (nome distinto) para o PAFC dos conselhos: `PAFC.save`
    # (``pafc/models.py:552``) copia o nome do curso do PPC para o PAFC, e a listagem do
    # admin exibe o nome do curso — dois PAFCs com o mesmo nome tornariam a linha ambígua.
    solicitacao_conselho, _ = SolicitacaoPPC.objects.get_or_create(
        solicitante=servidor,
        setor_solicitacao=setor,
        tipo_solicitacao=SolicitacaoPPC.TIPO_CRIACAO,
        justificativa='Justificativa da solicitação de criação de PPC (doc de usuário, conselho).',
        tipo_oferta=modalidade,
        modalidade=natureza,
        nome_curso='Curso de Exemplo da Doc (Conselho)',
    )
    ppc_conselho, _ = ProjetoPedagogicoCurso.objects.get_or_create(
        nome_curso='Curso de Exemplo da Doc (Conselho)',
        modelo_ppc=modelo_ppc,
        diretriz=diretriz,
        solicitacao=solicitacao_conselho,
        situacao=ProjetoPedagogicoCurso.APROVADO,
        periodicidade=1,
        ch_curso=3000,
    )

    modelo_pafc, _ = ModeloPAFC.objects.get_or_create(
        descricao='Modelo de PAFC doc de usuário',
        tipo_oferta=modalidade,
        versao_modelo=ModeloPAFC.VERSAO_PRESENCIAL,
        ativo=True,
    )

    # A secretaria dos conselhos é o setor A1: é o que torna o servidor (no A1)
    # `is_secretario_conselho` — condição para solicitar o ad referendum.
    Configuracao.objects.update_or_create(
        app='ppc',
        chave='setor_secretaria_conselhos',
        defaults={'valor': str(setor.pk), 'descricao': 'Setor da secretaria dos conselhos (doc de usuário)'},
    )

    # `PAFC.save` (``pafc/models.py:541``) resolve o setor do PAFC pela Diretoria Acadêmica
    # do diretor acadêmico no momento da criação — sem a diretoria o save dá
    # ``AttributeError: 'NoneType' object has no attribute 'setor'`` (medido nesta rodada).
    from edu.models import Diretoria

    vinculo = servidor.get_vinculo()
    Diretoria.objects.get_or_create(
        setor=setor,
        tipo=Diretoria.TIPO_DIRETORIA_ACADEMICA,
        defaults={'diretor_academico': vinculo, 'diretor_geral': vinculo},
    )

    pafc_elaboracao, _ = PAFC.objects.get_or_create(
        nome_curso='Curso de Exemplo da Doc',
        modelo=modelo_pafc,
        ppc=ppc,
        setor=setor,
        situacao=PAFC.EM_ELABORACAO,
        numero_vagas_curso=40,
        reitor=servidor,
        pro_reitor_ensino=servidor,
        diretor_geral=servidor,
        diretor_academico=servidor,
    )

    pafc_conselho, _ = PAFC.objects.get_or_create(
        nome_curso='Curso de Exemplo da Doc (Conselho)',
        modelo=modelo_pafc,
        ppc=ppc_conselho,
        setor=setor,
        situacao=PAFC.AGUARDANDO_APROVACAO_CONSEPEX,
        numero_vagas_curso=40,
        reitor=servidor,
        pro_reitor_ensino=servidor,
        diretor_geral=servidor,
        diretor_academico=servidor,
    )
    # `PAFC.atualizar_situacoes` (``pafc/models.py:2934``) regride para **Em solicitação**
    # qualquer PAFC sem portaria da comissão de elaboração vigente — o ad referendum exige
    # a situação de conselho, então a portaria precisa existir (medido nesta rodada).
    from django.core.files.uploadedfile import SimpleUploadedFile

    from pafc.models import DocumentoHibrido

    caminho = Path(settings.BASE_DIR) / 'djtools' / 'new_tests' / 'files' / 'arquivo.pdf'
    with caminho.open('rb') as f:
        conteudo = f.read()
    portaria, _ = DocumentoHibrido.objects.get_or_create(
        tipo=DocumentoHibrido.PORTARIA,
        situacao=DocumentoHibrido.DOCUMENTO_FINALIZADO,
        defaults={'arquivo': SimpleUploadedFile('portaria.pdf', conteudo)},
    )
    pafc_conselho.portaria_comissao_elaboracao_vigente = portaria
    pafc_conselho.save(update_fields=['portaria_comissao_elaboracao_vigente'])

    return {
        'modelo_ppc': modelo_ppc,
        'solicitacao': solicitacao,
        'ppc': ppc,
        'modelo_pafc': modelo_pafc,
        'pafc_elaboracao': pafc_elaboracao,
        'pafc_conselho': pafc_conselho,
    }


@pytest.fixture(scope='session')
def doc_seed(e2e_seed):
    """Usuários da doc + domínio do PAFC, antes da 1ª request."""
    from rh.models import Servidor

    setor_a1 = setor('A1', campus('A0'))
    criar_servidores(setor_a1, SERVIDORES)
    return _criar_dominio(Servidor.objects.get(matricula=PAPEIS['servidor']), setor_a1)


@pytest.fixture
def logado_doc(logado, doc_seed):
    """``(papel) -> Page`` autenticada como o usuário daquele papel de ``PAPEIS``."""

    def _logado(papel: str):
        assert papel in PAPEIS, f'papel desconhecido: {papel}; declare em PAPEIS'
        return logado(PAPEIS[papel])

    return _logado
