from djtools.utils import mask_cpf

NOTURNO = 'Noturno'
VESPERTINO = 'Vespertino'
MATUTINO = 'Matutino'
EAD = 'EAD'
DIURNO = 'Diurno'
INTEGRAL = 'Integral'

TURNOS = {
    'Matutino': MATUTINO,
    'Manhã + 1 tarde por semana': MATUTINO,
    'Matutino/Vespertino': DIURNO,
    'matutino': MATUTINO,
    'Manhã + duas tardes por semana': MATUTINO,
    'Noite': NOTURNO,
    'noturno': NOTURNO,
    'Integral / Diurno': DIURNO,
    'Tarde': VESPERTINO,
    'Diurno (tarde/manhã)': DIURNO,
    'Diurno': DIURNO,
    'Vespertino + aulas no período da manhã': VESPERTINO,
    'Manhã e Tarde': DIURNO,
    'Licenciatura Noturno. Bacharelado 2 anos noturno e 2 anos Vespertino': DIURNO,
    'Diurno (manhã/tarde)': DIURNO,
    'Integral': INTEGRAL,
    'Vespertino + três manhãs por semana': VESPERTINO,
    'Integral/Diurno': DIURNO,
    'Vespertino e Noturno': NOTURNO,
    'Matutino + aulas no período da tarde': MATUTINO,
    'Matutino e Vespertino': DIURNO,
    'Tarde e Noite': NOTURNO,
    'Noturno': NOTURNO,
    'Integral - Diurno': DIURNO,
    'Vespertino': VESPERTINO,
    'Manhã': MATUTINO,
    'Matutino + duas tardes por semana': MATUTINO,
    'Diurno(Matutino/Vespertino)': DIURNO,
}

XML_LISTA = """
        <lista>
            <codigo>{}</codigo>
            <descricao>{}</descricao>
        </lista>
"""

XML_VAGA = """
        <vaga>
            <codigo-curso>{}</codigo-curso>
            <linha-pesquisa>{}</linha-pesquisa>
            <codigo-lista>{}</codigo-lista>
            <quantidade>{}</quantidade>
            <numero-alunos>{}</numero-alunos>
            <turno>{}</turno>
            <campus-polo>{}</campus-polo>
        </vaga>
"""

XML_CANDIDATO = """
    <candidato>
        <inscricao>{}</inscricao>
        <cpf>{}</cpf>
        <email>{}</email>
        <telefone>{}</telefone>
        <nome>{}</nome>
        <codigo-curso>{}</codigo-curso>
        <turno>{}</turno>
        <campus-polo>{}</campus-polo>
    </candidato>
"""

XML_CANDIDATO_VAGA = """
    <candidato-vaga>
        <inscricao>{}</inscricao>
        <codigo-curso>{}</codigo-curso>
        <codigo-lista>{}</codigo-lista>
        <turno>{}</turno>
        <classificacao>{}</classificacao>
        <aprovado>{}</aprovado>
        <eliminado>{}</eliminado>
        <campus-polo>{}</campus-polo>
        <linha-pesquisa>{}</linha-pesquisa>
    </candidato-vaga>
"""


def get_dados_arquivo(file):
    keys = file.readline().decode('iso-8859-1').strip().split(';')
    line = file.readline().decode('iso-8859-1')
    while line:
        tokens = line.strip().split(';')
        line = file.readline().decode('iso-8859-1')
        yield {key.replace('\ufeff', ''): tokens[i] for i, key in enumerate(keys)}


def processar_listas(lista, file):
    for dados in get_dados_arquivo(file):
        lista.append(XML_LISTA.format(dados['SIGLA'], dados['DESCRICAO']))


def processar_vagas(lista, file):
    codigos = set()
    for dados in get_dados_arquivo(file):
        codigos.add(dados['COD_CURSO_SUAP'])
        lista.append(
            XML_VAGA.format(
                dados['COD_CURSO_SUAP'],
                dados['LINHA_PESQUISA'],
                dados['LISTA'],
                dados['VAGAS'],
                dados['QTD_INSCRITOS'],
                TURNOS[dados['TURNO']],
                dados['POLO'],
            )
        )
    return codigos


def consultar_dados_candidato(cpf, file):
    for dados in get_dados_arquivo(file):
        if mask_cpf(dados['CPF']) == cpf:
            return dados


def processar_candidatos(lista, file):
    for dados in get_dados_arquivo(file):
        lista.append(
            XML_CANDIDATO.format(
                dados['INSCRICAO'],
                mask_cpf(dados['CPF']),
                dados['EMAIL'],
                dados['TELEFONE'],
                dados['NOME'],
                dados['COD_CURSO_SUAP'],
                TURNOS[dados['TURNO']],
                dados['POLO'],
            )
        )


def processar_resultado(lista, file):
    for dados in get_dados_arquivo(file):
        lista.append(
            XML_CANDIDATO_VAGA.format(
                dados['INSCRICAO'],
                dados['COD_CURSO_SUAP'],
                dados['LISTA'],
                TURNOS[dados['TURNO']],
                dados['CLASSIFICACAO'] or 999999,
                'Sim' if dados['APROVADO'] == 'S' else 'Não',
                'Sim' if dados['ELIMINADO'] == 'S' else 'Não',
                dados['POLO'],
                dados['LINHA_PESQUISA'],
            )
        )


def processar_arquivos(arquivo_listas, arquivo_vagas, arquivo_candidatos, arquivo_resultado):
    lista = []
    lista.append('<edital>')
    lista.append('  <listas>')
    processar_listas(lista, arquivo_listas)
    lista.append('  </listas>')
    lista.append('  <vagas>')
    codigos = processar_vagas(lista, arquivo_vagas)
    lista.append('  </vagas>')
    lista.append('  <candidatos>')
    processar_candidatos(lista, arquivo_candidatos)
    lista.append('  </candidatos>')
    lista.append('  <resultado>')
    processar_resultado(lista, arquivo_resultado)
    lista.append('  </resultado>')
    lista.append('</edital>')
    xml = '\n'.join(lista)
    return codigos, xml
