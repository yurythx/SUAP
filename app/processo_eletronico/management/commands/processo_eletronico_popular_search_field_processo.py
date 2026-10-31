from django.contrib.postgres.aggregates import StringAgg
from django.db.models import ExpressionWrapper, F, OuterRef, Subquery, TextField
from django.db.models.functions import Concat, Substr

from djtools.management.commands import BaseCommandPlus
from processo_eletronico.models import Processo


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        if not Processo.objects.exists():
            self.stdout.write('Nenhum processo; search_fields_optimized ignorado')
            return
        qs = Processo.objects.all().annotate(
            search_fields_optimized_generated=ExpressionWrapper(
                Substr(
                    Concat(
                        F('id'),
                        F('numero_protocolo'),
                        F('numero_protocolo_fisico'),
                        F('assunto'),
                        Subquery(
                            Processo.objects.filter(pk=OuterRef('pk'))
                            .annotate(usuarios=StringAgg('interessados__pessoa__nome', delimiter=''))
                            .values('usuarios')
                        ),
                        output_field=TextField(),
                    ),
                    1,
                    1000,
                    output_field=TextField(),
                ),
                output_field=TextField(),
            )
        )
        qs.update(search_fields_optimized=F('search_fields_optimized_generated'))
