from django.db.models import Count, Q
from ninja import Router

from djtools.ninja.router import get
from edu.models import (
    Aluno,
    CursoCampus,
    MatrizCurso,
    Professor,
    ProjetoFinal,
    SituacaoMatricula,
)
from pit_rit_v2.models import PlanoIndividualTrabalhoV2

from ..schemas.ensino import (
    CursoSchema,
    DisciplinaSchema,
    EstatisticaAlunoCursoSchema,
    EstatisticaAlunoGeralSchema,
    PitSchema,
    ProfessorSchema,
    TccSchema,
)

router = Router(tags=['Dados Abertos'])


@get(
    router,
    '/estatistica/alunos_curso/',
    response=list[EstatisticaAlunoCursoSchema],
    auth=False,
    summary='Estatística alunos (curso)',
    description='Retorna nome do curso, campus, quantidade de alunos e quantidade de formados.',
)
def estatistica_alunos_curso(request):
    queryset = (
        CursoCampus.objects.annotate(
            total_alunos=Count('aluno', distinct=True),
            alunos_formados=Count(
                'aluno',
                filter=Q(aluno__situacao__id__in=[SituacaoMatricula.FORMADO, SituacaoMatricula.CONCLUIDO]),
                distinct=True,
            ),
        )
        .values('descricao_historico', 'diretoria__setor__uo__sigla', 'total_alunos', 'alunos_formados')
        .order_by('descricao')
    )
    return queryset


@get(
    router,
    '/estatistica/alunos_geral/',
    response=EstatisticaAlunoGeralSchema,
    auth=False,
    summary='Estatística de alunos (geral)',
    description='Retorna quantidade de alunos e quantidade de alunos trancados.',
)
def estatistica_alunos_geral(request):
    qs_alunos = Aluno.objects.filter(Q(participanteturmaminicurso__turma__gerar_matricula=True) | Q(matriz_id__isnull=False)).distinct()
    quantidade_total_alunos = qs_alunos.count()
    quantidade_total_matriculas_trancadas = qs_alunos.filter(situacao_id=SituacaoMatricula.TRANCADO).count()
    result = EstatisticaAlunoGeralSchema(
        quantidade_total_alunos=quantidade_total_alunos, quantidade_total_matriculas_trancadas=quantidade_total_matriculas_trancadas
    )
    return result


@get(
    router,
    '/cursos/',
    response=list[CursoSchema],
    auth=False,
    summary='Cursos',
    description='Retorna nome do curso, nome/email/telefone do coordenador, modalidade, grau, uf, município, duração, turno e quantidade de vagas dos cursos.',
)
def cursos(request):
    return MatrizCurso.objects.select_related('curso_campus__diretoria__setor__uo').exclude(curso_campus__ch_total__gt=0)


@get(
    router,
    '/disciplinas/',
    response=list[DisciplinaSchema],
    auth=False,
    summary='Disciplinas',
    description='Retorna nome da disciplina, nome do curso, campus, carga-horária e pre-requisitos das disciplinas.',
)
def disciplinas(request):
    queryset = (
        MatrizCurso.objects.order_by('matriz')
        .select_related('curso_campus__diretoria__setor__uo', 'atriz__componentecurricular__componente')
        .values(
            'matriz__componentecurricular__componente__descricao_historico',
            'curso_campus__descricao_historico',
            'curso_campus__diretoria__setor__uo__sigla',
            'matriz',
            'matriz__componentecurricular',
        )
    )
    return queryset


@get(
    router,
    '/professores/',
    response=list[ProfessorSchema],
    auth=False,
    summary='Professores',
    description='Retorna nome, campus, diretoria acadêmica, regime de trabalho, NCE e disciplina de ingresso dos professores',
)
def professres(request):
    queryset = Professor.objects.filter(vinculo__setor__isnull=False).order_by('id').select_related('vinculo__pessoa__pessoafisica')
    return queryset


@get(
    router,
    '/pit/',
    response=list[PitSchema],
    auth=False,
    summary='PIT',
    description='Retorna nome, campus, diretoria acadêmica, semestre de referência, atividades com cargas-horárias e carga-horária semanal dos PITs dos professores.',
)
def pit(request):
    queryset = (
        PlanoIndividualTrabalhoV2.objects.filter(professor__vinculo__setor__isnull=False)
        .select_related('professor__vinculo__pessoa__pessoafisica')
        .filter(publicado=True)
    )
    return queryset


@get(
    router,
    '/tcc/',
    response=list[TccSchema],
    auth=False,
    summary='TCC',
    description='Retorna nome, campus, diretoria acadêmica, semestre de referência, atividades com cargas-horárias e carga-horária semanal dos PITs dos professores.',
)
def tcc(request):
    queryset = ProjetoFinal.objects.filter(documento_cadastrado_em__isnull=False).select_related(
        'matricula_periodo__aluno__curso_campus__diretoria__setor__uo'
    )
    return queryset
