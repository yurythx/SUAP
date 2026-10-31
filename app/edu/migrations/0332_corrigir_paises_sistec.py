"""Leva às bases existentes a correção de comum/cadastros_basicos/paises.xls (a sigla do edu.Pais é o ISO 3166-1 alfa-3).

- "Irlanda Do Norte" tinha IRL e era a única Irlanda da lista: vira "Irlanda" (IRL), e a Irlanda do Norte ganha linha própria (GBR);
- "Estados Assoc. Das Antilhas" (dissolvidos em 1981) repetia ANT, das Antilhas Holandesas: sai, se nada o referencia;
- nomes truncados ou de país extinto ("Hong", "Sri", "Vietnã Do Sul") ganham o nome atual.

O edu_importar_sistec só insere pelo par (sigla, nome): sem esta migration, reimportar a planilha duplicaria as linhas.
"""

import sys

from django.db import migrations

RENOMES = [
    ('IRL', 'Irlanda Do Norte', 'Irlanda'),
    ('VNM', 'Vietnã Do Sul', 'Vietnã'),
    ('HKG', 'Hong', 'Hong Kong'),
    ('LKA', 'Sri', 'Sri Lanka'),
]


def corrigir(apps, schema_editor):
    Pais = apps.get_model('edu', 'Pais')
    for sigla, antigo, novo in RENOMES:
        if Pais.objects.filter(sigla=sigla, nome=antigo).update(nome=novo) and sigla == 'IRL':
            Pais.objects.get_or_create(sigla='GBR', nome='Irlanda Do Norte')
    for pais in Pais.objects.filter(sigla='ANT', nome='Estados Assoc. Das Antilhas'):
        if any(rel.related_model._base_manager.filter(**{rel.field.name: pais}).exists() for rel in Pais._meta.related_objects):
            sys.stdout.write(f'\nedu.Pais {pais.pk} "{pais.nome}" (ANT) mantido: há registros que o referenciam.\n')
        else:
            pais.delete()


class Migration(migrations.Migration):
    dependencies = [
        ('edu', '0331_merge_20261017_0619'),
    ]

    operations = [
        migrations.RunPython(corrigir, migrations.RunPython.noop),
    ]
