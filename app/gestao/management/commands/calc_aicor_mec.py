from djtools.management.commands import BaseCommandPlus
from edu.models import MatriculaPeriodo
from gestao.models import Variavel


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        v = Variavel()
        qs = v.get_qs_alunos_matriculados()[0]
        alunos_ingressantes_params = qs.values('aluno__curso_campus', 'ano_letivo', 'periodo_letivo').distinct()
        print(alunos_ingressantes_params.count())

        qs_ai_mec = None
        for aip in alunos_ingressantes_params:
            if qs_ai_mec is None:
                qs_ai_mec = MatriculaPeriodo.objects.filter(
                    aluno__curso_campus=aip['aluno__curso_campus'], ano_letivo=aip['ano_letivo'], periodo_letivo=aip['periodo_letivo']
                )
            else:
                qs_ai_mec = qs_ai_mec | MatriculaPeriodo.objects.filter(
                    aluno__curso_campus=aip['aluno__curso_campus'], ano_letivo=aip['ano_letivo'], periodo_letivo=aip['periodo_letivo']
                )

        print(qs_ai_mec.count())
        # print qs_ai_mec.query
