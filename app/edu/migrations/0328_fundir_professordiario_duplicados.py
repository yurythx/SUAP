"""Funde os ProfessorDiario duplicados por (diário, professor) antes da UniqueConstraint da 0329 (#17737).

Em cada par fica o vínculo de maior pk (o mais novo, decisão da #17737), com os próprios campos (tipo,
percentual_ch, ativo, datas de posse...): os dos excedentes, mais antigos, não são fundidos, só
registrados no log do migrate quando divergem. Toda FK/M2M que aponta para um excedente, em qualquer
app, é descoberta por introspecção e passa para o mantido; depois o excedente é apagado. Sem
duplicatas, não faz nada. A volta é no-op.
"""

from __future__ import annotations

import sys

from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.models import Count, Model
from django.db.models.fields.reverse_related import ForeignObjectRel


def _repassar_m2m(rel: ForeignObjectRel, excedentes: list[int], mantido: int) -> None:
    through = rel.through
    origem = through._meta.get_field(rel.field.m2m_field_name()).attname
    alvo = through._meta.get_field(rel.field.m2m_reverse_field_name()).attname
    antigos = through._base_manager.filter(**{f'{alvo}__in': excedentes})
    origens = set(antigos.values_list(origem, flat=True))
    # ignore_conflicts: a linha (origem, mantido) pode já existir.
    through._base_manager.bulk_create([through(**{origem: o, alvo: mantido}) for o in origens], ignore_conflicts=True)
    antigos.delete()


def _repassar_relacoes(modelo: type[Model], excedentes: list[int], mantido: int) -> None:
    for rel in modelo._meta.related_objects:
        if rel.many_to_many and rel.through._meta.auto_created:
            _repassar_m2m(rel, excedentes, mantido)
        elif rel.many_to_many:
            continue  # through explícito: a FK dele para ProfessorDiario aparece como ManyToOneRel própria
        elif rel.one_to_many:  # ForeignKey para ProfessorDiario
            campo = rel.field.attname
            rel.related_model._base_manager.filter(**{f'{campo}__in': excedentes}).update(**{campo: mantido})
        else:
            # Um OneToOne viraria duas linhas para o mesmo vínculo; apagar o excedente o perderia em cascata.
            raise NotImplementedError(f'Relação não tratada na fusão de ProfessorDiario: {rel!r}')


def _divergencias(mantido: Model, excedente: Model) -> list[str]:
    return [f.name for f in mantido._meta.concrete_fields if not f.primary_key and getattr(mantido, f.attname) != getattr(excedente, f.attname)]


def _remover_auto_compartilhamento(apps: Apps, mantido: int) -> None:
    """Tira o mantido dos ``outros_professor_diario`` das aulas em que ele é o titular (AulaForm recusa isso)."""
    through = apps.get_model('edu', 'Aula').outros_professor_diario.through
    through._base_manager.filter(professordiario_id=mantido, aula__professor_diario_id=mantido).delete()


def fundir_professordiario_duplicados(apps: Apps, schema_editor: BaseDatabaseSchemaEditor | None) -> None:
    ProfessorDiario = apps.get_model('edu', 'ProfessorDiario')
    pares = list(
        ProfessorDiario._base_manager.order_by()
        .values('diario_id', 'professor_id')
        .annotate(total=Count('pk'))
        .filter(total__gt=1)
        .values_list('diario_id', 'professor_id')
    )
    for diario_id, professor_id in pares:
        *excedentes, mantido = ProfessorDiario._base_manager.filter(diario_id=diario_id, professor_id=professor_id).order_by('pk')
        for excedente in excedentes:
            sys.stdout.write(
                f'\n  ProfessorDiario diário {diario_id}, professor {professor_id}: mantido #{mantido.pk} (o mais novo), removido #{excedente.pk}'
                f' (campos divergentes: {", ".join(_divergencias(mantido, excedente)) or "nenhum"})'
            )
        pks = [e.pk for e in excedentes]
        _repassar_relacoes(ProfessorDiario, pks, mantido.pk)
        _remover_auto_compartilhamento(apps, mantido.pk)
        ProfessorDiario._base_manager.filter(pk__in=pks).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('edu', '0327_alter_alunoarquivo_descricao_and_more'),
    ]

    operations = [
        migrations.RunPython(fundir_professordiario_duplicados, migrations.RunPython.noop),
    ]
