from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('eventos', '0083_merge_20260302_1110'),
    ]

    operations = [
        migrations.AddField(
            model_name='evento',
            name='exigir_avaliacao_para_certificado',
            field=models.BooleanField(
                default=False,
                help_text='Marque essa opção caso deseje condicionar a emissão do certificado ao preenchimento da avaliação pós-evento.',
                verbose_name='Exigir avaliação para certificado?',
            ),
        ),
    ]
