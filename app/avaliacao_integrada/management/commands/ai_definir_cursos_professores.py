import re

import pandas as pd

from djtools.management.commands import BaseCommandPlus
from djtools.utils import mask_cpf
from edu.models import CursoCampus, Professor, ProfessorDiario


class Command(BaseCommandPlus):
    def add_arguments(self, parser):
        parser.add_argument('file_path', nargs='+', type=str)

    def get_curso(self, codigo, codigos_invalidos):
        qs_curso_campus = CursoCampus.objects.filter(codigo=codigo)
        qs2_curso_campus = CursoCampus.objects.filter(codigo=f'0{codigo}')

        if qs_curso_campus.exists():
            return qs_curso_campus[0]
        elif qs2_curso_campus.exists():
            return qs2_curso_campus[0]
        else:
            codigos_invalidos.append(codigo)
            return None

    def get_professor(self, matricula, matriculas_invalidas):
        qs_professor = Professor.objects.filter(vinculo__user__username=matricula)
        if qs_professor.exists():
            return qs_professor[0]
        else:
            if len(matricula) == 10:
                matricula = f'0{matricula}'
            matricula = mask_cpf(matricula)
            qs_professor = Professor.objects.filter(vinculo__pessoa__pessoa_fisica__cpf=matricula)
            if qs_professor.exists():
                return qs_professor[0]
            else:
                matriculas_invalidas.append(matricula)
                return None

    def handle(self, file_path, **options):
        for professor_diario in ProfessorDiario.objects.all():
            professor_diario.professor.cursos_lecionados.add(professor_diario.diario.turma.curso_campus)

        df = pd.read_excel(file_path[0], header=None)

        re1 = re.compile(r'201[0-9][1|2]\.[0-9][0-9].*')
        re2 = re.compile(r'201[0-9][1|2]\.[0-9]\..*')
        re3 = re.compile(r'201[0-9]\.[1|2]\.[0-9]\..*')

        codigos_invalidos = []
        matriculas_invalidas = []

        for _index, row in df.iloc[1:].iterrows():
            # testando se o fluxo da integração foi seguido corretamente
            codigo_turma = row.iloc[3]
            matricula = row.iloc[5]
            if codigo_turma:
                m = re1.match(codigo_turma)
                if m:
                    codigo_turma = codigo_turma[6:].split('.')[0]
                else:
                    m = re2.match(codigo_turma)
                    if m:
                        codigo_turma = codigo_turma[8:].split('.')[0]
                    else:
                        m = re3.match(codigo_turma)
                        if m:
                            codigo_turma = codigo_turma[7:].split('.')[0]

                matricula = matricula.split('(')[1].split(')')[0]
                curso_campus = self.get_curso(codigo_turma, codigos_invalidos)
                if curso_campus:
                    professor = self.get_professor(matricula, matriculas_invalidas)
                    if professor:
                        professor.cursos_lecionados.add(curso_campus)
        self.stdout.write(str(set(codigos_invalidos)))
        self.stdout.write(str(set(matriculas_invalidas)))
