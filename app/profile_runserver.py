import cProfile
import os
import sys

# Adicione o diretório do projeto ao caminho de busca do Python
# Isso é útil caso você esteja em um subdiretório
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Importa a função de gerenciamento do Django
# **********************************************
# **** ADICIONE ESTAS LINHAS DE CONFIGURAÇÃO ****
# **********************************************
from django.conf import settings
from django.core.management import execute_from_command_line

# Verifica se as configurações já foram carregadas
if not settings.configured:
    # Defina o nome do seu arquivo de configurações aqui.
    # Exemplo: 'meu_projeto.settings'
    # Substitua 'NOME_DO_SEU_PROJETO' pelo nome real do diretório que contém seu settings.py
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'suap.settings')
# **********************************************

# Caminho do arquivo para o relatório de profiling
profiling_file = 'startup.prof'


# Função para executar o comando runserver
def run_server():
    # Simula a chamada da linha de comando
    # Pode passar argumentos como --noreload se desejar
    execute_from_command_line(['manage.py', 'run', '--noreload'])


# Executa o profiling
cProfile.run('run_server()', profiling_file)

sys.stdout.write(f'Relatório de profiling salvo em: {profiling_file}\n')
sys.stdout.flush()
