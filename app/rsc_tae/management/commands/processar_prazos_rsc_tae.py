from django.core.management.base import BaseCommand

from rsc_tae.enums import SituacaoProcesso
from rsc_tae.models import ProcessoRSCTae
from rsc_tae.views._helpers import _verificar_prazos_expirados


class Command(BaseCommand):
    help = 'Substitui avaliadores auxiliares com prazo de 10 dias úteis expirado (Art. 18, §3º).'

    def handle(self, *args, **kwargs):
        processos = ProcessoRSCTae.objects.filter(situacao=SituacaoProcesso.EM_ANALISE)
        total = processos.count()
        substituicoes = 0

        self.stdout.write(f'Verificando {total} processo(s) em análise...')

        for processo in processos:
            try:
                avaliadores_antes = set(processo.avaliadores.values_list('id', flat=True))
                _verificar_prazos_expirados(processo)
                processo.refresh_from_db()
                avaliadores_depois = set(processo.avaliadores.values_list('id', flat=True))
                trocas = len(avaliadores_antes - avaliadores_depois)
                if trocas:
                    substituicoes += trocas
                    self.stdout.write(f'  Processo #{processo.pk}: {trocas} substituição(ões) por prazo expirado.')
            except Exception as e:
                self.stderr.write(f'  Erro no processo #{processo.pk}: {e}')

        self.stdout.write(self.style.SUCCESS(f'Concluído. {substituicoes} substituição(ões) realizadas.'))
