from __future__ import annotations

from pathlib import Path

import pytest
from django.conf import settings

from comum.tests.factories import AnoFactory
from djtools.e2e_fixtures import *  # noqa: F403
from djtools.e2e_fixtures import campus, servidor_com_login
from auditoria.tests.factories import (
    AcaoFactory,
    NucleoAuditoriaFactory,
    ServidorFuncaoChefiaFactory,
    ClasseBeneficioFactory,
    AlcanceEstrategicoFactory,
    UnidadeAfetadaFactory,
    MotivacaoAtendimentoFactory,
    TipoPosicionamentoValidoAtendimentoFactory,
)
from rh.tests.factories import SetorSiapeFactory, JornadaTrabalhoFactory

DESTINO = Path(settings.BASE_DIR) / 'auditoria' / 'docs' / 'usuario'
capturar = capturas(DESTINO)  # noqa: F405


@pytest.fixture(scope='session', autouse=True)
def dados_auditoria(e2e_seed: object) -> dict[str, object]:
    from datetime import date

    unidade = campus('ADOC', 'Campus Demonstração Auditoria')
    auditor = servidor_com_login('auddoc1', unidade, grupos=['Auditor'], staff=True, pessoa_fisica__nome='Ana Auditora')
    chefe = servidor_com_login('auddoc2', unidade, grupos=['Auditor', 'Auditor Sistêmico'], staff=True, pessoa_fisica__nome='Carlos Coordenador')
    jornada = JornadaTrabalhoFactory(codigo='AD', nome='40 HORAS SEMANAIS')
    for responsavel in (auditor, chefe):
        responsavel.jornada_trabalho = jornada
        responsavel.save()
    servidor = servidor_com_login('auddoc3', unidade, staff=True, pessoa_fisica__nome='Marina Responsável')
    ServidorFuncaoChefiaFactory(servidor=servidor, setor=SetorSiapeFactory(), setor_suap=unidade)
    ano = AnoFactory(ano=date.today().year)
    nucleo = NucleoAuditoriaFactory(nome='Núcleo Demonstração', coordenador=chefe.get_vinculo())
    nucleo.membros.add(auditor.get_vinculo(), chefe.get_vinculo())
    ClasseBeneficioFactory(tipo=1, descricao='Economia de recursos')
    ClasseBeneficioFactory(tipo=2, descricao='Melhoria dos processos')
    AlcanceEstrategicoFactory(descricao='Melhoria da gestão')
    UnidadeAfetadaFactory(nome='Administração')
    MotivacaoAtendimentoFactory()
    TipoPosicionamentoValidoAtendimentoFactory()
    acao = AcaoFactory(nome='Avaliação de processos', tipo_servico__nome='Avaliação de processos')
    return {'unidade': unidade, 'auditor': auditor, 'chefe': chefe, 'servidor': servidor, 'ano': ano, 'nucleo': nucleo, 'acao': acao}
