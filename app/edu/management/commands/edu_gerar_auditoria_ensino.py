import datetime

from djtools.management.commands import BaseCommandPlus
from edu import tasks
from edu.models import AuditoriaEnsino, NivelEnsino
from rh.models import UnidadeOrganizacional


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        hoje = datetime.date.today()

        # executa rotina de geração de auditoria a cada 2 dias
        if hoje.day % 2 != 0:
            campi = UnidadeOrganizacional.objects.campi().all()

            # Auditorias mensais
            qs_auditoria_mensal = AuditoriaEnsino.objects.filter(
                data_auditoria__year=hoje.year, data_auditoria__month=hoje.month, geracao_finalizada=True
            )

            # Auditorias Trimestrais
            periodo_trimestral = [3, 6, 8, 12]  # alteração temporária para gerar auditorias em agosto.
            if hoje.month in periodo_trimestral:
                qs_auditoria_trimestral = AuditoriaEnsino.objects.filter(
                    data_auditoria__year=hoje.year, data_auditoria__month=hoje.month, geracao_finalizada=True
                )

            # Auditorias Semestrais
            periodo_semestral = [1, 7]
            if hoje.month in periodo_semestral:
                qs_auditoria_semestral = AuditoriaEnsino.objects.filter(
                    data_auditoria__year=hoje.year, data_auditoria__month=hoje.month, geracao_finalizada=True
                )

            # Auditoria Anual
            if hoje.month == 12:
                qs_auditoria_anual = AuditoriaEnsino.objects.filter(
                    data_auditoria__year=hoje.year, data_auditoria__month=hoje.month, geracao_finalizada=True
                )
            niveis = [NivelEnsino.FUNDAMENTAL, NivelEnsino.MEDIO, NivelEnsino.GRADUACAO, NivelEnsino.POS_GRADUACAO]
            for campus in campi:
                for nivel in niveis:
                    for tipo in AuditoriaEnsino.AUDITORIAS_MENSAIS:
                        if not qs_auditoria_mensal.filter(tipo_auditoria=tipo, campus_id=campus.id, nivel_ensino_id=nivel).exists():
                            auditoria = AuditoriaEnsino()
                            auditoria.tipo_auditoria = tipo
                            auditoria.campus = campus
                            auditoria.nivel_ensino_id = nivel
                            auditoria.save()
                            tasks.gerar_auditoria_ensino(auditoria)

                    if hoje.month in periodo_trimestral:
                        for tipo in AuditoriaEnsino.AUDITORIAS_TRIMESTRAIS:
                            gerar_auditoria = False
                            if tipo == AuditoriaEnsino.TIPO_CIDADE:
                                nivel_ensino_id = None
                                gerar_auditoria = not qs_auditoria_trimestral.filter(tipo_auditoria=tipo, campus_id=campus.id).exists()
                            else:
                                nivel_ensino_id = nivel
                                gerar_auditoria = not qs_auditoria_trimestral.filter(
                                    tipo_auditoria=tipo, campus_id=campus.id, nivel_ensino_id=nivel
                                ).exists()
                            if gerar_auditoria:
                                auditoria = AuditoriaEnsino()
                                auditoria.tipo_auditoria = tipo
                                auditoria.campus = campus
                                auditoria.nivel_ensino_id = nivel_ensino_id
                                auditoria.save()
                                tasks.gerar_auditoria_ensino(auditoria)

                    if hoje.month in periodo_semestral:
                        for tipo in AuditoriaEnsino.AUDITORIAS_SEMESTRAIS:
                            gerar_auditoria = False
                            if tipo == AuditoriaEnsino.TIPO_NOME_SERVIDOR:
                                nivel_ensino_id = None
                                gerar_auditoria = not qs_auditoria_semestral.filter(tipo_auditoria=tipo, campus_id=campus.id).exists()
                            else:
                                nivel_ensino_id = nivel
                                gerar_auditoria = not qs_auditoria_semestral.filter(
                                    tipo_auditoria=tipo, campus_id=campus.id, nivel_ensino_id=nivel
                                ).exists()
                            if gerar_auditoria:
                                auditoria = AuditoriaEnsino()
                                auditoria.tipo_auditoria = tipo
                                auditoria.campus = campus
                                auditoria.nivel_ensino_id = nivel_ensino_id
                                auditoria.save()
                                tasks.gerar_auditoria_ensino(auditoria)

                    if hoje.month == 12:
                        if not qs_auditoria_anual.filter(
                            tipo_auditoria=AuditoriaEnsino.TIPO_RECEITA_FEDERAL, campus_id=campus.id, nivel_ensino_id=nivel
                        ).exists():
                            auditoria = AuditoriaEnsino()
                            auditoria.tipo_auditoria = AuditoriaEnsino.TIPO_RECEITA_FEDERAL
                            auditoria.campus = campus
                            auditoria.nivel_ensino_id = nivel
                            auditoria.save()
                            tasks.gerar_auditoria_ensino(auditoria)
