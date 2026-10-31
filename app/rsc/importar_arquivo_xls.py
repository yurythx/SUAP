import os
from decimal import Decimal

import pandas as pd
from django.conf import settings

from rsc.models import CategoriaMemorialDescritivo, Criterio, Diretriz, TipoRsc, Unidade


def importar_diretrizes():
    arquivo = os.path.join(settings.BASE_DIR, 'rsc/static/rsc/diretrizes.xls')
    df = pd.read_excel(arquivo, header=None)
    for _index, row in df.iterrows():
        tipo_rsc = TipoRsc.objects.get_or_create(nome=row.iloc[0], categoria=row.iloc[1])[0]
        Diretriz.objects.get_or_create(
            tipo_rsc=tipo_rsc,
            nome=row.iloc[2],
            descricao=row.iloc[3],
            peso=int(row.iloc[4]),
            teto=int(row.iloc[5]),
        )


def importar_unidade_criterios():
    arquivo = os.path.join(settings.BASE_DIR, 'rsc/static/rsc/unidades_criterios.xls')
    df = pd.read_excel(arquivo, header=None)
    for _index, row in df.iterrows():
        unidade = Unidade.objects.get_or_create(nome=row.iloc[6], sigla=row.iloc[6])[0]
        tipo_rsc = TipoRsc.objects.get_or_create(nome=row.iloc[0], categoria=row.iloc[1])[0]
        diretriz = Diretriz.objects.get_or_create(tipo_rsc=tipo_rsc, nome=row.iloc[2])[0]
        categoria_memorial = CategoriaMemorialDescritivo.objects.get_or_create(nome=row.iloc[8])[0]
        Criterio.objects.get_or_create(
            diretriz=diretriz,
            unidade=unidade,
            numero=int(row.iloc[3]),
            nome=row.iloc[4],
            fator=Decimal(row.iloc[5]),
            teto=int(row.iloc[7]),
            categoria_memorial_descritivo=categoria_memorial,
            status=0,
        )
