from datetime import timedelta

from django.apps import apps

from comum.models import Configuracao
from djtools.management.commands import BaseCommandPlus
from rh.models import Servidor

Log = apps.get_model('comum', 'log')


class Command(BaseCommandPlus):
    help = 'Organizar Data Fim do Historico de Função'

    def handle(self, *args, **options):
        # tem casos onde o instituto/órgão pode querer manter apenas uma função SIAPE ativa
        # nesses casos, o suap irá manter a função mais nova ativa e irá setar uma data fim para todas as outras funções em aberto
        # como é um caso muito particular, foi criada essa configuração para executar ou não essa funcionalidade
        deixa_apenas_uma_funcao_siape_ativa = Configuracao.get_valor_por_chave('rh', 'deixa_apenas_uma_funcao_siape_ativa')
        if not deixa_apenas_uma_funcao_siape_ativa:
            return
        #
        # comando que tem por objetivo identificar quando o servidor tem mais de uma função ativa
        # - em caso positivo, o script irá identificar a função mais nova e inativar todas as funções mais antigas, setando a data fim corretamente
        lista_servidores_afetados = []
        for servidor in Servidor.objects.ativos().all():
            # verificando se o servidor tem função com data fim nula
            check_historico = servidor.servidorfuncaohistorico_set.filter(
                data_fim_funcao__isnull=True, funcao__funcao_siape=True
            )  # apenas funções criadas via SIAPE
            # se existir mais de um historico de setor com data fim nula, é necessário a correção
            if check_historico.count() > 1:
                s = f'{servidor.pessoa_fisica.nome} ({servidor.matricula})'
                lista_servidores_afetados.append(s)
                data_anterior = None
                for i in check_historico.order_by('-data_inicio_funcao'):
                    if data_anterior is not None:
                        i.data_fim_funcao = data_anterior
                        i.save()
                    data_anterior = i.data_inicio_funcao - timedelta(days=1)

        if lista_servidores_afetados:
            Log.objects.create(
                titulo='Ajustes no histórico de funções',
                texto='Os seguintes servidores tiveram seus históricos de função ajustados com relação a data fim:'
                + ', '.join(lista_servidores_afetados),
                app='rh',
            )
