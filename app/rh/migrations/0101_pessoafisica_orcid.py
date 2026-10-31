from django.db import migrations

import djtools.db.models


class Migration(migrations.Migration):
    dependencies = [
        ('rh', '0100_expandir_reativacao_temporaria_servidor'),
    ]

    operations = [
        migrations.AddField(
            model_name='pessoafisica',
            name='orcid',
            field=djtools.db.models.URLField(blank=True, verbose_name='ORCID'),
        ),
    ]
