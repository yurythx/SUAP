# pyright: reportPrivateImportUsage=false, reportIncompatibleVariableOverride=false
"""Factories factory_boy de modelos do app ``documento_eletronico``.

Reutilizáveis por testes de qualquer app (o dono do modelo provê a factory). O substrato de
pessoal (``Setor``, ``Servidor``, ``User``, ``Vinculo``) vem de ``rh.tests.factories``.
"""

from __future__ import annotations

from typing import Any

import factory
from factory.django import DjangoModelFactory

from djtools.utils import get_datetime_now
from documento_eletronico.models import (
    Documento,
    DocumentoDigitalizado,
    DocumentoTexto,
    ConfiguracaoVinculoDocumento,
    ModeloDocumento,
    RegistroAcaoDocumentoTexto,
    SolicitacaoAssinatura,
    TipoConferencia,
    TipoDocumento,
    TipoDocumentoTexto,
    TipoVinculoDocumento,
)
from documento_eletronico.status import DocumentoStatus

PDF_MINIMO = b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n'


class TipoVinculoDocumentoFactory(DjangoModelFactory):
    class Meta:
        model = TipoVinculoDocumento

    descricao = factory.Sequence(lambda n: f'Vínculo {n}')
    descricao_voz_ativa = factory.Sequence(lambda n: f'relaciona {n}')
    descricao_voz_passiva = factory.Sequence(lambda n: f'é relacionado {n}')
    modo_uso = TipoVinculoDocumento.MODO_REGULAMENTADO


class ConfiguracaoVinculoDocumentoFactory(DjangoModelFactory):
    class Meta:
        model = ConfiguracaoVinculoDocumento

    tipo_vinculo_documento = factory.SubFactory(TipoVinculoDocumentoFactory)
    tipo_documento_base = factory.SubFactory('documento_eletronico.tests.factories.TipoDocumentoTextoFactory')
    tipo_documento_alvo = factory.SubFactory('documento_eletronico.tests.factories.TipoDocumentoTextoFactory')
    ativo = True


class TipoDocumentoFactory(DjangoModelFactory):
    class Meta:
        model = TipoDocumento
        django_get_or_create = ('nome',)

    nome = factory.Sequence(lambda n: f'Tipo de Documento {n}')
    sigla = factory.Sequence(lambda n: f'TD{n}')


class TipoDocumentoTextoFactory(TipoDocumentoFactory):
    class Meta:
        model = TipoDocumentoTexto
        django_get_or_create = ('nome',)

    nome = factory.Sequence(lambda n: f'Tipo de Documento Texto {n}')
    sigla = factory.Sequence(lambda n: f'TDT{n}')


class ModeloDocumentoFactory(DjangoModelFactory):
    class Meta:
        model = ModeloDocumento
        django_get_or_create = ('nome',)

    nome = factory.Sequence(lambda n: f'Modelo de Documento {n}')
    tipo_documento_texto = factory.SubFactory(TipoDocumentoTextoFactory)


class TipoConferenciaFactory(DjangoModelFactory):
    class Meta:
        model = TipoConferencia
        django_get_or_create = ('descricao',)

    descricao = factory.Sequence(lambda n: f'Conferência {n}')


class DocumentoTextoFactory(DjangoModelFactory):
    """Documento texto em rascunho, público.

    Sem ``setor_dono`` é um documento **pessoal** (``eh_documento_pessoal``). Recebe
    ``usuario_criacao`` por parâmetro: é o dono do documento.
    """

    class Meta:
        model = DocumentoTexto

    assunto = factory.Sequence(lambda n: f'Documento {n}')
    modelo = factory.SubFactory(ModeloDocumentoFactory)
    status = DocumentoStatus.STATUS_RASCUNHO
    setor_dono = None
    corpo = 'Conteúdo de teste'
    nivel_acesso = Documento.NIVEL_ACESSO_PUBLICO
    data_ultima_modificacao = factory.LazyFunction(get_datetime_now)
    usuario_ultima_modificacao = factory.SelfAttribute('usuario_criacao')


class DocumentoDigitalizadoFactory(DjangoModelFactory):
    """Documento digitalizado (PDF mínimo). Sem ``setor_dono`` é um documento pessoal."""

    class Meta:
        model = DocumentoDigitalizado

    assunto = factory.Sequence(lambda n: f'Documento digitalizado {n}')
    setor_dono = None
    tipo = factory.SubFactory(TipoDocumentoFactory, permite_documentos_pessoais=True)
    tipo_conferencia = factory.SubFactory(TipoConferenciaFactory)
    arquivo = factory.django.FileField(filename='documento.pdf', data=PDF_MINIMO)
    data_ultima_modificacao = factory.LazyFunction(get_datetime_now)


class SolicitacaoAssinaturaFactory(DjangoModelFactory):
    """Solicitação de assinatura pendente. Recebe ``documento``, ``solicitante`` (User) e ``solicitado`` (Vinculo)."""

    class Meta:
        model = SolicitacaoAssinatura


class RegistroAcaoDocumentoTextoFactory(DjangoModelFactory):
    """Registro de uma ação (``tipo``) de ``user`` sobre ``documento``; por padrão, uma edição.

    ``data`` é ``auto_now_add`` e o ``save`` a sobrescreve: quando informada, é gravada por
    ``update`` logo após a criação, para montar históricos em datas específicas.
    """

    class Meta:
        model = RegistroAcaoDocumentoTexto

    tipo = RegistroAcaoDocumentoTexto.TIPO_EDICAO
    documento = factory.SubFactory(DocumentoTextoFactory, usuario_criacao=factory.SelfAttribute('..user'))
    ip = '127.0.0.1'
    observacao = ''

    @classmethod
    def _create(cls, model_class: type[RegistroAcaoDocumentoTexto], *args: Any, **kwargs: Any) -> RegistroAcaoDocumentoTexto:
        data = kwargs.pop('data', None)
        registro = super()._create(model_class, *args, **kwargs)
        if data is not None:
            model_class.objects.filter(pk=registro.pk).update(data=data)
            registro.data = data
        return registro
