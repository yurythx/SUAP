import ast
import os
import re

# Importa a classe base para comandos Django
from django.core.management.base import CommandError

from djtools.management.commands import BaseCommandPlus

# Extensões de arquivo para busca de USO
EXTENSOES_USO = ('.py', '.html')

# Pastas comuns a excluir
PASTAS_COMUNS_EXCLUIDAS = {'.git', '__pycache__', 'venv', 'env', '.vscode', '.idea', '.venv', 'static', 'deploy', 'features', 'migrations'}


# --- CLASSE DO COMANDO DJANGO ---


class Command(BaseCommandPlus):
    help = 'Busca em um diretório por funções e métodos que possuem apenas uma ocorrência (Definição + Uso) em arquivos .py e .html.'

    def add_arguments(self, parser):
        """Define os argumentos que o comando aceita."""

        # Argumento opcional para o caminho da pasta raiz
        parser.add_argument(
            '--path',
            type=str,
            default=os.getcwd(),  # Padrão é o diretório atual
            help='Caminho absoluto para a pasta raiz do projeto a ser analisado.',
        )

        # Argumento opcional para exclusão de subpastas
        parser.add_argument(
            '--exclude',
            nargs='*',  # Aceita 0 ou mais valores
            default=[],
            help='Lista de subpastas a serem excluídas (além das pastas padrão como venv e .git).',
        )

    def _extrair_definicoes_do_arquivo(self, caminho_completo: str) -> set[str]:
        """
        Analisa um arquivo Python usando AST e retorna um conjunto de nomes
        qualificados (Classe.metodo ou funcao_global) definidos.
        """
        definicoes = set()
        try:
            with open(caminho_completo, 'rb') as f:
                codigo_bytes = f.read()
                try:
                    codigo = codigo_bytes.decode('utf-8')
                except UnicodeDecodeError:
                    codigo = codigo_bytes.decode('latin-1')

            tree = ast.parse(codigo)

            for node in tree.body:
                if isinstance(node, ast.FunctionDef):
                    definicoes.add(node.name)
                elif isinstance(node, ast.ClassDef):
                    nome_classe = node.name
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef):
                            nome_metodo = item.name
                            definicoes.add(f'{nome_classe}.{nome_metodo}')
                            definicoes.add(nome_metodo)

        except Exception as e:
            if 'empty code' not in str(e):
                self.stderr.write(f'Aviso: Erro ao analisar AST em {caminho_completo}: {e}')

        return definicoes

    def handle(self, *args, **options):
        """Lógica principal do comando, chamada na execução."""

        caminho_pasta = options['path']
        subpastas_excluidas = options['exclude']

        if not os.path.isdir(caminho_pasta):
            raise CommandError(f"O caminho '{caminho_pasta}' não é uma pasta válida.")

        pastas_a_excluir = set(subpastas_excluidas or []).union(PASTAS_COMUNS_EXCLUIDAS)

        self.stdout.write(self.style.NOTICE(f'Buscando código utilizado em: {caminho_pasta}'))
        self.stdout.write(self.style.NOTICE(f'Pastas excluídas: {", ".join(pastas_a_excluir)}'))
        self.stdout.write('-' * 50)

        # Mapeamentos
        todas_definicoes: set[str] = set()
        python_files: list[str] = []
        arquivos_para_busca: list[str] = []

        # 1. Primeira Passagem: Mapear Definições e Arquivos para Busca
        for root, dirs, files in os.walk(caminho_pasta):
            # Lógica para Excluir Subpastas
            dirs[:] = [d for d in dirs if d not in pastas_a_excluir]

            for file in files:
                caminho_completo = os.path.join(root, file)

                if file.endswith('.py'):
                    python_files.append(caminho_completo)
                    todas_definicoes.update(self._extrair_definicoes_do_arquivo(caminho_completo))

                if caminho_completo.endswith(EXTENSOES_USO):
                    arquivos_para_busca.append(caminho_completo)

        if not todas_definicoes:
            self.stdout.write(self.style.SUCCESS('Nenhuma definição de função/método encontrada.'))
            return

        self.stdout.write(f'Total de definições encontradas: {len(todas_definicoes)}')
        self.stdout.write(f'Total de arquivos para busca de uso: {len(arquivos_para_busca)}')
        self.stdout.write(self.style.WARNING('Iniciando busca de ocorrências no Python...'))
        self.stdout.write('-' * 50)

        # 2. Segunda Passagem: Buscar Ocorrências de Todos os Nomes (Busca Única)
        contagem_ocorrencias = dict.fromkeys(todas_definicoes, 0)

        for caminho_arquivo in arquivos_para_busca:
            try:
                with open(caminho_arquivo, encoding='utf-8') as f:
                    conteudo = f.read()

                for nome_definicao in todas_definicoes:
                    padrao = r'\b' + re.escape(nome_definicao) + r'\b'

                    ocorrencias = re.findall(padrao, conteudo)
                    contagem_ocorrencias[nome_definicao] += len(ocorrencias)

            except Exception as e:
                self.stderr.write(f'Erro ao buscar uso no arquivo {caminho_arquivo}: {e}')

        # 3. Mapear Usos (Contagem == 1) de volta aos arquivos de definição
        nomes_utilizados_set = {nome for nome, count in contagem_ocorrencias.items() if count == 1}

        resultados_finais: list[tuple[str, str]] = []

        for arquivo_py in python_files:
            nome_relativo = os.path.relpath(arquivo_py, caminho_pasta)
            definicoes_no_arquivo = self._extrair_definicoes_do_arquivo(arquivo_py)

            for nome_qualificado in definicoes_no_arquivo:
                if nome_qualificado in nomes_utilizados_set:
                    resultados_finais.append((nome_relativo, nome_qualificado))

        # Limpeza e Relatório
        resultados_limpos: list[tuple[str, str]] = []
        nomes_qualificados_usados = {item[1] for item in resultados_finais}

        for arquivo, nome_qualificado in resultados_finais:
            if '.' not in nome_qualificado and any(
                f'{c}.' in n and n.endswith(nome_qualificado) for n in nomes_qualificados_usados for c in nome_qualificado
            ):
                continue
            resultados_limpos.append((arquivo, nome_qualificado))

        lista_final = list(set(resultados_limpos))

        if lista_final:
            self.stdout.write(self.style.SUCCESS('\n✅ FUNÇÕES E MÉTODOS UTILIZADOS ENCONTRADOS:'))
            self.stdout.write('-' * 50)

            funcoes_por_arquivo = {}
            for arquivo, nome_qualificado in lista_final:
                if arquivo not in funcoes_por_arquivo:
                    funcoes_por_arquivo[arquivo] = []
                funcoes_por_arquivo[arquivo].append(nome_qualificado)

            for arquivo, funcoes in funcoes_por_arquivo.items():
                self.stdout.write(f'\n📁 Arquivo: {arquivo}')
                for nome_funcao in sorted(set(funcoes)):
                    self.stdout.write(f'   - {self.style.SQL_FIELD(nome_funcao)}')

            self.stdout.write('-' * 50)
            self.stdout.write(self.style.SUCCESS(f'Total de {len(lista_final)} definições que parecem ser utilizadas.'))
        else:
            self.stdout.write(self.style.WARNING('❌ Nenhuma função ou método com mais de uma ocorrência encontrada.'))
