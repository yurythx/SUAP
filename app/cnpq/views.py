import datetime

import mechanicalsoup
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.db.models import Q, QuerySet
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.html import strip_tags

from cnpq import tasks
from cnpq.forms import (
    CATEGORIA_CHOICES,
    AnoResumoForm,
    CampusForm,
    ImportarListaCompletaForm,
    IndicadoresForm,
    PeriodicoRevistaForm,
    ProducaoCampusForm,
    ProducaoServidorForm,
    ServidoresSemLattesForm,
    TitulacaoForm,
)
from cnpq.management.commands import cnpq_importar
from cnpq.models import (
    CurriculoVittaeLattes,
    GrupoPesquisa,
    OrientacaoAndamento,
    OrientacaoConcluida,
    Parametro,
    PeriodicoRevista,
    ProducaoBibliografica,
    ProducaoTecnica,
    RegistroPatente,
)
from comum.models import Configuracao
from djtools.html.graficos import ColumnChart, GroupedColumnChart, PieChart
from djtools.storages import get_temp_storage
from djtools.templatetags.filters import format_
from djtools.utils import Relatorio, XlsResponse, httprr, permission_required, rtr
from rh.models import Servidor


@rtr()
@permission_required('cnpq.pode_ver_relatorios, rh.eh_servidor')
def index(request):
    title = 'Indicadores'

    form = IndicadoresForm(request.GET, request=request)
    form.is_valid()

    categoria = form.cleaned_data.get('categoria')
    campus = form.cleaned_data.get('campus')
    publicacao = form.cleaned_data.get('publicacao')
    tipo_publicacao = form.cleaned_data.get('tipo_publicacao')
    ano_ini = form.cleaned_data.get('ano_ini')
    ano_fim = form.cleaned_data.get('ano_fim')
    natureza_evento = form.cleaned_data.get('natureza_evento')
    classificacao_evento = form.cleaned_data.get('classificacao_trab')
    qualis_capes = form.cleaned_data.get('qualis_capes')
    servidor = form.cleaned_data.get('servidor')
    aluno = form.cleaned_data.get('aluno')
    grupo_pesquisa = form.cleaned_data.get('grupo_pesquisa')
    programa_posgraduacao = form.cleaned_data.get('programa_posgraduacao')
    apenas_no_exercicio = form.cleaned_data.get('apenas_no_exercicio')

    if publicacao:
        titulo_grafico = dict(form.PUBLICACOES_CHOICES)[publicacao]
        classe = form.get_classe()
        tipo_publicacao_choices = form.get_tipo_publicacao_choices()
        atributo_tipo = form.get_atributo_tipo_publicacao()
        modelos = classe.filtrar(
            tipo_publicacao,
            categoria,
            campus,
            ano_ini,
            ano_fim,
            natureza_evento,
            classificacao_evento,
            qualis_capes,
            servidor,
            grupo_pesquisa,
            apenas_no_exercicio,
        )
        dados_agrupados = classe.get_ano_tipo_qtd(
            tipo_publicacao,
            categoria,
            campus,
            ano_ini,
            ano_fim,
            natureza_evento,
            classificacao_evento,
            qualis_capes,
            servidor,
            grupo_pesquisa,
            apenas_no_exercicio,
        )

        groups = []
        data_anos_qtd_grouped = Relatorio.get_dados_em_coluna_linha(dados_agrupados, groups, atributo_tipo, 'ano', 'qtd')
        for i, v in enumerate(groups):
            groups[i] = tipo_publicacao_choices[v]

        data_anos_qtd_serie = []
        Relatorio.adiciona_e_totaliza_coluna(data_anos_qtd_grouped)
        if data_anos_qtd_grouped:
            # Soma a quantidade e gera uma coluna com o total
            Relatorio.adiciona_nova_coluna(data_anos_qtd_serie, data_anos_qtd_grouped, {1: len(data_anos_qtd_grouped[0]) - 1}, 2)

        if publicacao == form.REGISTRO_PATENTE:
            data_anos_qtd_serie = Relatorio.ordernar(data_anos_qtd_serie)
            data_anos_qtd_grouped = Relatorio.ordernar(data_anos_qtd_grouped)

        # contrução dos gráficos
        graficos = []
        graficos.append(ColumnChart('grafico1', title=titulo_grafico, minPointLength=3, data=data_anos_qtd_serie))

        graficos.append(GroupedColumnChart('grafico2', title=titulo_grafico, minPointLength=3, data=data_anos_qtd_grouped, groups=groups))

        if 'xls' in request.GET:
            return tasks.exportar_indicadores_com_publicacao_xls(modelos)

        titulo_box = []
        titulo_box.append(dict(form.PUBLICACOES_CHOICES)[publicacao])
        if tipo_publicacao:
            titulo_box.append(tipo_publicacao_choices[tipo_publicacao])
        if categoria:
            titulo_box.append(dict(CATEGORIA_CHOICES)[categoria])
        if campus:
            titulo_box.append(str(campus))
        if ano_ini and ano_fim:
            titulo_box.append(f'{ano_ini} a {ano_fim}')
        elif ano_ini:
            titulo_box.append(f'a partir de {ano_ini}')
        elif ano_fim:
            titulo_box.append(f'até {ano_fim}')

        titulo_box = ' - '.join(titulo_box)

    else:
        if 'xls' in request.GET:
            producoes_bibliograficas = ProducaoBibliografica.filtrar(
                categoria=categoria, campus=campus, grupo_pesquisa=grupo_pesquisa, programa_posgraduacao=programa_posgraduacao
            )
            producoes_tecnicas = ProducaoTecnica.filtrar(
                categoria=categoria, campus=campus, grupo_pesquisa=grupo_pesquisa, programa_posgraduacao=programa_posgraduacao
            )
            orientacoes_antamento = OrientacaoAndamento.filtrar(
                categoria=categoria, campus=campus, grupo_pesquisa=grupo_pesquisa, programa_posgraduacao=programa_posgraduacao
            )
            orientacoes_concluidas = OrientacaoConcluida.filtrar(
                categoria=categoria, campus=campus, grupo_pesquisa=grupo_pesquisa, programa_posgraduacao=programa_posgraduacao
            )
            registros_patentes = RegistroPatente.filtrar(
                categoria=categoria, campus=campus, grupo_pesquisa=grupo_pesquisa, programa_posgraduacao=programa_posgraduacao
            )

            if servidor:
                producoes_bibliograficas = producoes_bibliograficas.filter(curriculo__vinculo=servidor.get_vinculo())
                producoes_tecnicas = producoes_tecnicas.filter(curriculo__vinculo=servidor.get_vinculo())
                orientacoes_antamento = orientacoes_antamento.filter(dado_complementar__curriculovittaelattes__vinculo=servidor.get_vinculo())
                orientacoes_concluidas = orientacoes_concluidas.filter(curriculo__vinculo=servidor.get_vinculo())
                registros_patentes = registros_patentes.filter(curriculo__vinculo=servidor.get_vinculo())

            if aluno:
                producoes_bibliograficas = producoes_bibliograficas.filter(curriculo__vinculo=aluno.get_vinculo())
                producoes_tecnicas = producoes_tecnicas.filter(curriculo__vinculo=aluno.get_vinculo())
                orientacoes_antamento = orientacoes_antamento.filter(dado_complementar__curriculovittaelattes__vinculo=aluno.get_vinculo())
                orientacoes_concluidas = orientacoes_concluidas.filter(curriculo__vinculo=aluno.get_vinculo())
                registros_patentes = registros_patentes.filter(curriculo__vinculo=aluno.get_vinculo())

            dados = {}
            dados['Produções Bibliográficas'] = producoes_bibliograficas
            dados['Produções Técnicas'] = producoes_tecnicas
            dados['Orientações em Andamento'] = orientacoes_antamento
            dados['Orientações Concluídas'] = orientacoes_concluidas
            dados['Registros e Patentes'] = registros_patentes

            exibir_alerta_tamanho_maximo = False
            total = producoes_bibliograficas.count()
            if producoes_bibliograficas.count() > 65000:
                exibir_alerta_tamanho_maximo = True
            total += producoes_tecnicas.count()
            if producoes_tecnicas.count() > 65000:
                exibir_alerta_tamanho_maximo = True
            total += orientacoes_antamento.count()
            if orientacoes_antamento.count() > 65000:
                exibir_alerta_tamanho_maximo = True
            total += orientacoes_concluidas.count()
            if orientacoes_concluidas.count() > 65000:
                exibir_alerta_tamanho_maximo = True
            total += registros_patentes.count()
            if registros_patentes.count() > 65000:
                exibir_alerta_tamanho_maximo = True

            if not exibir_alerta_tamanho_maximo:
                return tasks.exportar_indicadores_sem_publicacao_xls(dados)

        # dados de produção bibliograficas
        data_bib = ProducaoBibliografica.get_tipo_qtd(
            categoria,
            campus,
            servidor=servidor,
            aluno=aluno,
            grupo_pesquisa=grupo_pesquisa,
            programa_posgraduacao=programa_posgraduacao,
            apenas_no_exercicio=apenas_no_exercicio,
        )
        data_bib = list(map(list, data_bib))
        for d in data_bib:
            d[0] = ProducaoBibliografica.tipo_pub_choices[d[0]]

        data_bib = Relatorio.ordernar(data_bib)

        # dados de produção técnica
        data_tec = ProducaoTecnica.get_tipo_qtd(
            categoria,
            campus,
            servidor=servidor,
            aluno=aluno,
            grupo_pesquisa=grupo_pesquisa,
            programa_posgraduacao=programa_posgraduacao,
            apenas_no_exercicio=apenas_no_exercicio,
        )
        data_tec = list(map(list, data_tec))
        for d in data_tec:
            d[0] = ProducaoTecnica.tipo_pub_choices[d[0]]

        data_tec = Relatorio.ordernar(data_tec)

        # dados de Orientações em andamento
        data_orient_andamento = OrientacaoAndamento.get_tipo_qtd(
            categoria,
            campus,
            servidor=servidor,
            aluno=aluno,
            grupo_pesquisa=grupo_pesquisa,
            programa_posgraduacao=programa_posgraduacao,
            apenas_no_exercicio=apenas_no_exercicio,
        )
        data_orient_andamento = list(map(list, data_orient_andamento))
        for d in data_orient_andamento:
            d[0] = OrientacaoAndamento.tipo_choices[d[0]]

        data_orient_andamento = Relatorio.ordernar(data_orient_andamento)

        # dados de Orientações concluida
        data_orient_concluida = OrientacaoConcluida.get_tipo_qtd(
            categoria,
            campus,
            servidor=servidor,
            aluno=aluno,
            grupo_pesquisa=grupo_pesquisa,
            programa_posgraduacao=programa_posgraduacao,
            apenas_no_exercicio=apenas_no_exercicio,
        )
        data_orient_concluida = list(map(list, data_orient_concluida))
        for d in data_orient_concluida:
            d[0] = OrientacaoConcluida.tipo_choices[d[0]]

        data_orient_concluida = Relatorio.ordernar(data_orient_concluida)

        # Registros e Patentes
        data_regis_paten = RegistroPatente.get_tipo_qtd(
            categoria,
            campus,
            servidor=servidor,
            aluno=aluno,
            grupo_pesquisa=grupo_pesquisa,
            programa_posgraduacao=programa_posgraduacao,
            apenas_no_exercicio=apenas_no_exercicio,
        )
        data_regis_paten = list(map(list, data_regis_paten))
        for d in data_regis_paten:
            d[0] = RegistroPatente.tipo_choices[d[0]]

        data_regis_paten = Relatorio.ordernar(data_regis_paten)

        # contrução dos gráficos
        graficos = []
        graficos.append(ColumnChart('grafico1', title='Publicações Bibliográficas', minPointLength=3, data=data_bib))
        graficos.append(ColumnChart('grafico2', title='Publicações Técnicas', minPointLength=3, data=data_tec))
        graficos.append(ColumnChart('grafico3', title='Orientações em Andamento', minPointLength=3, data=data_orient_andamento))
        graficos.append(ColumnChart('grafico4', title='Orientações Concluídas', minPointLength=3, data=data_orient_concluida))
        graficos.append(ColumnChart('grafico5', title='Patentes e Registros', minPointLength=3, data=data_regis_paten))

        graficos.append(PieChart('grafico6', title='Publicações Bibliográficas', data=data_bib))
        graficos.append(PieChart('grafico7', title='Publicações Técnicas', data=data_tec))
        graficos.append(PieChart('grafico8', title='Orientações em Andamento', data=data_orient_andamento))
        graficos.append(PieChart('grafico9', title='Orientações Concluídas', data=data_orient_concluida))
        graficos.append(PieChart('grafico10', title='Patentes e Registros', data=data_regis_paten))

    return locals()


@rtr()
@login_required()
def curriculo(request, servidor_pk):
    servidor = get_object_or_404(Servidor, id=servidor_pk)
    curriculo = get_object_or_404(CurriculoVittaeLattes, vinculo=servidor.get_vinculo())
    dados = curriculo.dado_geral
    dados_complementares = curriculo.dado_complementar
    formacoes_academicas_titulacoes = dados.formacoes_academicas_titulacoes.order_by('-ano_inicio')
    areas_atuacoes = dados.areas_atuacoes.order_by('sequencia_area_atuacao')
    producoes_bibliograficas = curriculo.producoes_bibliograficas.all()

    patentes_registros_software = curriculo.producoes_tecnicas.filter(software__registros_patentes__isnull=False)
    patentes_registros_produtotecnologico = curriculo.producoes_tecnicas.filter(produtotecnologico__registros_patentes__isnull=False)
    patentes_registros_processotecnica = curriculo.producoes_tecnicas.filter(processotecnica__registros_patentes__isnull=False)
    patentes_registros_patente = curriculo.producoes_tecnicas.filter(patente__registros_patentes__isnull=False)
    patentes_registros_marca = curriculo.producoes_tecnicas.filter(marca__registros_patentes__isnull=False)

    projetos_pesquisa = curriculo.get_projeto_pesquisa()
    projetos_extensao = curriculo.get_projeto_extensao()
    projetos_desenvolvimento = curriculo.get_projeto_desenvolvimento()
    projetos = projetos_pesquisa | projetos_extensao | projetos_desenvolvimento

    participacoes_banca_comissao_julgadora = curriculo.get_participacao_em_banca_comissoes_julgadoras()
    participacoes_banca_trabalho_conclusao = curriculo.get_participacao_em_banca_trabalho_conclusao()
    participacoes_banca = participacoes_banca_comissao_julgadora.exists() or participacoes_banca_trabalho_conclusao.exists()
    participacoes_evento_congresso = dados_complementares.participou_evento_congresso()
    participacoes_em_congressos = dados_complementares.get_participacao_congresso()
    participacoes_em_seminarios = dados_complementares.get_participacao_seminario()
    participacoes_em_oficinas = dados_complementares.get_participacao_oficina()
    participacoes_em_encontros = dados_complementares.get_participacao_encontro()
    outras_participacoes = dados_complementares.get_outras_participacoes()

    vinculos = curriculo.get_vinculos()

    premios_e_titulos = curriculo.get_premios_e_titulos()

    grupos_pesquisa = curriculo.grupos_pesquisa.all().order_by('codigo')
    title = str(servidor.pessoa_fisica.nome)

    maior_ano = datetime.datetime.today().year
    ano_inicial = maior_ano - 3

    form = AnoResumoForm(request.POST or None, ano_inicial=ano_inicial)
    if form.is_valid():
        ano_inicial = form.cleaned_data['ano']
        maior_ano = form.cleaned_data['ano_final']

    curriculo_resumo_itens = sorted(Parametro.get_numero_producao_academica(servidor, ano_inicial, maior_ano).values(), key=lambda item: item[1])

    return locals()


@rtr()
@permission_required('cnpq.pode_ver_relatorios, rh.eh_servidor')
def relatorio_importacao(request):
    title = 'Relatório de Importações'

    servidores = Servidor.objects.filter(ativo=True)
    docentes = Servidor.objects.filter(cargo_emprego__grupo_cargo_emprego__categoria='docente', ativo=True)
    tecadm = Servidor.objects.filter(cargo_emprego__grupo_cargo_emprego__categoria='tecnico_administrativo', ativo=True)

    form = CampusForm(request.GET or None)
    if form.is_valid():
        servidores = servidores.filter(setor_exercicio__uo__equivalente=form.cleaned_data.get('campus'))
        docentes = docentes.filter(setor_exercicio__uo__equivalente=form.cleaned_data.get('campus'))
        tecadm = tecadm.filter(setor_exercicio__uo__equivalente=form.cleaned_data.get('campus'))

    servidores_com_lattes = servidores.filter(vinculos__vinculo_curriculo_lattes__isnull=False)
    docentes_com_lattes = docentes.filter(vinculos__vinculo_curriculo_lattes__isnull=False)
    tec_adm_com_lattes = tecadm.filter(vinculos__vinculo_curriculo_lattes__isnull=False)
    lattes_servidores = servidores_com_lattes.count()
    lattes_docentes = docentes_com_lattes.count()
    lattes_tecadm = tec_adm_com_lattes.count()
    total_servidores = servidores.count()
    total_docentes = docentes.count()
    total_tecadm = tecadm.count()

    graficos = []
    # contrução dos gráficos
    graficos.append(
        PieChart(
            'grafico1',
            title='Importações Total dos Servidores',
            data=[['Servidores Importados', lattes_servidores], ['Servidores Não Importados', total_servidores - lattes_servidores]],
        )
    )
    graficos.append(
        PieChart(
            'grafico2',
            title='Importações de Docentes',
            data=[['Docentes Importados', lattes_docentes], ['Docentes Não Importados', total_docentes - lattes_docentes]],
        )
    )
    graficos.append(
        PieChart(
            'grafico3',
            title='Importações de Técnicos-Administrativos',
            data=[['Técnicos-Administrativos Importados', lattes_tecadm], ['Técnicos-Administrativos Não Importados', total_tecadm - lattes_tecadm]],
        )
    )
    return locals()


@rtr()
@permission_required('cnpq.pode_ver_relatorios, rh.eh_servidor')
def relatorio_importacoes_lattes(request):
    title = 'Relatório de Importações dos Currículos Lattes'
    form = ServidoresSemLattesForm(request.POST or None, request=request)
    data_atualizacao = None
    if form.is_valid():
        servidores = form.filtrar()
        if form.cleaned_data.get('situacao') == ServidoresSemLattesForm.IMPORTADOS:
            data_atualizacao = True

    return locals()


@rtr()
@permission_required('cnpq.pode_importar_planilha_periodicos')
def importar_lista_completa(request):
    title = 'Importar Lista Completa - Periódico Qualis'
    form = ImportarListaCompletaForm(data=request.POST or None, files=request.POST and request.FILES or None)
    if form.is_valid():
        try:
            return form.processar()
        except Exception as err:
            return httprr('.', str(err), 'error')
    return locals()


@rtr()
@login_required()
def atualiza_grupos_pesquisa(request, curriculo_id):
    curriculo = get_object_or_404(CurriculoVittaeLattes, id=curriculo_id)
    if curriculo.vinculo:
        url = f'/cnpq/curriculo/{curriculo.vinculo.relacionamento.pk}/'
    else:
        url = '/'
    status = atualizar_grupos_pesquisa(curriculo)

    if status == 1:
        return httprr(url, 'Atualização realizada com sucesso. Novo(s) grupo(s) de pesquisa adicionado(s).')
    elif status == 2:
        return httprr(url, 'Atualização realizada com sucesso. Nenhum novo grupo de pesquisa foi adicionado.')
    elif status == 3:
        return httprr(url, 'Diretório dos grupos de pesquisa no Lattes em manutenção.', tag='error')
    else:
        return httprr(url, 'Nenhum grupo de pesquisa foi atualizado.', tag='error')


def atualizar_grupos_pesquisa(curriculo):
    STATUS_NAO_HA_GRUPO = 0
    STATUS_NOVO_GRUPO_INSERIDO = 1
    STATUS_NENHUM_NOVO_GRUPO_INSERIDO = 2
    STATUS_CNPQ_EM_MANUTENCAO = 3

    """
    :param curriculo:
    :return: retornar o seguintes status: 0 - não há grupos de pesquisa cadastrados, 1 - novos grupos inseridos e 2 - nenhum novo grupo inserido
    """
    grupos = scrap_grupos_pesquisas(curriculo.numero_identificador)
    if grupos:
        if grupos == 3:
            return STATUS_CNPQ_EM_MANUTENCAO
        else:
            retorno, sistema_offline = carrega_grupos_pesquisa(grupos, curriculo)
            if sistema_offline:
                return STATUS_CNPQ_EM_MANUTENCAO
            curriculo.data_importacao_grupos_pesquisa = datetime.datetime.now()
            try:
                curriculo.save()
            except Exception:
                pass
            if retorno:
                return STATUS_NOVO_GRUPO_INSERIDO
            else:
                return STATUS_NENHUM_NOVO_GRUPO_INSERIDO
    else:
        instituicao_sigla = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
        curriculo.data_importacao_grupos_pesquisa = datetime.datetime.now()
        curriculo.save()
        if curriculo.grupos_pesquisa.filter(instituicao=instituicao_sigla).exists():
            return STATUS_NENHUM_NOVO_GRUPO_INSERIDO
        return STATUS_NAO_HA_GRUPO


def carrega_grupos_pesquisa(grupos, curriculo):
    todos_os_grupos = GrupoPesquisa.objects.all().values_list('codigo', flat=True)
    grupos_ja_cadastrados = curriculo.grupos_pesquisa.all().values_list('codigo', flat=True)
    inclusao = False
    sistema_offline = False
    for grupo in grupos:
        if grupo['id'] != 'errorPage.jsf':
            if grupo['id'] not in todos_os_grupos:
                novo_grupo = GrupoPesquisa()
                novo_grupo.codigo = grupo['id']
                novo_grupo.descricao = grupo['nome']
                novo_grupo.instituicao = grupo['instituicao']
                novo_grupo.save()
                try:
                    curriculo.grupos_pesquisa.add(novo_grupo.id)
                    inclusao = True
                except IntegrityError:
                    pass
            elif grupo['id'] not in grupos_ja_cadastrados:
                novo_grupo_curriculo = GrupoPesquisa.objects.get(codigo=grupo['id'])
                try:
                    curriculo.grupos_pesquisa.add(novo_grupo_curriculo.id)
                    inclusao = True
                except IntegrityError:
                    pass
            elif grupo['id']:
                grupo_ja_existente = GrupoPesquisa.objects.get(codigo=grupo['id'])
                grupo_ja_existente.descricao = grupo['nome']
                grupo_ja_existente.instituicao = grupo['instituicao']
                grupo_ja_existente.save()
        else:
            sistema_offline = True
    return inclusao, sistema_offline


def scrap_grupos_pesquisas(identificador_curriculo):
    br = mechanicalsoup.StatefulBrowser()

    url = f'http://dgp.cnpq.br/dgp/espelhorh/{identificador_curriculo}'
    try:
        response = br.open(url, timeout=100)
        texto = response.text
        if 'Sistema em manuten\xe7\xe3o.' in texto:
            return 3
    except Exception:
        return []
    grupos = []
    busca = br.get_current_page().find('div', id='gruposPesquisa')
    if busca:
        lista_grupos = list(busca)[2:3]
        for registro in lista_grupos:
            valores = list(registro.find_all('tr', class_='ui-widget-content'))
            id_controle = 0
            for valor in valores:
                grupo = {}
                celulas = valor.find_all('td')
                if celulas[0].text != 'Nenhum registro adicionado':
                    grupo['nome'] = celulas[0].text
                    grupo['instituicao'] = celulas[1].text.split('$')[0]
                    grupo['perfil'] = celulas[2].text
                    try:
                        form = br.select_form('form[name="formVisualizarRH"]')
                        if form:
                            form.choose_submit(f'formVisualizarRH:tblEspelhoRHGPAtuacao:{id_controle}:visualizarGPLider')
                            try:
                                br.submit_selected()
                                url_clicada = br.get_url()
                                if 'espelhogrupo/' in url_clicada:
                                    grupo['id'] = url_clicada.split('espelhogrupo/')[1]
                                    grupos.append(grupo)
                            except Exception:
                                pass
                    except Exception:
                        pass
                id_controle += 1
                try:
                    br.open(url, timeout=100)
                except Exception:
                    pass
    return grupos


@rtr()
@permission_required('cnpq.pode_importar_planilha_periodicos')
def cadastrar_periodico(request):
    title = 'Cadastrar Periódico'
    if request.GET.get('query'):
        query = request.GET['query']
        periodicos = PeriodicoRevista.objects.filter(nome__unaccent__icontains=query).order_by('nome')
    else:
        periodicos = PeriodicoRevista.objects.all().order_by('nome')
    form = PeriodicoRevistaForm(request.POST or None)
    if form.is_valid():
        form.save()
        return httprr('/cnpq/cadastrar_periodico/', 'Periódico cadastrado com sucesso.')

    return locals()


@rtr()
@permission_required('cnpq.pode_importar_planilha_periodicos')
def editar_periodico(request, periodico_id):
    title = 'Editar Periódico'
    periodico = get_object_or_404(PeriodicoRevista, pk=periodico_id)
    form = PeriodicoRevistaForm(request.POST or None, instance=periodico)
    if form.is_valid():
        form.save()
        return httprr('/cnpq/cadastrar_periodico/', 'Periódico editado com sucesso.')

    return locals()


@rtr()
@permission_required('cnpq.pode_ver_producao_servidor, rh.eh_servidor')
def producao_por_servidor(request):
    title = 'Produção por Servidor'
    form = ProducaoServidorForm(request.POST or None)
    encontrou_registro = False
    if form.is_valid():
        if form.cleaned_data.get('servidor'):
            servidor = form.cleaned_data.get('servidor')
            vinculo_servidor = servidor.get_vinculo()
            producoes_biblio = ProducaoBibliografica.objects.filter(curriculo__vinculo=vinculo_servidor).order_by('-ano', 'tipo_pub', 'titulo')
            producoes_tecnica = ProducaoTecnica.objects.filter(curriculo__vinculo=vinculo_servidor).order_by('-ano', 'tipo_pub', 'titulo')
            orientacoes_andamento = OrientacaoAndamento.objects.filter(dado_complementar__curriculovittaelattes__vinculo=vinculo_servidor).order_by(
                '-ano', 'tipo', 'titulo'
            )
            orientacoes_concluida = OrientacaoConcluida.objects.filter(curriculo__vinculo=vinculo_servidor).order_by(
                '-ano', 'tipo_orientacao', 'titulo'
            )
            registros_patente = RegistroPatente.objects.filter(curriculo__vinculo=vinculo_servidor).order_by(
                '-data_pedido_deposito', '-data_concessao'
            )

        if form.cleaned_data.get('palavra_chave'):
            palavra_chave = form.cleaned_data.get('palavra_chave')
            producoes_biblio = ProducaoBibliografica.objects.filter(titulo__icontains=palavra_chave).order_by('-ano', 'tipo_pub', 'titulo')
            producoes_tecnica = ProducaoTecnica.objects.filter(titulo__icontains=palavra_chave).order_by('-ano', 'tipo_pub', 'titulo')
            orientacoes_andamento = OrientacaoAndamento.objects.filter(titulo__icontains=palavra_chave).order_by('-ano', 'tipo', 'titulo')
            orientacoes_concluida = OrientacaoConcluida.objects.filter(titulo__icontains=palavra_chave).order_by('-ano', 'tipo_orientacao', 'titulo')
            registros_patente = RegistroPatente.objects.filter(titulo__icontains=palavra_chave).order_by('-data_pedido_deposito', '-data_concessao')

        encontrou_registro = (
            producoes_biblio.exists()
            or producoes_tecnica.exists()
            or orientacoes_andamento.exists()
            or orientacoes_concluida.exists()
            or registros_patente.exists()
        )
        if encontrou_registro:
            if form.cleaned_data.get('inicio_periodo'):
                ano_inicio = form.cleaned_data.get('inicio_periodo')
                producoes_biblio = producoes_biblio.filter(ano__gte=ano_inicio.ano)
                producoes_tecnica = producoes_tecnica.filter(ano__gte=ano_inicio.ano)
                orientacoes_andamento = orientacoes_andamento.filter(ano__gte=ano_inicio.ano)
                orientacoes_concluida = orientacoes_concluida.filter(ano__gte=ano_inicio.ano)
                registros_patente = registros_patente.filter(
                    Q(data_pedido_deposito__year__gte=ano_inicio.ano) | Q(data_concessao__year__gte=ano_inicio.ano)
                )

            if form.cleaned_data.get('fim_periodo'):
                fim_periodo = form.cleaned_data.get('fim_periodo')
                producoes_biblio = producoes_biblio.filter(ano__lte=fim_periodo.ano)
                producoes_tecnica = producoes_tecnica.filter(ano__lte=fim_periodo.ano)
                orientacoes_andamento = orientacoes_andamento.filter(ano__lte=fim_periodo.ano)
                orientacoes_concluida = orientacoes_concluida.filter(ano__lte=fim_periodo.ano)
                registros_patente = registros_patente.filter(
                    Q(data_pedido_deposito__year__lte=fim_periodo.ano) | Q(data_concessao__year__lte=fim_periodo.ano)
                )

            tabela = []
            if producoes_biblio.exists():
                tabela.append(('Produções Bibiográficas', producoes_biblio))
            if producoes_tecnica.exists():
                tabela.append(('Produções Técnicas', producoes_tecnica))
            if orientacoes_andamento.exists():
                tabela.append(('Orientações em Andamento', orientacoes_andamento))
            if orientacoes_concluida.exists():
                tabela.append(('Orientações Concluídas', orientacoes_concluida))
            if registros_patente.exists():
                tabela.append(('Registros de Patente', registros_patente))

    return locals()


@rtr()
@permission_required('cnpq.pode_ver_producao_servidor, rh.eh_servidor')
def producao_por_campus(request):
    title = 'Produção por Campus'
    form = ProducaoCampusForm(request.POST or None)
    encontrou_registo = False
    if form.is_valid():
        producoes_biblio = ProducaoBibliografica.objects.only('curriculo', 'ano', 'tipo_pub', 'titulo').order_by('-ano', 'tipo_pub', 'titulo')
        producoes_tecnica = ProducaoTecnica.objects.only('curriculo', 'ano', 'tipo_pub', 'titulo').order_by('-ano', 'tipo_pub', 'titulo')
        orientacoes_andamento = OrientacaoAndamento.objects.only('dado_complementar', 'ano', 'tipo', 'titulo').order_by('-ano', 'tipo', 'titulo')
        orientacoes_concluida = OrientacaoConcluida.objects.only('curriculo', 'ano', 'tipo_orientacao', 'titulo').order_by(
            '-ano', 'tipo_orientacao', 'titulo'
        )
        registros_patente = RegistroPatente.objects.only('curriculo', 'data_pedido_deposito', 'data_concessao').order_by(
            '-data_pedido_deposito', '-data_concessao'
        )

        if form.cleaned_data.get('campus'):
            campus = form.cleaned_data.get('campus')
            servidores = Servidor.objects.filter(Q(setor_exercicio__uo__equivalente=campus) | Q(setor_exercicio__uo=campus)).values_list(
                'id', flat=True
            )
            producoes_biblio = producoes_biblio.filter(curriculo__vinculo__id_relacionamento__in=servidores).order_by('-ano', 'tipo_pub', 'titulo')
            producoes_tecnica = producoes_tecnica.filter(curriculo__vinculo__id_relacionamento__in=servidores).order_by('-ano', 'tipo_pub', 'titulo')
            orientacoes_andamento = orientacoes_andamento.filter(
                dado_complementar__curriculovittaelattes__vinculo__id_relacionamento__in=servidores
            ).order_by('-ano', 'tipo', 'titulo')
            orientacoes_concluida = orientacoes_concluida.filter(curriculo__vinculo__id_relacionamento__in=servidores).order_by(
                '-ano', 'tipo_orientacao', 'titulo'
            )
            registros_patente = registros_patente.filter(curriculo__vinculo__id_relacionamento__in=servidores).order_by(
                '-data_pedido_deposito', '-data_concessao'
            )

        if form.cleaned_data.get('palavra_chave'):
            palavra_chave = form.cleaned_data.get('palavra_chave')
            producoes_biblio = producoes_biblio.filter(titulo__icontains=palavra_chave).order_by('-ano', 'tipo_pub', 'titulo')
            producoes_tecnica = producoes_tecnica.filter(titulo__icontains=palavra_chave).order_by('-ano', 'tipo_pub', 'titulo')
            orientacoes_andamento = orientacoes_andamento.filter(titulo__icontains=palavra_chave).order_by('-ano', 'tipo', 'titulo')
            orientacoes_concluida = orientacoes_concluida.filter(titulo__icontains=palavra_chave).order_by('-ano', 'tipo_orientacao', 'titulo')
            registros_patente = registros_patente.filter(titulo__icontains=palavra_chave).order_by('-data_pedido_deposito', '-data_concessao')

        encontrou_registo = (
            producoes_biblio.exists()
            or producoes_tecnica.exists()
            or orientacoes_andamento.exists()
            or orientacoes_concluida.exists()
            or registros_patente.exists()
        )

        if encontrou_registo:
            if form.cleaned_data.get('inicio_periodo'):
                ano_inicio = form.cleaned_data.get('inicio_periodo')
                producoes_biblio = producoes_biblio.filter(ano__gte=ano_inicio.ano)
                producoes_tecnica = producoes_tecnica.filter(ano__gte=ano_inicio.ano)
                orientacoes_andamento = orientacoes_andamento.filter(ano__gte=ano_inicio.ano)
                orientacoes_concluida = orientacoes_concluida.filter(ano__gte=ano_inicio.ano)
                registros_patente = registros_patente.filter(
                    Q(data_pedido_deposito__year__gte=ano_inicio.ano) | Q(data_concessao__year__gte=ano_inicio.ano)
                )

            if form.cleaned_data.get('fim_periodo'):
                fim_periodo = form.cleaned_data.get('fim_periodo')
                producoes_biblio = producoes_biblio.filter(ano__lte=fim_periodo.ano)
                producoes_tecnica = producoes_tecnica.filter(ano__lte=fim_periodo.ano)
                orientacoes_andamento = orientacoes_andamento.filter(ano__lte=fim_periodo.ano)
                orientacoes_concluida = orientacoes_concluida.filter(ano__lte=fim_periodo.ano)
                registros_patente = registros_patente.filter(
                    Q(data_pedido_deposito__year__lte=fim_periodo.ano) | Q(data_concessao__year__lte=fim_periodo.ano)
                )

            tabela = [
                (titulo, queryset)
                for titulo, queryset in (
                    ('Produções Bibiográficas', producoes_biblio),
                    ('Produções Técnicas', producoes_tecnica),
                    ('Orientações em Andamento', orientacoes_andamento),
                    ('Orientações Concluídas', orientacoes_concluida),
                    ('Registros de Patente', registros_patente),
                )
                if queryset.exists()
            ]
            if 'xls' in request.POST:
                return _producao_por_campus_xls(tabela)

    return locals()


def _producao_por_campus_xls(tabela: list[tuple[str, QuerySet]]) -> HttpResponse:
    rows = [['#', 'Produção', 'Ano', 'Tipo', 'Autores', 'Publicação']]
    contador = 0
    for titulo, publicacoes in tabela:
        for publicacao in publicacoes:
            contador += 1
            autores = ', '.join(format_(vinculo.pessoa, html=False) for vinculo in publicacao.get_autores_unicos())
            rows.append(
                [
                    contador,
                    titulo,
                    format_(publicacao.get_ano(), html=False),
                    format_(publicacao.get_tipo(), html=False),
                    autores,
                    strip_tags(format_(publicacao, html=False)),
                ]
            )
    return XlsResponse(rows, name='producao_por_campus')


@rtr()
@permission_required('rh.eh_servidor')
def busca_por_titulacao(request):
    title = 'Buscar Servidores Por Titulação e Área de Atuação'
    form = TitulacaoForm(request.POST or None)
    encontrou_registro = False
    if form.is_valid():
        servidor = form.cleaned_data.get('servidor')
        titulacao = form.cleaned_data.get('titulacao')
        atuacao = form.cleaned_data.get('atuacao')
        campus = form.cleaned_data.get('campus')
        grupo_pesquisa = form.cleaned_data.get('grupo_pesquisa')
        sexo = form.cleaned_data.get('sexo')
        apenas_grupos_pesquisa = form.cleaned_data.get('apenas_grupos_pesquisa')
        registros = Servidor.objects.ativos()
        if servidor:
            registros = registros.filter(id=servidor.id)
        if sexo:
            registros = registros.filter(pessoa_fisica__sexo=sexo)
        if titulacao:
            registros = registros.filter(titulacao=titulacao)
        if atuacao:
            registros_atuacao_grande_area = registros.filter(
                vinculos__vinculo_curriculo_lattes__dado_geral__areas_atuacoes__nome_grande_area_conhecimento__icontains=atuacao
            )
            registros_atuacao_area = registros.filter(
                vinculos__vinculo_curriculo_lattes__dado_geral__areas_atuacoes__nome_area_conhecimento__icontains=atuacao
            )
            registros_atuacao_subarea = registros.filter(
                vinculos__vinculo_curriculo_lattes__dado_geral__areas_atuacoes__nome_sub_area_conhecimento__icontains=atuacao
            )
            registros_atuacao_especialidade = registros.filter(
                vinculos__vinculo_curriculo_lattes__dado_geral__areas_atuacoes__nome_especialidade_conhecimento__icontains=atuacao
            )

            registros = registros & (
                registros_atuacao_grande_area | registros_atuacao_area | registros_atuacao_subarea | registros_atuacao_especialidade
            )
        if campus:
            registros = registros.filter(Q(setor_exercicio__uo__equivalente=campus) | Q(setor_exercicio__uo=campus))

        if apenas_grupos_pesquisa:
            curriculos = CurriculoVittaeLattes.objects.filter(grupos_pesquisa__isnull=False)
            registros = registros.filter(id__in=curriculos.values_list('vinculo__id_relacionamento', flat=True))

        if grupo_pesquisa:
            curriculos = CurriculoVittaeLattes.objects.filter(grupos_pesquisa=grupo_pesquisa)
            registros = registros.filter(id__in=curriculos.values_list('vinculo__id_relacionamento', flat=True))

        registros = registros.distinct()

    return locals()


@rtr()
@login_required()
def atualizar_curriculo(request, matricula, servidor_id):
    args = ()
    options = {'matricula': matricula, 'forcar': True, 'origem_view': True, 'pythonpath': None, 'verbosity': '1', 'traceback': None, 'settings': None}
    cnpq_importar_command = cnpq_importar.Command()
    count_exceptions = cnpq_importar_command.handle(*args, **options)
    if count_exceptions:
        servidor = get_object_or_404(Servidor, pk=servidor_id)
        return httprr(
            f'/rh/servidor/{servidor.matricula}/',
            'Não foi possivel atualizar seu currículo. Um email com o erro foi enviado para a equipe de desenvolvimento.',
            tag='error',
        )
    else:
        return httprr(f'/cnpq/curriculo/{servidor_id}/', 'Currículo atualizado com sucesso.')


def download_xml_curriculos(request):
    temp = get_temp_storage()
    try:
        tmp = temp.open('curriculos.zip')
        response = HttpResponse(tmp.read(), content_type='application/zip')
        response['Content-Disposition'] = 'attachment; filename=curriculos_IFRN.zip'
        return response
    except Exception:
        return httprr('/', 'Arquivo de curriculos não encontrado.', 'error')
