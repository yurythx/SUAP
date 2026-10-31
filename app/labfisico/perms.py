from comum.models import UsuarioGrupo, UsuarioGrupoSetor
from djtools.templatetags.filters import in_group


def is_group_admin(user):
    grupos_sistemicos = ['Coordenador de TI sistêmico', 'Gerente de Laboratório Físico']
    autorizado = UsuarioGrupo.objects.filter(user=user, group__name__in=grupos_sistemicos)
    return user.is_superuser or autorizado.exists()


def pode_gerenciar_solicitacao_labfisico(user, laboratorio=None):
    autorizado = is_group_admin(user) or in_group(user, 'edu Administrador')
    if not autorizado:
        grupos_sistemicos = [
            'Administrador Acadêmico',
            'Diretor Acadêmico Sistêmico',
            'Coordenador Acadêmico Sistêmico',
            'Avaliador de Laboratório Físico sistêmico',
        ]
        autorizado = UsuarioGrupo.objects.filter(user=user, group__name__in=grupos_sistemicos).exists()
        if not autorizado and laboratorio:
            eh_do_campus = laboratorio.campus == user.get_vinculo().setor.uo
            grupos_campus = ['Secretário Acadêmico', 'Diretor Acadêmico', 'Coordenador de Curso', 'Avaliador de Laboratório Físico de campus']
            autorizado = (
                eh_do_campus and UsuarioGrupoSetor.objects.filter(usuario_grupo__user=user, usuario_grupo__group__name__in=grupos_campus).exists()
            )
        #
    return autorizado


def pode_gerenciar_laboratorio_guacamole(user, laboratorio=None):
    autorizado = is_group_admin(user)
    if not autorizado and laboratorio:
        eh_do_campus = laboratorio.campus == user.get_vinculo().setor.uo
        autorizado = eh_do_campus and UsuarioGrupo.objects.filter(user=user, group__name='Coordenador de TI de campus').exists()
    #
    return autorizado
