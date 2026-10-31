from contracheques.models import ContraChequeRubrica, Rubrica, ContraCheque
from comum.models import Vinculo


def get_vinculos_servidores_com_aux_transporte_com_frequencia(ano, mes):
    def get_nao_efetivos():
        rubrica = Rubrica.objects.usadas_no_if().filter(codigo='82850').first()  # id=28394
        queryset = ContraChequeRubrica.objects.filter(
            contra_cheque__excluido=False,
            contra_cheque__tipo_importacao=ContraCheque.IMPORTACAO_FITA_ESPELHO,
            contra_cheque__mes=mes,
            contra_cheque__ano__ano=ano,
            rubrica=rubrica,
        )
        queryset = queryset.filter(tipo__nome='Rendimento')
        queryset = queryset.filter(sequencia__in=[0, 1])
        queryset = queryset.filter(contra_cheque__servidor__ativo=True)
        queryset = queryset.select_related(
            'contra_cheque__servidor',
        )

        return queryset

    def get_efetivos():
        # substituir pelo codigo? e juntar os metodos
        # OU colocar em configuracao (para todas as caracteristas)?
        rubrica = Rubrica.objects.usadas_no_if().filter(codigo='00951').first()  # id=28019
        queryset = ContraChequeRubrica.objects.filter(
            contra_cheque__excluido=False,
            contra_cheque__tipo_importacao=ContraCheque.IMPORTACAO_FITA_ESPELHO,
            contra_cheque__mes=mes,
            contra_cheque__ano__ano=ano,
            rubrica=rubrica,
        )
        queryset = queryset.filter(tipo__nome='Rendimento')
        queryset = queryset.filter(sequencia__in=[0])
        queryset = queryset.filter(contra_cheque__servidor__ativo=True)
        queryset = queryset.select_related(
            'contra_cheque__servidor',
        )

        return queryset

    servidores_com_aux_transporte = get_nao_efetivos() | get_efetivos()
    vinculos_com_aux_transporte = Vinculo.objects.ativos().filter(
        tipo_relacionamento__model='servidor', user__username__in=servidores_com_aux_transporte.values('contra_cheque__servidor__matricula')
    )

    return vinculos_com_aux_transporte
