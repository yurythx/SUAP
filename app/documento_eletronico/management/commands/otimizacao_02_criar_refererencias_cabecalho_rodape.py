import importlib
import json
import os

# Pattern padrão para extrair variáveis.
import re
import sys
import time

from django.apps import apps
from lxml import html

from djtools.management.commands import BaseCommandPlus
from documento_eletronico.utils import gerar_hash, processar_template_ckeditor

extrator_variavel = re.compile('{{ (.*?) }}')

# Entidades do domínio do módulo de Documento Eletrônico.
DocumentoTexto = apps.get_model('documento_eletronico', 'DocumentoTexto')
TipoDocumentoTexto = apps.get_model('documento_eletronico', 'TipoDocumentoTexto')
TipoDocumentoTextoHistoricoConteudo = apps.get_model('documento_eletronico', 'TipoDocumentoTextoHistoricoConteudo')

# Evita o erro "UnicodeEncodeError: 'ascii' codec can't encode character u'\xe9' in position 53: ordinal not in range(128)"

importlib.reload(sys)
default_encoding = sys.getdefaultencoding()
sys.setdefaultencoding('utf8')

# Cria o diretório no qual os cabeçalhos, rodapés e seus respectivos templates serão armazenados em disco. A ideia
# de salvar isso em disco, além de salvar no banco, é apenas para facilitar o debug na correção de algum erro.
caminho_arquivo_corrente_sem_extensao = os.path.splitext(__file__)[0]
DIRETORIO_BASE_TEMPLATE = caminho_arquivo_corrente_sem_extensao + '/'

if not os.path.exists(DIRETORIO_BASE_TEMPLATE):
    os.makedirs(DIRETORIO_BASE_TEMPLATE)


class Conteudo:
    def __init__(self, texto, descricao):
        self.descricao = descricao
        self.texto = texto

    @property
    def hash(self):
        return gerar_hash(self.texto)

    @property
    def tamanho_em_bytes(self):
        return len(self.texto)

    @property
    def tamanho_em_kbytes(self):
        return self.tamanho_em_bytes / 1024.0

    @property
    def texto_as_html_doc(self):
        texto_html = '<html><body>' + self.texto + '</body></html>'
        return html.fromstring(texto_html)

    @property
    def texto_as_lista(self):
        """
        A engine do python, quando lê um arquivo texto, se baseia nas quebras de linhas (\n) para determiar quantas linhas
        contém o arquivo, e para cada linha do arquivo monta um item do lista que ele retornária. Cada item dessa lista
        conterá todo o conteúdo da linha do arquivo texto, inclusive caracteres especiais como \r\n\t etc.'

        Ao usar a função split, passando o caractere divisor (no caso \n), o python gera corretamente o número de linhas conteúdo
        suprimi de cada linha o caractere divisor, por isso varremos a lista e adicionamos novamente esse caracteres, mantendo
        assim o mesmo padrão da leitura de um arquivo texto.
        """
        linhas_texto = self.texto.split('\n')
        for i in range(len(linhas_texto) - 1):
            linhas_texto[i] = linhas_texto[i] + '\n'
        return linhas_texto

    def salvar_para_arquivo(self, file_path):
        file = open(file_path, 'wb')
        # O encode para 'utf-8' foi necessário para evitar o erro "UnicodeEncodeError: 'ascii' codec can't encode
        # characters in position 1000098-1000099: ordinal not in range(128)."
        file.write(self.texto)
        file.close()

    def imprimir_info(self):
        print(f'Descrição : {self.descricao}')
        # print u'Texto : {}'.format(self.texto)
        print(f'Hash: {self.hash}')
        print(f'Tamanho: {self.tamanho_em_kbytes:,.2f} KB')


class ReprocessadorConteudo:
    @staticmethod
    def executar(conteudo_documento, conteudo_template):
        eh_compativel = False
        variaveis_extraidas = {}
        conteudo_reprocessado = None

        variaves_nao_processadas_conteudo_documento = extrator_variavel.findall(conteudo_documento.texto)
        if variaves_nao_processadas_conteudo_documento:
            print('O conteúdo do documento contém variáveis não processadas, o que inviabiliza a utilização o processamento do template.')
            print('Variáveis: {}'.format(', '.join(variaves_nao_processadas_conteudo_documento)))
            return eh_compativel, variaveis_extraidas, conteudo_reprocessado

        linhas_documento = conteudo_documento.texto_as_lista

        linhas_template = []

        # Varrendo as linhas do template. Geralmente ele vai conter apenas duas linhas: uma contendo o conteudo <img>
        # e outro contendo as variáveis.
        # Ex:
        #
        # <p align="center"><img align="bottom" border="0" height="143" name="Image1" src="data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofH...1Ef7h/8AkD//2Q==" width="328" /></p>
        # {{ html_linha_2 }}{{ html_linha_3 }}{{ html_linha_4 }}{{ html_linha_5 }}{{ html_linha_6 }}{{ html_linha_7 }}{{ html_linha_8 }}{{ html_linha_9 }}{{ html_linha_10 }}{{ html_linha_11 }}{{ html_linha_12 }}
        #
        for linha in conteudo_template.texto_as_lista:
            if '<img ' in linha:
                linhas_template.append(linha)
            else:
                # Transformando a linha que contém as variáveis em várias linhas, de acordo como o número de variáveis
                # identificadas no template. Isso é fundamental para sabermos o valor que cada variável irá ter comparando
                # o template com o conteúdo de um cabeçalho e rodapé.
                linhas_template.extend(['{{ ' + v + ' }}' for v in extrator_variavel.findall(linha)])

        # print len(linhas_documento), len(linhas_template)
        # Para um template ser compatível o primeiro requisito é ter o mesmo número de linhas do conteúdo do documento
        # em questão.
        if not (len(linhas_template) == 1 and '<img ' in linhas_template[0]) and (len(linhas_documento) == len(linhas_template)):
            # Para cada linha do template, se for uma variável, buscaramos o valor dessa variável no conteúdo do documento
            # na mesma linha. No caso as variáveis conterão todo o conteúdo (html e caracteres especials da linha).
            # Ex: {{ html_linha_2 }} = '<p style="text-align: center;"><strong>REITORIA</strong></p>\r\n'
            for i in range(len(linhas_template)):
                linha_template = linhas_template[i]
                if linha_template.startswith('{{ ') and linha_template.endswith(' }}'):
                    variavel = linha_template.replace('{{ ', '').replace(' }}', '')
                    # variavel = linha_template
                    valor_variavel = linhas_documento[i]
                    variaveis_extraidas[variavel] = valor_variavel

            # Uma vez que temos o template e as variáveis extraídas do documento, faremos um reprocessamento dessa informação.
            # Se o texto reprocessado tiver o mesmo hash do texto do conteúdo do documento (seja cabeçalho, rodapé etc), então
            # o template em questão é compatível.
            texto_reprocessado = processar_template_ckeditor(texto=conteudo_template.texto, variaveis=variaveis_extraidas)
            # texto_reprocessado = conteudo_template.texto
            # for k, v in variaveis_extraidas.items():
            #     # print k, v
            #     texto_reprocessado = texto_reprocessado.replace(k, v)

            # print texto_reprocessado
            conteudo_reprocessado = Conteudo(texto=texto_reprocessado, descricao=conteudo_documento.descricao + ' (REPROCESSADO USANDO O TEMPLATE)')
            eh_compativel = conteudo_reprocessado.hash == conteudo_documento.hash

            # if t.split('/')[-1] == 'tipo_01_doc_01050_template.txt':
            # conteudo_cabecalho_template.print_info()

            # print template_compativel_encontrado
            # print variaveis_extraidas
            # if conteudo_reprocessado:
            #     conteudo_reprocessado.imprimir_info()
            #     conteudo_reprocessado.salvar_para_arquivo(DIRETORIO_BASE_TEMPLATE + 'reprocessado.txt')

        return eh_compativel, variaveis_extraidas, conteudo_reprocessado

    @staticmethod
    def gerar_template(conteudo_documento, area_conteudo):
        """
        Este método cria um template a partir de um conteúdo html informado. A ideia é que no template as linhas que contiverem
        imagens sejam preservadas, e as linhas que não contiverem serão convertidas em variaveis "{{ html_linha_x }}", uma para
        cada linha.

        Uma vez criado este template, ele poderá ser utilizado para resolver vários cabeçalhos/rodapés de documentos, uma
        vez que para o que vai variar entre um template e outro será a imagem utilizada ou o número de linhas presentes
        no template.

        :param conteudo_documento:
        :param caminho_arquivo_template:
        :return: conteudo do template criado
        """
        variaves_nao_processadas_conteudo_documento = extrator_variavel.findall(conteudo_documento.texto)
        if variaves_nao_processadas_conteudo_documento:
            print('O conteúdo do documento contém variáveis não processadas, o que inviabiliza a crição de um template.')
            print('Variáveis: {}'.format(', '.join(variaves_nao_processadas_conteudo_documento)))
            return None

        template_linhas_texto = []

        if area_conteudo == TipoDocumentoTextoHistoricoConteudo.CABECALHO:
            prefixo_linha = 'cabecalho'
        elif area_conteudo == TipoDocumentoTextoHistoricoConteudo.RODAPE:
            prefixo_linha = 'rodape'

        i = 0
        for linha in conteudo_documento.texto_as_lista:
            i += 1
            if '<img ' in linha:
                template_linhas_texto.append(linha)
            else:
                template_linhas_texto.append('{{ ' + prefixo_linha + '_html_linha_' + str(i) + ' }}')

        texto = ''.join(template_linhas_texto)
        template_conteudo = Conteudo(texto=texto, descricao=f'Template compatível criado a partir do {conteudo_documento.descricao}')
        return template_conteudo


class Command(BaseCommandPlus):
    """
    Command criado para reassinar os depachos devido a um erro ao processamento
    das variáveis
    """

    def imprimir_titulo(self, titulo, primeira_linha_em_branco=True):
        if primeira_linha_em_branco:
            print()

        print('-' * len(titulo))
        print(titulo)
        print('-' * len(titulo))

    def get_tdhc_compativel(self, documento, area_conteudo):
        tdhc_disponiveis = TipoDocumentoTextoHistoricoConteudo.objects.filter(
            tipo_documento_texto=documento.tipo, area_conteudo=area_conteudo
        ).order_by('id')
        if area_conteudo == TipoDocumentoTextoHistoricoConteudo.CABECALHO:
            texto = documento.cabecalho
            sufixo_arquivo_novo_template = 'cabecalho'
        elif area_conteudo == TipoDocumentoTextoHistoricoConteudo.RODAPE:
            texto = documento.rodape
            sufixo_arquivo_novo_template = 'rodape'
        else:
            raise Exception('Impossível definir qual a área do documento será utilizada para identificação e/ou geração de template compatível')

        conteudo_documento = Conteudo(
            texto=texto,
            descricao=f'{sufixo_arquivo_novo_template.capitalize()} do documento "{documento.identificador}" (id: {documento.id})',
        )
        conteudo_documento.imprimir_info()

        # A variável "template" é um TipoDocumentoTextoHistoricoConteudo.
        # Tentativa 1 - Varrendo todos os registros de TipoDocumentoTextoHistoricoConteudo para ver se algum é
        # compatível. Se houver algum, ele será retornado.
        for tdhc in tdhc_disponiveis:
            conteudo_template = Conteudo(
                texto=tdhc.conteudo,
                descricao=f'Tipo Doc. {documento.tipo}  /  Tipo Doc. Hist. Cont. {tdhc.id} ({sufixo_arquivo_novo_template})',
            )
            template_compativel_encontrado, variaveis_extraidas, conteudo_reprocessado = ReprocessadorConteudo.executar(
                conteudo_documento=conteudo_documento, conteudo_template=conteudo_template
            )

            if template_compativel_encontrado:
                print()
                print(f'Template compatível encontrado no banco de dados: {conteudo_template.descricao}')
                conteudo_template.imprimir_info()

                print()
                conteudo_reprocessado.imprimir_info()
                print(f'Variáveis: {variaveis_extraidas}')

                return tdhc, variaveis_extraidas, False

        # Tentativa 2 - Como nenhum template foi encontrado no banco de dados, a tentativa seguinte é tentar criar um template
        # compatível a partir do conteúdo do próprio documento.
        documento_area_conteudo_file = (
            DIRETORIO_BASE_TEMPLATE + f'tipodoc_{documento.tipo.id:02d}__doc_{documento.id:05d}__{sufixo_arquivo_novo_template}.txt'
        )

        # Criando o template a partir do conteúdo do documento.
        conteudo_template_novo = ReprocessadorConteudo.gerar_template(conteudo_documento=conteudo_documento, area_conteudo=area_conteudo)

        # Se foi possível gerar um template a partir do conteúdo do documento, o passo seguinte é confirmar se realmennte
        # o template em questão é compatível.
        if conteudo_template_novo:
            template_compativel_encontrado, variaveis_extraidas, conteudo_reprocessado = ReprocessadorConteudo.executar(
                conteudo_documento=conteudo_documento, conteudo_template=conteudo_template_novo
            )

            if template_compativel_encontrado:
                tdhc_novo = TipoDocumentoTextoHistoricoConteudo(
                    tipo_documento_texto=documento.tipo,
                    area_conteudo=area_conteudo,
                    conteudo=conteudo_template_novo.texto,
                    hash=gerar_hash(conteudo_template_novo.texto),
                )
                tdhc_novo.save()

                tdhc_arquivo = (
                    DIRETORIO_BASE_TEMPLATE
                    + f'tipodoc_{documento.tipo.id:02d}__doc_{documento.id:05d}__{sufixo_arquivo_novo_template}__tipodochc__{tdhc_novo.id or 0:05d}__template.txt'
                )
                conteudo_template_novo.salvar_para_arquivo(tdhc_arquivo)
                conteudo_documento.salvar_para_arquivo(documento_area_conteudo_file)

                print()
                print(documento_area_conteudo_file.split('/')[-1])
                print(tdhc_arquivo.split('/')[-1])
                print(f'TipoDocumentoTextoHistoricoConteudo - id: {tdhc_novo.id}')
                conteudo_template_novo.imprimir_info()

                print()
                conteudo_reprocessado.imprimir_info()
                print(f'Variáveis: {variaveis_extraidas}')

                return tdhc_novo, variaveis_extraidas, True

        print()
        print('Nenhum template compatível localizado e/ou criado.')
        return None, {}, False

    # O método não foi marcado com "@transaction.atomic()" porque a ideia não é ser atômico, ou seja, se ocorrer algum erro
    # em algum documento, o que tiver sido feito e persistido antes com sucesso deve ser mantido. Caso haja necessidade
    # de um novo processamento, os documentos já processados não serão mais alvo do processamento uma vez que os filtros
    # estabelecidos irão barrá-los.
    def handle(self, *args, **options):
        tipos_documento = TipoDocumentoTexto.objects.all()
        tipos_documento = tipos_documento.order_by('id')

        qtd_total_templates_cabecalhos_criados = 0
        qtd_total_templates_rodapes_criados = 0
        qtd_total_documentos = 0
        qtd_total_documentos_passaram_a_ter_referencia_cabecalho_rodape = 0
        for td in tipos_documento:
            self.imprimir_titulo(titulo=f'Analisando o tipo de documento: {td.nome} - {td.sigla} (id: {td.id})...')
            documentos_pks = DocumentoTexto.objects.filter(modelo__tipo_documento_texto=td, assinaturadocumentotexto__isnull=False)
            documentos_pks = documentos_pks.filter(cabecalho_base_original__isnull=True, rodape_base_original__isnull=True)
            # O distinct se faz necessário por conta do filtro  "assinaturadocumentotexto__isnull".
            documentos_pks = documentos_pks.order_by('id').values_list('id', flat=True).distinct()

            total_docs = documentos_pks.count()
            if total_docs == 0:
                print('Nada a ser feito para o tipo de documento em questão')
            else:
                self.imprimir_titulo(titulo=f'Total de documentos deste tipo a serem avaliados: {total_docs})...')
                for doc_pk in documentos_pks:
                    qtd_total_documentos += 1

                    documento = DocumentoTexto.objects.get(id=doc_pk)
                    self.imprimir_titulo(titulo=f'Analisando o {qtd_total_documentos}º documento {documento.identificador} (id: {documento.id})...')

                    tdhc_cabecalho = None
                    tdhc_rodape = None
                    variaveis = {}
                    if not documento.cabecalho_base_original:
                        print()
                        print('<<< Analisando o cabeçalho >>>')
                        tdhc_cabecalho, variaveis_cabecalho, novo_template_cabecalho_criado = self.get_tdhc_compativel(
                            documento=documento, area_conteudo=TipoDocumentoTextoHistoricoConteudo.CABECALHO
                        )
                        variaveis.update(variaveis_cabecalho)
                        if novo_template_cabecalho_criado:
                            qtd_total_templates_cabecalhos_criados += 1

                    if not documento.rodape_base_original:
                        print()
                        print('<<< Analisando o rodapé >>>')
                        tdhc_rodape, variaveis_rodape, novo_template_rodape_criado = self.get_tdhc_compativel(
                            documento=documento, area_conteudo=TipoDocumentoTextoHistoricoConteudo.RODAPE
                        )
                        variaveis.update(variaveis_rodape)
                        if novo_template_rodape_criado:
                            qtd_total_templates_rodapes_criados += 1

                    # Por opção, somente se houver sido achada e/ou criada referência de histórico de cabeçalho e rodapé,
                    # é que iremos persistir a informação no documento.
                    if tdhc_cabecalho and tdhc_rodape:
                        if tdhc_cabecalho:
                            documento.cabecalho_base_original = tdhc_cabecalho
                        if tdhc_rodape:
                            documento.rodape_base_original = tdhc_rodape

                        documento.variaveis = json.dumps(variaveis)
                        documento.save()
                        qtd_total_documentos_passaram_a_ter_referencia_cabecalho_rodape += 1

                    if qtd_total_documentos % 100 == 0:
                        print()
                        print(
                            f'Documentos processados: {qtd_total_documentos}\n'
                            f'Documentos que passaram a ter referências de cabeçalho e rodapé: {qtd_total_documentos_passaram_a_ter_referencia_cabecalho_rodape}\n'
                            f'Templates de cabeçalho criados: {qtd_total_templates_cabecalhos_criados}\n'
                            f'Templates de rodapé criados: {qtd_total_templates_rodapes_criados}'
                        )
                        time.sleep(5)

        print()
        print(
            f'Documentos processados: {qtd_total_documentos}\n'
            f'Documentos que passaram a ter referências de cabeçalho e rodapé: {qtd_total_documentos_passaram_a_ter_referencia_cabecalho_rodape}\n'
            f'Templates de cabeçalho criados: {qtd_total_templates_cabecalhos_criados}\n'
            f'Templates de rodapé criados: {qtd_total_templates_rodapes_criados}'
        )

        print('<<< FIM >>')

        sys.setdefaultencoding(default_encoding)
