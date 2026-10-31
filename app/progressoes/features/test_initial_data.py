from progressoes.models import AvaliacaoModelo, AvaliacaoModeloCriterio
from rh.models import PadraoVencimento


def initial_data(verbosity=0):
    padrao_vencimento_E1 = PadraoVencimento(categoria=PadraoVencimento.CATEGORIA_TECNICO_ADMINISTRATIVO, classe='E', posicao_vertical='01')
    padrao_vencimento_E1.save()
    padrao_vencimento_E2 = PadraoVencimento(categoria=PadraoVencimento.CATEGORIA_TECNICO_ADMINISTRATIVO, classe='E', posicao_vertical='02')
    padrao_vencimento_E2.save()

    criterio_1 = AvaliacaoModeloCriterio(descricao_questao='Criterio 1')
    criterio_1.save()
    criterio_2 = AvaliacaoModeloCriterio(descricao_questao='Criterio 2')
    criterio_2.save()

    avaliacao_modelo = AvaliacaoModelo(nome='Teste')
    avaliacao_modelo.save()
    avaliacao_modelo.itens_avaliados.add(criterio_1, criterio_2)
