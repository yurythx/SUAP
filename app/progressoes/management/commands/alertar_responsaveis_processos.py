from comum.models import Configuracao
from djtools.management.commands import BaseCommandPlus
from progressoes.models import ProcessoProgressao


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        print('--- Alertando responsáveis ---')
        alertar = Configuracao.get_valor_por_chave('progressoes', 'alertar_responsaveis_servidores_a_progredir')
        if alertar:
            ProcessoProgressao.alertar_responsaveis_processos()
        else:
            print(
                'Os alertas estão desativados. Para ativá-los acesse as configurações do SUAP e procure pela opção "Alertar Responsáveis de Servidores a Progredir?".'
            )
        print('---- FIM ----')
