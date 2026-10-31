from django.core.management.base import BaseCommand
from django.db import models, transaction

from plan_estrategico.models import RequisicaoRealocacao, RequisicaoRealocacaoHistorico


JUSTIFICATIVA = 'Atividade cancelada por inconsistência.'


class Command(BaseCommand):
    help = 'Cancela as requisições de realocação em que a atividade concedente e a atividade recebedora são iguais, adicionando justificativa.'

    def handle(self, *args, **options):
        self.stdout.write('Buscando requisições com atividades concedente/recebedora iguais...\n')

        qs = RequisicaoRealocacao.objects.filter(atividade_concedente_id=models.F('atividade_recebedora_id')).exclude(
            status=RequisicaoRealocacao.STATUS_CANCELADA
        )

        total = qs.count()

        if total == 0:
            self.stdout.write(self.style.SUCCESS('Nenhuma requisição com atividades iguais encontrada.'))
            return

        self.stdout.write(self.style.WARNING(f'Encontradas {total} requisições com atividades duplicadas.\n'))

        for req in qs:
            self.stdout.write(f'- ID: {req.id} | UA: {req.unidade_concedente} | Atividade: {req.atividade_concedente} | Status atual: {req.status}')

        self.stdout.write(self.style.WARNING('\nIniciando cancelamento das requisições...'))

        alteradas = 0

        for req in qs:
            with transaction.atomic():
                update_fields = ['status']
                req.status = RequisicaoRealocacao.STATUS_CANCELADA

                if hasattr(req, 'motivo_cancelamento'):
                    req.motivo_cancelamento = JUSTIFICATIVA
                    update_fields.append('motivo_cancelamento')

                req.save(update_fields=update_fields)

                RequisicaoRealocacaoHistorico.objects.create(
                    requisicao=req,
                    status=req.status,
                )
                alteradas += 1

        self.stdout.write(self.style.SUCCESS(f'\nProcesso concluído! {alteradas} requisições foram marcadas como canceladas com justificativa.'))
