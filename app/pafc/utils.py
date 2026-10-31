from django.conf import settings

from comum.models import UsuarioGrupo


def eh_diretor_academico(usuario, diretoria=None):
    if usuario:
        qs_usuario_grupo = UsuarioGrupo.objects.filter(user=usuario, group__name='Diretor Acadêmico')
        if diretoria:
            qs_usuario_grupo = qs_usuario_grupo.filter(setores=diretoria.setor)
        return qs_usuario_grupo.exists()
    return False


def modulo_documento_eletronico_esta_ativo():
    return 'documento_eletronico' in settings.INSTALLED_APPS
