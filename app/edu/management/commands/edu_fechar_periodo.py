from datetime import datetime

import tqdm
from django.db.models import Q

from djtools.management.commands import BaseCommandPlus
from edu.models import Diario, MatriculaPeriodo, SituacaoMatriculaPeriodo


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        verbose = str(options.get('verbosity', '0')) != '0'
        qs = Diario.objects.filter(componente_curricular__qtd_avaliacoes__lte=2)
        qs.exclude(posse_etapa_3=Diario.POSSE_REGISTRO_ESCOLAR).update(posse_etapa_3=Diario.POSSE_REGISTRO_ESCOLAR)
        qs.exclude(posse_etapa_4=Diario.POSSE_REGISTRO_ESCOLAR).update(posse_etapa_4=Diario.POSSE_REGISTRO_ESCOLAR)
        qs = Diario.objects.filter(componente_curricular__qtd_avaliacoes__lt=2)
        qs.exclude(posse_etapa_2=Diario.POSSE_REGISTRO_ESCOLAR).update(posse_etapa_2=Diario.POSSE_REGISTRO_ESCOLAR)

        qs = MatriculaPeriodo.objects.filter(
            situacao_id=SituacaoMatriculaPeriodo.MATRICULADO,
            matriculadiario__diario__calendario_academico__data_fechamento_periodo__lte=datetime.today(),
        ).distinct()

        if verbose:
            qs = tqdm.tqdm(qs)

        for matriculaperiodo in qs:
            matriculaperiodo.fechar_periodo_letivo()

        ids_diario = (
            Diario.objects.filter(calendario_academico__data_fechamento_periodo__lte=datetime.now())
            .filter(
                Q(posse_etapa_1=Diario.POSSE_PROFESSOR)
                | Q(posse_etapa_2=Diario.POSSE_PROFESSOR)
                | Q(posse_etapa_3=Diario.POSSE_PROFESSOR)
                | Q(posse_etapa_4=Diario.POSSE_PROFESSOR)
                | Q(posse_etapa_5=Diario.POSSE_PROFESSOR)
            )
            .exclude(matriculadiario__matricula_periodo__situacao=SituacaoMatriculaPeriodo.MATRICULADO)
            .values_list('id')
            .distinct()
        )

        Diario.objects.filter(id__in=ids_diario).update(
            posse_etapa_1=Diario.POSSE_REGISTRO_ESCOLAR,
            posse_etapa_2=Diario.POSSE_REGISTRO_ESCOLAR,
            posse_etapa_3=Diario.POSSE_REGISTRO_ESCOLAR,
            posse_etapa_4=Diario.POSSE_REGISTRO_ESCOLAR,
            posse_etapa_5=Diario.POSSE_REGISTRO_ESCOLAR,
        )
