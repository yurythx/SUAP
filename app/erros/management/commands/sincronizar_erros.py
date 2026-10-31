"""
Atualiza a situação das issues no gitlab e sentry e os erros do suap.
"""

from datetime import datetime, timedelta

import tqdm
from django.db.models import Max

from comum.utils import ferramentas_configuradas
from djtools.management.commands import BaseCommandPlus
from erros.models import Erro, HistoricoComentarioErro
from erros.utils import sincronizar_ferramentas


class Command(BaseCommandPlus):
    def add_arguments(self, parser):
        parser.add_argument('pks', nargs='*', type=int)

    def handle(self, *args, **options):
        verbosity = options.get('verbosity', 3)
        pks = options.get('pks')
        conf = ferramentas_configuradas()
        if not conf:
            self.stdout.write('Sentry ou Gitlab não configurados em /comum/configuracao')
            return

        qs = Erro.objects.exclude(situacao__in=Erro.SITUACOES_FINAIS)
        if pks:
            qs = qs.filter(pk__in=pks)
        if verbosity:
            qs = tqdm.tqdm(qs)

        for erro in qs:
            sincronizar_ferramentas(erro, conf)

        semana_passada = datetime.now() - timedelta(7)
        qs_erro_sem_feedback = (
            Erro.objects.filter()
            .annotate(ultimo_comentario=Max('historicocomentarioerro__data_alteracao'))
            .filter(
                ultimo_comentario__lte=semana_passada,
                situacao=Erro.SITUACAO_AGUARDANDO_FEEDBACK,
                historicocomentarioerro__automatico=False,
                historicocomentarioerro__tipo=HistoricoComentarioErro.TIPO_COMENTARIO,
            )
        )
        for erro in qs_erro_sem_feedback:
            erro.cancelar_automatico()
