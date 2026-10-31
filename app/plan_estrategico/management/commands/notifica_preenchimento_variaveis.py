import datetime
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import Group

from comum.models import UsuarioGrupo
from djtools.management.commands import BaseCommandPlus
from djtools.utils import send_notification
from plan_estrategico.models import PeriodoPreenchimentoVariavel, VariavelCampus
from rh.models import UnidadeOrganizacional


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        hoje = datetime.datetime.now().date()
        grupo = Group.objects.get(name='Gestor Estratégico Local')
        titulo = '[SUAP] Farol de Desempenho: Variáveis não preenchidas'
        if PeriodoPreenchimentoVariavel.get_em_periodo_de_preenchimento():
            periodo = PeriodoPreenchimentoVariavel.get_em_periodo_de_preenchimento()[0]
            if (
                hoje + timedelta(5) == periodo.data_termino.date()
                or hoje + timedelta(3) == periodo.data_termino.date()
                or hoje == periodo.data_termino.date()
            ):
                for uo in UnidadeOrganizacional.objects.uo().all():
                    total_variaveis_preenchidas = (
                        VariavelCampus.objects.filter(
                            uo=uo,
                            ano=periodo.ano.ano,
                            variavel__fonte='Manual',
                            data_atualizacao__date__gte=periodo.data_inicio,
                            situacao=VariavelCampus.ATIVA,
                        ).count()
                        or 0
                    )
                    total_variaveis = (
                        VariavelCampus.objects.filter(uo=uo, ano=periodo.ano.ano, variavel__fonte='Manual', situacao=VariavelCampus.ATIVA).count()
                        or 1
                    )
                    percentual_preenchido = round(total_variaveis_preenchidas * 100.0 / total_variaveis)
                    total_restante = total_variaveis - total_variaveis_preenchidas
                    if total_variaveis_preenchidas < total_variaveis:
                        for usuario in UsuarioGrupo.objects.filter(group=grupo, user__vinculo__setor__uo=uo):
                            url = f'{settings.SITE_URL}/plan_estrategico/relatorio_ranking/'
                            texto = []
                            texto.append('<h1>Variáveis Não Preenchidas</h1>')
                            texto.append(
                                f'No ranking de preenchimento do Farol de Desempenho, a unidade {uo} preencheu {percentual_preenchido}% das variáveis até o momento. Faltam {total_restante} variáveis a serem preenchidas.</p>'
                            )
                            texto.append(
                                f'<p class="more-info">Para mais informações sobre o ranking completo, acesse: <a href="{url}">Ranking de Preenchimento</a></p>'
                            )

                            if hoje == periodo.data_termino.date():
                                texto = []
                                texto.append('<h1>Variáveis Não Preenchidas</h1>')
                                texto.append(
                                    f'<p>No ranking de preenchimento do Farol de Desempenho, a unidade {uo} preencheu {percentual_preenchido}% das variáveis até o momento. Faltam {total_restante} variáveis a serem preenchidas.</p>'
                                )
                                texto.append('<p>--</p>')
                                texto.append('<p>Atenção: O período de preenchimento se encerrará hoje. Fique atento!</p>')
                                texto.append('<p></p>')
                                texto.append(
                                    f'<p>Para mais informações sobre o ranking completo, acesse: <a href="{url}">Ranking de Preenchimento</a></p>'
                                )

                            send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, [usuario.user.get_vinculo()])
