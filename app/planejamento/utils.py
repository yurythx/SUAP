from comum.utils import get_setor
from planejamento.models import UnidadeAdministrativa

# verifica na hierarquia de setores qual o setor de nível mais baixo que possui unidade administrativa associada


def get_setor_unidade_administrativa(user=None):
    try:
        caminho = get_setor(user).get_caminho()
        while len(caminho):
            setor_atual = caminho.pop()
            unidade = UnidadeAdministrativa.objects.filter(setor_equivalente=setor_atual)
            if unidade:
                return unidade[0].setor_equivalente

        return None

    except Exception:
        return None
