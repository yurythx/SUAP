import django.db.models.deletion
import djtools.db.models
import djtools.middleware.threadlocals
from django.conf import settings
from django.db import migrations, models
import datetime


def migrar_avaliacoes_e_periodo_submissao(apps, schema_editor):
    Submissao = apps.get_model('eventos', 'Submissao')
    VersaoSubmissao = apps.get_model('eventos', 'VersaoSubmissao')
    AvaliacaoSubmissao = apps.get_model('eventos', 'AvaliacaoSubmissao')
    Configuracao = apps.get_model('eventos', 'Configuracao')
    FluxoSubmissao = apps.get_model('eventos', 'FluxoSubmissao')
    Evento = apps.get_model('eventos', 'Evento')

    print('\n[INFO] Iniciando migração da versão de submissão...\n')
    for submissao in Submissao.objects.all():
        versao = VersaoSubmissao.objects.create(
            submissao=submissao,
            numero=1,
            enviado_em=getattr(submissao, 'data_hora', None),
            arquivo=getattr(submissao, 'arquivo', None),
            texto=getattr(submissao, 'texto', None),
        )
        print(f'[OK] Criado versao {versao.pk}')
        AvaliacaoSubmissao.objects.filter(submissao=submissao).update(versao=versao)

    print('\n[INFO] Iniciando migração dos períodos de submissão e avaliação...\n')
    total_configs = 0
    total_periodos = 0
    for config in Configuracao.objects.all():
        total_configs += 1
        evento = Evento.objects.filter(configuracao_id=config.pk).first()
        if not evento:
            print(f'[WARN] Evento não encontrado para Configuração ID {config.pk}')
            continue

        data_sub_inicio = getattr(config, 'submissao_data_inicio', None)
        data_sub_fim = getattr(config, 'submissao_data_fim', None)
        data_ava_inicio = getattr(config, 'avaliacao_data_inicio', None)
        data_ava_fim = getattr(config, 'avaliacao_data_fim', None)

        if data_sub_inicio and data_sub_fim:
            FluxoSubmissao.objects.create(
                evento=evento,
                etapa='SUB',
                data_inicio=data_sub_inicio,
                data_fim=data_sub_fim,
            )
            total_periodos += 1
            print(f'[OK] Criado período SUB para Evento {evento.pk}: {data_sub_inicio} → {data_sub_fim}')

        if data_ava_inicio and data_ava_fim:
            FluxoSubmissao.objects.create(
                evento=evento,
                etapa='AVA',
                data_inicio=data_ava_inicio,
                data_fim=data_ava_fim,
            )
            total_periodos += 1
            print(f'[OK] Criado período AVA para Evento {evento.pk}: {data_ava_inicio} → {data_ava_fim}')

            data_ref_inicio = data_ava_fim + datetime.timedelta(days=1)
            FluxoSubmissao.objects.create(
                evento=evento,
                etapa='REF',
                data_inicio=data_ref_inicio,
            )
            total_periodos += 1
            print(f'[OK] Criado período REF para Evento {evento.pk}: {data_ref_inicio}')

    print(f'\n[INFO] Processadas {total_configs} configurações.')
    print(f'[INFO] Total de períodos criados: {total_periodos}\n')


def definir_primeiro_autor_como_correspondente(apps, schema_editor):
    Submissao = apps.get_model("eventos", "Submissao")
    AutorSubmissao = apps.get_model("eventos", "AutorSubmissao")

    for submissao in Submissao.objects.all():
        primeiro_autor = (
            AutorSubmissao.objects.filter(submissao=submissao)
            .order_by("id")
            .first()
        )
        if primeiro_autor:
            primeiro_autor.autor_correspondente = True
            primeiro_autor.save()


class Migration(migrations.Migration):

    dependencies = [
        ("eventos", "0070_alter_tipoparticipacao_modelo_certificado_padrao_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="avaliacaosubmissao",
            options={
                "ordering": ("versao", "avaliador_modalidade"),
                "verbose_name": "Avaliação da submissão",
                "verbose_name_plural": "Avaliações da submissão",
            },
        ),
        migrations.AlterUniqueTogether(
            name="avaliacaosubmissao",
            unique_together=set(),
        ),
        migrations.AddField(
            model_name="autorsubmissao",
            name="autor_correspondente",
            field=models.BooleanField(
                default=False,
                help_text="Marque este campo caso o autor seja o responsável pela comunicação com os avaliadores.",
                verbose_name="Autor correspondente",
            ),
        ),
        migrations.AddField(
            model_name="avaliacaosubmissao",
            name="recomendacao",
            field=models.SmallIntegerField(
                blank=True,
                choices=[(0, "Solicitar correções"), (1, "Aceitar"), (-1, "Rejeitar")],
                help_text="Recomendação final do avaliador com base na análise dos critérios.",
                null=True,
                verbose_name="Recomendação",
            ),
        ),
        migrations.AddField(
            model_name="submissao",
            name="situacao",
            field=djtools.db.models.CharFieldPlus(
                choices=[
                    ("SUB", "Submetido"),
                    ("EAV", "Em avaliação"),
                    ("COR", "Correções solicitadas"),
                    ("RES", "Ressubmetido"),
                    ("AAP", "Aguardando avaliação presencial"),
                    ("AVA", "Avaliado"),
                ],
                default="SUB",
                max_length=5,
                verbose_name="Situação da submissão",
            ),
        ),
        migrations.CreateModel(
            name="FluxoSubmissao",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "etapa",
                    djtools.db.models.CharFieldPlus(
                        choices=[
                            ("SUB", "Submissão"),
                            ("AVA", "Avaliação"),
                            ("COR", "Correções"),
                            ("REA", "Reavaliação"),
                            ("AVP", "Avaliação presencial"),
                            ("REF", "Resultado final"),
                        ],
                        default="SUB",
                        max_length=3,
                        verbose_name="Etapa do período",
                    ),
                ),
                (
                    "data_inicio",
                    djtools.db.models.DateFieldPlus(verbose_name="Data inicial"),
                ),
                (
                    "data_fim",
                    djtools.db.models.DateFieldPlus(
                        blank=True, null=True, verbose_name="Data final"
                    ),
                ),
                (
                    "ultima_atualizacao_em",
                    djtools.db.models.DateTimeFieldPlus(auto_now=True, null=True),
                ),
                (
                    "evento",
                    djtools.db.models.ForeignKeyPlus(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="fluxos_submissao",
                        to="eventos.evento",
                    ),
                ),
                (
                    "ultima_atualizacao_por",
                    djtools.db.models.CurrentUserField(
                        blank=True,
                        default=djtools.middleware.threadlocals.get_user,
                        editable=False,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Fluxo de submissão",
                "verbose_name_plural": "Fluxos de submissão",
                "ordering": ("data_inicio", "data_fim"),
            },
        ),
        migrations.CreateModel(
            name="VersaoSubmissao",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "numero",
                    models.PositiveSmallIntegerField(verbose_name="Número da versão"),
                ),
                (
                    "arquivo",
                    djtools.db.models.FileFieldPlus(
                        blank=True,
                        null=True,
                        upload_to="eventos/submissao/versoes/",
                        verbose_name="Arquivo",
                    ),
                ),
                (
                    "texto",
                    models.TextField(blank=True, null=True, verbose_name="Texto"),
                ),
                (
                    "comentario",
                    models.TextField(
                        blank=True, null=True, verbose_name="Comentário do autor"
                    ),
                ),
                (
                    "enviado_em",
                    djtools.db.models.DateTimeFieldPlus(
                        auto_now_add=True, verbose_name="Data de envio"
                    ),
                ),
                (
                    "submissao",
                    djtools.db.models.ForeignKeyPlus(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="versoes",
                        to="eventos.submissao",
                    ),
                ),
            ],
            options={
                "verbose_name": "Versão da submissão",
                "verbose_name_plural": "Versões da submissão",
                "ordering": ("submissao", "-numero"),
            },
        ),
        migrations.AddField(
            model_name="avaliacaosubmissao",
            name="versao",
            field=djtools.db.models.ForeignKeyPlus(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="pareceres",
                to="eventos.versaosubmissao",
            ),
        ),
        migrations.AddField(
            model_name="tipomodalidade",
            name="evento",
            field=djtools.db.models.ForeignKeyPlus(
                blank=True,
                help_text="Ao informar um evento, o tipo de modalidade ficará disponível apenas para este evento",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="tipos_modalidade",
                to="eventos.evento",
                verbose_name="Evento",
            ),
        ),
        migrations.AddField(
            model_name="versaosubmissao",
            name="etiqueta",
            field=models.CharField(
                blank=True, max_length=100, null=True, verbose_name="Etiqueta da versão"
            ),
        ),
        migrations.CreateModel(
            name="LogProcessamentoSubmissao",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "mensagem",
                    models.TextField(
                        help_text="Mensagem de log do processamento da submissão",
                        verbose_name="Mensagem",
                    ),
                ),
                ("data_hora", models.DateTimeField(auto_now_add=True)),
                (
                    "evento",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to="eventos.evento"
                    ),
                ),
                (
                    "executado_por",
                    djtools.db.models.ForeignKeyPlus(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Executado Por",
                    ),
                ),
                (
                    "fluxo_submissao",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="eventos.fluxosubmissao",
                    ),
                ),
            ],
            options={
                "verbose_name": "Log de Processamento de Submissão",
                "verbose_name_plural": "Logs de Processamento de Submissão",
                "ordering": ["evento", "-data_hora"],
                "unique_together": {("evento", "fluxo_submissao", "data_hora")},
            },
        ),

        migrations.RunPython(migrar_avaliacoes_e_periodo_submissao),
        migrations.RunPython(definir_primeiro_autor_como_correspondente),
        
        migrations.RemoveField(
            model_name="avaliacaosubmissao",
            name="submissao",
        ),
        migrations.RemoveField(
            model_name="configuracao",
            name="avaliacao_data_fim",
        ),
        migrations.RemoveField(
            model_name="configuracao",
            name="avaliacao_data_inicio",
        ),
        migrations.RemoveField(
            model_name="configuracao",
            name="submissao_data_fim",
        ),
        migrations.RemoveField(
            model_name="configuracao",
            name="submissao_data_inicio",
        ),
    ]
    
