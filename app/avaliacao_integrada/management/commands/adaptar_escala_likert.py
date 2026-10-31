import hashlib
from time import sleep

from django.db import transaction
from django.db.models import Count

from avaliacao_integrada.models import EscalaLikert, Indicador, NivelEscalaLikert, OpcaoResposta, Resposta
from djtools.management.commands import BaseCommandPlus

UNICA_ESCOLHA = Indicador.UNICA_ESCOLHA  # 'Única Escolha' (5)
FAIXA_NUMERICA = 8  # 'Escala Padrão'. Constante removida de Indicador, substituida por ESCALA_LIKERT
GRAU_SATISFACAO = 9  # 'Grau de Satisfação'. Constante removida de Indicador, substituida por ESCALA_LIKERT
ESCALA_LIKERT = Indicador.ESCALA_LIKERT  # 'Escala Likert' (99)
MULTIPLA_ESCOLHA = Indicador.MULTIPLA_ESCOLHA  # (6)
TIPOS_RESPOSTAS = (UNICA_ESCOLHA, FAIXA_NUMERICA, GRAU_SATISFACAO, ESCALA_LIKERT, MULTIPLA_ESCOLHA)

TIPOS_RESPOSTAS_PARSE = {
    UNICA_ESCOLHA: '5 - Única Escolha',
    FAIXA_NUMERICA: '8 - Faixa Númerica (Escala Padrão)',
    GRAU_SATISFACAO: '9 - Grau de Satisfação',
    ESCALA_LIKERT: '99 - Escala Likert',
    MULTIPLA_ESCOLHA: '6 - Multipla escolha',
}


class Command(BaseCommandPlus):
    def indicadores_definir_escala(self):
        escalas_encontradas = {}

        indicadores_ids = Indicador.objects.filter(tipo_resposta=UNICA_ESCOLHA).values_list('id', flat=True)
        for indicador_id in indicadores_ids:
            sopcoes_descricoes = OpcaoResposta.objects.filter(indicador=indicador_id).values_list('descricao', flat=True)
            escala_str = ''.join(snivel.replace(' ', '') for snivel in sopcoes_descricoes)
            codigo_hash = hashlib.sha256(escala_str.encode('utf-8')).hexdigest()

            if escalas_encontradas.get(codigo_hash) is None:
                escalas_encontradas[codigo_hash] = {
                    'niveis': list(sopcoes_descricoes),
                    'valores': set(),
                    'indicadores': [],
                }
            escalas_encontradas[codigo_hash]['indicadores'].append(indicador_id)

            respostas_qs = Resposta.objects.filter(indicador=indicador_id)
            valores = list(respostas_qs.values_list('valor', flat=True))
            escalas_encontradas[codigo_hash]['valores'].update(valores)

        for codigo_hash, dados in escalas_encontradas.items():
            self.stdout.write('\n')
            self.stdout.write(f'Código: {codigo_hash}')
            self.stdout.write(f'Níveis: {dados["niveis"]}')
            self.stdout.write(f'Valores: {dados["valores"]}')
            self.stdout.write(f'Indicadores: {sorted(dados["indicadores"])}')

            respostas_qs = Resposta.objects.filter(indicador__in=dados['indicadores']).values('respondente__avaliacao')
            avaliacoes_ids = respostas_qs.annotate(quant=Count('id')).values_list('respondente__avaliacao', flat=True)
            self.stdout.write(f'Avaliações: {sorted(avaliacoes_ids)}')

    def imprimir_detalhes_dados(self, qs_resposta):
        qs_resposta_sum = (
            qs_resposta.values('respondente__avaliacao', 'nivel_escala', 'indicador__tipo_resposta', 'valor')
            .annotate(total=Count('id'))
            .values('respondente__avaliacao', 'nivel_escala', 'indicador__tipo_resposta', 'valor', 'total')
            .order_by('respondente__avaliacao', 'nivel_escala', 'indicador__tipo_resposta')
        )
        for sumario in qs_resposta_sum:
            self.stdout.write(sumario)

        qs_indicador = qs_resposta.values_list('indicador', flat=True)
        sindicadores = set(qs_indicador)
        self.stdout.write('\t\tIndicadores: ', sindicadores or 0)

    def imprimir_avaliacao_com_pendencias(self):
        existem_pendencias = False
        pendencias = {}
        tipos_resposas = []
        sumario = {}

        qs_sum_tipo_resposta = Resposta.objects.values('indicador__tipo_resposta').exclude(valor='').annotate(total=Count('id'))
        self.stdout.write("Total de respostas válidas (valor <> '') por tipo de resposta: ")
        for tipo_resposta, total in qs_sum_tipo_resposta.values_list('indicador__tipo_resposta', 'total'):
            sumario[tipo_resposta] = total
            self.stdout.write(f'{tipo_resposta}:{total}')
            tipos_resposas.append(tipo_resposta)

        self.stdout.write('\n# Verificando existências de pendências ... ')
        for tipo_resposta in tipos_resposas:
            if tipo_resposta in (FAIXA_NUMERICA, GRAU_SATISFACAO, ESCALA_LIKERT):
                qs_resposta = Resposta.objects.filter(indicador__tipo_resposta=tipo_resposta).exclude(valor='')
                if tipo_resposta == ESCALA_LIKERT:
                    self.stdout.write('Resposta cujo tipo do indicador é ESCALA_LIKERT, mas nivel_escala da resposta é nulo. ')
                    qs_resposta = qs_resposta.filter(nivel_escala__isnull=True)
                else:
                    self.stdout.write(
                        'Resposta cujo tipo do indicador é (FAIXA_NUMERICA ou GRAU_SATISFACAO), mas nivel_escala da resposta não é nula. '
                    )
                    qs_resposta = qs_resposta.filter(nivel_escala__isnull=False)
                if not qs_resposta.exists():
                    continue

                existem_pendencias = True
                self.stdout.write(f'AVISO: Tipo resposta {tipo_resposta} necessita de verificação.')
                qs_resposta = qs_resposta.values('respondente__avaliacao', 'respondente__avaliacao__nome').annotate(quant=Count('id'))
                self.stdout.write('\tAvaliações: ')
                for respondente__avaliacao, respondente__avaliacao__nome, quant in qs_resposta.values_list(
                    'respondente__avaliacao', 'respondente__avaliacao__nome', 'quant'
                ):
                    if pendencias.get(respondente__avaliacao) is None:
                        pendencias[respondente__avaliacao] = {
                            'avaliacao_id': respondente__avaliacao,
                            'avaliacao_nome': respondente__avaliacao__nome,
                            'total_resposta': quant,
                            'tipos_respostas': {},
                        }
                    if pendencias[respondente__avaliacao].get('tipos_respostas') is None:
                        pendencias[respondente__avaliacao]['tipos_respostas'] = {}

                    # pendencias[respondente__avaliacao]['total_resposta']['totais_respostas'].append(quant)

                    self.stdout.write(f'\t{respondente__avaliacao} - {respondente__avaliacao__nome}, total: {quant} respostas')

                    respostas = (
                        qs_resposta.filter(respondente__avaliacao=respondente__avaliacao)
                        .values('indicador', 'valor')
                        .annotate(quant=Count('id'))
                        .values('valor', 'quant')
                    )
                    self.stdout.write('\tValores: ')
                    self.stdout.write('\t\t[Tipo Resposta], Indicador ID, Resposta Valor, Total')
                    for indicador, valor, quant in respostas.values_list('indicador', 'valor', 'quant'):
                        if pendencias[respondente__avaliacao]['tipos_respostas'].get(tipo_resposta) is None:
                            pendencias[respondente__avaliacao]['tipos_respostas'][tipo_resposta] = {}
                        if pendencias[respondente__avaliacao]['tipos_respostas'][tipo_resposta].get(indicador) is None:
                            pendencias[respondente__avaliacao]['tipos_respostas'][tipo_resposta][indicador] = {}
                            pendencias[respondente__avaliacao]['tipos_respostas'][tipo_resposta][indicador] = []
                        pendencias[respondente__avaliacao]['tipos_respostas'][tipo_resposta][indicador].append((valor, quant))

                        self.stdout.write(f'\t\t[{tipo_resposta}], {indicador}, {valor}, {quant}')
        if not existem_pendencias:
            self.stdout.write('Processamento concluído com sucesso, não foram encontrados pendências')

        sleep(1)

        self.stdout.write('\nTotal de respostas em que o tipo de resposta do indicador é uma Escala Likert, mas o nível da reposta está nula.')
        qs_respostas = Resposta.objects.filter(nivel_escala__isnull=True, indicador__tipo_resposta=ESCALA_LIKERT).exclude(valor='')
        self.imprimir_detalhes_dados(qs_respostas)

        self.stdout.write('\nTotal de respostas onde existe o nível de resposta, porém o tipo de resposta do indicador não é uma escala likert')
        qs_respostas = Resposta.objects.filter(nivel_escala__isnull=False).exclude(valor='').exclude(indicador__tipo_resposta=ESCALA_LIKERT)
        self.imprimir_detalhes_dados(qs_respostas)

        self.stdout.write('\nTotal de respostas por valor onde o tipo de resposta é "UNICA_ESCOLHA" e nível escala é nula.')
        qs_respostas = Resposta.objects.filter(indicador__tipo_resposta=UNICA_ESCOLHA, nivel_escala__isnull=True).exclude(valor='')
        qs_respostas = qs_respostas.values('valor').annotate(quant=Count('id'))
        valores = qs_respostas.values_list('valor', 'quant')

        for valor, quant in valores:
            self.stdout.write(f'- {valor}: {quant}')

        return existem_pendencias, pendencias, sumario

    def criar_ou_obter_nivel(self, escala, nivel, descricao, tipo_criterio, emoji=None):
        return NivelEscalaLikert.objects.get_or_create(escala=escala, nivel=nivel, descricao=descricao, tipo_criterio=tipo_criterio, emoji=emoji)

    @transaction.atomic
    def atualizar_respostas(self, indicadores_ids, valor_resposta, nivel):
        self.stdout.write(f'\tAtualizando respostas, cujo valor é "{valor_resposta}" para nível "{nivel}" ...')
        qs_respostas = Resposta.objects.filter(indicador__in=indicadores_ids, nivel_escala__isnull=True, valor=valor_resposta)
        rows = qs_respostas.update(valor=str(nivel.nivel), nivel_escala=nivel)
        self.stdout.write(f'\t\tRespostas atualizadas: {rows}')

    @transaction.atomic
    def atualizar_indicadores(self, indicadores_ids, escala):
        self.stdout.write(f'\tAtualizando indicadores "{indicadores_ids}" para a escala "{escala}" ...')
        rows = Indicador.objects.filter(id__in=indicadores_ids, escala__isnull=True).update(escala=escala, tipo_resposta=ESCALA_LIKERT)
        self.stdout.write(f'\tIndicadores atualizados: {rows}')

    def existe_respostas_a_atualizar(self, tipo_resposta):
        return Resposta.objects.filter(indicador__tipo_resposta=tipo_resposta, nivel_escala__isnull=True).exclude(valor='')

    def processar_escala(self, nome_escala, ativo, niveis, indicadores_ids):
        self.stdout.write(f'\nProcessando escala: {nome_escala} ...')

        escala, _ = EscalaLikert.objects.get_or_create(nome=nome_escala, ativo=ativo)

        for nivel_data in niveis:
            nivel, _created = self.criar_ou_obter_nivel(
                escala, nivel_data['nivel'], nivel_data['descricao'], nivel_data['tipo_criterio'], nivel_data.get('emoji')
            )
            for valor in nivel_data['valores']:
                self.atualizar_respostas(indicadores_ids, valor, nivel)

        self.atualizar_indicadores(indicadores_ids, escala)

    def processar_respostas_unica_escolha(self):
        # Dados obtidos do método self.indicadores_definir_escala

        # Código: 5dd480174727e5f5ae1e6347bdd68c55cdd64a4205a30479921d8639e5872ee5
        # Níveis: ['Concordo', 'Concordo parcialmente', 'Discordo parcialmente', 'Discordo', 'Desconheço']
        # Valores: {'Discordo', '', 'Desconheço', 'Discordo parcialmente', 'Concordo', 'Concordo parcialmente'}
        # Indicadores: [752, 753, 754, 756, 757, 758, 759, 760, 761, 762, 763, 764, 765, 766, 767,
        # 768, 769, 770, 771, 772, 773, 774, 775, 777, 780, 783, 784, 785, 786, 787, 788, 790, 791, 792, 793, 795, 796,
        # 797, 798, 799, 894, 904, 916, 933, 944, 949]
        # Avaliações: [13]
        # Exemplo para Escala 2020
        niveis = [
            {'nivel': 0, 'descricao': 'Desconheço', 'tipo_criterio': NivelEscalaLikert.CRITERIO_DESCONHECO, 'valores': ['Desconheço']},
            {'nivel': 1, 'descricao': 'Discordo', 'tipo_criterio': NivelEscalaLikert.CRITERIO_DISCORDO, 'valores': ['Discordo']},
            {
                'nivel': 2,
                'descricao': 'Discordo parcialmente',
                'tipo_criterio': NivelEscalaLikert.CRITERIO_DISCORDO_PARCIALMENTE,
                'valores': ['Discordo parcialmente'],
            },
            {
                'nivel': 3,
                'descricao': 'Concordo parcialmente',
                'tipo_criterio': NivelEscalaLikert.CRITERIO_CONCORDO_PARCIALMENTE,
                'valores': ['Concordo parcialmente'],
            },
            {'nivel': 4, 'descricao': 'Concordo', 'tipo_criterio': NivelEscalaLikert.CRITERIO_CONCORDO, 'valores': ['Concordo']},
        ]
        indicadores_ids = (
            752,
            753,
            754,
            756,
            757,
            758,
            759,
            760,
            761,
            762,
            763,
            764,
            765,
            766,
            767,
            768,
            769,
            770,
            771,
            772,
            773,
            774,
            775,
            777,
            780,
            783,
            784,
            785,
            786,
            787,
            788,
            790,
            791,
            792,
            793,
            795,
            796,
            797,
            798,
            799,
            894,
            904,
            916,
            933,
            944,
            949,
        )
        self.processar_escala('Escala 2020', False, niveis, indicadores_ids)

        # Código: 0569baa1e34a26f467a72fb9202a0fb36c1b3948b245f8f0da2ad352cc223fa2
        # Níveis: ['Concordo', 'Concordo Parcialmente', 'Discordo Parcialmente', 'Discordo', 'Desconheço']
        # Valores: {'Discordo', '', 'Desconheço', 'Discordo Parcialmente', 'Concordo', 'Concordo Parcialmente'}
        # Indicadores: [805, 807, 808, 809, 810, 811, 812, 813, 814, 815, 816, 817, 818, 819, 820,
        # 821, 822, 823, 824, 825, 826, 827, 828, 829, 830, 831, 834, 835, 836, 837, 838, 839, 840,
        #  841, 842, 843, 844, 845, 846, 847, 848, 849, 850, 851, 852, 853, 854, 855, 856, 857, 858, 859, 860, 861, 867, 869, 872, 893]
        # Avaliações: [14, 16]

        niveis = [
            {'nivel': 0, 'descricao': 'Desconheço', 'tipo_criterio': NivelEscalaLikert.CRITERIO_DESCONHECO, 'valores': ['Desconheço']},
            {'nivel': 1, 'descricao': 'Discordo', 'tipo_criterio': NivelEscalaLikert.CRITERIO_DISCORDO, 'valores': ['Discordo']},
            {
                'nivel': 2,
                'descricao': 'Discordo Parcialmente',
                'tipo_criterio': NivelEscalaLikert.CRITERIO_DISCORDO_PARCIALMENTE,
                'valores': ['Discordo Parcialmente', 'Discordo Parcilamente'],
            },
            {
                'nivel': 3,
                'descricao': 'Concordo Parcialmente',
                'tipo_criterio': NivelEscalaLikert.CRITERIO_CONCORDO_PARCIALMENTE,
                'valores': ['Concordo Parcialmente'],
            },
            {'nivel': 4, 'descricao': 'Concordo', 'tipo_criterio': NivelEscalaLikert.CRITERIO_CONCORDO, 'valores': ['Concordo']},
        ]

        indicadores_ids = (
            805,
            806,
            807,
            808,
            809,
            810,
            811,
            812,
            813,
            814,
            815,
            816,
            817,
            818,
            819,
            820,
            821,
            822,
            823,
            824,
            825,
            826,
            827,
            828,
            829,
            830,
            831,
            834,
            835,
            836,
            837,
            838,
            839,
            840,
            841,
            842,
            843,
            844,
            845,
            846,
            847,
            848,
            849,
            850,
            851,
            852,
            853,
            854,
            855,
            856,
            857,
            858,
            859,
            860,
            861,
            867,
            869,
            872,
            893,
        )

        self.processar_escala('Escala 2021/2022', False, niveis, indicadores_ids)

        # Código: ce30d81064374d366dcd580d0cf8d0d4faf3a1581186f601c1d42529bef49c37
        # Níveis: ['Concordo', 'Concordo Parcialmente', 'Discordo Parcilamente', 'Discordo', 'Desconheço']
        # Valores: {'Discordo', '', 'Desconheço', 'Discordo Parcilamente', 'Concordo', 'Concordo Parcialmente'}
        # Indicadores: [806]
        # Avaliações: [14]

        niveis = [
            {'nivel': 0, 'descricao': 'Desconheço', 'tipo_criterio': NivelEscalaLikert.CRITERIO_DESCONHECO, 'valores': ['Desconheço']},
            {'nivel': 1, 'descricao': 'Discordo', 'tipo_criterio': NivelEscalaLikert.CRITERIO_DISCORDO, 'valores': ['Discordo']},
            {
                'nivel': 2,
                'descricao': 'Discordo Parcilamente',
                'tipo_criterio': NivelEscalaLikert.CRITERIO_DISCORDO_PARCIALMENTE,
                'valores': ['Discordo Parcialmente'],
            },
            {
                'nivel': 3,
                'descricao': 'Concordo Parcialmente',
                'tipo_criterio': NivelEscalaLikert.CRITERIO_CONCORDO_PARCIALMENTE,
                'valores': ['Concordo Parcialmente'],
            },
            {'nivel': 4, 'descricao': 'Concordo', 'tipo_criterio': NivelEscalaLikert.CRITERIO_CONCORDO, 'valores': ['Concordo']},
        ]

        indicadores_ids = (806,)
        self.processar_escala('Escala 2021/2022', False, niveis, indicadores_ids)

        # Código: 4dd2f4580f6c2e1fd41c51b3fbc159bd06cf4daa2c0311602c975f5cfd757355
        # Níveis: ['Concordo', 'Concordo parcialmente', 'Discordo', 'Desconheço']
        # Valores: {'', 'Discordo', 'Desconheço', 'Concordo', 'Concordo parcialmente'}
        # Indicadores: [655, 656, 657, 658, 659, 662, 663, 664, 665, 666, 669, 670, 671, 672, 673,
        # 674, 676, 677, 678, 679, 680, 681, 682, 683, 684, 685, 686, 688, 689, 690, 691, 692, 693, 694, 696, 698, 699,
        # 700, 701, 702, 703, 704, 705, 706, 707, 950]
        # Avaliações: [10]

        niveis = [
            {'nivel': 0, 'descricao': 'Desconheço', 'tipo_criterio': NivelEscalaLikert.CRITERIO_DESCONHECO, 'valores': ['Desconheço']},
            {'nivel': 1, 'descricao': 'Discordo', 'tipo_criterio': NivelEscalaLikert.CRITERIO_DISCORDO, 'valores': ['Discordo']},
            {
                'nivel': 2,
                'descricao': 'Concordo parcialmente',
                'tipo_criterio': NivelEscalaLikert.CRITERIO_CONCORDO_PARCIALMENTE,
                'valores': ['Concordo parcialmente'],
            },
            {'nivel': 3, 'descricao': 'Concordo', 'tipo_criterio': NivelEscalaLikert.CRITERIO_CONCORDO, 'valores': ['Concordo']},
        ]

        indicadores_ids = (
            655,
            656,
            657,
            658,
            659,
            662,
            663,
            664,
            665,
            666,
            669,
            670,
            671,
            672,
            673,
            674,
            676,
            677,
            678,
            679,
            680,
            681,
            682,
            683,
            684,
            685,
            686,
            688,
            689,
            690,
            691,
            692,
            693,
            694,
            696,
            698,
            699,
            700,
            701,
            702,
            703,
            704,
            705,
            706,
            707,
            950,
        )
        self.processar_escala('Escala 2019', False, niveis, indicadores_ids)

        # Código: f9a10649f403c0a96c700c8526fc21b73bbeda2104ad8b0ba48fb2fb42dc011c
        # Níveis: ['😃 Concordo', '🙂 Concordo parcialmente', '😐 Discordo parcialmente', '☹️ Discordo', '😶 Desconheço']
        # Valores: {'', 'Discordo', 'Desconheço', '😃 Concordo', '🙂 Concordo parcialmente', 'Discordo parcialmente',
        # 'Concordo', '☹️ Discordo', 'Concordo parcialmente', '😶 Desconheço', '😐 Discordo parcialmente'}
        # Indicadores: [897, 898, 899, 900, 901, 902, 903, 905, 906, 907, 908, 909, 910, 911, 913,
        # 914, 915, 917, 918, 919, 920, 921, 922, 923, 924, 925, 927, 928, 930, 931, 934, 935, 936,
        #  937, 938, 939, 940, 941, 942, 946, 947, 948, 951, 952, 955, 956, 957, 958, 960, 961, 962
        # , 963, 964, 965, 968, 969, 970, 971, 973, 974, 976, 977, 978, 979, 982, 983, 985, 986, 987, 988, 989, 991, 992, 993, 994, 995]
        # Avaliações: [17, 18, 19, 20, 21]

        niveis = [
            {
                'nivel': 0,
                'descricao': 'Desconheço',
                'tipo_criterio': NivelEscalaLikert.CRITERIO_DESCONHECO,
                'valores': ['Desconheço', '😶 Desconheço'],
                'emoji': '😶',
            },
            {
                'nivel': 1,
                'descricao': 'Discordo',
                'tipo_criterio': NivelEscalaLikert.CRITERIO_DISCORDO,
                'valores': ['Discordo', '☹️ Discordo'],
                'emoji': '☹️',
            },
            {
                'nivel': 2,
                'descricao': 'Discordo parcialmente',
                'tipo_criterio': NivelEscalaLikert.CRITERIO_DISCORDO_PARCIALMENTE,
                'valores': ['Discordo parcialmente', '😐 Discordo parcialmente'],
                'emoji': '😐',
            },
            {
                'nivel': 3,
                'descricao': 'Concordo parcialmente',
                'tipo_criterio': NivelEscalaLikert.CRITERIO_CONCORDO_PARCIALMENTE,
                'valores': ['Concordo parcialmente', '🙂 Concordo parcialmente'],
                'emoji': '🙂',
            },
            {
                'nivel': 4,
                'descricao': 'Concordo',
                'tipo_criterio': NivelEscalaLikert.CRITERIO_CONCORDO,
                'valores': ['Concordo', '😃 Concordo'],
                'emoji': '😃',
            },
        ]

        indicadores_ids = (
            897,
            898,
            899,
            900,
            901,
            902,
            903,
            905,
            906,
            907,
            908,
            909,
            910,
            911,
            913,
            914,
            915,
            917,
            918,
            919,
            920,
            921,
            922,
            923,
            924,
            925,
            927,
            928,
            930,
            931,
            934,
            935,
            936,
            937,
            938,
            939,
            940,
            941,
            942,
            946,
            947,
            948,
            951,
            952,
            955,
            956,
            957,
            958,
            960,
            961,
            962,
            963,
            964,
            965,
            968,
            969,
            970,
            971,
            973,
            974,
            976,
            977,
            978,
            979,
            982,
            983,
            985,
            986,
            987,
            988,
            989,
            991,
            992,
            993,
            994,
            995,
        )

        self.processar_escala('Escala Padrão', True, niveis, indicadores_ids)

    def processar_respostas_faixa_numerica(self):
        niveis = [
            {'nivel': 0, 'descricao': 'Desconheço', 'tipo_criterio': NivelEscalaLikert.CRITERIO_DESCONHECO, 'valores': ['0']},
            {'nivel': 1, 'descricao': '1', 'tipo_criterio': NivelEscalaLikert.CRITERIO_DISCORDO, 'valores': ['1']},
            {'nivel': 2, 'descricao': '2', 'tipo_criterio': NivelEscalaLikert.CRITERIO_DISCORDO_PARCIALMENTE, 'valores': ['2']},
            {'nivel': 3, 'descricao': '3', 'tipo_criterio': NivelEscalaLikert.CRITERIO_NAO_SE_APLICA, 'valores': ['3']},
            {'nivel': 4, 'descricao': '4', 'tipo_criterio': NivelEscalaLikert.CRITERIO_CONCORDO_PARCIALMENTE, 'valores': ['4']},
            {'nivel': 5, 'descricao': '5', 'tipo_criterio': NivelEscalaLikert.CRITERIO_CONCORDO, 'valores': ['5']},
            {'nivel': 9, 'descricao': 'Não se aplica', 'tipo_criterio': NivelEscalaLikert.CRITERIO_NAO_SE_APLICA, 'valores': ['9']},
        ]
        qs_indicadores = Indicador.objects.filter(tipo_resposta=FAIXA_NUMERICA).values_list('id', flat=True)
        self.processar_escala('Escala Faixa Númerica', True, niveis, list(qs_indicadores))

    def processar_respostas_grau_satisfacao(self):
        niveis = [
            {'nivel': 0, 'descricao': 'Desconheço', 'tipo_criterio': NivelEscalaLikert.CRITERIO_DESCONHECO, 'valores': ['0']},
            {'nivel': 1, 'descricao': 'Muito insatisfeito', 'tipo_criterio': NivelEscalaLikert.CRITERIO_DISCORDO, 'valores': ['1']},
            {'nivel': 2, 'descricao': 'Insatisfeito', 'tipo_criterio': NivelEscalaLikert.CRITERIO_DISCORDO_PARCIALMENTE, 'valores': ['2']},
            {'nivel': 3, 'descricao': 'Neutro', 'tipo_criterio': NivelEscalaLikert.CRITERIO_NAO_SE_APLICA, 'valores': ['3']},
            {'nivel': 4, 'descricao': 'Satisfeito', 'tipo_criterio': NivelEscalaLikert.CRITERIO_CONCORDO_PARCIALMENTE, 'valores': ['4']},
            {'nivel': 5, 'descricao': 'Muito satisfeito', 'tipo_criterio': NivelEscalaLikert.CRITERIO_CONCORDO, 'valores': ['5']},
            {'nivel': 9, 'descricao': 'Não se aplica', 'tipo_criterio': NivelEscalaLikert.CRITERIO_NAO_SE_APLICA, 'valores': ['9']},
        ]
        qs_indicadores = Indicador.objects.filter(tipo_resposta=GRAU_SATISFACAO).values_list('id', flat=True)
        self.processar_escala('Escala Grau Satisfação', True, niveis, list(qs_indicadores))

    def handle(self, *args, **options):
        self.processar_respostas_unica_escolha()
        self.processar_respostas_faixa_numerica()
        self.processar_respostas_grau_satisfacao()
        self.imprimir_avaliacao_com_pendencias()
