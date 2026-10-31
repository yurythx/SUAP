from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('demandas', '0044_decisaoespecificacao'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='ambientehomologacao',
            name='usuarios',
        ),
        migrations.AlterField(
            model_name='demanda',
            name='id_merge_request',
            field=models.PositiveIntegerField(
                blank=True,
                help_text='Identificador do Merge-request. Exemplo: na url https://gitlab.com/suap/-/merge_requests/25 o número 25 é o identificador.',
                null=True,
                verbose_name='ID do Merge-Request',
            ),
        ),
    ]
