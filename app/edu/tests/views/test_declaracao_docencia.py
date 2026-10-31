"""Declaração de vínculo docente em PDF (``/edu/declaracaodocencia_pdf/<professor>/<ano>/``).

Em teste o ``@documento`` devolve o HTML sem passar pelo wkhtmltopdf: o que se mede aqui é a view
(ORM + template). O grafo é montado por ``bulk_create`` porque o ``save`` de ``Diario``,
``ProfessorDiario`` e ``Aula`` tem efeitos colaterais que o teste não precisa.
"""

from __future__ import annotations

import datetime
import itertools
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import Group
from django.db import connection
from django.test.utils import CaptureQueriesContext

from comum.models import Ano, User
from comum.tests.factories import AnoFactory
from rh.models import Setor
from rh.tests.factories import ServidorFactory, SetorFactory

from edu.models import (
    CalendarioAcademico,
    Componente,
    ComponenteCurricular,
    CursoCampus,
    Diario,
    DiarioEspecial,
    Diretoria,
    EstruturaCurso,
    HorarioCampus,
    Matriz,
    MatrizCurso,
    Minicurso,
    Modalidade,
    NivelEnsino,
    Nucleo,
    Professor,
    ProfessorDiario,
    ProfessorMinicurso,
    TipoComponente,
    TipoProfessorDiario,
    Turma,
    TurmaMinicurso,
    Turno,
)
from edu.models.diarios import Aula
from edu.tests.factories import AlunoFactory

COLUNA_PK = 6
_seq = itertools.count()


def _data(ano: int, dia: int = 1) -> datetime.date:
    return datetime.date(ano, 3, 1) + datetime.timedelta(days=dia)


def _base(s: int) -> SimpleNamespace:
    """Cursos (semestral e anual), calendários, matriz e demais pré-requisitos de um diário."""
    b = SimpleNamespace()
    b.turno, _ = Turno.objects.get_or_create(descricao='Matutino')
    setor = SetorFactory()
    b.horario_campus = HorarioCampus.objects.create(descricao='Horário Padrão', uo=setor.uo)
    b.diretoria = Diretoria.objects.create(setor=setor)
    nivel, _ = NivelEnsino.objects.get_or_create(id=NivelEnsino.GRADUACAO, defaults={'descricao': 'Graduação'})
    b.modalidade, _ = Modalidade.objects.get_or_create(descricao='Modalidade Declaração', nivel_ensino=nivel)
    b.modalidade_fic_menos, _ = Modalidade.objects.get_or_create(id=Modalidade.FIC_MENOS, defaults={'descricao': 'FIC-', 'nivel_ensino': nivel})
    b.nivel = nivel
    b.estrutura = EstruturaCurso.objects.create(
        descricao='Estrutura Declaração',
        tipo_avaliacao=EstruturaCurso.TIPO_AVALIACAO_CREDITO,
        criterio_avaliacao=EstruturaCurso.CRITERIO_AVALIACAO_NOTA,
        media_aprovacao_sem_prova_final=70,
        media_evitar_reprovacao_direta=20,
        media_aprovacao_avaliacao_final=50,
    )
    b.tipo_componente, _ = TipoComponente.objects.get_or_create(descricao='Disciplina')
    b.nucleo, _ = Nucleo.objects.get_or_create(descricao='Núcleo Comum')
    b.matriz = Matriz.objects.create(
        descricao=f'Matriz Declaração {s}',
        estrutura=b.estrutura,
        ano_criacao=AnoFactory(ano=2020),
        data_inicio=datetime.date(2020, 1, 1),
        qtd_periodos_letivos=2,
        ch_componentes_obrigatorios=100,
        ch_componentes_optativos=0,
        ch_componentes_eletivos=0,
        ch_seminarios=0,
        ch_pratica_profissional=0,
        ch_atividades_complementares=0,
        ch_atividades_aprofundamento=0,
        ch_componentes_tcc=0,
        ch_pratica_como_componente=0,
        ch_visita_tecnica=0,
    )
    b.curso_semestral = CursoCampus.objects.create(
        descricao='Curso Semestral', descricao_historico='Curso Semestral', codigo=f'DD{s}A', diretoria=b.diretoria, modalidade=b.modalidade
    )
    b.curso_anual = CursoCampus.objects.create(
        descricao='Curso Anual',
        descricao_historico='Curso Anual',
        codigo=f'DD{s}B',
        diretoria=b.diretoria,
        modalidade=b.modalidade,
        periodicidade=CursoCampus.PERIODICIDADE_ANUAL,
    )
    for curso in (b.curso_semestral, b.curso_anual):
        MatrizCurso.objects.create(matriz=b.matriz, curso_campus=curso)
    return b


def _calendario(b: SimpleNamespace, ano: Ano, anual: bool) -> CalendarioAcademico:
    return CalendarioAcademico.objects.create(
        descricao=f'Calendário {ano.ano} {"anual" if anual else "semestral"}',
        tipo=CalendarioAcademico.TIPO_ANUAL if anual else CalendarioAcademico.TIPO_SEMESTRAL,
        ano_letivo=ano,
        periodo_letivo=1,
        data_inicio=datetime.date(ano.ano, 2, 1),
        data_fim=datetime.date(ano.ano, 12, 15),
        data_fechamento_periodo=datetime.date(ano.ano, 12, 20),
        qtd_etapas=CalendarioAcademico.QTD_ETAPA_4 if anual else CalendarioAcademico.QTD_ETAPA_2,
        data_inicio_etapa_1=datetime.date(ano.ano, 2, 1),
        data_fim_etapa_1=datetime.date(ano.ano, 4, 30),
    )


def _diarios(b: SimpleNamespace, s: int, n_diarios: int) -> list[Diario]:
    """``n_diarios`` diários de 2025, exceto o último (2022, que usa o ``percentual_ch``).

    Os de índice par são de curso anual (calendário de 4 etapas); destes, os de índice múltiplo
    de 4 têm componente semestral (``qtd_avaliacoes=2``) em calendário anual. Cada diário tem
    componente e turma próprios.
    """
    ano_atual, ano_antigo = AnoFactory(ano=2025), AnoFactory(ano=2022)
    cal_sem, cal_anual = _calendario(b, ano_atual, False), _calendario(b, ano_atual, True)
    cal_antigo = _calendario(b, ano_antigo, False)
    diarios = []
    for i in range(n_diarios):
        antigo = i == n_diarios - 1 and n_diarios > 2
        anual = i % 2 == 0
        ano = ano_antigo if antigo else ano_atual
        componente = Componente.objects.create(
            descricao=f'Disciplina {i}',
            descricao_historico=f'Disciplina {i} (histórico)',
            sigla=f'DD{s}.{i:04d}',
            tipo=b.tipo_componente,
            diretoria=b.diretoria,
            nivel_ensino=b.nivel,
            ch_hora_relogio=40 + 10 * i,
            ch_hora_aula=60 + 10 * i,
            ch_qtd_creditos=2 + i,
        )
        cc = ComponenteCurricular.objects.create(
            matriz=b.matriz,
            componente=componente,
            periodo_letivo=1,
            tipo=ComponenteCurricular.TIPO_REGULAR,
            qtd_avaliacoes=4 if i % 4 == 2 else 2,
            nucleo=b.nucleo,
            ch_presencial=60,
            ch_pratica=0,
            optativo=False,
        )
        curso = b.curso_anual if anual else b.curso_semestral
        turma = Turma.objects.create(
            codigo=f'{ano.ano}.1.{s}.{i:02d}', curso_campus=curso, ano_letivo=ano, periodo_letivo=1, turno=b.turno, periodo_matriz=1, matriz=b.matriz
        )
        diarios.append(
            Diario(
                turma=turma,
                componente_curricular=cc,
                ano_letivo=ano,
                periodo_letivo=1,
                segundo_semestre=i % 4 == 3,
                horario_campus=b.horario_campus,
                turno=b.turno,
                estrutura_curso=b.estrutura,
                calendario_academico=cal_antigo if antigo else cal_anual if anual else cal_sem,
                percentual_minimo_ch=75,
                search_fields_optimized='',
            )
        )
    return Diario.objects.bulk_create(diarios)


def _aulas(pds: list[ProfessorDiario], pds2: dict[int, ProfessorDiario], n_aulas: int, diarios: list[Diario]) -> None:
    """``n_aulas`` aulas distribuídas nos diários (os de índice 2, 5, 8... ficam sem aula ministrada).

    Em um quarto delas quem ministra é o 2º professor, com o 1º em ``outros_professor_diario``;
    em outro quarto o 1º professor ministra junto com o 2º. Uma aula por diário é futura.
    """
    hoje = datetime.date.today()
    com_aula = {d.id for i, d in enumerate(diarios) if i % 3 != 2}
    alvo = [pd for pd in pds if pd.diario_id in com_aula]
    aulas, compartilhadas = [], []
    for k in range(n_aulas):
        pd = alvo[k % len(alvo)]
        pd2 = pds2.get(pd.diario_id)
        titular, outros = pd, None
        if pd2 and k % 4 == 1:
            titular, outros = pd2, pd
        elif pd2 and k % 4 == 2:
            outros = pd2
        data = hoje + datetime.timedelta(days=5) if k < len(alvo) else _data(pd.diario.ano_letivo.ano, k % 200)
        aulas.append(Aula(professor_diario=titular, data=data, conteudo=f'Aula {k}', quantidade=1 + k % 3, etapa=1))
        compartilhadas.append(outros)
    aulas = Aula.objects.bulk_create(aulas)
    through = Aula.outros_professor_diario.through
    through.objects.bulk_create([through(aula_id=a.id, professordiario_id=o.id) for a, o in zip(aulas, compartilhadas, strict=False) if o])


def montar_cenario(n_diarios: int = 10, n_aulas: int = 200, n_extras: int = 2) -> SimpleNamespace:
    """Professor com ``n_diarios`` diários e ``n_aulas`` aulas, mais minicursos/diários especiais."""
    s = next(_seq)
    b = _base(s)
    servidor = ServidorFactory()
    servidor2 = ServidorFactory()
    professor = Professor.objects.create(vinculo=servidor.get_vinculo())
    professor2 = Professor.objects.create(vinculo=servidor2.get_vinculo())
    tipo, _ = TipoProfessorDiario.objects.get_or_create(descricao='Principal')
    diarios = _diarios(b, s, n_diarios)
    pds = ProfessorDiario.objects.bulk_create(
        [ProfessorDiario(diario=d, professor=professor, tipo=tipo, ativo=True, percentual_ch=50 + i) for i, d in enumerate(diarios)]
    )
    # O 2º professor divide os 6 primeiros diários.
    pds2 = ProfessorDiario.objects.bulk_create(
        [ProfessorDiario(diario=d, professor=professor2, tipo=tipo, ativo=True, percentual_ch=50) for d in diarios[:6]]
    )
    for pd in pds:
        pd.diario = next(d for d in diarios if d.id == pd.diario_id)
    _aulas(pds, {p.diario_id: p for p in pds2}, n_aulas, diarios)

    ano = Ano.objects.get(ano=2025)
    for i in range(n_extras):
        minicurso = Minicurso.objects.create(
            descricao=f'Minicurso {i}', descricao_historico=f'Minicurso {i}', codigo=f'MC{s}{i}', ch_total=20, tipo_hora_aula=60,
            modalidade=b.modalidade_fic_menos, diretoria=b.diretoria,
        )  # fmt: skip
        turma = TurmaMinicurso.objects.create(
            descricao=f'Turma Minicurso {i}', minicurso=minicurso, ano_letivo=ano, periodo_letivo=1, data_inicio=_data(2025), data_fim=_data(2025, 60)
        )
        ProfessorMinicurso.objects.create(professor=professor, turma_minicurso=turma, carga_horaria=20)
        especial = DiarioEspecial.objects.create(
            ano_letivo=ano,
            periodo_letivo=1,
            componente=diarios[0].componente_curricular.componente,
            horario_campus=b.horario_campus,
            diretoria=b.diretoria,
        )
        especial.professores.add(professor)
    return SimpleNamespace(professor=professor, servidor=servidor, diarios=diarios, base=b)


@pytest.fixture
def cliente(db, sync_permissions, suap_client):
    return suap_client


def _requisitar(cliente, cenario: SimpleNamespace, ano: int | None = None):
    cliente.login(user=cenario.servidor.get_user())
    caminho = f'/edu/declaracaodocencia_pdf/{cenario.professor.pk}/' + (f'{ano}/' if ano else '')
    with CaptureQueriesContext(connection) as consultas:
        resposta = cliente.get(caminho)
    return resposta, consultas


def _normalizar(linhas: list[tuple], setor: str) -> list[tuple]:
    """Tira o que muda de execução para execução (pk e sigla do setor), mantendo a ordem da view."""
    saida = []
    for linha in linhas:
        linha = list(linha)
        if isinstance(linha[COLUNA_PK], int):
            linha[COLUNA_PK] = '#'
        if linha[2] == setor:
            linha[2] = 'SETOR'
        saida.append(tuple(linha))
    return saida


# Colunas: curso, modalidade, setor, ano, período, CH relógio, pk, % CH ministrada, componente,
# créditos, 2º semestre, periodicidade, % CH do vínculo.
LISTA_ESPERADA_TODOS = [
    ('Curso Anual', 'Modalidade Declaração', 'SETOR', 2025, 1, 40, '#', 93, 'Disciplina 0 (histórico)', 2, False, 'Semestral', 50),
    ('Curso Anual', 'Modalidade Declaração', 'SETOR', 2025, 1, 60, '#', 0, 'Disciplina 2 (histórico)', 4, False, 'Anual', 52),
    ('Curso Anual', 'Modalidade Declaração', 'SETOR', 2025, 1, 80, '#', 56, 'Disciplina 4 (histórico)', 6, False, 'Semestral', 54),
    ('Curso Anual', 'Modalidade Declaração', 'SETOR', 2025, 1, 100, '#', 45, 'Disciplina 6 (histórico)', 8, False, 'Anual', 56),
    ('Curso Anual', 'Modalidade Declaração', 'SETOR', 2025, 1, 120, '#', 0, 'Disciplina 8 (histórico)', 10, False, 'Semestral', 58),
    ('Curso Semestral', 'Modalidade Declaração', 'SETOR', 2022, 1, 130, '#', 59, 'Disciplina 9 (histórico)', 11, False, 'Semestral', 59),
    ('Curso Semestral', 'Modalidade Declaração', 'SETOR', 2025, 1, 50, '#', 81, 'Disciplina 1 (histórico)', 3, False, 'Semestral', 51),
    ('Curso Semestral', 'Modalidade Declaração', 'SETOR', 2025, 1, 70, '#', 61, 'Disciplina 3 (histórico)', 5, True, 'Semestral', 53),
    ('Curso Semestral', 'Modalidade Declaração', 'SETOR', 2025, 1, 90, '#', 0, 'Disciplina 5 (histórico)', 7, False, 'Semestral', 55),
    ('Curso Semestral', 'Modalidade Declaração', 'SETOR', 2025, 1, 110, '#', 41, 'Disciplina 7 (histórico)', 9, True, 'Semestral', 57),
    ('Minicursos', 'FIC-', 'SETOR', 2025, 1, 20, '-', '100', 'Minicurso 0', '-', False, '', '100'),
    ('Minicursos', 'FIC-', 'SETOR', 2025, 1, 20, '-', '100', 'Minicurso 1', '-', False, '', '100'),
    ('Diários Especiais', '', 'SETOR', 2025, 1, 40, '#', '100', 'Disciplina 0 (histórico)', 2, False, 'Semestral', '100'),
    ('Diários Especiais', '', 'SETOR', 2025, 1, 40, '#', '100', 'Disciplina 0 (histórico)', 2, False, 'Semestral', '100'),
]


def test_declaracao_mantem_o_conteudo_de_todos_os_anos(cliente):
    cenario = montar_cenario()

    resposta, _ = _requisitar(cliente, cenario)

    assert resposta.status_code == 200
    setor = cenario.base.diretoria.setor.sigla
    assert _normalizar(resposta.context['lists_diarios'], setor) == LISTA_ESPERADA_TODOS


def test_declaracao_mantem_o_conteudo_de_um_ano(cliente):
    cenario = montar_cenario()

    resposta, _ = _requisitar(cliente, cenario, ano=2025)

    assert resposta.status_code == 200
    setor = cenario.base.diretoria.setor.sigla
    assert _normalizar(resposta.context['lists_diarios'], setor) == [x for x in LISTA_ESPERADA_TODOS if x[3] == 2025]


def test_minicursos_e_diarios_especiais_saem_por_ano_periodo_e_descricao(cliente) -> None:
    cenario = montar_cenario(n_diarios=2, n_aulas=0, n_extras=0)
    b, s = cenario.base, next(_seq)
    componentes = {c.descricao_historico: c for c in (d.componente_curricular.componente for d in cenario.diarios)}
    # Criados fora da ordem esperada: a ordem de inserção não pode decidir a do documento.
    for i, (descricao, ano, periodo) in enumerate(
        [('Minicurso B', 2025, 1), ('Minicurso A', 2025, 1), ('Minicurso C', 2025, 2), ('Minicurso Z', 2024, 1)]
    ):
        minicurso = Minicurso.objects.create(
            descricao=descricao, descricao_historico=descricao, codigo=f'MO{s}{i}', ch_total=20, tipo_hora_aula=60,
            modalidade=b.modalidade_fic_menos, diretoria=b.diretoria,
        )  # fmt: skip
        turma = TurmaMinicurso.objects.create(
            descricao=f'Turma {descricao}', minicurso=minicurso, ano_letivo=AnoFactory(ano=ano), periodo_letivo=periodo,
            data_inicio=_data(ano), data_fim=_data(ano, 60),
        )  # fmt: skip
        ProfessorMinicurso.objects.create(professor=cenario.professor, turma_minicurso=turma, carga_horaria=20)
    for componente, ano in [('Disciplina 1 (histórico)', 2025), ('Disciplina 0 (histórico)', 2025), ('Disciplina 1 (histórico)', 2024)]:
        especial = DiarioEspecial.objects.create(
            ano_letivo=AnoFactory(ano=ano),
            periodo_letivo=1,
            componente=componentes[componente],
            horario_campus=b.horario_campus,
            diretoria=b.diretoria,
        )
        especial.professores.add(cenario.professor)

    resposta, _ = _requisitar(cliente, cenario)

    assert resposta.status_code == 200
    extras = [
        (linha[0], linha[3], linha[4], linha[8]) for linha in resposta.context['lists_diarios'] if linha[0] in ('Minicursos', 'Diários Especiais')
    ]
    assert extras == [
        ('Minicursos', 2024, 1, 'Minicurso Z'),
        ('Minicursos', 2025, 1, 'Minicurso A'),
        ('Minicursos', 2025, 1, 'Minicurso B'),
        ('Minicursos', 2025, 2, 'Minicurso C'),
        ('Diários Especiais', 2024, 1, 'Disciplina 1 (histórico)'),
        ('Diários Especiais', 2025, 1, 'Disciplina 0 (histórico)'),
        ('Diários Especiais', 2025, 1, 'Disciplina 1 (histórico)'),
    ]


def _consultas(cliente, **cenario_kwargs) -> int:
    """Consultas da requisição já aquecida (config/templates em cache)."""
    cenario = montar_cenario(**cenario_kwargs)
    _requisitar(cliente, cenario)
    return len(_requisitar(cliente, cenario)[1])


def test_consultas_nao_crescem_com_o_numero_de_aulas(cliente):
    poucas = _consultas(cliente, n_aulas=20)
    muitas = _consultas(cliente, n_aulas=200)

    assert muitas - poucas <= 2, f'20 aulas: {poucas} consultas; 200 aulas: {muitas}'


def test_consultas_nao_crescem_com_o_numero_de_diarios(cliente):
    poucos = _consultas(cliente, n_diarios=4, n_aulas=0)
    muitos = _consultas(cliente, n_diarios=10, n_aulas=0)

    assert muitos - poucos <= 1, f'4 diários: {poucos} consultas; 10 diários: {muitos}'


def test_consultas_nao_crescem_com_minicursos_e_diarios_especiais(cliente):
    poucos = _consultas(cliente, n_extras=1)
    muitos = _consultas(cliente, n_extras=6)

    assert muitos - poucos <= 2, f'1 de cada: {poucos} consultas; 6 de cada: {muitos}'


# Quem emite (#17725): o próprio professor, a gestão acadêmica e o RH.
ADMIN_ACADEMICO = 'Administrador Acadêmico'
DIRETOR_ACADEMICO_SISTEMICO = 'Diretor Acadêmico Sistêmico'
COORDENADOR_REGISTROS = 'Coordenador de Registros Acadêmicos'
COORDENADOR_CURSO = 'Coordenador de Curso'
SECRETARIO = 'Secretário Acadêmico'
DIRETOR_GERAL = 'Diretor Geral'
RH_SISTEMICO = 'Coordenador de Gestão de Pessoas Sistêmico'
RH_CAMPUS = 'Coordenador de Gestão de Pessoas'


def _servidor_com(*grupos: str, setor: Setor | None = None) -> User:
    """Servidor com os ``grupos``, lotado em ``setor`` (sem ele, num campus só seu)."""
    usuario = ServidorFactory(setor=setor or SetorFactory()).get_user()
    usuario.groups.add(*[Group.objects.get(name=grupo) for grupo in grupos])
    return usuario


def _professor() -> Professor:
    return Professor.objects.create(vinculo=ServidorFactory().get_vinculo())


def _no_campus_do(professor: Professor) -> Setor:
    """Outro setor, no campus do professor."""
    return SetorFactory(superior=professor.vinculo.setor)


USUARIOS = {
    'aluno': lambda professor: AlunoFactory().get_user(),
    'servidor sem papel': lambda professor: _servidor_com(setor=_no_campus_do(professor)),
    'outro professor': lambda professor: _professor().vinculo.user,
    'próprio professor': lambda professor: professor.vinculo.user,
    'secretário acadêmico do campus': lambda professor: _servidor_com(SECRETARIO, setor=_no_campus_do(professor)),
    'diretor geral do campus': lambda professor: _servidor_com(DIRETOR_GERAL, setor=_no_campus_do(professor)),
    'secretário acadêmico de outro campus': lambda professor: _servidor_com(SECRETARIO),
    'administrador acadêmico de outro campus': lambda professor: _servidor_com(ADMIN_ACADEMICO),
    'RH do campus': lambda professor: _servidor_com(RH_CAMPUS, setor=_no_campus_do(professor)),
    'RH de outro campus': lambda professor: _servidor_com(RH_CAMPUS),
    'RH sistêmico de outro campus': lambda professor: _servidor_com(RH_SISTEMICO),
    'diretor acadêmico sistêmico de outro campus': lambda professor: _servidor_com(DIRETOR_ACADEMICO_SISTEMICO),
    'coordenador de registros acadêmicos do campus': lambda professor: _servidor_com(COORDENADOR_REGISTROS, setor=_no_campus_do(professor)),
    'coordenador de curso do campus': lambda professor: _servidor_com(COORDENADOR_CURSO, setor=_no_campus_do(professor)),
    'coordenador de curso de outro campus': lambda professor: _servidor_com(COORDENADOR_CURSO),
}
PODEM = {'próprio professor', 'secretário acadêmico do campus', 'diretor geral do campus', 'administrador acadêmico de outro campus'}
PODEM |= {'RH do campus', 'RH sistêmico de outro campus'}
PODEM |= {'diretor acadêmico sistêmico de outro campus', 'coordenador de registros acadêmicos do campus', 'coordenador de curso do campus'}


@pytest.mark.parametrize('papel', USUARIOS)
def test_quem_pode_emitir_a_declaracao(cliente, papel: str):
    professor = _professor()
    cliente.force_login(USUARIOS[papel](professor))

    todos = cliente.get(f'/edu/declaracaodocencia_pdf/{professor.pk}/').status_code
    um_ano = cliente.get(f'/edu/declaracaodocencia_pdf/{professor.pk}/2025/').status_code

    esperado = 200 if papel in PODEM else 403
    assert (todos, um_ano) == (esperado, esperado)


@pytest.mark.parametrize(('grupo', 've_botao'), [(SECRETARIO, True), ('Professor', False)])
def test_botao_de_emitir_so_aparece_para_quem_pode(cliente, grupo: str, ve_botao: bool):
    professor = _professor()
    # O grupo Professor tem edu.view_professor: abre a tela de qualquer professor, mas não emite a declaração dele.
    cliente.force_login(_servidor_com(grupo, setor=_no_campus_do(professor)))

    resposta = cliente.get(f'/edu/professor/{professor.pk}/?tab=disciplinas')

    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert 'Nenhuma disciplina ministrada neste ano/periodo.' in conteudo  # a aba renderizou
    assert ('Emitir Declaração de Docência' in conteudo) is ve_botao
