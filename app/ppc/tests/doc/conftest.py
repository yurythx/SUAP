"""Substrato da rodada de geração da doc de usuário do ``ppc`` (Projeto Pedagógico de Curso).

Esta suíte NÃO é de regressão: ela navega o sistema vivo para *descobrir* o que a doc de
usuário vai afirmar e para capturar as telas. Cada teste é um roteiro de tarefa; a asserção
existe só para a rodada falhar alto quando a tela mudou de forma (senão a doc sairia
descrevendo um passo que já não existe).

O módulo não tem ``features/`` nem ``tests/e2e/`` — o roteiro e o seed foram PROPOSTOS
por este subagente a partir de ``menu.yaml``, ``urls.py`` e ``models.py`` (nada foi colhido
de ``.feature``, e a revisão do MR precisa saber disso).

Papéis: ``servidor`` (grupo ``Servidor`` — é ele que concede quase todas as permissões do
ppc, ver ``bin/scripts/papeis.py``) e ``admin_ppc`` (grupo ``Administrador de PPC``, para os
modelos e as telas de configuração).

O seed de domínio reproduz o mínimo que as telas navegadas precisam: a cadeia
``Diretriz → ModeloPPC (com seções e conteúdos) → SolicitacaoPPC → ProjetoPedagogicoCurso
(com ConteudoPPC)`` e um ``PlanoDisciplina`` com seu modelo. Tudo via ORM; os campos
exigidos foram descobertos rodando e corrigindo (a revisão do MR precisa saber disso).

Rodar::

    DATABASE_PORT=5432 TEST_DATABASE_NAME=test_suap_doc_e2e \\
        DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest -m doc ppc/tests/doc/
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from django.conf import settings

from djtools.e2e_fixtures import *  # noqa: F403
from djtools.e2e_fixtures import campus, criar_servidores, setor


PAPEIS = {'servidor': '155201', 'admin_ppc': '155202'}

# Matrícula -> (nome, grupos); os dois no setor A1 (sob o campus A0).
SERVIDORES = {
    '155201': ('Servidor PPC Doc', ['Servidor']),
    '155202': ('Admin PPC Doc', ['Administrador de PPC']),
}

DESTINO = Path(settings.BASE_DIR) / 'ppc' / 'docs' / 'usuario'

# A fixture `capturar` é compartilhada (`djtools/e2e_fixtures.py`): viewport, teto do WebP e
# limpeza do destino são os mesmos em todo módulo — só o destino muda.
capturar = capturas(DESTINO)  # noqa: F405


def _criar_dominio(servidor, setor) -> dict:
    """Cadeia Diretriz → Modelo → Solicitação → PPC → Plano de disciplina, via ORM."""
    from comum.models import Ano
    from edu.models import EstruturaCurso, Modalidade, NaturezaParticipacao, Nucleo
    from ppc.models import (
        Conteudo,
        Diretriz,
        ModeloPlanoDisciplina,
        ModeloPPC,
        PlanoDisciplina,
        ProjetoPedagogicoCurso,
        Secao,
        SolicitacaoPPC,
    )

    ano = Ano.objects.get_or_create(ano=date.today().year)[0]
    modalidade = Modalidade.objects.get_or_create(descricao='Técnico integrado ao ensino médio')[0]
    natureza = NaturezaParticipacao.objects.get_or_create(descricao='Presencial')[0]
    nucleo = Nucleo.objects.get_or_create(descricao='Núcleo Básico')[0]

    estrutura, _ = EstruturaCurso.objects.get_or_create(
        descricao='Estrutura de curso doc',
        tipo_avaliacao=EstruturaCurso.TIPO_AVALIACAO_SERIADO,
        criterio_avaliacao=EstruturaCurso.CRITERIO_AVALIACAO_NOTA,
    )

    diretriz, _ = Diretriz.objects.get_or_create(
        descricao='Diretriz doc de usuário',
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
        descricao='Modelo de PPC doc de usuário',
        tipo_oferta=modalidade,
        modalidade=natureza,
        ativo=True,
    )
    secao, _ = Secao.objects.get_or_create(titulo='Identificação do Curso', ordem_exibicao=1, modelo_ppc=modelo_ppc)
    conteudo_modelo, _ = Conteudo.objects.get_or_create(
        secao=secao,
        ordem_exibicao=1,
        texto='Texto do conteúdo do modelo de PPC.',
    )

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
        situacao=ProjetoPedagogicoCurso.EM_ELABORACAO,
        periodicidade=1,
        ch_curso=3000,
    )

    from ppc.models import ConteudoPPC

    ConteudoPPC.objects.get_or_create(ppc=ppc, conteudo_modelo=conteudo_modelo, texto='Conteúdo do PPC em elaboração.')

    modelo_pd, _ = ModeloPlanoDisciplina.objects.get_or_create(
        descricao='Modelo de plano de disciplina doc',
        nivel_ensino=modalidade.nivel_ensino,
        ativo=True,
    )
    plano_disciplina, _ = PlanoDisciplina.objects.get_or_create(
        nome_disciplina='Disciplina de Exemplo da Doc',
        ch_disciplina=80,
        ementa='Ementa da disciplina de exemplo.',
        diretriz=diretriz,
        tipo_oferta=modalidade,
        nucleo=nucleo,
        situacao=PlanoDisciplina.ELABORACAO,
    )
    # `PlanoDisciplina.save` (``ppc/models.py:4936``) resolve o modelo ativo pelo nível de
    # ensino quando o plano não o traz, e replica as seções do modelo; passar o modelo
    # direto por ORM dispara um `UnboundLocalError` no mesmo save (medido nesta rodada —
    # é um bug do módulo, não do seed). O modelo ativo criado acima é o que o save acha.

    return {
        'diretriz': diretriz,
        'modelo_ppc': modelo_ppc,
        'secao': secao,
        'conteudo_modelo': conteudo_modelo,
        'solicitacao': solicitacao,
        'ppc': ppc,
        'modelo_pd': modelo_pd,
        'plano_disciplina': plano_disciplina,
    }


@pytest.fixture(scope='session')
def doc_seed(e2e_seed):
    """Usuários da doc + domínio do PPC, antes da 1ª request.

    Session-scoped e eager pelo mesmo motivo dos e2e: o cache de permissão é por processo,
    então um usuário que ganha grupo depois do primeiro login continua sem acesso.
    """
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
