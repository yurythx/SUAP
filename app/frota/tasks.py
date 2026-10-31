from django.db.models import F

from djtools.assincrono import task
from djtools.templatetags.filters import format_
from djtools.utils import XlsResponse
from frota.models import Viagem


@task('Exportar Viagens por Viatura para XLS')
def viagens_por_viatura_to_xls(viaturas, motorista_form, data_inicio, data_termino, task=None):
    rows = [
        [
            '#',
            'Viatura',
            'Saída',
            'Chegada',
            'Motoristas',
            'Passageiros',
            'Objetivo',
            'Quilometragem Inicial',
            'Quilometragem Final',
            'Descontinuidade',
            'Distância Percorrida',
        ]
    ]
    contador = 1
    for viatura in task.iterate(viaturas):
        viagens_totais = (
            Viagem.objects.exclude(chegada_odometro=None)
            .filter(saida_data__gt=data_inicio, saida_data__lt=data_termino, viatura=viatura)
            .order_by('saida_data')
        )
        if motorista_form:
            viagens_totais = viagens_totais.filter(motoristas=motorista_form)
        viagens = viagens_totais.values(
            'chegada_odometro',
            'agendamento_resposta__agendamento__objetivo',
            'chegada_data',
            'saida_odometro',
            'saida_data',
            'agendamento_resposta__agendamento__vinculo_solicitante__pessoa__nome',
            'id',
            'viatura_id',
        ).annotate(distancia=F('chegada_odometro') - F('saida_odometro'))
        count = 0

        for viagem in viagens:
            viagem_obj = viagens_totais.filter(id=viagem['id'])[0]
            qtd_passageiros = viagem_obj.vinculos_passageiros.count()
            viagem['qtd_passageiros'] = qtd_passageiros
            viagem['passageiros_xls'] = viagem_obj.get_lista_passageiros_xls()
            viagem['motoristas'] = viagem_obj.get_motoristas()
            if count < len(viagens) - 1 and viagem_obj.tem_descontinuidade():
                viagens[count]['descontinuidade'] = viagens[count + 1]['saida_odometro'] - viagens[count]['chegada_odometro']
            else:
                viagens[count]['descontinuidade'] = 0
            count += 1
            row = [
                contador,
                format_(viatura),
                format_(viagem['saida_data']),
                format_(viagem['chegada_data']),
                format_(viagem['motoristas']),
                format_(viagem['passageiros_xls']),
                format_(viagem['agendamento_resposta__agendamento__objetivo']),
                format_(viagem['saida_odometro']),
                format_(viagem['chegada_odometro']),
                format_(viagem['descontinuidade']),
                format_(viagem['distancia']),
            ]
            rows.append(row)
            contador += 1
    return XlsResponse(rows, processo=task)
