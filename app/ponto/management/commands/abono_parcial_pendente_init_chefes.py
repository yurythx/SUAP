import tqdm
from djtools.management.commands import BaseCommandPlus
from ponto.models import SolicitacaoAbonoParcial


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        solicit_save = []
        solicit_errors = []
        for solicit in tqdm.tqdm(SolicitacaoAbonoParcial.query_base().filter(situacao=SolicitacaoAbonoParcial.SITUACAO_PENDENTE)):
            try:
                solicit.inicializar_chefes_data_aplicacao()
                solicit_save.append(solicit)
            except Exception:
                solicit_errors.append(solicit)
        self.stdout.write(f'Solicitações: {len(solicit_save) + len(solicit_errors)}')
        self.stdout.write(f'Solicitações atualizadas: {len(solicit_save)}')
        self.stdout.write(f'Solicitações não atualizadas: {len(solicit_errors)}')
        for solicit_error in solicit_errors:
            self.stdout.write(f'{solicit_error}')
