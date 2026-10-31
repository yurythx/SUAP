import datetime

from django.conf import settings

from djtools.management.commands import BaseCommandPlus
from djtools.utils import send_notification
from pesquisa.models import ParecerObra


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        agora = datetime.datetime.now()
        pareceres = ParecerObra.objects.filter(
            obra__edital__data_inicio_analise_especialista__lte=agora,
            obra__edital__data_termino_analise_especialista__gte=agora,
            parecer_realizado_em__isnull=True,
            recusou_indicacao=False,
            aceitou_indicacao=True,
        )
        if pareceres.exists():
            hoje = datetime.datetime.now().date()
            for parecer in pareceres:
                string = None
                if (hoje - parecer.analise_indicacao_em.date()).days % 10 == 0:
                    string = (hoje - parecer.analise_indicacao_em.date()).days
                if string:
                    obra = parecer.obra
                    titulo = '[SUAP] Pesquisa: Indicação de Parecerista de Obra'
                    texto = (
                        '<h1>Pesquisa</h1>'
                        '<h2>Parecerista de Obra</h2>'
                        f"<p>Faz {string} dias que você aceitou a indicação como parecerista da Obra '{obra.titulo}', mas não realizou a avaliação.</p>"
                        f'<p class="more-info">Para mais informações, acesse: <a href="{settings.SITE_URL}/pesquisa/obra/{obra.id}/">{settings.SITE_URL}/pesquisa/obra/{obra.id}/</a></p>'
                    )
                    send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, [parecer.parecer_realizado_por_vinculo])
