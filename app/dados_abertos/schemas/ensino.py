from ninja import Schema
from django.core.cache import cache
from rh.models import Servidor
from edu.models import Matriz, ComponenteCurricular, CalendarioAcademico, CursoCampus, Turno


class EstatisticaAlunoCursoSchema(Schema):
    nome_do_curso: str
    campus: str
    quantidade_alunos: int
    quantidade_formados: int

    @staticmethod
    def resolve_nome_do_curso(obj):
        return obj['descricao_historico']

    @staticmethod
    def resolve_campus(obj):
        return obj['diretoria__setor__uo__sigla']

    @staticmethod
    def resolve_quantidade_alunos(obj):
        return obj['total_alunos']

    @staticmethod
    def resolve_quantidade_formados(obj):
        return obj['alunos_formados']


class EstatisticaAlunoGeralSchema(Schema):
    quantidade_total_alunos: int
    quantidade_total_matriculas_trancadas: int


class CursoSchema(Schema):
    nome_do_curso: str
    nome_do_coordenador: str = None
    email: str = None
    telefone: str = None
    modalidade: str = None
    grau: str = None
    uf: str = None
    municipio_do_campus: str = None
    duracao: str = None
    turno_de_oferta: str = None
    vagas_anuais: int = None

    @staticmethod
    def resolve_nome_do_curso(matriz_curso):
        return matriz_curso.curso_campus.descricao_historico

    @staticmethod
    def resolve_nome_do_coordenador(matriz_curso):
        return matriz_curso.curso_campus.coordenador.nome_usual if matriz_curso.curso_campus.coordenador else ''

    @staticmethod
    def resolve_email(matriz_curso):
        return matriz_curso.curso_campus.coordenador.email_notificacao if matriz_curso.curso_campus.coordenador else ''

    @staticmethod
    def resolve_telefone(matriz_curso):
        return matriz_curso.curso_campus.diretoria.setor.telefones()

    @staticmethod
    def resolve_modalidade(matriz_curso):
        return matriz_curso.curso_campus.modalidade.descricao

    @staticmethod
    def resolve_grau(matriz_curso):
        return matriz_curso.curso_campus.modalidade.nivel_ensino.descricao

    @staticmethod
    def resolve_uf(matriz_curso):
        return matriz_curso.curso_campus.diretoria.setor.uo.municipio.uf

    @staticmethod
    def resolve_municipio_do_campus(matriz_curso):
        return matriz_curso.curso_campus.diretoria.setor.uo.municipio.nome

    @staticmethod
    def resolve_duracao(matriz_curso):
        duracao = ''
        if matriz_curso.curso_campus.periodicidade == CursoCampus.PERIODICIDADE_ANUAL:
            duracao = f'{matriz_curso.matriz.qtd_periodos_letivos} anos'
        elif matriz_curso.curso_campus.periodicidade == CursoCampus.PERIODICIDADE_SEMESTRAL:
            duracao = f'{matriz_curso.matriz.qtd_periodos_letivos} semestres'
        else:
            for inicio, fim in (
                CalendarioAcademico.objects.filter(turma__curso_campus=matriz_curso.curso_campus)
                .order_by('-id')
                .values_list('data_inicio', 'data_fim')[0:1]
            ):
                duracao = f'{(fim - inicio).days} dias'
        return duracao

    @staticmethod
    def resolve_turno_de_oferta(matriz_curso):
        turnos = cache.get('turnos')
        if turnos is None:
            turnos = {turno.pk: turno.descricao for turno in Turno.objects.all()}
            cache.set('turnos', turnos)
        return ', '.join(
            [
                turnos[pk]
                for pk in matriz_curso.curso_campus.aluno_set.filter(turno__isnull=False).values_list('turno', flat=True).order_by('turno').distinct()
            ]
        )

    @staticmethod
    def resolve_vagas_anuais(matriz_curso):
        return matriz_curso.curso_campus.quantidade_vagas or 0


class DisciplinaSchema(Schema):
    nome_da_disciplina: str
    nome_do_curso: str
    campus: str
    carga_horaria: int
    pre_requisito: str

    @staticmethod
    def resolve_nome_da_disciplina(matriz_curso):
        return matriz_curso['matriz__componentecurricular__componente__descricao_historico']

    @staticmethod
    def resolve_nome_do_curso(matriz_curso):
        return matriz_curso['curso_campus__descricao_historico']

    @staticmethod
    def resolve_campus(matriz_curso):
        return matriz_curso['curso_campus__diretoria__setor__uo__sigla']

    @staticmethod
    def resolve_carga_horaria(matriz_curso):
        return Matriz.objects.get(pk=matriz_curso['matriz']).get_ch_total()

    @staticmethod
    def resolve_pre_requisito(matriz_curso):
        return ', '.join(
            ComponenteCurricular.objects.get(pk=matriz_curso['matriz__componentecurricular']).pre_requisitos.values_list(
                'componente__descricao_historico', flat=True
            )
        )


class ProfessorSchema(Schema):
    nome_do_professor: str
    campus: str | None = None
    diretoria_academica: str | None = None
    regime_de_trabalho: str | None = None
    nce: str
    disciplina_de_ingresso: str

    @staticmethod
    def resolve_nome_do_professor(professor):
        return professor.get_nome()

    @staticmethod
    def resolve_campus(professor):
        uo = professor.get_uo()
        return uo.sigla if uo else ''

    @staticmethod
    def resolve_diretoria_academica(professor):
        return professor.get_sigla_diretoria()

    @staticmethod
    def resolve_regime_de_trabalho(professor):
        return Servidor.objects.filter(matricula=professor.vinculo.user.username).values_list('regime_juridico__nome', flat=True).first()

    @staticmethod
    def resolve_nce(professor):
        return ', '.join(professor.nce.values_list('descricao', flat=True))

    @staticmethod
    def resolve_disciplina_de_ingresso(professor):
        return professor.disciplina.descricao if professor.disciplina_id else ''


class AtividadePitSchema(Schema):
    nome: str
    ch_semanal: int


class PitSchema(Schema):
    nome_do_professor: str
    campus: str
    diretoria_academica: str
    semestre_de_referencia: str
    atividade_e_ch_semanal: list[AtividadePitSchema]
    total_semanal: int

    @staticmethod
    def resolve_nome_do_professor(pit):
        return pit.professor.get_nome()

    @staticmethod
    def resolve_campus(pit):
        uo = pit.professor.get_uo()
        return uo.sigla if uo else ''

    @staticmethod
    def resolve_diretoria_academica(pit):
        return pit.professor.get_sigla_diretoria()

    @staticmethod
    def resolve_semestre_de_referencia(pit):
        return f'{pit.ano_letivo}/{pit.periodo_letivo}'

    @staticmethod
    def resolve_atividade_e_ch_semanal(pit):
        ch = pit.get_cargas_horarias()
        atividades = {
            'Diários Regulares': ch[2],
            'Diários FIC': ch[3],
            'Minicurso': ch[4],
            'Diários Especiais': ch[5],
            'Preparação de Manutenção do Ensino': ch[6],
            'Apoio ao Ensino': ch[7],
            'Projetos de Ensino': ch[8],
            'Orientação aos Alunos': ch[9],
            'Reuniões': ch[10],
            'Pesquisa': ch[11],
            'Extensão': ch[12],
            'Gestão': ch[13],
        }
        pit.total = ch[14]
        return [{'nome': nome, 'ch_semanal': ch_semanal} for nome, ch_semanal in atividades.items()]

    @staticmethod
    def resolve_total_semanal(pit):
        return pit.total


class TccSchema(Schema):
    titulo_do_trabalho: str
    autores: str
    campus: str
    curso: str
    tipo_do_curso: str
    data_do_documento: str

    @staticmethod
    def resolve_titulo_do_trabalho(tcc):
        return f'{tcc.tipo} - {tcc.titulo}'

    @staticmethod
    def resolve_autores(tcc):
        return tcc.matricula_periodo.aluno.pessoa_fisica.nome

    @staticmethod
    def resolve_campus(tcc):
        return tcc.matricula_periodo.aluno.curso_campus.diretoria.setor.uo.sigla

    @staticmethod
    def resolve_curso(tcc):
        return tcc.matricula_periodo.aluno.curso_campus.descricao_historico

    @staticmethod
    def resolve_tipo_do_curso(tcc):
        return tcc.matricula_periodo.aluno.curso_campus.modalidade.descricao

    @staticmethod
    def resolve_data_do_documento(tcc):
        return tcc.documento_cadastrado_em.strftime('%d/%m/%Y')
