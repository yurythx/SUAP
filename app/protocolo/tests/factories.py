"""Factories dos processos de protocolo usados pelos fluxos de negócio."""

import factory
from factory.django import DjangoModelFactory

from protocolo.models import Processo


class ProcessoFactory(DjangoModelFactory):
    class Meta:
        model = Processo

    assunto = factory.Sequence(lambda n: f'Processo de demonstração {n}')
    tipo = Processo.TIPO_MEMORANDO
    interessado_nome = 'Pessoa de Demonstração'
    interessado_documento = ''
    interessado_pf = True
