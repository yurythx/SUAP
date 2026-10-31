from djtools.management.commands import BaseCommandPlus
from edu.models import Aluno, CursoCampus, SequencialMatricula


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        print('CURSOS INCONSISTENTES')
        for curso_campus in CursoCampus.objects.filter(estrutura__isnull=False):
            if curso_campus.codigo.startswith('-') or not curso_campus.ativo:
                print((curso_campus.descricao, curso_campus.codigo))

        print('TURMAS COM CÓDIGOS INCONSISTENTES')
        for curso_campus in CursoCampus.objects.filter(estrutura__isnull=False):
            for turma in curso_campus.turma_set.all():
                codigo = f'{turma.ano_letivo.ano}{turma.periodo_letivo}.{turma.periodo_matriz}.{turma.curso_campus.codigo}.{turma.sequencial}{turma.turno.descricao[0]}'
                if turma.codigo != codigo:
                    print((turma.curso_campus.codigo, turma))

        print('ALUNOS COM MATRÍCULAS INCONSISTENTES')
        for aluno in Aluno.objects.filter(matriculaperiodo__turma__isnull=False).distinct():
            prefixo = f'{aluno.ano_letivo}{aluno.periodo_letivo}{aluno.curso_campus.codigo}'
            if not aluno.matricula.startswith(prefixo):
                print((prefixo, aluno.matricula))

        print('SEQUENCIAIS DE MATRÍCULAS INCONSISTENTES')
        for s in SequencialMatricula.objects.all():
            contador = Aluno.objects.filter(matricula__startswith=s.prefixo).count()
            if contador > s.contador:
                print((s.prefixo, contador, s.contador))
