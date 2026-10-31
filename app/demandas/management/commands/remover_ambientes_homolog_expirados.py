from __future__ import annotations

from datetime import date, timedelta

from django.db.models import Q, QuerySet

from demandas.models import AmbienteHomologacao, Situacao
from demandas.utils import Notificar
from djtools.management.commands import BaseCommandPlus

# ponytail: janela fixa para reprocessar inativos, que limita as chamadas ao GitLab por execução;
# ambiente que falhar por mais tempo que isso sai da fila e precisa de limpeza manual.
DIAS_REPROCESSAR_INATIVOS = 30
SITUACOES_ENCERRADAS = [Situacao.ESTADO_CANCELADO, Situacao.ESTADO_SUSPENSO, Situacao.ESTADO_CONCLUIDO]


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        """
        Notifica os desenvolvedores de ambiente que com data de expiração para próximo dia
        Remove os ambientes de homologação com data de expiração inferior a data atual
        """
        hoje = date.today()
        self.notificar_expiracao_proxima(hoje)

        # Exclui ambientes expirados ou de entregas de demandas concluídas, canceladas ou suspensas
        a_remover = AmbienteHomologacao.objects.filter(ativo=True).filter(self.criterio_remocao(hoje)).distinct()
        self.stdout.write(f'{a_remover.count()} serão excluídos!')
        self.destruir(a_remover)

        # Inativos cujo banco pode ter ficado para trás: "Remover Provisoriamente" seguido de
        # expiração, ou um destroy anterior que o GitLab não chegou a executar.
        inativos = AmbienteHomologacao.objects.filter(ativo=False, data_expiracao__gte=hoje - timedelta(days=DIAS_REPROCESSAR_INATIVOS))
        pendentes = [ambiente for ambiente in inativos.filter(self.criterio_remocao(hoje)).distinct() if self.destroy_pendente(ambiente)]
        self.stdout.write(f'{len(pendentes)} inativos com destroy pendente serão excluídos!')
        self.destruir(pendentes)

    @staticmethod
    def criterio_remocao(hoje: date) -> Q:
        return Q(data_expiracao__lt=hoje) | Q(entregas__demanda__situacao__in=SITUACOES_ENCERRADAS)

    def notificar_expiracao_proxima(self, hoje: date) -> None:
        ambientes = AmbienteHomologacao.objects.filter(ativo=True, data_expiracao=hoje + timedelta(days=1))
        self.stdout.write(f'{ambientes.count()} a expirar em dois dias!')
        for ambiente in ambientes:
            try:
                Notificar.ambiente_homologacao_expira_em_1_dia(ambiente)
            except Exception as e:
                self.stderr.write(f'Falha ao notificar {ambiente}: {e}')

    def destroy_pendente(self, ambiente: AmbienteHomologacao) -> bool:
        try:
            return ambiente.destroy_pendente()
        except Exception as e:
            self.stderr.write(f'Falha ao consultar o destroy de {ambiente}: {e}')
            return False

    def destruir(self, ambientes: QuerySet[AmbienteHomologacao] | list[AmbienteHomologacao]) -> None:
        for ambiente in ambientes:
            try:
                ambiente.destruir()
            except Exception as e:
                # Sem `continue` silencioso: o motivo (job não executável, recusa do GitLab) fica no log da task.
                self.stderr.write(f'Falha ao remover {ambiente}: {e}')
