from django.core.mail import mail_admins
from tqdm import tqdm

from cnpq.models import CurriculoVittaeLattes
from cnpq.views import atualizar_grupos_pesquisa
from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        mensagem = '\n\t ERROS '
        count_exceptions = total = sem_grupo = inserido = sem_novo_grupo = em_manutencao = 0
        STATUS_NAO_HA_GRUPO = 0
        STATUS_NOVO_GRUPO_INSERIDO = 1
        STATUS_NENHUM_NOVO_GRUPO_INSERIDO = 2
        STATUS_CNPQ_EM_MANUTENCAO = 3
        queryset = CurriculoVittaeLattes.objects.filter(data_importacao_grupos_pesquisa__isnull=True)[:50]
        for registro in tqdm(queryset):
            try:
                retorno = atualizar_grupos_pesquisa(registro)
                total += 1
                if retorno == STATUS_NAO_HA_GRUPO:
                    sem_grupo += 1
                elif retorno == STATUS_NOVO_GRUPO_INSERIDO:
                    inserido += 1
                elif retorno == STATUS_NENHUM_NOVO_GRUPO_INSERIDO:
                    sem_novo_grupo += 1
                elif retorno == STATUS_CNPQ_EM_MANUTENCAO:
                    em_manutencao += 1
            except Exception as e:
                if registro.vinculo:
                    mensagem += f'\n{registro.vinculo.relacionamento} => {e}'
                count_exceptions += 1

        mensagem += f'\n{count_exceptions} \t Exceções '
        mensagem += f'\n{total} \t TOTAL '
        mensagem += f'\n{sem_grupo} \t Sem grupos '
        mensagem += f'\n{inserido} \t Novos '
        mensagem += f'\n{sem_novo_grupo} \t Sem novos grupos '
        mensagem += f'\n{em_manutencao} \t CNPQ em manutenção '
        if count_exceptions:
            mail_admins('[SUAP] Importação dos Grupos de Pesquisa', mensagem)
        return mensagem
