from django.conf import settings
from django.db import migrations
import django.db.models.deletion
import djtools.db.models


def marcar_reativacoes_temporarias_existentes_como_autorizadas(apps, schema_editor):
    ServidorReativacaoTemporaria = apps.get_model('rh', 'ServidorReativacaoTemporaria')
    ServidorReativacaoTemporaria.objects.all().update(situacao='autorizada')


def desfazer_status_reativacoes_temporarias(apps, schema_editor):
    ServidorReativacaoTemporaria = apps.get_model('rh', 'ServidorReativacaoTemporaria')
    ServidorReativacaoTemporaria.objects.all().update(situacao='solicitada')


class Migration(migrations.Migration):
    dependencies = [
        ('rh', '0099_pessoa_pessoa_nome_d9e804_unac_btree_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='servidorreativacaotemporaria',
            name='justificativa',
            field=djtools.db.models.TextField(default='', verbose_name='Justificativa'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='servidorreativacaotemporaria',
            name='cadastrado_por',
            field=djtools.db.models.ForeignKeyPlus(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='reativacoes_temporarias_cadastradas',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Cadastrado Por',
            ),
        ),
        migrations.AddField(
            model_name='servidorreativacaotemporaria',
            name='data_cadastro',
            field=djtools.db.models.DateTimeFieldPlus(auto_now_add=True, null=True, verbose_name='Data de Cadastro'),
        ),
        migrations.AddField(
            model_name='servidorreativacaotemporaria',
            name='situacao',
            field=djtools.db.models.CharField(
                choices=[
                    ('solicitada', 'Solicitada'),
                    ('autorizada', 'Autorizada'),
                    ('negada', 'Não autorizada'),
                ],
                default='solicitada',
                max_length=20,
                verbose_name='Status',
            ),
        ),
        migrations.AddField(
            model_name='servidorreativacaotemporaria',
            name='autorizador',
            field=djtools.db.models.ForeignKeyPlus(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='reativacoes_temporarias_autorizadas',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Autorizador',
            ),
        ),
        migrations.AddField(
            model_name='servidorreativacaotemporaria',
            name='data_autorizacao',
            field=djtools.db.models.DateTimeFieldPlus(blank=True, null=True, verbose_name='Data da Autorização'),
        ),
        migrations.AlterModelOptions(
            name='servidorreativacaotemporaria',
            options={
                'ordering': ('-data_inicio', '-pk'),
                'verbose_name': 'Reativação Temporária de Servidor',
                'verbose_name_plural': 'Reativações Temporárias dos Servidores',
            },
        ),
        migrations.RunPython(
            marcar_reativacoes_temporarias_existentes_como_autorizadas,
            desfazer_status_reativacoes_temporarias,
        ),
        migrations.CreateModel(
            name='ServidorReativacaoPermanente',
            fields=[
                ('id', djtools.db.models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('justificativa', djtools.db.models.TextField(verbose_name='Justificativa')),
                ('data_cadastro', djtools.db.models.DateTimeFieldPlus(auto_now_add=True, null=True, verbose_name='Data de Cadastro')),
                (
                    'situacao',
                    djtools.db.models.CharField(
                        choices=[
                            ('solicitada', 'Solicitada'),
                            ('autorizada', 'Autorizada'),
                            ('negada', 'Não autorizada'),
                        ],
                        default='solicitada',
                        max_length=20,
                        verbose_name='Status',
                    ),
                ),
                ('data_autorizacao', djtools.db.models.DateTimeFieldPlus(blank=True, null=True, verbose_name='Data da Autorização')),
                ('ocorrencia_removida', djtools.db.models.BooleanField(default=False, verbose_name='Ocorrência removida?')),
                ('ocorrencia_codigo', djtools.db.models.CharField(blank=True, max_length=10, null=True, verbose_name='Código da Ocorrência Removida')),
                ('ocorrencia_nome', djtools.db.models.CharField(blank=True, max_length=255, null=True, verbose_name='Ocorrência Removida')),
                ('ocorrencia_data', djtools.db.models.DateField(blank=True, null=True, verbose_name='Data da Ocorrência')),
                ('ocorrencia_data_termino', djtools.db.models.DateField(blank=True, null=True, verbose_name='Data de Término da Ocorrência')),
                ('subgrupo_descricao', djtools.db.models.CharField(blank=True, max_length=255, null=True, verbose_name='Subgrupo')),
                ('diploma_legal_num', djtools.db.models.CharField(blank=True, max_length=10, null=True, verbose_name='Número do Diploma Legal')),
                ('diploma_legal_data', djtools.db.models.DateField(blank=True, null=True, verbose_name='Data do Diploma Legal')),
                (
                    'autorizador',
                    djtools.db.models.ForeignKeyPlus(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='reativacoes_permanentes_autorizadas',
                        to=settings.AUTH_USER_MODEL,
                        verbose_name='Autorizador',
                    ),
                ),
                (
                    'cadastrado_por',
                    djtools.db.models.ForeignKeyPlus(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='reativacoes_permanentes_cadastradas',
                        to=settings.AUTH_USER_MODEL,
                        verbose_name='Cadastrado Por',
                    ),
                ),
                ('servidor', djtools.db.models.ForeignKeyPlus(on_delete=django.db.models.deletion.CASCADE, to='rh.servidor', verbose_name='Servidor')),
            ],
            options={
                'verbose_name': 'Reativação Permanente de Servidor',
                'verbose_name_plural': 'Reativações Permanentes dos Servidores',
                'ordering': ('-data_cadastro', '-pk'),
            },
        ),
    ]
