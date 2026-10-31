from comum.models import UsuarioGrupoSetor
from comum.utils import get_sigla_reitoria
from djtools.templatetags.filters import in_group
from edu.perms import tem_permissao_realizar_procedimentos
from rh.models import UnidadeOrganizacional


def tem_permissao_realizar_procedimentos_etep(request, setor):
    if request.user.is_superuser:
        return True
    if request.user.is_anonymous:
        return False
    qs_reitoria = UnidadeOrganizacional.objects.suap().filter(sigla=get_sigla_reitoria())
    setor_reitoria = qs_reitoria.exists() and qs_reitoria[0].setor or None
    autorizado = (
        UsuarioGrupoSetor.objects.filter(
            usuario_grupo__user=request.user,
            usuario_grupo__group__name='Membro ETEP',
            setor__uo__in=[setor.uo, setor_reitoria and setor_reitoria.uo or None],
        ).exists()
        or in_group(request.user, 'etep Administrador')
        or in_group(request.user, 'Administrador Acadêmico')
    )
    return autorizado


def pode_ver_etep(request, acompanhamento):
    if request.user.is_superuser:
        return True
    if request.user.is_anonymous:
        return False
    setor = acompanhamento.aluno.curso_campus.diretoria.setor
    return (
        tem_permissao_realizar_procedimentos_etep(request, setor)
        or request.user.get_vinculo().id in acompanhamento.interessado_set.values_list('vinculo', flat=True)
        or tem_permissao_realizar_procedimentos(request.user, acompanhamento.aluno)
    )


def pode_editar_registro(request, registro):
    if request.user.is_superuser:
        return True
    if request.user.is_anonymous:
        return False
    return pode_ver_etep(request, registro.acompanhamento) and registro.usuario == request.user


def tem_permissao_ver_documentos_etep(request):
    if request.user.is_superuser:
        return True
    try:
        return request.user.has_perm('etep.view_documento')
    except Exception:
        return False


def tem_permissao_alterar_documentos_etep(request, atividade):
    if request.user.is_superuser:
        return True
    try:
        return (
            tem_permissao_ver_documentos_etep(request)
            and atividade.usuario.get_relacionamento().setor.uo == request.user.get_relacionamento().setor.uo
        )
    except Exception:
        return False
