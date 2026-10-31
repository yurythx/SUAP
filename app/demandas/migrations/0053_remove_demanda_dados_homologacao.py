# Ambiente, URL e senha de homologação passam a viver só na Entrega
# (docs/specs/2026-10-21-demandas-fluxo-entrega-homologacao.md). A 0052 já copiou para
# uma entrega pendente os dados das demandas que estavam "Em homologação".
#
# Os campos saem só do state: as colunas `ambiente_homologacao_id`, `url_validacao` e
# `senha_homologacao` continuam em `demandas_demanda`, sem uso pelo Django e legíveis só por SQL.
# Isso preserva o histórico das demandas encerradas e evita que os slaves, ainda no código
# antigo durante o deploy, quebrem ao selecionar colunas que não existem mais. A única
# mudança no banco é a queda da constraint de FK: sem o campo no state o Django não faz mais
# o SET_NULL, e apagar um AmbienteHomologacao ainda citado por uma demanda antiga daria
# IntegrityError. Dropar as colunas, se um dia for o caso, é decisão de outra release.

import django.db.models.deletion
from django.db import migrations

import djtools.db.models


class Migration(migrations.Migration):

    dependencies = [
        ("demandas", "0052_reconciliar_etapa_com_entrega_pendente"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(model_name="demanda", name="ambiente_homologacao"),
                migrations.RemoveField(model_name="demanda", name="senha_homologacao"),
                migrations.RemoveField(model_name="demanda", name="url_validacao"),
            ],
            database_operations=[
                migrations.AlterField(
                    model_name="demanda",
                    name="ambiente_homologacao",
                    field=djtools.db.models.ForeignKeyPlus(
                        blank=True,
                        null=True,
                        db_constraint=False,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="demandas.ambientehomologacao",
                        verbose_name="Ambiente de Homologação",
                    ),
                ),
            ],
        ),
    ]
