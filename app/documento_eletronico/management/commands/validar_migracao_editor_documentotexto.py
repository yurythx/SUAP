import csv
import importlib.util
import json
import requests
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse

from django.conf import settings
from django.utils.text import slugify
from urllib3 import disable_warnings
from urllib3.exceptions import InsecureRequestWarning

from djtools.management.commands import BaseCommandPlus


DEFAULT_AMOSTRA_FILE = 'documento_eletronico/relatorio_tinymce/amostra_validacao_migracao_editor_documentotexto.csv'
DEFAULT_EVIDENCIAS_DIR = 'documento_eletronico/relatorio_tinymce/tmp/evidencias_validacao_migracao_editor_documentotexto'
DEFAULT_ARQUIVO_PREPARACAO = 'documento_eletronico/relatorio_tinymce/tmp/preparacao_validacao_migracao_editor_documentotexto.json'

disable_warnings(InsecureRequestWarning)


class Command(BaseCommandPlus):
    """Prepara e executa a validacao da migracao do editor no escopo de ``DocumentoTexto``.

    O fluxo tem tres etapas executadas via ``--etapa``:
    * ``dependencias`` — verifica/instala dependencias (Playwright, Chromium).
    * ``preparacao`` — le a amostra, monta estrutura de diretorios e arquivos
      de metadados para cada caso.
    * ``visualizacao`` — navega com Playwright nos ambientes antigo e novo,
      captura screenshots e PDFs, e registra evidencias.
    """

    help = """
Prepara a validacao da migracao do editor no escopo de DocumentoTexto.

Exemplos:

    python -u manage.py validar_migracao_editor_documentotexto --etapa dependencias

    python -u manage.py validar_migracao_editor_documentotexto \
      --etapa preparacao \
      --amostra-file documento_eletronico/relatorio_tinymce/amostra_validacao_editor.json \
      --quantidade-documentos 1

    python -u manage.py validar_migracao_editor_documentotexto \
      --etapa preparacao \
      --amostra-file documento_eletronico/relatorio_tinymce/amostra_validacao_editor.json \
      --arquivo-preparacao documento_eletronico/relatorio_tinymce/tmp/preparacao_validacao_teste.json \
      --evidencias-dir documento_eletronico/relatorio_tinymce/tmp/evidencias_validacao_teste

    python -u manage.py validar_migracao_editor_documentotexto \
      --etapa visualizacao \
      --quantidade-documentos 1 \
      --senha-antiga <senha_antiga> \
      --senha-nova <senha_nova>
""".strip()

    def add_arguments(self, parser):
        """Configura os argumentos de linha de comando aceitos pelo comando."""
        parser.add_argument(
            '--etapa',
            choices=('dependencias', 'preparacao', 'visualizacao'),
            default='preparacao',
            help='Etapa a executar. Padrao: preparacao.',
        )
        parser.add_argument(
            '--amostra-file',
            dest='amostra_file',
            default=DEFAULT_AMOSTRA_FILE,
            help=f'Arquivo CSV ou JSON com a amostra. Padrao: {DEFAULT_AMOSTRA_FILE}',
        )
        parser.add_argument(
            '--quantidade-documentos',
            dest='quantidade_documentos',
            type=int,
            help='Quantidade maxima de documentos encontrados a preparar.',
        )
        parser.add_argument(
            '--evidencias-dir',
            dest='evidencias_dir',
            default=DEFAULT_EVIDENCIAS_DIR,
            help=f'Diretorio base das evidencias. Padrao: {DEFAULT_EVIDENCIAS_DIR}',
        )
        parser.add_argument(
            '--arquivo-preparacao',
            dest='arquivo_preparacao',
            default=DEFAULT_ARQUIVO_PREPARACAO,
            help=f'Arquivo JSON de preparacao. Padrao: {DEFAULT_ARQUIVO_PREPARACAO}',
        )
        parser.add_argument(
            '--instalar-dependencias',
            action='store_true',
            help='Tenta instalar dependencias ausentes necessarias para a automacao.',
        )
        parser.add_argument(
            '--senha-antiga',
            dest='senha_antiga',
            help='Senha usada no login do ambiente antigo.',
        )
        parser.add_argument(
            '--senha-nova',
            dest='senha_nova',
            help='Senha usada no login do ambiente novo.',
        )
        parser.add_argument(
            '--username-antigo-fixo',
            dest='username_antigo_fixo',
            help='Sobrescreve o username da amostra para o login no ambiente antigo.',
        )
        parser.add_argument(
            '--username-novo-fixo',
            dest='username_novo_fixo',
            help='Sobrescreve o username da amostra para o login no ambiente novo.',
        )
        parser.add_argument(
            '--headless',
            dest='headless',
            default='true',
            choices=('true', 'false'),
            help='Executa o navegador em modo headless. Padrao: true.',
        )
        parser.add_argument(
            '--timeout-seconds',
            dest='timeout_seconds',
            type=int,
            default=60,
            help='Timeout padrao, em segundos, para navegacoes e waits do Playwright. Padrao: 60.',
        )

    def handle(self, *args, **options):
        """Ponto de entrada do comando: delega para a etapa solicitada."""
        etapa = options['etapa']
        instalar_dependencias = options['instalar_dependencias']
        self.timeout_seconds = options['timeout_seconds']
        if self.timeout_seconds < 1:
            raise ValueError('O valor de --timeout-seconds deve ser maior que zero.')
        self.timeout_ms = self.timeout_seconds * 1000

        if etapa == 'dependencias':
            diagnostico = self._verificar_dependencias(instalar_dependencias=instalar_dependencias)
            self._emitir_resumo_dependencias(diagnostico)
            return

        diagnostico = self._verificar_dependencias(instalar_dependencias=instalar_dependencias)
        self._emitir_resumo_dependencias(diagnostico)
        self._garantir_dependencias_ok(diagnostico)

        quantidade_documentos = options.get('quantidade_documentos')
        arquivo_preparacao = options['arquivo_preparacao']
        headless = options['headless'] == 'true'

        if etapa == 'visualizacao':
            self._validar_credenciais_visualizacao(options)
            preparacao = self._carregar_preparacao(arquivo_preparacao)
            casos = self._limitar_casos(preparacao.get('casos', []), quantidade_documentos)
            self._executar_etapa_visualizacao(
                preparacao=preparacao,
                casos=casos,
                senha_antiga=options['senha_antiga'],
                senha_nova=options['senha_nova'],
                username_antigo_fixo=options.get('username_antigo_fixo'),
                username_novo_fixo=options.get('username_novo_fixo'),
                arquivo_preparacao=arquivo_preparacao,
                headless=headless,
            )
            self._salvar_preparacao(preparacao, arquivo_preparacao)
            self.stdout.write(f'{len(casos)} caso(s) processado(s) na etapa de visualizacao.')
            self.stdout.write(f'Arquivo de preparacao atualizado em: {arquivo_preparacao}')
            return

        amostra_file = options['amostra_file']
        evidencias_dir = options['evidencias_dir']
        rows = self._carregar_amostra(amostra_file)
        casos = self._filtrar_casos_com_documento(rows)
        casos_limitados = self._limitar_casos(casos, quantidade_documentos)
        preparacao = self._preparar_execucao(
            rows=rows,
            casos=casos_limitados,
            amostra_file=amostra_file,
            evidencias_dir=evidencias_dir,
            arquivo_preparacao=arquivo_preparacao,
            quantidade_documentos=quantidade_documentos,
        )
        self._salvar_preparacao(preparacao, arquivo_preparacao)

        self.stdout.write(f'{len(rows)} linha(s) lidas da amostra.')
        self.stdout.write(f'{len(casos_limitados)} documento(s) preparado(s) para validacao.')
        self.stdout.write(f'Arquivo de preparacao salvo em: {arquivo_preparacao}')

    def _emitir_status(self, mensagem):
        self.stdout.write(mensagem)
        self.stdout.flush()

    def _validar_credenciais_visualizacao(self, options):
        if not options.get('senha_antiga'):
            raise ValueError('Informe --senha-antiga para executar a etapa visualizacao.')
        if not options.get('senha_nova'):
            raise ValueError('Informe --senha-nova para executar a etapa visualizacao.')

    def _verificar_dependencias(self, instalar_dependencias=False):
        """Verifica se Playwright Python e Chromium estao disponiveis.

        Args:
            instalar_dependencias: quando ``True``, tenta instalar as
                dependencias ausentes automaticamente.

        Returns:
            ``dict`` com chaves ``python_package_playwright``,
            ``browser_chromium``, ``instalacao_tentada``,
            ``instalacao_realizada`` e ``mensagens``.
        """
        diagnostico = {
            'python_package_playwright': self._playwright_python_instalado(),
            'browser_chromium': False,
            'instalacao_tentada': False,
            'instalacao_realizada': False,
            'mensagens': [],
        }

        if diagnostico['python_package_playwright']:
            diagnostico['browser_chromium'] = self._playwright_browser_disponivel(diagnostico['mensagens'])

        faltantes = self._listar_dependencias_faltantes(diagnostico)
        if faltantes and instalar_dependencias:
            diagnostico['instalacao_tentada'] = True
            self._emitir_status(f'Tentando instalar dependencias ausentes: {", ".join(faltantes)}')
            self._instalar_dependencias_faltantes(diagnostico)
            diagnostico['python_package_playwright'] = self._playwright_python_instalado()
            if diagnostico['python_package_playwright']:
                diagnostico['browser_chromium'] = self._playwright_browser_disponivel(diagnostico['mensagens'])
            diagnostico['instalacao_realizada'] = not self._listar_dependencias_faltantes(diagnostico)

        return diagnostico

    def _emitir_resumo_dependencias(self, diagnostico):
        self.stdout.write(f'Playwright Python instalado: {"sim" if diagnostico["python_package_playwright"] else "nao"}')
        self.stdout.write(f'Chromium do Playwright disponivel: {"sim" if diagnostico["browser_chromium"] else "nao"}')
        for mensagem in diagnostico['mensagens']:
            self.stdout.write(mensagem)

    def _garantir_dependencias_ok(self, diagnostico):
        faltantes = self._listar_dependencias_faltantes(diagnostico)
        if faltantes:
            faltantes_texto = ', '.join(faltantes)
            raise RuntimeError(
                f'Dependencias ausentes: {faltantes_texto}. '
                'Execute novamente com --instalar-dependencias ou instale manualmente antes da etapa de preparacao.'
            )

    def _listar_dependencias_faltantes(self, diagnostico):
        faltantes = []
        if not diagnostico['python_package_playwright']:
            faltantes.append('playwright-python')
        if not diagnostico['browser_chromium']:
            faltantes.append('playwright-chromium')
        return faltantes

    def _playwright_python_instalado(self):
        return importlib.util.find_spec('playwright') is not None

    def _playwright_browser_disponivel(self, mensagens):
        """Verifica se o binario Chromium do Playwright consegue ser iniciado.

        Args:
            mensagens: lista onde erros de inicializacao sao acrescentados.

        Returns:
            ``True`` se o Chromium abrir e fechar sem excecao, ``False`` caso contrario.
        """
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    headless=True,
                    args=[
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-gpu',
                        '--disable-setuid-sandbox',
                    ],
                )
                browser.close()
            return True
        except Exception as exc:
            mensagens.append(f'Falha ao abrir o Chromium do Playwright: {exc}')
            return False

    def _instalar_dependencias_faltantes(self, diagnostico):
        """Tenta instalar as dependencias ausentes (Playwright Python e Chromium)."""
        if not diagnostico['python_package_playwright']:
            self._executar_subprocesso(
                ['uv', 'sync', '--group', 'dev'],
                'Instalando dependencias Python do grupo dev via uv...',
            )
        self._executar_subprocesso(
            [sys.executable, '-m', 'playwright', 'install', 'chromium'],
            'Instalando o Chromium do Playwright...',
        )

    def _executar_subprocesso(self, comando, mensagem):
        self._emitir_status(mensagem)
        subprocess.run(
            comando,
            cwd=settings.BASE_DIR,
            check=True,
        )

    def _carregar_amostra(self, amostra_file):
        """Carrega a amostra de um arquivo CSV ou JSON.

        Args:
            amostra_file: caminho (relativo ou absoluto) do arquivo.

        Returns:
            ``list[dict]`` com os registros da amostra.

        Raises:
            FileNotFoundError: se o arquivo nao existir.
        """
        path = Path(amostra_file)
        if not path.is_absolute():
            path = Path(settings.BASE_DIR) / path
        if not path.exists():
            raise FileNotFoundError(f'Amostra nao encontrada: {path}')

        self._emitir_status(f'Lendo amostra em: {path}')
        if path.suffix.lower() == '.json':
            with path.open() as fp:
                return json.load(fp)

        with path.open(newline='') as fp:
            return list(csv.DictReader(fp))

    def _carregar_preparacao(self, arquivo_preparacao):
        path = self._resolve_path(arquivo_preparacao)
        if not path.exists():
            raise FileNotFoundError(f'Arquivo de preparacao nao encontrado: {path}. Execute primeiro a etapa de preparacao.')
        self._emitir_status(f'Lendo arquivo de preparacao em: {path}')
        with path.open() as fp:
            return json.load(fp)

    def _filtrar_casos_com_documento(self, rows):
        return [row for row in rows if self._as_bool(row.get('documento_encontrado'))]

    def _limitar_casos(self, casos, quantidade_documentos):
        if not quantidade_documentos:
            return casos
        if quantidade_documentos < 1:
            raise ValueError('O valor de --quantidade-documentos deve ser maior que zero.')
        return casos[:quantidade_documentos]

    def _preparar_execucao(self, rows, casos, amostra_file, evidencias_dir, arquivo_preparacao, quantidade_documentos):
        """Monta a estrutura de preparacao com os casos a serem validados.

        Returns:
            ``dict`` com metadados da execucao e lista de ``casos``.
        """
        evidencias_path = self._resolve_path(evidencias_dir)
        evidencias_path.mkdir(parents=True, exist_ok=True)

        preparacao = {
            'origem_amostra': str(Path(amostra_file)),
            'evidencias_dir': str(Path(evidencias_dir)),
            'arquivo_preparacao': str(Path(arquivo_preparacao)),
            'quantidade_documentos_solicitada': quantidade_documentos or '',
            'total_linhas_amostra': len(rows),
            'total_linhas_com_documento': len(self._filtrar_casos_com_documento(rows)),
            'documentos_preparados': len(casos),
            'casos': [],
        }

        for row in casos:
            caso = self._preparar_caso(row=row, evidencias_path=evidencias_path)
            preparacao['casos'].append(caso)

        return preparacao

    def _preparar_caso(self, row, evidencias_path):
        """Prepara um caso individual: cria diretorio, metadados e arquivos esperados.

        Args:
            row: linha da amostra com dados do documento.
            evidencias_path: diretorio base para as evidencias.

        Returns:
            ``dict`` com os dados do caso pronto para a etapa de visualizacao.
        """
        tipo_slug = slugify(row['tipo_documento_nome']) or f'tipo-{row["tipo_documento_id"]}'
        categoria_slug = slugify(row['categoria_amostra']) or 'categoria'
        documento_id = row['documento_id']
        diretorio_caso = evidencias_path / tipo_slug / categoria_slug / f'documento_{documento_id}'
        diretorio_caso.mkdir(parents=True, exist_ok=True)

        arquivos_esperados = self._montar_arquivos_esperados(
            diretorio_caso=diretorio_caso,
            status_id=row.get('status_id'),
        )
        metadata_file = diretorio_caso / 'metadata.json'

        caso = {
            'tipo_documento_id': self._as_int(row.get('tipo_documento_id')),
            'tipo_documento_nome': row.get('tipo_documento_nome', ''),
            'categoria_amostra': row.get('categoria_amostra', ''),
            'status_id': self._as_int(row.get('status_id')),
            'status_nome': row.get('status_nome', ''),
            'documento_id': self._as_int(row.get('documento_id')),
            'documento_identificador': row.get('documento_identificador', ''),
            'username_dono': row.get('username_dono', ''),
            'procedimento_edicao': row.get('procedimento_edicao', ''),
            'diretorio_caso': self._path_relativa(diretorio_caso),
            'metadata_file': self._path_relativa(metadata_file),
            'arquivos_esperados': arquivos_esperados,
            'status_execucao': 'pendente',
            'houve_divergencia': '',
            'descricao_divergencia': '',
            'observacoes': '',
            'urls': self._extrair_urls(row),
        }

        metadata_file.write_text(json.dumps(caso, indent=2, ensure_ascii=False) + '\n')
        return caso

    def _montar_arquivos_esperados(self, diretorio_caso, status_id):
        """Monta o mapeamento de arquivos de evidencia esperados para o caso.

        Inclui screenshots e PDFs para visualizacao, edicao e (se ``status_id``
        for ``'7'``) clonagem.

        Args:
            diretorio_caso: diretorio do caso.
            status_id: codigo do status do documento.

        Returns:
            ``dict`` com nome logico da evidencia -> caminho relativo.
        """
        arquivos = {
            'antiga_visualizacao': self._path_relativa(diretorio_caso / 'antiga_visualizacao.png'),
            'nova_visualizacao': self._path_relativa(diretorio_caso / 'nova_visualizacao.png'),
            'antiga_pdf': self._path_relativa(diretorio_caso / 'antiga_pdf.pdf'),
            'nova_pdf': self._path_relativa(diretorio_caso / 'nova_pdf.pdf'),
        }

        if str(status_id) == '7':
            arquivos.update(
                {
                    'antiga_clonagem': self._path_relativa(diretorio_caso / 'antiga_clonagem.png'),
                    'antiga_clonagem_pre_salvar': self._path_relativa(diretorio_caso / 'antiga_clonagem_pre_salvar.png'),
                    'antiga_clonagem_pos_salvar': self._path_relativa(diretorio_caso / 'antiga_clonagem_pos_salvar.png'),
                    'antiga_clonagem_pos_salvar_formulario': self._path_relativa(diretorio_caso / 'antiga_clonagem_pos_salvar_formulario.png'),
                    'nova_clonagem': self._path_relativa(diretorio_caso / 'nova_clonagem.png'),
                    'nova_clonagem_pre_salvar': self._path_relativa(diretorio_caso / 'nova_clonagem_pre_salvar.png'),
                    'nova_clonagem_pos_salvar': self._path_relativa(diretorio_caso / 'nova_clonagem_pos_salvar.png'),
                    'nova_clonagem_pos_salvar_formulario': self._path_relativa(diretorio_caso / 'nova_clonagem_pos_salvar_formulario.png'),
                    'antiga_edicao_clone': self._path_relativa(diretorio_caso / 'antiga_edicao_clone.png'),
                    'nova_edicao_clone': self._path_relativa(diretorio_caso / 'nova_edicao_clone.png'),
                }
            )
        else:
            arquivos.update(
                {
                    'antiga_retornar_para_rascunho': self._path_relativa(diretorio_caso / 'antiga_retornar_para_rascunho.png'),
                    'nova_retornar_para_rascunho': self._path_relativa(diretorio_caso / 'nova_retornar_para_rascunho.png'),
                    'antiga_edicao': self._path_relativa(diretorio_caso / 'antiga_edicao.png'),
                    'nova_edicao': self._path_relativa(diretorio_caso / 'nova_edicao.png'),
                }
            )

        return arquivos

    def _extrair_urls(self, row):
        """Extrai do dicionario da amostra as URLs de interesse para validacao.

        Returns:
            ``dict`` com chaves no formato ``<operacao>_<ambiente>``.
        """
        return {
            'visualizacao_antiga': row.get('url_visualizacao_antiga', ''),
            'visualizacao_nova': row.get('url_visualizacao_nova', ''),
            'pdf_antiga': row.get('url_pdf_antiga', ''),
            'pdf_nova': row.get('url_pdf_nova', ''),
            'edicao_antiga': row.get('url_edicao_antiga', ''),
            'edicao_nova': row.get('url_edicao_nova', ''),
            'clonar_antiga': row.get('url_clonar_antiga', ''),
            'clonar_nova': row.get('url_clonar_nova', ''),
            'edicao_clone_antiga_template': row.get('url_edicao_clone_antiga_template', ''),
            'edicao_clone_nova_template': row.get('url_edicao_clone_nova_template', ''),
            'retornar_para_rascunho_antiga': row.get('url_retornar_para_rascunho_antiga', ''),
            'retornar_para_rascunho_nova': row.get('url_retornar_para_rascunho_nova', ''),
        }

    def _salvar_preparacao(self, preparacao, arquivo_preparacao):
        path = self._resolve_path(arquivo_preparacao)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(preparacao, indent=2, ensure_ascii=False) + '\n')

    def _executar_etapa_visualizacao(
        self,
        preparacao,
        casos,
        senha_antiga,
        senha_nova,
        username_antigo_fixo,
        username_novo_fixo,
        arquivo_preparacao,
        headless,
    ):
        """Percorre todos os casos e executa a validacao visual com Playwright.

        Args:
            preparacao: estrutura de preparacao (atualizada ao final de cada caso).
            casos: lista de dicionarios com dados dos casos.
            senha_antiga: senha para login no ambiente antigo.
            senha_nova: senha para login no ambiente novo.
            username_antigo_fixo: username fixo para ambiente antigo (opcional).
            username_novo_fixo: username fixo para ambiente novo (opcional).
            arquivo_preparacao: caminho para salvar o progresso a cada caso.
            headless: ``True`` para executar o navegador em modo headless.
        """
        from playwright.sync_api import sync_playwright

        if not casos:
            self._emitir_status('Nenhum caso disponivel para a etapa de visualizacao.')
            return

        self._emitir_status(f'Iniciando etapa de visualizacao para {len(casos)} caso(s).')
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=headless,
                args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-setuid-sandbox',
                ],
            )
            try:
                for indice, caso in enumerate(casos, start=1):
                    self._emitir_status(
                        f'[{indice}/{len(casos)}] Visualizacao do documento {caso.get("documento_id")} ({caso.get("categoria_amostra")})'
                    )
                    self._executar_visualizacao_caso(
                        browser=browser,
                        caso=caso,
                        senha_antiga=senha_antiga,
                        senha_nova=senha_nova,
                        username_antigo_fixo=username_antigo_fixo,
                        username_novo_fixo=username_novo_fixo,
                    )
                    self._atualizar_metadata_caso(caso)
                    self._salvar_preparacao(preparacao, arquivo_preparacao)
            finally:
                browser.close()

    def _executar_visualizacao_caso(
        self,
        browser,
        caso,
        senha_antiga,
        senha_nova,
        username_antigo_fixo,
        username_novo_fixo,
    ):
        """Executa a validacao visual de um unico caso nos dois ambientes.

        Para cada ambiente (antigo e novo), realiza login, captura screenshot
        da visualizacao, baixa o PDF e, conforme o status, executa o fluxo de
        edicao direta ou via clonagem.

        Raises:
            RuntimeError: se URL de visualizacao ou username estiverem ausentes.
        """
        self._resetar_estado_caso(caso)
        etapa_visualizacao = caso['etapas']['visualizacao']
        username_amostra = caso.get('username_dono') or ''
        status_id = str(caso.get('status_id') or '')

        ambientes = (
            (
                'antiga',
                caso['urls'].get('visualizacao_antiga'),
                caso['arquivos_esperados'].get('antiga_visualizacao'),
                caso['urls'].get('pdf_antiga'),
                caso['arquivos_esperados'].get('antiga_pdf'),
                caso['urls'].get('edicao_antiga'),
                caso['arquivos_esperados'].get('antiga_edicao'),
                caso['urls'].get('retornar_para_rascunho_antiga'),
                caso['arquivos_esperados'].get('antiga_retornar_para_rascunho'),
                caso['urls'].get('clonar_antiga'),
                caso['arquivos_esperados'].get('antiga_clonagem'),
                caso['arquivos_esperados'].get('antiga_clonagem_pre_salvar'),
                caso['arquivos_esperados'].get('antiga_clonagem_pos_salvar'),
                caso['arquivos_esperados'].get('antiga_clonagem_pos_salvar_formulario'),
                caso['urls'].get('edicao_clone_antiga_template'),
                caso['arquivos_esperados'].get('antiga_edicao_clone'),
                username_antigo_fixo or username_amostra,
                senha_antiga,
            ),
            (
                'nova',
                caso['urls'].get('visualizacao_nova'),
                caso['arquivos_esperados'].get('nova_visualizacao'),
                caso['urls'].get('pdf_nova'),
                caso['arquivos_esperados'].get('nova_pdf'),
                caso['urls'].get('edicao_nova'),
                caso['arquivos_esperados'].get('nova_edicao'),
                caso['urls'].get('retornar_para_rascunho_nova'),
                caso['arquivos_esperados'].get('nova_retornar_para_rascunho'),
                caso['urls'].get('clonar_nova'),
                caso['arquivos_esperados'].get('nova_clonagem'),
                caso['arquivos_esperados'].get('nova_clonagem_pre_salvar'),
                caso['arquivos_esperados'].get('nova_clonagem_pos_salvar'),
                caso['arquivos_esperados'].get('nova_clonagem_pos_salvar_formulario'),
                caso['urls'].get('edicao_clone_nova_template'),
                caso['arquivos_esperados'].get('nova_edicao_clone'),
                username_novo_fixo or username_amostra,
                senha_nova,
            ),
        )

        try:
            for (
                ambiente_nome,
                url_visualizacao,
                screenshot_relpath,
                url_pdf,
                pdf_relpath,
                url_edicao,
                edicao_relpath,
                url_retornar_rascunho,
                retornar_rascunho_relpath,
                url_clonagem,
                clonagem_relpath,
                clonagem_pre_salvar_relpath,
                clonagem_pos_salvar_relpath,
                clonagem_pos_salvar_formulario_relpath,
                url_edicao_clone_template,
                edicao_clone_relpath,
                username,
                senha,
            ) in ambientes:
                if not url_visualizacao:
                    raise RuntimeError(f'URL de visualizacao ausente para o ambiente {ambiente_nome}.')
                if not username:
                    raise RuntimeError(f'Username ausente para o ambiente {ambiente_nome}.')

                contexto = browser.new_context(ignore_https_errors=True, accept_downloads=True, viewport={'width': 1440, 'height': 1200})
                try:
                    page = contexto.new_page()
                    page.set_default_timeout(self.timeout_ms)
                    page.set_default_navigation_timeout(self.timeout_ms)
                    self._realizar_login(page, url_visualizacao, username, senha, ambiente_nome)
                    self._abrir_visualizacao_e_salvar_screenshot(page, url_visualizacao, screenshot_relpath, ambiente_nome)
                    ambiente_info = {
                        'status': 'ok',
                        'username': username,
                        'url_visualizacao': url_visualizacao,
                        'screenshot': screenshot_relpath,
                    }
                    if url_pdf and pdf_relpath:
                        self._baixar_pdf(contexto, url_pdf, pdf_relpath, ambiente_nome)
                        ambiente_info['pdf'] = {'url': url_pdf, 'arquivo': pdf_relpath}
                    if status_id == '7':
                        clone_id = self._capturar_edicao_via_clonagem(
                            page=page,
                            ambiente_nome=ambiente_nome,
                            url_clonagem=url_clonagem,
                            clonagem_relpath=clonagem_relpath,
                            clonagem_pre_salvar_relpath=clonagem_pre_salvar_relpath,
                            clonagem_pos_salvar_relpath=clonagem_pos_salvar_relpath,
                            clonagem_pos_salvar_formulario_relpath=clonagem_pos_salvar_formulario_relpath,
                            url_edicao_clone_template=url_edicao_clone_template,
                            edicao_clone_relpath=edicao_clone_relpath,
                        )
                        ambiente_info['edicao'] = {
                            'fluxo': 'clonagem',
                            'clone_id': clone_id,
                            'clonagem': clonagem_relpath,
                            'screenshot': edicao_clone_relpath,
                        }
                    elif url_edicao and edicao_relpath:
                        self._capturar_edicao_direta(
                            page=page,
                            ambiente_nome=ambiente_nome,
                            url_retornar_rascunho=url_retornar_rascunho,
                            retornar_rascunho_relpath=retornar_rascunho_relpath,
                            url_edicao=url_edicao,
                            edicao_relpath=edicao_relpath,
                        )
                        ambiente_info['edicao'] = {
                            'fluxo': 'direta',
                            'retornar_para_rascunho': retornar_rascunho_relpath,
                            'screenshot': edicao_relpath,
                        }
                    etapa_visualizacao['ambientes'][ambiente_nome] = ambiente_info
                finally:
                    contexto.close()

            etapa_visualizacao['status'] = 'ok'
            caso['status_execucao'] = 'visualizacao_ok'
        except Exception as exc:
            etapa_visualizacao['status'] = 'erro'
            etapa_visualizacao['erro'] = str(exc)
            caso['status_execucao'] = 'erro'
            caso['observacoes'] = self._append_observacao(caso.get('observacoes', ''), f'Falha na etapa de visualizacao: {exc}')

    def _realizar_login(self, page, url_referencia, username, senha, ambiente_nome):
        """Autentica o usuario no ambiente via pagina de login do SUAP.

        Args:
            page: instancia de ``Page`` do Playwright.
            url_referencia: URL de uma pagina interna (usada para montar o
                parametro ``next``).
            username: nome de usuario.
            senha: senha do usuario.
            ambiente_nome: identificador do ambiente (usado apenas em logs).

        Raises:
            RuntimeError: se o login nao for concluido (URL ainda contem
                ``/accounts/login/``).
        """
        base_url = self._get_base_url(url_referencia)
        caminho_destino = urlparse(url_referencia).path or '/'
        next_param = quote(caminho_destino, safe='/')
        login_url = f'{base_url}/accounts/login/?next={next_param}'
        self._emitir_status(f'[{ambiente_nome}] Fazendo login em {login_url} com o usuario {username}. Timeout: {self.timeout_seconds}s.')

        inicio = time.perf_counter()
        page.goto(login_url, wait_until='load')
        self._emitir_tempo_decorrido(f'[{ambiente_nome}] GET login', inicio)

        page.locator('#id_username').fill(username)
        page.locator('#id_password').fill(senha)

        inicio = time.perf_counter()
        page.locator('input[type="submit"][value="Acessar"]').click()
        page.wait_for_load_state('networkidle')
        self._emitir_tempo_decorrido(f'[{ambiente_nome}] POST login', inicio)

        if '/accounts/login/' in page.url:
            erros = [texto.strip() for texto in page.locator('.errornote, .alert-danger').all_inner_texts() if texto.strip()]
            detalhes = f' Detalhes: {" | ".join(erros)}' if erros else ''
            raise RuntimeError(f'Login nao concluido no ambiente {ambiente_nome}.{detalhes}')

    def _abrir_visualizacao_e_salvar_screenshot(self, page, url_visualizacao, screenshot_relpath, ambiente_nome):
        """Navega ate a URL de visualizacao e salva um screenshot da pagina.

        Args:
            page: instancia de ``Page`` do Playwright.
            url_visualizacao: URL da pagina de visualizacao do documento.
            screenshot_relpath: caminho relativo para salvar o screenshot.
            ambiente_nome: identificador do ambiente (logs).
        """
        screenshot_path = self._resolve_path(screenshot_relpath)
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        self._emitir_status(f'[{ambiente_nome}] Abrindo visualizacao: {url_visualizacao}. Timeout: {self.timeout_seconds}s.')
        inicio = time.perf_counter()
        page.goto(url_visualizacao, wait_until='networkidle')
        self._emitir_tempo_decorrido(f'[{ambiente_nome}] GET visualizacao', inicio)

        self._salvar_screenshot_pagina(
            page=page,
            screenshot_relpath=screenshot_relpath,
            ambiente_nome=ambiente_nome,
            descricao='Screenshot visualizacao',
            expandir_visualizacao=True,
        )

    def _expandir_iframes_visualizacao(self, page, ambiente_nome):
        total_iframes = page.locator('iframe').count()
        if not total_iframes:
            self._emitir_status(f'[{ambiente_nome}] Nenhum iframe encontrado na visualizacao.')
            return

        self._expandir_iframes_da_pagina(page, ambiente_nome, contexto='visualizacao')

    def _capturar_edicao_direta(self, page, ambiente_nome, url_retornar_rascunho, retornar_rascunho_relpath, url_edicao, edicao_relpath):
        """Retorna o documento para rascunho (se aplicavel) e captura a tela de edicao."""
        if url_retornar_rascunho and retornar_rascunho_relpath:
            retornar_path = self._resolve_path(retornar_rascunho_relpath)
            retornar_path.parent.mkdir(parents=True, exist_ok=True)
            self._emitir_status(f'[{ambiente_nome}] Retornando documento para rascunho: {url_retornar_rascunho}. Timeout: {self.timeout_seconds}s.')
            inicio = time.perf_counter()
            page.goto(url_retornar_rascunho, wait_until='networkidle')
            self._emitir_tempo_decorrido(f'[{ambiente_nome}] GET retornar_para_rascunho', inicio)
            inicio = time.perf_counter()
            page.screenshot(path=str(retornar_path), full_page=True)
            self._emitir_tempo_decorrido(f'[{ambiente_nome}] Screenshot retornar_para_rascunho', inicio)

        self._abrir_edicao_e_salvar_screenshot(page, ambiente_nome, url_edicao, edicao_relpath)

    def _capturar_edicao_via_clonagem(
        self,
        page,
        ambiente_nome,
        url_clonagem,
        clonagem_relpath,
        clonagem_pre_salvar_relpath,
        clonagem_pos_salvar_relpath,
        clonagem_pos_salvar_formulario_relpath,
        url_edicao_clone_template,
        edicao_clone_relpath,
    ):
        """Executa o fluxo de clonagem de documento e captura a tela de edicao do clone.

        Raises:
            RuntimeError: se URL de clonagem ou template de edicao estiverem
                ausentes, ou se o clone nao for identificado apos a submissao.

        Returns:
            ``int`` com o ID do documento clonado.
        """
        if not url_clonagem:
            raise RuntimeError(f'URL de clonagem ausente para o ambiente {ambiente_nome}.')
        if not url_edicao_clone_template:
            raise RuntimeError(f'URL template de edicao do clone ausente para o ambiente {ambiente_nome}.')

        clonagem_path = self._resolve_path(clonagem_relpath)
        clonagem_path.parent.mkdir(parents=True, exist_ok=True)
        self._emitir_status(f'[{ambiente_nome}] Abrindo clonagem: {url_clonagem}. Timeout: {self.timeout_seconds}s.')
        inicio = time.perf_counter()
        page.goto(url_clonagem, wait_until='networkidle')
        self._emitir_tempo_decorrido(f'[{ambiente_nome}] GET clonagem', inicio)
        inicio = time.perf_counter()
        page.screenshot(path=str(clonagem_path), full_page=True)
        self._emitir_tempo_decorrido(f'[{ambiente_nome}] Screenshot clonagem', inicio)

        self._preencher_formulario_clonagem(page, ambiente_nome)
        self._salvar_screenshot_pagina(
            page=page,
            screenshot_relpath=clonagem_pre_salvar_relpath,
            ambiente_nome=ambiente_nome,
            descricao='Screenshot clonagem antes de salvar',
        )
        inicio = time.perf_counter()
        self._submeter_formulario(page)
        page.wait_for_load_state('networkidle')
        self._emitir_tempo_decorrido(f'[{ambiente_nome}] POST clonagem', inicio)
        self._salvar_screenshot_pagina(
            page=page,
            screenshot_relpath=clonagem_pos_salvar_relpath,
            ambiente_nome=ambiente_nome,
            descricao='Screenshot clonagem apos salvar',
            expandir_visualizacao=True,
        )
        self._salvar_screenshot_area_formulario(
            page=page,
            screenshot_relpath=clonagem_pos_salvar_formulario_relpath,
            ambiente_nome=ambiente_nome,
            descricao='Screenshot formulario clonagem apos salvar',
        )

        clone_id = self._extrair_documento_id_visualizacao(page.url)
        if not clone_id:
            detalhes = self._extrair_erros_pagina(page)
            detalhes_texto = f' Detalhes: {detalhes}' if detalhes else ''
            raise RuntimeError(f'[{ambiente_nome}] Nao foi possivel identificar o documento clonado a partir da URL {page.url}.{detalhes_texto}')

        url_edicao_clone = url_edicao_clone_template.replace('<clone_id>', str(clone_id))
        self._abrir_edicao_e_salvar_screenshot(page, ambiente_nome, url_edicao_clone, edicao_clone_relpath)
        return clone_id

    def _abrir_edicao_e_salvar_screenshot(self, page, ambiente_nome, url_edicao, edicao_relpath):
        """Navega ate a URL de edicao, ajusta o editor e salva um screenshot.

        Args:
            page: instancia de ``Page`` do Playwright.
            ambiente_nome: identificador do ambiente (logs).
            url_edicao: URL da pagina de edicao do documento.
            edicao_relpath: caminho relativo para salvar o screenshot.
        """
        edicao_path = self._resolve_path(edicao_relpath)
        edicao_path.parent.mkdir(parents=True, exist_ok=True)
        self._emitir_status(f'[{ambiente_nome}] Abrindo edicao: {url_edicao}. Timeout: {self.timeout_seconds}s.')
        inicio = time.perf_counter()
        page.goto(url_edicao, wait_until='networkidle')
        self._emitir_tempo_decorrido(f'[{ambiente_nome}] GET edicao', inicio)
        inicio = time.perf_counter()
        self._ajustar_editor_para_captura(page, ambiente_nome)
        self._emitir_tempo_decorrido(f'[{ambiente_nome}] Ajuste do editor para captura', inicio)
        inicio = time.perf_counter()
        page.screenshot(path=str(edicao_path), full_page=True)
        self._emitir_tempo_decorrido(f'[{ambiente_nome}] Screenshot edicao', inicio)

    def _preencher_formulario_clonagem(self, page, ambiente_nome):
        """Preenche campos do formulario de clonagem (assunto, setor, ciencia, obrigatorios)."""
        assunto = page.locator('#id_assunto')
        if assunto.count():
            valor = assunto.input_value().strip()
            if not valor:
                assunto.fill('Clone automatico para validacao do editor')
            else:
                assunto.fill(valor)

        setor_dono_preenchido = self._preencher_setor_dono_clonagem(page)
        if setor_dono_preenchido:
            self._emitir_status(f'[{ambiente_nome}] Campo setor_dono ajustado para submissao.')

        ciencia = page.locator('#id_ciencia_instrucoes_gerais')
        if ciencia.count():
            tag_name = (ciencia.evaluate('(el) => el.tagName.toLowerCase()') or '').strip()
            input_type = (ciencia.get_attribute('type') or '').strip().lower()
            if tag_name == 'input' and input_type in ('checkbox', 'radio') and not ciencia.is_checked():
                ciencia.check()

        preenchidos = self._preencher_campos_obrigatorios_vazios(page)
        if preenchidos:
            self._emitir_status(f'[{ambiente_nome}] Campos obrigatorios preenchidos automaticamente: {", ".join(preenchidos)}')

        self._emitir_status(f'[{ambiente_nome}] Formulario de clonagem preparado para submissao.')

    def _preencher_setor_dono_clonagem(self, page):
        """Preenche o campo de setor dono no formulario de clonagem.

        Se for um ``<select>``, tenta selecionar a opcao valida atual ou a
        primeira opcao nao-desabilitada.

        Args:
            page: instancia de ``Page`` do Playwright.

        Returns:
            ``True`` se o campo foi preenchido/validado, ``False`` se o
            campo nao existe na pagina.
        """
        setor = page.locator('#id_setor_dono')
        if not setor.count():
            return False

        tag_name = (setor.evaluate('(el) => el.tagName.toLowerCase()') or '').strip()
        if tag_name != 'select':
            valor_atual = (setor.input_value() or '').strip()
            return bool(valor_atual)

        dados = setor.evaluate(
            """
            (el) => {
                const opcoes = Array.from(el.options || []).map((opt) => ({
                    value: opt.value,
                    disabled: opt.disabled,
                    selected: opt.selected,
                }));
                const selecionada = opcoes.find((opt) => opt.selected && opt.value && !opt.disabled);
                const primeiraValida = opcoes.find((opt) => opt.value && !opt.disabled);
                return {
                    value: el.value || '',
                    selecionada: selecionada ? selecionada.value : '',
                    primeiraValida: primeiraValida ? primeiraValida.value : '',
                };
            }
            """
        )

        valor = (dados.get('selecionada') or dados.get('value') or dados.get('primeiraValida') or '').strip()
        if not valor:
            return False

        try:
            setor.select_option(value=valor)
        except Exception:
            page.evaluate(
                """
                ({ selector, value }) => {
                    const campo = document.querySelector(selector);
                    if (!campo) return;
                    campo.value = value;
                    campo.dispatchEvent(new Event('input', { bubbles: true }));
                    campo.dispatchEvent(new Event('change', { bubbles: true }));
                }
                """,
                {'selector': '#id_setor_dono', 'value': valor},
            )
        return True

    def _preencher_campos_obrigatorios_vazios(self, page):
        """Preenche automaticamente campos obrigatorios vazios no formulario.

        Args:
            page: instancia de ``Page`` do Playwright.

        Returns:
            ``list[str]`` com os nomes/ids dos campos preenchidos.
        """
        return page.evaluate(
            """
            () => {
                const preenchidos = [];
                const campos = Array.from(
                    document.querySelectorAll('form [required], form [aria-required="true"]')
                );

                const campoVisivel = (el) => {
                    const style = window.getComputedStyle(el);
                    return style.display !== 'none' && style.visibility !== 'hidden' && el.type !== 'hidden';
                };

                for (const campo of campos) {
                    if (!campo.name || campo.disabled || !campoVisivel(campo)) continue;

                    const tag = campo.tagName.toLowerCase();
                    const tipo = (campo.getAttribute('type') || '').toLowerCase();
                    const identificador = campo.name || campo.id || tag;

                    if (tag === 'select') {
                        if (campo.value) continue;
                        const opcoes = Array.from(campo.options || []).filter((opt) => !opt.disabled && opt.value);
                        if (opcoes.length) {
                            campo.value = opcoes[0].value;
                            campo.dispatchEvent(new Event('change', { bubbles: true }));
                            preenchidos.push(identificador);
                        }
                        continue;
                    }

                    if (tag === 'textarea' || (tag === 'input' && ['text', 'email', 'number', 'search', 'url', 'tel'].includes(tipo))) {
                        if ((campo.value || '').trim()) continue;
                        campo.value = tag === 'textarea' ? 'Preenchimento automatico para validacao' : 'Preenchimento automatico';
                        campo.dispatchEvent(new Event('input', { bubbles: true }));
                        campo.dispatchEvent(new Event('change', { bubbles: true }));
                        preenchidos.push(identificador);
                        continue;
                    }

                    if (tag === 'input' && tipo === 'checkbox') {
                        if (!campo.checked) {
                            campo.checked = true;
                            campo.dispatchEvent(new Event('change', { bubbles: true }));
                            preenchidos.push(identificador);
                        }
                        continue;
                    }

                    if (tag === 'input' && tipo === 'radio') {
                        if (campo.checked) continue;
                        const grupo = Array.from(document.querySelectorAll(`input[type="radio"][name="${campo.name}"]`)).filter(
                            (radio) => !radio.disabled
                        );
                        if (grupo.length) {
                            grupo[0].checked = true;
                            grupo[0].dispatchEvent(new Event('change', { bubbles: true }));
                            preenchidos.push(identificador);
                        }
                    }
                }

                return preenchidos;
            }
            """
        )

    def _submeter_formulario(self, page):
        """Localiza e clica no primeiro botao de submit encontrado no formulario.

        Raises:
            RuntimeError: se nenhum botao de submit for encontrado.
        """
        seletores = (
            'form .submit-row input[type="submit"]',
            'form .submit-row button[type="submit"]',
            'form input[type="submit"]',
            'form button[type="submit"]',
        )
        for seletor in seletores:
            locator = page.locator(seletor).first
            if locator.count():
                locator.click()
                return
        raise RuntimeError('Nao foi encontrado botao de submit no formulario.')

    def _salvar_screenshot_pagina(self, page, screenshot_relpath, ambiente_nome, descricao, expandir_visualizacao=False):
        """Tira um screenshot full-page e salva no caminho especificado.

        Args:
            page: instancia de ``Page`` do Playwright.
            screenshot_relpath: caminho relativo do arquivo de screenshot.
            ambiente_nome: identificador do ambiente (logs).
            descricao: texto descritivo para o log.
            expandir_visualizacao: se ``True``, expande iframes antes de capturar.
        """
        if not screenshot_relpath:
            return
        screenshot_path = self._resolve_path(screenshot_relpath)
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        if expandir_visualizacao:
            self._expandir_iframes_visualizacao(page, ambiente_nome)
        inicio = time.perf_counter()
        page.screenshot(path=str(screenshot_path), full_page=True)
        self._emitir_tempo_decorrido(f'[{ambiente_nome}] {descricao}', inicio)

    def _salvar_screenshot_area_formulario(self, page, screenshot_relpath, ambiente_nome, descricao):
        """Tira um screenshot restrito ao elemento ``<form>`` da pagina.

        Args:
            page: instancia de ``Page`` do Playwright.
            screenshot_relpath: caminho relativo do arquivo de screenshot.
            ambiente_nome: identificador do ambiente (logs).
            descricao: texto descritivo para o log.
        """
        if not screenshot_relpath:
            return

        locator = page.locator('form').first
        if not locator.count():
            self._salvar_screenshot_pagina(page, screenshot_relpath, ambiente_nome, descricao)
            return

        screenshot_path = self._resolve_path(screenshot_relpath)
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        inicio = time.perf_counter()
        locator.screenshot(path=str(screenshot_path))
        self._emitir_tempo_decorrido(f'[{ambiente_nome}] {descricao}', inicio)

    def _extrair_erros_pagina(self, page):
        """Extrai mensagens de erro visiveis na pagina usando seletores conhecidos.

        Args:
            page: instancia de ``Page`` do Playwright.

        Returns:
            ``str`` com todas as mensagens concatenadas por `` | ``, ou vazio.
        """
        seletores = (
            '.errornote',
            '.errorlist',
            '.alert-danger',
            '.messages .error',
            '.messages .warning',
            '.messages .info',
        )
        mensagens = []
        for seletor in seletores:
            try:
                textos = page.locator(seletor).all_inner_texts()
            except Exception:
                textos = []
            for texto in textos:
                texto = (texto or '').strip()
                if texto and texto not in mensagens:
                    mensagens.append(texto)
        return ' | '.join(mensagens)

    def _extrair_documento_id_visualizacao(self, url):
        parsed = urlparse(url)
        partes = [parte for parte in parsed.path.split('/') if parte]
        for indice, parte in enumerate(partes[:-1]):
            if parte == 'visualizar_documento' and partes[indice + 1].isdigit():
                return int(partes[indice + 1])
        return None

    def _ajustar_editor_para_captura(self, page, ambiente_nome):
        self._expandir_iframes_da_pagina(page, ambiente_nome, contexto='editor')
        self._emitir_status(f'[{ambiente_nome}] Editor ajustado para captura completa.')

    def _expandir_iframes_da_pagina(self, page, ambiente_nome, contexto):
        """Expande todos os iframes, contenedores e textarea na pagina para captura visual completa.

        Args:
            page: instancia de ``Page`` do Playwright.
            ambiente_nome: identificador do ambiente (logs).
            contexto: ``'visualizacao'`` ou ``'editor'`` — usado para ajustar
                contenedores do TinyMCE.
        """
        resultado = page.evaluate(
            """
            (contexto) => {
                const expandirContenedorRolavel = (elemento, alturaMinima = 0) => {
                    if (!elemento) return false;
                    const style = window.getComputedStyle(elemento);
                    const altura = Math.max(
                        elemento.scrollHeight || 0,
                        elemento.offsetHeight || 0,
                        elemento.clientHeight || 0,
                        alturaMinima || 0,
                    );
                    const temRolagem =
                        ['auto', 'scroll'].includes(style.overflow) ||
                        ['auto', 'scroll'].includes(style.overflowY) ||
                        ['auto', 'scroll'].includes(style.overflowX);

                    if (temRolagem || altura > elemento.clientHeight || alturaMinima) {
                        elemento.style.overflow = 'visible';
                        elemento.style.overflowY = 'visible';
                        elemento.style.overflowX = 'visible';
                        elemento.style.height = `${altura + 40}px`;
                        elemento.style.maxHeight = 'none';
                        return true;
                    }
                    return false;
                };

                const medirDocumentoIframe = (doc) => {
                    const html = doc.documentElement;
                    const body = doc.body;
                    if (!html || !body) return 0;

                    html.style.overflow = 'visible';
                    html.style.height = 'auto';
                    html.style.maxHeight = 'none';
                    body.style.overflow = 'visible';
                    body.style.height = 'auto';
                    body.style.maxHeight = 'none';
                    body.style.minHeight = '0';

                    const candidatos = [
                        html.scrollHeight,
                        body.scrollHeight,
                        html.offsetHeight,
                        body.offsetHeight,
                        html.clientHeight,
                        body.clientHeight,
                    ];

                    if (body.firstElementChild) {
                        candidatos.push(body.firstElementChild.scrollHeight || 0);
                        candidatos.push(body.firstElementChild.offsetHeight || 0);
                    }

                    const elementos = Array.from(body.querySelectorAll('*'));
                    for (const elemento of elementos) {
                        try {
                            const rect = elemento.getBoundingClientRect();
                            const scrollY = doc.defaultView?.scrollY || 0;
                            const bottom = rect.bottom + scrollY;
                            const top = rect.top + scrollY;
                            candidatos.push(bottom || 0);
                            candidatos.push((bottom - top) || 0);
                            candidatos.push(elemento.scrollHeight || 0);
                            candidatos.push(elemento.offsetHeight || 0);
                        } catch (error) {
                            // Ignora elementos que nao puderem ser medidos.
                        }
                    }

                    return Math.max(...candidatos.filter((valor) => Number.isFinite(valor)));
                };

                let iframesAjustados = 0;
                const iframes = Array.from(document.querySelectorAll('iframe'));
                for (const iframe of iframes) {
                    try {
                        const doc = iframe.contentDocument || iframe.contentWindow?.document;
                        if (!doc) continue;

                        let altura = medirDocumentoIframe(doc);

                        if (contexto === 'editor' && window.tinymce?.editors?.length) {
                            for (const editor of window.tinymce.editors) {
                                const editorIframe = editor.iframeElement || editor.getContainer?.()?.querySelector('iframe');
                                if (editorIframe !== iframe) continue;

                                const body = editor.getBody?.();
                                const editorDoc = editor.getDoc?.();
                                altura = Math.max(
                                    altura,
                                    body?.scrollHeight || 0,
                                    body?.offsetHeight || 0,
                                    editorDoc?.documentElement?.scrollHeight || 0,
                                    editorDoc?.documentElement?.offsetHeight || 0,
                                );

                                const container = editor.getContainer?.();
                                if (container) {
                                    container.style.height = 'auto';
                                    container.style.maxHeight = 'none';
                                    container.style.overflow = 'visible';
                                    altura = Math.max(
                                        altura,
                                        container.scrollHeight || 0,
                                        container.offsetHeight || 0,
                                    );
                                }
                            }
                        }

                        iframe.style.overflow = 'hidden';
                        iframe.setAttribute('scrolling', 'no');
                        const alturaFinal = altura + 80;
                        iframe.style.height = `${alturaFinal}px`;
                        iframe.style.minHeight = `${alturaFinal}px`;
                        iframe.style.maxHeight = 'none';

                        expandirContenedorRolavel(iframe.parentElement, alturaFinal);
                        expandirContenedorRolavel(
                            iframe.closest('.visualizacao, .documento, .tox-edit-area, .tox-editor-container, .tox, .mce-edit-area, .mce-container, .editor, .form-row, .form-row.corpo, .fieldBox, .field-box-first, .grp-row'),
                            alturaFinal
                        );

                        if (contexto === 'editor') {
                            const editorContainers = [
                                iframe.closest('.tox-edit-area'),
                                iframe.closest('.tox-editor-container'),
                                iframe.closest('.tox'),
                                iframe.closest('.mce-edit-area'),
                                iframe.closest('.mce-container'),
                                iframe.closest('.field-box-first'),
                                iframe.closest('.fieldBox'),
                                iframe.closest('.form-row.corpo'),
                                iframe.closest('.form-row'),
                            ].filter(Boolean);

                            for (const container of editorContainers) {
                                container.style.height = 'auto';
                                container.style.minHeight = `${alturaFinal + 120}px`;
                                container.style.maxHeight = 'none';
                                container.style.overflow = 'visible';
                            }
                        }
                        iframesAjustados += 1;
                    } catch (error) {
                        // Ignora iframes sem acesso.
                    }
                }

                let contenedoresAjustados = 0;
                const candidatos = Array.from(
                    document.querySelectorAll(
                        '.visualizacao, .documento, .tox, .tox-editor-container, .tox-edit-area, .mce-container, .mce-edit-area, .fieldBox, .form-row, .grp-row'
                    )
                );
                for (const candidato of candidatos) {
                    if (expandirContenedorRolavel(candidato)) {
                        contenedoresAjustados += 1;
                    }
                }

                let textareaAjustada = false;
                const textarea = document.querySelector('textarea.tinymce, #id_corpo');
                if (textarea) {
                    const alturaTextarea = Math.max(textarea.scrollHeight || 0, 2000);
                    textarea.style.height = `${alturaTextarea}px`;
                    textarea.style.minHeight = `${alturaTextarea}px`;
                    textarea.style.maxHeight = 'none';
                    textarea.style.overflow = 'visible';
                    expandirContenedorRolavel(textarea.parentElement, alturaTextarea);
                    textareaAjustada = true;
                }

                document.documentElement.style.overflow = 'visible';
                document.documentElement.style.height = 'auto';
                document.documentElement.style.maxHeight = 'none';
                document.body.style.overflow = 'visible';
                document.body.style.height = 'auto';
                document.body.style.maxHeight = 'none';

                return { iframesAjustados, contenedoresAjustados, textareaAjustada };
            }
            """,
            contexto,
        )
        self._emitir_status(
            f'[{ambiente_nome}] Ajuste de iframes ({contexto}): '
            f'{resultado.get("iframesAjustados", 0)} iframe(s), '
            f'{resultado.get("contenedoresAjustados", 0)} contenedor(es), '
            f'textarea ajustada={resultado.get("textareaAjustada", False)}.'
        )

    def _baixar_pdf(self, contexto, url_pdf, pdf_relpath, ambiente_nome):
        """Baixa o PDF de um documento, lidando com redirecionamento para task assincrona.

        Tenta obter o PDF diretamente via GET. Se a resposta for um
        redirecionamento para ``/djtools/process/``, delega para
        ``_baixar_pdf_via_task``.

        Args:
            contexto: instancia de ``BrowserContext`` do Playwright (para cookies).
            url_pdf: URL do PDF.
            pdf_relpath: caminho relativo para salvar o arquivo.
            ambiente_nome: identificador do ambiente (logs).

        Raises:
            RuntimeError: se a resposta nao for PDF nem redirecionamento esperado.
        """
        pdf_path = self._resolve_path(pdf_relpath)
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        self._emitir_status(f'[{ambiente_nome}] Baixando PDF: {url_pdf}. Timeout: {self.timeout_seconds}s.')

        sessao = requests.Session()
        sessao.verify = False
        for cookie in contexto.cookies():
            sessao.cookies.set(
                cookie['name'],
                cookie['value'],
                domain=cookie.get('domain'),
                path=cookie.get('path', '/'),
            )

        inicio = time.perf_counter()
        response = sessao.get(url_pdf, timeout=self.timeout_seconds, allow_redirects=False)
        self._emitir_tempo_decorrido(f'[{ambiente_nome}] GET pdf', inicio)
        response.raise_for_status()

        if self._resposta_ja_eh_pdf(response):
            inicio = time.perf_counter()
            pdf_path.write_bytes(response.content)
            self._emitir_tempo_decorrido(f'[{ambiente_nome}] Escrita pdf', inicio)
            return

        process_url = response.headers.get('Location') or response.url
        process_url = urljoin(url_pdf, process_url)
        if '/djtools/process/' not in process_url:
            content_type = response.headers.get('Content-Type', '')
            raise RuntimeError(f'[{ambiente_nome}] Resposta inesperada ao baixar PDF ({content_type or "sem content-type"}).')

        self._baixar_pdf_via_task(sessao, process_url, pdf_path, ambiente_nome)

    def _baixar_pdf_via_task(self, sessao, process_url, pdf_path, ambiente_nome):
        """Acompanha uma task assincrona de geracao de PDF e baixa o resultado.

        Args:
            sessao: instancia de ``requests.Session`` com cookies do Playwright.
            process_url: URL da task (``/djtools/process/<uuid>/``).
            pdf_path: caminho absoluto para salvar o PDF.
            ambiente_nome: identificador do ambiente (logs).

        Raises:
            RuntimeError: se a task falhar, retornar tipo inesperado ou
                exceder o timeout.
        """
        task_uuid = self._extrair_task_uuid(process_url)
        if not task_uuid:
            raise RuntimeError(f'[{ambiente_nome}] Nao foi possivel identificar o task UUID do PDF em {process_url}.')

        progresso_url, download_url = self._montar_urls_task(process_url, task_uuid)
        self._emitir_status(f'[{ambiente_nome}] Acompanhando task de PDF {task_uuid}.')

        deadline = time.monotonic() + self.timeout_seconds
        while time.monotonic() < deadline:
            inicio = time.perf_counter()
            response = sessao.get(progresso_url, timeout=self.timeout_seconds)
            self._emitir_tempo_decorrido(f'[{ambiente_nome}] Poll progresso pdf', inicio)
            response.raise_for_status()
            percentual, mensagem, arquivo, _url, erro = self._parse_process_progress(response.text)

            if erro:
                raise RuntimeError(f'[{ambiente_nome}] Erro ao gerar PDF: {mensagem or erro}')

            if mensagem or arquivo:
                inicio = time.perf_counter()
                download_response = sessao.get(download_url, timeout=self.timeout_seconds)
                self._emitir_tempo_decorrido(f'[{ambiente_nome}] Download arquivo pdf', inicio)
                download_response.raise_for_status()
                if not self._resposta_ja_eh_pdf(download_response):
                    content_type = download_response.headers.get('Content-Type', '')
                    raise RuntimeError(
                        f'[{ambiente_nome}] Download final do PDF retornou content-type inesperado ({content_type or "sem content-type"}).'
                    )
                inicio = time.perf_counter()
                pdf_path.write_bytes(download_response.content)
                self._emitir_tempo_decorrido(f'[{ambiente_nome}] Escrita pdf', inicio)
                return

            self._emitir_status(f'[{ambiente_nome}] Progresso PDF: {percentual or "?"}%')
            time.sleep(1)

        raise RuntimeError(f'[{ambiente_nome}] Timeout aguardando geracao do PDF pela task {task_uuid}.')

    def _resetar_estado_caso(self, caso):
        caso['status_execucao'] = 'pendente'
        caso['houve_divergencia'] = ''
        caso['descricao_divergencia'] = ''
        caso['observacoes'] = ''
        caso['etapas'] = {'visualizacao': {'status': 'pendente', 'ambientes': {}}}

    def _resposta_ja_eh_pdf(self, response):
        content_type = (response.headers.get('Content-Type') or '').lower()
        return 'application/pdf' in content_type or response.content[:4] == b'%PDF'

    def _extrair_task_uuid(self, process_url):
        parsed = urlparse(process_url)
        partes = [parte for parte in parsed.path.split('/') if parte]
        if len(partes) >= 3 and partes[-2] == 'process':
            return partes[-1]
        return None

    def _montar_urls_task(self, process_url, task_uuid):
        parsed = urlparse(process_url)
        base = f'{parsed.scheme}://{parsed.netloc}'
        return (
            f'{base}/djtools/process_progress/0/{task_uuid}/',
            f'{base}/djtools/process_progress/1/{task_uuid}/',
        )

    def _parse_process_progress(self, payload):
        tokens = payload.split('::', 4)
        while len(tokens) < 5:
            tokens.append('')
        return tokens

    def _emitir_tempo_decorrido(self, operacao, inicio):
        duracao = time.perf_counter() - inicio
        self._emitir_status(f'{operacao} concluido em {duracao:.2f}s')

    def _atualizar_metadata_caso(self, caso):
        metadata_path = self._resolve_path(caso['metadata_file'])
        metadata_path.write_text(json.dumps(caso, indent=2, ensure_ascii=False) + '\n')

    def _append_observacao(self, observacoes_atuais, nova_observacao):
        observacoes_atuais = (observacoes_atuais or '').strip()
        if not observacoes_atuais:
            return nova_observacao
        return f'{observacoes_atuais}\n{nova_observacao}'

    def _resolve_path(self, path_str):
        path = Path(path_str)
        if path.is_absolute():
            return path
        return Path(settings.BASE_DIR) / path

    def _get_base_url(self, url):
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f'URL invalida para obter base: {url}')
        return f'{parsed.scheme}://{parsed.netloc}'

    def _path_relativa(self, path):
        try:
            return str(path.relative_to(settings.BASE_DIR))
        except ValueError:
            return str(path)

    def _as_bool(self, value):
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ('1', 'true', 'sim', 'yes')

    def _as_int(self, value):
        if value in (None, ''):
            return None
        return int(value)
