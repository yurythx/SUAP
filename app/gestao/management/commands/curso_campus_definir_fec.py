import datetime
import os
from decimal import Decimal

from django.db import transaction

from djtools.management.commands import BaseCommandPlus
from edu.models import CursoCampus

__location__ = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))


class Command(BaseCommandPlus):
    gerar_planilha = False
    importar_planilha = True
    label_sem_informacao = '----'

    def handle(self, *args, **options):
        if Command.gerar_planilha:
            self.gerar_planilha(*args, **options)
        elif Command.importar_planilha:
            self.importar_planilha_execute(*args, **options)
        else:
            self.stdout.write('Defina o que o comando deverá fazer: gerar_planilha ou importar_planilha')

    def gerar_planilha_execute(self, *args, **options):
        title = 'Curso Campus - Planilha para Definir FEC (Fator de Esforço do Curso) Em Lote'

        self.stdout.write('\n')
        self.stdout.write('- ' * int(len(title) / 2))
        self.stdout.write(title)
        self.stdout.write('- ' * int(len(title) / 2))
        self.stdout.write('Início do processamento: {}'.format(datetime.datetime.now().strftime('%d/%m/%Y - %H:%M:%S')))
        self.stdout.write('\n')

        colunas = '{id};{descricao};{modalidade};{ano_letivo};{periodo_letivo};{fec};{ativo}'
        self.stdout.write(
            colunas.format(
                id='Id',
                descricao='Descrição',
                modalidade='Modalidade',
                ano_letivo='Ano Letivo',
                periodo_letivo='Período Letivo',
                fec='FEC',
                ativo='Ativo',
            )
        )
        qs_cursos_campus = CursoCampus.objects.all().order_by('descricao')

        for curso_campus in qs_cursos_campus:
            self.stdout.write(
                colunas.format(
                    id=curso_campus.id,
                    descricao=curso_campus.descricao,
                    modalidade=curso_campus.modalidade.descricao if curso_campus.modalidade else self.label_sem_informacao,
                    ano_letivo=curso_campus.ano_letivo.ano if curso_campus.ano_letivo else self.label_sem_informacao,
                    periodo_letivo=curso_campus.periodo_letivo or self.label_sem_informacao,
                    fec=curso_campus.fator_esforco_curso,
                    ativo='SIM' if curso_campus.ativo else 'NAO',
                )
            )
        self.stdout.write('\n')
        self.stdout.write('Processamento concluído com sucesso')
        self.stdout.write('Fim do processamento: {}'.format(datetime.datetime.now().strftime('%d/%m/%Y - %H:%M:%S')))

    @transaction.atomic()
    def importar_planilha_execute(self, *args, **options):
        title = 'Curso Campus - Importação de Planilha para Definir FEC (Fator de Esforço do Curso) Em Lote'

        self.stdout.write('\n')
        self.stdout.write('- ' * int(len(title) / 2))
        self.stdout.write(title)
        self.stdout.write('- ' * int(len(title) / 2))
        self.stdout.write('Início do processamento: {}'.format(datetime.datetime.now().strftime('%d/%m/%Y - %H:%M:%S')))
        self.stdout.write('\n')

        with open(os.path.join(__location__, 'CursosCampus_Definir_FEC.csv')) as f:
            lines = f.readlines()

        is_valid_line = False
        for line in lines:
            if '{{END}}' in line:
                is_valid_line = False

            if is_valid_line:
                curso_campus_csv_line = line.split(';')
                # print curso_campus_csv_line
                curso_campus_id = int(curso_campus_csv_line[0])
                curso_campus_descricao = curso_campus_csv_line[1]
                curso_campus_fec = Decimal(curso_campus_csv_line[-2].replace(',', '.'))
                # print curso_campus_id, curso_campus_fec

                if curso_campus_fec != 1.0:
                    # print curso_campus_id, curso_campus_descricao, curso_campus_fec
                    # SQL gerado: UPDATE "edu_cursocampus" SET "fator_esforco_curso" = '1.99' WHERE "edu_cursocampus"."id" = 123
                    CursoCampus.objects.filter(id=curso_campus_id).update(fator_esforco_curso=curso_campus_fec)
                    self.stdout.write(f'O curso {curso_campus_id:d}, "{curso_campus_descricao}", teve seu FEC atualizado para {curso_campus_fec:.2f}')

            if '{{BEGIN}}' in line:
                is_valid_line = True

        self.stdout.write('\n')
        self.stdout.write('Processamento concluído com sucesso')
        self.stdout.write('Fim do processamento: {}'.format(datetime.datetime.now().strftime('%d/%m/%Y - %H:%M:%S')))
