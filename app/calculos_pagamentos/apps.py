from djtools.apps import SuapAppConfig as AppConfig


class CalculosConfig(AppConfig):
    default = True
    name = 'calculos_pagamentos'
    verbose_name = 'Cálculos de Pagamento'
    description = 'Auxilia a gestão de pessoas nos mais diversos cálculos relativos à folha de pagamento. Os principais cálculos deste módulo dizem respeito a substiuição de chefia e auxílio transporte.'
    icon = 'dollar-sign'
    area = 'Gestão de Pessoas'
