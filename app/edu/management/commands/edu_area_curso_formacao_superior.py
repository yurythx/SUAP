import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand

from edu.models import CursoFormacaoSuperior
from edu.models.cadastros_gerais import AreaCursoFormacaoSuperior

"""
python manage.py edu_area_curso_formacao_superior
"""


class Command(BaseCommand):
    help = 'Importa dados do arquivo Cursos_Formacao_Superior_2024.xlsx para o modelo AreaCursoFormacaoSuperior'

    def handle(self, *args, **kwargs):
        df = pd.read_excel(f'{settings.BASE_DIR}/edu/fixtures/Cursos_Formacao_Superior_2024.xlsx', header=None)

        # Criar um dicionário para armazenar códigos já importados (para evitar duplicidade)
        imported_codes = set()
        for _index, row in df.iloc[1:].iterrows():  # Ignorar o cabeçalho
            codigo = str(row.iloc[6])[:-1]  # Remove o último dígito da coluna "Código"
            nome = row.iloc[7].split(' - ')[0]  # Remove o texto após o hífen na coluna "Nome"

            cod_geral = str(int(row.iloc[0]))
            area_geral = row.iloc[1]
            cod_especifica = str(int(row.iloc[2]))
            area_especifica = row.iloc[3]
            cod_detalhada = str(int(row.iloc[4]))
            area_detalhada = row.iloc[5]

            # Verificar duplicidade
            if codigo in imported_codes:
                continue

            # Adicionar código ao conjunto de códigos importados
            imported_codes.add(codigo)

            # Criar ou atualizar o objeto no banco de dados
            AreaCursoFormacaoSuperior.objects.update_or_create(
                codigo_cine=codigo,
                defaults={
                    'cine': nome,
                    'codigo_area_geral': cod_geral,
                    'area_geral': area_geral,
                    'codigo_area_especifica': cod_especifica,
                    'area_especifica': area_especifica,
                    'codigo_area_detalhada': cod_detalhada,
                    'area_detalhada': area_detalhada,
                },
            )

        # Atualizar o modelo CursoFormacaoSuperior
        cursos = CursoFormacaoSuperior.objects.all()
        for curso in cursos:
            codigo_curso = curso.codigo[:-1]  # Remove o último dígito do código do curso
            try:
                area_curso = AreaCursoFormacaoSuperior.objects.get(codigo_cine=codigo_curso)
                curso.area_curso_formacao_superior = area_curso
                curso.save()
            except AreaCursoFormacaoSuperior.DoesNotExist:
                self.stdout.write(self.style.WARNING(f'Área NÃO encontrada => {codigo_curso} - {curso.descricao}'))

        self.stdout.write(self.style.SUCCESS('Dados importados com sucesso!'))
