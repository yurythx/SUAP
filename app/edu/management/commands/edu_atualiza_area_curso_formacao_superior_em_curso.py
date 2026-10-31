import csv

import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand

from edu.models import CursoCampus
from edu.models.cadastros_gerais import AreaCursoFormacaoSuperior

"""
python manage.py edu_atualiza_area_curso_formacao_superior_em_curso
"""


class Command(BaseCommand):
    help = 'Atualiza o atributo AreaCursoFormacaoSuperior do modelo CampusCurso com base no arquivo '

    def handle(self, *args, **kwargs):
        file_path = f'{settings.BASE_DIR}/edu/fixtures/eMEC_Relatorio_Cursos_Graduacao.csv'

        # Listas para armazenar linhas com problemas
        linhas_com_problemas = []

        # Ler o arquivo CSV manualmente para identificar e reportar problemas linha a linha
        with open(file_path, encoding='Windows-1252') as csvfile:
            reader = csv.DictReader(csvfile, delimiter=';')
            rows = []
            for i, row in enumerate(reader, start=1):
                try:
                    # Remover espaços em branco dos cabeçalhos e aspas das variáveis
                    row = {k.strip(): v.strip().replace('"', '') for k, v in row.items()}
                    rows.append(row)
                except Exception as e:
                    linhas_com_problemas.append((i, str(e)))

        df = pd.DataFrame(rows)

        # Criar um dicionário para mapeamento rápido
        cine_map = {str(row['CÓDIGO DO CURSO']): str(row['CÓDIGO CINE RÓTULO']).lstrip('=') for _, row in df.iterrows()}
        cursos_campus = CursoCampus.objects.exclude(codigo_emec__isnull=True).exclude(codigo_emec__exact='')
        for curso_campus in cursos_campus:
            codigo_emec = curso_campus.codigo_emec
            # Verificar se o código e-MEC está no mapeamento do CSV
            if codigo_emec in cine_map:
                codigo_cine_rotulo = cine_map[codigo_emec]

                # Tentar encontrar o registro correspondente no modelo AreaCursoFormacaoSuperior
                try:
                    area_curso = AreaCursoFormacaoSuperior.objects.get(codigo_cine=codigo_cine_rotulo)
                    curso_campus.area_curso_formacao_superior = area_curso
                    curso_campus.save()
                    self.stdout.write(self.style.SUCCESS(f'CursoCampus atualizado para o código e-MEC {codigo_emec}'))
                except AreaCursoFormacaoSuperior.DoesNotExist:
                    self.stdout.write(self.style.WARNING(f'Área não encontrada para o código CINE {codigo_cine_rotulo} no curso e-MEC {codigo_emec}'))
            else:
                self.stdout.write(self.style.SUCCESS(f'Curso {curso_campus} ({codigo_emec}) não encontrado no arquivo csv.'))

        # Reportar linhas com problemas
        if linhas_com_problemas:
            self.stdout.write(self.style.ERROR('Linhas com problemas encontradas no CSV:'))
            for linha, erro in linhas_com_problemas:
                self.stdout.write(self.style.ERROR(f'Linha {linha}: {erro}'))

        self.stdout.write(self.style.SUCCESS('Atualização de CursoCampus concluída!'))
        self.stdout.write(self.style.SUCCESS(f'Linhas com problemas: {len(linhas_com_problemas)}'))
