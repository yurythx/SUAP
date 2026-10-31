"""Converte ``DeliberacaoLAI`` em linha do tempo de eventos do ciclo LAI.

As deliberações já registradas viram eventos: ``decisao`` (LIBERADO/DEVOLVIDO) é traduzida para
``tipo`` (LIBERACAO/DEVOLUCAO) antes de o campo ser removido, de modo que nenhum histórico se
perde. Os renomeios acompanham a mudança de sentido do model — ``deliberado_por`` não descreve
quem reenviou um dataset após ajustes.
"""

import django.db.models.deletion
import djtools.db.models.fields.datetimeplus
import djtools.db.models.fields.foreignkey
from django.db import migrations, models

# Valores literais: migração não deve depender dos enums, que podem mudar depois dela.
DECISAO_LIBERADO = 3
DECISAO_DEVOLVIDO = 4
TIPO_LIBERACAO = 2
TIPO_DEVOLUCAO = 3


def decisao_para_tipo(apps, schema_editor):
    DeliberacaoLAI = apps.get_model('dados_abertos', 'DeliberacaoLAI')
    DeliberacaoLAI.objects.filter(decisao=DECISAO_LIBERADO).update(tipo=TIPO_LIBERACAO)
    DeliberacaoLAI.objects.filter(decisao=DECISAO_DEVOLVIDO).update(tipo=TIPO_DEVOLUCAO)


def tipo_para_decisao(apps, schema_editor):
    DeliberacaoLAI = apps.get_model('dados_abertos', 'DeliberacaoLAI')
    DeliberacaoLAI.objects.filter(tipo=TIPO_LIBERACAO).update(decisao=DECISAO_LIBERADO)
    DeliberacaoLAI.objects.filter(tipo=TIPO_DEVOLUCAO).update(decisao=DECISAO_DEVOLVIDO)


class Migration(migrations.Migration):
    dependencies = [
        ('comum', '0119_municipio_codigo_ibge'),
        ('dados_abertos', '0021_etapa_pulavel_pdaetapa'),
    ]

    operations = [
        migrations.AddField(
            model_name='deliberacaolai',
            name='tipo',
            field=models.IntegerField(
                choices=[
                    (1, 'Enviado para análise'),
                    (2, 'Liberado pelo Responsável LAI'),
                    (3, 'Devolvido para ajustes'),
                    (4, 'Reenviado após ajustes'),
                    (5, 'Reaberto por edição do conteúdo'),
                ],
                default=TIPO_LIBERACAO,
                verbose_name='Evento',
            ),
            preserve_default=False,
        ),
        migrations.RunPython(decisao_para_tipo, tipo_para_decisao),
        migrations.RemoveField(model_name='deliberacaolai', name='decisao'),
        migrations.RenameField(model_name='deliberacaolai', old_name='parecer', new_name='texto'),
        migrations.RenameField(model_name='deliberacaolai', old_name='deliberado_por', new_name='autor'),
        migrations.RenameField(model_name='deliberacaolai', old_name='data_deliberacao', new_name='data'),
        migrations.AlterField(
            model_name='deliberacaolai',
            name='texto',
            field=models.TextField(
                blank=True,
                help_text='Parecer do Responsável LAI na devolução, ou a resposta do gestor no reenvio.',
                verbose_name='Parecer/Resposta',
            ),
        ),
        migrations.AlterField(
            model_name='deliberacaolai',
            name='autor',
            field=djtools.db.models.fields.foreignkey.ForeignKeyPlus(
                blank=True,
                help_text='Vazio nos eventos automáticos (envio pela etapa e reabertura por edição).',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to='comum.vinculo',
                verbose_name='Autor',
            ),
        ),
        migrations.AlterField(
            model_name='deliberacaolai',
            name='data',
            field=djtools.db.models.fields.datetimeplus.DateTimeFieldPlus(auto_now_add=True, verbose_name='Data'),
        ),
        migrations.AlterField(
            model_name='deliberacaolai',
            name='pda_base_dados',
            field=djtools.db.models.fields.foreignkey.ForeignKeyPlus(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='eventos_lai',
                to='dados_abertos.pdabasedados',
                verbose_name='Base de Dados no PDA',
            ),
        ),
        migrations.AlterModelOptions(
            name='deliberacaolai',
            options={
                'ordering': ('-data', '-id'),
                'permissions': [('deliberar_lai', 'Pode deliberar sobre a liberação LAI de datasets')],
                'verbose_name': 'Evento LAI',
                'verbose_name_plural': 'Eventos LAI',
            },
        ),
    ]
