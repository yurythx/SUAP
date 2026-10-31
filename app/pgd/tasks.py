from datetime import date

from dateutil.relativedelta import relativedelta

from djtools.assincrono import task
from djtools.utils import render_html_file
from pgd.models import DesligamentoPgdServidor, RegistroAcaoSolicitacaoAdesaoServidor, SolicitacaoAdesaoServidor
from rh.models import Servidor, UnidadeOrganizacional


@task('Relatório de Participantes do PGD com desligamento')
def gerar_relatorio_participantes_desligamento(mes_ini, ano_ini, mes_fim, ano_fim, request, task=None):
    lista_dados_periodo = []
    lista_dados = []
    dict_consolidado_uos = {}

    # ---------------------------
    # Dados iniciais
    # ---------------------------
    servidores_pgd_adesao_deferida = SolicitacaoAdesaoServidor.get_servidores_com_adesao_deferida()
    servidores_pgd_desligados = SolicitacaoAdesaoServidor.get_servidores_desligados()
    campis = UnidadeOrganizacional.objects.uo()

    # Obtendo os periodos conforme periodo inicial e final passados como parametro
    data_inicio = date(ano_ini, mes_ini, 1)
    data_final = date(ano_fim, mes_fim, 1)
    periodos = []
    if data_inicio and data_final:
        if data_inicio == data_final:
            periodos.append(data_inicio)
        else:
            parar = False
            d = data_inicio
            periodos.append(d)
            while not parar:
                d = d + relativedelta(months=1)
                periodos.append(d)
                if d.month == data_final.month and d.year == data_final.year:
                    parar = True

    def adesoes_deferidas_periodo(mes=None, ano=None, uo=None):
        ad = servidores_pgd_adesao_deferida
        if mes and ano:
            ids_servidores_adesoes_periodo = RegistroAcaoSolicitacaoAdesaoServidor.objects.filter(
                data__month=mes, data__year=ano, tipo=RegistroAcaoSolicitacaoAdesaoServidor.TIPO_DEFERIDO
            ).values_list('solicitacao__servidor_id')
            ad = ad.filter(id__in=ids_servidores_adesoes_periodo)
        if uo:
            ad = ad.filter(setor__uo=uo)
        return ad

    def desligamentos_voluntarios_periodo(mes=None, ano=None, uo=None):
        ids_servidores = []
        if mes and ano:
            ids_servidores = DesligamentoPgdServidor.objects.filter(
                adesao__servidor__in=servidores_pgd_desligados,
                data_desligamento_efeitos_a_partir_de__month=mes,
                data_desligamento_efeitos_a_partir_de__year=ano,
                data_cancelamento__isnull=True,
                justificativa__qtd_dias_punicao=0,
            ).values_list('adesao__servidor_id')
        ids_servidores = DesligamentoPgdServidor.objects.filter(
            adesao__servidor__in=servidores_pgd_desligados, data_cancelamento__isnull=True, justificativa__qtd_dias_punicao=0
        ).values_list('adesao__servidor_id')
        if uo:
            return Servidor.objects.vinculados().filter(id__in=ids_servidores, setor__uo=uo)
        return Servidor.objects.vinculados().filter(id__in=ids_servidores)

    def desligamentos_punicao_periodo(mes=None, ano=None, uo=None):
        ids_servidores = []
        if mes and ano:
            ids_servidores = DesligamentoPgdServidor.objects.filter(
                adesao__servidor__in=servidores_pgd_desligados,
                data_desligamento_efeitos_a_partir_de__month=mes,
                data_desligamento_efeitos_a_partir_de__year=ano,
                data_cancelamento__isnull=True,
                justificativa__qtd_dias_punicao__gt=0,
            ).values_list('adesao__servidor_id')
        ids_servidores = DesligamentoPgdServidor.objects.filter(
            adesao__servidor__in=servidores_pgd_desligados, data_cancelamento__isnull=True, justificativa__qtd_dias_punicao__gt=0
        ).values_list('adesao__servidor_id')
        if uo:
            return Servidor.objects.vinculados().filter(id__in=ids_servidores, setor__uo=uo)
        return Servidor.objects.vinculados().filter(id__in=ids_servidores)

    # ---------------------------
    # Quando tem os períodos como parametro
    # - Dados por periodo
    # - Dados consolidados do periodo
    # ---------------------------
    if periodos:
        # Estruturas de somatório
        dict_consolidado = {
            'ifrn_adesoes': 0,
            'ifrn_desligamento_voluntario': 0,
            'ifrn_desligamento_penalidade': 0,
            'tae_adesoes': 0,
            'tae_desligamento_voluntario': 0,
            'tae_desligamento_penalidade': 0,
            'docente_adesoes': 0,
            'docente_desligamento_voluntario': 0,
            'docente_desligamento_penalidade': 0,
            'estagiario_adesoes': 0,
            'estagiario_desligamento_voluntario': 0,
            'estagiario_desligamento_penalidade': 0,
        }
        for campus in campis:
            dict_consolidado_uos[campus.sigla] = {
                'ifrn_adesoes': 0,
                'ifrn_desligamento_voluntario': 0,
                'ifrn_desligamento_penalidade': 0,
                'tae_adesoes': 0,
                'tae_desligamento_voluntario': 0,
                'tae_desligamento_penalidade': 0,
                'docente_adesoes': 0,
                'docente_desligamento_voluntario': 0,
                'docente_desligamento_penalidade': 0,
                'estagiario_adesoes': 0,
                'estagiario_desligamento_voluntario': 0,
                'estagiario_desligamento_penalidade': 0,
            }

        for periodo in task.iterate(periodos):
            lista_dados = []

            # ---------------------------
            # Dados por periodo
            # ---------------------------
            dict_dados = {}
            dict_dados['descricao'] = '1 - COLABORADORES DO IFRN'
            dict_dados['adesoes'] = adesoes_deferidas_periodo(periodo.month, periodo.year).count()
            dict_dados['desligamento_voluntario'] = desligamentos_voluntarios_periodo(periodo.month, periodo.year).count()
            dict_dados['desligamento_penalidade'] = desligamentos_punicao_periodo(periodo.month, periodo.year).count()
            lista_dados.append(dict_dados)
            dict_consolidado['ifrn_adesoes'] += dict_dados['adesoes']
            dict_consolidado['ifrn_desligamento_voluntario'] += dict_dados['desligamento_voluntario']
            dict_consolidado['ifrn_desligamento_penalidade'] += dict_dados['desligamento_penalidade']

            dict_dados = {}
            dict_dados['descricao'] = '1.1 - TÉCNICO ADMINISTRATIVO'
            dict_dados['adesoes'] = adesoes_deferidas_periodo(periodo.month, periodo.year).tecnicos_administrativos().count()
            dict_dados['desligamento_voluntario'] = desligamentos_voluntarios_periodo(periodo.month, periodo.year).tecnicos_administrativos().count()
            dict_dados['desligamento_penalidade'] = desligamentos_punicao_periodo(periodo.month, periodo.year).tecnicos_administrativos().count()
            lista_dados.append(dict_dados)
            dict_consolidado['tae_adesoes'] += dict_dados['adesoes']
            dict_consolidado['tae_desligamento_voluntario'] += dict_dados['desligamento_voluntario']
            dict_consolidado['tae_desligamento_penalidade'] += dict_dados['desligamento_penalidade']

            dict_dados = {}
            dict_dados['descricao'] = '1.2 - DOCENTE'
            dict_dados['adesoes'] = adesoes_deferidas_periodo(periodo.month, periodo.year).docentes().count()
            dict_dados['desligamento_voluntario'] = desligamentos_voluntarios_periodo(periodo.month, periodo.year).docentes().count()
            dict_dados['desligamento_penalidade'] = desligamentos_punicao_periodo(periodo.month, periodo.year).docentes().count()
            lista_dados.append(dict_dados)
            dict_consolidado['docente_adesoes'] += dict_dados['adesoes']
            dict_consolidado['docente_desligamento_voluntario'] += dict_dados['desligamento_voluntario']
            dict_consolidado['docente_desligamento_penalidade'] += dict_dados['desligamento_penalidade']

            dict_dados = {}
            dict_dados['descricao'] = '1.3 - ESTAGIÁRIO'
            dict_dados['adesoes'] = adesoes_deferidas_periodo(periodo.month, periodo.year).estagiarios().count()
            dict_dados['desligamento_voluntario'] = desligamentos_voluntarios_periodo(periodo.month, periodo.year).estagiarios().count()
            dict_dados['desligamento_penalidade'] = desligamentos_punicao_periodo(periodo.month, periodo.year).estagiarios().count()
            lista_dados.append(dict_dados)
            dict_consolidado['estagiario_adesoes'] += dict_dados['adesoes']
            dict_consolidado['estagiario_desligamento_voluntario'] += dict_dados['desligamento_voluntario']
            dict_consolidado['estagiario_desligamento_penalidade'] += dict_dados['desligamento_penalidade']

            # Por campus
            # --------------------
            for campus in campis:
                dict_dados = {}
                dict_dados['descricao'] = campus
                lista_dados.append(dict_dados)

                dict_dados = {}
                dict_dados['descricao'] = '1 - COLABORADORES DO CAMPUS'
                dict_dados['adesoes'] = adesoes_deferidas_periodo(periodo.month, periodo.year, uo=campus).count()
                dict_dados['desligamento_voluntario'] = desligamentos_voluntarios_periodo(periodo.month, periodo.year, uo=campus).count()
                dict_dados['desligamento_penalidade'] = desligamentos_punicao_periodo(periodo.month, periodo.year, uo=campus).count()
                lista_dados.append(dict_dados)
                dict_consolidado_uos[campus.sigla]['ifrn_adesoes'] += dict_dados['adesoes']
                dict_consolidado_uos[campus.sigla]['ifrn_desligamento_voluntario'] += dict_dados['desligamento_voluntario']
                dict_consolidado_uos[campus.sigla]['ifrn_desligamento_penalidade'] += dict_dados['desligamento_penalidade']

                dict_dados = {}
                dict_dados['descricao'] = '1.1 - TÉCNICO ADMINISTRATIVO'
                dict_dados['adesoes'] = adesoes_deferidas_periodo(periodo.month, periodo.year, uo=campus).tecnicos_administrativos().count()
                dict_dados['desligamento_voluntario'] = (
                    desligamentos_voluntarios_periodo(periodo.month, periodo.year, uo=campus).tecnicos_administrativos().count()
                )
                dict_dados['desligamento_penalidade'] = (
                    desligamentos_punicao_periodo(periodo.month, periodo.year, uo=campus).tecnicos_administrativos().count()
                )
                lista_dados.append(dict_dados)
                dict_consolidado_uos[campus.sigla]['tae_adesoes'] += dict_dados['adesoes']
                dict_consolidado_uos[campus.sigla]['tae_desligamento_voluntario'] += dict_dados['desligamento_voluntario']
                dict_consolidado_uos[campus.sigla]['tae_desligamento_penalidade'] += dict_dados['desligamento_penalidade']

                dict_dados = {}
                dict_dados['descricao'] = '1.2 - DOCENTE'
                dict_dados['adesoes'] = adesoes_deferidas_periodo(periodo.month, periodo.year, uo=campus).docentes().count()
                dict_dados['desligamento_voluntario'] = desligamentos_voluntarios_periodo(periodo.month, periodo.year, uo=campus).docentes().count()
                dict_dados['desligamento_penalidade'] = desligamentos_punicao_periodo(periodo.month, periodo.year, uo=campus).docentes().count()
                lista_dados.append(dict_dados)
                dict_consolidado_uos[campus.sigla]['docente_adesoes'] += dict_dados['adesoes']
                dict_consolidado_uos[campus.sigla]['docente_desligamento_voluntario'] += dict_dados['desligamento_voluntario']
                dict_consolidado_uos[campus.sigla]['docente_desligamento_penalidade'] += dict_dados['desligamento_penalidade']

                dict_dados = {}
                dict_dados['descricao'] = '1.3 - ESTAGIÁRIO'
                dict_dados['adesoes'] = adesoes_deferidas_periodo(periodo.month, periodo.year, uo=campus).estagiarios().count()
                dict_dados['desligamento_voluntario'] = (
                    desligamentos_voluntarios_periodo(periodo.month, periodo.year, uo=campus).estagiarios().count()
                )
                dict_dados['desligamento_penalidade'] = desligamentos_punicao_periodo(periodo.month, periodo.year, uo=campus).estagiarios().count()
                lista_dados.append(dict_dados)
                dict_consolidado_uos[campus.sigla]['estagiario_adesoes'] += dict_dados['adesoes']
                dict_consolidado_uos[campus.sigla]['estagiario_desligamento_voluntario'] += dict_dados['desligamento_voluntario']
                dict_consolidado_uos[campus.sigla]['estagiario_desligamento_penalidade'] += dict_dados['desligamento_penalidade']

            dict_dados_periodo = {}
            dict_dados_periodo['periodo'] = f'{periodo.month}/{periodo.year}'
            dict_dados_periodo['dados'] = lista_dados
            lista_dados_periodo.append(dict_dados_periodo)

        # ---------------------------
        # Dados consolidados do periodo
        # ---------------------------
        lista_dados = []

        dict_dados = {}
        dict_dados['descricao'] = '1 - COLABORADORES DO IFRN'
        dict_dados['adesoes'] = dict_consolidado['ifrn_adesoes']
        dict_dados['desligamento_voluntario'] = dict_consolidado['ifrn_desligamento_voluntario']
        dict_dados['desligamento_penalidade'] = dict_consolidado['ifrn_desligamento_penalidade']
        lista_dados.append(dict_dados)

        dict_dados = {}
        dict_dados['descricao'] = '1.1 - TÉCNICO ADMINISTRATIVO'
        dict_dados['adesoes'] = dict_consolidado['tae_adesoes']
        dict_dados['desligamento_voluntario'] = dict_consolidado['tae_desligamento_voluntario']
        dict_dados['desligamento_penalidade'] = dict_consolidado['tae_desligamento_penalidade']
        lista_dados.append(dict_dados)

        dict_dados = {}
        dict_dados['descricao'] = '1.2 - DOCENTE'
        dict_dados['adesoes'] = dict_consolidado['docente_adesoes']
        dict_dados['desligamento_voluntario'] = dict_consolidado['docente_desligamento_voluntario']
        dict_dados['desligamento_penalidade'] = dict_consolidado['docente_desligamento_penalidade']
        lista_dados.append(dict_dados)

        dict_dados = {}
        dict_dados['descricao'] = '1.3 - ESTAGIÁRIO'
        dict_dados['adesoes'] = dict_consolidado['estagiario_adesoes']
        dict_dados['desligamento_voluntario'] = dict_consolidado['estagiario_desligamento_voluntario']
        dict_dados['desligamento_penalidade'] = dict_consolidado['estagiario_desligamento_penalidade']
        lista_dados.append(dict_dados)

        # Por campus
        # --------------------
        for campus in task.iterate(campis):
            dict_dados = {}
            dict_dados['descricao'] = campus
            lista_dados.append(dict_dados)

            dict_dados = {}
            dict_dados['descricao'] = '1 - COLABORADORES DO CAMPUS'
            dict_dados['adesoes'] = dict_consolidado_uos[campus.sigla]['ifrn_adesoes']
            dict_dados['desligamento_voluntario'] = dict_consolidado_uos[campus.sigla]['ifrn_desligamento_voluntario']
            dict_dados['desligamento_penalidade'] = dict_consolidado_uos[campus.sigla]['ifrn_desligamento_penalidade']
            lista_dados.append(dict_dados)

            dict_dados = {}
            dict_dados['descricao'] = '1.1 - TÉCNICO ADMINISTRATIVO'
            dict_dados['adesoes'] = dict_consolidado_uos[campus.sigla]['tae_adesoes']
            dict_dados['desligamento_voluntario'] = dict_consolidado_uos[campus.sigla]['tae_desligamento_voluntario']
            dict_dados['desligamento_penalidade'] = dict_consolidado_uos[campus.sigla]['tae_desligamento_penalidade']
            lista_dados.append(dict_dados)

            dict_dados = {}
            dict_dados['descricao'] = '1.2 - DOCENTE'
            dict_dados['adesoes'] = dict_consolidado_uos[campus.sigla]['docente_adesoes']
            dict_dados['desligamento_voluntario'] = dict_consolidado_uos[campus.sigla]['docente_desligamento_voluntario']
            dict_dados['desligamento_penalidade'] = dict_consolidado_uos[campus.sigla]['docente_desligamento_penalidade']
            lista_dados.append(dict_dados)

            dict_dados = {}
            dict_dados['descricao'] = '1.3 - ESTAGIÁRIO'
            dict_dados['adesoes'] = dict_consolidado_uos[campus.sigla]['estagiario_adesoes']
            dict_dados['desligamento_voluntario'] = dict_consolidado_uos[campus.sigla]['estagiario_desligamento_voluntario']
            dict_dados['desligamento_penalidade'] = dict_consolidado_uos[campus.sigla]['estagiario_desligamento_penalidade']
            lista_dados.append(dict_dados)

        dict_dados_periodo = {}
        dict_dados_periodo['periodo'] = 'Consolidado'
        dict_dados_periodo['dados'] = lista_dados
        lista_dados_periodo.append(dict_dados_periodo)

    title = f'Relatório de Participantes do PGD com desligamento (Por período, categoria e campus) - {mes_ini}/{ano_ini} a {mes_fim}/{ano_fim}'

    return render_html_file('pgd/templates/relatorio_participantes_desligamento.html', locals(), request, task)
