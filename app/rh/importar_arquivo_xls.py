import os

import pandas as pd
from django.conf import settings

from rh.models import PadraoVencimento


def importar_dados_progressoes():
    arquivo_padrao_vencimento = os.path.join(settings.BASE_DIR, 'progressoes/static/progressoes/padrao_vencimento.xlsx')
    df = pd.read_excel(arquivo_padrao_vencimento, header=None)
    for _index, row in df.iterrows():
        PadraoVencimento.objects.get_or_create(
            categoria=row.iloc[0],
            classe=row.iloc[1],
            posicao_vertical=f'{int(row.iloc[2]):02d}',
        )
