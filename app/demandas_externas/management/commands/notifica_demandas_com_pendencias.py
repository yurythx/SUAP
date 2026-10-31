import datetime

from django.conf import settings

from comum.models import UsuarioGrupo
from demandas_externas.models import Demanda
from djtools.management.commands import BaseCommandPlus
from djtools.utils import send_notification


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        hoje = datetime.datetime.now().date()
        demandas = Demanda.objects.filter(situacao=Demanda.SUBMETIDA)
        for demanda in demandas:
            if (hoje - demanda.cadastrada_em.date()).days % 7 == 0:
                string = (hoje - demanda.cadastrada_em.date()).days
                lista_coordenadores = [
                    registro.user.get_vinculo()
                    for registro in UsuarioGrupo.objects.filter(
                        group__name__in=['Coordenador de Extensão', 'Coordenador de Demandas Externas']
                    ).filter(user__vinculo__setor__uo=demanda.campus_indicado)
                ]

                titulo = '[SUAP] Demanda da comunidade: Pendente de análise'
                texto = []
                texto.append('<h1>Demanda da comunidade</h1>')
                texto.append(f'<p>Uma demanda da comunidade foi aberta há {string} dias e ainda não foi analisada.')
                texto.append(
                    '<p class="more-info">Para mais informações, acesse: <a href="{0}">{0}</a></p>'.format(demanda.get_visualizar_demanda_url())
                )
                send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, lista_coordenadores)

        demandas = Demanda.objects.filter(situacao=Demanda.EM_ESPERA, responsavel=None)
        for demanda in demandas:
            if (hoje - demanda.avaliada_em.date()).days % 7 == 0:
                string = (hoje - demanda.avaliada_em.date()).days
                lista_coordenadores = [
                    registro.user.get_vinculo()
                    for registro in UsuarioGrupo.objects.filter(
                        group__name__in=['Coordenador de Extensão', 'Coordenador de Demandas Externas']
                    ).filter(user__vinculo__setor__uo=demanda.campus_indicado)
                ]

                titulo = '[SUAP] Demanda da comunidade: Aguardando indicação de responsável'
                texto = []
                texto.append('<h1>Demanda da comunidade</h1>')
                texto.append(f'<p>Uma demanda da comunidade foi aceita há {string} dias e ainda não possui responsável.')
                texto.append(
                    '<p class="more-info">Para mais informações, acesse: <a href="{0}">{0}</a></p>'.format(demanda.get_visualizar_demanda_url())
                )
                send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, lista_coordenadores)
