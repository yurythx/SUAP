from ae.models import Participacao
from djtools.management.commands import BaseCommandPlus

# 20241198060027
# 110552 Alimentação Estudantil (CANG)
# 110550 Alimentação Estudantil (CANG)
# 107422 Auxílio Transporte (CANG)
# 20232190220028
# 110254 Alimentação Estudantil (CANG)
# 108115 Alimentação Estudantil (CANG)
# 107258 Apoio à Formação Estudantil (CANG)
# 20241194010029
# 110659 Alimentação Estudantil (CANG)
# 108804 Alimentação Estudantil (CANG)
# 108803 Alimentação Estudantil (CANG)
# 20231190340042
# 107711 Alimentação Estudantil (CANG)
# 102822 Alimentação Estudantil (CANG)
# 20231194010002
# 107934 Alimentação Estudantil (CANG)
# 103885 Alimentação Estudantil (CANG)
# 20211197100017
# 110553 Alimentação Estudantil (CANG)
# 110551 Alimentação Estudantil (CANG)
# 109756 Auxílio Transporte (CANG)
# 20221194010035
# 111161 Alimentação Estudantil (CANG)
# 106358 Alimentação Estudantil (CANG)
# 20221010590024
# 109976 Alimentação Estudantil (CNAT)
# 109975 Alimentação Estudantil (CNAT)
# 83252 Auxílio Transporte (CNAT)
# 20211021010028
# 108779 Alimentação Estudantil (MO)
# 109535 Auxílio Transporte (MO)
# 104328 Alimentação Estudantil (MO)
# 20211022020014
# 108175 Alimentação Estudantil (MO)
# 108162 Alimentação Estudantil (MO)
# 20231022010023
# 110829 Alimentação Estudantil (MO)
# 110850 Alimentação Estudantil (MO)
# 20231024010002
# 109700 Alimentação Estudantil (MO)
# 110106 Apoio à Formação Estudantil (MO)
# 108376 Alimentação Estudantil (MO)
# 20211021010030
# 109363 Alimentação Estudantil (MO)
# 109386 Auxílio Transporte (MO)
# 104321 Alimentação Estudantil (MO)
# 20231020450022
# 109544 Auxílio Transporte (MO)
# 104877 Alimentação Estudantil (MO)
# 110042 Alimentação Estudantil (MO)
# 20231021010006
# 109701 Alimentação Estudantil (MO)
# 109242 Auxílio Transporte (MO)
# 108179 Alimentação Estudantil (MO)
# 20231022010004
# 109226 Alimentação Estudantil (MO)
# 109224 Alimentação Estudantil (MO)
# 109314 Auxílio Transporte (MO)
# 20221041110002
# 111200 Alimentação Estudantil (ZN)
# 111199 Alimentação Estudantil (ZN)
# 97815 Auxílio Transporte (ZN)
# 20222071060010
# 105204 Auxílio Moradia (MC)
# 105203 Auxílio Moradia (MC)
# 20212024300027
# 110423 Auxílio Transporte (MO)
# 110424 Auxílio Transporte (MO)
# 101903 Alimentação Estudantil (MO)
# 20221024010040
# 109325 Auxílio Transporte (MO)
# 109326 Auxílio Transporte (MO)
# 108513 Alimentação Estudantil (MO)
# 20211022020005
# 109045 Alimentação Estudantil (MO)
# 109347 Auxílio Transporte (MO)
# 109348 Auxílio Transporte (MO)
# 20231022010019
# 111144 Auxílio Transporte (MO)
# 109480 Auxílio Transporte (MO)
# 109547 Auxílio Transporte (MO)
# 108492 Alimentação Estudantil (MO)
# 20231024010006
# 109472 Auxílio Transporte (MO)
# 109474 Auxílio Transporte (MO)
# 108428 Alimentação Estudantil (MO)
# 20231024010036
# 108940 Alimentação Estudantil (MO)
# 109674 Auxílio Transporte (MO)
# 109634 Auxílio Transporte (MO)
# 109633 Apoio à Formação Estudantil (MO)
# 20231022010013
# 111143 Auxílio Transporte (MO)
# 109267 Auxílio Transporte (MO)
# 108426 Alimentação Estudantil (MO)


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        # 20241198060027
        participacao = Participacao.objects.get(id=110552)
        participacao.delete()

        # 20232190220028
        participacao = Participacao.objects.get(id=106602)
        participacao.data_termino = '2024-08-13'
        participacao.save()

        participacao_anterior = Participacao.objects.get(id=106536)
        participacao_anterior.data_termino = '2024-08-13'
        participacao_anterior.save()

        participacao = Participacao.objects.get(id=108115)
        participacao.data_termino = '2024-10-13'
        participacao.finalizado_por = participacao_anterior.atualizado_por
        participacao.finalizado_em = participacao_anterior.atualizado_em
        participacao.motivo_termino = 'Edição da participação.'
        participacao.save()

        # 20241194010029
        participacao = Participacao.objects.get(id=108803)
        participacao.delete()

        participacao = Participacao.objects.get(id=108804)
        participacao.delete()

        # 20231190340042
        participacao_anterior = Participacao.objects.get(id=103963)

        participacao = Participacao.objects.get(id=102822)
        participacao.data_termino = '2024-03-13'
        participacao.finalizado_por = participacao_anterior.atualizado_por
        participacao.finalizado_em = participacao_anterior.atualizado_em
        participacao.save()

        # 20231194010002
        participacao_anterior = Participacao.objects.get(id=103883)

        participacao = Participacao.objects.get(id=103885)
        participacao.data_termino = '2024-03-07'
        participacao.finalizado_por = participacao_anterior.atualizado_por
        participacao.finalizado_em = participacao_anterior.atualizado_em
        participacao.save()

        # 20211197100017
        participacao = Participacao.objects.get(id=110551)
        participacao.delete()

        # 20221194010035
        participacao = Participacao.objects.get(id=106314)
        participacao.data_termino = '2024-08-08'
        participacao.save()

        participacao_anterior = Participacao.objects.get(id=110246)

        participacao = Participacao.objects.get(id=106358)
        participacao.data_termino = '2024-10-14'
        participacao.finalizado_por = participacao_anterior.atualizado_por
        participacao.finalizado_em = participacao_anterior.atualizado_em
        participacao.motivo_termino = 'Edição da participação.'
        participacao.save()

        # 20221010590024
        participacao = Participacao.objects.get(id=109975)
        participacao.delete()

        # 20211021010028
        participacao_anterior = Participacao.objects.get(id=103984)
        participacao_anterior.data_termino = '2024-07-08'
        participacao_anterior.save()

        participacao = Participacao.objects.get(id=104328)
        participacao.data_termino = '2024-09-03'
        participacao.finalizado_por = participacao_anterior.atualizado_por
        participacao.finalizado_em = participacao_anterior.atualizado_em
        participacao.motivo_termino = 'Edição da participação.'
        participacao.save()

        # 20211022020014
        participacao = Participacao.objects.get(id=108162)
        participacao.delete()

        participacao = Participacao.objects.get(id=100496)
        participacao.data_termino = '2024-07-22'
        participacao.save()

        # 20231022010023
        participacao = Participacao.objects.get(id=110850)
        participacao.delete()

        # 20231024010002
        participacao_anterior = Participacao.objects.get(id=109700)

        participacao = Participacao.objects.get(id=108376)
        participacao.data_termino = '2024-09-18'
        participacao.finalizado_por = participacao_anterior.atualizado_por
        participacao.finalizado_em = participacao_anterior.atualizado_em
        participacao.motivo_termino = 'Edição da participação.'
        participacao.save()

        # 20211021010030
        participacao_anterior = Participacao.objects.get(id=96470)
        participacao_anterior.data_termino = '2024-07-08'
        participacao_anterior.save()

        participacao_anterior = Participacao.objects.get(id=109363)

        participacao = Participacao.objects.get(id=104321)
        participacao.data_termino = '2024-09-11'
        participacao.finalizado_por = participacao_anterior.atualizado_por
        participacao.finalizado_em = participacao_anterior.atualizado_em
        participacao.motivo_termino = 'Edição da participação.'
        participacao.save()

        # 20231020450022
        participacao = Participacao.objects.get(id=104877)
        participacao.delete()

        # 20231021010006
        participacao_anterior = Participacao.objects.get(id=100630)
        participacao_anterior.data_termino = '2024-08-27'
        participacao_anterior.save()

        participacao_anterior = Participacao.objects.get(id=109701)

        participacao = Participacao.objects.get(id=108179)
        participacao.data_termino = '2024-09-18'
        participacao.finalizado_por = participacao_anterior.atualizado_por
        participacao.finalizado_em = participacao_anterior.atualizado_em
        participacao.motivo_termino = 'Edição da participação.'
        participacao.save()

        # 20231022010004
        participacao = Participacao.objects.get(id=109224)
        participacao.delete()

        # 20221041110002
        participacao = Participacao.objects.get(id=111199)
        participacao.delete()

        # 20222071060010
        participacao = Participacao.objects.get(id=105203)
        participacao.delete()

        # 20212024300027
        participacao = Participacao.objects.get(id=110423)
        participacao.delete()

        # 20221024010040
        participacao = Participacao.objects.get(id=109325)
        participacao.delete()

        # 20211022020005
        participacao = Participacao.objects.get(id=109347)
        participacao.delete()

        # 20231022010019
        participacao = Participacao.objects.get(id=109480)
        participacao.delete()

        participacao = Participacao.objects.get(id=111144)
        participacao.delete()

        participacao_anterior = Participacao.objects.get(id=103551)
        participacao_anterior.data_termino = '2024-08-31'
        participacao_anterior.save()

        # 20231024010006
        participacao = Participacao.objects.get(id=109472)
        participacao.delete()

        # 20231024010036
        participacao = Participacao.objects.get(id=109674)
        participacao.delete()

        # 20231022010013
        participacao_anterior = Participacao.objects.get(id=102209)
        participacao_anterior.data_termino = '2024-08-31'
        participacao_anterior.save()

        participacao_anterior = Participacao.objects.get(id=111143)

        participacao = Participacao.objects.get(id=109267)
        participacao.data_termino = '2024-10-24'
        participacao.finalizado_por = participacao_anterior.atualizado_por
        participacao.finalizado_em = participacao_anterior.atualizado_em
        participacao.motivo_termino = 'Edição da participação.'
        participacao.save()
