import os

import pandas as pd
from django.conf import settings

from centralservicos.models import AtendimentoAtribuicao, Chamado
from djtools.management.commands import BaseCommandPlus
from djtools.templatetags.filters import format_

"""
python manage.py centralservicos_relatorios_xls
"""


class Command(BaseCommandPlus):
    def chamados_abertos(self, ano, grupos):
        atendimentos = AtendimentoAtribuicao.objects.filter(grupo_atendimento__pk__in=grupos, cancelado_em__isnull=True)
        lista = Chamado.objects.filter(aberto_em__year=ano, pk__in=atendimentos.values('chamado'))

        rows = [['#', 'Chamado', 'Atendente (Nome)', 'Atendente (Login)', 'Grupo Serviço', 'Serviço', 'Aberto Em']]
        count = 0
        for chamado in lista:
            count += 1
            atendente = chamado.get_atendente_do_chamado()
            if atendente:
                nome = atendente.get_profile().nome
                username = atendente.username
            else:
                nome = ''
                username = ''
            row = [
                count,
                format_(chamado.id),
                format_(nome),
                format_(username),
                format_(chamado.servico.grupo_servico.nome),
                format_(chamado.servico.nome),
                format_(chamado.aberto_em),
            ]
            rows.append(row)

        file_path = f'centralservicos/fixtures/chamados_abertos{ano}.xlsx'
        file_path = os.path.join(settings.BASE_DIR, file_path)
        self.stdout.write(file_path)

        # Create DataFrame
        # rows contains header as first element
        headers = rows[0]
        data = rows[1:]

        df = pd.DataFrame(data, columns=headers)

        # Save to Excel
        df.to_excel(file_path, index=False, sheet_name='planilha1')

    def handle(self, *args, **options):
        grupos = [2, 4, 10]
        self.chamados_abertos(2017, grupos)
