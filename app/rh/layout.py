layout_servidor_1 = {
    'descricao': 'SIAPE-SERVIDOR-EXTR I',
    'dica': 'Este arquivo insere Matrícula, Nome, Nome da Mãe, CPF, PIS, Estado Civil, Regime Jurídico, \
Situação, Dados Bancários, Afastamentos, Exclusões, Inatividades, Cargo, Classe, Nível, Padrão, Lotação.',
    'total': 332,
    'campos': {
        1: {'nome': 'GR-MATRICULA', 'tipo': 'N', 'tamanho': 12},
        2: {'nome': 'IT-NO-SERVIDOR', 'tipo': 'A', 'tamanho': 60},
        3: {'nome': 'IT-NO-MAE', 'tipo': 'A', 'tamanho': 50},
        4: {'nome': 'IT-NU-CPF', 'tipo': 'N', 'tamanho': 11},
        5: {'nome': 'IT-NU-PIS-PASEP', 'tipo': 'N', 'tamanho': 11},
        6: {'nome': 'IT-CO-ESTADO-CIVIL', 'tipo': 'N', 'tamanho': 1},
        7: {'nome': 'IT-SG-REGIME-JURIDICO', 'tipo': 'A', 'tamanho': 3},
        8: {'nome': 'IT-CO-SITUACAO-SERVIDOR', 'tipo': 'N', 'tamanho': 2},
        9: {'nome': 'IT-CO-BANCO-PGTO-SERVIDOR', 'tipo': 'N', 'tamanho': 3},
        10: {'nome': 'IT-CO-AGENCIA-BANCARIA-PGTO-SERV', 'tipo': 'A', 'tamanho': 6},
        11: {'nome': 'IT-NU-CCOR-PGTO-SERVIDOR', 'tipo': 'A', 'tamanho': 13},
        12: {'nome': 'IT-CO-GRUPO-OCOR-AFASTAMENTO', 'tipo': 'N', 'tamanho': 2},
        13: {'nome': 'IT-CO-OCOR-AFASTAMENTO', 'tipo': 'N', 'tamanho': 3},
        14: {'nome': 'IT-DA-INICIO-OCOR-AFASTAMENTO', 'tipo': 'N', 'tamanho': 8},
        15: {'nome': 'IT-DA-TERMINO-OCOR-AFASTAMENTO', 'tipo': 'N', 'tamanho': 8},
        16: {'nome': 'IT-CO-DIPL-AFASTAMENTO', 'tipo': 'N', 'tamanho': 2},
        17: {'nome': 'IT-DA-PUBL-DIPL-AFASTAMENTO', 'tipo': 'N', 'tamanho': 8},
        18: {'nome': 'IT-NU-DIPL-AFASTAMENTO', 'tipo': 'A', 'tamanho': 9},
        19: {'nome': 'IT-CO-GRUPO-OCOR-EXCLUSAO', 'tipo': 'N', 'tamanho': 2},
        20: {'nome': 'IT-CO-OCOR-EXCLUSAO', 'tipo': 'N', 'tamanho': 3},
        21: {'nome': 'IT-DA-OCOR-EXCLUSAO-SERV', 'tipo': 'N', 'tamanho': 8},
        22: {'nome': 'IT-CO-DIPL-EXCLUSAO', 'tipo': 'N', 'tamanho': 2},
        23: {'nome': 'IT-DA-PUBL-DIPL-EXCLUSAO', 'tipo': 'N', 'tamanho': 8},
        24: {'nome': 'IT-NU-DIPL-EXCLUSAO', 'tipo': 'A', 'tamanho': 9},
        25: {'nome': 'IT-CO-GRUPO-OCOR-INATIVIDADE', 'tipo': 'N', 'tamanho': 2},
        26: {'nome': 'IT-CO-OCOR-INATIVIDADE', 'tipo': 'N', 'tamanho': 3},
        27: {'nome': 'IT-DA-OCOR-INATIVIDADE-SERV', 'tipo': 'N', 'tamanho': 8},
        28: {'nome': 'IT-CO-DIPL-INATIVIDADE', 'tipo': 'N', 'tamanho': 2},
        29: {'nome': 'IT-DA-PUBL-DIPL-INATIVIDADE', 'tipo': 'N', 'tamanho': 8},
        30: {'nome': 'IT-NU-DIPL-INATIVIDADE', 'tipo': 'A', 'tamanho': 9},
        31: {'nome': 'IT-CO-GRUPO-CARGO-EMPREGO', 'tipo': 'N', 'tamanho': 3},
        32: {'nome': 'IT-CO-CARGO-EMPREGO', 'tipo': 'N', 'tamanho': 3},
        33: {'nome': 'IT-CO-CLASSE', 'tipo': 'A', 'tamanho': 1},
        34: {'nome': 'IT-CO-PADRAO', 'tipo': 'A', 'tamanho': 3},
        35: {'nome': 'IT-CO-NIVEL', 'tipo': 'N', 'tamanho': 3},
        36: {'nome': 'IT-DA-OCUPACAO-CARGO-EMPREGO', 'tipo': 'N', 'tamanho': 8},
        37: {'nome': 'IT-DA-SAIDA-CARGO-EMPREGO', 'tipo': 'N', 'tamanho': 8},
        38: {'nome': 'IT-CO-UORG-LOTACAO-SERVIDOR', 'tipo': 'N', 'tamanho': 9},
        39: {'nome': 'IT-DA-LOTACAO', 'tipo': 'N', 'tamanho': 8},
        40: {'nome': 'IT-DA-EXCLUSAO-INSTITUIDOR', 'tipo': 'N', 'tamanho': 8},
    },
}

layout_servidor_2 = {
    'descricao': 'SIAPE-SERVIDOR-EXTR II',
    'dica': 'Este arquivo insere Nascimento, Sexo, Carteria de Trabalho, Data de Cadastro no SIAPE, \
Nível Escolaridade, Ingresso no Órgão e Serviço Público, Função, Atividade, Jornada de Trabalho, Identidade, Aposentadoria.',
    'total': 239,
    'campos': {
        1: {'nome': 'GR-MATRICULA', 'tipo': 'N', 'tamanho': 12},
        2: {'nome': 'IT-DA-NASCIMENTO', 'tipo': 'N', 'tamanho': 8},
        3: {'nome': 'IT-CO-SEXO', 'tipo': 'A', 'tamanho': 1},
        4: {'nome': 'IT-QT-DEPENDENTE-IR', 'tipo': 'N', 'tamanho': 2},
        5: {'nome': 'IT-NU-CARTEIRA-TRABALHO', 'tipo': 'N', 'tamanho': 11},
        6: {'nome': 'IT-NU-SERIE-CARTEIRA-TRABALHO', 'tipo': 'N', 'tamanho': 5},
        7: {'nome': 'IT-SG-UF-CTRA-SERVIDOR', 'tipo': 'A', 'tamanho': 2},
        8: {'nome': 'IT-DA-PRIMEIRO-EMPREGO', 'tipo': 'N', 'tamanho': 8},
        9: {'nome': 'IT-DA-CADASTRAMENTO-SERVIDOR', 'tipo': 'N', 'tamanho': 8},
        10: {'nome': 'IT-CO-NIVEL-ESCOLARIDADE', 'tipo': 'N', 'tamanho': 2},
        11: {'nome': 'IT-CO-GRUPO-OCOR-INGR-ORGAO', 'tipo': 'N', 'tamanho': 2},
        12: {'nome': 'IT-CO-OCOR-INGR-ORGAO', 'tipo': 'N', 'tamanho': 3},
        13: {'nome': 'IT-DA-OCOR-INGR-ORGAO-SERV', 'tipo': 'N', 'tamanho': 8},
        14: {'nome': 'IT-CO-DIPL-INGR-ORGAO', 'tipo': 'N', 'tamanho': 2},
        15: {'nome': 'IT-DA-PUBL-DIPL-INGR-ORGAO', 'tipo': 'N', 'tamanho': 8},
        16: {'nome': 'IT-NU-DIPL-INGR-ORGAO', 'tipo': 'A', 'tamanho': 9},
        17: {'nome': 'IT-CO-GRUPO-OCOR-INGR-SPUB', 'tipo': 'N', 'tamanho': 2},
        18: {'nome': 'IT-CO-OCOR-INGR-SPUB', 'tipo': 'N', 'tamanho': 3},
        19: {'nome': 'IT-DA-OCOR-INGR-SPUB-SERV', 'tipo': 'N', 'tamanho': 8},
        20: {'nome': 'IT-CO-DIPL-INGR-SPUB', 'tipo': 'N', 'tamanho': 2},
        21: {'nome': 'IT-DA-PUBL-DIPL-INGR-SPUB', 'tipo': 'N', 'tamanho': 8},
        22: {'nome': 'IT-NU-DIPL-INGR-SPUB', 'tipo': 'A', 'tamanho': 9},
        23: {'nome': 'IT-SG-FUNCAO', 'tipo': 'A', 'tamanho': 3},
        24: {'nome': 'IT-CO-NIVEL-FUNCAO', 'tipo': 'N', 'tamanho': 4},
        25: {'nome': 'IT-SG-ESCOLARIDADE-FUNCAO', 'tipo': 'A', 'tamanho': 2},
        26: {'nome': 'IT-IN-OPCAO-FUNCAO', 'tipo': 'A', 'tamanho': 1},
        27: {'nome': 'IT-DA-INGRESSO-FUNCAO', 'tipo': 'N', 'tamanho': 8},
        28: {'nome': 'IT-DA-SAIDA-FUNCAO', 'tipo': 'N', 'tamanho': 8},
        29: {'nome': 'IT-CO-UORG-FUNCAO', 'tipo': 'N', 'tamanho': 9},
        30: {'nome': 'IT-SG-NOVA-FUNCAO', 'tipo': 'A', 'tamanho': 3},
        31: {'nome': 'IT-CO-NIVEL-NOVA-FUNCAO', 'tipo': 'N', 'tamanho': 4},
        32: {'nome': 'IT-SG-ESCOLARIDADE-NOVA-FUNCAO', 'tipo': 'A', 'tamanho': 2},
        33: {'nome': 'IT-IN-OPCAO-NOVA-FUNCAO', 'tipo': 'A', 'tamanho': 1},
        34: {'nome': 'IT-DA-INGRESSO-NOVA-FUNCAO', 'tipo': 'N', 'tamanho': 8},
        35: {'nome': 'IT-DA-SAIDA-NOVA-FUNCAO', 'tipo': 'N', 'tamanho': 8},
        36: {'nome': 'IT-CO-UORG-NOVA-FUNCAO', 'tipo': 'N', 'tamanho': 9},
        37: {'nome': 'IT-CO-JORNADA-TRABALHO', 'tipo': 'N', 'tamanho': 2},
        38: {'nome': 'IT-NU-NUMERADOR-PROP', 'tipo': 'N', 'tamanho': 2},
        39: {'nome': 'IT-NU-DENOMINADOR-PROP', 'tipo': 'N', 'tamanho': 2},
        40: {'nome': 'IT-NU-PROCESSO-APOSENTADORIA', 'tipo': 'A', 'tamanho': 30},
        41: {'nome': 'IT-CO-ATIVIDADE-FUNCAO', 'tipo': 'N', 'tamanho': 4},
        42: {'nome': 'IT-CO-ATIVIDADE-NOVA-FUNCAO', 'tipo': 'N', 'tamanho': 4},
    },
}

layout_servidor_3 = {
    'descricao': 'SIAPE-SERVIDOR-EXTR III',
    'dica': 'Este arquivo insere Código da Vaga, Título Eleitoral, Operação de Raio-X, \
Posse no Serviço Público e futuramente Titulação.',
    'total': 125,
    'campos': {
        1: {'nome': 'GR-MATRICULA', 'tipo': 'N', 'tamanho': 12},
        2: {'nome': 'IT-NU-MATRICULA-ANTERIOR', 'tipo': 'N', 'tamanho': 7},
        3: {'nome': 'IT-CO-REGISTRO-GERAL', 'tipo': 'A', 'tamanho': 14},
        4: {'nome': 'IT-SG-ORGAO-EXPEDIDOR-IDEN', 'tipo': 'A', 'tamanho': 5},
        5: {'nome': 'IT-DA-EXPEDICAO-IDEN', 'tipo': 'N', 'tamanho': 8},
        6: {'nome': 'IT-SG-UF-IDEN', 'tipo': 'A', 'tamanho': 2},
        7: {'nome': 'IT-DA-OBITO', 'tipo': 'N', 'tamanho': 8},
        8: {'nome': 'NU-TITULO-ELEITOR', 'tipo': 'N', 'tamanho': 13},
        9: {'nome': 'IT-IN-OPERADOR-RAIOX', 'tipo': 'N', 'tamanho': 1},
        10: {'nome': 'IT-CO-VAGA', 'tipo': 'N', 'tamanho': 7},
        11: {'nome': 'IT-CO-GRUPO-OCOR-INGR-SPUB-POSSE', 'tipo': 'N', 'tamanho': 2},
        12: {'nome': 'IT-CO-OCOR-INGR-SPUB-POSSE', 'tipo': 'N', 'tamanho': 3},
        13: {'nome': 'IT-DA-OCOR-INGR-SPUB-POSSE', 'tipo': 'N', 'tamanho': 8},
        14: {'nome': 'IT-CO-DIPL-INGR-SPUB-POSSE', 'tipo': 'N', 'tamanho': 2},
        15: {'nome': 'IT-DA-PUBL-DIPL-INGR-SPUB-POSSE', 'tipo': 'N', 'tamanho': 8},
        16: {'nome': 'IT-NU-DIPL-INGR-SPUB-POSSE', 'tipo': 'A', 'tamanho': 9},
        17: {'nome': 'IT-CO-UORG-EXERCICIO-SERV', 'tipo': 'N', 'tamanho': 9},
        18: {'nome': 'IT-NU-SEQ-FORMACAO-RH', 'tipo': 'N', 'tamanho': 3},
        19: {'nome': 'IT-CO-TITULACAO-FORMACAO-RH', 'tipo': 'N', 'tamanho': 2},
    },
}

layout_servidor_4 = {
    'descricao': 'SIAPE-SERVIDOR-DISPONIVEL',
    'dica': 'Este arquivo insere Endereço, Telefone, E-mail e Grupo Sangüíneo.',
    'total': 221,
    'campos': {
        1: {'nome': 'GR-MATRICULA-SERV-DISPONIVEL', 'tipo': 'N', 'tamanho': 12},
        2: {'nome': 'IT-NO-LOGRADOURO', 'tipo': 'A', 'tamanho': 40},
        3: {'nome': 'IT-NO-BAIRRO', 'tipo': 'A', 'tamanho': 25},
        4: {'nome': 'IT-NO-MUNICIPIO', 'tipo': 'A', 'tamanho': 30},
        5: {'nome': 'IT-CO-CEP', 'tipo': 'N', 'tamanho': 8},
        6: {'nome': 'IT-SG-UF-SERV-DISPONIVEL', 'tipo': 'A', 'tamanho': 2},
        7: {'nome': 'IT-NU-ENDERECO', 'tipo': 'A', 'tamanho': 6},
        8: {'nome': 'IT-NU-COMPLEMENTO-ENDERECO', 'tipo': 'A', 'tamanho': 21},
        9: {'nome': 'IT-CO-PAIS-ENDERECO', 'tipo': 'N', 'tamanho': 3},
        10: {'nome': 'IT-NU-DDD-TELEFONE', 'tipo': 'A', 'tamanho': 5},
        11: {'nome': 'IT-NU-TELEFONETELEFONE', 'tipo': 'A', 'tamanho': 9},
        12: {'nome': 'IT-NU-RAMAL-TELEFONE', 'tipo': 'A', 'tamanho': 5},
        13: {'nome': 'IT-ED-CORREIO-ELETRONICO', 'tipo': 'A', 'tamanho': 50},
        14: {'nome': 'IT-SG-GRUPO-SANGUINEO', 'tipo': 'A', 'tamanho': 2},
        15: {'nome': 'IT-SG-FATOR-RH', 'tipo': 'A', 'tamanho': 1},
    },
}

layout_servidor_5 = {
    'descricao': 'SIPE-U-RH',
    'dica': 'Este arquivo insere Naturalidade, Nome do Pai, Complementos do Título Eleitoral, \
Carteira de Habilitação, Fax e Identidade Única.',
    'total': 206,
    'campos': {
        1: {'nome': 'NU-CPF-RH', 'tipo': 'N', 'tamanho': 11},
        2: {'nome': 'NO-MUNICIPIO-NASCIMENTO-RH', 'tipo': 'A', 'tamanho': 50},
        3: {'nome': 'SG-UF-NASCIMENTO-RH', 'tipo': 'A', 'tamanho': 2},
        4: {'nome': 'NO-PAI-RH', 'tipo': 'A', 'tamanho': 50},
        5: {'nome': 'SG-UF-TITULO-ELEITOR-RH', 'tipo': 'A', 'tamanho': 2},
        6: {'nome': 'NU-ZONA-ELEITORAL-RH', 'tipo': 'N', 'tamanho': 3},
        7: {'nome': 'NU-SECAO-ELEITORAL-RH', 'tipo': 'A', 'tamanho': 4},
        8: {'nome': 'DA-EMISSAO-TITULO-ELEITOR-RH', 'tipo': 'A', 'tamanho': 8},
        9: {'nome': 'NU-CART-MOTORISTA-RH', 'tipo': 'N', 'tamanho': 10},
        10: {'nome': 'NU-REGISTRO-CART-MOTORISTA-RH', 'tipo': 'N', 'tamanho': 10},
        11: {'nome': 'IN-CATEGORIA-CART-MOTORISTA-RH', 'tipo': 'A', 'tamanho': 10},
        12: {'nome': 'SG-UF-CART-MOTORISTA-RH', 'tipo': 'A', 'tamanho': 2},
        13: {'nome': 'DA-EXPEDICAO-CART-MOTORISTA-RH', 'tipo': 'A', 'tamanho': 8},
        14: {'nome': 'DA-VALIDADE-CART-MOTORISTA-RH', 'tipo': 'A', 'tamanho': 8},
        15: {'nome': 'ED-FAX-RH', 'tipo': 'A', 'tamanho': 15},
        # O campo abaixo não é usado, mas é necessário para filtrar melhore os arquivos extraídos
        16: {'nome': 'ED-SG-UF-MUNICIPIO-RH', 'tipo': 'A', 'tamanho': 2},
        17: {'nome': 'CO-IDENT-UNICA-SIAPE-RH', 'tipo': 'N', 'tamanho': 9},
    },
}

layout_servidor_6 = {
    'descricao': 'SIAPE-SERVIDOR-FERIAS',
    'dica': 'Este arquivo insere as Férias relativas ao último ano. \
Caso deseje um histórico mais abrangente, utilize o próximo campo para executar essa tarefa.',
    'total': 46,
    'campos': {
        1: {'nome': 'GR-MATRICULA-EXERCICIO-FERIAS', 'tipo': 'N', 'tamanho': 16},
        2: {'nome': 'IT-DA-INICIO-FERIAS(1)', 'tipo': 'N', 'tamanho': 8},
        3: {'nome': 'IT-QT-DIAS-FERIAS(1)', 'tipo': 'N', 'tamanho': 2},
        4: {'nome': 'IT-DA-INTERRUPCAO-FERIAS(1)', 'tipo': 'N', 'tamanho': 8},
        5: {'nome': 'IT-DA-INICIO-FERIAS-INTERROMPIDA(1)', 'tipo': 'N', 'tamanho': 8},
        6: {'nome': 'IT-QT-DIA-FERIAS-INTERROMPIDA(1)', 'tipo': 'N', 'tamanho': 2},
    },
}


layout_servidor_7 = {
    'descricao': 'SIAPE-SERVIDOR-FERIAS-HIST',
    'dica': 'Este arquivo insere as Férias relativas a todo o histórico da Instituição. \
É demasiadamente grande e sugere-se usar apenas para popular incialmente a base de dados.',
    'total': 52,
    'campos': {
        1: {'nome': 'GR-MATRICULA-EXERCICIO-FERIAS-HIST', 'tipo': 'N', 'tamanho': 22},
        2: {'nome': 'IT-DA-INICIO-FERIAS(1)', 'tipo': 'N', 'tamanho': 8},
        3: {'nome': 'IT-QT-DIAS-FERIAS(1)', 'tipo': 'N', 'tamanho': 2},
        4: {'nome': 'IT-DA-INTERRUPCAO-FERIAS(1)', 'tipo': 'N', 'tamanho': 8},
        5: {'nome': 'IT-DA-INICIO-FERIAS-INTERROMPIDA(1)', 'tipo': 'N', 'tamanho': 8},
        6: {'nome': 'IT-QT-DIA-FERIAS-INTERROMPIDA(1)', 'tipo': 'N', 'tamanho': 2},
    },
}

layout_servidor_8 = {
    'descricao': 'SIAPE-SERVIDOR-HISTORICO (Afastamentos)',
    'dica': 'Este arquivo insere os Afastamentos relativas a todo o histórico da Instituição. \
É demasiadamente grande e sugere-se usar apenas para popular incialmente a base de dados ou quando se perceber que \
há lacunas nos relatórios de ponto.',
    'total': 60,
    'campos': {
        1: {'nome': 'GR-MATRICULA-ANO-MES', 'tipo': 'N', 'tamanho': 18},
        2: {'nome': 'IT-CO-GRUPO-OCOR-AFASTAMENTO', 'tipo': 'N', 'tamanho': 2},
        3: {'nome': 'IT-CO-OCOR-AFASTAMENTO', 'tipo': 'N', 'tamanho': 3},
        4: {'nome': 'IT-DA-INICIO-OCOR-AFASTAMENTO', 'tipo': 'N', 'tamanho': 8},
        5: {'nome': 'IT-DA-TERMINO-OCOR-AFASTAMENTO', 'tipo': 'N', 'tamanho': 8},
        6: {'nome': 'IT-CO-DIPL-AFASTAMENTO', 'tipo': 'N', 'tamanho': 2},
        7: {'nome': 'IT-DA-PUBL-DIPL-AFASTAMENTO', 'tipo': 'N', 'tamanho': 8},
        8: {'nome': 'IT-NU-DIPL-AFASTAMENTO', 'tipo': 'A', 'tamanho': 9},
    },
}

layout_setor = {
    'descricao': 'SIAPE-UNIDADEORGANIZACIONAL',
    'dica': 'Este arquivo insere Setores.',
    'total': 81,
    'campos': {
        1: {'nome': 'IT-IN-STATUS-REGISTRO-TABELA', 'tipo': 'N', 'tamanho': 1},
        2: {'nome': 'GR-IDENTIFICACAO-UORG', 'tipo': 'N', 'tamanho': 14},
        3: {'nome': 'IT-NO-UNIDADE-ORGANIZACIONAL', 'tipo': 'A', 'tamanho': 40},
        4: {'nome': 'IT-SG-UNIDADE-ORGANIZACIONAL', 'tipo': 'A', 'tamanho': 10},
        5: {'nome': 'IT-CO-UORG-VINCULACAO', 'tipo': 'N', 'tamanho': 14},
    },
}
layout_atividade = {
    'descricao': 'SIAPE-ATIVIDADE',
    'dica': 'Este arquivo insere Atividades.',
    'total': 37,
    'campos': {
        1: {'nome': 'IT-IN-STATUS-REGISTRO-TABELA', 'tipo': 'N', 'tamanho': 1},
        2: {'nome': 'IT-CO-ATIVIDADE', 'tipo': 'N', 'tamanho': 4},
        3: {'nome': 'IT-NO-ATIVIDADE', 'tipo': 'A', 'tamanho': 30},
    },
}
layout_funcao = {
    'descricao': 'SIAPE-FUNCAO',
    'dica': 'Este arquivo insere Funções.',
    'total': 46,
    'campos': {
        1: {'nome': 'IT-IN-STATUS-REGISTRO-TABELA', 'tipo': 'N', 'tamanho': 1},
        2: {'nome': 'IT-SG-FUNCAO', 'tipo': 'A', 'tamanho': 3},
        3: {'nome': 'IT-NO-FUNCAO', 'tipo': 'A', 'tamanho': 40},
    },
}
layout_cargoclasse = {
    'descricao': 'SIAPE-CLASSE',
    'dica': 'Este arquivo insere Classes de Cargos.',
    'total': 19,
    'campos': {
        1: {'nome': 'IT-IN-STATUS-REGISTRO-TABELA', 'tipo': 'N', 'tamanho': 1},
        2: {'nome': 'IT-CO-CLASSE', 'tipo': 'A', 'tamanho': 1},
        3: {'nome': 'IT-NO-CLASSE', 'tipo': 'A', 'tamanho': 15},
    },
}

layout_diplomalegal = {
    'descricao': 'SIAPE-DIPLOMA-LEGAL',
    'dica': 'Este arquivo insere Diplomas Legais.',
    'total': 29,
    'campos': {
        1: {'nome': 'IT-IN-STATUS-REGISTRO-TABELA', 'tipo': 'N', 'tamanho': 1},
        2: {'nome': 'IT-CO-DIPLOMA-LEGAL', 'tipo': 'N', 'tamanho': 2},
        3: {'nome': 'IT-SG-DIPLOMA-LEGAL', 'tipo': 'A', 'tamanho': 4},
        4: {'nome': 'IT-NO-DIPLOMA-LEGAL', 'tipo': 'A', 'tamanho': 20},
    },
}

layout_grupocargoemprego = {
    'descricao': 'SIAPE-GRUPO-CARGO-EMPREGO',
    'dica': 'Este arquivo insere Grupos de Cargos.',
    'total': 51,
    'campos': {
        1: {'nome': 'IT-IN-STATUS-REGISTRO-TABELA', 'tipo': 'N', 'tamanho': 1},
        2: {'nome': 'IT-CO-GRUPO-CARGO-EMPREGO', 'tipo': 'N', 'tamanho': 3},
        3: {'nome': 'IT-SG-GRUPO-CARGO-EMPREGO', 'tipo': 'A', 'tamanho': 5},
        4: {'nome': 'IT-NO-GRUPO-CARGO-EMPREGO', 'tipo': 'A', 'tamanho': 40},
    },
}
layout_cargoemprego = {
    'descricao': 'SIAPE-CARGO-EMPREGO',
    'dica': 'Este arquivo insere Cargos.',
    'total': 51,
    'campos': {
        1: {'nome': 'IT-IN-STATUS-REGISTRO-TABELA', 'tipo': 'N', 'tamanho': 1},
        2: {'nome': 'GR-IDEN-CARGO-EMPREGO', 'tipo': 'N', 'tamanho': 6},
        3: {'nome': 'IT-NO-CARGO-EMPREGO', 'tipo': 'A', 'tamanho': 40},
        4: {'nome': 'IT-SG-ESCOLARIDADE', 'tipo': 'A', 'tamanho': 2},
    },
}
layout_grupoocorrencia = {
    'descricao': 'SIAPE-GRUPO-OCORRENCIA',
    'dica': 'Este arquivo insere Grupos de Ocorrência.',
    'total': 35,
    'campos': {
        1: {'nome': 'IT-IN-STATUS-REGISTRO-TABELA', 'tipo': 'N', 'tamanho': 1},
        2: {'nome': 'IT-CO-GRUPO-OCORRENCIA', 'tipo': 'N', 'tamanho': 2},
        3: {'nome': 'IT-NO-GRUPO-OCORRENCIA', 'tipo': 'A', 'tamanho': 30},
    },
}
layout_jornadatrabalho = {
    'descricao': 'SIAPE-JORNADA-TRABALHO',
    'dica': 'Este arquivo insere Jornadas de Trabalho.',
    'total': 25,
    'campos': {
        1: {'nome': 'IT-IN-STATUS-REGISTRO-TABELA', 'tipo': 'N', 'tamanho': 1},
        2: {'nome': 'IT-CO-JORNADA-TRABALHO', 'tipo': 'N', 'tamanho': 2},
        3: {'nome': 'IT-NO-JORNADA-TRABALHO', 'tipo': 'A', 'tamanho': 20},
    },
}
layout_nivelescolaridade = {
    'descricao': 'SIAPE-NIVEL-ESCOLARIDADE',
    'dica': 'Este arquivo insere Npiveis de Escolaridade.',
    'total': 50,
    'campos': {
        1: {'nome': 'IT-IN-STATUS-REGISTRO-TABELA', 'tipo': 'N', 'tamanho': 1},
        2: {'nome': 'IT-CO-NIVEL-ESCOLARIDADE', 'tipo': 'N', 'tamanho': 2},
        3: {'nome': 'IT-NO-NIVEL-ESCOLARIDADE', 'tipo': 'A', 'tamanho': 45},
    },
}
layout_ocorrencia = {
    'descricao': 'SIAPE-OCORRENCIA',
    'dica': 'Este arquivo insere Ocorrências.',
    'total': 58,
    'campos': {
        1: {'nome': 'IT-IN-STATUS-REGISTRO-TABELA', 'tipo': 'N', 'tamanho': 1},
        2: {'nome': 'GR-IDEN-OCORRENCIA', 'tipo': 'N', 'tamanho': 5},
        3: {'nome': 'IT-NO-OCORRENCIA', 'tipo': 'A', 'tamanho': 50},
    },
}
layout_regimejuridico = {
    'descricao': 'SIAPE-REGIME-JURIDICO',
    'dica': 'Este arquivo insere Regimes Jurídicos.',
    'total': 41,
    'campos': {
        1: {'nome': 'IT-IN-STATUS-REGISTRO-TABELA', 'tipo': 'N', 'tamanho': 1},
        2: {'nome': 'IT-SG-REGIME-JURIDICO', 'tipo': 'A', 'tamanho': 3},
        3: {'nome': 'IT-NO-REGIME-JURIDICO', 'tipo': 'A', 'tamanho': 35},
    },
}
layout_pais = {
    'descricao': 'SIAPE-PAIS',
    'dica': 'Este arquivo insere Países.',
    'total': 37,
    'campos': {
        1: {'nome': 'IT-IN-STATUS-REGISTRO-TABELA', 'tipo': 'N', 'tamanho': 1},
        2: {'nome': 'IT-CO-PAIS', 'tipo': 'A', 'tamanho': 3},
        3: {'nome': 'IT-NO-PAIS', 'tipo': 'A', 'tamanho': 30},
        4: {'nome': 'IT-IN-PAIS-EQUIPARADO', 'tipo': 'A', 'tamanho': 1},
    },
}
layout_situacao = {
    'descricao': 'SIAPE-SITUACAO-SERVIDOR',
    'dica': 'Este arquivo insere Situações.',
    'total': 25,
    'campos': {
        1: {'nome': 'IT-IN-STATUS-REGISTRO-TABELA', 'tipo': 'N', 'tamanho': 1},
        2: {'nome': 'IT-CO-SITUACAO-SERVIDOR', 'tipo': 'A', 'tamanho': 2},
        3: {'nome': 'IT-NO-SITUACAO-SERVIDOR', 'tipo': 'A', 'tamanho': 20},
    },
}
layout_titulacao = {
    'descricao': 'SIAPE-UF',
    'total': 30,
    'campos': {1: {'nome': 'CO-FORMACAO', 'tipo': 'N', 'tamanho': 4}, 2: {'nome': 'NO-FORMACAO', 'tipo': 'A', 'tamanho': 40}},
}
layout_estadocivil = {
    'descricao': 'SIAPE-ESTADO-CIVIL',
    'dica': 'Este arquivo insere Estados Civis.',
    'total': 29,
    'campos': {
        1: {'nome': 'IT-IN-STATUS-REGISTRO-TABELA', 'tipo': 'N', 'tamanho': 1},
        2: {'nome': 'IT-CO-ESTADO-CIVIL', 'tipo': 'N', 'tamanho': 1},
        3: {'nome': 'IT-NO-ESTADO-CIVIL', 'tipo': 'A', 'tamanho': 25},
    },
}

layout_banco = {
    'descricao': 'SIAPE-BANCOS',
    'dica': 'Este arquivo insere Bancos.',
    'total': 51,
    'campos': {
        1: {'nome': 'IT-IN-STATUS-REGISTRO-TABELA', 'tipo': 'N', 'tamanho': 1},
        2: {'nome': 'IT-CO-BANCO', 'tipo': 'N', 'tamanho': 3},
        3: {'nome': 'IT-NO-BANCO', 'tipo': 'A', 'tamanho': 30},
        4: {'nome': 'IT-SG-BANCO', 'tipo': 'A', 'tamanho': 15},
    },
}

layout_pensionista = {
    'descricao': 'SIAPE-BENEFICIARIO-PENSAO',
    'dica': 'Este arquivo insere Pensionistas.',
    'total': 388,
    'campos': {
        1: {'nome': 'IT-DA-ANO-MES-PAGAMENTO', 'tipo': 'N', 'tamanho': 6},
        2: {'nome': 'IT-NU-MATRICULA-BENEF-PENSAO', 'tipo': 'N', 'tamanho': 8},
        3: {'nome': 'IT-NO-BENEFICIARIO-PENSAO', 'tipo': 'A', 'tamanho': 45},
        4: {'nome': 'IT-DA-NASCIMENTO-BENEF-PENSAO', 'tipo': 'N', 'tamanho': 8},
        5: {'nome': 'IT-NU-CPF', 'tipo': 'N', 'tamanho': 11},
        6: {'nome': 'IT-CO-SEXO', 'tipo': 'A', 'tamanho': 1},
        7: {'nome': 'IT-CO-ESTADO-CIVIL', 'tipo': 'N', 'tamanho': 1},
        8: {'nome': 'IT-QT-DEPENDENTE-IR', 'tipo': 'N', 'tamanho': 2},
        9: {'nome': 'IT-CO-REGISTRO-GERAL', 'tipo': 'N', 'tamanho': 14},
        10: {'nome': 'IT-SG-ORGAO-EXPEDIDOR-IDEN', 'tipo': 'A', 'tamanho': 5},
        11: {'nome': 'IT-DA-EXPEDICAO-IDEN', 'tipo': 'N', 'tamanho': 8},
        12: {'nome': 'IT-SG-UF-IDEN', 'tipo': 'A', 'tamanho': 2},
        13: {'nome': 'IT-NO-LOGRADOURO', 'tipo': 'A', 'tamanho': 40},
        14: {'nome': 'IT-NO-BAIRRO', 'tipo': 'A', 'tamanho': 25},
        15: {'nome': 'IT-NO-MUNICIPIO', 'tipo': 'A', 'tamanho': 30},
        16: {'nome': 'IT-CO-CEP', 'tipo': 'N', 'tamanho': 8},
        17: {'nome': 'IT-NU-TELEFONE', 'tipo': 'N', 'tamanho': 12},
        18: {'nome': 'IT-SG-UF', 'tipo': 'A', 'tamanho': 2},
        19: {'nome': 'IT-CO-ORGAO(1)', 'tipo': 'N', 'tamanho': 5},
        20: {'nome': 'IT-NU-MATRICULA(1)', 'tipo': 'N', 'tamanho': 7},
        21: {'nome': 'IT-DA-INICIO-OCOR-PENSAO', 'tipo': 'N', 'tamanho': 8},
        22: {'nome': 'IT-DA-TERMINO-OCOR-PENSAO', 'tipo': 'N', 'tamanho': 8},
        23: {'nome': 'IT-NO-MAE', 'tipo': 'A', 'tamanho': 50},
        24: {'nome': 'IT-ED-CORREIO-ELETRONICO', 'tipo': 'A', 'tamanho': 50},
        25: {'nome': 'IT-NU-TITULO-ELEITOR', 'tipo': 'N', 'tamanho': 13},
        26: {'nome': 'IT-SG-UF-TITULO-ELEITOR', 'tipo': 'A', 'tamanho': 2},
        27: {'nome': 'IT-NU-ZONA-ELEITORAL', 'tipo': 'N', 'tamanho': 3},
        28: {'nome': 'IT-NU-SECAO-ELEITORAL', 'tipo': 'A', 'tamanho': 4},
        29: {'nome': 'IT-DA-EMISSAO-TITULO-ELEITOR', 'tipo': 'N', 'tamanho': 8},
    },
}

layout_dependente = {
    'descricao': 'SIAPE-DEPENDENTE-EXTR',
    'dica': 'Este arquivo insere Dependentes Econômicos.',
    'total': 187,
    'campos': {
        1: {'nome': 'IT-NU-DEPENDENTE', 'tipo': 'N', 'tamanho': 8},
        2: {'nome': 'IT-NO-DEPENDENTE', 'tipo': 'A', 'tamanho': 60},
        3: {'nome': 'IT-CO-SEXO', 'tipo': 'A', 'tamanho': 1},
        4: {'nome': 'GR-MATRICULA-DEPENDENCIA-SERV(1)', 'tipo': 'N', 'tamanho': 12},
        5: {'nome': 'IT-CO-GRAU-PARENTESCO(1)', 'tipo': 'N', 'tamanho': 3},
        6: {'nome': 'IT-NU-CPF', 'tipo': 'N', 'tamanho': 11},
        7: {'nome': 'IT-NO-MAE', 'tipo': 'A', 'tamanho': 50},
        8: {'nome': 'IT-DA-NASCIMENTO', 'tipo': 'N', 'tamanho': 8},
        9: {'nome': 'IT-NU-RG', 'tipo': 'A', 'tamanho': 14},
        10: {'nome': 'IT-SG-UF-RG', 'tipo': 'A', 'tamanho': 2},
        11: {'nome': 'IT-SG-ORGAO-EXPEDIDOR-RG', 'tipo': 'A', 'tamanho': 5},
        12: {'nome': 'IT-DA-EXPEDICAO-RG', 'tipo': 'N', 'tamanho': 8},
        13: {'nome': 'IT-CO-CONDICAO-DEPENDENTE(1)', 'tipo': 'N', 'tamanho': 3},
    },
}

layout_grau_parentesco = {
    'descricao': 'SIAPE-PARENTESCO',
    'dica': 'Este arquivo insere Graus de Parentesco.',
    'total': 56,
    'campos': {
        1: {'nome': 'IT-IN-STATUS-REGISTRO-TABELA', 'tipo': 'N', 'tamanho': 1},
        2: {'nome': 'IT-CO-GRAU-PARENTESCO', 'tipo': 'N', 'tamanho': 3},
        3: {'nome': 'IT-NO-GRAU-PARENTESCO', 'tipo': 'A', 'tamanho': 50},
    },
}

layout_beneficio = {
    'descricao': 'SIAPE-BENEFICIO',
    'dica': 'Este arquivo insere Benefícios.',
    'total': 35,
    'campos': {
        1: {'nome': 'IT-CO-BENEFICIO', 'tipo': 'N', 'tamanho': 2},
        2: {'nome': 'IT-NO-BENEFICIO', 'tipo': 'A', 'tamanho': 30},
        3: {'nome': 'IT-IN-STATUS-REGISTRO-TABELA', 'tipo': 'N', 'tamanho': 1},
    },
}

layout_beneficio_dependente = {
    'descricao': 'SIAPE-BENEFICIO-DEPENDENTE',
    'dica': """Este arquivo associa os Benefícios aos Dependentes.
                                    É necessário  que ambas as tabelas já tenham sido populadas.""",
    'total': 40,
    'campos': {
        1: {'nome': 'GR-IDENT-BENEFICIO-DEPENDENTE', 'tipo': 'N', 'tamanho': 22},
        2: {'nome': 'IT-DA-INIC-BENEFICIO-DEPENDENTE', 'tipo': 'N', 'tamanho': 8},
        3: {'nome': 'IT-DA-TERM-BENEFICIO-DEPENDENTE', 'tipo': 'N', 'tamanho': 8},
    },
}
