"""Harness da doc de usuário do módulo ``saude``.

Reusa as fixtures de ``djtools/e2e_fixtures.py`` sem alterá-las; aqui vive só o seed do módulo
(por factories, #17486) e o atalho de login por papel.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest
from dateutil.relativedelta import relativedelta
from django.conf import settings

from djtools.e2e_fixtures import *  # noqa: F403
from djtools.e2e_fixtures import campus, servidor_com_login

DESTINO = Path(settings.BASE_DIR) / 'saude' / 'docs' / 'usuario'
capturar = capturas(DESTINO)  # noqa: F405

PAPEIS = {
    'coordenador': '111001',
    'medico': '111002',
    'odontologo': '111003',
    'enfermeiro': '111004',
    'tecnico_enfermagem': '111005',
    'auxiliar_enfermagem': '111006',
    'fisioterapeuta': '111007',
    'psicologo': '111008',
    'nutricionista': '111009',
    'tecnico_saude_bucal': '111010',
    'aluno': '20191101011111',
}

# Matrícula -> (nome, grupo) dos profissionais, todos no campus CZN; o aluno sai de
# ``criar_aluno`` do seed do e2e (mesma matrícula e CPF).
SERVIDORES = {
    '111001': ('Coord Saúde Sistêmico', 'Coordenador de Saúde Sistêmico'),
    '111002': ('Médico Saúde', 'Médico'),
    '111003': ('Odontólogo Saúde', 'Odontólogo'),
    '111004': ('Enfermeiro Saúde', 'Enfermeiro'),
    '111005': ('Técnico Enfermagem Saúde', 'Técnico em Enfermagem'),
    '111006': ('Auxiliar Enfermagem Saúde', 'Auxiliar de Enfermagem'),
    '111007': ('Fisioterapeuta Saúde', 'Fisioterapeuta'),
    '111008': ('Psicólogo Saúde', 'Psicólogo'),
    '111009': ('Nutricionista Saúde', 'Nutricionista'),
    '111010': ('Técnico Saúde Bucal', 'Técnico em Saúde Bucal'),
}


@pytest.fixture(scope='session')
def saude_doc_seed(e2e_seed: None) -> None:
    """Profissionais (com o cargo da especialidade), aluno-paciente e cadastros de apoio."""
    from comum.models import Ano
    from edu.models import Aluno
    from rh.models import Servidor
    from saude.models import (
        AnoReferenciaAcaoEducativa,
        AtividadeRegistroAdministrativo,
        AvaliacaoGastroIntestinal,
        BloqueioAtendimentoSaude,
        CategoriaExameLaboratorial,
        DiagnosticoNutricional,
        MotivoAtendimentoNutricao,
        MotivoChegadaPsicologia,
        ObjetivoAcaoEducativa,
        OrientacaoNutricional,
        PerguntaMarcadorNutricao,
        ProcedimentoEnfermagem,
        ProcedimentoMultidisciplinar,
        ProcedimentoOdontologia,
        QueixaPsicologica,
        ReceitaNutricional,
        RestricaoAlimentar,
        TipoAtividadeGrupo,
        TipoAtendimentoPsicologia,
    )
    from saude.tests.e2e.seed import MATRICULA_ALUNO, cargo_saude, criar_aluno

    czn = campus('CZN', 'Campus Zona Norte')
    for matricula, (nome, grupo) in SERVIDORES.items():
        servidor_com_login(matricula, czn, grupos=[grupo], staff=True, pessoa_fisica__nome=nome, **cargo_saude(grupo))
    criar_aluno(nome='Aluno Saúde Documentação')

    hoje = datetime.date.today()
    Ano.objects.get_or_create(ano=hoje.year)
    AnoReferenciaAcaoEducativa.objects.get_or_create(ano=str(hoje.year))
    ObjetivoAcaoEducativa.objects.get_or_create(descricao='Promover saúde e qualidade de vida')
    TipoAtividadeGrupo.objects.get_or_create(descricao='Reunião')
    AtividadeRegistroAdministrativo.objects.get_or_create(descricao='Orientação individual', defaults={'ativa': True})
    CategoriaExameLaboratorial.objects.get_or_create(nome='Perfil Glicêmico')
    PerguntaMarcadorNutricao.objects.get_or_create(pergunta='Consumiu frutas ontem?', defaults={'tipo_resposta': 'Única Escolha'})
    ProcedimentoEnfermagem.objects.get_or_create(denominacao='Outros')
    ProcedimentoOdontologia.objects.get_or_create(denominacao='Outros')
    ProcedimentoMultidisciplinar.objects.get_or_create(denominacao='Outros')
    MotivoChegadaPsicologia.objects.get_or_create(descricao='Demanda Espontânea')
    QueixaPsicologica.objects.get_or_create(descricao='Ansiedade')
    TipoAtendimentoPsicologia.objects.get_or_create(descricao='Atendimento individual')
    AvaliacaoGastroIntestinal.objects.get_or_create(descricao='Outros')
    RestricaoAlimentar.objects.get_or_create(descricao='Outros')
    MotivoAtendimentoNutricao.objects.get_or_create(descricao='Outros')
    DiagnosticoNutricional.objects.get_or_create(descricao='Outros')
    OrientacaoNutricional.objects.get_or_create(titulo='Orientação equilibrada', defaults={'descricao': 'Manter alimentação equilibrada.'})
    ReceitaNutricional.objects.get_or_create(titulo='Receita saudável', defaults={'descricao': 'Preparação saudável.'})

    paciente = Aluno.objects.get(matricula=MATRICULA_ALUNO).get_vinculo()
    profissional = Servidor.objects.get(matricula=PAPEIS['coordenador']).get_vinculo()
    BloqueioAtendimentoSaude.objects.get_or_create(
        vinculo_paciente=paciente,
        vinculo_profissional=profissional,
        defaults={'data': hoje + relativedelta(years=1)},
    )


@pytest.fixture
def logado_saude(logado, saude_doc_seed):
    def _logado(papel: str):
        return logado(PAPEIS[papel])

    return _logado
