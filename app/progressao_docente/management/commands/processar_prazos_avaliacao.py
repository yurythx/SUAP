import logging

from djtools.management.commands import BaseCommandPlus

from progressao_docente.models import Avaliacao

logger = logging.getLogger(__name__)


class Command(BaseCommandPlus):
    help = (
        'Tramita automaticamente as avaliações cujo prazo de etapa venceu: preenchimento (-> EM_AVALIACAO), '
        'edição para reavaliação (-> CONCLUIDA), reavaliação (-> AGUARDANDO_CIENCIA_RESULTADO) e '
        'ciência de resultado (-> CONCLUIDA).'
    )

    # Ordem do fluxo: a edição para reavaliação e a reavaliação vêm antes da ciência para que uma
    # avaliação que estoure a reavaliação hoje já possa ter a ciência avaliada na varredura seguinte.
    ETAPAS = (
        ('preenchimento', Avaliacao.AGUARDANDO_PREENCHIMENTO, 'expirar_preenchimento'),
        ('edição para reavaliação', Avaliacao.EDITACAO_PARA_REAVALIACAO, 'expirar_edicao_reavaliacao'),
        ('reavaliação', Avaliacao.REAVALIACAO, 'expirar_reavaliacao'),
        ('ciência', Avaliacao.AGUARDANDO_CIENCIA_RESULTADO, 'expirar_ciencia'),
    )

    def handle(self, *args, **options):
        totais = {rotulo: self._processar(situacao, metodo) for rotulo, situacao, metodo in self.ETAPAS}
        resumo = ', '.join(f'{rotulo}={total}' for rotulo, total in totais.items())
        logger.info('Tramitadas por expiração: %s', resumo)

    def _processar(self, situacao: int, metodo: str) -> int:
        total = 0
        # select_related('progressao'): os expirar_* acessam _load_configs (evita N+1)
        for avaliacao in Avaliacao.objects.filter(situacao=situacao).select_related('progressao'):
            if getattr(avaliacao, metodo)():
                total += 1
        return total
