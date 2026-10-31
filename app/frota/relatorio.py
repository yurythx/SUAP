import datetime

from django.db.models import Count, F, Sum

from comum.utils import get_uo
from djtools import relatorios
from djtools.templatetags.filters import mascara_dinheiro
from djtools.utils import PDFResponse, calendario, permission_required, rtr, somar_dias
from estacionamento.models import Veiculo
from frota.forms import (
    CampusViaturaForm,
    FiltroMaquinaForm,
    FiltroViaturaForm,
    MotoristaTemporarioFilterForm,
    SolicitanteViagemForm,
    ViagemMotoristaForm,
)
from frota.models import Maquina, MaquinaOrdemAbastecimento, MotoristaTemporario, Viagem, Viatura, ViaturaOrdemAbastecimento


@rtr()
@permission_required(['frota.tem_acesso_viatura_sistemico', 'frota.tem_acesso_viatura_campus'])
def relatorio_viaturas(request):
    title = 'Relatório da Frota Atual'
    buscou = False
    if request.method == 'GET' and 'uo' not in request.GET:
        form = CampusViaturaForm(request=request)
    else:
        form = CampusViaturaForm(request.GET, request=request)
        if form.is_valid():
            buscou = True
            grupo_viatura = form.cleaned_data['grupo_viatura']
            campus = form.cleaned_data['uo']
            salvar_pdf = 'pdf' in request.GET
            hoje = datetime.datetime.today().strftime('%d/%m/%Y')
            if campus:
                viaturas = Viatura.objects.filter(campus=campus).order_by('placa_codigo_atual')
            else:
                viaturas = Viatura.objects.all().order_by('placa_codigo_atual')

            if grupo_viatura:
                viaturas = viaturas.filter(grupo=grupo_viatura)
            uo = request.user.get_vinculo().setor.uo
            topo = relatorios.get_topo_pdf(title)
            servidor = request.user.get_relacionamento()
            info = [['Data', hoje], ['Total de Viaturas', str(len(viaturas))]]
            dados = [['Modelo', 'Placa', 'Campus', 'Lotação', 'Combustíveis', 'Cor']]
            for viatura in viaturas:
                dados.append(
                    [viatura.modelo.nome, viatura.placa_codigo_atual, str(viatura.get_uo()), viatura.lotacao, viatura.get_combustiveis(), viatura.cor]
                )
            tabela_info = relatorios.table(info, grid=0, w=[30, 160], auto_align=0)
            tabela_dados = relatorios.table(dados, head=1, zebra=1, w=[50, 30, 20, 25, 25, 20], count=0)
            body = [*topo, tabela_info, relatorios.space(8), tabela_dados]
            if request.GET and 'pdf' in request.GET:
                return PDFResponse(relatorios.PdfReport(body=body).generate())
            else:
                return locals()
    return locals()


@rtr()
@permission_required(['frota.tem_acesso_viagem_sistemico', 'frota.tem_acesso_viagem_campus'])
def relatorio_solicitacoes_por_pessoa(request):
    title = 'Relatório de Viagens por Solicitante'
    buscou = False
    hoje = datetime.datetime.today()
    data_inicio = somar_dias(hoje, -30)
    data_termino = hoje
    if request.method == 'GET' and 'data_inicio' not in request.GET:
        form = SolicitanteViagemForm(request=request)
        form.fields['data_inicio'].initial = data_inicio
        form.fields['data_termino'].initial = data_termino
    else:
        form = SolicitanteViagemForm(request.GET, request=request)
        if form.is_valid():
            buscou = True
            data_inicio = form.cleaned_data['data_inicio']
            data_termino = form.cleaned_data['data_termino']
            uo = form.cleaned_data['uo']
            salvar_pdf = 'pdf' in request.GET
            data_inicio_str = data_inicio.strftime('%d/%m/%Y')
            data_termino_str = data_termino.strftime('%d/%m/%Y')
            hoje = datetime.datetime.today().strftime('%d/%m/%Y')
            data_inicio_sql = calendario.somar_dias(data_inicio, -1)
            data_termino_sql = calendario.somar_dias(data_termino, +1)
            if uo:
                registros = (
                    Viagem.objects.filter(
                        agendamento_resposta__agendamento__setor__uo=uo, saida_data__gt=data_inicio_sql, chegada_data__lt=data_termino_sql
                    )
                    .values('agendamento_resposta__agendamento__vinculo_solicitante__pessoa__nome')
                    .annotate(total=Count('id'))
                    .order_by('agendamento_resposta__agendamento__vinculo_solicitante__pessoa__nome')
                )
            else:
                registros = (
                    Viagem.objects.filter(saida_data__gt=data_inicio_sql, chegada_data__lt=data_termino_sql)
                    .values('agendamento_resposta__agendamento__vinculo_solicitante__pessoa__nome')
                    .annotate(total=Count('id'))
                    .order_by('agendamento_resposta__agendamento__vinculo_solicitante__pessoa__nome')
                )
            total_solicitante = registros.count()
            total_viagens = registros.aggregate(viagens=Sum('total'))['viagens']
            uo = request.user.get_vinculo().setor.uo
            topo = relatorios.get_topo_pdf(title)
            servidor = request.user.get_relacionamento()
            dados = [['Solicitante', 'Número de Viagens']]
            hoje = datetime.datetime.today().strftime('%d/%m/%Y')
            for registro in registros:
                dados.append([registro['agendamento_resposta__agendamento__vinculo_solicitante__pessoa__nome'], registro['total']])
            info = [['Data', hoje], ['Total de Solicitantes', str(len(registros))], ['Total de Viagens', str(total_viagens)]]
            tabela_info = relatorios.table(info, grid=0, w=[30, 160], auto_align=0)
            tabela_dados = relatorios.table(dados, head=1, zebra=1, w=[80, 30], count=0)
            body = [*topo, tabela_info, relatorios.space(8), tabela_dados]
            if request.GET and 'pdf' in request.GET:
                return PDFResponse(relatorios.PdfReport(body=body).generate())
            else:
                return locals()

    return locals()


@rtr()
@permission_required(['frota.tem_acesso_viatura_sistemico', 'frota.tem_acesso_viatura_campus'])
def relatorio_motoristas_temporarios(request):
    title = 'Motoristas Temporários'
    buscou = False

    if request.method == 'GET' and 'uo' not in request.GET:
        form = MotoristaTemporarioFilterForm(request=request)

    else:
        form = MotoristaTemporarioFilterForm(request.GET, request=request)
        if form.is_valid():
            buscou = True
            motorista_servidor = []
            motorista_terceirizado = []
            ids_repetidos = []
            campus = form.cleaned_data['uo']
            categoria = form.cleaned_data['categoria']
            disponibilidade = form.cleaned_data['disponibilidade']
            nome = form.cleaned_data.get('nome')

            hoje = datetime.datetime.now()
            viagens_em_andamento = Viagem.objects.filter(saida_data__lte=hoje, chegada_data__gte=hoje).values_list('motoristas', flat=True)

            if categoria == MotoristaTemporario.SERVIDOR:
                if campus:
                    motoristas = MotoristaTemporario.objects.filter(vinculo_pessoa__setor__uo=campus)
                else:
                    motoristas = MotoristaTemporario.objects.all()

                if nome:
                    motoristas = motoristas.filter(vinculo_pessoa__pessoa__nome__icontains=nome)

                if disponibilidade != MotoristaTemporario.TODOS:
                    if disponibilidade == MotoristaTemporario.DISPONIVEL:
                        motoristas = motoristas.exclude(vinculo_pessoa__in=viagens_em_andamento)
                    else:
                        motoristas = motoristas.filter(vinculo_pessoa__in=viagens_em_andamento)

                for motorista in motoristas:
                    if motorista.is_servidor():
                        if motorista.vinculo_pessoa not in ids_repetidos:
                            motorista_servidor.append(motorista)
                            ids_repetidos.append(motorista.vinculo_pessoa)

            elif categoria == MotoristaTemporario.TERCEIRIZADO:
                if campus:
                    motoristas = MotoristaTemporario.objects.filter(vinculo_pessoa__setor__uo=campus)
                else:
                    motoristas = MotoristaTemporario.objects.all()

                if nome:
                    motoristas = motoristas.filter(vinculo_pessoa__pessoa__nome__icontains=nome)

                if disponibilidade != MotoristaTemporario.TODOS:
                    if disponibilidade == MotoristaTemporario.DISPONIVEL:
                        motoristas = motoristas.exclude(vinculo_pessoa__in=viagens_em_andamento)
                    else:
                        motoristas = motoristas.filter(vinculo_pessoa__in=viagens_em_andamento)

                for motorista in motoristas:
                    if not motorista.is_servidor():
                        if motorista.vinculo_pessoa not in ids_repetidos:
                            motorista_terceirizado.append(motorista)
                            ids_repetidos.append(motorista.vinculo_pessoa)

            if request.GET and 'pdf' in request.GET:
                uo = get_uo(request.user)
                servidor = request.user.get_relacionamento()
                hoje = datetime.datetime.today().strftime('%d/%m/%Y')

                if categoria == MotoristaTemporario.SERVIDOR:
                    topo = relatorios.get_topo_pdf('Relatório de Motoristas Temporários com Portaria em Vigor - Servidores')
                    dados = [['Nome', 'Campus', 'Matricula', 'Portaria', 'Data Inicial', 'Data Final']]
                    for motorista in motorista_servidor:
                        adicionar = False
                        if not motorista.portaria_mais_recente().validade_final:
                            adicionar = True
                        else:
                            if motorista.portaria_mais_recente().validade_final > datetime.datetime.today().date():
                                adicionar = True
                        if adicionar:
                            tem_campus = '-'
                            if get_uo(motorista.vinculo_pessoa.user):
                                tem_campus = get_uo(motorista.vinculo_pessoa.user)

                            dados.append(
                                [
                                    motorista.vinculo_pessoa.pessoa.nome,
                                    tem_campus,
                                    motorista.get_matricula_servidor(),
                                    motorista.portaria_mais_recente().portaria,
                                    motorista.portaria_mais_recente().validade_inicial,
                                    motorista.portaria_mais_recente().validade_final,
                                ]
                            )
                    tabela_dados = relatorios.table(dados, head=1, zebra=1, w=[50, 20, 20, 30, 20, 20], count=0)
                else:
                    topo = relatorios.get_topo_pdf('Relatório de Motoristas Temporários com Portaria em Vigor - Terceirizados')
                    dados = [['Nome', 'Campus', 'Portaria', 'Data Inicial', 'Data Final']]
                    for motorista in motorista_terceirizado:
                        adicionar = False
                        if not motorista.portaria_mais_recente().validade_final:
                            adicionar = True
                        else:
                            if motorista.portaria_mais_recente().validade_final > datetime.datetime.today().date():
                                adicionar = True
                        if adicionar:
                            tem_campus = '-'
                            if get_uo(motorista.vinculo_pessoa.user):
                                tem_campus = get_uo(motorista.vinculo_pessoa.user)
                            dados.append(
                                [
                                    motorista.vinculo_pessoa.pessoa.nome,
                                    tem_campus,
                                    motorista.portaria_mais_recente().portaria,
                                    motorista.portaria_mais_recente().validade_inicial,
                                    motorista.portaria_mais_recente().validade_final,
                                ]
                            )

                    tabela_dados = relatorios.table(dados, head=1, zebra=1, w=[50, 20, 30, 20, 20], count=0)

                total = len(dados) - 1
                info = [['Data', hoje], ['N° de Registros', str(total)]]
                tabela_info = relatorios.table(info, grid=0, w=[30, 160], auto_align=0)
                body = [*topo, tabela_info, relatorios.space(8), tabela_dados]
                dados = sorted(dados, key=lambda x: x[0])

                return PDFResponse(relatorios.PdfReport(body=body).generate())
            else:
                return locals()
    return locals()


@rtr()
@permission_required(['frota.tem_acesso_viatura_sistemico', 'frota.tem_acesso_viatura_campus'])
def relatorio_deslocamento_por_viatura(request):
    title = 'Relatório de Consumo Estimado por Viatura'
    buscou = False
    hoje = datetime.datetime.today()
    data_inicio = somar_dias(hoje, -30)
    data_termino = hoje
    if request.method == 'GET' and 'data_inicio' not in request.GET:
        form = FiltroViaturaForm(request=request)
        form.fields['data_inicio'].initial = data_inicio
        form.fields['data_termino'].initial = data_termino
    else:
        form = FiltroViaturaForm(request.GET, request=request)
        if form.is_valid():
            buscou = True
            data_inicio = form.cleaned_data['data_inicio']
            data_termino = form.cleaned_data['data_termino']
            viatura = form.cleaned_data['viatura']
            campus = form.cleaned_data['uo']
            salvar_pdf = 'pdf' in request.GET
            data_inicio_str = data_inicio.strftime('%d/%m/%Y')
            data_termino_str = data_termino.strftime('%d/%m/%Y')
            hoje = datetime.datetime.today().strftime('%d/%m/%Y')
            data_inicio_sql = calendario.somar_dias(data_inicio, -1)
            data_termino_sql = calendario.somar_dias(data_termino, +1)
            if viatura:
                viagens_no_periodo = Viagem.objects.filter(
                    viatura=viatura, saida_data__gt=data_inicio_sql, chegada_data__lt=data_termino_sql
                ).values_list('viatura', flat=True)
            else:
                if campus:
                    viagens_no_periodo = Viagem.objects.filter(
                        viatura__campus=campus, saida_data__gt=data_inicio_sql, chegada_data__lt=data_termino_sql
                    ).values_list('viatura', flat=True)
                else:
                    viagens_no_periodo = Viagem.objects.filter(saida_data__gt=data_inicio_sql, chegada_data__lt=data_termino_sql).values_list(
                        'viatura', flat=True
                    )
            rs_viatura = Viatura.objects.filter(id__in=viagens_no_periodo)
            rs_viatura = rs_viatura.values('id')
            total = 0
            uo = request.user.get_vinculo().setor.uo
            topo = relatorios.get_topo_pdf(title)
            servidor = request.user.get_relacionamento()
            dados = [['Viatura', 'Combustível', 'Km Rodados', 'Consumo (L)', '(Km/L)', 'Total (R$)']]

            for registro in rs_viatura:
                viatura_id = registro['id']
                viatura = Viatura.objects.get(pk=viatura_id)
                rs_tipo_combustivel = []
                veiculos = Veiculo.objects.filter(viatura=viatura)
                rs_deslocamento = (
                    Viagem.objects.filter(viatura=viatura, saida_data__gt=data_inicio_sql, chegada_data__lt=data_termino_sql)
                    .annotate(distancia=F('chegada_odometro') - F('saida_odometro'))
                    .aggregate(deslocamento=Sum('distancia'))
                )
                rs_consumo_combustivel = ViaturaOrdemAbastecimento.objects.filter(
                    viatura=viatura, data__gt=data_inicio_sql, data__lt=data_termino_sql
                ).aggregate(total=Sum('quantidade'))
                rs_custo_total = ViaturaOrdemAbastecimento.objects.filter(
                    viatura=viatura, data__gt=data_inicio_sql, data__lt=data_termino_sql
                ).aggregate(custo=Sum('valor_total_nf'))

                custo_total = 0
                deslocamento = 0
                consumo_combustivel = 0
                deslocamento_por_litro = 0
                custo_por_km_rodado = 0
                custo_por_litro = 0
                if rs_custo_total and rs_custo_total['custo']:
                    custo_total = rs_custo_total['custo']
                if rs_deslocamento and rs_deslocamento['deslocamento']:
                    deslocamento = rs_deslocamento['deslocamento']
                if rs_consumo_combustivel and rs_consumo_combustivel['total']:
                    consumo_combustivel = rs_consumo_combustivel['total']
                if consumo_combustivel != 0:
                    deslocamento_por_litro = deslocamento / consumo_combustivel
                total += custo_total
                nome_viatura = viatura.modelo.nome + ' (' + viatura.placa_codigo_atual + ')'

                dados.append(
                    [
                        nome_viatura,
                        viatura.combustiveis.all()[0].nome,
                        deslocamento,
                        f'{consumo_combustivel:0.2f}',
                        f'{deslocamento_por_litro:0.2f}',
                        mascara_dinheiro(f'{custo_total:0.2f}'),
                    ]
                )
            dados.append(['Total ', ' ', ' ', ' ', ' ', mascara_dinheiro(f'{total:0.2f}')])
            info = [
                ['Data', hoje],
                ['Período', data_inicio.strftime('%d/%m/%Y') + ' - ' + data_termino.strftime('%d/%m/%Y')],
                ['Quantidade de Viagens', rs_viatura.count()],
                ['Total', mascara_dinheiro(f'{total:0.2f}')],
            ]
            tabela_info = relatorios.table(info, grid=0, w=[30, 160], auto_align=0)
            tabela_dados = relatorios.table(dados, head=1, zebra=1, w=[40, 25, 20, 30, 20, 20], count=0)
            body = [*topo, tabela_info, relatorios.space(8), tabela_dados]
            if salvar_pdf:
                return PDFResponse(relatorios.PdfReport(body=body).generate())
            else:
                return locals()
    return locals()


@rtr()
@permission_required(['frota.tem_acesso_maquina_sistemico', 'frota.tem_acesso_maquina_campus'])
def relatorio_consumo_por_maquina(request):
    title = 'Relatório de Consumo Estimado por Máquina'
    buscou = False
    hoje = datetime.datetime.today()
    data_inicio = somar_dias(hoje, -30)
    data_termino = hoje
    if request.method == 'GET' and 'data_inicio' not in request.GET:
        form = FiltroMaquinaForm(request=request)
        form.fields['data_inicio'].initial = data_inicio
        form.fields['data_termino'].initial = data_termino
    else:
        form = FiltroMaquinaForm(request.GET or None, request=request)
        if form.is_valid():
            buscou = True
            data_inicio = form.cleaned_data['data_inicio']
            data_termino = form.cleaned_data['data_termino']
            campus = form.cleaned_data['uo']
            salvar_pdf = 'pdf' in request.GET
            data_inicio_str = data_inicio.strftime('%d/%m/%Y')
            data_termino_str = data_termino.strftime('%d/%m/%Y')
            hoje = datetime.datetime.today().strftime('%d/%m/%Y')
            data_inicio_sql = calendario.somar_dias(data_inicio, -1)
            data_termino_sql = calendario.somar_dias(data_termino, +1)
            ordens_no_periodo = MaquinaOrdemAbastecimento.objects.filter(data__gt=data_inicio_sql, data__lt=data_termino_sql)
            maquinas = Maquina.objects.filter(id__in=ordens_no_periodo.values_list('maquina', flat=True))

            if campus:
                maquinas = maquinas.filter(campus=campus)

            total = 0
            uo = request.user.get_vinculo().setor.uo
            topo = relatorios.get_topo_pdf(title)
            servidor = request.user.get_relacionamento()
            dados = [['Máquina', 'Combustível', 'Consumo (L)', 'Total (R$)']]

            for maquina in maquinas:
                rs_tipo_combustivel = []

                rs_custo_total = MaquinaOrdemAbastecimento.objects.filter(
                    maquina=maquina, data__gt=data_inicio_sql, data__lt=data_termino_sql
                ).aggregate(custo=Sum('valor_total_nf'))
                rs_consumo_combustivel = MaquinaOrdemAbastecimento.objects.filter(
                    maquina=maquina, data__gt=data_inicio_sql, data__lt=data_termino_sql
                ).aggregate(total=Sum('quantidade'))
                custo_total = 0
                consumo_combustivel = 0

                if rs_custo_total and rs_custo_total['custo']:
                    custo_total = rs_custo_total['custo']

                if rs_consumo_combustivel and rs_consumo_combustivel['total']:
                    consumo_combustivel = rs_consumo_combustivel['total']

                total += custo_total

                dados.append(
                    [
                        maquina,
                        maquina.combustiveis.all()[0].nome,
                        f'{consumo_combustivel:0.2f}',
                        mascara_dinheiro(f'{custo_total:0.2f}'),
                    ]
                )
            dados.append(['Total ', ' ', ' ', mascara_dinheiro(f'{total:0.2f}')])
            info = [
                ['Data', hoje],
                ['Período', data_inicio.strftime('%d/%m/%Y') + ' - ' + data_termino.strftime('%d/%m/%Y')],
                ['Total', mascara_dinheiro(f'{total:0.2f}')],
            ]
            tabela_info = relatorios.table(info, grid=0, w=[30, 160], auto_align=0)
            tabela_dados = relatorios.table(dados, head=1, zebra=1, w=[40, 25, 20, 30], count=0)
            body = [*topo, tabela_info, relatorios.space(8), tabela_dados]
            if salvar_pdf:
                return PDFResponse(relatorios.PdfReport(body=body).generate())
            else:
                return locals()
    return locals()


@rtr()
@permission_required(['frota.tem_acesso_viagem_sistemico', 'frota.tem_acesso_viagem_campus'])
def relatorio_viagens_por_motorista(request):
    title = 'Relatório de Viagens por Motorista'
    hoje = datetime.datetime.today()
    data_inicio = somar_dias(hoje, -30)
    data_termino = hoje
    if request.method == 'GET' and 'data_inicio' not in request.GET:
        form = ViagemMotoristaForm(request=request)
        form.fields['data_inicio'].initial = data_inicio
        form.fields['data_termino'].initial = data_termino
    else:
        form = ViagemMotoristaForm(request.GET or None, request=request)
        if form.is_valid():
            buscou = True
            data_inicio = form.cleaned_data['data_inicio']
            data_termino = form.cleaned_data['data_termino']
            campus = form.cleaned_data['uo']
            motorista = form.cleaned_data['motorista']
            quantidade_diarias = form.cleaned_data['quantidade_diarias']
            salvar_pdf = 'pdf' in request.GET
            data_inicio_str = data_inicio.strftime('%d/%m/%Y')
            data_termino_str = data_termino.strftime('%d/%m/%Y')
            hoje = datetime.datetime.today().strftime('%d/%m/%Y')

            if motorista.vinculo_pessoa.eh_servidor() or motorista.vinculo_pessoa.eh_prestador():
                viagens = Viagem.objects.filter(saida_data__gt=data_inicio, chegada_data__lt=data_termino, motoristas=motorista.vinculo_pessoa)
            if campus:
                viagens = viagens.filter(agendamento_resposta__agendamento__setor__uo=campus)

            if quantidade_diarias:
                viagens = viagens.filter(agendamento_resposta__agendamento__quantidade_diarias=quantidade_diarias)

            total = 0
            uo = request.user.get_vinculo().setor.uo
            topo = relatorios.get_topo_pdf(title)
            servidor = request.user.get_relacionamento()
            dados = [['Campus', 'ID da Viagem', 'Viatura', 'Solicitante', 'Motoristas', 'Situação', 'Período', 'Itinerário']]

            for viagem in viagens:
                if viagem.chegada_data is None:
                    situacao = 'Em andamento'
                else:
                    situacao = 'Concluída'

                uo_viatura = '-'
                if viagem.viatura.campus:
                    uo_viatura = viagem.viatura.campus
                periodo = '{} - {}'.format(viagem.saida_data.strftime('%d/%m/%y'), viagem.chegada_data.strftime('%d/%m/%y'))
                dados.append(
                    [
                        uo_viatura,
                        viagem.agendamento_resposta.agendamento.id,
                        viagem.viatura,
                        viagem.agendamento_resposta.agendamento.vinculo_solicitante.pessoa.nome,
                        viagem.get_motoristas(),
                        situacao,
                        periodo,
                        viagem.agendamento_resposta.agendamento.intinerario,
                    ]
                )
            info = [
                ['Data de Emissão', hoje],
                ['Motorista', motorista],
                ['Período das viagens', data_inicio.strftime('%d/%m/%Y') + ' - ' + data_termino.strftime('%d/%m/%Y')],
            ]
            tabela_info = relatorios.table(info, grid=0, w=[30, 160], auto_align=0)
            tabela_dados = relatorios.table(dados, head=1, zebra=1, w=[12, 20, 40, 30, 30, 20, 20, 30], count=0)
            body = [*topo, tabela_info, relatorios.space(8), tabela_dados]
            if salvar_pdf:
                return PDFResponse(relatorios.PdfReport(body=body).generate())
            else:
                return locals()
    return locals()
