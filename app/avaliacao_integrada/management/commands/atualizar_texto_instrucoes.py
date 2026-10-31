from django.db.models import F

from avaliacao_integrada.models import Avaliacao, Segmento
from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    help = 'Aplica migração de dados para Segmento.'

    def handle(self, *args, **options):
        Avaliacao.objects.filter(segmentos__in=Segmento.SERVIDORES).update(texto_instrucoes_servidores=F('descricao'))
        Avaliacao.objects.filter(segmentos__in=(Segmento.ESTUDANTE,)).update(texto_instrucoes_alunos=F('descricao'))
        Avaliacao.objects.filter(segmentos__in=Segmento.SOCIEDADE_CIVIL).update(texto_instrucoes_sociedade_civil=F('descricao'))
