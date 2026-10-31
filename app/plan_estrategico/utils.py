from django.core.exceptions import PermissionDenied
from django.db.models import Q

from comum.utils import get_setor, get_setores_que_sou_chefe_hoje

# verifica na hierarquia de setores qual o setor de nível mais baixo que possui unidade administrativa associada
from plan_estrategico.models import UnidadeGestora


def get_setor_unidade_gestora(user=None):
    try:
        caminho = get_setor(user).get_caminho()
        while len(caminho):
            setor_atual = caminho.pop()
            unidade = UnidadeGestora.objects.filter(setor_equivalente=setor_atual)
            if unidade:
                return unidade[0].setor_equivalente

        return None

    except Exception:
        return None


def get_setor_unidade_administrativa(user=None):
    try:
        caminho = get_setor(user).get_caminho()
        while len(caminho):
            setor_atual = caminho.pop()
            unidade = UnidadeGestora.objects.filter(setor_equivalente=setor_atual)
            if unidade:
                return unidade[0].setor_administrativo

        return None

    except Exception:
        return None


def iniciar_gerenciamento_acesso(request):
    msg_erro = 'Accesso permitido apenas para Gestores do Plano Estratégico.'

    setor_escolhido = get_setor_unidade_gestora(user=request.user)
    lista_setores_user_eh_chefe_hoje = get_setores_que_sou_chefe_hoje(request.user)

    if not setor_escolhido:
        raise PermissionDenied(msg_erro)

    if not lista_setores_user_eh_chefe_hoje and not request.user.has_group('Coordenador de UA'):
        raise PermissionDenied(msg_erro)

    su = True

    msg_orientacao_acesso = f'Você está acessando essa tela por ser Gestor ou ter poder de gestor para cadastrar atividades na unidade {setor_escolhido} ou um dos seus descendentes.'
    return su, setor_escolhido, setor_escolhido, msg_orientacao_acesso


GRUPOS_EMPENHOS_SEM_REQUISICAO_SISTEMICO = ['Administrador de Planejamento Estratégico', 'Gestor Orçamentário Sistêmico']
GRUPOS_EMPENHOS_SEM_REQUISICAO = [*GRUPOS_EMPENHOS_SEM_REQUISICAO_SISTEMICO, 'Gestor Orçamentário de UA', 'Executor Orçamentário']


def get_codigos_ug_empenhos_sem_requisicao(user, plano_atividade):
    """Códigos das UGs cujos empenhos sem requisição o usuário pode consultar."""
    unidades = UnidadeGestora.objects.filter(pdi=plano_atividade.pdi).exclude(codigo_ug='')
    if not user.has_group_cached(GRUPOS_EMPENHOS_SEM_REQUISICAO_SISTEMICO):
        setor = get_setor(user)
        if setor is None:
            return []
        filtro = Q(pk__in=[])
        if user.has_group_cached('Gestor Orçamentário de UA'):
            filtro |= Q(setor_administrativo__sigla=setor.sigla)
        if user.has_group_cached('Executor Orçamentário'):
            filtro |= Q(setor_financeiro__sigla=setor.sigla)
        unidades = unidades.filter(filtro)
    return list(unidades.order_by('codigo_ug').values_list('codigo_ug', flat=True).distinct())
