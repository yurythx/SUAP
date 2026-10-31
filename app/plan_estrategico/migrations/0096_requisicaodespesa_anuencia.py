import django.db.models.deletion
import djtools.db.models.fields.datetimeplus
import djtools.db.models.fields.foreignkey
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("comum", "0125_auth_user_username_upper"),
        ("plan_estrategico", "0095_ajusta_rotulos_variavelcampus"),
        ("rh", "0111_documento_pessoa_unico"),
    ]

    operations = [
        migrations.RenameField(
            model_name="unidadegestora",
            old_name="setor_gabinete",
            new_name="setor_ordenador_despesa",
        ),
        migrations.AlterField(
            model_name="unidadegestora",
            name="setor_ordenador_despesa",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="unidadegestora_setor_ordenador_despesa",
                to="rh.setor",
                verbose_name="Setor responsável ordenador de despesa",
            ),
        ),
        migrations.AddField(
            model_name="unidadegestora",
            name="setor_anuencia_despesa",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="unidadegestora_setor_anuencia_despesa",
                to="rh.setor",
                verbose_name="Setor Anuência da Despesa",
            ),
        ),
        migrations.AddField(
            model_name="unidadegestora",
            name="ug_secundaria",
            field=models.CharField(
                blank=True, max_length=6, verbose_name="UG Secundária"
            ),
        ),
        migrations.AddField(
            model_name="requisicaodespesa",
            name="ua_vinculada",
            field=models.PositiveSmallIntegerField(
                choices=[(1, "UA Principal"), (2, "UA Secundária")],
                default=1,
                verbose_name="Despesa vinculada à",
            ),
        ),
        migrations.AddField(
            model_name="requisicaodespesa",
            name="data_anuencia",
            field=djtools.db.models.fields.datetimeplus.DateTimeFieldPlus(
                null=True, verbose_name="Data de anuência da despesa"
            ),
        ),
        migrations.AddField(
            model_name="requisicaodespesa",
            name="despacho_anuencia",
            field=models.TextField(
                blank=True, null=True, verbose_name="Despacho de anuência da despesa"
            ),
        ),
        migrations.AddField(
            model_name="requisicaodespesa",
            name="vinculo_anuencia",
            field=djtools.db.models.fields.foreignkey.ForeignKeyPlus(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="vinculo_anuencia_despesa",
                to="comum.vinculo",
                verbose_name="Anuente da despesa",
            ),
        ),
        migrations.AlterField(
            model_name="requisicaodespesa",
            name="status",
            field=models.PositiveIntegerField(
                choices=[
                    (1, "Cadastrada"),
                    (2, "Aguardando emissão do CDO"),
                    (3, "Aguardando validação do SIAFI"),
                    (11, "Aguardando anuência de despesa"),
                    (4, "Aguardando autorização de despesa"),
                    (5, "Despesa Autorizada"),
                    (6, "Aguardando processo licitatório"),
                    (7, "Aguardando emissão de empenho"),
                    (8, "Cancelada"),
                    (9, "Requisição com inconsistências"),
                    (10, "Concluída"),
                ],
                default=2,
                verbose_name="Situação",
            ),
        ),
        migrations.AlterField(
            model_name="requisicaodespesahistorico",
            name="status",
            field=models.PositiveIntegerField(
                choices=[
                    (1, "Cadastrada"),
                    (2, "Aguardando emissão do CDO"),
                    (3, "Aguardando validação do SIAFI"),
                    (11, "Aguardando anuência de despesa"),
                    (4, "Aguardando autorização de despesa"),
                    (5, "Despesa Autorizada"),
                    (6, "Aguardando processo licitatório"),
                    (7, "Aguardando emissão de empenho"),
                    (8, "Cancelada"),
                    (9, "Requisição com inconsistências"),
                    (10, "Concluída"),
                ]
            ),
        ),
    ]
