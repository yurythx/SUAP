from datetime import date

from django.db.models import Q

from ae.models import OfertaBolsa, ParticipacaoTrabalho
from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        hoje = date.today()

        for oferta in OfertaBolsa.objects.filter(disponivel=False):
            if (
                not ParticipacaoTrabalho.objects.filter(bolsa_concedida=oferta).exists()
                or ParticipacaoTrabalho.objects.filter(bolsa_concedida=oferta, participacao__data_termino__lt=hoje).exists()
            ):
                oferta.disponivel = True
                oferta.save()
            elif not oferta.ativa:
                oferta.ativa = True
                oferta.save()

        for oferta in OfertaBolsa.objects.filter(disponivel=True):
            if ParticipacaoTrabalho.objects.filter(
                Q(bolsa_concedida=oferta), Q(participacao__data_termino__gte=hoje) | Q(participacao__data_termino__isnull=True)
            ).exists():
                oferta.disponivel = False
                oferta.ativa = True
                oferta.save()
