from djtools.management.commands import BaseCommandPlus
from edu.models import Requerimento, RequerimentoAproveitamentoEstudo
from datetime import date
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommandPlus):
    def add_arguments(self, parser):
        parser.add_argument('--debug', action='store_true', default=False, help='Simula o arquivamento sem salvar os objetos (apenas log)')

    def handle(self, *args, **options):
        debug = options.get('debug', False)
        hoje = date.today()
        qs = RequerimentoAproveitamentoEstudo.objects.filter(situacao__isnull=True, data__lt=hoje)
        for requerimento in qs:
            if not requerimento.pode_finalizar_cadastro()[0]:
                if requerimento.solicitacaoaproveitamentoestudo_set.exists():
                    if debug:
                        logger.info(f"Finalizando requerimento '{requerimento}' devido fim do prazo para envio...")
                    else:
                        requerimento.situacao = Requerimento.SITUACAO_EM_ANDAMENTO
                        requerimento.observacao = 'Enviado automaticamente pelo sistema devido fim do prazo para envio.'
                        requerimento.save()
                else:
                    if debug:
                        logger.info(f"Arquivando requerimento '{requerimento}' por perda de prazo para envio...")
                    else:
                        requerimento.situacao = Requerimento.SITUACAO_ARQUIVADO
                        requerimento.observacao = 'Arquivado automaticamente por não ter sido enviado dentro do prazo.'
                        requerimento.save()
