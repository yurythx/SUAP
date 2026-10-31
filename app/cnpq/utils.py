from html import unescape


def _decode_html_entities(value):
    if isinstance(value, str):
        return unescape(value)
    if isinstance(value, list):
        return [_decode_html_entities(item) for item in value]
    if isinstance(value, dict):
        return {key: _decode_html_entities(item) for key, item in value.items()}
    return value


def extrair_dados_curriculo_lattes(curriculo):
    """
    Extrai e estrutura os dados de um currículo Lattes.

    Args:
        curriculo: Objeto do tipo CurriculoVittaeLattes

    Returns:
        dict: Dicionário com todos os dados estruturados do currículo Lattes
    """
    if not curriculo:
        return None

    dados_lattes = {
        'biografia': curriculo.dado_geral.texto_resumo if curriculo.dado_geral else None,
        'formacao_academica': [],
        'grande_area': [],
        'area_atuacao': [],
        'grupos_pesquisa': [],
        'publicacoes': {
            'artigos_completos': [],
            'artigos_resumos': [],
            'trabalhos_eventos': [],
            'livros': [],
            'capitulos': [],
        },
        'producoes_bibliograficas': {
            'textos_jornal_revista': [],
            'prefacios_posfacios': [],
            'traducoes': [],
            'outras': [],
        },
        'producoes_tecnicas': {
            'softwares': [],
            'produtos_tecnologicos': [],
            'processos_tecnicas': [],
            'trabalhos_tecnicos': [],
            'patentes': [],
        },
        'projetos': {
            'pesquisa': [],
            'extensao': [],
            'desenvolvimento': [],
        },
        'premios_titulos': [],
        'link_lattes': f'http://lattes.cnpq.br/{curriculo.numero_identificador}' if curriculo.numero_identificador else None,
    }

    # Formação Acadêmica
    if curriculo.dado_geral:
        for formacao in curriculo.dado_geral.formacoes_academicas_titulacoes.order_by('-ano_conclusao'):
            dados_lattes['formacao_academica'].append(
                {
                    'tipo': formacao.get_tipo(),
                    'curso': formacao.nome_curso,
                    'instituicao': formacao.nome_instituicao,
                    'ano_inicio': formacao.ano_inicio,
                    'ano_conclusao': formacao.ano_conclusao,
                    'titulo': formacao.titulo_trabalho_conclusao,
                    'orientador': formacao.nome_orientador,
                }
            )

        # Áreas de Atuação
        for area in curriculo.dado_geral.areas_atuacoes.all():
            dados_lattes['area_atuacao'].append(
                {
                    'grande_area': area.nome_grande_area_conhecimento,
                    'area': area.nome_area_conhecimento,
                    'sub_area': area.nome_sub_area_conhecimento,
                    'especialidade': area.nome_especialidade_conhecimento,
                }
            )

        # Prêmios e Títulos
        for premio in curriculo.get_premios_e_titulos():
            dados_lattes['premios_titulos'].append(
                {
                    'nome': premio.nome_premio_titulo,
                    'entidade': premio.nome_entidade_promotora,
                    'ano': premio.ano_premiacao,
                }
            )

    # Grupos de Pesquisa
    for grupo in curriculo.grupos_pesquisa.all():
        dados_lattes['grupos_pesquisa'].append(
            {
                'codigo': grupo.codigo,
                'descricao': grupo.descricao,
                'instituicao': grupo.instituicao,
            }
        )

    # Publicações
    for artigo in curriculo.get_artigos_completos():
        dados_lattes['publicacoes']['artigos_completos'].append(
            {
                'titulo': artigo.titulo,
                'ano': artigo.ano,
                'periodico': artigo.titulo_periodico_revista,
            }
        )

    for artigo in curriculo.get_artigos_resumos():
        dados_lattes['publicacoes']['artigos_resumos'].append(
            {
                'titulo': artigo.titulo,
                'ano': artigo.ano,
                'periodico': artigo.titulo_periodico_revista,
            }
        )

    for trabalho in curriculo.get_trabalhos_eventos():
        dados_lattes['publicacoes']['trabalhos_eventos'].append(
            {
                'titulo': trabalho.titulo,
                'ano': trabalho.ano,
                'evento': trabalho.nome_evento,
            }
        )

    for livro in curriculo.get_livros():
        dados_lattes['publicacoes']['livros'].append(
            {
                'titulo': livro.titulo,
                'ano': livro.ano,
                'editora': livro.nome_editora,
            }
        )

    for capitulo in curriculo.get_capitulos():
        dados_lattes['publicacoes']['capitulos'].append(
            {
                'titulo': capitulo.titulo,
                'ano': capitulo.ano,
                'livro': capitulo.titulo_livro,
            }
        )

    # Outras Produções Bibliográficas
    for texto in curriculo.get_textos_jornal_revista():
        dados_lattes['producoes_bibliograficas']['textos_jornal_revista'].append(
            {
                'titulo': texto.titulo,
                'ano': texto.ano,
            }
        )

    for prefacio in curriculo.get_prefacios_posfacios():
        dados_lattes['producoes_bibliograficas']['prefacios_posfacios'].append(
            {
                'titulo': prefacio.titulo,
                'ano': prefacio.ano,
            }
        )

    for traducao in curriculo.get_traducoes():
        dados_lattes['producoes_bibliograficas']['traducoes'].append(
            {
                'titulo': traducao.titulo,
                'ano': traducao.ano,
            }
        )

    for outra in curriculo.get_outras_producoes():
        dados_lattes['producoes_bibliograficas']['outras'].append(
            {
                'titulo': outra.titulo,
                'ano': outra.ano,
            }
        )

    # Produções Técnicas
    for software in curriculo.get_softwares():
        dados_lattes['producoes_tecnicas']['softwares'].append(
            {
                'titulo': software.titulo,
                'ano': software.ano,
            }
        )

    for produto in curriculo.get_produtos_tecnologicos():
        dados_lattes['producoes_tecnicas']['produtos_tecnologicos'].append(
            {
                'titulo': produto.titulo,
                'ano': produto.ano,
            }
        )

    for processo in curriculo.get_processos_tecnicas():
        dados_lattes['producoes_tecnicas']['processos_tecnicas'].append(
            {
                'titulo': processo.titulo,
                'ano': processo.ano,
            }
        )

    for trabalho in curriculo.get_trabalhos_tecnicos():
        dados_lattes['producoes_tecnicas']['trabalhos_tecnicos'].append(
            {
                'titulo': trabalho.titulo,
                'ano': trabalho.ano,
            }
        )

    for patente in curriculo.get_patentes():
        dados_lattes['producoes_tecnicas']['patentes'].append(
            {
                'titulo': patente.titulo,
                'ano': patente.ano,
            }
        )

    # Projetos
    for projeto in curriculo.get_projeto_pesquisa():
        dados_lattes['projetos']['pesquisa'].append(
            {
                'nome': projeto.nome,
                'ano_inicio': projeto.ano_inicio,
                'ano_fim': projeto.ano_fim,
                'situacao': projeto.situacao,
            }
        )

    for projeto in curriculo.get_projeto_extensao():
        dados_lattes['projetos']['extensao'].append(
            {
                'nome': projeto.nome,
                'ano_inicio': projeto.ano_inicio,
                'ano_fim': projeto.ano_fim,
                'situacao': projeto.situacao,
            }
        )

    for projeto in curriculo.get_projeto_desenvolvimento():
        dados_lattes['projetos']['desenvolvimento'].append(
            {
                'nome': projeto.nome,
                'ano_inicio': projeto.ano_inicio,
                'ano_fim': projeto.ano_fim,
                'situacao': projeto.situacao,
            }
        )

    return _decode_html_entities(dados_lattes)
