import tqdm
from django.apps import apps
from django.db import transaction

from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        SolicitacaoAdesaoServidor = apps.get_model('pgd', 'SolicitacaoAdesaoServidor')
        RelatorioIndividualTrabalho = apps.get_model('pgd', 'RelatorioIndividualTrabalho')

        adesoes = SolicitacaoAdesaoServidor.objects.all()

        for adesao in tqdm.tqdm(adesoes):
            rits = RelatorioIndividualTrabalho.objects.filter(pit__adesao=adesao)
            rits = rits.order_by('pit__data_inicial')
            for rit in rits:
                if rit.pit.situacao == rit.pit.AUTORIZADO and rit.foi_avaliado() and rit.get_tempo_homologado() > 0:
                    sid = transaction.savepoint()
                    try:
                        rit.distribuir_horas_automaticamente()
                        transaction.savepoint_commit(sid)
                    except Exception as e:
                        transaction.savepoint_rollback(sid)
                        self.stdout.write(f'>>> {rit.get_verbose_rit_servidor()} > ERRO: {e}')
