# ruff: noqa: T100
"""
Comando utilitário para migrar todos os dados de um objeto para outro.
"""

import pdb

from django.db.transaction import atomic

from djtools.management.commands import BaseCommandPlus


@atomic
def atualizar_referencia(command, source, target, verbose=False):
    cls = type(source)
    fields = cls._meta.get_fields()
    for field in fields:
        if hasattr(field, 'field') and not field.concrete:
            related_cls = field.related_model
            related_filter = {field.field.name: source.pk}
            related_pks = related_cls.objects.filter(**related_filter).values_list('pk', flat=True)
            if verbose and related_pks.exists():
                command.stdout.write((related_cls._meta.app_label, related_cls, field, related_pks))
            for related_pk in related_pks:
                if related_cls.__name__ != 'Caracterizacao':
                    related_obj = related_cls.objects.get(pk=related_pk)
                    if field.many_to_many:
                        related_field = getattr(related_obj, field.field.name)
                        related_field.remove(source)
                        related_field.add(target)
                    else:
                        setattr(related_obj, field.field.name, target)
                        related_obj.save()


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        source = None
        target = None
        self.stdout.write(
            """Por favor, localize o objeto que deseja mover os dados e o atribua à variável "source".
        Em seguida, localize o objeto para qual deseja mover os dados e o atribua à variável "target".'
        Por fim, pressione a tecla "c"."""
        )
        pdb.set_trace()
        if source and target:
            atualizar_referencia(self, source, target, True)
