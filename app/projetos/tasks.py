from django.conf import settings
from django.db.models import Sum, ExpressionWrapper, F, FloatField

from comum.models import Vinculo
from djtools.assincrono import task
from djtools.templatetags.filters import format_
from djtools.utils import XlsResponse, send_notification
from projetos.models import Avaliacao, Edital, OfertaProjeto, OfertaProjetoPorGrupo, ItemMemoriaCalculo, Comunicador
from rh.models import Servidor


@task('Exportar Relatório de Dimensão para XLS')
def relatorio_dimensao_export_to_xls(quantidade_projetos, quantidade_participantes, participantes_por_area_tematica, task=None):
    task.start_progress()
    total_projetos = 0
    total_projetos_aprovados = 0
    rows = [['Projetos por Edital']]

    row = ['Edital', 'Projetos Submetidos', 'Projetos Aprovados']
    rows.append(row)
    for info in quantidade_projetos:
        total_projetos = total_projetos + info['total']
        total_projetos_aprovados = total_projetos_aprovados + info['aprovados']

        row = [format_(info['edital']), format_(info['total']), format_(info['aprovados'])]
        rows.append(row)
    task.update_progress(20)
    row = ['Total', format_(total_projetos), format_(total_projetos_aprovados)]
    rows.append(row)
    row = ['']
    rows.append(row)
    row = ['Projetos por Área Temática (Submetidos/Aprovados)']
    rows.append(row)
    row = [
        'Edital',
        'Comunicação',
        'Cultura',
        'Direitos Humanos e Justiça',
        'Educação',
        'Meio Ambiente',
        'Saúde',
        'Tecnologia e Produção',
        'Trabalho',
        'Multidisciplinar',
        'Outros/Não Informado',
        'Total Submetido',
        'Total Aprovado',
    ]
    rows.append(row)

    for info in quantidade_projetos:
        row = [
            format_(info['edital']),
            format_('%s/%s') % (info['comunicacao_total'], info['comunicacao_aprovados']),
            format_('%s/%s') % (info['cultura_total'], info['cultura_aprovados']),
            format_('%s/%s') % (info['direito_total'], info['direito_aprovados']),
            format_('%s/%s') % (info['educacao_total'], info['educacao_aprovados']),
            format_('%s/%s') % (info['meio_ambiente_total'], info['meio_ambiente_aprovados']),
            format_('%s/%s') % (info['saude_total'], info['saude_aprovados']),
            format_('%s/%s') % (info['tecnologia_total'], info['tecnologia_aprovados']),
            format_('%s/%s') % (info['trabalho_total'], info['trabalho_aprovados']),
            format_('%s/%s') % (info['multidisciplinar_total'], info['multidisciplinar_aprovados']),
            format_('%s/%s') % (info['outros_total'], info['outros_aprovados']),
            format_(info['total']),
            format_(info['aprovados']),
        ]
        rows.append(row)
    task.update_progress(40)
    row = ['']
    rows.append(row)
    row = ['Participantes por Edital']
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
    task.update_progress(60)

    row = ['']
    rows.append(row)
    row = ['Participantes por Área Temática']
    rows.append(row)
    row = ['Área', 'Bolsistas (Docentes/Téc. Adm/Discentes)', 'Voluntários (Docentes/Téc. Adm/Discentes)']
    rows.append(row)

    for info in participantes_por_area_tematica:
        row = [
            format_(info['area']),
            format_('%s/%s/%s') % (info['docentes_bolsistas'], info['tec_adm_bolsistas'], info['alunos_bolsistas']),
            format_('%s/%s/%s') % (info['docentes_voluntarios'], info['tec_adm_voluntarios'], info['alunos_voluntarios']),
        ]

        rows.append(row)

    task.update_progress(80)

    return XlsResponse(rows, processo=task)


@task('Exportar Relatório de Lições Aprendidas para XLS')
def relatorio_licoes_aprendidas_to_xls(licoes, task=None):
    rows = [['#', 'Campus', 'Edital', 'Projeto', 'Coordenador', 'Lição Aprendida', 'Área de Conhecimento']]
    contador = 0
    for licao in task.iterate(licoes):
        contador += 1
        if licao.projeto.vinculo_coordenador:
            coordenador = licao.projeto.vinculo_coordenador.pessoa.nome
        else:
            coordenador = licao.projeto.get_responsavel().pessoa.nome
        row = [
            contador,
            format_(licao.projeto.uo.nome),
            format_(licao.projeto.edital),
            format_(licao.projeto.titulo),
            format_(coordenador),
            format_(licao.descricao),
            format_(licao.area_licao_aprendida),
        ]
        rows.append(row)
    return XlsResponse(rows, processo=task)


@task('Exportar Relatório de Equipes de Projetos para XLS')
def listar_equipes_dos_projetos_to_xls(dados_do_projeto, task=None):
    rows = [
        [
            '#',
            'Campus',
            'Edital',
            'Projeto',
            'Nome',
            'CPF',
            'Lattes',
            'ORCID',
            'Vínculo',
            'Titulação',
            'Curso',
            'Observações',
            'Banco',
            'Agência',
            'Conta',
            'Tipo da conta',
            'Operação',
        ]
    ]

    contador = 1
    for dados in task.iterate(dados_do_projeto):
        nome_pessoa = '{} ({})'.format(dados['nome'], dados['matricula'])

        titulacao = dados['titulacao']
        if dados['nivel_ensino']:
            titulacao += f' - Nível {dados["nivel_ensino"]}'
        row = [
            contador,
            format_(dados['campus']),
            format_(dados['edital']),
            format_(dados['projeto']),
            format_(nome_pessoa),
            format_(dados['cpf']),
            format_(dados['lattes']),
            format_(dados['orcid']),
            format_(dados['vinculo']),
            format_(titulacao),
            format_(dados['curso']),
            format_(dados['obs']),
            format_(dados['banco']),
            format_(dados['agencia']),
            format_(dados['numero_conta']),
            format_(dados['tipo_conta']),
            format_(dados['operacao']),
        ]
        contador += 1
        rows.append(row)
    return XlsResponse(rows, processo=task)


@task('Exportar Projetos em Atraso para XLS')
def listar_projetos_em_atraso_export_to_xls(projetos, task=None):
    rows = [['#', 'Campus', 'Edital', 'Projeto', 'Coordenador', 'Email', 'Fim da Execução']]

    contador = 0
    for projeto in task.iterate(projetos):
        contador += 1
        if projeto.vinculo_coordenador:
            coordenador = projeto.vinculo_coordenador
        else:
            coordenador = projeto.get_responsavel()
        row = [
            contador,
            format_(projeto.uo.nome),
            format_(projeto.edital),
            format_(projeto.titulo),
            format_(coordenador.pessoa.nome),
            format_(coordenador.email_notificacao),
            format_(projeto.fim_execucao),
        ]
        rows.append(row)
    return XlsResponse(rows, processo=task)


@task('Exportar Relatório de Avaliadores de Projetos para XLS')
def listar_avaliadores_de_projetos_export_to_xls(avaliadores, task=None):
    rows = [['#', 'Nome', 'Matrícula', 'Instituição', 'Email', 'Áreas Temáticas']]
    contador = 0
    for avaliador in task.iterate(avaliadores):
        matricula = '-'
        if avaliador.vinculo.eh_servidor():
            matricula = (avaliador.vinculo.relacionamento.matricula,)

        areas_tematicas = avaliador.get_areas_tematicas().values_list('descricao', flat=True)
        areas = ', '.join(areas_tematicas)
        row = [
            contador,
            format_(avaliador.vinculo.pessoa.nome),
            format_(matricula),
            format_(avaliador.get_instituicao()),
            format_(avaliador.get_email()),
            format_(areas),
        ]
        rows.append(row)
    return XlsResponse(rows, processo=task)


@task('Exportar Relatório de Caracterização de Beneficiários para XLS')
def relatorio_caracterizacao_beneficiarios_to_xls(registros, task=None):
    rows = [['#', 'Campus', 'Edital', 'Projeto', 'Coordenador', 'Tipo de Beneficiário', 'Quantidade Prevista', 'Quantidade Atendida']]

    contador = 0
    total_prevista = registros.aggregate(total=Sum('quantidade'))['total']
    total_atendida = registros.aggregate(total=Sum('quantidade_atendida'))['total']
    for registro in task.iterate(registros):
        contador += 1
        coordenador = registro.projeto.vinculo_coordenador.pessoa.nome
        row = [
            contador,
            format_(registro.projeto.uo.nome),
            format_(registro.projeto.edital),
            format_(registro.projeto.titulo),
            format_(coordenador),
            format_(registro.tipo_beneficiario.descricao),
            format_(registro.quantidade),
            format_(registro.quantidade_atendida),
        ]
        rows.append(row)
    row = [
        'Total',
        '',
        '',
        '',
        '',
        '',
        total_prevista,
        total_atendida,
    ]
    rows.append(row)
    XlsResponse(rows, processo=task)


@task('Exportar Relatório Financeiro para XLS')
def relatorio_financeiro_to_xls(registros, texto, valor_total, recurso, task=None):
    contador = 0
    rows = [['', '', texto]]
    row = ['#', 'Campus', 'Edital', 'Projeto', 'Coordenador', 'Recurso (R$)']
    rows.append(row)
    for registro in task.iterate(registros):
        contador += 1
        coordenador = registro.vinculo_coordenador.pessoa.nome
        valor_linha = (
            hasattr(registro, 'valor')
            and registro.valor
            or ItemMemoriaCalculo.objects.filter(projeto=registro, origem=recurso.origem, despesa=recurso.despesa)
            .only('qtd', 'valor_unitario')
            .annotate(total=ExpressionWrapper(F('qtd') * F('valor_unitario'), output_field=FloatField()))
            .aggregate(valor=Sum('total'))['valor']
        )
        row = [
            contador,
            format_(registro.uo.nome),
            format_(registro.edital),
            format_(registro.titulo),
            format_(coordenador),
            format_(valor_linha),
        ]
        rows.append(row)
    row = [
        '',
        '',
        '',
        '',
        'Total',
        format_(valor_total),
    ]
    rows.append(row)
    XlsResponse(rows, processo=task)


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


@task('Notificar servidores sobre edital de extensão aberto')
def notificar_servidores_edital(edital, task=None):
    titulo = '[SUAP] Extensão: Edital com inscrições abertas'
    texto = (
        '<h1>Extensão</h1>'
        '<h2>Edital com inscrições abertas</h2>'
        f'<p>Olá, Servidor(a).</p>'
        f"<p>O edital '{edital.titulo}' foi publicado no SUAP e está com inscrições abertas.</p>"
        f'<p>As inscrições podem ser realizadas através do seguinte endereço: <a href="{settings.SITE_URL}/projetos/adicionar_projeto/{edital.id}/">{settings.SITE_URL}/projetos/adicionar_projeto/{edital.id}/</a></p>'
        f'<p class="more-info">Para mais informações, acesse: <a href="{settings.SITE_URL}/projetos/editais_abertos/">{settings.SITE_URL}/projetos/editais_abertos/</a></p>'
    )
    for oferta in task.iterate(OfertaProjeto.objects.filter(edital=edital)):
        vinculos = list(
            Vinculo.objects.filter(
                tipo_relacionamento__model='servidor',
                id__in=Servidor.objects.filter(ativo=True, setor__uo=oferta.uo).values_list('vinculos', flat=True),
            )
        )
        send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, vinculos)
    task.finalize('Notificações enviadas com sucesso.', f'/projetos/edital/{edital.id}/')


@task('Exportar Pareceres Emitidos para XLS')
def relatorio_pareceres_emitidos_to_xls(projetos, task=None):
    contador = 0
    rows = [['', '', 'Relatórios de Pareceres Emitidos']]
    row = ['#', 'Campus', 'Edital', 'Projeto', 'Parecer 1', 'Parecer 2', 'Parecer 3', 'Parecer 4', 'Parecer 5']
    rows.append(row)
    for projeto in task.iterate(projetos):
        contador += 1
        row = [
            contador,
            format_(projeto.uo.nome),
            format_(projeto.edital),
            format_(projeto.titulo),
        ]
        conta = 0
        for avaliacao in Avaliacao.objects.filter(projeto=projeto).order_by('id'):
            row.append(avaliacao.parecer)
            conta += 1
        while conta < 5:
            row.append(' ')
            conta += 1
        rows.append(row)
    XlsResponse(rows, processo=task)


@task('Executa rotina de classificação dos projetos do edital')
def executa_rotina_classificacao_projetos_edital(edital, task=None):
    if edital.forma_selecao == Edital.CAMPUS:
        for oferta in task.iterate(OfertaProjeto.objects.filter(edital=edital)):
            edital.classifica_projetos_extensao(uo=oferta.uo)
    elif edital.forma_selecao == Edital.GRUPO:
        for grupo in task.iterate(OfertaProjetoPorGrupo.objects.filter(edital=edital)):
            edital.classifica_projetos_extensao(grupo=grupo)
    else:
        edital.classifica_projetos_extensao()
    task.finalize('Rotina de classificação dos projetos executada com sucesso.', f'/projetos/edital/{edital.id}/')


@task('Mensagem enviada pelo comunicador da extensão')
def enviar_msg_comunicador_extensao(titulo, conteudo, vinculos, request, task=None):
    send_notification(titulo, conteudo, settings.DEFAULT_FROM_EMAIL, vinculos, categoria='Comunicador da Extensão')
    obj = Comunicador()
    obj.titulo = titulo
    obj.conteudo = conteudo
    obj.cadastrado_por = request.user.get_vinculo()
    obj.destinatarios = ', '.join([vinculo.__str__() for vinculo in vinculos])
    obj.save()
    task.finalize('Mensagem enviada com sucesso.', '/admin/projetos/comunicador/')
