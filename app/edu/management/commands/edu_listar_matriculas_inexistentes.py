from django.db.models.deletion import Collector

from ae.models import AgendamentoRefeicao, Caracterizacao, DadosBancarios, HistoricoRendaFamiliar, Inscricao, InscricaoCaracterizacao
from djtools.management.commands import BaseCommandPlus
from edu.models import Aluno, HistoricoSituacaoMatricula, Log, RegistroDiferenca
from edu.q_academico import DAO


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        dao = DAO()
        lista = []
        lista_completa = Aluno.objects.filter(matriculaperiodo__isnull=True).values_list('matricula', flat=True)
        lista_matriculas = dao.alunos_existem(lista_completa)
        collector = Collector('default')
        contador = 0
        related_fields = [
            f for f in Aluno._meta.get_fields(include_hidden=True) if (f.one_to_many or f.one_to_one) and f.auto_created and not f.concrete
        ]
        for matricula in lista_completa:
            pode_apagar = True
            if matricula not in lista_matriculas:
                resultado = matricula
                qs = Aluno.objects.filter(matricula=matricula)
                for related_field in related_fields:
                    objs = collector.related_objects(related_field, qs)
                    for obj in objs:
                        if obj not in lista:
                            if obj._meta.model not in (
                                Caracterizacao,
                                HistoricoRendaFamiliar,
                                Inscricao,
                                DadosBancarios,
                                InscricaoCaracterizacao,
                                AgendamentoRefeicao,
                                HistoricoSituacaoMatricula,
                                Log,
                                RegistroDiferenca,
                            ):
                                pode_apagar = False
                                resultado += ' - ' + str(obj._meta.model)
                if pode_apagar:
                    contador += 1
                    print(resultado)
        print(('Total de alunos: ', contador))
