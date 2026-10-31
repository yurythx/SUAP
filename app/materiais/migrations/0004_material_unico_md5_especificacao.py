import django.db.models.functions.text
from django.db import migrations, models


class Migration(migrations.Migration):
    """Troca a unicidade do Material por uma com md5 da especificacao (#17730).

    A UNIQUE por colunas não cabe no btree quando a especificacao passa de ~2,7 kB. O banco do IFRN
    tinha, no lugar dela, um índice legado sobre o md5 da concatenação, que este substitui. O nome
    da UNIQUE do Django é o que bancos criados por migrations (e a comum 0122, quando coube) têm.
    """

    dependencies = [
        ('materiais', '0003_auto_20210301_1709'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    'ALTER TABLE materiais_material DROP CONSTRAINT IF EXISTS materiais_material_categoria_id_descricao_e_35611a16_uniq',
                    migrations.RunSQL.noop,
                ),
                # Legado do IFRN: UNIQUE (md5(categoria_id || descricao || especificacao || unidade_medida_id))
                migrations.RunSQL('DROP INDEX IF EXISTS materiais_material_categoria_id_key', migrations.RunSQL.noop),
            ],
            state_operations=[
                migrations.AlterUniqueTogether(name='material', unique_together=set()),
            ],
        ),
        migrations.AddConstraint(
            model_name='material',
            constraint=models.UniqueConstraint(
                models.F('categoria'),
                models.F('descricao'),
                django.db.models.functions.text.MD5('especificacao'),
                models.F('unidade_medida'),
                name='materiais_material_unico',
                violation_error_message='Já existe material com esta categoria, descrição, especificação e unidade de medida.',
            ),
        ),
    ]
