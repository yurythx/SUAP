import threading
import time
import traceback

from django.http import HttpResponseRedirect
from sentry_sdk import set_context

from djtools.middleware import threadlocals as tl
from suap import celery_app as app


@app.task
def error_handler(request, exc, traceback, task_uuid=None, url='..'):
    from djtools.models import Task

    task = Task.objects.filter(uuid=task_uuid).first() if task_uuid else None
    if task:
        task.finalize(traceback, url, error=True)


@app.task
def execute_task(module_name, func_name, *args, **kwargs):
    module = __import__(module_name, fromlist=module_name.split('.'))
    funcao_decorada = getattr(module, func_name)
    funcao_decorada.executar_de_dentro_da_fila(*args, **kwargs)


class Thread(threading.Thread):
    def __init__(self, task=None, targs=None, tkwargs=None, request=None, path='..', *args, **kwargs):
        self._task = task
        self._targs = targs or ()
        self._tkwargs = tkwargs or {}
        self._target = kwargs['target']
        self._request = request
        self._path = path
        super().__init__(*args, **kwargs)

    def run(self):
        try:
            tl.context.request = self._request
            self._target(*self._targs, **self._tkwargs)
        except BaseException:
            self._task.finalize(traceback.format_exc(), self._path, error=True)


def _criar_decorate_suap(func, name, queues):
    """Chamada direta (fora da fila): serializa os argumentos e enfileira via Celery."""

    def decorate_suap(*args, **kwargs):
        from djtools.models import Task
        from djtools.utils import serialization

        request = tl.get_request()
        user = None
        path = ''
        if request:
            if request.user and not request.user.is_anonymous:
                user = request.user
            path = request.get_full_path()
        tarefa = Task.objects.create(type=name, user=user)
        kwargs['task'] = tarefa

        args = [serialization.serialize(arg) for arg in args]
        all_args = [func.__module__, func.__name__]
        func_qual_name = '.'.join(all_args)
        all_args.extend(args)

        queue = 'geral'
        for key, value in queues.items():
            if func_qual_name == key:
                queue = value

        new_kwargs = {}
        for key, value in list(kwargs.items()):
            new_kwargs[key] = serialization.serialize(value)
        new_kwargs['__path'] = path
        new_kwargs['__request'] = serialization.serialize(request)
        tarefa.save()
        retorno = execute_task.apply_async(
            args=tuple(all_args), kwargs=new_kwargs, link_error=error_handler.s(task_uuid=tarefa.uuid, url=path), queue=queue
        )
        tarefa.celery_uuid = retorno.id
        tarefa.celery_queue = queue
        tarefa.save()
        return HttpResponseRedirect(f'/djtools/process/{tarefa.uuid}/')

    return decorate_suap


def _criar_decorate_celery(func):
    """Só deve ser invocada por `execute_task`: os argumentos já chegam serializados pela fila."""

    def decorate_celery(*args: object, **kwargs: object) -> None:
        from djtools.utils import serialization

        deserialized_args = (serialization.deserialize(arg) for arg in args)
        new_kwargs = {}
        path = kwargs.pop('__path', '')
        request = serialization.deserialize(kwargs.pop('__request', 'null'))
        for key, value in list(kwargs.items()):
            new_kwargs[key] = serialization.deserialize(value)
        attempts = 0
        # force deserialize
        while attempts < 10:
            if 'task' in new_kwargs and new_kwargs['task'] is None:
                new_kwargs['task'] = serialization.deserialize(kwargs['task'])
            else:
                break
            attempts += 1
            time.sleep(1)
        task = new_kwargs.get('task')
        try:
            tl.context.user = request and request.user or getattr(task, 'user', None)
            tl.context.request = request
            func(*deserialized_args, **new_kwargs)
        except Exception as e:
            set_context('request', {'user': str(getattr(task, 'user', None)), 'task_id': getattr(task, 'id', None), 'path': path})
            raise e
        return None

    return decorate_celery


def _criar_decorate_thread(func, name):
    def decorate_thread(*args, **kwargs):
        from djtools.models import Task
        from djtools.utils import running_tests

        user = tl.get_user()
        if user and user.is_anonymous:
            user = None
        request = tl.get_request()
        path = ''
        if request:
            if request.user and not request.user.is_anonymous:
                user = request.user
            path = request.get_full_path()
        tarefa = Task.objects.create(type=name, user=user)
        kwargs['task'] = tarefa
        if running_tests():
            func(*args, **kwargs)
        else:
            Thread(target=func, task=tarefa, targs=args, request=request, tkwargs=kwargs, path=path).start()
        return HttpResponseRedirect(f'/djtools/process/{tarefa.uuid}/')

    return decorate_thread


# Decorator
def task(name, method=None):
    def assincrono(func):
        from django.conf import settings

        use_celery = getattr(settings, 'USE_CELERY', False)
        queues = getattr(settings, 'TASK_QUEUES_CELERY', {})

        if use_celery and method != 'thread':
            retorno = _criar_decorate_suap(func, name, queues)
            # Chamada direta de código de aplicação (fora da fila) sempre enfileira,
            # mesmo quando o processo em execução é um worker Celery: um worker que
            # invoca esta função por uma chamada Python comum (ex.: dentro de um
            # signal disparado por outra task) não está recebendo os argumentos já
            # serializados que só `execute_task` entrega. Só o próprio `execute_task`
            # deve rodar a versão que desserializa.
            retorno.executar_de_dentro_da_fila = _criar_decorate_celery(func)
        else:
            retorno = _criar_decorate_thread(func, name)

        return retorno

    return assincrono
