# pyright: reportPrivateImportUsage=false, reportIncompatibleVariableOverride=false
"""Factories factory_boy de modelos do app ``processo_eletronico``.

O substrato de pessoal vem de ``rh.tests.factories`` e os documentos de
``documento_eletronico.tests.factories``.
"""

from __future__ import annotations

import factory
from factory.django import DjangoModelFactory

from processo_eletronico.models import (
    Apensamento,
    ApensamentoProcesso,
    CompartilhamentoProcessoEletronicoPoderDeChefe,
    CompartilhamentoProcessoEletronicoSetorPessoa,
    Processo,
    SolicitacaoCiencia,
    SolicitacaoDespacho,
    TipoProcesso,
    Tramite,
)


class CompartilhamentoPoderChefeFactory(DjangoModelFactory):
    class Meta:
        model = CompartilhamentoProcessoEletronicoPoderDeChefe

    de_oficio = False


class CompartilhamentoProcessoEletronicoSetorPessoaFactory(DjangoModelFactory):
    """Permite ao ``vinculo_permitido`` operar os processos do ``setor_dono`` (ambos por parâmetro)."""

    class Meta:
        model = CompartilhamentoProcessoEletronicoSetorPessoa

    nivel_permissao = Processo.PERMISSAO_OPERAR_PROCESSO


class TipoProcessoFactory(DjangoModelFactory):
    class Meta:
        model = TipoProcesso
        django_get_or_create = ('nome',)

    nome = factory.Sequence(lambda n: f'Tipo de Processo {n}')
    nivel_acesso_default = Processo.NIVEL_ACESSO_PUBLICO


class ProcessoFactory(DjangoModelFactory):
    """Processo público.

    Recebe ``setor_criacao`` e ``usuario_gerador`` por parâmetro. O NUP é gerado no ``save``
    a partir do código SIORG do setor, então o setor precisa tê-lo (fixture ``setor_com_siorg``).
    """

    class Meta:
        model = Processo

    tipo_processo = factory.SubFactory(TipoProcessoFactory)
    nivel_acesso = Processo.NIVEL_ACESSO_PUBLICO
    modificado_por = factory.SelfAttribute('usuario_gerador')


class TramiteFactory(DjangoModelFactory):
    class Meta:
        model = Tramite


class SolicitacaoDespachoFactory(DjangoModelFactory):
    """Recebe ``processo``, ``remetente_setor``, ``remetente_vinculo`` e ``solicitado`` por parâmetro."""

    class Meta:
        model = SolicitacaoDespacho

    despacho_corpo = 'Despacho solicitado'
    destinatario_setor_tramite = factory.SelfAttribute('remetente_setor')


class SolicitacaoCienciaFactory(DjangoModelFactory):
    """Recebe ``processo``, ``tramite`` e ``solicitado`` por parâmetro."""

    class Meta:
        model = SolicitacaoCiencia


class ApensamentoFactory(DjangoModelFactory):
    class Meta:
        model = Apensamento

    justificativa_criacao = 'Apensamento de teste'


class ApensamentoProcessoFactory(DjangoModelFactory):
    """Recebe ``processo`` por parâmetro."""

    class Meta:
        model = ApensamentoProcesso

    apensamento = factory.SubFactory(ApensamentoFactory)
    justificativa_criacao = 'Apensamento de teste'
