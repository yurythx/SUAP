import datetime

from dateutil.relativedelta import relativedelta
from django.apps import apps

from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        ServidorAfastamento = apps.get_model('rh', 'ServidorAfastamento')
        # AfastamentoSiape = apps.get_model('rh', 'AfastamentoSiape')
        EditalLicCapacitacao = apps.get_model('licenca_capacitacao', 'EditalLicCapacitacao')
        LicCapacitacaoPorDia = apps.get_model('licenca_capacitacao', 'LicCapacitacaoPorDia')
        Ano = apps.get_model('comum', 'Ano')
        PedidoLicCapacitacao = apps.get_model('licenca_capacitacao', 'PedidoLicCapacitacao')

        codigos_lc = EditalLicCapacitacao.get_todos_os_codigos_licenca_capacitacao()

        # lista_licenca_capacitacao_siape = ServidorAfastamento.objects.filter(afastamento__codigo=AfastamentoSiape.LICENCA_CAPACITACAO_3_MESES,
        #                                                                     cancelado=False).order_by('data_inicio')
        lista_licenca_capacitacao_siape = ServidorAfastamento.objects.filter(afastamento__codigo__in=codigos_lc, cancelado=False).order_by(
            'data_inicio'
        )

        # =====================================
        # Calcula/Recalcula os licenciados por dia
        # =====================================

        # ---------------------------------------------
        # Zerando o quadro
        # ---------------------------------------------
        LicCapacitacaoPorDia.objects.all().delete()

        # ---------------------------------------------
        # Com base nos dados do SIAPE
        # Gera os dias desde a primeira lic capacitacao até 3 anos depois da data atual
        # ---------------------------------------------
        lista_datas_insert = []
        if lista_licenca_capacitacao_siape:
            inicio = lista_licenca_capacitacao_siape.first().data_inicio
            final = datetime.datetime.today().date()
            final_total = final + relativedelta(years=3)
            qtd_dias = (final_total - inicio).days
            lista_datas = [inicio + datetime.timedelta(days=x) for x in range(qtd_dias + 1)]
            for d in lista_datas:
                lista_datas_insert.append(LicCapacitacaoPorDia(ano=Ano.objects.get(ano=d.year), mes=d.month, dia=d.day, data=d))
            LicCapacitacaoPorDia.objects.bulk_create(lista_datas_insert)

        # ---------------------------------------------
        # Com base nos dados do SIAPE
        # Puxa os dias que existe afastamento e quantas pessoas estao naquele dia
        # ---------------------------------------------
        lista_datas_update = []
        for d in lista_datas_insert:
            lista_datas_update.append({'data': d, 'qtd_docentes': 0, 'qtd_taes': 0})
        for afast in lista_licenca_capacitacao_siape:
            data_atual = afast.data_inicio
            data_final = afast.data_termino
            while data_atual <= data_final:
                if afast.servidor.eh_docente:
                    q = lista_datas_update[lista_datas.index(data_atual)]['qtd_docentes']
                    lista_datas_update[lista_datas.index(data_atual)]['qtd_docentes'] = q + 1
                if afast.servidor.eh_tecnico_administrativo:
                    q = lista_datas_update[lista_datas.index(data_atual)]['qtd_taes']
                    lista_datas_update[lista_datas.index(data_atual)]['qtd_taes'] = q + 1
                data_atual = data_atual + datetime.timedelta(days=1)
        datas = LicCapacitacaoPorDia.objects.all().order_by('data')
        for data in datas:
            data.qtd_docentes = lista_datas_update[lista_datas.index(data.data)]['qtd_docentes']
            data.qtd_taes = lista_datas_update[lista_datas.index(data.data)]['qtd_taes']
            data.qtd_total = data.qtd_docentes + data.qtd_taes
        LicCapacitacaoPorDia.objects.bulk_update(datas, ['qtd_docentes', 'qtd_taes', 'qtd_total'], batch_size=500)

        # ---------------------------------------------
        # Sincroniza SUAP com SIAPE
        # Pega os aprovados em definitivo no SUAP e verifica se ja veio do SIAPE
        # cadastrado_no_siape
        # ---------------------------------------------
        lista_licenca_capacitacao_suap = PedidoLicCapacitacao.get_pedidos_aprovado_em_definitivo_nao_cadastrados_no_siape()
        for licenca_capacitacao_suap in lista_licenca_capacitacao_suap:
            # Se essa licenca do SUAP ainda nao foi caastrada no SIAPE
            # Se ja foi entao a do SUAP sera marcada como "cadastrado_no_siape=True"
            inicio_primeiro_periodo_pedido = PedidoLicCapacitacao.get_inicio_primeiro_periodo_pedido(licenca_capacitacao_suap)
            licenca_capacitacao_suap.cadastrado_no_siape = False
            if inicio_primeiro_periodo_pedido:
                existe_no_siape = lista_licenca_capacitacao_siape.filter(
                    servidor=licenca_capacitacao_suap.servidor, data_inicio=inicio_primeiro_periodo_pedido
                )
                if existe_no_siape:
                    licenca_capacitacao_suap.cadastrado_no_siape = True
        PedidoLicCapacitacao.objects.bulk_update(lista_licenca_capacitacao_suap, ['cadastrado_no_siape'], batch_size=500)

        # ---------------------------------------------
        # Contabiliza as licencas do SUAP
        # - Que foram aprovadas em definitivo E que ainda nao foram cadastradas no SIAPE
        # ---------------------------------------------
        lista_licenca_capacitacao_suap = PedidoLicCapacitacao.get_pedidos_aprovado_em_definitivo_nao_cadastrados_no_siape()
        for suap in lista_licenca_capacitacao_suap:
            periodos = suap.get_lista_periodos_pedido()
            for p in periodos:
                data_atual = p.data_inicio
                data_final = p.data_termino
                while data_atual <= data_final:
                    quadro = LicCapacitacaoPorDia.objects.get(data=data_atual)
                    if p.pedido.eh_docente:
                        quadro.qtd_docentes_suap += 1
                    if p.pedido.eh_tecnico_administrativo:
                        quadro.qtd_taes_suap += 1
                    quadro.save()
                    data_atual = data_atual + datetime.timedelta(days=1)

        # Conta geral
        # qtd_total_suap, qtd_docentes_geral, qtd_taes_geral, qtd_total_geral
        lcpds = LicCapacitacaoPorDia.objects.all()
        for lcpd in lcpds:
            lcpd.qtd_total_suap = lcpd.qtd_taes_suap + lcpd.qtd_docentes_suap

            lcpd.qtd_docentes_geral = lcpd.qtd_docentes + lcpd.qtd_docentes_suap
            lcpd.qtd_taes_geral = lcpd.qtd_taes + lcpd.qtd_taes_suap
            lcpd.qtd_total_geral = lcpd.qtd_total + lcpd.qtd_total_suap
            lcpd.save()

        """
        # LicCapacitacaoPorDia.objects.bulk_update(lcpd, ['qtd_total_suap',
        #                                                'qtd_docentes_geral',
        #                                                'qtd_taes_geral',
        #                                                'qtd_total_geral'], batch_size=500)
        """
