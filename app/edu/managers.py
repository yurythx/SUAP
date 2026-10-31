import datetime

from django.apps import apps
from django.conf import settings
from django.db import ProgrammingError, models
from django.db.models import Count, Exists, F, OuterRef, Q, Sum
from django.db.utils import OperationalError

from comum.utils import get_sigla_reitoria, tl

GRUPOS = [
    'Administrador Acadêmico',
    'Secretário Acadêmico',
    'Diretor Acadêmico',
    'Visualizador de Informações Acadêmicas',
    'Auditor',
    'Estagiário Acadêmico Sistêmico',
]


class FiltroDiretoriaManager(models.Manager):
    def __init__(self, key=None):
        super().__init__()
        self.key = key

    def get_queryset(self):
        qs = super().get_queryset()
        ids = self.get_ids()
        if ids:
            from edu.models.diretorias import Diretoria

            if Diretoria.objects.filter(tipo=Diretoria.TIPO_SISTEMICA, setor_id__in=ids).exists():
                return qs

            ids_diretoria_ensino = Diretoria.objects.filter(tipo=Diretoria.TIPO_DIRETORIA_ENSINO, setor_id__in=ids).values_list('id', flat=True)
            if ids_diretoria_ensino:
                ids_uos_diretoria_ensino = Diretoria.objects.filter(id__in=ids_diretoria_ensino).values_list('setor__uo_id', flat=True)
                ids.extend(Diretoria.objects.filter(setor__uo_id__in=ids_uos_diretoria_ensino).values_list('setor_id', flat=True))

            if self.key:
                filtro = {f'{self.key}__setor_id__in': ids}
            else:
                filtro = {'setor_id__in': ids}

            qs = qs.filter(**filtro)
        return qs

    def get_ids(self):
        ids = []
        try:
            user = tl.get_user()
            if user is None or user.is_anonymous:
                ids = [None]
            elif user.is_superuser:
                return ids
            else:
                from comum.models import UsuarioGrupoSetor
                from edu.models.diretorias import Diretoria

                ids_diretoria_sistemica = Diretoria.objects.filter(tipo=Diretoria.TIPO_SISTEMICA).values_list('setor_id', flat=True)
                eh_sistemico = (
                    ids_diretoria_sistemica
                    and UsuarioGrupoSetor.objects.filter(usuario_grupo__user=user, setor_id__in=ids_diretoria_sistemica).exists()
                )
                eh_administrador = user.groups.filter(name__in=['Administrador Acadêmico', 'Estagiário Acadêmico Sistêmico']).exists()

                if eh_sistemico or eh_administrador:
                    return ids

                groups = [
                    *GRUPOS,
                    'Apoio Acadêmico',
                    'Auxiliar de Secretaria Acadêmica',
                    'Diretor Geral',
                    'Estagiário',
                    'Membro ETEP',
                    'Organizador de Formatura',
                    'Organizador de Minicurso',
                    'Pedagogo',
                ]
                ids = list(
                    UsuarioGrupoSetor.objects.filter(usuario_grupo__user=user, usuario_grupo__group__name__in=groups)
                    .values_list('setor_id', flat=True)
                    .distinct()
                )
                if not ids:
                    if user.get_vinculo() and user.get_vinculo().setor:
                        ids = [user.get_vinculo().setor.id]
                    else:
                        ids = [None]

                qs = apps.get_model('rh', 'UnidadeOrganizacional').objects.suap().filter(sigla=get_sigla_reitoria())
                try:
                    reitoria = qs.first()
                # banco ainda não foi criado
                except OperationalError:
                    reitoria = None
                if reitoria and reitoria.setor_id in ids:
                    return []
        except ProgrammingError:
            pass
        return ids


class AbonoFaltaManager(FiltroDiretoriaManager):
    def get_queryset(self):
        user = tl.get_user()
        qs = super().get_queryset()
        filtros = Q()
        if user and user.groups.filter(name='Coordenador de Curso').exists():
            filtros |= Q(aluno__curso_campus__coordenador__user_id=user.id) | Q(aluno__curso_campus__coordenador_2__user_id=user.id)
        if user and user.groups.filter(name='Professor').exists():
            from edu.models import ProfessorDiario

            ids_alunos = (
                ProfessorDiario.objects.filter(professor__vinculo__user__username=user.username)
                .values_list('diario__matriculadiario__matricula_periodo__aluno_id', flat=True)
                .distinct()
            )
            filtros |= Q(aluno__in=ids_alunos)
        if filtros:
            return (qs | qs.model.objects.filter(filtros)).distinct()
        return qs

    def aguardando_reposicao_atividade(self, queryset: models.QuerySet | None = None, user: models.Model | None = None) -> models.QuerySet:
        qs = self.get_queryset() if queryset is None else queryset

        filtros = Q(
            deferido=True,
            motivo_ausencia_escolar__isnull=False,
            solicitacaoreposicaoatividade__isnull=False,
            solicitacaoreposicaoatividade__data_reposicao__isnull=True,
        ) & (Q(solicitacaoreposicaoatividade__deferida=True) | Q(solicitacaoreposicaoatividade__deferida__isnull=True))

        if user:
            # No mesmo filter() dos demais: mesma solicitação e mesmo diário. O aluno ainda tem de estar
            # matriculado no diário da reposição (removido dele, a reposição fica órfã), o que também o
            # põe no escopo ``locals`` do professor e dispensa esse escopo na contagem do quadro (#17795).
            diario = 'solicitacaoreposicaoatividade__item_configuracao_avaliacao__configuracao_avaliacao__diario'
            filtros &= Q(
                **{f'{diario}__professordiario__professor__vinculo__user': user, f'{diario}__matriculadiario__matricula_periodo__aluno': F('aluno')}
            )

        return qs.filter(filtros).distinct()

    def sem_abono_docente(self, queryset=None, user=None):
        qs = self.get_queryset() if queryset is None else queryset

        filtros = Q(
            deferido=True,
            motivo_ausencia_escolar__possui_previsao_normativa=False,
            falta__contabilizar=True,
        )

        if user:
            filtros &= Q(falta__matricula_diario__diario__professordiario__professor__vinculo__user=user)

        return qs.filter(filtros).distinct()


class FiltroPoloManager(FiltroDiretoriaManager):
    def __init__(self, key=None, polo_key=None):
        super().__init__()
        self.key = key
        self.polo_key = polo_key

    def get_queryset(self):
        user = tl.get_user()
        qs = super().get_queryset()
        if user and user.groups.filter(name='Coordenador de Polo EAD Sistêmico').exists():
            return qs.model.objects.all()
        elif not user or user.groups.filter(name__in=[*GRUPOS, 'Administrador EAD', 'Diretor de Avaliação e Regulação do Ensino']).exists():
            return qs
        else:
            from edu.models import CoordenadorPolo, Polo, TutorPolo

            pks = list(Polo.objects.filter(turma__curso_campus__coordenador__user=user).values_list('id', flat=True))
            pks.extend(list(TutorPolo.objects.filter(vinculo__user=user).values_list('polo_id', flat=True)))
            pks.extend(list(CoordenadorPolo.objects.filter(vinculo__user=user).values_list('polo_id', flat=True)))
            if self.polo_key:
                return qs.filter(**{f'{self.polo_key}__id__in': pks})
            else:
                return qs.filter(id__in=pks)


class FiltroUnidadeOrganizacionalManager(models.Manager):
    def __init__(self, key=None):
        super().__init__()
        self.key = key

    def campi(self):
        UnidadeOrganizacional = apps.get_model('rh', 'UnidadeOrganizacional')
        return self.get_queryset().filter(
            tipo__in=[
                UnidadeOrganizacional.TIPO_CAMPUS_EAD,
                UnidadeOrganizacional.TIPO_CAMPUS_NAO_PRODUTIVO,
                UnidadeOrganizacional.TIPO_CAMPUS_PRODUTIVO,
            ]
        )

    def get_queryset(self):
        qs = super().get_queryset()
        eh_setor_suap = settings.TIPO_ARVORE_SETORES == 'SUAP'
        if not self.key:
            if eh_setor_suap:
                qs = qs.filter(setor__codigo__isnull=True)
            else:
                qs = qs.filter()
        ids = self.get_ids()
        if ids:
            if self.key:
                filtro = {f'{self.key}__id__in': ids}
            else:
                filtro = {'id__in': ids}
            qs = qs.filter(**filtro)
        return qs

    def get_ids(self):
        from comum.models import UsuarioGrupoSetor

        user = tl.get_user()
        ids = []
        if not user or user.groups.filter(name__in=['Administrador Acadêmico', 'Estagiário Acadêmico Sistêmico']).exists():
            return ids
        elif user and user.pk:
            groups = [
                *GRUPOS,
                'Agendador de Aula de Campo EDU',
                'Coordenador de Registros Acadêmicos',
                'Coordenador de Desporto',
                'Coordenador de Curso',
                'Coordenador de Laboratório',
                'Coordenador de Modalidade Acadêmica',
                'Pedagogo',
                'Membro ETEP',
            ]
            ids = UsuarioGrupoSetor.objects.filter(usuario_grupo__user=user, usuario_grupo__group__name__in=groups).values_list(
                'setor__uo', flat=True
            )

        UnidadeOrganizacional = apps.get_model('rh', 'UnidadeOrganizacional')
        qs = UnidadeOrganizacional.objects.suap().filter(sigla=get_sigla_reitoria())
        if qs.exists() and qs[0].pk in ids:
            return []
        return ids


class DiretoriaManager(FiltroDiretoriaManager):
    def __init__(self):
        super().__init__(None)

    def get_queryset(self):
        qs = super().get_queryset()
        user = tl.get_user()
        if user and user.groups.filter(name='Coordenador de Curso').exists():
            qs_coordenador = qs.model.objects.filter(Q(cursocampus__coordenador__user_id=user.id) | Q(cursocampus__coordenador_2__user_id=user.id))
            return (qs | qs_coordenador).distinct()
        return qs

    def sem_diretores(self):
        return self.get_queryset().exclude(setor__usuariogrupo__group__name='Diretor Acadêmico')

    def sem_secretarios(self):
        return self.get_queryset().exclude(setor__usuariogrupo__group__name='Secretário Acadêmico')

    def sem_coordenadores(self):
        return self.get_queryset().exclude(setor__usuariogrupo__group__name='Coordenador de Curso')

    def sem_pedagogos(self):
        return self.get_queryset().exclude(setor__usuariogrupo__group__name='Pedagogo')


class ProjetoIntegradorManager(models.Manager):
    def get_queryset(self):
        from edu.models import Diretoria

        user = tl.get_user()
        if user is None or user.is_anonymous:
            return self.model.objects.none()

        qs = super().get_queryset()
        if user.has_group_cached(['Administrador Acadêmico']):
            return qs

        if user.has_group_cached(['Aluno']):
            return qs.filter(participantes__matricula_periodo__aluno__vinculos=user.get_vinculo())

        filtros = Q()
        if user.has_group_cached(['Secretário Acadêmico', 'Diretor Acadêmico']):
            pks = Diretoria.locals.values_list('pk', flat=True)
            filtros |= Q(diario__turma__curso_campus__diretoria__in=pks)

        if user.has_group_cached(['Professor']):
            filtros |= Q(professores__vinculo=user.get_vinculo()) | Q(diario__professordiario__professor__vinculo=user.get_vinculo())

        if user.has_group_cached(['Coordenador de Curso']):
            filtros |= Q(diario__turma__curso_campus__coordenador=user.get_vinculo()) | Q(
                diario__turma__curso_campus__coordenador_2=user.get_vinculo()
            )

        if not filtros:
            return self.model.objects.none()

        return qs.filter(filtros).distinct()


class DiarioQuery(models.QuerySet):
    def sem_professores(self):
        from comum.models import Configuracao

        ano_letivo_atual = int(Configuracao.get_valor_por_chave('edu', 'ano_letivo_atual') or 1)
        periodo_letivo_atual = int(Configuracao.get_valor_por_chave('edu', 'periodo_letivo_atual') or 1)
        qs = self.exclude(professordiario__id__isnull=False)
        if periodo_letivo_atual == 1:
            qs = qs.exclude(segundo_semestre=True, ano_letivo__ano=ano_letivo_atual)
        return qs

    def sem_local_aula(self):
        from comum.models import Configuracao
        from edu.models import ComponenteCurricular

        ano_letivo_atual = int(Configuracao.get_valor_por_chave('edu', 'ano_letivo_atual') or 1)
        periodo_letivo_atual = int(Configuracao.get_valor_por_chave('edu', 'periodo_letivo_atual') or 1)
        qs = self.filter(turma__curso_campus__diretoria__ead=False, local_aula_id__isnull=True, local_laboratorio_id__isnull=True)
        # plano de retomada de aulas em virtude da pandemia (COVID19)
        qs = qs.exclude(turma__pertence_ao_plano_retomada=True)
        if periodo_letivo_atual == 1:
            qs = qs.exclude(segundo_semestre=True, ano_letivo__ano=ano_letivo_atual)
        qs = qs.exclude(
            componente_curricular__tipo__in=[
                ComponenteCurricular.TIPO_PRATICA_PROFISSIONAL,
                ComponenteCurricular.TIPO_TRABALHO_CONCLUSAO_CURSO,
                ComponenteCurricular.TIPO_SEMINARIO,
            ]
        )
        return qs

    def sem_horario_aula(self):
        from edu.models import ComponenteCurricular, HorarioAulaDiario

        qs = self.filter(turma__curso_campus__diretoria__ead=False)

        diarios_pks = HorarioAulaDiario.objects.all().values_list('diario_id', flat=True).distinct()
        qs = qs.exclude(pk__in=diarios_pks)

        qs = qs.exclude(
            componente_curricular__tipo__in=[
                ComponenteCurricular.TIPO_PRATICA_PROFISSIONAL,
                ComponenteCurricular.TIPO_TRABALHO_CONCLUSAO_CURSO,
                ComponenteCurricular.TIPO_SEMINARIO,
            ]
        )
        return qs

    def sem_aluno(self):
        return self.filter(matriculadiario__isnull=True)

    def pendentes(self) -> DiarioQuery:
        from edu.models import MatriculaDiario

        # Correlacionado e preguiçoso (#17801): o filtro de quem chama (ex.: painel da diretoria)
        # restringe os diários antes, e cada um só sonda as próprias matrículas pelo índice de diario_id.
        matriculas_pendentes = MatriculaDiario.objects.filter(
            Q(diario__componente_curricular__qtd_avaliacoes__gte=1, nota_1__isnull=True)
            | Q(diario__componente_curricular__qtd_avaliacoes__gte=2, nota_2__isnull=True)
            | Q(diario__componente_curricular__qtd_avaliacoes__gte=4, nota_3__isnull=True)
            | Q(diario__componente_curricular__qtd_avaliacoes__gte=4, nota_4__isnull=True)
            | Q(prova_final_pendente=True),
            diario=OuterRef('pk'),
            situacao__in=[MatriculaDiario.SITUACAO_CURSANDO, MatriculaDiario.SITUACAO_PROVA_FINAL],
        )
        return self.filter(Exists(matriculas_pendentes), calendario_academico__data_fechamento_periodo__lt=datetime.datetime.now())

    def com_ch_pendente(self):
        from edu.models import Aula, MatriculaDiario

        ids_diarios_cursando = (
            MatriculaDiario.objects.filter(
                situacao__in=[MatriculaDiario.SITUACAO_CURSANDO, MatriculaDiario.SITUACAO_PROVA_FINAL],
                diario__calendario_academico__data_fechamento_periodo__lt=datetime.datetime.now(),
            )
            .values_list('diario_id', flat=True)
            .distinct()
        )

        qs_diarios_ch_pendente = (
            Aula.objects.filter(professor_diario__diario__pk__in=ids_diarios_cursando)
            .order_by('professor_diario__diario__pk')
            .values('professor_diario__diario__pk')
            .annotate(
                ch_minima=(
                    F('professor_diario__diario__componente_curricular__ch_presencial')
                    * (F('professor_diario__diario__percentual_minimo_ch') / 100.0)
                ),
                total_aulas=Sum('quantidade'),
            )
            .filter(total_aulas__lt=F('ch_minima'))
        )

        ids_diarios_ch_pendente = qs_diarios_ch_pendente.values_list('professor_diario__diario__pk', flat=True)

        return self.filter(pk__in=ids_diarios_ch_pendente)

    def em_andamento(self):
        now = datetime.datetime.now()
        return self.filter(calendario_academico__data_inicio__lte=now, calendario_academico__data_fechamento_periodo__gte=now).order_by('id')

    def semestrais_em_cursos_anuais(self):
        return self.filter(calendario_academico__qtd_etapas=4, componente_curricular__qtd_avaliacoes=2)

    def em_curso(self):
        qs = self
        qs1 = qs.filter(componente_curricular__qtd_avaliacoes__lt=2, posse_etapa_1=1)
        qs2 = qs.filter(componente_curricular__qtd_avaliacoes=2, posse_etapa_2=1)
        qs3 = qs.filter(componente_curricular__qtd_avaliacoes=4)
        qs3 = qs3.filter(posse_etapa_3=1) | qs3.filter(posse_etapa_4=1)

        return qs1 | qs2 | qs3

    def entregues(self):
        from edu.models.diarios import Diario

        return self.filter(posse_etapa_5=Diario.POSSE_REGISTRO_ESCOLAR)

    def nao_entregues(self):
        from edu.models.diarios import Diario

        return self.filter(posse_etapa_5=Diario.POSSE_PROFESSOR, calendario_academico__data_fechamento_periodo__lt=datetime.datetime.now())

    def frequencias_pendentes(self):
        from edu.models import MatriculaDiario

        return (
            self.filter(matriculadiario__situacao__in=[MatriculaDiario.SITUACAO_CURSANDO, MatriculaDiario.SITUACAO_PROVA_FINAL])
            .exclude(professordiario__aula__registro_frequencia_confirmado=True)
            .distinct()
        )

    def suspensos(self):
        return self.filter(suspensaodiario__inicio__lte=datetime.date.today()).filter(
            Q(suspensaodiario__fim__isnull=True) | Q(suspensaodiario__fim__gt=datetime.date.today())
        )

    def sem_aulas_registradas(self):
        from edu.models import MatriculaDiario

        return (
            self.filter(
                matriculadiario__situacao__in=[MatriculaDiario.SITUACAO_CURSANDO, MatriculaDiario.SITUACAO_PROVA_FINAL],
                calendario_academico__data_fechamento_periodo__gte=datetime.datetime.now(),
            )
            .annotate(num_aulas=Count('professordiario__aula'))
            .filter(num_aulas=0)
        )


class DiarioManager(models.Manager):
    def sem_professores(self):
        return self.get_queryset().sem_professores()

    def sem_local_aula(self):
        return self.get_queryset().sem_local_aula()

    def sem_horario_aula(self):
        return self.get_queryset().sem_horario_aula()

    def pendentes(self) -> DiarioQuery:
        return self.get_queryset().pendentes()

    def em_andamento(self):
        return self.get_queryset().em_andamento()

    def semestrais_em_cursos_anuais(self):
        return self.get_queryset().semestrais_em_cursos_anuais()

    def em_curso(self):
        return self.get_queryset().em_curso()

    def entregues(self):
        return self.get_queryset().entregues()

    def get_queryset(self):
        return DiarioQuery(self.model, using=self._db)


class DiarioLocalManager(FiltroDiretoriaManager, DiarioManager):
    def __init__(self):
        super().__init__('turma__curso_campus__diretoria')

    def by_user(self, user=None):
        qs = super().get_queryset()
        if not user:
            user = tl.get_user()

        if user:
            setor = user.get_vinculo().setor

            # Coordenadores de polo podem visualizar diarios de turmas dos polos que ele coordena
            if user.groups.filter(name='Coordenador de Polo EAD').exists():
                from edu.models import CoordenadorPolo

                ids = CoordenadorPolo.objects.filter(vinculo=user.get_vinculo()).values_list('polo__id')
                qs = qs | qs.model.objects.filter(turma__polo__id__in=ids)

            # Coordenadores de cursos podem visualizar diarios de turmas dos cursos que ele coordena
            if user.groups.filter(name='Coordenador de Curso').exists():
                qs = (
                    qs
                    | qs.model.objects.filter(turma__curso_campus__coordenador=user.get_vinculo())
                    | qs.model.objects.filter(turma__curso_campus__coordenador_2=user.get_vinculo())
                )

            # Diretores Acadêmicos podem visualizar diarios de sua diretoria ou diarios de professores de sua diretoria

            if setor and user.groups.filter(name='Diretor Acadêmico').exists():
                from edu.models.diarios import Diario

                qs = qs | qs.model.objects.filter(turma__curso_campus__diretoria__setor__uo=setor.uo_id)
                qs = qs | Diario.objects.filter(professordiario__professor__vinculo__setor__uo=setor.uo_id)

            if user.groups.filter(name='Auxiliar de Secretaria Acadêmica').exists():
                from comum.models import UsuarioGrupoSetor
                from edu.models.diarios import Diario

                ids_setores_asa = list(
                    UsuarioGrupoSetor.objects.filter(
                        usuario_grupo__user=user, usuario_grupo__group__name='Auxiliar de Secretaria Acadêmica'
                    ).values_list('setor_id', flat=True)
                )
                qs = qs | qs.model.objects.filter(turma__curso_campus__diretoria__setor__in=ids_setores_asa)

            # Diretor Geral e Comissão de horário podem visualizar todos os diarios do campus
            if setor and user.groups.filter(name__in=['Diretor Geral', 'Comissão de Horários']).exists():
                qs = qs | qs.model.objects.filter(turma__curso_campus__diretoria__setor__uo=setor.uo_id)

            # Coordenador de Modalidade Acadêmica
            if user.groups.filter(name='Coordenador de Modalidade Acadêmica').exists():
                qs = qs | qs.model.objects.filter(
                    turma__curso_campus__modalidade__id__in=list(
                        user.get_vinculo().relacionamento.coordenadormodalidade_set.values_list('modalidades', flat=True)
                    )
                )

            # Professores podem acessar todos os seus diários
            if user.groups.filter(name='Professor').exists():
                qs = qs | qs.model.objects.filter(professordiario__professor__vinculo__user=user)

        return qs.select_related('componente_curricular__componente__nivel_ensino', 'turma', 'ano_letivo').distinct()

    def get_queryset(self):
        return self.by_user()


class DiarioEspecialManager(FiltroDiretoriaManager):
    def __init__(self):
        super().__init__('diretoria')

    def by_user(self, user=None):
        qs = super().get_queryset()
        if not user:
            user = tl.get_user()

        if user:
            # Coordenadores de cursos podem visualizar diarios de turmas dos cursos que ele coordena
            if user.groups.filter(name='Coordenador de Curso').exists():
                qs = qs | qs.model.objects.filter(diretoria__setor__uo=user.get_vinculo().setor.uo)

        return qs

    def get_queryset(self):
        return self.by_user()

    def sem_professores(self):
        return self.get_queryset().exclude(professores__isnull=False)

    def sem_local_aula(self):
        return self.get_queryset().filter(sala__isnull=True)

    def sem_horario_aula(self):
        return self.get_queryset().exclude(horarioauladiarioespecial__id__isnull=False)


class MatriculaDiarioLocalManager(FiltroDiretoriaManager):
    def __init__(self):
        super().__init__('diario__turma__curso_campus__diretoria')

    def by_user(self, user=None):
        qs = super().get_queryset()
        if not user:
            user = tl.get_user()

        if user:
            # Coordenadores de polo podem visualizar diarios de turmas dos polos que ele coordena
            if user.groups.filter(name='Coordenador de Polo EAD').exists():
                from edu.models import CoordenadorPolo

                ids = CoordenadorPolo.objects.filter(vinculo=user.get_vinculo()).values_list('polo__id')
                qs = qs | qs.model.objects.filter(diario__turma__polo__id__in=ids)

            # Coordenadores de cursos podem visualizar diarios de turmas dos cursos que ele coordena
            if user.groups.filter(name='Coordenador de Curso').exists():
                qs = (
                    qs
                    | qs.model.objects.filter(diario__turma__curso_campus__coordenador=user.get_vinculo())
                    | qs.model.objects.filter(diario__turma__curso_campus__coordenador_2=user.get_vinculo())
                )

        return qs

    def get_queryset(self):
        return self.by_user()


class ProfessorDiarioLocalManager(FiltroDiretoriaManager):
    def __init__(self):
        super().__init__('diario__turma__curso_campus__diretoria')

    def by_user(self, user=None):
        qs = super().get_queryset()
        if not user:
            user = tl.get_user()

        if user:
            # Coordenadores de polo podem visualizar diarios de turmas dos polos que ele coordena
            if user.groups.filter(name='Coordenador de Polo EAD').exists():
                from edu.models import CoordenadorPolo

                ids = CoordenadorPolo.objects.filter(vinculo=user.get_vinculo()).values_list('polo__id')
                qs = qs | qs.model.objects.filter(diario__turma__polo__id__in=ids)

            # Coordenadores de cursos podem visualizar diarios de turmas dos cursos que ele coordena
            if user.groups.filter(name='Coordenador de Curso').exists():
                qs = (
                    qs
                    | qs.model.objects.filter(diario__turma__curso_campus__coordenador=user.get_vinculo())
                    | qs.model.objects.filter(diario__turma__curso_campus__coordenador_2=user.get_vinculo())
                )
        return qs

    def get_queryset(self):
        return self.by_user()


class RegistroConvocacaoENADEManager(models.Manager):
    def convocacoes_avaliacao_pratica(self) -> models.QuerySet:
        from edu.models.enade import RegistroConvocacaoENADE

        return (
            self.get_queryset()
            .filter(tipo_convocacao=RegistroConvocacaoENADE.TIPO_CONVOCACAO_CONCLUINTE_AP)
            .exclude(situacao=RegistroConvocacaoENADE.SITUACAO_AUSENTE)
        )


class TurmaQuery(models.QuerySet):
    def pendentes(self) -> TurmaQuery:
        from edu.models import Diario

        # Correlacionado (#17815): cada turma sonda só os próprios diários pendentes, no escopo de
        # ``Diario.locals``, e o filtro de quem chama (ex.: curso no painel do coordenador) restringe
        # as turmas antes. Com ``diario__in`` o Postgres avaliava os pendentes da instituição inteira.
        # O ``Exists`` não duplica turmas: o ``.distinct()`` do join antigo não é mais necessário.
        return self.filter(Exists(Diario.locals.pendentes().filter(turma=OuterRef('pk')))).order_by('id')

    def em_andamento(self):
        from edu.models import Diario

        return self.filter(diario__in=Diario.locals.em_andamento()).order_by('id').distinct()


class TurmaManager(models.Manager):
    def get_queryset(self):
        return TurmaQuery(self.model, using=self._db)

    def pendentes(self):
        return self.get_queryset().pendentes()

    def em_andamento(self):
        return self.get_queryset().em_andamento()


class TurmaLocalManager(FiltroDiretoriaManager, TurmaManager):
    def __init__(self):
        super().__init__('curso_campus__diretoria')

    def by_user(self, user=None):
        qs = super().get_queryset()
        if not user:
            user = tl.get_user()

        if user:
            setor = user.get_vinculo().setor

            # Coordenadores de polo podem visualizar turmas dos polos que ele coordena
            if user.groups.filter(name='Coordenador de Polo EAD').exists():
                from edu.models import CoordenadorPolo

                ids = CoordenadorPolo.objects.filter(vinculo=user.get_vinculo()).values_list('polo__id')
                qs = qs | qs.model.objects.filter(polo__id__in=ids)

            # Coordenadores de cursos podem visualizar turmas dos cursos que ele coordena
            if user.groups.filter(name='Coordenador de Curso').exists():
                qs = (
                    qs
                    | qs.model.objects.filter(curso_campus__coordenador=user.get_vinculo())
                    | qs.model.objects.filter(curso_campus__coordenador_2=user.get_vinculo())
                )

            if setor and user.groups.filter(name__in=['Diretor Geral', 'Auxiliar de Secretaria Acadêmica', 'Apoio Acadêmico']).exists():
                qs = qs | qs.model.objects.filter(curso_campus__diretoria__setor__uo=setor.uo_id)

            # Coordenador de Modalidade Acadêmica
            if user.groups.filter(name='Coordenador de Modalidade Acadêmica').exists():
                qs = qs | qs.model.objects.filter(
                    curso_campus__modalidade__id__in=user.get_vinculo().relacionamento.coordenadormodalidade_set.values_list('modalidades', flat=True)
                )

        return qs.distinct()

    def get_queryset(self):
        return self.by_user()


class MatrizQuery(models.QuerySet):
    def vazias(self):
        return self.exclude(componentecurricular__id__isnull=False)

    def incompletas(self):
        return self.filter(inconsistente=True)


class MatrizManager(models.Manager):
    def get_queryset(self):
        return MatrizQuery(self.model, using=self._db)

    def vazias(self):
        return self.get_queryset().vazias()

    def incompletas(self):
        return self.get_queryset().incompletas()


class SolicitacaoUsuarioManager(FiltroUnidadeOrganizacionalManager):
    def __init__(self):
        super().__init__('uo')

    def pendentes(self):
        return self.get_queryset().exclude(avaliador__id__isnull=False)


class SolicitacaoRelancamentoEtapaManager(FiltroUnidadeOrganizacionalManager):
    def __init__(self):
        super().__init__('uo')

    def pendentes(self):
        return self.get_queryset().exclude(avaliador__id__isnull=False)


class SolicitacaoProrrogacaoEtapaManager(FiltroDiretoriaManager):
    def __init__(self):
        super().__init__('professor_diario__diario__turma__curso_campus__diretoria')

    def pendentes(self):
        return self.get_queryset().exclude(avaliador__id__isnull=False)


class AtividadeComplementarManager(FiltroDiretoriaManager):
    def __init__(self):
        super().__init__('aluno__curso_campus__diretoria')

    def get_queryset(self):
        qs = super().get_queryset()
        user = tl.get_user()
        if user and user.groups.filter(name='Coordenador de Curso').exists():
            qs_coordenador = qs.model.objects.filter(
                Q(aluno__curso_campus__coordenador__user_id=user.id) | Q(aluno__curso_campus__coordenador_2__user_id=user.id)
            )
            return (qs | qs_coordenador).distinct()
        return qs

    def pendentes(self):
        return self.get_queryset().filter(deferida__isnull=True)


class AtividadeAprofundamentoManager(FiltroDiretoriaManager):
    def __init__(self):
        super().__init__('aluno__curso_campus__diretoria')

    def get_queryset(self):
        qs = super().get_queryset()
        user = tl.get_user()
        if user and user.groups.filter(name='Coordenador de Curso').exists():
            qs_coordenador = qs.model.objects.filter(
                Q(aluno__curso_campus__coordenador__user_id=user.id) | Q(aluno__curso_campus__coordenador_2__user_id=user.id)
            )
            return (qs | qs_coordenador).distinct()
        return qs

    def pendentes(self):
        return self.get_queryset().filter(deferida__isnull=True)


class MatrizCursoManager(FiltroDiretoriaManager):
    def __init__(self):
        super().__init__('curso_campus__diretoria')

    def get_queryset(self):
        qs = super().get_queryset()
        user = tl.get_user()
        if user and user.groups.filter(name='Coordenador de Curso').exists():
            qs_coordenador = qs.model.objects.filter(Q(curso_campus__coordenador__user_id=user.id) | Q(curso_campus__coordenador_2__user_id=user.id))
            return (qs | qs_coordenador).distinct()
        return qs


class ConfiguracaoPedidoMatriculaManager(FiltroDiretoriaManager):
    def __init__(self):
        super().__init__('diretorias')

    def get_queryset(self):
        qs = super().get_queryset()
        user = tl.get_user()
        if user and user.groups.filter(name='Coordenador de Curso').exists():
            qs_coordenador = qs.model.objects.filter(Q(cursos__coordenador__user_id=user.id) | Q(cursos__coordenador_2__user_id=user.id))
            return (qs | qs_coordenador).distinct()
        return qs


class CursoCampusQuery(models.QuerySet):
    def sem_coordenadores(self):
        return self.filter(coordenador__isnull=True, ativo=True)

    def com_coordenadores(self):
        return self.filter(coordenador__isnull=False)

    def nao_vinculados_diretoria(self):
        return self.filter(diretoria__isnull=True)

    def sob_coordenacao_de(self, vinculo):
        return self.filter(coordenador=vinculo)

    def integralizados(self):
        return self.filter(aluno__matriz_id__isnull=False, aluno__codigo_academico__isnull=False).distinct()

    def migrados(self):
        return self.filter(codigo_academico__isnull=False).distinct()


class CursoCampusManager(models.Manager):
    def get_queryset(self):
        return CursoCampusQuery(self.model, using=self._db).select_related('diretoria__setor__uo')

    def sem_coordenadores(self):
        return self.get_queryset().sem_coordenadores()

    def com_coordenadores(self):
        return self.get_queryset().com_coordenadores()

    def nao_vinculados_diretoria(self):
        return self.get_queryset().nao_vinculados_diretoria()

    def sob_coordenacao_de(self, vinculo):
        return self.get_queryset().sob_coordenacao_de(vinculo)

    def integralizados(self):
        return self.get_queryset().integralizados()

    def migrados(self):
        return self.get_queryset().migrados()


class MinicursoObjectsManager(models.Manager):
    def get_queryset(self):
        from edu.models import Modalidade

        return super().get_queryset().filter(modalidade_id=Modalidade.FIC_MENOS).distinct()


class MinicursoLocalsManager(FiltroDiretoriaManager):
    def __init__(self):
        super().__init__('diretoria')

    def get_queryset(self):
        from edu.models import Modalidade

        return super().get_queryset().filter(modalidade_id=Modalidade.FIC_MENOS).distinct()


class ProfessorQuery(models.QuerySet):
    def ativo(self):
        return self.all().distinct()

    def servidores_docentes(self):
        from rh.models import Servidor

        return self.servidores().filter(vinculo__id_relacionamento__in=Servidor.objects.filter(eh_docente=True).values_list('id', flat=True))

    def servidores_tecnicos(self):
        from rh.models import Servidor

        return self.servidores().filter(
            vinculo__id_relacionamento__in=Servidor.objects.filter(eh_tecnico_administrativo=True).values_list('id', flat=True)
        )

    def nao_servidores(self):
        return self.exclude(vinculo__tipo_relacionamento__app_label='rh', vinculo__tipo_relacionamento__model='servidor')

    def servidores(self):
        return self.filter(vinculo__tipo_relacionamento__app_label='rh', vinculo__tipo_relacionamento__model='servidor')


class ProfessorAtivoManager(FiltroDiretoriaManager):
    def __init__(self):
        super().__init__('professordiario__diario__turma__curso_campus__diretoria')

    def get_queryset(self):
        return super().get_queryset().distinct()


class ProfessorServidorDocenteManager(ProfessorAtivoManager):
    def get_queryset(self):
        from rh.models import Servidor

        return (
            super(self.__class__, self)
            .get_queryset()
            .filter(vinculo__pessoa__id__in=Servidor.objects.filter(eh_docente=True).values_list('pessoa_fisica__id', flat=True))
        )


class ProfessorServidorTecnicoManager(ProfessorAtivoManager):
    def get_queryset(self):
        from rh.models import Servidor

        return (
            super(self.__class__, self)
            .get_queryset()
            .filter(vinculo__pessoa__id__in=Servidor.objects.filter(eh_tecnico_administrativo=True).values_list('pessoa_fisica__id', flat=True))
        )


class ProfessorNaoServidorManager(ProfessorAtivoManager):
    def get_queryset(self):
        return (
            super(self.__class__, self)
            .get_queryset()
            .exclude(vinculo__tipo_relacionamento__app_label='rh', vinculo__tipo_relacionamento__model='servidor')
        )


class ProfessorServidorManager(ProfessorAtivoManager):
    def get_queryset(self):
        return (
            super(self.__class__, self)
            .get_queryset()
            .filter(vinculo__tipo_relacionamento__app_label='rh', vinculo__tipo_relacionamento__model='servidor')
        )


class AlunoManager(models.Manager):
    def autocomplete(self):
        qs = super().get_queryset()
        qs = qs.select_related('pessoa_fisica', 'pessoa_fisica__pessoa_ptr', 'curso_campus', 'curso_campus__diretoria__setor__uo')
        qs = qs.only(
            'foto',
            'matricula',
            'pessoa_fisica__pessoa_ptr__search_fields_optimized',
            'pessoa_fisica__nome',
            'pessoa_fisica__nome_registro',
            'pessoa_fisica__nome_social',
            'curso_campus__codigo',
            'curso_campus__descricao',
            'curso_campus__diretoria__setor__uo__nome',
        )
        return qs


class AlunosNaoFICManager(models.Manager):
    def get_queryset(self):
        from edu.models import Modalidade

        return (
            super().get_queryset().exclude(curso_campus__modalidade_id__in=[Modalidade.FIC, Modalidade.PROEJA_FIC_FUNDAMENTAL, Modalidade.FIC_MENOS])
        )


class AlunosAtivosManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(situacao__ativo=True)


class AlunosCaracterizadosManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(caracterizacao__isnull=False)


class AlunosComMatrizManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(matriz__isnull=False)


class AlunoLocalManager(models.Manager):
    def get_queryset(self):
        qs = super().get_queryset()
        user = tl.get_user()
        # Coordenadores de polo que não possuem outro perfil que permite visualização de aluno, só podem visualizar alunos do seu polo
        if user and user.groups.filter(name='Coordenador de Polo EAD').exists():
            if user.groups.filter(permissions__codename='view_aluno').count() == 1:
                from edu.models import CoordenadorPolo

                ids = CoordenadorPolo.objects.filter(vinculo=user.get_vinculo()).values_list('polo__id')
                return qs.filter(polo__id__in=ids)
        return qs


class EstagioDocenteManager(models.Manager):
    def get_queryset(self):
        user = tl.get_user()
        qs = (
            super()
            .get_queryset()
            .order_by(
                '-matricula_diario__diario__ano_letivo__ano',
                '-matricula_diario__diario__periodo_letivo',
                'matricula_diario__matricula_periodo__aluno__matricula',
            )
        )

        GRUPOS_ACESSO_TOTAL = {
            'Coordenador de Estágio Sistêmico',
            'estagios Administrador',
            'Administrador Acadêmico',
            'Auditor',
            'Estagiário Acadêmico Sistêmico',
        }
        user_groups = set(user.groups.values_list('name', flat=True))

        # interseção entre grupos do usuário e grupos com acesso total
        if user_groups & GRUPOS_ACESSO_TOTAL:
            return qs

        if 'Aluno' in user_groups:
            return qs.filter(matricula_diario__matricula_periodo__aluno__matricula=user.username)

        filtros = Q()
        vinculo = user.get_vinculo()

        if vinculo is None:
            return qs.none()

        vinculo_id = vinculo.id

        if 'Coordenador de Estágio Docente' in user_groups:
            filtros |= Q(matricula_diario__matricula_periodo__aluno__curso_campus__coordenadores_estagio_docente__vinculo_id=vinculo_id)

        if 'Coordenador de Curso' in user_groups:
            filtros |= Q(matricula_diario__matricula_periodo__aluno__curso_campus__coordenador_id=vinculo_id)
            filtros |= Q(matricula_diario__matricula_periodo__aluno__curso_campus__coordenador_2_id=vinculo_id)

        if 'Professor' in user_groups:
            filtros |= Q(professor_orientador__vinculo_id=vinculo_id)

        if not filtros:
            return qs.none()

        return qs.filter(filtros).distinct()
