from django.core.management import call_command

from avaliacao_integrada.models import Avaliacao, ComissaoCPA
from djtools.management.commands import BaseCommandPlus
from documento_eletronico.models import DocumentoTexto


class Command(BaseCommandPlus):
    def handle(self, **options):
        call_command('adaptar_escala_likert')

        avaliacao_qs = Avaliacao.objects.filter(ano__ano='2024')
        if not avaliacao_qs.exists():
            call_command('gerar_aai_2024', '/opt/suap/avaliacao_integrada/management/commands/Instrumento_AAI_2024_EIXO3_17092024.CSV')

        if not DocumentoTexto.objects.exists():
            call_command('loaddata', '/opt/suap/documento_texto.json')
            call_command('loaddata', '/opt/suap/setores.json')

        if not ComissaoCPA.objects.exists():
            call_command('loaddata', '/opt/suap/comissao_cpa_data.json')

        avaliacao = avaliacao_qs[0]
        call_command('gerar_respondentes_avaliacao', '--avaliacao_id', str(avaliacao.pk))
