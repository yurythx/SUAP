import time

from demandas.models import AnalistaDesenvolvedor
from djtools.assincrono import task


@task('Criar/Atualizar Container')
def criar_atualizar_container(ambiente, url, task=None):
    i = 0
    ambiente.criar_atualizar_container()
    task.start_progress()
    time.sleep(5)
    # 30 min for gitlab create the container
    while i < 120:
        i += 1
        status = ambiente.get_status_container()
        task.update_progress(status[0])
        time.sleep(15)
        if status[0] == 100:
            task.finalize(f'Container criado com sucesso. A senha de acesso é: {ambiente.senha}', url)
            return
        elif status[0] == -1:
            task.finalize(status[1], error=True)
            return
    task.finalize(f'Problema ao criar container. ({status[1]})', url, error=True)


@task('Criar/Atualizar IDE')
def criar_atualizar_ide(analista, url, task=None):
    i = 0
    analista.criar_atualizar_ide()
    task.start_progress()
    time.sleep(5)
    # 5 min for gitlab create the IDE
    while i < 20:
        i += 1
        log = analista.get_log_ide_cricao_atualizacao_ide()
        task.update_progress(50)
        time.sleep(15)
        senha = analista.get_senha_ide()
        if senha:
            AnalistaDesenvolvedor.filter(id=analista.id).update(senha_id=senha)
            task.finalize(f'IDE criada com sucesso. A senha de acesso é: {senha}', url)
            return
        elif 'Job succeeded' in log or 'Job failed' in log:
            task.finalize(100, error=True)
            return
    task.finalize('Problema ao criar IDE.', url, error=True)
