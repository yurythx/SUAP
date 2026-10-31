from django.contrib.auth.models import Group

from comum.models import UsuarioGrupo, UsuarioGrupoSetor
from djtools.templatetags.filters import in_group
from edu.models.cadastros_gerais import NivelEnsino


CACHED_GROUP_PKS = None

grupos_sistemicos = [
    'Administrador Acadêmico',
    'Coordenador de Atividades Estudantis Sistêmico',
    'Coordenador de Egressos Sistêmico',
    'Coordenador de Estágio Sistêmico',
    'Coordenador de Saúde Sistêmico',
    'Diretor Acadêmico Sistêmico',
    'Diretor de Avaliação e Regulação do Ensino',
    'edu Administrador',
    'Gerente Sistêmico de Extensão',
    'Pró-Reitor',
    'Reitor',
    'Operador de Censo',
    'Visualizador de Informações Acadêmicas',
]

grupos_campus = [
    'Assistente Social',
    'Auxiliar de Enfermagem',
    'Coordenador de Atividades Estudantis',
    'Coordenador de Egressos',
    'Coordenador de Estágio',
    'Coordenador de Extensão',
    'Coordenador de Saúde',
    'Diretor Geral',
    'Membro ETEP',
]

grupos_diretoria = [
    'Apoio Acadêmico',
    'Auxiliar de Secretaria Acadêmica',
    'Coordenador de Modalidade Acadêmica',
    'Diretor Acadêmico',
    'Diretor de Ensino',
    'Estagiário',
    'Secretário Acadêmico',
]

grupos_curso = [
    'Coordenador de Curso',
]


def realizar_procedimentos_academicos(user, curso_campus=None):
    if user.is_anonymous:
        return False

    if UsuarioGrupo.objects.filter(user=user, group__name__in=['Administrador Acadêmico', 'Diretor Acadêmico Sistêmico']).exists():
        return True

    if curso_campus is None:
        return False

    if UsuarioGrupoSetor.objects.filter(
        usuario_grupo__user_id=user.id,
        usuario_grupo__group__name__in=['Secretário Acadêmico', 'Diretor Acadêmico', 'Diretor de Ensino'],
        setor_id=curso_campus.diretoria.setor_id,
    ).exists():
        return True

    vinculo = user.get_vinculo()
    if not vinculo:
        return False

    if vinculo.pk in (curso_campus.coordenador_id, curso_campus.coordenador_2_id):
        return True

    if user.eh_servidor and vinculo.setor:
        # é coordenador de modalidade de ensino
        return vinculo.relacionamento.coordenadormodalidade_set.filter(
            modalidades=curso_campus.modalidade, diretoria__setor__uo_id=vinculo.setor.uo_id
        ).exists()

    return False


def realizar_procedimentos_diarios_especiais(user, diario_especial=None):
    autorizado = user.is_superuser
    if not autorizado:
        autorizado = (
            UsuarioGrupoSetor.objects.all()
            .filter(
                usuario_grupo__user=user,
                usuario_grupo__group__name__in=['Secretário Acadêmico', 'Diretor Acadêmico', 'Coordenador de Curso', 'Coordenador de Desporto'],
                setor=diario_especial.diretoria.setor,
            )
            .exists()
        )
        if not autorizado:
            autorizado = UsuarioGrupo.objects.filter(
                user=user, group__name__in=['Administrador Acadêmico', 'Diretor Acadêmico Sistêmico', 'Coordenador Acadêmico Sistêmico']
            ).exists()
    return autorizado


def is_admin(user):
    return user.is_superuser or in_group(user, 'edu Administrador')


def is_responsavel(request, aluno):
    return request.user.is_anonymous and request.session.get('matricula_aluno_como_resposavel') == aluno.matricula


def is_proprio_aluno(request, aluno):
    return request.user.is_authenticated and aluno.is_user(request)


def is_orientador(request, aluno):
    if request.user.is_authenticated:
        is_orientador_projetofinal = aluno.matriculaperiodo_set.filter(projetofinal__orientador__vinculo__user=request.user).exists()
        is_orientador_aluno = not is_responsavel and aluno.orientador.vinculo == request.user.get_vinculo()
        return is_orientador_projetofinal or is_orientador_aluno
    return False


def is_coorientador(request, aluno):
    if request.user.is_authenticated:
        is_coorientador_projetofinal = aluno.matriculaperiodo_set.filter(projetofinal__coorientadores_vinculos__user=request.user).exists()
        is_coorientador_aluno = aluno.coorientadores.filter(id=request.user.get_vinculo().id).exists()
        return is_coorientador_projetofinal or is_coorientador_aluno
    return False


def is_examinador(request, aluno):
    return request.user.is_authenticated and (
        aluno.matriculaperiodo_set.filter(projetofinal__examinador_interno__user=request.user).exists()
        | aluno.matriculaperiodo_set.filter(projetofinal__examinador_externo__user=request.user).exists()
        | aluno.matriculaperiodo_set.filter(projetofinal__terceiro_examinador__user=request.user).exists()
    )


def is_presidente(request, aluno):
    return request.user.is_authenticated and aluno.matriculaperiodo_set.filter(projetofinal__presidente__vinculo__user=request.user).exists()


def pode_ver_dados_anonimos_aluno(user, aluno=None):
    global CACHED_GROUP_PKS

    grupos_todos = grupos_sistemicos + grupos_campus + grupos_diretoria + grupos_curso

    if CACHED_GROUP_PKS is None:
        CACHED_GROUP_PKS = {}
        CACHED_GROUP_PKS['grupos_sistemicos'] = list(Group.objects.filter(name__in=grupos_sistemicos).values_list('pk', flat=True))
        CACHED_GROUP_PKS['grupos_campus'] = list(Group.objects.filter(name__in=grupos_campus).values_list('pk', flat=True))
        CACHED_GROUP_PKS['grupos_diretoria'] = list(Group.objects.filter(name__in=grupos_diretoria).values_list('pk', flat=True))
        CACHED_GROUP_PKS['grupos_curso'] = list(Group.objects.filter(name__in=grupos_curso).values_list('pk', flat=True))

    autorizado = False
    if not user.is_anonymous:
        autorizado = user.is_superuser
        if not autorizado:
            # sistêmico
            autorizado = UsuarioGrupo.objects.filter(user=user, group__in=CACHED_GROUP_PKS['grupos_sistemicos']).exists()
            if not autorizado:
                if aluno is None:
                    autorizado = in_group(user, grupos_todos)
                else:
                    curso_campus = aluno.curso_campus
                    if curso_campus is not None:
                        # campus
                        autorizado = UsuarioGrupoSetor.objects.filter(
                            usuario_grupo__user=user,
                            usuario_grupo__group__in=CACHED_GROUP_PKS['grupos_campus'],
                            setor__uo=curso_campus.diretoria.setor.uo,
                        ).exists()
                        if not autorizado:
                            autorizado = (
                                UsuarioGrupo.objects.filter(user=user, group__in=CACHED_GROUP_PKS['grupos_campus']).exists()
                                and user.get_vinculo().setor.uo == curso_campus.diretoria.setor.uo
                            )
                            if not autorizado:
                                # diretoria
                                autorizado = UsuarioGrupoSetor.objects.filter(
                                    usuario_grupo__user=user,
                                    usuario_grupo__group__in=CACHED_GROUP_PKS['grupos_diretoria'],
                                    setor=curso_campus.diretoria.setor,
                                ).exists()
                                if not autorizado and UsuarioGrupo.objects.filter(user=user, group__in=CACHED_GROUP_PKS['grupos_curso']).exists():
                                    # curso
                                    vinculo = user.get_vinculo()
                                    autorizado = (
                                        (vinculo and curso_campus.coordenador and vinculo.pk == curso_campus.coordenador.pk)
                                        or (vinculo and curso_campus.coordenador_2 and vinculo.pk == curso_campus.coordenador_2.pk)
                                        or False
                                    )
    return autorizado


def pode_ver_dados_sociais(request, aluno):
    return (
        is_admin(request.user)
        or is_proprio_aluno(request, aluno)
        or in_group(request.user, 'Assistente Social, Coordenador de Atividades Estudantis Sistêmico')
    )


def pode_ver_dados_academicos(request, aluno):
    """
    podem ver dados acadêmicos:
     - Admistrador do edu
     - Responsável pelo aluno
     - Próprio aluno
     - usuário sistêmico com permissão view_dados_academicos
     - usuário com permissão view_dados_academicos do mesmo campus do aluno
    """
    user = request.user
    pode_ver = is_admin(user) or is_responsavel(request, aluno) or is_proprio_aluno(request, aluno)
    if not pode_ver and user.has_perm('edu.view_dados_academicos'):
        setor = request.user.get_vinculo().setor
        pode_ver = setor and setor.uo == aluno.curso_campus.diretoria.setor.uo
        if not pode_ver:
            grupos = list(
                Group.objects.filter(permissions__content_type__app_label='edu', permissions__codename='view_dados_academicos').values_list(
                    'name', flat=True
                )
            )
            pode_ver = UsuarioGrupoSetor.objects.filter(
                usuario_grupo__user=user, usuario_grupo__group__name__in=grupos, setor__uo_id=aluno.curso_campus.diretoria.setor.uo.id
            ).exists()
            if not pode_ver:
                grupos_sistemicos = [s for s in grupos if 'Sistêmico' in s.split()]
                grupos_sistemicos.append('Administrador Acadêmico')
                pode_ver = UsuarioGrupo.objects.filter(user=user, group__name__in=grupos_sistemicos).exists()
    return pode_ver


def tem_permissao_realizar_procedimentos(user, aluno):
    return is_admin(user) or realizar_procedimentos_academicos(user, aluno.curso_campus)


def pode_realizar_procedimentos_enade(user, curso_campus):
    if user is None or user.is_anonymous:
        return False
    if UsuarioGrupo.objects.filter(
        user=user, group__name__in=['Administrador Acadêmico', 'Diretor de Avaliação e Regulação do Ensino', 'Operador ENADE']
    ).exists():
        return True
    vinculo = user.get_vinculo()
    return vinculo and vinculo.id in [curso_campus.coordenador_id, curso_campus.coordenador_2_id]


def pode_realizar_procedimentos(user, aluno):
    return is_admin(user) or tem_permissao_realizar_procedimentos(user, aluno) and not aluno.is_concluido()


def pode_ver_endereco_professores(user):
    return in_group(user, 'Administrador Acadêmico')


def pode_alterar_email(request, aluno):
    if request.user.is_anonymous:
        return False
    if aluno:
        if UsuarioGrupo.objects.filter(user=request.user, group__name='Coordenador de TI sistêmico').exists():
            return True
        if UsuarioGrupo.objects.filter(
            user=request.user, group__name='Coordenador de Registros Acadêmicos', setores__uo=aluno.curso_campus.diretoria.setor.uo_id
        ).exists():
            return True
        if tem_permissao_realizar_procedimentos(request.user, aluno):
            return True
        if uo_user := request.user.get_vinculo().setor:
            return (
                UsuarioGrupo.objects.filter(user=request.user, group__name='Coordenador de TI de campus').exists()
                if aluno.curso_campus.diretoria.setor.uo_id == uo_user.uo_id
                else False
            )
    return False


def pode_editar_orientadores_pos(request, aluno):
    if request.user.is_anonymous:
        return False
    is_nivel_pos_graduacao = aluno.curso_campus.modalidade and aluno.curso_campus.modalidade.nivel_ensino.pk == NivelEnsino.POS_GRADUACAO
    is_vinculado_a_programa_pos = aluno.curso_campus.cursoprogramapos_set.filter(curso__pk=aluno.curso_campus.pk).exists()
    return bool(request.user.has_perm('edu.pode_editar_orientador_pos') and is_nivel_pos_graduacao and is_vinculado_a_programa_pos)
