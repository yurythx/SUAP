import django.db.models.deletion
import djtools.db.models.fields.foreignkey
import djtools.db.models.fields.string
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('demandas', '0043_merge_0042'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='DecisaoEspecificacao',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('criado_em', models.DateTimeField(auto_now_add=True, verbose_name='Criado em')),
                ('decisao', models.TextField(verbose_name='Decisão')),
                ('contexto', models.JSONField(blank=True, default=dict, verbose_name='Contexto')),
                (
                    'origem',
                    djtools.db.models.fields.string.CharFieldPlus(
                        choices=[('manual', 'Manual'), ('agente', 'Agente')], default='manual', max_length=10, verbose_name='Origem'
                    ),
                ),
                (
                    'autor',
                    djtools.db.models.fields.foreignkey.ForeignKeyPlus(
                        on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL, verbose_name='Autor'
                    ),
                ),
                (
                    'demanda',
                    djtools.db.models.fields.foreignkey.ForeignKeyPlus(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='decisoes_especificacao',
                        to='demandas.demanda',
                        verbose_name='Demanda',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Decisão de Especificação',
                'verbose_name_plural': 'Decisões de Especificação',
                'ordering': ['criado_em'],
            },
        ),
    ]
