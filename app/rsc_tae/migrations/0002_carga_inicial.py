from pathlib import Path

from django.db import migrations

from djtools.db.migrations.operations.loaddata import RunLoadData

# Cópia congelada das fixtures no estado desta migração. Não usar `rsc_tae/fixtures/` nem o
# `loaddata` do manage.py aqui: ambos refletem os models ATUAIS, e numa instalação nova a
# carga quebra ao gravar colunas criadas só em migrações posteriores (ex.: `aceita_papel`, 0007).
# O `RunLoadData` usa os models históricos; a fusão do Requisito V é feita adiante pela 0008.
DADOS = Path(__file__).resolve().parent / 'dados_0002'

# Ordem de dependência para a carga:
#   requisito         → sem dependências
#   nivel             → M2M requisitos_obrigatorios (precisa dos requisitos)
#   grupo             → FK para requisito
#   saber_competencia → FK para grupo (RolSaberCompetencia)
#   configuracao      → independente (registro único de ConfiguracaoRSCTae)
FIXTURES = [
    'initial_data_requisito.json',
    'initial_data_nivel.json',
    'initial_data_grupo.json',
    'initial_data_saber_competencia.json',
    'initial_data_configuracao.json',
]


class Migration(migrations.Migration):
    dependencies = [
        ('rsc_tae', '0001_initial'),
    ]

    operations = [RunLoadData(str(DADOS / fixture)) for fixture in FIXTURES]
