from django.conf import settings

from comum.models import Vinculo, UsuarioGrupo
from djtools.management.commands import BaseCommandPlus
from djtools.utils import send_notification
from frota.models import Viatura
from rh.models import UnidadeOrganizacional


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        for campus in UnidadeOrganizacional.objects.all():
            por_km = []
            por_tempo = []
            vinculos = list(
                Vinculo.objects.filter(
                    setor__uo=campus,
                    user__in=UsuarioGrupo.objects.filter(group__name='Operador de Frota').only('user').values_list('user_id', flat=True),
                )
            )
            for viatura in Viatura.objects.filter(ativo=True, campus=campus):
                if viatura.tem_odometro_perto_km_revisao():
                    por_km.append(viatura)

                if viatura.tem_revisao_prevista():
                    por_tempo.append(viatura)

            if por_km:
                lista_viaturas = '<br>'.join([viatura.__str__() for viatura in por_km])
                titulo = '[SUAP] Frota: Viatura(s) com quilometragem perto da próxima revisão'
                texto = (
                    '<h1>Frota</h1>'
                    '<h2>Revisão de viatura</h2>'
                    f'<p>Faltam menos de 1000km para a(s) viatura(s) listada(s) abaixo atingir(em) a quilometragem prevista para a próxima revisão:</p><br>'
                    f'<p>{lista_viaturas}</p>'
                    f'<p class="more-info">Acesse o SUAP para mais detalhes.</p>'
                )

                send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, vinculos)
            if por_tempo:
                lista_viaturas = '<br>'.join([viatura.__str__() for viatura in por_tempo])
                titulo = '[SUAP] Frota: Viatura(s) com revisão prevista para os próximos 30 dias'
                texto = (
                    '<h1>Frota</h1>'
                    '<h2>Revisão de viatura</h2>'
                    f'<p>Faltam menos de 30 dias para a próxima revisão da(s) viatura(s) abaixo:</p><br>'
                    f'<p>{lista_viaturas}</p>'
                    f'<p class="more-info">Acesse o SUAP para mais detalhes.</p>'
                )

                send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, vinculos)
