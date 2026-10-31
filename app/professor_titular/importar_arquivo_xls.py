import os
from decimal import Decimal

import pandas as pd
from django.conf import settings

from professor_titular.models import CategoriaMemorialDescritivo, Criterio, Grupo, Indicador, PontuacaoMinima, Unidade


def importar_dados_titular():
    arquivo_grupo = os.path.join(settings.BASE_DIR, 'professor_titular/static/titular/grupo_titular.xlsx')
    df_grupo = pd.read_excel(arquivo_grupo, header=None)
    for _index, row in df_grupo.iterrows():
        Grupo.objects.get_or_create(nome=row.iloc[0], percentual=Decimal(row.iloc[1]))

    arquivo_memorial = os.path.join(settings.BASE_DIR, 'professor_titular/static/titular/memorial_descritivo_titular.xlsx')
    df_memorial = pd.read_excel(arquivo_memorial, header=None)
    for _index, row in df_memorial.iterrows():
        CategoriaMemorialDescritivo.objects.get_or_create(nome=row.iloc[1], indice=row.iloc[0])

    arquivo_pontuacao_minima = os.path.join(settings.BASE_DIR, 'professor_titular/static/titular/pontuacao_minima_titular_por_ano.xlsx')
    df_pontuacao = pd.read_excel(arquivo_pontuacao_minima, header=None)
    for _index, row in df_pontuacao.iterrows():
        for grupo_banco in Grupo.objects.all():
            PontuacaoMinima.objects.get_or_create(
                grupo=grupo_banco,
                ano=row.iloc[0],
                pontuacao_exigida=Decimal(row.iloc[1]),
                qtd_minima_grupos=row.iloc[2],
            )

    arquivo_indicador_criterios_titular = os.path.join(settings.BASE_DIR, 'professor_titular/static/titular/indicador_criterios_titular.xlsx')
    df_indicador = pd.read_excel(arquivo_indicador_criterios_titular, header=None)
    for _index, row in df_indicador.iterrows():
        unidade = Unidade.objects.get_or_create(nome=row.iloc[6], sigla=row.iloc[6])[0]
        grupo = Grupo.objects.get_or_create(nome=row.iloc[0])[0]
        item_memorial = CategoriaMemorialDescritivo.objects.get_or_create(indice=row.iloc[1])[0]
        indicador = Indicador.objects.get_or_create(grupo=grupo, nome=row.iloc[2], descricao=row.iloc[3])[0]
        Criterio.objects.get_or_create(
            indicador=indicador,
            artigo=row.iloc[4],
            nome=row.iloc[5],
            status=0,
            pontos=Decimal(row.iloc[7]),
            unidade=unidade,
            categoria_memorial_descritivo=item_memorial,
        )
