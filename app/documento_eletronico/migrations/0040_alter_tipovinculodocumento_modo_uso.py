from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('documento_eletronico', '0039_remover_assinaturadigital'),
    ]

    operations = [
        migrations.AlterField(
            model_name='tipovinculodocumento',
            name='modo_uso',
            field=models.CharField(
                choices=[('livre', 'Livre'), ('regulamentado', 'Regulamentado')],
                default='livre',
                help_text=(
                    'Livre: permite relacionar manualmente documentos de quaisquer tipos. '
                    'Regulamentado: aplica as configurações às combinações cadastradas e permite livremente as demais. '
                    'Configurações desativadas impedem a vinculação da respectiva combinação.'
                ),
                max_length=20,
                verbose_name='Modo de Uso',
            ),
        ),
    ]
