from django.apps import apps
from django.db.models import F

from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        lista = [
            {'model_name': 'aproveitamentoestudo', 'name': 'nota'},
            {'model_name': 'certificacaoconhecimento', 'name': 'nota'},
            {'model_name': 'estruturacurso', 'name': 'media_aprovacao_avaliacao_final'},
            {'model_name': 'estruturacurso', 'name': 'media_aprovacao_sem_prova_final'},
            {'model_name': 'estruturacurso', 'name': 'media_certificacao_conhecimento'},
            {'model_name': 'estruturacurso', 'name': 'media_evitar_reprovacao_direta'},
            {'model_name': 'itemconfiguracaoavaliacao', 'name': 'nota_maxima'},
            {'model_name': 'matriculadiario', 'name': 'nota_1'},
            {'model_name': 'matriculadiario', 'name': 'nota_2'},
            {'model_name': 'matriculadiario', 'name': 'nota_3'},
            {'model_name': 'matriculadiario', 'name': 'nota_4'},
            {'model_name': 'matriculadiario', 'name': 'nota_final'},
            {'model_name': 'matriculadiarioresumida', 'name': 'media_final_disciplina'},
            {'model_name': 'notaavaliacao', 'name': 'nota'},
            {'model_name': 'registrohistorico', 'name': 'media_final_disciplina'},
            {'model_name': 'projetofinal', 'name': 'nota'},
            {'model_name': 'representacaoconceitual', 'name': 'valor_maximo'},
            {'model_name': 'representacaoconceitual', 'name': 'valor_minimo'},
        ]
        for item in lista:
            model = apps.get_model('edu', item['model_name'])
            kwargs = {item['name']: F(item['name']) * 10}
            model.objects.update(**kwargs)
