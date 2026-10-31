import os
import yaml
import glob
from django.core.management.base import BaseCommand
from datetime import datetime
from collections import defaultdict
from argparse import RawTextHelpFormatter


class Command(BaseCommand):
    help = """
    Realiza substituições com base em YAML, aplicadas por extensão de arquivo.
    Exemplo:
        0001_adicao_bootstrap.yaml
            html:
              'class="msg alert"': 'class="alert alert-warning"'
              'class="msg info"': 'class="alert alert-info"'
            py:
              'class="msg info"': 'class="alert alert-info"'

        Nesse cenário de exemplo, ao executarmos "python manage.py replace_code --config 0001",
        todos os arquivos com extensão ".html" terão...
        - O texto class="msg alert" substituído por class="alert alert-warning".
        - O texto class="msg info" substituído por class="alert alert-info"
        ... e todos os arquivos com extesão ".py" terão:
        - O texto class="msg info" substituído por class="alert alert-info"

    Exemplo de uso:
      python manage.py replace_code --help

      python manage.py replace_code --list
      Obs: Lista as configurações disponíveis em suap/comum/management/commands/replace_codes.

      python manage.py replace_code --config 0001 --simulate
      Obs: Tanto faz informar 0001 ou 1.

      python manage.py replace_code --config 0001
      Obs: Aqui vai ser aplicado de fato as alterações definidas no arquivo 0001.

      python manage.py replace_code --config /home/my/full/path/replace_code.yaml --simulate

      python manage.py replace_code --config replace_code.yaml --simulate
      Obs: Nesse caso o arquivo "replace_code.yaml" deve estar na pasta raiz do suap.

      python manage.py replace_code --simulate
      Obs: Nesse caso será buscado o arquivo "replace_code.yaml" na pasta raiz do suap.
    """

    def create_parser(self, *args, **kwargs):
        parser = super().create_parser(*args, **kwargs)
        # Ajuste necessário para exibir o help de maneira legal no console.
        # python manage.py replace_code --help
        parser.formatter_class = RawTextHelpFormatter
        return parser

    def add_arguments(self, parser):
        parser.add_argument('--list', action='store_true', help='Lista os arquivos YAML disponíveis e sai.')
        parser.add_argument('--simulate', action='store_true', help='Executa em modo simulação (sem modificar os arquivos).')
        parser.add_argument(
            '--config', type=str, default='replace_code.yaml', help='Número (ex: 1 ou 0001) ou caminho para o arquivo YAML com os mapeamentos.'
        )

        log_file_suffix = datetime.now().strftime('%Y-%m-%d_%Hh%Mmin%Ss')
        log_file_name_default = f'replace_code_{log_file_suffix}.log'
        parser.add_argument('--logfile', type=str, default=log_file_name_default, help='Nome do arquivo de log.')

    def handle(self, *args, **options):
        # Criando um método interno para facilitar a geração do log tanto via console como em arquivo.
        def log(msg, title=False):
            if title:
                msg = '\n' + len(msg) * '-' + '\n' + msg + '\n' + len(msg) * '-'
            self.stdout.write(msg)
            self.log_entries.append(msg)

        replace_code_yaml_base_dir = os.path.join(os.path.dirname(__file__), 'replace_codes')

        if options.get('list'):
            arquivos = sorted(glob.glob(os.path.join(replace_code_yaml_base_dir, '????_*.yaml')))
            if not arquivos:
                self.stdout.write('Nenhum arquivo encontrado na pasta replace_codes.')
            else:
                self.stdout.write('Arquivos disponíveis:')
                for arq in arquivos:
                    self.stdout.write('  - ' + os.path.basename(arq))
            return
        simulate = options['simulate']
        config_path = options['config']
        log_path = options['logfile']

        if simulate:
            base, ext = os.path.splitext(log_path)
            log_path = f'{base}_simulacao{ext}'

        self.log_entries = []
        global_stats = {
            'total_arquivos_modificados': 0,
            'total_substituicoes': 0,
            'substituicoes_por_padrao': defaultdict(lambda: defaultdict(int)),
            'mapa_de_para': defaultdict(dict),
        }

        if config_path.isdigit():
            pattern = os.path.join(replace_code_yaml_base_dir, f'{int(config_path):04d}_*.yaml')
            arquivos = glob.glob(pattern)
            if not arquivos:
                self.stderr.write(self.style.ERROR(f'Nenhum arquivo encontrado para o número {config_path} em replace_codes/.'))
                self.stdout.write('Opções disponíveis:')
                todos = sorted(glob.glob(os.path.join(replace_code_yaml_base_dir, '????_*.yaml')))
                for caminho in todos:
                    self.stdout.write('  - ' + os.path.basename(caminho))
                return
            config_path = arquivos[0]

        if not os.path.exists(config_path):
            self.stderr.write(self.style.ERROR(f'Arquivo de configuração não encontrado: {config_path}'))
            return

        with open(config_path, encoding='utf-8') as f:
            config = yaml.safe_load(f)

        for extensao, extension_mappings in config.items():
            if isinstance(extension_mappings, dict):
                for antigo, novo in extension_mappings.items():
                    global_stats['mapa_de_para'][extensao][antigo] = novo

        base_dir = os.getcwd()
        log(f'Arquivo de configuração: {config_path}')
        log(f'Varredura em: {base_dir}\n')
        log(f'Início da varredura: {datetime.now()}\n')
        log(f'Modo de execução: {"SIMULAÇÃO" if simulate else "REAL"}\n')

        arquivos_modificados = {}

        for root, _, files in os.walk(base_dir):
            for file in files:
                caminho = os.path.join(root, file)
                extensao = os.path.splitext(file)[1][1:]
                extension_mappings = config.get(extensao)
                if isinstance(extension_mappings, dict):
                    count, detalhes = self.processar_arquivo(caminho, extension_mappings, log, simulate, global_stats, extensao)
                    if count > 0:
                        arquivos_modificados[caminho] = {'total': count, 'detalhes': detalhes}

        log('Resumo de Alterações', title=True)
        if not arquivos_modificados:
            log('  Nenhuma alteração realizada.')
        else:
            for arquivo, info in arquivos_modificados.items():
                log(f'{arquivo} — {info["total"]} substituições')
                for detalhe in info['detalhes']:
                    log(f'  Linha {detalhe["linha"]}:')
                    log(f'    - {detalhe["antes"]}')
                    log(f'    + {detalhe["depois"]}')

        log('Estatísticas Totais', title=True)
        log(f'Total de arquivos modificados: {global_stats["total_arquivos_modificados"]}')
        log(f'Total de substituições realizadas: {global_stats["total_substituicoes"]}')
        log('Substituições por padrão:')
        log(f'  ({config_path})')

        log('  \nCompleto:')
        for extensao, padroes in global_stats['mapa_de_para'].items():
            log(f'  {extensao}:')
            for padrao_antigo, padrao_novo in padroes.items():
                qtd = global_stats['substituicoes_por_padrao'].get(extensao).get(padrao_antigo, 0)
                log(f"    '{padrao_antigo}'  alterado para  '{padrao_novo}': {qtd}")

        log('  \nResumido (maiores quantidades primeiro):')
        for extensao, padroes in global_stats['substituicoes_por_padrao'].items():
            log(f'  {extensao}:')
            for padrao, qtd in sorted(padroes.items(), key=lambda x: -x[1]):
                novo_valor = global_stats['mapa_de_para'][extensao].get(padrao, '???')
                log(f"    '{padrao}'  alterado para  '{novo_valor}': {qtd}")

        log(f'\nModo de execução: {"SIMULAÇÃO" if simulate else "REAL"}')
        log(f'\nFim da varredura: {datetime.now()}')

        try:
            with open(log_path, 'w', encoding='utf-8') as log_file:
                log_file.write('\n'.join(self.log_entries))
            self.stdout.write(self.style.NOTICE(f'Log salvo em: {log_path}'))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Erro ao salvar log: {e}'))

    def processar_arquivo(self, caminho, extension_mappings, log, simulate, global_stats, extensao):
        log(f'Analisando arquivo {caminho}...')
        try:
            with open(caminho, encoding='utf-8') as f:
                linhas = f.readlines()
        except Exception as e:
            log(f'[ERRO] Falha ao ler {caminho}: {e}')
            return 0, []

        alteracoes = 0
        novo_conteudo = []
        detalhes = []

        for idx, linha in enumerate(linhas):
            linha_original = linha
            linha_modificada = linha
            for antigo, novo in extension_mappings.items():
                if antigo in linha_modificada:
                    ocorrencias = linha_modificada.count(antigo)
                    linha_modificada = linha_modificada.replace(antigo, novo)
                    global_stats['substituicoes_por_padrao'][extensao][antigo] += ocorrencias
                    global_stats['total_substituicoes'] += ocorrencias
            if linha_modificada != linha_original:
                alteracoes += 1
                detalhes.append({'linha': idx + 1, 'antes': linha_original.strip(), 'depois': linha_modificada.strip()})
            novo_conteudo.append(linha_modificada)

        if alteracoes > 0:
            global_stats['total_arquivos_modificados'] += 1
            if not simulate:
                try:
                    with open(caminho, 'w', encoding='utf-8') as f:
                        f.writelines(novo_conteudo)
                except Exception as e:
                    log(f'[ERRO] Falha ao salvar {caminho}: {e}')
                    return 0, []

        return alteracoes, detalhes
