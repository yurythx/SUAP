import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('comum', '0117_merge_20260731_1759'),
    ]

    operations = [
        migrations.AddField(
            model_name='vinculo',
            name='uuid',
            field=models.UUIDField(null=True, unique=True),
        ),
        # ponytail: um UPDATE só; RunPython linha a linha (precedente rh/0016) levaria minutos nesta tabela.
        migrations.RunSQL(
            sql='UPDATE comum_vinculo SET uuid = gen_random_uuid() WHERE uuid IS NULL',
            reverse_sql=migrations.RunSQL.noop,
            elidable=True,
        ),
        migrations.AlterField(
            model_name='vinculo',
            name='uuid',
            field=models.UUIDField(default=uuid.uuid4, unique=True),
        ),
    ]
