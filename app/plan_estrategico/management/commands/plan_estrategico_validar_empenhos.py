import tqdm

from djtools.management.commands import BaseCommandPlus
from plan_estrategico.models import RequisicaoDespesa


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        requisicoes = RequisicaoDespesa.objects.filter(status=RequisicaoDespesa.STATUS_AGUARDANDO_VALIDACAO)

        for requisicao in tqdm.tqdm(requisicoes):
            requisicao.validar_requisicao()
