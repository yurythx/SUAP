TIPO_PERMISSAO = ['add', 'change', 'delete']

gp = {}


def get_lista_permissao(lista, permissoes):
    retLista = []
    for item in lista:
        if item[0] in permissoes:
            retLista.append(item[1])

    return retLista


def planejamento_permissoes(gp):
    # Listas de perfis de permissão
    gp_administrador = []
    gp_gerente_sistemico = []
    gp_gerente_campus = []

    # Listas de permissões por modelo
    configuracao = [[i, f'planejamento.configuracao.{i}_configuracao'] for i in TIPO_PERMISSAO]
    dimensao = [[i, f'planejamento.dimensao.{i}_dimensao'] for i in TIPO_PERMISSAO]
    origemrecurso = [[i, f'planejamento.origemrecurso.{i}_origemrecurso'] for i in TIPO_PERMISSAO]
    unidade_administrativa = [[i, f'planejamento.unidadeadministrativa.{i}_unidadeadministrativa'] for i in TIPO_PERMISSAO]
    unidade_medida = [[i, f'planejamento.unidademedida.{i}_unidademedida'] for i in TIPO_PERMISSAO]
    natureza_despesa = [[i, f'planejamento.naturezadespesa.{i}_naturezadespesa'] for i in TIPO_PERMISSAO]
    objetivo_estrategico = [[i, f'planejamento.objetivoestrategico.{i}_objetivoestrategico'] for i in TIPO_PERMISSAO]
    meta = [[i, f'planejamento.meta.{i}_meta'] for i in TIPO_PERMISSAO]
    meta_unidade = [[i, f'planejamento.metaunidade.{i}_metaunidade'] for i in TIPO_PERMISSAO]
    meta_unidade_acao_proposta = [[i, f'planejamento.metaunidadeacaoproposta.{i}_metaunidadeacaoproposta'] for i in TIPO_PERMISSAO]
    acao_proposta = [[i, f'planejamento.acaoproposta.{i}_acaoproposta'] for i in TIPO_PERMISSAO]
    acao = [[i, f'planejamento.acao.{i}_acao'] for i in TIPO_PERMISSAO]
    acaoextrateto = [[i, f'planejamento.acaoextrateto.{i}_acaoextrateto'] for i in TIPO_PERMISSAO]
    atividade = [[i, f'planejamento.atividade.{i}_atividade'] for i in TIPO_PERMISSAO]

    # Cria permissoes para Administrador de acordo com o ticket #533
    #     - Cadastro de Configuracoes
    #     - Cadastro de Dimensoes
    #     - Cadastro de Unidades Administrativas
    #     - Cadastro de Unidades de Medida
    gp_administrador += get_lista_permissao(configuracao, ['add', 'change'])
    gp_administrador += get_lista_permissao(dimensao, ['add', 'change', 'delete'])
    gp_administrador += get_lista_permissao(origemrecurso, ['add', 'change', 'delete'])
    gp_administrador += get_lista_permissao(unidade_administrativa, ['add', 'change', 'delete'])
    gp_administrador += get_lista_permissao(unidade_medida, ['add', 'change', 'delete'])
    gp_administrador += get_lista_permissao(natureza_despesa, ['add', 'change', 'delete'])
    gp_administrador += get_lista_permissao(objetivo_estrategico, ['add', 'change', 'delete'])
    gp_administrador += get_lista_permissao(meta, ['add', 'change', 'delete'])
    gp_administrador += get_lista_permissao(meta_unidade, ['add', 'change', 'delete'])
    gp_administrador += get_lista_permissao(acao_proposta, ['add', 'change', 'delete'])
    gp_administrador += get_lista_permissao(meta_unidade_acao_proposta, ['add', 'change', 'delete'])
    gp_administrador += get_lista_permissao(acao, ['add', 'change', 'delete'])
    gp_administrador += get_lista_permissao(acaoextrateto, ['add', 'change', 'delete'])
    gp_administrador += get_lista_permissao(atividade, ['add', 'change', 'delete'])

    # Cria permissoes para Gerente Sistêmico de acordo com o ticket #533
    #     - Cadastro de Objetivos Estratégicos
    #     - Cadastro de Metas
    #     - Cadastro de Ações Propostas
    #     - Cadastro de Ações
    #     - Cadastro de Atividades
    gp_gerente_sistemico += get_lista_permissao(objetivo_estrategico, ['add', 'change', 'delete'])
    gp_gerente_sistemico += get_lista_permissao(meta, ['add', 'change', 'delete'])
    gp_gerente_sistemico += get_lista_permissao(meta_unidade, ['add', 'change', 'delete'])
    gp_gerente_sistemico += get_lista_permissao(acao_proposta, ['add', 'change', 'delete'])
    gp_gerente_sistemico += get_lista_permissao(meta_unidade_acao_proposta, ['add', 'change', 'delete'])
    gp_gerente_sistemico += get_lista_permissao(acao, ['add', 'change', 'delete'])
    gp_gerente_sistemico += get_lista_permissao(acaoextrateto, ['add', 'change', 'delete'])
    gp_gerente_sistemico += get_lista_permissao(atividade, ['add', 'change', 'delete'])

    # Cria permissoes para Gerente Campus de acordo com o ticket #533
    #     - Cadastro de Ações
    #     - Cadastrp de Atividades
    gp_gerente_campus += get_lista_permissao(meta_unidade, ['change'])
    gp_gerente_campus += get_lista_permissao(acao, ['add', 'change', 'delete'])
    gp_gerente_campus += get_lista_permissao(acao_proposta, ['add', 'change', 'delete'])
    gp_gerente_campus += get_lista_permissao(acaoextrateto, ['add', 'change', 'delete'])
    gp_gerente_campus += get_lista_permissao(atividade, ['add', 'change', 'delete'])

    # Faz a associacao com o dicionário de grupos e permissões
    gp['Administrador de Planejamento'] = gp_administrador
    gp['Coordenador de Planejamento Sistêmico'] = gp_gerente_sistemico
    gp['Coordenador de Planejamento'] = gp_gerente_campus
