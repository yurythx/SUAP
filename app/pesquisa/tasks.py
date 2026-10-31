from django.conf import settings
from django.template.defaultfilters import yesno
from django.utils.html import strip_tags

from cnpq.models import CurriculoVittaeLattes
from comum.models import Vinculo
from djtools.assincrono import task
from djtools.templatetags.filters import format_
from djtools.utils import XlsResponse, send_notification
from pesquisa.models import BolsaDisponivel, Participacao
from rh.models import Servidor


@task('Exportar Lista de Avaliadores para XLS')
def listar_avaliadores_export_to_xls(avaliadores, task=None):
    rows = [['#', 'Nome', 'Email', 'Lattes', 'ORCID', 'Área de Conhecimento', 'Indicações']]

    contador = 0
    for avaliador in task.iterate(avaliadores):
        areas = []
        for area in avaliador.areas_de_conhecimento.all():
            areas.append(area.descricao)

        lattes = '-'
        vinculo = avaliador.get_vinculo()
        if CurriculoVittaeLattes.objects.filter(vinculo=vinculo).exists():
            lattes = f'http://lattes.cnpq.br/{CurriculoVittaeLattes.objects.filter(vinculo=vinculo)[0].numero_identificador}'
        row = [
            contador,
            format_(avaliador.pessoa_fisica.nome),
            format_(getattr(avaliador, 'email_institucional', '')),
            format_(lattes),
            format_(avaliador.pessoa_fisica.orcid),
            format_(', '.join(areas)),
            avaliador.get_indicacoes_como_avaliador_pesquisa(),
        ]
        rows.append(row)
        contador += 1
    return XlsResponse(rows, processo=task)


@task('Exportar Equipe dos Projetos para XLS')
def listar_equipes_dos_projetos_export_to_xls(participacoes, task=None):
    rows = [
        [
            '#',
            'Campus',
            'Edital',
            'Projeto',
            'Área de Conhecimento',
            'Nome',
            'Matrícula',
            'CPF',
            'Email',
            'Lattes',
            'ORCID',
            'Vínculo',
            'Ativo',
            'Titulação',
            'Curso',
            'Banco',
            'Agência',
            'Conta',
            'Tipo da conta',
            'Operação',
        ]
    ]

    contador = 0
    for participacao in task.iterate(participacoes):
        contador += 1
        cpf = ''
        curso = ''
        email = ''
        lattes = ''
        orcid = ''
        participante = participacao.get_participante()
        matricula = participacao.get_identificador()
        if participacao.ativo:
            ativo = 'Sim'
        else:
            ativo = 'Não'
        titulacao = participacao.get_titulacao()
        nome = f'{participacao.get_nome()}'
        if participacao.is_servidor():
            email = participante.email_institucional
            cpf = participante.pessoa_fisica.cpf
            orcid = participante.pessoa_fisica.orcid
        elif hasattr(participante, 'lattes'):
            email = participante.email
            lattes = participante.lattes
            cpf = participante.prestador.pessoa_fisica.cpf
        elif participante:
            email = getattr(participante, 'email_institucional', '')
            lattes = participante.pessoa_fisica.lattes
            orcid = participante.pessoa_fisica.orcid
            curso = participante.curso_campus
            cpf = participante.pessoa_fisica.cpf

        banco = (participacao.instituicao and str(participacao.instituicao) or '-',)
        agencia = (participacao.numero_agencia or '-',)
        tipo_conta = (participacao.tipo_conta or '-',)
        numero_conta = (participacao.numero_conta or '-',)
        operacao = (participacao.operacao or '-',)

        if participacao.responsavel:
            vinculo = 'Coordenador'
        else:
            vinculo = 'Membro'
        if participacao.vinculo == 'Bolsista' and participacao.bolsa_concedida:
            vinculo = vinculo + ' Bolsista'
        else:
            vinculo = vinculo + ' Não Bolsista'
        row = [
            contador,
            format_(participacao.projeto.uo.sigla),
            format_(participacao.projeto.edital.titulo),
            format_(participacao.projeto.titulo),
            format_(participacao.projeto.area_conhecimento),
            format_(nome),
            format_(matricula),
            format_(cpf),
            format_(email),
            format_(lattes),
            format_(orcid),
            format_(vinculo),
            format_(ativo),
            format_(titulacao),
            format_(curso),
            format_(banco),
            format_(agencia),
            format_(numero_conta),
            format_(tipo_conta),
            format_(operacao),
        ]
        rows.append(row)
    return XlsResponse(rows, processo=task)


@task('Atualizar Curriculo Lattes')
def atualizar_curriculo_lattes(url, edital, task=None):
    edital.normalizar_pontuacao_curriculo_lattes(uo=None, task=task)
    task.finalize('Atualização realizada com sucesso.', url)
    edital.classifica_projetos_pesquisa()


@task('Exportar Bolsas de Projetos para XLS')
def exportar_bolsas_para_xls(projetos, task=None):
    rows = [
        [
            '#',
            'Edital',
            'Projeto',
            'Coordenador',
            'Vínculo/Bolsa',
            'Servidor',
            'Categoria/Titulação',
            'Aluno',
            'CRE',
            'Modalidade/Forma de Ensino',
            'Forma de Ingresso',
            'Curso',
            'Situação',
            'Pontuação do Currículo',
            'Pontuação do Currículo normalizado',
            'Pontuação do Grupo de Pesquisa',
            'Pontuação do Grupo de Pesquisa normalizado',
            'Pontuação da Avaliação',
            'Pontuação Final',
        ]
    ]

    contador = 0
    for projeto in task.iterate(projetos):
        for participacao in projeto.participacao_por_vinculo.all():
            contador += 1
            responsavel_nome = ''
            servidor_nome = ''
            aluno_nome = ''
            aluno_ira = ''
            aluno_forma_ingresso = ''
            aluno_curso = ''
            aluno_modalidade = ''

            if participacao.responsavel:
                responsavel_nome = participacao.vinculo_pessoa.pessoa.nome

            if participacao.eh_aluno():
                registro_aluno = participacao.get_participante()
                aluno_nome = participacao.get_nome()
                if registro_aluno:
                    aluno_ira = registro_aluno.get_ira()
                    aluno_forma_ingresso = registro_aluno.forma_ingresso
                    aluno_curso = registro_aluno.curso_campus
                    aluno_modalidade = registro_aluno.curso_campus.modalidade
            else:
                servidor_nome = participacao.vinculo_pessoa.pessoa.nome

            if participacao.vinculo == 'Bolsista' and participacao.bolsa_concedida:
                bolsa_status = 'Bolsa concedida'
            elif participacao.vinculo == 'Bolsista' and not participacao.bolsa_concedida:
                bolsa_status = 'Bolsa não concedida'
            else:
                bolsa_status = 'Vonlutário'

            if projeto.aprovado:
                situacao = 'Aprovado'
            else:
                situacao = 'Não Aprovado'
            row = [
                contador,
                format_(projeto.edital.titulo),
                format_(projeto.titulo),
                format_(responsavel_nome),
                format_(bolsa_status),
                format_(servidor_nome),
                format_(participacao.get_titulacao()),
                format_(aluno_nome),
                format_(aluno_ira),
                format_(aluno_modalidade),
                format_(aluno_forma_ingresso),
                format_(aluno_curso),
                format_(situacao),
                format_(projeto.pontuacao_curriculo),
                format_(projeto.pontuacao_curriculo_normalizado),
                format_(projeto.pontuacao_grupo_pesquisa),
                format_(projeto.pontuacao_grupo_pesquisa_normalizado),
                format_(projeto.pontuacao),
                format_(projeto.pontuacao_total),
            ]
            rows.append(row)
    return XlsResponse(rows, processo=task)


@task('Exportar Lista de Projetos em Atraso para XLS')
def listar_projetos_em_atraso_export_to_xls(projetos, task=None):
    rows = [['#', 'Edital', 'Projeto', 'Coordenador', 'Fim da Execução']]

    contador = 0
    for projeto in task.iterate(projetos):
        contador += 1
        row = [
            contador,
            format_(projeto.edital),
            format_(projeto.titulo),
            format_(projeto.vinculo_coordenador.pessoa.nome),
            format_(projeto.fim_execucao),
        ]
        rows.append(row)
    return XlsResponse(rows, processo=task)


@task('Exportar Relatório de Dimensão para XLS')
def relatorio_dimensao_export_to_xls(
    quantidade_projetos, areas, lista_qtd, quantidade_participantes, participantes_por_area_conhecimento, lista_grupos_pesquisa, task=None
):
    total_projetos = 0
    total_projetos_aprovados = 0
    total_projetos_concluidos = 0
    rows = [['Projetos por Edital']]

    row = ['Edital', 'Projetos Submetidos', 'Projetos Aprovados', 'Projetos Concluídos']
    rows.append(row)

    task.start_progress()

    for info in quantidade_projetos:
        total_projetos = total_projetos + info['total']
        total_projetos_aprovados = total_projetos_aprovados + info['aprovados']
        total_projetos_concluidos = total_projetos_concluidos + info['concluidos']

        row = [format_(info['edital']), format_(info['total']), format_(info['aprovados']), format_(info['concluidos'])]
        rows.append(row)

        task.update_progress(10)
    row = ['Total', format_(total_projetos), format_(total_projetos_aprovados), format_(total_projetos_concluidos)]
    rows.append(row)
    row = ['']
    rows.append(row)

    row = ['Projetos por Área de Conhecimento (Submetidos/Aprovados)']
    rows.append(row)
    qtd_areas = len(areas)
    areas.insert(0, 'Edital')
    rows.append(areas)

    for info, valores in list(lista_qtd.items()):
        lista_valores = []
        lista_valores.append(info)
        idx = 0

        while idx < qtd_areas * 2:
            lista_valores.append('{}/{}'.format(valores['valores'][idx], valores['valores'][idx + 1]))
            idx += 2
        rows.append(lista_valores)

        task.update_progress(30)

    row = ['']
    rows.append(row)
    row = ['Participações por Edital']
    rows.append(row)

    row = ['Edital', 'Bolsistas (Docentes/Téc. Adm/Discentes)', 'Voluntários (Docentes/Téc. Adm/Discentes)']
    rows.append(row)

    for info in quantidade_participantes:
        row = [
            format_(info['edital']),
            format_('%s/%s/%s') % (info['docentes_bolsistas'], info['tecnicos_adm_bolsistas'], info['alunos_bolsistas']),
            format_('%s/%s/%s') % (info['docentes_voluntarios'], info['tecnicos_adm_voluntarios'], info['alunos_voluntarios']),
        ]

        rows.append(row)

        task.update_progress(50)

    row = ['']
    rows.append(row)
    row = ['Participantes por Área de Conhecumento']
    rows.append(row)
    row = ['Área', 'Bolsistas (Docentes/Téc. Adm/Discentes)', 'Voluntários (Docentes/Téc. Adm/Discentes)']
    rows.append(row)

    for info in participantes_por_area_conhecimento:
        row = [
            format_(info['area']),
            format_('%s/%s/%s') % (info['docentes_bolsistas'], info['tec_adm_bolsistas'], info['alunos_bolsistas']),
            format_('%s/%s/%s') % (info['docentes_voluntarios'], info['tec_adm_voluntarios'], info['alunos_voluntarios']),
        ]

        rows.append(row)

        task.update_progress(70)

    row = ['']
    rows.append(row)
    row = ['Quantidade de Projetos Aprovados por Grupo de Pesquisa']
    rows.append(row)
    row = ['Grupo de Pesquisa', 'Quantidade de Projetos']
    rows.append(row)

    for info in lista_grupos_pesquisa:
        row = [format_(f'{info[0]}'), format_(f'{info[1]}')]

        rows.append(row)

        task.update_progress(90)

    return XlsResponse(rows, processo=task)


@task('Exportar Lista Mensal de Bolsistas para XLS')
def lista_mensal_bolsistas_to_xls(registros, ano, mes, task=None):
    rows = [['', '', f'Relatório Mensal de Bolsistas - {mes} / {ano}'], ['']]
    rows.append(['#', 'Aluno', 'Edital', 'Projeto', 'Bolsista', 'Dados Bancários', 'Ativo'])

    contador = 0
    for registro in task.iterate(registros):
        contador += 1
        participacao = registro.get_participacao()
        bolsista = 'Não'
        ativo = 'Não'
        matricula = ''
        nome = ''
        if participacao:
            if participacao.eh_aluno() == 'Bolsista' and participacao.bolsa_concedida:
                bolsista = 'Sim'
            if participacao.ativo:
                ativo = 'Sim'
            matricula = participacao.get_participante().matricula
        if registro.vinculo_membro_equipe:
            nome = registro.vinculo_membro_equipe.pessoa.nome
        dados_bancarios = ''
        if participacao.instituicao:
            dados_bancarios += f'Banco: {participacao.instituicao} | '
        if participacao.numero_agencia:
            dados_bancarios += f'Agência: {participacao.numero_agencia} | '
        if participacao.tipo_conta:
            dados_bancarios += f'Tipo da Conta: {participacao.tipo_conta} | '
        if participacao.numero_conta:
            dados_bancarios += f'Número da Conta: {participacao.numero_conta} | '
        if participacao.operacao:
            dados_bancarios += f'Operação: {participacao.operacao} | '
        row = [
            contador,
            format_(f'{nome} ({matricula})'),
            format_(registro.projeto.edital.titulo),
            format_(registro.projeto.titulo),
            format_(bolsista),
            format_(dados_bancarios),
            format_(ativo),
        ]
        rows.append(row)
    return XlsResponse(rows, processo=task)


@task('Exportar Atividades do Projeto para XLS')
def exportar_atividades_projeto_xls(projeto, task=None):
    rows = [['', f'{projeto.titulo} - Relatório de Objetivos Específicos']]
    row = ['']
    rows.append(row)
    for meta in task.iterate(projeto.get_metas()):
        row = ['***', f'Meta {meta.ordem} - Descrição: {meta.descricao} - Período: {meta.get_periodo_meta()}']
        rows.append(row)
        row = ['']
        rows.append(row)
        row = ['***', 'Lista de Atividades']
        rows.append(row)
        row = ['']
        rows.append(row)
        row = [
            'Ordem',
            'Descrição',
            'Período Planejado',
            'Resultados Esperados',
            'Validação',
            'Resultados Obtidos',
            'Observação',
            'Período Executado',
        ]
        rows.append(row)
        for etapa in meta.get_etapas():
            descricao = etapa.descricao

            if etapa.responsavel:
                descricao += f' Responsável: {etapa.responsavel}'
            inicio = etapa.inicio_execucao.strftime('%d/%m/%Y')
            fim = etapa.fim_execucao.strftime('%d/%m/%Y')
            periodo = f'De {inicio} até {fim}'
            obs = ''
            indicadores = ''
            periodo_execucao = ''
            validacao = ''
            if etapa.get_registro_execucao():
                obs = etapa.get_registro_execucao().obs
                indicadores = etapa.get_registro_execucao().get_tipo_indicador_qualitativo_display()
                inicio = etapa.get_registro_execucao().inicio_execucao.strftime('%d/%m/%Y')
                fim = etapa.get_registro_execucao().fim_execucao.strftime('%d/%m/%Y')
                periodo_execucao = f'De {inicio} até {fim}'
                validacao = f'{strip_tags(etapa.get_registro_execucao().get_mensagem_avaliacao())}'

            row = [
                f'{etapa.ordem}',
                f'{etapa.descricao}',
                f'{periodo}',
                f'{etapa.indicadores_qualitativos}',
                f'{validacao}',
                f'{indicadores}',
                f'{obs}',
                f'{periodo_execucao}',
            ]

            rows.append(row)
        row = ['']
        rows.append(row)

    return XlsResponse(rows, processo=task)


@task('Notificar servidores sobre edital aberto')
def notificar_servidores_edital(edital, task=None):
    titulo = '[SUAP] Pesquisa: Edital com inscrições abertas'
    texto = (
        '<h1>Pesquisa</h1>'
        '<h2>Edital com inscrições abertas</h2>'
        f'<p>Olá, Servidor(a).</p>'
        f"<p>O edital '{edital.titulo}' foi publicado no SUAP e está com inscrições abertas.</p>"
        f'<p>As inscrições podem ser realizadas através do seguinte endereço: <a href="{settings.SITE_URL}/pesquisa/adicionar_projeto/{edital.id}/">{settings.SITE_URL}/pesquisa/adicionar_projeto/{edital.id}/</a></p>'
        f'<p class="more-info">Para mais informações, acesse: <a href="{settings.SITE_URL}/pesquisa/editais_abertos/">{settings.SITE_URL}/pesquisa/editais_abertos/</a></p>'
    )
    for oferta in task.iterate(BolsaDisponivel.objects.filter(edital=edital)):
        vinculos = list(
            Vinculo.objects.filter(
                tipo_relacionamento__model='servidor',
                id__in=Servidor.objects.filter(ativo=True, setor__uo=oferta.uo).values_list('vinculos', flat=True),
            )
        )
        send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, vinculos)
    task.finalize('Notificações enviadas com sucesso.', f'/pesquisa/edital/{edital.id}/')


@task('Exportar Estatísticas por Campus para XLS')
def estatisticas_por_campus_to_xls(cabecalho, dict_retorno, total, task=None):
    rows = [['', '', 'Estatísticas de Projetos por Campus']]
    row = ['#', 'Campus']
    row.extend(cabecalho)
    rows.append(row)
    contador = 0
    for registro in task.iterate(dict_retorno.items()):
        contador += 1
        row = [contador, registro[0]]
        for item in registro[1]:
            row.append(item)
        rows.append(row)
    row = ['', 'Total']
    row.extend(total.values())
    rows.append(row)
    return XlsResponse(rows, processo=task)


@task('Exportar Dados para solicitação do Cartão Pesquisador')
def relatorio_dados_cartao_pesquisador_to_xls(projetos, task=None):
    rows = [
        [
            '#',
            'Tem interesse no cartão?',
            'Edital',
            'Nome',
            'CPF',
            'Data de Nascimento',
            'Campus',
            'DDD',
            'Telefone',
            'Email',
            'Logradouro',
            'Número',
            'Complemento',
            'Bairro',
            'Município',
            'UF',
            'CEP',
            'RG',
            'Órgão Emissor',
            'UF do RG',
            'Data de emissão',
            'Sexo',
            'Estado civil',
            'Cargo na Instituição',
            'Data de Início no cargo',
            'Mês/Ano de início do cargo',
            'Banco',
            'Agência',
            'Conta',
            'Tipo da Conta',
            'Operação',
        ],
    ]
    contador = 1
    for projeto in task.iterate(projetos):
        if projeto.vinculo_coordenador.eh_servidor():
            pessoa = projeto.vinculo_coordenador.pessoa
            servidor = projeto.vinculo_coordenador.relacionamento
            participacao = Participacao.objects.get(projeto=projeto, responsavel=True, vinculo_pessoa=projeto.vinculo_coordenador)
            banco = participacao.instituicao and str(participacao.instituicao) or servidor.pessoa_fisica.pagto_banco
            agencia = participacao.numero_agencia or servidor.pessoa_fisica.pagto_agencia
            tipo_conta = participacao.tipo_conta or '-'
            numero_conta = participacao.numero_conta or servidor.pessoa_fisica.pagto_ccor
            operacao = participacao.operacao or '-'
            row = [
                contador,
                yesno(projeto.tem_interesse_cartao_pesquisador, 'Sim,Não,Não informado'),
                projeto.edital.titulo,
                pessoa.nome,
                pessoa.pessoafisica.cpf,
                pessoa.pessoafisica.nascimento_data,
                projeto.uo.sigla,
                pessoa.pessoafisica.telefones_pessoais and pessoa.pessoafisica.telefones_pessoais.split(' ')[0].replace('(', '').replace(')', ''),
                pessoa.pessoafisica.telefones_pessoais and pessoa.pessoafisica.telefones_pessoais.split(' ')[1],
                servidor.email_institucional,
                pessoa.endereco_logradouro,
                pessoa.endereco_numero,
                pessoa.endereco_complemento,
                pessoa.endereco_bairro,
                pessoa.endereco_municipio and pessoa.endereco_municipio.nome,
                pessoa.endereco_municipio and pessoa.endereco_municipio.uf,
                pessoa.endereco_cep,
                pessoa.pessoafisica.rg,
                pessoa.pessoafisica.rg_orgao,
                pessoa.pessoafisica.rg_uf,
                pessoa.pessoafisica.rg_data,
                pessoa.pessoafisica.get_sexo_display(),
                servidor.pessoa_fisica.estado_civil,
                servidor.cargo_emprego_area or servidor.cargo_emprego,
                servidor.data_inicio_exercicio_no_cargo,
                servidor.data_inicio_exercicio_no_cargo.strftime('%d/%m/%Y').split('/', 1)[1] if servidor.data_inicio_exercicio_no_cargo else '',
                banco,
                agencia,
                numero_conta,
                tipo_conta,
                operacao,
            ]
            rows.append(row)
            contador += 1
    return XlsResponse(rows, processo=task)
