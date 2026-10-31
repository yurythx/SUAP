from django.db import connection

from ae.models import DemandaAlunoAtendida, Programa
from djtools.db import has_column
from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        sql = """
            ALTER TABLE "ae_demandaalunoatendida" ADD COLUMN "programa_id" integer NULL REFERENCES "ae_programa" ("id")  DEFERRABLE INITIALLY DEFERRED;
            CREATE INDEX "ae_demandaalunoatendida_programa_id" ON "ae_demandaalunoatendida" ("programa_id");
        """

        if not has_column('programa_id', 'ae_demandaalunoatendida'):
            cur = connection.cursor()
            print(sql)
            cur.execute(sql)
            connection._commit()

        for programa in Programa.objects.filter(tipo_programa__sigla=Programa.TIPO_ALIMENTACAO):
            atendimentos1 = DemandaAlunoAtendida.objects.filter(aluno__curso__instituicao__uo=programa.instituicao, demanda__id=1)  # Almoço
            atendimentos2 = DemandaAlunoAtendida.objects.filter(aluno__curso__instituicao__uo=programa.instituicao, demanda__id=2)  # Jantar
            total = atendimentos1.count() + atendimentos2.count()
            if total:
                print((programa, total))
                atendimentos1.update(programa=programa)
                atendimentos2.update(programa=programa)

        for programa in Programa.objects.filter(tipo_programa__sigla=Programa.TIPO_TRANSPORTE):
            atendimentos1 = DemandaAlunoAtendida.objects.filter(aluno__curso__instituicao__uo=programa.instituicao, demanda__id=12)  # Passe Municipal
            atendimentos2 = DemandaAlunoAtendida.objects.filter(
                aluno__curso__instituicao__uo=programa.instituicao, demanda__id=13
            )  # Passe Intemunicipal
            total = atendimentos1.count() + atendimentos2.count()
            if total:
                print((programa, total))
                atendimentos1.update(programa=programa)
                atendimentos2.update(programa=programa)

        for programa in Programa.objects.filter(tipo_programa__sigla=Programa.TIPO_IDIOMA):
            atendimentos = DemandaAlunoAtendida.objects.filter(
                aluno__curso__instituicao__uo=programa.instituicao, demanda__id=14
            )  # bolsa em curso de idiomas
            total = atendimentos.count()
            if total:
                print((programa, total))
                atendimentos.update(programa=programa)

        for programa in Programa.objects.filter(tipo_programa__sigla=Programa.TIPO_TRABALHO):
            atendimentos = DemandaAlunoAtendida.objects.filter(aluno__curso__instituicao__uo=programa.instituicao, demanda__id=15)  # bolsa de estágio
            total = atendimentos.count()
            if total:
                print((programa, total))
                atendimentos.update(programa=programa)
