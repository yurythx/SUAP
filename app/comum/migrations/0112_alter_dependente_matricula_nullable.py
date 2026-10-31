from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("comum", "0111_auto_20260311_1557"),
    ]

    operations = [
        migrations.AlterField(
            model_name="dependente",
            name="matricula",
            field=models.CharField(max_length=8, unique=True, null=True, blank=True),
        ),
    ]
