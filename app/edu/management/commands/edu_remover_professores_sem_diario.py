"""
Remover os professores técnicos administrativos que não possuem diário
"""

from django.contrib.auth.models import Group
from django.db.models.deletion import Collector

from djtools.management.commands import BaseCommandPlus
from edu.models import Professor
from rh.models import Servidor


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        grupo_professor = Group.objects.get(name='Professor')

        # Removendo os professores que são técnicos e que não possuem diário caso exista
        ids = Servidor.objects.filter(eh_tecnico_administrativo=True).exclude(vinculo__professor__professordiario__isnull=False).values_list('id')
        qs = Professor.objects.filter(vinculo__pessoa__id__in=ids)

        collector = Collector('default')

        related_fields = [
            f for f in Professor._meta.get_fields(include_hidden=True) if (f.one_to_many or f.one_to_one) and f.auto_created and not f.concrete
        ]

        for related_field in related_fields:
            objs = collector.related_objects(related_field, qs)
            for obj in objs:
                print(obj.__class__)
                return

        for professor in qs:
            grupo_professor.user_set.remove(professor.vinculo.user)
        qs.delete()
