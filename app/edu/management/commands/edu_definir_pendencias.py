from djtools.management.commands import BaseCommandPlus
from edu.models import Aluno, Modalidade, SituacaoMatricula

import logging

logger = logging.getLogger(__name__)


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        MODALIDADES_FIC = [Modalidade.FIC, Modalidade.PROEJA_FIC_FUNDAMENTAL, Modalidade.FIC_MENOS]
        qs = Aluno.objects.filter(matriz__isnull=False)

        qs_alunos_fic = qs.filter(curso_campus__modalidade__in=MODALIDADES_FIC)
        qs_alunos_fic.filter(situacao=SituacaoMatricula.MATRICULADO).update(pendencia_ch_obrigatoria=True)
        qs_alunos_fic.filter(situacao=SituacaoMatricula.NAO_CONCLUIDO).update(pendencia_ch_obrigatoria=True)
        qs_alunos_fic.filter(situacao=SituacaoMatricula.CONCLUIDO).update(pendencia_ch_obrigatoria=False)

        qs_alunos_regulares = qs.exclude(curso_campus__modalidade_id__in=MODALIDADES_FIC)
        total = qs_alunos_regulares.count()
        for i, o in enumerate(qs_alunos_regulares):
            o.get_situacao_id()
            o.save()
            if not i % 500:
                logger.info((i * 100 / total, '%'))
