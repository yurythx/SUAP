from datetime import date

from dateutil.relativedelta import relativedelta
from sentry_sdk import capture_exception

from djtools.management.commands import BaseCommandPlus
from estagios.models import PraticaProfissional


def notificar(meses):
    hoje = date.today()
    data_inicio = hoje - relativedelta(months=meses)
    data_fim = data_inicio + relativedelta(days=15)
    qs = PraticaProfissional.objects.filter(tipo=PraticaProfissional.TIPO_ESTAGIO, data_fim=None, data_inicio__range=(data_inicio, data_fim))
    for estagio in qs:
        try:
            data_limite_renovacao = estagio.data_inicio + relativedelta(months=meses)
            estagio.notificar_aluno_necessidade_atualizacao_pae(data_limite_renovacao)
            estagio.notificar_supervisor_aluno_necessidade_atualizacao_pae(data_limite_renovacao)
            estagio.notificar_orientador_necessidade_atualizacao_pae(data_limite_renovacao)
            estagio.notificar_coordenadores_extensao_necessidade_atualizacao_pae(data_limite_renovacao)
        except Exception as e:
            capture_exception(e)


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        # Notificando o pessoal sobre os Planos de Atividades de Estágio (PAEs) que estão para vencer.
        #
        # A notificação deve ser enviada a: Alunos, Supervisores e Orientadores envolvidos no Estágio,
        # bem como aos Coordenadores de Estágio do campus correspondente.
        #
        # Esse envio deve ocorrer a 15 dias do vencimento do PAE, que se vence em 6 meses, contados
        # a partir de sua data de início.

        # notificar a cada 6 meses por 4 anos  (suposto tempo máximo de um estágio)

        # notificação 6 meses
        notificar(meses=6)
        # notificação 12 meses
        notificar(meses=12)
        # notificação 18 meses
        notificar(meses=18)
        # notificação 24 meses
        notificar(meses=24)
        # notificação 30 meses
        notificar(meses=30)
        # notificação 36 meses
        notificar(meses=36)
        # notificação 42 meses
        notificar(meses=42)
