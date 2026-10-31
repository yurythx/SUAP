import django.db.models.fields.json
from django.db import migrations, models


class Migration(migrations.Migration):
    """Traz o índice do e-mail do respondente para o model (`Meta.indexes`).

    O índice já existe no banco desde a 0009, criado por `RunSQL` — invisível para o autodetector e,
    portanto, ausente em bancos montados a partir dos models (`create_db`). Aqui ele só é renomeado
    (metadata, sem recriar) para caber no limite de 30 caracteres do Django e passa a ser declarado.
    """

    dependencies = [
        ('avaliacao_integrada', '0012_alter_avaliacao_options_alter_indicador_options_and_more'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql='ALTER INDEX IF EXISTS idx_dados_usuario_externo_email RENAME TO idx_respondente_email;',
                    reverse_sql='ALTER INDEX IF EXISTS idx_respondente_email RENAME TO idx_dados_usuario_externo_email;',
                ),
            ],
            state_operations=[
                migrations.AddIndex(
                    model_name='respondente',
                    index=models.Index(
                        django.db.models.fields.json.KeyTextTransform('email', 'dados_usuario_externo'),
                        name='idx_respondente_email',
                    ),
                ),
            ],
        ),
    ]
