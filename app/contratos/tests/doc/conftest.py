"""Navegação e capturas do manual de Contratos, em banco exclusivo de documentação."""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

import pytest
from django.conf import settings

from djtools.e2e_fixtures import *  # noqa: F403
from djtools.e2e_fixtures import campus, servidor_com_login
from contratos.models import BaseLegal, SubtipoContrato
from protocolo.models import Processo
from rh.models import PessoaJuridica, Servidor, Setor
from tesouro_gerencial.models import DocumentoEmpenho


class DadosContratos(TypedDict):
    unidade: Setor
    gerente: Servidor
    fiscal: Servidor
    processo: Processo
    contratada: PessoaJuridica
    empenho: DocumentoEmpenho
    subtipo: SubtipoContrato
    base_legal: BaseLegal


DESTINO = Path(settings.BASE_DIR) / 'contratos' / 'docs' / 'usuario'
capturar = capturas(DESTINO)  # noqa: F405


@pytest.fixture(scope='session')
def contratos_doc_seed(e2e_seed: None) -> DadosContratos:
    """Cria papéis reais antes da primeira request e usa catálogos institucionais."""
    unidade = campus('DOCCT', nome='Campus de Demonstração', codigo_protocolo='99001')
    gerente = servidor_com_login('159601', unidade, grupos=['Gerente de Contrato'], staff=True, pessoa_fisica__nome='Marina Gestora')
    fiscal = servidor_com_login('159602', unidade, grupos=['Fiscal de Contrato'], staff=True, pessoa_fisica__nome='Carlos Fiscal')
    from contratos.tests.factories import BaseLegalFactory, SubtipoContratoFactory
    from protocolo.tests.factories import ProcessoFactory
    from rh.tests.factories import PessoaJuridicaFactory

    from comum.tests.factories import AnoFactory
    from datetime import date

    AnoFactory(ano=date.today().year)
    processo = ProcessoFactory(vinculo_cadastro=gerente.get_vinculo(), setor_origem=unidade, assunto='Manutenção predial de demonstração')
    contratada = PessoaJuridicaFactory(nome='Empresa de Serviços de Demonstração')
    contratada.get_vinculo()
    contratada.save()
    from tesouro_gerencial.tests.factories import DocumentoEmpenhoFactory, DocumentoEmpenhoItemFactory, UnidadeGestoraFactory

    empenho = DocumentoEmpenhoFactory(emitente_ug=UnidadeGestoraFactory(uo=unidade.uo))
    DocumentoEmpenhoItemFactory(documento_empenho=empenho)
    return {
        'unidade': unidade,
        'gerente': gerente,
        'fiscal': fiscal,
        'processo': processo,
        'contratada': contratada,
        'empenho': empenho,
        'subtipo': SubtipoContratoFactory(),
        'base_legal': BaseLegalFactory(),
    }
