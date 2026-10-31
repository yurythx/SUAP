"""Seed das tabelas-tipo do acadêmico — o que o antigo `light_data` semeava.

São linhas de REFERÊNCIA com id constante (`Turno`, `NivelEnsino`, `Modalidade`,
`SituacaoMatricula`, `SituacaoMatriculaPeriodo`, `ConfiguracaoAvaliacao`) mais o trio de
`Configuracao` da instituição. O `light_data` as commitava numa fixture de classe; aqui
cada teste cria as suas, dentro da própria transação, pelas factories dos apps donos.
"""

from __future__ import annotations

from comum.models import Configuracao
from comum.tests.factories import _sincronizar_sequencia
from edu.models import (
    Modalidade,
    NivelEnsino,
    SituacaoMatricula,
    SituacaoMatriculaPeriodo,
)
from edu.tests.factories import (
    ConfiguracaoAvaliacaoFactory,
    ModalidadeFactory,
    NivelEnsinoFactory,
    TurnoFactory,
)
from rh.tests.factories import TitulacaoFactory

SIGLA_INSTITUICAO = 'IFRN'


def _semear_por_constantes(model):
    """Cria uma linha para CADA constante inteira maiúscula do model.

    As tabelas de situação são consultadas por várias dessas constantes ao longo dos
    fluxos (`TRANCADO`, `CONCLUIDO`, `REPROVADO`...), não só pela MATRICULADO: semear uma
    só deixava os fluxos do `edu` com `DoesNotExist`.
    """
    for nome, valor in list(vars(model).items()):
        if nome.isupper() and isinstance(valor, int):
            model.objects.update_or_create(id=valor, defaults={'descricao': nome.replace('_', ' ').title()})


def seed_configuracao_instituicao():
    """Trio de `Configuracao` que o SUAP lê para se identificar."""
    Configuracao.objects.get_or_create(
        app='comum',
        chave='instituicao',
        defaults={'valor': 'Instituto Federal de Educação, Ciência e Tecnologia do Rio Grande do Norte'},
    )
    Configuracao.objects.get_or_create(app='comum', chave='instituicao_sigla', defaults={'valor': SIGLA_INSTITUICAO})
    Configuracao.objects.get_or_create(app='comum', chave='instituicao_pessoa_juridica', defaults={'valor': '1'})


def seed_academico() -> None:
    """Tabelas-tipo do acadêmico, pelos ids constantes dos próprios models."""
    seed_configuracao_instituicao()
    TurnoFactory()
    TitulacaoFactory()

    fundamental = NivelEnsinoFactory(id=NivelEnsino.FUNDAMENTAL, descricao='Fundamental')
    NivelEnsinoFactory(id=NivelEnsino.MEDIO, descricao='Médio')
    graduacao = NivelEnsinoFactory(id=NivelEnsino.GRADUACAO, descricao='Graduação')
    pos_graduacao = NivelEnsinoFactory(id=NivelEnsino.POS_GRADUACAO, descricao='Pós-Graduação')

    ModalidadeFactory(id=Modalidade.FIC, descricao='FIC', nivel_ensino=fundamental)
    ModalidadeFactory(id=Modalidade.FIC_MENOS, descricao='FIC-', nivel_ensino=fundamental)
    ModalidadeFactory(id=Modalidade.MESTRADO, descricao='Mestrado', nivel_ensino=pos_graduacao)
    ModalidadeFactory(id=Modalidade.LICENCIATURA, descricao='Licenciatura', nivel_ensino=graduacao)

    _semear_por_constantes(SituacaoMatricula)
    # Só a MATRICULADO fica ativa. Por UPDATE, não pela factory: com
    # `django_get_or_create`, a factory ENCONTRA a linha que `_semear_por_constantes`
    # acabou de criar e devolve como está, sem aplicar `ativo=True`. E `ativo` não é
    # cosmético: `MatriculaPeriodo.pode_realizar_transferencia()` exige
    # `aluno.situacao.ativo`.
    SituacaoMatricula.objects.filter(id=SituacaoMatricula.MATRICULADO).update(ativo=True)
    SituacaoMatricula.objects.exclude(id=SituacaoMatricula.MATRICULADO).update(ativo=False)
    _semear_por_constantes(SituacaoMatriculaPeriodo)

    ConfiguracaoAvaliacaoFactory()

    for model in (NivelEnsino, Modalidade, SituacaoMatricula, SituacaoMatriculaPeriodo):
        _sincronizar_sequencia(model)
