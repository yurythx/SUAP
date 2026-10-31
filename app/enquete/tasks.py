from collections import OrderedDict

from djtools.assincrono import task
from djtools.utils import XlsResponse, getattrr, render_html_file
from enquete.forms import FiltrarRespostasForm
from enquete.models import Resposta


@task('Processar Respostas da Enquete')
def processar_respostas_enquete(request, enquete, title, task=None):
    form = FiltrarRespostasForm(request.GET or None, enquete=enquete)
    form.ACTION = f'/enquete/ver_resultados/{enquete.id}/'
    participantes = form.get_participantes()
    respostas_participantes = (
        form.get_respostas_participantes().values('vinculo__pessoa__nome', 'data_cadastro', 'data_ultima_resposta').distinct('vinculo__pessoa__nome')
    )
    task.count(enquete.categoria_set.all())
    graficos = enquete.get_graficos_resultado(participantes, task)
    contexto = {
        'graficos': graficos,
        'enquete': enquete,
        'participantes': participantes,
        'respostas_participantes': respostas_participantes,
        'form': form,
        'title': title,
    }
    return render_html_file('enquete/templates/ver_resultados.html', contexto, request, task)


@task('Exportar Resultados de Enquetes para XLS')
def exportar_resultado_to_xls(enquete, participantes, task=None):
    task.count(enquete.categoria_set.all())
    task.count(participantes)
    task.count(enquete.categoria_set.all())
    enquete.get_graficos_resultado(participantes, task)
    exportacao = OrderedDict()
    if enquete.resultado_publico:
        campos = {
            'aluno': {
                'Nome': 'pessoa_fisica.nome',
                'CPF': 'pessoa_fisica.cpf',
                'Passaporte': 'pessoa_fisica.passaporte',
                'Sexo': 'pessoa_fisica.sexo',
                'Etnia/Raça': 'raca',
                'Município de Residência': 'cidade',
                'Naturalidade': 'naturalidade',
                'Naturalidade (Código IBGE)': 'naturalidade.codigo',
                'Estado': 'cidade.estado.get_sigla',
                'Zona Residencial': 'get_tipo_zona_residencial_display',
                'Campus': 'curso_campus.diretoria.setor.uo',
                'Código Curso': 'curso_campus.codigo',
                'Descrição do Curso': 'curso_campus.descricao',
                'Situação no Curso': 'situacao',
                'Polo': 'polo',
                'Nacionalidade': 'nacionalidade',
                'País de Origem': 'pais_origem',
                'Ano de Ingresso': 'ano_letivo',
                'Período de Ingresso': 'periodo_letivo',
                'Data de Matrícula': 'data_matricula',
                'Turno': 'turno',
                'Forma de Ingresso': 'forma_ingresso',
                'Convênio': 'convenio',
                'Período Atual': 'periodo_atual',
                'Diretoria': 'curso_campus.diretoria',
                'Modalidade': 'curso_campus.modalidade',
                'Nível de Ensino': 'curso_campus.modalidade.nivel_ensino',
                'Natureza de Participação': 'matriz.natureza_participacao',
            },
            'servidor': {
                'Nome': 'pessoa_fisica.nome',
                'CPF': 'pessoa_fisica.cpf',
                'Passaporte': 'pessoa_fisica.passaporte',
                'Sexo': 'pessoa_fisica.sexo',
                'Etnia/Raça': 'raca',
                'Matrícula': 'matricula',
                'Função': 'funcao.nome',
                'Atividade': 'atividade',
                'Setor': 'setor',
                'Cargo Emprego': 'cargo_emprego',
                'E-mail Institucional': 'email_institucional',
            },
            'prestadorservico': {
                'Nome': 'pessoa_fisica.nome',
                'CPF': 'pessoa_fisica.cpf',
                'Passaporte': 'pessoa_fisica.passaporte',
                'Sexo': 'pessoa_fisica.sexo',
                'Etnia/Raça': 'raca',
            },
        }
        count = 0
        for vinculo in task.iterate(participantes):
            count += 1
            relacionamento = vinculo.relacionamento
            nome_modelo = vinculo.tipo_relacionamento.model
            if nome_modelo not in exportacao:
                exportacao[nome_modelo] = []
                exportacao[nome_modelo].append(list(campos[nome_modelo]))
            valor_campos = []
            for attr in campos[nome_modelo].values():
                valor_campos.append(getattrr(relacionamento, attr))
            exportacao[nome_modelo].append(valor_campos)
    for categoria in task.iterate(enquete.categorias):
        cat_nome = f'Categoria Ordem #{categoria.ordem}'
        if enquete.resultado_publico:
            exportacao[cat_nome] = [['Participantes', *categoria.cabecalho, 'Data Resposta', 'Data da última resposta']]
        else:
            exportacao[cat_nome] = [[*categoria.cabecalho, 'Data Resposta', 'Data da última resposta']]
        if hasattr(categoria, 'tabela'):
            for row in categoria.tabela:
                resp = row[0]
                cpf = '-'
                data_cadastro = '-'
                data_ultima_resposta = '-'
                if isinstance(resp, Resposta):
                    cpf = resp.vinculo.pessoa.pessoafisica.cpf
                    data_cadastro = resp.data_cadastro
                    data_ultima_resposta = resp.data_ultima_resposta
                if enquete.resultado_publico:
                    linha = [cpf, *row, data_cadastro, data_ultima_resposta]
                else:
                    linha = [*row, data_cadastro, data_ultima_resposta]
                exportacao[cat_nome].append(linha)
    return XlsResponse(exportacao, processo=task, iterate_processo=False)
