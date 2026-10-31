import tqdm
from dateutil.relativedelta import relativedelta
from django.apps import apps

from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        # ----------------------------------------------
        # Ajusta o SolicitacaoAdesaoServidor.data_desligamento_carencia_ate para o novo valor do PlanoIndividualTrabalho.CARENCIA_PARA_EDICAO_PIT_SEM_ADESA_VIGENTE
        # ----------------------------------------------
        """
        - Pega todos os desligamentos
        - Calcula nova data de carencia pra cada um deles
        - Ajusta a data de carencia em SolicitacaoAdesaoServidor
        """

        SolicitacaoAdesaoServidor = apps.get_model('pgd', 'SolicitacaoAdesaoServidor')

        adesoes = SolicitacaoAdesaoServidor.objects.filter(situacao=SolicitacaoAdesaoServidor.DEFERIDO)

        for adesao in tqdm.tqdm(adesoes):
            if adesao.tem_desligamento_cadastrado:
                data_desligamento_efeitos_a_partir_de = adesao.data_desligamento_efeitos_a_partir_de
                adesao.data_desligamento_carencia_ate = data_desligamento_efeitos_a_partir_de + relativedelta(days=820)
                adesao.save()
