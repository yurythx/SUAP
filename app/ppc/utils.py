import re

# Blocos do editor (TinyMCE) que podem conter uma referência: parágrafo ou item de lista.
_BLOCOS_DE_REFERENCIA = ('p', 'li')
# Marca as quebras de linha (<br>) para separar referências digitadas no mesmo parágrafo.
_SEPARADOR_DE_LINHA = '\x1e'
# Numeração digitada no início da referência ("1.", "1)", "1 -"). Até 3 dígitos para não
# confundir com títulos que começam por ano/número (ex.: "1984. Rio de Janeiro: ...").
_NUMERACAO_INICIAL = re.compile(r'^\d{1,3}\s*[.)\-\u2013\u2014]\s*(?!\d)')


def extrair_bibliografias_da_secao(texto_da_secao: str | None) -> list[str]:
    """Extrai as referências bibliográficas do HTML de uma seção do plano de disciplina.

    Cada parágrafo, item de lista ou linha separada por ``<br>`` é uma referência; a numeração
    digitada no início ("1.", "1)", "1 -") é descartada, pois indica só a posição na lista.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(texto_da_secao or '', 'html.parser')
    for quebra in soup.find_all('br'):
        quebra.replace_with(_SEPARADOR_DE_LINHA)

    bibliografias = []
    for bloco in soup.find_all(_BLOCOS_DE_REFERENCIA):
        # Bloco que contém outros blocos (ex.: <li><p>, <p><ol>): os internos são lidos separadamente.
        if bloco.find(_BLOCOS_DE_REFERENCIA):
            continue
        for linha in bloco.get_text().split(_SEPARADOR_DE_LINHA):
            texto = _NUMERACAO_INICIAL.sub('', linha.strip()).strip()
            if texto:
                bibliografias.append(texto)
    return bibliografias


def processar_bibliografia(projeto, funcao_iterator=iter, formatar_resposta_em_html=True):
    """
    Processa a bibliografia de um PPC com base nos Planos de Disciplinas associados,
    retornando as obras bibliográficas em formato de dicionário ou html (se `formatar_resposta_em_html` for True).

    Ao chamar este método em uma task, é possível informar `task.iterate` no parâmetro `funcao_iterator`
    para registrar o progresso do processamento na task.

    Parâmetros:
    - projeto: O PPC cuja bibliografia será processada.
    - funcao_iterator: A função de iteração a ser usada para percorrer os planos de disciplina. Padrão é iter (builtin).
    - formatar_resposta_em_html: Se True, a resposta será formatada em HTML. Se False, retornará informações brutas. Padrão é True.

    Retorna:
    - Um dicionário (ou um texto HTML) com as seções (Bibliografia Básica/Complementar) e suas respectivas bibliografias.
    """

    import re

    titulos_secoes = ('Bibliografia Básica', 'Bibliografia Complementar')

    planos = projeto.get_planos_disciplina()
    bibliografias = {titulo: {} for titulo in titulos_secoes}

    for plano in funcao_iterator(planos):
        disciplina = plano.nome_disciplina
        for titulo_secao in titulos_secoes:
            secoes = plano.secaoplanodisciplina_set.filter(modelo_secao_plano_disciplina__titulo=titulo_secao).only('texto')

            # bibliografia é única no plano independente de existir versão EAD.
            secoes = secoes.filter(versao_ead=False)
            for secao in secoes:
                bibliografias_da_secao = extrair_bibliografias_da_secao(secao.texto)
                for texto in bibliografias_da_secao:
                    if texto:
                        texto_limpo = re.sub(r'[^a-zA-Z0-9]', '', texto).lower()
                        if texto_limpo in bibliografias[titulo_secao] and disciplina not in bibliografias[titulo_secao][texto_limpo]['disciplinas']:
                            bibliografias[titulo_secao][texto_limpo]['disciplinas'].append(disciplina)
                        else:
                            bibliografias[titulo_secao][texto_limpo] = {
                                'texto_original': texto,
                                'disciplinas': [disciplina],
                                'qtd_exemplares': 5,
                            }

    html = ''
    if formatar_resposta_em_html:
        for titulo_secao in titulos_secoes:
            if bibliografias[titulo_secao]:
                html += f"""
                    <table class="bordered">
                        <thead>
                            <tr><th colspan="3" class="center">{titulo_secao}</th></tr>
                            <tr>
                                <th class="quebra-texto">Descrição (Autor, Título, Editora, Ano)</th>
                                <th>Disciplina(s) Contempladas(s)</th>
                                <th>Quantidade de Exemplares</th>
                            </tr>
                        </thead>
                        <tbody>
                """

                for texto_limpo in sorted(bibliografias[titulo_secao].keys()):
                    bibliografia = bibliografias[titulo_secao][texto_limpo]['texto_original']
                    disciplinas = [f'- {disciplina}<br>' for disciplina in sorted(bibliografias[titulo_secao][texto_limpo]['disciplinas'])]
                    qtd_exemplares = bibliografias[titulo_secao][texto_limpo]['qtd_exemplares']
                    html += f"""
                        <tr>
                            <td class="quebra-texto">{bibliografia}</td>
                            <td>{'<br>'.join(disciplinas)}</td>
                            <td>{qtd_exemplares}</td>
                        </tr>
                    """

                html += """
                        </tbody>
                    </table><br>
                """

    return html if formatar_resposta_em_html else bibliografias
