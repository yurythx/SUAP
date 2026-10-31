import datetime
import subprocess

from celery.exceptions import SoftTimeLimitExceeded
from celery.signals import before_task_publish, task_prerun
from celery.utils.log import get_task_logger

from suap import celery_app as app

from .models import ResultadoExecucao

logger = get_task_logger(__name__)

# Constantes para maior clareza e fácil manutenção
SECONDS_IN_HOUR = 3600
TASK_SOFT_TIME_LIMIT_HOURS = 22
TASK_HARD_TIME_LIMIT_HOURS = 23

DEFAULT_BEAT_TASK_KWARGS = {
    'autoretry_for': (Exception,),
    'retry_kwargs': {'max_retries': 0},
    'max_retries': 0,
    'default_retry_delay': 60,
    'soft_time_limit': TASK_SOFT_TIME_LIMIT_HOURS * SECONDS_IN_HOUR,
    'time_limit': TASK_HARD_TIME_LIMIT_HOURS * SECONDS_IN_HOUR,
}


def run_command_with_capture(command_name, *args, timeout=None, **kwargs):
    """
    Executa um comando de gerenciamento do Django e captura sua saída,
    com suporte a timeout.

    :param command_name: O nome do comando Django.
    :param args: Argumentos posicionais para o comando.
    :param timeout: Tempo limite em segundos para a execução do comando.
    :param kwargs: Argumentos nomeados (opções) para o comando.
    :return: Uma tupla (stdout, stderr).
    :raises subprocess.TimeoutExpired: Se o comando exceder o tempo limite.
    :raises subprocess.CalledProcessError: Se o comando retornar um código de erro.
    """

    # Prepara a lista de argumentos para o subprocess.run
    # Isso é necessário se você quiser ter controle granular ou usar subprocess diretamente
    # No entanto, django.core.management.call_command já lida com muitos detalhes
    # Para timeout, precisamos usar subprocess.run diretamente ou passar o timeout para ele

    # Se você usar django.core.management.call_command, ele não tem um argumento de timeout.
    # Teremos que simular isso com subprocess.run para ter controle de timeout.

    command = ['python', 'manage.py', command_name]
    command.extend([str(arg) for arg in args])

    # Converte os kwargs em argumentos de linha de comando (--key=value)
    for key, value in kwargs.items():
        if len(key) == 1:  # Single-letter options, e.g., -v
            command.append(f'-{key}')
        else:  # Long options, e.g., --verbosity
            command.append(f'--{key}={value}')

    # Usamos subprocess.run para ter o controle do timeout e captura de saída robusta
    process = subprocess.run(
        command,
        capture_output=True,
        text=True,  # Decodifica stdout/stderr como texto
        check=True,  # Lança CalledProcessError se o comando falhar
        timeout=timeout,  # Adiciona o timeout aqui!
    )
    return process.stdout, process.stderr


@before_task_publish.connect
def pre_publish_hook(sender=None, headers=None, body=None, **options):
    """
    Esta função será executada no processo que publica a tarefa (Celery Beat, neste caso).
    """
    task_name = sender  # O nome da tarefa que está sendo publicada
    args = body[0]  # Os argumentos posicionais da tarefa
    kwargs = body[1]  # Os argumentos de palavra-chave da tarefa

    # Exemplo de lógica de pré-processamento:
    # Você pode acessar e até modificar os argumentos da tarefa aqui, se necessário.
    # Por exemplo, adicionar um timestamp ou um ID de rastreamento.
    if task_name in ['beat.tasks.call_command', 'beat.tasks.execute_bash_script']:
        resultado_execucao = ResultadoExecucao.objects.create(
            command_name=args[0],
            args=str(args[1:]),
            kwargs=str(kwargs),
            status=ResultadoExecucao.STATUS_PENDING,
        )
        body[1]['_resultado_execucao_id'] = resultado_execucao.id
        logger.info(f"Executando lógica específica para '{task_name}' antes de publicar.")
        # Exemplo: Adicionar um novo argumento ou modificar um existente
        # headers['custom_header'] = 'valor_personalizado' # Adicionar um cabeçalho
        # body[0].append("novo_dado_adicionado_no_pre_publish") # Modificar args


@task_prerun.connect
def pre_run_hook(task_id=None, task=None, args=None, kwargs=None, **options):
    """
    Esta função será executada no processo que executa a tarefa (o worker Celery).
    """
    # Aqui você pode acessar o ID da tarefa, os argumentos e os kwargs
    # e realizar ações antes da execução da tarefa.
    if task.name in ['beat.tasks.call_command', 'beat.tasks.execute_bash_script']:
        resultado_execucao_id = kwargs.get('_resultado_execucao_id', None)
        if resultado_execucao_id:
            resultado_execucao = ResultadoExecucao.objects.filter(id=resultado_execucao_id).first()
            if resultado_execucao:
                resultado_execucao.task_id = task_id
                resultado_execucao.save()
                logger.info(f'Tarefa {task.name} ({task_id}) iniciada com ID de execução {resultado_execucao.id}.')


@app.task(**DEFAULT_BEAT_TASK_KWARGS)
def execute_bash_script(script_path, *args, **kwargs):
    """
    Uma tarefa genérica que executa um script bash.
    """
    result = ResultadoExecucao.objects.filter(id=kwargs.pop('_resultado_execucao_id', 0)).first()
    if not result:
        # Se não houver um resultado de execução associado, cria um novo
        result = ResultadoExecucao.objects.create(
            command_name=script_path,
            args=str(args),
            kwargs=str(kwargs),
            status=ResultadoExecucao.STATUS_RUNNING,
        )
    else:
        result.status = ResultadoExecucao.STATUS_RUNNING
        result.save()

    # Obtenha o timeout dos kwargs, com um valor padrão se não for fornecido
    timeout = kwargs.get('timeout')
    if timeout is not None:
        try:
            timeout = int(timeout)
            if timeout <= 0:
                raise ValueError('Timeout deve ser um número inteiro positivo.')
        except ValueError, TypeError:
            msg = f"Erro: O valor de 'timeout' em kwargs é inválido: {kwargs.get('timeout')}. Deve ser um número inteiro positivo."
            logger.warning(msg)
            result.datetime_end = datetime.datetime.now()
            result.stderr = msg
            result.status = ResultadoExecucao.STATUS_FAILED
            result.save()
            raise ValueError(msg)

    try:
        command = [script_path]
        if args:
            command = command + list(args)

        logger.info(f'Executando o script: {script_path} com argumentos: {args}')
        # subprocess.run é a forma moderna e segura de executar comandos
        response = subprocess.run(
            command,
            capture_output=True,  # Captura a saída padrão e de erro
            text=True,  # Decodifica a saída como texto (UTF-8)
            check=True,  # Lança uma exceção se o script retornar um código de erro
            timeout=timeout,  # Define o timeout se fornecido
        )
        result.datetime_end = datetime.datetime.now()
        result.stdout = response.stdout
        result.stderr = response.stderr
        result.status = ResultadoExecucao.STATUS_SUCCESS
        result.save()
        return f"Script '{script_path}' executado com sucesso. Saída: {response.stdout.strip()}"
    except FileNotFoundError:
        msg = f"Erro: O script '{script_path}' não foi encontrado."
        logger.warning(msg, exc_info=True)
        result.datetime_end = datetime.datetime.now()
        result.stderr = msg
        result.status = ResultadoExecucao.STATUS_FAILED
        result.save()
        raise
    except subprocess.CalledProcessError as e:
        # Este erro ocorre se check=True e o script falhar (exit code != 0)
        msg = f"Erro ao executar o script '{script_path}': {e}\nSaída padrão: {e.stdout}\nSaída de erro: {e.stderr}"
        logger.warning(msg, exc_info=True)
        result.datetime_end = datetime.datetime.now()
        result.stderr = msg
        result.status = ResultadoExecucao.STATUS_FAILED
        result.save()
        raise
    except subprocess.TimeoutExpired as e:
        msg = (
            f"Erro: O script '{script_path}' excedeu o tempo limite de {timeout} segundos."
            f'\nSaída padrão capturada até o momento: {e.stdout}'
            f'\nSaída de erro capturada até o momento: {e.stderr}'
        )
        logger.warning(msg, exc_info=True)
        result.datetime_end = datetime.datetime.now()
        result.stderr = msg
        result.status = ResultadoExecucao.STATUS_TIMEOUT
        result.save()
        raise


@app.task(**DEFAULT_BEAT_TASK_KWARGS)
def call_command(command_name, *args, **kwargs):
    """
    Uma tarefa genérica para executar qualquer comando de gerenciamento do Django.

    :param command_name: O nome do comando a ser executado (ex: 'clearsessions').
    :param args: Argumentos posicionais para o comando.
    :param kwargs: Argumentos nomeados (opções) para o comando (ex: '--verbosity=0').
    """
    # Extrai o timeout dos kwargs. Remove ele para não ser passado como argumento do comando Django
    timeout_value = kwargs.pop('timeout', None)

    result = ResultadoExecucao.objects.filter(id=kwargs.pop('_resultado_execucao_id', 0)).first()
    if not result:
        # Se não houver um resultado de execução associado, cria um novo
        result = ResultadoExecucao.objects.create(
            command_name=command_name,
            args=str(args),
            kwargs=str(kwargs),
            status=ResultadoExecucao.STATUS_RUNNING,
        )
    else:
        result.status = ResultadoExecucao.STATUS_RUNNING
        result.save()

    # Validação do timeout
    if timeout_value is not None:
        try:
            timeout_value = int(timeout_value)
            if timeout_value <= 0:
                raise ValueError('Timeout deve ser um número inteiro positivo.')
        except ValueError, TypeError:
            msg = f"Erro: O valor de 'timeout' em kwargs é inválido: {timeout_value}. Deve ser um número inteiro positivo."
            logger.warning(msg)
            result.datetime_end = datetime.datetime.now()
            result.stderr = msg
            result.status = ResultadoExecucao.STATUS_FAILED
            result.save()
            raise ValueError(msg)  # A tarefa falhará no Celery

    try:
        logger.info(f'Executando o comando Django: {command_name}')
        stdout_output, stderr_output = run_command_with_capture(command_name, *args, **kwargs, timeout=timeout_value)
        result.datetime_end = datetime.datetime.now()
        result.stdout = stdout_output
        result.stderr = stderr_output
        result.status = ResultadoExecucao.STATUS_SUCCESS
        result.save()
        logger.info(f"Comando '{command_name}' executado com sucesso.")
        return f"Comando '{command_name}' executado com sucesso."
    except subprocess.CalledProcessError as e:
        msg = f"Erro ao executar o comando '{command_name}': {e}\nSaída padrão: {e.stdout}\nSaída de erro: {e.stderr}"
        logger.warning(msg, exc_info=True)
        result.datetime_end = datetime.datetime.now()
        result.stdout = e.stdout
        result.stderr = e.stderr
        result.status = ResultadoExecucao.STATUS_FAILED
        result.save()
        raise
    except subprocess.TimeoutExpired as e:
        msg = (
            f"Erro: O comando '{command_name}' excedeu o tempo limite de {timeout_value} segundos."
            f'\nSaída padrão capturada até o momento: {e.stdout}'
            f'\nSaída de erro capturada até o momento: {e.stderr}'
        )
        logger.warning(msg, exc_info=True)
        result.datetime_end = datetime.datetime.now()
        result.stdout = e.stdout
        result.stderr = e.stderr
        result.status = ResultadoExecucao.STATUS_TIMEOUT
        result.save()
        raise
    except SoftTimeLimitExceeded:
        msg = f"Erro: O comando '{command_name}' excedeu o limite de tempo do Celery."
        logger.warning(msg, exc_info=True)
        result.datetime_end = datetime.datetime.now()
        result.stderr = msg
        result.status = ResultadoExecucao.STATUS_TIMEOUT
        result.save()
        raise
    except Exception as e:
        msg = f"Erro ao executar o comando '{command_name}': {e}"
        logger.warning(msg, exc_info=True)
        result.datetime_end = datetime.datetime.now()
        result.stderr = msg
        result.status = ResultadoExecucao.STATUS_FAILED
        result.save()
        raise
