from djtools.assincrono import task
from djtools.templatetags.filters import format_
from djtools.utils import XlsResponse


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
    rows = [['#', 'Campus', 'Edital', 'Projeto', 'Nome', 'Vínculo', 'Titulação', 'Curso', 'Banco', 'Agência', 'Conta']]

    contador = 1
    for dados in task.iterate(dados_do_projeto):
        if dados['lattes']:
            nome_pessoa = '{} ({}) - {}'.format(dados['nome'], dados['matricula'], dados['lattes'])
        else:
            nome_pessoa = '{} ({})'.format(dados['nome'], dados['matricula'])

        row = [
            contador,
            format_(dados['campus']),
            format_(dados['edital']),
            format_(dados['projeto']),
            format_(nome_pessoa),
            format_(dados['vinculo']),
            format_(dados['titulacao']),
            format_(dados['curso']),
            format_(dados['banco']),
            format_(dados['agencia']),
            format_(dados['conta']),
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
    rows = [['#', 'Nome', 'Matrícula', 'Instituição', 'Email']]
    contador = 0
    for avaliador in task.iterate(avaliadores):
        matricula = '-'
        if avaliador.vinculo.eh_servidor():
            matricula = (avaliador.vinculo.relacionamento.matricula,)

        row = [
            contador,
            format_(avaliador.vinculo.pessoa.nome),
            format_(matricula),
            format_(avaliador.get_instituicao()),
            format_(avaliador.get_email()),
        ]
        rows.append(row)
    return XlsResponse(rows, processo=task)


@task('Exportar Relatório de Caracterização de Beneficiários para XLS')
def relatorio_caracterizacao_beneficiarios_to_xls(registros, task=None):
    rows = [['#', 'Campus', 'Edital', 'Projeto', 'Coordenador', 'Tipo de Beneficiário', 'Quantidade Prevista', 'Quantidade Atendida']]

    contador = 0
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
    return XlsResponse(rows, processo=task)
