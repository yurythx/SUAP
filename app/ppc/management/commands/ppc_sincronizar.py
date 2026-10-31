from django.core.exceptions import ValidationError

from djtools.management.commands import BaseCommandPlus
from ppc.models import ProjetoPedagogicoCurso, SolicitacaoPPC


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        for solicitacao in SolicitacaoPPC.objects.filter(situacao__in=[SolicitacaoPPC.EMISSAO_ATA, SolicitacaoPPC.EMISSAO_PORTARIA]):
            try:
                solicitacao.atualizar_situacao()
            except ValidationError:
                pass

        for projeto in ProjetoPedagogicoCurso.objects.filter(situacao__in=[ProjetoPedagogicoCurso.EM_ELABORACAO, ProjetoPedagogicoCurso.EM_REVISAO]):
            try:
                projeto.atualizar_situacao()
            except ValidationError:
                pass
