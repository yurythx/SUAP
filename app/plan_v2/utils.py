from comum.utils import get_setor
from plan_v2.models import UnidadeAdministrativa


# verifica na hierarquia de setores qual o setor de nível mais baixo que possui unidade administrativa associada
def get_setor_unidade_administrativa_equivalente(user=None):
    try:
        caminho = get_setor(user).get_caminho()
        while len(caminho):
            setor_atual = caminho.pop()
            unidade = UnidadeAdministrativa.objects.filter(setor_equivalente=setor_atual)
            if unidade:
                return unidade[0]

        return None

    except Exception:
        return None


def get_setor_unidade_administrativa_participante(user=None):
    try:
        setor_atual = get_setor(user).get_caminho().pop()
        unidade = UnidadeAdministrativa.objects.filter(setores_participantes=setor_atual)
        return unidade[0]

    except Exception:
        return None


def get_setor_unidade_administrativa(user=None):
    unidade_adm_usuario_equivalente = get_setor_unidade_administrativa_equivalente(user)
    unidade_adm_usuario_participante = get_setor_unidade_administrativa_participante(user)
    if unidade_adm_usuario_participante and not unidade_adm_usuario_equivalente:
        unidade_adm_usuario = [unidade_adm_usuario_participante]
    elif not unidade_adm_usuario_participante and unidade_adm_usuario_equivalente:
        unidade_adm_usuario = [unidade_adm_usuario_equivalente]
    else:
        unidade_adm_usuario = [unidade_adm_usuario_equivalente, unidade_adm_usuario_participante]
    return unidade_adm_usuario


def get_setores_participantes(unidade_adm_usuario):
    setores_usuario = [unidade.setor_equivalente for unidade in unidade_adm_usuario]
    return setores_usuario
