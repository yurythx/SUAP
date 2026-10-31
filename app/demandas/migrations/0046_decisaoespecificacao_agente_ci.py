import djtools.db.models.fields.string
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('demandas', '0045_remove_ambientehomologacao_usuarios_alter_demanda_id_merge_request'),
    ]

    operations = [
        migrations.AlterField(
            model_name='decisaoespecificacao',
            name='origem',
            field=djtools.db.models.fields.string.CharFieldPlus(
                choices=[('manual', 'Manual'), ('agente', 'Agente'), ('agente-ci', 'Agente CI')],
                default='manual',
                max_length=10,
                verbose_name='Origem',
            ),
        ),
    ]
