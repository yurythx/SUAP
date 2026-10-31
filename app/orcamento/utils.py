from comum.utils import get_setor
from financeiro.models import NotaCredito, NotaDotacao, NotaEmpenho, UnidadeGestora


# verifica na hierarquia de setores qual o setor de nível mais baixo que possui unidade gestora associada
def get_setor_unidade_gestora(user=None):
    try:
        caminho = get_setor(user).get_caminho()
        while len(caminho):
            setor_atual = caminho.pop()
            unidade = UnidadeGestora.objects.filter(setor=setor_atual)
            if unidade:
                return unidade[0].setor

        return None
    except Exception:
        return None


# verifica em quais anos existem notas importadas
def get_anos_importados(user_or_profile=None):
    anos = []
    try:
        anos = set(NotaCredito.objects.all().extra(select={'ano': 'extract(YEAR FROM datahora_emissao)'}).values_list('ano', flat=True).distinct())
        anos.update(NotaDotacao.objects.all().extra(select={'ano': 'extract(YEAR FROM datahora_emissao)'}).values_list('ano', flat=True).distinct())
        anos.update(NotaEmpenho.objects.all().extra(select={'ano': 'extract(YEAR FROM data_emissao)'}).values_list('ano', flat=True).distinct())
        anos = [int(x) for x in sorted(anos, reverse=True)]
    except Exception:
        pass

    return anos
