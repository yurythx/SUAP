from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F

from plan_estrategico.models import AtividadeEtapa, RequisicaoRealocacao


class Command(BaseCommand):
    help = 'Recalcula o campo valor_realocado de todas as AtividadeEtapa com base nas realocações deferidas.'

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write('Zerando valor_realocado das atividades...\n')
        AtividadeEtapa.objects.update(valor_realocado=0)

        self.stdout.write('Buscando requisições de realocação deferidas...\n')
        qs = RequisicaoRealocacao.objects.filter(status=RequisicaoRealocacao.STATUS_DEFERIDA)

        total = qs.count()
        self.stdout.write(f'{total} requisições encontradas.\n')

        # Aplica realocações
        for req in qs.select_related('atividade_concedente', 'atividade_recebedora'):
            if not req.atividade_concedente or not req.atividade_recebedora:
                continue

            valor = req.valor_final or 0

            AtividadeEtapa.objects.filter(id=req.atividade_concedente_id).update(valor_realocado=F('valor_realocado') - valor)

            AtividadeEtapa.objects.filter(id=req.atividade_recebedora_id).update(valor_realocado=F('valor_realocado') + valor)

        self.stdout.write(self.style.SUCCESS('Recalculo concluído com sucesso!'))
